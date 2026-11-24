## UAK-187 · A test's seconds live in its own file, so two tasks that add a test can run at once

- **Type:** refactor
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-156
- **Paths:** scripts/kit_lint.py, scripts/ci_select.py, kit/.uak/tests/timings, kit/.uak/tests/test_ci_shards.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/tests/test_ci_timings.py, kit/.uak/docs/WHY.md, AGENTS.md, install.sh, kit/.uak/tests/test_install_light.py
- **Acceptance:**
  - the seconds of a test file are read from `kit/.uak/tests/timings/NAME.txt` (two lines: `ci N` and `windows N`, an optional `# why` line), one file per test; `CI_SECONDS` and `CI_WINDOWS_SECONDS` in `scripts/kit_lint.py` are built from that folder at import, with the same values as today for every test (a case compares the two tables before and after, entry by entry). Why: thirteen published tasks (UAK-156, 158 … 167, 169) list `scripts/kit_lint.py` only to add two numbers, the protocol refuses two live claims that share a path, so on 2026-11-23 the tasks of plan "visual setup" could only run one at a time
  - a task that adds a test adds its own timing file and does not touch `scripts/kit_lint.py`; AGENTS.md says so in one sentence
  - the lint still refuses a test file with no entry for either system and names the file to create; it also refuses a timing file with no test, a line it cannot read, a number that is not a whole number of seconds between 1 and 3600, and a second `ci` or `windows` line
  - `lint.CI_SECONDS`, `lint.CI_WINDOWS_SECONDS`, `ci_seconds`, `ci_windows_seconds`, `ci_shards` and `timing_problems` keep their names and results, so no existing case of `test_ci_shards` or `test_ci_tiers` changes; the shards of main are the same lists as before
  - the timing files are not installed in a project: an install has the same number of files as before this task
  - a pull request that changes only a timing file runs the first tier, not the whole matrix
- **Tests:** tables_equal_before_and_after, test_without_timing_file_is_named, timing_file_without_test_is_refused, unreadable_timing_line_is_refused, shards_are_unchanged, timings_are_not_installed, timing_only_change_is_first_tier
- **Verify:** `python3 kit/.uak/tests/test_ci_timings.py && python3 kit/.uak/tests/test_ci_shards.py && python3 kit/.uak/tests/test_ci_tiers.py && python3 scripts/kit_lint.py`
- **Next step:** `CI_SECONDS` at scripts/kit_lint.py:122 and `CI_WINDOWS_SECONDS` at :160; write the folder from the two tables with a script run once, then replace the literals by the reader. After it merges the human amends the Paths of the open tasks (remove `scripts/kit_lint.py`, add `kit/.uak/tests/timings`): the amend file is written with this task

## UAK-188 · The guard and SECURITY.md know the wizard's reopen key and its two new requests

- **Type:** fix
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-156
- **Paths:** kit/.uak/bin/guard, kit/.uak/docs/SECURITY.md, kit/.uak/tests/test_setup_trust.py, kit/.uak/tests/test_guard_wizard_files.py, kit/.uak/tests/timings
- **Acceptance:**
  - while a wizard is live for the project (its port file names a live process), the guard refuses an agent's command that reads, copies or prints `uak-wizard.key`, and one that names `/api/reopen` or `/api/closing` on the wizard's port or on a port it cannot read; with no live wizard the same commands pass, and a project's own `/api/reopen` on another port passes. Why: the review of UAK-156 ran `cat .git/uak-wizard.key` and a `curl` to `/api/reopen` through `guard check` and both were allowed; the key gives a fresh code for the human's page
  - the guard refuses an agent's command that removes or rewrites `uak-wizard.port`, `uak-wizard.key` or `uak-wizard.children` while a wizard is live: without the port file the rule above stops matching
  - SECURITY.md says what is left: a script that hides the request, any process of the same user that reads the key, and what the person sees when it happens (the line on the first server's terminal, the entry in the register, the notice on the open page); the sentence about a stolen code being "used once" is corrected for the reopen route
  - no rule of UAK-153's guard changes its result on the cases of `test_setup_trust`
- **Tests:** key_read_is_refused_while_live, reopen_and_closing_are_refused_on_the_wizard_port, same_names_pass_without_a_wizard, other_port_passes, record_files_cannot_be_removed_while_live, security_doc_names_the_reopen_key
- **Verify:** `python3 kit/.uak/tests/test_guard_wizard_files.py && python3 kit/.uak/tests/test_setup_trust.py`
- **Next step:** `wizard_mentioned` in kit/.uak/bin/guard; SECURITY.md line 42; the guard is the human's file, so the merge goes to the human

## UAK-189 · The gate's smoke does not inherit the caller's task, and three small leftovers of the reviews

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-186, UAK-185
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/bin/hook, kit/.uak/tests/test_gate_environment.py, kit/.uak/tests/test_hook_session_start_speed.py, kit/.uak/tests/test_smoke_onboarding.py, kit/.uak/tests/timings
- **Acceptance:**
  - `uak merge` run from a task's worktree gives the same smoke result as from the main checkout: the gate removes `UAK_TASK` (and the other variables `.uak-env` sets) from the environment of its smoke. Why: on 2026-11-23 the merge of UAK-157, run from its worktree, failed `test_manual_notes` and `test_task_participants` because their fixtures recorded under the real task; from the main checkout without the variable it merged
  - a pending black-box file whose owner belongs to another user of the system is not taken: a `kill -0` that fails for lack of permission counts as "alive" (the review of UAK-185: EPERM was read as "dead")
  - the smoke boot refuses a newline in any component of a path, not only in the last name
  - in `Review-Mode: auto` a project without `gh` in PATH says which mode it chose and why, once, in `uak done` and `uak merge`
- **Tests:** merge_from_worktree_equals_merge_from_main, smoke_environment_has_no_task, other_users_pending_file_is_left, newline_in_a_folder_is_refused, auto_mode_says_what_it_chose
- **Verify:** `python3 kit/.uak/tests/test_gate_environment.py && python3 kit/.uak/tests/test_smoke_onboarding.py && python3 kit/.uak/tests/test_hook_session_start_speed.py`
- **Next step:** where `approval_check` and the smoke are called in kit/.uak/bin/lib/review-merge.sh (search `smoke`); `bb_flush_job` in kit/.uak/bin/hook (search `kill -0`); the gate's library is the human's file, so the merge goes to the human
