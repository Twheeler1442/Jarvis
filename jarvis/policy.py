"""Tool authority, read from the registry.

The registry is the source of truth for what a tool is allowed to do. Before
this module existed the bridge classified tools from one hand-maintained
frozenset and the confirm gate from another, and both drifted from the
registry: `pay_bill` and `send_message` are declared `external` on the map but
were classified `write` at the gate, so a surface that may only approve writes
could approve them, with no one time code. A capability that is not on the map
does not exist; a capability that is on the map must be enforced from the map.

Everything here fails closed. An unknown tool that somehow reaches a gate is
treated as `external`: the strictest class, needing the strongest surface and
a one time code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jarvis.config import CONSEQUENTIAL_TOOLS, ROOT, WRITE_TOOLS

REGISTRY_PATH = ROOT / "jarvis" / "graph" / "registry.json"

# Ordered weakest to strongest. A surface policy names the classes it may
# approve, so the order here is documentation, not logic.
CLASSES = ("read", "vault", "write", "device", "external")

STRICTEST = "external"
"""What an unknown tool is treated as. Never relax this to 'write'."""


@lru_cache(maxsize=1)
def _registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _tools() -> dict[str, dict]:
    return {t["id"]: t for t in _registry().get("tools", [])}


def reload() -> None:
    """Drop the cache. For tests and for anyone editing the registry live."""
    _registry.cache_clear()
    _tools.cache_clear()


def tool_class(name: str) -> str:
    """The registry's class for a tool, or the strictest class if unknown."""
    tool = _tools().get(name)
    if tool is None:
        # Legacy sets are a floor, not a ceiling: a tool missing from the
        # registry is still at least as dangerous as these say.
        if name in CONSEQUENTIAL_TOOLS or name in WRITE_TOOLS:
            return STRICTEST
        return STRICTEST
    cls = tool.get("class")
    return cls if cls in CLASSES else STRICTEST


def is_gated(name: str) -> bool:
    """True when a tool must stop and ask a human. Unknown tools are gated."""
    tool = _tools().get(name)
    if tool is None:
        return True
    return bool(tool.get("gate", True))


def gated_tools() -> dict[str, bool]:
    """Every tool that must pause, as HumanInTheLoopMiddleware wants it.

    The union of the registry's gated tools and the legacy config sets. The
    union, not the registry alone, so that deleting a row from the registry
    can never quietly un-gate something that used to stop.
    """
    interrupt_on = {name: True for name, tool in _tools().items()
                    if bool(tool.get("gate", True))}
    for name in WRITE_TOOLS | CONSEQUENTIAL_TOOLS:
        interrupt_on[name] = True
    return interrupt_on


def denied_tools() -> set[str]:
    """Tools the registry marks denied. These must never be attached at all."""
    return {name for name, tool in _tools().items() if tool.get("status") == "denied"}
