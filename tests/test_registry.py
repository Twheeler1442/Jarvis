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


# ---------------------------------------------------------------------------
# Regressions. Each is a contradiction the linter used to accept.
# ---------------------------------------------------------------------------

def _lint(reg):
    from jarvis.graph.build_graph import lint

    return lint(reg)


def test_a_duplicate_tool_id_is_caught_wherever_it_sits(registry):
    """Rows are keyed by id, last one winning. A second `write_file` declaring
    itself ungated and owned by Research replaced the real row and linted
    clean, because by the time any check ran there was only one of them.
    Position must not matter."""
    import copy

    shadow = {"id": "write_file", "name": "write_file", "class": "external",
              "gate": False, "owner": "research", "status": "live", "detail": "shadow"}
    for position in (0, len(registry["tools"])):
        reg = copy.deepcopy(registry)
        reg["tools"].insert(position, shadow)
        errors = _lint(reg)
        assert any("duplicate id write_file" in e for e in errors), \
            f"a shadow tool row at position {position} linted clean: {errors}"


def test_a_second_holder_of_the_send_key_is_caught(registry):
    import copy

    reg = copy.deepcopy(registry)
    # ha_call_service is `device`: exactly one agent may hold it.
    next(a for a in reg["agents"] if a["id"] == "scribe")["owns"].append("ha_call_service")
    assert any("send key has one holder" in e for e in _lint(reg))


def test_shared_read_and_write_tools_are_still_allowed(registry):
    """The rule is about the send key, not about every tool. Five agents
    legitimately write into the vault; the path lock in the tool confines
    them. A linter that forbade that would just be wrong."""
    holders = [a["id"] for a in registry["agents"] if "write_file" in a.get("owns", [])]
    assert len(holders) > 1
    assert _lint(registry) == []


def test_a_truthy_string_in_the_gate_field_is_caught(registry):
    import copy

    reg = copy.deepcopy(registry)
    next(t for t in reg["tools"] if t["id"] == "write_file")["gate"] = "no"
    assert any("gate must be true or false" in e for e in _lint(reg))


def test_ceiling_only_words_are_not_tool_classes(registry):
    """`propose` is a ceiling and never a class. A tool claiming one used to
    raise KeyError straight out of lint() instead of printing a FAIL line, so
    the operator got a traceback where a verdict belonged."""
    import copy

    for bogus in ("propose", "nonsense", None, 7):
        reg = copy.deepcopy(registry)
        next(t for t in reg["tools"] if t["id"] == "web_search")["class"] = bogus
        errors = _lint(reg)               # must not raise
        assert any("unknown class" in e for e in errors), f"{bogus!r} linted clean"


def test_an_unknown_class_is_charged_the_highest_ceiling(registry):
    """A typo in a class must not buy a tool more reach than it declared."""
    import copy

    reg = copy.deepcopy(registry)
    # web_search belongs to Research, whose ceiling is `read`.
    next(t for t in reg["tools"] if t["id"] == "web_search")["class"] = "raed"
    assert any("cannot hold web_search" in e for e in _lint(reg))


def test_a_gesture_that_authorizes_is_caught(registry):
    """`binds` is prose: "confirm the pending write" contains no "approve".
    The check has to read a boolean."""
    import copy

    reg = copy.deepcopy(registry)
    reg["gestures"][0]["authorizes"] = True
    reg["gestures"][0]["binds"] = "confirm the pending write, commit it"
    assert any("authorizes must be false" in e for e in _lint(reg))


def test_removing_every_gesture_does_not_remove_the_halt_requirement(registry):
    import copy

    reg = copy.deepcopy(registry)
    reg["gestures"] = []
    assert any("HALT" in e for e in _lint(reg))


def test_an_unattended_surface_may_not_approve(registry):
    import copy

    reg = copy.deepcopy(registry)
    cron = next(c for c in reg["clients"] if c["id"] == "cl_cron")
    cron["may_approve"] = ["external"]
    assert any("nobody is there to answer a gate" in e for e in _lint(reg))


def test_a_door_may_not_hand_an_agent_a_tool_it_does_not_own(registry):
    """A connector was an unaudited path around the ceiling: the Workspace
    door handed Planner's calendar tools to Comms."""
    import copy

    reg = copy.deepcopy(registry)
    next(c for c in reg["connectors"] if c["id"] == "co_fs")["provides"].append("web_search")
    assert any("does not own it" in e for e in _lint(reg))


def test_a_door_may_not_exceed_its_owners_ceiling(registry):
    import copy

    reg = copy.deepcopy(registry)
    fs = next(c for c in reg["connectors"] if c["id"] == "co_fs")
    fs["provides"].append("ha_call_service")
    next(a for a in reg["agents"] if a["id"] == "scribe")["owns"].append("ha_call_service")
    assert any("whose ceiling is vault" in e for e in _lint(reg))


def test_the_map_and_the_bridge_agree_on_every_surface(registry):
    """The registry's clients and the bridge's SURFACE_POLICY are two
    statements of the same rule. When they drift, the map is a lie."""
    from jarvis.server import SURFACE_POLICY

    declared = {c["surface"]: set(c["may_approve"]) for c in registry["clients"]}
    assert declared == {name: policy["approve"] for name, policy in SURFACE_POLICY.items()}


def test_every_gated_tool_on_the_map_actually_stops_at_runtime(registry):
    """Four tools were marked `gate: true` on the map and never interrupted,
    because the middleware read a different, hand-kept list."""
    from jarvis.policy import gated_tools

    interrupt_on = gated_tools()
    for tool in registry["tools"]:
        if tool["gate"]:
            assert interrupt_on.get(tool["id"]), \
                f"{tool['id']} is gated on the map but does not stop at runtime"
