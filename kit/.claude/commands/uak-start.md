---
description: Take the next task and get its worktree ready (claim included)
argument-hint: "[ID] [agent-name]"
---
Goal: from zero to editing code in under 2 min. Arguments: $ARGUMENTS
1. Already in a worktree with `.uak-env` and its task still CLAIMED? Follow its `Next` (`bash .uak/bin/uak status --task $UAK_TASK --summary`). Do not claim another.
2. Otherwise run `bash .uak/bin/uak next` and take its candidate (or the argument). Read only its section: `grep -n -A25 '^## ID' .uak/TASKS.md`. If it is not there, it came via `uak plan`, and `uak status --task ID` shows Verify and Paths.
3. Identity: the argument or `UAK_AGENT`. Otherwise ask ONCE (format `person-N`).
4. `bash .uak/bin/wt new ID --agent NAME --next "<exact first step>"`. On CONFLICT (exit 3), go back to `next` and pick another; don't retry.
5. Ask the human to `cd <worktree>` and open the agent there, or continue there yourself if you can.
6. Read the task thread: `bash .uak/bin/uak inbox --task ID`.
7. Get context cheaply: send up to 3 `uak-scout` subagents in parallel with precise questions (where is X, which tests cover Y), instead of reading files yourself. If your plan touches more than 2 files or a contract, consult the advisor (or `/uak-advise plan`) before editing.
8. Run `/uak-loop` on the first criterion. When it is green, commit and push the branch.
