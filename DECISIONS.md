# DECISIONS

Coordination decisions on the claims branch.
Why: a reversible option after 15 min keeps work moving.
- 1793650134 | UAK-001 | reuse test_v592's shim counter; measure the second call | Why: one counter for hooks and claims; the first call of a clone writes its session file
- 1793681696 | UAK-009 | follow-up of UAK-001 by kit-1: The process counter counts ps, measures next for an idle agent too, and names traces uniquely (kit-r1's notes on UAK-001) | Why: same Paths, no scope change
- 1793681793 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-009 Paths: kit/.uak/tests/test_claims_perf.py, scripts/perf_claims.sh, kit/.uak/bin/smoke, .github/workflows/test.yml → kit/.uak/tests/test_claims_perf.py, scripts/perf_claims.sh; | Why: scope or criteria fixed before review
- 1793688176 | plan | JoahanMorales/JoahanMorales | tasks added: UAK-010 | Why: backlog without PR (Plan-Channel: claims)
- 1793737007 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-006 | Why: scope or criteria fixed before review
- 1793739442 | plan | JoahanMorales/JoahanMorales | tasks added: UAK-011 UAK-012 | Why: backlog without PR (Plan-Channel: claims)
- 1793753501 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-003 Paths: kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/state.awk, kit/.uak/tests/test_claims_read.py → kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/core.sh, kit/.uak/bin/lib/state.awk, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_claims_read.py, kit/.uak/tests/test_claims_perf.py; Verify changed; UAK-002 UAK-006 | Why: scope or criteria fixed before review
- 1793906635 | deadline lease/UAK-002/1793874851 | REQUIRES_RECOVERY | Claim kept; read the summary and use release --expired --read-summary. No work is deleted.
- 1793906660 | UAK-013 | follow-up of UAK-012 by kit-2: The merge redirect parses on bash 3.2 (no case pattern) inside a command substitution | Why: same Paths, no scope change
- 1793906662 | UAK-014 | follow-up of UAK-003 by kit-3: status and next print no carriage return from a CRLF checkout; golden test normalizes /private | Why: same Paths, no scope change
- 1793919362 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-006 | Why: scope or criteria fixed before review
- 1793919365 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-013 Verify changed; UAK-014 | Why: scope or criteria fixed before review
- 1793920297 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-013 Paths: kit/.uak/bin/uak, kit/.uak/tests/test_v511.py → kit/.uak/bin/uak, kit/.uak/bin/doctor, kit/.uak/tests/test_v511.py; | Why: scope or criteria fixed before review
- 1793924778 | UAK-015 | follow-up of UAK-013 by kit-2: The bash 3.2 comsub checker counts $(( )) inside $( ) as one paren level: y=$(case $a in (b) echo $((1));; esac) is a false positive, y=$(echo $((1+1)); case $a in b) :;; esac) a false negative; consume both closing parens and add the two samples | Why: same Paths, no scope change
- 1793930986 | UAK-002 | Paused: about 5 processes saved per call (next 93->88) does not justify the concurrency risk before the hackathon. | Why: CI on git 2.56 (ubuntu) still lets two processes into uak-claims: the lock event log shows 2 of 6 calls working there with no acquire event, one hit an existing .git/shallow.lock. Not reproducible locally (git 2.34).
- 1793931936 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-005 | Why: scope or criteria fixed before review
- 1793932634 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-006 | Why: scope or criteria fixed before review
- 1793933304 | plan | JoahanMorales/JoahanMorales | tasks added: UAK-016 | Why: backlog without PR (Plan-Channel: claims)
