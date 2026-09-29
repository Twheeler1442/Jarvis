"""The confirm gate, end to end, with a scripted model instead of Ollama.

This is the test that matters most: reject must actually prevent the write.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from tests.conftest import ScriptedModel, tool_call


def _agent():
    from jarvis.tools.authority import write_gate
    from jarvis.tools.files import write_file

    model = ScriptedModel(script=[
        tool_call("write_file", {"relpath": "notes/gated.md", "content": "written by the agent"}),
        AIMessage(content="wrote notes/gated.md"),
    ])
    return create_agent(
        model=model,
        tools=[write_file],
        system_prompt="test agent",
        middleware=[write_gate()],
        checkpointer=InMemorySaver(),
    )


def _interrupts(state):
    return state.get("__interrupt__") if isinstance(state, dict) else getattr(state, "interrupts", None)


def test_write_pauses_at_the_gate(vault):
    agent = _agent()
    config = {"configurable": {"thread_id": "t-pause"}}
    state = agent.invoke({"messages": [{"role": "user", "content": "write it"}]}, config=config)

    assert _interrupts(state), "write_file ran without stopping for a human"
    assert not (vault / "notes" / "gated.md").exists()


def test_reject_prevents_the_write(vault):
    agent = _agent()
    config = {"configurable": {"thread_id": "t-reject"}}
    agent.invoke({"messages": [{"role": "user", "content": "write it"}]}, config=config)

    agent.invoke(
        Command(resume={"decisions": [{"type": "reject", "message": "no"}]}),
        config=config,
    )
    assert not (vault / "notes" / "gated.md").exists(), "reject did not stop the write"


def test_approve_performs_the_write(vault):
    agent = _agent()
    config = {"configurable": {"thread_id": "t-approve"}}
    agent.invoke({"messages": [{"role": "user", "content": "write it"}]}, config=config)

    agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=config)
    target = vault / "notes" / "gated.md"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "written by the agent"


def test_read_tools_do_not_raise_a_gate(vault):
    from jarvis.tools.authority import write_gate
    from jarvis.tools.clock import now

    agent = create_agent(
        model=ScriptedModel(script=[tool_call("now", {}), AIMessage(content="it is now")]),
        tools=[now],
        system_prompt="test agent",
        middleware=[write_gate()],
        checkpointer=InMemorySaver(),
    )
    state = agent.invoke(
        {"messages": [{"role": "user", "content": "what time is it"}]},
        config={"configurable": {"thread_id": "t-read"}},
    )
    assert not _interrupts(state), "a read tool should never stop the loop"
