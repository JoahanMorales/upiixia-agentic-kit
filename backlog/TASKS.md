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
