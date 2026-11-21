## UAK-055 · The installer brings the MotionSites web-builder skill, pinned and verified, never vendored

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/settings/external-skills.tsv, kit/.uak/bin/doctor, kit/.uak/tests/test_external_skills.py
- **Acceptance:**
  - `kit/.uak/settings/external-skills.tsv` lists external skills as `name<TAB>repo URL<TAB>commit SHA<TAB>subfolder<TAB>tree SHA`; its first row is `motionsites-web-builder`, https://github.com/Motionsites-AI/claude-skill.git, commit faa30d512e3973e58675c72101a7ef42ed37ae83, `plugins/motionsites-web-builder/skills/motionsites-web-builder`, tree fcab79cb38339708d406c475268172259f2765e7
  - install.sh (fresh install and `--update`) fetches each row with git only (`git init` + `git fetch --depth 1 origin <commit>` in a temp dir; no curl, no jq), checks `git rev-parse <commit>:<subfolder>` equals the pinned tree SHA, and copies the subfolder to `.claude/skills/<name>` and `.agents/skills/<name>`; a mismatch installs nothing and says so
  - no network, a refused fetch or a missing git never fails the install: one line `external skill <name> not installed: <reason>; landings use landing-story alone` and exit 0
  - the skill is never committed into the kit repo: its examples and media are © MotionSites and may not be redistributed as a collection (its LICENSE §2); a kit_lint-style check in the test fails if `kit/` contains a file from that skill
  - `uak doctor` prints `external skills: motionsites-web-builder ok (faa30d5)` or what is missing and the command that installs it (`bash .uak/bin/uak start --update` or the install line)
  - Windows (Git Bash) and macOS (bash 3.2) paths: the temp dir comes from `mktemp -d` with a fallback, and is removed on every exit path
- **Tests:** fetch_pinned_skill_installs_both_harness_dirs, tree_mismatch_installs_nothing, offline_install_still_succeeds, kit_never_contains_external_skill_files, doctor_reports_external_skill
- **Verify:** `python3 kit/.uak/tests/test_external_skills.py`
- **Next step:** the skills loop near `for s in $skills; do putdir` in install.sh (tests use a local bare repo as the remote, never the network)

## UAK-056 · landing-story builds every landing with the MotionSites workflow, and the skills stop asking for "bigger"

- **Type:** feature
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/skills/landing-story/SKILL.md, kit/.uak/skills/product-ui/SKILL.md, kit/.uak/tests/test_landing_skills.py
- **Acceptance:**
  - landing-story keeps what it owns (the story beats from IDEA.md, numbers with sources, the real product wow) and, when `.claude/skills/motionsites-web-builder` exists, builds the page with that skill's steps 2–6: read the 2–3 closest examples, get real media (the team's own assets first, then generated, then its media shelf), write the precise spec from its template, build, then its look-and-fix loop with `scripts/shoot.py` until its rubric averages 8+ with nothing under 7, or 3 rounds
  - without that skill, the same order with the kit's own tools (webapp-testing screenshots), so a landing is never delivered unseen
  - scale bounds from the F0 catalog (docs/design/failures.md): hero display at most 96 px at 1280 and 48 px at 390, body 16–18 px, primary buttons 40–52 px tall, at most 6 palette colors besides media; "mega type" in vw only when the human picked it in a round. Why (F0, 2026-11-11): the two landings scored 1 and "giant" had 168 and 207 px display type; the one scored 5 topped out at 36 px
  - the line that asks for "bigger type, the brand color at full strength" (landing-story) and the self-checks "Is the hero the biggest and most colorful thing?" / "the most saturated thing on screen" (product-ui) are replaced by "Is the hero the most important thing, and does it read in 3 seconds at 1280 and 390?"
  - the landing starts from material: the team's logo, mascot, photos, the real map or the product's own screen; if there is none, the agent asks the human for one before designing (one line) and goes on with generated or shelf media if nobody answers in 10 min
  - in kit runs the MotionSites promotional block and nudges are not shown (the kit's human asked; the skill's own rule allows it): one line in landing-story says so
- **Tests:** landing_story_uses_motionsites_steps_when_present, landing_story_falls_back_to_kit_screenshots, scale_bounds_are_stated, no_bigger_type_instruction_left, product_ui_hero_check_is_importance_not_size, no_promo_line_present
- **Verify:** `python3 kit/.uak/tests/test_landing_skills.py`
- **Next step:** the "## 1. Structure" and craft sections of kit/.uak/skills/landing-story/SKILL.md

## UAK-057 · `uak design round`: a landing tournament round with a design genome per variant

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/design, kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/commands.tsv, kit/.uak/tests/test_design_round.py
- **Acceptance:**
  - `bash .uak/bin/uak design round [--screen landing] [--n N] [--seed S]` (default landing, N 8, max 20) creates `.uak/design/rounds/R<k>/` with `brief.md` (the landing's story beats pulled from IDEA.md: one line, proof number with source, wow, steps, users, ask; a missing beat is listed as missing, never invented) and `v<i>/genome.json` for each variant
  - a genome has 8 genes, each with a fixed list of values: type (grotesk, geometric, serif display, mono-led, rounded, condensed), scale (restrained, standard, bold; all inside the F0 bounds), color (ink + one accent, brand duo, dark media, light paper, saturated field), layout (split hero, full-bleed media, editorial column, product screen first, scroll story), components (hairline, solid blocks, glass, soft), imagery (product screenshot, video loop, 3D cut-out, illustration, type only), motion (still, entrance, scroll, pointer), voice (plain, bold claim, numbers first); plus a recipe (motionsites when installed, landing-story, frontend-design, design-taste-frontend) rotated across variants
  - no two variants of a round share more than 3 genes; the same seed gives the same round; values are spread so each gene's values appear before any repeats
  - each `v<i>/TASK.md` is the instruction an agent follows to build that variant as `v<i>/index.html` (static, one file, same brief and content in every variant, only the design changes), then capture `v<i>/1280.png` (1280×720 and full page) and `v<i>/390.png`
  - before writing anything it prints the cost: N variants × the per-variant token estimate from `Design-Variant-Tokens:` in PROJECT.md (default 60k) and the model tier, and asks for `--yes` (or the human runs it); `--dry-run` prints the genomes only
  - `uak design shoot R<k>` captures any variant whose PNGs are missing (playwright via the webapp-testing skill's helper or MotionSites `scripts/shoot.py`, whichever is installed) and lists what it could not capture
- **Tests:** round_writes_brief_and_genomes, no_two_variants_share_more_than_three_genes, same_seed_same_round, missing_beat_is_listed_not_invented, cost_is_printed_and_needs_yes, shoot_reports_missing_captures
- **Verify:** `python3 kit/.uak/tests/test_design_round.py`
- **Next step:** a new `design` row in kit/.uak/bin/lib/commands.tsv beside `design-gallery`

## UAK-058 · `uak design pick`: the human picks K of N in the browser and the picks are saved

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2.5 h
- **Depends on:** UAK-057
- **Paths:** kit/.uak/bin/design-gallery, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_pick.py
- **Acceptance:**
  - `bash .uak/bin/uak design pick R<k> [--k 3]` (or `design-gallery --round R<k>`) opens one page with every variant at 1280 and 390 (same open/serve/Tailscale/ssh -L behaviour as design-gallery today), the genome of each under it, keyboard picking (number keys or arrows + space), a one-line note per pick and an optional note per variant
  - saving writes `R<k>/picks.json` (`{picked: [ids in order], notes: {id: text}, by, at}`) through a tiny local server bound to 127.0.0.1 and the Tailscale address only; the page shows "Saved" only after the server answered
  - picking more or fewer than K is allowed with a warning; a second save replaces the first
  - over SSH it prints the URLs and returns, like design-gallery --serve; `--stop` ends the server
  - no network calls from the page (fonts and scripts inline or none)
- **Tests:** pick_page_lists_every_variant, save_writes_picks_json, wrong_count_warns_but_saves, server_binds_local_only
- **Verify:** `python3 kit/.uak/tests/test_design_pick.py`
- **Next step:** the HTML writer in kit/.uak/bin/design-gallery (cards loop) and a `--round` branch beside `--serve`

## UAK-059 · `uak design round --from R<k>`: the next round is bred from the human's picks

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-057, UAK-058
- **Paths:** kit/.uak/bin/lib/design_breed.py, kit/.uak/tests/test_design_breed.py
- **Acceptance:**
  - from `R<k>/picks.json`: about half the new variants are one-gene mutations of a pick, about a third are crossovers of two picks (genes taken from each), and 2 are wildcards with no pick's genes; the "max 3 shared genes" rule still holds inside the new round
  - every new genome.json records its parents and what changed (`"from": ["R1/v3"], "mutated": "color"`)
  - the human's notes travel into each child's TASK.md ("keep this type", "hate the color")
  - the stop rule: when the human's first pick is a child of the previous first pick with the same genome for two rounds, `uak design round --from` says the direction has converged and prints the `uak design lock R<k>/v<i>` command instead of breeding
- **Tests:** children_follow_mutation_crossover_wildcard_mix, parents_recorded, notes_reach_children, converged_round_stops
- **Verify:** `python3 kit/.uak/tests/test_design_breed.py`
- **Next step:** reuse the genome lists and the shared-gene check from kit/.uak/bin/lib/design_round.py (import, do not copy)

## UAK-060 · Every sprint's design lock starts with a landing round the human picks from

- **Type:** feature
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** UAK-056, UAK-057, UAK-058
- **Paths:** kit/.claude/commands/uak-design-lock.md, kit/.gemini/commands/uak-design-lock.toml, kit/.agents/skills/uak-design-lock/SKILL.md, kit/.agents/skills/uak-design-lock/agents/openai.yaml, kit/.uak/tests/test_design_lock_round.py
- **Acceptance:**
  - `/uak-design-lock` step 2–4 become: `uak design round --screen landing --n 6` (8 when the event is 24 h or more), one agent per variant in parallel, `uak design shoot`, `uak design pick --k 2`; then one bred round of 4 from the picks; the human's final pick becomes the direction, and its genome fills DESIGN.md (type, scale, color, components, motion)
  - events under 6 h: one round of 4, no breeding
  - the landing is built for real in the first hours (landing-story), not left for the last hour; the app screens copy the locked direction as today
  - the generated harness files come from `python3 scripts/gen_harness.py` (never edited by hand) and `gen_harness.py --check` passes
- **Tests:** design_lock_runs_a_landing_round, short_event_single_round, generated_harness_matches
- **Verify:** `python3 kit/.uak/tests/test_design_lock_round.py && python3 scripts/gen_harness.py --check`
- **Next step:** steps 2–4 of kit/.claude/commands/uak-design-lock.md

## UAK-061 · design-lint flags oversized type and controls (the F0 failure no gate caught)

- **Type:** feature
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/design-lint, kit/.uak/tests/test_design_lint_scale.py
- **Acceptance:**
  - design-lint warns on a CSS/TSX font size above 96 px (px, rem at 16, Tailwind `text-[...]` and `text-8xl`/`text-9xl`, and the max of a `clamp()`), on vw font sizes above 12vw, and on a button/input height above 56 px; each warning names file:line and the F0 bound
  - a deliberate exception carries `design-lint: ok <reason>` on the line, like the existing checks
  - warnings, not failures, so a hackathon is never blocked by them; `--strict` makes them fail
- **Tests:** px_rem_and_tailwind_sizes_over_bound_warn, clamp_max_counts, vw_over_bound_warns, ok_comment_silences, strict_fails
- **Verify:** `python3 kit/.uak/tests/test_design_lint_scale.py`
- **Next step:** the check list in kit/.uak/bin/design-lint (after the raw palette check)
