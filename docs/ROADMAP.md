# Roadmap

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
