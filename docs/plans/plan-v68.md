## UAK-127 · An install without the kit's own tests, with skills on demand

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/bin/doctor, kit/.uak/bin/smoke, kit/.uak/bin/uak-coordination, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, scripts/kit_hashes.py, kit/.uak/tests/test_install_light.py
- **Acceptance:**
  - `install.sh` no longer copies `kit/.uak/tests/` into a project (112 files, 1.5 MB): a project's `smoke` runs its own checks and the product smoke, and says in one line that the kit's protocol suite runs in the kit's repository. `--with-tests` installs them as today; `--update` removes the kit's test files it recognizes by hash (`known-files.txt`) and keeps any file a team edited or added
  - the skill library (`.uak/skills/`, 114 files) is not copied whole: the install places only the skills the mode, stack and `--skills` ask for, as today under `.claude/skills` and `.agents/skills`, and `uak skill add NAME` copies one more from the kit's checkout or, with no checkout, from the pinned release (git only, hash-checked like the external skills)
  - a marathon install for Claude Code is under 200 files (was 535, 9.3 MB); the test prints the count and the bytes and fails over the bound
  - `doctor` does not ask for the test directory, and every command that reads `.uak/tests` or `.uak/skills` works when they are absent
  - Why (audit of v6.5.0, docs/audit-2026-11.md §1): an install put 535 files and 9.3 MB in a project, of which 108 were the kit's own tests and 114 the skill library; heavy in files, not in context
- **Tests:** install_has_no_kit_tests, with_tests_installs_them, update_removes_only_known_test_files, skill_add_copies_one, marathon_install_under_200_files
- **Verify:** `python3 kit/.uak/tests/test_install_light.py`
- **Next step:** the copy loop at install.sh:107 (`for part in bin docs modes templates tests settings stacks skills`) and the skill placement at install.sh:162-173

## UAK-128 · Windows CI in shards, and one run per commit

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** .github/workflows/test.yml, scripts/kit_lint.py, kit/.uak/tests/test_ci_shards.py
- **Acceptance:**
  - the Windows job runs the test files in shards balanced by each file's measured seconds, as Linux and macOS already do (`kit_lint.py --ci-shards N`), instead of one job per test file; the number of shards is the smallest that keeps the longest shard under 25 minutes with the measured times, and the test computes it from the same table
  - a push to a branch that has an open pull request does not run the suite twice: the workflow runs on `pull_request` and on pushes to `main` and tags only
  - a commit on main starts at most 24 jobs (was 121), and a new test file still runs on the three systems with no edit to the workflow
  - a shard that fails names the test file that failed in its job summary
  - Why (audit §1): 105 jobs per push and about 200 checks per PR, one job per test file on Windows, on push and again on pull_request; the largest cost in compute, and "every run green" meant reading 121 results
- **Tests:** windows_matrix_is_shards, shards_cover_every_test_file_once, longest_shard_under_the_bound, workflow_runs_once_per_commit
- **Verify:** `python3 kit/.uak/tests/test_ci_shards.py`
- **Next step:** the `windows:` job at .github/workflows/test.yml:67 and `--ci-shards` in scripts/kit_lint.py

## UAK-129 · The reviewer runs Verify and the tests the diff touches; the whole suite runs once, at the merge gate

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/smoke, kit/.uak/bin/lib/tests.sh, kit/.claude/agents/uak-reviewer.md, kit/.uak/modes/sprint.md, kit/.uak/modes/marathon.md, kit/.uak/docs/CLI.md, kit/.uak/tests/test_smoke_affected.py
- **Acceptance:**
  - `smoke --affected [BASE]` runs the lint, the secret scan, the task's Verify and only the test files the diff against BASE touches or names (a test file changed; a test file whose name or imports match a changed engine file; every file when the diff touches `lib/core.sh`, `lib/tx.sh` or the test helpers). It prints which files it chose and why, and how many it left for the gate
  - the reviewer's instructions and both mode files say: Verify plus `smoke --affected`, and the note of an approval says which was run; the author does the same before `done`
  - the merge gate keeps running the whole suite on the merged result; nothing an agent sets (an environment variable, a flag) makes the gate run fewer tests
  - on the kit's own repository the three runs per task become one whole run and two partial ones; the test measures a partial run on a one-file diff under a quarter of the files
  - Why (audit §1): the suite took 8–10 min and ran three times per task (author, reviewer, gate), the largest cost in time; 152 review rounds in 105 tasks each paid a whole run
- **Tests:** affected_runs_changed_test_files, engine_change_selects_its_tests, core_change_runs_everything, gate_ignores_the_shortcut, prints_what_it_left
- **Verify:** `python3 kit/.uak/tests/test_smoke_affected.py`
- **Next step:** the `UAK_SMOKE_TESTS` selection at kit/.uak/bin/smoke:41-56 and step 26 of kit/.claude/agents/uak-reviewer.md

## UAK-130 · `status` and `next` read one cached fetch of claims

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/cache.sh, kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/net.sh, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_read_cache.py, kit/.uak/tests/test_claims_perf.py
- **Acceptance:**
  - a read command (`status`, `next`, `inbox`, `board`, `timeline`, `metrics`) reuses the last fetch of claims when it is younger than `Read-Cache: N` seconds of PROJECT.md (default 20; 0 turns it off), and says so in its last line ("claims as of 12 s ago"); `--fresh` fetches now
  - every command that writes (claim, done, review, merge, heartbeat and the rest) fetches as today and refreshes the cache with what it pushed, so an agent always reads its own writes
  - two reads within the window cost one fetch: the test counts the fetches, and the second `status` takes under half the time of the first on the fixture
  - the process targets `test_claims_perf` keeps as expected failures are measured again and lowered to what this reaches; `heartbeat` is not a read and stays out of this task
  - Why (audit §1; `uak metrics`, 2026-11-21): `status` took 3.7 s and `next` 2.3 s, each a fetch of claims, and agents poll 2.7 times per `done`; the ledger measured `status` at a median of 1.9 s over 13 calls
- **Tests:** second_read_reuses_the_fetch, a_write_refreshes_the_cache, fresh_fetches_now, zero_turns_it_off, read_says_how_old
- **Verify:** `python3 kit/.uak/tests/test_read_cache.py`
- **Next step:** the tip-keyed cache in kit/.uak/bin/lib/cache.sh and the fetch in kit/.uak/bin/lib/net.sh

## UAK-131 · `Merge-Engine: ci`: an approved engine change with every check green does not wait for a human

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/config.sh, kit/.uak/bin/lib/github.sh, kit/.uak/bin/doctor, kit/.uak/docs/WHY.md, kit/.uak/docs/CLI.md, kit/.uak/tests/test_merge_engine_policy.py
- **Acceptance:**
  - `Merge-Engine: human` (the default, today's behavior) or `ci` in `.uak/PROJECT.md`, changed only by a human commit on the base. With `ci`, a task whose diff touches a shared path of the engine list (`.uak/bin/uak`, `.uak/bin/lib/`, `.uak/bin/smoke`, `.githooks/`, CI workflows) merges through the gate when: an identity other than the author approved the exact tip, every check of that SHA on the forge finished green (all runs, not the first), the gate's own smoke passed on the merged result, and the task is in sprint mode or `Review-Independence` is satisfied
  - lock files, migrations, `PROJECT.md` and the smoke provenance file still go to the human with either value; a check still running or not found is "wait", never green
  - the task record says `Merge-Policy: ci` and names the checks counted; `uak metrics` counts these merges apart from the human-landed ones
  - `doctor` warns when `Merge-Engine: ci` is set and the base branch has no required checks on the forge
  - Why (`uak metrics`, 2026-11-21): the gate sent 39 of 39 queued tasks to a human, 38 of them as "Shared resource/CI needs a human"; 46 of 104 integrated tasks were built by the gate and then landed by a person who added no check of their own
- **Tests:** human_is_the_default, ci_merges_when_every_check_is_green, a_running_check_waits, a_red_check_refuses, lock_files_still_need_a_human, record_names_the_policy
- **Verify:** `python3 kit/.uak/tests/test_merge_engine_policy.py`
- **Next step:** the `shared` list and `RM_REASON="Shared resource/CI needs a human"` at kit/.uak/bin/lib/review-merge.sh:628-655

## UAK-132 · `Merge-Commit` names the task's own merge

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/bin/lib/metrics.py, kit/.uak/tests/test_merge_commit_field.py
- **Acceptance:**
  - `integrate` records in `Merge-Commit` the commit on the base that brought this task's tip in (the merge commit whose second parent is the tip or contains it and whose subject or PR names the task; for a squash, the commit whose tree matches), never the tip of the base at the time or another task's merge
  - when no such commit is found the field says `unknown` and the reason goes in the event, instead of a wrong SHA
  - `uak metrics` and `uak timeline` use the field again and report how many records they had to classify by history because the field was wrong or unknown; records written before this task are not rewritten
  - Why (review of UAK-117, 2026-11-21): on UAK-030 and UAK-013 the field named another task's merge, so `metrics` stopped trusting it and classified 104 tasks from the base's history
- **Tests:** integrate_records_its_own_merge, two_tasks_merged_together_get_their_own, squash_is_found_by_tree, unknown_when_not_found, metrics_counts_untrusted_records
- **Verify:** `python3 kit/.uak/tests/test_merge_commit_field.py`
- **Next step:** `put "$RECORD" Merge-Commit "$merged"` at kit/.uak/bin/lib/done.sh:282 and :333, and the note at kit/.uak/bin/lib/metrics.py:203

## UAK-133 · `tokens --since` by message time, and the budget warning where agents look

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-130
- **Paths:** kit/.uak/bin/tokens, kit/.uak/bin/lib/status.sh, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_tokens_window.py
- **Acceptance:**
  - `--since DAYS` counts the messages whose own timestamp is inside the window; a long session file changed today no longer brings in the tokens of last month (today the window picks whole files by modification time)
  - `uak next` and `uak status` print the `TOKENS_BUDGET` line of `tokens --budget-check` for the agent's live task when it crossed `Token-Budget`, once per call, and nothing when no budget is set or no transcript is readable; no extra fetch
  - totals without `--since` stay byte-identical on the fixture
  - Why (v6.7.0, left open): one session of several days put its whole spend in a one-day window, and the budget warning existed only as a command nobody calls
- **Tests:** since_counts_by_message_time, an_old_message_in_a_new_file_is_out, next_warns_over_budget, status_warns_over_budget, no_budget_prints_nothing
- **Verify:** `python3 kit/.uak/tests/test_tokens_window.py`
- **Next step:** `find … -mtime "-$since"` at kit/.uak/bin/tokens:71 and :145, and the budget check at kit/.uak/bin/tokens:286

## UAK-134 · REVIEW sub-states in `board` and in `--json status`

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** UAK-133
- **Paths:** kit/.uak/bin/board, kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/json.sh, kit/.uak/docs/CLI.md, kit/.uak/tests/test_review_substates.py
- **Acceptance:**
  - `uak board` prints each REVIEW task's sub-state and the time in it, with the words `uak status` and the dashboard use
  - `uak --json status` carries `review_substate`, `review_substate_since` and `review_round` for a task in REVIEW, documented in CLI.md; every existing key keeps its name and type
  - the three surfaces are compared in one test on the same fixture, so they cannot drift
  - Why (UAK-119's acceptance, v6.7.0): the sub-state reached `status` and the dashboard, and `board` and the JSON output were left out
- **Tests:** board_prints_the_substate, json_status_has_the_substate, three_surfaces_agree
- **Verify:** `python3 kit/.uak/tests/test_review_substates.py`
- **Next step:** `review_substate` at kit/.uak/bin/lib/status.sh:37 and the board's REVIEW column in kit/.uak/bin/board

## UAK-135 · `doctor` and `wt` know the pre-push hook, and never point git at a hooks directory that is not there

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-127
- **Paths:** kit/.uak/bin/doctor, kit/.uak/bin/wt, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/tests/test_hooks_health.py
- **Acceptance:**
  - `doctor` checks the pre-push hook as it checks pre-commit: present, executable, the kit's or calling the kit's (`bash .uak/githooks/pre-push "$@"` from another hook manager), and `--fix` restores the kit's own without overwriting a team's
  - `wt new` sets `core.hooksPath` only to a directory that exists and holds the kit's hooks; when neither `.uak/githooks` nor `.githooks` is there it leaves the setting alone and says so once
  - `doctor` fails when `core.hooksPath` names a directory that does not exist (every hook silently off), with the fix in the message
  - Why (v6.7.0): the kit's own repository had `core.hooksPath=.githooks` with no such directory for weeks, set by `wt`, so neither the secret scan nor the pre-push ran there and nothing said so; `doctor` and `wt` were written before UAK-124 added pre-push
- **Tests:** doctor_checks_pre_push, doctor_fails_on_a_missing_hooks_dir, wt_does_not_point_at_nothing, fix_keeps_a_teams_hook
- **Verify:** `python3 kit/.uak/tests/test_hooks_health.py`
- **Next step:** the hooks block at kit/.uak/bin/doctor:69-82 and `hooks_dir=` at kit/.uak/bin/wt:271

## UAK-136 · The ledger times every command, and `metrics` has no empty rows

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-132
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/lib/ledger.sh, kit/.uak/bin/lib/metrics.py, kit/.uak/tests/test_command_ledger.py, kit/.uak/tests/test_metrics.py
- **Acceptance:**
  - a command the dispatcher starts by replacing the shell (`metrics`, `timeline`, `dash`, `autopsy`, `stats`, `red` and the rest of the `exec` rows) records its exit code and milliseconds like the others, with no extra process when the command is one of the engine's own scripts (the script closes its own ledger line) and at most one otherwise
  - `uak metrics` prints "errors 0 of 0 · median -" for no command that ran after this task; lines written before it are counted as "outcome not recorded", apart
  - "commits on the base with no task" is computed inside a `--since` window too (first-parent commits of the window), and says `n/a` only when the base branch is really not visible
  - "manual notes" prints a count, 0 included, once any black box of the window comes from a version that records them
  - Why (`uak metrics`, 2026-11-21): six commands showed calls with "errors 0 of 0" and no duration, and the two lines about work outside the kit said `n/a` and "not recorded yet" on a repository that records both
- **Tests:** exec_commands_record_code_and_ms, old_lines_are_counted_apart, direct_commits_inside_a_window, manual_notes_print_zero
- **Verify:** `python3 kit/.uak/tests/test_command_ledger.py && python3 kit/.uak/tests/test_metrics.py`
- **Next step:** `[ "$REG_RUN" != exec ] || { ledger_end - …; exec …; }` at kit/.uak/bin/uak:117 and kit/.uak/bin/lib/metrics.py:443-448

## UAK-137 · The autopsy keeps exit codes apart and labels anonymous notes as what they are

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/autopsy, kit/.uak/tests/test_autopsy.py
- **Acceptance:**
  - failure classes are grouped after normalizing only what varies (paths, SHAs, task IDs, durations); a number that carries meaning stays: `exit 1` and `exit 2`, an HTTP status and a signal are different classes
  - with `--anonymous` the notes section says the free text was withheld and shows counts by kind; it no longer says "verbatim" above text that is not there
  - the report of a fixture with both exit codes lists two classes with their own counts
  - Why (review of UAK-123, v6.7.0): the normalizer merged `exit 1` with `exit 2`, and the anonymous report kept the banner of the full one
- **Tests:** exit_codes_stay_apart, http_status_stays_apart, anonymous_banner_says_withheld
- **Verify:** `python3 kit/.uak/tests/test_autopsy.py`
- **Next step:** the normalizer and the "Agent notes · UNTRUSTED DATA" banner at kit/.uak/bin/autopsy:367

## UAK-138 · Three tests that fail on a loaded or Windows runner without a defect

- **Type:** bug
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-128
- **Paths:** kit/.uak/bin/lib/gallery_pick.py, kit/.uak/bin/uak-mcp, kit/.uak/tests/test_design_pick.py, kit/.uak/tests/test_review_merge.py, kit/.uak/tests/test_hack.py, tests/test_mcp_tools.py, kit/.uak/tests/test_flaky_guard.py
- **Acceptance:**
  - the design picker reads the request body before it answers 403 to a request without the token, so a Windows client no longer sees the connection reset (WinError 10053) while it is still sending
  - the MCP server exits within 2 seconds of its input closing on Windows (today the test's teardown has to kill it and warns); the teardown's kill stays as a net and the test fails when it is needed
  - the lease test that depends on wall-clock margins (`gate_and_lease` in test_review_merge.py) uses the engine's injected clock for every deadline, so a slow runner cannot expire a lease mid-test
  - each of the three passes 20 times in a row under load (the suite running beside it); the test file that proves it runs them with a CPU hog and is skipped only when `UAK_SMOKE_FAST=1`
  - Why (CI of v6.5.0 to v6.7.0): these three failed and passed on a rerun on at least five pushes, and "every run green" meant rerunning jobs by hand
- **Tests:** picker_reads_the_body_before_403, mcp_server_exits_when_stdin_closes, lease_test_uses_the_injected_clock, twenty_runs_under_load
- **Verify:** `python3 kit/.uak/tests/test_flaky_guard.py`
- **Next step:** the 403 path in kit/.uak/bin/lib/gallery_pick.py, the read loop of kit/.uak/bin/uak-mcp and the teardown in tests/test_mcp_tools.py

## UAK-139 · The demo records a model and a harness, so its story shows who did what

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/demo, kit/.uak/tests/test_demo.py, docs/media/dash-task.png
- **Acceptance:**
  - the three agents of `uak demo` run with a model and a harness of their own (set by the demo, marked as the demo's), so `uak timeline HACK-001` and the dashboard's drawer show them instead of "model unknown · harness unknown"
  - the demo's printed lines and its duration stay as they are; `docs/media/dash-task.png` is captured again from the demo
  - Why (2026-11-21, the README capture): the first thing a new user opens showed "unknown" eight times in the feature v6.7 added
- **Tests:** demo_timeline_names_models, demo_output_unchanged
- **Verify:** `python3 kit/.uak/tests/test_demo.py`
- **Next step:** where the demo sets each agent's environment in kit/.uak/bin/demo
