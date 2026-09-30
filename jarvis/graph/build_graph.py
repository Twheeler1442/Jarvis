"""Build dashboard/graph.json from the node registry, and lint the roster.

The registry is the single source of truth. Code, map, and docs read the same
file. If a tool is not in registry.json, it does not exist.

    python -m jarvis.graph.build_graph          # write dashboard/graph.json
    python -m jarvis.graph.build_graph --check  # lint only, exit 1 on failure
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REGISTRY = HERE / "registry.json"
OUT = ROOT / "dashboard" / "graph.json"
HUD = ROOT / "hud" / "graph.json"
VAULT = ROOT / "vault"

STATUS_COLOR = {"live": "#3dcc6a", "wired": "#d7b056", "planned": "#5b6478", "denied": "#e2725b"}

# What an agent is allowed to reach, weakest first.
CEILING_RANK = {"read": 0, "vault": 1, "propose": 2, "device": 3, "external": 4}

# What holding a tool of each class demands of its owner's ceiling. Separate
# from CEILING_RANK because the two vocabularies only look alike: `propose` is
# a ceiling and never a tool class, `write` is a class and never a ceiling.
CLASS_NEED = {"read": 0, "vault": 1, "write": 1, "device": 3, "external": 4}

CHANGES_THE_WORLD = {"write", "device", "external"}

# Classes where a second holder means a second copy of the key. Read and
# write tools are legitimately shared (five agents write into the vault, and
# the path lock in the tool is what confines them). A device or external tool
# is the send key, and the send key has exactly one holder.
SOLE_OWNER_CLASSES = {"device", "external"}


def load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# lint: the map is not decoration, it is the permission model
# --------------------------------------------------------------------------

def _duplicate_ids(reg: dict) -> list[str]:
    """Two rows with one id is not a typo, it is a silent override.

    Every collection here is keyed by id elsewhere in this file, last row
    winning. A second `write_file` row declaring itself unGated and owned by
    Research therefore replaced the real one and linted clean, because by the
    time any check ran there was only ever one of them.
    """
    errors = []
    for section in ("clusters", "agents", "tools", "connectors", "clients", "gestures", "strands"):
        seen: set[str] = set()
        for row in reg.get(section, []):
            rid = row.get("id")
            if rid in seen:
                errors.append(f"{section}: duplicate id {rid}. one row silently overrides the other")
            seen.add(rid)
    return errors


def lint(reg: dict) -> list[str]:
    errors: list[str] = _duplicate_ids(reg)
    agents = {a["id"]: a for a in reg["agents"]}
    tools = {t["id"]: t for t in reg["tools"]}
    clusters = {c["id"] for c in reg["clusters"]}

    for agent in reg["agents"]:
        aid = agent["id"]
        if agent["cluster"] not in clusters:
            errors.append(f"{aid}: unknown cluster {agent['cluster']}")
        if not agent.get("done"):
            errors.append(f"{aid}: no definition of done")
        if not agent.get("eval"):
            errors.append(f"{aid}: no eval. an agent without an eval is a rumor")
        if not agent.get("never"):
            errors.append(f"{aid}: empty ban list")
        if agent.get("checkpointer") and agent["type"] != "supervisor":
            errors.append(f"{aid}: specialist has a checkpointer. interrupts will not bubble up")
        for tid in agent.get("owns", []):
            if tid not in tools:
                errors.append(f"{aid}: owns unknown tool {tid}")

    # the owner claims its tool, the class is a real class, and the gate is a
    # real boolean. `"gate": "no"` is truthy, and a truthy string read as a
    # boolean is how a tool stops stopping.
    for tid, tool in tools.items():
        owner = tool["owner"]
        cls = tool.get("class")
        if cls not in CLASS_NEED:
            errors.append(f"{tid}: unknown class {cls!r}. expected one of {sorted(CLASS_NEED)}")
        if not isinstance(tool.get("gate"), bool):
            errors.append(f"{tid}: gate must be true or false, got {tool.get('gate')!r}")
        if owner not in agents:
            errors.append(f"{tid}: owner {owner} is not an agent")
            continue
        if tool["status"] != "denied" and tid not in agents[owner].get("owns", []):
            errors.append(f"{tid}: owned by {owner} on the map but not in its tool list")
        if cls in CHANGES_THE_WORLD and not tool.get("gate"):
            errors.append(f"{tid}: {cls} tool with no confirm gate")

    # the send key has exactly one holder
    for tid, tool in tools.items():
        if tool.get("class") not in SOLE_OWNER_CLASSES:
            continue
        holders = [a["id"] for a in reg["agents"] if tid in a.get("owns", [])]
        if len(holders) > 1:
            errors.append(
                f"{tid}: {tool['class']} tool held by {len(holders)} agents "
                f"({', '.join(sorted(holders))}). the send key has one holder")

    # no agent may hold a tool that reaches past its ceiling
    for agent in reg["agents"]:
        if agent["ceiling"] not in CEILING_RANK:
            errors.append(f"{agent['id']}: unknown ceiling {agent['ceiling']!r}")
        ceiling = CEILING_RANK.get(agent["ceiling"], 0)
        for tid in agent.get("owns", []):
            tool = tools.get(tid)
            if not tool:
                continue
            # An unknown class is treated as the most dangerous, so a typo
            # cannot buy a tool more reach than it declared.
            need = CLASS_NEED.get(tool.get("class"), max(CLASS_NEED.values()))
            if need > ceiling:
                errors.append(f"{agent['id']}: ceiling {agent['ceiling']} cannot hold {tid} ({tool.get('class')})")

    # supervisor sanity
    supervisors = [a for a in reg["agents"] if a["type"] == "supervisor"]
    if len(supervisors) != 1:
        errors.append(f"expected exactly one supervisor, found {len(supervisors)}")
    elif not supervisors[0].get("checkpointer"):
        errors.append("supervisor has no checkpointer. there is no conversation memory")

    # connectors: the doorway is a node too, and a door is not a way around
    # the ceiling of the agent that opens it
    for co in reg.get("connectors", []):
        owner = agents.get(co["owner"])
        if owner is None:
            errors.append(f"{co['id']}: owner {co['owner']} is not an agent")
        for tid in co.get("provides", []):
            if tid not in tools:
                errors.append(f"{co['id']}: provides unknown tool {tid}")
                continue
            if co["status"] == "denied" and tools[tid]["status"] in {"live", "wired"}:
                errors.append(f"{co['id']}: connector denied but {tid} is {tools[tid]['status']}")
            if owner is None or co["status"] == "denied":
                # A denied door delivers nothing, so it may name a tool that
                # no agent is allowed to hold yet: that is what denied means.
                # These checks bite the moment you try to open it, which is
                # exactly when the ownership question has to be answered.
                continue
            if tid not in owner.get("owns", []):
                errors.append(
                    f"{co['id']}: hands {tid} to {owner['id']}, which does not own it. "
                    f"a door may only deliver tools its owner already declares")
            need = CLASS_NEED.get(tools[tid].get("class"), max(CLASS_NEED.values()))
            if need > CEILING_RANK.get(owner["ceiling"], 0):
                errors.append(
                    f"{co['id']}: delivers {tid} ({tools[tid].get('class')}) to {owner['id']}, "
                    f"whose ceiling is {owner['ceiling']}")
        if not co.get("cap"):
            errors.append(f"{co['id']}: no cap. a connector without a written cap is an open door")

    # clients: a surface declares what it may approve as a list the bridge can
    # actually compare, not as a sentence of prose. `may_approve: []` is the
    # unattended surface. Prose stays in `gate` for humans to read.
    for cli in reg.get("clients", []):
        if not cli.get("thread"):
            errors.append(f"{cli['id']}: no thread_id")
        if not cli.get("gate"):
            errors.append(f"{cli['id']}: no gate policy in prose")
        approves = cli.get("may_approve")
        if not isinstance(approves, list):
            errors.append(f"{cli['id']}: may_approve must be a list of tool classes, "
                          f"got {approves!r}")
            continue
        for cls in approves:
            if cls not in CLASS_NEED:
                errors.append(f"{cli['id']}: may_approve names unknown class {cls!r}")
        if cli.get("attended") is False and approves:
            errors.append(f"{cli['id']}: unattended surface may approve {approves}. "
                          f"nobody is there to answer a gate")

    # gestures: an input modality may stop things, never authorize them.
    # Declared as booleans, because `binds` is free text and "confirm the
    # pending write" does not contain the substring "approve".
    gestures = reg.get("gestures", [])
    if not gestures:
        errors.append("gestures: none declared. a hands-on surface needs a HALT gesture")
    if gestures and not any(g.get("halts") for g in gestures):
        errors.append("gestures: no gesture with halts: true. every hands-on surface needs one")
    for g in gestures:
        if g.get("authorizes"):
            errors.append(f"{g['id']}: authorizes must be false. "
                          f"gestures reject, humans approve")
        if not isinstance(g.get("authorizes"), bool):
            errors.append(f"{g['id']}: must declare authorizes: false explicitly")

    for strand in reg["strands"]:
        for member in strand["members"]:
            if member not in agents:
                errors.append(f"{strand['id']}: unknown member {member}")

    return errors


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def vault_nodes() -> list[dict]:
    nodes = []
    if not VAULT.exists():
        return nodes
    for path in sorted(VAULT.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".txt", ".json", ".csv"}:
            rel = str(path.relative_to(VAULT))
            nodes.append({
                "id": f"file:{rel}",
                "name": path.name,
                "type": "file",
                "group": "vault",
                "status": "live",
                "val": 4,
                "detail": f"vault/{rel} ({path.stat().st_size} bytes)",
            })
    return nodes


def build(reg: dict) -> dict:
    nodes: list[dict] = []
    links: list[dict] = []
    agents = {a["id"]: a for a in reg["agents"]}

    nodes.append({
        "id": "core", "name": "SECOND BRAIN", "type": "core", "group": "core",
        "status": "live", "val": 30,
        "detail": "The house brain. Only mouth. Routes work. Holds no send keys itself.",
    })

    counts = {c["id"]: 0 for c in reg["clusters"]}
    for agent in reg["agents"]:
        counts[agent["cluster"]] += 1 + len(agent.get("owns", []))

    for cluster in reg["clusters"]:
        nodes.append({
            "id": cluster["id"], "name": cluster["name"], "type": "cluster", "group": "clusters",
            "status": "live", "val": 14, "count": counts[cluster["id"]],
            "color": cluster["color"], "detail": cluster["detail"],
        })
        links.append({"source": "core", "target": cluster["id"], "kind": "contains"})

    for agent in reg["agents"]:
        nodes.append({
            "id": agent["id"], "name": agent["name"],
            "type": agent["type"], "group": "agents",
            "status": agent["status"], "val": 16 if agent["type"] == "supervisor" else 11,
            "ceiling": agent["ceiling"], "model": agent["model"],
            "detail": agent["done"],
            "never": agent.get("never", []),
            "eval": agent.get("eval", ""),
        })
        links.append({"source": agent["cluster"], "target": agent["id"], "kind": "holds"})
        for callee in agent.get("calls", []):
            if callee in agents:
                links.append({"source": agent["id"], "target": callee, "kind": "delegates"})

    for tool in reg["tools"]:
        nodes.append({
            "id": f"tool:{tool['id']}", "name": tool["name"], "type": "tool", "group": "tools",
            "status": tool["status"], "val": 5,
            "gate": tool["gate"], "cls": tool["class"],
            "detail": f"{tool['class']} · owner {tool['owner']} · gate {'yes' if tool['gate'] else 'no'} · {tool['detail']}",
        })
        links.append({"source": tool["owner"], "target": f"tool:{tool['id']}", "kind": "owns"})

    for strand in reg["strands"]:
        nodes.append({
            "id": strand["id"], "name": strand["name"], "type": "strand", "group": "strands",
            "status": "live", "val": 8, "detail": strand["detail"],
        })
        for member in strand["members"]:
            links.append({"source": strand["id"], "target": member, "kind": "uses"})

    for co in reg.get("connectors", []):
        nodes.append({
            "id": co["id"], "name": co["name"], "type": "connector", "group": "connectors",
            "status": co["status"], "val": 9,
            "detail": f"{co['transport']} · {co['auth']} · scopes: {', '.join(co['scopes'])} · cap: {co['cap']}",
            "never": [f"exceed scope: {s}" for s in co["scopes"]],
        })
        links.append({"source": co["owner"], "target": co["id"], "kind": "connects"})
        for tid in co.get("provides", []):
            links.append({"source": co["id"], "target": f"tool:{tid}", "kind": "provides"})

    for cli in reg.get("clients", []):
        nodes.append({
            "id": cli["id"], "name": cli["name"], "type": "client", "group": "clients",
            "status": cli["status"], "val": 8,
            "detail": f"thread_id {cli['thread']} · input {cli['input']} · gate: {cli['gate']}",
        })
        links.append({"source": cli["id"], "target": "jarvis", "kind": "speaks"})

    for node in vault_nodes():
        nodes.append(node)
        links.append({"source": "memory", "target": node["id"], "kind": "stores"})

    live = sum(1 for a in reg["agents"] if a["status"] == "live")
    gated = sum(1 for t in reg["tools"] if t["gate"])
    return {
        "meta": {
            "agents": len(reg["agents"]),
            "live": live,
            "tools": len(reg["tools"]),
            "gated": gated,
            "clusters": len(reg["clusters"]),
            "connectors": len(reg.get("connectors", [])),
            "clients": len(reg.get("clients", [])),
            "strands": len(reg["strands"]),
            "statuses": reg["statuses"],
            "ceilings": reg["ceilings"],
            "status_color": STATUS_COLOR,
        },
        "nodes": nodes,
        "links": links,
    }


def embed_into(page: Path, data: dict) -> bool:
    """Inline the graph into dashboard/index.html so file:// still works.

    Browsers block fetch() of a local json file when the page is opened from
    disk. The dashboard tries fetch first and falls back to this snapshot.
    """
    if not page.exists():
        return False
    text = page.read_text(encoding="utf-8")
    start, end = "/* SNAPSHOT-START */", "/* SNAPSHOT-END */"
    if start not in text or end not in text:
        return False
    head = text.split(start)[0]
    tail = text.split(end)[1]
    block = f"{start}\nconst SNAPSHOT = {json.dumps(data)};\n{end}"
    page.write_text(head + block + tail, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="build the Jarvis node map")
    parser.add_argument("--check", action="store_true", help="lint only")
    args = parser.parse_args()

    reg = load()
    errors = lint(reg)
    for err in errors:
        print(f"FAIL  {err}", file=sys.stderr)
    if errors:
        return 1
    print(f"OK    {len(reg['agents'])} agents, {len(reg['tools'])} tools, 0 violations")
    if args.check:
        return 0

    data = build(reg)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"WROTE {OUT}  ({len(data['nodes'])} nodes, {len(data['links'])} links)")
    if HUD.parent.exists():
        HUD.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"WROTE {HUD}")
    for page in (OUT.parent / "index.html", HUD.parent / "index.html"):
        if embed_into(page, data):
            print(f"EMBED {page}  (offline snapshot refreshed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
