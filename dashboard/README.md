# `dashboard/` — the map, read only

The same graph as the HUD, driven by mouse and keyboard, with no camera and no tracking
code. Use this one when you want to look at the system rather than operate it.

```bash
open dashboard/index.html                      # works straight from disk
cd dashboard && python -m http.server 8080     # or serve it, to pick up graph.json live
```

## Files

| File | Notes |
|---|---|
| `index.html` | The page. One file, no build step. The graph library is loaded from `vendor/`, not a CDN. |
| `graph.json` | Generated. Do not hand edit: `python -m jarvis.graph.build_graph` rewrites it from the registry. |

Every build also embeds a snapshot of the graph into `index.html` itself, because a
browser blocks `fetch()` of a local file when the page is opened from disk. The page
tries the fetch first and falls back to the snapshot, so the map is correct whether it
is served or double clicked. CI fails if a rebuild changes either file, which is what
keeps the committed map honest.

## Legend

| Mark | Means |
|---|---|
| Ring colour | Status: green live, gold wired, grey planned, red denied |
| Number in a cluster ring | Agents plus tools accumulating in that neighbourhood |
| Hexagon | A connector, a door to something outside the house |
| Small gold pip | This tool is gated and will stop and ask |
| Animated gold edge | The supervisor delegates along this line |

The tabs filter the same graph: `brain`, `tools`, `doors`, `surfaces`, `strands`, and
`gates`. Click any node for its definition of done, its ban list, and its first eval,
read straight from the registry.

If a tool does not appear here, it does not exist. That is the rule the whole project
rests on, and it is why the map is generated rather than drawn.
