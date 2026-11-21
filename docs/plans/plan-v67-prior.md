## UAK-075 · The kit ships a default design prior learned from real rounds, so every team starts from it

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-074
- **Paths:** kit/.uak/settings/design-prior.json, kit/.uak/bin/lib/design_prior.py, scripts/design_prior.py, kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_prior.py
- **Acceptance:**
  - `kit/.uak/settings/design-prior.json` is shipped and versioned: per gene value a weight with its evidence (picks/shown across how many distinct projects), only traits — no names, no project names, no hex, no pages, no notes text
  - `python3 scripts/design_prior.py --from ~/.uak/taste/<human>.json [--from ...]` (maintainers, at release) writes it; a trait enters the prior only when it was picked in at least 2 distinct projects with a weight clearly above or below neutral; stylistic genes (type family, ground/color family, scale) are kept neutral unless 3+ projects agree, so the prior never pushes every team to the same look
  - `uak design round` draws with: prior (when no personal/team profile, or blended with it), then the personal/team profile on top; `--no-prior` turns it off; the "why" of each gene says "prior", "taste" or "spread"
  - the kit's own round rules (bounds, desktop first, stand-by loop, stage, fonts, ground balance, performance, information density) stay in TASK.md/landing-story for everyone regardless of the prior
  - the release checklist (CHANGELOG step) regenerates the prior from the maintainers' profiles and records how many rounds/projects it came from
  - Why (2026-11-12, the human): "I thought this was becoming a default of the kit: these iterations are so that anyone gets the best version on GitHub, not that everyone builds their own model"; today the profile lives only in ~/.uak/taste of one machine
- **Tests:** prior_has_traits_only, needs_two_projects_to_enter, stylistic_genes_stay_neutral, round_uses_prior_without_profile, profile_blends_over_prior, no_prior_flag
- **Verify:** `python3 kit/.uak/tests/test_design_prior.py`
- **Next step:** a new kit/.uak/bin/lib/design_prior.py, then the weights argument of make_genomes in design_round.py

## UAK-076 · A team's taste lives in the project repo and one person has one profile

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-067
- **Paths:** kit/.uak/bin/lib/design_taste.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_taste_team.py
- **Acceptance:**
  - `uak design taste --team` folds the project's rounds into `.uak/design/taste.json` in the repo (committed like the rest of .uak/design), so a team shares one profile across machines; round 1 uses team → personal → prior, in that order
  - the pick page's name field defaults to UAK_HUMAN / git user.name and suggests existing profile names; a typed name that differs only in case, accents or a known alias (`.uak/design/aliases` or `~/.uak/taste/aliases`) maps to the same profile
  - `uak design taste --merge A B` merges two profiles of the same person
  - Why (2026-11-12): the same human ended with two profiles ("joahan" from the colonIA page, "JoahanMorales" from the CLI) and a profile that never leaves one machine
- **Tests:** team_profile_in_repo, order_team_personal_prior, name_variants_map_to_one_profile, merge_two_profiles
- **Verify:** `python3 kit/.uak/tests/test_design_taste_team.py`
- **Next step:** profile path resolution in kit/.uak/bin/lib/design_taste.py

## UAK-077 · Landings breathe: an information-density budget for the hero, stated and measured

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-075, UAK-073
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/skills/landing-story/SKILL.md, kit/.uak/tests/test_design_density.py
- **Acceptance:**
  - TASK.md and landing-story state a hero budget at 1920×1080 and 1280×720: one headline, one sentence, one or two actions, at most 3 secondary elements (a stat, a legend, a badge) besides the stage; at most ~45 words in the fold; the stage carries the story, the text doesn't repeat it; no text block over the stage's focal point
  - the capture counts, at the fold of each viewport, visible text elements and words (and how many overlap the stage's canvas/SVG), writes them to metrics.json, and flags "dense" over the budget; the pick page shows it
  - later sections: one idea per section, no section with more than ~4 cards or ~80 words
  - Why (colonIA R1, 2026-11-12): the human on v1, v5 and v6: "too much information, things pop up everywhere and it looks saturated, it's too much for anyone"; on v5 "the pink text doesn't let you see the background"
- **Tests:** budget_in_task_and_skill, capture_counts_words_and_elements, dense_flag_over_budget, overlap_with_stage_counted
- **Verify:** `python3 kit/.uak/tests/test_design_density.py`
- **Next step:** task_text in design_round.py and section 2 of landing-story

## UAK-078 · Color is a palette with roles and proportions, measured from the page, and that is what taste learns

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-077
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_color.py, kit/.uak/bin/lib/design_taste.py, kit/.uak/tests/test_design_color.py
- **Acceptance:**
  - each variant gets a palette with roles built from the project's brand colors (brief.md): ground, ink, primary, accent(s), with target area shares (e.g. 60/30/10 or a stated alternative per strategy) and a maximum share for any saturated color; strategies replace the bare labels (monochrome + one accent, brand duo, full brand range, tinted neutrals, …) and are written into TASK.md with the exact hex per role
  - contrast: ink on ground ≥ 7:1, primary text/buttons ≥ 4.5:1 (checked from the hex, before building)
  - the capture measures the real color use at the 1920 fold (share of saturated pixels, share of dark pixels, the 5 dominant colors and their areas, how much of each brand color appears) into metrics.json; the pick page shows a palette strip per variant
  - the taste profile learns from the measured features (saturation share, dark share, brand-color coverage, number of hues), not only from the gene label, so "uses color well" is learned as numbers
  - Why (2026-11-12, the human: "the taste profile uses colors very badly"): measured at the fold, all six AXIA R3 pages were 1–3 % saturated (an almost monochrome navy; the Kavak blue barely appears) while their label said "ink + one accent" or "dark media"; colonIA v4 used a washed pink ("doesn't use the colors well"); the profile learned the labels, not what was on screen
- **Tests:** palette_roles_from_brand_colors, contrast_checked, capture_measures_color_use, taste_learns_measured_color, pick_shows_palette_strip
- **Verify:** `python3 kit/.uak/tests/test_design_color.py`
- **Next step:** a new kit/.uak/bin/lib/design_color.py (roles, contrast, measuring a PNG with the stdlib zlib PNG reader), then task_text

## UAK-079 · test_v59 "a Verify that does not parse is refused" stops flaking under parallel load

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/tests/test_v59.py, kit/.uak/bin/lib/lint.sh, kit/.uak/bin/lib/plan.sh
- **Acceptance:**
  - find why, under load, `uak lint` reads the old Verify of a task the test just pushed (the failure shows `LINT_OK` plus the negated-rg warning instead of the refusal): a stale claims cache, a fetch that returns before the push is visible, or the test reading too early; fix the cause (not a sleep)
  - the test passes 30 times in a row under `smoke --jobs 4` and alone; a regression case reproduces the race deterministically (e.g. a forced stale cache)
  - Why (v6.1.1 → v6.3, 2026-11-11/12): it failed in 2 of 4 parallel runs during UAK-054 and again in the full smoke before merging UAK-068, each time passing alone; flaky gates train people to rerun instead of read
- **Tests:** a_verify_that_does_not_parse_is_refused, stale_claims_cache_still_refuses
- **Verify:** `python3 kit/.uak/tests/test_v59.py`
- **Next step:** reproduce with `for i in $(seq 30); do UAK_SMOKE_TESTS="test_v59 test_hack test_v58 test_v42" bash kit/.uak/bin/smoke --package-only --jobs 4 || break; done`
