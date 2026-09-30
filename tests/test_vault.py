"""Law 5: path locks live in the tool, not the prompt."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_write_then_read_round_trip(vault):
    from jarvis.tools.files import read_file, write_file

    out = write_file.invoke({"relpath": "notes/brief.md", "content": "# Brief\n- one\n"})
    assert "wrote notes/brief.md" in out
    assert (vault / "notes" / "brief.md").exists()
    assert "# Brief" in read_file.invoke({"relpath": "notes/brief.md"})


@pytest.mark.parametrize(
    "escape",
    [
        "../outside.md",
        "../../etc/passwd",
        "notes/../../escape.md",
        "/etc/passwd",
    ],
)
def test_refuses_to_escape_the_vault(vault, escape):
    from jarvis.tools.files import write_file

    with pytest.raises(Exception) as err:
        write_file.invoke({"relpath": escape, "content": "nope"})
    assert "outside vault" in str(err.value).lower()


@pytest.mark.parametrize("suffix", ["-evil", "2", ".bak", "X"])
def test_refuses_a_sibling_that_shares_the_vault_name(vault, suffix):
    """The bypass a string prefix check cannot see.

    A vault at /home/me/vault and a sibling at /home/me/vault-evil: the
    second path really does start with the first, so `startswith` waves the
    write through and it lands outside the vault. Only a component-wise
    compare catches it. The sibling name is derived from the real vault so
    this keeps testing the bug wherever the fixture puts the vault, instead
    of quietly passing against a hardcoded name that shares no prefix.
    """
    from jarvis.tools.files import write_file

    sibling = f"../{vault.name}{suffix}/pwned.md"
    with pytest.raises(Exception) as err:
        write_file.invoke({"relpath": sibling, "content": "escaped"})
    assert "outside vault" in str(err.value).lower()
    assert not (vault.parent / f"{vault.name}{suffix}").exists(), \
        f"write escaped the vault into {vault.parent / (vault.name + suffix)}"


def test_refused_write_leaves_nothing_on_disk(vault):
    """A refusal that still created the parent directory is not a refusal."""
    from jarvis.tools.files import write_file

    for escape in (f"../{vault.name}-evil/pwned.md", "../../etc/jarvis-pwned"):
        with pytest.raises(Exception):
            write_file.invoke({"relpath": escape, "content": "nope"})
    assert not (vault.parent / f"{vault.name}-evil").exists()
    assert not Path("/etc/jarvis-pwned").exists()


def test_symlink_out_of_the_vault_is_refused(vault):
    """resolve() collapses the symlink, so the target is judged, not the link."""
    from jarvis.tools.files import read_file

    secret = vault.parent / "outside-secret.md"
    secret.write_text("sensitive", encoding="utf-8")
    (vault / "escape-link.md").symlink_to(secret)

    with pytest.raises(Exception) as err:
        read_file.invoke({"relpath": "escape-link.md"})
    assert "outside vault" in str(err.value).lower()


def test_list_dir_stays_inside(vault):
    from jarvis.tools.files import list_dir

    with pytest.raises(Exception):
        list_dir.invoke({"relpath": "../.."})


def test_clock_is_timezone_aware():
    from jarvis.tools.clock import now

    stamp = now.invoke({})
    assert any(z in stamp for z in ("MDT", "MST"))
