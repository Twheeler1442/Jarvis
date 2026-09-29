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
CEILING_RANK = {"read": 0, "vault": 1, "propose": 2, "device": 3, "external": 4}


def load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# lint: the map is not decoration, it is the permission model
# --------------------------------------------------------------------------

def lint(reg: dict) -> list[str]:
    errors: list[str] = []
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

    # every tool has exactly one owner, and the owner claims it
    for tid, tool in tools.items():
        owner = tool["owner"]
        if owner not in agents:
            errors.append(f"{tid}: owner {owner} is not an agent")
            continue
        if tool["status"] != "denied" and tid not in agents[owner].get("owns", []):
            errors.append(f"{tid}: owned by {owner} on the map but not in its tool list")
        if tool["class"] in {"write", "device", "external"} and not tool["gate"]:
            errors.append(f"{tid}: {tool['class']} tool with no confirm gate")

    # a read-ceiling agent may not hold a tool that changes anything
    for agent in reg["agents"]:
        ceiling = CEILING_RANK.get(agent["ceiling"], 0)
        for tid in agent.get("owns", []):
            tool = tools.get(tid)
            if not tool:
                continue
            need = {"read": 0, "write": 1, "device": 3, "external": 4}[tool["class"]]
            if need > ceiling:
                errors.append(f"{agent['id']}: ceiling {agent['ceiling']} cannot hold {tid} ({tool['class']})")

    # supervisor sanity
    supervisors = [a for a in reg["agents"] if a["type"] == "supervisor"]
    if len(supervisors) != 1:
        errors.append(f"expected exactly one supervisor, found {len(supervisors)}")
    elif not supervisors[0].get("checkpointer"):
        errors.append("supervisor has no checkpointer. there is no conversation memory")

    # connectors: the doorway is a node too
    for co in reg.get("connectors", []):
        if co["owner"] not in agents:
            errors.append(f"{co['id']}: owner {co['owner']} is not an agent")
        for tid in co.get("provides", []):
            if tid not in tools:
                errors.append(f"{co['id']}: provides unknown tool {tid}")
            elif co["status"] == "denied" and tools[tid]["status"] in {"live", "wired"}:
                errors.append(f"{co['id']}: connector denied but {tid} is {tools[tid]['status']}")
        if not co.get("cap"):
            errors.append(f"{co['id']}: no cap. a connector without a written cap is an open door")

    # clients: every surface declares how a gate is answered on it
    for cli in reg.get("clients", []):
        if not cli.get("thread"):
            errors.append(f"{cli['id']}: no thread_id")
        if not cli.get("gate"):
            errors.append(f"{cli['id']}: no gate policy")
        if cli["id"] == "cl_cron" and "read-only" not in cli["gate"]:
            errors.append("cl_cron: unattended surface must be read-only, no gate can be answered")

    # gestures: an input modality may stop things, never authorize them
    gestures = reg.get("gestures", [])
    if gestures and not any("HALT" in g["binds"] or "kill" in g["binds"] for g in gestures):
        errors.append("gestures: no HALT gesture. every hands-on surface needs one")
    for g in gestures:
        if "approve" in g["binds"].lower():
            errors.append(f"{g['id']}: a gesture may never bind to approve. gestures reject, humans approve")

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
