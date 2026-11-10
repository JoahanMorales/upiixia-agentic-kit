# STATE

Phase: execution
Updated: 1794355134
AVAILABLE: UAK-038 
CLAIMED: -
BLOCKED: -
REVIEW: -
INTEGRATED: (35; last 12) ... UAK-031 UAK-032 UAK-033 UAK-034 UAK-035 UAK-036 UAK-037 UAK-039 UAK-040 UAK-041 UAK-042 UAK-043 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1794351939 | UAK-043 | per-dir archive; strip CR | Why: CI macos+windows
- 1794353950 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-033 Paths: kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/uak-coordination, kit/.uak/docs/PROTOCOL.md, kit/
- 1794353953 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-037 Paths: kit/.uak/bin/secret-scan, kit/.uak/bin/lib/security.sh, kit/.uak/tests/test_gitleaks_exception.p
- 1794354597 | UAK-041 | doctor FAILs only on a text-file/broken link or stale .agents/skills; a working symlink passes; install removes .cursor/skills when it holds only kit skill
- 1794355134 | UAK-044 | follow-up of UAK-037 by joahanmorales-7: gitleaks exceptions combine with .gitleaksignore on Windows | Why: same Paths, no scope change

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
