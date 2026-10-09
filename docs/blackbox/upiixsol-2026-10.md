# Black box · UpiixSol (Oct 6–9, 2026) · first harvest, reconstructed by hand

Source: one 3-day marathon-mode project (2 humans, 6 agent identities, 38 tasks, 477 claims commits, 312 messages),
read from the claims branch and the session transcripts (30 MB, 80 subagent runs). Same line format as `uak bb`.
Status column: what v4.1 does about it.

| # | Kind | Command | What happened | Count | v4.1 fix |
|---|---|---|---|---|---|
| 1 | bug | `uak done` | Unquoted `--evidence` text failed with "Unexpected argument" | 3 | trailing words are appended to the evidence |
| 2 | friction | any | "Set UAK_AGENT or UAK_HUMAN" in the main checkout | 3 | clearer error + `git config uak.agent NAME` fallback |
| 3 | bug | `wt new` / `uak` | A lead's exported `UAK_AGENT` overrode the worktree's `.uak-env`: a subagent's claim landed under the lead's name | 1 | `.uak-env` wins inside its worktree (`UAK_ENV_OVERRIDE=1` to keep the export); `wt new` warns |
| 4 | bug | dependencies | A PR merged on GitHub stayed REVIEW in uak; only the offline owner could close it; dependents blocked for hours | 3 | `uak integrate ID`: any agent records a verifiable merge; the dependency error names it |
| 5 | bug | `uak claim` | A claim taken after the code existed stored the finished tip as its base → "TIP equals the claim base; nothing implemented" | 2 | the claim base is the fork point with the remote base |
| 6 | friction | `uak review` | Reviewers lost eligibility the moment their own task merged; only a human could re-register them; reviews stalled overnight | 2 | agents with a task integrated in the last 24 h stay eligible |
| 7 | friction | scope gate | 4 of 11 decisions were "this task adds a new test file outside its Paths" (15 min wait each) | 4 | `Additive-Paths: e2e/, tests/` lets NEW files there merge |
| 8 | bug | `STATE.md` | Lists were silently cut at 120 chars: INTEGRATED looked stuck at UPS-015 with 26 tasks done | 1 | counts + last 12 IDs |
| 9 | bug | shell | `pkill -f "...port 8220"` killed the agent's own shell (exit 144) twice | 2 | guard blocks `pkill -f`/`killall`; `wt stop` kills exact PIDs on the worktree ports |
| 10 | friction | `wt new` | "address already in use" on the assigned port (leftover servers, IDs 90 apart) | 3 | `wt new` skips busy ports; `wt rm` stops the worktree's servers |
| 11 | friction | `gh pr create` | A fine-grained token without "Pull requests: write" blocked PR creation for a day | 2 | `wt pr` prints the compare URL for the human |
| 12 | bug | Verify | e2e passed 12/12 only because of a stale `web/dist`; a fresh build failed 3 steps | 1 | LOOPS.md: Verify builds from scratch; never trust build output older than the diff |
| 13 | friction | merges | The generated `docs/permissions-matrix.md` conflicted in several PRs | 2 | PROTOCOL.md: generated files get one owner; others regenerate after `git merge origin/main` |
| 14 | need | plan limits | The 5-hour usage limit hit at night with work in flight; the session stopped until the reset | 1 | `uak pace` + the statusline: the guard halves parallelism and blocks the strong tier before the limit |
| 15 | need | feedback | The same kit errors repeated across sessions; the only record was 30 MB of transcripts | — | `uak bb`: the black box (this file's format) |
| 16 | praise | protocol | Overlap CONFLICTs and stale-SHA rejections caught real problems (approving an old SHA after a 10-line fix) | 4 | kept |

## As black box lines

```text
- 2026-10-07T06:10Z | v4.0.0 | claude-code | marathon | auto | exit2 | uak done | ERROR: Unexpected argument: UX pass (redesign-existing-projects) at <sha> | fix: -
- 2026-10-07T06:40Z | v4.0.0 | claude-code | marathon | auto | exit2 | uak inbox | ERROR: Set UAK_AGENT or UAK_HUMAN. | fix: -
- 2026-10-08T07:20Z | v4.0.0 | claude-code | marathon | agent | bug | wt new | the claim landed under the lead's name because UAK_AGENT was exported | fix: .uak-env should win inside its worktree
- 2026-10-08T05:50Z | v4.0.0 | claude-code | marathon | auto | exit3 | uak claim | CONFLICT: UPS-N depends on UPS-N; claim it after INTEGRATED. | fix: -
- 2026-10-08T05:51Z | v4.0.0 | claude-code | marathon | agent | friction | uak done | PR merged on GitHub but the task stays REVIEW until its offline owner closes it | fix: let any agent record a verifiable merge
- 2026-10-08T15:30Z | v4.0.0 | claude-code | marathon | auto | exit3 | uak done | CONFLICT: TIP equals the claim base; nothing implemented. | fix: -
- 2026-10-08T15:31Z | v4.0.0 | claude-code | marathon | agent | friction | uak review | reviewers lose eligibility when their task merges; only the human can register them | fix: recent agents stay eligible
- 2026-10-08T21:00Z | v4.0.0 | claude-code | marathon | agent | friction | scope | new e2e test files outside Paths needed a 15-minute decision each | fix: allow new files in test dirs
- 2026-10-07T07:00Z | v4.0.0 | claude-code | marathon | agent | bug | shell | pkill -f with a port pattern killed my own shell (exit 144) | fix: kill exact PIDs
- 2026-10-08T10:00Z | v4.0.0 | claude-code | marathon | auto | exit1 | uvicorn | ERROR: [Errno 98] address already in use (127.0.0.1:<port>) | fix: pick a free port
- 2026-10-07T06:20Z | v4.0.0 | claude-code | marathon | agent | need | gh pr create | fine-grained token lacks Pull requests: write; no fallback to open the PR | fix: print the compare URL
- 2026-10-08T09:00Z | v4.0.0 | claude-code | marathon | agent | bug | verify | e2e green only because web/dist was stale | fix: Verify must rebuild
- 2026-10-09T03:50Z | v4.0.0 | claude-code | marathon | agent | need | limits | hit the 5-hour usage limit overnight with tasks open | fix: pace spending by plan usage
```
