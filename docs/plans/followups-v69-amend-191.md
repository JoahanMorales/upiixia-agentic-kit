## UAK-191 · CI leftovers: a cancelled step leaves no test running, and stale seconds are measured again

- **Type:** fix
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** UAK-169
- **Paths:** scripts/ci_select.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/tests/timings/test_done_without_github.txt, kit/.uak/tests/timings/test_ci_tiers.txt, kit/.uak/tests/timings/test_install_choice.txt, kit/.uak/tests/timings/test_guard_wizard_files.txt
- **Acceptance:**
  - when the driver of a test job receives SIGTERM or SIGINT (a cancelled step), the test file it is running and that file's children end with it: nothing is left reparented. Why: the review of UAK-169 sent SIGTERM to the driver and the test file and its grandchild kept running in their own session
  - `test_done_without_github` says `windows 68` and takes 187 to 263 s on Windows: its file, and the three others listed in Paths whose seconds were estimates, carry the median of the last five runs of main with a `# measured` line
  - no shard of main passes 80 % of its bound with the new numbers; if one does, the task says which and stops for the human (the number of jobs is the human's to change)
  - the cases of `test_ci_tiers` that replay a shard (`one_stale_entry_cannot_trip_the_slow_rule`, `truly_slow_job_trips_early`) use a frozen list of files and seconds written in the test, not the live table: adding or remeasuring any timing file can no longer flip them. Why: on 2026-11-24 the honest seconds of `test_install_choice` (windows 85) and of `test_guard_wizard_files` failed `one_stale_entry_cannot_trip_the_slow_rule` because they changed which files share a shard with `test_done_without_github`; 60 passed, 85 to 88 failed, 90 to 105 passed, 150 failed, so authors were choosing numbers that pass instead of the measured ones. The changed lines need `uak allow UAK-191 --tests`
- **Tests:** cancelled_driver_leaves_no_test_running, shard_replays_do_not_read_the_live_table
- **Verify:** `python3 kit/.uak/tests/test_ci_tiers.py && python3 scripts/kit_lint.py`
- **Next step:** `run_files` and the session it starts each file in (scripts/ci_select.py); the group times in `gh run view RUN --log --job JOB` of the last five runs of main
