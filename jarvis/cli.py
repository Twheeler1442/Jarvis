from __future__ import annotations

import argparse
import json
import uuid

from langgraph.types import Command

from jarvis.agents.factory import phase1_agent
from jarvis.agents.supervisor import build_jarvis
from jarvis.config import ensure_vault


def _has_interrupt(state) -> bool:
    if isinstance(state, dict) and state.get("__interrupt__"):
        return True
    interrupts = getattr(state, "interrupts", None)
    return bool(interrupts)


def _print_interrupt(state) -> None:
    raw = state.get("__interrupt__") if isinstance(state, dict) else getattr(state, "interrupts", [])
    print("\n--- CONFIRM REQUIRED ---")
    print(raw)
    print("approve / reject / edit")


def _resume_payload(decision: str) -> dict:
    kind = decision.strip().lower()
    if kind.startswith("reject"):
        return {"decisions": [{"type": "reject", "message": "User rejected this write."}]}
    return {"decisions": [{"type": "approve"}]}


def chat(agent, thread: str) -> None:
    config = {"configurable": {"thread_id": thread}}
    print(f"thread={thread}  (ctrl-d to exit)")
    while True:
        try:
            line = input("\nyou> ").strip()
        except EOFError:
            print()
            return
        if not line:
            continue
        if line in {"/exit", "/quit"}:
            return
        state = agent.invoke({"messages": [{"role": "user", "content": line}]}, config=config)
        while _has_interrupt(state):
            _print_interrupt(state)
            decision = input("gate> ").strip() or "reject"
            state = agent.invoke(Command(resume=_resume_payload(decision)), config=config)
        msg = state["messages"][-1]
        print("\njarvis>", getattr(msg, "content", msg))


def main() -> None:
    ensure_vault()
    parser = argparse.ArgumentParser(description="Jarvis CLI")
    parser.add_argument("--phase", choices=["1", "2"], default="1")
    parser.add_argument("--thread", default="home")
    args = parser.parse_args()
    agent = phase1_agent() if args.phase == "1" else build_jarvis()
    chat(agent, args.thread)


if __name__ == "__main__":
    main()
