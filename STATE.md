# STATE

Phase: execution
Updated: 1794346856
AVAILABLE: UAK-033 UAK-035 UAK-036 UAK-038 UAK-041 UAK-042 
CLAIMED: -
BLOCKED: -
REVIEW: UAK-037 UAK-040 
INTEGRATED: (27; last 12) ... UAK-018 UAK-019 UAK-020 UAK-021 UAK-027 UAK-028 UAK-029 UAK-030 UAK-031 UAK-032 UAK-034 UAK-039 
CANCELLED: UAK-002 UAK-005 

Claims (first 24; status --task ID shows detail):
UAK-037 | REVIEW | joahanmorales-7 | until 1794429003
UAK-040 | REVIEW | joahanmorales-3 | until 1794428731

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1794342433 | UAK-034 | fallback only on a miss, so hot paths add no process | Why: read paths without coord_init saw only main's TASKS.md
- 1794342559 | UAK-030 | reuse code ui-shots-missing (new code would need CLI.md); exact N.png wins | Why: critic approved prefixed names
- 1794342600 | UAK-037 | Gitleaks-Exception line in claims DECISIONS.md, turned into a temp .gitleaksignore (plus the project's own) via --gitleaks-ignore-path; path of fingerprint
- 1794342753 | UAK-027 | one step, hashFiles guard over all lockfiles, shell loop per dir; yarn via corepack too | Why: tsc not found in CI
- 1794342895 | UAK-032 | wt checks only an empty derived human (no --human, UAK_HUMAN or user.name); doctor FAILs on missing name or email | Why: spec

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
