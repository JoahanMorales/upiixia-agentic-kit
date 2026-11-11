# Two events on v6.0.0: DevDay-Exchange and deus-ex-machina (Nov 2026)

The first two events on kit v6.0.0, read from their claims branches (`blackbox/`, `tokens/`, `tasks/`, `STATE.md`) and
their git history. Read-only clones; nothing in either repo was run. Every finding maps to a v6.1.0 task.

| | DevDay-Exchange (2026-11-07 → 08) | deus-ex-machina, OpenAI x Kavak, **first place** (2026-11-09) |
|---|---|---|
| Kit, mode | v6.0.0, sprint | v6.0.0, sprint |
| Harnesses | Claude Code (most), Codex (one on Windows) | Claude Code, Codex, plus other models through a teammate's agents |
| Machines | 5 published black box or tokens | 3 Macs worked; 2 published black box, 1 published tokens |
| Tasks in claims at the end | 37 of 41 INTEGRATED | 6 of 23 INTEGRATED, 6 stuck in REVIEW, 3 expired claims |
| First-parent commits on main | 4 outside tasks | 120 of 155 outside tasks |
| Black box lines | 134 | 96 |
| Tokens published | 406 M, 78 % in the main checkout | 185 M, 100 % in the main checkout |

DevDay used the kit as designed. deus-ex-machina won while most of its work went around the kit: agents committed in the
main checkout, PRs were squash-merged on GitHub, and the claims never learned about it. The kit's own numbers (progress,
tokens per task, stats) were wrong for that event, which is the main lesson.

## Findings → v6.1.0

| # | Evidence | Fix |
|---|---|---|
| 1 | deus: 11 `integrate` refusals ("tree hash does not match", "changes no task file", "is AVAILABLE, not REVIEW"), 5 agent reports; dependents stayed blocked | UAK-033: `integrate` records work that reached main outside the gate, by the task's own commits file by file |
| 2 | deus: 120 of 155 commits on main made in the main checkout; the guard blocked one push after the commits existed | UAK-035: the pre-commit hook refuses product commits on main; `stats` counts them |
| 3 | deus: tokens from 1 of 3 Macs, all "main"; DevDay: one coordinator session 178 M cache reads | UAK-036/043: publish from session start and Codex too, name machines that never reported, show the main share |
| 4 | deus: eval runs stored 0 cost and tokens; the submission had to say "the zeros are not a measurement" | UAK-039: a metric not measured is `null`, never 0 |
| 5 | DevDay: main red 9 times in a row, `tsc: not found` (no `npm ci` in `web/`) | UAK-027: the CI template installs web/frontend/client dependencies |
| 6 | Both: `/uak-*` existed only for Claude Code; Codex no longer reads custom prompts | UAK-040: phase scripts as Agent Skills (`$uak-X`) and Gemini commands |
| 7 | Both repos commit `.agents/skills` and `.cursor/skills` as symlinks; a Windows clone gets a text file and no skills | UAK-041: real folders, `doctor` detects and repairs |
| 8 | DevDay: design-lint failed on the kit's own gallery page | UAK-028 |
| 9 | DevDay: a quoted compound Verify ran as one command name (exit 127) | UAK-029 |
| 10 | DevDay: `done` wanted `1280.png`; the critic approved `landing-1280.png` (twice) | UAK-030 |
| 11 | DevDay: one agent retried a frozen claim 7 times | UAK-031 |
| 12 | v6.0 review: a laptop with no git identity got a message about `--human` | UAK-032 |
| 13 | Both: "HACK-0xx is not in TASKS.md" 12 times, minutes after a plan (most were IDs whose plan had been refused or not yet published) | UAK-034: every read path sees the canonical backlog |
| 14 | deus: gitleaks findings in fixture history pointed to `secret-exception`, which refused non-kit rules | UAK-037/044: fingerprint exceptions |
| 15 | DevDay: a review-only Codex agent was offered coding work and missed a review | UAK-038 |

## What worked
- The guard blocked 30 destructive or authority actions at DevDay (UAK_HUMAN, `pkill -f`, `rm -r` outside the worktree,
  `worktree remove --force`, a push to main, a third subagent) and force-push, `reset --hard` and `gh pr merge` at deus.
- 22 of 65 `done` calls at DevDay were refused, nearly all by legitimate gates (PR URL, screenshots, a critic about
  another commit).
