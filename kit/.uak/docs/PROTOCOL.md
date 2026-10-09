# Protocol: state, leases, reviews, merges

## Source of truth: the `claims` branch
| Path | Content |
|---|---|
| `tasks/ID.md`, `claims/ID.md` | The durable record, and the live reservation (CLAIMED/BLOCKED/REVIEW) |
| `worklog/WL-*.md` | A 6-line live summary (Done, Decision, Why, Failing, Commands, Next) plus an append-only history |
| `inbox/log.md` | All agent messages, append-only |
| `backlog/TASKS.md`, `backlog/OWNERS.md` | Tasks and owners published with `uak plan` |
| `STATE.md`, `DECISIONS.md` | A bounded snapshot (60 lines or fewer), and decisions and receipts |
| `reviews/`, `roles/reviewers/` | Per-SHA approvals and reviewer roles |
| `queue/`, `deadlines/`, `meta/` | Merge queue and lock, deadline receipts, config, counters and sessions |

Every change is a commit pushed fast-forward. On contention, uak fetches, rebases, **re-validates every gate** and retries. Losing a race on one task never blocks a different task.

## Leases and continuity
- A claim lasts `Lease-Seconds` (sprint 2700, marathon 14400). In REVIEW it lasts `Review-Lease-Seconds` (4× by default), because reviews and humans are slow.
- An expired lease becomes `REQUIRES_RECOVERY`. The claim and summary are kept, never deleted. To recover, read the summary and pass its `Read-token`: proof that you read it.
- Running out of tokens: `/uak-handoff`, then `uak release ID`. The next `claim` reuses the same worklog and its exact `Next`.
- Budget: `Events-Per-Session` events. At `Checkpoint-Percent`, `CHECKPOINT NOW` blocks new claims until you checkpoint.

## Decisions and deadlines
| Situation | Mechanism |
|---|---|
| Backlog not approved | After 10 min, only P0 can start, and only with `Autonomy: yes`. |
| Reversible product question | `uak decision`. After 15 min an authorized routine option is applied and logged. |
| Money, accounts, publishing, scope | Never by timeout. The task stays BLOCKED; take another task. |
| Freeze (`Freeze-Epoch`) | New claims and merges only for `Freeze-Allowed: yes`. |

Deadlines run when any agent calls `next` or `status` (or cron or a GitHub Action calls `uak tick`). With nobody online, no deadline fires.

## Review and merge
1. `done` records the task tip and asks the least-loaded active agent for a review.
2. The reviewer runs Verify in a temp worktree, then `review --sha <current HEAD>`. A new push invalidates the approval.
3. `merge` (sprint, `Auto-Merge: yes`) takes a leased lock and re-checks everything against the **current** base:
   - the approved SHA;
   - the diff stays inside `Paths`;
   - no shared or CI files without an owner;
   - the secret scan;
   - `smoke` and Verify, with no tracked file modified.

   Then it pushes base and claims atomically. If anything fails, the task goes to the human queue (`digest`) and the agent moves on.
4. Human merges: `done ID --integrated COMMIT`, verified by ancestry or a rebuilt tree hash, so squash and rebase merges work.
5. In marathon, agents only pre-review. Humans merge through branch protection and CI.

## Merged outside uak
- A human merged the PR on GitHub and the owner agent is offline: any agent runs `uak integrate ID`. It needs a valid approval for the merged SHA and proof that the SHA is in the remote base. For a squash merge, pass `--integrated COMMIT`.
- Generated files that every task touches (permission matrices, OpenAPI dumps, snapshots) get one owner in `OWNERS.md`. Other tasks regenerate them after `git merge origin/main` instead of hand-merging.
- New test files outside a task's `Paths`: list the test dirs in `Additive-Paths` (PROJECT.md). New files there pass the scope gate; edits to existing files still need a reservation.

## Offline
If the remote is unreachable, `status` and `next` print `NO REMOTE`. No claim is created offline. Keep a local checkpoint and reconcile when the remote returns. Clock drift over 60 s (from the GitHub Date header) prints `CLOCK_SKEW`.
