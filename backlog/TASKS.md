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
