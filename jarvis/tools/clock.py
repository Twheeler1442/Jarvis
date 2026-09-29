from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain.tools import tool

from jarvis.config import JARVIS_TZ


@tool
def now() -> str:
    """Return the current local date, time, weekday, and timezone. Call this
    before interpreting words like today, tomorrow, this afternoon, or next Tuesday."""
    dt = datetime.now(ZoneInfo(JARVIS_TZ))
    return dt.strftime("%Y-%m-%d %H:%M %Z %A")
