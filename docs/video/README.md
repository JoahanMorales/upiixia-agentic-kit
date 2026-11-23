# The demonstration video (UI-016)

A 74-second, simulated walk through the kit: an empty folder, `install.sh --wizard`, the local setup page (install,
prepare, plan with a typed approval), the team (Claude Code as `claude-ana`, a second identity `ana-r` reviewing),
claims with tests first, review, merge, the board, and a deployed cafeteria queue board. Every screen is scripted;
nothing here runs the kit.

The rendered files ship with the kit in `kit/.uak/media/` (the setup page shows them, UI-017):

| File | What |
|---|---|
| `tutorial.mp4` | H.264, 1280x720, 10 fps, no audio, at most 3 MB |
| `tutorial-en.vtt`, `tutorial-es.vtt` | WebVTT captions, same cues and timings |
| `tutorial-poster.jpg` | the first frame, at most 150 KB |

## Render

Needs Node 18+ and `ffmpeg` on the PATH. From this folder:

```bash
npm ci && npx playwright-core install chromium-headless-shell && npm run render
```

- `scenes.html` draws every frame as a pure function of time (`window.seek(t)`); open it with `?t=42` to see one frame.
- `captions.json` holds the cues in both languages; `render.mjs` writes both `.vtt` files from it, so the timings
  always match.
- `render.mjs` screenshots each frame with headless Chromium (`playwright-core`, pinned in `package-lock.json`),
  encodes the MP4 with ffmpeg (`-crf 23 -tune animation`) and the poster JPEG.

Check the result: `python3 kit/.uak/tests/test_tutorial_video.py` (duration, sizes, captions, the install copies it).
