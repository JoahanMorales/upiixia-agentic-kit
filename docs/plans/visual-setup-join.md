## UAK-163 · Someone who joins a project that is already set up: three screens, nothing to configure about the project

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159, UAK-162
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/start, kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/docs/CLI.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_setup_join.py
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
