# uak CLI reference

Every command runs as `bash .uak/bin/uak CMD`. It needs Bash 3.2+, Git with worktrees and POSIX tools; no jq and no Python (Python 3.8+ only for the kit tests). On Windows, use Git Bash. `gh` is optional, but `Review-Mode: gh` needs it.

## Environment
| Variable | Use |
|---|---|
| `UAK_AGENT` | Unique, stable agent identity (`ana-1`). `wt new` writes it to `.uak-env`. |
| `UAK_HUMAN` | Responsible human. Needed for `plan` and `register-reviewer`. |
| `UAK_SESSION` | One per session; `wt session` rotates it. |
| `UAK_TASK`, `UAK_PORT` | Set by `wt new`. The app listens on `$UAK_PORT` (API) and `$UAK_PORT+1` (web). |
| `UAK_REMOTE` / `UAK_BASE` | Default `origin` / `main`. |
| `UAK_LEASE_SECONDS` | Overrides `Lease-Seconds` from PROJECT.md. |
| `UAK_NOW`, `UAK_REMOTE_NOW` | Simulated clocks, for tests only. |
| `UAK_BLACKBOX=off` · `UAK_PACE=off` | Turn off the black box or pacing for one person. |
| `UAK_ENV_OVERRIDE=1` | Keep an exported `UAK_AGENT`/`UAK_TASK` even inside a worktree whose `.uak-env` says otherwise. |
| `UAK_HARNESS` | Overrides harness detection in black box lines. |

`.uak/PROJECT.md`, `.uak/TASKS.md` and `.uak/OWNERS.md` are read from the **remote base branch**, never from a stale worktree.

## PROJECT.md config fields
`Mode` (sprint|marathon) · `Pace` (auto|off) · `Blackbox` (on|off) · `Additive-Paths` (dirs where NEW files skip the scope gate, e.g. `e2e/, tests/`) · `Autonomy` · `Auto-Merge` · `Backlog-Approved` · `Backlog-Proposed-Epoch` · `Review-Mode` (claims|gh|auto) · `Plan-Channel` (claims|main) · `Freeze-Epoch` · `Lease-Seconds` · `Review-Lease-Seconds` · `Events-Per-Session` · `Checkpoint-Percent` · `Merge-Lease-Seconds` · `Merge-Wait-Seconds` · `Max-Parallel-Subagents` · `Opus-Subagents-Per-Session`. A missing yes/no field means `no`.

## TASKS.md fields
`## ID · title` (ID = `PREFIX-NNN`) · `Priority: P0|P1|P2` · `Paths:` (comma-separated, dirs end in `/`) · `Depends on:` (IDs or `None`; parentheses are ignored) · `Uses contract:` (soft, notify-only) · `Related:` · `Verify:` (an exact command) · `Next step:` · `Estimate:` · `Freeze-Allowed: yes`.

## Commands
| Command | Effect |
|---|---|
| `next` | Your current task, or the best eligible one (priority, deps, path overlap, owners, freeze). When idle, it suggests reviews. Never reserves. |
| `status [--task ID --summary]` | Remote state. `--summary` prints the live summary and a `Read-token`. |
| `claim ID --branch B --worktree W [--next T]` | Reserves the task. Use `wt new`, which calls it. |
| `heartbeat ID` | Renews your lease. |
| `release ID [--cancel REASON]` | Frees your claim (AVAILABLE or CANCELLED). The summary is kept for the next claimer. |
| `release ID --expired --read-summary TOKEN` | Recovers an expired claim after reading its summary. |
| `log ID [--state CLAIMED\|BLOCKED] TEXT` | Appends a one-line event. |
| `checkpoint ID\|--session --done --decision --why --fails --commands --next` | Rewrites the six-field live summary and resets the budget. |
| `handoff ID` | Prints the summary for the next session. |
| `decision ID --option --why --reversible yes\|no --authorized yes\|no --class routine\|money\|accounts\|publish\|scope` | Opens a decision. After 15 min, only an authorized, reversible, routine decision is applied. |
| `done ID --pr URL --evidence TEXT` | Moves the task to REVIEW and asks a reviewer by rotation (least loaded active agent). |
| `integrate ID [--integrated COMMIT]` | Any agent records a task whose approved SHA is already in the remote base (a human merged on the forge while the owner was away). |
| `done ID --pr URL --evidence TEXT --integrated COMMIT` | Records a human merge. It needs a current approval and proof of ancestry or tree. |
| `review ID --sha SHA --verdict approve\|reject` | Reviews the task's current HEAD. The reviewer must not be the owner. |
| `register-reviewer NAME` | The human (`UAK_HUMAN`) grants another identity the reviewer role. |
| `merge ID` | Exclusive leased queue. Re-checks the approved SHA, base, scope, secrets, smoke and Verify, then pushes base and claims atomically. On any failure it goes to the human queue (exit 3). |
| `plan FILE` | Publishes `## ID` sections (and `\| pattern \| ID \|` owner rows) to `claims:backlog/` without a PR. Needs `Plan-Channel: claims` and `UAK_HUMAN`. |
| `graph [--mermaid] [--min-wave1 N]` | Backlog DAG: waves, cycles, missing deps, critical path. See GRAPH.md. |
| `loop --verify CMD [--agent CMD] [--max N]` | Autonomous verify → fix loop with a budget and stuck detection. See LOOPS.md. |
| `board [--md] [--watch S]` | Team kanban from the claims branch: state, owner, lease left, PR, wave, title. `--md` prints a GitHub table. |
| `stats` | Retro numbers: tasks by state, messages by kind and agent, review verdicts per reviewer, lease recoveries, human-queue reasons. |
| `up N [--prefix P] [--tool CMD] [--tmux]` | Claims the N best eligible tasks for agents `P-1..N`, one worktree each. With `--tmux`, opens a window per worktree running CMD. |
| `demo [--keep] [--fast]` | A real 3-agent run in a temp repo (claims, a conflict, a loop, a review, a merge, an unlock). No network or keys. |
| `pace [--caps\|--json]` | Plan pacing: budget left vs time left per usage window (Claude statusline, Codex logs, `pace set`). Prints surge/normal/conserve/critical and the subagent caps the guard applies. See COSTS.md. |
| `pace set USED --resets +3h [--window 5h\|7d\|30d]` · `pace clear` | Record usage by hand (Cursor, Gemini, any dashboard). |
| `bb add bug\|friction\|need\|idea\|praise TEXT [--fix IDEA]` | Black box: one anonymous line about the kit. `bb flush` · `bb show [N]` · `bb export` (writes `.uak/BLACKBOX.md`) · `bb status`. See BLACKBOX.md. |
| `version` | Prints the kit version. |
| `doctor [--fix]` | Minute-0 preflight: remote, push, gh permissions, hooks, `.gitignore`, mode, freeze, ports. |
| `msg TO TEXT [--kind K] [--task ID]` | Sends an append-only message. Targets: `NAME`, `ID`, `related:ID`, `all`, `human`. Kinds: `info`, `request`, `contract`, `blocker`, `reply`, `review`, `approve`, `reject`, `integrated`, `human`. |
| `inbox [--ack] [--all] [--peek] [--task ID] [--human]` | Shows unread messages; `--ack` marks them read. |
| `digest` | The human's single summary: reviews, blockers, decisions. |
| `tick` | Evaluates deadlines (backlog, decisions, leases, freeze, queue). `next` and `status` run it. |
| `init-smoke --command CMD` | Builds `.uak/bin/smoke-project` from your real product check. |
| `secret-exception ID --path P --rule R --reason T` | A non-owner reviewer approves one exact index blob. |
| `lint [--secrets]` | Checks budgets, the PR template, states, history, owners, the sprint freeze and graph cycles. |

## Helpers
| Script | Use |
|---|---|
| `bash .uak/bin/wt new ID --agent NAME` | branch `feat/<id>` + worktree `../<repo>-wt/<id>` + `.uak-env` + port + claim |
| `bash .uak/bin/wt session` · `wt rm ID` · `wt ls` · `wt stop [ID]` · `wt pr` | rotate the session · remove your worktree (never `--force`; stops its servers) · list worktrees · stop the servers on the worktree ports (exact PIDs) · print the GitHub compare URL when `gh pr create` lacks permission |
| `bash .uak/bin/q CMD` | quiet runner: one line on success, the tail on failure, full log in `.git/uak-q.log` |
| `guard agent` / `guard agent-stop` | Claude Code, Codex and Cursor hooks: subagent parallel cap and strong-tier budget per session (scaled by `pace`), spawn log (`.git/uak-agents.log`). Human override: `UAK_ALLOW_OPUS=1`. |
| `guard shell` · `guard tier MODEL` | Cursor `beforeShellExecution` payloads · prints a model's tier (fast/balanced/strong). |
| `bash .uak/bin/statusline` | Claude Code status line: task, 5 h/7 d usage, context, pace. Caches `rate_limits` for `pace`. |
| `bash .uak/bin/guard check "CMD"` | ask the guard before running (Codex, Cursor and others without hooks) |
| `bash .uak/bin/smoke [--package-only]` | product smoke, or the kit's own 70+ integration tests |

## Exit codes
`0` ok · `1` Git or remote failure, or lint failed · `2` invalid input, or PRODUCT_UNVERIFIED · `3` conflict or gate denied (including the human merge queue).
