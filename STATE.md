# STATE

Phase: execution
Updated: 1795324207
AVAILABLE: UAK-134 UAK-135 UAK-142 
CLAIMED: -
BLOCKED: -
REVIEW: UAK-131 UAK-133 UAK-138 UAK-140 
INTEGRATED: (113; last 12) ... UAK-124 UAK-125 UAK-126 UAK-127 UAK-128 UAK-129 UAK-130 UAK-132 UAK-136 UAK-137 UAK-139 UAK-141 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-131 | REVIEW | kit-a1 | until 1795410178
UAK-133 | REVIEW | kit-a2 | until 1795410607
UAK-138 | REVIEW | kit-a1 | until 1795406161
UAK-140 | REVIEW | kit-a4 | until 1795404722

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1795300377 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-127 Paths: install.sh, kit/.uak/bin/doctor, kit/.uak/bin/smoke, kit/.uak/bin/uak-coordination, kit/.uak/bin
- 1795300954 | allow | JoahanMorales | test change: UAK-141 | Why: the minimal-count assertions compare against the bound with its 15% margin; calibrated from real Windows runs (on
- 4102444800 | deadline lease/UAK-130/1795319001 | REQUIRES_RECOVERY | Claim kept; read the summary and use release --expired --read-summary. No work is deleted.
- 1795313415 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-129 Paths: kit/.uak/bin/smoke, kit/.uak/bin/lib/tests.sh, kit/.claude/agents/uak-reviewer.md, kit/.uak/mode
- 1795321743 | UAK-142 | follow-up of UAK-130 by joahanmorales-11: The read cache's lock is taken over atomically: clearing a dead holder's lock let two writers into the critical s

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
