# Contributing

Thanks for helping agent teams ship faster. The kit lives in `kit/`; `install.sh` copies it into projects.

## Quick loop
```bash
git clone https://github.com/JoahanMorales/upiixia-agentic-kit && cd upiixia-agentic-kit/kit
bash .uak/bin/smoke --package-only      # ~4 min: 70+ tests with real Git and bare remotes, no network
python3 .uak/tests/test_v3.py           # fastest suite: plan, deps, leases, guard, graph, loop
```

## Rules for a mergeable PR
1. **Evidence.** A new rule cites the incident or data behind it in `kit/.uak/docs/WHY.md`.
2. **Tests.** An engine change (`kit/.uak/bin/`) adds a test in `kit/.uak/tests/` that fails without it.
3. **Portability.**
   - Bash 3.2 (macOS) and POSIX tools; no jq.
   - **No awk `{n}` intervals** (mawk ignores them); use `grep -E`.
   - No `gensub` and no arrays of arrays.
4. **Tokens.** `kit/AGENTS.md` stays at 100 lines or fewer. Prefer one imperative line per rule. Detail goes in `.uak/docs/`.
5. **Skills.** Pin the commit, review the content, include the LICENSE and record it in `kit/.uak/skills/SOURCES.md`. Skills that fetch instructions at runtime are rejected.
6. **English** in code, messages and docs. Conventional commits (`feat:`, `fix:`, `docs:`…).

## Great first contributions
- A stack preset in `kit/.uak/stacks/<name>/` (STACK.md + skills + smoke command).
- A retro from your hackathon in `docs/retro/`, with numbers. It is the best way to improve the rules.
- New `uak graph` checks (for example, two wave-1 tasks sharing Paths) or `uak loop` features.

Security issues: see [SECURITY.md](SECURITY.md). Please don't open a public issue.
