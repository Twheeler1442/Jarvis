# Make one agent, then make many

This is the chapter that answers “how do I actually create an agent — and then a team.”
Framework of record for this repo: LangChain `create_agent` (2026). The patterns transfer to the OpenAI Agents SDK and Claude Agent SDK.

---

## 0. The only definition that matters

A **model** answers.

An **agent** is a model inside a loop:

```
while not done:
    think
    maybe call a tool
    observe the result
done → answer
```

A **multi-agent system** is several of those loops, with a rule for who talks to whom.

You do not need a framework to understand this. You need a framework so you do not reimplement the loop, the tool schema, the interrupt, and the checkpoint every Saturday.

---

## 1. Make ONE agent — full walkthrough

### 1.1 Ingredients (exactly three)

| Ingredient | What it is | Example |
|---|---|---|
| Model | Something that can call tools | `ChatOllama(model="qwen3:8b")` |
| Tools | Python functions with a docstring the model reads | `web_search`, `read_file` |
| System prompt | Who it is, what it owns, what “done” is, what it may never do | See §1.3 |

That is the whole object. Memory, confirm gates, and other agents come later.

### 1.2 Install

```bash
# Python 3.11+
python3 -m venv .venv && source .venv/bin/activate
pip install langchain langchain-ollama langgraph duckduckgo-search python-dotenv

# Local model with native tool calling
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b
```

Qwen3.x is the 2026 local default because tool calling is in the chat template. A bigger model that cannot call tools is a worse agent.

### 1.3 Write the prompt first, on paper

```
YOU ARE: a research assistant that runs on my laptop.
TOOLS: web_search, now.
DONE WHEN: 3–7 bullets, each with a URL, plus CONFIDENCE high|medium|low.
YOU NEVER: invent a URL. never claim you sent mail or booked anything.
If the question is ambiguous, ask one question instead of searching.
```

If you cannot fill those four lines, you are not ready to write code. The ban list is load-bearing. Models try to be helpful. Helpful without a ban list is how things get sent.

### 1.4 Write two tools

```python
# agent_one.py
from datetime import datetime
from zoneinfo import ZoneInfo
from langchain.tools import tool
from langchain.agents import create_agent
from langchain_ollama import ChatOllama


@tool
def now() -> str:
    """Current local date, time, weekday, timezone.
    Call this before interpreting today / tomorrow / Thursday."""
    return datetime.now(ZoneInfo("America/Denver")).strftime(
        "%Y-%m-%d %H:%M %Z %A"
    )


@tool
def web_search(query: str) -> str:
    """Search the public web. Use for anything after your cutoff.
    Returns title, URL, snippet. Cite URLs in the final answer."""
    from duckduckgo_search import DDGS
    rows = []
    with DDGS() as ddg:
        for hit in ddg.text(query, max_results=5):
            rows.append(f"- {hit['title']}\n  {hit['href']}\n  {hit['body']}")
    return "\n".join(rows) or f"no results for {query}"


SYSTEM = """YOU ARE: a research assistant on the user's laptop.
TOOLS: web_search, now.
DONE WHEN: 3–7 bullets, each ending with a URL, then CONFIDENCE high|medium|low.
YOU NEVER: invent a URL. never claim you emailed or booked anything.
Call now() before using words like today or tomorrow.
"""

agent = create_agent(
    model=ChatOllama(model="qwen3:8b", temperature=0.2),
    tools=[now, web_search],
    system_prompt=SYSTEM,
)

if __name__ == "__main__":
    q = "What landed in the agent-frameworks world this month?"
    out = agent.invoke({"messages": [{"role": "user", "content": q}]})
    print(out["messages"][-1].content)
```

Run it:

```bash
python agent_one.py
```

You now have one agent. Everything else is packaging.

### 1.5 What `create_agent` is doing

```
user message
   ↓
model (+ system prompt + tool schemas)
   ↓
does it want a tool? --no--> final answer
   ↓ yes
run the Python function
   ↓
feed the string back as a ToolMessage
   ↓
model again
   ↓
repeat until no tool calls
```

You can write this loop by hand. The factory is so you do not.

### 1.6 Acceptance test for a single agent

A single agent is “done” when all three pass:

1. It calls `now` before answering “what day is tomorrow.”
2. It calls `web_search` for a current-events question and the answer contains real URLs.
3. It does **not** claim to have sent an email (it has no such tool).

If (3) fails, the prompt is wrong. If (1) or (2) fail, the tool description is wrong or the model cannot call tools — switch model before you add more tools.

### 1.7 When to stop adding tools to this one agent

Stop at about 8–12 tools. Past that the model picks the wrong one and the context fills with schemas. That is the signal to split into a second agent, not to write a longer prompt.

---

## 2. Make a SECOND agent — only when a boundary is real

Do not create “Researcher 2.” Create a second agent when at least one of these is true:

- **Different tools.** Research can search. Comms can draft mail. Neither should hold the other’s tools.
- **Different permissions.** Home can flip lights. It cannot send money.
- **Different definition of done.** Research is done when sources are cited. Email is done when a draft is waiting for you.
- **Genuine parallelism.** Four PDFs, six vendors. Fan out identical workers.

If none of those are true, add a tool to the first agent.

### 2.1 The second agent is built the same way

```python
# Same three ingredients. Different tools. Different prompt.
comms = create_agent(
    model=ChatOllama(model="qwen3:8b", temperature=0.2),
    tools=[read_file, write_file],     # vault drafts only, for now
    system_prompt=COMMS_PROMPT,
)
```

`COMMS_PROMPT`:

```
YOU ARE: the comms specialist. You draft messages. You do not talk to the user.
TOOLS: read_file, write_file. Vault only.
DONE WHEN: a draft is written and you report to / subject / body.
YOU NEVER: send. never invent a recipient. if the address is missing, return ASK_USER.
Your LAST message must contain everything the supervisor needs.
The supervisor cannot see your tool calls.
```

That last pair of sentences is the most important multi-agent prompt trick. The outer agent only sees the string you return.

---

## 3. Make MANY agents — pick one of two wiring patterns

There are only two wirings worth using for a personal Jarvis.

### Pattern A — Supervisor stays in the conversation (agents-as-tools)

**This is the one to use.** You talk to Jarvis the whole time. Jarvis calls specialists like tools and then answers you.

```
You  →  Jarvis  →  research("…")  →  string comes back
                 →  comms("…")     →  string comes back
                 →  Jarvis answers you
```

```python
from langchain.tools import tool

research_agent = create_agent(model=local, tools=[web_search, now], system_prompt=RESEARCH)
comms_agent    = create_agent(model=local, tools=[read_file, write_file], system_prompt=COMMS)

@tool
def research(query: str) -> str:
    """Current facts, docs, news. Returns a cited brief."""
    result = research_agent.invoke({"messages": [{"role": "user", "content": query}]})
    return result["messages"][-1].content

@tool
def comms(request: str) -> str:
    """Draft or read mail. Never sends."""
    result = comms_agent.invoke({"messages": [{"role": "user", "content": request}]})
    return result["messages"][-1].content

jarvis = create_agent(
    model=smart_model(),          # put the smarter model HERE
    tools=[research, comms, now],
    system_prompt=JARVIS_PROMPT,
    checkpointer=checkpointer,    # ONLY on Jarvis
)
```

Why this pattern:

- You always talk to one personality.
- Specialists cannot go rogue in front of you.
- Interrupts (confirm-on-write) bubble up to one place.
- The graph of who-owns-what stays visible.

Put the **smarter / more expensive model on Jarvis**. Routing mistakes cost more than specialist mistakes.

Specialists get **no checkpointer**. If they do, human-in-the-loop interrupts often cannot propagate.

### Pattern B — Handoff (specialist takes over the mic)

Use this when the specialist should *become* the thing you are talking to. Customer-support “you are now speaking to billing” is the textbook case.

```
You → Triage → (handoff) → Billing talks to you directly
```

OpenAI Agents SDK:

```python
from agents import Agent, handoff

billing = Agent(name="Billing", instructions="You handle invoices.")
refund  = Agent(name="Refund",  instructions="You handle refunds.")
triage  = Agent(
    name="Triage",
    instructions="Route to billing or refund.",
    handoffs=[billing, handoff(refund)],
)
```

For a household Jarvis, Pattern B is usually worse. You do not want the kitchen speaker to suddenly be “the coder.” Stay on Pattern A.

### Pattern C — Role crew (CrewAI)

```python
from crewai import Agent, Task, Crew, Process

researcher = Agent(role="Researcher", goal="Cite sources", tools=[search])
writer     = Agent(role="Writer",     goal="Draft the brief")
crew = Crew(agents=[researcher, writer], tasks=[t1, t2], process=Process.sequential)
crew.kickoff()
```

Fine for a weekend prototype. Weaker on durable state, confirm gates, and “this write needs a human.” Use it to learn the *idea* of roles. Do not make it the house brain.

---

## 4. The supervisor prompt (copy this)

```
You are Jarvis. You are the only agent that talks to the user.

You do not call raw APIs. You delegate.

TOOLS:
- research(query): current facts, cited
- comms(request): read or draft mail. does not send
- planner(request): calendar and tasks. does not invite outsiders
- now / read_file / write_file / list_dir: small jobs you can do yourself

RULES:
- If a job spans two specialists, call them in sequence and synthesize.
- If a recipient, time, or intent is ambiguous, ASK. Do not guess.
- Never tell the user something happened unless a tool result says it happened.
- Writes that leave the building require a confirm gate. Say so.

DONE WHEN: the user has an answer, a draft in the vault, or one clear question from you.
```

---

## 5. Adding a third, fourth, fifth agent

Checklist. Print it. Use it every time.

1. Write the four-block prompt on disk (`prompts/home.md`).
2. List the tools it **exclusively** owns. If a tool is already owned, do not attach it here.
3. List the tools it must **never** see.
4. Build it with `create_agent(...)` and **no** checkpointer.
5. Wrap it as a `@tool` with a description written for Jarvis, not for you.
6. Add that tool to Jarvis’s tool list. Do not add the inner tools to Jarvis.
7. Add a node and edges on the map (`core → home`, `home → ha_call_service`).
8. Add two evals: one happy path, one ban-list path (“do not unlock the door”).
9. Run the old evals. If morning-brief broke, you leaked a tool or polluted a prompt.

Worked additions:

| New agent | Exclusive tools | Ban list | First eval |
|---|---|---|---|
| Planner | `list_events`, `freebusy` | invite others, delete events | “when am I free Thursday 2–4” |
| Home | `ha_call_service` on exposed entities | locks, garage, alarm | “dim kitchen to 30%” |
| Coder | sandboxed `run_tests`, `edit_worktree` | `git push`, SSH, docker.sock | “add a failing test for X” |
| Critic | `read_diff` only | any execute tool | “is this diff safe to merge” |
| Watcher | read-only views of the others | every write | “write brief.md, do not send” |

Fan-out workers (four PDFs) are copies of Research with different inputs, not four new personas.

---

## 6. Confirm-on-write (required before any second write tool)

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.types import Command

gate = HumanInTheLoopMiddleware(
    interrupt_on={
        "write_file": True,
        "draft_email": True,
        "create_calendar_event": True,
        "ha_call_service": True,
    },
    description_prefix="Jarvis wants to change something",
)

# Jarvis only
jarvis = create_agent(..., middleware=[gate], checkpointer=checkpointer)

# Resume after you look at the proposed tool call
jarvis.invoke(
    Command(resume={"decisions": [{"type": "approve"}]}),
    config={"configurable": {"thread_id": "home"}},
)
```

Reject:

```python
Command(resume={"decisions": [{"type": "reject", "message": "Do not send."}]})
```

Until this works, do not attach `send_email`. Have drafts land in `vault/drafts/`.

---

## 7. Memory without a product

Three files beat a vector database for month one.

```
vault/identity.md          # stuffed into every prompt
vault/notes/               # working documents
vault/memory/episodes/     # dated log of what actually happened
```

Working memory = the checkpointer (`thread_id="home"` for the house, `"kitchen"` for the speaker, `"telegram"` for the phone). Same Jarvis, different threads — or the same thread if you want them to share.

The Memory librarian, when you add it, is the only writer to `vault/memory/`. Everyone else asks. You must be able to delete a line in a text editor.

---

## 8. Minimum evals (keep these forever)

```
1. now() is called for "what's tomorrow"
2. web_search is called for a current-events ask; answer has URLs
3. write_file cannot escape the vault
4. comms returns ASK_USER if the recipient is unknown
5. planner never says "booked" unless create_event returned ok
6. jarvis does not claim to have sent mail
7. two-step: "find a Thursday slot and draft Alex" calls planner then comms
8. reject at the gate actually prevents the write
```

A 20-line pytest around `agent.invoke(...)` is worth more than agent number eight.

---

## 9. Best resources (ranked)

Read top-down. Ignore the rest until these are worn out.

### Must read (free, primary sources)

1. **Anthropic — Building Effective Agents**
   https://www.anthropic.com/research/building-effective-agents
   The vocabulary: workflow vs agent, prompt chaining, routing, parallelization, orchestrator-workers, evaluator-optimizer. The most important ten pages in the field. Start here so you do not confuse a flowchart with a staff.

2. **Anthropic cookbook — agent patterns**
   https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents
   The notebooks that implement (1). Orchestrator-workers is your Jarvis pattern.

3. **Anthropic — How we built our multi-agent research system**
   https://www.anthropic.com/engineering/multi-agent-research-system
   Why a lead + parallel specialists beat one giant agent on breadth-first work, and why it costs more tokens. Read this before you add agent number five.

4. **LangChain — create_agent + personal assistant with subagents**
   https://docs.langchain.com/oss/python/langchain/agents
   https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant
   The exact constructor and the exact “wrap a specialist as a tool” pattern this repo uses. Also the HITL middleware docs:
   https://docs.langchain.com/oss/python/langchain/human-in-the-loop

5. **LangChain Academy — LangGraph course** (free)
   https://academy.langchain.com
   State, checkpoints, interrupts. Even if you only call `create_agent`, this is the runtime underneath.

6. **Model Context Protocol spec + HA MCP + Google Workspace MCP**
   https://modelcontextprotocol.io
   https://www.home-assistant.io/integrations/mcp_server
   https://github.com/taylorwilsdon/google_workspace_mcp
   Tools in 2026 should arrive as MCP servers, not as one-off API wrappers.

### Best “build along” courses

7. **Hugging Face Agents course** (free) — https://huggingface.co/learn/agents-course
   Best first course if you have never written a tool loop.

8. **Anthropic Academy — Building MCP servers** (free) — https://academy.anthropic.com
   Four hours. Do this before you write your own Gmail wrapper.

### Best model-agnostic SDKs to know (you only need one)

9. **LangChain `create_agent` / Deep Agents** — https://github.com/langchain-ai/deepagents
   Default for this project. Deep Agents is `create_agent` plus filesystem, sub-agents, skills.

10. **OpenAI Agents SDK** — https://openai.github.io/openai-agents-python
    Cleanest handoff vs agents-as-tools explanation. Use it if you are all-in on OpenAI. The “manager stays in control” page is the same idea as Pattern A:
    https://developers.openai.com/api/docs/guides/agents/orchestration

11. **Claude Agent SDK** — if you want the Claude Code harness as a library. Not required for Jarvis.

### Best local / home pieces

12. **Ollama tool calling** — https://docs.langchain.com/oss/python/integrations/chat/ollama
13. **Home Assistant voice + Ollama + Wyoming (Whisper/Piper)** — HA docs, Voice Preview Edition
14. **openWakeWord** — https://github.com/dscripka/openWakeWord (`hey_jarvis_v0.1`)
15. **3d-force-graph** — https://github.com/vasturiano/3d-force-graph
    The library behind `dashboard/index.html`. Cosmograph (https://cosmograph.app) if the graph grows past a few thousand nodes.

### Best “how do the real ones work” reading

16. **Awesome Agent Architecture** — https://github.com/hardness1020/awesome-agent-architecture
    Harness, not hype. Walks Claude Code / similar systems section by section.

17. **AI Agent Engineering Handbook** — https://github.com/vasilyevdm/ai-agent-handbook
    Patterns mined from 30+ codebases. Use the decision table, skip the tourist lists.

18. **2026 Agent Engineering Roadmap** — https://github.com/codejunkie99/agent-roadmap-2026
    Subscribe list: Anthropic engineering blog first, LangChain blog second, OpenAI cookbook third.

### Use once, then leave

- CrewAI docs — fastest role demo, then come back to `create_agent`
- n8n agent nodes — no-code prototype of the same supervisor idea
- LangSmith — when you need traces, not on day one

### Skip for a personal Jarvis

- Anything titled “14-agent team, one click”
- AutoGPT-style fully autonomous loops with write tools
- New projects on `langgraph.prebuilt.create_react_agent` (deprecated) or `langgraph-supervisor` (unmaintained)
- Fine-tuning a 70B “so it has a personality” — a markdown identity file is cheaper and reversible

---

## 10. One-page build order

```
Day 1   one agent, two tools, four-block prompt, three evals
Day 2   vault file tools + path lock + identity.md
Day 3   wrap Research + Comms as tools; Jarvis is the only mouth
Day 4   confirm gate on write_file; prove reject works
Day 5   Planner; two-step eval (slot + draft)
Week 2  MCP read-only mail/calendar
Week 3  morning brief cron + the 3D map
Week 4  Home allow-list + voice as another client of the same Jarvis
later   Coder+Critic, Memory librarian, anything else that earned a node
```

You do not make twelve agents. You make one that works, then you split only at a real boundary, and you put every split on the map so you can see who holds the send key.
