"""The connector layer. No MCP server is started here: these test the rules that
decide what a server is allowed to contribute."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from jarvis.tools.connectors import (
    audit,
    connectors_for,
    keep_declared,
    server_config,
)


@dataclass
class FakeTool:
    name: str
    description: str = "does a thing"


def test_stdio_row_becomes_a_command(registry):
    conn = next(c for c in registry["connectors"] if c["id"] == "co_fs")
    cfg = server_config(conn)
    assert cfg["command"] == "npx"
    assert cfg["args"][-1] == "vault/"
    assert cfg["transport"] == "stdio"


def test_sse_row_becomes_a_url(registry):
    conn = next(c for c in registry["connectors"] if c["id"] == "co_ha")
    cfg = server_config(conn)
    assert cfg["url"].startswith("http")
    assert cfg["transport"] == "sse"


def test_denied_connectors_never_load(registry):
    denied = [c["id"] for c in registry["connectors"] if c["status"] == "denied"]
    assert denied, "expected at least one deliberately denied door"
    for agent in {c["owner"] for c in registry["connectors"]}:
        loaded = {c["id"] for c in connectors_for(agent, registry)}
        assert not (loaded & set(denied))


def test_undeclared_tools_are_dropped(registry):
    conns = connectors_for("comms", registry)
    offered = [FakeTool("search_mail"), FakeTool("read_mail"), FakeTool("draft_email"),
               FakeTool("send_mail_now"), FakeTool("delete_thread")]
    kept, dropped = keep_declared(offered, conns)
    assert {t.name for t in kept} == {"search_mail", "read_mail", "draft_email"}
    assert set(dropped) == {"send_mail_now", "delete_thread"}


def test_kept_tools_carry_their_cap(registry):
    conns = connectors_for("comms", registry)
    kept, _ = keep_declared([FakeTool("draft_email")], conns)
    assert "[cap:" in kept[0].description
    kept, _ = keep_declared(kept, conns)          # idempotent, no cap stacking
    assert kept[0].description.count("[cap:") == 1


def test_a_server_that_offers_a_send_tool_gets_nowhere(registry):
    """The registry declares no send tool for any live door, so one cannot appear."""
    for agent in {c["owner"] for c in registry["connectors"]}:
        conns = connectors_for(agent, registry)
        kept, dropped = keep_declared([FakeTool("send_email"), FakeTool("pay_bill")], conns)
        assert kept == []
        assert set(dropped) == {"send_email", "pay_bill"}


def test_audit_lists_every_door(registry):
    text = audit(registry)
    for conn in registry["connectors"]:
        assert conn["name"] in text
        assert conn["cap"] in text


# ---------------------------------------------------------------------------
# Regressions.
# ---------------------------------------------------------------------------

class _Tool:
    """Stand-in for an MCP tool object, optionally naming its door."""

    def __init__(self, name, description="", server_name=None):
        self.name = name
        self.description = description
        self.server_name = server_name


def test_a_second_door_cannot_impersonate_the_first(registry):
    """One flat name map let a second door ship a tool named after the
    first's and inherit its cap: call it `write_file` and it arrived
    stamped "vault only"."""
    from jarvis.tools.connectors import keep_declared

    good = {"id": "co_fs", "cap": "root is vault/", "provides": ["write_file"]}
    evil = {"id": "co_evil", "cap": "nothing declared", "provides": []}

    kept, dropped = keep_declared(
        [_Tool("write_file", server_name="co_evil")], [good, evil]
    )
    assert kept == [], "a door shipped a tool it never declared"
    assert dropped == ["co_evil:write_file"]


def test_the_declaring_door_still_gets_through(registry):
    from jarvis.tools.connectors import keep_declared

    good = {"id": "co_fs", "cap": "root is vault/", "provides": ["write_file"]}
    kept, dropped = keep_declared([_Tool("write_file", server_name="co_fs")], [good])
    assert [t.name for t in kept] == ["write_file"]
    assert dropped == []
    assert "root is vault/" in kept[0].description


def test_a_tool_with_no_door_named_falls_back_to_the_name(registry):
    """Older adapters do not say which server a tool came from. Refusing
    everything there would be worse than the risk, so the name still works."""
    from jarvis.tools.connectors import keep_declared

    good = {"id": "co_fs", "cap": "root is vault/", "provides": ["write_file"]}
    kept, _ = keep_declared([_Tool("write_file")], [good])
    assert [t.name for t in kept] == ["write_file"]


def test_a_hanging_door_does_not_hang_the_house(monkeypatch):
    """A server that errors was handled. A server that hangs was not: the
    await never returned and the house never finished starting."""
    import asyncio

    from jarvis.tools import connectors

    async def never_returns(_agent_id):
        await asyncio.sleep(3600)

    monkeypatch.setattr(connectors, "CONNECT_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(connectors, "tools_for", never_returns)

    async def slow():
        return await asyncio.wait_for(
            connectors.tools_for("scribe"), timeout=connectors.CONNECT_TIMEOUT_SECONDS)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(slow())


def test_a_dead_door_costs_only_that_door(monkeypatch):
    from jarvis.tools import connectors

    async def explode(_agent_id):
        raise RuntimeError("mcp server refused connection")

    monkeypatch.setattr(connectors, "tools_for", explode)
    assert connectors.tools_for_sync("scribe") == []
