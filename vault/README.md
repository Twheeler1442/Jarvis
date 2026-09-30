# `vault/` — the only folder the file tools may touch

Plain markdown you can open in a text editor and delete a line from. If you cannot do
that, you do not own the system.

| Path | Holds | In git? |
|---|---|---|
| `identity.md` | Who you are, your hours, your deny list. Injected into every prompt as `{{IDENTITY}}`. | yes, as a template |
| `notes/` | Working documents. The morning brief lands here. | `todo.md` only |
| `plans/` | One file per multi week intention, with front matter. | one example |
| `money/` | Exported CSVs, one per account per month. See `money/README.md`. | the README only |
| `drafts/` | Where `draft_email` writes until a send tool is earned. | no |
| `memory/episodes/` | Dated log of what actually happened, one file per day. | no |

## What never gets committed

`.gitignore` keeps out `.env`, `vault/jarvis.db`, `drafts/`, `memory/episodes/`,
`money/*.csv` and `notes/brief.md`.

**`identity.md` is tracked, and the version here is a placeholder.** The moment you put
real names, addresses, or household details in it, add it to `.gitignore` and remove it
from the index:

```bash
echo "vault/identity.md" >> .gitignore
git rm --cached vault/identity.md
```

The same goes for anything real you write into `plans/`.

## The rule about secrets

No API tokens, account numbers, or card numbers, ever, in any file here. The vault is
plain text that gets read into prompts, so treat every byte in it as something you have
already pasted into a model. Credentials belong in the OS keychain or the environment.

## Who may write here

`write_file` is gated: every write stops and asks. The path lock in
`jarvis/tools/files.py` resolves the path and compares it to the vault by components,
so `../vault-evil/` and a symlink pointing outside are both refused. When the Memory
librarian is wired it becomes the only writer to `memory/`, and everyone else asks it.
