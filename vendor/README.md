# vendor/

Third-party code committed on purpose, so the two surfaces work with no network.

| File | Version | License | Upstream |
|---|---|---|---|
| `force-graph.min.js` | 1.43.4 | MIT (`force-graph.LICENSE`) | https://github.com/vasturiano/force-graph |

Refresh it deliberately, never automatically:

    npm pack force-graph@<version>
    tar xzf force-graph-<version>.tgz
    cp package/dist/force-graph.min.js vendor/
    cp package/LICENSE vendor/force-graph.LICENSE

Then rerun `pytest -q` and `python tests/browser_check.py`, and bump the version
in the table above.

## What is deliberately NOT vendored

MediaPipe Tasks Vision (hand and face landmarkers) stays on the CDN: the wasm
plus model bundle is tens of megabytes, and it is only needed when you click
**start tracking**. The HUD loads it with a dynamic `import()` inside that click
handler, so an unreachable CDN costs you eye and hand tracking and nothing else.
The map, the node contracts, the gate strip, and mouse and keyboard all keep
working offline.
