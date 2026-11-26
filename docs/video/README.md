# The tutorial video (UI-016, redrawn in UAK-199)

A 74-second walk through what a person does with the kit today, on the kit's designed dark theme (Lavanda, the
default palette of a new install, so the video looks like the pages the viewer will open) with Inter and JetBrains Mono.
It opens on the team: the agents' pixel avatars, large, each with its own terminal ("Meet your coding team"), then the
person ("You bring the idea") and `install.sh --wizard`. The setup page follows (the project found, install, rules and
people, publish, the idea and the typed approval of the plan, "Start this agent" with the same command to copy below
it, the last screen), then the agents at work: each in its own terminal, their tasks riding lanes into one `main`, the
plan's squares turning green. It ends on the dashboard (a square that says what it waits for, "Needs you" and a review
that merges, the agents as cards, Edit, Share). Every screen is drawn and scripted; nothing here runs the kit.

The direction was chosen by the human from three shown as stills (2026-11-25): the crew for the poster and the
opening, the grid of squares as the payoff, the lanes for the beat that explains how work joins `main`.

The rendered files ship with the kit in `kit/.uak/media/` (the setup page shows them, UI-017):

| File | What |
|---|---|
| `tutorial.mp4` | H.264, 1280x720, 10 fps, no audio, at most 75 s and 820,642 bytes (the size of v6.8) |
| `tutorial-en.vtt`, `tutorial-es.vtt` | WebVTT captions, same cues and timings, written from `captions.json` |
| `tutorial-poster.jpg` | the title frame (the crew), 1280x720, at most 38,328 bytes (the size of v6.8) |
| `tutorial-frame-1.png` … `-3.png` | three 320x180 frames of the encoded video (a wizard screen, the crew, the dashboard), for the palette test |

## Render

Needs Node 18+ and `ffmpeg` on the PATH with libx264 and libwebp (`sudo apt install -y ffmpeg`; 4.4 is enough). From
this folder:

```bash
npm ci && npx playwright-core install chromium-headless-shell && npm run render
```

About two minutes. `node render.mjs --still 42 out.png` draws one frame, to look at a scene while drawing it.

- `scenes.html` draws every frame as a pure function of time (`window.seek(t)`). Its scenes and their seconds are the
  JSON block at its top. The wizard scenes use the stylesheet of `kit/.uak/bin/lib/setup.html` and the dashboard scenes
  the one of `kit/.uak/bin/lib/dash.html`, each in its own shadow root on `data-theme="dark"`, read when the page loads:
  a change of the product's look shows in the next render. The crew, the lanes and the grid are drawn with the same
  tokens and the dashboard's identicon (the pattern from the person's name, the colour from the agent's).
- `captions.json` holds the cues in both languages on the same seconds as the scenes; `render.mjs` writes both `.vtt`
  files from it.
- No network: `render.mjs` serves the files of this repository to headless Chromium (`playwright-core`, pinned in
  `package-lock.json`) under a made-up origin and refuses every other request; a refused request fails the render. The
  fonts are the kit's own `kit/.uak/bin/lib/fonts/*.woff2`.
- The same frames every time: no clock and no randomness in `scenes.html`, a fixed viewport, locale, time zone, colour
  scheme and reduced motion, the fonts loaded before the first frame. ffmpeg encodes with a fixed thread count
  (`-crf 29 -tune animation -threads 4`, bit-exact flags), so the same frames give the same file with the same ffmpeg.
- The poster is the best JPEG quality that stays under 38,328 bytes. The three PNG frames are extracted from the encoded
  video and say in a text chunk which video (its SHA-256) and which second they come from.
- `render.mjs` exits with an error when the video or the poster is heavier than v6.8 or the video longer than 75 s.

## The README's images

`npm run readme -- DIR` writes, from the same drawing and in dark: `banner.png` (1280x640, the crew and the vision line;
its eyebrow says `vX.Y · multi-agent orchestration` with the major.minor of `kit/.uak/VERSION`, read at render time like
`scripts/make_media.py` does), `parallel-loop.webp` and `parallel-loop.gif` (8 s that loop: avatars take squares, a
reviewer passes, squares turn green; GitHub plays both inline), `parallel-loop-still.png` (a still of that loop),
`crew.png` and `lanes-into-main.png` (1280x720). Nothing is written into `docs/media/` by this command.

Check the result: `python3 kit/.uak/tests/test_setup_tutorial.py` (the poster's and the frames' colours are the dark
palette's, the captions match the scenes to the second, the files are not heavier; pure Python, no ffmpeg) and
`python3 kit/.uak/tests/test_tutorial_video.py` (duration, sizes, captions, the install leaves the media in the kit).
