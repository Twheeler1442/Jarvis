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


def keep_declared(offered: list, conns: list[dict]) -> tuple[list, list[str]]:
    """Drop every tool the registry did not declare. Returns (kept, dropped names).

    This is the whole security value of the connector layer: a server that adds
    twelve tools in an update contributes exactly the ones you wrote down.
    """
    declared: dict[str, dict] = {}
    for conn in conns:
        for name in conn.get("provides", []):
            declared[name] = conn

    kept, dropped = [], []
    for tool in offered:
        conn = declared.get(getattr(tool, "name", None))
        if conn is None:
            dropped.append(getattr(tool, "name", str(tool)))
            continue
        cap = f"\n[cap: {conn['cap']}]"
        if cap not in (tool.description or ""):
            tool.description = (tool.description or "") + cap
        kept.append(tool)
    return kept, dropped


async def tools_for(agent_id: str) -> list:
    """Every declared tool for one agent, from every door it owns."""
    conns = connectors_for(agent_id)
    if not conns:
        return []

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({c["id"]: server_config(c) for c in conns})
    kept, dropped = keep_declared(await client.get_tools(), conns)
    if dropped:
        print(f"connectors: dropped {len(dropped)} undeclared tools for {agent_id}: "
              f"{', '.join(sorted(dropped)[:8])}")
    return kept


def tools_for_sync(agent_id: str) -> list:
    try:
        return asyncio.run(tools_for(agent_id))
    except Exception as exc:                       # a dead server must not take the house down
        print(f"connectors: {agent_id} degraded, running local tools only ({exc})")
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
