"""The registry is the permission model. These are the invariants the linter enforces,
asserted again here so a bad merge fails CI rather than a browser refresh."""

from __future__ import annotations


def test_linter_reports_zero_violations(registry):
    from jarvis.graph.build_graph import lint

    assert lint(registry) == []


def test_exactly_one_supervisor_and_it_owns_the_checkpointer(registry):
    supervisors = [a for a in registry["agents"] if a["type"] == "supervisor"]
    assert len(supervisors) == 1
    assert supervisors[0]["checkpointer"] is True


def test_no_specialist_has_a_checkpointer(registry):
    for agent in registry["agents"]:
        if agent["type"] != "supervisor":
            assert not agent.get("checkpointer"), f"{agent['id']} would swallow interrupts"


def test_every_world_changing_tool_is_gated(registry):
    for tool in registry["tools"]:
        if tool["class"] in {"write", "device", "external"}:
            assert tool["gate"], f"{tool['id']} changes the world without a gate"


def test_every_tool_has_exactly_one_owner(registry):
    owners = {}
    for tool in registry["tools"]:
        owners.setdefault(tool["id"], set()).add(tool["owner"])
    for tid, who in owners.items():
        assert len(who) == 1, f"{tid} has more than one owner"


def test_research_never_holds_a_write_tool(registry):
    """Law 2. The agent that reads untrusted text never gets a key."""
    tools = {t["id"]: t for t in registry["tools"]}
    research = next(a for a in registry["agents"] if a["id"] == "research")
    assert research["ceiling"] == "read"
    for tid in research["owns"]:
        assert tools[tid]["class"] == "read"


def test_send_and_pay_are_denied(registry):
    tools = {t["id"]: t for t in registry["tools"]}
    for tid in ("send_email", "send_message", "create_calendar_event", "pay_bill"):
        assert tools[tid]["status"] == "denied", f"{tid} should not be attached in v1"


def test_no_gesture_binds_to_approve(registry):
    """Law 11. Gestures reject. Humans sign."""
    for gesture in registry["gestures"]:
        assert "approve" not in gesture["binds"].lower()
    assert any("HALT" in g["binds"] or "kill" in g["binds"] for g in registry["gestures"])


def test_unattended_surfaces_cannot_answer_a_gate(registry):
    cron = next(c for c in registry["clients"] if c["id"] == "cl_cron")
    assert "read-only" in cron["gate"]
    voice = next(c for c in registry["clients"] if c["id"] == "cl_voice")
    assert "never spoken approve" in voice["gate"]


def test_every_connector_has_a_written_cap(registry):
    for conn in registry["connectors"]:
        assert conn["cap"].strip(), f"{conn['id']} is an open door"


def test_every_agent_has_a_ban_list_a_done_and_an_eval(registry):
    for agent in registry["agents"]:
        assert agent["never"], agent["id"]
        assert agent["done"], agent["id"]
        assert agent["eval"], agent["id"]


def test_graph_builds_and_every_link_resolves(registry, tmp_path):
    from jarvis.graph.build_graph import build

    data = build(registry)
    ids = {n["id"] for n in data["nodes"]}
    for link in data["links"]:
        assert link["source"] in ids, link
        assert link["target"] in ids, link
    assert data["meta"]["agents"] == len(registry["agents"])
    assert data["meta"]["gated"] == sum(1 for t in registry["tools"] if t["gate"])
