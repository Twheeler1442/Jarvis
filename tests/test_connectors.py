"""The connector layer. No MCP server is started here: these test the rules that
decide what a server is allowed to contribute."""

from __future__ import annotations

from dataclasses import dataclass

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
