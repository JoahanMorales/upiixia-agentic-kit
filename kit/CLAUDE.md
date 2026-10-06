# Shared instructions

@AGENTS.md

Load `.uak/docs/` only when `AGENTS.md` §7 or your mode says so. Minimal context leaves tokens for the task.

## Claude Code only
- Hooks:
  - `SessionStart` already ran `uak next` and showed your inbox.
  - `PostToolUse` sends heartbeats and injects only actionable messages.
  - `Stop` won't let you finish with unhandled messages.
  - `PreToolUse` (`guard`) blocks destructive or publishing commands, even when chained.
  - `UserPromptSubmit` blocks pasted secrets.
- Commands:
  - All modes: `/uak-setup`, `/uak-plan`, `/uak-start`, `/uak-loop`, `/uak-ship`, `/uak-review`, `/uak-handoff`, `/uak-retro`.
  - sprint: `/uak-design-lock`, `/uak-demo`.
  - marathon: `/uak-spec`.
- Subagents (isolated context, summary only):
  - `uak-runner` (Haiku): tests, smoke, app.
  - `uak-reviewer`: reviews.
  - `design-critic`: sprint UI screenshots.
  - `security-reviewer`: marathon sensitive PRs.
  - `Explore`: wide searches.
- Run tests with `bash .uak/bin/q ...`, using pytest `-q --tb=short -x`. Edit with Edit; never rewrite whole files.
- Avoid editing `AGENTS.md` or `CLAUDE.md` while agents are running: it invalidates every agent's prompt cache. Urgent amendments go through `uak decision`.

## When compacting
Keep only: ID, branch, worktree, exact next step, pending criteria, failures with exact errors, verify commands, decisions and unanswered inbox. Drop command output, diffs and explorations.
