# STATE

Phase: execution
Updated: 1795334808
AVAILABLE: UAK-134 UAK-135 UAK-143 UAK-142 
CLAIMED: -
BLOCKED: -
REVIEW: UAK-131 
INTEGRATED: (116; last 12) ... UAK-127 UAK-128 UAK-129 UAK-130 UAK-132 UAK-133 UAK-136 UAK-137 UAK-138 UAK-139 UAK-140 UAK-141 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-131 | REVIEW | kit-a1 | until 1795418921

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1795300954 | allow | JoahanMorales | test change: UAK-141 | Why: the minimal-count assertions compare against the bound with its 15% margin; calibrated from real Windows runs (on
- 4102444800 | deadline lease/UAK-130/1795319001 | REQUIRES_RECOVERY | Claim kept; read the summary and use release --expired --read-summary. No work is deleted.
- 1795313415 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-129 Paths: kit/.uak/bin/smoke, kit/.uak/bin/lib/tests.sh, kit/.claude/agents/uak-reviewer.md, kit/.uak/mode
- 1795321743 | UAK-142 | follow-up of UAK-130 by joahanmorales-11: The read cache's lock is taken over atomically: clearing a dead holder's lock let two writers into the critical s
- 1795325610 | UAK-143 | follow-up of UAK-133 by joahanmorales-11: tokens: the budget scan runs in the background (a cold read added 4.5 s to status once per 5 min); a malformed ti

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
