## UAK-158 · One design system: the wizard is drawn with the dashboard's tokens, and `design-lint` reads HTML

- **Type:** feature
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-156
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/fonts/, kit/.uak/bin/design-lint, kit/.uak/media/, docs/DASHBOARD.md, docs/design/, scripts/kit_lint.py, kit/.uak/tests/test_setup_design.py
- **Acceptance:**
  - the design system is `docs/design/DIRECTION.md` (chosen by the human on 2026-11-23) and its mock `docs/design/direction/mock.html`: scale, type, radii, the pills, the line of nodes, the window, the single bordered list and the three-figure footer are built once and used by both pages
  - nine palettes, each in light and dark, as in the mock: Clásico (the exact colours of the dashboard of v6.8), Lavanda, Cielo, Menta, Salvia, Durazno, Rosa, Arena, Grafito. One control, "Apariencia", in both pages sets theme and palette; the choice is the viewer's, kept in the browser, and changes no tracked file. The default is Lavanda in a checkout that never had a dashboard, and Clásico where a dashboard of v6.8 or earlier was already generated (its output directory exists), so nobody's panel changes colour by itself. In Menta and Salvia the green of "integrated" stays distinguishable from the accent (a test measures the difference)
  - type is Inter for text and JetBrains Mono for IDs, commands, pills and counters, as in the mock: shipped in the kit as subset `woff2` files with their licence (SIL OFL), written beside the dashboard's page and served by the wizard, with the system stack as fallback. Neither page makes a network request, with or without the files; the dashboard's HTML file is not heavier than today
  - `setup.html` and `dash.html` declare the same custom properties with the same values in light and dark (page, surface, raised, ink, ink-2, muted, line, accent, accent-ink, critical, shadow, mono, radii): the set is the direction the human chose from the three shown to them, recorded in `docs/design/DIRECTION.md` on main before this task starts (palette, type, radii, spacing, in light and dark); the wizard's own palette, its 20 px radius and its three hard-coded shadows go. A test compares the two `:root` blocks and fails on any difference
  - outside `:root` no colour literal remains in either file; the wizard uses at most 6 font sizes and one spacing scale (4, 8, 12, 16, 24, 32, 48), the radii and the body size of the chosen direction, one shadow token
  - `design-lint` applies its rules to `.html` (inline `<style>` and `style=`), not only the two scale checks: colour literals outside `:root`, coloured side stripes, glass, glow, emoji and glyphs used as icons (`✓ ✗ ! •` included), more than 6 font sizes, more than one primary button visible in a view. Both pages pass with `--strict`, with no finding suppressed
  - status marks are inline SVG icons with a text label, never a glyph; a disabled control keeps 4.5:1 for its label (2.9:1 today); every text/background pair of the tokens is at least 4.5:1 in both themes, computed by the test
  - the tutorial's poster and its frames use the kit's palette (no purple glow)
  - screenshots at 1280 and 390, light and dark, of every screen are in `.uak-shots/UAK-158/` with the design critic's `VERDICT: SHIP` for the task's commit
  - Why (2026-11-22): the two pages share no colour value; the wizard frames the blue dashboard inside a green page; `design-lint` printed PASS for both because it does not read HTML (a copy renamed `.js` gave 40 findings)
- **Tests:** wizard_and_dashboard_share_tokens, no_colour_literal_outside_root, six_font_sizes_one_spacing_scale, design_lint_reads_html, every_pair_has_contrast, disabled_label_is_readable
- **Verify:** `python3 kit/.uak/tests/test_setup_design.py && bash kit/.uak/bin/design-lint --strict kit/.uak/bin/lib/setup.html kit/.uak/bin/lib/dash.html`
- **Next step:** `:root` in setup.html (lines 13-28 and 657-702 of the contributed file) against dash.html lines 12-47; existing tests that assert the old colours or classes need `uak allow UAK-158 --tests` from the human

## UAK-159 · The wizard's flow: ten screens, one job each, and it covers what the kit does today

- **Type:** feature
- **Priority:** P0
- **Estimate:** 12 h
- **Depends on:** UAK-158
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, docs/DASHBOARD.md, kit/.uak/tests/test_setup_forms.py, kit/.uak/tests/test_setup_guide.py, kit/.uak/tests/test_setup_resume.py, kit/.uak/tests/test_setup_first_run.py
- **Acceptance:**
  - every screen follows rule 11 of `docs/design/DIRECTION.md` and the wizard of its mock: the line of nodes as progress at the top with "continue in the terminal" beside it; the choices at the left; at the right a window that shows what will be written or changed by this screen and updates as the person chooses (files and counts on Install, the lines of PROJECT.md on the rules, the people on People); "Exit" and one primary button at the bottom
  - the flow approved by the human (2026-11-23), one screen per job, each with one primary button: (1) Your project: what was detected (folder, new or existing repository, a hook manager such as husky or lefthook, CI, the project's own tests, the stack) and the mode proposed with its reason; the tools are chosen here. (2) Install: what will be written, how many files, and how the kit's hooks live beside the team's. (3) Unblock: only when something fails, one problem at a time with its fix. (4) How your team will work: the project's rules in plain words with the mode's defaults (`Test-First`, review with or without GitHub, `Review-Independence`, `Merge-Engine`, generated files, the token budget), details under "Advanced"; it writes nothing the human did not confirm. (5) People: the human's identity, reviewers, roles. (6) Schedule: only in Hackathon mode. (7) Publish the kit. (8) Idea and plan: the idea, the design direction when the project has screens (the creativity index and the design lock), the plan, the approval. (9) Start: the command for each agent; the screen says when the first agent has claimed a task. (10) Dashboard: from here, deployment (`uak deploy`, the smoke that boots the app, `Live-URL`), external skills (`uak skill add`) and "Close the wizard", which ends the server
  - a project that already has the kit opens on the screen it needs; an older kit opens "Update", a path of its own, never an alarm heading over another screen
  - there is no welcome screen, no slogan, no eyebrow and no benefit pairs; the first screen says what will happen in this project in two sentences. The video is a link. The folder is not asked inside a repository (it is shown with "Change"). A first install takes at most 4 clicks
  - diagnostics (`Blackbox`) are never pre-checked: the screen says what is published and where, and that a public repository makes it public; the human chooses
  - no screen is taller than two viewports at 1280×800 or three at 390×844 with real content ("Get ready" was 4518 px and 6457 px)
  - an instruction appears once: one command, one copy box, the folder already in it; raw output of `uak start` is under "Technical details", never a heading. A heading is a sentence that starts with a capital and says what to do
  - an error is next to the control that caused it and above the button, in view after the click at both widths, names what to do, and is the message of that step
  - the step is in the URL: reload stays on it, the browser's Back and Forward move between steps, reopening a project resumes where it was
  - at 390 px the content starts within 160 px of the top, every target is at least 44×44 px, nothing scrolls sideways; the journey bar and the step rail are one component
  - a running action shows what it is doing and for how long, next to its button; a page whose server ended says so when it comes back into view, with the command that reopens it
  - screenshots at 1280 and 390, light and dark, Spanish and English, of every screen and of one error and one loading state are in `.uak-shots/UAK-159/` with the design critic's `VERDICT: SHIP` for the task's commit
- **Tests:** flow_has_the_ten_screens, existing_repository_is_detected, rules_screen_writes_only_what_was_confirmed, schedule_only_in_hackathon, diagnostics_are_not_prechecked, old_kit_opens_update, close_ends_the_server, no_screen_taller_than_two_viewports, instruction_appears_once, first_install_in_four_clicks, error_is_next_to_its_control, step_survives_reload_and_back, mobile_content_starts_within_160px, targets_are_44px
- **Verify:** `python3 kit/.uak/tests/test_setup_forms.py && python3 kit/.uak/tests/test_setup_guide.py && python3 kit/.uak/tests/test_setup_resume.py && python3 kit/.uak/tests/test_setup_first_run.py`
- **Next step:** the "Get ready" markup in setup.html (about lines 1700-2040 of the contributed file) and the hero at 1434-1460; the detection of hooks is `doctor`'s (UAK-135, UAK-146), reuse it; changed assertions need `uak allow UAK-159 --tests` from the human

## UAK-162 · The dashboard is redrawn in the chosen direction

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-158
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, docs/DASHBOARD.md, docs/media/, README.md, kit/.uak/tests/test_dashboard_truth.py, kit/.uak/tests/test_dashboard_profiles.py
- **Acceptance:**
  - built to `docs/design/DIRECTION.md` (rules 6 to 10) and its mock: the summary in the mock's order (what needs the person; tasks as a list or as columns; activity in its window; at the side progress, agents, integrations per period, tokens) with its maximums (8 task rows of what is moving, 4 agents, progress as blocks up to 24 tasks and one bar beyond), so a plan of 60 tasks adds less than 50 px to the page; integrations per period adapt to the time elapsed (6 to 8 bars) and can be fixed at 1 h, 2 h, 4 h or a day
  - the board has four stages (to do, in progress, in review, integrated); blocked and overdue are conditions on the card; each header says the one thing that matters; the page scrolls, columns show 8 and a "more"; a search filters by task or agent
  - a click on a task opens its detail with the structure of v6.8, restyled: header, time in each state, who took part with model and harness, every move in order with time, elapsed, who and note, then the acceptance criteria with their tests. It closes with the button, Escape or a click outside, and works with the keyboard
  - the tab's title says how many things need the person (`(2) project`), and nothing when none
  - the tabs the mock does not show (Agents, Messages, Black box, Memory, Tokens), the empty project and the finished project are designed in the same language and shown to the human as screenshots before the task is sent to review; the note of `uak done` says the human saw them
  - the dashboard is redesigned with the tokens of `docs/design/DIRECTION.md`: the same information as today (progress, agents online, reviews waiting with their sub-state, stalled, needs a human, board, agents, conversation, black box, memory, tokens), nothing dropped; the first thing read is what needs a person now, then progress, then the board
  - an empty project is not a grid of zeros: it says the one next step and its command; each number that is zero because nothing happened yet says so in words
  - it stays one file opened from `file://`, with no server, no port, no external request and no build step; the page is not heavier than today (84 KB) and its two timers start no process
  - both profiles (beginner, advanced), both themes and both languages are complete; every text/background pair is at least 4.5:1; every target is at least 44×44 px at 390; nothing scrolls sideways; it is usable with the keyboard alone, and motion stops under `prefers-reduced-motion`
  - `design-lint --strict` passes on it with no finding suppressed (main's file has 26 today: 19 colour literals, 5 rgba, 1 glass, 1 emoji)
  - screenshots at 1280 and 390, light and dark, of an empty project, a project in progress (20 tasks, 3 agents, a review over its lease, a blocked task) and a finished one are in `.uak-shots/UAK-162/` with the design critic's `VERDICT: SHIP` for the task's commit; the README's and the docs' images of the dashboard are replaced
- **Tests:** dashboard_keeps_every_field, empty_project_says_the_next_step, no_server_no_request, page_is_not_heavier, both_profiles_and_languages_are_complete
- **Verify:** `python3 kit/.uak/tests/test_dashboard_truth.py && python3 kit/.uak/tests/test_dashboard_profiles.py && bash kit/.uak/bin/design-lint --strict kit/.uak/bin/lib/dash.html`
- **Next step:** kit/.uak/bin/lib/dash.html (tokens at the top, the hero and the four tiles, the tabs); the data comes from `dash.py`, whose fields the existing tests list; changed assertions need `uak allow UAK-162 --tests` from the human
