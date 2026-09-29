"""Law 5: path locks live in the tool, not the prompt."""

from __future__ import annotations

import pytest


def test_write_then_read_round_trip(vault):
    from jarvis.tools.files import read_file, write_file

    out = write_file.invoke({"relpath": "notes/brief.md", "content": "# Brief\n- one\n"})
    assert "wrote notes/brief.md" in out
    assert (vault / "notes" / "brief.md").exists()
    assert "# Brief" in read_file.invoke({"relpath": "notes/brief.md"})


@pytest.mark.parametrize(
    "escape",
    ["../outside.md", "../../etc/passwd", "notes/../../escape.md", "/etc/passwd"],
)
def test_refuses_to_escape_the_vault(vault, escape):
    from jarvis.tools.files import write_file

    with pytest.raises(Exception) as err:
        write_file.invoke({"relpath": escape, "content": "nope"})
    assert "outside vault" in str(err.value).lower()


def test_list_dir_stays_inside(vault):
    from jarvis.tools.files import list_dir

    with pytest.raises(Exception):
        list_dir.invoke({"relpath": "../.."})


def test_clock_is_timezone_aware():
    from jarvis.tools.clock import now

    stamp = now.invoke({})
    assert any(z in stamp for z in ("MDT", "MST"))
