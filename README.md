# Jarvis

A personal multi-agent assistant that runs on your machine. One supervisor, specialists as tools, vault-only files, a confirm gate on every write, a node map of every permission, and a HUD you drive with your eyes and hands.

The rule the whole thing is built on: **an input may target and halt, it may never approve.** Gestures reject. Humans sign.

### Where things are

| Folder | What it holds |
|---|---|
| [`jarvis/`](jarvis/) | The package. The registry, the linter, the bridge, the agents, the tools. |
| [`hud/`](hud/) | The cockpit: gaze targets, hands select, the gate strip demands a typed phrase. |
| [`dashboard/`](dashboard/) | The same map, mouse only, no camera. For looking rather than operating. |
| [`tests/`](tests/) | 96 offline tests, plus a live socket check and a real browser check. |
| [`vault/`](vault/) | The only folder the file tools may touch. Plain markdown you can edit by hand. |
| [`docs/`](docs/) | Four build manuals, from "what is an agent" to the HUD and the threat model. |
| [`vendor/`](vendor/) | The graph library, committed, so both surfaces work with no network. |

Each of those folders has its own README explaining what is inside and why.

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
vendor/         force-graph, committed so the surfaces work with no network
docs/           the four volumes of the build manual
tests/          63 tests, plus on-demand browser and live-socket checks
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
| No duplicate ids, anywhere | A second row silently overriding the first |
| The declared owner claims its tool | A tool nobody actually holds |
| Every device and external tool has exactly one holder | The send key quietly held by two agents |
| Every write, device, and external tool is gated, with a real boolean | Silent writes, and `"gate": "no"` reading as true |
| Tool class never exceeds the owner's ceiling | A read-only agent holding a send tool |
| A door only delivers tools its owner already declares, within its ceiling | A connector as an unaudited path around the ceiling |
| Every agent has a ban list, a definition of done, and an eval | Personas with no contract |
| Every connector has a written cap | An open door |
| Every gesture declares `authorizes: false`, and one declares `halts: true` | A camera that can authorize an action |
| Every surface declares `may_approve` as a list; an unattended one is empty | A gate policy that reads well in prose and enforces nothing |

Read and write tools are deliberately shareable: five agents write into the vault, and the path lock inside the tool is what confines them. The single-holder rule is about the send key, so it binds `device` and `external` only.

Two invariants keep the map and the code from drifting apart, and both are tested: the registry's `may_approve` must equal the bridge's `SURFACE_POLICY`, and every tool marked `gate: true` must actually interrupt at runtime.

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
| HUD | everything, typed phrase plus a one-time code for device and external writes | yes, palm out |
| Kitchen speaker | nothing | yes |
| Telegram | vault and write only | yes |
| Cron | nothing (nobody is there) | n/a |

A socket is whatever `hello` says it is, **once**. It starts in the weakest seat, so a client that never introduces itself approves nothing, and the seat cannot be changed afterwards: saying `voice`, getting refused, then saying `cli` and answering the same open gate does not work. The one-time code is shown only to sockets whose seat could actually use it, so a cron or voice listener is never handed the proof it is not allowed to give.

This is a policy boundary between surfaces, not authentication. The bridge binds `127.0.0.1` on purpose. Anyone who can open a socket to it can claim the `cli` seat, so if you tunnel the HUD to another device, register that surface as `voice` — it can reject but never approve.

## Tests

```bash
pytest -q          # 96 tests: no model, no network, no credentials
```

They cover the vault path lock (including a sibling directory that shares the vault's name, which a string-prefix check waves straight through), the confirm gate end to end (reject must actually prevent the write), the registry invariants, the bridge (surface policy, seat escalation, one-time codes, replay, halt), the connector loader dropping undeclared tools and refusing a second door that impersonates the first, and both browser surfaces (snapshot freshness, pinned versions, no gesture path to approve).

Every security fix in this repo has a test that was verified to fail when the fix is reverted. A test that cannot fail is not a test.

Two checks need more than a test file, so they run on demand and in CI:

```bash
# a real browser: fails on any console error, proves the graph drew pixels,
# drives the gate strip, writes screenshots to /tmp/shots
python -m http.server 8099 &
python tests/browser_check.py

# a real socket: gate raised, voice surface refused, wrong code refused,
# replay is a no-op, the right code approves, halt rejects
python tests/live_check.py
```

## Offline

Both surfaces work with no network at all. `vendor/force-graph.min.js` is committed, the graph data is embedded into each page on every build, and the tracking library is loaded by a dynamic `import()` inside the start-tracking handler rather than at the top of the module. An unreachable CDN costs you eye and hand tracking and nothing else; if even the graph library is missing, the page prints the roster as text instead of going black.

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
