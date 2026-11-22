# STATE

Phase: execution
Updated: 1795364873
AVAILABLE: -
CLAIMED: UAK-144 
BLOCKED: -
REVIEW: -
INTEGRATED: (124; last 12) ... UAK-135 UAK-136 UAK-137 UAK-138 UAK-139 UAK-140 UAK-141 UAK-142 UAK-143 UAK-145 UAK-146 UAK-147 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-144 | CLAIMED | kit-a1 | until 1795352826 (EXPIRED: release --expired --read-summary TOKEN)

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1795334835 | UAK-144 | follow-up of UAK-128 by joahanmorales-11: The CI timing table is measured again: Windows shards 5 and 6 took 34m39s and 26m59s against a predicted 20.4 min
- 1795338625 | UAK-145 | follow-up of UAK-134 by joahanmorales-11: board reads the review lease from the fetched config and honours UAK_LEASE_SECONDS, so board and status agree on 
- 1795349411 | UAK-146 | follow-up of UAK-135 by joahanmorales-11: doctor compares hook dirs with -ef instead of lowercase text (a different .UAK/githooks is not the kit's on a cas
- 1795352835 | deadline lease/UAK-144/1795352826 | REQUIRES_RECOVERY | Claim kept; read the summary and use release --expired --read-summary. No work is deleted.
- 1795358521 | UAK-147 | follow-up of UAK-119 by joahanmorales-11: the dashboard computes the review lease like status and board: UAK_LEASE_SECONDS, else Lease-Seconds (default 180

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
