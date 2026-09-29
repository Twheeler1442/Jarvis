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
    assert "tasks-vision@0.10.14/vision_bundle.mjs" in text
    assert "tasks-vision@0.10.14/wasm" in text


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
