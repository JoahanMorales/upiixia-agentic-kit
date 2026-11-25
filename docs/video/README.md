# The tutorial video (UI-016, redrawn in UAK-199)

A 74-second walk through what a person does with the kit today, drawn with the kit's own design system
(`docs/design/DIRECTION.md`: Lavanda in light, Inter and JetBrains Mono, the window, the line of nodes, the mono pills):
`install.sh --wizard` in a terminal, the setup page (the project found, install, rules and people, publish, the idea and
the typed approval of the plan, "Start this agent" with the same command to copy below it, the claim, the last screen),
then the dashboard (every task as a square, what a square waits for, "Needs you" and a review that merges, the agents
as cards, Edit to arrange the summary, Share). Every screen is drawn and scripted; nothing here runs the kit.

The rendered files ship with the kit in `kit/.uak/media/` (the setup page shows them, UI-017):

| File | What |
|---|---|
| `tutorial.mp4` | H.264, 1280x720, 10 fps, no audio, at most 75 s and 820,642 bytes (the size of v6.8) |
| `tutorial-en.vtt`, `tutorial-es.vtt` | WebVTT captions, same cues and timings, written from `captions.json` |
| `tutorial-poster.jpg` | the title frame, 1280x720, at most 38,328 bytes (the size of v6.8) |
| `tutorial-frame-1.png` … `-3.png` | three 320x180 frames of the encoded video (a wizard screen, the start screen, the dashboard), for the palette test |

## Render

Needs Node 18+ and `ffmpeg` on the PATH (`sudo apt install -y ffmpeg`; 4.4 is enough). From this folder:

```bash
npm ci && npx playwright-core install chromium-headless-shell && npm run render
```

About two minutes. `node render.mjs --still 42 out.png` draws one frame, to look at a scene while drawing it.

- `scenes.html` draws every frame as a pure function of time (`window.seek(t)`). Its scenes and their seconds are the
  JSON block at its top. The wizard scenes use the stylesheet of `kit/.uak/bin/lib/setup.html` and the dashboard scenes
  the one of `kit/.uak/bin/lib/dash.html`, each in its own shadow root, read when the page loads: a change of the
  product's look shows in the next render.
- `captions.json` holds the cues in both languages on the same seconds as the scenes; `render.mjs` writes both `.vtt`
  files from it.
- No network: `render.mjs` serves the files of this repository to headless Chromium (`playwright-core`, pinned in
  `package-lock.json`) under a made-up origin and refuses every other request; a refused request fails the render. The
  fonts are the kit's own `kit/.uak/bin/lib/fonts/*.woff2`.
- The same frames every time: no clock and no randomness in `scenes.html`, a fixed viewport, locale, time zone, colour
  scheme and reduced motion, the fonts loaded before the first frame. ffmpeg encodes with a fixed thread count
  (`-crf 27 -tune animation -threads 4`, bit-exact flags), so the same frames give the same file with the same ffmpeg.
- The poster is the best JPEG quality that stays under 38,328 bytes. The three PNG frames are extracted from the encoded
  video and say in a text chunk which video (its SHA-256) and which second they come from.
- `render.mjs` exits with an error when the video or the poster is heavier than v6.8 or the video longer than 75 s.

Check the result: `python3 kit/.uak/tests/test_setup_tutorial.py` (the poster's and the frames' colours are the
palette's, the captions match the scenes to the second, the files are not heavier; pure Python, no ffmpeg) and
`python3 kit/.uak/tests/test_tutorial_video.py` (duration, sizes, captions, the install leaves the media in the kit).
