# STATE

Phase: execution
Updated: 4102444800
AVAILABLE: UAK-129 UAK-133 UAK-134 UAK-135 UAK-140 
CLAIMED: UAK-130 
BLOCKED: -
REVIEW: UAK-131 UAK-136 UAK-138 UAK-139 UAK-141 
INTEGRATED: (108; last 12) ... UAK-119 UAK-120 UAK-121 UAK-122 UAK-123 UAK-124 UAK-125 UAK-126 UAK-127 UAK-128 UAK-132 UAK-137 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-130 | CLAIMED | kit-a2 | until 1795319001 (EXPIRED: release --expired --read-summary TOKEN)
UAK-131 | REVIEW | kit-a1 | until 1795392881
UAK-136 | REVIEW | kit-a4 | until 1795387251
UAK-138 | REVIEW | kit-a1 | until 1795388291
UAK-139 | REVIEW | kit-a1 | until 1795389943
UAK-141 | REVIEW | kit-a5 | until 1795388281

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1795297417 | UAK-140 | follow-up of UAK-132 by joahanmorales-11: find_merge_commit compares trees from one git log, not one process per commit (2000 commits with a stale tip: 199
- 1795298010 | UAK-141 | follow-up of UAK-128 by joahanmorales-11: A seventh Windows shard: the longest took 23m55s of a 25 min bound; the lint also flags a bare push: with no bran
- 1795300377 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-127 Paths: install.sh, kit/.uak/bin/doctor, kit/.uak/bin/smoke, kit/.uak/bin/uak-coordination, kit/.uak/bin
- 1795300954 | allow | JoahanMorales | test change: UAK-141 | Why: the minimal-count assertions compare against the bound with its 15% margin; calibrated from real Windows runs (on
- 4102444800 | deadline lease/UAK-130/1795319001 | REQUIRES_RECOVERY | Claim kept; read the summary and use release --expired --read-summary. No work is deleted.

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
