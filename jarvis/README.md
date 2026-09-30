# `jarvis/` — the package

One supervisor talks to you. Specialists are wrapped as tools it can call. Nothing
reaches the world without passing a gate.

| Path | What lives here |
|---|---|
| `graph/registry.json` | **The source of truth.** Every agent, tool, connector, surface, and gesture, with its class, ceiling, gate, and ban list. |
| `graph/build_graph.py` | Lints the registry and draws the map. Refuses to render a roster that contradicts itself. |
| `policy.py` | Reads tool class and gate **from the registry**, so the bridge and the confirm gate cannot drift from the map. Unknown tools are charged the strictest class. |
| `server.py` | The websocket bridge. Surface policy, gate arbitration, one time codes. |
| `agents/factory.py` | `make_specialist()`. Builds a `create_agent` with no checkpointer, on purpose. |
| `agents/supervisor.py` | `build_jarvis()`. The only agent with a checkpointer, and the only one that talks to you. |
| `tools/authority.py` | The confirm gate. Its interrupt list is generated from the registry. |
| `tools/files.py` | Vault reads and writes. The path lock lives here, not in a prompt. |
| `tools/connectors.py` | The MCP loader. Drops any tool the registry did not declare, per door. |
| `prompts/*.md` | Four block prompts: YOU ARE, TOOLS, DONE WHEN, YOU NEVER. |
| `cli.py` | Terminal client. The safest surface, because approval is typed. |

## Where authority is decided

Three questions, three different files, none of them a prompt:

1. **May this agent hold this tool?** `graph/registry.json`, enforced by `build_graph.py`.
   A tool's class may never exceed its owner's ceiling.
2. **Must this call stop and ask?** `policy.py` reads the registry's `gate` flag, and
   `tools/authority.py` turns that into the middleware's interrupt list.
3. **May this surface approve it?** `server.py`, in `SURFACE_POLICY`. The browser does
   not get a vote, and a socket cannot change the seat it claimed.

A prompt that says "please do not write to `~/.ssh`" is a suggestion. A resolved path
check in `tools/files.py` is a lock. Put the rule in the tool.

## Adding an agent

1. Write `prompts/<name>.md` first, all four blocks.
2. Add the agent to `graph/registry.json` with `status: "planned"`, a ceiling, a ban
   list, a definition of done, and an eval.
3. Run `python -m jarvis.graph.build_graph --check` and fix what it rejects before you
   write any code.
4. Build it with `make_specialist()` and **no** checkpointer.
5. Wrap it as a `@tool` whose docstring is written for the supervisor, not for you.
6. Add two evals: one happy path, one ban list path. Flip `status` to `"wired"`.
