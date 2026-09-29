"""Test rig. No model, no network, no credentials.

The vault is redirected to a temp directory BEFORE jarvis.config is imported,
because config reads the environment at import time.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

_TMP_VAULT = Path(tempfile.mkdtemp(prefix="jarvis-test-vault-"))
os.environ["JARVIS_VAULT"] = str(_TMP_VAULT)
os.environ["JARVIS_DB"] = str(_TMP_VAULT / "jarvis.db")
os.environ.setdefault("JARVIS_TZ", "America/Denver")

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


class ScriptedModel(BaseChatModel):
    """A model that replays a fixed list of AIMessages.

    Enough to drive create_agent through a tool call and a final answer, which
    is all the agent loop needs to be exercised. Keeps CI free of Ollama.
    """

    script: list[Any] = []
    cursor: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN003
        index = min(self.cursor, len(self.script) - 1)
        object.__setattr__(self, "cursor", self.cursor + 1)
        return ChatResult(generations=[ChatGeneration(message=self.script[index])])


def tool_call(name: str, args: dict, call_id: str = "call_1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


@pytest.fixture
def vault() -> Path:
    from jarvis.config import VAULT, ensure_vault

    ensure_vault()
    return VAULT


@pytest.fixture
def registry() -> dict:
    import json

    return json.loads((REPO / "jarvis" / "graph" / "registry.json").read_text(encoding="utf-8"))
