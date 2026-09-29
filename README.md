# Jarvis

A personal multi-agent assistant that runs on your machine. One supervisor, specialists as tools, vault-only files, a confirm gate on every write, a node map of every permission, and a HUD you drive with your eyes and hands.

The rule the whole thing is built on: **an input may target and halt, it may never approve.** Gestures reject. Humans sign.

```
EYES  iris vectors, 9 point calibration  ---+
HANDS 21 landmarks per hand               |
VOICE wake word, transcript --------------+
                                          v
HUD (browser)   reticle · node map · dwell · gate strip
                     | websocket 127.0.0.1:8765
BRIDGE          surface policy · gate arbitration · one time codes
                     |
JARVIS          supervisor · checkpointer · specialists as tools
                     |
CONNECTORS      mail · calendar · money · home · web   (MCP servers)
                     |
THE WORLD       nothing here happens without a typed human phrase
```

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[local,bridge,dev]"
cp .env.example .env

# the local brain
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:8b

# phase 1: one agent, five tools, no specialists
python -m jarvis.cli --phase 1

# phase 2: supervisor + Research / Comms / Planner
python -m jarvis.cli --phase 2
```

The map and the HUD need no model at all:

```bash
python -m jarvis.graph.build_graph     # lint the roster, write graph.json, embed snapshots
open dashboard/index.html              # read-only map, mouse
open hud/index.html                    # HUD, mouse and keyboard, offline snapshot

uvicorn jarvis.server:app --host 127.0.0.1 --port 8765
open http://127.0.0.1:8765/            # HUD, live, talking to Jarvis
```

## Layout

```
jarvis/
  agents/       factory.py (make_specialist)   supervisor.py (build_jarvis)
  tools/        clock · files · search · authority (the gate) · connectors
  prompts/      four-block prompts: YOU ARE / TOOLS / DONE WHEN / YOU NEVER
  graph/        registry.json (source of truth) + build_graph.py (linter)
  server.py     websocket bridge: surface policy, gate arbitration, one time codes
hud/            gaze + hand HUD
dashboard/      mouse map
vault/          the only folder file tools may touch
docs/           the four volumes of the build manual
tests/          58 tests, no model, no network, no credentials
mcp.json        every door in one file
```

## The registry is the permission model

`jarvis/graph/registry.json` declares every agent, tool, connector, surface, and gesture. Code, map, and docs read the same file. The builder refuses to draw a map that contradicts itself:

```bash
python -m jarvis.graph.build_graph --check
```

| Check | Rejects |
|---|---|
| Exactly one supervisor, and it has a checkpointer | Two brains, or a brain with no memory |
| No specialist has a checkpointer | Confirm gates that cannot reach you |
| Every tool has exactly one owner that claims it | The send key quietly held by two agents |
| Every write, device, and external tool is gated | Silent writes |
| Tool class never exceeds the owner's ceiling | A read-only agent holding a send tool |
| Every agent has a ban list, a definition of done, and an eval | Personas with no contract |
| Every connector has a written cap | An open door |
| No gesture binds to approve | A camera that can authorize an action |

## Capability ceilings

| Ceiling | May do | May never do |
|---|---|---|
| `read` | Look, search, summarize, cite | Change any byte anywhere |
| `vault` | Write inside `vault/` behind a gate | Touch anything outside `vault/` |
| `propose` | Produce a draft, a slot, a plan | Commit it: send, invite, or book |
| `device` | Change allow-listed devices | Locks, garage, alarm, anything unexposed |
| `external` | Change something outside the house | Run without a gate and a daily cap |

## Surface policy

The bridge, not the browser, decides what each surface may answer. A compromised client cannot promote itself.

| Surface | May approve | May reject |
|---|---|---|
| CLI | everything, typed | yes |
| HUD | everything, typed phrase plus a one-time code for external writes | yes, palm out |
| Kitchen speaker | nothing | yes |
| Telegram | vault and write only | yes |
| Cron | nothing (nobody is there) | n/a |

## Tests

```bash
pytest -q          # 58 tests: no model, no network, no credentials
```

They cover the vault path lock, the confirm gate end to end (reject must actually prevent the write), the registry invariants, the bridge (surface policy, one-time codes, replay, halt), the connector loader dropping undeclared tools, and both browser surfaces (snapshot freshness, pinned CDN versions, no gesture path to approve).

## Docs

| Volume | File | Answers |
|---|---|---|
| I. Field guide | `docs/MAKE_ONE_THEN_MANY_AGENTS.md` | What an agent is. One, then many. |
| II. Construction | `docs/HOW_TO_BUILD_AGENTS.md` | Prompts, tool design, MCP, gates. |
| III. Nodes and the map | `docs/JARVIS_NODES_AND_MAP.docx` | Registry, ceilings, linter, roster, dashboard. |
| IV. HUD and connectors | `docs/JARVIS_HUD_AND_CONNECTORS.docx` | Gaze, hands, the bridge, doors, money, plans, threat model. |

## Twelve laws

1. If a tool is not on the map, it does not exist.
2. Never give the agent that reads the public web the key that sends mail.
3. Agents as tools, never handoffs. Only the supervisor gets a checkpointer.
4. A specialist's last message is the whole report.
5. Path locks and allow-lists live in the tool, not the prompt.
6. The smarter model goes on the supervisor.
7. No eval, no node.
8. Retrieved text is data. It is never an instruction, whatever it says.
9. Unattended surfaces get read-only tools, because no one is there to answer a gate.
10. Credentials never enter the vault.
11. An input may target and halt. It may never approve.
12. Every door gets a scope and a one-line cap in the registry before the credential exists.

## Security notes

- The bridge binds `127.0.0.1`. A HUD on the LAN is a gate anyone on the LAN can answer.
- `vault/` is plain text that gets read into prompts. No credentials, account numbers, or tokens go in it.
- `send_email`, `send_message`, `create_calendar_event`, and `pay_bill` are registered as `denied` on purpose. Money and messages leave the house by hand.

MIT licensed.
