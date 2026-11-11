# worklog/WL-1794357842-joahanmorales-1-UAK-046-hack.jGvzxP.md · UAK-046

## Live summary
- Done: doctor skill compare via find+tr+cksum; 3 tests green
- Decision: per-file path+cksum of CR-stripped content, extra/missing files count as stale
- Why: BSD diff <macOS13 lacks --strip-trailing-cr
- Failing: none
- Commands: python3 kit/.uak/tests/test_doctor_skills_compare.py
- Next: review

## History
- 1794357842 | CLAIMED | joahanmorales-1 | claim; next: the `diff -r -q --strip-trailing-cr` call in kit/.uak/bin/doctor
- 1794357965 | CLAIMED | joahanmorales-1 | checkpoint; next: review
