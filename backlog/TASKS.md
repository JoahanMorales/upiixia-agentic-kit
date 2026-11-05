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
