## UAK-168 · A pull request waits about ten minutes, not forty: CI in two tiers

- **Type:** feature
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-152
- **Paths:** .github/workflows/test.yml, scripts/kit_lint.py, scripts/ci_select.py, kit/.uak/tests/test_ci_shards.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/docs/WHY.md, AGENTS.md, docs/ARCHITECTURE.md
- **Acceptance:**
  - a pull request runs the first tier: the whole suite on Linux (4 shards, 3 to 7 minutes each today), and on macOS and on Windows only the tests the change can affect, in one job per system, two when the selection is predicted over 10 minutes. The selection is: every test file the change adds or edits; the tests that name a command or a library the change touches (the selector of `smoke --affected`, without its escalation to the whole suite); and a fixed portability set of at most six files, each under two minutes on Windows, listed with its reason (paths with spaces, symlinks, Bash 3.2, CRLF, case-insensitive names, process groups). What was not selected is printed in the job's summary as "runs on main"
  - a push to main and a tag run the second tier, the whole matrix as today (18 jobs), never cancelled; every commit on main keeps its own result
  - the whole matrix can be asked for on a pull request: the label `ci-full`, or a manual run (`workflow_dispatch`) of the branch; it is automatic when the change touches `.github/workflows/` or the selector itself
  - when the whole matrix of a commit on main fails, the workflow opens one issue "main is red at SHA" naming the failed jobs and the pull request that brought the commit, or adds to the open one; the first green run of main closes it. AGENTS.md says what follows: nobody merges on a red main except the fix or the revert
  - the selection is computed by one script the tests can call (`scripts/ci_select.py BASE HEAD` prints the files per system and the predicted seconds from the timing tables); the lint refuses a portability file that is missing, over two minutes on Windows, or without a reason; `test_ci_shards.py` keeps its bounds for the second tier and gains the first tier's: at most 9 jobs on a pull request, each macOS and Windows job predicted under 10 minutes
  - a change that adds a test file runs it on the three systems in the pull request, so its seconds can be measured before the timing tables are filled
  - measured on this task's own pull request and written in WHY.md: time from push to the last check before (a recent pull request of v6.8) and after
  - Why (the human, 2026-11-23, and run 45116515431): macOS jobs take 15 to 19 minutes and Windows 17 to 26, plus the wait for a runner; every push of every pull request paid all 18. Sixteen tasks are queued behind this
- **Tests:** pull_request_runs_the_first_tier, main_runs_the_whole_matrix, selection_has_changed_tests_named_tests_and_the_portability_set, selection_never_escalates_to_the_whole_suite, ci_full_label_runs_everything, workflow_change_runs_everything, new_test_file_runs_on_three_systems, red_main_opens_one_issue, first_tier_is_at_most_nine_jobs
- **Verify:** `python3 kit/.uak/tests/test_ci_tiers.py && python3 kit/.uak/tests/test_ci_shards.py`
- **Next step:** `.github/workflows/test.yml` (the `discover` job already computes the shards with `kit_lint.py --ci-shards` and `--ci-windows`); the selector of UAK-129 is in kit/.uak/bin/smoke (`--affected`); a new test file needs its entries in both timing tables; the workflow is the human's file, so the merge goes to the human
