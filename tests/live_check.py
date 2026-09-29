"""Live end-to-end check of the bridge over a real socket.

Not part of the pytest suite: it binds a port and runs uvicorn. The suite covers
the same rules in-process; this proves the real transport path once.

    python tests/live_check.py

Walks one write through the gate and asserts, against a running server:
  1. a write pauses and the gate reaches the socket with the full arguments
  2. the voice surface cannot approve it
  3. the wrong one-time code cannot approve it
  4. a replayed decision is a no-op
  5. the typed phrase plus the right code approves, and the turn finishes
  6. halt rejects an open gate
"""

from __future__ import annotations

import json
import sys
import threading
import time

import uvicorn
from fastapi.testclient import TestClient  # noqa: F401  (import parity with the suite)
from langgraph.types import Command
from websockets.sync.client import connect

from jarvis import server

PORT = 8766
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


class StubAgent:
    """Stands in for Jarvis: interrupts once, then reports the decision."""

    def __init__(self, tool: str, args: dict):
        self.tool, self.args = tool, args
        self.decisions: list = []

    def invoke(self, payload, config=None):  # noqa: ANN001
        if isinstance(payload, Command):
            self.decisions.append(payload.resume)
            kind = payload.resume["decisions"][0]["type"]
            return {"messages": [type("M", (), {"content": f"turn finished: {kind}"})()]}
        return {
            "__interrupt__": [{"action_requests": [{"name": self.tool, "args": self.args}]}],
            "messages": [type("M", (), {"content": "paused"})()],
        }


agent = StubAgent("send_email", {"to": "alex@example.com", "subject": "Thursday",
                                 "body": "does 2pm work?"})
server.set_agent(agent)

config = uvicorn.Config(server.app, host="127.0.0.1", port=PORT, log_level="warning")
http = uvicorn.Server(config)
threading.Thread(target=http.run, daemon=True).start()
for _ in range(100):
    if http.started:
        break
    time.sleep(0.05)
check("server started", http.started)


def drain(ws, kind, limit=8):
    for _ in range(limit):
        msg = json.loads(ws.recv(timeout=10))
        if msg["type"] == kind:
            return msg
    raise AssertionError(f"never received {kind}")


try:
    # ---------------------------------------------------------------- run one
    with connect(f"ws://127.0.0.1:{PORT}/ws") as voice, \
         connect(f"ws://127.0.0.1:{PORT}/ws") as cli:
        voice.send(json.dumps({"type": "hello", "surface": "voice"}))
        cli.send(json.dumps({"type": "hello", "surface": "cli"}))
        # hello is acked with a say, so drain past it before watching for gates
        check("hello ack names the surface",
              drain(voice, "say")["text"] == "surface: voice")
        drain(cli, "say")

        cli.send(json.dumps({"type": "ask", "text": "email alex", "thread": "home"}))
        gate = drain(cli, "gate")
        check("gate reaches the socket", gate["tool"] == "send_email")
        check("gate carries the full arguments, not a summary",
              gate["args"]["body"] == "does 2pm work?")
        check("external class is recognized", gate["cls"] == "external", gate["cls"])
        check("a one-time code was issued", len(str(gate["code"])) == 4, str(gate["code"]))

        # 2. the voice surface must not be able to approve it
        voice.send(json.dumps({"type": "decision", "id": gate["id"],
                               "decision": "approve", "code": gate["code"]}))
        refusal = drain(voice, "error")
        check("voice surface cannot approve an external write",
              "may not approve" in refusal["text"], refusal["text"])
        check("the agent has still not been resumed", not agent.decisions)

        # 3. the wrong code must not approve it
        cli.send(json.dumps({"type": "decision", "id": gate["id"],
                             "decision": "approve", "code": "0000"}))
        wrong = drain(cli, "error")
        check("wrong one-time code is refused", "code" in wrong["text"].lower(), wrong["text"])
        check("still not resumed", not agent.decisions)

        # 5. the right code approves
        cli.send(json.dumps({"type": "decision", "id": gate["id"],
                             "decision": "approve", "code": gate["code"]}))
        done = drain(cli, "say")
        check("correct code approves and the turn finishes",
              "approve" in done["text"], done["text"])
        check("the agent received exactly one decision", len(agent.decisions) == 1,
              str(agent.decisions))

        # 4. replaying that decision must do nothing
        before = len(agent.decisions)
        cli.send(json.dumps({"type": "decision", "id": gate["id"],
                             "decision": "approve", "code": gate["code"]}))
        time.sleep(0.4)
        check("replaying a resolved decision is a no-op", len(agent.decisions) == before)

    # ---------------------------------------------------------------- halt
    agent.decisions.clear()
    with connect(f"ws://127.0.0.1:{PORT}/ws") as cli:
        cli.send(json.dumps({"type": "hello", "surface": "cli"}))
        drain(cli, "say")
        cli.send(json.dumps({"type": "ask", "text": "email alex", "thread": "home2"}))
        drain(cli, "gate")
        cli.send(json.dumps({"type": "halt"}))
        time.sleep(0.6)
        kinds = [d["decisions"][0]["type"] for d in agent.decisions]
        check("halt rejects the open gate", kinds == ["reject"], str(kinds))
finally:
    http.should_exit = True
    time.sleep(0.4)
    server.set_agent(None)

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
