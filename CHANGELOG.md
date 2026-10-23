# Changelog

## v5.2.0 · 2026-10-23 · Delivery, the graph in the loop, and the whole team on one page
The second MLB autopsy ([the v5 week](docs/blackbox/mlb-2026-10-week2.md)): 67 review offers went to one named
agent and that agent gave 14 of the verdicts; 28 messages over the event reached identities that never came back.
- **Presence.** Each identity's last event, inbox read or message on claims. The reviewer pick prefers agents seen in the last 30 min (`Presence-Seconds`), then the last 3 h; a human's bare name never reviews.
- **Review offers move on.** An offer nobody starts within 15 min (`Review-Offer-Seconds`) goes to another agent on anyone's next `status`/`next`, from the scheduler, saying why; a live review lock holds it; after 3 offers it goes to `all`. `next` suggests a review while your own task waits in REVIEW.
- **Messages to offline identities.** They also reach the identity's live tasks and the sender gets a NOTE (a never-seen name is flagged as a typo). `next` lists unread requests and reviews that reached your offline identities; the same human's live identity may hand over a task whose owner has been offline for 1 h.
- **One identity per agent, reused.** `wt new ID` without `--agent` reuses this machine's identity with no claim, or takes the next number (`git config uak.name` sets the prefix). The MCP `uak_claim` no longer needs `agent`.
- **Human authority only from the shell.** Worktrees write `UAK_AGENT_HUMAN` (recorded for presence), not `UAK_HUMAN`; an older `.uak-env` is read the same way. Run `wt session` in an old worktree to refresh Claude's `settings.local.json`.
- **Merges.** An approval survives the PR's own merge commit after "merge on GitHub, then pull main" (the carried parent is the one containing the approved SHA). Follow-ups work on the paths their parent owns in OWNERS.md. The merge candidate links the worktree's `node_modules` when the lockfile is identical (a junction on Windows, removed before cleanup), else `npm ci`.
- **Reliability.** No uak call waits forever: without a terminal, git and ssh never prompt, connect in 15 s and drop a dead link in ~30 s. A sandbox that forbids git in the system temp dir gets one inside `.git`. `next` says when the worktree runs an older kit than the base.
- **Fixes.** The product CI checks shell files by shebang and parses `uak-mcp` as Python (bash -n on it failed every PR); `install.sh --update` keeps `.uak/bin/smoke-project`; Cursor and Codex reviewer/runner subagents can run Verify; `done` refuses a GitHub PR link to another repository; `msg impact:ID` with no importers is OK; `tasks`, `task ID`, `show ID`, `backlog`, `status --verbose` work; the guard no longer reads an uppercase `-D…` inside a clone URL as `branch -D`.
- **The graph comes to the agent.** The claim prints the task's slice of the code map (`map brief`: its files, what they define, who imports them, which tasks to warn). After a search for a symbol or a read of a file, the post-tool hook adds one line from the map index (`map lens`: definition and callers, importers, hub, outside the task's Paths), in Claude Code, Codex, Gemini and now Cursor; each symbol or file once per session, never a rebuild in the hook. Why: 9 agent calls of the map for 67 Claude Code tasks at MLB, and a pilot study measured 0–6% routing to a semantic tool when grep was there.
- **Cursor gets the post-tool hook** (`postToolUse` → `hook tick cursor`): automatic heartbeats, new messages after a tool result, reminders and map lines. Cursor agents polled 44.9 times per shipped task at MLB.
- **`uak plan FILE --amend`** (UAK_HUMAN): new Paths, Verify or criteria for published tasks while AVAILABLE, CLAIMED or BLOCKED; a claimed task's record takes the new Paths; overlaps with live claims and OWNERS rows are refused; REVIEW and INTEGRATED are refused (`followup`).
- **`impact:ID` reads the full backlog**: it failed for tasks published with `uak plan` (HACK-075..079 at MLB); its owners now come from the same backlog.
- **Adoption is measured.** Calls the hooks make are counted as `hook-CMD`, pushed map lines as `lens`, and `uak stats` prints agent calls per task and harness.
- **Sessions leave a trace.** Every heartbeat (sent by the hooks) writes the task's progress: commits since the claim, the last one, uncommitted files; `status --task` shows it to the next owner. `uak away` (run by the SessionEnd hooks of Claude Code, Cursor and Gemini; not on /clear) takes the identity out of the reviewer rotation at once and sends messages for it to its tasks; any uak command brings it back. Why: 74 checkpoints for 130 claims, 43 lease recoveries, 5 handoffs.
- **Past work comes back by words.** `claim` and `next` add the top 3 of what the team learned on similar work: lessons, reject notes, contract messages and decisions, ranked by the task's title, acceptance and Paths (BM25 in awk; at least 2 shared words; no model, no network). The live summaries of INTEGRATED tasks are ranked too (how something like it was solved). `uak recall ID --similar` and `recall --search "words"` show more. On MLB data a paper task got the earlier reject "the paper's numbers do not match label_shift.csv" from another task with other Paths; ~20 ms per query.
- **Upstream drift, told while working.** `map drift`: what the base changed since the branch last synced that touches the branch's files or the files they import, with the commit and the fix; the post-tool hook checks every 5 min in the background and says each change set once, and `done` repeats it. Why: STORM (arXiv 2605.20563) beat isolated worktrees by +18.7 on Commit0 by catching conflicts at write time.
- **Stalled tasks.** Heartbeats record when the work last moved (a new HEAD or other uncommitted files). A CLAIMED task still for 90 min (`Stall-Seconds`) is STALLED: the owner's `next` says to mark it BLOCKED with the error or hand it over; idle agents and the human digest see it. Why: 43 lease recoveries at MLB; "reassign an agent stuck on one error" (Addy Osmani).
- **GitHub feedback reaches the task.** `uak pr-sync [ID]` turns failed checks (with `gh run view RUN --log-failed`) and new human PR comments or change requests into one message to the task, once each; the owner's hook runs it every 5 min, the `uak-tick` Action for all tasks. Why: 52 of 59 MLB integrations were merged on GitHub, where CI and comments lived.
- **Commands come up when they apply.** `q` (where agents run their tests) says `LOOP:` on the same failure twice in a row, with the `log ID --state BLOCKED` command (the loop guards lived only in `uak loop`, 0 calls at MLB); `secret-scan` shows the `secret-exception` way out when it blocks; after a compaction the session start asks for a checkpoint; the human digest suggests `uak up N` or `graph --assign` from tasks waiting vs idle agents online.
- **A smaller project root.** `CLAUDE.md` installs as `.claude/CLAUDE.md` (Claude Code reads it there; it imports `../AGENTS.md`), the pre-commit scanner as `.uak/githooks`, and `install.sh --harness claude,codex,cursor,gemini` installs only the directories of the tools the team uses (`.agents/skills` only with Codex, `.mcp.json` only with Claude and MCP). A Claude-only install without MCP leaves `AGENTS.md`, `.claude/`, `.github/`, `.uak/` and `.gitignore` lines; the full one 10 entries instead of 12. `--update` moves an older install's kit-owned `CLAUDE.md` and `.githooks`; customized ones stay.
- **Spring Boot stack preset** (`--stack spring-boot`): package by feature, Initializr setup (current versions), `server.port: ${UAK_PORT:8080}`, ProblemDetail errors, MockMvc/Testcontainers tests, Flyway migrations with timestamp versions (`db/migration/` and `gradle.lockfile` are shared resources; `target/`, `.gradle/`, `*.class` are generated), a skill and the smoke example. The code map now resolves Java/Kotlin imports (package path, wildcard, static), Java methods and same-package calls across `src/main` and `src/test`, so `brief`, `lens` and `impact` work there.
- **`uak dash`: the whole team on one local page.** Progress % (integrated and in flight), a board by state, agents with GitHub-style identicons (pattern per human, color per identity) and presence, the conversation with filters, reviews waiting, stalled tasks, the human queue, the black box with adoption per harness, lessons, decisions and tokens. Read-only from claims, self-contained HTML that reloads its data file (works from file://), `--watch` keeps it current. The human digest points to it. Designed with the kit's `redesign-existing-projects` skill: one neutral palette with light and dark (auto or picked), state colors validated for color-blind separation (red never sits next to yellow in the bar), a "needs attention" list that collapses to one line when all is clear, integrated-per-day and messages-per-day charts with tooltips, task IDs that open their thread, short links and SHAs in messages, a freshness pill that says "Snapshot" when the data stopped moving, and a layout that works at phone width.
- `test_v51.py`: 20 scenarios, one per failure.

## v5.0.0 · 2026-10-15 · 5x faster, a code graph, team memory, the real bill
v5 folds in v4.3 (the MLB autopsy, below; it was never published separately) and closes most of the roadmap.
- **Speed: one network round trip per call.** One fetch brings claims and the base config together (no `ls-remote` prechecks); OpenSSH connection reuse for ssh remotes (`ControlMaster`, off on Windows and with a custom ssh command; `UAK_SSH_MUX=off`); the GitHub clock check is cached for an hour; `next` drops taken and blocked tasks before its gates. Measured on GitHub against a real 36-task repo: `next` 10.4–12.2 s → 1.5–2.1 s, `status` 7.3–9.2 s → 1.7 s; a round trip 1.2 s → 0.4 s.
- **`uak wait ID --for approve|integrated|message`:** one call that returns when it happens (a `ls-remote` every 15 s, claims read only when they move), instead of polling `status`/`inbox` (225 and 172 calls at MLB).
- **Messages in ~20 s:** the hook checks the claims tip every 20 s and reads the inbox only when it moved (was a full read every 2 min). New identities start with the last 6 h of messages, not the whole history.
- **`uak map`: a code graph, graphify-style.** EXTRACTED layer (Bash + awk, no LLM, no dependencies): symbols with file:line, resolved imports for Python, JS/TS (`@/`), Go, Rust, shell, Ruby and C includes, and call edges with the enclosing caller (5/5, 26/28, 41/44 of `git grep`'s calls on a real repo); `MAP.md` with areas, hubs, most-called functions, entry points, area dependencies and files per task; `find`, `callers`, `calls`, `deps`, `users --depth`, `path`, `related`, `impact` (with the functions used). INFERRED layer, optional: `uak map notes` asks the fast model for a purpose and concepts of the key files (cached by content hash) and links files that share concepts. On a 123-file repo: source ~187k tokens, `MAP.md` ~1.3k; a "where and who uses" question ~280 tokens vs ~3.1k reading files. Built in background at session start; the scout subagent asks it first.
- **`msg impact:ID`** routes a contract to every task whose files import ID's files (the code graph); `msg A,B` sends one line to a list.
- **Team memory anchored to paths:** `uak learn "what bites · where · what to do"` (task paths by default), `uak recall ID|PATH`, `learn --forget N`, `review … --learn`; `uak next` shows the newest lessons for the task to whoever works there.
- **MCP server (`.uak/bin/uak-mcp`): the harness as native tools in every MCP client.** 14 tools with "when to use" descriptions, strict schemas and annotations (`uak_next`, `uak_claim`, `uak_ship`, `uak_wait` with progress and cancellation, `uak_review`, `uak_merge`, `uak_message`, `uak_inbox`, `uak_map`, `uak_memory`, `uak_checkpoint`, `uak_tokens`, `uak_status`, `uak_cli`), resources (code map, status, lessons, the quick card, AGENTS.md, task and lesson templates) and the `/uak-*` workflows as prompts, so Codex, Cursor and Gemini get them too. Dual-era: MCP 2026-07-28 (stateless `_meta`, `server/discover`, `resultType`, `ttlMs`/`cacheScope`, `-32022`) and 2025-11-25/06-18/03-26 (`initialize` with the quick card as `instructions`). Every tool runs the same uak CLI and gates. Python 3.8+ standard library; configured in `.mcp.json`, `.codex/config.toml`, `.cursor/mcp.json` and `.gemini/settings.json`. Tested over stdio (both eras, errors, resources, prompts, progress, cancel) and with real headless Claude Code sessions; a run with the CLI blocked found that clients show `structuredContent` instead of text, so tools return text only. Optional: MCP and the Bash CLI work side by side on the same state, and `install.sh --no-mcp` leaves the server config out. UTF-8 stdio on every OS (Windows code pages broke `→`). The launchers try `python3`, `python`, `py` and keep the first that runs (on Windows `python3` is often the Store alias that exits 9009); the Cursor rule names the tools and sends message text and long waits through them.
- **Adoption layer: the agent uses the harness at the right moment.** A quick card at session start (when X → run Y, Superpowers-style), event-driven reminders after tool calls with per-session caps (OpenDev-style: exploration spiral → code map, polling → `uak wait`, a push touching imported files → `msg impact:`, done → wait, repeated kit errors → `bb add`, long stretches → checkpoint; templates in `.uak/reminders.md`), the next step printed by `done`, `claim`, `= unchanged` and rejects, and `uak done` checking the code graph for live tasks that import the diff. Command descriptions now say "Use when…". Measured with a new adoption eval (`scripts/adoption_eval.py`, `docs/evals/`): with AGENTS.md in context a Sonnet agent sent the contract to the importing task in 0/3 runs before, 3/3 after (all before `done`: the card did it; the `done` check is the backstop).
- The installer adds `__pycache__/`, `*.pyc`, `node_modules/` and other build output to `.gitignore` (an agent's `git add -A` committed `__pycache__` in the eval); the merge gate names generated files as such.
- **`karpathy-guidelines` skill** in both modes (pinned, MIT; "ask" maps to `uak decision`/`uak msg`).
- **`uak tokens`: the real bill.** Reads the transcripts Claude Code (`~/.claude/projects`, subagents included, deduped by message id) and Codex (`~/.codex/sessions`) already write, no API key: input, cache write, cache read and output, share and cache hit, `--by task|harness|model|scope|agent`. Tasks come from the worktree folder, so removed worktrees still count. `--publish` writes this machine to `claims:tokens/` (the Stop hook does it every 30 min); `--team` adds every machine and names the owner; `stats` and the human `digest` show the total and the top task.
- **Loops with guards.** `uak loop` stops when an iteration changes nothing and when the agent edits or deletes an existing test (`--protect`); the prompt carries the diff stat so far; `LOOP_SUMMARY` at the end; one log per run. `--parallel N --each "CMD {}"`: one sub-loop per failing test file (pytest, jest/vitest, go) in temporary worktrees of the current state, passing fixes applied back, Verify once.
- **`uak handover ID --to NAME`:** pass a live claim without AVAILABLE (owner, human, or anyone after the lease); the local `.uak-env` follows.
- **`uak graph --assign`:** one idle agent per ready task, by who integrated work in the same folders, then speed.
- **Actions.** Opt-in `.github/workflows/uak-tick.yml.example` (deadlines advance at night); a weekly black box harvest in this repo that opens an issue (`HARVEST_TOKEN` secret).
- **Stack presets:** `--stack nextjs|django|go|expo|python-data|ai-agent`, each with a setup page, a skill with parallel-work rules and its product smoke (fastapi-react kept; its test path fixed).
- **Gemini CLI hooks:** `BeforeTool` guard and output cap, `SessionStart` context (Gemini CLI was replaced by Antigravity CLI in June 2026; the hooks follow its published docs).
- **Demo animation:** `docs/media/demo.svg` (15 KB, CSS-animated, rendered from a real `uak demo` by `scripts/render_demo.py`) replaces the 270 KB GIF.
- 11 new tests (`test_v5.py`; 114 in total).

## v4.3.0 · 2026-10-15 · The MLB autopsy: nobody waits, Windows gets the cap (shipped inside v5.0.0)
From 60 h of a 10-day hackathon on **4 Windows laptops** (Git Bash), 4 humans, 13 identities on Claude Code, Codex and Cursor: 32 of 36 tasks integrated. Every number is in `docs/blackbox/mlb-2026-10.md`; every rule cites it in WHY.md.
- **Approved tasks merge without their owner.** After `Merge-Adopt-Seconds` (20 min) any eligible agent runs `uak merge ID`; `next` points idle agents at it and the task records `Merged-By`. In REVIEW the lease no longer matters. 9 tasks had waited 7–13 h after approval.
- **Approvals survive clean merges of main.** When every commit after the approved SHA is a clean 2-parent merge of the base (the merge tree is recomputed: `merge-tree`, or a stricter 3-way index merge on git < 2.38), `merge` and `integrate` accept it. A hand edit still needs a review, and `review` says what moved since the reviewer's SHA.
- **Merge gate.** The candidate runs with the worktree's or main checkout's `.venv` first on PATH and `UAK_MAIN_CHECKOUT` exported; a red gate keeps its log and quotes the error line (6 of 17 human-queue entries were "Smoke red"). Scope reasons say new vs edited, the task that owns the path and the fix; new empty files (`__init__.py`) pass; the smoke provenance file is a shared resource. `MERGE_BUSY` replaces the "Queue busy" human entry.
- **Identities and reviews.** `uak retire NAME`: rotation, messages and approvals skip it (a claim brings it back). Rotation asks whoever rejected the previous SHA, then another human's agent, then idle agents. `done --to NAME --note TEXT` makes a re-review one message; integrated notices are one line. `review ID --stop` gives a review lock back.
- **`uak followup ID --title TEXT`:** a new task on an integrated task's Paths (3 follow-up PRs had gone around the kit).
- **Output cap everywhere.** Codex moved from PostToolUse `block` (it cut documentation reads and broke tool batches) to PreToolUse `allow` + `updatedInput` with the same allowlist as Cursor. On Windows, Cursor gets the cap too: the command goes base64 to `cap --b64`, which PowerShell and bash read alike. A huge diff becomes a per-file index with line ranges.
- **Windows.** `= unchanged` works without `ps -o` (the hook's session id is the key). `status`/`next` answer even if the deadline reconcile fails; `git init` retries and shows its error. `doctor` warns about OneDrive/Dropbox/iCloud folders and checks `.githooks` executable bits.
- **Less noise.** REVIEW leases write no recovery receipts (19 of 22 were on REVIEW tasks). Per-command `--help`, case-insensitive IDs and refusals that show the value, a per-command identity prefix in "No identity", OK for `heartbeat`/`integrate` of finished tasks, one `q` log per run, LONG EVENT advice from `uak clock`.
- 8 new tests (`test_v43.py`; 103 in total).

## v4.2.1 · 2026-10-10 · The rest of the Reap autopsy
- **`uak review ID --start`.** A 20-min "I am reviewing this SHA" lock: a second reviewer gets CONFLICT, `next` stops suggesting it, an approved SHA prints SKIP. The `uak-reviewer` subagent and `/uak-review` start with it. At Reap 2–3 agents reviewed the same SHA at once.
- **`MERGE_WAIT`.** `uak merge` with no approval on the current SHA waits instead of filling the human queue.
- **Contracts supersede.** A newer contract from the same sender and task hides the older one in the inbox; the task thread marks it "superseded by #N".
- **Freeze warning.** 30 min before `Freeze-Epoch`, `next` and `digest` say "finish and `uak done`, or release".
- **Short events.** `/uak-plan`: at most 2 tasks per agent, 45 min each, done by the "first claim by" time. `/uak-design-lock`: one direction, not three.
- **Rules.** Plain words in messages (no glued words); agents use their own names, humans `UAK_HUMAN`, and no "coordinator" agent speaks for a human; `review --start` before reviewing.
- **Fewer claims writes.** The hook heartbeat runs every lease/3 (15 min in sprint) and renews REVIEW tasks at most every 30 min.
- `integrate` says the task's real state when it is not in REVIEW.
- 1 new test (`test_v42.py`: 11; 95 in total).

## v4.2.0 · 2026-10-10 · The Reap autopsy: less process, fewer tokens
From the first full team event on the kit (Reap x AI Builders buildathon: 4 h, 5 humans, 11 agents on Codex, Cursor and Claude Code). Every number is in `docs/blackbox/reap-2026-10.md`; every rule cites it in WHY.md.
- **Scope gate on the current base.** `uak merge` checks what the merge changes in the current base, not Task-Base..tip. 6 of 13 integrated tasks had gone to the human queue for files their branch inherited from main.
- **`uak clock START DEADLINE ZONE --write`.** The sprint schedule scales with the event (freeze = 15% of it, 30 min to 6 h) and prints "first claim by". A fixed −6 h froze a 4 h event one hour after its first claim.
- **`uak allow ID… --reason` / `--in-flight`.** An audited human freeze exception for claims and merges (no more PRs to flip `Freeze-Allowed`).
- **Context hygiene, the real answer to "tool calling hogs the context":**
  - Shell outputs over `Output-Cap-Chars` (12000) reach the model as head + tail + the saved log: Claude Code `PostToolUse` `updatedToolOutput`; Codex `PostToolUse` `decision: "block"` (replaces the result; the command already ran); Cursor `preToolUse` `updated_input`, which wraps tests, builds, linters and read-only git/search commands in `{ cmd; } > log` + `.uak/bin/cap` (exit code, `cd` and `export` kept). Cursor also gets a `sessionStart` hook.
  - The same `status`/`next`/`digest` twice in one session prints `= unchanged`; unread messages are shown once per session (`--full` reprints).
  - `LOOP:` after the same error 3 times in 10 min.
  - One message line for many targets; `review --note` (one message per verdict); a second approval of an approved SHA records nothing; ack-only replies are refused.
- **Less contention.** Jittered exponential backoff (max 30 attempts), `--depth 2` claims fetch and depth-1 config fetch, network retried 3 times.
- **Identity.** One identity holds one CLAIMED/BLOCKED task (`UAK_MULTI_CLAIM=1`); a warning when two sessions share a worktree.
- **Reviews move faster.** Idle agents are picked first; `next` suggests only SHAs without an approval; every human-queue entry prints the fast path (merge on GitHub, then `uak integrate`).
- **Black box.** `next` probes are not errors (153 of 290 lines were); identical lines publish once with `(xN)`; the harness is remembered per worktree; leftovers flush at session start.
- `uak next` works without an identity (Reap's top error: 24 "No identity").
- Fixes: `msg Ana-1` (uppercase agent names), `status ID`, `register-reviewer A B C`, a guard that ignores safety rules inside quoted prompts and now catches `cat ".env"`, Git Bash `ref:path` arguments (`MSYS2_ARG_CONV_EXCL`), a board that no longer shows everything AVAILABLE when the fetch fails, a one-time `gh` preflight, portable JSON escaping in hooks (mawk).
- 10 new tests (`test_v42.py`, 94 in total).

## v4.1.1 · 2026-10-09 · Hackathon-ready safety
- **Hard limits above pacing.** These are fixed numbers that `uak pace` can lower but never raise (sprint / marathon):
  - `Subagent-Hard-Cap` 6/4 and `Strong-Hard-Cap` 3/4;
  - `Subagents-Per-Session` 40/30 and `Subagents-Per-Machine` 8/6, counting every worktree;
  - `Subagent-Burst-Per-Minute` 6;
  - `Max-Worktree-Agents` 6/4, for `uak up`.

  A wrong usage reading can no longer empty a plan in minutes.
- **Surge needs fresh data.** Status line or Codex readings must be under 30 min old, manual ones under 12 h. Impossible readings are ignored.
- **The mode is the human's choice.** `install.sh` has no default and explains both modes. `/uak-setup` and the plugin skill never infer or switch it. A task diff that touches `.uak/PROJECT.md` goes to the human queue.
- `docs/HACKATHON.md`: the one-page plan for a team on its way to an event.
- Fixes:
  - A relative remote URL now resolves from the main checkout, not the worktree.
  - `/uak-ship` uses `wt pr` and `uak integrate`.
- Codex, Cursor and Gemini files were checked against public repos that use the same formats (Khan/perseus, dlt-hub/dlt and telepresence for `.codex/hooks.json`; LibreQoS for `.codex/agents`; TablePro for `[agents]`; photon-hq for `.cursor/hooks.json`; rancher and streamlit-echarts for `.gemini/agents`).
- 2 new tests (84 in total).

## v4.1.0 · 2026-10-09 · Black box, pacing, every harness
From the first post-mortem of a real kit user (UpiixSol: 3 days, 2 humans, 6 agent identities, 38 tasks). Every fix cites its incident in WHY.md.
- **Black box (`uak bb`), on by default.** Every `uak` error and guard block is recorded as one anonymous line, and agents add notes with `uak bb add bug|friction|need|idea|praise`. Lines carry no identities, paths, SHAs, code or secrets. They are published to `claims:blackbox/` (one file per machine and day, so pushes never conflict). `uak bb export` writes `.uak/BLACKBOX.md` and `scripts/blackbox_harvest.py` ranks issues across public repos. Off with `Blackbox: off` or `install.sh --no-blackbox`.
- **Plan pacing (`uak pace`).** Budget left vs time left per usage window gives surge, normal, conserve or critical. The levels scale the guard's caps: surge doubles parallel subagents and adds 2 strong ones; critical allows 1 subagent and no strong model. Sources: the Claude Code status line `rate_limits` (new `.uak/bin/statusline`), Codex session logs, and `uak pace set` for Cursor and any dashboard. The hook tells the agent once whenever the level changes.
- **Every harness gets the tiers.** Fast, balanced and strong tiers:
  - Claude: Haiku/Sonnet/Opus 5.5.
  - Codex: GPT-6 Luna, GPT-6.1 Sol, GPT-6 Astra (or GPT-5.6 Luna/Terra/Sol).
  - Cursor: Composer 2.5, your model, Opus 5.5.
  - Gemini: Flash, your model, Pro.
  - New: `.codex/config.toml`, `.codex/agents/*.toml`, `.codex/hooks.json`, `.cursor/agents/*.md`, `.cursor/hooks.json`, `.gemini/agents/*.md` and `.gemini/settings.json`. They are generated from `.claude/agents` by `scripts/gen_harness.py`, which CI checks.
  - `guard` reads every harness's payloads (Claude/Codex `PreToolUse`, Gemini `BeforeTool`, Cursor `beforeShellExecution`, Codex/Cursor subagent start).
- **COSTS.md:** API price tables, the Claude Pro/Max, Codex Plus/Pro and Cursor Pro/Ultra limits, and starting caps per plan.
- **UpiixSol fixes:**
  - `uak integrate ID`: any agent records a PR a human merged while its owner was away.
  - The claim base is now the fork point, so a late claim is no longer "nothing implemented".
  - Agents integrated in the last 24 h can still review.
  - `Additive-Paths` lets new test files pass the scope gate.
  - `.uak-env` beats an exported `UAK_AGENT`.
  - Unquoted `--evidence` words are accepted.
  - A clearer missing-identity error, with a `git config uak.agent` fallback.
  - `STATE.md` lists show counts instead of a silent cut.
  - The guard blocks `pkill -f`/`killall`; `wt stop` kills exact PIDs.
  - `wt new` skips busy ports and `wt rm` stops the worktree's servers.
  - `wt pr` prints the PR URL when the token can't create PRs.
  - LOOPS.md: Verify builds fresh.
- 6 new tests (`test_v41.py`); 82 in total.


## v4.0.1 · 2026-10-07
- New banner and demo GIF. Both are rendered from HTML/CSS in headless Chromium (Inter + JetBrains Mono) instead of PIL drawing. The GIF is 6 curated scenes with typed commands, every line taken from a real `uak demo` run, plus a closing card whose commands work as written. `scripts/make_media.py` regenerates both (`uv run --with playwright --with pillow python scripts/make_media.py`).

## v4.0.0 · 2026-10-07 · Orchestration
- **Model routing:** Haiku 5.5 scouts, a Sonnet 5.5 lead and an Opus 5.5 advisor/architect, consulted only at plan lock, the same failure twice and done. Installed settings: `model: sonnet`, `advisorModel: opus`, `effortLevel` per mode, `CLAUDE_CODE_SUBAGENT_MODEL=haiku`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`, and concurrency per mode.
- **`guard agent`** (PreToolUse `Agent|Task` + SubagentStop) caps parallel subagents and Opus subagents per session, also under ultracode (which bypasses Claude Code's own cap). It logs every spawn by tier; `uak stats` reports it.
- **New subagents:** `uak-scout` (Haiku, read-only, ≤15-line structured answers) and `uak-architect` (Opus, checkpoint packets). Every subagent now pins `model`, `effort` and `maxTurns`, and cannot spawn subagents.
- **New commands:** `/uak-advise plan|stuck|done` (a ≤40-line packet when the advisor tool is unavailable or the session is long) and `/uak-secure` (the pre-launch audit). `/uak-start`, `/uak-loop` and `/uak-ship` call the checkpoints.
- **Launch checklist** in SECURITY.md: 22 verifiable items plus human-only ones. `security-reviewer` checks the relevant items.
- **Media:** `docs/media/demo.gif`, rendered from a real `uak demo` run, and `docs/media/banner.png` (`scripts/make_media.py` regenerates both).
- Viral orchestration claims were checked against the Claude Code docs; the unsupported ones are listed in ORCHESTRATION.md.

## v3.1.0 · 2026-10-06
- **`uak demo`:** a real 3-agent session in a temp repo in about 15 s, with no setup, network or keys. It covers claims, a rejected overlap, a bounded loop, an independent review, a gated merge and a dependency unlocking.
- **`uak board`:** a team kanban read from the claims branch (state, owner, lease left, PR, wave). `--watch` refreshes it live and `--md` prints a GitHub table.
- **`uak up N`:** claims the N best eligible tasks into worktrees, one command for the whole team. `--tmux` launches one agent per window.
- **`uak stats`:** retro numbers (messages by kind and agent, review load, lease recoveries, human-queue reasons). Run on the real Hack-Nation data, it corrected two numbers in the docs: 717 messages (not 720), and 2 agents giving 51 of 70 review verdicts.
- `examples/ai-hackathon`: a 10-task AI backlog with 7 tasks in wave 1, plus its Mermaid graph.
- README: "Try it in 30 seconds" and a comparison table.
- Repo: CODE_OF_CONDUCT and issue template config.

## v3.0.0 · 2026-10-06 · UPIIXIA Agentic Kit
A rewrite after the Hack-Nation 2026 post-mortem of the `hack` v2.1 protocol (5 agents, 4 humans, 76 PRs).

### New
- **Two modes**, chosen with one line in `.uak/PROJECT.md`. Each has its own settings, commands, subagents and skills:
  - `sprint`, for hackathons and AI prototypes;
  - `marathon`, for real products.
- **Loop engineering:** `uak loop` runs a bounded, unattended verify → fix loop (budget, stuck detection, BLOCKED on exhaustion). Also new: `/uak-loop` and `LOOPS.md`.
- **Graph engineering:** `uak graph` shows waves, the critical path, cycles, missing deps and a Mermaid diagram with live state. `lint` fails on cycles. Also `GRAPH.md`.
- **`uak plan`** publishes backlog to the claims branch without a PR.
- **`uak doctor`**, a minute-0 preflight.
- **Guards:** a PreToolUse `guard` checks every segment of chained commands; a UserPromptSubmit secret guard blocks pasted secrets.
- **Claude Code plugin + marketplace:** `/plugin install uak@upiixia-agentic-kit`.
- **Skills:** curated, pinned and installed per mode (superpowers TDD, debugging and verification; Anthropic webapp-testing and mcp-builder; Vercel React; taste-skill).
- **Subagents:** `design-critic` and `security-reviewer`. **Commands:** `/uak-design-lock`, `/uak-spec`, `/uak-retro`.

### Fixed
- The secret scanner detected nothing on Debian/Ubuntu (mawk ignores awk `{n}`). It now uses `grep -E`.
- The dependency parser treated IDs inside parentheses as hard dependencies.
- `wt` crashed with `tr: invalid range` when deriving the human's name.

### Changed
- Everything is in English and token-lean. `AGENTS.md` went from 114 lines to 60 (lint cap 100).
- Self-contained layout: everything lives in `.uak/`; the installer never overwrites user files.
- Coordination:
  - mode-aware leases, with a longer wait in REVIEW;
  - reviewer rotation by load;
  - one `integrated` notice per owner;
  - only actionable messages injected;
  - generic task IDs;
  - a `UAK_PORT` per worktree.
- 70+ integration tests against real Git, in CI on Linux (mawk) and macOS.
