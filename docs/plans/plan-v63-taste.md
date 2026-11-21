## UAK-062 · A taste profile learned from every pick, kept per human across projects

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/design_taste.py, kit/.uak/tests/test_design_taste.py
- **Acceptance:**
  - `design_taste.update(project_root, human)` reads every round of the project (`.uak/design/rounds/R*/genome.json` + `picks.json`) and folds it into `~/.uak/taste/<human>.json` (`UAK_TASTE_HOME` overrides the folder): per gene value, how often it was shown, picked first, picked, and never picked; the human's notes per gene value; and the project's final direction (the last converged or final pick) with its genome, project name and date
  - the profile stores traits, not templates: weights per gene value (Laplace-smoothed picked/shown), never a palette's hex values or a whole page; the final genomes are kept only as "past directions" for novelty (UAK-063)
  - idempotent: folding the same round twice changes nothing (each round is keyed by project + round id)
  - `design_taste.show(human)` prints, per gene, the values from most to least liked with counts, and the past directions, in under 40 lines
  - a profile with fewer than 10 picks says it is still learning (`confidence: low`) so rounds keep exploring
  - Why (v6.2, the human): once a genome wins, every project must not come out the same; the kit learns what the human likes, not what one page looked like
- **Tests:** folds_picks_into_weights, folding_twice_is_idempotent, stores_traits_not_hex, past_directions_recorded, low_confidence_under_ten_picks
- **Verify:** `python3 kit/.uak/tests/test_design_taste.py`
- **Next step:** read genome.json / picks.json the way kit/.uak/bin/lib/design_breed.py does (import its readers, do not copy)

## UAK-063 · Round 1 of a new project is seeded by taste, shaped by the project, and never repeats a past direction

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-062
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_round_taste.py
- **Acceptance:**
  - `uak design round` (first round of a project) draws gene values weighted by the human's profile (`--human NAME`, default `UAK_HUMAN`, then git user.name): liked values are more likely, never certain; with `confidence: low` or no profile it draws as today
  - exploration stays: at least 2 variants per round (1 when N ≤ 4) ignore the profile entirely (wildcards), and the ≤ 3 shared genes rule still holds
  - novelty: no variant shares more than 5 of the 8 genes with any past direction in the profile (another project's winner), so a new project never starts as a copy of the last one; `--allow-repeat` lifts it
  - the project shapes the round, not only the profile: (a) the default seed comes from the project's name, not 1; (b) the color gene gets the project's own brand colors when they exist (hex values in IDEA.md §0, CSS custom properties under web/, fills in SVGs under assets/ or web/public/), written into brief.md as "Brand colors (from the project)"; (c) the imagery gene prefers what the project really has (real product screens, photos, video, a map, a mascot) — values with no material behind them are drawn less; (d) brief.md gets a "Subject world" beat: the agent building each variant lists 3–5 concrete things from the project's domain (its objects, instruments, units, local vernacular) and uses at least one as a visual element
  - each genome.json records why each gene was chosen (`"why": {"color": "brand duo · project colors #0367FC #0B1020", "type": "taste 0.71", "layout": "wildcard"}`) so the human can see what the kit learned
  - the cost line and `--dry-run` show how many variants come from taste, wildcards and novelty constraints
- **Tests:** liked_values_drawn_more_often, wildcards_ignore_taste, never_repeats_a_past_direction, seed_comes_from_project_name, project_colors_reach_the_brief, imagery_follows_available_material, why_is_recorded
- **Verify:** `python3 kit/.uak/tests/test_design_round_taste.py && python3 kit/.uak/tests/test_design_round.py`
- **Next step:** `make_genomes` in kit/.uak/bin/lib/design_round.py (add an optional weights/constraints argument; keep its signature compatible for design_breed.py)

## UAK-064 · `uak design taste`: update and show the profile; the pick saves feed it

- **Type:** feature
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** UAK-062
- **Paths:** kit/.uak/bin/design, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_design_taste_cli.py
- **Acceptance:**
  - `bash .uak/bin/uak design taste [--human NAME]` prints the profile (design_taste.show); `uak design taste --update` folds the current project's rounds
  - a save in `uak design pick` folds that round into the picker's profile right away (the name typed on the page, else UAK_HUMAN); a failure to write the profile never fails the save, it is reported on the page
  - `uak design taste --forget PROJECT` drops one project's rounds and direction from the profile (the human may want a fresh start)
  - CLI.md regenerated by scripts/gen_registry.py
- **Tests:** taste_command_prints_profile, pick_save_updates_profile, forget_drops_a_project
- **Verify:** `python3 kit/.uak/tests/test_design_taste_cli.py`
- **Next step:** the `pick` branch of kit/.uak/bin/design and the save handler in kit/.uak/bin/lib/gallery_pick.py

## UAK-065 · Bred rounds read the human's notes: mutate what the note names, and never send wildcards into rejected genes

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_breed_notes.py
- **Acceptance:**
  - a pick's note that names a gene ("colores", "color", "fondo", "background" → color; "tipografía", "letra", "font" → type; "espacio", "acomodación", "layout", "flujo" → layout; "animación", "movimiento" → motion; "formal", "divertida", "tono" → voice; Spanish and English) makes that gene the one mutated for that parent's children; with no named gene it stays random
  - a variant the human did not pick and whose note is negative ("no me gustó", "la peor", "lastiman", "feo", "hate", "ugly") marks its gene values as rejected for the next round: wildcards may not use them; when the "no pick's value" rule leaves only rejected values for a gene, the wildcard takes a picked value instead (it is still a wildcard on the other genes)
  - each child's genome.json records `"because": "note on R1/v6: el fondo debería ser completamente blanco → color"` when a note chose the gene
  - Why (AXIA R2, 2026-11-11): the human picked 3 and annotated all 6, but breeding mutated scale where the note asked for colors, and both wildcards fell on the saturated blue fields the human said "hurt the eyes"; the lead had to search seeds and override two genes by hand
- **Tests:** note_naming_color_mutates_color, rejected_values_never_reach_wildcards, wildcard_falls_back_to_a_picked_value, because_is_recorded
- **Verify:** `python3 kit/.uak/tests/test_design_breed_notes.py && python3 kit/.uak/tests/test_design_breed.py`
- **Next step:** the mutation and wildcard choice in kit/.uak/bin/lib/design_breed.py

## UAK-066 · design-lint checks a round's static variants (tokens inside the page's <style>)

- **Type:** bug
- **Priority:** P2
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/design-lint, kit/.uak/tests/test_design_lint_html.py
- **Acceptance:**
  - tokens (CSS custom properties) inside an .html file's <style> count as design tokens, so design-lint no longer prints DESIGN_LINT_SKIP for a folder of static pages and runs its scale checks (UAK-061) and tells on them
  - `design-lint .uak/design/rounds/R<k>` lints every v*/index.html of a round and names the variant in each finding
  - Why (AXIA R1): design-lint skipped all six variants of the first real round ("no design tokens yet") because their tokens live in <style>, so its giant-type warnings never ran where they matter most
- **Tests:** html_style_tokens_count, round_folder_lints_each_variant, scale_warning_names_the_variant
- **Verify:** `python3 kit/.uak/tests/test_design_lint_html.py`
- **Next step:** the token detection at the top of kit/.uak/bin/design-lint (the `tokfiles` find)

## UAK-067 · `uak design shoot` gives videos a real poster and the human sees full pages, not only the fold

- **Type:** feature
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** UAK-063, UAK-064
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_shoot_full.py
- **Acceptance:**
  - the Playwright capture waits for media: a <video> is seeked to 30 % of its length (or to its poster) before the shot, so captures never show an empty first frame
  - captures also write 1280-full.png and 390-full.png; the pick page shows the fold by default and the full page on a toggle, plus a link to each variant's live index.html served by the same server
  - Why (AXIA R1): two variants looked broken in their captures because the video's first frame is empty; the human judged six landings from their first screen only
- **Tests:** video_is_not_captured_blank, full_page_captures_written, pick_page_links_live_variant
- **Verify:** `python3 kit/.uak/tests/test_design_shoot_full.py`
- **Next step:** the playwright branch of `capture_one` in kit/.uak/bin/lib/design_round.py
