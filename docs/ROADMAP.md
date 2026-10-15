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

## Ideas
- Linear and Jira ID prefixes with two-way AVAILABLE/INTEGRATED sync.
- Localized agent-facing texts (`UAK_LANG`).
- `uak loop --parallel` for test runners beyond pytest, jest/vitest and go.

## Earlier releases
- v4.3 (MLB autopsy) and v4.2 (Reap autopsy): see CHANGELOG.md and `docs/blackbox/`.
- v3.1: `uak stats`, `uak board`, `uak up`, `uak demo`.
