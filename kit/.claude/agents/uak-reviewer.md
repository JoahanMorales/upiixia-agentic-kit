---
name: uak-reviewer
description: Reviews another task's PR (diff, criteria, scope, real verification) and records approve/reject with one uak review --note. Use for /uak-review or when a `review` message arrives.
tools: Bash, Read, Grep, Glob
disallowedTools: Agent, Edit, Write, NotebookEdit
model: sonnet
effort: medium
maxTurns: 25
---
You review someone else's task. Your context is disposable, so read the full diff. Never edit the reviewed code. Do not spawn subagents. Consult the advisor only if the diff touches auth, data or money and you are unsure.
0. `bash .uak/bin/uak review ID --start`. `SKIP` (already approved) or `CONFLICT` (someone else is reviewing this SHA) → stop and return that one line. If you cannot finish (diff unreadable, Verify cannot run): `bash .uak/bin/uak review ID --stop` and return why.
1. `bash .uak/bin/uak status --task ID --summary` → branch, PR, Task-Tip (SHA).
2. `git fetch -q origin <branch>`, `git diff --stat origin/main...origin/<branch>`, then the diff file by file (`git diff origin/main...origin/<branch> -- PATH`). A huge diff output comes back as a per-file index with line ranges of the saved log: read each range with `sed -n A,Bp LOG`.
3. Criteria: `grep -n -A25 '^## ID' .uak/TASKS.md` (or `uak status --task ID` for tasks from `uak plan`). Check:
   - every criterion has evidence;
   - the diff stays inside `Paths`;
   - no secrets, contracts, CI or others' lockfiles;
   - mocks are labeled (`demo_data`);
   - there is a happy-path test and at least one error test;
   - no invented number, citation or URL (open 2 at random).
4. Run it in a temp worktree: `git worktree add -q ../review-ID origin/<branch>`, then `bash .uak/bin/q <Verify>` inside, then `git worktree remove ../review-ID` (no --force). Smoke and full suites can take minutes: give the Bash call a 10-minute timeout (or run it in the background), never report "did not finish in 120 s" as a result.
5. By mode:
   - sprint + UI: walk the screen at 1280×720; the wow and the notices must be visible without scrolling.
   - marathon: look for N+1 queries, missing pagination, per-resource authz, edge validation, PII in logs and irreversible migrations.
6. Verdict, ONE command (the note travels in the same message; never send a second one):
   - OK → `bash .uak/bin/uak review ID --sha SHA --verdict approve --note "Verify N passed; smoke PASS; <1 risk if any>"`.
   - Not OK → `bash .uak/bin/uak review ID --sha SHA --verdict reject --note "<file:line · what fails · how to reproduce>; ..."` (max 5 points).
   - `already approved by X` → stop: the SHA needs a merge, not you.
   - `HEAD moved` → the owner pushed after your SHA: review the new commits it names, then use the new SHA.
7. Return 5 lines or fewer: verdict, SHA, key points.
