# worklog/WL-1795235901-kit-breed-1-UAK-114-hack.ICH2Ng.md · UAK-114

## Live summary
- Done: Read done.sh and the existing tests; no code written
- Decision: Stopped: existing tests encode the old behaviour
- Why: Tests only grow
- Failing: test_integrate_outside.py merged_branch_of_an_available_task_unblocks_its_dependents (agent integrates AVAILABLE, no approval, expects rc 0) and outside_merges_are_counted_apart (agent integrates CLAIMED, no approval, 2 files, expects rc 0 and stats line) contradict the acceptance
- Commands: -
- Next: A human decides: amend those two tests (give them an approval or a human) or relax UAK-114

## History
- 1795235901 | CLAIMED | kit-breed-1 | claim; next: integrate_mutate at kit/.uak/bin/lib/done.sh:203-241
- 1795235921 | CLAIMED | kit-breed-1 | checkpoint; next: A human decides: amend those two tests (give them an approval or a human) or relax UAK-114
- 1795235924 | AVAILABLE | kit-breed-1 | release; claim released by kit-breed-1; reason: -; summary kept
