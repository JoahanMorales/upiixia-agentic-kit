# Amended tasks (uak plan --amend)

Append-only; the last section of an ID replaces its section in the backlog. Why: Paths can grow before review.

## UAK-009 · The process counter counts ps, measures next for an idle agent too, and names traces uniquely (follow-up of UAK-001)

- **Type:** follow-up
- **Priority:** P1
- **Depends on:** UAK-001
- **Follow-up of:** UAK-001
- **Paths:** kit/.uak/tests/test_claims_perf.py, scripts/perf_claims.sh
- **Freeze-Allowed:** no
- **Acceptance:** the counter's shims include `ps` (next and status call it; they were 5 processes short), `next` is also counted for an agent with no claim (choosing a task, not resuming one), trace and stdin file names are unique per call (no time-based names: Windows Python before 3.13 ticks coarsely)
- **Tests:** the_counter_sees_ps, next_for_an_idle_agent_starts_at_most_40_processes
- **Verify:** `python3 kit/.uak/tests/test_claims_perf.py`
## UAK-006 · Proof of no change, and the targets turned on

- **Type:** integration
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-003, UAK-004, UAK-005, UAK-008, UAK-010
- **Paths:** scripts/claims_diff.py, kit/.uak/tests/test_claims_perf.py, kit/.uak/bin/lib/, kit/.uak/bin/uak, kit/.uak/bin/uak-coordination, docs/perf-windows.md
- **Acceptance:** the protocol suites run the old and the new engine side by side on the same fixtures: every command's stdout and the resulting claims tree are identical, the XFAIL set of test_claims_perf.py is empty: next ≤ 40, status ≤ 30, heartbeat ≤ 20 processes, docs/perf-windows.md has the before and after times from `scripts/perf_claims.sh` on Windows
- **Tests:** old_and_new_engines_print_the_same_and_write_the_same_tree
- **Verify:** `python3 scripts/claims_diff.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** reuse the guard differential of v5.9.2 (docs/perf-windows.md)

## UAK-003 · Reads without a subshell per field: status and next load the state in one pass

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-001, UAK-011
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/core.sh, kit/.uak/bin/lib/state.awk, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_claims_read.py, kit/.uak/tests/test_claims_perf.py
- **Acceptance:** measured first (UAK-001's counter): about half of the ~210 processes of `next` are subshells, one per `$(field …)` or `$(coord_config …)`; the git calls that a persistent repo would save are fewer than 10, `status`, `next` and `inbox --peek` read `tasks/`, `claims/` and the messages in one awk pass into variables; no `$(field …)` on the read path; the session key (a `ps` walk up to 8 levels) is computed once per session and cached, `next` and `status` start at least half the processes they start today (210 and 192), and print the same output on the protocol fixtures, a target met here leaves the XFAIL set of test_claims_perf.py in this task
- **Tests:** status_reads_the_state_in_one_pass, next_reads_the_state_in_one_pass, a_record_with_crlf_reads_like_lf, next_and_status_print_the_same_as_before
- **Verify:** `python3 kit/.uak/tests/test_claims_read.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** list every `$(field` and `$(coord_config` on the read path of lib/status.sh and uak-coordination (coord_next)

## UAK-002 · A persistent claims repo per clone

- **Type:** feature
- **Priority:** P1
- **Estimate:** 4 h
- **Depends on:** UAK-003
- **Paths:** kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_claims_repo.py
- **Acceptance:** `<git-common-dir>/uak-claims/` replaces `git init` per call: one `git fetch` refreshes it; its config is set once (it saves network round trips and about 10 git processes per call), a `mkdir` lock serializes the processes of one machine; a stale lock (dead PID, older than the lease) is taken over, a corrupt or locked repo (antivirus, OneDrive) falls back to today's temporary clone and says so once
- **Tests:** reuses_the_claims_repo_between_calls, serializes_two_processes_on_one_machine, falls_back_to_a_temp_clone_when_the_repo_is_corrupt
- **Verify:** `python3 kit/.uak/tests/test_claims_repo.py`
- **Next step:** fresh_state in kit/.uak/bin/lib/tx.sh
## UAK-006 · Proof of no change, and the targets turned on

- **Type:** integration
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-003, UAK-004, UAK-005, UAK-008, UAK-010, UAK-011, UAK-012
- **Paths:** scripts/claims_diff.py, kit/.uak/tests/test_claims_perf.py, kit/.uak/bin/lib/, kit/.uak/bin/uak, kit/.uak/bin/uak-coordination, docs/perf-windows.md
- **Acceptance:** the protocol suites run the old and the new engine side by side on the same fixtures: every command's stdout and the resulting claims tree are identical, the XFAIL set of test_claims_perf.py is empty: next ≤ 40, status ≤ 30, heartbeat ≤ 20 processes, docs/perf-windows.md has the before and after times from `scripts/perf_claims.sh` on Windows
- **Tests:** old_and_new_engines_print_the_same_and_write_the_same_tree
- **Verify:** `python3 scripts/claims_diff.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** reuse the guard differential of v5.9.2 (docs/perf-windows.md)

## UAK-006 · Proof of no change, and the targets turned on

- **Type:** integration
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-003, UAK-004, UAK-005, UAK-008, UAK-010, UAK-011, UAK-012, UAK-013, UAK-014
- **Paths:** scripts/claims_diff.py, kit/.uak/tests/test_claims_perf.py, kit/.uak/bin/lib/, kit/.uak/bin/uak, kit/.uak/bin/uak-coordination, docs/perf-windows.md
- **Acceptance:** the protocol suites run the old and the new engine side by side on the same fixtures: every command's stdout and the resulting claims tree are identical, the XFAIL set of test_claims_perf.py is empty: next ≤ 40, status ≤ 30, heartbeat ≤ 20 processes, docs/perf-windows.md has the before and after times from `scripts/perf_claims.sh` on Windows
- **Tests:** old_and_new_engines_print_the_same_and_write_the_same_tree
- **Verify:** `python3 scripts/claims_diff.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** reuse the guard differential of v5.9.2 (docs/perf-windows.md)
## UAK-013 · The merge redirect parses on bash 3.2

- **Type:** fix
- **Priority:** P0
- **Estimate:** 30 min
- **Depends on:** UAK-012
- **Paths:** kit/.uak/bin/uak, kit/.uak/tests/test_v511.py
- **Acceptance:** bash 3.2 (macOS) parses kit/.uak/bin/uak: no `case` with a bare `pattern)` inside a `$( … )` (CI 7b37537: "line 27: syntax error near unexpected token `;;'"), a static test finds a `case` whose `esac` falls outside the naive paren match of its `$(`: what bash 3.2 misparses, caught on Linux too
- **Tests:** the_dispatcher_parses_on_bash_3_2
- **Verify:** `python3 kit/.uak/tests/test_v511.py --case the_dispatcher_parses_on_bash_3_2 --case merge_runs_the_main_checkouts_engine_not_the_branchs`
- **Next step:** the redirect block at the top of kit/.uak/bin/uak

## UAK-014 · status and next print no carriage return from a CRLF checkout

- **Type:** fix
- **Priority:** P0
- **Estimate:** 30 min
- **Depends on:** UAK-003
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/core.sh, kit/.uak/bin/lib/state.awk, kit/.uak/bin/uak-coordination, kit/.uak/tests/test_claims_read.py, kit/.uak/tests/test_claims_perf.py
- **Acceptance:** a VERSION or smoke file checked out with CRLF (Git for Windows) prints `uak v5.11.0`, not `uak v5.11.0\r` (CI e5957e5: test_v52 audit_small_fixes, test_v55 claims_read_on_a_crlf_machine, test_claims_read golden), the golden test reads macOS's /private/var as /var (CI e5957e5: "Worktree: /private<base>/worktree-1")
- **Tests:** a_crlf_checkout_prints_no_carriage_return
- **Verify:** `python3 kit/.uak/tests/test_claims_read.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** the builtin reads of VERSION and smoke in lib/status.sh and uak-coordination

## UAK-013 · The merge redirect parses on bash 3.2

- **Type:** fix
- **Priority:** P0
- **Estimate:** 30 min
- **Depends on:** UAK-012
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/doctor, kit/.uak/tests/test_v511.py
- **Acceptance:** bash 3.2 (macOS) parses kit/.uak/bin/uak: no `case` with a bare `pattern)` inside a `$( … )` (CI 7b37537: "line 27: syntax error near unexpected token `;;'"), a static test reads every command substitution of the engine like bash 3.2 does (inside double quotes too, past heredocs and $'…') and finds a `case` it would cut short: caught on Linux too, doctor's Verify hint (`"$(case … *" uv "*) …)"`) uses `(pat)`: on macOS it printed the rest of the case as text (kit-r1)
- **Tests:** the_dispatcher_parses_on_bash_3_2
- **Verify:** `python3 kit/.uak/tests/test_v511.py --case the_dispatcher_parses_on_bash_3_2 --case merge_runs_the_main_checkouts_engine_not_the_branchs`
- **Next step:** the redirect block at the top of kit/.uak/bin/uak

## UAK-005 · Mutations on a reused worktree of the claims repo

- **Type:** feature
- **Priority:** P1
- **Estimate:** 4 h
- **Depends on:** ninguna
- **Paths:** kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_claims_write.py
- **Acceptance:** `checkout -f refs/uak/claims`, write, commit, push in the persistent repo; a rejected push retries on the new tip, each retry keeps today's semantics: a fresh clock, the secret check before the commit, the append-only lint on `HEAD^`
- **Tests:** a_rejected_push_retries_on_the_new_tip, every_retry_reads_a_fresh_clock, a_secret_is_refused_before_the_commit
- **Verify:** `python3 kit/.uak/tests/test_claims_write.py`
- **Next step:** to be cancelled: it builds on UAK-002 (the persistent claims repo), which was cancelled
## UAK-006 · Proof of no change, and the measured gains

- **Type:** integration
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-003, UAK-004, UAK-008, UAK-010, UAK-011, UAK-012, UAK-013, UAK-014
- **Paths:** scripts/claims_diff.py, kit/.uak/tests/test_claims_perf.py, kit/.uak/bin/lib/, kit/.uak/bin/uak, kit/.uak/bin/uak-coordination, docs/perf-windows.md
- **Acceptance:** the protocol suites run the old and the new engine side by side on the same fixtures: every command's stdout and the resulting claims tree are identical, test_claims_perf.py's XFAIL set keeps only the targets the redesign does not reach (UAK-002 and UAK-005, the persistent claims repo, were cancelled: about 5 processes per call for a lock shared between processes); a target that is met leaves the set, docs/perf-windows.md has the before and after process counts and times from `scripts/perf_claims.sh` on Windows, and says which targets were dropped and why
- **Tests:** old_and_new_engines_print_the_same_and_write_the_same_tree
- **Verify:** `python3 scripts/claims_diff.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** reuse the guard differential of v5.9.2 (docs/perf-windows.md)
## UAK-006 · Proof of no change, and the measured gains

- **Type:** integration
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-003, UAK-004, UAK-008, UAK-010, UAK-011, UAK-012, UAK-013, UAK-014, UAK-015, UAK-016
- **Paths:** scripts/claims_diff.py, kit/.uak/tests/test_claims_perf.py, kit/.uak/bin/lib/, kit/.uak/bin/uak, kit/.uak/bin/uak-coordination, docs/perf-windows.md
- **Acceptance:** the protocol suites run the old and the new engine side by side on the same fixtures: every command's stdout and the resulting claims tree are identical, test_claims_perf.py's XFAIL set keeps only the targets the redesign does not reach (UAK-002 and UAK-005, the persistent claims repo, were cancelled: about 5 processes per call for a lock shared between processes); a target that is met leaves the set, docs/perf-windows.md has the before and after process counts and times from `scripts/perf_claims.sh` on Windows, and says which targets were dropped and why
- **Tests:** old_and_new_engines_print_the_same_and_write_the_same_tree
- **Verify:** `python3 scripts/claims_diff.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** reuse the guard differential of v5.9.2 (docs/perf-windows.md)
## UAK-006 · Proof of no change, and the measured gains

- **Type:** integration
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-003, UAK-004, UAK-008, UAK-010, UAK-011, UAK-012, UAK-013, UAK-014, UAK-015, UAK-016, UAK-017
- **Paths:** scripts/claims_diff.py, kit/.uak/tests/test_claims_perf.py, kit/.uak/bin/lib/, kit/.uak/bin/uak, kit/.uak/bin/uak-coordination, docs/perf-windows.md
- **Acceptance:** the protocol suites run the old and the new engine side by side on the same fixtures: every command's stdout and the resulting claims tree are identical, test_claims_perf.py's XFAIL set keeps only the targets the redesign does not reach (UAK-002 and UAK-005, the persistent claims repo, were cancelled: about 5 processes per call for a lock shared between processes); a target that is met leaves the set, docs/perf-windows.md has the before and after process counts and times from `scripts/perf_claims.sh` on Windows, and says which targets were dropped and why
- **Tests:** old_and_new_engines_print_the_same_and_write_the_same_tree
- **Verify:** `python3 scripts/claims_diff.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** reuse the guard differential of v5.9.2 (docs/perf-windows.md)
## UAK-033 · A PR merged outside the gate can still be recorded, so claims match main

- **Type:** bug
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/done.sh, kit/.uak/bin/stats, kit/.uak/bin/lib/dash.py, kit/.uak/docs/PROTOCOL.md, kit/.uak/tests/test_integrate_outside.py
- **Acceptance:** `uak integrate ID` records INTEGRATED when main already contains the task's work, in each case seen: a squash merge, a PR merged after more commits than the approved SHA, a task branch that carried unrelated base merges, and identical content that landed on main by another commit. The check compares the task's own diff (merge-base..tip, base merges dropped) by patch-id or by final file content on main, never the whole tree hash, a task still AVAILABLE or CLAIMED whose `feat/<id>` PR is merged (gh, or the branch tip reachable from main) can be recorded by its owner or a human; the record says `Integrated-Outside: yes` and the approval it had (or `none`), and `uak stats`/`dash` count it apart from gated merges, its dependents become claimable at once; its file reservations are released, why (deus-ex-machina, OpenAI x Kavak hackathon, 1st place, 2026-11-09): 11 `integrate` refusals ("tree hash does not match", "changes no task file", "is AVAILABLE, not REVIEW") and 5 agent reports. At the end claims said 6 of 23 integrated, with 6 stuck in REVIEW and 3 expired claims, while the product had shipped and won
- **Tests:** squash_merged_pr_is_recorded, pr_merged_after_extra_commits_is_recorded, base_merges_in_the_task_branch_are_ignored, equivalent_content_on_main_is_recorded, merged_branch_of_an_available_task_unblocks_its_dependents, outside_merges_are_counted_apart
- **Verify:** `python3 kit/.uak/tests/test_integrate_outside.py`
- **Next step:** the tree-hash comparison of the integrate path in kit/.uak/bin/lib/review-merge.sh

## UAK-040 · The `/uak-*` phase commands exist natively in Codex, Cursor and Gemini CLI

- **Type:** bug
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.claude/commands/, kit/.uak/skills/, kit/.agents/skills/, kit/.gemini/commands/, kit/.cursor/rules/uak.mdc, README.md, install.sh, scripts/gen_harness.py, kit/AGENTS.md, kit/.uak/tests/test_harness_commands.py
- **Acceptance:** the 13 phase scripts (uak-setup, uak-plan, uak-ship, uak-review, uak-handoff, uak-demo, …) come from one source and reach every harness the team installed:, Claude Code: `/uak-X`, as today;, Codex: an Agent Skill under `.agents/skills/uak-X/SKILL.md`, invoked as `$uak-X` or from `/skills` (Codex deprecated custom prompts);, Cursor: `/uak-X`, as a skill or from `.cursor/commands/uak-X.md`;, Gemini CLI: `/uak-X`, as a skill from `.agents/skills` or from `.gemini/commands/uak-X.toml`, a skill made from a phase script is only run when asked (`disable-model-invocation: true` or the harness's equivalent), so no agent starts `/uak-demo` on its own; Claude Code shows no duplicate `/uak-X`, `gen_harness.py --check` fails when a generated copy is stale (CI already runs it); the AGENTS.md line "Codex, Cursor, Gemini: `/uak-X` means follow `.claude/commands/uak-X.md`" changes to the native call, why (user's teammate, 2026-11-10): in Codex and Cursor the kit's commands "were not up to date". Codex and Cursor had no `/uak-*` at all, and Codex no longer reads custom prompts
- **Tests:** every_phase_command_reaches_every_harness, phase_skills_are_not_model_invoked, generated_commands_match_their_source
- **Verify:** `python3 kit/.uak/tests/test_harness_commands.py`
- **Next step:** the command → skill writer in scripts/gen_harness.py

## UAK-037 · A gitleaks finding has its own way out

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/secret-scan, kit/.uak/bin/lib/security.sh, kit/.uak/bin/uak, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_gitleaks_exception.py
- **Acceptance:** when the finding comes from gitleaks (SECRET_EXTERNAL), the message points to its fingerprint and to `uak secret-exception ID --fingerprint FP --reason TEXT`, which secret-scan honors through a `.gitleaksignore` entry; the kit's own rules keep `--path --rule`. The scan stays on, why (deus-ex-machina): smoke flagged fixture history through gitleaks and suggested secret-exception, which refuses rules that are not the kit's
- **Tests:** gitleaks_finding_names_its_fingerprint, fingerprint_exception_clears_only_that_finding
- **Verify:** `python3 kit/.uak/tests/test_gitleaks_exception.py`
- **Next step:** the SECRET_EXTERNAL branch of kit/.uak/bin/secret-scan

## UAK-038 · Registered reviewers get the review work first

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/wait.sh, kit/.uak/bin/uak-coordination, kit/.uak/bin/uak, kit/.uak/tests/test_reviewer_next.py
- **Acceptance:** for an identity registered as reviewer (or with no live claim and reviews pending), `uak next` offers every REVIEW task it may review before any coding task; `uak wait --for message` also wakes when a task enters REVIEW that it may review, `uak status ID --summary` works like `status --task ID --summary`, why (DevDay): a review-only Codex agent missed a REVIEW task because next offered coding work and wait did not wake it; Codex hit "--summary needs --task ID" 3 times in deus
- **Tests:** reviewer_next_offers_review_first, wait_wakes_on_new_review_work, status_id_summary_works
- **Verify:** `python3 kit/.uak/tests/test_reviewer_next.py`
- **Next step:** the candidate order of coord_next in kit/.uak/bin/uak-coordination

## UAK-047 · install keeps a team's edited copy of a kit skill in .cursor/skills

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/tests/test_cursor_skills_keep.py, kit/.uak/tests/test_skills_windows_clone.py
- **Acceptance:** install/--update removes a skill folder from `.cursor/skills` only when its files equal a version the kit shipped (known-files.txt hashes, as the rest of --update decides); an edited copy stays, and install prints "kept .cursor/skills/NAME: edited by the team; Cursor also reads .agents/skills", why (v6.1.0 review of UAK-041): an edited kit skill in .cursor/skills was deleted because only its name was compared
- **Tests:** unedited_kit_skill_copy_is_removed, edited_kit_skill_copy_is_kept_and_named
- **Verify:** `python3 kit/.uak/tests/test_cursor_skills_keep.py`
- **Next step:** the .cursor/skills cleanup in install.sh

## UAK-050 · `plan --amend` checks overlaps the way claims do

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/plan.sh, kit/.uak/tests/test_plan_amend_overlap.py, kit/.uak/tests/test_plan_owners.py
- **Acceptance:** amending a task that holds no reservation (AVAILABLE) never fails on overlap: it prints "UAK-NNN's new Paths overlap UAK-MMM (CLAIMED/REVIEW): its claim will wait for it" and publishes; the claim gate still refuses the overlapping claim later, amending several tasks in one file checks each task against the others' NEW Paths (an amend that drops a file from one task frees it for another in the same file), a CLAIMED or REVIEW task whose new Paths overlap another live claim is still refused, as today, why (v6.1.0 session): the human had to run four amends in a fixed order; UAK-038 (AVAILABLE) was refused twice for tasks only waiting for review
- **Tests:** available_task_amend_overlap_warns_and_publishes, one_file_amend_uses_the_new_paths_of_the_others, claimed_task_amend_overlap_is_still_refused
- **Verify:** `python3 kit/.uak/tests/test_plan_amend_overlap.py`
- **Next step:** the overlap check of plan_amend_mutate in kit/.uak/bin/lib/plan.sh

## UAK-078 · Colors combine well: palettes built with harmony rules from the brand, picked by the human before building, measured on the page

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3.5 h
- **Depends on:** UAK-077
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_color.py, kit/.uak/bin/lib/design_taste.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_color.py
- **Acceptance:** palettes are built from the project's brand colors with harmony rules, not as a list of hex: one dominant hue; neutrals (ground, ink, borders) tinted toward the dominant hue instead of pure grey/black/white; at most 2 saturated hues in one view; every other brand color used only as a small accent or desaturated; lightness and saturation adjusted so adjacent saturated colors don't vibrate (no complementary pair at equal lightness side by side); never all brand colors at full saturation together, each palette has roles and area shares (ground, surface, ink, primary, accent; e.g. 60/30/10) with the exact hex per role, and passes contrast (ink on ground ≥ 7:1, buttons and body text ≥ 4.5:1) before any page is built, `uak design palettes [--n 6]` makes a cheap palette round first (no agents, no tokens): N harmonious palettes from the brand, shown in the pick page as swatch strips and as a tiny mock (ground, a headline, a button, a chart line); the human picks 1–2 in seconds; the landing round's variants use the picked palettes (still split light/dark per UAK-072), the capture measures color use at the 1920 fold (saturated share, dark share, dominant colors, how much each palette role covers, hue clashes found) into metrics.json; the pick page shows the measured strip next to the planned one, and a variant that drifted from its palette is flagged, the taste profile learns palette features (dominant hue family, number of saturated hues, neutral temperature, saturation share) from the picks of both rounds, and the kit prior (UAK-075) only takes palette rules that held across projects, Why (2026-11-12, the human: "the taste profile uses colors very badly … it doesn't combine them correctly and it isn't pretty"): measured at the fold, AXIA R3 pages were 1–3 % saturated, an almost monochrome navy; colonIA v4 put a washed pink on cream; the gene only said "ink + one accent" with no palette, roles or harmony, and the profile learned labels, not combinations
- **Tests:** dominant_hue_and_tinted_neutrals, at_most_two_saturated_hues, no_vibrating_pairs, contrast_checked_before_build, palette_round_needs_no_agents, variants_use_picked_palette, capture_flags_palette_drift, taste_learns_palette_features
- **Verify:** `python3 kit/.uak/tests/test_design_color.py`
- **Next step:** a new kit/.uak/bin/lib/design_color.py (OKLCH-like lightness/chroma math in the stdlib, harmony rules, contrast, measuring a PNG), then `uak design palettes`
## UAK-114 · An unapproved task recorded INTEGRATED says so, and in marathon it needs a human

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/bin/stats, kit/.uak/tests/test_integrate_unreviewed.py
- **Acceptance:** sprint (and any mode that is not marathon): `integrate` of a CLAIMED, BLOCKED or AVAILABLE task whose content is on main, with no valid approval, works for an agent as today (the board must tell the truth during an event), and its record keeps `Integrated-Outside: yes` and adds `Unreviewed: yes`; the output says the code reached main without a review, marathon: the same integrate needs a human (`UAK_HUMAN=NAME … --reason TEXT`); an agent gets the refusal used from REVIEW, with the line the human runs; the record adds `Unreviewed: yes` and the reason goes to DECISIONS.md, with a valid approval of that SHA by another seen identity, an agent integrates in both modes and no `Unreviewed` field is written (UAK-092 behaviour kept), `uak stats` keeps its `outside the gate: N` line and adds how many of them were unreviewed, the existing tests of test_integrate_outside.py stay untouched and pass (they run in sprint), Why (audit of v6.5.0, docs/audit-2026-11.md #7; decided by the human on 2026-11-21): integrate required a human only from REVIEW, so an owner could unlock dependents on unreviewed code; an agent integrating outside the gate is by design in sprint (deus-ex-machina: PRs merged on GitHub that the claims never learned about), so the rule depends on the mode and the record always says it
- **Tests:** sprint_agent_integrates_and_record_says_unreviewed, marathon_agent_is_refused, marathon_human_records_it_with_a_reason, approved_sha_integrates_in_both_modes, stats_counts_unreviewed
- **Verify:** `python3 kit/.uak/tests/test_integrate_unreviewed.py`
- **Next step:** integrate_mutate at kit/.uak/bin/lib/done.sh:203-241; the `outside the gate` line in kit/.uak/bin/stats
## UAK-127 · An install without the kit's own tests, with skills on demand

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/bin/doctor, kit/.uak/bin/smoke, kit/.uak/bin/uak-coordination, kit/.uak/bin/skill, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/settings/known-files.txt, scripts/kit_hashes.py, kit/.uak/tests/test_install_light.py
- **Acceptance:** `install.sh` no longer copies `kit/.uak/tests/` into a project (112 files, 1.5 MB): a project's `smoke` runs its own checks and the product smoke, and says in one line that the kit's protocol suite runs in the kit's repository. `--with-tests` installs them as today; `--update` removes the kit's test files it recognizes by hash (`known-files.txt`) and keeps any file a team edited or added, the skill library (`.uak/skills/`, 114 files) is not copied whole: the install places only the skills the mode, stack and `--skills` ask for, as today under `.claude/skills` and `.agents/skills`, and `uak skill add NAME` copies one more from the kit's checkout or, with no checkout, from the pinned release (git only, hash-checked like the external skills), a default marathon install for Claude Code (`--harness claude`, external skills on, as a user gets it) is under 260 files (was 534, 9.3 MB); the test counts it with the external skills fetched from a local fixture, prints the count and the bytes, and fails over the bound. Decided by the human on 2026-11-21: the first bound was 200, and the 63 files over it are the pinned external landing skill, which an existing test requires the install to fetch; placing it on demand is a task of its own, `doctor` does not ask for the test directory, and every command that reads `.uak/tests` or `.uak/skills` works when they are absent, Why (audit of v6.5.0, docs/audit-2026-11.md §1): an install put 535 files and 9.3 MB in a project, of which 108 were the kit's own tests and 114 the skill library; heavy in files, not in context
- **Tests:** install_has_no_kit_tests, with_tests_installs_them, update_removes_only_known_test_files, skill_add_copies_one, marathon_install_under_260_files
- **Verify:** `python3 kit/.uak/tests/test_install_light.py`
- **Next step:** the copy loop at install.sh:107 (`for part in bin docs modes templates tests settings stacks skills`) and the skill placement at install.sh:162-173
## UAK-129 · The reviewer runs Verify and the tests the diff touches; the whole suite runs once, at the merge gate

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/smoke, kit/.uak/bin/lib/tests.sh, kit/.claude/agents/uak-reviewer.md, kit/.uak/modes/sprint.md, kit/.uak/modes/marathon.md, kit/.uak/tests/test_smoke_affected.py
- **Acceptance:** `smoke --affected [BASE]` runs the lint, the secret scan, the task's Verify and only the test files the diff against BASE touches or names (a test file changed; a test file whose name or imports match a changed engine file; every file when the diff touches `lib/core.sh`, `lib/tx.sh` or the test helpers). It prints which files it chose and why, and how many it left for the gate, `smoke --affected` is documented in its own usage line and in both mode files (docs/CLI.md is held by UAK-131 and gets its line in a follow-up), the reviewer's instructions and both mode files say: Verify plus `smoke --affected`, and the note of an approval says which was run; the author does the same before `done`, the merge gate keeps running the whole suite on the merged result; nothing an agent sets (an environment variable, a flag) makes the gate run fewer tests, on the kit's own repository the three runs per task become one whole run and two partial ones; the test measures a partial run on a one-file diff under a quarter of the files, Why (audit §1): the suite took 8–10 min and ran three times per task (author, reviewer, gate), the largest cost in time; 152 review rounds in 105 tasks each paid a whole run
- **Tests:** affected_runs_changed_test_files, engine_change_selects_its_tests, core_change_runs_everything, gate_ignores_the_shortcut, prints_what_it_left
- **Verify:** `python3 kit/.uak/tests/test_smoke_affected.py`
- **Next step:** the `UAK_SMOKE_TESTS` selection at kit/.uak/bin/smoke:41-56 and step 26 of kit/.claude/agents/uak-reviewer.md
## UAK-158 · One design system: the wizard is drawn with the dashboard's tokens, and `design-lint` reads HTML

- **Type:** feature
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-156
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/fonts/, kit/.uak/bin/design-lint, kit/.uak/media/, docs/DASHBOARD.md, docs/design/, scripts/kit_lint.py, kit/.uak/tests/test_setup_design.py
- **Acceptance:** the design system is `docs/design/DIRECTION.md` (chosen by the human on 2026-11-23) and its mock `docs/design/direction/mock.html`: scale, type, radii, the pills, the line of nodes, the window, the single bordered list and the three-figure footer are built once and used by both pages, nine palettes, each in light and dark, as in the mock: Clásico (the exact colours of the dashboard of v6.8), Lavanda, Cielo, Menta, Salvia, Durazno, Rosa, Arena, Grafito. One control, "Apariencia", in both pages sets theme and palette; the choice is the viewer's, kept in the browser, and changes no tracked file. The default is Lavanda in a checkout that never had a dashboard, and Clásico where a dashboard of v6.8 or earlier was already generated (its output directory exists), so nobody's panel changes colour by itself. In Menta and Salvia the green of "integrated" stays distinguishable from the accent (a test measures the difference), type is Inter for text and JetBrains Mono for IDs, commands, pills and counters, as in the mock: shipped in the kit as subset `woff2` files with their licence (SIL OFL), written beside the dashboard's page and served by the wizard, with the system stack as fallback. Neither page makes a network request, with or without the files; the dashboard's HTML file is not heavier than today, `setup.html` and `dash.html` declare the same custom properties with the same values in light and dark (page, surface, raised, ink, ink-2, muted, line, accent, accent-ink, critical, shadow, mono, radii): the set is the direction the human chose from the three shown to them, recorded in `docs/design/DIRECTION.md` on main before this task starts (palette, type, radii, spacing, in light and dark); the wizard's own palette, its 20 px radius and its three hard-coded shadows go. A test compares the two `:root` blocks and fails on any difference, outside `:root` no colour literal remains in either file; the wizard uses at most 6 font sizes and one spacing scale (4, 8, 12, 16, 24, 32, 48), the radii and the body size of the chosen direction, one shadow token, `design-lint` applies its rules to `.html` (inline `<style>` and `style=`), not only the two scale checks: colour literals outside `:root`, coloured side stripes, glass, glow, emoji and glyphs used as icons (`✓ ✗ ! •` included), more than 6 font sizes, more than one primary button visible in a view. Both pages pass with `--strict`, with no finding suppressed, status marks are inline SVG icons with a text label, never a glyph; a disabled control keeps 4.5:1 for its label (2.9:1 today); every text/background pair of the tokens is at least 4.5:1 in both themes, computed by the test, the tutorial's poster and its frames use the kit's palette (no purple glow), screenshots at 1280 and 390, light and dark, of every screen are in `.uak-shots/UAK-158/` with the design critic's `VERDICT: SHIP` for the task's commit, Why (2026-11-22): the two pages share no colour value; the wizard frames the blue dashboard inside a green page; `design-lint` printed PASS for both because it does not read HTML (a copy renamed `.js` gave 40 findings)
- **Tests:** wizard_and_dashboard_share_tokens, no_colour_literal_outside_root, six_font_sizes_one_spacing_scale, design_lint_reads_html, every_pair_has_contrast, disabled_label_is_readable
- **Verify:** `python3 kit/.uak/tests/test_setup_design.py && bash kit/.uak/bin/design-lint --strict kit/.uak/bin/lib/setup.html kit/.uak/bin/lib/dash.html`
- **Next step:** `:root` in setup.html (lines 13-28 and 657-702 of the contributed file) against dash.html lines 12-47; existing tests that assert the old colours or classes need `uak allow UAK-158 --tests` from the human

## UAK-159 · The wizard's flow: ten screens, one job each, and it covers what the kit does today

- **Type:** feature
- **Priority:** P0
- **Estimate:** 12 h
- **Depends on:** UAK-158
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, docs/DASHBOARD.md, kit/.uak/tests/test_setup_forms.py, kit/.uak/tests/test_setup_guide.py, kit/.uak/tests/test_setup_resume.py, kit/.uak/tests/test_setup_first_run.py
- **Acceptance:** every screen follows rule 11 of `docs/design/DIRECTION.md` and the wizard of its mock: the line of nodes as progress at the top with "continue in the terminal" beside it; the choices at the left; at the right a window that shows what will be written or changed by this screen and updates as the person chooses (files and counts on Install, the lines of PROJECT.md on the rules, the people on People); "Exit" and one primary button at the bottom, the flow approved by the human (2026-11-23), one screen per job, each with one primary button: (1) Your project: what was detected (folder, new or existing repository, a hook manager such as husky or lefthook, CI, the project's own tests, the stack) and the mode proposed with its reason; the tools are chosen here. (2) Install: what will be written, how many files, and how the kit's hooks live beside the team's. (3) Unblock: only when something fails, one problem at a time with its fix. (4) How your team will work: the project's rules in plain words with the mode's defaults (`Test-First`, review with or without GitHub, `Review-Independence`, `Merge-Engine`, generated files, the token budget), details under "Advanced"; it writes nothing the human did not confirm. (5) People: the human's identity, reviewers, roles. (6) Schedule: only in Hackathon mode. (7) Publish the kit. (8) Idea and plan: the idea, the design direction when the project has screens (the creativity index and the design lock), the plan, the approval. (9) Start: the command for each agent; the screen says when the first agent has claimed a task. (10) Dashboard: from here, deployment (`uak deploy`, the smoke that boots the app, `Live-URL`), external skills (`uak skill add`) and "Close the wizard", which ends the server, a project that already has the kit opens on the screen it needs; an older kit opens "Update", a path of its own, never an alarm heading over another screen, there is no welcome screen, no slogan, no eyebrow and no benefit pairs; the first screen says what will happen in this project in two sentences. The video is a link. The folder is not asked inside a repository (it is shown with "Change"). A first install takes at most 4 clicks, diagnostics (`Blackbox`) are never pre-checked: the screen says what is published and where, and that a public repository makes it public; the human chooses, no screen is taller than two viewports at 1280×800 or three at 390×844 with real content ("Get ready" was 4518 px and 6457 px), an instruction appears once: one command, one copy box, the folder already in it; raw output of `uak start` is under "Technical details", never a heading. A heading is a sentence that starts with a capital and says what to do, an error is next to the control that caused it and above the button, in view after the click at both widths, names what to do, and is the message of that step, the step is in the URL: reload stays on it, the browser's Back and Forward move between steps, reopening a project resumes where it was, at 390 px the content starts within 160 px of the top, every target is at least 44×44 px, nothing scrolls sideways; the journey bar and the step rail are one component, a running action shows what it is doing and for how long, next to its button; a page whose server ended says so when it comes back into view, with the command that reopens it, screenshots at 1280 and 390, light and dark, Spanish and English, of every screen and of one error and one loading state are in `.uak-shots/UAK-159/` with the design critic's `VERDICT: SHIP` for the task's commit
- **Tests:** flow_has_the_ten_screens, existing_repository_is_detected, rules_screen_writes_only_what_was_confirmed, schedule_only_in_hackathon, diagnostics_are_not_prechecked, old_kit_opens_update, close_ends_the_server, no_screen_taller_than_two_viewports, instruction_appears_once, first_install_in_four_clicks, error_is_next_to_its_control, step_survives_reload_and_back, mobile_content_starts_within_160px, targets_are_44px
- **Verify:** `python3 kit/.uak/tests/test_setup_forms.py && python3 kit/.uak/tests/test_setup_guide.py && python3 kit/.uak/tests/test_setup_resume.py && python3 kit/.uak/tests/test_setup_first_run.py`
- **Next step:** the "Get ready" markup in setup.html (about lines 1700-2040 of the contributed file) and the hero at 1434-1460; the detection of hooks is `doctor`'s (UAK-135, UAK-146), reuse it; changed assertions need `uak allow UAK-159 --tests` from the human

## UAK-162 · The dashboard is redrawn in the chosen direction

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-158
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, docs/DASHBOARD.md, docs/media/, README.md, kit/.uak/tests/test_dashboard_truth.py, kit/.uak/tests/test_dashboard_profiles.py
- **Acceptance:** built to `docs/design/DIRECTION.md` (rules 6 to 10) and its mock: the summary in the mock's order (what needs the person; tasks as a list or as columns; activity in its window; at the side progress, agents, integrations per period, tokens) with its maximums (8 task rows of what is moving, 4 agents, progress as blocks up to 24 tasks and one bar beyond), so a plan of 60 tasks adds less than 50 px to the page; integrations per period adapt to the time elapsed (6 to 8 bars) and can be fixed at 1 h, 2 h, 4 h or a day, the board has four stages (to do, in progress, in review, integrated); blocked and overdue are conditions on the card; each header says the one thing that matters; the page scrolls, columns show 8 and a "more"; a search filters by task or agent, a click on a task opens its detail with the structure of v6.8, restyled: header, time in each state, who took part with model and harness, every move in order with time, elapsed, who and note, then the acceptance criteria with their tests. It closes with the button, Escape or a click outside, and works with the keyboard, the tab's title says how many things need the person (`(2) project`), and nothing when none, the tabs the mock does not show (Agents, Messages, Black box, Memory, Tokens), the empty project and the finished project are designed in the same language and shown to the human as screenshots before the task is sent to review; the note of `uak done` says the human saw them, the dashboard is redesigned with the tokens of `docs/design/DIRECTION.md`: the same information as today (progress, agents online, reviews waiting with their sub-state, stalled, needs a human, board, agents, conversation, black box, memory, tokens), nothing dropped; the first thing read is what needs a person now, then progress, then the board, an empty project is not a grid of zeros: it says the one next step and its command; each number that is zero because nothing happened yet says so in words, it stays one file opened from `file://`, with no server, no port, no external request and no build step; the page is not heavier than today (84 KB) and its two timers start no process, both profiles (beginner, advanced), both themes and both languages are complete; every text/background pair is at least 4.5:1; every target is at least 44×44 px at 390; nothing scrolls sideways; it is usable with the keyboard alone, and motion stops under `prefers-reduced-motion`, `design-lint --strict` passes on it with no finding suppressed (main's file has 26 today: 19 colour literals, 5 rgba, 1 glass, 1 emoji), screenshots at 1280 and 390, light and dark, of an empty project, a project in progress (20 tasks, 3 agents, a review over its lease, a blocked task) and a finished one are in `.uak-shots/UAK-162/` with the design critic's `VERDICT: SHIP` for the task's commit; the README's and the docs' images of the dashboard are replaced
- **Tests:** dashboard_keeps_every_field, empty_project_says_the_next_step, no_server_no_request, page_is_not_heavier, both_profiles_and_languages_are_complete
- **Verify:** `python3 kit/.uak/tests/test_dashboard_truth.py && python3 kit/.uak/tests/test_dashboard_profiles.py && bash kit/.uak/bin/design-lint --strict kit/.uak/bin/lib/dash.html`
- **Next step:** kit/.uak/bin/lib/dash.html (tokens at the top, the hero and the four tiles, the tabs); the data comes from `dash.py`, whose fields the existing tests list; changed assertions need `uak allow UAK-162 --tests` from the human
## UAK-162 · The dashboard is redrawn in the chosen direction

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-158
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/bin/lib/dash.py, docs/DASHBOARD.md, docs/media/, README.md, kit/.uak/tests/test_dashboard_truth.py, kit/.uak/tests/test_dashboard_profiles.py
- **Acceptance:** each block of the summary is built as a component from the start: a name, a title, a column, a maximum of rows and one render function over the dashboard's data, kept in one registry, so that UAK-165 can let the viewer arrange them without a rewrite, built to `docs/design/DIRECTION.md` (rules 6 to 10) and its mock: the summary in the mock's order (what needs the person; tasks as a list or as columns; activity in its window; at the side progress, agents, integrations per period, tokens) with its maximums (8 task rows of what is moving, 4 agents, progress as blocks up to 24 tasks and one bar beyond), so a plan of 60 tasks adds less than 50 px to the page; integrations per period adapt to the time elapsed (6 to 8 bars) and can be fixed at 1 h, 2 h, 4 h or a day, the board has four stages (to do, in progress, in review, integrated); blocked and overdue are conditions on the card; each header says the one thing that matters; the page scrolls, columns show 8 and a "more"; a search filters by task or agent, a click on a task opens its detail with the structure of v6.8, restyled: header, time in each state, who took part with model and harness, every move in order with time, elapsed, who and note, then the acceptance criteria with their tests. It closes with the button, Escape or a click outside, and works with the keyboard, the tab's title says how many things need the person (`(2) project`), and nothing when none, the tabs the mock does not show (Agents, Messages, Black box, Memory, Tokens), the empty project and the finished project are designed in the same language and shown to the human as screenshots before the task is sent to review; the note of `uak done` says the human saw them, the dashboard is redesigned with the tokens of `docs/design/DIRECTION.md`: the same information as today (progress, agents online, reviews waiting with their sub-state, stalled, needs a human, board, agents, conversation, black box, memory, tokens), nothing dropped; the first thing read is what needs a person now, then progress, then the board, an empty project is not a grid of zeros: it says the one next step and its command; each number that is zero because nothing happened yet says so in words, it stays one file opened from `file://`, with no server, no port, no external request and no build step; the page is not heavier than today (84 KB) and its two timers start no process, both profiles (beginner, advanced), both themes and both languages are complete; every text/background pair is at least 4.5:1; every target is at least 44×44 px at 390; nothing scrolls sideways; it is usable with the keyboard alone, and motion stops under `prefers-reduced-motion`, `design-lint --strict` passes on it with no finding suppressed (main's file has 26 today: 19 colour literals, 5 rgba, 1 glass, 1 emoji), screenshots at 1280 and 390, light and dark, of an empty project, a project in progress (20 tasks, 3 agents, a review over its lease, a blocked task) and a finished one are in `.uak-shots/UAK-162/` with the design critic's `VERDICT: SHIP` for the task's commit; the README's and the docs' images of the dashboard are replaced
- **Tests:** dashboard_keeps_every_field, empty_project_says_the_next_step, no_server_no_request, page_is_not_heavier, both_profiles_and_languages_are_complete
- **Verify:** `python3 kit/.uak/tests/test_dashboard_truth.py && python3 kit/.uak/tests/test_dashboard_profiles.py && bash kit/.uak/bin/design-lint --strict kit/.uak/bin/lib/dash.html`
- **Next step:** kit/.uak/bin/lib/dash.html (tokens at the top, the hero and the four tiles, the tabs); the data comes from `dash.py`, whose fields the existing tests list; changed assertions need `uak allow UAK-162 --tests` from the human
