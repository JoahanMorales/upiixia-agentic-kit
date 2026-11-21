# Plan: `uak video` (the project's video, made from the repo's own facts)

Status (2026-11-21): written on 2026-11-10, **not published and not built**. Scheduled as v7.2 in `docs/ROADMAP.md`.
The IDs below (UAK-022 … UAK-026) were never used on claims; they get new numbers when the plan is published.
What still holds: the pipeline (script from repo facts → ElevenLabs narration with word timings → real captures →
HyperFrames render → a measured MP4), Higgsfield only for at most two short B-roll clips after the human approves the
cost, never a generated picture of the product's UI. What changed since: the kit now has `uak design` rounds, `uak dash`
and `uak stats` numbers a script can cite (tasks, reviews, rejections), and `docs/media/demo.svg` as a ready terminal
scene. To do when it is published: add the facts from `uak metrics` (v6.7) to the `Facts:` sources.

## UAK-022 · `uak video script`: the video's script and measurements, from the repo's own facts

- **Type:** feature
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/video, kit/.uak/bin/lib/video/script.py, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/docs/VIDEO.md, kit/.uak/tests/test_video_script.py
- **Acceptance:**
  - `uak video script [--seconds N] [--lang es|en] [--for submission|planb]` writes `.uak/video/script.md`, one `## <scene-id> · <kind>` block per scene with `Seconds:`, `Say:` (narration), `Show:` (what is on screen) and `Facts:` (the source of every number said). Kinds: title, app, terminal, dash, clip, metrics, close. A human or agent edits this file; every later step reads it
  - facts come only from the repo: README title and first paragraph, `.uak/PROJECT.md` (event, rubric, "Format and video limits"), the claims branch (tasks integrated, agents, reviews, merges, as `uak stats` counts them), the deploy URL, the test count. A number in `Say:` that no `Facts:` line backs fails `--check`
  - measurements: default 120 s for submission and 75 s for planb; a limit in PROJECT.md's "Format and video limits" row (e.g. "3 min") caps `--seconds` and a larger value is refused naming the row. Word budget per scene = seconds × 150 / 60 × 0.9. Default submission split: title 8, problem 15, app 50, how (terminal + dash) 27, metrics 15, close 5
  - `uak video script --check` exits 1 naming the scene for: narration over its word budget, a scene without `Show:`, total seconds over the limit, an unbacked number
  - `uak video` with no step prints the pipeline (script, voice, capture, render) with `VIDEO_TODO <step> · <exact command>` for the first step not done, or `VIDEO_READY <path to the mp4>`; `uak video <step>` runs `lib/video/<step>.py` (the dispatcher every later step uses, so UAK-023..025 add files only)
  - `kit/.uak/docs/VIDEO.md` is the contract, exactly as below; commands.tsv gets the `video` row and CLI.md its prose row (gen_registry --check passes)
- **Contract (VIDEO.md):** everything lives in `.uak/video/` of the team repo; script.md is committed, the rest is gitignored by `uak video script` (adds `.uak/video/{voice,assets,build,out}/` to .gitignore)
  - `voice/<scene>.mp3` and `voice/timings.json`: `{"lang","voice","model","scenes":[{"id","audio","seconds","words":[{"text","start","end"}]}]}` (seconds from the scene's start)
  - `voice/captions.srt`: the whole video, cues at most 2 lines × 42 chars and 6 s
  - `assets/manifest.json`: `{"scenes":{"<id>":{"kind","files":[...],"seconds"}}}` (paths relative to `.uak/video/`)
  - `out/video.mp4`, `out/video.srt`, `out/thumb.png`, `out/report.txt`
- **Tests:** script_uses_only_repo_facts, script_fits_the_word_budget, event_limit_caps_the_seconds, check_names_the_overlong_scene, check_refuses_an_unbacked_number, video_status_names_the_next_step
- **Verify:** `python3 kit/.uak/tests/test_video_script.py`
- **Next step:** the commands.tsv row and the dispatcher in kit/.uak/bin/video

## UAK-023 · `uak video voice`: ElevenLabs narration with word timings, a free local voice without a key

- **Type:** feature
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** None (uses the contract written in UAK-022 of this plan)
- **Uses contract:** UAK-022
- **Paths:** kit/.uak/bin/lib/video/voice.py, kit/.uak/tests/test_video_voice.py
- **Acceptance:**
  - with `ELEVENLABS_API_KEY` set: one `POST /v1/text-to-speech/{voice}/with-timestamps` per scene (model `eleven_multilingual_v2` unless `--model`; voice from `--voice` or `UAK_VIDEO_VOICE`; `previous_text`/`next_text` from the neighbour scenes so the tone carries), writing `voice/<scene>.mp3`, `voice/timings.json` (words built from the character alignment) and `voice/captions.srt` as the contract says. Python stdlib only (urllib)
  - before calling, it prints the characters it will spend; `--max-chars` (default 5000) refuses a run above it. A scene whose text, voice and model did not change is reused from a cache: a second run with no edits makes no request
  - the key never appears in output, logs, files or error text; an API error prints the HTTP status and ElevenLabs' message only
  - without a key: `--local` uses `npx hyperframes tts` (Kokoro, offline; es → `ef_dora`, en → `af_heart`) and `npx hyperframes transcribe` for the word timings; `--silent` writes timings from 150 wpm (captions-only video). With no key and no flag: `VIDEO_TODO voice · export ELEVENLABS_API_KEY=… (free tier: 10k characters a month) or --local`, exit 2
  - the base URL is `UAK_ELEVENLABS_URL` (default `https://api.elevenlabs.io`) so tests use a local fake server
- **Tests:** voice_writes_audio_timings_and_srt, a_second_run_makes_no_requests, the_key_never_reaches_disk_or_output, srt_cues_fit_two_lines, silent_mode_times_by_words, a_run_over_max_chars_is_refused
- **Verify:** `python3 kit/.uak/tests/test_video_voice.py`
- **Next step:** the alignment → words function in kit/.uak/bin/lib/video/voice.py

## UAK-024 · `uak video capture`: real screens for every scene, never invented ones

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None (uses the contract written in UAK-022 of this plan)
- **Uses contract:** UAK-022
- **Paths:** kit/.uak/bin/lib/video/capture.py, kit/.uak/tests/test_video_capture.py
- **Acceptance:**
  - `terminal` scene: runs the command in its `Show:` line (default `bash .uak/bin/uak demo --fast`) and keeps its real output with colors in `assets/<scene>.ansi`, temp paths replaced by `~/demo` as scripts/render_demo.py does; a line that the command did not print never appears
  - `dash` scene: a static copy of `uak dash`'s page (data from the claims branch) in `assets/<scene>/index.html`
  - `app` scene: `Show:` names a public URL (default: the deploy URL) captured with `npx hyperframes capture URL --skip-vision`; a localhost URL is refused with "record it as a clip"
  - `clip` scene: `.uak/video/clips/<scene>.{mp4,mov,webm}` recorded by a human (OBS, Xbox Game Bar, QuickTime), checked with ffprobe; missing or shorter than the scene's seconds → `VIDEO_TODO capture · record <file>, at least N s`
  - every text asset goes through `.uak/bin/secret-scan`; an asset with a secret is refused naming the file and line, and nothing is written
  - writes `assets/manifest.json` as the contract says, every scene listed
- **Tests:** terminal_scene_keeps_real_output, temp_paths_are_hidden, a_secret_in_a_capture_is_refused, a_missing_clip_names_the_file_and_seconds, localhost_app_is_sent_to_a_clip, manifest_lists_every_scene
- **Verify:** `python3 kit/.uak/tests/test_video_capture.py`
- **Next step:** the scene loop over script.md in kit/.uak/bin/lib/video/capture.py

## UAK-025 · `uak video render`: a HyperFrames composition with burned captions, a measured MP4

- **Type:** feature
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** None (uses the contract written in UAK-022 of this plan)
- **Uses contract:** UAK-022, UAK-023, UAK-024
- **Paths:** kit/.uak/bin/lib/video/render.py, kit/.uak/templates/video/index.html, kit/.uak/templates/video/scenes.css, kit/.uak/tests/test_video_render.py
- **Acceptance:**
  - builds `.uak/video/build/`, a HyperFrames project: one sub-composition per scene; a scene lasts its narration + 0.4 s (its `Seconds:` when silent); audio placed with `data-start`; captions burned in the lower third with the spoken word highlighted, from timings.json; terminal scenes typed from the real `.ansi` text; dash and app screens with a slow pan; clips muted under the narration; title and close cards in the project's design tokens (DESIGN.md colors and fonts when locked, the kit's neutral theme otherwise)
  - `--dry-run` writes the project and starts no Node (the tests use it); otherwise `npx hyperframes lint` must report 0 errors, then `npx hyperframes render --quality delivery` at 1920×1080, 30 fps, H.264 yuv420p + AAC 48 kHz, then ffmpeg loudnorm to −14 LUFS (true peak −1.5 dB). Also `out/video.srt` and `out/thumb.png` (the title card)
  - measures the file with ffprobe into `out/report.txt`: duration, resolution, fps, codecs, loudness, size, caption cues, words per minute. `VIDEO_PASS` only when the duration is 85–105 % of the target and within the event limit, an audio stream exists (unless silent), and the size is under 100 MB; otherwise `VIDEO_FAIL <measure> · <value> (want <range>)`
  - before building: Node ≥ 22, ffmpeg and ffprobe, or `VIDEO_TODO render · <install line for Linux, macOS and Windows>` and exit 2
- **Tests:** dry_run_builds_one_composition_per_scene, captions_follow_word_timings, scene_lengths_follow_the_audio, the_report_fails_an_overlong_video (fake ffprobe), missing_node_22_names_the_fix
- **Verify:** `python3 kit/.uak/tests/test_video_render.py`
- **Next step:** the scene → sub-composition writer in kit/.uak/bin/lib/video/render.py

## UAK-026 · `/uak-video`: an agent makes the plan-B and submission video end to end

- **Type:** feature
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** UAK-022, UAK-023, UAK-024, UAK-025
- **Paths:** kit/.claude/commands/uak-video.md, kit/.claude/commands/uak-demo.md, kit/.uak/bin/doctor, kit/.uak/modes/sprint.md, docs/HACKATHON.md, README.md, llms.txt, CHANGELOG.md, kit/.uak/tests/test_video_doctor.py
- **Acceptance:**
  - `/uak-video` runs: `uak video script` → the agent rewrites `Say:` in the team's words inside the budget, using only `Facts:` → the human approves script.md (it is the pitch) → `voice` → `capture` (lists the clips a human must record) → `render` → it watches the result: 6 frames extracted with ffmpeg and looked at, report.txt read, before saying done
  - the ElevenLabs hosted MCP (`https://api.elevenlabs.io/v1/mcp`) is optional and only to browse and preview voices; the narration always goes through `uak video voice` (timings, cache, key hygiene)
  - Higgsfield is optional B-roll for the title and close only: at most 2 clips of at most 5 s, through the `higgsfield` CLI, each one after the human approves its credit cost; never a generated picture of the product's UI
  - `/uak-demo` step 5 says to run `/uak-video` for the plan-B video at T−50 % and the submission video at T−2 h, instead of "you can't"
  - `doctor` prints one info line `VIDEO node <v> · ffmpeg <yes/no> · elevenlabs key <set/unset> · hyperframes <yes/no>` that never fails doctor and never prints the key
  - docs/HACKATHON.md gets "The video" with the measurements table (120 s, 1080p30, −14 LUFS, captions burned and .srt, < 100 MB, cost per take); README commands, llms.txt and CHANGELOG list `uak video`
- **Tests:** doctor_reports_video_tools_without_the_key, uak_demo_points_to_uak_video
- **Verify:** `python3 kit/.uak/tests/test_video_doctor.py`
- **Next step:** kit/.claude/commands/uak-video.md
