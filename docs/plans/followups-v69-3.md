## UAK-190 · A killed black-box flush leaves no clone directory on Windows

- **Type:** fix
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-189
- **Paths:** kit/.uak/bin/hook, kit/.uak/bin/bb, kit/.uak/tests/test_hook_session_start_speed.py, kit/.uak/tests/timings/test_hook_session_start_speed.txt
- **Acceptance:**
  - after the hook kills a `bb flush` that passed its limit, no `uak-bb-tmp.*` directory is left in the git directory, on Windows as on Linux and macOS: the case `killed_bb_flush_is_recovered_and_published_once` passes 20 times in a row on a Windows runner. Why: on main at `967f794` (run 45326081765, `windows (10)`) the case failed with "the killed flush's clone directory is removed: […/.git/uak-bb-tmp.1795494673.16989]"; it had passed in the review of UAK-185 and in three earlier runs of main, so the removal races with the kill (a file still open in the killed tree cannot be removed on Windows)
  - the removal is retried for a bounded time after the kill and, when it still fails, the next flush removes the leftover first; a leftover older than its limit is never read as a live clone
  - the cause is written in the test's comment with the measurement that showed it (how long after the kill the directory could be removed, on Windows)
  - the file's Windows seconds are measured again and written with a `# measured` line; if it stays over 300 s, WHY.md says that a failure of this file on Windows is never retried in its job and needs `gh run rerun ID --failed`
- **Tests:** killed_flush_leaves_no_clone_on_windows, leftover_clone_is_removed_by_the_next_flush
- **Verify:** `python3 kit/.uak/tests/test_hook_session_start_speed.py`
- **Next step:** `bb_flush_job` and the kill of a limited job in kit/.uak/bin/hook; where `bb` makes `uak-bb-tmp.<time>.<pid>` through TMPDIR; prove it on CI with the label `ci-full` on the pull request, since the failure is only seen on Windows

## UAK-191 · CI leftovers: a cancelled step leaves no test running, and stale seconds are measured again

- **Type:** fix
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-169
- **Paths:** scripts/ci_select.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/tests/timings/test_done_without_github.txt, kit/.uak/tests/timings/test_ci_tiers.txt, kit/.uak/tests/timings/test_install_choice.txt, kit/.uak/tests/timings/test_guard_wizard_files.txt
- **Acceptance:**
  - when the driver of a test job receives SIGTERM or SIGINT (a cancelled step), the test file it is running and that file's children end with it: nothing is left reparented. Why: the review of UAK-169 sent SIGTERM to the driver and the test file and its grandchild kept running in their own session
  - `test_done_without_github` says `windows 68` and takes 187 to 263 s on Windows: its file, and the three others listed in Paths whose seconds were estimates, carry the median of the last five runs of main with a `# measured` line
  - no shard of main passes 80 % of its bound with the new numbers; if one does, the task says which and stops for the human (the number of jobs is the human's to change)
- **Tests:** cancelled_driver_leaves_no_test_running
- **Verify:** `python3 kit/.uak/tests/test_ci_tiers.py && python3 scripts/kit_lint.py`
- **Next step:** `run_files` and the session it starts each file in (scripts/ci_select.py); the group times in `gh run view RUN --log --job JOB` of the last five runs of main
