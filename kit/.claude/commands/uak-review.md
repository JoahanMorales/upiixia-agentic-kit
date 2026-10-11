---
model: sonnet
description: Review another task's PR and record approve/reject for its SHA
argument-hint: "ID"
---
Delegate the whole review of $ARGUMENTS to the `uak-reviewer` subagent (isolated context; the diff never enters yours). Pass it the ID and the mode.
Before delegating, run `bash .uak/bin/uak review $ARGUMENTS --start`. `SKIP` (already approved) or `CONFLICT` (another agent is reviewing this SHA) → do not review; a second review adds nothing.
When it returns (5 lines or fewer), don't redo its work. Its verdict is ONE command with the detail inside: `uak review ID --sha SHA --verdict approve|reject --note "file:line · what · how to reproduce"`; never a second message. Continue your task.
If you cannot review now: `bash .uak/bin/uak msg <owner> --kind reply "can't review ID now; next free agent takes it"`.
Requirements: it is not your own task, and you hold an active claim or the reviewer role (`UAK_HUMAN=<human> uak register-reviewer NAME`).
