## UAK-158 · One design system: the wizard is drawn with the dashboard's tokens, and `design-lint` reads HTML

- **Type:** feature
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-156
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/fonts/, kit/.uak/bin/design-lint, kit/.uak/media/, docs/DASHBOARD.md, docs/design/, kit/.uak/tests/test_setup_design.py, kit/.uak/tests/timings/test_setup_design.txt
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

## UAK-161 · The install asks how you want to continue: in the browser or in the terminal, and both reach the same place

- **Type:** feature
- **Priority:** P0
- **Estimate:** 5 h
- **Depends on:** UAK-154
- **Paths:** install.sh, kit/.uak/bin/start, kit/.uak/docs/CLI.md, README.md, docs/HACKATHON.md, kit/.uak/tests/test_install_choice.py, kit/.uak/tests/timings/test_install_choice.txt
- **Acceptance:**
  - `bash install.sh` run by a person at a terminal ends with one question: continue in the browser (the wizard) or here in the terminal; Enter takes the terminal, the answer is one key, and the question says in one line what each is. `--wizard` and `--terminal` answer it beforehand
  - with no terminal (a pipe, CI, an agent, `UAK_AGENT` set) nothing is asked and nothing opens: the install ends as today, so every existing script and test keeps working
  - the choice is remembered for the project (git config, not a tracked file) and can be changed: `uak start --wizard` opens the wizard later, and the wizard's last screen and its "Close" say the terminal command that continues from the same point
  - the terminal path covers the same steps as the wizard, in the same order and with the same names: `uak start` prints the one next step with its command (project detected, rules, people, schedule in Hackathon mode, publish the kit, idea and plan, start the agents), and a step done in one is done in the other: the state is the project's, never the page's
  - a machine without Python 3.8 or without a browser is told so and continues in the terminal; the wizard is never a requirement
- **Tests:** install_asks_once_at_a_terminal, no_terminal_no_question, flags_answer_the_question, choice_is_remembered, terminal_and_wizard_share_the_state, start_names_the_same_steps, no_python_continues_in_terminal
- **Verify:** `python3 kit/.uak/tests/test_install_choice.py`
- **Next step:** the end of install.sh (`--wizard` execs setup.py today) and the needs of kit/.uak/bin/start; a new test file needs its own timing file under kit/.uak/tests/timings (UAK-187)

## UAK-163 · Someone who joins a project that is already set up: three screens, nothing to configure about the project

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159, UAK-162
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/start, kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/docs/CLI.md, docs/DASHBOARD.md, kit/.uak/tests/test_setup_join.py, kit/.uak/bin/lib/workspace.js, kit/.uak/tests/test_setup_language.py, kit/.uak/tests/timings/test_setup_join.txt
- **Acceptance:**
  - a person who clones a repository whose base branch already has the kit, and runs `uak start` (or `uak start --wizard`), is not sent through the ten screens of the setup: the project is set up, their machine is not. They get the join path, three screens, in the browser or in the terminal with the same names and order: (1) The team: the project's mode and rules in plain words, who its humans and reviewers are, the plan's state; read from the base branch, read-only. (2) Your machine: their identity (the git identity), the kit's hooks for this checkout and how they live beside a hook manager, the coding tools found on this machine and their files; each problem with its one fix; nothing is committed and no tracked file changes. (3) Start: the command that launches their agent with a name that is free, the three tasks an agent of theirs can claim now, or the reviews waiting when they come as a reviewer; then the dashboard
  - the join path never asks for the mode, the stack, the schedule, the plan or any project setting, never writes PROJECT.md and never offers an act of the project's human (register a reviewer, approve a plan, publish the kit): where one is missing it names who can do it
  - which path a person gets is decided from the repository, not from a choice: no kit on the base branch → setup; kit on the base branch and this checkout not prepared → join; both done → the dashboard. A test covers the three
  - the dashboard knows who is looking: "Needs you" lists what waits for this person (reviews offered to their agents, their stalled tasks, decisions when they are a human of the project) and shows what waits for someone else as "waits for NAME", not as theirs; with no identity it shows the project's list and says so. The page stays one file with no server
  - a second and a third person can join at the same time without one writing over the other: the join path writes only inside the person's checkout and git directory
  - screenshots at 1280 and 390, light and dark, Spanish and English, of the three screens are in `.uak-shots/UAK-163/` with the design critic's `VERDICT: SHIP` for the task's commit
  - Why (2026-11-23): the wizard was designed for the one person who sets a project up; most people who use a project arrive after that, and today they would be shown a setup that is already done
- **Tests:** joiner_gets_three_screens, path_is_decided_from_the_repository, join_never_writes_project_settings, join_offers_no_human_act, needs_you_is_per_person, two_people_join_at_once, terminal_join_names_the_same_steps
- **Verify:** `python3 kit/.uak/tests/test_setup_join.py`
- **Next step:** the route that picks the first screen in kit/.uak/bin/lib/setup.py (`open_target`) and the needs of kit/.uak/bin/start; the identity the dashboard reads is the one `uak status` uses; a new test file needs its own timing file under kit/.uak/tests/timings (UAK-187)

## UAK-164 · Paste or drop what you already have: the agent fills the form, the person confirms

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/planning.py, kit/.uak/bin/start, kit/.uak/docs/CLI.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, kit/.uak/tests/test_setup_intake.py, kit/.uak/bin/lib/workspace.js, kit/.uak/tests/test_setup_language.py, kit/.uak/tests/timings/test_setup_intake.txt
- **Acceptance:**
  - every wizard screen that asks for more than two typed values (the schedule, the idea, the rubric, the people) opens with one input: paste text, or drop or pick a file (`.md`, `.txt`, `.pdf`, an image of a call for projects, an existing `IDEA.md`). The form is still there below it, and typing by hand always works
  - the person's own coding tool (the one the planner already uses: `claude -p` or `codex exec`) reads what was given and proposes the fields of that screen: for the schedule, start, deadline, time zone and freeze; for the idea, what is built, for whom, the rubric with its weights, the duration and the team size; for people, names and roles. While it reads, the input shows what it is doing and for how long, and can be cancelled; it has a time limit of 60 s
  - nothing is saved until the person confirms: each proposed field is marked as proposed, shows the sentence of the source it came from, and can be edited or cleared; a field the source does not state stays empty and says so, it is never invented; a date without a year or a time zone is asked, not guessed. One button confirms the screen
  - the source is data, never instructions: the reader runs with no tools, no file access and no write permission, gets the text only, and must answer in a fixed schema that the server validates (types, ranges, known time zones, lengths); anything outside the schema is dropped; a source that tells the reader to do something changes nothing. The test gives it a file with an injected instruction and with a field of 10,000 characters
  - a file is read on the machine and never uploaded by the kit; the screen says, before reading, which tool will receive the text; files over 2 MB or of another type are refused with the reason; the source is not committed unless the person keeps it as `IDEA.md`
  - with no coding tool that can run headless, the input says so and the form is filled by hand; dates and times in common formats are still recognised without a model
  - the terminal has the same: `uak start --from FILE` proposes the same fields as text and asks for a confirmation per screen; an agent identity cannot confirm for the person
  - the tokens the reading cost are shown next to the result and recorded in the ledger
  - Why (the human, 2026-11-23): typing the event's data and the idea by hand defeats the purpose when the call for projects or the idea already exists as a file
- **Tests:** dropped_file_fills_the_schedule, pasted_idea_fills_the_form, nothing_is_saved_before_confirm, missing_field_stays_empty, injected_instruction_changes_nothing, oversized_field_is_dropped, no_headless_tool_falls_back_to_the_form, terminal_from_file_proposes_the_same, reading_can_be_cancelled
- **Verify:** `python3 kit/.uak/tests/test_setup_intake.py`
- **Next step:** the headless runner in kit/.uak/bin/lib/planning.py (it already builds the `claude -p` and `codex exec` commands and checks for violations afterwards); the forms are the schedule and the idea in setup.html; a new test file needs its own timing file under kit/.uak/tests/timings (UAK-187); the tests use a fake tool in PATH, never a real model

## UAK-165 · The summary is made of components the viewer arranges: move, hide, add

- **Type:** feature
- **Priority:** P1
- **Estimate:** 8 h
- **Depends on:** UAK-162
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/dash, kit/.uak/docs/CLI.md, docs/DASHBOARD.md, docs/design/DIRECTION.md, kit/.uak/tests/test_dashboard_layout.py, kit/.uak/tests/timings/test_dashboard_layout.txt
- **Acceptance:**
  - every block of the summary (needs you, tasks, activity, progress, agents, integrations per period, tokens) is a component with a name, a title, a size (main column or side column), its maximum of rows and one render function over the dashboard's data; the summary is a list of component names per column, and the default list is today's order
  - "Edit" in the summary's header turns on an arrange mode: each component shows handles to move it up or down, to send it to the other column, and to hide it; "Add" lists the components not shown, each with one line saying what it shows. Everything works with the keyboard (no drag is required) and at phone width; "Done" leaves the mode, "Restore" returns to the default
  - the arrange mode is unmistakable the moment it starts: every component that can be moved shakes slightly (a small, slow rotation of about one degree, each out of step with its neighbours, as app icons do on a phone when they can be rearranged), gets a dashed outline and shows its handles, and one line at the top says what can be done ("Move, hide or add components. Done when you finish."). Under `prefers-reduced-motion` nothing moves: the outline, the handles and the line carry the meaning. The shake stops for the component under the pointer or with keyboard focus, so its controls hold still, and it never runs outside the arrange mode
  - the arrangement is the viewer's: kept in the browser per project, it changes no tracked file and nobody else's panel. A team may ship a default: `uak dash layout --save` writes the current arrangement to `.uak/dash/layout.json` (a file a task or the human commits), and a viewer with no arrangement of their own starts from it
  - "needs you" can be moved but not hidden: a panel that does not say what waits for the person is not the kit's panel. The rule that the summary never grows with the plan holds for every component in every position
  - an arrangement that names a component that no longer exists, or a corrupt one, falls back to the default and says so once; it never leaves an empty page
  - the page stays one file opened from `file://`, with no server, no request and no build step
- **Tests:** summary_is_a_list_of_components, arrange_mode_shakes_and_respects_reduced_motion, move_hide_and_add_persist_per_viewer, needs_you_cannot_be_hidden, team_default_is_used_when_the_viewer_has_none, unknown_component_falls_back, arranging_works_with_the_keyboard
- **Verify:** `python3 kit/.uak/tests/test_dashboard_layout.py`
- **Next step:** the summary's sections in kit/.uak/bin/lib/dash.html after UAK-162; the data every component reads is what `dash.py` already writes to `data.js`; a new test file needs its own timing file under kit/.uak/tests/timings (UAK-187)

## UAK-167 · Describe a component in words and get it: a declarative spec the panel draws, reusable in any project

- **Type:** feature
- **Priority:** P2
- **Estimate:** 10 h
- **Depends on:** UAK-165, UAK-164
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/dash, kit/.uak/bin/lib/planning.py, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/setup.html, kit/.uak/docs/CLI.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, kit/.uak/tests/test_dashboard_widget_spec.py, kit/.uak/bin/lib/workspace.js, kit/.uak/tests/test_setup_language.py, kit/.uak/tests/timings/test_dashboard_widget_spec.txt
- **Acceptance:**
  - a component can be a spec, not code: a small JSON file that names a source of the dashboard's data (tasks, agents, reviews, moves, messages, tokens, merges), a filter, a grouping, an order, a maximum, the fields to show and one of the panel's own drawings (list, table, counter, bars, lanes, timeline). The panel validates the spec against a schema and draws it with its own trusted renderers; it never runs code from a spec, and a spec cannot make a request, read anything outside the dashboard's data or draw outside its box. An invalid spec shows its error in its place and nothing else changes
  - `uak dash widget "the agents of mine that are reviewing, with how long"` asks the person's own coding tool (the reader of UAK-164: no tools, no file access, a fixed answer schema) for a spec, validates it, shows what it would draw with the project's real data, and saves it only when the person confirms. With the wizard's server open, the same is a field in "Add" with a visible wait and a preview. With no tool that can run headless, the command says so and names the file format to write by hand
  - specs live in `.uak/dash/widgets/NAME.json` for the project (a file a task or the human commits) and in the person's own directory for every project of theirs; `uak dash widget --list`, `--remove NAME` and `--export NAME` manage them. A spec written in one project draws in another without change, because it names data every project of the kit has; a field the other project lacks shows as empty, not as an error
  - a spec inherits theme, palette, scale and the maximums of the direction: it has no colours, sizes or fonts of its own
  - the description is data, never instructions: the test gives a description that tries to make the reader write a file or add a script, and a spec with a `script`, a URL or an unknown drawing; all are refused
  - Why (the human, 2026-11-23): people should put on their panel what they need most, including a view nobody built yet, and carry it to their next project
- **Tests:** spec_is_validated_and_drawn_by_the_panel, spec_never_runs_code, described_widget_is_previewed_before_saving, spec_from_one_project_draws_in_another, invalid_spec_shows_its_error, injected_description_is_refused, no_headless_tool_says_how_to_write_it
- **Verify:** `python3 kit/.uak/tests/test_dashboard_widget_spec.py`
- **Next step:** the component registry of UAK-165 (a spec becomes a component whose render function is one of the fixed drawings); the headless reader of UAK-164 in kit/.uak/bin/lib/planning.py; a new test file needs its own timing file under kit/.uak/tests/timings (UAK-187)

## UAK-188 · The guard and SECURITY.md know the wizard's reopen key and its two new requests

- **Type:** fix
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-156
- **Paths:** kit/.uak/bin/guard, kit/.uak/docs/SECURITY.md, kit/.uak/tests/test_setup_trust.py, kit/.uak/tests/test_guard_wizard_files.py, kit/.uak/tests/timings/test_guard_wizard_files.txt
- **Acceptance:**
  - while a wizard is live for the project (its port file names a live process), the guard refuses an agent's command that reads, copies or prints `uak-wizard.key`, and one that names `/api/reopen` or `/api/closing` on the wizard's port or on a port it cannot read; with no live wizard the same commands pass, and a project's own `/api/reopen` on another port passes. Why: the review of UAK-156 ran `cat .git/uak-wizard.key` and a `curl` to `/api/reopen` through `guard check` and both were allowed; the key gives a fresh code for the human's page
  - the guard refuses an agent's command that removes or rewrites `uak-wizard.port`, `uak-wizard.key` or `uak-wizard.children` while a wizard is live: without the port file the rule above stops matching
  - SECURITY.md says what is left: a script that hides the request, any process of the same user that reads the key, and what the person sees when it happens (the line on the first server's terminal, the entry in the register, the notice on the open page); the sentence about a stolen code being "used once" is corrected for the reopen route
  - no rule of UAK-153's guard changes its result on the cases of `test_setup_trust`
- **Tests:** key_read_is_refused_while_live, reopen_and_closing_are_refused_on_the_wizard_port, same_names_pass_without_a_wizard, other_port_passes, record_files_cannot_be_removed_while_live, security_doc_names_the_reopen_key
- **Verify:** `python3 kit/.uak/tests/test_guard_wizard_files.py && python3 kit/.uak/tests/test_setup_trust.py`
- **Next step:** `wizard_mentioned` in kit/.uak/bin/guard; SECURITY.md line 42; the guard is the human's file, so the merge goes to the human

## UAK-189 · The gate's smoke does not inherit the caller's task, and three small leftovers of the reviews

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-186, UAK-185
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/bin/hook, kit/.uak/tests/test_gate_environment.py, kit/.uak/tests/test_hook_session_start_speed.py, kit/.uak/tests/test_smoke_onboarding.py, kit/.uak/tests/timings/test_gate_environment.txt
- **Acceptance:**
  - `uak merge` run from a task's worktree gives the same smoke result as from the main checkout: the gate removes `UAK_TASK` (and the other variables `.uak-env` sets) from the environment of its smoke. Why: on 2026-11-23 the merge of UAK-157, run from its worktree, failed `test_manual_notes` and `test_task_participants` because their fixtures recorded under the real task; from the main checkout without the variable it merged
  - a pending black-box file whose owner belongs to another user of the system is not taken: a `kill -0` that fails for lack of permission counts as "alive" (the review of UAK-185: EPERM was read as "dead")
  - the smoke boot refuses a newline in any component of a path, not only in the last name
  - in `Review-Mode: auto` a project without `gh` in PATH says which mode it chose and why, once, in `uak done` and `uak merge`
- **Tests:** merge_from_worktree_equals_merge_from_main, smoke_environment_has_no_task, other_users_pending_file_is_left, newline_in_a_folder_is_refused, auto_mode_says_what_it_chose
- **Verify:** `python3 kit/.uak/tests/test_gate_environment.py && python3 kit/.uak/tests/test_smoke_onboarding.py && python3 kit/.uak/tests/test_hook_session_start_speed.py`
- **Next step:** where `approval_check` and the smoke are called in kit/.uak/bin/lib/review-merge.sh (search `smoke`); `bb_flush_job` in kit/.uak/bin/hook (search `kill -0`); the gate's library is the human's file, so the merge goes to the human
