from __future__ import annotations

from pathlib import Path

from langchain.tools import tool

from jarvis.config import VAULT, ensure_vault


def _safe(relpath: str) -> Path:
    ensure_vault()
    target = (VAULT / relpath).resolve()
    if not str(target).startswith(str(VAULT)):
        raise ValueError(f"refusing path outside vault: {relpath}")
    return target


@tool
def list_dir(relpath: str = ".") -> str:
    """List files and folders inside the vault. relpath is relative to the vault root.
    Example: list_dir('notes') or list_dir('.')."""
    path = _safe(relpath)
    if not path.exists():
        return f"missing: {relpath}"
    if path.is_file():
        return f"file: {relpath}"
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    if not entries:
        return f"{relpath}/ (empty)"
    lines = []
    for item in entries:
        mark = "/" if item.is_dir() else ""
        lines.append(f"{item.name}{mark}")
    return "\n".join(lines)


@tool
def read_file(relpath: str) -> str:
    """Read a UTF-8 text file from the vault. relpath is relative to the vault root.
    Example: read_file('identity.md') or read_file('notes/todo.md')."""
    path = _safe(relpath)
    if not path.is_file():
        return f"not a file: {relpath}"
    text = path.read_text(encoding="utf-8")
    if len(text) > 20_000:
        return text[:20_000] + "\n\n[truncated]"
    return text


@tool
def write_file(relpath: str, content: str) -> str:
    """Write UTF-8 text into the vault, creating parent folders. Overwrites.
    Never used for secrets, SSH keys, or anything outside the vault.
    Example: write_file('notes/brief.md', '# Brief\\n- ...')."""
    path = _safe(relpath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"wrote {relpath} ({len(content)} chars)"
