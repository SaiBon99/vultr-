---
name: close-session
description: "Close a working session: rewrite STATE, fix specs found wrong, add a decision when direction changed, one learning per failure, a history note, then run the record check. Use when the user says close the session, wrap up, or update the docs. Not for committing."
---

# Close session

Each fact lives in one place; link to it from the others. Make surgical edits.

1. List what changed, failed, was decided and was not verified; confirm with `git diff --stat` and `git log`.
2. Specs: only if this session found a spec wrong or changed what one describes, fix those lines.
3. STATE.md: rewrite the affected lines to describe now. Every new unverified line ends with `closed when:`; delete the lines this session closed.
4. DECISIONS.md: only if direction changed. Next ID, an Index row, `Context changed:` when it supersedes, `Revisit if:` when its reason can expire.
5. OpenSpec: for each merged change, `openspec archive <change> --yes` (it folds the deltas into the specs), then `openspec validate --specs --strict --no-interactive`.
6. LEARNINGS.md: one line per failure, under its area; grep first. Delete a gotcha now enforced by code or a check.
7. history/: one note `YYYY-MM-DD-<topic>.md` with the why, and a row in history/README.md.
8. Run the record check (`record:check` script, or `python .agents/skills/close-session/record_check.py`) and fix what it reports. Do not commit.

Return the files changed, one line each, and anything unverified.
