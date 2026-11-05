# STATE

Phase: execution
Updated: 1793906660
AVAILABLE: UAK-004 UAK-005 UAK-006 UAK-007 UAK-008 
CLAIMED: UAK-002 
BLOCKED: -
REVIEW: -
INTEGRATED: UAK-001 UAK-003 UAK-009 UAK-010 UAK-011 UAK-012 
CANCELLED: -

Claims (first 24; status --task ID shows detail):
UAK-002 | CLAIMED | kit-1 | until 1793874851 (EXPIRED: release --expired --read-summary TOKEN)

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1793737007 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-006 | Why: scope or criteria fixed before review
- 1793739442 | plan | JoahanMorales/JoahanMorales | tasks added: UAK-011 UAK-012 | Why: backlog without PR (Plan-Channel: claims)
- 1793753501 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-003 Paths: kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/state.awk, kit/.uak/tests/test_claims_read.py → k
- 1793906635 | deadline lease/UAK-002/1793874851 | REQUIRES_RECOVERY | Claim kept; read the summary and use release --expired --read-summary. No work is deleted.
- 1793906660 | UAK-013 | follow-up of UAK-012 by kit-2: The merge redirect parses on bash 3.2 (no case pattern) inside a command substitution | Why: same Paths, no scope change

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
