## UAK-169 · The second run of a slow file cannot cost the job, and `ci` passes only on success

- **Type:** fix
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-168
- **Paths:** .github/workflows/test.yml, scripts/ci_select.py, scripts/kit_lint.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/tests/test_ci_shards.py, kit/.uak/docs/WHY.md, AGENTS.md
- **Acceptance:**
  - a failed file runs once more only when its second run fits: its entry in the timing table is at most 300 s and the job's elapsed time plus that entry stays under the job's test bound. A file over that fails the job on its first failure, and the summary says "not run again: FILE takes N s". Why: on main at `e4f2f83d` (run 45198280141) `windows (1)`, which holds `test_flaky_guard_race` (862 to 1336 s alone), was cancelled by its 45 minute limit after 55 minutes with no log left
  - a job cancelled by its time limit still says which file it was running: the runner prints the file's name and the clock before each file, flushed, and writes the partial result so the artifact exists
  - the final job `ci` passes only when `discover` and every test job that the tier planned concluded `success`; `skipped` and `cancelled` fail it
  - the issue "main is red" is closed only by a run of main whose `ci` job succeeded; a run cancelled by hand closes nothing. The job that opens it runs after a real re-run of the failed jobs when the failure was not in a file that already ran twice (a Linux failure, a set-up failure, a time limit), and says which of the two it was
  - the portability set has no file that failed intermittently on Windows in the last ten runs of main: `test_merge_renewer_orphan` is replaced by another file that covers process groups, or kept with the measurements that say it is steady; the lint refuses a member named in a list of known intermittent files
  - the cases that read the workflow as text are replaced or joined by cases on behaviour: the label reaching the selector (`ci_full_label_runs_everything`), `--retry` absent on Linux (`flaky_pass_is_reported_not_hidden`), the condition of the job that opens the issue (`red_main_opens_one_issue`); a case fails when a `run:` line of the workflow contains `${{ github.event` or `${{ inputs`
  - a selector that fails for one file fails `discover`; it does not select nothing for that file (`|| true` after `tf_affected_select` is removed or its failure is told apart from "no test names it")
  - the summary's "runs on main: N of M" counts both systems
- **Tests:** slow_file_is_not_run_twice, second_run_must_fit_the_bound, cancelled_job_names_its_file, ci_needs_success_not_skipped, cancelled_main_does_not_close_the_issue, portability_set_has_no_intermittent_file, label_reaches_the_selector, linux_never_retries_by_behaviour, no_event_text_in_run_lines, selector_failure_fails_discover
- **Verify:** `python3 kit/.uak/tests/test_ci_tiers.py && python3 kit/.uak/tests/test_ci_shards.py`
- **Next step:** `run_files` and `gate` in scripts/ci_select.py; the `windows` and `suite` jobs in `.github/workflows/test.yml`; the workflow is the human's file, so the merge goes to the human

## UAK-185 · The hook survives its own files being wrong, and no background job is without a limit

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-157
- **Paths:** kit/.uak/bin/hook, kit/.uak/tests/test_hook_session_start_speed.py
- **Acceptance:**
  - a time file (`uak-start.NAME.at`, a lock's `since`, the pace stamp) that holds `08`, letters, nothing, a date in the future or a number of twenty digits never ends the hook early and never blocks `pace` or `map build`: the value is treated as stale, and the session start prints everything it prints today. Why: the review of UAK-157 measured that `08` reduced the output to the identity line (an arithmetic error), and that a time one hour ahead stopped both jobs for that hour
  - reclaiming a stale lock cannot delete a lock another start has just taken: of eight simultaneous starts on a stale lock, each job runs once, in ten rounds of ten
  - `tokens --publish`, `bb flush`, the lens `map build`, `pr-sync` and `heartbeat` started by the hook run under the same limit as the session start's worker (60 s by default), and are killed with their children when they pass it; none leaves a process after the limit
  - a cached copy says its age whenever it is shown, not only while a refresh runs; a copy without a time file says "age unknown"; an age is never negative
  - the foreground of a session start launches no more processes than today (14 on startup, 9 on resume)
- **Tests:** corrupt_time_file_does_not_end_the_hook, future_time_file_is_stale, stale_lock_reclaim_runs_once, every_background_job_has_a_limit, cached_copy_always_says_its_age
- **Verify:** `python3 kit/.uak/tests/test_hook_session_start_speed.py`
- **Next step:** `start_once`, `start_show` and `pace_at` in kit/.uak/bin/hook (search `$((NOW - `); the `nohup` lines of `tokens_publish`, `bb flush` and `tick`

## UAK-186 · The merge reads the review mode from the base, and the smoke boot names what it refuses

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-155
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/done.sh, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/docs/CLI.md, kit/.uak/tests/test_done_without_github.py, kit/.uak/tests/test_smoke_onboarding.py, kit/.uak/tests/test_review_identity.py
- **Acceptance:**
  - `approval_check` reads `Review-Mode` from the base branch's configuration; `UAK_REVIEW_MODE` in the environment of `uak merge` cannot turn a project whose base says `gh` into one approved on claims. Why: the review of UAK-155 found the variable still read at `review-merge.sh:276`, so a task with a real pull request could be merged on a claims approval by whoever sets it
  - the tests that rely on the variable today set the mode in their fixture's base instead; the list of changed lines is in the task's note for the human's `uak allow`
  - the hint of `uak done` about `--pr none` no longer names the environment variable
  - a file or folder name with a newline is refused by the smoke boot with the same `SMOKE_REFUSED` line as the other names, and nothing runs
- **Tests:** env_review_mode_does_not_change_the_merge, merge_reads_the_base_mode, newline_name_is_refused_by_name
- **Verify:** `python3 kit/.uak/tests/test_done_without_github.py && python3 kit/.uak/tests/test_smoke_onboarding.py`
- **Next step:** `approval_check` in kit/.uak/bin/lib/review-merge.sh; `git grep -n UAK_REVIEW_MODE kit/.uak/tests` lists the tests to move to the base's configuration; changed assertions need `uak allow UAK-186 --tests` from the human
