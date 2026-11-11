# worklog/WL-1794358236-joahanmorales-10-UAK-051-hack.H9uRar.md · UAK-051

## Live summary
- Done: python3 kit/.uak/tests/test_lint_paths_hint.py exit 0; kit_lint PASS with a local map · red at 1b3f9a6: exit 1 (no assertion line recognized: the reviewer reads the log)
- Decision: function counts only if it has _ or inner capital; warn only if no defining file is inside Paths; takes optional backlog file arg for plan
- Why: avoid prose false positives
- Failing: plan side needs lib/plan.sh (outside Paths); kit_lint dogfood flags UAK-006 when a local map exists
- Commands: python3 kit/.uak/tests/test_lint_paths_hint.py
- Next: Integrated in main: 35495b4146a430e0813f781b25d5d62f6c5d2a45 (recorded by joahanmorales-10)

## History
- 1794358236 | CLAIMED | joahanmorales-10 | claim; next: a new lint_paths_hint next to lint_tests_named in kit/.uak/bin/lib/lint.sh
- 1794358440 | CLAIMED | joahanmorales-10 | checkpoint; next: review
- 1794358442 | REVIEW | joahanmorales-10 | done; PR https://github.com/JoahanMorales/upiixia-agentic-kit/tree/feat/uak-051; evidence: python3 kit/.uak/tests/test_lint_paths_hint.py exit 0; warn/silent/no-map cases; 12 lint-related test files green; lint side only, plan side outside Paths · red at 1b3f9a6: exit 1 (no assertion line recognized: the reviewer reads the log); reviewer: -
- 1794358679 | REVIEW | joahanmorales-10 | done; PR https://github.com/JoahanMorales/upiixia-agentic-kit/tree/feat/uak-051; evidence: python3 kit/.uak/tests/test_lint_paths_hint.py exit 0; kit_lint PASS with a local map · red at 1b3f9a6: exit 1 (no assertion line recognized: the reviewer reads the log); reviewer: -
- 1794359015 | REVIEW | kit-r1 | review; approve; SHA f0d50e4f5ca4414ac3b3de0f7eba2f488d835317; reviewer kit-r1
- 1794359669 | INTEGRATED | joahanmorales-10 | integrate; recorded by joahanmorales-10; PR https://github.com/JoahanMorales/upiixia-agentic-kit/tree/feat/uak-051; merged 35495b4146a430e0813f781b25d5d62f6c5d2a45; proof ancestry
