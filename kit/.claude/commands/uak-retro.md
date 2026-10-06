---
model: opus
description: Data-driven retro from the claims branch; proposes concrete kit and project changes
---
1. Data: `bash .uak/bin/uak stats` (messages by kind and agent, review load, lease recoveries, queue reasons), `bash .uak/bin/uak board`, `bash .uak/bin/uak graph`, and `gh pr list --state all --limit 200 --json number,state,additions,deletions,createdAt,mergedAt`.
2. Classify each problem: coordination, quality, security, product or time. Each one cites evidence (a number, a SHA or message #N).
3. For each problem, propose the smallest change that would have prevented it (a rule, hook, CLI gate, template or checklist) and name the exact file.
4. Write `docs/retro/YYYY-MM-DD.md` with four parts: keep, broke (with data), proposed changes, and the top 3 for next time.
5. Don't edit `AGENTS.md` while agents are running. Propose changes as a PR, and consider upstreaming generic fixes to upiixia-agentic-kit.
