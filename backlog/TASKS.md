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
## UAK-027 · CI installs the web/ dependencies before the product smoke

- **Type:** bug
- **Priority:** P0
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.github/workflows/uak.yml, kit/.uak/tests/test_ci_web_deps.py
- **Acceptance:** the team workflow gets a step before "Product smoke" that runs `npm ci --no-audit --no-fund` in every one of `.`, `web`, `frontend`, `client` that has a `package-lock.json` (pnpm-lock.yaml → `pnpm install --frozen-lockfile` via corepack; yarn.lock → `yarn install --frozen-lockfile`), skipped when none exists, why (DevDay hackathon, 2026-11-08): the smoke runs `npm --prefix web run build`; the runner had no web/node_modules, so main failed 9 times in a row and every PR with "sh: 1: tsc: not found" until the team patched the workflow by hand, a fresh sprint install into a repo with `web/package-lock.json` gets that step; the workflow stays valid YAML
- **Tests:** workflow_installs_web_deps_before_smoke, workflow_skips_install_without_a_lockfile
- **Verify:** `python3 kit/.uak/tests/test_ci_web_deps.py`
- **Next step:** the step after "Go toolchain" in kit/.github/workflows/uak.yml

## UAK-028 · The design gallery's page passes design-lint

- **Type:** bug
- **Priority:** P1
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/design-gallery, kit/.uak/tests/test_gallery_lint.py
- **Acceptance:** every color in the generated `design-lock/index.html` outside `:root` is a `var(--…)` token (today `kbd { color: #1d1f1c }`), so `design-lint` on a repo with tokens and a generated gallery prints DESIGN_LINT_PASS, why (DevDay hackathon): an agent's `done` was refused by design-lint for a hex in the kit's own gallery page
- **Tests:** generated_gallery_passes_design_lint
- **Verify:** `python3 kit/.uak/tests/test_gallery_lint.py`
- **Next step:** the kbd rule in the page template of kit/.uak/bin/design-gallery

## UAK-029 · `q` runs a Verify given as one string

- **Type:** bug
- **Priority:** P0
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/q, kit/.uak/tests/test_q_string.py
- **Acceptance:** `bash .uak/bin/q "cmd1 && cmd2"` (one argument with a space or shell operator) runs it with `bash -c`, so `&&`, `|`, quotes and redirections work and its exit code is the command's; several arguments keep running as `"$@"` exactly as today, why (DevDay hackathon): an agent passed the task's Verify quoted and got exit 127 (the whole string taken as a command name), the LOOP signature and the log path are unchanged for both forms
- **Tests:** a_quoted_compound_verify_runs, a_quoted_failing_verify_keeps_its_exit_code, argv_form_is_unchanged
- **Verify:** `python3 kit/.uak/tests/test_q_string.py`
- **Next step:** the `"$@" > "$log"` line of kit/.uak/bin/q

## UAK-030 · `done` and the design critic agree on the screenshot names

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.claude/agents/design-critic.md, kit/.uak/tests/test_ui_shot_names.py
- **Acceptance:** the UI gate accepts `1280.png` or exactly one `*-1280.png` (same for 390) in `.uak-shots/ID/`; with two candidates and no `1280.png` it refuses naming them and asking which is the main screen, design-critic.md says the main screen must be saved as `1280.png` and `390.png` and the critic checks those names exist before writing its verdict, why (DevDay hackathon): the critic approved `landing-1280.png` and `voz-1280.png`, then `done` refused twice for missing `1280.png`
- **Tests:** a_prefixed_main_shot_is_accepted, two_prefixed_shots_are_refused_by_name
- **Verify:** `python3 kit/.uak/tests/test_ui_shot_names.py`
- **Next step:** the `for f in 1280.png 390.png critic.txt` loop of ui_gate in kit/.uak/bin/lib/done.sh

## UAK-031 · A claim refused by the freeze says not to retry

- **Type:** bug
- **Priority:** P2
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak-coordination, kit/.uak/tests/test_freeze_claim.py
- **Acceptance:** the FREEZE refusal of `claim` ends with "Do not retry: the answer only changes when a human runs it. Take other work: uak next." and keeps UAK_CODE=freeze and the `uak allow` line, why (DevDay hackathon): one agent retried the same frozen claim 7 times
- **Tests:** freeze_claim_says_do_not_retry
- **Verify:** `python3 kit/.uak/tests/test_freeze_claim.py`
- **Next step:** the coord_freeze_allowed line of the claim command in kit/.uak/bin/uak-coordination

## UAK-032 · No git identity: wt and doctor say to set user.name and user.email

- **Type:** bug
- **Priority:** P1
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/wt, kit/.uak/bin/doctor, kit/.uak/tests/test_git_identity_msg.py
- **Acceptance:** on a machine with no `git config user.name`, `wt new ID` exits 2 with "git has no identity: git config --global user.name \"Your Name\" && git config --global user.email you@example.com", not "--human: letters, digits…", `doctor` reports a missing git user.name or user.email as a FAIL line with the same command, why (v6.0 review): a fresh laptop got a message about --human it never passed
- **Tests:** wt_new_without_git_identity_names_the_fix, doctor_flags_missing_git_identity
- **Verify:** `python3 kit/.uak/tests/test_git_identity_msg.py`
- **Next step:** where wt derives the human name from git config, before clean_id, in kit/.uak/bin/wt

## UAK-033 · A PR merged outside the gate can still be recorded, so claims match main

- **Type:** bug
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/uak-coordination, kit/.uak/docs/PROTOCOL.md, kit/.uak/tests/test_integrate_outside.py
- **Acceptance:** `uak integrate ID` records INTEGRATED when main already contains the task's work, in each case seen: a squash merge, a PR merged after more commits than the approved SHA, a task branch that carried unrelated base merges, and identical content that landed on main by another commit. The check compares the task's own diff (merge-base..tip, base merges dropped) by patch-id or by final file content on main, never the whole tree hash, a task still AVAILABLE or CLAIMED whose `feat/<id>` PR is merged (gh, or the branch tip reachable from main) can be recorded by its owner or a human; the record says `Integrated-Outside: yes` and the approval it had (or `none`), and `uak stats`/`dash` count it apart from gated merges, its dependents become claimable at once; its file reservations are released, why (deus-ex-machina, OpenAI x Kavak hackathon, 1st place, 2026-11-09): 11 `integrate` refusals ("tree hash does not match", "changes no task file", "is AVAILABLE, not REVIEW") and 5 agent reports. At the end claims said 6 of 23 integrated, with 6 stuck in REVIEW and 3 expired claims, while the product had shipped and won
- **Tests:** squash_merged_pr_is_recorded, pr_merged_after_extra_commits_is_recorded, base_merges_in_the_task_branch_are_ignored, equivalent_content_on_main_is_recorded, merged_branch_of_an_available_task_unblocks_its_dependents, outside_merges_are_counted_apart
- **Verify:** `python3 kit/.uak/tests/test_integrate_outside.py`
- **Next step:** the tree-hash comparison of the integrate path in kit/.uak/bin/lib/review-merge.sh

## UAK-034 · `status` and `next` see a task published with `uak plan` before its first claim

- **Type:** bug
- **Priority:** P0
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/backlog.sh, kit/.uak/tests/test_status_planned.py
- **Acceptance:** right after `uak plan FILE` (Plan-Channel: claims), `uak status ID` and `status --task ID` print the new task as AVAILABLE with its Paths, Verify and criteria (they come from claims:backlog/TASKS.md plus AMEND.md, as the transaction's canonical backlog does), on the read path that does not open a transaction too, why (both v6.0 events): "HACK-0xx is not in TASKS.md" 12 times, always minutes after a plan published that ID (DevDay HACK-037..041, deus HACK-017/019/021/022)
- **Tests:** status_shows_a_task_planned_on_claims, amended_task_shows_its_new_verify
- **Verify:** `python3 kit/.uak/tests/test_status_planned.py`
- **Next step:** the load_task fallback in the AVAILABLE branch of kit/.uak/bin/lib/status.sh

## UAK-035 · Work committed straight to main is stopped at commit time and counted

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.githooks/pre-commit, kit/.uak/bin/stats, kit/.uak/bin/doctor, kit/.uak/tests/test_direct_main.py
- **Acceptance:** in a repo with a backlog, a commit on the base branch in the main checkout is refused with "main takes work through tasks: bash .uak/bin/wt new ID (or a human: UAK_DIRECT_MAIN=1 git commit … for a hotfix)"; `uak merge`, `wt` and the kit's own commits are not affected, `uak stats` prints `Direct to main: N of M first-parent commits` (commits on main not reached through a task merge), and `doctor` warns when core.hooksPath is not the kit's (the hook would not run), why (deus-ex-machina): 120 of 155 first-parent commits on main came from agents working in the main checkout. The guard blocked one push to main, but the commits had already been made, so none of that work has a task, review, token attribution or a black box line
- **Tests:** commit_on_main_with_a_backlog_is_refused, hotfix_override_is_allowed_and_logged, uak_merge_still_commits, stats_counts_direct_commits
- **Verify:** `python3 kit/.uak/tests/test_direct_main.py`
- **Next step:** the branch check at the top of kit/.githooks/pre-commit

## UAK-036 · Token spend: every machine reports it, and the main checkout's share is visible

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/tokens, kit/.uak/bin/hook, kit/.uak/bin/lib/status.sh, kit/.uak/tests/test_tokens_coverage.py
- **Acceptance:** besides the Claude Code Stop hook, `tokens --publish` also runs from session-start (for the previous sessions) and from the Codex hooks, and a failed publish writes one black box line with the reason instead of failing silently in the background, `uak tokens --team` lists the machines that worked (hosts of task worktrees, black box files) but never published: `NOT REPORTED: 2 machines (worktrees under /Users/…/orca, …)`; status's Tokens line says `from 1 of 3 machines`, the spend of sessions in the main checkout is shown as `main (coordination and work outside tasks) NN%`, with a warning above 50 %, why (both events): deus published tokens from 1 of 3 Macs (185 M tokens, 100 % "main"); DevDay 406 M with 78 % "main", one coordinator session alone 178 M cache reads. Per-task cost could not be measured
- **Tests:** publish_failure_is_recorded, team_view_names_machines_that_never_reported, main_share_is_reported_and_warned
- **Verify:** `python3 kit/.uak/tests/test_tokens_coverage.py`
- **Next step:** the publish call at the end of the session-start branch of kit/.uak/bin/hook

## UAK-037 · A gitleaks finding has its own way out

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/secret-scan, kit/.uak/bin/lib/security.sh, kit/.uak/tests/test_gitleaks_exception.py
- **Acceptance:** when the finding comes from gitleaks (SECRET_EXTERNAL), the message points to its fingerprint and to `uak secret-exception ID --fingerprint FP --reason TEXT`, which secret-scan honors through a `.gitleaksignore` entry; the kit's own rules keep `--path --rule`. The scan stays on, why (deus-ex-machina): smoke flagged fixture history through gitleaks and suggested secret-exception, which refuses rules that are not the kit's
- **Tests:** gitleaks_finding_names_its_fingerprint, fingerprint_exception_clears_only_that_finding
- **Verify:** `python3 kit/.uak/tests/test_gitleaks_exception.py`
- **Next step:** the SECRET_EXTERNAL branch of kit/.uak/bin/secret-scan

## UAK-038 · Registered reviewers get the review work first

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/wait.sh, kit/.uak/tests/test_reviewer_next.py
- **Acceptance:** for an identity registered as reviewer (or with no live claim and reviews pending), `uak next` offers every REVIEW task it may review before any coding task; `uak wait --for message` also wakes when a task enters REVIEW that it may review, `uak status ID --summary` works like `status --task ID --summary`, why (DevDay): a review-only Codex agent missed a REVIEW task because next offered coding work and wait did not wake it; Codex hit "--summary needs --task ID" 3 times in deus
- **Tests:** reviewer_next_offers_review_first, wait_wakes_on_new_review_work, status_id_summary_works
- **Verify:** `python3 kit/.uak/tests/test_reviewer_next.py`
- **Next step:** the candidate order of uak_next in kit/.uak/bin/lib/status.sh

## UAK-039 · A metric that was not measured is null, never 0

- **Type:** docs
- **Priority:** P2
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** kit/.uak/modes/sprint.md, kit/.uak/docs/WHY.md
- **Acceptance:** sprint.md, a new rule next to the demo rules: cost, tokens, latency or any score that was not instrumented is written as `null` with "not measured", never 0, and the pitch says which measures are real, why (deus-ex-machina): the eval runs recorded 0 cost and tokens; the team had to add a warning to its submission that "the zeros are not a measurement"
- **Verify:** `grep -q "never 0" kit/.uak/modes/sprint.md`
- **Next step:** the demo rules of kit/.uak/modes/sprint.md

## UAK-040 · The `/uak-*` phase commands exist natively in Codex, Cursor and Gemini CLI

- **Type:** bug
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.claude/commands/, kit/.uak/skills/, install.sh, scripts/gen_harness.py, kit/AGENTS.md, kit/.uak/docs/CLI.md, kit/.uak/tests/test_harness_commands.py
- **Acceptance:** the 13 phase scripts (uak-setup, uak-plan, uak-ship, uak-review, uak-handoff, uak-demo, …) come from one source and reach every harness the team installed:, Claude Code: `/uak-X`, as today;, Codex: an Agent Skill under `.agents/skills/uak-X/SKILL.md`, invoked as `$uak-X` or from `/skills` (Codex deprecated custom prompts);, Cursor: `/uak-X`, as a skill or from `.cursor/commands/uak-X.md`;, Gemini CLI: `/uak-X`, as a skill from `.agents/skills` or from `.gemini/commands/uak-X.toml`, a skill made from a phase script is only run when asked (`disable-model-invocation: true` or the harness's equivalent), so no agent starts `/uak-demo` on its own; Claude Code shows no duplicate `/uak-X`, `gen_harness.py --check` fails when a generated copy is stale (CI already runs it); the AGENTS.md line "Codex, Cursor, Gemini: `/uak-X` means follow `.claude/commands/uak-X.md`" changes to the native call, why (user's teammate, 2026-11-10): in Codex and Cursor the kit's commands "were not up to date". Codex and Cursor had no `/uak-*` at all, and Codex no longer reads custom prompts
- **Tests:** every_phase_command_reaches_every_harness, phase_skills_are_not_model_invoked, generated_commands_match_their_source
- **Verify:** `python3 kit/.uak/tests/test_harness_commands.py`
- **Next step:** the command → skill writer in scripts/gen_harness.py

## UAK-041 · Skills work on a Windows clone and in a Gemini-only install

- **Type:** bug
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** UAK-040
- **Paths:** install.sh, kit/.uak/bin/doctor, kit/.uak/bin/start, kit/.uak/tests/test_skills_windows_clone.py
- **Acceptance:** a teammate who clones on Windows (Git for Windows has `core.symlinks=false` by default) a repo installed on macOS or Linux gets working skills in Codex, Cursor and Gemini. Today `.agents/skills` and `.cursor/skills` are committed as symlinks (mode 120000), so that clone checks them out as one-line text files and the skills disappear, the reverse also works: a repo installed on Windows (where the installer copies the folder) does not leave stale copies for Mac and Linux teammates after `--update`, `doctor` flags `.agents/skills` or `.cursor/skills` when it is a file or a stale copy, with the exact fix; `doctor --fix` (or `uak start`) repairs it, `--harness gemini` without codex still gets the skills (Gemini reads `.agents/skills`; today only codex installs it), why (DevDay and deus-ex-machina, both v6.0.0): both repos commit those links as symlinks, and DevDay had a Codex teammate on Windows whose black box line only said "PowerShell"
- **Tests:** windows_clone_without_symlinks_has_skills, doctor_flags_a_symlink_checked_out_as_a_file, gemini_only_install_gets_skills, update_refreshes_copied_skills
- **Verify:** `python3 kit/.uak/tests/test_skills_windows_clone.py`
- **Next step:** the `.agents/skills .cursor/skills` loop in install.sh

## UAK-042 · Subagent model IDs checked against the harnesses' current docs

- **Type:** chore
- **Priority:** P2
- **Estimate:** 45 min
- **Depends on:** UAK-040
- **Paths:** scripts/gen_harness.py, kit/.codex/agents/, kit/.cursor/agents/, kit/.gemini/agents/, kit/.uak/docs/ORCHESTRATION.md
- **Acceptance:** the TIERS table (codex gpt-6-luna / gpt-6.1-sol / gpt-6-astra, cursor composer-2.5, gemini 3 preview IDs; last verified 2026-10-09) is checked against the official model pages of OpenAI, Cursor and Google, and every ID is one the harness accepts today; the date and sources in the docstring are updated; regenerated files pass `gen_harness.py --check`, why: the Gemini 3.1 and 3.5 IDs exist now, while the kit still pins the 3.0 previews
- **Verify:** `python3 scripts/gen_harness.py --check`
- **Next step:** the TIERS table in scripts/gen_harness.py

## UAK-043 · tokens publish: no race with an explicit publish; the Codex tick publishes on Windows (follow-up of UAK-036)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-036
- **Follow-up of:** UAK-036
- **Paths:** kit/.uak/bin/tokens, kit/.uak/bin/hook, kit/.uak/bin/lib/status.sh, kit/.uak/tests/test_tokens_coverage.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - tokens publish: no race with an explicit publish; the Codex tick publishes on Windows
- **Verify:** `python3 kit/.uak/tests/test_tokens_coverage.py`

## UAK-044 · gitleaks exceptions combine with .gitleaksignore on Windows (follow-up of UAK-037)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-037
- **Follow-up of:** UAK-037
- **Paths:** kit/.uak/bin/secret-scan, kit/.uak/bin/lib/security.sh, kit/.uak/bin/uak, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_gitleaks_exception.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - gitleaks exceptions combine with .gitleaksignore on Windows
- **Verify:** `python3 kit/.uak/tests/test_gitleaks_exception.py`
## UAK-045 · An unapproved task matched by one file is not recorded as integrated without a human

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/done.sh, kit/.uak/tests/test_integrate_outside.py
- **Acceptance:** `uak integrate ID` on the outside path, when the task has no approval (`Approval: none`) and its own commits change exactly one file, is refused for an agent with "only one file matched main and nobody approved it: a human records it (UAK_HUMAN=NAME uak integrate ID)"; a human may record it; two or more matching files, or any approval, behave as in v6.1.0, why (v6.1.0 review of UAK-033): a one-file task whose content equals main by coincidence would be credited as integrated
- **Tests:** single_file_unapproved_match_needs_a_human, single_file_match_with_approval_is_recorded
- **Verify:** `python3 kit/.uak/tests/test_integrate_outside.py`
- **Next step:** integrated_outside_check in kit/.uak/bin/lib/review-merge.sh

## UAK-046 · doctor compares skill copies without `diff --strip-trailing-cr`

- **Type:** bug
- **Priority:** P1
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/doctor, kit/.uak/tests/test_doctor_skills_compare.py
- **Acceptance:** the stale-copy check of `.agents/skills` against `.claude/skills` uses only POSIX tools (e.g. `tr -d '\r' | cksum` per file, or one awk pass), so it gives the same answer on macOS before 13 (BSD diff without `--strip-trailing-cr`), Linux and Git Bash; CRLF-only differences are not stale, why (v6.1.0 review of UAK-041): on an older Mac every doctor run would call the skills stale
- **Tests:** crlf_only_difference_is_not_stale, real_difference_is_stale, works_without_diff_strip_flag
- **Verify:** `python3 kit/.uak/tests/test_doctor_skills_compare.py`
- **Next step:** the `diff -r -q --strip-trailing-cr` call in kit/.uak/bin/doctor

## UAK-047 · install keeps a team's edited copy of a kit skill in .cursor/skills

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/tests/test_cursor_skills_keep.py
- **Acceptance:** install/--update removes a skill folder from `.cursor/skills` only when its files equal a version the kit shipped (known-files.txt hashes, as the rest of --update decides); an edited copy stays, and install prints "kept .cursor/skills/NAME: edited by the team; Cursor also reads .agents/skills", why (v6.1.0 review of UAK-041): an edited kit skill in .cursor/skills was deleted because only its name was compared
- **Tests:** unedited_kit_skill_copy_is_removed, edited_kit_skill_copy_is_kept_and_named
- **Verify:** `python3 kit/.uak/tests/test_cursor_skills_keep.py`
- **Next step:** the .cursor/skills cleanup in install.sh

## UAK-048 · Cursor model IDs from Cursor's official pages

- **Type:** chore
- **Priority:** P2
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** scripts/gen_harness.py, kit/.cursor/agents/, kit/.uak/docs/ORCHESTRATION.md
- **Acceptance:** the Cursor strong and fast IDs (`claude-opus-5-5[effort=high]`, `composer-2.5`) are checked against cursor.com/docs/models and cursor.com/docs/subagents; each is replaced only by an ID those pages show; the standard (not fast) variant is chosen where the syntax allows (`composer-2.5[]` if that is the documented way); sources and date in the docstring; `gen_harness.py --check` green, why (v6.1.0 review of UAK-042): neither ID appears verbatim in Cursor's docs
- **Verify:** `python3 scripts/gen_harness.py --check`
- **Next step:** the cursor column of TIERS in scripts/gen_harness.py

## UAK-049 · A refused `wt new` leaves no unused identity

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/wt, kit/.uak/tests/test_wt_refused_identity.py
- **Acceptance:** when the claim of `wt new ID` is refused (overlap, dependency, freeze, owners), no new identity is registered on claims and no branch or worktree is left; a retry after the blocker clears picks the same free identity, why (v6.1.0 session): refused claims created joahanmorales-6, -7, -9 and -11, which never held a task
- **Tests:** refused_claim_registers_no_identity, retry_reuses_the_free_identity
- **Verify:** `python3 kit/.uak/tests/test_wt_refused_identity.py`
- **Next step:** the identity registration before the claim in kit/.uak/bin/wt

## UAK-050 · `plan --amend` checks overlaps the way claims do

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/plan.sh, kit/.uak/tests/test_plan_amend_overlap.py
- **Acceptance:** amending a task that holds no reservation (AVAILABLE) never fails on overlap: it prints "UAK-NNN's new Paths overlap UAK-MMM (CLAIMED/REVIEW): its claim will wait for it" and publishes; the claim gate still refuses the overlapping claim later, amending several tasks in one file checks each task against the others' NEW Paths (an amend that drops a file from one task frees it for another in the same file), a CLAIMED or REVIEW task whose new Paths overlap another live claim is still refused, as today, why (v6.1.0 session): the human had to run four amends in a fixed order; UAK-038 (AVAILABLE) was refused twice for tasks only waiting for review
- **Tests:** available_task_amend_overlap_warns_and_publishes, one_file_amend_uses_the_new_paths_of_the_others, claimed_task_amend_overlap_is_still_refused
- **Verify:** `python3 kit/.uak/tests/test_plan_amend_overlap.py`
- **Next step:** the overlap check of plan_amend_mutate in kit/.uak/bin/lib/plan.sh

## UAK-051 · `uak lint` warns when a task's own words point outside its Paths

- **Type:** feature
- **Priority:** P2
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/lint.sh, kit/.uak/tests/test_lint_paths_hint.py
- **Acceptance:** for each backlog task, a file path or a function name in its `Next step:` or Acceptance that the code map places in a file outside its Paths gives `LINT WARNING: UAK-NNN mentions coord_next (kit/.uak/bin/uak-coordination), outside its Paths`; plan files get the same warning before publishing (`uak plan FILE` prints it, never fails on it), no map yet → silent; at most 5 warnings per task, why (v6.1.0 session): 4 of 16 tasks needed a Paths amend because the function they changed lived in another file
- **Tests:** next_step_function_outside_paths_warns, mention_inside_paths_is_silent
- **Verify:** `python3 kit/.uak/tests/test_lint_paths_hint.py`
- **Next step:** a new lint_paths_hint next to lint_tests_named in kit/.uak/bin/lib/lint.sh

## UAK-052 · The merge gate can run only the affected tests, CI runs the rest

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-045
- **Paths:** kit/.uak/bin/smoke, kit/.uak/bin/lib/review-merge.sh, kit/.uak/docs/PROTOCOL.md, kit/.uak/tests/test_merge_affected.py
- **Acceptance:** with `Merge-Smoke: affected` in PROJECT.md, `uak merge` runs kit_lint (or the project's smoke) + the task's Verify + the test files that name a changed file or were changed themselves, instead of the whole suite; default stays `full`; the merge record says which (`Smoke: affected 7 of 52 test files`), with `affected`, a merge whose diff touches the engine's shared files (lib/core.sh, lib/tx.sh, uak-coordination) still runs the whole suite, after it merges, the human may set `Merge-Smoke: affected` in the kit repo's .uak/PROJECT.md (CI still runs every test on every push), why (v6.1.0 session): each `uak merge` ran the full suite on the maintainer's machine, over 10 minutes per task
- **Tests:** affected_mode_runs_only_matching_tests, engine_core_change_runs_everything, default_is_full
- **Verify:** `python3 kit/.uak/tests/test_merge_affected.py`
- **Next step:** the smoke call in the merge gate of kit/.uak/bin/lib/review-merge.sh

## UAK-053 · One canonical-backlog builder, and status from any clone

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak-coordination, kit/.uak/bin/lib/backlog.sh, kit/.uak/tests/test_status_planned.py
- **Acceptance:** coord_init calls backlog_canonical (lib/backlog.sh) instead of its own copy; claims_diff shows 0 differences, `uak status ID` for a task published with `uak plan` prints its Paths and Verify from a fresh clone at an older commit of main too (the reviewer saw "not in TASKS.md" from its clone four times); if it cannot, the message says which backlog it read and how to refresh, why (v6.1.0 review of UAK-034 and the reviewer's notes)
- **Tests:** status_from_an_old_clone_shows_a_planned_task
- **Verify:** `python3 kit/.uak/tests/test_status_planned.py`
- **Next step:** the builder in coord_init of kit/.uak/bin/uak-coordination
## UAK-054 · The merge gate runs the full suite in parallel shards on the local machine

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/smoke, kit/.uak/docs/PROTOCOL.md, kit/.uak/tests/test_smoke_parallel.py
- **Acceptance:** `bash .uak/bin/smoke --package-only --jobs N` (and `Smoke-Jobs: N` in PROJECT.md, read by the gate's smoke) runs the suite's test files in N balanced shards at once, the same split CI uses (`UAK_SMOKE_TESTS` per shard, balanced by the timings test_ci_shards already knows), and fails if any shard fails, printing each failing shard's tail; default 1 (today's behaviour), every shard gets its own TMPDIR and HOME-like scratch so tests cannot collide; the result is identical to a serial run on the kit's suite (same PASS/FAIL set), `--jobs auto` uses the CPU count minus one, at most 4, why (v6.1.0 and v6.1.1): every `uak merge` on the maintainer's machine ran the whole suite serially, over 10 minutes per task; `Merge-Smoke: affected` cannot help the kit itself because almost every task touches `.uak/bin/`
- **Tests:** jobs_split_runs_every_file_once, a_failing_shard_fails_the_run, default_is_serial
- **Verify:** `python3 kit/.uak/tests/test_smoke_parallel.py`
- **Next step:** the test-file loop of the package mode in kit/.uak/bin/smoke
## UAK-055 · The installer brings the MotionSites web-builder skill, pinned and verified, never vendored

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/settings/external-skills.tsv, kit/.uak/bin/doctor, kit/.uak/tests/test_external_skills.py
- **Acceptance:** `kit/.uak/settings/external-skills.tsv` lists external skills as `name<TAB>repo URL<TAB>commit SHA<TAB>subfolder<TAB>tree SHA`; its first row is `motionsites-web-builder`, https://github.com/Motionsites-AI/claude-skill.git, commit faa30d512e3973e58675c72101a7ef42ed37ae83, `plugins/motionsites-web-builder/skills/motionsites-web-builder`, tree fcab79cb38339708d406c475268172259f2765e7, install.sh (fresh install and `--update`) fetches each row with git only (`git init` + `git fetch --depth 1 origin <commit>` in a temp dir; no curl, no jq), checks `git rev-parse <commit>:<subfolder>` equals the pinned tree SHA, and copies the subfolder to `.claude/skills/<name>` and `.agents/skills/<name>`; a mismatch installs nothing and says so, no network, a refused fetch or a missing git never fails the install: one line `external skill <name> not installed: <reason>; landings use landing-story alone` and exit 0, the skill is never committed into the kit repo: its examples and media are © MotionSites and may not be redistributed as a collection (its LICENSE §2); a kit_lint-style check in the test fails if `kit/` contains a file from that skill, `uak doctor` prints `external skills: motionsites-web-builder ok (faa30d5)` or what is missing and the command that installs it (`bash .uak/bin/uak start --update` or the install line), Windows (Git Bash) and macOS (bash 3.2) paths: the temp dir comes from `mktemp -d` with a fallback, and is removed on every exit path
- **Tests:** fetch_pinned_skill_installs_both_harness_dirs, tree_mismatch_installs_nothing, offline_install_still_succeeds, kit_never_contains_external_skill_files, doctor_reports_external_skill
- **Verify:** `python3 kit/.uak/tests/test_external_skills.py`
- **Next step:** the skills loop near `for s in $skills; do putdir` in install.sh (tests use a local bare repo as the remote, never the network)

## UAK-056 · landing-story builds every landing with the MotionSites workflow, and the skills stop asking for "bigger"

- **Type:** feature
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/skills/landing-story/SKILL.md, kit/.uak/skills/product-ui/SKILL.md, kit/.uak/tests/test_landing_skills.py
- **Acceptance:** landing-story keeps what it owns (the story beats from IDEA.md, numbers with sources, the real product wow) and, when `.claude/skills/motionsites-web-builder` exists, builds the page with that skill's steps 2–6: read the 2–3 closest examples, get real media (the team's own assets first, then generated, then its media shelf), write the precise spec from its template, build, then its look-and-fix loop with `scripts/shoot.py` until its rubric averages 8+ with nothing under 7, or 3 rounds, without that skill, the same order with the kit's own tools (webapp-testing screenshots), so a landing is never delivered unseen, scale bounds from the F0 catalog (docs/design/failures.md): hero display at most 96 px at 1280 and 48 px at 390, body 16–18 px, primary buttons 40–52 px tall, at most 6 palette colors besides media; "mega type" in vw only when the human picked it in a round. Why (F0, 2026-11-11): the two landings scored 1 and "giant" had 168 and 207 px display type; the one scored 5 topped out at 36 px, the line that asks for "bigger type, the brand color at full strength" (landing-story) and the self-checks "Is the hero the biggest and most colorful thing?" / "the most saturated thing on screen" (product-ui) are replaced by "Is the hero the most important thing, and does it read in 3 seconds at 1280 and 390?", the landing starts from material: the team's logo, mascot, photos, the real map or the product's own screen; if there is none, the agent asks the human for one before designing (one line) and goes on with generated or shelf media if nobody answers in 10 min, in kit runs the MotionSites promotional block and nudges are not shown (the kit's human asked; the skill's own rule allows it): one line in landing-story says so
- **Tests:** landing_story_uses_motionsites_steps_when_present, landing_story_falls_back_to_kit_screenshots, scale_bounds_are_stated, no_bigger_type_instruction_left, product_ui_hero_check_is_importance_not_size, no_promo_line_present
- **Verify:** `python3 kit/.uak/tests/test_landing_skills.py`
- **Next step:** the "## 1. Structure" and craft sections of kit/.uak/skills/landing-story/SKILL.md

## UAK-057 · `uak design round`: a landing tournament round with a design genome per variant

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/design, kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/commands.tsv, kit/.uak/tests/test_design_round.py
- **Acceptance:** `bash .uak/bin/uak design round [--screen landing] [--n N] [--seed S]` (default landing, N 8, max 20) creates `.uak/design/rounds/R<k>/` with `brief.md` (the landing's story beats pulled from IDEA.md: one line, proof number with source, wow, steps, users, ask; a missing beat is listed as missing, never invented) and `v<i>/genome.json` for each variant, a genome has 8 genes, each with a fixed list of values: type (grotesk, geometric, serif display, mono-led, rounded, condensed), scale (restrained, standard, bold; all inside the F0 bounds), color (ink + one accent, brand duo, dark media, light paper, saturated field), layout (split hero, full-bleed media, editorial column, product screen first, scroll story), components (hairline, solid blocks, glass, soft), imagery (product screenshot, video loop, 3D cut-out, illustration, type only), motion (still, entrance, scroll, pointer), voice (plain, bold claim, numbers first); plus a recipe (motionsites when installed, landing-story, frontend-design, design-taste-frontend) rotated across variants, no two variants of a round share more than 3 genes; the same seed gives the same round; values are spread so each gene's values appear before any repeats, each `v<i>/TASK.md` is the instruction an agent follows to build that variant as `v<i>/index.html` (static, one file, same brief and content in every variant, only the design changes), then capture `v<i>/1280.png` (1280×720 and full page) and `v<i>/390.png`, before writing anything it prints the cost: N variants × the per-variant token estimate from `Design-Variant-Tokens:` in PROJECT.md (default 60k) and the model tier, and asks for `--yes` (or the human runs it); `--dry-run` prints the genomes only, `uak design shoot R<k>` captures any variant whose PNGs are missing (playwright via the webapp-testing skill's helper or MotionSites `scripts/shoot.py`, whichever is installed) and lists what it could not capture
- **Tests:** round_writes_brief_and_genomes, no_two_variants_share_more_than_three_genes, same_seed_same_round, missing_beat_is_listed_not_invented, cost_is_printed_and_needs_yes, shoot_reports_missing_captures
- **Verify:** `python3 kit/.uak/tests/test_design_round.py`
- **Next step:** a new `design` row in kit/.uak/bin/lib/commands.tsv beside `design-gallery`

## UAK-058 · `uak design pick`: the human picks K of N in the browser and the picks are saved

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2.5 h
- **Depends on:** UAK-057
- **Paths:** kit/.uak/bin/design-gallery, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_pick.py
- **Acceptance:** `bash .uak/bin/uak design pick R<k> [--k 3]` (or `design-gallery --round R<k>`) opens one page with every variant at 1280 and 390 (same open/serve/Tailscale/ssh -L behaviour as design-gallery today), the genome of each under it, keyboard picking (number keys or arrows + space), a one-line note per pick and an optional note per variant, saving writes `R<k>/picks.json` (`{picked: [ids in order], notes: {id: text}, by, at}`) through a tiny local server bound to 127.0.0.1 and the Tailscale address only; the page shows "Saved" only after the server answered, picking more or fewer than K is allowed with a warning; a second save replaces the first, over SSH it prints the URLs and returns, like design-gallery --serve; `--stop` ends the server, no network calls from the page (fonts and scripts inline or none)
- **Tests:** pick_page_lists_every_variant, save_writes_picks_json, wrong_count_warns_but_saves, server_binds_local_only
- **Verify:** `python3 kit/.uak/tests/test_design_pick.py`
- **Next step:** the HTML writer in kit/.uak/bin/design-gallery (cards loop) and a `--round` branch beside `--serve`

## UAK-059 · `uak design round --from R<k>`: the next round is bred from the human's picks

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-057, UAK-058
- **Paths:** kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_breed.py
- **Acceptance:** from `R<k>/picks.json`: about half the new variants are one-gene mutations of a pick, about a third are crossovers of two picks (genes taken from each), and 2 are wildcards with no pick's genes; the "max 3 shared genes" rule still holds inside the new round, every new genome.json records its parents and what changed (`"from": ["R1/v3"], "mutated": "color"`), the human's notes travel into each child's TASK.md ("keep this type", "hate the color"), the stop rule: when the human's first pick is a child of the previous first pick with the same genome for two rounds, `uak design round --from` says the direction has converged and prints the `uak design lock R<k>/v<i>` command instead of breeding
- **Tests:** children_follow_mutation_crossover_wildcard_mix, parents_recorded, notes_reach_children, converged_round_stops
- **Verify:** `python3 kit/.uak/tests/test_design_breed.py`
- **Next step:** reuse the genome lists and the shared-gene check from kit/.uak/bin/lib/design_round.py (import, do not copy)

## UAK-060 · Every sprint's design lock starts with a landing round the human picks from

- **Type:** feature
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** UAK-056, UAK-057, UAK-058
- **Paths:** kit/.claude/commands/uak-design-lock.md, kit/.gemini/commands/uak-design-lock.toml, kit/.agents/skills/uak-design-lock/SKILL.md, kit/.agents/skills/uak-design-lock/agents/openai.yaml, kit/.uak/tests/test_design_lock_round.py
- **Acceptance:** `/uak-design-lock` step 2–4 become: `uak design round --screen landing --n 6` (8 when the event is 24 h or more), one agent per variant in parallel, `uak design shoot`, `uak design pick --k 2`; then one bred round of 4 from the picks; the human's final pick becomes the direction, and its genome fills DESIGN.md (type, scale, color, components, motion), events under 6 h: one round of 4, no breeding, the landing is built for real in the first hours (landing-story), not left for the last hour; the app screens copy the locked direction as today, the generated harness files come from `python3 scripts/gen_harness.py` (never edited by hand) and `gen_harness.py --check` passes
- **Tests:** design_lock_runs_a_landing_round, short_event_single_round, generated_harness_matches
- **Verify:** `python3 kit/.uak/tests/test_design_lock_round.py && python3 scripts/gen_harness.py --check`
- **Next step:** steps 2–4 of kit/.claude/commands/uak-design-lock.md

## UAK-061 · design-lint flags oversized type and controls (the F0 failure no gate caught)

- **Type:** feature
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/design-lint, kit/.uak/tests/test_design_lint_scale.py
- **Acceptance:** design-lint warns on a CSS/TSX font size above 96 px (px, rem at 16, Tailwind `text-[...]` and `text-8xl`/`text-9xl`, and the max of a `clamp()`), on vw font sizes above 12vw, and on a button/input height above 56 px; each warning names file:line and the F0 bound, a deliberate exception carries `design-lint: ok <reason>` on the line, like the existing checks, warnings, not failures, so a hackathon is never blocked by them; `--strict` makes them fail
- **Tests:** px_rem_and_tailwind_sizes_over_bound_warn, clamp_max_counts, vw_over_bound_warns, ok_comment_silences, strict_fails
- **Verify:** `python3 kit/.uak/tests/test_design_lint_scale.py`
- **Next step:** the check list in kit/.uak/bin/design-lint (after the raw palette check)
## UAK-062 · A taste profile learned from every pick, kept per human across projects

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/design_taste.py, kit/.uak/tests/test_design_taste.py
- **Acceptance:** `design_taste.update(project_root, human)` reads every round of the project (`.uak/design/rounds/R*/genome.json` + `picks.json`) and folds it into `~/.uak/taste/<human>.json` (`UAK_TASTE_HOME` overrides the folder): per gene value, how often it was shown, picked first, picked, and never picked; the human's notes per gene value; and the project's final direction (the last converged or final pick) with its genome, project name and date, the profile stores traits, not templates: weights per gene value (Laplace-smoothed picked/shown), never a palette's hex values or a whole page; the final genomes are kept only as "past directions" for novelty (UAK-063), idempotent: folding the same round twice changes nothing (each round is keyed by project + round id), `design_taste.show(human)` prints, per gene, the values from most to least liked with counts, and the past directions, in under 40 lines, a profile with fewer than 10 picks says it is still learning (`confidence: low`) so rounds keep exploring, Why (v6.2, the human): once a genome wins, every project must not come out the same; the kit learns what the human likes, not what one page looked like
- **Tests:** folds_picks_into_weights, folding_twice_is_idempotent, stores_traits_not_hex, past_directions_recorded, low_confidence_under_ten_picks
- **Verify:** `python3 kit/.uak/tests/test_design_taste.py`
- **Next step:** read genome.json / picks.json the way kit/.uak/bin/lib/design_breed.py does (import its readers, do not copy)

## UAK-063 · Round 1 of a new project is seeded by taste, shaped by the project, and never repeats a past direction

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-062
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_round_taste.py
- **Acceptance:** `uak design round` (first round of a project) draws gene values weighted by the human's profile (`--human NAME`, default `UAK_HUMAN`, then git user.name): liked values are more likely, never certain; with `confidence: low` or no profile it draws as today, exploration stays: at least 2 variants per round (1 when N ≤ 4) ignore the profile entirely (wildcards), and the ≤ 3 shared genes rule still holds, novelty: no variant shares more than 5 of the 8 genes with any past direction in the profile (another project's winner), so a new project never starts as a copy of the last one; `--allow-repeat` lifts it, the project shapes the round, not only the profile: (a) the default seed comes from the project's name, not 1; (b) the color gene gets the project's own brand colors when they exist (hex values in IDEA.md §0, CSS custom properties under web/, fills in SVGs under assets/ or web/public/), written into brief.md as "Brand colors (from the project)"; (c) the imagery gene prefers what the project really has (real product screens, photos, video, a map, a mascot) — values with no material behind them are drawn less; (d) brief.md gets a "Subject world" beat: the agent building each variant lists 3–5 concrete things from the project's domain (its objects, instruments, units, local vernacular) and uses at least one as a visual element, each genome.json records why each gene was chosen (`"why": {"color": "brand duo · project colors #0367FC #0B1020", "type": "taste 0.71", "layout": "wildcard"}`) so the human can see what the kit learned, the cost line and `--dry-run` show how many variants come from taste, wildcards and novelty constraints
- **Tests:** liked_values_drawn_more_often, wildcards_ignore_taste, never_repeats_a_past_direction, seed_comes_from_project_name, project_colors_reach_the_brief, imagery_follows_available_material, why_is_recorded
- **Verify:** `python3 kit/.uak/tests/test_design_round_taste.py && python3 kit/.uak/tests/test_design_round.py`
- **Next step:** `make_genomes` in kit/.uak/bin/lib/design_round.py (add an optional weights/constraints argument; keep its signature compatible for design_breed.py)

## UAK-064 · `uak design taste`: update and show the profile; the pick saves feed it

- **Type:** feature
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** UAK-062
- **Paths:** kit/.uak/bin/design, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_design_taste_cli.py
- **Acceptance:** `bash .uak/bin/uak design taste [--human NAME]` prints the profile (design_taste.show); `uak design taste --update` folds the current project's rounds, a save in `uak design pick` folds that round into the picker's profile right away (the name typed on the page, else UAK_HUMAN); a failure to write the profile never fails the save, it is reported on the page, `uak design taste --forget PROJECT` drops one project's rounds and direction from the profile (the human may want a fresh start), CLI.md regenerated by scripts/gen_registry.py
- **Tests:** taste_command_prints_profile, pick_save_updates_profile, forget_drops_a_project
- **Verify:** `python3 kit/.uak/tests/test_design_taste_cli.py`
- **Next step:** the `pick` branch of kit/.uak/bin/design and the save handler in kit/.uak/bin/lib/gallery_pick.py

## UAK-065 · Bred rounds read the human's notes: mutate what the note names, and never send wildcards into rejected genes

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_breed_notes.py
- **Acceptance:** a pick's note that names a gene ("colores", "color", "fondo", "background" → color; "tipografía", "letra", "font" → type; "espacio", "acomodación", "layout", "flujo" → layout; "animación", "movimiento" → motion; "formal", "divertida", "tono" → voice; Spanish and English) makes that gene the one mutated for that parent's children; with no named gene it stays random, a variant the human did not pick and whose note is negative ("no me gustó", "la peor", "lastiman", "feo", "hate", "ugly") marks its gene values as rejected for the next round: wildcards may not use them; when the "no pick's value" rule leaves only rejected values for a gene, the wildcard takes a picked value instead (it is still a wildcard on the other genes), each child's genome.json records `"because": "note on R1/v6: el fondo debería ser completamente blanco → color"` when a note chose the gene, Why (AXIA R2, 2026-11-11): the human picked 3 and annotated all 6, but breeding mutated scale where the note asked for colors, and both wildcards fell on the saturated blue fields the human said "hurt the eyes"; the lead had to search seeds and override two genes by hand
- **Tests:** note_naming_color_mutates_color, rejected_values_never_reach_wildcards, wildcard_falls_back_to_a_picked_value, because_is_recorded
- **Verify:** `python3 kit/.uak/tests/test_design_breed_notes.py && python3 kit/.uak/tests/test_design_breed.py`
- **Next step:** the mutation and wildcard choice in kit/.uak/bin/lib/design_breed.py

## UAK-066 · design-lint checks a round's static variants (tokens inside the page's <style>)

- **Type:** bug
- **Priority:** P2
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/design-lint, kit/.uak/tests/test_design_lint_html.py
- **Acceptance:** tokens (CSS custom properties) inside an .html file's <style> count as design tokens, so design-lint no longer prints DESIGN_LINT_SKIP for a folder of static pages and runs its scale checks (UAK-061) and tells on them, `design-lint .uak/design/rounds/R<k>` lints every v*/index.html of a round and names the variant in each finding, Why (AXIA R1): design-lint skipped all six variants of the first real round ("no design tokens yet") because their tokens live in <style>, so its giant-type warnings never ran where they matter most
- **Tests:** html_style_tokens_count, round_folder_lints_each_variant, scale_warning_names_the_variant
- **Verify:** `python3 kit/.uak/tests/test_design_lint_html.py`
- **Next step:** the token detection at the top of kit/.uak/bin/design-lint (the `tokfiles` find)

## UAK-067 · `uak design shoot` gives videos a real poster and the human sees full pages, not only the fold

- **Type:** feature
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** UAK-063, UAK-064
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_shoot_full.py
- **Acceptance:** the Playwright capture waits for media: a <video> is seeked to 30 % of its length (or to its poster) before the shot, so captures never show an empty first frame, captures also write 1280-full.png and 390-full.png; the pick page shows the fold by default and the full page on a toggle, plus a link to each variant's live index.html served by the same server, Why (AXIA R1): two variants looked broken in their captures because the video's first frame is empty; the human judged six landings from their first screen only
- **Tests:** video_is_not_captured_blank, full_page_captures_written, pick_page_links_live_variant
- **Verify:** `python3 kit/.uak/tests/test_design_shoot_full.py`
- **Next step:** the playwright branch of `capture_one` in kit/.uak/bin/lib/design_round.py
## UAK-068 · Landings fill the desktop and open with a stand-by spectacle: the `stage` gene

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2.5 h
- **Depends on:** UAK-063
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/skills/landing-story/SKILL.md, kit/.uak/tests/test_design_stage.py
- **Acceptance:** a 9th gene `stage` with values: three.js scene, three.js point cloud from the team's own image, three.js scroll-driven, canvas 2D generative, SVG/CSS animation, real video with a live overlay, still (no animation); drawn like the others (≤ 3 shared genes, taste, wildcards); `still` is drawn at most once per round, every TASK.md (and landing-story) states: design for 1440 and 1920 first, then 390; the hero is full-bleed; content containers ≥ 1200 px at 1440 (a text column may be narrower, the composition fills the screen); no section with wide empty gutters, the hero is a stand-by loop for a projector: it runs with no interaction in a 10–15 s cycle and tells the project to a stranger (subject → what the product finds → the result → the wow); reduced motion gives a complete still, images: never show a raster upscaled; recreate the subject (3D, points, line art, vector) or show it at ≤ native size; real result charts may be rebuilt as live SVG/HTML from their real numbers, three.js rules in TASK.md: pinned CDN import map (three@0.170.0), DPR ≤ 2, pause when hidden, a designed still when WebGL is missing, no branded 3D models, no fetches but the CDN and fonts, glows, neon blurs and soft gradient haze are listed as tells (the human: "AI slop"), Why (AXIA R1–R2, 2026-11-11): every variant sat in a 600–900 px column with empty sides on a desktop; the human wants landings that make a hackathon room turn their heads while the team sets up, with three.js when it fits; resized car renders and result captures "looked stretched and ugly"
- **Tests:** stage_gene_drawn_with_still_at_most_once, task_states_desktop_first_bounds, task_states_standby_loop, task_forbids_upscaled_rasters, three_rules_pinned_cdn, landing_story_has_the_same_rules
- **Verify:** `python3 kit/.uak/tests/test_design_stage.py && python3 kit/.uak/tests/test_design_round.py`
- **Next step:** GENES and task_text in kit/.uak/bin/lib/design_round.py; section 2 of landing-story

## UAK-069 · `uak design shoot` judges what the human judges: 1920 projector shot, served over http, WebGL, and a QA line

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-067, UAK-068
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_shoot_qa.py
- **Acceptance:** the Playwright capture serves the round folder over a local http server (canvas pixel reads and fetches fail on file://), launches Chromium with software WebGL (`--use-angle=swiftshader --enable-unsafe-swiftshader`), and shoots 1920×1080 (`1920.png`, the projector) besides 1280 and 390, ~3 s after load so animations are mid-cycle, a QA line per viewport: WebGL available, page errors (count + first), horizontal overflow, the width of the content's bounding box as a share of the viewport (warn under 75 % at 1920 and 1440: "narrow page, empty gutters"), and every <img> drawn larger than its natural size × DPR ("upscaled raster: file, natural → drawn"), `uak design pick` shows the 1920 shot first, the QA warnings under each variant, and links to the live page, the shoot exits non-zero when any variant has page errors, and lists them, Why (AXIA R1–R3): the lead had to hand-patch the capture script for 1920, http and WebGL, and the human found the narrow pages and stretched images by eye; the kit should catch both before the human looks
- **Tests:** serves_over_http_so_canvas_reads_work, writes_1920_shot, flags_narrow_page, flags_upscaled_raster, page_errors_fail_the_shoot, pick_page_shows_qa_and_1920
- **Verify:** `python3 kit/.uak/tests/test_design_shoot_qa.py`
- **Next step:** `capture_one` in kit/.uak/bin/lib/design_round.py (the reference implementation is /home/joahan/Proyectos/design-rounds/bin/shoot.js, a Node script; port its behavior to the Python/Playwright path and keep the UAK_DESIGN_SHOOT override)
## UAK-070 · Every design round measures its tokens and its time, and the next estimate uses them

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2.5 h
- **Depends on:** UAK-069, UAK-064
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/bin/lib/design_metrics.py, kit/.uak/tests/test_design_metrics.py
- **Acceptance:** each variant records `metrics.json` in its folder: started (TASK.md written), first page (first index.html write), done (last capture), wall seconds, look-and-fix passes (captures taken), and tokens with their source: the agent's reported usage when the builder writes it (`uak design done R<k> v<i> --tokens N` — one line in TASK.md tells the agent to run it with its usage), else the kit's own token records for that session (`uak tokens`), else `null` with the reason (never 0, never estimated), `uak design report R<k>` prints one row per variant (tokens, minutes, passes, page errors) and the round's totals: tokens, wall time in parallel (longest variant), and tokens per picked variant; `--all` lists every round of the project with cumulative totals, the cost line before a round uses the measured median tokens per variant of this human's past rounds (by stage family: still/SVG/canvas vs three.js; from the taste profile store) and says where the number comes from; the 60k default only when there is no history, labeled "no history", the cost line also estimates wall time (median minutes per variant at the given parallelism) and warns when a round won't fit before the event's next deadline in `uak clock` (sprint), `uak design pick` shows each variant's tokens and minutes under its captures, and the round's totals in the header, the machine's load is recorded with each variant (1-min load average at start and end), so wall time inflated by an overloaded machine is visible, Why (AXIA R1–R3, 2026-11-11): in a hackathon, tokens and minutes decide whether a round fits. Measured by hand from the harness: R1 ≈ 454k tokens (partial, a usage limit cut it), R2 415k tokens in about 2.5 min wall (60–75k per variant), R3 812k tokens and 54 min wall (119–156k per variant: three.js spectacle, an overloaded Jetson). The kit's fixed 60k-per-variant estimate was off by 2× on R3.
- **Tests:** variant_metrics_written, tokens_null_with_reason_when_unknown, report_totals_and_parallel_wall, estimate_uses_measured_median_by_stage, deadline_warning_in_sprint, pick_page_shows_tokens_and_minutes
- **Verify:** `python3 kit/.uak/tests/test_design_metrics.py`
- **Next step:** a new kit/.uak/bin/lib/design_metrics.py (read/write metrics.json, medians), then the cost line in design_round.py
## UAK-071 · Each variant gets a real font pair, different from the rest of the round and from past directions

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-068
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_fonts.py, kit/.uak/tests/test_design_fonts.py
- **Acceptance:** every value of the `type` gene has a pool of at least 6 vetted Google Fonts pairs (display + body, with weights), kept in design_fonts.py; Inter, Roboto, Arial and Geist are never a display face, a round assigns one exact pair per variant (TASK.md and genome.json `fonts`): no two variants of a round share a display or body face; bred children keep the parent's pair unless `type` mutated, fonts of past directions in the taste profile (read from the winning page's Google Fonts link) are not reused in a new project's round 1 (`--allow-repeat` lifts it); the profile records the winning pair, design-lint (round folder) warns when a variant's page loads a different pair than its TASK.md assigned, Why (AXIA R3, 2026-11-11): the type gene said "serif display" and all six agents picked the same pair (Fraunces + Geist); the human: "the fonts in all of them are the same now, they need more variety"
- **Tests:** pools_have_six_pairs, round_pairs_all_distinct, child_keeps_parent_pair, past_direction_fonts_not_reused, lint_flags_wrong_pair
- **Verify:** `python3 kit/.uak/tests/test_design_fonts.py`
- **Next step:** a new kit/.uak/bin/lib/design_fonts.py, then `task_text` in design_round.py

## UAK-072 · Rounds keep light and dark in balance; taste cannot drift a round to one ground

- **Type:** feature
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** UAK-071
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_ground.py
- **Acceptance:** each genome gets a `ground` (light or dark) derived from its color gene (dark media → dark; light paper → light; ink + one accent, brand duo, saturated field → drawn), written into TASK.md, a round of N ≥ 4 has at least ⌈N/3⌉ light and ⌈N/3⌉ dark variants, also bred rounds (a dark parent's child may be flipped to light, recorded in "because") and taste-seeded rounds, the taste profile stores ground as a trait like the others, Why (AXIA R1–R3): dark won 4 of 5 picks and breeding drifted every later round to dark; the human: "the dark ones gained too much ground over the white ones"
- **Tests:** ground_derived_from_color, round_has_third_light_and_dark, bred_round_flips_to_keep_balance, taste_cannot_make_all_dark
- **Verify:** `python3 kit/.uak/tests/test_design_ground.py && python3 kit/.uak/tests/test_design_breed.py`
- **Next step:** after make_genomes in design_round.py and after breed() in design_breed.py

## UAK-073 · An animation performance budget the capture measures

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-070
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_perf.py
- **Acceptance:** TASK.md states the budget for three.js stages: low-power context, DPR ≤ 1.5, ≤ ~40k points or ~10k instances (InstancedMesh / one BufferGeometry), render only while visible, hero capped at 30 fps, drop detail when frames run slow; and for SVG/canvas/CSS stages: animate transforms and opacity, not layout, the capture measures, per viewport, the average frame interval over 3 s (requestAnimationFrame), long tasks and JS heap, writes them to the variant's metrics.json, and flags "heavy" over a threshold set in PROJECT.md (`Design-Frame-Budget-Ms:`, default 50 for WebGL stages and 20 for the rest, on the machine that captures), `uak design pick` shows the frame time and the heavy flag under each variant, Why (AXIA R3 → colonIA R1, 2026-11-11): the human: "it has to find a way not to spend exaggerated resources on three.js"; measured on the Jetson: an R3 three.js hero ran at 122 ms per frame (~8 fps) against 17 ms for an SVG one, and six three.js pages captured at once saturated the machine
- **Tests:** budget_in_task_for_webgl_stage, frame_time_recorded, heavy_flag_over_threshold, pick_shows_frame_time
- **Verify:** `python3 kit/.uak/tests/test_design_perf.py`
- **Next step:** the capture in design_round.py (port the perf probe of /home/joahan/Proyectos/design-rounds/bin/shoot-patient.js)

## UAK-074 · The brief finds the project's material and story beats the way teams really write them

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1.5 h
- **Depends on:** UAK-072
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_brief_real.py
- **Acceptance:** PNG/JPG files whose width ≥ 1000 and aspect ≈ 16:9 or 16:10 are classified as product screens (not "3D cut-out"); a PNG with a transparent background is a cut-out; .geojson/.json with coordinates is "real data (map)"; .mp4/.webm is video — and brief.md lists real data, the wow is found in "Wow in one sentence:", a `**Wow:**` cell, or a "**Wow N:**" mark inside the flow table; the ask in an `Ask:` line or the CTA of the live product's index.html; headings in Spanish ("Una línea", "Usuarios", "Flujo de la demo", "Datos citables") count like the English ones, the project's name comes from IDEA.md §0's name line, else the web/index.html <title>, Why (colonIA R1, 2026-11-11): the brief said wow MISSING and ask MISSING although IDEA.md has both, and classified four real product screens as "3D cut-out" while missing the real hex.geojson; the lead fixed brief.md by hand
- **Tests:** screens_vs_cutouts, geojson_is_real_data, wow_inside_flow_table, spanish_headings, name_from_title
- **Verify:** `python3 kit/.uak/tests/test_design_brief_real.py`
- **Next step:** the brief/material readers in kit/.uak/bin/lib/design_round.py
## UAK-075 · The kit ships a default design prior learned from real rounds, so every team starts from it

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-074
- **Paths:** kit/.uak/settings/design-prior.json, kit/.uak/bin/lib/design_prior.py, scripts/design_prior.py, kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_prior.py
- **Acceptance:** `kit/.uak/settings/design-prior.json` is shipped and versioned: per gene value a weight with its evidence (picks/shown across how many distinct projects), only traits — no names, no project names, no hex, no pages, no notes text, `python3 scripts/design_prior.py --from ~/.uak/taste/<human>.json [--from ...]` (maintainers, at release) writes it; a trait enters the prior only when it was picked in at least 2 distinct projects with a weight clearly above or below neutral; stylistic genes (type family, ground/color family, scale) are kept neutral unless 3+ projects agree, so the prior never pushes every team to the same look, `uak design round` draws with: prior (when no personal/team profile, or blended with it), then the personal/team profile on top; `--no-prior` turns it off; the "why" of each gene says "prior", "taste" or "spread", the kit's own round rules (bounds, desktop first, stand-by loop, stage, fonts, ground balance, performance, information density) stay in TASK.md/landing-story for everyone regardless of the prior, the release checklist (CHANGELOG step) regenerates the prior from the maintainers' profiles and records how many rounds/projects it came from, Why (2026-11-12, the human): "I thought this was becoming a default of the kit: these iterations are so that anyone gets the best version on GitHub, not that everyone builds their own model"; today the profile lives only in ~/.uak/taste of one machine
- **Tests:** prior_has_traits_only, needs_two_projects_to_enter, stylistic_genes_stay_neutral, round_uses_prior_without_profile, profile_blends_over_prior, no_prior_flag
- **Verify:** `python3 kit/.uak/tests/test_design_prior.py`
- **Next step:** a new kit/.uak/bin/lib/design_prior.py, then the weights argument of make_genomes in design_round.py

## UAK-076 · A team's taste lives in the project repo and one person has one profile

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-067
- **Paths:** kit/.uak/bin/lib/design_taste.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_taste_team.py
- **Acceptance:** `uak design taste --team` folds the project's rounds into `.uak/design/taste.json` in the repo (committed like the rest of .uak/design), so a team shares one profile across machines; round 1 uses team → personal → prior, in that order, the pick page's name field defaults to UAK_HUMAN / git user.name and suggests existing profile names; a typed name that differs only in case, accents or a known alias (`.uak/design/aliases` or `~/.uak/taste/aliases`) maps to the same profile, `uak design taste --merge A B` merges two profiles of the same person, Why (2026-11-12): the same human ended with two profiles ("joahan" from the colonIA page, "JoahanMorales" from the CLI) and a profile that never leaves one machine
- **Tests:** team_profile_in_repo, order_team_personal_prior, name_variants_map_to_one_profile, merge_two_profiles
- **Verify:** `python3 kit/.uak/tests/test_design_taste_team.py`
- **Next step:** profile path resolution in kit/.uak/bin/lib/design_taste.py

## UAK-077 · Landings breathe: an information-density budget for the hero, stated and measured

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-075, UAK-073
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/skills/landing-story/SKILL.md, kit/.uak/tests/test_design_density.py
- **Acceptance:** TASK.md and landing-story state a hero budget at 1920×1080 and 1280×720: one headline, one sentence, one or two actions, at most 3 secondary elements (a stat, a legend, a badge) besides the stage; at most ~45 words in the fold; the stage carries the story, the text doesn't repeat it; no text block over the stage's focal point, the capture counts, at the fold of each viewport, visible text elements and words (and how many overlap the stage's canvas/SVG), writes them to metrics.json, and flags "dense" over the budget; the pick page shows it, later sections: one idea per section, no section with more than ~4 cards or ~80 words, Why (colonIA R1, 2026-11-12): the human on v1, v5 and v6: "too much information, things pop up everywhere and it looks saturated, it's too much for anyone"; on v5 "the pink text doesn't let you see the background"
- **Tests:** budget_in_task_and_skill, capture_counts_words_and_elements, dense_flag_over_budget, overlap_with_stage_counted
- **Verify:** `python3 kit/.uak/tests/test_design_density.py`
- **Next step:** task_text in design_round.py and section 2 of landing-story

## UAK-078 · Color is a palette with roles and proportions, measured from the page, and that is what taste learns

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-077
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_color.py, kit/.uak/bin/lib/design_taste.py, kit/.uak/tests/test_design_color.py
- **Acceptance:** each variant gets a palette with roles built from the project's brand colors (brief.md): ground, ink, primary, accent(s), with target area shares (e.g. 60/30/10 or a stated alternative per strategy) and a maximum share for any saturated color; strategies replace the bare labels (monochrome + one accent, brand duo, full brand range, tinted neutrals, …) and are written into TASK.md with the exact hex per role, contrast: ink on ground ≥ 7:1, primary text/buttons ≥ 4.5:1 (checked from the hex, before building), the capture measures the real color use at the 1920 fold (share of saturated pixels, share of dark pixels, the 5 dominant colors and their areas, how much of each brand color appears) into metrics.json; the pick page shows a palette strip per variant, the taste profile learns from the measured features (saturation share, dark share, brand-color coverage, number of hues), not only from the gene label, so "uses color well" is learned as numbers, Why (2026-11-12, the human: "the taste profile uses colors very badly"): measured at the fold, all six AXIA R3 pages were 1–3 % saturated (an almost monochrome navy; the Kavak blue barely appears) while their label said "ink + one accent" or "dark media"; colonIA v4 used a washed pink ("doesn't use the colors well"); the profile learned the labels, not what was on screen
- **Tests:** palette_roles_from_brand_colors, contrast_checked, capture_measures_color_use, taste_learns_measured_color, pick_shows_palette_strip
- **Verify:** `python3 kit/.uak/tests/test_design_color.py`
- **Next step:** a new kit/.uak/bin/lib/design_color.py (roles, contrast, measuring a PNG with the stdlib zlib PNG reader), then task_text

## UAK-079 · test_v59 "a Verify that does not parse is refused" stops flaking under parallel load

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/tests/test_v59.py, kit/.uak/bin/lib/lint.sh, kit/.uak/bin/lib/plan.sh
- **Acceptance:** find why, under load, `uak lint` reads the old Verify of a task the test just pushed (the failure shows `LINT_OK` plus the negated-rg warning instead of the refusal): a stale claims cache, a fetch that returns before the push is visible, or the test reading too early; fix the cause (not a sleep), the test passes 30 times in a row under `smoke --jobs 4` and alone; a regression case reproduces the race deterministically (e.g. a forced stale cache), Why (v6.1.1 → v6.3, 2026-11-11/12): it failed in 2 of 4 parallel runs during UAK-054 and again in the full smoke before merging UAK-068, each time passing alone; flaky gates train people to rerun instead of read
- **Tests:** a_verify_that_does_not_parse_is_refused, stale_claims_cache_still_refuses
- **Verify:** `python3 kit/.uak/tests/test_v59.py`
- **Next step:** reproduce with `for i in $(seq 30); do UAK_SMOKE_TESTS="test_v59 test_hack test_v58 test_v42" bash kit/.uak/bin/smoke --package-only --jobs 4 || break; done`
## UAK-080 · Breeding from near-identical picks explores instead of failing

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_breed_twins.py
- **Acceptance:** when the picks share most of their genes (e.g. 8 of 9), `design round --from` still produces N children: the relaxation ladder's last step treats children of near-identical picks as kin for the shared-genes rule (they only must not be identical), and the round adds wildcards so at least ⌈N/3⌉ children differ from every pick in 4+ genes; every relaxation is recorded in "because", the ground balance (UAK-072) and distinct fonts for wildcards still hold, the human sees why: the cost/mix line says "picks nearly identical (8/9 genes): exploring with N wildcards", Why (AXIA R3, 2026-11-13): the human picked v5 and v3 (both dark, serif, 8 of 9 genes shared); `design round --from R3` failed on every seed with "could not breed … diversity rule", before and after UAK-072 — exactly when the human most needs the kit to explore
- **Tests:** twins_still_breed, twins_round_has_explorers, ground_and_fonts_hold_for_twins, because_explains_twins
- **Verify:** `python3 kit/.uak/tests/test_design_breed_twins.py && python3 kit/.uak/tests/test_design_breed.py`
- **Next step:** the relaxation ladder in kit/.uak/bin/lib/design_breed.py (after the rejected-values steps)
## UAK-081 · The capture catches distorted images (aspect ratio), the "stretched" look the human saw

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** UAK-073
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_aspect.py
- **Acceptance:** the capture's QA flags "distorted image: file, natural W×H → drawn W×H" when an <img>, <video>, CSS background (size set in both axes) or <canvas> is drawn with an aspect ratio more than 8 % off its natural one and object-fit (or background-size) does not preserve it (fill / explicit stretched sizes), TASK.md and landing-story say: raster images keep their aspect ratio — `object-fit: cover` (crop) or `contain` (fit), never `fill` or a width and height that disagree with the file, Why (AXIA R1, found by the UAK-073 review, 2026-11-13): the human called the images "stretched and ugly"; they were not upscaled but squashed: R1/v2 drew loop.png (900×620) at 532×620 (ratio 0.86 vs 1.45) and resultados-60.png (900×520) at 612×520 with object-fit: fill; no check caught it
- **Tests:** squashed_img_flagged, cover_and_contain_not_flagged, stretched_background_flagged, rule_in_task_and_skill
- **Verify:** `python3 kit/.uak/tests/test_design_aspect.py`
- **Next step:** QA_JS in kit/.uak/bin/lib/design_round.py (next to the upscaled-raster check)
## UAK-082 · test_tokens_coverage no longer fails on Windows when its temp worktree is still locked at cleanup

- **Type:** bug
- **Priority:** P2
- **Estimate:** 30 min
- **Depends on:** —
- **Paths:** kit/.uak/tests/test_tokens_coverage.py
- **Acceptance:** the test's temporary directory is removed with retries (a short backoff for WinError 32 / 5) and a cleanup that still fails is reported as a warning, never as a test failure; every case's own pass/fail is unchanged, if a process of the test itself (git, a hook) still holds `tk-hooks/worktree-1`, it is waited for or closed before cleanup, and the Why names it, Why (CI 2026-11-14, runs 43561825313 and 43563146571 of v6.3.0): both failed only on Windows with `PermissionError: [WinError 32] … uak-tokens-coverage-*\tk-hooks\worktree-1` raised by `TemporaryDirectory` cleanup after every case passed; a rerun went green each time, so the release needed manual reruns
- **Tests:** cleanup_survives_locked_worktree
- **Verify:** `python3 kit/.uak/tests/test_tokens_coverage.py`
- **Next step:** the `tempfile.TemporaryDirectory(prefix="uak-tokens-coverage-")` block in main() of kit/.uak/tests/test_tokens_coverage.py (line ~151)
