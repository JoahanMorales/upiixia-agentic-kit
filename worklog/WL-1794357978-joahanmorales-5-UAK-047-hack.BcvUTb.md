# worklog/WL-1794357978-joahanmorales-5-UAK-047-hack.BcvUTb.md · UAK-047

## Live summary
- Done: install cleanup per skill folder by known-files hashes; tests green
- Decision: CRLF-stripped hash also counts as shipped; extra file = edited; folder rmdir'd when empty
- Why: name-only match deleted edited copies
- Failing: test_skills_windows_clone update_refreshes_copied_skills (UAK-041) asserts the old behaviour, outside Paths
- Commands: python3 kit/.uak/tests/test_cursor_skills_keep.py
- Next: review

## History
- 1794357978 | CLAIMED | joahanmorales-5 | claim; next: the .cursor/skills cleanup in install.sh
- 1794358222 | CLAIMED | joahanmorales-5 | checkpoint; next: review
