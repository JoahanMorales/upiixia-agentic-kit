## UAK-199 · The tutorial's poster and video are drawn in the kit's direction

- **Type:** fix
- **Priority:** P1
- **Estimate:** 4 h
- **Depends on:** UAK-158
- **Paths:** docs/video/, kit/.uak/media/, kit/.uak/tests/test_setup_tutorial.py, kit/.uak/tests/timings/test_setup_tutorial.txt
- **Acceptance:**
  - the tutorial's poster (`kit/.uak/media/tutorial-poster.jpg`) and every scene of the video (`tutorial.mp4`) use the kit's direction (`docs/design/DIRECTION.md`): the Lavanda palette in light, Inter for text and JetBrains Mono for commands, the radii and the window of the mock, no glow, no gradient, no purple card on a dark ground. Why: UAK-158 asked for it ("the tutorial's poster and its frames use the kit's palette") and it was not done because rendering needs Node and ffmpeg, which the author did not have; the review of UAK-158 found the poster still showing "the old dark-purple glow card", and the human decided on 2026-11-25 to do it in the team instead of leaving it to a contributor
  - the scenes show the wizard and the dashboard as they are now (the ten screens of UAK-159 with the line of nodes, the buttons of UAK-192, the dashboard of UAK-162 and UAK-165), not the screens of v6.8; what the video says still matches what the product does, step by step, and the captions in Spanish and English (`tutorial-es.vtt`, `tutorial-en.vtt`) match the new scenes to the second
  - the video is rendered by `npm run render` in `docs/video` from `scenes.html`, with the fonts the kit ships (no network request while rendering), and `docs/video/README.md` says how to render it and what it needs; the same command on another machine gives the same frames
  - the files are not heavier than today (video 820,642 bytes, poster 38,328 bytes) and the video is not longer than 75 seconds
  - a test reads the poster's pixels and three frames of the video and fails when the dominant colours are not the palette's (so the old card cannot come back), without needing ffmpeg at test time: the three frames are extracted when the video is rendered and committed beside it as small images the test compares with the poster's palette
- **Tests:** poster_uses_the_kit_palette, frames_use_the_kit_palette, captions_match_the_scenes, media_is_not_heavier
- **Verify:** `python3 kit/.uak/tests/test_setup_tutorial.py`
- **Next step:** `docs/video/scenes.html` and `render.mjs`; `cd docs/video && npm ci && npx playwright-core install chromium-headless-shell && npm run render`; ffmpeg must be on PATH (`sudo apt install -y ffmpeg` on the machine that renders). Screenshots of the poster and of each scene go to the human before review
