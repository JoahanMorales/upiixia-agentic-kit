# STATE

Phase: execution
Updated: 1795543557
AVAILABLE: UAK-160 UAK-163 UAK-164 UAK-165 UAK-166 UAK-167 
CLAIMED: UAK-159 UAK-162 
BLOCKED: -
REVIEW: UAK-190 UAK-191 
INTEGRATED: (143; last 12) ... UAK-155 UAK-156 UAK-157 UAK-158 UAK-161 UAK-168 UAK-169 UAK-185 UAK-186 UAK-187 UAK-188 UAK-189 
CANCELLED: UAK-002 UAK-005 UAK-149 

Claims (first 24; status --task ID shows detail):
UAK-159 | CLAIMED | kit-a1 | until 1795531661 (EXPIRED: release --expired --read-summary TOKEN)
UAK-162 | CLAIMED | kit-a2 | until 1795552429
UAK-190 | REVIEW | kit-a3 | until 1795611856
UAK-191 | REVIEW | kit-a4 | until 1795629650

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1795537979 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-159 Paths: kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, docs/DASHBOARD.md, kit/.uak/tests/test_s
- 1795537983 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-191 Paths: scripts/ci_select.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/tests/timings/test_done_without_
- 1795537986 | allow | JoahanMorales | test change: UAK-191 | Why: dos casos de test_ci_tiers leen la tabla viva y tres casos fijan el tope en 19 trabajos
- 1795538018 | deadline lease/UAK-159/1795531661 | REQUIRES_RECOVERY | Claim kept; read the summary and use release --expired --read-summary. No work is deleted.
- 1795542933 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-162 | Why: scope or criteria fixed before review

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
