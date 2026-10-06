# Roadmap

## v3.1
- [ ] `uak stats`: retro numbers (messages by kind, lease recoveries, review load, PR timeline) in one command.
- [ ] A 60-second demo GIF: 3 agents claiming, looping, reviewing and merging.
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
