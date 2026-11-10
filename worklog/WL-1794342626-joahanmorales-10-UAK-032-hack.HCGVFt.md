# worklog/WL-1794342626-joahanmorales-10-UAK-032-hack.HCGVFt.md · UAK-032

## Live summary
- Done: wt new and doctor name the git config fix
- Decision: wt checks only an empty derived human (no --human, UAK_HUMAN or user.name); doctor FAILs on missing name or email
- Why: spec
- Failing: none
- Commands: python3 kit/.uak/tests/test_git_identity_msg.py
- Next: done

## History
- 1794342626 | CLAIMED | joahanmorales-10 | claim; next: where wt derives the human name from git config, before clean_id, in kit/.uak/bin/wt
- 1794342895 | CLAIMED | joahanmorales-10 | checkpoint; next: done
