from __future__ import annotations

from langchain.agents.middleware import HumanInTheLoopMiddleware

from jarvis.config import CONSEQUENTIAL_TOOLS, WRITE_TOOLS


def write_gate() -> HumanInTheLoopMiddleware:
    """Pause before any tool that changes the world.

    Read tools are omitted so they auto-approve.
    Write tools allow approve / edit / reject.
    Consequential tools do not allow silent auto-run.
    """
    interrupt_on: dict[str, bool] = {}
    for name in WRITE_TOOLS | CONSEQUENTIAL_TOOLS:
        interrupt_on[name] = True
    return HumanInTheLoopMiddleware(
        interrupt_on=interrupt_on,
        description_prefix="Jarvis wants to change something",
    )
