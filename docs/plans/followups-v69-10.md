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

## UAK-202 · The README is rewritten: what the kit is, in plain words, readable by a person and by an agent

- **Type:** docs
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-195
- **Paths:** README.md, llms.txt, docs/GUIDE.md, docs/REFERENCE.md, docs/EVIDENCE.md, kit/.uak/tests/test_readme.py, kit/.uak/tests/timings/test_readme.txt
- **Acceptance:**
  - the README is rewritten from an empty page, not edited: at most 150 lines, and its first screen answers four questions in this order with no slogan before them: what this is (one sentence a person outside the project understands), who it is for, what you get after ten minutes, and the one command to start. Why: the human, 2026-11-25: "every time it fills with more slop and buzzwords and it is not understandable for an agent"; the README is 656 lines and 57,919 bytes, with 26 top-level sections, and each release appended a section instead of rewriting
  - no sentence sells: no superlative, no "without chaos", "battle-tested", "blazing", "seamless", "powerful", "supercharge", "next-level" or the like; a list of such words lives in the test and a new one fails it. Every number in the README names what was measured and links to where (`docs/EVIDENCE.md`, a run, a task); a number that cannot be traced is removed, not softened
  - an agent can act from it: the commands are in code blocks that can be pasted as they are; every `uak` command the README names exists in `kit/.uak/bin/lib/commands.tsv` with the options shown (a case checks each one); a short section "For an agent reading this" says which file to read for what (`AGENTS.md` for the rules, `kit/.uak/docs/CLI.md` for commands, `kit/.uak/docs/WHY.md` for the reasons), and `llms.txt` says the same things in the same order, shorter, with no claim the README does not make
  - what leaves the README is not lost: the walkthroughs go to `docs/GUIDE.md`, the lists of commands, modes, stacks and options to `docs/REFERENCE.md`, the measurements and the team runs to `docs/EVIDENCE.md`; each is linked once from the README, and a case fails when a section of today's README has no home in one of the four files (by its heading or an explicit "dropped: reason" line in the pull request)
  - the screenshots in the README are the product of today (the wizard of UAK-159 and UAK-192, the dashboard of UAK-162, UAK-165 and UAK-198) and each has alt text that says what it shows
  - the existing cases that read the README (`test_tutorial_video`, `test_external_skills`, `test_tokens_elsewhere`, `test_setup_prepare`, `test_merge_engine_policy`, `test_ci_tiers`, `test_ci_shards`, `test_hook_session_start_speed`) keep passing unchanged: what they assert stays in the README or the task stops and lists the lines for the human's `uak allow`
  - the draft is shown to the human before review, as a rendered page and as plain text, in Spanish summary of each section's purpose; the README itself stays in English
- **Tests:** readme_is_at_most_150_lines, first_screen_answers_the_four_questions, no_selling_words, every_number_has_a_source, every_command_exists, llms_txt_agrees_with_the_readme, every_old_section_has_a_home
- **Verify:** `python3 kit/.uak/tests/test_readme.py && python3 scripts/kit_lint.py`
- **Next step:** read today's README once to list what it claims, then close it; write for a reader who has ten minutes and no context; the measurements are in `uak metrics`, kit/.uak/docs/WHY.md and docs/plans; the release (UAK v6.9) uses this README, so this task lands before it
