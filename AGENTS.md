# AGENTS.md · working ON the UPIIXIA Agentic Kit repo

You are in the kit's source repo. Users install `kit/` into their projects with `install.sh`; the plugin entry point is `skills/setup/`.
If a user asks you to set up multi-agent coordination in ANOTHER repo, use `skills/setup/SKILL.md`.

## Layout
- `kit/` is the payload: `AGENTS.md`, `CLAUDE.md`, `.uak/` (bin, docs, modes, templates, skills, stacks, tests), `.claude/`, `.cursor/`, `.github/`, `.githooks/`.
- `install.sh`, `.claude-plugin/`, `skills/setup/` and `llms.txt` are distribution. `docs/` holds the retro, inspirations and roadmap.

## Rules
1. Every engine change (`kit/.uak/bin/`) ships with a test in `kit/.uak/tests/` that fails without it. Run `cd kit && bash .uak/bin/smoke --package-only` (about 4 min, real Git, no network). All green before a PR.
2. Portability:
   - Bash 3.2 (macOS);
   - POSIX tools, no jq;
   - **no `{n}` regex intervals inside awk** (mawk ignores them), so use `grep -E`;
   - no `gensub` and no arrays of arrays.
3. Token budget: `kit/AGENTS.md` stays at 100 lines or fewer (lint enforces it). Prefer tables and imperative one-liners. Detail goes in `.uak/docs/`, linked from §7.
4. Every new rule cites its incident or evidence in `kit/.uak/docs/WHY.md`. A rule without evidence is an opinion.
5. Third-party skills: pin the commit, review the content, include the LICENSE, and record them in `kit/.uak/skills/SOURCES.md`. Never vendor skills that fetch instructions at runtime.
6. English everywhere: code, messages, docs.
