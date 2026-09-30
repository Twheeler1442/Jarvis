# `tests/` — what each file proves

```bash
pytest -q          # no model, no network, no credentials
```

A scripted model stands in for Ollama and a stub agent stands in for the supervisor, so
the whole suite runs offline in about a second.

| File | What it proves |
|---|---|
| `test_vault.py` | The path lock holds. Includes the sibling directory case: a vault at `/home/me/vault` must refuse `/home/me/vault-evil`, which a `startswith` check waves straight through. |
| `test_gate.py` | Confirm on write, end to end. Reject must actually prevent the write, not merely report that it did. |
| `test_registry.py` | Every invariant the linter claims: duplicate ids, one holder per send key, real boolean gates, ceilings, doors, gestures, surfaces. Also that the map and the code agree. |
| `test_bridge.py` | Surface policy, seat escalation, one time codes, replay, halt, and the deadlock that happens if a turn awaits a gate on the socket that has to answer it. |
| `test_connectors.py` | Undeclared tools are dropped, a denied door loads nothing, and a second door cannot ship a tool named after the first one's. |
| `test_supervisor.py` | The architecture wired together: the supervisor delegates, specialists return strings, only the supervisor has a checkpointer. |
| `test_surfaces.py` | Static checks on the two browser pages: the embedded graph snapshot is current, versions are pinned, and there is no gesture path to approve. |

Two scripts are not part of the pytest run, because they need a server or a browser:

```bash
python tests/live_check.py                            # real websocket, 14 checks
python -m http.server 8099 &                          # then, in another shell:
python tests/browser_check.py http://127.0.0.1:8099 /tmp/shots   # real Chromium, 18 checks
```

`live_check.py` proves the real transport path rather than the in-process ASGI client.
`browser_check.py` loads both surfaces, fails on any console error, proves the graph
drew actual pixels, and drives the gate strip to confirm a bare "approve" cannot
approve an external write.

## The standard this suite is held to

Every security fix in this repo has a test that was verified to fail when the fix is
reverted. A test that cannot fail is not a test, and a green suite is not a
verification. The suite that missed the vault escape was green at the time.

Two rules follow from that:

- Derive fixture-dependent values from the fixture. The original escape test used a
  hardcoded `../vault-evil`, which shared no prefix with the temp vault's real name, so
  it passed against the bug it was written to catch.
- Assert on the object under test. A test that installs a stub and then asserts against
  the fixture's stub will pass no matter what the code does.
