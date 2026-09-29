# How to build Jarvis agents

This is the construction manual. The field guide is the map. This file is the wrench.

Correction from the first guide: do **not** start new code on `langgraph-supervisor`. That package is unmaintained. In 2026 the official pattern is:

```python
from langchain.agents import create_agent
from langchain.tools import tool
```

A specialist is a `create_agent`. Jarvis is also a `create_agent`. Jarvis's "tools" are functions that invoke specialists. Only Jarvis gets a checkpointer.

---

## 1. What an agent actually is

An agent is not a persona paragraph. It is five things packaged together:

1. **Model** — which brain, temperature, local vs cloud
2. **Tools** — functions with names, descriptions, and typed arguments
3. **System prompt** — who it is, what it owns, what done looks like, what it may never do
4. **Middleware** — confirm gates, PII redaction, summarization
5. **Definition of done** — a sentence the prompt and the evals both use

If two "agents" share the same tools, the same credentials, and the same definition of done, they are one agent wearing two hats. Do not pay for the second hat.

Test before you add a specialist:

- Does it need a **different toolbox**?
- Does it need a **different permission ceiling**?
- Does it need to run **in parallel** with something else?

Yes to one of those → new agent. Otherwise → another tool on the existing agent.

---

## 2. The four-block prompt

Every specialist prompt is the same shape. Do not write novels.

```
YOU ARE: one sentence role.
TOOLS: the complete list. If it is not here, it does not exist.
DONE WHEN: the exact artifact you return to Jarvis.
YOU NEVER: the ban list. More important than the persona.
```

Example — Comms:

```
YOU ARE: the comms specialist. You handle email and messages.
TOOLS: search_mail, read_mail, draft_email. That is the full list.
DONE WHEN: a draft exists and you have reported to / subject / body
           back to Jarvis. You do not send.
YOU NEVER: send, delete, forward, or change filters.
           You never invent a recipient. If the address is
           ambiguous, return ASK_USER.
```

The ban list is load-bearing. Models love to be helpful. Helpful without a ban list is how mail gets sent.

A common failure: the specialist calls tools and then returns "done" without putting the result in the final message. Jarvis only sees the final message. End every specialist prompt with:

```
Your last message must contain everything Jarvis needs.
Do not assume Jarvis can see your tool calls.
```

---

## 3. Tool design

Tools are how the model touches the world. Bad tools make smart models look drunk.

### Write the description for the model, not for you

```python
from langchain.tools import tool

@tool
def web_search(query: str) -> str:
    """Search the public web for current information. Use for news,
    facts, documentation, and anything after the model's training cutoff.
    Returns titles, URLs, and snippets. Cite URLs in the final answer."""
    ...
```

The first sentence is the routing hint. The rest is the contract.

### Typed arguments, boring types

Use `str`, `int`, `float`, `bool`, `list[str]`. Do not accept "a JSON blob of whatever." If the API wants ISO-8601, the tool argument is `start_time: str` and the docstring says `ISO-8601, e.g. 2026-08-28T15:00:00-06:00`. The specialist translates "Thursday at 3" into that. The tool does not.

### Return strings a model can read

Return short text, not Python objects. `wrote notes/brief.md (812 chars)` is better than `{"ok": True}`.

### Path and network allow-lists live in the tool, not the prompt

```python
def _safe(relpath: str) -> Path:
    target = (VAULT / relpath).resolve()
    if not str(target).startswith(str(VAULT)):
        raise ValueError(f"refusing path outside vault: {relpath}")
    return target
```

A prompt that says "please don't write to ~/.ssh" is a suggestion. A resolved-path check is a lock.

### Split read and write

`search_mail` and `draft_email` are two tools. `send_email` is a third tool you do not attach until the confirm gate is proven. Never give the agent that reads the public web the send key.

---

## 4. Build one agent (Phase 1)

```python
from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from jarvis.tools import PHASE1_TOOLS
from jarvis.prompts import load
from jarvis.tools.authority import write_gate

agent = create_agent(
    model=ChatOllama(model="qwen3:8b", temperature=0.2),
    tools=PHASE1_TOOLS,          # now, list_dir, read_file, write_file, web_search
    system_prompt=load("phase1"),
    middleware=[write_gate()],
)
```

`create_agent` is the loop: model → tool calls → observe → model → stop when there are no more tool calls.

Run it:

```bash
ollama pull qwen3:8b
cd jarvis
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
python -m jarvis.cli --phase 1
```

Acceptance test, typed into the CLI:

```
What's on my plate tomorrow, based on notes/todo.md,
and write a 5-bullet brief to notes/brief.md.
```

If it cannot do that without leaving the vault, do not add specialists.

---

## 5. Promote it to a staff (Phase 2)

Wrap each specialist as a tool. Jarvis never sees `search_mail`. Jarvis sees `comms`.

```python
from langchain.tools import tool
from jarvis.agents.factory import make_specialist

research_agent = make_specialist("research", [web_search, now])

@tool
def research(query: str) -> str:
    """Look up current facts, docs, news. Returns a cited brief."""
    result = research_agent.invoke(
        {"messages": [{"role": "user", "content": query}]}
    )
    return result["messages"][-1].content
```

Then:

```python
from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3

conn = sqlite3.connect("vault/jarvis.db", check_same_thread=False)
jarvis = create_agent(
    model=smart_model(),          # cloud if you have a key, else local
    tools=[research, comms, planner, now, list_dir, read_file, write_file],
    system_prompt=load("jarvis"),
    middleware=[write_gate()],
    checkpointer=SqliteSaver(conn),
)
```

Rules that will save you days:

- Specialists do **not** get a checkpointer. Only Jarvis does. Interrupts cannot bubble up otherwise.
- Specialists do **not** talk to each other. They return a string to Jarvis.
- Put the smarter model on Jarvis. Routing mistakes are more expensive than specialist mistakes.
- `thread_id` is the conversation. Use `home` for the house, or one id per channel (telegram, kitchen, desk).

---

## 6. Confirm-on-write

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware

HumanInTheLoopMiddleware(
    interrupt_on={
        "write_file": True,
        "draft_email": True,
        "send_email": True,
        "create_calendar_event": True,
        "ha_call_service": True,
    },
    description_prefix="Jarvis wants to change something",
)
```

Resume:

```python
from langgraph.types import Command

agent.invoke(
    Command(resume={"decisions": [{"type": "approve"}]}),
    config={"configurable": {"thread_id": "home"}},
)
```

Other decisions: `{"type": "reject", "message": "..."}` or
`{"type": "edit", "edited_action": {"name": "write_file", "args": {...}}}`.

Until the gate is wired, `send_email` should not exist. Have `draft_email` write `vault/drafts/....md` instead.

---

## 7. Worked example — building Comms from zero

Day 1. No Gmail.

1. Create `prompts/comms.md` with the four blocks above.
2. Give it `read_file` and `write_file` only.
3. Jarvis tool:

```python
@tool
def comms(request: str) -> str:
    """Read or draft email. Never sends."""
    ...
```

4. Eval: “draft Alex a note asking if Thursday 2pm works, save to vault/drafts/alex.md.”
5. Confirm the file exists and the body does not invent an email address. If identity.md has no Alex, the agent must return ASK_USER.

Day 2. Add MCP.

1. Run Google Workspace MCP in read-only.
2. Attach `search_mail` and `read_mail` only.
3. Eval: “summarize unread from Alex this week.” Still no send.

Day 3. Draft against real threads.

1. Attach `draft_email` (Gmail drafts endpoint, not send).
2. HITL on `draft_email`.
3. You approve in the CLI. You send from Gmail yourself.

Day 4. Maybe send.

1. Attach `send_email` with HITL and a daily cap of 3.
2. Keep it off the Research agent forever.

That is how you build one specialist. Repeat the shape for Planner and Home. Do not skip days 1–3.

---

## 8. Memory

Three stores:

| Store | Holds | Where |
|---|---|---|
| Working | this conversation | SqliteSaver checkpointer |
| Profile | who you are, deny list | `vault/identity.md`, stuffed into every prompt via `{{IDENTITY}}` |
| Episodes | what happened | `vault/memory/episodes/YYYY-MM-DD.md` |

The Memory librarian is the only writer to long-term storage. Everyone else asks it. You must be able to open the file in a text editor and delete a line. If you cannot, you do not own the system.

Extract facts at end of turn or on a cron, not inside every token. Every stored fact needs a source and a timestamp.

---

## 9. Voice is a client, not a second brain

```
wake word (openWakeWord "hey jarvis")
  → capture until silence (Silero VAD)
  → faster-whisper
  → the SAME Jarvis.invoke(... thread_id="kitchen")
  → Piper / Kokoro
  → speaker
```

Home Assistant Voice Preview Edition is the satellite. Simple commands ("kitchen lights off") should hit HA's native intent pipeline, not the LLM. Point HA's conversation agent at your Jarvis HTTP wrapper so the kitchen and the CLI share memory.

---

## 10. The graph

The dashboard at `dashboard/index.html` is the NeuralOS-style map. Nodes are not decoration. They are the roster:

- **Core** — Jarvis
- **Agents** — specialists
- **Tools** — what each one is allowed to hold
- **Strands** — reusable workflows (morning brief, schedule+draft)
- **Vault** — files the system actually reads
- **Folders** — clusters you will fill with real life

When you add an agent, add a node and an edge `core → agent` and edges `agent → tools it owns`. If a tool does not appear on the map, it does not exist. That rule keeps the blast radius visible.

Rebuild the data file anytime:

```bash
python -m jarvis.graph.build_graph
```

---

## 11. Eval folder

Keep twenty canned jobs. Run them after every prompt change.

```
evals/01_brief_from_todo.md
evals/02_refuse_outside_vault.md
evals/03_ask_if_recipient_unknown.md
evals/04_research_returns_urls.md
evals/05_planner_does_not_claim_booked.md
```

A twelve-line pytest that calls `phase1_agent().invoke(...)` and asserts `notes/brief.md` exists is worth more than a thirteenth specialist.

---

## 12. MCP wiring (when you are ready)

Google Workspace (read-only first):

```json
{
  "mcpServers": {
    "google": {
      "command": "uvx",
      "args": ["workspace-mcp"]
    }
  }
}
```

Home Assistant: Settings → Devices → MCP Server. Create a long-lived token. Expose entities explicitly. Locks and garage stay off the list.

Filesystem MCP: root = `vault/`. Never `$HOME`.

Playwright MCP: one dedicated profile. No password manager.

---

## 13. What "10x more agents" actually looks like

You do not start with 12 agents. You grow like this:

| Week | What exists |
|---|---|
| 1 | Phase 1 single agent + vault + clock + search |
| 2 | Jarvis + Research + Comms + Planner |
| 3 | Confirm gate + identity.md + morning brief cron |
| 4 | Home Assistant allow-list + voice satellite |
| 5 | Coder in a worktree + Critic |
| 6 | Graph dashboard reading live runs |
| later | Finance read-only, Browser, Memory librarian as a real writer |

Twelve hats on day one is how this dies. Twelve nodes on the map, with four of them actually wired, is fine — the rest are placeholders you can see and not pretend are live.
