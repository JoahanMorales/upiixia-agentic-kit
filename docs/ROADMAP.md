# Roadmap

## v4.2 (from the black box)
- [ ] A live paid run of the Codex and Cursor configs (hooks + tiered subagents); record any schema drift with `uak bb`.
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
