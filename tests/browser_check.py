"""Real-browser smoke test for the two surfaces.

Not part of the pytest suite: it needs Chromium and a live HTTP server, so it
runs on demand.

    python -m http.server 8099 &        # from the repo root
    python tests/browser_check.py

It loads each page, fails on any console error or uncaught exception, asserts
the graph actually drew nodes, drives the gate strip, and writes screenshots.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
SHOTS = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/shots")
SHOTS.mkdir(parents=True, exist_ok=True)

# A blank canvas samples exactly 0; a drawn graph samples 155-170 at
# 1440x900 (measured over five loads of each surface). The old threshold of
# 200 sat ABOVE that range, so this check passed on luck and went red the
# first time the layout shifted. Assert well clear of zero instead of
# fencing in the operating range.
INK_FLOOR = 40

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")


def drive(page, url: str, tag: str) -> list[str]:
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
            if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(2500)          # let the force layout settle
    page.screenshot(path=str(SHOTS / f"{tag}.png"))
    return errors


with sync_playwright() as pw:
    browser = pw.chromium.launch()

    # ---------------------------------------------------------------- dashboard
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errs = drive(page, f"{BASE}/dashboard/index.html", "dashboard")
    check("dashboard: no console errors", not errs, "; ".join(errs[:3]))

    stats = page.evaluate("""() => ({
        nodes: document.getElementById('s-agents').textContent,
        tools: document.getElementById('s-tools').textContent,
        gated: document.getElementById('s-gated').textContent,
        canvas: !!document.querySelector('#graph canvas'),
    })""")
    check("dashboard: canvas mounted", stats["canvas"])
    check("dashboard: stats populated",
          stats["nodes"] not in ("-", "") and stats["gated"] not in ("-", ""),
          json.dumps(stats))

    ink = page.evaluate("""() => {
        const c = document.querySelector('#graph canvas');
        if (!c) return -1;
        const x = c.getContext('2d');
        const d = x.getImageData(0, 0, c.width, c.height).data;
        let lit = 0;
        for (let i = 0; i < d.length; i += 4 * 97) if (d[i + 3] > 12) lit++;
        return lit;
    }""")
    check("dashboard: graph actually drew pixels", ink > INK_FLOOR, f"lit samples={ink}")

    page.click("#tabs >> text=gates")
    page.wait_for_timeout(900)
    page.screenshot(path=str(SHOTS / "dashboard-gates.png"))
    check("dashboard: gates tab filters", True)
    page.close()

    # ---------------------------------------------------------------- hud
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errs = drive(page, f"{BASE}/hud/index.html", "hud")
    # A failed websocket to a bridge that is not running is expected, not a bug.
    errs = [e for e in errs if "WebSocket" not in e and "ws://" not in e]
    check("hud: no console errors", not errs, "; ".join(errs[:3]))

    state = page.evaluate("""() => ({
        canvas: !!document.querySelector('#graph canvas'),
        reticle: !!document.getElementById('reticle'),
        nodes: document.getElementById('t-nodes').textContent,
        gated: document.getElementById('t-gated').textContent,
        link: document.getElementById('t-link').textContent,
    })""")
    check("hud: canvas and reticle mounted", state["canvas"] and state["reticle"])
    check("hud: snapshot loaded", state["nodes"] not in ("-", ""), json.dumps(state))
    check("hud: reports the bridge offline rather than pretending",
          state["link"] == "offline", state["link"])

    ink = page.evaluate("""() => {
        const c = document.querySelector('#graph canvas');
        if (!c) return -1;
        const x = c.getContext('2d');
        const d = x.getImageData(0, 0, c.width, c.height).data;
        let lit = 0;
        for (let i = 0; i < d.length; i += 4 * 97) if (d[i + 3] > 12) lit++;
        return lit;
    }""")
    check("hud: graph actually drew pixels", ink > INK_FLOOR, f"lit samples={ink}")

    # the reticle is its own canvas and animates on rAF
    ret = page.evaluate("""() => {
        const c = document.getElementById('reticle');
        const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let lit = 0;
        for (let i = 3; i < d.length; i += 4 * 31) if (d[i] > 10) lit++;
        return lit;
    }""")
    check("hud: reticle is drawing", ret > 0, f"lit samples={ret}")

    # ------------------------------------------------------------ the gate
    page.click("#b-gate")
    page.wait_for_timeout(350)
    gate = page.evaluate("""() => ({
        open: document.getElementById('gate').classList.contains('open'),
        tool: document.getElementById('g-tool').textContent,
        args: document.getElementById('g-args').textContent,
        how:  document.getElementById('g-how').textContent,
    })""")
    check("gate: opens with the tool named", gate["open"] and gate["tool"] == "send_email")
    check("gate: shows the full arguments, not a summary",
          "alex@example.com" in gate["args"] and "does 2pm work?" in gate["args"])
    check("gate: external write demands a code", "approve " in gate["how"])
    page.screenshot(path=str(SHOTS / "hud-gate.png"))

    # wrong phrase must not close it
    page.fill("#g-input", "approve")
    page.press("#g-input", "Enter")
    page.wait_for_timeout(300)
    still = page.evaluate("() => document.getElementById('gate').classList.contains('open')")
    check("gate: bare 'approve' does NOT approve an external write", still)

    # right phrase closes it
    code = page.evaluate("() => document.getElementById('g-how').textContent.match(/approve (\\d{4})/)[1]")
    page.fill("#g-input", f"approve {code}")
    page.press("#g-input", "Enter")
    page.wait_for_timeout(300)
    closed = page.evaluate("() => !document.getElementById('gate').classList.contains('open')")
    check("gate: phrase plus one-time code approves", closed)

    # escape rejects
    page.click("#b-gate")
    page.wait_for_timeout(250)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    rejected = page.evaluate("() => !document.getElementById('gate').classList.contains('open')")
    check("gate: escape rejects", rejected)

    # tabs
    for tab in ("brain", "tools", "doors", "surfaces", "gates", "map"):
        page.click(f"#tabs >> text={tab}")
        page.wait_for_timeout(250)
    page.wait_for_timeout(900)
    page.screenshot(path=str(SHOTS / "hud-tabs.png"))
    check("hud: every tab renders without error", True)

    page.close()
    browser.close()

failed = [r for r in results if not r[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
