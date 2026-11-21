## UAK-045 · An unapproved task matched by one file is not recorded as integrated without a human

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/bin/lib/done.sh, kit/.uak/tests/test_integrate_outside.py
- **Acceptance:**
  - `uak integrate ID` on the outside path, when the task has no approval (`Approval: none`) and its own commits change exactly one file, is refused for an agent with "only one file matched main and nobody approved it: a human records it (UAK_HUMAN=NAME uak integrate ID)"; a human may record it; two or more matching files, or any approval, behave as in v6.1.0
  - why (v6.1.0 review of UAK-033): a one-file task whose content equals main by coincidence would be credited as integrated
- **Tests:** single_file_unapproved_match_needs_a_human, single_file_match_with_approval_is_recorded
- **Verify:** `python3 kit/.uak/tests/test_integrate_outside.py`
- **Next step:** integrated_outside_check in kit/.uak/bin/lib/review-merge.sh

## UAK-046 · doctor compares skill copies without `diff --strip-trailing-cr`

- **Type:** bug
- **Priority:** P1
- **Estimate:** 45 min
- **Depends on:** None
- **Paths:** kit/.uak/bin/doctor, kit/.uak/tests/test_doctor_skills_compare.py
- **Acceptance:**
  - the stale-copy check of `.agents/skills` against `.claude/skills` uses only POSIX tools (e.g. `tr -d '\r' | cksum` per file, or one awk pass), so it gives the same answer on macOS before 13 (BSD diff without `--strip-trailing-cr`), Linux and Git Bash; CRLF-only differences are not stale
  - why (v6.1.0 review of UAK-041): on an older Mac every doctor run would call the skills stale
- **Tests:** crlf_only_difference_is_not_stale, real_difference_is_stale, works_without_diff_strip_flag
- **Verify:** `python3 kit/.uak/tests/test_doctor_skills_compare.py`
- **Next step:** the `diff -r -q --strip-trailing-cr` call in kit/.uak/bin/doctor

## UAK-047 · install keeps a team's edited copy of a kit skill in .cursor/skills

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/tests/test_cursor_skills_keep.py
- **Acceptance:**
  - install/--update removes a skill folder from `.cursor/skills` only when its files equal a version the kit shipped (known-files.txt hashes, as the rest of --update decides); an edited copy stays, and install prints "kept .cursor/skills/NAME: edited by the team; Cursor also reads .agents/skills"
  - why (v6.1.0 review of UAK-041): an edited kit skill in .cursor/skills was deleted because only its name was compared
- **Tests:** unedited_kit_skill_copy_is_removed, edited_kit_skill_copy_is_kept_and_named
- **Verify:** `python3 kit/.uak/tests/test_cursor_skills_keep.py`
- **Next step:** the .cursor/skills cleanup in install.sh

## UAK-048 · Cursor model IDs from Cursor's official pages

- **Type:** chore
- **Priority:** P2
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** scripts/gen_harness.py, kit/.cursor/agents/, kit/.uak/docs/ORCHESTRATION.md
- **Acceptance:**
  - the Cursor strong and fast IDs (`claude-opus-5-5[effort=high]`, `composer-2.5`) are checked against cursor.com/docs/models and cursor.com/docs/subagents; each is replaced only by an ID those pages show; the standard (not fast) variant is chosen where the syntax allows (`composer-2.5[]` if that is the documented way); sources and date in the docstring; `gen_harness.py --check` green
  - why (v6.1.0 review of UAK-042): neither ID appears verbatim in Cursor's docs
- **Verify:** `python3 scripts/gen_harness.py --check`
- **Next step:** the cursor column of TIERS in scripts/gen_harness.py

## UAK-049 · A refused `wt new` leaves no unused identity

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/wt, kit/.uak/tests/test_wt_refused_identity.py
- **Acceptance:**
  - when the claim of `wt new ID` is refused (overlap, dependency, freeze, owners), no new identity is registered on claims and no branch or worktree is left; a retry after the blocker clears picks the same free identity
  - why (v6.1.0 session): refused claims created joahanmorales-6, -7, -9 and -11, which never held a task
- **Tests:** refused_claim_registers_no_identity, retry_reuses_the_free_identity
- **Verify:** `python3 kit/.uak/tests/test_wt_refused_identity.py`
- **Next step:** the identity registration before the claim in kit/.uak/bin/wt

## UAK-050 · `plan --amend` checks overlaps the way claims do

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/plan.sh, kit/.uak/tests/test_plan_amend_overlap.py
- **Acceptance:**
  - amending a task that holds no reservation (AVAILABLE) never fails on overlap: it prints "UAK-NNN's new Paths overlap UAK-MMM (CLAIMED/REVIEW): its claim will wait for it" and publishes; the claim gate still refuses the overlapping claim later
  - amending several tasks in one file checks each task against the others' NEW Paths (an amend that drops a file from one task frees it for another in the same file)
  - a CLAIMED or REVIEW task whose new Paths overlap another live claim is still refused, as today
  - why (v6.1.0 session): the human had to run four amends in a fixed order; UAK-038 (AVAILABLE) was refused twice for tasks only waiting for review
- **Tests:** available_task_amend_overlap_warns_and_publishes, one_file_amend_uses_the_new_paths_of_the_others, claimed_task_amend_overlap_is_still_refused
- **Verify:** `python3 kit/.uak/tests/test_plan_amend_overlap.py`
- **Next step:** the overlap check of plan_amend_mutate in kit/.uak/bin/lib/plan.sh

## UAK-051 · `uak lint` warns when a task's own words point outside its Paths

- **Type:** feature
- **Priority:** P2
- **Estimate:** 1.5 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/lint.sh, kit/.uak/tests/test_lint_paths_hint.py
- **Acceptance:**
  - for each backlog task, a file path or a function name in its `Next step:` or Acceptance that the code map places in a file outside its Paths gives `LINT WARNING: UAK-NNN mentions coord_next (kit/.uak/bin/uak-coordination), outside its Paths`; plan files get the same warning before publishing (`uak plan FILE` prints it, never fails on it)
  - no map yet → silent; at most 5 warnings per task
  - why (v6.1.0 session): 4 of 16 tasks needed a Paths amend because the function they changed lived in another file
- **Tests:** next_step_function_outside_paths_warns, mention_inside_paths_is_silent
- **Verify:** `python3 kit/.uak/tests/test_lint_paths_hint.py`
- **Next step:** a new lint_paths_hint next to lint_tests_named in kit/.uak/bin/lib/lint.sh

## UAK-052 · The merge gate can run only the affected tests, CI runs the rest

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** UAK-045
- **Paths:** kit/.uak/bin/smoke, kit/.uak/bin/lib/review-merge.sh, kit/.uak/docs/PROTOCOL.md, kit/.uak/tests/test_merge_affected.py
- **Acceptance:**
  - with `Merge-Smoke: affected` in PROJECT.md, `uak merge` runs kit_lint (or the project's smoke) + the task's Verify + the test files that name a changed file or were changed themselves, instead of the whole suite; default stays `full`; the merge record says which (`Smoke: affected 7 of 52 test files`)
  - with `affected`, a merge whose diff touches the engine's shared files (lib/core.sh, lib/tx.sh, uak-coordination) still runs the whole suite
  - after it merges, the human may set `Merge-Smoke: affected` in the kit repo's .uak/PROJECT.md (CI still runs every test on every push)
  - why (v6.1.0 session): each `uak merge` ran the full suite on the maintainer's machine, over 10 minutes per task
- **Tests:** affected_mode_runs_only_matching_tests, engine_core_change_runs_everything, default_is_full
- **Verify:** `python3 kit/.uak/tests/test_merge_affected.py`
- **Next step:** the smoke call in the merge gate of kit/.uak/bin/lib/review-merge.sh

## UAK-053 · One canonical-backlog builder, and status from any clone

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak-coordination, kit/.uak/bin/lib/backlog.sh, kit/.uak/tests/test_status_planned.py
- **Acceptance:**
  - coord_init calls backlog_canonical (lib/backlog.sh) instead of its own copy; claims_diff shows 0 differences
  - `uak status ID` for a task published with `uak plan` prints its Paths and Verify from a fresh clone at an older commit of main too (the reviewer saw "not in TASKS.md" from its clone four times); if it cannot, the message says which backlog it read and how to refresh
  - why (v6.1.0 review of UAK-034 and the reviewer's notes)
- **Tests:** status_from_an_old_clone_shows_a_planned_task
- **Verify:** `python3 kit/.uak/tests/test_status_planned.py`
- **Next step:** the builder in coord_init of kit/.uak/bin/uak-coordination
