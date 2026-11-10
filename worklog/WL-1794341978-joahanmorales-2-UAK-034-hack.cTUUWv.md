# worklog/WL-1794341978-joahanmorales-2-UAK-034-hack.cTUUWv.md · UAK-034

## Live summary
- Done: backlog_canonical shared by coord_init and load_task; 3 tests
- Decision: fallback only on a miss, so hot paths add no process
- Why: read paths without coord_init saw only main's TASKS.md
- Failing: -
- Commands: python3 kit/.uak/tests/test_status_planned.py
- Next: done

## History
- 1794341978 | CLAIMED | joahanmorales-2 | claim; next: the load_task fallback in the AVAILABLE branch of kit/.uak/bin/lib/status.sh
- 1794342433 | CLAIMED | joahanmorales-2 | checkpoint; next: done
