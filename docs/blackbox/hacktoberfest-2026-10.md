# Black box · Hacktoberfest (Oct 27–28, 2026) · an overnight sprint, reconstructed from claims

Source: one sprint-mode hackathon on kit v5.4.2 (5 humans, 13 agent identities on 6 macOS and Windows laptops,
Claude Code and Codex, 35 tasks over ~16 h overnight, 33 reviews, 179 messages, 68 decisions), read from the claims
branch: `blackbox/*.md` from 6 machines, `inbox/log.md`, `DECISIONS.md`, the reviews and the product's code on `main`.
33 of 35 tasks integrated, 1 cancelled, 1 (real fixtures with API keys) left claimed with an expired lease.
Status column: what v5.5.0 does about it (**fixed**, **rule** in the mode file, or **kept** as designed).

| # | Kind | Where | What happened | Count | Status |
|---|---|---|---|---|---|
| 1 | bug | review rotation | 22 review offers went to a human's `UAK_HUMAN` name, each waiting 15–20 min for the re-offer. The kit marks humans `Role: human`, but on macOS `meta/agents/Name.md` opened the `name.md` already there (case-insensitive file system): the role landed on the lower-case name and the rotation compared names case by case | 22 offers | **fixed**: humans are matched case-blind |
| 2 | bug | `uak review` | A task was rejected for a real bug (named SSE events never reached the delivery view); 15 min later another reviewer approved the same SHA, the approve replaced the reject, and the task merged. The bug surfaced ~10 h later in the end-to-end test and needed a follow-up | 1 | **fixed**: a reject stands until a new commit; only the rejecter can change it |
| 3 | bug | `uak review` | `review --start` said CONFLICT (another agent held the review), the reviewer's chained command still sent its approve, and it was recorded while the holder reviewed | 1 | **fixed**: no verdict while someone else holds the review of that SHA |
| 4 | bug | merge gate | A test repository under `app/fixtures/…/supabase/migrations/*.sql` went to the human queue as a shared resource (migrations) | 1 | **fixed**: fixtures and test data are not shared resources |
| 5 | friction | merge gate | Two stacked branches carried a dependency's new file (a demo fixture, a drafts file) and went to the human queue as "New file outside Paths", with nothing about whose file it was | 2 | **fixed**: the reason names the owning task and the order (merge it first, then `git merge origin/main`) |
| 6 | bug | merge gate | An approved e2e task failed in the gate with "no UAK_PORT": the merge ran from the main checkout, which has no `.uak-env` | 1 | **fixed**: the gate gives the candidate its own port (above the worktree range) |
| 7 | friction | merge gate | 4 "PRODUCT_FAIL: adapter exit=1/2" from lint errors that only appeared when two unmerged branches met (one task's ruff config, the other's code), and 1 exit 127 on Windows | 5 | kept: the gate was right; exit 127 not reproducible from claims (the log stays on that laptop) |
| 8 | bug | permissions | The deny rule `Read(./.env.*)` also covered `.env.example`. An agent could not add two variable names a reviewer asked for; a human had to edit the file, and four other merges waited on it | 1 (blocked 4) | **fixed**: the deny list names the secret variants (`.env.local`, `.env.production`, …) |
| 9 | friction | `uak done` | `done` failed 3 times in a row on one machine (first `--pr`, then `--evidence`) and 3 more elsewhere; `wt pr` and the hints never named the flags | 6 | **fixed**: one error names both flags and prints the whole command; `wt pr` prints it too |
| 10 | friction | `uak claim` | 31 refused claims of tasks that depended on, or overlapped, one task in REVIEW; one agent retried 14 times in 40 min | 31 | **fixed**: the refusal says not to retry and gives `uak wait ID --for integrated` |
| 11 | bug | `uak status` | `status --task` printed AVAILABLE for a task whose claim had already landed; `wt new` then failed with CONFLICT | 1 | **fixed**: a claim without its task record shows as claimed |
| 12 | friction | Codex on Windows | 5 lines of "Git metadata writes require sandbox escalation": a worktree's `.git` (index, refs, uak state) lives in the main checkout, outside Codex's writable workspace | 5 | **fixed**: `wt new` prints `codex --add-dir <shared .git>`; `AGENTS.md` says so |
| 13 | bug | `wt stop` on Windows | "nothing listening" while the task's API kept serving: Git Bash has neither `lsof` nor `ss` | 1 | **fixed**: `netstat -ano` (state word not matched: it is localized) and `taskkill /T` |
| 14 | friction | network | Parallel `status`/`review --start` fetches on venue Wi-Fi retried for 5+ min; one reviewer gave up ("Operation too slow") | 2 | kept: retries worked; a shared read cache is a future item |
| 15 | friction | leases | 12 `REQUIRES_RECOVERY` leases, most overnight (no session open from ~00:30 to 05:00 local); 2 humans' tasks were reassigned by message | 12 | kept: no work was lost |
| 16 | hole | plan | The pipeline looked up `run_stage(ctx)` in 8 service modules (a contract sent to 16 tasks); no task wrote one. Every run, whatever the idea typed, replayed the same recorded project; the pitch room answered "I don't have that data" | 1 (the product) | **rule**: a contract that says "each module exposes X" needs a task that implements X; a fallback to the recording must say so; `/uak-demo` rehearses with an input that is not in the fixtures |
| 17 | hole | plan | No API keys during the event: every service shipped on hand-written `demo_data` fixtures; the task that needed a human with keys to record real fixtures stayed claimed, lease expired | 1 | **rule**: get keys in the first hour; a task only a human with keys can finish is P0 with a named human |
| 18 | praise | protocol | Rejects with `file:line` caught real gaps (missing env names, simulated fixtures presented as real, scope creep into another task's files, a Verify naming a file that did not exist); the e2e task found three UI bugs that became follow-ups | 9 rejects | kept |

The frontend held: one design lock picked from three screenshotted directions, a shared UI kit, `design-lint`
passing on every UI task. The demo looked like one product; what failed was the data behind it (16, 17).
