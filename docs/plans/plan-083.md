## UAK-083 · A bred round keeps the rules of a fresh one: picked palettes, distinct fonts, at most two three.js stages, re-shoot

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-071, UAK-073, UAK-078
- **Paths:** kit/.uak/bin/lib/design_breed.py, kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_fonts.py, kit/.uak/tests/test_design_breed_rules.py, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/docs/WHY.md, kit/.uak/tests/test_design_breed.py, kit/.uak/tests/test_design_breed_notes.py, kit/.uak/tests/test_design_fonts.py, kit/.uak/tests/test_design_perf.py, kit/.uak/tests/test_design_round.py
- **Acceptance:**
  - `design round --from R<k>` gives every child the palettes of the latest palette round with picks (as a fresh round does, via `design_color.picked_palettes` + `with_ground`), and the color gene agrees with the palette's ground
  - no two variants of a bred round share a display face: a child keeps its parent's pair only when no sibling has it; otherwise it gets a distinct pair of the same `type` gene (and never a past direction's face)
  - a round (fresh or bred) has at most `Design-Max-WebGL` variants whose stage is three.js (default 2, PROJECT.md); the extra ones move to a light stage (canvas 2D, SVG/CSS, scroll, video) and the genome's `because` says why
  - `design shoot R<k> [v<i>…] --again` recaptures variants that already have PNGs (today the only way is deleting them); the "already had N" line names the flag
  - when Playwright for Python is missing and the fallback writes screenshots without a QA report, `design shoot` says how to install it (`pip install playwright && python -m playwright install chromium`) instead of only "not captured"
  - Why (colonIA R2, 2026-11-14): bred from R1, the round had no palettes (the human's picks of P1 were ignored), v1/v3 both Anton and v2/v4 both Fraunces (the human, after AXIA: "las fuentes en todos ya son las mismas"), 4 of 6 stages three.js (the human: "no gastar cantidades exageradas de recursos en el three js"); the lead fixed all three by hand
- **Tests:** bred_round_uses_picked_palettes, bred_round_fonts_distinct, webgl_cap_fresh_and_bred, shoot_again_recaptures, shoot_says_how_to_install_playwright
- **Verify:** `python3 kit/.uak/tests/test_design_breed_rules.py`
- **Next step:** the children loop at the end of `run()` in kit/.uak/bin/lib/design_breed.py (after `design_fonts.inherit`), reusing the palette block of design_round.py:789
