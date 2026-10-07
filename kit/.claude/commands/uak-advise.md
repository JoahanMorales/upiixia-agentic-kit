---
description: Opus checkpoint from a compact packet (plan | stuck | done). Use when the advisor tool is unavailable or the session is long.
argument-hint: "plan|stuck|done"
---
Checkpoint: $ARGUMENTS. Build a packet of 40 lines or fewer. Never paste whole files or logs:
1. `GOAL:` the task ID, title and the criterion in play (from `uak status --task $UAK_TASK`).
2. By checkpoint:
   - **plan**: the plan as 3–8 numbered steps, plus the files and contracts it touches.
   - **stuck**: the exact failing command, the last 20 lines of its output, the 2 attempts already made, and your current hypothesis.
   - **done**: `git diff --stat origin/main...HEAD`, the risky hunks (paths + line ranges), and the Verify result.
3. `PATHS:` the files the architect may read to verify claims.
Send it to the `uak-architect` subagent, once. Apply a `CHANGE` verdict's steps; a `STOP` means `uak log $UAK_TASK --state BLOCKED "<why>"` and tell the human.
Budget: at most 3 consultations per task. If the advisor tool is on and the session is short, prefer "consult the advisor" instead, since it already has the transcript.
