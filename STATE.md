# STATE

Phase: execution
Updated: 1794358313
AVAILABLE: UAK-048 UAK-050 UAK-052 
CLAIMED: UAK-045 UAK-049 UAK-051 
BLOCKED: -
REVIEW: UAK-046 UAK-047 UAK-053 
INTEGRATED: (37; last 12) ... UAK-033 UAK-034 UAK-035 UAK-036 UAK-037 UAK-038 UAK-039 UAK-040 UAK-041 UAK-042 UAK-043 UAK-044 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-045 | CLAIMED | joahanmorales-4 | until 1794372091
UAK-046 | REVIEW | joahanmorales-1 | until 1794444367
UAK-047 | REVIEW | joahanmorales-5 | until 1794444624
UAK-049 | CLAIMED | joahanmorales-9 | until 1794372080
UAK-051 | CLAIMED | joahanmorales-10 | until 1794372636
UAK-053 | REVIEW | joahanmorales-8 | until 1794444713

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1794356207 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-038 Paths: kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/wait.sh, kit/.uak/tests/test_reviewer_next.py → k
- 1794356618 | UAK-038 | registered reviewers only; file tests, no new process | Why: DevDay
- 1794357639 | plan | JoahanMorales/JoahanMorales | tasks added: UAK-045 UAK-046 UAK-047 UAK-048 UAK-049 UAK-050 UAK-051 UAK-052 UAK-053 | Why: backlog without PR (Plan-Channel: cl
- 1794357965 | UAK-046 | per-file path+cksum of CR-stripped content, extra/missing files count as stale | Why: BSD diff <macOS13 lacks --strip-trailing-cr
- 1794358222 | UAK-047 | CRLF-stripped hash also counts as shipped; extra file = edited; folder rmdir'd when empty | Why: name-only match deleted edited copies

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
