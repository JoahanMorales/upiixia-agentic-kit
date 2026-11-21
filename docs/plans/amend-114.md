## UAK-114 · An unapproved task recorded INTEGRATED says so, and in marathon it needs a human

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/bin/stats, kit/.uak/tests/test_integrate_unreviewed.py
- **Acceptance:**
  - sprint (and any mode that is not marathon): `integrate` of a CLAIMED, BLOCKED or AVAILABLE task whose content is on main, with no valid approval, works for an agent as today (the board must tell the truth during an event), and its record keeps `Integrated-Outside: yes` and adds `Unreviewed: yes`; the output says the code reached main without a review
  - marathon: the same integrate needs a human (`UAK_HUMAN=NAME … --reason TEXT`); an agent gets the refusal used from REVIEW, with the line the human runs; the record adds `Unreviewed: yes` and the reason goes to DECISIONS.md
  - with a valid approval of that SHA by another seen identity, an agent integrates in both modes and no `Unreviewed` field is written (UAK-092 behaviour kept)
  - `uak stats` keeps its `outside the gate: N` line and adds how many of them were unreviewed
  - the existing tests of test_integrate_outside.py stay untouched and pass (they run in sprint)
  - Why (audit of v6.5.0, docs/audit-2026-11.md #7; decided by the human on 2026-11-21): integrate required a human only from REVIEW, so an owner could unlock dependents on unreviewed code; an agent integrating outside the gate is by design in sprint (deus-ex-machina: PRs merged on GitHub that the claims never learned about), so the rule depends on the mode and the record always says it
- **Tests:** sprint_agent_integrates_and_record_says_unreviewed, marathon_agent_is_refused, marathon_human_records_it_with_a_reason, approved_sha_integrates_in_both_modes, stats_counts_unreviewed
- **Verify:** `python3 kit/.uak/tests/test_integrate_unreviewed.py`
- **Next step:** integrate_mutate at kit/.uak/bin/lib/done.sh:203-241; the `outside the gate` line in kit/.uak/bin/stats
