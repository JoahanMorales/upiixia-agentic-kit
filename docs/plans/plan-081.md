## UAK-081 · The capture catches distorted images (aspect ratio), the "stretched" look the human saw

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** UAK-073
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/tests/test_design_aspect.py
- **Acceptance:**
  - the capture's QA flags "distorted image: file, natural W×H → drawn W×H" when an <img>, <video>, CSS background (size set in both axes) or <canvas> is drawn with an aspect ratio more than 8 % off its natural one and object-fit (or background-size) does not preserve it (fill / explicit stretched sizes)
  - TASK.md and landing-story say: raster images keep their aspect ratio — `object-fit: cover` (crop) or `contain` (fit), never `fill` or a width and height that disagree with the file
  - Why (AXIA R1, found by the UAK-073 review, 2026-11-13): the human called the images "stretched and ugly"; they were not upscaled but squashed: R1/v2 drew loop.png (900×620) at 532×620 (ratio 0.86 vs 1.45) and resultados-60.png (900×520) at 612×520 with object-fit: fill; no check caught it
- **Tests:** squashed_img_flagged, cover_and_contain_not_flagged, stretched_background_flagged, rule_in_task_and_skill
- **Verify:** `python3 kit/.uak/tests/test_design_aspect.py`
- **Next step:** QA_JS in kit/.uak/bin/lib/design_round.py (next to the upscaled-raster check)
