---
description: Use while implementing a criterion: implement, run Verify, fix, with a budget and stuck detection; for long mechanical fixes it can run unattended with uak loop.
argument-hint: "[Verify command]"
---
Verifier: ${ARGUMENTS:-the task's `Verify`}. Loop rules (`.uak/docs/LOOPS.md`):
1. Make the smallest change toward the criterion. For new behavior, write the test first (skill `test-driven-development` when installed).
2. `bash .uak/bin/q <verifier>`. If OK, go to step 5.
3. On failure, read only the tail `q` printed. Find the root cause before editing (skill `systematic-debugging`). Never weaken, skip or delete a test or the verifier to make it pass.
4. Repeat, up to 5 attempts. If the same error appears twice, consult the advisor (or `/uak-advise stuck`) ONCE and apply its single experiment. If it fails again, STOP: `bash .uak/bin/uak log ID --state BLOCKED "<exact error>"` (ID = your task), or run `uak decision ID --option "TEXT" --why "TEXT" --reversible yes --authorized yes --class routine` (the reversible fallback), and tell the human in 1 line.
5. Before claiming it works (skill `verification-before-completion`), re-run the verifier and smoke, then commit and push. `bash .uak/bin/uak checkpoint ...` with the next criterion.
Long mechanical loops (lint, types, a flaky failure with a clear error) can run unattended: `bash .uak/bin/uak loop --verify "<cmd>" --agent "claude -p --permission-mode acceptEdits" --max 5 --task ID`.
