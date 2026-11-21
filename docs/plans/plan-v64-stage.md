## UAK-068 · Landings fill the desktop and open with a stand-by spectacle: the `stage` gene

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2.5 h
- **Depends on:** UAK-063
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/skills/landing-story/SKILL.md, kit/.uak/tests/test_design_stage.py
- **Acceptance:**
  - a 9th gene `stage` with values: three.js scene, three.js point cloud from the team's own image, three.js scroll-driven, canvas 2D generative, SVG/CSS animation, real video with a live overlay, still (no animation); drawn like the others (≤ 3 shared genes, taste, wildcards); `still` is drawn at most once per round
  - every TASK.md (and landing-story) states: design for 1440 and 1920 first, then 390; the hero is full-bleed; content containers ≥ 1200 px at 1440 (a text column may be narrower, the composition fills the screen); no section with wide empty gutters
  - the hero is a stand-by loop for a projector: it runs with no interaction in a 10–15 s cycle and tells the project to a stranger (subject → what the product finds → the result → the wow); reduced motion gives a complete still
  - images: never show a raster upscaled; recreate the subject (3D, points, line art, vector) or show it at ≤ native size; real result charts may be rebuilt as live SVG/HTML from their real numbers
  - three.js rules in TASK.md: pinned CDN import map (three@0.170.0), DPR ≤ 2, pause when hidden, a designed still when WebGL is missing, no branded 3D models, no fetches but the CDN and fonts
  - glows, neon blurs and soft gradient haze are listed as tells (the human: "AI slop")
  - Why (AXIA R1–R2, 2026-11-11): every variant sat in a 600–900 px column with empty sides on a desktop; the human wants landings that make a hackathon room turn their heads while the team sets up, with three.js when it fits; resized car renders and result captures "looked stretched and ugly"
- **Tests:** stage_gene_drawn_with_still_at_most_once, task_states_desktop_first_bounds, task_states_standby_loop, task_forbids_upscaled_rasters, three_rules_pinned_cdn, landing_story_has_the_same_rules
- **Verify:** `python3 kit/.uak/tests/test_design_stage.py && python3 kit/.uak/tests/test_design_round.py`
- **Next step:** GENES and task_text in kit/.uak/bin/lib/design_round.py; section 2 of landing-story

## UAK-069 · `uak design shoot` judges what the human judges: 1920 projector shot, served over http, WebGL, and a QA line

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-067, UAK-068
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_shoot_qa.py
- **Acceptance:**
  - the Playwright capture serves the round folder over a local http server (canvas pixel reads and fetches fail on file://), launches Chromium with software WebGL (`--use-angle=swiftshader --enable-unsafe-swiftshader`), and shoots 1920×1080 (`1920.png`, the projector) besides 1280 and 390, ~3 s after load so animations are mid-cycle
  - a QA line per viewport: WebGL available, page errors (count + first), horizontal overflow, the width of the content's bounding box as a share of the viewport (warn under 75 % at 1920 and 1440: "narrow page, empty gutters"), and every <img> drawn larger than its natural size × DPR ("upscaled raster: file, natural → drawn")
  - `uak design pick` shows the 1920 shot first, the QA warnings under each variant, and links to the live page
  - the shoot exits non-zero when any variant has page errors, and lists them
  - Why (AXIA R1–R3): the lead had to hand-patch the capture script for 1920, http and WebGL, and the human found the narrow pages and stretched images by eye; the kit should catch both before the human looks
- **Tests:** serves_over_http_so_canvas_reads_work, writes_1920_shot, flags_narrow_page, flags_upscaled_raster, page_errors_fail_the_shoot, pick_page_shows_qa_and_1920
- **Verify:** `python3 kit/.uak/tests/test_design_shoot_qa.py`
- **Next step:** `capture_one` in kit/.uak/bin/lib/design_round.py (the reference implementation is ~/Proyectos/design-rounds/bin/shoot.js, a Node script; port its behavior to the Python/Playwright path and keep the UAK_DESIGN_SHOOT override)
