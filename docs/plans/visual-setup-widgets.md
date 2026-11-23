## UAK-165 · The summary is made of components the viewer arranges: move, hide, add

- **Type:** feature
- **Priority:** P1
- **Estimate:** 8 h
- **Depends on:** UAK-162
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/dash, kit/.uak/docs/CLI.md, docs/DASHBOARD.md, docs/design/DIRECTION.md, scripts/kit_lint.py, kit/.uak/tests/test_dashboard_layout.py
- **Acceptance:**
  - every block of the summary (needs you, tasks, activity, progress, agents, integrations per period, tokens) is a component with a name, a title, a size (main column or side column), its maximum of rows and one render function over the dashboard's data; the summary is a list of component names per column, and the default list is today's order
  - "Edit" in the summary's header turns on an arrange mode: each component shows handles to move it up or down, to send it to the other column, and to hide it; "Add" lists the components not shown, each with one line saying what it shows. Everything works with the keyboard (no drag is required) and at phone width; "Done" leaves the mode, "Restore" returns to the default
  - the arrangement is the viewer's: kept in the browser per project, it changes no tracked file and nobody else's panel. A team may ship a default: `uak dash layout --save` writes the current arrangement to `.uak/dash/layout.json` (a file a task or the human commits), and a viewer with no arrangement of their own starts from it
  - "needs you" can be moved but not hidden: a panel that does not say what waits for the person is not the kit's panel. The rule that the summary never grows with the plan holds for every component in every position
  - an arrangement that names a component that no longer exists, or a corrupt one, falls back to the default and says so once; it never leaves an empty page
  - the page stays one file opened from `file://`, with no server, no request and no build step
- **Tests:** summary_is_a_list_of_components, move_hide_and_add_persist_per_viewer, needs_you_cannot_be_hidden, team_default_is_used_when_the_viewer_has_none, unknown_component_falls_back, arranging_works_with_the_keyboard
- **Verify:** `python3 kit/.uak/tests/test_dashboard_layout.py`
- **Next step:** the summary's sections in kit/.uak/bin/lib/dash.html after UAK-162; the data every component reads is what `dash.py` already writes to `data.js`; a new test file needs its entries in both timing tables

## UAK-166 · More components to choose from

- **Type:** feature
- **Priority:** P1
- **Estimate:** 8 h
- **Depends on:** UAK-165
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, docs/DASHBOARD.md, kit/.uak/tests/test_dashboard_layout.py, kit/.uak/tests/test_dashboard_truth.py
- **Acceptance:**
  - the catalogue gains these components, each within the direction's rules (a title and a count, a maximum, a link to its tab), each fed only by data the engine already records: (1) Review queue: every review with its sub-state, its reviewer and the share of its lease used, overdue first. (2) My agents: the agents of the person looking, what each does and for how long (needs the identity of UAK-163; without one it says how to set it). (3) What unblocks what: the tasks that hold others back, with how many wait behind each. (4) Event clock, in Hackathon mode: time to the freeze and to the deadline, and the share of the plan integrated against the share of the time gone. (5) Last integrations: the last merges with task, author, reviewer and commit. (6) Recent messages: the last messages between agents and to the human. (7) Cost per task: tokens per task, the dearest first, against the estimate. (8) Checks: the state of the required checks of the open pull requests, when the forge gives it. (9) Deployment: the `Live-URL` and when it last answered, when one is set
  - a component with nothing to show says why in one line (no reviews waiting, no schedule set) and takes one row, never an empty box
  - each has a test with a fixture that pins its numbers against the claims data, as the existing components have
  - screenshots of every new component at 1280 and 390, light and dark, in two palettes, are in `.uak-shots/UAK-166/` with the design critic's `VERDICT: SHIP` for the task's commit
- **Tests:** review_queue_orders_overdue_first, my_agents_needs_an_identity, blockers_count_what_waits, event_clock_only_in_hackathon, empty_component_says_why, each_new_component_matches_the_claims
- **Verify:** `python3 kit/.uak/tests/test_dashboard_layout.py && python3 kit/.uak/tests/test_dashboard_truth.py`
- **Next step:** the component registry of UAK-165; `dash.py` already reads reviews, messages, tokens and merge commits from the claims branch

## UAK-167 · Describe a component in words and get it: a declarative spec the panel draws, reusable in any project

- **Type:** feature
- **Priority:** P2
- **Estimate:** 10 h
- **Depends on:** UAK-165, UAK-164
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/dash, kit/.uak/bin/lib/planning.py, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/setup.html, kit/.uak/docs/CLI.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_dashboard_widget_spec.py
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
