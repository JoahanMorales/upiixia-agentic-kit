## UAK-080 · Breeding from near-identical picks explores instead of failing

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_breed_twins.py
- **Acceptance:**
  - when the picks share most of their genes (e.g. 8 of 9), `design round --from` still produces N children: the relaxation ladder's last step treats children of near-identical picks as kin for the shared-genes rule (they only must not be identical), and the round adds wildcards so at least ⌈N/3⌉ children differ from every pick in 4+ genes; every relaxation is recorded in "because"
  - the ground balance (UAK-072) and distinct fonts for wildcards still hold
  - the human sees why: the cost/mix line says "picks nearly identical (8/9 genes): exploring with N wildcards"
  - Why (AXIA R3, 2026-11-13): the human picked v5 and v3 (both dark, serif, 8 of 9 genes shared); `design round --from R3` failed on every seed with "could not breed … diversity rule", before and after UAK-072 — exactly when the human most needs the kit to explore
- **Tests:** twins_still_breed, twins_round_has_explorers, ground_and_fonts_hold_for_twins, because_explains_twins
- **Verify:** `python3 kit/.uak/tests/test_design_breed_twins.py && python3 kit/.uak/tests/test_design_breed.py`
- **Next step:** the relaxation ladder in kit/.uak/bin/lib/design_breed.py (after the rejected-values steps)
