## UAK-027 · CI installs the web/ dependencies before the product smoke

- **Type:** bug
- **Priority:** P0
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.github/workflows/uak.yml, kit/.uak/tests/test_ci_web_deps.py
- **Acceptance:**
  - the team workflow gets a step before "Product smoke" that runs `npm ci --no-audit --no-fund` in every one of `.`, `web`, `frontend`, `client` that has a `package-lock.json` (pnpm-lock.yaml → `pnpm install --frozen-lockfile` via corepack; yarn.lock → `yarn install --frozen-lockfile`), skipped when none exists
  - why (DevDay hackathon, 2026-11-08): the smoke runs `npm --prefix web run build`; the runner had no web/node_modules, so main failed 9 times in a row and every PR with "sh: 1: tsc: not found" until the team patched the workflow by hand
  - a fresh sprint install into a repo with `web/package-lock.json` gets that step; the workflow stays valid YAML
- **Tests:** workflow_installs_web_deps_before_smoke, workflow_skips_install_without_a_lockfile
- **Verify:** `python3 kit/.uak/tests/test_ci_web_deps.py`
- **Next step:** the step after "Go toolchain" in kit/.github/workflows/uak.yml

## UAK-028 · The design gallery's page passes design-lint

- **Type:** bug
- **Priority:** P1
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/design-gallery, kit/.uak/tests/test_gallery_lint.py
- **Acceptance:**
  - every color in the generated `design-lock/index.html` outside `:root` is a `var(--…)` token (today `kbd { color: #1d1f1c }`), so `design-lint` on a repo with tokens and a generated gallery prints DESIGN_LINT_PASS
  - why (DevDay hackathon): an agent's `done` was refused by design-lint for a hex in the kit's own gallery page
- **Tests:** generated_gallery_passes_design_lint
- **Verify:** `python3 kit/.uak/tests/test_gallery_lint.py`
- **Next step:** the kbd rule in the page template of kit/.uak/bin/design-gallery

## UAK-029 · `q` runs a Verify given as one string

- **Type:** bug
- **Priority:** P0
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/q, kit/.uak/tests/test_q_string.py
- **Acceptance:**
  - `bash .uak/bin/q "cmd1 && cmd2"` (one argument with a space or shell operator) runs it with `bash -c`, so `&&`, `|`, quotes and redirections work and its exit code is the command's; several arguments keep running as `"$@"` exactly as today
  - why (DevDay hackathon): an agent passed the task's Verify quoted and got exit 127 (the whole string taken as a command name)
  - the LOOP signature and the log path are unchanged for both forms
- **Tests:** a_quoted_compound_verify_runs, a_quoted_failing_verify_keeps_its_exit_code, argv_form_is_unchanged
- **Verify:** `python3 kit/.uak/tests/test_q_string.py`
- **Next step:** the `"$@" > "$log"` line of kit/.uak/bin/q

## UAK-030 · `done` and the design critic agree on the screenshot names

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.claude/agents/design-critic.md, kit/.uak/tests/test_ui_shot_names.py
- **Acceptance:**
  - the UI gate accepts `1280.png` or exactly one `*-1280.png` (same for 390) in `.uak-shots/ID/`; with two candidates and no `1280.png` it refuses naming them and asking which is the main screen
  - design-critic.md says the main screen must be saved as `1280.png` and `390.png` and the critic checks those names exist before writing its verdict
  - why (DevDay hackathon): the critic approved `landing-1280.png` and `voz-1280.png`, then `done` refused twice for missing `1280.png`
- **Tests:** a_prefixed_main_shot_is_accepted, two_prefixed_shots_are_refused_by_name
- **Verify:** `python3 kit/.uak/tests/test_ui_shot_names.py`
- **Next step:** the `for f in 1280.png 390.png critic.txt` loop of ui_gate in kit/.uak/bin/lib/done.sh

## UAK-031 · A claim refused by the freeze says not to retry

- **Type:** bug
- **Priority:** P2
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak-coordination, kit/.uak/tests/test_freeze_claim.py
- **Acceptance:**
  - the FREEZE refusal of `claim` ends with "Do not retry: the answer only changes when a human runs it. Take other work: uak next." and keeps UAK_CODE=freeze and the `uak allow` line
  - why (DevDay hackathon): one agent retried the same frozen claim 7 times
- **Tests:** freeze_claim_says_do_not_retry
- **Verify:** `python3 kit/.uak/tests/test_freeze_claim.py`
- **Next step:** the coord_freeze_allowed line of the claim command in kit/.uak/bin/uak-coordination

## UAK-032 · No git identity: wt and doctor say to set user.name and user.email

- **Type:** bug
- **Priority:** P1
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/wt, kit/.uak/bin/doctor, kit/.uak/tests/test_git_identity_msg.py
- **Acceptance:**
  - on a machine with no `git config user.name`, `wt new ID` exits 2 with "git has no identity: git config --global user.name \"Your Name\" && git config --global user.email you@example.com", not "--human: letters, digits…"
  - `doctor` reports a missing git user.name or user.email as a FAIL line with the same command
  - why (v6.0 review): a fresh laptop got a message about --human it never passed
- **Tests:** wt_new_without_git_identity_names_the_fix, doctor_flags_missing_git_identity
- **Verify:** `python3 kit/.uak/tests/test_git_identity_msg.py`
- **Next step:** where wt derives the human name from git config, before clean_id, in kit/.uak/bin/wt

## UAK-033 · A PR merged outside the gate can still be recorded, so claims match main

- **Type:** bug
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/uak-coordination, kit/.uak/docs/PROTOCOL.md, kit/.uak/tests/test_integrate_outside.py
- **Acceptance:**
  - `uak integrate ID` records INTEGRATED when main already contains the task's work, in each case seen: a squash merge, a PR merged after more commits than the approved SHA, a task branch that carried unrelated base merges, and identical content that landed on main by another commit. The check compares the task's own diff (merge-base..tip, base merges dropped) by patch-id or by final file content on main, never the whole tree hash
  - a task still AVAILABLE or CLAIMED whose `feat/<id>` PR is merged (gh, or the branch tip reachable from main) can be recorded by its owner or a human; the record says `Integrated-Outside: yes` and the approval it had (or `none`), and `uak stats`/`dash` count it apart from gated merges
  - its dependents become claimable at once; its file reservations are released
  - why (deus-ex-machina, OpenAI x Kavak hackathon, 1st place, 2026-11-09): 11 `integrate` refusals ("tree hash does not match", "changes no task file", "is AVAILABLE, not REVIEW") and 5 agent reports. At the end claims said 6 of 23 integrated, with 6 stuck in REVIEW and 3 expired claims, while the product had shipped and won
- **Tests:** squash_merged_pr_is_recorded, pr_merged_after_extra_commits_is_recorded, base_merges_in_the_task_branch_are_ignored, equivalent_content_on_main_is_recorded, merged_branch_of_an_available_task_unblocks_its_dependents, outside_merges_are_counted_apart
- **Verify:** `python3 kit/.uak/tests/test_integrate_outside.py`
- **Next step:** the tree-hash comparison of the integrate path in kit/.uak/bin/lib/review-merge.sh

## UAK-034 · `status` and `next` see a task published with `uak plan` before its first claim

- **Type:** bug
- **Priority:** P0
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/backlog.sh, kit/.uak/tests/test_status_planned.py
- **Acceptance:**
  - right after `uak plan FILE` (Plan-Channel: claims), `uak status ID` and `status --task ID` print the new task as AVAILABLE with its Paths, Verify and criteria (they come from claims:backlog/TASKS.md plus AMEND.md, as the transaction's canonical backlog does), on the read path that does not open a transaction too
  - why (both v6.0 events): "HACK-0xx is not in TASKS.md" 12 times, always minutes after a plan published that ID (DevDay HACK-037..041, deus HACK-017/019/021/022)
- **Tests:** status_shows_a_task_planned_on_claims, amended_task_shows_its_new_verify
- **Verify:** `python3 kit/.uak/tests/test_status_planned.py`
- **Next step:** the load_task fallback in the AVAILABLE branch of kit/.uak/bin/lib/status.sh

## UAK-035 · Work committed straight to main is stopped at commit time and counted

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.githooks/pre-commit, kit/.uak/bin/stats, kit/.uak/bin/doctor, kit/.uak/tests/test_direct_main.py
- **Acceptance:**
  - in a repo with a backlog, a commit on the base branch in the main checkout is refused with "main takes work through tasks: bash .uak/bin/wt new ID (or a human: UAK_DIRECT_MAIN=1 git commit … for a hotfix)"; `uak merge`, `wt` and the kit's own commits are not affected
  - `uak stats` prints `Direct to main: N of M first-parent commits` (commits on main not reached through a task merge), and `doctor` warns when core.hooksPath is not the kit's (the hook would not run)
  - why (deus-ex-machina): 120 of 155 first-parent commits on main came from agents working in the main checkout. The guard blocked one push to main, but the commits had already been made, so none of that work has a task, review, token attribution or a black box line
- **Tests:** commit_on_main_with_a_backlog_is_refused, hotfix_override_is_allowed_and_logged, uak_merge_still_commits, stats_counts_direct_commits
- **Verify:** `python3 kit/.uak/tests/test_direct_main.py`
- **Next step:** the branch check at the top of kit/.githooks/pre-commit

## UAK-036 · Token spend: every machine reports it, and the main checkout's share is visible

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/tokens, kit/.uak/bin/hook, kit/.uak/bin/lib/status.sh, kit/.uak/tests/test_tokens_coverage.py
- **Acceptance:**
  - besides the Claude Code Stop hook, `tokens --publish` also runs from session-start (for the previous sessions) and from the Codex hooks, and a failed publish writes one black box line with the reason instead of failing silently in the background
  - `uak tokens --team` lists the machines that worked (hosts of task worktrees, black box files) but never published: `NOT REPORTED: 2 machines (worktrees under /Users/…/orca, …)`; status's Tokens line says `from 1 of 3 machines`
  - the spend of sessions in the main checkout is shown as `main (coordination and work outside tasks) NN%`, with a warning above 50 %
  - why (both events): deus published tokens from 1 of 3 Macs (185 M tokens, 100 % "main"); DevDay 406 M with 78 % "main", one coordinator session alone 178 M cache reads. Per-task cost could not be measured
- **Tests:** publish_failure_is_recorded, team_view_names_machines_that_never_reported, main_share_is_reported_and_warned
- **Verify:** `python3 kit/.uak/tests/test_tokens_coverage.py`
- **Next step:** the publish call at the end of the session-start branch of kit/.uak/bin/hook

## UAK-037 · A gitleaks finding has its own way out

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/secret-scan, kit/.uak/bin/lib/security.sh, kit/.uak/tests/test_gitleaks_exception.py
- **Acceptance:**
  - when the finding comes from gitleaks (SECRET_EXTERNAL), the message points to its fingerprint and to `uak secret-exception ID --fingerprint FP --reason TEXT`, which secret-scan honors through a `.gitleaksignore` entry; the kit's own rules keep `--path --rule`. The scan stays on
  - why (deus-ex-machina): smoke flagged fixture history through gitleaks and suggested secret-exception, which refuses rules that are not the kit's
- **Tests:** gitleaks_finding_names_its_fingerprint, fingerprint_exception_clears_only_that_finding
- **Verify:** `python3 kit/.uak/tests/test_gitleaks_exception.py`
- **Next step:** the SECRET_EXTERNAL branch of kit/.uak/bin/secret-scan

## UAK-038 · Registered reviewers get the review work first

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/wait.sh, kit/.uak/tests/test_reviewer_next.py
- **Acceptance:**
  - for an identity registered as reviewer (or with no live claim and reviews pending), `uak next` offers every REVIEW task it may review before any coding task; `uak wait --for message` also wakes when a task enters REVIEW that it may review
  - `uak status ID --summary` works like `status --task ID --summary`
  - why (DevDay): a review-only Codex agent missed a REVIEW task because next offered coding work and wait did not wake it; Codex hit "--summary needs --task ID" 3 times in deus
- **Tests:** reviewer_next_offers_review_first, wait_wakes_on_new_review_work, status_id_summary_works
- **Verify:** `python3 kit/.uak/tests/test_reviewer_next.py`
- **Next step:** the candidate order of uak_next in kit/.uak/bin/lib/status.sh

## UAK-039 · A metric that was not measured is null, never 0

- **Type:** docs
- **Priority:** P2
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** kit/.uak/modes/sprint.md, kit/.uak/docs/WHY.md
- **Acceptance:**
  - sprint.md, a new rule next to the demo rules: cost, tokens, latency or any score that was not instrumented is written as `null` with "not measured", never 0, and the pitch says which measures are real
  - why (deus-ex-machina): the eval runs recorded 0 cost and tokens; the team had to add a warning to its submission that "the zeros are not a measurement"
- **Verify:** `grep -q "never 0" kit/.uak/modes/sprint.md`
- **Next step:** the demo rules of kit/.uak/modes/sprint.md

## UAK-040 · The `/uak-*` phase commands exist natively in Codex, Cursor and Gemini CLI

- **Type:** bug
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.claude/commands/, kit/.uak/skills/, install.sh, scripts/gen_harness.py, kit/AGENTS.md, kit/.uak/docs/CLI.md, kit/.uak/tests/test_harness_commands.py
- **Acceptance:**
  - the 13 phase scripts (uak-setup, uak-plan, uak-ship, uak-review, uak-handoff, uak-demo, …) come from one source and reach every harness the team installed:
    - Claude Code: `/uak-X`, as today;
    - Codex: an Agent Skill under `.agents/skills/uak-X/SKILL.md`, invoked as `$uak-X` or from `/skills` (Codex deprecated custom prompts);
    - Cursor: `/uak-X`, as a skill or from `.cursor/commands/uak-X.md`;
    - Gemini CLI: `/uak-X`, as a skill from `.agents/skills` or from `.gemini/commands/uak-X.toml`
  - a skill made from a phase script is only run when asked (`disable-model-invocation: true` or the harness's equivalent), so no agent starts `/uak-demo` on its own; Claude Code shows no duplicate `/uak-X`
  - `gen_harness.py --check` fails when a generated copy is stale (CI already runs it); the AGENTS.md line "Codex, Cursor, Gemini: `/uak-X` means follow `.claude/commands/uak-X.md`" changes to the native call
  - why (user's teammate, 2026-11-10): in Codex and Cursor the kit's commands "were not up to date". Codex and Cursor had no `/uak-*` at all, and Codex no longer reads custom prompts
- **Tests:** every_phase_command_reaches_every_harness, phase_skills_are_not_model_invoked, generated_commands_match_their_source
- **Verify:** `python3 kit/.uak/tests/test_harness_commands.py`
- **Next step:** the command → skill writer in scripts/gen_harness.py

## UAK-041 · Skills work on a Windows clone and in a Gemini-only install

- **Type:** bug
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** UAK-040
- **Paths:** install.sh, kit/.uak/bin/doctor, kit/.uak/bin/start, kit/.uak/tests/test_skills_windows_clone.py
- **Acceptance:**
  - a teammate who clones on Windows (Git for Windows has `core.symlinks=false` by default) a repo installed on macOS or Linux gets working skills in Codex, Cursor and Gemini. Today `.agents/skills` and `.cursor/skills` are committed as symlinks (mode 120000), so that clone checks them out as one-line text files and the skills disappear
  - the reverse also works: a repo installed on Windows (where the installer copies the folder) does not leave stale copies for Mac and Linux teammates after `--update`
  - `doctor` flags `.agents/skills` or `.cursor/skills` when it is a file or a stale copy, with the exact fix; `doctor --fix` (or `uak start`) repairs it
  - `--harness gemini` without codex still gets the skills (Gemini reads `.agents/skills`; today only codex installs it)
  - why (DevDay and deus-ex-machina, both v6.0.0): both repos commit those links as symlinks, and DevDay had a Codex teammate on Windows whose black box line only said "PowerShell"
- **Tests:** windows_clone_without_symlinks_has_skills, doctor_flags_a_symlink_checked_out_as_a_file, gemini_only_install_gets_skills, update_refreshes_copied_skills
- **Verify:** `python3 kit/.uak/tests/test_skills_windows_clone.py`
- **Next step:** the `.agents/skills .cursor/skills` loop in install.sh

## UAK-042 · Subagent model IDs checked against the harnesses' current docs

- **Type:** chore
- **Priority:** P2
- **Estimate:** 45 min
- **Depends on:** UAK-040
- **Paths:** scripts/gen_harness.py, kit/.codex/agents/, kit/.cursor/agents/, kit/.gemini/agents/, kit/.uak/docs/ORCHESTRATION.md
- **Acceptance:**
  - the TIERS table (codex gpt-6-luna / gpt-6.1-sol / gpt-6-astra, cursor composer-2.5, gemini 3 preview IDs; last verified 2026-10-09) is checked against the official model pages of OpenAI, Cursor and Google, and every ID is one the harness accepts today; the date and sources in the docstring are updated; regenerated files pass `gen_harness.py --check`
  - why: the Gemini 3.1 and 3.5 IDs exist now, while the kit still pins the 3.0 previews
- **Verify:** `python3 scripts/gen_harness.py --check`
- **Next step:** the TIERS table in scripts/gen_harness.py
