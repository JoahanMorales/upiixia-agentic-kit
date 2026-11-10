# STATE

Phase: execution
Updated: 1794354919
AVAILABLE: UAK-038 
CLAIMED: -
BLOCKED: -
REVIEW: UAK-041 UAK-042 
INTEGRATED: (33; last 12) ... UAK-029 UAK-030 UAK-031 UAK-032 UAK-033 UAK-034 UAK-035 UAK-036 UAK-037 UAK-039 UAK-040 UAK-043 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-041 | REVIEW | joahanmorales-9 | until 1794440999
UAK-042 | REVIEW | joahanmorales-4 | until 1794441086

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1794351772 | UAK-043 | follow-up of UAK-036 by kit-w36: tokens publish: no race with an explicit publish; the Codex tick publishes on Windows | Why: same Paths, no scope change
- 1794351939 | UAK-043 | per-dir archive; strip CR | Why: CI macos+windows
- 1794353950 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-033 Paths: kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/uak-coordination, kit/.uak/docs/PROTOCOL.md, kit/
- 1794353953 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-037 Paths: kit/.uak/bin/secret-scan, kit/.uak/bin/lib/security.sh, kit/.uak/tests/test_gitleaks_exception.p
- 1794354597 | UAK-041 | doctor FAILs only on a text-file/broken link or stale .agents/skills; a working symlink passes; install removes .cursor/skills when it holds only kit skill

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
