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
  - The status line shows task, 5 h/7 d plan usage and `uak pace`; when the pace level changes, a hook tells you once.
- Commands:
  - All modes: `/uak-setup`, `/uak-plan`, `/uak-start`, `/uak-loop`, `/uak-advise`, `/uak-ship`, `/uak-review`, `/uak-handoff`, `/uak-secure`, `/uak-retro`.
  - sprint: `/uak-design-lock`, `/uak-demo`.
  - marathon: `/uak-spec`.
- Subagents (isolated context, summary only):
  - `uak-scout` (Haiku): read-only lookups.
  - `uak-runner` (Haiku): tests, smoke, app.
  - `uak-reviewer`: reviews.
  - `design-critic`: sprint UI screenshots.
  - `security-reviewer` (Opus): marathon sensitive PRs.
  - `uak-architect` (Opus): checkpoints only.
  - `Explore`: only when uak-scout is not enough (it runs on the lead model, so it is pricier).
- Orchestration (`.uak/docs/ORCHESTRATION.md`):
  - You are the Sonnet lead. Send `uak-scout` (Haiku) for any lookup needing 3 or more searches, up to 3 in parallel on disjoint questions. Do one-search lookups yourself.
  - Consult the Opus advisor only at the 3 checkpoints: plan lock (more than 2 files or a contract), the same failure twice, done on risky diffs. If the advisor tool is missing or the session is long, use `/uak-advise <plan|stuck|done>` instead.
  - Never fan out Opus subagents. The `guard agent` hook caps parallel subagents and the Opus budget per session, scaled by `uak pace` (surge 2×, conserve ½, critical 1 and no Opus).
- Run tests with `bash .uak/bin/q ...`, using pytest `-q --tb=short -x`. Edit with Edit; never rewrite whole files.
- Avoid editing `AGENTS.md` or `CLAUDE.md` while agents are running: it invalidates every agent's prompt cache. Urgent amendments go through `uak decision`.

## When compacting
Keep only: ID, branch, worktree, exact next step, pending criteria, failures with exact errors, verify commands, decisions and unanswered inbox. Drop command output, diffs and explorations.
