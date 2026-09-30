"""Static checks on the two browser surfaces.

No headless browser here: these assert the contracts that break silently in a
browser (stale snapshot, unpinned CDN, a gesture wired to approve).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PAGES = [REPO / "hud" / "index.html", REPO / "dashboard" / "index.html"]


def snapshot_of(page: Path) -> dict:
    text = page.read_text(encoding="utf-8")
    block = text.split("/* SNAPSHOT-START */")[1].split("/* SNAPSHOT-END */")[0]
    raw = re.search(r"const SNAPSHOT = (.*);", block, re.S).group(1)
    return json.loads(raw)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.parent.name)
def test_offline_snapshot_is_valid_and_current(page):
    """Opened from disk the page cannot fetch graph.json, so the snapshot must be real."""
    snap = snapshot_of(page)
    live = json.loads((REPO / "dashboard" / "graph.json").read_text(encoding="utf-8"))
    assert snap["nodes"], "empty snapshot: run python -m jarvis.graph.build_graph"
    assert len(snap["nodes"]) == len(live["nodes"]), "snapshot is stale versus graph.json"
    assert snap["meta"]["agents"] == live["meta"]["agents"]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.parent.name)
def test_every_link_in_the_snapshot_resolves(page):
    snap = snapshot_of(page)
    ids = {n["id"] for n in snap["nodes"]}
    for link in snap["links"]:
        assert link["source"] in ids and link["target"] in ids, link


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.parent.name)
def test_javascript_parses(page):
    """node --check on the page's own script, so a typo fails CI, not the browser."""
    text = page.read_text(encoding="utf-8")
    match = re.search(r'<script(?: type="module")?>\n(.*?)</script>', text, re.S)
    assert match, "no inline script found"
    tmp = REPO / ".pytest-script-check.mjs"
    tmp.write_text(match.group(1), encoding="utf-8")
    try:
        result = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    finally:
        tmp.unlink(missing_ok=True)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.parent.name)
def test_all_external_scripts_are_version_pinned(page):
    text = page.read_text(encoding="utf-8")
    urls = re.findall(r"https://(?:unpkg\.com|cdn\.jsdelivr\.net)/[^\"'\s)]+", text)
    assert urls
    for url in urls:
        assert "@" in url.split("/npm/")[-1] or "@" in url, f"unpinned dependency: {url}"


def test_hud_imports_the_esm_entry_not_the_bare_package():
    """A bare jsdelivr package URL can resolve to the CommonJS build and fail the import."""
    text = (REPO / "hud" / "index.html").read_text(encoding="utf-8")
    assert 'VISION_CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14"' in text
    assert "${VISION_CDN}/vision_bundle.mjs" in text
    assert "${VISION_CDN}/wasm" in text


def test_tracking_library_is_loaded_lazily_not_at_module_top():
    """A static top-level import of a CDN module makes the whole HUD hostage to
    that CDN: one failed fetch and the module never runs, so the map, the node
    contracts and the gate strip die with it."""
    text = (REPO / "hud" / "index.html").read_text(encoding="utf-8")
    static = re.findall(r"^\s*import\s+[^(]", text, re.M)
    assert not static, f"top-level static import(s) in the HUD: {static}"
    assert "await import(`${VISION_CDN}/vision_bundle.mjs`)" in text
    # and the failure is reported to the user, not swallowed
    assert "tracking library unreachable" in text


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.parent.name)
def test_graph_library_is_vendored_locally_first(page):
    """The surfaces must render with no network at all."""
    text = page.read_text(encoding="utf-8")
    assert '<script src="../vendor/force-graph.min.js"></script>' in text
    local = text.index("../vendor/force-graph.min.js")
    cdn = text.index("unpkg.com/force-graph")
    assert local < cdn, "the CDN copy must only be a fallback, loaded after the local one"
    assert (REPO / "vendor" / "force-graph.min.js").exists()
    assert (REPO / "vendor" / "force-graph.LICENSE").exists()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.parent.name)
def test_no_graph_library_still_shows_the_roster(page):
    """No library must never mean a black screen."""
    text = page.read_text(encoding="utf-8")
    assert "const HAVE_LIB = typeof ForceGraph === \"function\"" in text
    assert "function fallbackRoster(data)" in text
    assert "if (!HAVE_LIB) { fallbackRoster(data); return; }" in text
    assert "Graph library did not load." in text


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.parent.name)
def test_node_draw_guards_against_non_finite_coordinates(page):
    """A node can be drawn before the layout has placed it. createRadialGradient
    throws on NaN, and a throw in the draw callback kills the render loop for
    good, which shows up as a permanently black canvas."""
    text = page.read_text(encoding="utf-8")
    assert "if (!Number.isFinite(n.x) || !Number.isFinite(n.y)) return;" in text
    guard = text.index("if (!Number.isFinite(n.x)")
    gradient = text.index("ctx.createRadialGradient(")   # the call, not the comment
    assert guard < gradient, "the guard must come before the first gradient call"


def test_hud_falls_back_when_fetch_fails():
    text = (REPO / "hud" / "index.html").read_text(encoding="utf-8")
    assert ".catch(() => boot(SNAPSHOT))" in text


def test_no_gesture_path_can_approve():
    """Law 11, asserted against the page, not just the registry."""
    text = (REPO / "hud" / "index.html").read_text(encoding="utf-8")
    for line in text.splitlines():
        if "closeGate(" in line and "approve" in line:
            assert "g-input" in text.split(line)[0][-400:] or "=== gate.phrase" in text, line
    assert 'closeGate("approve")' in text
    # the only approve path is behind the typed phrase comparison
    approve_calls = [l for l in text.splitlines() if 'closeGate("approve")' in l]
    assert len(approve_calls) == 1, approve_calls
    context = text.split('closeGate("approve")')[0]
    assert "g-input" in context and "gate.phrase" in context


def test_external_gate_demands_a_one_time_code():
    text = (REPO / "hud" / "index.html").read_text(encoding="utf-8")
    assert 'gate.phrase = external ? "approve " + m.code : "approve"' in text


def test_kill_and_halt_exist_and_only_ever_stop_things():
    text = (REPO / "hud" / "index.html").read_text(encoding="utf-8")
    assert 'send({ type: "halt" })' in text
    assert 'send({ type: "kill" })' in text
    assert 'closeGate("reject", "palm out")' in text
