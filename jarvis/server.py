"""HTTP + WebSocket bridge between Jarvis and every surface.

    uvicorn jarvis.server:app --host 127.0.0.1 --port 8765

One Jarvis. Many clients. The surface decides how a gate is answered, and the
bridge decides what a surface is allowed to answer. Those are two different
questions, which is why the policy lives here and not in the browser.

    POST /ask        {"text": "...", "thread": "home", "surface": "cli"}
    GET  /graph      the node map, same file the dashboard reads
    GET  /health     liveness plus open gate count
    WS   /ws         push: graph | say | gate | error
                     recv: hello | ask | decision | halt | kill
"""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command

from jarvis.config import ROOT
from jarvis.policy import tool_class

GRAPH = ROOT / "dashboard" / "graph.json"
HUD = ROOT / "hud"
GATE_TIMEOUT_SECONDS = 180

# Which surfaces may answer which gates. A surface that cannot prove a human is
# present may only ever say no. Anyone may always say no.
SURFACE_POLICY: dict[str, dict[str, Any]] = {
    "cli":      {"approve": {"vault", "write", "device", "external"}},
    "hud":      {"approve": {"vault", "write", "device", "external"}},
    "voice":    {"approve": set()},
    "telegram": {"approve": {"vault", "write"}},
    "cron":     {"approve": set()},
}
DEFAULT_SURFACE = "cron"
"""What a socket is until it proves otherwise: the weakest policy, approves
nothing. A socket that never says hello used to default to `hud`, which may
approve everything, so simply omitting the handshake was a privilege
escalation. Unauthenticated clients get the weakest seat, never the strongest."""

CODE_REQUIRED = frozenset({"device", "external"})
"""Classes whose approval must echo the one time code. Anything that reaches
past the software into the house or the outside world. The HUD has always
demanded the code for both; the bridge used to require it only for `external`,
so a device call could be approved by a bare 'approve'."""

app = FastAPI(title="jarvis-bridge")

_agent: Any = None
_sockets: dict[WebSocket, dict[str, Any]] = {}   # ws -> {"surface": str, "greeted": bool}
_pending: dict[str, dict[str, Any]] = {}
_turns: set[asyncio.Task] = set()
_lock = asyncio.Lock()


def may_approve(surface: str, cls: str) -> bool:
    return cls in SURFACE_POLICY.get(surface, SURFACE_POLICY[DEFAULT_SURFACE])["approve"]


# ------------------------------------------------------------------ agent
def get_agent() -> Any:
    """Built on first use, not at import. Keeps tests and --help free of a model."""
    global _agent
    if _agent is None:
        from jarvis.agents.supervisor import build_jarvis

        _agent = build_jarvis()
    return _agent


def set_agent(agent: Any) -> None:
    """Inject an agent. Used by tests and by anyone embedding the bridge."""
    global _agent
    _agent = agent


# ------------------------------------------------------------------ helpers
async def broadcast(payload: dict) -> None:
    dead = []
    for ws in list(_sockets):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _sockets.pop(ws, None)


async def broadcast_gate(payload: dict, code: str, cls: str) -> None:
    """Show the gate to everyone; hand the one time code only to a seat that
    could actually use it.

    Every surface should see what is being asked, so any of them can say no.
    But the code is the proof that a human is reading this screen right now,
    and broadcasting it to a cron or voice socket hands that proof to a seat
    that is not allowed to give it.
    """
    dead = []
    for ws, state in list(_sockets.items()):
        body = dict(payload)
        if code is not None and may_approve(state["surface"], cls):
            body["code"] = code
        try:
            await ws.send_text(json.dumps(body))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _sockets.pop(ws, None)


def interrupts_of(state: Any) -> list[dict]:
    """Normalize the interrupt payload across langgraph versions and shapes."""
    raw = state.get("__interrupt__") if isinstance(state, dict) else getattr(state, "interrupts", None)
    if not raw:
        return []
    out: list[dict] = []
    for item in raw if isinstance(raw, (list, tuple)) else [raw]:
        value = getattr(item, "value", item)
        if isinstance(value, (list, tuple)):
            candidates = list(value)
        elif isinstance(value, dict) and value.get("action_requests"):
            candidates = list(value["action_requests"])
        else:
            candidates = [value]
        for cand in candidates:
            if isinstance(cand, dict):
                request = cand.get("action_request") or cand
                out.append({
                    "name": request.get("name") or request.get("action") or "unknown_tool",
                    "args": request.get("args", {}),
                })
            else:
                out.append({"name": str(cand), "args": {}})
    return out


def last_text(state: Any) -> str:
    msg = state["messages"][-1]
    return getattr(msg, "content", None) or str(msg)


async def gate_one(request: dict, surface: str) -> dict:
    """Open one gate and wait. Returns the resume decision for this request."""
    name, args = request["name"], request["args"]
    cls = tool_class(name)
    gid = secrets.token_hex(4)
    code = f"{secrets.randbelow(9000) + 1000}"

    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    async with _lock:
        _pending[gid] = {"future": fut, "cls": cls, "code": code, "tool": name}

    await broadcast_gate({"type": "gate", "id": gid, "tool": name, "args": args,
                          "cls": cls, "asked_by": surface}, code, cls)

    try:
        decision = await asyncio.wait_for(fut, timeout=GATE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        decision = {"decision": "reject", "message": "gate timed out, nobody answered"}
    except asyncio.CancelledError:
        async with _lock:
            _pending.pop(gid, None)
        raise
    finally:
        async with _lock:
            _pending.pop(gid, None)

    if decision.get("decision") == "approve":
        return {"type": "approve"}
    return {"type": "reject", "message": decision.get("message") or "rejected at the gate"}


async def run_turn(text: str, thread: str, surface: str) -> str:
    """One user turn. Pauses at every gate until some surface answers it."""
    config = {"configurable": {"thread_id": thread}}
    state = await asyncio.to_thread(
        get_agent().invoke, {"messages": [{"role": "user", "content": text}]}, config
    )

    while True:
        requests = interrupts_of(state)
        if not requests:
            break

        # One gate per request. A parallel batch used to gate only requests[0]
        # and resume with a single decision: the second call was never shown to
        # a human, and the count mismatch failed the whole turn.
        decisions: list[dict] = []
        halted = False
        for request in requests:
            if halted:
                decisions.append({"type": "reject", "message": "halted, rest of batch refused"})
                continue
            decision = await gate_one(request, surface)
            decisions.append(decision)
            if decision["type"] == "reject" and decision["message"].startswith(("halt", "kill")):
                halted = True

        state = await asyncio.to_thread(
            get_agent().invoke, Command(resume={"decisions": decisions}), config
        )

    return last_text(state)


async def resolve_gate(msg: dict, surface: str, ws: WebSocket | None = None) -> str:
    """Apply the surface policy to one decision. Returns what happened, for the log."""
    gid = msg.get("id")
    async with _lock:
        item = _pending.get(gid)
    if not item or item["future"].done():
        return "stale"                       # first decision wins, the rest are no-ops

    if msg.get("decision") != "approve":
        item["future"].set_result({"decision": "reject", "message": msg.get("message", "")})
        return "reject"

    if not may_approve(surface, item["cls"]):
        if ws:
            await ws.send_text(json.dumps({"type": "error", "id": gid,
                "text": f"{surface} may not approve "
                        f"{'an' if item['cls'][0] in 'aeiou' else 'a'} {item['cls']} write. "
                        f"Approve it from the CLI."}))
        return "refused-by-policy"

    # Writes that reach outside the software echo a one time code, so a stored
    # gesture, a stuck key, or a replayed message cannot approve anything.
    if item["cls"] in CODE_REQUIRED and msg.get("code") != item["code"]:
        if ws:
            await ws.send_text(json.dumps({"type": "error", "id": gid, "text": "wrong confirm code"}))
        return "wrong-code"

    item["future"].set_result({"decision": "approve"})
    return "approve"


async def reject_all(reason: str) -> int:
    async with _lock:
        items = list(_pending.values())
    count = 0
    for item in items:
        if not item["future"].done():
            item["future"].set_result({"decision": "reject", "message": reason})
            count += 1
    return count


# ------------------------------------------------------------------ routes
@app.get("/health")
def health() -> dict:
    return {"ok": True, "sockets": len(_sockets), "open_gates": len(_pending)}


@app.get("/graph")
def graph() -> Any:
    if GRAPH.exists():
        return JSONResponse(json.loads(GRAPH.read_text(encoding="utf-8")))
    return JSONResponse({"nodes": [], "links": [], "meta": {}})


@app.post("/ask")
async def ask(body: dict) -> dict:
    reply = await run_turn(body.get("text", ""), body.get("thread", "home"),
                           body.get("surface", "cli"))
    await broadcast({"type": "say", "text": reply[:400]})
    return {"reply": reply}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    state = {"surface": DEFAULT_SURFACE, "greeted": False}
    _sockets[ws] = state
    try:
        if GRAPH.exists():
            await ws.send_text(json.dumps({"type": "graph",
                                           "data": json.loads(GRAPH.read_text(encoding="utf-8"))}))
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")
            surface = state["surface"]

            if kind == "hello":
                # A seat is claimed once, on the first message, and never
                # changed. Re-sending hello used to let a socket introduce
                # itself as `voice`, get refused at a gate, then say hello
                # again as `cli` and approve that same open gate.
                if state["greeted"]:
                    await ws.send_text(json.dumps({"type": "error",
                        "text": f"surface is already {surface} and cannot be changed; "
                                f"open a new connection"}))
                    continue
                claimed = msg.get("surface", DEFAULT_SURFACE)
                state["surface"] = claimed if claimed in SURFACE_POLICY else DEFAULT_SURFACE
                state["greeted"] = True
                await ws.send_text(json.dumps({"type": "say",
                                               "text": f"surface: {state['surface']}"}))

            elif kind == "ask":
                # Run the turn as a task. If we awaited it here the receive loop
                # would be blocked, and the decision that unblocks the gate
                # arrives on this same socket. That is a deadlock, not a delay.
                task = asyncio.create_task(_answer(ws, msg, surface))
                _turns.add(task)
                task.add_done_callback(_turns.discard)

            elif kind == "decision":
                await resolve_gate(msg, surface, ws)

            elif kind in {"halt", "kill"}:
                count = await reject_all(f"{kind} from {surface}")
                await ws.send_text(json.dumps({"type": "say",
                                               "text": f"{kind}: {count} gate(s) rejected"}))
                if kind == "kill":
                    for task in list(_turns):
                        task.cancel()
                    await ws.close()
                    return
    except WebSocketDisconnect:
        pass
    finally:
        _sockets.pop(ws, None)


async def _answer(ws: WebSocket, msg: dict, surface: str) -> None:
    try:
        reply = await run_turn(msg.get("text", ""), msg.get("thread", "home"), surface)
        await ws.send_text(json.dumps({"type": "say", "text": reply}))
    except asyncio.CancelledError:
        pass
    except Exception as exc:                       # a bad turn must not kill the socket
        try:
            await ws.send_text(json.dumps({"type": "error", "text": f"turn failed: {exc}"}))
        except Exception:
            pass


if HUD.exists():
    app.mount("/hud", StaticFiles(directory=str(HUD), html=True), name="hud")


@app.get("/")
def index() -> Any:
    page = HUD / "index.html"
    return FileResponse(page) if page.exists() else JSONResponse({"ok": True})
