Real tool runs (contract amendment 7), 2026-11-12, macOS, project installed by install.sh --harness claude,codex:
- Claude Code 2.1.323, `claude -p "Run /uak-start for APP-001. Work only in this worktree." --model haiku --max-turns 3`:
  init lists slash command uak-start; the model opened .claude/commands/uak-start.md and ran `uak next` (its first step).
  Mid-sentence /uak-start is not auto-expanded; the model follows the command file instead. Same flow.
- Codex 0.167.1, `UAK_AGENT=ana-r codex exec -s read-only '<REVIEW_PROMPT>'`: "$uak-review" resolved to
  .agents/skills/uak-review/SKILL.md; it ran uak next as ana-r (blocked only by the probe's read-only sandbox).
- NOT verified: Windows Git Bash (needs Dylan's Windows machine).
