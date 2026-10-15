# Roadmap

## v4.2 (Reap autopsy) — shipped
- [x] Scope gate on the current base · [x] `uak clock` · [x] `uak allow` · [x] quiet probes and `(xN)` · [x] backoff + shallow fetch
- [x] One identity = one task · [x] one-line multi-target messages, `review --note`, no acks · [x] `= unchanged`, `LOOP:`, output cap

## v4.3 (MLB autopsy) — shipped
- [x] Approval survives clean merges of main · [x] any agent merges an approved task after 20 min · [x] gate `.venv` + kept logs
- [x] Scope reasons with owner and fix · [x] `retire`, rotation (rejecter, other human) · [x] `done --to/--note` · [x] `followup`
- [x] Output cap on Windows Cursor and Codex (base64 pre-rewrite), diff index · [x] dedupe without `ps -o` · [x] status survives a failed tick
- [x] Windows: 4 Git Bash laptops ran Claude Code, Codex and Cursor for 60 h (the v4.2 MSYS fixes held)

## v4.4 (open)
- [ ] A live Windows Cursor session with the base64 rewrite, and a live Codex session with `updatedInput`; record drift with `uak bb`.
- [ ] Gemini CLI hooks (`BeforeTool` → `guard bash`) once hooks leave experimental.
- [ ] A weekly GitHub Action in this repo that runs `scripts/blackbox_harvest.py` and opens an issue with the top 10.
- [ ] `uak pace` from the Cursor usage API, if one is published.
- [ ] `uak handover ID --to AGENT`: explicit transfer without going through AVAILABLE.


## v3.1
- [x] `uak stats` (v3.1) · [x] `uak board` (v3.1) · [x] `uak up` (v3.1) · [x] `uak demo` (v3.1)
- [ ] A 60-second GIF of `uak demo` and `uak board --watch` for the README.
- [ ] `uak handover ID --to AGENT`: explicit transfer without going through AVAILABLE.
- [ ] A GitHub Action that runs `uak tick` every 5 min, so leases and deadlines advance with nobody online.

## v3.2
- [ ] Stack presets: Next.js, Django, Go, Expo, and an AI-agent preset (MCP server + evals).
- [ ] `uak loop --parallel`: one loop per failing test file, in separate worktrees.
- [ ] `uak graph --assign`: suggest an agent per wave-1 task by past throughput.

## Ideas
- Token budgets from each tool's usage API instead of event counts.
- Linear and Jira ID prefixes with two-way AVAILABLE/INTEGRATED sync.
- Localized agent-facing texts (`UAK_LANG`).
