# Existing tests a human allowed to change (uak allow --tests)

Append-only. Format: - ID | epoch | human | reason. Why: a test is a spec; changing one is a human decision.

- UAK-068 | 1794533900 | JoahanMorales | gene count 8 to 9 (stage gene)
- UAK-082 | 1794637977 | JoahanMorales | flake de Windows en la limpieza
- UAK-083 | 1794676817 | JoahanMorales | premisas que cambian con el tope de three.js y las fuentes distintas
- UAK-141 | 1795300954 | JoahanMorales | the minimal-count assertions compare against the bound with its 15% margin; calibrated from real Windows runs (one shard took 26m36s of 25)
- UAK-144 | 1795382352 | JoahanMorales | the Windows table is now in measured Windows seconds, the bound is 30 min (test_flaky_guard alone takes 25 min on Windows), WINDOWS_SCALE is gone
- UAK-150 | 1795392855 | JoahanMorales | twenty_runs_under_load and its assertion line moved unchanged from test_flaky_guard.py to test_flaky_guard_race.py; the MEASURED_* anchors in test_ci_shards.py got new values for the two files
