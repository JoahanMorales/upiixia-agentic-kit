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
  - the last screen and its "Close" say the one command that continues in the terminal (`cd PROJECT && bash .uak/bin/uak start`, the path quoted so the line can be pasted), and the rail uses the same step names as `uak start --steps` (Project detected, Rules, People, Schedule, Publish the kit, Idea and plan, Start the agents). Why: UAK-161 made the install offer both ways; its clause about this screen could not be met there because the page is outside its Paths
- **Tests:** flow_has_the_ten_screens, existing_repository_is_detected, rules_screen_writes_only_what_was_confirmed, schedule_only_in_hackathon, diagnostics_are_not_prechecked, old_kit_opens_update, close_ends_the_server, no_screen_taller_than_two_viewports, instruction_appears_once, first_install_in_four_clicks, error_is_next_to_its_control, step_survives_reload_and_back, mobile_content_starts_within_160px, targets_are_44px, last_screen_says_the_terminal_command, rail_names_match_the_terminal_steps
- **Verify:** `python3 kit/.uak/tests/test_setup_forms.py && python3 kit/.uak/tests/test_setup_guide.py && python3 kit/.uak/tests/test_setup_resume.py && python3 kit/.uak/tests/test_setup_first_run.py`
- **Next step:** the "Get ready" markup in setup.html (about lines 1700-2040 of the contributed file) and the hero at 1434-1460; the detection of hooks is `doctor`'s (UAK-135, UAK-146), reuse it; changed assertions need `uak allow UAK-159 --tests` from the human

## UAK-160 · The wizard's Spanish is written, not translated from the engine's sentences

- **Type:** fix
- **Priority:** P1
- **Estimate:** 5 h
- **Depends on:** UAK-159, UAK-161
- **Paths:** kit/.uak/bin/lib/workspace.js, kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/start, kit/.uak/tests/test_setup_language.py, install.sh, kit/.uak/tests/test_install_choice.py
- **Acceptance:**
  - the page never matches the engine's English prose: `uak --json start` (and the other commands the wizard runs) give each need and note a stable code and its values, and the page's texts are keyed by code in both languages. A test rewords an engine sentence and the Spanish page is unchanged; a code with no text in a language fails the test, it does not fall back to English
  - one voice in Spanish: "tú" throughout, usage of Mexico ("haz clic", not "pulsa"), no sentence that mixes languages. A glossary in the page's dictionary fixes the terms that stay in English because they are commands or git words (`commit`, `merge`, `pull request`, `worktree`, `main`) and the ones that are translated (dashboard → panel, claim → tomar una tarea); the test fails on a term outside it
  - both languages are complete on every screen, including the readiness block and the commands' explanations
  - no exclamation marks, no filler ("simplemente", "fácilmente", "potente"), sentence case in headings and buttons
  - the question the install asks at a terminal ("browser or terminal"), its answers and the lines that say how to continue are written in Spanish when the person's language is Spanish (the same rule the wizard uses to choose its language; `navegador` and `terminal` are accepted as answers in either language), and in English otherwise; the tokens other tools read (`Done`, `Next:`, exit codes, the commands themselves) do not change, and an install with no terminal prints the same lines as today. Asked by the human on 2026-11-24
- **Tests:** texts_are_keyed_by_code, rewording_the_engine_changes_nothing, no_missing_text_in_either_language, one_voice_in_spanish, glossary_is_respected, install_question_is_spanish_for_a_spanish_speaker, install_tokens_do_not_change
- **Verify:** `python3 kit/.uak/tests/test_setup_language.py && python3 kit/.uak/tests/test_install_choice.py`
- **Next step:** the dictionary and the regex table in kit/.uak/bin/lib/workspace.js and the needs of kit/.uak/bin/start; changed assertions need `uak allow UAK-160 --tests` from the human
