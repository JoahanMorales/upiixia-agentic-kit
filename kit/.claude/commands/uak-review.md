---
model: sonnet
description: Review another task's PR and record approve/reject for its SHA
argument-hint: "ID"
---
Delegate the whole review of $ARGUMENTS to the `uak-reviewer` subagent (isolated context; the diff never enters yours). Pass it the ID and the mode.
When it returns (5 lines or fewer), don't redo its work. If it rejected, the owner was already told. Continue your task.
If you cannot review now: `bash .uak/bin/uak msg <owner> --kind reply "can't review ID now; next free agent takes it"`.
Requirements: it is not your own task, and you hold an active claim or the reviewer role (`UAK_HUMAN=<human> uak register-reviewer NAME`).
