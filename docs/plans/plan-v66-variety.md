## UAK-071 · Each variant gets a real font pair, different from the rest of the round and from past directions

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-068
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_fonts.py, kit/.uak/tests/test_design_fonts.py
- **Acceptance:**
  - every value of the `type` gene has a pool of at least 6 vetted Google Fonts pairs (display + body, with weights), kept in design_fonts.py; Inter, Roboto, Arial and Geist are never a display face
  - a round assigns one exact pair per variant (TASK.md and genome.json `fonts`): no two variants of a round share a display or body face; bred children keep the parent's pair unless `type` mutated
  - fonts of past directions in the taste profile (read from the winning page's Google Fonts link) are not reused in a new project's round 1 (`--allow-repeat` lifts it); the profile records the winning pair
  - design-lint (round folder) warns when a variant's page loads a different pair than its TASK.md assigned
  - Why (AXIA R3, 2026-11-11): the type gene said "serif display" and all six agents picked the same pair (Fraunces + Geist); the human: "the fonts in all of them are the same now, they need more variety"
- **Tests:** pools_have_six_pairs, round_pairs_all_distinct, child_keeps_parent_pair, past_direction_fonts_not_reused, lint_flags_wrong_pair
- **Verify:** `python3 kit/.uak/tests/test_design_fonts.py`
- **Next step:** a new kit/.uak/bin/lib/design_fonts.py, then `task_text` in design_round.py

## UAK-072 · Rounds keep light and dark in balance; taste cannot drift a round to one ground

- **Type:** feature
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** UAK-071
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_ground.py
- **Acceptance:**
  - each genome gets a `ground` (light or dark) derived from its color gene (dark media → dark; light paper → light; ink + one accent, brand duo, saturated field → drawn), written into TASK.md
  - a round of N ≥ 4 has at least ⌈N/3⌉ light and ⌈N/3⌉ dark variants, also bred rounds (a dark parent's child may be flipped to light, recorded in "because") and taste-seeded rounds
  - the taste profile stores ground as a trait like the others
  - Why (AXIA R1–R3): dark won 4 of 5 picks and breeding drifted every later round to dark; the human: "the dark ones gained too much ground over the white ones"
- **Tests:** ground_derived_from_color, round_has_third_light_and_dark, bred_round_flips_to_keep_balance, taste_cannot_make_all_dark
- **Verify:** `python3 kit/.uak/tests/test_design_ground.py && python3 kit/.uak/tests/test_design_breed.py`
- **Next step:** after make_genomes in design_round.py and after breed() in design_breed.py

## UAK-073 · An animation performance budget the capture measures

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-070
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_perf.py
- **Acceptance:**
  - TASK.md states the budget for three.js stages: low-power context, DPR ≤ 1.5, ≤ ~40k points or ~10k instances (InstancedMesh / one BufferGeometry), render only while visible, hero capped at 30 fps, drop detail when frames run slow; and for SVG/canvas/CSS stages: animate transforms and opacity, not layout
  - the capture measures, per viewport, the average frame interval over 3 s (requestAnimationFrame), long tasks and JS heap, writes them to the variant's metrics.json, and flags "heavy" over a threshold set in PROJECT.md (`Design-Frame-Budget-Ms:`, default 50 for WebGL stages and 20 for the rest, on the machine that captures)
  - `uak design pick` shows the frame time and the heavy flag under each variant
  - Why (AXIA R3 → colonIA R1, 2026-11-11): the human: "it has to find a way not to spend exaggerated resources on three.js"; measured on the Jetson: an R3 three.js hero ran at 122 ms per frame (~8 fps) against 17 ms for an SVG one, and six three.js pages captured at once saturated the machine
- **Tests:** budget_in_task_for_webgl_stage, frame_time_recorded, heavy_flag_over_threshold, pick_shows_frame_time
- **Verify:** `python3 kit/.uak/tests/test_design_perf.py`
- **Next step:** the capture in design_round.py (port the perf probe of ~/Proyectos/design-rounds/bin/shoot-patient.js)

## UAK-074 · The brief finds the project's material and story beats the way teams really write them

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1.5 h
- **Depends on:** UAK-072
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_brief_real.py
- **Acceptance:**
  - PNG/JPG files whose width ≥ 1000 and aspect ≈ 16:9 or 16:10 are classified as product screens (not "3D cut-out"); a PNG with a transparent background is a cut-out; .geojson/.json with coordinates is "real data (map)"; .mp4/.webm is video — and brief.md lists real data
  - the wow is found in "Wow in one sentence:", a `**Wow:**` cell, or a "**Wow N:**" mark inside the flow table; the ask in an `Ask:` line or the CTA of the live product's index.html; headings in Spanish ("Una línea", "Usuarios", "Flujo de la demo", "Datos citables") count like the English ones
  - the project's name comes from IDEA.md §0's name line, else the web/index.html <title>
  - Why (colonIA R1, 2026-11-11): the brief said wow MISSING and ask MISSING although IDEA.md has both, and classified four real product screens as "3D cut-out" while missing the real hex.geojson; the lead fixed brief.md by hand
- **Tests:** screens_vs_cutouts, geojson_is_real_data, wow_inside_flow_table, spanish_headings, name_from_title
- **Verify:** `python3 kit/.uak/tests/test_design_brief_real.py`
- **Next step:** the brief/material readers in kit/.uak/bin/lib/design_round.py
