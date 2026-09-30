"""The bridge. Surface policy, one time codes, halt, and the deadlock that used to
happen when a turn awaited a gate on the socket that had to answer it.

A stub agent stands in for Jarvis: it raises one interrupt, then reports what the
decision was. No model, no network.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langgraph.types import Command


class StubAgent:
    """Interrupts once on `tool`, then reports the decision it received."""

    def __init__(self, tool: str = "write_file", args: dict | None = None):
        self.tool = tool
        self.args = args or {"relpath": "notes/x.md", "content": "hi"}
        self.paused = False
        self.decisions: list = []

    def invoke(self, payload, config=None):  # noqa: ANN001
        if isinstance(payload, Command):
            self.decisions.append(payload.resume)
            self.paused = False
            kind = payload.resume["decisions"][0]["type"]
            return {"messages": [type("M", (), {"content": f"turn finished: {kind}"})()]}
        self.paused = True
        return {
            "__interrupt__": [{"action_requests": [{"name": self.tool, "args": self.args}]}],
            "messages": [type("M", (), {"content": "paused"})()],
        }


@pytest.fixture
def bridge():
    from jarvis import server

    server._pending.clear()
    server._sockets.clear()
    agent = StubAgent()
    server.set_agent(agent)
    with TestClient(server.app) as client:
        yield client, agent, server
    server.set_agent(None)


def _drain_to(ws, kind, limit=6):
    for _ in range(limit):
        msg = json.loads(ws.receive_text())
        if msg["type"] == kind:
            return msg
    raise AssertionError(f"never received a {kind} message")


def test_health(bridge):
    client, _, _ = bridge
    assert client.get("/health").json()["ok"] is True


def test_gate_round_trip_does_not_deadlock(bridge):
    """The turn must run as a task, or the decision can never be received."""
    client, agent, _ = bridge
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "hud"}))
        ws.send_text(json.dumps({"type": "ask", "text": "write it"}))

        gate = _drain_to(ws, "gate")
        assert gate["tool"] == "write_file"
        assert gate["cls"] == "write"

        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "approve"}))
        say = _drain_to(ws, "say")
        assert "approve" in say["text"]
    assert agent.decisions[0]["decisions"][0]["type"] == "approve"


def test_reject_reaches_the_agent(bridge):
    client, agent, _ = bridge
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "ask", "text": "write it"}))
        gate = _drain_to(ws, "gate")
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"],
                                 "decision": "reject", "message": "no"}))
        _drain_to(ws, "say")
    assert agent.decisions[0]["decisions"][0]["type"] == "reject"


def test_voice_surface_cannot_approve(bridge):
    client, agent, _ = bridge
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "voice"}))
        ws.send_text(json.dumps({"type": "ask", "text": "write it"}))
        gate = _drain_to(ws, "gate")
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "approve"}))
        err = _drain_to(ws, "error")
        assert "may not approve" in err["text"]
    assert agent.decisions == [], "voice approved a write"


def test_voice_surface_can_always_reject(bridge):
    client, agent, _ = bridge
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "voice"}))
        ws.send_text(json.dumps({"type": "ask", "text": "write it"}))
        gate = _drain_to(ws, "gate")
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "reject"}))
        _drain_to(ws, "say")
    assert agent.decisions[0]["decisions"][0]["type"] == "reject"


def test_external_write_requires_the_one_time_code(bridge):
    client, agent, server = bridge
    agent = StubAgent(tool="send_email", args={"to": "alex@example.com"})
    server.set_agent(agent)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "cli"}))
        ws.send_text(json.dumps({"type": "ask", "text": "send it"}))
        gate = _drain_to(ws, "gate")
        assert gate["cls"] == "external"

        ws.send_text(json.dumps({"type": "decision", "id": gate["id"],
                                 "decision": "approve", "code": "0000"}))
        err = _drain_to(ws, "error")
        assert "wrong confirm code" in err["text"]

        ws.send_text(json.dumps({"type": "decision", "id": gate["id"],
                                 "decision": "approve", "code": gate["code"]}))
        say = _drain_to(ws, "say")
        assert "approve" in say["text"]


def test_replaying_a_decision_is_a_no_op(bridge):
    client, agent, _ = bridge
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "ask", "text": "write it"}))
        gate = _drain_to(ws, "gate")
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "reject"}))
        _drain_to(ws, "say")
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "approve"}))
        ws.send_text(json.dumps({"type": "hello", "surface": "hud"}))
        _drain_to(ws, "say")
    assert len(agent.decisions) == 1, "a replayed decision resumed the agent twice"


def test_halt_rejects_every_open_gate(bridge):
    client, agent, _ = bridge
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "ask", "text": "write it"}))
        _drain_to(ws, "gate")
        ws.send_text(json.dumps({"type": "halt"}))
        _drain_to(ws, "say")
    assert agent.decisions[0]["decisions"][0]["type"] == "reject"


def test_unknown_surface_gets_the_weakest_policy(bridge):
    client, agent, _ = bridge
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "some-new-thing"}))
        ws.send_text(json.dumps({"type": "ask", "text": "write it"}))
        gate = _drain_to(ws, "gate")
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "approve"}))
        err = _drain_to(ws, "error")
        assert "may not approve" in err["text"]
    assert agent.decisions == []


def test_interrupt_shapes_all_normalize():
    from jarvis.server import interrupts_of

    shapes = [
        {"__interrupt__": [{"action_requests": [{"name": "write_file", "args": {"a": 1}}]}]},
        {"__interrupt__": [{"name": "write_file", "args": {"a": 1}}]},
        {"__interrupt__": [[{"action_request": {"name": "write_file", "args": {"a": 1}}}]]},
    ]
    for shape in shapes:
        parsed = interrupts_of(shape)
        assert parsed and parsed[0]["name"] == "write_file", shape


def test_tool_class_comes_from_the_registry():
    """Not from a hand-kept frozenset. The two used to disagree on 18 of 24
    tools, and the disagreement is what let telegram approve `pay_bill`."""
    from jarvis.server import tool_class

    assert tool_class("write_file") == "write"
    assert tool_class("draft_email") == "write"
    assert tool_class("send_email") == "external"
    assert tool_class("ha_call_service") == "device"
    # Declared external on the map but absent from the old frozensets.
    assert tool_class("pay_bill") == "external"
    assert tool_class("send_message") == "external"


def test_unknown_tool_is_treated_as_the_strictest_class():
    """A tool nobody declared must not be waved through as a mere write."""
    from jarvis.server import tool_class

    assert tool_class("ha_unlock_the_front_door") == "external"
    assert tool_class("") == "external"


# ---------------------------------------------------------------------------
# Regressions. Every test below is a bypass that a green suite once allowed.
# ---------------------------------------------------------------------------

def test_a_socket_that_never_says_hello_gets_the_weakest_seat(bridge):
    """Omitting the handshake used to mean `hud`, which may approve anything.

    An unauthenticated client must land in the weakest seat, never the
    strongest, so forgetting to introduce yourself cannot be an escalation.
    """
    client, agent, server = bridge
    agent = StubAgent(tool="send_email", args={"to": "alex@example.com"})
    server.set_agent(agent)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "ask", "text": "send it"}))
        gate = _drain_to(ws, "gate")
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"],
                                 "decision": "approve", "code": gate.get("code", "")}))
        err = _drain_to(ws, "error")
        assert "may not approve" in err["text"]
    assert agent.decisions == [], "a socket with no hello approved an external write"


def test_surface_cannot_be_changed_after_the_handshake(bridge):
    """hello once. Re-introducing yourself used to be a live escalation:
    say voice, get refused, say cli, approve that same open gate."""
    client, agent, server = bridge
    agent = StubAgent(tool="send_email", args={"to": "alex@example.com"})
    server.set_agent(agent)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "voice"}))
        ws.send_text(json.dumps({"type": "ask", "text": "send it"}))
        gate = _drain_to(ws, "gate")

        ws.send_text(json.dumps({"type": "decision", "id": gate["id"],
                                 "decision": "approve", "code": "1234"}))
        assert "may not approve" in _drain_to(ws, "error")["text"]

        ws.send_text(json.dumps({"type": "hello", "surface": "cli"}))
        assert "cannot be changed" in _drain_to(ws, "error")["text"]

        ws.send_text(json.dumps({"type": "decision", "id": gate["id"],
                                 "decision": "approve", "code": "1234"}))
        assert "may not approve" in _drain_to(ws, "error")["text"]
    assert agent.decisions == [], "a socket escalated its own surface"


def test_unknown_surface_falls_back_to_the_weakest_seat(bridge):
    client, agent, _ = bridge
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "definitely-not-a-surface"}))
        assert "cron" in _drain_to(ws, "say")["text"]
        ws.send_text(json.dumps({"type": "ask", "text": "write it"}))
        gate = _drain_to(ws, "gate")
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "approve"}))
        assert "may not approve" in _drain_to(ws, "error")["text"]
    assert agent.decisions == []


def test_the_code_is_not_handed_to_a_seat_that_cannot_use_it(bridge):
    """The code proves a human is reading this screen. Broadcasting it to a
    cron or voice socket hands that proof to a seat that may not give it."""
    client, agent, server = bridge
    agent = StubAgent(tool="send_email", args={"to": "alex@example.com"})
    server.set_agent(agent)
    with client.websocket_connect("/ws") as privileged:
        privileged.send_text(json.dumps({"type": "hello", "surface": "cli"}))
        _drain_to(privileged, "say")
        with client.websocket_connect("/ws") as bystander:
            bystander.send_text(json.dumps({"type": "hello", "surface": "voice"}))
            _drain_to(bystander, "say")

            privileged.send_text(json.dumps({"type": "ask", "text": "send it"}))
            mine = _drain_to(privileged, "gate")
            theirs = _drain_to(bystander, "gate")

            # Both see what is being asked, so either can say no.
            assert mine["tool"] == theirs["tool"] == "send_email"
            assert mine["args"] == theirs["args"]
            # Only the seat that could use the code is given it.
            assert mine.get("code"), "the approving seat never got the code"
            assert "code" not in theirs, "the code leaked to a seat that cannot approve"

            privileged.send_text(json.dumps({"type": "decision", "id": mine["id"],
                                             "decision": "approve", "code": mine["code"]}))
            _drain_to(privileged, "say")
    assert agent.decisions[0]["decisions"][0]["type"] == "approve"


def test_device_writes_also_demand_the_code(bridge):
    """The HUD has always demanded a code for device calls. The bridge asked
    only for external, so a bare 'approve' could flip a switch in the house."""
    client, agent, server = bridge
    agent = StubAgent(tool="ha_call_service", args={"entity": "light.kitchen"})
    server.set_agent(agent)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "cli"}))
        ws.send_text(json.dumps({"type": "ask", "text": "dim the kitchen"}))
        gate = _drain_to(ws, "gate")
        assert gate["cls"] == "device"

        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "approve"}))
        assert "wrong confirm code" in _drain_to(ws, "error")["text"]
        assert agent.decisions == [], "a bare approve moved a device"

        ws.send_text(json.dumps({"type": "decision", "id": gate["id"],
                                 "decision": "approve", "code": gate["code"]}))
        _drain_to(ws, "say")
    assert agent.decisions[0]["decisions"][0]["type"] == "approve"


def test_telegram_cannot_approve_an_external_tool_the_frozenset_forgot(bridge):
    """`pay_bill` is external on the map. It was classified `write` at the
    gate, so telegram could approve it with no code at all."""
    client, agent, server = bridge
    agent = StubAgent(tool="pay_bill", args={"amount": 400})
    server.set_agent(agent)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "hello", "surface": "telegram"}))
        ws.send_text(json.dumps({"type": "ask", "text": "pay it"}))
        gate = _drain_to(ws, "gate")
        assert gate["cls"] == "external"
        ws.send_text(json.dumps({"type": "decision", "id": gate["id"], "decision": "approve"}))
        assert "may not approve" in _drain_to(ws, "error")["text"]
    assert agent.decisions == [], "telegram approved a payment"
