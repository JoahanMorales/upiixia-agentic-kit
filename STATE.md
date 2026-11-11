# STATE

Phase: execution
Updated: 1794358488
AVAILABLE: UAK-050 UAK-052 
CLAIMED: UAK-048 UAK-049 
BLOCKED: -
REVIEW: UAK-045 UAK-046 UAK-047 UAK-051 UAK-053 
INTEGRATED: (37; last 12) ... UAK-033 UAK-034 UAK-035 UAK-036 UAK-037 UAK-038 UAK-039 UAK-040 UAK-041 UAK-042 UAK-043 UAK-044 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-045 | REVIEW | joahanmorales-4 | until 1794444888
UAK-046 | REVIEW | joahanmorales-1 | until 1794444367
UAK-047 | REVIEW | joahanmorales-5 | until 1794444624
UAK-048 | CLAIMED | kit-w33 | until 1794372854
UAK-049 | CLAIMED | joahanmorales-9 | until 1794372080
UAK-051 | REVIEW | joahanmorales-10 | until 1794444842
UAK-053 | REVIEW | joahanmorales-8 | until 1794444722

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1794357965 | UAK-046 | per-file path+cksum of CR-stripped content, extra/missing files count as stale | Why: BSD diff <macOS13 lacks --strip-trailing-cr
- 1794358222 | UAK-047 | CRLF-stripped hash also counts as shipped; extra file = edited; folder rmdir'd when empty | Why: name-only match deleted edited copies
- 1794358322 | UAK-053 | refusal text lives in backlog_read_note | Why: reviewer could not tell what was read
- 1794358440 | UAK-051 | function counts only if it has _ or inner capital; warn only if no defining file is inside Paths; takes optional backlog file arg for plan | Why: avoid pro
- 1794358486 | UAK-045 | two existing fixtures got a second file | Why: spec says one file unapproved needs human

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
