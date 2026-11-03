# Amended tasks (uak plan --amend)

Append-only; the last section of an ID replaces its section in the backlog. Why: Paths can grow before review.

## UAK-009 · The process counter counts ps, measures next for an idle agent too, and names traces uniquely (follow-up of UAK-001)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-001
- **Follow-up of:** UAK-001
- **Paths:** kit/.uak/tests/test_claims_perf.py, scripts/perf_claims.sh
- **Freeze-Allowed:** no
- **Acceptance:** the counter's shims include `ps` (next and status call it; they were 5 processes short), `next` is also counted for an agent with no claim (choosing a task, not resuming one), trace and stdin file names are unique per call (no time-based names: Windows Python before 3.13 ticks coarsely)
- **Tests:** the_counter_sees_ps, next_for_an_idle_agent_starts_at_most_40_processes
- **Verify:** `python3 kit/.uak/tests/test_claims_perf.py`
## UAK-006 · Proof of no change, and the targets turned on

- **Type:** integration
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-003, UAK-004, UAK-005, UAK-008, UAK-010
- **Paths:** scripts/claims_diff.py, kit/.uak/tests/test_claims_perf.py, kit/.uak/bin/lib/, kit/.uak/bin/uak, kit/.uak/bin/uak-coordination, docs/perf-windows.md
- **Acceptance:** the protocol suites run the old and the new engine side by side on the same fixtures: every command's stdout and the resulting claims tree are identical, the XFAIL set of test_claims_perf.py is empty: next ≤ 40, status ≤ 30, heartbeat ≤ 20 processes, docs/perf-windows.md has the before and after times from `scripts/perf_claims.sh` on Windows
- **Tests:** old_and_new_engines_print_the_same_and_write_the_same_tree
- **Verify:** `python3 scripts/claims_diff.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** reuse the guard differential of v5.9.2 (docs/perf-windows.md)

