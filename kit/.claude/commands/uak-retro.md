---
model: opus
description: Data-driven retro from the claims branch; proposes concrete kit and project changes
---
1. Data (never cat whole files):
   - `git log --oneline origin/claims | wc -l`
   - messages by kind and agent: `git show origin/claims:inbox/log.md | awk -F' [|] ' '{print $5}' | sort | uniq -c`
   - lease recoveries: `git show origin/claims:DECISIONS.md | grep -c REQUIRES_RECOVERY`
   - human-queue reasons: `queue/*.md` on claims
   - PRs: `gh pr list --state all --limit 200 --json number,state,additions,deletions,createdAt,mergedAt`
   - graph: `bash .uak/bin/uak graph`
2. Classify each problem: coordination, quality, security, product or time. Each one cites evidence (a number, a SHA or message #N).
3. For each problem, propose the smallest change that would have prevented it (a rule, hook, CLI gate, template or checklist) and name the exact file.
4. Write `docs/retro/YYYY-MM-DD.md` with four parts: keep, broke (with data), proposed changes, and the top 3 for next time.
5. Don't edit `AGENTS.md` while agents are running. Propose changes as a PR, and consider upstreaming generic fixes to upiixia-agentic-kit.
