# DECISIONS

Coordination decisions on the claims branch.
Why: a reversible option after 15 min keeps work moving.
- 1793650134 | UAK-001 | reuse test_v592's shim counter; measure the second call | Why: one counter for hooks and claims; the first call of a clone writes its session file
- 1793681696 | UAK-009 | follow-up of UAK-001 by kit-1: The process counter counts ps, measures next for an idle agent too, and names traces uniquely (kit-r1's notes on UAK-001) | Why: same Paths, no scope change
