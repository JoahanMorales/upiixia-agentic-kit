---
model: sonnet
description: Verify, open the PR and move the task to REVIEW (then merge if approved and the mode allows it)
argument-hint: "[ID]"
---
Task: ${ARGUMENTS:-$UAK_TASK}. Run these in order and stop at the first red; fix it before continuing.
0. `bash .uak/bin/uak inbox`: handle pending reject, request and contract messages first.
1. `git fetch origin main && git merge origin/main`. Never force anything. On conflicts, keep both sides' work.
2. `git diff --stat origin/main...HEAD`: everything must be inside `Paths`. Take anything outside out, or request it from its owner.
3. `bash .uak/bin/q <Verify> && bash .uak/bin/q bash .uak/bin/smoke`. Use `uak-runner` for long output or when the app must run.
   - sprint + UI: screenshots at 1280×720 and 390×844 → `design-critic`; fix its P1s.
   - marathon + sensitive area: `security-reviewer`; a HIGH finding blocks.
3b. Risky diff (auth, data, money, migrations, or more than 300 lines): consult the advisor (or `/uak-advise done`) before pushing, and apply its CHANGE items.
4. `git push -u origin HEAD && gh pr create --title "ID · <visible result>" --body "<.github/pull_request_template.md filled in>"`. If gh cannot create PRs (403), do NOT stop: `bash .uak/bin/wt pr` prints the URL; give it to the human and use it below.
5. `bash .uak/bin/uak done ID --pr URL --evidence "<cmd> exit 0; <criteria>"`. This asks a reviewer by rotation. If others consume your change: `uak msg related:ID --kind contract "<what · what to do>"`.
6. `bash .uak/bin/uak checkpoint ID --done ... --decision ... --why ... --fails ... --commands ... --next "Wait for review of SHA <sha>"`.
7. Don't idle. Run `/uak-start` from the main checkout, or review others' PRs.
8. When `approve` arrives:
   - sprint: `bash .uak/bin/uak heartbeat ID && bash .uak/bin/uak merge ID`. Exit 3 means it went to the human queue and shows up in `digest`.
   - marathon: a CODEOWNERS human merges on GitHub.
9. After a human merge: `uak done ID --pr URL --evidence "human merge" --integrated "$(gh pr view URL --json mergeCommit -q .mergeCommit.oid)"`. If you are not the owner (it went offline), `bash .uak/bin/uak integrate ID`.
