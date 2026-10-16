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
| `UAK_MAIN_CHECKOUT` | Set by the merge gate for smoke and Verify: the main checkout, where git-ignored data and `.venv` live. |

`.uak/PROJECT.md`, `.uak/TASKS.md` and `.uak/OWNERS.md` are read from the **remote base branch**, never from a stale worktree.

## PROJECT.md config fields
`Mode` (sprint|marathon) · `Pace` (auto|off) · `Blackbox` (on|off) · `Additive-Paths` (dirs where NEW files skip the scope gate, e.g. `e2e/, tests/`) · `Autonomy` · `Auto-Merge` · `Backlog-Approved` · `Backlog-Proposed-Epoch` · `Review-Mode` (claims|gh|auto) · `Plan-Channel` (claims|main) · `Freeze-Epoch` · `Lease-Seconds` · `Review-Lease-Seconds` · `Events-Per-Session` · `Checkpoint-Percent` · `Merge-Lease-Seconds` · `Merge-Wait-Seconds` · `Max-Parallel-Subagents` · `Opus-Subagents-Per-Session` · hard limits that pacing never raises: `Subagent-Hard-Cap` · `Strong-Hard-Cap` · `Subagents-Per-Session` · `Subagents-Per-Machine` · `Subagent-Burst-Per-Minute` · `Max-Worktree-Agents` (COSTS.md) · `Output-Cap-Chars` (default 12000, `off`: shell outputs bigger than this reach Claude Code, Codex and Cursor agents as head + tail + log path; a diff becomes a per-file index) · `Merge-Adopt-Seconds` (default 1200: after an approval this old, any eligible agent may merge the task). A missing yes/no field means `no`.

## TASKS.md fields
`## ID · title` (ID = `PREFIX-NNN`) · `Priority: P0|P1|P2` · `Paths:` (comma-separated, dirs end in `/`) · `Depends on:` (IDs or `None`; parentheses are ignored) · `Uses contract:` (soft, notify-only) · `Related:` · `Verify:` (an exact command) · `Next step:` · `Estimate:` · `Freeze-Allowed: yes`.

## Commands
| Command | Effect |
|---|---|
| `next [--full]` | Your current task, or the best eligible one (priority, deps, path overlap, owners, freeze). When idle, it first suggests merging an approved task whose owner has not merged it after `Merge-Adopt-Seconds`, then a review of a SHA that has no approval yet. After the freeze it says so and how a human allows a task. Never reserves. |
| `status [ID \| --task ID] [--summary] [--full]` | Remote state. If the deadline reconcile it runs first cannot push, it says `NOTE: deadline reconcile skipped` and still answers. `--summary` prints the live summary and a `Read-token`. The same output twice in one agent session prints `= unchanged …` (`--full` reprints; `UAK_DEDUPE=off` disables). |
| `claim ID --branch B --worktree W [--next T]` | Reserves the task. Use `wt new`, which calls it. One identity holds one CLAIMED/BLOCKED task (`UAK_MULTI_CLAIM=1` overrides). |
| `heartbeat ID` | Renews your lease. On your own task that is already INTEGRATED or CANCELLED: `OK … nothing to renew`. |
| `release ID [--cancel REASON]` | Frees your claim (AVAILABLE or CANCELLED). The summary is kept for the next claimer. |
| `release ID --expired --read-summary TOKEN` | Recovers an expired claim after reading its summary. |
| `log ID [--state CLAIMED\|BLOCKED] TEXT` | Appends a one-line event. |
| `checkpoint ID\|--session --done --decision --why --fails --commands --next` | Rewrites the six-field live summary and resets the budget. |
| `handoff ID` | Prints the summary for the next session. |
| `decision ID --option --why --reversible yes\|no --authorized yes\|no --class routine\|money\|accounts\|publish\|scope` | Opens a decision. After 15 min, only an authorized, reversible, routine decision is applied. |
| `done ID --pr URL --evidence TEXT [--to NAME] [--note TEXT]` | Moves the task to REVIEW and asks ONE reviewer in ONE message: `--to NAME`, or by rotation (whoever rejected the previous SHA, then another human's agent, then idle agents, then the least loaded; never retired identities). `--note` says what changed since the last review. |
| `integrate ID [--integrated COMMIT]` | Any agent records a task whose approved SHA is already in the remote base (a human merged on the forge while the owner was away). On an INTEGRATED task: `OK … already INTEGRATED`. |
| `followup ID --title TEXT` | After ID is INTEGRATED: a new task (next free number) on ID's Paths, `Depends on: ID`, same Verify, P1, published on claims (`Plan-Channel: claims`). For fixes, polish and a reviewer's non-blocking notes; no human needed because the scope does not change. |
| `retire NAME...` | An identity with no session left leaves the reviewer rotation, and messages to it are refused. The agent itself or a human (`UAK_HUMAN`); refused while it holds a CLAIMED/BLOCKED task. A new claim brings it back. |
| `handover ID --to NAME` | Passes a live claim (branch, worktree, summary) to NAME without AVAILABLE: the owner, a human (`UAK_HUMAN`) or anyone once the lease expired. Renews the lease, rewrites the local worktree's `.uak-env` and sends NAME one message. One identity = one live task still holds. |
| `done ID --pr URL --evidence TEXT --integrated COMMIT` | Records a human merge. It needs a current approval and proof of ancestry or tree. |
| `review ID --start` | "I am reviewing this SHA" for 20 min (`UAK_REVIEW_LOCK_SECONDS`): another agent gets CONFLICT, `next` stops suggesting it, an approved SHA prints SKIP. The verdict releases it. |
| `review ID --stop` | Gives your review lock back (you could not finish). |
| `review ID --sha SHA --verdict approve\|reject [--note TEXT]` | Reviews the task's current HEAD (a 7+ char prefix is fine). The reviewer must not be the owner. `--note` goes in the same message. A second approval of an already approved SHA records nothing. If HEAD moved, the CONFLICT says how many commits and files changed since your SHA. When everything after your SHA is a clean merge of the base, the verdict is recorded on HEAD (`Carried-From`). |
| `register-reviewer NAME...` | The human (`UAK_HUMAN`, from the main checkout) grants the reviewer role to one or more identities in one call. |
| `allow ID... --reason TEXT` · `allow --in-flight --reason TEXT` | Human freeze exception (`UAK_HUMAN`): the tasks may be claimed and merged after `Freeze-Epoch`. Audited in `claims:backlog/ALLOW.md` and DECISIONS.md. `--in-flight` allows every CLAIMED/BLOCKED/REVIEW task. |
| `clock "START" "DEADLINE" [ZONE] [--write]` | Sprint schedule scaled to the event length: first claim, design lock, skeleton, plan-B, freeze (15% of the event, 30 min to 6 h), rehearsal, submission. `--write` sets `Freeze-Epoch`. |
| `merge ID` | Exclusive leased queue. Re-checks the approved SHA, base, scope (what the merge changes in the current base), secrets, smoke and Verify, then pushes base and claims atomically. On any failure it goes to the human queue (exit 3) and prints the fast path: merge on the forge, then `uak integrate ID`. With no approval on the current SHA yet it prints `MERGE_WAIT` and queues nothing. An approval stays valid when the only later commits are clean merges of the base (each a 2-parent merge with the base, whose tree is what git computes: no hand edits). The owner merges during the first `Merge-Adopt-Seconds` after the approval; then any eligible agent can (`Merged-By` is recorded). A busy queue prints `MERGE_BUSY` (retry later), not a human entry. The gate puts the worktree's or the main checkout's `.venv` (or `venv`) first on PATH and exports `UAK_MAIN_CHECKOUT`; a red gate keeps its log in `.git/uak-out/gate-*.log` and the reason quotes the error line. Scope reasons say whether a file is new or edited, which task reserves it, and the fix; a new empty file (`__init__.py`, `.gitkeep`) is always allowed. |
| `plan FILE` | Publishes `## ID` sections (and `\| pattern \| ID \|` owner rows) to `claims:backlog/` without a PR. Needs `Plan-Channel: claims` and `UAK_HUMAN`. |
| `graph [--mermaid] [--min-wave1 N]` · `graph --assign` | Backlog DAG: waves, cycles, missing deps, critical path. See GRAPH.md. `--assign` suggests one idle agent per ready task (dependencies INTEGRATED): first whoever integrated work in the same folders, then the fastest; one task per agent. A suggestion: agents still claim with `wt new`. |
| `loop --verify CMD [--agent CMD] [--max N] [--minutes M] [--task ID] [--protect REGEX]` · `loop … --parallel N --each "CMD {}"` | Autonomous verify → fix loop. Stops on pass, budget, the same failure twice, an iteration where the agent changed nothing, or an edited/deleted existing test (the verifier; `--protect` sets the pattern). `--parallel` runs one sub-loop per failing test file (pytest `FAILED`/`ERROR`, jest/vitest `FAIL`, go `FAIL pkg`) in temporary worktrees of the current state, applies the passing fixes here and runs Verify once. Logs in `<git dir>/uak-out/loop-*.log`. See LOOPS.md. |
| `board [--md] [--watch S]` | Team kanban from the claims branch: state, owner, lease left, PR, wave, title. `--md` prints a GitHub table. |
| `stats` | Retro numbers: tasks by state, messages by kind and agent, review verdicts per reviewer, lease recoveries, human-queue reasons. |
| `up N [--prefix P] [--tool CMD] [--tmux]` | Claims the N best eligible tasks for agents `P-1..N`, one worktree each. With `--tmux`, opens a window per worktree running CMD. |
| `demo [--keep] [--fast]` | A real 3-agent run in a temp repo (claims, a conflict, a loop, a review, a merge, an unlock). No network or keys. |
| `tokens [--team] [--by task\|harness\|model\|scope\|agent] [--since DAYS] [--publish] [--json]` | Real token spend from the transcripts Claude Code (`~/.claude/projects`, subagents included, deduped by message id) and Codex (`~/.codex/sessions`) already write: input, cache write, cache read, output, share and cache hit per key. The task comes from the worktree folder (`<repo>-wt/<id>`), so removed worktrees still count. `--publish` writes this machine to `claims:tokens/<machine>.md` (the Stop hook does it every 30 min); `--team` adds all machines and names the task owner. `stats` and `digest` show the total. Cursor keeps no local token log. |
| `map` · `map show` · `map find NAME` · `map callers NAME` · `map calls NAME` · `map deps FILE` · `map users FILE [--depth N]` · `map path A B` · `map related FILE` · `map impact [--tasks] ID\|FILE…` | Code map (`<git dir>/uak-map/`, rebuilt when HEAD or the tree changes; Bash + awk, no LLM): symbols with file:line, resolved in-repo imports (Python, JS/TS with `@/`, Go packages, Rust, shell, Ruby, C includes), call edges (each `name(` resolved through the file's own definitions, its imports or its Go package; the caller is the enclosing definition), and `MAP.md` (areas, hubs, most-called functions, entry points, area dependencies, files per task). `impact` lists the files outside a task's Paths that import them, the functions they use, and the tasks that own them. `related` labels neighbors EXTRACTED or INFERRED. |
| `map notes [--agent CMD] [--max N] [--dry-run]` | Optional semantic pass: the fast-tier model (`claude -p --model haiku`, else `codex exec -m gpt-6-luna -`, or `--agent`) gives the most connected files a purpose and concepts, in batches of 6; cached by content hash in `<git common dir>/uak-map-notes.tsv`, so only changed files are sent again. Adds a purpose column, a Concepts section and INFERRED edges (2+ shared keywords, no import between them). ~1k input tokens per file. |
| `pace [--caps\|--json]` | Plan pacing: budget left vs time left per usage window (Claude statusline, Codex logs, `pace set`). Prints surge/normal/conserve/critical and the subagent caps the guard applies. See COSTS.md. |
| `pace set USED --resets +3h [--window 5h\|7d\|30d]` · `pace clear` | Record usage by hand (Cursor, Gemini, any dashboard). |
| `bb add bug\|friction\|need\|idea\|praise TEXT [--fix IDEA]` | Black box: one anonymous line about the kit. `bb flush` · `bb show [N]` · `bb export` (writes `.uak/BLACKBOX.md`) · `bb status`. See BLACKBOX.md. |
| `version` | Prints the kit version. |
| `doctor [--fix]` | Minute-0 preflight: remote, push, gh permissions, hooks (and their executable bit), `.gitignore`, mode, freeze, ports, a repo inside OneDrive/Dropbox/iCloud. |
| `msg TO TEXT [--kind K] [--task ID]` | TO: `NAME`, `ID`, `related:ID` (TASKS.md edges), `impact:ID` (tasks whose files import ID's files, from the code map), `all`, `human`, or a comma list. Sends an append-only message (one line, even for many targets; refused to a retired identity). Targets: `NAME`, `ID`, `related:ID`, `all`, `human`. Kinds: `info`, `request`, `contract`, `blocker`, `reply`, `review`, `approve`, `reject`, `integrated`, `human`. A short `reply` that is only an ack is refused (use `inbox --ack`); messages over 1200 chars are refused. A newer `contract` from the same sender and `--task` supersedes the older one: the inbox shows only the current one, `inbox --task` marks the old one. |
| `inbox [--ack] [--all] [--peek] [--task ID] [--human] [--full]` | Shows unread messages; `--ack` marks them read. Unread messages already shown in this session print one line. |
| `wait [ID] --for approve\|integrated\|message [--timeout S]` | One call that returns when it happens, instead of polling `status`/`inbox`: an approval or reject of your REVIEW task (exit 0/3), a dependency INTEGRATED (0), a new message (0, printed). A `git ls-remote` every 15 s (`UAK_WAIT_EVERY`); claims are read only when their tip moves. Default timeout 540 s (exit 4). |
| `learn "TEXT" [--path P,Q] [--task ID]` · `learn --forget N` | A lesson (a gotcha or a convention, ≤300 chars) tied to paths, on `claims:memory/LESSONS.md`. Default paths: the task's (`--task` or `UAK_TASK`); `--path "*"` for everyone. `next` shows the newest 3 for the task it proposes or you hold; `review … --verdict reject --note T --learn` records the note. |
| `recall [ID\|PATH]` | The lessons for a task's Paths or a path, newest first. |
| `digest` | The human's single summary: reviews, blockers, decisions. 30 min before `Freeze-Epoch`, `digest` and `next` warn once. |
| `tick` | Evaluates deadlines (backlog, decisions, leases, freeze, queue). `next` and `status` run it. |
| `init-smoke --command CMD` | Builds `.uak/bin/smoke-project` from your real product check. |
| `secret-exception ID --path P --rule R --reason T` | A non-owner reviewer approves one exact index blob. |
| `lint [--secrets]` | Checks budgets, the PR template, states, history, owners, the sprint freeze and graph cycles. |

## Helpers
| Script | Use |
|---|---|
| `bash .uak/bin/wt new ID --agent NAME` | branch `feat/<id>` + worktree `../<repo>-wt/<id>` + `.uak-env` + port + claim |
| `bash .uak/bin/wt session` · `wt rm ID` · `wt ls` · `wt stop [ID]` · `wt pr` | rotate the session · remove your worktree (never `--force`; stops its servers) · list worktrees · stop the servers on the worktree ports (exact PIDs) · print the GitHub compare URL when `gh pr create` lacks permission |
| `bash .uak/bin/q CMD` | quiet runner: one line on success, the tail on failure, full log in `<git dir>/uak-out/q-*.log` (one per run, last 20) |
| `guard agent` / `guard agent-stop` | Claude Code, Codex and Cursor hooks: subagent parallel cap and strong-tier budget per session (scaled by `pace`), spawn log (`.git/uak-agents.log`). Human override: `UAK_ALLOW_OPUS=1`. |
| `guard shell` · `guard tier MODEL` | Cursor `beforeShellExecution` payloads · prints a model's tier (fast/balanced/strong). |
| `bash .uak/bin/statusline` | Claude Code status line: task, 5 h/7 d usage, context, pace. Caches `rate_limits` for `pace`. |
| `bash .uak/bin/guard check "CMD"` | ask the guard before running (Codex, Cursor and others without hooks) |
| `bash .uak/bin/smoke [--package-only]` | product smoke, or the kit's own 90+ integration tests |
| `hook wrap` · `hook wrap codex` · `bash .uak/bin/cap LOG RC \| --shape LOG \| --b64 CMD64` | Cursor preToolUse(Shell) and Codex PreToolUse(Bash) rewrite noisy low-risk commands (tests, builds, linters, read-only git/search; never `cat`/`sed` reads) so `cap` prints them whole or cut. bash/zsh: a `{ }` group in the same shell. Windows and Codex: the command goes base64 to `cap --b64` (PowerShell and bash read it the same; skipped when it has `$`, `\`, backticks, `cd`/`export` or a PowerShell cmdlet). |
| `bash .uak/bin/hook output` | Claude Code PostToolUse(Bash): outputs over `Output-Cap-Chars` become head 30 + tail 50 lines (a diff: a per-file index with line ranges) + the path of the full log (`.git/uak-out/`). `UAK_RAW=1 cmd` opts out. |
| `hook tick` coach · `.uak/reminders.md` | Event-driven reminders injected after a tool call (Claude Code, Codex; Gemini via AfterTool), each capped per session: 5 reads in a row → the code map; the third status/inbox look in 10 min → `uak wait`; a `git push` whose files other live tasks import with no contract sent → `msg impact:ID`; `uak done` → `uak wait`; a repeated kit error → `bb add friction`; 40 calls without a checkpoint → checkpoint. Session start prints the quick card (when X → run Y). Templates in `.uak/reminders.md`; `UAK_COACH=off` disables it. |
| `.uak/bin/uak-mcp` (MCP server) | The harness as native tools in any MCP client: `uak_next`, `uak_status`, `uak_claim`, `uak_ship`, `uak_wait` (progress notifications, cancellable), `uak_review`, `uak_merge`, `uak_message`, `uak_inbox`, `uak_map`, `uak_memory`, `uak_checkpoint`, `uak_tokens`, `uak_cli`; resources `uak://map`, `uak://status`, `uak://lessons`, `uak://card`, `uak://agents`, `uak://task/{id}`, `uak://recall/{id}`; the `/uak-*` workflows as prompts. Dual-era: MCP 2026-07-28 (stateless `_meta`, `server/discover`, `resultType`, `ttlMs`) and 2025-11-25/06-18/03-26 (`initialize` with instructions). Configured by `.mcp.json` (Claude Code; approve it once), `.codex/config.toml`, `.cursor/mcp.json`, `.gemini/settings.json`. Python 3.8+ standard library; every tool runs the same uak CLI and gates. In the main checkout pass `agent`. Optional: tools and the Bash CLI mix freely on the same state; `install.sh --no-mcp` leaves the config out. |

## Exit codes
`uak CMD --help` prints that command's usage. IDs are case-insensitive (`hack-021` = `HACK-021`); an invalid ID error shows the value you passed. No identity: prefix the command, `UAK_AGENT=NAME bash .uak/bin/uak CMD`.

Messages on stderr: `LOOP:` = the same error 3 times in 10 min on this machine; stop retrying. `RETRY` = claims contention, retried with jittered backoff (max 30 attempts).

`0` ok · `1` Git or remote failure (network retried 3 times), or lint failed · `2` invalid input, or PRODUCT_UNVERIFIED · `3` conflict or gate denied (including the human merge queue).
