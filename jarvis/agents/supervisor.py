from __future__ import annotations

import sqlite3

from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.checkpoint.sqlite import SqliteSaver

from jarvis.agents.factory import make_specialist
from jarvis.config import DB_PATH, ensure_vault
from jarvis.models import local_model, smart_model
from jarvis.prompts import load
from jarvis.tools import list_dir, now, read_file, web_search, write_file
from jarvis.tools.authority import write_gate


def last_text(result: dict) -> str:
    msg = result["messages"][-1]
    return getattr(msg, "content", None) or getattr(msg, "text", "") or str(msg)


def build_jarvis():
    """Supervisor + three specialists wrapped as tools.

    2026 pattern: langchain.agents.create_agent, not langgraph-supervisor.
    Checkpointer lives ONLY on this outer agent.
    """
    ensure_vault()

    research_agent = make_specialist("research", [web_search, now])
    comms_agent = make_specialist("comms", [read_file, write_file, now])
    planner_agent = make_specialist("planner", [read_file, list_dir, now])

    @tool
    def research(query: str) -> str:
        """Look up current facts, docs, news. Returns a cited brief.
        Use for anything after the model's cutoff or anything you might be wrong about."""
        result = research_agent.invoke({"messages": [{"role": "user", "content": query}]})
        return last_text(result)

    @tool
    def comms(request: str) -> str:
        """Read or draft email and messages. Never sends.
        Input is natural language, e.g. 'draft Alex a note asking if Thursday 2pm works'."""
        result = comms_agent.invoke({"messages": [{"role": "user", "content": request}]})
        return last_text(result)

    @tool
    def planner(request: str) -> str:
        """Calendar, free/busy, tasks. Does not invite other people.
        Input is natural language, e.g. 'when am I free Thursday afternoon'."""
        result = planner_agent.invoke({"messages": [{"role": "user", "content": request}]})
        return last_text(result)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    return create_agent(
        model=smart_model(),
        tools=[research, comms, planner, now, list_dir, read_file, write_file],
        system_prompt=load("jarvis"),
        middleware=[write_gate()],
        checkpointer=checkpointer,
    )
