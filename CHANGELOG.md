# Changelog

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
