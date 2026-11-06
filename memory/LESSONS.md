# Lessons (uak learn)

Append-only. Format: - N | epoch | agent | task | paths | text. `uak recall` and `uak next` show the ones for your paths.

- 1 | 1793943651 | kit-r1 | - | kit/.uak/bin/lib/ | cache_put keys on TX's HEAD without checking the state was loaded from it: a put after a commit stores old state under the new tip. UAK-006: put only right after a state_load that follows the last commit.
