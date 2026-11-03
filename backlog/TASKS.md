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
