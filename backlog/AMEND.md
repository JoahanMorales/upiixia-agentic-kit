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
