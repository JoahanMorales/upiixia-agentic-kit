## UAK-152 · The visual setup and the unified dashboard come in: the contributed branch is merged onto v6.8 with its history

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** None
- **Test-First:** no (a merge of a contribution that brings its own tests; the task adds no behaviour of its own)
- **Paths:** .github/workflows/test.yml, CHANGELOG.md, README.md, install.sh, docs/, kit/, scripts/
- **Acceptance:**
  - the branch of the third delivery (commit `8c9e2f17`, which contains the first two; fetch it with `git fetch https://github.com/DylanMCDS/upiixia-agentic-kit.git pull/52/head`) is merged into the task's branch with a merge commit, so the contributor's 201 commits and authorship stay in the history; nothing is squashed or rebased
  - conflicts are resolved keeping both sides' behaviour: `hook` keeps the background session start and prints main's "claims as of N s ago" line; `status.sh` keeps `budget_note`, `rc_age_line` and the reviewer-aware `next`; `dash.py` and `dash.html` keep the REVIEW sub-states and the single lease rule of v6.8 and gain the profiles, the offline mode and `Live-URL`; `CLI.md` lists the fields of both sides
  - decided by the human (2026-11-22), applied here: CI stays as on main (18 jobs per commit, macOS on pull requests); the contributed `exclude` of macOS, `ci_once_problems` and `test_ci_light.py` are not taken, and the check that the workflow has `workflow_dispatch` moves into main's lint; `install.sh` keeps main's handling of tests (`--with-tests`, pruning by known hash) and never runs `rm -rf .uak/tests`; the tutorial video and its poster and captions are not copied into a project (the wizard shows them from the kit's checkout when it is there, and a link otherwise); the design lock stays for events under 24 h, and the task cap by hours and people is taken
  - task IDs that collide with main are renumbered everywhere they appear (changelog, WHY.md, tests, comments): the contributed UAK-009…013, 038, 067…069 and 087…096 get new numbers from UAK-160 on, listed in one table in the changelog entry; UI-001…024 keep their numbers. WHY.md rows state the rule and its reason without naming who decided; the changelog credits the contributor
  - every new test file has an entry in `CI_SECONDS` and `CI_WINDOWS_SECONDS` measured in the task's own CI run, no file is over half of `WINDOWS_BOUND_S` (split it, do not add an exception), the longest Windows shard stays under the margin, and the job count stays 18
  - `kit_lint`, `kit_hashes`, `gen_registry` and the whole smoke pass on Linux, macOS and Windows; a marathon install stays under 270 files
  - main is not released between this task and UAK-153: the wizard still performs the human's acts unguarded until then
- **Verify:** `python3 scripts/kit_lint.py && python3 kit/.uak/tests/test_ci_shards.py && python3 kit/.uak/tests/test_install_light.py && python3 kit/.uak/tests/test_setup_wizard.py`
- **Next step:** `git merge --no-ff 8c9e2f17`; nine files conflict (`test.yml`, `CHANGELOG.md`, `install.sh`, `hook`, `dash.html`, `dash.py`, `status.sh`, `CLI.md`, `known-files.txt`); regenerate `known-files.txt` last

## UAK-153 · The wizard acts for the human only when a human runs it

- **Type:** fix
- **Priority:** P0
- **Estimate:** 5 h
- **Depends on:** UAK-152
- **Paths:** kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/setup.html, kit/.uak/bin/guard, kit/.uak/docs/WHY.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, kit/.uak/tests/test_setup_trust.py
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

## UAK-154 · A newer kit blocks a published project only on a major version

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-152
- **Paths:** kit/.uak/bin/start, kit/.uak/docs/CLI.md, kit/.uak/tests/test_start_version_gate.py
- **Acceptance:**
  - in a project whose kit is already on the team's base branch (or with `Freeze-Epoch` set), a newer release with the same major version is a note that does not block `uak start`; a newer major version is a `need` that blocks until the kit is updated, and says which version and how
  - a project that has not published the kit yet is blocked by any newer release, as before the contribution
  - `UAK_KIT_PIN` behaves as today; versions are compared as numbers (`6.10.0` is newer than `6.9.0`), and an unreadable version blocks nothing and says so
- **Tests:** same_major_is_a_note, newer_major_blocks_a_published_project, unpublished_project_is_blocked_by_any_release, versions_compare_as_numbers
- **Verify:** `python3 kit/.uak/tests/test_start_version_gate.py`
- **Next step:** the version check in kit/.uak/bin/start (search `VERSION` and `not blocking`)

## UAK-155 · `done --pr none` is tested under every review mode, and the generated smoke does not trust file names

- **Type:** fix
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-152
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/bin/lib/smoke-init.sh, kit/.uak/tests/test_done_without_github.py, kit/.uak/tests/test_smoke_onboarding.py
- **Acceptance:**
  - a task finished with `--pr none` is never merged without an approval of its exact tip by another registered identity, in `Review-Mode` claims, gh and auto; under `Merge-Engine: ci` it goes to the human (the required checks need a pull request), with a reason that says so
  - `UAK_REVIEW_MODE` in the environment never lets `--pr none` through on a repository whose base PROJECT.md says `Review-Mode: gh`
  - the boot command that `init-smoke` generates never interpolates a file or package name into a shell string: a name with a quote, a space, `;` or `$(` is passed as an argument or refused, and the generated smoke says which
- **Tests:** pr_none_still_needs_an_approval, pr_none_goes_to_the_human_under_merge_engine_ci, env_review_mode_does_not_override_the_base, smoke_boot_does_not_run_a_file_name
- **Verify:** `python3 kit/.uak/tests/test_done_without_github.py && python3 kit/.uak/tests/test_smoke_onboarding.py`
- **Next step:** `done_no_pr_check` in kit/.uak/bin/lib/done.sh and `boot`/`detect` in kit/.uak/bin/lib/smoke-init.sh
