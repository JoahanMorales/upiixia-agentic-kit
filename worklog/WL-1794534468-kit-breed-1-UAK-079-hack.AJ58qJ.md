# worklog/WL-1794534468-kit-breed-1-UAK-079-hack.AJ58qJ.md · UAK-079

## Live summary
- Done: root cause + fix + regression cases
- Decision: fix verify_parse_error (SIGPIPE under pipefail); stale-cache was not the cause
- Why: flaky gate
- Failing: -
- Commands: python3 kit/.uak/tests/test_v59.py
- Next: done

## History
- 1794534468 | CLAIMED | kit-breed-1 | claim; next: reproduce with `for i in $(seq 30); do UAK_SMOKE_TESTS="test_v59 test_hack test_v58 test_v42" bash kit/.uak/bin/smoke --package-only --jobs 4 || break; done`
- 1794536297 | CLAIMED | kit-breed-1 | checkpoint; next: done
