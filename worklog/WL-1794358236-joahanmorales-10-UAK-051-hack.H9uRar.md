# worklog/WL-1794358236-joahanmorales-10-UAK-051-hack.H9uRar.md · UAK-051

## Live summary
- Done: lint_paths_hint in lint.sh (awk, symbols.tsv+files.tsv of the map); tests green
- Decision: function counts only if it has _ or inner capital; warn only if no defining file is inside Paths; takes optional backlog file arg for plan
- Why: avoid prose false positives
- Failing: plan side needs lib/plan.sh (outside Paths); kit_lint dogfood flags UAK-006 when a local map exists
- Commands: python3 kit/.uak/tests/test_lint_paths_hint.py
- Next: review

## History
- 1794358236 | CLAIMED | joahanmorales-10 | claim; next: a new lint_paths_hint next to lint_tests_named in kit/.uak/bin/lib/lint.sh
- 1794358440 | CLAIMED | joahanmorales-10 | checkpoint; next: review
