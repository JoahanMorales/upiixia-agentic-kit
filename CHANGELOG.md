# Changelog

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
