# Backlog published on claims (uak plan)

Append-only; added to .uak/TASKS.md from main. Why: adding tasks never waits for a PR.

## UAK-009 · The process counter counts ps, measures next for an idle agent too, and names traces uniquely (kit-r1's notes on UAK-001) (follow-up of UAK-001)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-001
- **Follow-up of:** UAK-001
- **Paths:** kit/.uak/tests/test_claims_perf.py, scripts/perf_claims.sh, kit/.uak/bin/smoke, .github/workflows/test.yml
- **Freeze-Allowed:** no
- **Acceptance:**
  - The process counter counts ps, measures next for an idle agent too, and names traces uniquely (kit-r1's notes on UAK-001)
- **Verify:** `python3 kit/.uak/tests/test_claims_perf.py`
## UAK-010 · The merge gate runs smoke and Verify without uak's own SSH settings

- **Type:** bug
- **Priority:** P0
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/lib/net.sh, kit/.uak/bin/lib/review-merge.sh, kit/.uak/tests/test_v511.py
- **Acceptance:** uak turns on its SSH connection reuse (`GIT_SSH_COMMAND` with ControlMaster) for its own git calls only; the project's smoke and Verify, run by the merge gate, see the caller's `GIT_SSH_COMMAND` and `GIT_SSH` as they were (unset when they were unset), found by dogfooding: the gate of UAK-009 failed test_v5 latency_paths ("https remotes are left alone") because the suite inherited uak's `GIT_SSH_COMMAND`
- **Tests:** gate_runs_smoke_and_verify_with_the_callers_ssh_env
- **Verify:** `python3 kit/.uak/tests/test_v511.py --case gate_runs_smoke_and_verify_with_the_callers_ssh_env`
- **Next step:** save the caller's GIT_SSH_COMMAND/GIT_SSH before ssh_mux in kit/.uak/bin/uak; restore them in the two subshells of rm_gate (review-merge.sh: smoke and Verify)
## UAK-011 · CI finds the test files itself

- **Type:** feature
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** .github/workflows/test.yml, kit/.uak/bin/smoke, scripts/kit_lint.py
- **Test-First:** no (CI configuration: kit_lint checks it, and CI runs it on the three systems)
- **Acceptance:** a first CI job lists `kit/.uak/tests/test_*.py` and the Windows matrix comes from that list: a new test file runs on Windows with no edit to the workflow, `kit/.uak/bin/smoke --package-only` runs every `test_*.py` it finds, in a stable order, instead of a hand-kept list, kit_lint stops asking for each test file in the workflow and in smoke, and checks the discovery instead, found by dogfooding: every task that added a test file had to edit the workflow, and the merge gate sends every workflow change to a human
- **Verify:** `python3 scripts/kit_lint.py`
- **Next step:** the `windows` job of .github/workflows/test.yml (matrix.t) and the list in kit/.uak/bin/smoke

## UAK-012 · uak merge runs the base's engine, never the branch's

- **Type:** bug
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak, kit/.uak/tests/test_v511.py
- **Acceptance:** `uak merge` run from a task worktree whose `.uak/bin` differs from the main checkout's runs the main checkout's engine (and says so in one line): the gate that checks a branch is never that branch's code, found by dogfooding: with the shims of this repo, `uak merge` from a worktree ran the branch's own review-merge.sh
- **Tests:** merge_runs_the_main_checkouts_engine_not_the_branchs
- **Verify:** `python3 kit/.uak/tests/test_v511.py --case merge_runs_the_main_checkouts_engine_not_the_branchs`
- **Next step:** the dispatch of `merge` in kit/.uak/bin/uak (registry route merge_run)

## UAK-013 · The merge redirect parses on bash 3.2 (no case pattern) inside a command substitution (follow-up of UAK-012)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-012
- **Follow-up of:** UAK-012
- **Paths:** kit/.uak/bin/uak, kit/.uak/tests/test_v511.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - The merge redirect parses on bash 3.2 (no case pattern) inside a command substitution
- **Verify:** `python3 kit/.uak/tests/test_v511.py --case merge_runs_the_main_checkouts_engine_not_the_branchs`

## UAK-014 · status and next print no carriage return from a CRLF checkout; golden test normalizes /private (follow-up of UAK-003)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-003
- **Follow-up of:** UAK-003
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/core.sh, kit/.uak/bin/lib/state.awk, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_claims_read.py, kit/.uak/tests/test_claims_perf.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - status and next print no carriage return from a CRLF checkout; golden test normalizes /private
- **Verify:** `python3 kit/.uak/tests/test_claims_read.py && python3 kit/.uak/tests/test_claims_perf.py`

## UAK-015 · The bash 3.2 comsub checker counts $(( )) inside $( ) as one paren level: y=$(case $a in (b) echo $((1));; esac) is a false positive, y=$(echo $((1+1)); case $a in b) :;; esac) a false negative; consume both closing parens and add the two samples (follow-up of UAK-013)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-013
- **Follow-up of:** UAK-013
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/doctor, kit/.uak/tests/test_v511.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - The bash 3.2 comsub checker counts $(( )) inside $( ) as one paren level: y=$(case $a in (b) echo $((1));; esac) is a false positive, y=$(echo $((1+1)); case $a in b) :;; esac) a false negative; consume both closing parens and add the two samples
- **Verify:** `python3 kit/.uak/tests/test_v511.py --case the_dispatcher_parses_on_bash_3_2 --case merge_runs_the_main_checkouts_engine_not_the_branchs`
## UAK-016 · STATE.md in one pass: every mutation stops paying per task

- **Type:** feature
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-003
- **Paths:** kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_snapshot.py
- **Acceptance:** `snapshot` (kit/.uak/bin/lib/tx.sh, run by every mutation: heartbeat, claim, msg, done…) writes STATE.md with one awk pass over the task and claim records, not `$(field …)` per record and per state: on the 12-task fixture `uak heartbeat` starts about 90 fewer processes (152 → about 60), and the count no longer grows with the number of tasks, STATE.md is byte-identical to today's on the protocol fixtures: phases and freeze, every state's IDs (and the 120-char cut with "(N; last 12)"), AVAILABLE from the backlog, the first 24 claims with EXPIRED leases, the last 5 decisions, a record with CRLF, an ID or field with spaces, quotes or `$(…)` is written as text and runs nothing
- **Tests:** state_md_is_identical_to_before, heartbeat_does_not_grow_with_tasks, a_hostile_record_runs_nothing
- **Verify:** `python3 kit/.uak/tests/test_snapshot.py`
- **Next step:** the per-state `for record in "$TX"/tasks/*.md` loop of snapshot in kit/.uak/bin/lib/tx.sh
## UAK-017 · next shows every AVAILABLE task, even one an earlier task depends on

- **Type:** bug
- **Priority:** P0
- **Estimate:** 1 h
- **Depends on:** UAK-003
- **Paths:** kit/.uak/bin/uak-coordination, kit/.uak/tests/test_next_prefilter.py
- **Acceptance:** the prefilter awk of `coord_next` (kit/.uak/bin/uak-coordination) reads a dependency's state without creating its key (`(x in st) ? st[x] : ""`), so a task with no claims record stays a candidate when a task listed before it depends on it, on a fixture where A (listed first) depends on B and B has no record, `uak next` offers B, and says A waits on B (AVAILABLE), the other refusals are unchanged: a task with an un-integrated dependency still waits, and a CLAIMED, REVIEW, INTEGRATED or CANCELLED task is never offered
- **Tests:** a_dependency_listed_later_is_still_offered, the_dependent_still_waits, closed_tasks_are_never_offered
- **Verify:** `python3 kit/.uak/tests/test_next_prefilter.py`
- **Next step:** line 672 of kit/.uak/bin/uak-coordination: `st[x]` in the dependency loop
## UAK-018 · CI in about 7 minutes: the macOS and Linux suites in balanced shards

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** .github/workflows/test.yml, kit/.uak/bin/smoke, scripts/kit_lint.py, kit/.uak/tests/test_ci_shards.py
- **Acceptance:** measured on 4854882 (run 42310349789): the run takes 15.6 min, all of it waiting on `suite (macos-latest)`, which runs the 31 test files one after another (about 14.5 min of tests); Windows (one job per file) ends by 7 min, Linux at 6.5, `python3 scripts/kit_lint.py --ci-shards 4` prints the suite's shards as JSON: every discovered `kit/.uak/tests/test_*.py` in exactly one shard, balanced by each file's measured seconds on macOS (longest first); a file with no measured time counts 60 s, so a new test is never left out, only weighed by guess, the `suite` job runs per OS and shard (4 each): `smoke --package-only` with `UAK_SMOKE_TESTS` set to the shard's files runs only those; a name in it that is not a discovered test fails the shard (a typo never skips a test); without the variable smoke runs every test as today (the merge gate, a laptop), the checks that are not test files (gen_harness, kit_lint, kit_hashes, MCP tools, installer) run once per OS, in shard 1, kit_lint fails when the workflow's suite does not come from `--ci-shards` or smoke ignores `UAK_SMOKE_TESTS`, the CI run of this task's last commit takes under 9 minutes wall clock, every job green (the run's id and time in the done evidence)
- **Tests:** shards_cover_every_test_once, smoke_runs_only_its_shard, a_name_that_is_not_a_test_fails_the_shard
- **Verify:** `python3 kit/.uak/tests/test_ci_shards.py && python3 scripts/kit_lint.py`
- **Next step:** `ci_tests()` in scripts/kit_lint.py, then the test-file loop of kit/.uak/bin/smoke
## UAK-019 · plan's owner checks match claim's: no false "never claimed", and an amend checks only the Paths it adds

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/backlog.sh, kit/.uak/bin/lib/plan.sh, kit/.uak/tests/test_plan_owners.py
- **Acceptance:** `uak plan` no longer warns "can never be claimed" for a path whose OWNERS row belongs to a task already INTEGRATED: `owner_conflicts` (lib/backlog.sh) skips it as `check_owners` does for claim (black box, Nov 7: UAK-018 got the warning and claimed fine), it still warns for an owner that is not INTEGRATED and does not depend on the task, `plan FILE --amend` checks the other live claims only against the Paths the amend adds: an amend that keeps a task's Paths (only Depends or criteria change) passes while a claim sits under them (black box, Nov 6: UAK-006's Depends waited for UAK-008 to integrate); a newly added path that overlaps a live claim is still refused
- **Tests:** plan_does_not_warn_for_an_integrated_owner, plan_still_warns_for_a_live_owner, amend_with_the_same_paths_passes_a_live_claim, amend_adding_a_claimed_path_is_refused
- **Verify:** `python3 kit/.uak/tests/test_plan_owners.py`
- **Next step:** the `owner_waits_on_me` line of owner_conflicts in kit/.uak/bin/lib/backlog.sh

## UAK-020 · A review run in the author's worktree says where to review from

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/lib/review-merge.sh, kit/.uak/tests/test_review_identity.py
- **Acceptance:** when the worktree's .uak-env replaced the shell's UAK_AGENT and the resulting identity owns the task, `uak review ID` refuses as today ("The owner cannot approve their own task") and adds: this worktree's .uak-env names AGENT (the shell had X); review from the main checkout or your own clone (black box, Nov 6: the only way out a reviewer found was UAK_ENV_OVERRIDE), the refusal does not suggest UAK_ENV_OVERRIDE, the same review from the main checkout with UAK_AGENT=X is accepted as before
- **Tests:** review_in_the_authors_worktree_names_the_way_out, review_from_the_main_checkout_still_works
- **Verify:** `python3 kit/.uak/tests/test_review_identity.py`
- **Next step:** the .uak-env loop in kit/.uak/bin/uak, then the own-review conflict in kit/.uak/bin/lib/review-merge.sh

## UAK-021 · Windows-proof timing: a slow runner is measured twice, and the hook reads a CRLF epoch

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/tests/test_v592.py, kit/.uak/bin/hook, kit/.uak/tests/test_hook_claims.py
- **Acceptance:** test_v592's `a_long_heredoc_is_read_in_time` measures again when the first call is over its limit and fails only when both are (black box, Nov 6: 5.2 s once on a Windows runner, a commit that did not touch guard; the rerun passed); its assertion is unchanged, the hook's `fresh` reads an epoch followed by `\r` (a state file written with CRLF) as that epoch, instead of falling back to the file's mtime (black box, Nov 7: a CRLF seen file made the pace check never run)
- **Tests:** fresh_reads_a_crlf_epoch
- **Verify:** `python3 kit/.uak/tests/test_hook_claims.py && python3 kit/.uak/tests/test_v592.py --case a_long_heredoc_is_read_in_time`
- **Next step:** `fresh()` in kit/.uak/bin/hook
