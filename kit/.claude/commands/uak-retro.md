---
model: opus
description: Data-driven retro from the claims branch; proposes concrete kit and project changes
---
1. Data: `bash .uak/bin/uak stats` (messages by kind and agent, review load, lease recoveries, queue reasons), `bash .uak/bin/uak board`, `bash .uak/bin/uak graph`, and `gh pr list --state all --limit 200 --json number,state,additions,deletions,createdAt,mergedAt`.
   Also `bash .uak/bin/uak bb show 100` (the black box: kit errors with counts and agents' notes), and `bash .uak/bin/uak pace`.
2. Classify each problem: coordination, quality, security, product or time. Each one cites evidence (a number, a SHA or message #N).
3. For each problem, propose the smallest change that would have prevented it (a rule, hook, CLI gate, template or checklist) and name the exact file.
4. Write `docs/retro/YYYY-MM-DD.md` with four parts: keep, broke (with data), proposed changes, and the top 3 for next time.
5. Run `bash .uak/bin/uak bb export` and commit `.uak/BLACKBOX.md` in the retro PR. Public repos let the kit maintainers fix the kit from it.
6. Don't edit `AGENTS.md` while agents are running. Propose changes as a PR, and consider upstreaming generic fixes to upiixia-agentic-kit.
