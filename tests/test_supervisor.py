"""The whole architecture, wired, with scripted models in place of Ollama.

Proves: the supervisor builds, a specialist runs as a tool, the supervisor only
ever sees the specialist's final string, and the specialist has no checkpointer.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from tests.conftest import ScriptedModel, tool_call


def _patch_models(monkeypatch, supervisor_script):
    """Supervisor gets a scripted brain, every specialist gets its own."""
    import jarvis.agents.factory as factory
    import jarvis.agents.supervisor as supervisor

    def fake_local(temperature: float = 0.2):
        return ScriptedModel(script=[AIMessage(content="SPECIALIST REPORT: two bullets, one URL")])

    monkeypatch.setattr(factory, "local_model", fake_local)
    monkeypatch.setattr(supervisor, "local_model", fake_local)
    monkeypatch.setattr(supervisor, "smart_model",
                        lambda temperature=0.2: ScriptedModel(script=supervisor_script))


def test_supervisor_builds_and_delegates(monkeypatch, vault):
    from jarvis.agents.supervisor import build_jarvis

    _patch_models(monkeypatch, [
        tool_call("research", {"query": "what shipped this month"}),
        AIMessage(content="here is what I found"),
    ])

    jarvis = build_jarvis()
    state = jarvis.invoke(
        {"messages": [{"role": "user", "content": "what shipped this month"}]},
        config={"configurable": {"thread_id": "t-delegate"}},
    )

    texts = [getattr(m, "content", "") for m in state["messages"]]
    assert any("SPECIALIST REPORT" in t for t in texts), "the specialist's report never came back"
    assert state["messages"][-1].content == "here is what I found"


def test_supervisor_exposes_specialists_not_their_tools(monkeypatch, vault):
    """Jarvis sees comms(). It must never see draft_email, search_mail, or web_search."""
    import jarvis.agents.supervisor as supervisor

    _patch_models(monkeypatch, [AIMessage(content="ok")])

    captured = {}
    real_create_agent = supervisor.create_agent

    def spy(**kwargs):
        if "checkpointer" in kwargs:                 # the outer agent, not a specialist
            captured["tools"] = {t.name for t in kwargs["tools"]}
            captured["has_checkpointer"] = kwargs["checkpointer"] is not None
        return real_create_agent(**kwargs)

    monkeypatch.setattr(supervisor, "create_agent", spy)
    supervisor.build_jarvis()

    assert {"research", "comms", "planner"} <= captured["tools"]
    assert captured["has_checkpointer"], "the supervisor lost its conversation memory"
    for leaked in ("draft_email", "search_mail", "web_search", "send_email"):
        assert leaked not in captured["tools"], f"{leaked} leaked onto the supervisor"


def test_specialists_have_no_checkpointer(monkeypatch, vault):
    from jarvis.agents.factory import make_specialist
    from jarvis.tools.clock import now

    _patch_models(monkeypatch, [AIMessage(content="ok")])
    specialist = make_specialist("research", [now])
    assert getattr(specialist, "checkpointer", None) in (None, False), \
        "a specialist with a checkpointer swallows the confirm gate"


def test_prompts_carry_the_identity_and_a_ban_list():
    from jarvis.prompts import load

    for name in ("jarvis", "research", "comms", "planner", "phase1"):
        text = load(name)
        assert "{{IDENTITY}}" not in text, f"{name}: identity was not substituted"
        assert "NEVER" in text.upper(), f"{name}: no ban list"
