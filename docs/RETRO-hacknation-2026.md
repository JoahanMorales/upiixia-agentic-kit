# Retro · Hack-Nation 2026 (Challenge 05, AI Atlas for Rare Diseases)

**Team:** 4 humans and 5 agents (Claude Code and Codex) on 3 machines, one of them a Jetson Orin Nano.
**Window:** 2026-10-03 21:30 UTC → 2026-10-04 11:50 UTC, about 14 h of active coordination.
**Sources:** the `claims` branch (774 commits), `inbox/log.md` (720 messages), `DECISIONS.md` (116 entries) and 76 GitHub PRs. Agents are named by role, not by person.

## Outcome
- 75 PRs merged and 1 left open (the submission task). The backlog had 34 tasks, in 3 waves.
- The product: an atlas of 12,867 rare diseases. It offers diagnosis from dictated symptoms, an evidence inspector with citations, a pathway navigator, and sourced collaboration proposals.
- Quality: 29 approvals, plus formal rejects that caught real bugs. One example: the validation benchmark used a different `clip()` than production and reported a top-1 score 2 points too high.

## What worked (kept)
| Piece | Evidence |
|---|---|
| Worktree + branch + claim per task (`wt new`) | 75 PRs from 5 parallel agents. Path overlaps were rejected at claim time, not at merge time |
| The `claims` branch as the database | 774 coordination commits from 3 machines, with no server |
| Contracts and mocks before the wave | Frontend and backend moved in parallel from hour 1 |
| Cross-review that runs, not just reads | It caught the `clip` divergence, an overlay hiding a Close button, and a 1.2 s intro that never played |
| `q` and runner subagents | Test logs never entered the main context |
| Live summary + read token | Tasks were resumed by another agent without reading any chat |
| `demo_data: true` and recorded responses | The demo worked with no network and no API key |

## What broke, with data
| # | Problem | Data | Root cause | v3 fix |
|---:|---|---|---|---|
| 1 | The secret scanner detected nothing | The kit's security suite was red (4/8) and nobody noticed | Rules used awk `{n}`, which mawk (Ubuntu, Jetson) ignores | `grep -E` rules, a regression test, a `doctor` check |
| 2 | Destructive ops despite the deny list | 1 force-push, 2 `worktree remove --force` | The settings deny list matches prefixes; `cd x && git push --force` doesn't start with `git push` | `guard` PreToolUse hook that checks every segment |
| 3 | Secrets in chat | 1 API key and 1 sudo password pasted by a human | No barrier on prompts | `guard prompt` UserPromptSubmit hook |
| 4 | Message noise | 720 messages; 194 were duplicate `integrated` notices; one agent sent 247 | One notice per related task, even for the same owner or already-merged tasks | One notice per owner, only for claimed tasks; the hook injects only actionable kinds |
| 5 | Expired leases | 38 `REQUIRES_RECOVERY` | A fixed 30-min lease, even while waiting for review | `Lease-Seconds` per mode; `Review-Lease-Seconds` (4×) |
| 6 | Backlog changes by PR | 8 `planning/*` PRs; 3 merges to the human queue over TASKS.md | The backlog lived only on `main` | `uak plan` publishes to `claims` (sprint) |
| 7 | Dependency parser | 2 PRs to reword `Depends on` | It read any ID, including inside parentheses | Parentheses ignored; `Uses contract:` soft edges; `uak graph` |
| 8 | The human as a traffic light | Humans merged all 75 PRs, and one gh token couldn't create PRs | No permission preflight | `uak doctor` at minute 0; `/uak-ship` continues with a manual PR URL |
| 9 | An agent out of tokens holding work | A task waited for its lease to expire | Review load concentrated on one agent; no "low on tokens" protocol | Reviewer rotation by load; `handoff` + `release` |
| 10 | No freeze | `Freeze-Epoch: 0`; 8 PRs, including a product rename, in the last 6 h | The field was optional | Freeze required in sprint (`lint` and `doctor` fail without it) |
| 11 | Visual churn | 4 global visual directions in 8 h | No moment of visual decision | `/uak-design-lock` at T0+1h; after that, a human decision |
| 12 | Submission at risk | The submission PR stayed open | Assigned to an agent that ran out of tokens | A human owns submission from T−8 h |
| 13 | Unverified citations | DOIs written from memory into curated data | No explicit rule | AGENTS.md §1.6; the reviewer opens 2 sources at random |
| 14 | Wrong SHA in notices | 2 contract messages with a stale SHA | `;` kept going after a failed commit | AGENTS.md §4.3: always `&&` |
| 15 | Fake UI failures | Red checks from 3–6 s animations on software WebGL | Fixed sleeps in checks | Reduced motion + waiting for the final state |
| 16 | Port conflicts | 8000 was taken on the Jetson | Fixed ports | `UAK_PORT` per worktree |
| 17 | `wt` bug | `tr: invalid range` when deriving the human's name | `.-\n` inside `tr -c` is a range | Fixed |
| 18 | Frozen rules | "Don't edit AGENTS.md during the event" blocked rule fixes | Prompt-cache invalidation | Amendments via `uak decision`; AGENTS.md cut from 114 to 60 lines |
| 19 | Retry spirals | Agents re-tried the same failing approach | No loop budget or stuck detection | The bounded inner loop (5 tries, 2 identical failures → stop) and `uak loop` |

## What we did not change, and why
- **Bash with no dependencies.** It ran the same on macOS, Linux and the Jetson. Moving to Node or Python would add an install step at minute 0.
- **One state vocabulary** (AVAILABLE … CANCELLED). No agent was ever confused about state.
- **Per-SHA reviews.** An approval of an old commit never counts for a new one.

## Top 3 for your next hackathon
1. Run `uak doctor` at minute 0, on every machine, until it passes.
2. Fix the freeze, the product name and the visual direction in hour 1.
3. Max 2 agents per human, and a human owns submission from T−8 h.
