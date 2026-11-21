## UAK-086 · `design shoot` no longer loses a variant to a 30 s screenshot timeout after the QA pass

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** UAK-084
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_shoot_timeout.py
- **Acceptance:**
  - the capture takes each viewport's screenshots BEFORE the long QA work (frame timing, background-image loads, mass), or gives `page.screenshot` a timeout that scales with the page height (at least 90 s for a full-page capture at device scale 2)
  - a screenshot that still times out leaves the variant's other viewports and its qa.json written, and the line names the viewport ("390-full timed out after 90 s: the page keeps repainting; pause loops off screen"), never "captured none" for a variant whose 1920 and 1280 were fine
  - shooting several variants at once (agents shooting in parallel on one machine) is serialized by a lock file in the round folder, so one shoot never starves another
  - Why (colonIA R3, 2026-11-15): R3/v4 never got a 390.png in 5 runs: `Page.screenshot: Timeout 30000ms exceeded`. Alone and without the QA pass, the same page shot its 390 full page (780x12620) in 3.4 s; after MEDIA_JS + QA_JS the viewport shot took 17 s and the full page 35 s. The lead captured 390 by hand. R3/v3's agent also lost 3 passes with six variants shooting at once (load average ~17)
- **Tests:** screenshots_before_qa, timeout_scales_with_height, timeout_names_viewport_keeps_others, parallel_shoots_serialized
- **Verify:** `python3 kit/.uak/tests/test_design_shoot_timeout.py`
- **Next step:** the `for name, w, h in (("1920", …` loop in the `_PLAYWRIGHT` script of kit/.uak/bin/lib/design_round.py (~line 1197)
