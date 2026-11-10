# STATE

Phase: execution
Updated: 1794342561
AVAILABLE: UAK-027 UAK-032 UAK-033 UAK-035 UAK-036 UAK-038 UAK-041 UAK-042 
CLAIMED: UAK-037 
BLOCKED: -
REVIEW: UAK-028 UAK-029 UAK-030 UAK-031 UAK-034 UAK-039 UAK-040 
INTEGRATED: (19; last 12) ... UAK-010 UAK-011 UAK-012 UAK-013 UAK-014 UAK-015 UAK-016 UAK-017 UAK-018 UAK-019 UAK-020 UAK-021 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-028 | REVIEW | joahanmorales-4 | until 1794428603
UAK-029 | REVIEW | joahanmorales-1 | until 1794428523
UAK-030 | REVIEW | joahanmorales-8 | until 1794428961
UAK-031 | REVIEW | joahanmorales-5 | until 1794428724
UAK-034 | REVIEW | joahanmorales-2 | until 1794428856
UAK-037 | CLAIMED | joahanmorales-7 | until 1794356775
UAK-039 | REVIEW | joahanmorales-6 | until 1794428781
UAK-040 | REVIEW | joahanmorales-3 | until 1794428731

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1794342308 | UAK-040 | phase skills in kit/.agents/skills real dir; .agents/skills no longer a symlink; Gemini toml + skill; no .cursor/commands | Why: Cursor reads .agents/skill
- 1794342321 | UAK-031 | sentence appended after the allow line | Why: 7 retries
- 1794342379 | UAK-039 | rule 9 after the demo number-source rule | Why: zeros not a measurement
- 1794342433 | UAK-034 | fallback only on a miss, so hot paths add no process | Why: read paths without coord_init saw only main's TASKS.md
- 1794342559 | UAK-030 | reuse code ui-shots-missing (new code would need CLI.md); exact N.png wins | Why: critic approved prefixed names

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
