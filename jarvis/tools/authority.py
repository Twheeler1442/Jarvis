from __future__ import annotations

from langchain.agents.middleware import HumanInTheLoopMiddleware

from jarvis.policy import gated_tools


def write_gate() -> HumanInTheLoopMiddleware:
    """Pause before any tool that changes the world.

    The list comes from the registry, via jarvis.policy, not from a second
    hand-kept set. While those were two lists they drifted: four tools were
    marked `gate: true` on the map and never actually stopped at runtime.
    Read tools are omitted, so they auto-approve.
    """
    return HumanInTheLoopMiddleware(
        interrupt_on=gated_tools(),
        description_prefix="Jarvis wants to change something",
    )
