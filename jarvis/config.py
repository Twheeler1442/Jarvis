from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
VAULT = Path(os.getenv("JARVIS_VAULT", ROOT / "vault")).resolve()
DB_PATH = Path(os.getenv("JARVIS_DB", VAULT / "jarvis.db")).resolve()
IDENTITY_PATH = VAULT / "identity.md"
NOTES_DIR = VAULT / "notes"
MEMORY_DIR = VAULT / "memory"
EPISODES_DIR = MEMORY_DIR / "episodes"

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
JARVIS_TZ = os.getenv("JARVIS_TZ", "America/Denver")

WRITE_TOOLS = frozenset({
    "write_file",
    "draft_email",
    "send_email",
    "create_calendar_event",
    "delete_calendar_event",
    "ha_call_service",
})
CONSEQUENTIAL_TOOLS = frozenset({
    "send_email",
    "create_calendar_event",
    "delete_calendar_event",
    "ha_call_service",
})
DENIED_TOOLS = frozenset({
    "delete_file",
    "git_push",
    "shell_exec",
})


def ensure_vault() -> None:
    for path in (VAULT, NOTES_DIR, MEMORY_DIR, EPISODES_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not IDENTITY_PATH.exists():
        IDENTITY_PATH.write_text("# Identity\n\nFill this in.\n", encoding="utf-8")


def load_identity() -> str:
    ensure_vault()
    return IDENTITY_PATH.read_text(encoding="utf-8")
