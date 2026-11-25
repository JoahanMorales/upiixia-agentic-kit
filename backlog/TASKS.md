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
## UAK-083 · A bred round keeps the rules of a fresh one: picked palettes, distinct fonts, at most two three.js stages, re-shoot

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-071, UAK-073, UAK-078
- **Paths:** kit/.uak/bin/lib/design_breed.py, kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_fonts.py, kit/.uak/tests/test_design_breed_rules.py
- **Acceptance:** `design round --from R<k>` gives every child the palettes of the latest palette round with picks (as a fresh round does, via `design_color.picked_palettes` + `with_ground`), and the color gene agrees with the palette's ground, no two variants of a bred round share a display face: a child keeps its parent's pair only when no sibling has it; otherwise it gets a distinct pair of the same `type` gene (and never a past direction's face), a round (fresh or bred) has at most `Design-Max-WebGL` variants whose stage is three.js (default 2, PROJECT.md); the extra ones move to a light stage (canvas 2D, SVG/CSS, scroll, video) and the genome's `because` says why, `design shoot R<k> [v<i>…] --again` recaptures variants that already have PNGs (today the only way is deleting them); the "already had N" line names the flag, when Playwright for Python is missing and the fallback writes screenshots without a QA report, `design shoot` says how to install it (`pip install playwright && python -m playwright install chromium`) instead of only "not captured", Why (colonIA R2, 2026-11-14): bred from R1, the round had no palettes (the human's picks of P1 were ignored), v1/v3 both Anton and v2/v4 both Fraunces (the human, after AXIA: "las fuentes en todos ya son las mismas"), 4 of 6 stages three.js (the human: "no gastar cantidades exageradas de recursos en el three js"); the lead fixed all three by hand
- **Tests:** bred_round_uses_picked_palettes, bred_round_fonts_distinct, webgl_cap_fresh_and_bred, shoot_again_recaptures, shoot_says_how_to_install_playwright
- **Verify:** `python3 kit/.uak/tests/test_design_breed_rules.py`
- **Next step:** the children loop at the end of `run()` in kit/.uak/bin/lib/design_breed.py (after `design_fonts.inherit`), reusing the palette block of design_round.py:789
## UAK-084 · A creativity index: every variant has its own identity motif and hero composition, and the capture flags siblings that came out the same

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-083
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_breed.py, kit/.uak/bin/lib/design_metrics.py, kit/.uak/bin/lib/design_creativity.py, kit/.uak/tests/test_design_creativity.py, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/docs/WHY.md, kit/.uak/tests/test_design_breed.py, kit/.uak/tests/test_design_breed_notes.py, kit/.uak/tests/test_design_breed_rules.py, kit/.uak/tests/test_design_round.py
- **Acceptance:** `Design-Creativity` in PROJECT.md (1-5, default 3), overridable with `design round ... --creativity N`, is the round's creativity index; the genome records it and TASK.md says what it asks for (1: refine the parent, 3: same family and a new identity, 5: a new direction), every genome has a `composition` gene, the hero's geometry in measurable terms, drawn from at least 6 archetypes (e.g. poster: the headline is the image, centered, at least 40% of the fold; stage full-bleed with the copy in a bottom band; stage left with the copy right; one object centered as a monument with the copy under it; editorial grid led by one huge number; split copy left with the stage right). No two siblings share one while archetypes remain. In a bred round, at creativity 3 or higher, a child's composition differs from its parent's unless the human's note on the parent praises the layout, every genome has a `motif`, the page's one identity idea, taken from a family that does not depend on the domain (craft or pattern of the place, an everyday object as the hero, a typographic poster, a cartography, documentary photography, an illustrated character). Siblings get distinct families. TASK.md asks for ONE motif carried strongly and for few objects: "identity, not quantity". The builder writes it as `<!-- motif: ... -->` at the top of index.html, and `design shoot` copies it into the genome, in a bred round, a child whose parent got a note praising it ("linda", "bonita", "creativa", "identidad", "me encanta"…) inherits the parent's literal motif: TASK.md quotes it as read from the parent's index.html, and the parent's note about too many objects becomes "keep the motif, cut the objects", after a capture, QA_JS records a composition signature at 1920 (headline rect, stage rect and focal point, normalized; ground luminance; dominant hue of the fold). `design shoot` compares the signatures of the round's captured siblings. Two variants that are too close get the warning `clone of v<j>: same hero composition (headline …, stage …)`, and the round gets a creativity score from 0 to 100 (mean pairwise distance), printed by `design shoot` and `design report`, Why (colonIA R2, 2026-11-14): the six variants bred from R1 all came out the same: headline left, hex map right. R1/v1 was the best ("ESTA SUPER LINDA Y CREATIVA") because of its papel picado, a strong identity whose only problem was too many objects. The child kept the genes but lost the motif, since no gene carried it. The human: "deberías añadir un índice de creatividad y volver a hacer esta ronda, el problema está en que ahora todos son iguales … tenía muy bonitas banderas encima, una identidad muy marcada y linda, donde el único problema era que había demasiados objetos encima"
- **Tests:** creativity_from_project_and_flag, compositions_distinct_across_siblings, bred_child_changes_composition_at_creativity_3, motif_families_distinct, praised_parent_motif_inherited_and_quoted, shoot_reads_motif_comment, clone_warning_on_same_signature, creativity_score_in_report
- **Verify:** `python3 kit/.uak/tests/test_design_creativity.py`
- **Next step:** the new `design_creativity.py` holds the archetypes, the motif families, the signature distance and the score;, `make_genomes` in design_round.py and `run()` in design_breed.py (after `_distinct_display_faces`) assign composition and motif;, QA_JS in design_round.py (near the `focal` rect) records the signature.
## UAK-086 · `design shoot` no longer loses a variant to a 30 s screenshot timeout after the QA pass

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** UAK-084
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_shoot_timeout.py
- **Acceptance:** the capture takes each viewport's screenshots BEFORE the long QA work (frame timing, background-image loads, mass), or gives `page.screenshot` a timeout that scales with the page height (at least 90 s for a full-page capture at device scale 2), a screenshot that still times out leaves the variant's other viewports and its qa.json written, and the line names the viewport ("390-full timed out after 90 s: the page keeps repainting; pause loops off screen"), never "captured none" for a variant whose 1920 and 1280 were fine, shooting several variants at once (agents shooting in parallel on one machine) is serialized by a lock file in the round folder, so one shoot never starves another, Why (colonIA R3, 2026-11-15): R3/v4 never got a 390.png in 5 runs: `Page.screenshot: Timeout 30000ms exceeded`. Alone and without the QA pass, the same page shot its 390 full page (780x12620) in 3.4 s; after MEDIA_JS + QA_JS the viewport shot took 17 s and the full page 35 s. The lead captured 390 by hand. R3/v3's agent also lost 3 passes with six variants shooting at once (load average ~17)
- **Tests:** screenshots_before_qa, timeout_scales_with_height, timeout_names_viewport_keeps_others, parallel_shoots_serialized
- **Verify:** `python3 kit/.uak/tests/test_design_shoot_timeout.py`
- **Next step:** the `for name, w, h in (("1920", …` loop in the `_PLAYWRIGHT` script of kit/.uak/bin/lib/design_round.py (~line 1197)
## UAK-085 · A bred round keeps a praised parent's motif even when the parent predates motifs, and its TASK.md does not tell the child to keep the parent's layout at creativity 3+

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** UAK-084
- **Paths:** kit/.uak/bin/lib/design_creativity.py, kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_creativity_inherit.py
- **Acceptance:** a child of a praised parent inherits the parent's motif when the parent's genome has no `motif.family` but its index.html has a `<!-- motif: -->` comment. The family is taken from the parent's genome when present, else it is the first family no sibling uses, and the inherited text is quoted, when the parent has neither, TASK.md tells the child to read the parent's page and name its motif. This already exists as "(its index.html has no motif comment: read the page)", but it was unreachable because `assign` required the family first, at creativity 3 or higher, `child_task` no longer says "keep the rest of the parent's look". It says the other genes are kept, and that the composition and motif above replace the parent's hero layout. At 1-2 the old sentence stays, the creativity line and the inheritance line no longer contradict each other: level 4 says "a clearly different composition; a new motif unless the human praised the parent's", Why (colonIA R3, 2026-11-15): bred from R1 at creativity 4, the child of R1/v1 got the motif family "specimen sheet" instead of R1/v1's papel picado, which the human loved: "tenía muy bonitas banderas encima, una identidad muy marcada". R1's genomes come from before UAK-084, so `assign` saw no `motif.family` and skipped the inheritance. TASK.md also still said "keep the rest of the parent's look", which pulls the child back to the parent's layout, the same convergence that made R2's six heroes identical. The lead added motif comments to R1/v1 and R1/v5 and fixed R3/v1, v2 and v6 by hand
- **Tests:** inherits_motif_text_without_family, no_motif_comment_says_read_the_page, child_task_layout_sentence_by_level, level4_text_mentions_praised_motif
- **Verify:** `python3 kit/.uak/tests/test_design_creativity_inherit.py`
- **Next step:** the `inherit = par and praised(note) and (par.get("motif") or {}).get("family")` line in `assign()` (design_creativity.py:~97);, `child_task` in design_breed.py:326.
## UAK-087 · `review` records a valid verdict when the SHA's existing approval names an identity never seen or retired

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/tests/test_review_unseen_approval.py
- **Acceptance:** with reviews/ID.md approving the current SHA by an identity that has no meta/agents file or is retired, `uak review ID --start` does not answer SKIP and `uak review ID --sha SHA --verdict approve` by a valid reviewer records the verdict; `uak merge` then accepts it, an approval by a seen, not retired identity keeps today's answers ("already approved by X on this SHA"), the replaced approval is named in the output ("replaces an approval by ghost, never seen on claims"), Why (private sprint on v6.4.0, 2026-11-17, agent note): review refused to record because an unknown identity had approved the SHA, and merge rejected that same approval as "never seen on claims or retired": the task could only go to the human. docs/blackbox/harvest-2026-11.md #3
- **Tests:** unseen_approval_does_not_skip_start, valid_reviewer_replaces_unseen_approval, seen_approval_still_skips, merge_accepts_the_replacement
- **Verify:** `python3 kit/.uak/tests/test_review_unseen_approval.py`
- **Next step:** the two "already approved by" branches (~lines 181 and 238) and the "never seen on claims or retired" gate (~line 286) of kit/.uak/bin/lib/review-merge.sh

## UAK-088 · `wt new ID --agent NAME` resumes a claim that already belongs to NAME

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/wt, kit/.uak/bin/lib/claim.sh, kit/.uak/tests/test_wt_resume_claim.py
- **Acceptance:** after `uak handover ID --to NAME` (or a claim NAME made on another machine), `wt new ID --agent NAME` creates the worktree on the task's existing branch with its .uak-env, and says it resumed the claim; it does not answer "already has claims/ID.md", a claim owned by another identity keeps the refusal, and names the owner, the branch is fetched from origin when it only exists there, Why (UpiixSol, 2026-11-13, two agent notes): "wt new refuses owner of a handed-over claim"; "wt new UPS-052 --agent david-5 refused… had to git worktree add by hand". docs/blackbox/harvest-2026-11.md #4
- **Tests:** resumes_own_claim_after_handover, refuses_claim_of_another_identity, fetches_the_remote_branch
- **Verify:** `python3 kit/.uak/tests/test_wt_resume_claim.py`
- **Next step:** the already-claimed check at kit/.uak/bin/lib/claim.sh:19 and the claim call in kit/.uak/bin/wt

## UAK-089 · The black box is published without harness hooks

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/bb, kit/.uak/tests/test_bb_flush_no_hooks.py
- **Acceptance:** a `uak` command that ends with pending black box lines older than 10 minutes (and no flush in the last 10) starts `bb flush --quiet` in the background, detached, without delaying or changing the command's output or exit code, UAK_BLACKBOX=off starts nothing; a failed flush stays silent and keeps the pending lines, the hook's own flush keeps working and the two never run at once (the `flushed` stamp is taken first), Why (the kit's own repo, 10 → 15 Nov 2026): 61 errors sat in .git/uak-blackbox.pending and none was published, because flush only starts from a harness hook and the kit is driven by subagents and plain shells. docs/blackbox/harvest-2026-11.md #2
- **Tests:** old_pending_is_flushed_by_a_plain_command, fresh_pending_waits, blackbox_off_starts_nothing, output_and_exit_code_unchanged
- **Verify:** `python3 kit/.uak/tests/test_bb_flush_no_hooks.py`
- **Next step:** the flush trigger in kit/.uak/bin/hook:637 (copy its condition) and the calls counter at kit/.uak/bin/uak:104

## UAK-090 · The weekly harvest finds the repos again, and an empty harvest fails

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** scripts/blackbox_harvest.py, .github/workflows/blackbox-harvest.yml, kit/.uak/tests/test_harvest_discovery.py
- **Acceptance:** discovery calls `gh search code` with `--filename PROJECT.md` (text "Plan-Channel") and `--filename BLACKBOX.md`, and drops repos where neither claims:blackbox/ nor .uak/BLACKBOX.md has a kit line, no repo found exits 1 with the gh error when there is one, and the workflow step fails instead of ending green with no issue, the test stubs `gh` (a Python stub on PATH, no sh) and checks the arguments and the parsing, Why (2026-11-20): `gh search code "path:.uak filename:PROJECT.md Mode"` returns nothing; the weekly workflow has been green and has never opened an issue. By hand with --filename the search finds 14 repos. docs/blackbox/harvest-2026-11.md #1
- **Tests:** discovery_uses_filename_flag, repos_without_kit_lines_are_dropped, empty_discovery_exits_1
- **Verify:** `python3 kit/.uak/tests/test_harvest_discovery.py`
- **Next step:** `search()` and the `repos = …` line of scripts/blackbox_harvest.py

## UAK-091 · A guessed spelling gets the right one back: nearest command, `--approve`, a bare SHA

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-089
- **Paths:** kit/.uak/bin/uak, kit/.uak/tests/test_cli_spelling_hints.py
- **Acceptance:** an unknown command names the nearest registered one when there is one ("Unknown command: decisions. Did you mean: decision"; `owners` → the OWNERS.md file; `agents` → `status --agents` or the right command), `review ID --approve` / `--reject` answer with the exact line to run (`--sha SHA --verdict approve`); `review ID SHA`, `status ID SHA` and `merge ID NAME` name the flag the bare word needs, `done ID --pr BRANCH` answers with the PR's URL command (`bash .uak/bin/wt pr`) and says a branch name is not a URL; `log --task ID` says the ID goes first, exit codes and UAK_CODE stay as they are; only the text gains the hint, Why (harvest 2026-11): review with a bare SHA ×4, `--approve` ×2, merge with a name ×2, unknown commands decisions/owners/agents/kit-hashes, `done --pr <branch>` ×2, `log --task`. docs/blackbox/harvest-2026-11.md #5
- **Tests:** unknown_command_suggests_nearest, review_approve_flag_names_verdict, bare_sha_names_the_flag, done_branch_is_not_a_url
- **Verify:** `python3 kit/.uak/tests/test_cli_spelling_hints.py`
- **Next step:** kit/.uak/bin/uak:107 (unknown command) and the argument loop at kit/.uak/bin/uak:247-258

## UAK-092 · `integrate` records a task whose reviewed code is already on main

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-087
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/tests/test_integrate_on_main.py
- **Acceptance:** when the approved SHA is an ancestor of main and the branch has commits after it, `integrate` records the task INTEGRATED at the approved SHA and names the leftover commits ("1 commit after the approved SHA is not on main: <sha> <subject>"), instead of refusing, a CANCELLED task whose PR merge is on main can be recorded by a human (`UAK_HUMAN=NAME uak integrate ID --reason TEXT`), and its dependents can then be claimed, code on main with no approval at all keeps today's refusal for agents (the human record stays the only way), Why (UpiixSol, 11 → 18 Nov 2026): 15 refusals "Missing verifiable approval" and two agent notes: "a task merged on the forge before its claim was cancelled… its dependents now refuse to claim"; "UPS-031 is in main (PR #50) but stays AVAILABLE… integrate blocked by an unmerged review commit". docs/blackbox/harvest-2026-11.md #6
- **Tests:** approved_ancestor_with_leftover_commit_integrates, cancelled_with_merged_pr_recorded_by_human, dependents_claimable_after, unapproved_code_still_refused
- **Verify:** `python3 kit/.uak/tests/test_integrate_on_main.py`
- **Next step:** `integrate` in kit/.uak/bin/lib/review-merge.sh (~line 862, the refusal reasons)

## UAK-093 · A design critique survives commits that touch no UI, and `done` names the fallback when the critic agent is missing

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/skills/product-ui/SKILL.md, kit/.uak/tests/test_critic_stale_ui_only.py
- **Acceptance:** critic.txt about commit A stays valid at commit B when `git diff A B` touches no UI path (the same paths that make `done` ask for shots); a UI change keeps today's refusal, the missing-critic and stale-critic messages name the fallback: any subagent given kit's design-critic prompt file, writing the same critic.txt, the product-ui skill documents the fallback in one paragraph, Why: UpiixSol (12 and 16 Nov 2026) "design-critic is in .claude/agents but the Agent tool of the session does not list it, so done cannot get a SHIP"; private sprint on v6.4.0, "critic.txt is about another commit" ×3 in one night. docs/blackbox/harvest-2026-11.md #7
- **Tests:** critique_valid_after_non_ui_commit, critique_stale_after_ui_commit, messages_name_the_fallback
- **Verify:** `python3 kit/.uak/tests/test_critic_stale_ui_only.py`
- **Next step:** the critic-stale check at kit/.uak/bin/lib/done.sh:56

## UAK-094 · The banner's version comes from VERSION, and the lint and the checklist know it

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** scripts/make_media.py, scripts/kit_lint.py, CONTRIBUTING.md, kit/.uak/tests/test_banner_version.py
- **Acceptance:** make_media.py reads major.minor from kit/.uak/VERSION for the banner's eyebrow and writes it next to the PNG (docs/media/banner.version), kit_lint fails when banner.version differs from VERSION's major.minor, naming the command that regenerates it, the release checklist in CONTRIBUTING.md lists the banner, Why (release v6.4.0, 2026-11-16): the banner still said v6.1 after three releases; the version was a literal and no check read it. docs/blackbox/harvest-2026-11.md #8
- **Tests:** banner_text_uses_version_file, lint_flags_a_stale_banner
- **Verify:** `python3 kit/.uak/tests/test_banner_version.py`
- **Next step:** the eyebrow literal at scripts/make_media.py:103
## UAK-110 · One identity, one live task also holds for heartbeat, log, checkpoint and handoff

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/claim.sh, kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_one_live_renew.py
- **Acceptance:** an identity whose claim on X expired and that then claimed Y cannot renew X: `heartbeat`, `log`, `checkpoint` and `handoff` on X refuse with UAK_CODE one-live-task and say which task is live and how to give X up (release) or take it back (release Y first), a claim that is not expired, or an identity with no other live claim, renews as today; UAK_MULTI_CLAIM=1 keeps its meaning, a claim file whose Lease-Until is empty or not a number counts as live for the one-live-task check (it cannot be used to take a second task), and `tick` reports it, Why (audit of v6.5.0, docs/audit-2026-11.md #1 and #10; first found by a TLA+ model of claims in a fork: trace claim t1, lease expires, claim t2, heartbeat t1): heartbeat_mutate checks only the owner and refresh_lease rewrites Lease-Until
- **Tests:** expired_claim_cannot_be_renewed_with_another_live, log_and_checkpoint_refuse_too, unexpired_claim_renews, damaged_lease_counts_as_live
- **Verify:** `python3 kit/.uak/tests/test_one_live_renew.py`
- **Next step:** heartbeat_mutate at kit/.uak/bin/lib/claim.sh:250, check_collisions at claim.sh:44, refresh_lease at kit/.uak/bin/lib/tx.sh:117

## UAK-111 · The guard treats a substitution inside quotes as code, sees `gh … merge` with flags, and refuses a plain push to claims

- **Type:** bug
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/guard, kit/.uak/tests/test_guard_substitution.py
- **Acceptance:** a double-quoted span that contains a command substitution (`$(` or a backtick) is not dropped as prose: the rules see its contents, so a blocked command inside a commit message or an echo is blocked, the merge rule matches `gh` with flags between the words (`gh -R o/r pr merge`, `gh pr --repo o/r merge`), a `git push` whose destination is the claims branch (`claims`, `refs/heads/claims`, `HEAD:claims`) is blocked with the reason (claims is written only by uak commands); the engine's own pushes are not affected (they do not pass through the hook), a `git` or `gh` segment that pushes or merges and contains a variable, a substitution or a backslash in the ref answers `ask` (the human decides), not allow, every existing guard test still passes and `guard bash` on `ls` and on a plain commit stays within the process counts of test_v592 (builtins only), Why (audit of v6.5.0, docs/audit-2026-11.md #3, #4, #5): reproduced with `guard check`; the guard is a text filter, so each rule is a speed bump that must at least see what runs
- **Tests:** substitution_in_double_quotes_is_checked, gh_merge_with_flags_is_blocked, push_to_claims_is_blocked, dynamic_ref_asks, plain_commands_stay_on_builtins
- **Verify:** `python3 kit/.uak/tests/test_guard_substitution.py`
- **Next step:** strip_prose and the gh rule (~line 100) in kit/.uak/bin/guard

## UAK-112 · The MCP `uak_cli` tool cannot run a passed command the guard does not see

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak-mcp, kit/.uak/tests/test_mcp_runs_commands.py
- **Acceptance:** the refusal of commands that run a passed command looks past a leading `--json` (and any other global flag) to the command name, `red` is in the set (it runs `-- CMD` and `--cmd CMD`), and the set is derived from commands.tsv plus the explicit list, with a test that fails when a new command of that kind is added without it, the refusal names the terminal as the place to run it, as today, Why (audit of v6.5.0, docs/audit-2026-11.md #2): `["--json","loop",…]` and `red ID -- CMD` reached eval without the guard
- **Tests:** json_prefix_does_not_hide_the_command, red_is_refused, registry_and_set_agree
- **Verify:** `python3 kit/.uak/tests/test_mcp_runs_commands.py`
- **Next step:** RUNS_COMMANDS at kit/.uak/bin/uak-mcp:394 and the test at line 401

## UAK-113 · The merge lock's renewer stops when the merge that started it dies

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/tests/test_merge_renewer_orphan.py
- **Acceptance:** the background loop that renews merge-lock.md exits within one interval after its parent process is gone (kill -9 of the merge), without pushing again, a normal merge still renews and releases the lock as today, Why (audit of v6.5.0, docs/audit-2026-11.md #6): the EXIT trap does not run on SIGKILL (a harness timeout, the OOM killer) and the orphan kept the queue locked
- **Tests:** renewer_exits_after_parent_is_killed, normal_merge_releases_the_lock
- **Verify:** `python3 kit/.uak/tests/test_merge_renewer_orphan.py`
- **Next step:** the renewer subshell at kit/.uak/bin/lib/review-merge.sh:~926

## UAK-114 · An unapproved task cannot be recorded INTEGRATED by its owner

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/tests/test_integrate_unreviewed.py
- **Acceptance:** `integrate` of a CLAIMED, BLOCKED or AVAILABLE task whose content is on main, with no valid approval, needs a human (`UAK_HUMAN=NAME … --reason TEXT`); an agent gets the same refusal as from REVIEW, with the line the human runs, the record of such an integrate says `Integrated-Outside: unreviewed`, and `stats` counts it, with a valid approval of that SHA by another seen identity, an agent integrates as today (UAK-092 behaviour kept), Why (audit of v6.5.0, docs/audit-2026-11.md #7): integrate_mutate required a human only when the task was in REVIEW, so an owner could unlock dependents on unreviewed code
- **Tests:** owner_cannot_integrate_unapproved_claimed_task, human_records_it_as_unreviewed, approved_sha_still_integrates
- **Verify:** `python3 kit/.uak/tests/test_integrate_unreviewed.py`
- **Next step:** integrate_mutate at kit/.uak/bin/lib/done.sh:203-241

## UAK-115 · Temp files get unpredictable names and Python helpers get timeouts

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/wt, kit/.uak/bin/doctor, kit/.uak/bin/bb, kit/.uak/bin/lib/dash.py, kit/.uak/tests/test_temp_and_timeouts.py
- **Acceptance:** `wt` (wt-add), `doctor` (doctor-verify) and `bb export` create their temp files with mktemp (or under the git dir) and remove them on every exit path, every `subprocess.run` of git in dash.py has a timeout (30 s) and a TimeoutExpired ends with a one-line message, not a hang or a traceback, a lint check (in the test) finds no `.$$` temp name under ${TMPDIR:-/tmp} in kit/.uak/bin, Why (audit of v6.5.0, docs/audit-2026-11.md #8, #9): predictable names in a shared temp dir, and `uak dash` hanging on an unreachable remote
- **Tests:** no_pid_named_temp_files, temp_files_removed_on_error, dash_times_out_on_a_dead_remote
- **Verify:** `python3 kit/.uak/tests/test_temp_and_timeouts.py`
- **Next step:** kit/.uak/bin/wt:288, kit/.uak/bin/doctor:206, kit/.uak/bin/bb:161, the `git` helper of kit/.uak/bin/lib/dash.py
## UAK-116 · A ledger of every command: name, outcome and milliseconds

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-125
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/bb, kit/.uak/tests/test_command_ledger.py
- **Acceptance:** every `uak` command appends one line when it ends to `<git-common-dir>/uak-ledger.pending`: epoch, command (with the `UAK_CALLER` prefix the calls file already uses), task ID when it has one, exit code, UAK_CODE when set, milliseconds, agent, harness. No extra process on the way (shell builtins; the clock from the cache the engine already has, or `$SECONDS`/`EPOCHREALTIME` where bash has them, falling back to whole seconds on bash 3.2), `bb flush` publishes the pending ledger to claims as `metrics/<day>-<machine>.tsv` in the same transaction as the black box lines, then empties it; a flush that fails keeps the lines; the file per day and machine is capped (oldest lines summarized as counts per command and outcome) so claims does not grow without bound, UAK_BLACKBOX=off writes nothing; the existing `uak-blackbox.calls` file and its readers keep working, the output, exit code and process counts of every command stay as they are (test_claims_perf, test_v592), Why (audit of v6.5.0, docs/audit-2026-11.md §4): calls were names only, per machine, with no durations and no outcomes; "how often does `claim` fail and how long does `status` take" could not be answered
- **Tests:** a_command_appends_one_ledger_line, a_failed_command_records_its_code, flush_publishes_and_empties, blackbox_off_writes_nothing, output_and_exit_code_unchanged
- **Verify:** `python3 kit/.uak/tests/test_command_ledger.py`
- **Next step:** the calls counter at kit/.uak/bin/uak:~103 and the flush in kit/.uak/bin/bb

## UAK-117 · `uak metrics`: every speed number next to an instability number

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-116
- **Paths:** kit/.uak/bin/metrics, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_metrics.py
- **Acceptance:** `uak metrics [--since DAYS] [--task ID] [--json]` reads claims only (ledger files, tasks, reviews, queue, events, black box) and prints, in this order: tasks integrated per day next to tasks reopened, followed up or recorded `Unreviewed`; median hours from claim to INTEGRATED next to the share of tasks rejected at least once and the review rounds per task; per command: calls, error rate, median and p95 milliseconds; human interventions by reason (the queue reasons, `allow`, human integrates); work outside the kit (commits on the base branch without a task, integrates outside the gate, `manual` notes when UAK-121 lands: the section says "not recorded yet" until then), every count is printed with its denominator ("7 of 89"), never a bare percentage for fewer than 20 events, `--task ID` prints one task: time in each state, rounds of review with each verdict and reviewer, who integrated it, its commands and errors, `--json` prints the same numbers as one object with stable keys (documented in CLI.md); commands.tsv gets the row and `gen_registry --check` passes, Why (audit §4; the human, 2026-11-20: "que todo sea medible y cuantificable para poder mejorar el kit"): `stats` counts events but pairs no speed with its cost, and has no per-command error rate or duration
- **Tests:** throughput_is_printed_with_instability, per_command_error_rate_and_p95, small_samples_print_counts, task_view_lists_review_rounds, json_has_stable_keys
- **Verify:** `python3 kit/.uak/tests/test_metrics.py`
- **Next step:** kit/.uak/bin/stats (the reader of claims to copy) and the commands.tsv row

## UAK-118 · Every task records who touched it and which model and harness each one ran

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak-coordination, kit/.uak/bin/hook, kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_task_participants.py
- **Acceptance:** the session record a task already gets (`meta/task-sessions/<ID>/agent-<name>/session-*.md`) also holds `Harness:` and `Model:`, and so does the event line of every mutation (claim, done, review, merge, integrate, handover). The model comes from `UAK_MODEL` when set, else from what the harness hook saw at session start (Claude Code's payload, Codex's), else `unknown`; a subagent's model is its own, not its parent's, a task record lists its participants by role: author(s), reviewers with their verdicts, who merged or integrated, humans who stepped in, `uak status --task ID` prints the participants line; STATE.md keeps its format (test_snapshot stays byte-identical), Why (the human, 2026-11-21: "debemos guardar qué agentes y modelos participaron en una tarea"): the session record had Agent, Session and Started only, and nothing said which model reviewed or wrote a task
- **Tests:** session_record_has_harness_and_model, events_carry_the_model, participants_by_role, unknown_when_nothing_tells, snapshot_unchanged
- **Verify:** `python3 kit/.uak/tests/test_task_participants.py`
- **Next step:** the session files written at kit/.uak/bin/uak-coordination:~381-394 and the harness detection at kit/.uak/bin/hook:~424

## UAK-119 · REVIEW says what it is waiting for, and for how long

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-118
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/dash.py, kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_review_substates.py
- **Acceptance:** a task in REVIEW has one derived sub-state, computed from claims (no new stored state): `waiting for a reviewer`, `in review by NAME`, `changes requested (round N)` after a reject with no newer tip, `re-review (round N)` after the author pushed again, `approved, waiting for CI` when pr-sync knows the checks, `approved, waiting for a human merge` with the queue reason, `approved, waiting for the owner to merge`, `uak status`, `uak status --task ID` and `uak board` print the sub-state and the time spent in it; the dashboard's REVIEW column groups its cards by sub-state, each card with a badge (rounds, rejects) and the time in the sub-state, and a card that sat more than the review lease is marked, the text of the sub-state is the same everywhere (one function); STATE.md keeps its format, Why (the human, 2026-11-21: "a veces está en In review por horas y visualmente no sabes si hubo un rejected, está en CI o lo que sea"; v6.6: UAK-111 and UAK-114 each went through a reject and several rounds and the board showed REVIEW)
- **Tests:** substate_after_a_reject, substate_after_a_new_tip, approved_waiting_for_a_human_names_the_reason, time_in_substate, dashboard_data_groups_by_substate
- **Verify:** `python3 kit/.uak/tests/test_review_substates.py`
- **Next step:** the REVIEW rows in kit/.uak/bin/lib/status.sh and `build()` in kit/.uak/bin/lib/dash.py:~133

## UAK-120 · A task's whole story: `uak timeline ID`, and a click on its card

- **Type:** feature
- **Priority:** P1
- **Estimate:** 4 h
- **Depends on:** UAK-117, UAK-119
- **Paths:** kit/.uak/bin/timeline, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/bin/lib/dash.py, kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_task_timeline.py
- **Acceptance:** `uak timeline ID [--json]` prints every move of a task in order, from claims and its history: planned and amended (by whom), claimed, each checkpoint, red recorded, done (PR, evidence), each review (reviewer, model, verdict, the reason of a reject, the SHA), each new tip after a reject with the files it changed, CI results when pr-sync has them, the merge or the human queue with its reason, integrate (and `Unreviewed`), handovers, expired leases and takeovers; each line with its time, the gap since the previous one, the agent, its model and harness, the totals at the end: hours in each state and sub-state, review rounds, agents and models that took part, commands and errors (from the ledger), tokens when published, the dashboard: clicking a card opens the task's story as a vertical timeline with the same lines, colored by kind of move, rejects and human steps standing out, with the sub-state durations as a bar on top; it works from file:// like the rest of the page (data embedded, no server), and Escape or a click outside closes it, a task with no history yet says so; a task from before the model was recorded shows `unknown`, not a guess, Why (the human, 2026-11-21: "presionar sobre una tarea debe mostrar todo el mapa de agentes y movimientos de la tarea súper bien explicado para realmente poder auditar")
- **Tests:** timeline_orders_every_move, a_reject_shows_reason_and_the_next_tip, totals_match_the_lines, json_has_stable_keys, dashboard_embeds_the_timeline
- **Verify:** `python3 kit/.uak/tests/test_task_timeline.py`
- **Next step:** the worklog and event readers in kit/.uak/bin/lib/dash.py (`snapshot`, `build`) and the card markup in kit/.uak/bin/lib/dash.html

## UAK-121 · "I had to do this by hand": manual steps are recorded and counted

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-116, UAK-118
- **Paths:** kit/.uak/bin/bb, kit/.uak/bin/hook, kit/.uak/tests/test_manual_notes.py
- **Acceptance:** `uak bb note manual "what I did by hand" --fix "what the kit should do"` records a note of kind `manual` (next to friction, bug, idea, need), with the task and the command that was missing when given, the output hook recognizes the manual moves the black boxes show most: `git worktree add` in a kit repo, a commit on the base branch from the main checkout (the pre-commit log already has them), `gh pr merge` run by a human after MERGE_HUMAN, a `git push` of claims refused by the guard. Each becomes one `manual` line (auto), at most one per kind per session, AGENTS.md is not touched: the rule that asks for the note is one line in the text `uak bb` prints after a refused or failed command that has a known manual workaround, Why (the human, 2026-11-20: "en qué se tuvo que hacer algo que no estaba en el kit"; harvest 2026-11: "had to git worktree add by hand"): work outside the kit was visible only as "Direct to main: 130 of 222" with no reason
- **Tests:** manual_note_is_recorded_with_task, worktree_add_by_hand_is_noticed_once, human_merge_after_merge_human_is_counted
- **Verify:** `python3 kit/.uak/tests/test_manual_notes.py`
- **Next step:** the note kinds in kit/.uak/bin/bb and the output hook in kit/.uak/bin/hook:~657

## UAK-122 · Tokens per task and per step, also when the session started somewhere else

- **Type:** bug
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/tokens, kit/.uak/tests/test_tokens_elsewhere.py
- **Acceptance:** a transcript whose session started outside the repo counts for the project when its tool calls ran in the main checkout or in a worktree under `<repo>-wt/` (the cwd of the calls, not only the cwd of the session); its subagent transcripts are attributed to the task whose worktree they worked in, tokens are split per step of a task: author work, review, merge gate and lead/coordination, from the worktree and the commands the transcript ran (`uak review`, `uak merge`); `uak tokens --by step` prints it and `--publish` includes it, `Token-Budget: N` in PROJECT.md (per task): `uak next` and `uak status --task` warn when a task's published tokens cross it; no budget, no warning, the transcripts' content is never copied: only counts, model names and task IDs leave the machine (as today), Why (audit §1, 2026-11-20): `uak tokens` answered "no transcripts of this project found" in the kit's own repo, because every session that drives it starts in the home directory; so the cost per task of the kit's own development was unknown
- **Tests:** a_session_started_elsewhere_counts, subagent_tokens_go_to_their_task, tokens_by_step, budget_warns_once_crossed, no_content_leaves_the_machine
- **Verify:** `python3 kit/.uak/tests/test_tokens_elsewhere.py`
- **Next step:** the "a transcript belongs to this project" rule at the top of kit/.uak/bin/tokens

## UAK-123 · `uak autopsy`: the report of an event, written from claims

- **Type:** feature
- **Priority:** P2
- **Estimate:** 3 h
- **Depends on:** UAK-120
- **Paths:** kit/.uak/bin/autopsy, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_autopsy.py
- **Acceptance:** `uak autopsy [--since DATE] [--until DATE] [--out FILE] [--claims DIR]` writes one markdown file in the shape of docs/blackbox/*.md: the facts table (kit version, mode, harnesses and models, machines, tasks by final state, commits on the base outside tasks, black box lines, tokens), the `uak metrics` numbers, the ten most repeated errors with their counts, every agent note verbatim marked as untrusted data, the slowest and the most-reviewed tasks with their timelines in short form, and a last section "Findings" left with one line per repeated issue for a human or an agent to complete, it reads claims only (or `--claims DIR`, an extracted checkout, for another repo's event) and runs nothing from it, names of people and repos stay as they are in claims for the team's own report; `--anonymous` replaces agent and human names with roles and drops repo names (for a public autopsy), Why (the human, 2026-11-20: "cuando hagamos la autopsia sea más fácil identificar qué pasó"): each autopsy in docs/blackbox/ was assembled by hand from five commands
- **Tests:** autopsy_has_the_facts_table, top_errors_are_counted, notes_are_marked_untrusted, anonymous_hides_names, reads_an_extracted_claims_dir
- **Verify:** `python3 kit/.uak/tests/test_autopsy.py`
- **Next step:** kit/.uak/bin/stats and scripts/blackbox_harvest.py (what they already count)

## UAK-124 · A pre-push hook that reads the real ref, and the guard reads Mode like the engine

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.githooks/pre-push, kit/.uak/bin/guard, install.sh, kit/.uak/tests/test_pre_push.py
- **Acceptance:** `kit/.githooks/pre-push` reads the refs git is about to push (its stdin) and refuses a push by an agent to the base branch or to the claims branch from outside the engine, with the same reasons as the guard; the engine's own pushes (merge gate, transactions) pass (they set a marker the hook checks), and a human passes with the documented override (`UAK_DIRECT_MAIN=1`, as pre-commit), the installer puts it next to pre-commit under the same rules (another hook manager keeps its hooks; the kit says how to add the check), `guard` reads `Mode` trimmed and case-insensitively, like UAK-114's reader, Why (v6.6 review of UAK-111): the guard reads text, so a ref built by an arbitrary command, or a script written to a file and then run, is not seen; git itself knows the real ref at push time. And `Mode: Marathon` was not marathon for the guard
- **Tests:** push_to_base_is_refused_for_an_agent, push_to_claims_is_refused, engine_pushes_pass, human_override_passes, guard_reads_mode_case_insensitively
- **Verify:** `python3 kit/.uak/tests/test_pre_push.py`
- **Next step:** kit/.githooks/pre-commit (the pattern to copy) and where install.sh places it (~line 285)

## UAK-125 · `uak plan FILE --check`: a plan is validated before a human publishes it

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/plan.sh, kit/.uak/bin/uak, kit/.uak/tests/test_plan_check.py
- **Acceptance:** `uak plan FILE --check` (and `uak plan FILE --amend --check`) runs every validation the publish runs (required fields, ID format and duplicates against main's TASKS.md and the claims backlog, Depends on pointing at existing tasks, Paths overlaps with live claims and with tasks of the same file, OWNERS, a Verify that parses, the amend rules such as a task in REVIEW) and writes nothing: no commit, no push, no message to owners, it needs no UAK_HUMAN: any agent or human may run it; without `--check` the command needs a human as today, it reports every problem of the file in one run, one line per problem naming the task and the field, in the words the publish uses, and exits 0 with `OK plan --check | N tasks would be published` when there is none; the publish itself keeps stopping at its first error (its messages are an API), the output says what it cannot promise: the board can change between the check and the publish, the usage line in commands.tsv is not changed by this task (`--check` is listed in the help text plan.sh prints for a wrong usage); if the registry check needs the flag in commands.tsv, say so in the report instead of widening the scope, Why (2026-11-20 and 21): the v6.5 plan failed at publish on a missing `Depends on` and the human ran the command twice; an amend of UAK-083 was refused for a task in REVIEW; the v6.6 and v6.7 plans were handed to the human unvalidated, because the only way to validate a plan was to publish it, and publishing is the one step reserved to the human
- **Tests:** check_writes_nothing, check_needs_no_human, check_reports_every_problem, check_passes_a_valid_plan, amend_check_names_a_task_in_review
- **Verify:** `python3 kit/.uak/tests/test_plan_check.py`
- **Next step:** plan_mutate in kit/.uak/bin/lib/plan.sh (split the validation from the write) and the UAK_HUMAN requirement for `plan` at kit/.uak/bin/uak:177

## UAK-126 · pre-push lets an agent create the base branch on a remote that does not have it yet (uak demo failed for agents) (follow-up of UAK-124)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-124
- **Follow-up of:** UAK-124
- **Paths:** kit/.githooks/pre-push, kit/.uak/bin/guard, install.sh, kit/.uak/tests/test_pre_push.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - pre-push lets an agent create the base branch on a remote that does not have it yet (uak demo failed for agents)
- **Verify:** `python3 kit/.uak/tests/test_pre_push.py`
## UAK-127 · An install without the kit's own tests, with skills on demand

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/bin/doctor, kit/.uak/bin/smoke, kit/.uak/bin/uak-coordination, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, scripts/kit_hashes.py, kit/.uak/tests/test_install_light.py
- **Acceptance:** `install.sh` no longer copies `kit/.uak/tests/` into a project (112 files, 1.5 MB): a project's `smoke` runs its own checks and the product smoke, and says in one line that the kit's protocol suite runs in the kit's repository. `--with-tests` installs them as today; `--update` removes the kit's test files it recognizes by hash (`known-files.txt`) and keeps any file a team edited or added, the skill library (`.uak/skills/`, 114 files) is not copied whole: the install places only the skills the mode, stack and `--skills` ask for, as today under `.claude/skills` and `.agents/skills`, and `uak skill add NAME` copies one more from the kit's checkout or, with no checkout, from the pinned release (git only, hash-checked like the external skills), a marathon install for Claude Code is under 200 files (was 535, 9.3 MB); the test prints the count and the bytes and fails over the bound, `doctor` does not ask for the test directory, and every command that reads `.uak/tests` or `.uak/skills` works when they are absent, Why (audit of v6.5.0, docs/audit-2026-11.md §1): an install put 535 files and 9.3 MB in a project, of which 108 were the kit's own tests and 114 the skill library; heavy in files, not in context
- **Tests:** install_has_no_kit_tests, with_tests_installs_them, update_removes_only_known_test_files, skill_add_copies_one, marathon_install_under_200_files
- **Verify:** `python3 kit/.uak/tests/test_install_light.py`
- **Next step:** the copy loop at install.sh:107 (`for part in bin docs modes templates tests settings stacks skills`) and the skill placement at install.sh:162-173

## UAK-128 · Windows CI in shards, and one run per commit

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** .github/workflows/test.yml, scripts/kit_lint.py, kit/.uak/tests/test_ci_shards.py
- **Acceptance:** the Windows job runs the test files in shards balanced by each file's measured seconds, as Linux and macOS already do (`kit_lint.py --ci-shards N`), instead of one job per test file; the number of shards is the smallest that keeps the longest shard under 25 minutes with the measured times, and the test computes it from the same table, a push to a branch that has an open pull request does not run the suite twice: the workflow runs on `pull_request` and on pushes to `main` and tags only, a commit on main starts at most 24 jobs (was 121), and a new test file still runs on the three systems with no edit to the workflow, a shard that fails names the test file that failed in its job summary, Why (audit §1): 105 jobs per push and about 200 checks per PR, one job per test file on Windows, on push and again on pull_request; the largest cost in compute, and "every run green" meant reading 121 results
- **Tests:** windows_matrix_is_shards, shards_cover_every_test_file_once, longest_shard_under_the_bound, workflow_runs_once_per_commit
- **Verify:** `python3 kit/.uak/tests/test_ci_shards.py`
- **Next step:** the `windows:` job at .github/workflows/test.yml:67 and `--ci-shards` in scripts/kit_lint.py

## UAK-129 · The reviewer runs Verify and the tests the diff touches; the whole suite runs once, at the merge gate

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/smoke, kit/.uak/bin/lib/tests.sh, kit/.claude/agents/uak-reviewer.md, kit/.uak/modes/sprint.md, kit/.uak/modes/marathon.md, kit/.uak/docs/CLI.md, kit/.uak/tests/test_smoke_affected.py
- **Acceptance:** `smoke --affected [BASE]` runs the lint, the secret scan, the task's Verify and only the test files the diff against BASE touches or names (a test file changed; a test file whose name or imports match a changed engine file; every file when the diff touches `lib/core.sh`, `lib/tx.sh` or the test helpers). It prints which files it chose and why, and how many it left for the gate, the reviewer's instructions and both mode files say: Verify plus `smoke --affected`, and the note of an approval says which was run; the author does the same before `done`, the merge gate keeps running the whole suite on the merged result; nothing an agent sets (an environment variable, a flag) makes the gate run fewer tests, on the kit's own repository the three runs per task become one whole run and two partial ones; the test measures a partial run on a one-file diff under a quarter of the files, Why (audit §1): the suite took 8–10 min and ran three times per task (author, reviewer, gate), the largest cost in time; 152 review rounds in 105 tasks each paid a whole run
- **Tests:** affected_runs_changed_test_files, engine_change_selects_its_tests, core_change_runs_everything, gate_ignores_the_shortcut, prints_what_it_left
- **Verify:** `python3 kit/.uak/tests/test_smoke_affected.py`
- **Next step:** the `UAK_SMOKE_TESTS` selection at kit/.uak/bin/smoke:41-56 and step 26 of kit/.claude/agents/uak-reviewer.md

## UAK-130 · `status` and `next` read one cached fetch of claims

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/cache.sh, kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/net.sh, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_read_cache.py, kit/.uak/tests/test_claims_perf.py
- **Acceptance:** a read command (`status`, `next`, `inbox`, `board`, `timeline`, `metrics`) reuses the last fetch of claims when it is younger than `Read-Cache: N` seconds of PROJECT.md (default 20; 0 turns it off), and says so in its last line ("claims as of 12 s ago"); `--fresh` fetches now, every command that writes (claim, done, review, merge, heartbeat and the rest) fetches as today and refreshes the cache with what it pushed, so an agent always reads its own writes, two reads within the window cost one fetch: the test counts the fetches, and the second `status` takes under half the time of the first on the fixture, the process targets `test_claims_perf` keeps as expected failures are measured again and lowered to what this reaches; `heartbeat` is not a read and stays out of this task, Why (audit §1; `uak metrics`, 2026-11-21): `status` took 3.7 s and `next` 2.3 s, each a fetch of claims, and agents poll 2.7 times per `done`; the ledger measured `status` at a median of 1.9 s over 13 calls
- **Tests:** second_read_reuses_the_fetch, a_write_refreshes_the_cache, fresh_fetches_now, zero_turns_it_off, read_says_how_old
- **Verify:** `python3 kit/.uak/tests/test_read_cache.py`
- **Next step:** the tip-keyed cache in kit/.uak/bin/lib/cache.sh and the fetch in kit/.uak/bin/lib/net.sh

## UAK-131 · `Merge-Engine: ci`: an approved engine change with every check green does not wait for a human

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/config.sh, kit/.uak/bin/lib/github.sh, kit/.uak/bin/doctor, kit/.uak/docs/WHY.md, kit/.uak/docs/CLI.md, kit/.uak/tests/test_merge_engine_policy.py
- **Acceptance:** `Merge-Engine: human` (the default, today's behavior) or `ci` in `.uak/PROJECT.md`, changed only by a human commit on the base. With `ci`, a task whose diff touches a shared path of the engine list (`.uak/bin/uak`, `.uak/bin/lib/`, `.uak/bin/smoke`, `.githooks/`, CI workflows) merges through the gate when: an identity other than the author approved the exact tip, every check of that SHA on the forge finished green (all runs, not the first), the gate's own smoke passed on the merged result, and the task is in sprint mode or `Review-Independence` is satisfied, lock files, migrations, `PROJECT.md` and the smoke provenance file still go to the human with either value; a check still running or not found is "wait", never green, the task record says `Merge-Policy: ci` and names the checks counted; `uak metrics` counts these merges apart from the human-landed ones, `doctor` warns when `Merge-Engine: ci` is set and the base branch has no required checks on the forge, Why (`uak metrics`, 2026-11-21): the gate sent 39 of 39 queued tasks to a human, 38 of them as "Shared resource/CI needs a human"; 46 of 104 integrated tasks were built by the gate and then landed by a person who added no check of their own
- **Tests:** human_is_the_default, ci_merges_when_every_check_is_green, a_running_check_waits, a_red_check_refuses, lock_files_still_need_a_human, record_names_the_policy
- **Verify:** `python3 kit/.uak/tests/test_merge_engine_policy.py`
- **Next step:** the `shared` list and `RM_REASON="Shared resource/CI needs a human"` at kit/.uak/bin/lib/review-merge.sh:628-655

## UAK-132 · `Merge-Commit` names the task's own merge

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/bin/lib/metrics.py, kit/.uak/tests/test_merge_commit_field.py
- **Acceptance:** `integrate` records in `Merge-Commit` the commit on the base that brought this task's tip in (the merge commit whose second parent is the tip or contains it and whose subject or PR names the task; for a squash, the commit whose tree matches), never the tip of the base at the time or another task's merge, when no such commit is found the field says `unknown` and the reason goes in the event, instead of a wrong SHA, `uak metrics` and `uak timeline` use the field again and report how many records they had to classify by history because the field was wrong or unknown; records written before this task are not rewritten, Why (review of UAK-117, 2026-11-21): on UAK-030 and UAK-013 the field named another task's merge, so `metrics` stopped trusting it and classified 104 tasks from the base's history
- **Tests:** integrate_records_its_own_merge, two_tasks_merged_together_get_their_own, squash_is_found_by_tree, unknown_when_not_found, metrics_counts_untrusted_records
- **Verify:** `python3 kit/.uak/tests/test_merge_commit_field.py`
- **Next step:** `put "$RECORD" Merge-Commit "$merged"` at kit/.uak/bin/lib/done.sh:282 and :333, and the note at kit/.uak/bin/lib/metrics.py:203

## UAK-133 · `tokens --since` by message time, and the budget warning where agents look

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-130
- **Paths:** kit/.uak/bin/tokens, kit/.uak/bin/lib/status.sh, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_tokens_window.py
- **Acceptance:** `--since DAYS` counts the messages whose own timestamp is inside the window; a long session file changed today no longer brings in the tokens of last month (today the window picks whole files by modification time), `uak next` and `uak status` print the `TOKENS_BUDGET` line of `tokens --budget-check` for the agent's live task when it crossed `Token-Budget`, once per call, and nothing when no budget is set or no transcript is readable; no extra fetch, totals without `--since` stay byte-identical on the fixture, Why (v6.7.0, left open): one session of several days put its whole spend in a one-day window, and the budget warning existed only as a command nobody calls
- **Tests:** since_counts_by_message_time, an_old_message_in_a_new_file_is_out, next_warns_over_budget, status_warns_over_budget, no_budget_prints_nothing
- **Verify:** `python3 kit/.uak/tests/test_tokens_window.py`
- **Next step:** `find … -mtime "-$since"` at kit/.uak/bin/tokens:71 and :145, and the budget check at kit/.uak/bin/tokens:286

## UAK-134 · REVIEW sub-states in `board` and in `--json status`

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** UAK-133
- **Paths:** kit/.uak/bin/board, kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/json.sh, kit/.uak/docs/CLI.md, kit/.uak/tests/test_review_substates.py
- **Acceptance:** `uak board` prints each REVIEW task's sub-state and the time in it, with the words `uak status` and the dashboard use, `uak --json status` carries `review_substate`, `review_substate_since` and `review_round` for a task in REVIEW, documented in CLI.md; every existing key keeps its name and type, the three surfaces are compared in one test on the same fixture, so they cannot drift, Why (UAK-119's acceptance, v6.7.0): the sub-state reached `status` and the dashboard, and `board` and the JSON output were left out
- **Tests:** board_prints_the_substate, json_status_has_the_substate, three_surfaces_agree
- **Verify:** `python3 kit/.uak/tests/test_review_substates.py`
- **Next step:** `review_substate` at kit/.uak/bin/lib/status.sh:37 and the board's REVIEW column in kit/.uak/bin/board

## UAK-135 · `doctor` and `wt` know the pre-push hook, and never point git at a hooks directory that is not there

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-127
- **Paths:** kit/.uak/bin/doctor, kit/.uak/bin/wt, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/tests/test_hooks_health.py
- **Acceptance:** `doctor` checks the pre-push hook as it checks pre-commit: present, executable, the kit's or calling the kit's (`bash .uak/githooks/pre-push "$@"` from another hook manager), and `--fix` restores the kit's own without overwriting a team's, `wt new` sets `core.hooksPath` only to a directory that exists and holds the kit's hooks; when neither `.uak/githooks` nor `.githooks` is there it leaves the setting alone and says so once, `doctor` fails when `core.hooksPath` names a directory that does not exist (every hook silently off), with the fix in the message, Why (v6.7.0): the kit's own repository had `core.hooksPath=.githooks` with no such directory for weeks, set by `wt`, so neither the secret scan nor the pre-push ran there and nothing said so; `doctor` and `wt` were written before UAK-124 added pre-push
- **Tests:** doctor_checks_pre_push, doctor_fails_on_a_missing_hooks_dir, wt_does_not_point_at_nothing, fix_keeps_a_teams_hook
- **Verify:** `python3 kit/.uak/tests/test_hooks_health.py`
- **Next step:** the hooks block at kit/.uak/bin/doctor:69-82 and `hooks_dir=` at kit/.uak/bin/wt:271

## UAK-136 · The ledger times every command, and `metrics` has no empty rows

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-132
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/lib/ledger.sh, kit/.uak/bin/lib/metrics.py, kit/.uak/tests/test_command_ledger.py, kit/.uak/tests/test_metrics.py
- **Acceptance:** a command the dispatcher starts by replacing the shell (`metrics`, `timeline`, `dash`, `autopsy`, `stats`, `red` and the rest of the `exec` rows) records its exit code and milliseconds like the others, with no extra process when the command is one of the engine's own scripts (the script closes its own ledger line) and at most one otherwise, `uak metrics` prints "errors 0 of 0 · median -" for no command that ran after this task; lines written before it are counted as "outcome not recorded", apart, "commits on the base with no task" is computed inside a `--since` window too (first-parent commits of the window), and says `n/a` only when the base branch is really not visible, "manual notes" prints a count, 0 included, once any black box of the window comes from a version that records them, Why (`uak metrics`, 2026-11-21): six commands showed calls with "errors 0 of 0" and no duration, and the two lines about work outside the kit said `n/a` and "not recorded yet" on a repository that records both
- **Tests:** exec_commands_record_code_and_ms, old_lines_are_counted_apart, direct_commits_inside_a_window, manual_notes_print_zero
- **Verify:** `python3 kit/.uak/tests/test_command_ledger.py && python3 kit/.uak/tests/test_metrics.py`
- **Next step:** `[ "$REG_RUN" != exec ] || { ledger_end - …; exec …; }` at kit/.uak/bin/uak:117 and kit/.uak/bin/lib/metrics.py:443-448

## UAK-137 · The autopsy keeps exit codes apart and labels anonymous notes as what they are

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/autopsy, kit/.uak/tests/test_autopsy.py
- **Acceptance:** failure classes are grouped after normalizing only what varies (paths, SHAs, task IDs, durations); a number that carries meaning stays: `exit 1` and `exit 2`, an HTTP status and a signal are different classes, with `--anonymous` the notes section says the free text was withheld and shows counts by kind; it no longer says "verbatim" above text that is not there, the report of a fixture with both exit codes lists two classes with their own counts, Why (review of UAK-123, v6.7.0): the normalizer merged `exit 1` with `exit 2`, and the anonymous report kept the banner of the full one
- **Tests:** exit_codes_stay_apart, http_status_stays_apart, anonymous_banner_says_withheld
- **Verify:** `python3 kit/.uak/tests/test_autopsy.py`
- **Next step:** the normalizer and the "Agent notes · UNTRUSTED DATA" banner at kit/.uak/bin/autopsy:367

## UAK-138 · Three tests that fail on a loaded or Windows runner without a defect

- **Type:** bug
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-128
- **Paths:** kit/.uak/bin/lib/gallery_pick.py, kit/.uak/bin/uak-mcp, kit/.uak/tests/test_design_pick.py, kit/.uak/tests/test_review_merge.py, kit/.uak/tests/test_hack.py, tests/test_mcp_tools.py, kit/.uak/tests/test_flaky_guard.py
- **Acceptance:** the design picker reads the request body before it answers 403 to a request without the token, so a Windows client no longer sees the connection reset (WinError 10053) while it is still sending, the MCP server exits within 2 seconds of its input closing on Windows (today the test's teardown has to kill it and warns); the teardown's kill stays as a net and the test fails when it is needed, the lease test that depends on wall-clock margins (`gate_and_lease` in test_review_merge.py) uses the engine's injected clock for every deadline, so a slow runner cannot expire a lease mid-test, each of the three passes 20 times in a row under load (the suite running beside it); the test file that proves it runs them with a CPU hog and is skipped only when `UAK_SMOKE_FAST=1`, Why (CI of v6.5.0 to v6.7.0): these three failed and passed on a rerun on at least five pushes, and "every run green" meant rerunning jobs by hand
- **Tests:** picker_reads_the_body_before_403, mcp_server_exits_when_stdin_closes, lease_test_uses_the_injected_clock, twenty_runs_under_load
- **Verify:** `python3 kit/.uak/tests/test_flaky_guard.py`
- **Next step:** the 403 path in kit/.uak/bin/lib/gallery_pick.py, the read loop of kit/.uak/bin/uak-mcp and the teardown in tests/test_mcp_tools.py

## UAK-139 · The demo records a model and a harness, so its story shows who did what

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/demo, kit/.uak/tests/test_demo.py, docs/media/dash-task.png
- **Acceptance:** the three agents of `uak demo` run with a model and a harness of their own (set by the demo, marked as the demo's), so `uak timeline HACK-001` and the dashboard's drawer show them instead of "model unknown · harness unknown", the demo's printed lines and its duration stay as they are; `docs/media/dash-task.png` is captured again from the demo, Why (2026-11-21, the README capture): the first thing a new user opens showed "unknown" eight times in the feature v6.7 added
- **Tests:** demo_timeline_names_models, demo_output_unchanged
- **Verify:** `python3 kit/.uak/tests/test_demo.py`
- **Next step:** where the demo sets each agent's environment in kit/.uak/bin/demo

## UAK-140 · find_merge_commit compares trees from one git log, not one process per commit (2000 commits with a stale tip: 1995 git calls, 45 s) (follow-up of UAK-132)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-132
- **Follow-up of:** UAK-132
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/bin/lib/metrics.py, kit/.uak/tests/test_merge_commit_field.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - find_merge_commit compares trees from one git log, not one process per commit (2000 commits with a stale tip: 1995 git calls, 45 s)
- **Verify:** `python3 kit/.uak/tests/test_merge_commit_field.py`

## UAK-141 · A seventh Windows shard: the longest took 23m55s of a 25 min bound; the lint also flags a bare push: with no branches filter (follow-up of UAK-128)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-128
- **Follow-up of:** UAK-128
- **Paths:** .github/workflows/test.yml, scripts/kit_lint.py, kit/.uak/tests/test_ci_shards.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - A seventh Windows shard: the longest took 23m55s of a 25 min bound; the lint also flags a bare push: with no branches filter
- **Verify:** `python3 kit/.uak/tests/test_ci_shards.py`

## UAK-142 · The read cache's lock is taken over atomically: clearing a dead holder's lock let two writers into the critical section (15-20 of 1,200 acquisitions with dead locks planted) (follow-up of UAK-130)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-130
- **Follow-up of:** UAK-130
- **Paths:** kit/.uak/bin/lib/cache.sh, kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/net.sh, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_read_cache.py, kit/.uak/tests/test_claims_perf.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - The read cache's lock is taken over atomically: clearing a dead holder's lock let two writers into the critical section (15-20 of 1,200 acquisitions with dead locks planted)
- **Verify:** `python3 kit/.uak/tests/test_read_cache.py`

## UAK-143 · tokens: the budget scan runs in the background (a cold read added 4.5 s to status once per 5 min); a malformed timestamp counts like a missing one; a negative Token-Budget is refused; --since 0 and the mtime pre-filter documented (follow-up of UAK-133)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-133
- **Follow-up of:** UAK-133
- **Paths:** kit/.uak/bin/tokens, kit/.uak/bin/lib/status.sh, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_tokens_window.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - tokens: the budget scan runs in the background (a cold read added 4.5 s to status once per 5 min); a malformed timestamp counts like a missing one; a negative Token-Budget is refused; --since 0 and the mtime pre-filter documented
- **Verify:** `python3 kit/.uak/tests/test_tokens_window.py`

## UAK-144 · The CI timing table is measured again: Windows shards 5 and 6 took 34m39s and 26m59s against a predicted 20.4 min, macOS 4 took 25m31s (follow-up of UAK-128)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-128
- **Follow-up of:** UAK-128
- **Paths:** .github/workflows/test.yml, scripts/kit_lint.py, kit/.uak/tests/test_ci_shards.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - The CI timing table is measured again: Windows shards 5 and 6 took 34m39s and 26m59s against a predicted 20.4 min, macOS 4 took 25m31s
- **Verify:** `python3 kit/.uak/tests/test_ci_shards.py`

## UAK-145 · board reads the review lease from the fetched config and honours UAK_LEASE_SECONDS, so board and status agree on the OVER mark; a tab in a queue reason or reviewer name does not break review_substate_since (follow-up of UAK-134)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-134
- **Follow-up of:** UAK-134
- **Paths:** kit/.uak/bin/board, kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/json.sh, kit/.uak/docs/CLI.md, kit/.uak/tests/test_review_substates.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - board reads the review lease from the fetched config and honours UAK_LEASE_SECONDS, so board and status agree on the OVER mark; a tab in a queue reason or reviewer name does not break review_substate_since
- **Verify:** `python3 kit/.uak/tests/test_review_substates.py`

## UAK-146 · doctor compares hook dirs with -ef instead of lowercase text (a different .UAK/githooks is not the kit's on a case-sensitive disk); wt new does not replace a valid core.hooksPath of another hook manager (follow-up of UAK-135)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-135
- **Follow-up of:** UAK-135
- **Paths:** kit/.uak/bin/doctor, kit/.uak/bin/wt, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/tests/test_hooks_health.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - doctor compares hook dirs with -ef instead of lowercase text (a different .UAK/githooks is not the kit's on a case-sensitive disk); wt new does not replace a valid core.hooksPath of another hook manager
- **Verify:** `python3 kit/.uak/tests/test_hooks_health.py`

## UAK-147 · the dashboard computes the review lease like status and board: UAK_LEASE_SECONDS, else Lease-Seconds (default 1800, no marathon default), Review-Lease-Seconds else 4 times the lease, so the late mark agrees with the OVER mark in a default setup (follow-up of UAK-119)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-119
- **Follow-up of:** UAK-119
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/dash.py, kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_review_substates.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - the dashboard computes the review lease like status and board: UAK_LEASE_SECONDS, else Lease-Seconds (default 1800, no marathon default), Review-Lease-Seconds else 4 times the lease, so the late mark agrees with the OVER mark in a default setup
- **Verify:** `python3 kit/.uak/tests/test_review_substates.py`
## UAK-148 · A generated file does not send a task to the human: the gate checks it against its generator

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/config.sh, kit/.uak/docs/CLI.md, kit/.uak/docs/WHY.md, kit/.uak/tests/test_gate_scope.py
- **Acceptance:** PROJECT.md on the base branch may name generated files, one per line: `Generated: PATH = COMMAND` (for this repository: `Generated: kit/.uak/settings/known-files.txt = python3 scripts/kit_hashes.py`). The key is read from the base tip the candidate is built on, never from the branch under review, as `Merge-Engine` is, a task that changes a generated file outside its Paths is not flagged by `uak done` (no `SCOPE?` line for that file) and is not sent to the human by the merge gate for that file alone, the gate does not trust the file's content: on the merged result it runs COMMAND in the gate's own checkout and requires the file to be byte-identical afterwards; when it differs the merge is refused with a reason that names the file and the command, and nothing lands. COMMAND runs with the gate's environment and time limit, and a COMMAND that fails or is missing refuses the merge, a generated path that is also a shared resource of the human (a lock file, a migration, PROJECT.md, a workflow, a hook, one of the gate's own files) stays the human's: `Generated:` never releases those, and `doctor` warns about such a line, with no `Generated:` line every behaviour is as today, Why (v6.8, 21 tasks): every task's PR changed `known-files.txt` (regenerated by `kit_hashes.py`), `uak done` flagged it each time and the gate answered MERGE_HUMAN "Edits a file outside Paths" for tasks with no other reason; after each merge a person regenerated the file by hand
- **Tests:** generated_file_is_not_out_of_scope, gate_refuses_a_generated_file_that_differs, generated_never_releases_a_human_file, generated_key_is_read_from_the_base, no_key_no_change
- **Verify:** `python3 kit/.uak/tests/test_gate_scope.py`
- **Next step:** the scope pass at kit/.uak/bin/lib/review-merge.sh:755 (the awk over `merge-list`) and the `SCOPE?` hint at kit/.uak/bin/lib/done.sh:440; add the tests to the existing test_gate_scope.py so no new timing entry is needed

## UAK-149 · `Merge-Engine: ci` with two approvals releases the engine's libraries

- **Type:** feature
- **Priority:** P1
- **Estimate:** 4 h
- **Depends on:** UAK-148
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/doctor, kit/.uak/docs/CLI.md, kit/.uak/docs/WHY.md, kit/.uak/tests/test_merge_engine_policy.py
- **Acceptance:** `Merge-Engine-Approvals: 2` in PROJECT.md on the base branch, with `Merge-Engine: ci`, lets the gate merge a change to a library of the engine that the gate loads (`kit/.uak/bin/lib/*.sh`, `*.awk`, `*.tsv`) when all of these hold on the exact tip: the required checks are green as `ci` already demands; two registered reviewers, different from each other and from the author, have an approve verdict recorded for that SHA; no reject for that SHA is newer than an approve, never released, whatever the key says: the gate's own files (the four the human kept in UAK-131: read the list in WHY.md and in `rm_released_lib`), `bin/uak`, `uak-coordination`, `.github/`, the hooks and `guard`, `smoke` and `secret-scan`, lock files, migrations, PROJECT.md, symlinks. The test lists them one by one, with one approval, or with the key absent, 1 or unreadable, the released set is exactly today's (the lib files the gate does not load); the default policy `human` is unchanged, a second approval by the same identity, by the author, by an unregistered reviewer, or for an older SHA does not count; an approval followed by a new tip does not count, `uak status --task ID` and the gate's refusal say how many approvals of the tip exist and how many the policy needs; `doctor` explains the key and warns when it is set without `Merge-Engine: ci` or without two registered reviewers, Why (`uak metrics`, v6.8): with `ci` releasing nine files, the merges of v6.8 that waited for a human were for `status.sh`, `cache.sh`, `json.sh`, `review-merge.sh` and the workflow; the human who landed them added no check beyond the review and the CI. Two independent approvals are the added check a library loaded into the gate asks for
- **Tests:** two_approvals_release_a_loaded_lib, one_approval_releases_only_todays_set, gate_files_are_never_released, same_identity_twice_counts_once, approval_of_an_older_sha_does_not_count, status_says_how_many_approvals
- **Verify:** `python3 kit/.uak/tests/test_merge_engine_policy.py`
- **Next step:** `rm_released_lib` and `shared_kind` at kit/.uak/bin/lib/review-merge.sh:726-790; the reviews of a task live in `reviews/ID.md` on the claims branch

## UAK-150 · No single test file takes a whole shard: `test_flaky_guard` is two files, and the lint says when a file is too long

- **Type:** fix
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/tests/test_flaky_guard.py, kit/.uak/tests/test_flaky_guard_race.py, scripts/kit_lint.py, kit/.uak/tests/test_ci_shards.py
- **Acceptance:** `test_flaky_guard.py` (1500 s on Windows, 508 s on macOS, alone in a shard 15 s under the planned bound) becomes two files with the same cases and the same run counts (`RUNS = 20`, `RACE_RUNS = 60`): the renewer race in `test_flaky_guard_race.py`, the rest where it is. No case is dropped and no count is lowered; shared helpers are imported, not copied, both files have measured entries in `CI_SECONDS` and `CI_WINDOWS_SECONDS`, taken from the task's own CI run, and the longest Windows shard is predicted at least 2 minutes under the margin (0.85 of the bound), the lint refuses a test file whose Windows time is over half of `WINDOWS_BOUND_S` and says to split it, and reports a timing entry whose test file no longer exists; when a file is missing from both tables the message names both, the number of jobs per commit does not grow (18 today), Why (UAK-144, 2026-11-22): 11 Windows samples of `test_flaky_guard` ran 1232 to 1628 s; one update of its entry to 1550 s turns `test_ci_shards` red and forces the bound up again. A stale entry and the one-table wording were found by the review of UAK-144
- **Tests:** flaky_guard_cases_are_all_kept, no_file_over_half_the_bound, stale_timing_entry_is_reported, message_names_both_tables
- **Verify:** `python3 kit/.uak/tests/test_ci_shards.py`
- **Next step:** `engine_renewer_never_runs_the_owners_cleanup` at kit/.uak/tests/test_flaky_guard.py:122 and `timing_problems` in scripts/kit_lint.py; moving test lines needs `uak allow UAK-150 --tests` from the human

## UAK-151 · twenty_runs_under_load runs as three cases, one per kind of job (picker, mcp, lease), so no test file is excepted from the half-bound rule for flaky_guard; the test of the split proves the load (jobs, hogs, workers), not only the case names; the race file's Windows entry is measured again (follow-up of UAK-150)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-150
- **Follow-up of:** UAK-150
- **Paths:** kit/.uak/tests/test_flaky_guard.py, kit/.uak/tests/test_flaky_guard_race.py, scripts/kit_lint.py, kit/.uak/tests/test_ci_shards.py
- **Freeze-Allowed:** no
- **Acceptance:**
  - twenty_runs_under_load runs as three cases, one per kind of job (picker, mcp, lease), so no test file is excepted from the half-bound rule for flaky_guard; the test of the split proves the load (jobs, hogs, workers), not only the case names; the race file's Windows entry is measured again
- **Verify:** `python3 kit/.uak/tests/test_ci_shards.py`
## UAK-152 · The visual setup and the unified dashboard come in: the contributed branch is merged onto v6.8 with its history

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** None
- **Test-First:** no (a merge of a contribution that brings its own tests; the task adds no behaviour of its own)
- **Paths:** .github/workflows/test.yml, CHANGELOG.md, README.md, install.sh, docs/, kit/, scripts/
- **Acceptance:** the branch of the third delivery (commit `8c9e2f17`, which contains the first two; fetch it with `git fetch https://github.com/DylanMCDS/upiixia-agentic-kit.git pull/52/head`) is merged into the task's branch with a merge commit, so the contributor's 201 commits and authorship stay in the history; nothing is squashed or rebased, conflicts are resolved keeping both sides' behaviour: `hook` keeps the background session start and prints main's "claims as of N s ago" line; `status.sh` keeps `budget_note`, `rc_age_line` and the reviewer-aware `next`; `dash.py` and `dash.html` keep the REVIEW sub-states and the single lease rule of v6.8 and gain the profiles, the offline mode and `Live-URL`; `CLI.md` lists the fields of both sides, decided by the human (2026-11-22), applied here: CI stays as on main (18 jobs per commit, macOS on pull requests); the contributed `exclude` of macOS, `ci_once_problems` and `test_ci_light.py` are not taken, and the check that the workflow has `workflow_dispatch` moves into main's lint; `install.sh` keeps main's handling of tests (`--with-tests`, pruning by known hash) and never runs `rm -rf .uak/tests`; the tutorial video and its poster and captions are not copied into a project (the wizard shows them from the kit's checkout when it is there, and a link otherwise); the design lock stays for events under 24 h, and the task cap by hours and people is taken, task IDs that collide with main are renumbered everywhere they appear (changelog, WHY.md, tests, comments): the contributed UAK-009…013, 038, 067…069 and 087…096 get new numbers from UAK-170 on, listed in one table in the changelog entry; UI-001…024 keep their numbers. WHY.md rows state the rule and its reason without naming who decided; the changelog credits the contributor, every new test file has an entry in `CI_SECONDS` and `CI_WINDOWS_SECONDS` measured in the task's own CI run, no file is over half of `WINDOWS_BOUND_S` (split it, do not add an exception), the longest Windows shard stays under the margin, and the job count stays 18, `kit_lint`, `kit_hashes`, `gen_registry` and the whole smoke pass on Linux, macOS and Windows; a marathon install stays under 270 files, main is not released between this task and UAK-153: the wizard still performs the human's acts unguarded until then
- **Verify:** `python3 scripts/kit_lint.py && python3 kit/.uak/tests/test_ci_shards.py && python3 kit/.uak/tests/test_install_light.py && python3 kit/.uak/tests/test_setup_wizard.py`
- **Next step:** `git merge --no-ff 8c9e2f17`; nine files conflict (`test.yml`, `CHANGELOG.md`, `install.sh`, `hook`, `dash.html`, `dash.py`, `status.sh`, `CLI.md`, `known-files.txt`); regenerate `known-files.txt` last

## UAK-153 · The wizard acts for the human only when a human runs it

- **Type:** fix
- **Priority:** P0
- **Estimate:** 5 h
- **Depends on:** UAK-152
- **Paths:** kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/setup.html, kit/.uak/bin/guard, kit/.uak/docs/WHY.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, kit/.uak/tests/test_setup_trust.py
- **Acceptance:** `setup.py` (and so `install.sh --wizard`) refuses to start when the process has an agent identity: `UAK_AGENT` set, a `.uak-env` naming an agent, `uak.agent` in the git config, or a checkout that is an agent's worktree. The refusal names the reason and how a human starts it, `guard` blocks an agent's command that starts the wizard (`setup.py`, `install.sh --wizard`) or that sends a request to a local wizard, in every mode, as it blocks a command that sets `UAK_HUMAN`, the session token is never printed and never appears in a process's arguments: the browser is opened on a one-time code that the server exchanges, once, for the session; the printed line carries no secret. A session idle for 30 minutes ends, and the terminal says how to open a new one, the human's name is not free text from the page: it is the git identity of the checkout, shown, not typed; a request that names another is refused, registering a reviewer, approving a plan and publishing the kit go through the engine's own commands where one exists, and each writes one line to `uak-direct-main.log` (what, who, when, the commit), as a human's direct push does, a page of another origin, a request with a wrong Host and a request without the session are refused as today, Why (audit, 2026-11-22): an agent could start the wizard, read the token from its own output, name any human and register a reviewer, approve a plan and push to main; the server strips `UAK_*`, so the pre-push hook saw no agent. WHY.md: "Human authority only from the shell"
- **Tests:** agent_identity_cannot_start_the_wizard, guard_blocks_an_agent_starting_the_wizard, token_is_not_printed_or_in_argv, one_time_code_works_once, idle_session_ends, human_name_is_the_git_identity, human_acts_are_logged
- **Verify:** `python3 kit/.uak/tests/test_setup_trust.py`
- **Next step:** `run_command` and the token in kit/.uak/bin/lib/setup.py (search `token_urlsafe`, `UAK SETUP`, `safe_environment`); the POST dispatcher lists the three acts (`/api/team/reviewer`, `/api/plan/approve`, `/api/publish-kit`)

## UAK-154 · A newer kit blocks a published project only on a major version

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-152
- **Paths:** kit/.uak/bin/start, kit/.uak/docs/CLI.md, kit/.uak/tests/test_start_version_gate.py
- **Acceptance:** in a project whose kit is already on the team's base branch (or with `Freeze-Epoch` set), a newer release with the same major version is a note that does not block `uak start`; a newer major version is a `need` that blocks until the kit is updated, and says which version and how, a project that has not published the kit yet is blocked by any newer release, as before the contribution, `UAK_KIT_PIN` behaves as today; versions are compared as numbers (`6.10.0` is newer than `6.9.0`), and an unreadable version blocks nothing and says so
- **Tests:** same_major_is_a_note, newer_major_blocks_a_published_project, unpublished_project_is_blocked_by_any_release, versions_compare_as_numbers
- **Verify:** `python3 kit/.uak/tests/test_start_version_gate.py`
- **Next step:** the version check in kit/.uak/bin/start (search `VERSION` and `not blocking`)

## UAK-155 · `done --pr none` is tested under every review mode, and the generated smoke does not trust file names

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-152
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/tests/test_done_without_github.py, kit/.uak/tests/test_smoke_onboarding.py
- **Acceptance:** a task finished with `--pr none` is never merged without an approval of its exact tip by another registered identity, in `Review-Mode` claims, gh and auto; under `Merge-Engine: ci` it goes to the human (the required checks need a pull request), with a reason that says so, `UAK_REVIEW_MODE` in the environment never lets `--pr none` through on a repository whose base PROJECT.md says `Review-Mode: gh`, the boot command that `init-smoke` generates never interpolates a file or package name into a shell string: a name with a quote, a space, `;` or `$(` is passed as an argument or refused, and the generated smoke says which
- **Tests:** pr_none_still_needs_an_approval, pr_none_goes_to_the_human_under_merge_engine_ci, env_review_mode_does_not_override_the_base, smoke_boot_does_not_run_a_file_name
- **Verify:** `python3 kit/.uak/tests/test_done_without_github.py && python3 kit/.uak/tests/test_smoke_onboarding.py`
- **Next step:** `done_no_pr_check` in kit/.uak/bin/lib/done.sh and `boot`/`detect` in kit/.uak/bin/lib/smoke-init.sh

## UAK-156 · The wizard is one process that ends by itself, and an open page costs nothing while nothing happens

- **Type:** fix
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-153
- **Paths:** kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/planning.py, kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/dash.py, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_setup_processes.py
- **Acceptance:** one server per project: a start records its pid and port under the git directory; a second start for the same project checks that the first answers and opens that one, and starts nothing; a stale record (dead pid, port not answering) is replaced, the server ends by itself: 15 minutes with no request, or the page closed (the page says so on `pagehide`) and no action running; SIGTERM, SIGHUP and Ctrl-C end it too. The terminal prints why it ended and the one command that opens it again. The port is free at once, no child outlives the server: every child (git, `uak`, `install.sh`, the planner `claude`/`codex`) is in a group the server records and kills on every exit path, on Linux, macOS and Windows; on Linux a child also dies when the server is killed with SIGKILL (parent-death signal); a start reaps what a killed server left, from the record. The planner's time limit is 10 minutes, not 30, no timer runs the readiness check: `/api/check` runs when the page loads, after an action of the user, and on a button; never every 60 s, every poll stops while the page is hidden and backs off while nothing changes (20 s, 60 s, 120 s); progress of a running action may poll every 1.2 s only while that action runs, the dashboard's data inside the wizard imports `dash.py` once per server, and when the claims tip did not move a refresh costs one `git ls-remote` and nothing else, the standalone dashboard keeps main's model (a file under the git directory, opened from `file://`, no server, no port); the wizard shows that same page and never needs a second process for it, measured in the test with a counting `git` in PATH: a visible idle page on any wizard screen starts 0 processes in 60 s after its first load (950 before); the dashboard screen at most 3 `git` per minute when nothing moved (18 before); 200 quick requests leave no extra thread after 30 s, Why (measured 2026-11-22): one `/api/check` costs about 950 forks and 1.25 CPU-s and ran every minute for ever; two starts gave two servers on two ports, neither ended; a planner survived SIGTERM, SIGKILL and SIGHUP of the server with PPID 1
- **Tests:** second_start_reuses_the_first, idle_server_ends, closed_page_ends_the_server, no_child_survives_sigterm, no_child_survives_sigkill_on_linux, stale_record_is_reaped, idle_page_starts_no_process, hidden_page_does_not_poll, dashboard_refresh_is_one_ls_remote
- **Verify:** `python3 kit/.uak/tests/test_setup_processes.py`
- **Next step:** `run_command` (`start_new_session=True`) and `main()` (`serve_forever`) in kit/.uak/bin/lib/setup.py; `autoCheck` (`setInterval(...,60000)`) and `loadDashboard` (`setTimeout(...,20000)`) in setup.html; `PLAN_TIMEOUT` in planning.py. A new test file needs its entries in both timing tables

## UAK-157 · The hook's background start cannot hang or pile up

- **Type:** fix
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-152
- **Paths:** kit/.uak/bin/hook, kit/.uak/tests/test_hook_session_start_speed.py
- **Acceptance:** the background worker of a session start has a time limit (60 s): a `git` that hangs is killed with its children and leaves no process with PPID 1, `pace` and `map build` started by the hook are single-flight like `next`: ten session starts in ten seconds run each at most once, the foreground waits only when there is no cached copy to show; with a cached copy the hook answers without waiting for the network, and says how old the copy is
- **Tests:** hung_worker_is_killed, pace_and_map_run_once_under_ten_starts, cached_start_does_not_wait
- **Verify:** `python3 kit/.uak/tests/test_hook_session_start_speed.py`
- **Next step:** `start_bg` in kit/.uak/bin/hook (`trap '' HUP`, no timeout; `UAK_START_WAIT`)

## UAK-158 · One design system: the wizard is drawn with the dashboard's tokens, and `design-lint` reads HTML

- **Type:** feature
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-156
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/dash.html, kit/.uak/bin/design-lint, kit/.uak/media/, docs/DASHBOARD.md, docs/design/, scripts/kit_lint.py, kit/.uak/tests/test_setup_design.py
- **Acceptance:** `setup.html` and `dash.html` declare the same custom properties with the same values in light and dark (page, surface, raised, ink, ink-2, muted, line, accent, accent-ink, critical, shadow, mono, radii): the set is the direction the human chose from the three shown to them, recorded in `docs/design/DIRECTION.md` on main before this task starts (palette, type, radii, spacing, in light and dark); the wizard's own palette, its 20 px radius and its three hard-coded shadows go. A test compares the two `:root` blocks and fails on any difference, outside `:root` no colour literal remains in either file; the wizard uses at most 6 font sizes and one spacing scale (4, 8, 12, 16, 24, 32, 48), the radii and the body size of the chosen direction, one shadow token, `design-lint` applies its rules to `.html` (inline `<style>` and `style=`), not only the two scale checks: colour literals outside `:root`, coloured side stripes, glass, glow, emoji and glyphs used as icons (`✓ ✗ ! •` included), more than 6 font sizes, more than one primary button visible in a view. Both pages pass with `--strict`, with no finding suppressed, status marks are inline SVG icons with a text label, never a glyph; a disabled control keeps 4.5:1 for its label (2.9:1 today); every text/background pair of the tokens is at least 4.5:1 in both themes, computed by the test, the tutorial's poster and its frames use the kit's palette (no purple glow), screenshots at 1280 and 390, light and dark, of every screen are in `.uak-shots/UAK-158/` with the design critic's `VERDICT: SHIP` for the task's commit, Why (2026-11-22): the two pages share no colour value; the wizard frames the blue dashboard inside a green page; `design-lint` printed PASS for both because it does not read HTML (a copy renamed `.js` gave 40 findings)
- **Tests:** wizard_and_dashboard_share_tokens, no_colour_literal_outside_root, six_font_sizes_one_spacing_scale, design_lint_reads_html, every_pair_has_contrast, disabled_label_is_readable
- **Verify:** `python3 kit/.uak/tests/test_setup_design.py && bash kit/.uak/bin/design-lint --strict kit/.uak/bin/lib/setup.html kit/.uak/bin/lib/dash.html`
- **Next step:** `:root` in setup.html (lines 13-28 and 657-702 of the contributed file) against dash.html lines 12-47; existing tests that assert the old colours or classes need `uak allow UAK-158 --tests` from the human

## UAK-159 · The wizard's flow: ten screens, one job each, and it covers what the kit does today

- **Type:** feature
- **Priority:** P0
- **Estimate:** 12 h
- **Depends on:** UAK-158
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, docs/DASHBOARD.md, kit/.uak/tests/test_setup_forms.py, kit/.uak/tests/test_setup_guide.py, kit/.uak/tests/test_setup_resume.py, kit/.uak/tests/test_setup_first_run.py
- **Acceptance:** the flow approved by the human (2026-11-23), one screen per job, each with one primary button: (1) Your project: what was detected (folder, new or existing repository, a hook manager such as husky or lefthook, CI, the project's own tests, the stack) and the mode proposed with its reason; the tools are chosen here. (2) Install: what will be written, how many files, and how the kit's hooks live beside the team's. (3) Unblock: only when something fails, one problem at a time with its fix. (4) How your team will work: the project's rules in plain words with the mode's defaults (`Test-First`, review with or without GitHub, `Review-Independence`, `Merge-Engine`, generated files, the token budget), details under "Advanced"; it writes nothing the human did not confirm. (5) People: the human's identity, reviewers, roles. (6) Schedule: only in Hackathon mode. (7) Publish the kit. (8) Idea and plan: the idea, the design direction when the project has screens (the creativity index and the design lock), the plan, the approval. (9) Start: the command for each agent; the screen says when the first agent has claimed a task. (10) Dashboard: from here, deployment (`uak deploy`, the smoke that boots the app, `Live-URL`), external skills (`uak skill add`) and "Close the wizard", which ends the server, a project that already has the kit opens on the screen it needs; an older kit opens "Update", a path of its own, never an alarm heading over another screen, there is no welcome screen, no slogan, no eyebrow and no benefit pairs; the first screen says what will happen in this project in two sentences. The video is a link. The folder is not asked inside a repository (it is shown with "Change"). A first install takes at most 4 clicks, diagnostics (`Blackbox`) are never pre-checked: the screen says what is published and where, and that a public repository makes it public; the human chooses, no screen is taller than two viewports at 1280×800 or three at 390×844 with real content ("Get ready" was 4518 px and 6457 px), an instruction appears once: one command, one copy box, the folder already in it; raw output of `uak start` is under "Technical details", never a heading. A heading is a sentence that starts with a capital and says what to do, an error is next to the control that caused it and above the button, in view after the click at both widths, names what to do, and is the message of that step, the step is in the URL: reload stays on it, the browser's Back and Forward move between steps, reopening a project resumes where it was, at 390 px the content starts within 160 px of the top, every target is at least 44×44 px, nothing scrolls sideways; the journey bar and the step rail are one component, a running action shows what it is doing and for how long, next to its button; a page whose server ended says so when it comes back into view, with the command that reopens it, screenshots at 1280 and 390, light and dark, Spanish and English, of every screen and of one error and one loading state are in `.uak-shots/UAK-159/` with the design critic's `VERDICT: SHIP` for the task's commit
- **Tests:** flow_has_the_ten_screens, existing_repository_is_detected, rules_screen_writes_only_what_was_confirmed, schedule_only_in_hackathon, diagnostics_are_not_prechecked, old_kit_opens_update, close_ends_the_server, no_screen_taller_than_two_viewports, instruction_appears_once, first_install_in_four_clicks, error_is_next_to_its_control, step_survives_reload_and_back, mobile_content_starts_within_160px, targets_are_44px
- **Verify:** `python3 kit/.uak/tests/test_setup_forms.py && python3 kit/.uak/tests/test_setup_guide.py && python3 kit/.uak/tests/test_setup_resume.py && python3 kit/.uak/tests/test_setup_first_run.py`
- **Next step:** the "Get ready" markup in setup.html (about lines 1700-2040 of the contributed file) and the hero at 1434-1460; the detection of hooks is `doctor`'s (UAK-135, UAK-146), reuse it; changed assertions need `uak allow UAK-159 --tests` from the human

## UAK-160 · The wizard's Spanish is written, not translated from the engine's sentences

- **Type:** fix
- **Priority:** P1
- **Estimate:** 5 h
- **Depends on:** UAK-159, UAK-161
- **Paths:** kit/.uak/bin/lib/workspace.js, kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/start, kit/.uak/tests/test_setup_language.py
- **Acceptance:** the page never matches the engine's English prose: `uak --json start` (and the other commands the wizard runs) give each need and note a stable code and its values, and the page's texts are keyed by code in both languages. A test rewords an engine sentence and the Spanish page is unchanged; a code with no text in a language fails the test, it does not fall back to English, one voice in Spanish: "tú" throughout, usage of Mexico ("haz clic", not "pulsa"), no sentence that mixes languages. A glossary in the page's dictionary fixes the terms that stay in English because they are commands or git words (`commit`, `merge`, `pull request`, `worktree`, `main`) and the ones that are translated (dashboard → panel, claim → tomar una tarea); the test fails on a term outside it, both languages are complete on every screen, including the readiness block and the commands' explanations, no exclamation marks, no filler ("simplemente", "fácilmente", "potente"), sentence case in headings and buttons
- **Tests:** texts_are_keyed_by_code, rewording_the_engine_changes_nothing, no_missing_text_in_either_language, one_voice_in_spanish, glossary_is_respected
- **Verify:** `python3 kit/.uak/tests/test_setup_language.py`
- **Next step:** the dictionary and the regex table in kit/.uak/bin/lib/workspace.js and the needs of kit/.uak/bin/start; changed assertions need `uak allow UAK-160 --tests` from the human

## UAK-161 · The install asks how you want to continue: in the browser or in the terminal, and both reach the same place

- **Type:** feature
- **Priority:** P0
- **Estimate:** 5 h
- **Depends on:** UAK-154
- **Paths:** install.sh, kit/.uak/bin/start, kit/.uak/docs/CLI.md, README.md, docs/HACKATHON.md, scripts/kit_lint.py, kit/.uak/tests/test_install_choice.py
- **Acceptance:** `bash install.sh` run by a person at a terminal ends with one question: continue in the browser (the wizard) or here in the terminal; Enter takes the terminal, the answer is one key, and the question says in one line what each is. `--wizard` and `--terminal` answer it beforehand, with no terminal (a pipe, CI, an agent, `UAK_AGENT` set) nothing is asked and nothing opens: the install ends as today, so every existing script and test keeps working, the choice is remembered for the project (git config, not a tracked file) and can be changed: `uak start --wizard` opens the wizard later, and the wizard's last screen and its "Close" say the terminal command that continues from the same point, the terminal path covers the same steps as the wizard, in the same order and with the same names: `uak start` prints the one next step with its command (project detected, rules, people, schedule in Hackathon mode, publish the kit, idea and plan, start the agents), and a step done in one is done in the other: the state is the project's, never the page's, a machine without Python 3.8 or without a browser is told so and continues in the terminal; the wizard is never a requirement
- **Tests:** install_asks_once_at_a_terminal, no_terminal_no_question, flags_answer_the_question, choice_is_remembered, terminal_and_wizard_share_the_state, start_names_the_same_steps, no_python_continues_in_terminal
- **Verify:** `python3 kit/.uak/tests/test_install_choice.py`
- **Next step:** the end of install.sh (`--wizard` execs setup.py today) and the needs of kit/.uak/bin/start; a new test file needs its entries in both timing tables

## UAK-162 · The dashboard is redrawn in the chosen direction

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-158
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, docs/DASHBOARD.md, docs/media/, README.md, kit/.uak/tests/test_dashboard_truth.py, kit/.uak/tests/test_dashboard_profiles.py
- **Acceptance:** the dashboard is redesigned with the tokens of `docs/design/DIRECTION.md`: the same information as today (progress, agents online, reviews waiting with their sub-state, stalled, needs a human, board, agents, conversation, black box, memory, tokens), nothing dropped; the first thing read is what needs a person now, then progress, then the board, an empty project is not a grid of zeros: it says the one next step and its command; each number that is zero because nothing happened yet says so in words, it stays one file opened from `file://`, with no server, no port, no external request and no build step; the page is not heavier than today (84 KB) and its two timers start no process, both profiles (beginner, advanced), both themes and both languages are complete; every text/background pair is at least 4.5:1; every target is at least 44×44 px at 390; nothing scrolls sideways; it is usable with the keyboard alone, and motion stops under `prefers-reduced-motion`, `design-lint --strict` passes on it with no finding suppressed (main's file has 26 today: 19 colour literals, 5 rgba, 1 glass, 1 emoji), screenshots at 1280 and 390, light and dark, of an empty project, a project in progress (20 tasks, 3 agents, a review over its lease, a blocked task) and a finished one are in `.uak-shots/UAK-162/` with the design critic's `VERDICT: SHIP` for the task's commit; the README's and the docs' images of the dashboard are replaced
- **Tests:** dashboard_keeps_every_field, empty_project_says_the_next_step, no_server_no_request, page_is_not_heavier, both_profiles_and_languages_are_complete
- **Verify:** `python3 kit/.uak/tests/test_dashboard_truth.py && python3 kit/.uak/tests/test_dashboard_profiles.py && bash kit/.uak/bin/design-lint --strict kit/.uak/bin/lib/dash.html`
- **Next step:** kit/.uak/bin/lib/dash.html (tokens at the top, the hero and the four tiles, the tabs); the data comes from `dash.py`, whose fields the existing tests list; changed assertions need `uak allow UAK-162 --tests` from the human
## UAK-163 · Someone who joins a project that is already set up: three screens, nothing to configure about the project

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159, UAK-162
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/start, kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/docs/CLI.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_setup_join.py
- **Acceptance:** a person who clones a repository whose base branch already has the kit, and runs `uak start` (or `uak start --wizard`), is not sent through the ten screens of the setup: the project is set up, their machine is not. They get the join path, three screens, in the browser or in the terminal with the same names and order: (1) The team: the project's mode and rules in plain words, who its humans and reviewers are, the plan's state; read from the base branch, read-only. (2) Your machine: their identity (the git identity), the kit's hooks for this checkout and how they live beside a hook manager, the coding tools found on this machine and their files; each problem with its one fix; nothing is committed and no tracked file changes. (3) Start: the command that launches their agent with a name that is free, the three tasks an agent of theirs can claim now, or the reviews waiting when they come as a reviewer; then the dashboard, the join path never asks for the mode, the stack, the schedule, the plan or any project setting, never writes PROJECT.md and never offers an act of the project's human (register a reviewer, approve a plan, publish the kit): where one is missing it names who can do it, which path a person gets is decided from the repository, not from a choice: no kit on the base branch → setup; kit on the base branch and this checkout not prepared → join; both done → the dashboard. A test covers the three, the dashboard knows who is looking: "Needs you" lists what waits for this person (reviews offered to their agents, their stalled tasks, decisions when they are a human of the project) and shows what waits for someone else as "waits for NAME", not as theirs; with no identity it shows the project's list and says so. The page stays one file with no server, a second and a third person can join at the same time without one writing over the other: the join path writes only inside the person's checkout and git directory, screenshots at 1280 and 390, light and dark, Spanish and English, of the three screens are in `.uak-shots/UAK-163/` with the design critic's `VERDICT: SHIP` for the task's commit, Why (2026-11-23): the wizard was designed for the one person who sets a project up; most people who use a project arrive after that, and today they would be shown a setup that is already done
- **Tests:** joiner_gets_three_screens, path_is_decided_from_the_repository, join_never_writes_project_settings, join_offers_no_human_act, needs_you_is_per_person, two_people_join_at_once, terminal_join_names_the_same_steps
- **Verify:** `python3 kit/.uak/tests/test_setup_join.py`
- **Next step:** the route that picks the first screen in kit/.uak/bin/lib/setup.py (`open_target`) and the needs of kit/.uak/bin/start; the identity the dashboard reads is the one `uak status` uses; a new test file needs its entries in both timing tables
## UAK-164 · Paste or drop what you already have: the agent fills the form, the person confirms

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/planning.py, kit/.uak/bin/start, kit/.uak/docs/CLI.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_setup_intake.py
- **Acceptance:** every wizard screen that asks for more than two typed values (the schedule, the idea, the rubric, the people) opens with one input: paste text, or drop or pick a file (`.md`, `.txt`, `.pdf`, an image of a call for projects, an existing `IDEA.md`). The form is still there below it, and typing by hand always works, the person's own coding tool (the one the planner already uses: `claude -p` or `codex exec`) reads what was given and proposes the fields of that screen: for the schedule, start, deadline, time zone and freeze; for the idea, what is built, for whom, the rubric with its weights, the duration and the team size; for people, names and roles. While it reads, the input shows what it is doing and for how long, and can be cancelled; it has a time limit of 60 s, nothing is saved until the person confirms: each proposed field is marked as proposed, shows the sentence of the source it came from, and can be edited or cleared; a field the source does not state stays empty and says so, it is never invented; a date without a year or a time zone is asked, not guessed. One button confirms the screen, the source is data, never instructions: the reader runs with no tools, no file access and no write permission, gets the text only, and must answer in a fixed schema that the server validates (types, ranges, known time zones, lengths); anything outside the schema is dropped; a source that tells the reader to do something changes nothing. The test gives it a file with an injected instruction and with a field of 10,000 characters, a file is read on the machine and never uploaded by the kit; the screen says, before reading, which tool will receive the text; files over 2 MB or of another type are refused with the reason; the source is not committed unless the person keeps it as `IDEA.md`, with no coding tool that can run headless, the input says so and the form is filled by hand; dates and times in common formats are still recognised without a model, the terminal has the same: `uak start --from FILE` proposes the same fields as text and asks for a confirmation per screen; an agent identity cannot confirm for the person, the tokens the reading cost are shown next to the result and recorded in the ledger, Why (the human, 2026-11-23): typing the event's data and the idea by hand defeats the purpose when the call for projects or the idea already exists as a file
- **Tests:** dropped_file_fills_the_schedule, pasted_idea_fills_the_form, nothing_is_saved_before_confirm, missing_field_stays_empty, injected_instruction_changes_nothing, oversized_field_is_dropped, no_headless_tool_falls_back_to_the_form, terminal_from_file_proposes_the_same, reading_can_be_cancelled
- **Verify:** `python3 kit/.uak/tests/test_setup_intake.py`
- **Next step:** the headless runner in kit/.uak/bin/lib/planning.py (it already builds the `claude -p` and `codex exec` commands and checks for violations afterwards); the forms are the schedule and the idea in setup.html; a new test file needs its entries in both timing tables; the tests use a fake tool in PATH, never a real model
## UAK-165 · The summary is made of components the viewer arranges: move, hide, add

- **Type:** feature
- **Priority:** P1
- **Estimate:** 8 h
- **Depends on:** UAK-162
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/dash, kit/.uak/docs/CLI.md, docs/DASHBOARD.md, docs/design/DIRECTION.md, scripts/kit_lint.py, kit/.uak/tests/test_dashboard_layout.py
- **Acceptance:** every block of the summary (needs you, tasks, activity, progress, agents, integrations per period, tokens) is a component with a name, a title, a size (main column or side column), its maximum of rows and one render function over the dashboard's data; the summary is a list of component names per column, and the default list is today's order, "Edit" in the summary's header turns on an arrange mode: each component shows handles to move it up or down, to send it to the other column, and to hide it; "Add" lists the components not shown, each with one line saying what it shows. Everything works with the keyboard (no drag is required) and at phone width; "Done" leaves the mode, "Restore" returns to the default, the arrange mode is unmistakable the moment it starts: every component that can be moved shakes slightly (a small, slow rotation of about one degree, each out of step with its neighbours, as app icons do on a phone when they can be rearranged), gets a dashed outline and shows its handles, and one line at the top says what can be done ("Move, hide or add components. Done when you finish."). Under `prefers-reduced-motion` nothing moves: the outline, the handles and the line carry the meaning. The shake stops for the component under the pointer or with keyboard focus, so its controls hold still, and it never runs outside the arrange mode, the arrangement is the viewer's: kept in the browser per project, it changes no tracked file and nobody else's panel. A team may ship a default: `uak dash layout --save` writes the current arrangement to `.uak/dash/layout.json` (a file a task or the human commits), and a viewer with no arrangement of their own starts from it, "needs you" can be moved but not hidden: a panel that does not say what waits for the person is not the kit's panel. The rule that the summary never grows with the plan holds for every component in every position, an arrangement that names a component that no longer exists, or a corrupt one, falls back to the default and says so once; it never leaves an empty page, the page stays one file opened from `file://`, with no server, no request and no build step
- **Tests:** summary_is_a_list_of_components, arrange_mode_shakes_and_respects_reduced_motion, move_hide_and_add_persist_per_viewer, needs_you_cannot_be_hidden, team_default_is_used_when_the_viewer_has_none, unknown_component_falls_back, arranging_works_with_the_keyboard
- **Verify:** `python3 kit/.uak/tests/test_dashboard_layout.py`
- **Next step:** the summary's sections in kit/.uak/bin/lib/dash.html after UAK-162; the data every component reads is what `dash.py` already writes to `data.js`; a new test file needs its entries in both timing tables

## UAK-166 · More components to choose from

- **Type:** feature
- **Priority:** P1
- **Estimate:** 8 h
- **Depends on:** UAK-165
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, docs/DASHBOARD.md, kit/.uak/tests/test_dashboard_layout.py, kit/.uak/tests/test_dashboard_truth.py
- **Acceptance:** the catalogue gains these components, each within the direction's rules (a title and a count, a maximum, a link to its tab), each fed only by data the engine already records: (1) Review queue: every review with its sub-state, its reviewer and the share of its lease used, overdue first. (2) My agents: the agents of the person looking, what each does and for how long (needs the identity of UAK-163; without one it says how to set it). (3) What unblocks what: the tasks that hold others back, with how many wait behind each. (4) Event clock, in Hackathon mode: time to the freeze and to the deadline, and the share of the plan integrated against the share of the time gone. (5) Last integrations: the last merges with task, author, reviewer and commit. (6) Recent messages: the last messages between agents and to the human. (7) Cost per task: tokens per task, the dearest first, against the estimate. (8) Checks: the state of the required checks of the open pull requests, when the forge gives it. (9) Deployment: the `Live-URL` and when it last answered, when one is set, a component with nothing to show says why in one line (no reviews waiting, no schedule set) and takes one row, never an empty box, each has a test with a fixture that pins its numbers against the claims data, as the existing components have, screenshots of every new component at 1280 and 390, light and dark, in two palettes, are in `.uak-shots/UAK-166/` with the design critic's `VERDICT: SHIP` for the task's commit
- **Tests:** review_queue_orders_overdue_first, my_agents_needs_an_identity, blockers_count_what_waits, event_clock_only_in_hackathon, empty_component_says_why, each_new_component_matches_the_claims
- **Verify:** `python3 kit/.uak/tests/test_dashboard_layout.py && python3 kit/.uak/tests/test_dashboard_truth.py`
- **Next step:** the component registry of UAK-165; `dash.py` already reads reviews, messages, tokens and merge commits from the claims branch

## UAK-167 · Describe a component in words and get it: a declarative spec the panel draws, reusable in any project

- **Type:** feature
- **Priority:** P2
- **Estimate:** 10 h
- **Depends on:** UAK-165, UAK-164
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/dash, kit/.uak/bin/lib/planning.py, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/setup.html, kit/.uak/docs/CLI.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_dashboard_widget_spec.py
- **Acceptance:** a component can be a spec, not code: a small JSON file that names a source of the dashboard's data (tasks, agents, reviews, moves, messages, tokens, merges), a filter, a grouping, an order, a maximum, the fields to show and one of the panel's own drawings (list, table, counter, bars, lanes, timeline). The panel validates the spec against a schema and draws it with its own trusted renderers; it never runs code from a spec, and a spec cannot make a request, read anything outside the dashboard's data or draw outside its box. An invalid spec shows its error in its place and nothing else changes, `uak dash widget "the agents of mine that are reviewing, with how long"` asks the person's own coding tool (the reader of UAK-164: no tools, no file access, a fixed answer schema) for a spec, validates it, shows what it would draw with the project's real data, and saves it only when the person confirms. With the wizard's server open, the same is a field in "Add" with a visible wait and a preview. With no tool that can run headless, the command says so and names the file format to write by hand, specs live in `.uak/dash/widgets/NAME.json` for the project (a file a task or the human commits) and in the person's own directory for every project of theirs; `uak dash widget --list`, `--remove NAME` and `--export NAME` manage them. A spec written in one project draws in another without change, because it names data every project of the kit has; a field the other project lacks shows as empty, not as an error, a spec inherits theme, palette, scale and the maximums of the direction: it has no colours, sizes or fonts of its own, the description is data, never instructions: the test gives a description that tries to make the reader write a file or add a script, and a spec with a `script`, a URL or an unknown drawing; all are refused, Why (the human, 2026-11-23): people should put on their panel what they need most, including a view nobody built yet, and carry it to their next project
- **Tests:** spec_is_validated_and_drawn_by_the_panel, spec_never_runs_code, described_widget_is_previewed_before_saving, spec_from_one_project_draws_in_another, invalid_spec_shows_its_error, injected_description_is_refused, no_headless_tool_says_how_to_write_it
- **Verify:** `python3 kit/.uak/tests/test_dashboard_widget_spec.py`
- **Next step:** the component registry of UAK-165 (a spec becomes a component whose render function is one of the fixed drawings); the headless reader of UAK-164 in kit/.uak/bin/lib/planning.py; a new test file needs its entries in both timing tables
## UAK-168 · A pull request waits about ten minutes, not forty: CI in two tiers

- **Type:** feature
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-152
- **Paths:** .github/workflows/test.yml, scripts/kit_lint.py, scripts/ci_select.py, kit/.uak/tests/test_ci_shards.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/docs/WHY.md, AGENTS.md, docs/ARCHITECTURE.md
- **Acceptance:** a pull request runs the first tier: the whole suite on Linux (4 shards, 3 to 7 minutes each today), and on macOS and on Windows only the tests the change can affect, in one job per system, two when the selection is predicted over 10 minutes. The selection is: every test file the change adds or edits; the tests that name a command or a library the change touches (the selector of `smoke --affected`, without its escalation to the whole suite); and a fixed portability set of at most six files, each under two minutes on Windows, listed with its reason (paths with spaces, symlinks, Bash 3.2, CRLF, case-insensitive names, process groups). What was not selected is printed in the job's summary as "runs on main", a push to main and a tag run the second tier, the whole matrix as today (18 jobs), never cancelled; every commit on main keeps its own result, the whole matrix can be asked for on a pull request: the label `ci-full`, or a manual run (`workflow_dispatch`) of the branch; it is automatic when the change touches `.github/workflows/` or the selector itself, when the whole matrix of a commit on main fails, the workflow opens one issue "main is red at SHA" naming the failed jobs and the pull request that brought the commit, or adds to the open one; the first green run of main closes it. AGENTS.md says what follows: nobody merges on a red main except the fix or the revert, no trigger is filtered by path at the workflow level (a required check of a skipped workflow stays "Pending" and blocks the merge, as GitHub's documentation says): the workflow always runs and decides inside what to select. One final job, `ci`, always runs and passes only when every job that ran passed; it is the single check to require, on a pull request and on main, and the only name `Merge-Engine-Checks` needs, a test file that fails on macOS or Windows is run once more in the same job: when it then passes, the job passes but its summary and an annotation say "flaky: FILE passed on the second run", and the count per file is kept (an artifact per run); it is never reported as a plain pass. A file that failed twice fails the job. Linux never retries. On main, the issue "main is red" is opened only after the failed jobs were re-run once, and says which files failed both times, Windows jobs put their temporary directory on the runner's `D:` drive (`TEMP`, `TMP`, `TMPDIR`): measured first on one shard of this task's own run against the same shard without it, and kept only if it is at least 10% faster; the numbers go in WHY.md either way, two pull requests that pass alone can break main together: the kit's gate already runs the smoke on the merged result before it merges (Linux), and the second tier catches the rest on the commit; a merge queue is not available to a repository of a personal account, and the task does not require branches to be up to date, the selection is computed by one script the tests can call (`scripts/ci_select.py BASE HEAD` prints the files per system and the predicted seconds from the timing tables); the lint refuses a portability file that is missing, over two minutes on Windows, or without a reason; `test_ci_shards.py` keeps its bounds for the second tier and gains the first tier's: at most 9 jobs on a pull request, each macOS and Windows job predicted under 10 minutes, a change that adds a test file runs it on the three systems in the pull request, so its seconds can be measured before the timing tables are filled, measured on this task's own pull request and written in WHY.md: time from push to the last check before (a recent pull request of v6.8) and after, sources read for this design (2026-11-23), cited in WHY.md with what each reports: Meta's predictive test selection (a third of the tests, over 99.9% of faulty changes caught, about 5% of individual failures not shown), LLVM's developer policy ("revert to green"), Rust's CI guide (a short suite on pull requests, the full one elsewhere), Uber's "Keeping master green at scale", pip's maintainer write-up on Windows temp directories (17m37s to 12m41s), GitHub's documentation on skipped required checks and on concurrent jobs (20, of them 5 macOS), Why (the human, 2026-11-23, and run 45116515431): macOS jobs take 15 to 19 minutes and Windows 17 to 26, plus the wait for a runner; every push of every pull request paid all 18. Sixteen tasks are queued behind this
- **Tests:** pull_request_runs_the_first_tier, main_runs_the_whole_matrix, selection_has_changed_tests_named_tests_and_the_portability_set, selection_never_escalates_to_the_whole_suite, ci_full_label_runs_everything, workflow_change_runs_everything, new_test_file_runs_on_three_systems, red_main_opens_one_issue, first_tier_is_at_most_nine_jobs, one_final_job_gates_the_run, flaky_pass_is_reported_not_hidden, no_workflow_level_path_filter
- **Verify:** `python3 kit/.uak/tests/test_ci_tiers.py && python3 kit/.uak/tests/test_ci_shards.py`
- **Next step:** `.github/workflows/test.yml` (the `discover` job already computes the shards with `kit_lint.py --ci-shards` and `--ci-windows`); the selector of UAK-129 is in kit/.uak/bin/smoke (`--affected`); a new test file needs its entries in both timing tables; the workflow is the human's file, so the merge goes to the human
## UAK-169 · The second run of a slow file cannot cost the job, and `ci` passes only on success

- **Type:** fix
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-168
- **Paths:** .github/workflows/test.yml, scripts/ci_select.py, scripts/kit_lint.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/tests/test_ci_shards.py, kit/.uak/docs/WHY.md, AGENTS.md
- **Acceptance:** a failed file runs once more only when its second run fits: its entry in the timing table is at most 300 s and the job's elapsed time plus that entry stays under the job's test bound. A file over that fails the job on its first failure, and the summary says "not run again: FILE takes N s". Why: on main at `e4f2f83d` (run 45198280141) `windows (1)`, which holds `test_flaky_guard_race` (862 to 1336 s alone), was cancelled by its 45 minute limit after 55 minutes with no log left, a job cancelled by its time limit still says which file it was running: the runner prints the file's name and the clock before each file, flushed, and writes the partial result so the artifact exists, the final job `ci` passes only when `discover` and every test job that the tier planned concluded `success`; `skipped` and `cancelled` fail it, the issue "main is red" is closed only by a run of main whose `ci` job succeeded; a run cancelled by hand closes nothing. The job that opens it runs after a real re-run of the failed jobs when the failure was not in a file that already ran twice (a Linux failure, a set-up failure, a time limit), and says which of the two it was, the portability set has no file that failed intermittently on Windows in the last ten runs of main: `test_merge_renewer_orphan` is replaced by another file that covers process groups, or kept with the measurements that say it is steady; the lint refuses a member named in a list of known intermittent files, the cases that read the workflow as text are replaced or joined by cases on behaviour: the label reaching the selector (`ci_full_label_runs_everything`), `--retry` absent on Linux (`flaky_pass_is_reported_not_hidden`), the condition of the job that opens the issue (`red_main_opens_one_issue`); a case fails when a `run:` line of the workflow contains `${{ github.event` or `${{ inputs`, a selector that fails for one file fails `discover`; it does not select nothing for that file (`|| true` after `tf_affected_select` is removed or its failure is told apart from "no test names it"), the summary's "runs on main: N of M" counts both systems
- **Tests:** slow_file_is_not_run_twice, second_run_must_fit_the_bound, cancelled_job_names_its_file, ci_needs_success_not_skipped, cancelled_main_does_not_close_the_issue, portability_set_has_no_intermittent_file, label_reaches_the_selector, linux_never_retries_by_behaviour, no_event_text_in_run_lines, selector_failure_fails_discover
- **Verify:** `python3 kit/.uak/tests/test_ci_tiers.py && python3 kit/.uak/tests/test_ci_shards.py`
- **Next step:** `run_files` and `gate` in scripts/ci_select.py; the `windows` and `suite` jobs in `.github/workflows/test.yml`; the workflow is the human's file, so the merge goes to the human

## UAK-185 · The hook survives its own files being wrong, and no background job is without a limit

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-157
- **Paths:** kit/.uak/bin/hook, kit/.uak/tests/test_hook_session_start_speed.py
- **Acceptance:** a time file (`uak-start.NAME.at`, a lock's `since`, the pace stamp) that holds `08`, letters, nothing, a date in the future or a number of twenty digits never ends the hook early and never blocks `pace` or `map build`: the value is treated as stale, and the session start prints everything it prints today. Why: the review of UAK-157 measured that `08` reduced the output to the identity line (an arithmetic error), and that a time one hour ahead stopped both jobs for that hour, reclaiming a stale lock cannot delete a lock another start has just taken: of eight simultaneous starts on a stale lock, each job runs once, in ten rounds of ten, `tokens --publish`, `bb flush`, the lens `map build`, `pr-sync` and `heartbeat` started by the hook run under the same limit as the session start's worker (60 s by default), and are killed with their children when they pass it; none leaves a process after the limit, a cached copy says its age whenever it is shown, not only while a refresh runs; a copy without a time file says "age unknown"; an age is never negative, the foreground of a session start launches no more processes than today (14 on startup, 9 on resume)
- **Tests:** corrupt_time_file_does_not_end_the_hook, future_time_file_is_stale, stale_lock_reclaim_runs_once, every_background_job_has_a_limit, cached_copy_always_says_its_age
- **Verify:** `python3 kit/.uak/tests/test_hook_session_start_speed.py`
- **Next step:** `start_once`, `start_show` and `pace_at` in kit/.uak/bin/hook (search `$((NOW - `); the `nohup` lines of `tokens_publish`, `bb flush` and `tick`

## UAK-186 · The merge reads the review mode from the base, and the smoke boot names what it refuses

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-155
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/done.sh, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/docs/CLI.md, kit/.uak/tests/test_done_without_github.py, kit/.uak/tests/test_smoke_onboarding.py, kit/.uak/tests/test_review_identity.py
- **Acceptance:** `approval_check` reads `Review-Mode` from the base branch's configuration; `UAK_REVIEW_MODE` in the environment of `uak merge` cannot turn a project whose base says `gh` into one approved on claims. Why: the review of UAK-155 found the variable still read at `review-merge.sh:276`, so a task with a real pull request could be merged on a claims approval by whoever sets it, the tests that rely on the variable today set the mode in their fixture's base instead; the list of changed lines is in the task's note for the human's `uak allow`, the hint of `uak done` about `--pr none` no longer names the environment variable, a file or folder name with a newline is refused by the smoke boot with the same `SMOKE_REFUSED` line as the other names, and nothing runs
- **Tests:** env_review_mode_does_not_change_the_merge, merge_reads_the_base_mode, newline_name_is_refused_by_name
- **Verify:** `python3 kit/.uak/tests/test_done_without_github.py && python3 kit/.uak/tests/test_smoke_onboarding.py`
- **Next step:** `approval_check` in kit/.uak/bin/lib/review-merge.sh; `git grep -n UAK_REVIEW_MODE kit/.uak/tests` lists the tests to move to the base's configuration; changed assertions need `uak allow UAK-186 --tests` from the human
## UAK-187 · A test's seconds live in its own file, so two tasks that add a test can run at once

- **Type:** refactor
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-156
- **Paths:** scripts/kit_lint.py, scripts/ci_select.py, kit/.uak/tests/timings, kit/.uak/tests/test_ci_shards.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/tests/test_ci_timings.py, kit/.uak/docs/WHY.md, AGENTS.md, install.sh, kit/.uak/tests/test_install_light.py
- **Acceptance:** the seconds of a test file are read from `kit/.uak/tests/timings/NAME.txt` (two lines: `ci N` and `windows N`, an optional `# why` line), one file per test; `CI_SECONDS` and `CI_WINDOWS_SECONDS` in `scripts/kit_lint.py` are built from that folder at import, with the same values as today for every test (a case compares the two tables before and after, entry by entry). Why: thirteen published tasks (UAK-156, 158 … 167, 169) list `scripts/kit_lint.py` only to add two numbers, the protocol refuses two live claims that share a path, so on 2026-11-23 the tasks of plan "visual setup" could only run one at a time, a task that adds a test adds its own timing file and does not touch `scripts/kit_lint.py`; AGENTS.md says so in one sentence, the lint still refuses a test file with no entry for either system and names the file to create; it also refuses a timing file with no test, a line it cannot read, a number that is not a whole number of seconds between 1 and 3600, and a second `ci` or `windows` line, `lint.CI_SECONDS`, `lint.CI_WINDOWS_SECONDS`, `ci_seconds`, `ci_windows_seconds`, `ci_shards` and `timing_problems` keep their names and results, so no existing case of `test_ci_shards` or `test_ci_tiers` changes; the shards of main are the same lists as before, the timing files are not installed in a project: an install has the same number of files as before this task, a pull request that changes only a timing file runs the first tier, not the whole matrix
- **Tests:** tables_equal_before_and_after, test_without_timing_file_is_named, timing_file_without_test_is_refused, unreadable_timing_line_is_refused, shards_are_unchanged, timings_are_not_installed, timing_only_change_is_first_tier
- **Verify:** `python3 kit/.uak/tests/test_ci_timings.py && python3 kit/.uak/tests/test_ci_shards.py && python3 kit/.uak/tests/test_ci_tiers.py && python3 scripts/kit_lint.py`
- **Next step:** `CI_SECONDS` at scripts/kit_lint.py:122 and `CI_WINDOWS_SECONDS` at :160; write the folder from the two tables with a script run once, then replace the literals by the reader. After it merges the human amends the Paths of the open tasks (remove `scripts/kit_lint.py`, add `kit/.uak/tests/timings`): the amend file is written with this task

## UAK-188 · The guard and SECURITY.md know the wizard's reopen key and its two new requests

- **Type:** fix
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-156
- **Paths:** kit/.uak/bin/guard, kit/.uak/docs/SECURITY.md, kit/.uak/tests/test_setup_trust.py, kit/.uak/tests/test_guard_wizard_files.py, kit/.uak/tests/timings
- **Acceptance:** while a wizard is live for the project (its port file names a live process), the guard refuses an agent's command that reads, copies or prints `uak-wizard.key`, and one that names `/api/reopen` or `/api/closing` on the wizard's port or on a port it cannot read; with no live wizard the same commands pass, and a project's own `/api/reopen` on another port passes. Why: the review of UAK-156 ran `cat .git/uak-wizard.key` and a `curl` to `/api/reopen` through `guard check` and both were allowed; the key gives a fresh code for the human's page, the guard refuses an agent's command that removes or rewrites `uak-wizard.port`, `uak-wizard.key` or `uak-wizard.children` while a wizard is live: without the port file the rule above stops matching, SECURITY.md says what is left: a script that hides the request, any process of the same user that reads the key, and what the person sees when it happens (the line on the first server's terminal, the entry in the register, the notice on the open page); the sentence about a stolen code being "used once" is corrected for the reopen route, no rule of UAK-153's guard changes its result on the cases of `test_setup_trust`
- **Tests:** key_read_is_refused_while_live, reopen_and_closing_are_refused_on_the_wizard_port, same_names_pass_without_a_wizard, other_port_passes, record_files_cannot_be_removed_while_live, security_doc_names_the_reopen_key
- **Verify:** `python3 kit/.uak/tests/test_guard_wizard_files.py && python3 kit/.uak/tests/test_setup_trust.py`
- **Next step:** `wizard_mentioned` in kit/.uak/bin/guard; SECURITY.md line 42; the guard is the human's file, so the merge goes to the human

## UAK-189 · The gate's smoke does not inherit the caller's task, and three small leftovers of the reviews

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-186, UAK-185
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/bin/hook, kit/.uak/tests/test_gate_environment.py, kit/.uak/tests/test_hook_session_start_speed.py, kit/.uak/tests/test_smoke_onboarding.py, kit/.uak/tests/timings
- **Acceptance:** `uak merge` run from a task's worktree gives the same smoke result as from the main checkout: the gate removes `UAK_TASK` (and the other variables `.uak-env` sets) from the environment of its smoke. Why: on 2026-11-23 the merge of UAK-157, run from its worktree, failed `test_manual_notes` and `test_task_participants` because their fixtures recorded under the real task; from the main checkout without the variable it merged, a pending black-box file whose owner belongs to another user of the system is not taken: a `kill -0` that fails for lack of permission counts as "alive" (the review of UAK-185: EPERM was read as "dead"), the smoke boot refuses a newline in any component of a path, not only in the last name, in `Review-Mode: auto` a project without `gh` in PATH says which mode it chose and why, once, in `uak done` and `uak merge`
- **Tests:** merge_from_worktree_equals_merge_from_main, smoke_environment_has_no_task, other_users_pending_file_is_left, newline_in_a_folder_is_refused, auto_mode_says_what_it_chose
- **Verify:** `python3 kit/.uak/tests/test_gate_environment.py && python3 kit/.uak/tests/test_smoke_onboarding.py && python3 kit/.uak/tests/test_hook_session_start_speed.py`
- **Next step:** where `approval_check` and the smoke are called in kit/.uak/bin/lib/review-merge.sh (search `smoke`); `bb_flush_job` in kit/.uak/bin/hook (search `kill -0`); the gate's library is the human's file, so the merge goes to the human
## UAK-190 · A killed black-box flush leaves no clone directory on Windows

- **Type:** fix
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-189
- **Paths:** kit/.uak/bin/hook, kit/.uak/bin/bb, kit/.uak/tests/test_hook_session_start_speed.py, kit/.uak/tests/timings/test_hook_session_start_speed.txt
- **Acceptance:** after the hook kills a `bb flush` that passed its limit, no `uak-bb-tmp.*` directory is left in the git directory, on Windows as on Linux and macOS: the case `killed_bb_flush_is_recovered_and_published_once` passes 20 times in a row on a Windows runner. Why: on main at `967f794` (run 45326081765, `windows (10)`) the case failed with "the killed flush's clone directory is removed: […/.git/uak-bb-tmp.1795494673.16989]"; it had passed in the review of UAK-185 and in three earlier runs of main, so the removal races with the kill (a file still open in the killed tree cannot be removed on Windows), the removal is retried for a bounded time after the kill and, when it still fails, the next flush removes the leftover first; a leftover older than its limit is never read as a live clone, the cause is written in the test's comment with the measurement that showed it (how long after the kill the directory could be removed, on Windows), the file's Windows seconds are measured again and written with a `# measured` line; if it stays over 300 s, WHY.md says that a failure of this file on Windows is never retried in its job and needs `gh run rerun ID --failed`
- **Tests:** killed_flush_leaves_no_clone_on_windows, leftover_clone_is_removed_by_the_next_flush
- **Verify:** `python3 kit/.uak/tests/test_hook_session_start_speed.py`
- **Next step:** `bb_flush_job` and the kill of a limited job in kit/.uak/bin/hook; where `bb` makes `uak-bb-tmp.<time>.<pid>` through TMPDIR; prove it on CI with the label `ci-full` on the pull request, since the failure is only seen on Windows

## UAK-191 · CI leftovers: a cancelled step leaves no test running, and stale seconds are measured again

- **Type:** fix
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-169
- **Paths:** scripts/ci_select.py, kit/.uak/tests/test_ci_tiers.py, kit/.uak/tests/timings/test_done_without_github.txt, kit/.uak/tests/timings/test_ci_tiers.txt, kit/.uak/tests/timings/test_install_choice.txt, kit/.uak/tests/timings/test_guard_wizard_files.txt
- **Acceptance:** when the driver of a test job receives SIGTERM or SIGINT (a cancelled step), the test file it is running and that file's children end with it: nothing is left reparented. Why: the review of UAK-169 sent SIGTERM to the driver and the test file and its grandchild kept running in their own session, `test_done_without_github` says `windows 68` and takes 187 to 263 s on Windows: its file, and the three others listed in Paths whose seconds were estimates, carry the median of the last five runs of main with a `# measured` line, no shard of main passes 80 % of its bound with the new numbers; if one does, the task says which and stops for the human (the number of jobs is the human's to change)
- **Tests:** cancelled_driver_leaves_no_test_running
- **Verify:** `python3 kit/.uak/tests/test_ci_tiers.py && python3 scripts/kit_lint.py`
- **Next step:** `run_files` and the session it starts each file in (scripts/ci_select.py); the group times in `gh run view RUN --log --job JOB` of the last five runs of main
## UAK-192 · The wizard runs the command for you: a button where today it shows a command to copy

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/workspace.js, kit/.uak/docs/SECURITY.md, kit/.uak/docs/CLI.md, kit/.uak/tests/test_setup_run_here.py, kit/.uak/tests/test_setup_language.py, kit/.uak/tests/timings/test_setup_run_here.txt
- **Acceptance:** every command the wizard shows in a copy box has a button that does it from the page, and the copy box stays beside it for who prefers the terminal. Why (the human, 2026-11-24, on the screens of UAK-159): "if it is meant to make the work easier, why does it make you run commands in an uncomfortable way? can't there be a button to run it from there?", "Start this agent" (the Start screen) opens a terminal window of the person's system in the project folder with the agent's command already running: Terminal on macOS, Windows Terminal or `cmd` on Windows, the first of `x-terminal-emulator`, `gnome-terminal`, `konsole`, `xterm` on Linux. The coding tool is interactive, so it runs in that window, never hidden inside the server. When no terminal can be opened (a remote machine, no display, WSL without one) the button says so in one sentence and the copy box is what remains; the page never says "started" for a window it could not open, the commands that are not interactive run in the server and show their progress next to the button, with the time, the last lines of output under "Technical details", and the result in a sentence: deploy help and the smoke that boots the app, adding an external skill, saving the live link, the readiness check, and the command the Rules screen gives to open `PROJECT.md` (it opens the file in the system's editor), the server runs only commands from a fixed list built by the server from the project's state; the page sends the name of an action and its fields, never a command line, and a field is validated like the forms of today (no shell, arguments as a list). A request with an unknown action or a command line is refused and written in the register, what the browser may not grant stays that way: the button never writes `Review-Mode`, `Review-Independence`, `Auto-Merge` or `Merge-Engine`, never approves a plan or registers a reviewer in a way the forms of today do not, and never runs with `UAK_HUMAN` set from the page. SECURITY.md lists which actions have a button, which open a terminal, and which stay copy-only with the reason, every process a button starts is in `uak-wizard.children` and ends with the wizard like the others (UAK-156), except the terminal windows, which are the person's: closing the wizard leaves them open, and the page says so, a running action can be stopped from the page; two clicks do not start it twice; an action that fails says what to do next to its button (the rule of UAK-159), Spanish and English for every new sentence; screenshots at 1280 and 390, light and dark, of the Start screen with one agent started and of one action running, one failed and one refused are in `.uak-shots/UAK-192/`
- **Tests:** every_copy_box_has_a_button, start_opens_a_terminal_or_says_why, no_terminal_falls_back_to_copy, page_cannot_send_a_command_line, unknown_action_is_refused_and_recorded, button_grants_no_authority, started_processes_end_with_the_wizard, double_click_starts_once, running_action_can_be_stopped
- **Verify:** `python3 kit/.uak/tests/test_setup_run_here.py && python3 kit/.uak/tests/test_setup_trust.py && python3 kit/.uak/tests/test_setup_processes.py`
- **Next step:** `run_command` and the child record in kit/.uak/bin/lib/setup.py (search `CHILD_RECORD`); the copy rows of the Start and Dashboard screens in setup.html; the terminal opener is a function with one branch per system, tested with a fake opener on PATH. The guard's files are not touched
## UAK-193 · An install never copies Python's bytecode, so the merge gate's smoke stops counting it

- **Type:** fix
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** UAK-190
- **Paths:** install.sh, kit/.uak/tests/test_install_light.py, kit/.uak/tests/timings/test_install_light.txt
- **Acceptance:** an install made from a kit folder that holds `__pycache__` directories or `.pyc` files (in `bin`, `bin/lib`, `docs`, `modes`, `templates`, `settings`, `stacks` or a skill) writes none of them into the project, in every mode and for an update as for a first install. Why: on 2026-11-24 the gate's smoke for UAK-190 failed `marathon_install_under_260_files` twice with 270 and 271 files against a bound of 270, while the same case alone on main counts 256; `install.sh` copies `.uak/bin` and the other parts with `cp -R` and removes `__pycache__` only under `tests`, so the bytecode that the other test files of the smoke write into `kit/.uak/bin/lib` while they run is installed and counted. With two `.pyc` files planted the case counted 258, the count of `marathon_install_under_260_files` is the same alone and while the whole smoke runs in four shards: a case plants bytecode in the kit's folders before installing and the count does not move, an install does not delete or change anything in the kit's own folder (the source): bytecode is left out of the copy, not removed from where it was, a project's own `__pycache__` outside `.uak/` and the kit's folders is never touched by an install or an update
- **Tests:** install_copies_no_bytecode, update_copies_no_bytecode, count_is_the_same_with_bytecode_in_the_kit, source_folder_is_left_as_it_was
- **Verify:** `python3 kit/.uak/tests/test_install_light.py`
- **Next step:** the loop `for part in bin docs modes templates settings stacks` in install.sh (line 153) and the skill copies below it; `files()` in the test
## UAK-194 · The Share card can be saved on a phone

- **Type:** fix
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-162
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_dashboard_truth.py, docs/DASHBOARD.md
- **Acceptance:** on an iPhone, with the dashboard opened over plain `http://` from another machine or from a file, the person leaves the Share dialog with the image saved or shared: the dialog shows the card as a real image (an `<img>` whose source is the exported PNG, in both formats), so a long press offers "Save to Photos", "Copy" and "Share", and one sentence under it says so. Why: on 2026-11-25 the human could neither copy nor download the card on an iPhone; the dialog drew a `<canvas>` (a long press on a canvas offers nothing), "Copy image" needs the clipboard API, which browsers give only to `https://` or `localhost`, and "Download PNG" used a link with `download` on a blob, which Safari on iOS ignores from a page like that, where the browser can share a file (`navigator.canShare` with the PNG), a "Share" button hands the image to the system's sheet (Instagram, Photos, Messages); where it cannot, the button is not shown, "Copy image" and "Download PNG" are shown only where they work, decided by testing the capability and not the browser's name; a button that cannot work is not on the screen, and when none of the three can, the image and its sentence are what remains. No button fails in silence: a refusal says what to do instead, nothing of this needs a network request or a server; the image shown is byte for byte the PNG that would be downloaded, at 1200×630 and 1080×1920, the dialog fits a phone: at 390×844 the image, the format switch and the actions are visible without scrolling sideways, and the image is not shown smaller than half its width allows
- **Tests:** share_dialog_shows_a_real_image, share_buttons_follow_capability, share_refusal_says_what_to_do, share_image_equals_the_download
- **Verify:** `python3 kit/.uak/tests/test_dashboard_truth.py`
- **Next step:** the Share dialog in kit/.uak/bin/lib/dash.html (search `toBlob` and `clipboard`); the capability checks are pure functions over an object that stands for `navigator`, so the cases run under node without a browser, and in Chromium with a phone profile when Playwright is present
## UAK-195 · CI has a browser: the cases that need one run there, and a case that did not run says so

- **Type:** fix
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-191
- **Paths:** .github/workflows/test.yml, scripts/ci_select.py, kit/.uak/tests/test_ci_browser.py, kit/.uak/tests/timings/test_ci_browser.txt, kit/.uak/docs/WHY.md, AGENTS.md
- **Acceptance:** the Linux suite jobs of the kit's CI install Chromium for Playwright (pinned version, cached between runs) before the tests, on pull requests and on main; the install's seconds are measured and written in WHY.md, and a pull request does not wait more than 60 s longer for it once the cache is warm. Why: on 2026-11-24 and 25 the reviews of UAK-159, UAK-162, UAK-192 and UAK-194 found defects that only a browser shows (a click refused in the first second after load, a tab that stopped drawing on partial data, a dialog that opened nothing); every case that needs Playwright passed in CI without running, so a green CI said nothing about them and each defect cost a review round, a test case that needs a browser and finds none does not print PASS: it prints `SKIP name (no browser)`, the file's result line counts skips, and on a job that declares it has a browser (an environment variable set by the workflow) a skip for lack of browser fails the file. On macOS and Windows, and on a developer's machine without Playwright, a skip stays a skip, the summary of a CI run says how many cases ran in a browser and how many were skipped, per system, the kit's rule is written once in AGENTS.md: behaviour of a page is tested in pure functions under node and in Chromium; a case that only reads the page's source does not count as testing a behaviour, nothing is downloaded at install time of the kit, and an installed project gains no file and no dependency: the browser is the kit's CI's, not the product's
- **Tests:** browser_cases_run_on_the_linux_job, skip_without_browser_is_not_a_pass, skip_fails_where_a_browser_is_declared, summary_counts_browser_cases, install_gains_no_file
- **Verify:** `python3 kit/.uak/tests/test_ci_browser.py && python3 kit/.uak/tests/test_ci_tiers.py && python3 scripts/kit_lint.py`
- **Next step:** how the existing cases find Playwright (search `playwright` in kit/.uak/tests: `test_setup_guide.py`, `test_setup_resume.py`, `test_dashboard_truth.py`, `test_setup_run_here.py`) and what they print when it is missing; the `suite` job in `.github/workflows/test.yml`; the workflow is the human's file, so the merge goes to the human. The helper that prints SKIP lives in each test file today: changing those files is not in this task's Paths, so this task adds the shared rule and the check of the result lines, and lists the files to convert for the tasks that own them
## UAK-196 · The wizard never kills a process it did not start, and the guard knows the wizard's new routes and files

- **Type:** fix
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-192
- **Paths:** kit/.uak/bin/lib/setup.py, kit/.uak/bin/guard, kit/.uak/docs/SECURITY.md, kit/.uak/tests/test_setup_processes.py, kit/.uak/tests/test_guard_wizard_files.py, kit/.uak/tests/timings/test_setup_processes.txt, kit/.uak/tests/timings/test_guard_wizard_files.txt
- **Acceptance:** every kill the wizard does checks that the process is still the one it recorded: `stop_children()` compares each recorded pid with its recorded start time, as `reap_children` and `TreeWatch.kill` already do, and skips a pid whose start time differs or cannot be read. Why: the review of UAK-192 planted a record whose stamp differed and `stop_children()` killed an unrelated process; since UAK-192 the record also holds the descendants of each run, so a pid that exits and is given to another program during a run could be killed when the wizard ends. The human's rule since the first day of this plan: the wizard must not ruin ports or processes, a case fails when the start-time check is removed from any of the three places (`stop_children`, `reap_children`, `TreeWatch.kill`): today removing it from `TreeWatch.kill` leaves the suite green, the sweep of launcher folders removes only folders this wizard created: the record line carries what proves it (the folder's device, inode and creation stamp, or a random name kept in the wizard's memory and its key file), and an empty `uak-agent-*` folder that a hand-written record names is left alone, while a wizard is live for the project, the guard refuses an agent's command that names `/api/run`, `/api/run/stop` or `/api/close` on the wizard's port or on a port it cannot read, and one that removes, empties or rewrites `uak-wizard.refused` or `uak-wizard.launchers`; with no live wizard the same commands pass, and the rules of UAK-188 keep their results on the cases of `test_guard_wizard_files` and `test_setup_trust`. Why: the reviews of UAK-159 and UAK-192 found the three routes missing from the guard's list (not exploitable: without the token the server answers 403) and that an agent could quietly delete the record of refused requests, an error of the `awk` the guard runs for the wizard's rules blocks the command and says so, instead of allowing it: today `WZ=$(awk …)` followed by `[ -z "$WZ" ] || block` lets every command through when `awk` fails (found by the author of UAK-188 when a duplicated function name made every refusal pass). A case runs the guard with an `awk` that exits non-zero, `uak-wizard.refused` cannot grow without bound: it keeps its last 200 lines, SECURITY.md lists the routes and the files as they are after this task, and what is still not covered on macOS (a descendant that started its own session and whose parent ended within the first poll), no foreground process is added to an unrelated command checked by the guard (counted as in UAK-188), and the wizard's idle CPU does not grow
- **Tests:** stop_children_checks_the_start_time, start_time_check_is_pinned_in_three_places, sweep_removes_only_its_own_folders, guard_refuses_the_new_routes_while_live, guard_protects_the_refused_and_launcher_records, awk_error_blocks, refused_record_is_bounded
- **Verify:** `python3 kit/.uak/tests/test_setup_processes.py && python3 kit/.uak/tests/test_guard_wizard_files.py && python3 kit/.uak/tests/test_setup_trust.py`
- **Next step:** `stop_children`, `reap_children`, `TreeWatch` and the launcher sweep in kit/.uak/bin/lib/setup.py; the wizard's endpoint regex in kit/.uak/bin/guard (line 716 at UAK-192) and `WZ=$(awk` (lines 133 and 346 at UAK-188); the guard is the human's file, so the merge goes to the human
