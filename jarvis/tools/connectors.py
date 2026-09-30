"""Connectors: every door to something outside the vault.

A connector is an MCP server. The registry says which one, with what scopes,
for which agent, under what cap. This module turns that into tools and refuses
anything the registry did not declare.

    pip install langchain-mcp-adapters

Rules enforced here at load time, not in a prompt:
  1. A tool the registry does not declare is dropped, even if the server offers it.
  2. A connector marked denied loads nothing at all.
  3. Tools land on the owning agent only. Nothing is added to the supervisor.
  4. A dead server degrades that agent. It never takes the house down.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from pathlib import Path
from typing import Any

REGISTRY = Path(__file__).resolve().parents[1] / "graph" / "registry.json"
LOADABLE = {"live", "wired", "planned"}          # "denied" is deliberately absent


def load_registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def connectors_for(agent_id: str, registry: dict | None = None) -> list[dict]:
    """Doors this agent owns that are allowed to load at all."""
    reg = registry or load_registry()
    return [c for c in reg.get("connectors", [])
            if c["owner"] == agent_id and c["status"] in LOADABLE]


def server_config(conn: dict) -> dict[str, Any]:
    """Translate one registry row into a MultiServerMCPClient entry."""
    if conn["transport"] == "stdio":
        parts = shlex.split(conn["server"])
        return {"command": parts[0], "args": parts[1:], "transport": "stdio"}
    return {"url": conn["server"], "transport": conn["transport"]}


def door_of(tool: Any) -> str | None:
    """Which door a tool came through, if the adapter says.

    langchain-mcp-adapters keys its client by our connector id, and carries
    that back on the tool. Versions differ about where, so try the places it
    has lived and treat "cannot tell" as unknown rather than as a match.
    """
    for attr in ("server_name", "server", "namespace"):
        value = getattr(tool, attr, None)
        if isinstance(value, str) and value:
            return value
    meta = getattr(tool, "metadata", None) or {}
    if isinstance(meta, dict):
        for key in ("server_name", "server", "connector"):
            value = meta.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def keep_declared(offered: list, conns: list[dict]) -> tuple[list, list[str]]:
    """Drop every tool the registry did not declare. Returns (kept, dropped names).

    This is the whole security value of the connector layer: a server that adds
    twelve tools in an update contributes exactly the ones you wrote down.

    Matching is per door, not on the bare tool name. With one flat name map,
    an agent holding two doors let the second one ship a tool named after the
    first one's and inherit its cap: name a tool `write_file` and it arrives
    stamped "vault only". When the adapter tells us which server a tool came
    from we require that server to be the one that declared it; when it will
    not say, we fall back to the name and say so in the log, because refusing
    everything on an older adapter would be worse than the risk.
    """
    by_door: dict[tuple[str, str], dict] = {}
    by_name: dict[str, dict] = {}
    for conn in conns:
        for name in conn.get("provides", []):
            by_door[(conn["id"], name)] = conn
            by_name.setdefault(name, conn)

    kept, dropped = [], []
    for tool in offered:
        name = getattr(tool, "name", None)
        if not name:
            dropped.append(str(tool))
            continue
        door = door_of(tool)
        if door is not None:
            conn = by_door.get((door, name))
        else:
            conn = by_name.get(name)
        if conn is None:
            dropped.append(f"{door}:{name}" if door else name)
            continue
        cap = f"\n[cap: {conn['cap']}]"
        if cap not in (tool.description or ""):
            tool.description = (tool.description or "") + cap
        kept.append(tool)
    return kept, dropped


CONNECT_TIMEOUT_SECONDS = 20
"""A server that errors is handled. A server that hangs is not: without this
the await never returns and the house never finishes starting up."""


async def tools_for(agent_id: str) -> list:
    """Every declared tool for one agent, from every door it owns."""
    conns = connectors_for(agent_id)
    if not conns:
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({c["id"]: server_config(c) for c in conns})
    offered = await asyncio.wait_for(client.get_tools(), timeout=CONNECT_TIMEOUT_SECONDS)
    kept, dropped = keep_declared(offered, conns)
    if dropped:
        print(f"connectors: dropped {len(dropped)} undeclared tools for {agent_id}: "
              f"{', '.join(sorted(dropped)[:8])}")
    return kept


def tools_for_sync(agent_id: str) -> list:
    """Never raises. A dead, missing, or hanging door costs you that door and
    nothing else: the agent runs on its local tools.

    CancelledError is re-raised rather than swallowed. It is not a failure of
    the connector, it is someone shutting us down, and eating it turns a kill
    into a hang.
    """
    try:
        return asyncio.run(tools_for(agent_id))
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        print(f"connectors: {agent_id} timed out after {CONNECT_TIMEOUT_SECONDS}s, "
              f"running local tools only")
        return []
    except BaseException as exc:                 # noqa: BLE001 - the house must still start
        print(f"connectors: {agent_id} degraded, running local tools only ({exc!r})")
        return []


def audit(registry: dict | None = None) -> str:
    """One line per door. Run it weekly and read it out loud."""
    reg = registry or load_registry()
    return "\n".join(
        f"{c['status']:<8} {c['name']:<24} scopes={','.join(c['scopes'])} "
        f"owner={c['owner']} cap={c['cap']}"
        for c in reg.get("connectors", [])
    )


if __name__ == "__main__":
    print(audit())
