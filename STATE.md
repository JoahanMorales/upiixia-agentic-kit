# STATE

Phase: execution
Updated: 1795403886
AVAILABLE: -
CLAIMED: UAK-151 
BLOCKED: -
REVIEW: UAK-149 
INTEGRATED: (127; last 12) ... UAK-138 UAK-139 UAK-140 UAK-141 UAK-142 UAK-143 UAK-144 UAK-145 UAK-146 UAK-147 UAK-148 UAK-150 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-149 | REVIEW | kit-a2 | until 1795489843
UAK-151 | CLAIMED | kit-a1 | until 1795407396

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1795358521 | UAK-147 | follow-up of UAK-119 by joahanmorales-11: the dashboard computes the review lease like status and board: UAK_LEASE_SECONDS, else Lease-Seconds (default 180
- 1795382352 | allow | JoahanMorales | test change: UAK-144 | Why: the Windows table is now in measured Windows seconds, the bound is 30 min (test_flaky_guard alone takes 25 min on
- 1795386636 | plan | JoahanMorales/JoahanMorales | tasks added: UAK-148 UAK-149 UAK-150 | Why: backlog without PR (Plan-Channel: claims)
- 1795392855 | allow | JoahanMorales | test change: UAK-150 | Why: twenty_runs_under_load and its assertion line moved unchanged from test_flaky_guard.py to test_flaky_guard_race.p
- 1795392957 | UAK-151 | follow-up of UAK-150 by joahanmorales-11: twenty_runs_under_load runs as three cases, one per kind of job (picker, mcp, lease), so no test file is excepted

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
