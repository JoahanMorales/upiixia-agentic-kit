# worklog/WL-1794342018-joahanmorales-3-UAK-040-hack.hDYTSR.md · UAK-040

## Live summary
- Done: generator, installer, tests, AGENTS line
- Decision: phase skills in kit/.agents/skills real dir; .agents/skills no longer a symlink; Gemini toml + skill; no .cursor/commands
- Why: Cursor reads .agents/skills so commands would duplicate
- Failing: none
- Commands: python3 kit/.uak/tests/test_harness_commands.py
- Next: done

## History
- 1794342018 | CLAIMED | joahanmorales-3 | claim; next: the command → skill writer in scripts/gen_harness.py
- 1794342308 | CLAIMED | joahanmorales-3 | checkpoint; next: done
