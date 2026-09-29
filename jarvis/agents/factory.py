from __future__ import annotations

from langchain.agents import create_agent

from jarvis.models import local_model, smart_model
from jarvis.prompts import load
from jarvis.tools import PHASE1_TOOLS
from jarvis.tools.authority import write_gate


def phase1_agent():
    """Single agent. No specialists. Prove tools work first."""
    return create_agent(
        model=local_model(),
        tools=PHASE1_TOOLS,
        system_prompt=load("phase1"),
        middleware=[write_gate()],
    )


def make_specialist(prompt_name: str, tools: list, model=None):
    """A specialist has NO checkpointer. Only the outer Jarvis does.

    That is required for human-in-the-loop interrupts to bubble up.
    """
    return create_agent(
        model=model or local_model(),
        tools=tools,
        system_prompt=load(prompt_name),
        middleware=[write_gate()],
    )
