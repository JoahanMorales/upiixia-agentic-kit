# Lessons (uak learn)

Append-only. Format: - N | epoch | agent | task | paths | text. `uak recall` and `uak next` show the ones for your paths.

- 1 | 1793943651 | kit-r1 | - | kit/.uak/bin/lib/ | cache_put keys on TX's HEAD without checking the state was loaded from it: a put after a commit stores old state under the new tip. UAK-006: put only right after a state_load that follows the last commit.
- 2 | 1793993092 | kit-4 | - | kit/.uak/bin/lib/tx.sh | snapshot in lib/tx.sh: one awk pass; if a record can't be read awk fails and STATE.md is not rewritten (the old one did). Keep records readable; a fix would skip unreadable files before awk
- 3 | 1794006789 | kit-4 | - | scripts/claims_diff.py,kit/.uak/bin/lib/status.sh | claims_diff: no status --task runs after done, so status.sh's Task-Tip line is never compared (kit-r1 on c3b58d8); labels match on sha[:7]. Add a status --task step after done when touching it
- 4 | 1794010555 | kit-5 | - | kit/.uak/bin/smoke | smoke's UAK_SMOKE_TESTS is inherited by child processes and a duplicate name runs twice (kit-r1 on 5703f0d): unset it before the test loop if a nested smoke ever needs the whole suite
