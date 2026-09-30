# `docs/` — the build manuals

Four volumes. The two markdown files are the field guide and the wrench; the two `.docx`
files are the reference manuals, in navy and gold, meant to be printed or read on a
tablet while you build.

| File | Answers | Read it |
|---|---|---|
| `MAKE_ONE_THEN_MANY_AGENTS.md` | What an agent actually is. How to make one, then a team. The two wiring patterns and why only one of them belongs in a house. | Before you write any code |
| `HOW_TO_BUILD_AGENTS.md` | Prompt shape, tool design, confirm gates, MCP wiring, memory, the eval folder. | While you write code |
| `JARVIS_NODES_AND_MAP.docx` | Volume III. Node ontology, capability ceilings, the registry, the roster, the linter, ten laws of wiring, an eight week build order. | Every time you add a node |
| `JARVIS_HUD_AND_CONNECTORS.docx` | Volume IV. The gaze and hand pipelines in detail, input hardware, the bridge, connectors for mail, plans, money, home and web, and a threat model. | When you add a surface or a door |

## The shortest version

One brain that talks to you. Specialists as tools, each with one toolbox and one ban
list. Every write pauses for a human. Every capability visible as a node, or it does not
exist. An input may target and halt; it may never approve.

## Where the docs and the code meet

The manuals describe rules; `jarvis/graph/registry.json` is where those rules are
actually written down, and `jarvis/graph/build_graph.py` is what refuses to let them
contradict each other. When a manual and the linter disagree, the linter wins and the
manual is wrong. That has already happened once: Volume III claimed every tool has
exactly one owner, while the code deliberately lets several agents share a vault write
whose path lock confines them. The rule was narrowed to the send key, and the README
now says so.
