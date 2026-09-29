from pathlib import Path

from jarvis.config import load_identity

DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    text = (DIR / f"{name}.md").read_text(encoding="utf-8")
    return text.replace("{{IDENTITY}}", load_identity())
