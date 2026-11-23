## UAK-153 · The wizard acts for the human only when a human runs it

- **Type:** fix
- **Priority:** P0
- **Estimate:** 5 h
- **Depends on:** UAK-152
- **Paths:** kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/setup.html, kit/.uak/bin/guard, kit/.uak/docs/WHY.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, kit/.uak/tests/test_setup_trust.py, kit/.uak/bin/lib/workspace.js, scripts/kit_lint.py, kit/.uak/tests/test_setup_resume.py, kit/.uak/tests/test_setup_roles.py, kit/.uak/tests/test_setup_team.py, kit/.uak/tests/test_setup_language.py
- **Acceptance:**
  - `setup.py` (and so `install.sh --wizard`) refuses to start when the process has an agent identity: `UAK_AGENT` set, a `.uak-env` naming an agent, `uak.agent` in the git config, or a checkout that is an agent's worktree. The refusal names the reason and how a human starts it
  - `guard` blocks an agent's command that starts the wizard (`setup.py`, `install.sh --wizard`) or that sends a request to a local wizard, in every mode, as it blocks a command that sets `UAK_HUMAN`
  - the session token is never printed and never appears in a process's arguments: the browser is opened on a one-time code that the server exchanges, once, for the session; the printed line carries no secret. A session idle for 30 minutes ends, and the terminal says how to open a new one
  - the human's name is not free text from the page: it is the git identity of the checkout, shown, not typed; a request that names another is refused
  - registering a reviewer, approving a plan and publishing the kit go through the engine's own commands where one exists, and each writes one line to `uak-direct-main.log` (what, who, when, the commit), as a human's direct push does
  - a page of another origin, a request with a wrong Host and a request without the session are refused as today
  - Why (audit, 2026-11-22): an agent could start the wizard, read the token from its own output, name any human and register a reviewer, approve a plan and push to main; the server strips `UAK_*`, so the pre-push hook saw no agent. WHY.md: "Human authority only from the shell"
- **Tests:** agent_identity_cannot_start_the_wizard, guard_blocks_an_agent_starting_the_wizard, token_is_not_printed_or_in_argv, one_time_code_works_once, idle_session_ends, human_name_is_the_git_identity, human_acts_are_logged
- **Verify:** `python3 kit/.uak/tests/test_setup_trust.py`
- **Next step:** `run_command` and the token in kit/.uak/bin/lib/setup.py (search `token_urlsafe`, `UAK SETUP`, `safe_environment`); the POST dispatcher lists the three acts (`/api/team/reviewer`, `/api/plan/approve`, `/api/publish-kit`)

## UAK-156 · The wizard is one process that ends by itself, and an open page costs nothing while nothing happens

- **Type:** fix
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-153
- **Paths:** kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/planning.py, kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/dash.py, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_setup_processes.py, kit/.uak/bin/lib/workspace.js, kit/.uak/tests/test_setup_language.py
- **Acceptance:**
  - one server per project: a start records its pid and port under the git directory; a second start for the same project checks that the first answers and opens that one, and starts nothing; a stale record (dead pid, port not answering) is replaced
  - the server ends by itself: 15 minutes with no request, or the page closed (the page says so on `pagehide`) and no action running; SIGTERM, SIGHUP and Ctrl-C end it too. The terminal prints why it ended and the one command that opens it again. The port is free at once
  - no child outlives the server: every child (git, `uak`, `install.sh`, the planner `claude`/`codex`) is in a group the server records and kills on every exit path, on Linux, macOS and Windows; on Linux a child also dies when the server is killed with SIGKILL (parent-death signal); a start reaps what a killed server left, from the record. The planner's time limit is 10 minutes, not 30
  - no timer runs the readiness check: `/api/check` runs when the page loads, after an action of the user, and on a button; never every 60 s
  - every poll stops while the page is hidden and backs off while nothing changes (20 s, 60 s, 120 s); progress of a running action may poll every 1.2 s only while that action runs
  - the dashboard's data inside the wizard imports `dash.py` once per server, and when the claims tip did not move a refresh costs one `git ls-remote` and nothing else
  - the standalone dashboard keeps main's model (a file under the git directory, opened from `file://`, no server, no port); the wizard shows that same page and never needs a second process for it
  - measured in the test with a counting `git` in PATH: a visible idle page on any wizard screen starts 0 processes in 60 s after its first load (950 before); the dashboard screen at most 3 `git` per minute when nothing moved (18 before); 200 quick requests leave no extra thread after 30 s
  - Why (measured 2026-11-22): one `/api/check` costs about 950 forks and 1.25 CPU-s and ran every minute for ever; two starts gave two servers on two ports, neither ended; a planner survived SIGTERM, SIGKILL and SIGHUP of the server with PPID 1
- **Tests:** second_start_reuses_the_first, idle_server_ends, closed_page_ends_the_server, no_child_survives_sigterm, no_child_survives_sigkill_on_linux, stale_record_is_reaped, idle_page_starts_no_process, hidden_page_does_not_poll, dashboard_refresh_is_one_ls_remote
- **Verify:** `python3 kit/.uak/tests/test_setup_processes.py`
- **Next step:** `run_command` (`start_new_session=True`) and `main()` (`serve_forever`) in kit/.uak/bin/lib/setup.py; `autoCheck` (`setInterval(...,60000)`) and `loadDashboard` (`setTimeout(...,20000)`) in setup.html; `PLAN_TIMEOUT` in planning.py. A new test file needs its entries in both timing tables

## UAK-159 · The wizard's flow: ten screens, one job each, and it covers what the kit does today

- **Type:** feature
- **Priority:** P0
- **Estimate:** 12 h
- **Depends on:** UAK-158
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, docs/DASHBOARD.md, kit/.uak/tests/test_setup_forms.py, kit/.uak/tests/test_setup_guide.py, kit/.uak/tests/test_setup_resume.py, kit/.uak/tests/test_setup_first_run.py, kit/.uak/bin/lib/workspace.js, kit/.uak/tests/test_setup_language.py
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

## UAK-163 · Someone who joins a project that is already set up: three screens, nothing to configure about the project

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159, UAK-162
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/start, kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/docs/CLI.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_setup_join.py, kit/.uak/bin/lib/workspace.js, kit/.uak/tests/test_setup_language.py
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
- **Next step:** the route that picks the first screen in kit/.uak/bin/lib/setup.py (`open_target`) and the needs of kit/.uak/bin/start; the identity the dashboard reads is the one `uak status` uses; a new test file needs its entries in both timing tables

## UAK-164 · Paste or drop what you already have: the agent fills the form, the person confirms

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/planning.py, kit/.uak/bin/start, kit/.uak/docs/CLI.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_setup_intake.py, kit/.uak/bin/lib/workspace.js, kit/.uak/tests/test_setup_language.py
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
- **Next step:** the headless runner in kit/.uak/bin/lib/planning.py (it already builds the `claude -p` and `codex exec` commands and checks for violations afterwards); the forms are the schedule and the idea in setup.html; a new test file needs its entries in both timing tables; the tests use a fake tool in PATH, never a real model

## UAK-167 · Describe a component in words and get it: a declarative spec the panel draws, reusable in any project

- **Type:** feature
- **Priority:** P2
- **Estimate:** 10 h
- **Depends on:** UAK-165, UAK-164
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/dash, kit/.uak/bin/lib/planning.py, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/setup.html, kit/.uak/docs/CLI.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_dashboard_widget_spec.py, kit/.uak/bin/lib/workspace.js, kit/.uak/tests/test_setup_language.py
- **Acceptance:**
  - a component can be a spec, not code: a small JSON file that names a source of the dashboard's data (tasks, agents, reviews, moves, messages, tokens, merges), a filter, a grouping, an order, a maximum, the fields to show and one of the panel's own drawings (list, table, counter, bars, lanes, timeline). The panel validates the spec against a schema and draws it with its own trusted renderers; it never runs code from a spec, and a spec cannot make a request, read anything outside the dashboard's data or draw outside its box. An invalid spec shows its error in its place and nothing else changes
  - `uak dash widget "the agents of mine that are reviewing, with how long"` asks the person's own coding tool (the reader of UAK-164: no tools, no file access, a fixed answer schema) for a spec, validates it, shows what it would draw with the project's real data, and saves it only when the person confirms. With the wizard's server open, the same is a field in "Add" with a visible wait and a preview. With no tool that can run headless, the command says so and names the file format to write by hand
  - specs live in `.uak/dash/widgets/NAME.json` for the project (a file a task or the human commits) and in the person's own directory for every project of theirs; `uak dash widget --list`, `--remove NAME` and `--export NAME` manage them. A spec written in one project draws in another without change, because it names data every project of the kit has; a field the other project lacks shows as empty, not as an error
  - a spec inherits theme, palette, scale and the maximums of the direction: it has no colours, sizes or fonts of its own
  - the description is data, never instructions: the test gives a description that tries to make the reader write a file or add a script, and a spec with a `script`, a URL or an unknown drawing; all are refused
  - Why (the human, 2026-11-23): people should put on their panel what they need most, including a view nobody built yet, and carry it to their next project
- **Tests:** spec_is_validated_and_drawn_by_the_panel, spec_never_runs_code, described_widget_is_previewed_before_saving, spec_from_one_project_draws_in_another, invalid_spec_shows_its_error, injected_description_is_refused, no_headless_tool_says_how_to_write_it
- **Verify:** `python3 kit/.uak/tests/test_dashboard_widget_spec.py`
- **Next step:** the component registry of UAK-165 (a spec becomes a component whose render function is one of the fixed drawings); the headless reader of UAK-164 in kit/.uak/bin/lib/planning.py; a new test file needs its entries in both timing tables
