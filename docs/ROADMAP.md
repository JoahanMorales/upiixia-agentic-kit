# Roadmap

## Now: v6.6 → v7.0 (from the audit of Nov 2026, `docs/audit-2026-11.md`)

**v6.6 · The defects the audit found.** One live task per identity holds for heartbeat, log and checkpoint; the MCP
`uak_cli` cannot run a passed command unseen; the guard treats substitutions inside quotes as code, sees `gh … merge`
with flags and refuses a plain push to claims; the merge lock's renewer dies with its parent; an unapproved task cannot be
recorded INTEGRATED by its owner; temp files and Python subprocesses get names and timeouts.

**v6.7 · Everything measurable.** A ledger of every command (name, outcome, milliseconds) published with the black box;
`uak metrics`: calls and error rate per command, time per step, review rejections, rework after a reject, reverts and
reopened tasks, human interventions with their reason, work outside the kit (commits on main without a task, and a
`manual` note for "I had to do this by hand"), tokens per task and per step. Each speed number next to an instability
number. `uak autopsy` writes the event report (timeline, top issues, metrics) from claims.

**v6.8 · Lighter.** An install without the kit's own tests and with skills on demand (535 files → under 200); CI in
shards instead of one job per test file (105 jobs → about a dozen per OS set); the reviewer runs Verify and the tests the
diff touches, the full suite runs once, at the merge gate; `status` and `next` read one cached fetch of claims; a
Merge-Engine policy so an approved engine change with every CI run green does not wait for a human.

**v7.0 · A kit that improves itself, behind a gate.** Scenario evals (`uak eval`): seeded mini-repos that replay each
failure class of the black boxes against the engine, reported as k of n; mutation tests of the guard and the gates (remove
a rule, a scenario must fail). While agents work: a repeated error in a session brings its lesson into context, and a
correction made twice becomes a candidate check. After an event: `uak improve` clusters the black box, proposes a
lesson, a hint or a rule as a PR, and it is adopted only if the evals pass and a human approves; it never edits the guard
or the gates, and every adoption can be reverted.

**v7.1 · Marathon in a codebase that already exists.** `install --adopt`: reads the stack, the test command and the CI
that are there, writes a short PROJECT.md and a map for a human to trim, takes over no file; tasks imported from the
issues the team already has; a pilot scope (one module's paths) before the whole repo; quality gates that use the
project's own checks. Two modes stay (sprint, marathon): adoption is a way to install marathon, not a third mode.

Waiting: the fork with the TLA+ model of claims, the revert rate in `stats`, WHY.md enforcers and verification skills
(merge when its author finishes); external PR #2 (visual setup).

## v5.0 — shipped
- [x] Speed: one round trip per call, SSH reuse, clock cache, `next` prefilter (next 10–12 s → 1.5–2 s on GitHub)
- [x] `uak wait` · messages in ~20 s · `uak map` (code graph) · `msg impact:ID` · path-anchored memory (`learn`/`recall`)
- [x] `karpathy-guidelines` skill
- [x] `uak tokens`: the real token bill per task, model, harness and lead vs subagent, from Claude Code and Codex
  transcripts; published per machine to claims; in `stats` and `digest`
- [x] `uak loop`: stops on no progress and on an edited test (the verifier); `--parallel N --each` (one loop per
  failing test file, in temporary worktrees, fixes applied back)
- [x] `uak handover ID --to NAME` · [x] `uak graph --assign` · [x] opt-in scheduled `uak tick` (GitHub Action)
- [x] Weekly black box harvest Action in this repo (needs the `HARVEST_TOKEN` secret)
- [x] Stack presets: Next.js, Django, Go, Expo, Python data/ML, AI agent (MCP server + evals)
- [x] Gemini CLI hooks: guard, session context, output cap (Gemini CLI was replaced by Antigravity CLI in June 2026)
- [x] An animated demo (`docs/media/demo.svg`, regenerated from a real run by `scripts/render_demo.py`)
- [x] Everything from the MLB autopsy (v4.3, folded into this release): approvals that survive clean merges of main,
  merge by any agent after 20 min, gate `.venv`, `retire`, `followup`, output cap on Windows and Codex

## v5.1 (open)
- [ ] A live Windows Cursor session with the base64 rewrite, and a live Codex session with `updatedInput`; record drift with `uak bb`.
- [ ] Antigravity CLI support (the successor of Gemini CLI) once its hook and config docs settle.
- [ ] Token budgets: `Token-Budget` per task in PROJECT.md, warned by `next` when `uak tokens` crosses it.
- [ ] Cursor token spend, if Cursor publishes a usage API or a local log.
- [ ] `uak map`: optional tree-sitter backend when available, and call edges (not only imports).
- [ ] Lessons ranked by how often they were recalled; expiry for stale ones.
- [ ] A harness eval set: 20–50 frozen tasks from black box failures, run per release.
- [ ] `uak board --watch` in the demo animation.

## Next: the claims transaction without the process storm (Windows)
The tasks are in `.uak/TASKS.md` (UAK-001 … UAK-008): this repo develops the kit with the kit since v5.11. What
follows is the design they implement.

Why: on Git Bash a process costs 20–50 ms, and `uak next` starts about 200 (`status` 173, `inbox` 67, `heartbeat`
70; measured on Linux by PID, v5.9.2), most of them the claims transaction: `mktemp`, `git init`, five `git config`,
`remote add`, `fetch --depth 2`, `checkout`, then one `sed` per field read (`field()`), then commit and push. v5.9.2
cut the hooks (35 → 1, 85 → 3) but left this, because it needs a design, not builtins: 4–8 s per `next` on a laptop.
- [ ] **A persistent claims repo per clone**: `<git-common-dir>/uak-claims/` instead of `git init` per call. One
  `git fetch` refreshes it; config is set once (or `git init --template`). A `mkdir` lock serializes the machine's
  processes; a corrupt or locked repo (antivirus, OneDrive) falls back to today's temporary one.
- [ ] **Reads without a checkout**: `status`, `next`, `inbox --peek` and `board` read `claims/*.md`, `tasks/*.md` and
  the messages through one `git cat-file --batch` (or `git archive | tar`) into ONE awk pass that builds the state in
  memory; no file per field, no `sed` per key.
- [ ] **Tip-keyed cache**: the hook already runs `ls-remote` of claims every 20 s (`uak-claims.tip`). A read whose tip
  is unchanged reuses the parsed state; only the clock-dependent parts (leases, the freeze, `ago`) are recomputed.
- [ ] **Mutations on a reused worktree** of that repo: `checkout -f refs/uak/claims`, write, commit, push; retries keep
  today's semantics (fresh clock per attempt, the secret check before commit, append-only lint on `HEAD^`).
- [ ] **Proof of no change**: the protocol suites run old and new side by side on the same fixtures; every command's
  stdout and the resulting claims tree must be identical (the v5.9.2 guard method). Targets: `next` ≤ 40 processes,
  `status` ≤ 30, `heartbeat` ≤ 20, `test_v592` counts them, `scripts/perf_hooks.sh` times them on Windows.
- [ ] Then `hook stop` (one `inbox --peek` per turn, 19 git calls) and `session-start` (once per session) ride on it.
- [ ] Every 5 min `tick` runs `pace --caps` in the foreground (about 40 processes): move it to the background like the poll.

## Ideas
- Linear and Jira ID prefixes with two-way AVAILABLE/INTEGRATED sync.
- Localized agent-facing texts (`UAK_LANG`).
- `uak loop --parallel` for test runners beyond pytest, jest/vitest and go.

## Earlier releases
- v4.3 (MLB autopsy) and v4.2 (Reap autopsy): see CHANGELOG.md and `docs/blackbox/`.
- v3.1: `uak stats`, `uak board`, `uak up`, `uak demo`.
