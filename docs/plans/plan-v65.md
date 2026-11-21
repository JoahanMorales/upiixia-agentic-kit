## UAK-087 · `review` records a valid verdict when the SHA's existing approval names an identity never seen or retired

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/tests/test_review_unseen_approval.py
- **Acceptance:**
  - with reviews/ID.md approving the current SHA by an identity that has no meta/agents file or is retired, `uak review ID --start` does not answer SKIP and `uak review ID --sha SHA --verdict approve` by a valid reviewer records the verdict; `uak merge` then accepts it
  - an approval by a seen, not retired identity keeps today's answers ("already approved by X on this SHA")
  - the replaced approval is named in the output ("replaces an approval by ghost, never seen on claims")
  - Why (private sprint on v6.4.0, 2026-11-17, agent note): review refused to record because an unknown identity had approved the SHA, and merge rejected that same approval as "never seen on claims or retired": the task could only go to the human. docs/blackbox/harvest-2026-11.md #3
- **Tests:** unseen_approval_does_not_skip_start, valid_reviewer_replaces_unseen_approval, seen_approval_still_skips, merge_accepts_the_replacement
- **Verify:** `python3 kit/.uak/tests/test_review_unseen_approval.py`
- **Next step:** the two "already approved by" branches (~lines 181 and 238) and the "never seen on claims or retired" gate (~line 286) of kit/.uak/bin/lib/review-merge.sh

## UAK-088 · `wt new ID --agent NAME` resumes a claim that already belongs to NAME

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/wt, kit/.uak/bin/lib/claim.sh, kit/.uak/tests/test_wt_resume_claim.py
- **Acceptance:**
  - after `uak handover ID --to NAME` (or a claim NAME made on another machine), `wt new ID --agent NAME` creates the worktree on the task's existing branch with its .uak-env, and says it resumed the claim; it does not answer "already has claims/ID.md"
  - a claim owned by another identity keeps the refusal, and names the owner
  - the branch is fetched from origin when it only exists there
  - Why (UpiixSol, 2026-11-13, two agent notes): "wt new refuses owner of a handed-over claim"; "wt new UPS-052 --agent david-5 refused… had to git worktree add by hand". docs/blackbox/harvest-2026-11.md #4
- **Tests:** resumes_own_claim_after_handover, refuses_claim_of_another_identity, fetches_the_remote_branch
- **Verify:** `python3 kit/.uak/tests/test_wt_resume_claim.py`
- **Next step:** the already-claimed check at kit/.uak/bin/lib/claim.sh:19 and the claim call in kit/.uak/bin/wt

## UAK-089 · The black box is published without harness hooks

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/bb, kit/.uak/tests/test_bb_flush_no_hooks.py
- **Acceptance:**
  - a `uak` command that ends with pending black box lines older than 10 minutes (and no flush in the last 10) starts `bb flush --quiet` in the background, detached, without delaying or changing the command's output or exit code
  - UAK_BLACKBOX=off starts nothing; a failed flush stays silent and keeps the pending lines
  - the hook's own flush keeps working and the two never run at once (the `flushed` stamp is taken first)
  - Why (the kit's own repo, 10 → 15 Nov 2026): 61 errors sat in .git/uak-blackbox.pending and none was published, because flush only starts from a harness hook and the kit is driven by subagents and plain shells. docs/blackbox/harvest-2026-11.md #2
- **Tests:** old_pending_is_flushed_by_a_plain_command, fresh_pending_waits, blackbox_off_starts_nothing, output_and_exit_code_unchanged
- **Verify:** `python3 kit/.uak/tests/test_bb_flush_no_hooks.py`
- **Next step:** the flush trigger in kit/.uak/bin/hook:637 (copy its condition) and the calls counter at kit/.uak/bin/uak:104

## UAK-090 · The weekly harvest finds the repos again, and an empty harvest fails

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** scripts/blackbox_harvest.py, .github/workflows/blackbox-harvest.yml, kit/.uak/tests/test_harvest_discovery.py
- **Acceptance:**
  - discovery calls `gh search code` with `--filename PROJECT.md` (text "Plan-Channel") and `--filename BLACKBOX.md`, and drops repos where neither claims:blackbox/ nor .uak/BLACKBOX.md has a kit line
  - no repo found exits 1 with the gh error when there is one, and the workflow step fails instead of ending green with no issue
  - the test stubs `gh` (a Python stub on PATH, no sh) and checks the arguments and the parsing
  - Why (2026-11-20): `gh search code "path:.uak filename:PROJECT.md Mode"` returns nothing; the weekly workflow has been green and has never opened an issue. By hand with --filename the search finds 14 repos. docs/blackbox/harvest-2026-11.md #1
- **Tests:** discovery_uses_filename_flag, repos_without_kit_lines_are_dropped, empty_discovery_exits_1
- **Verify:** `python3 kit/.uak/tests/test_harvest_discovery.py`
- **Next step:** `search()` and the `repos = …` line of scripts/blackbox_harvest.py

## UAK-091 · A guessed spelling gets the right one back: nearest command, `--approve`, a bare SHA

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-089
- **Paths:** kit/.uak/bin/uak, kit/.uak/tests/test_cli_spelling_hints.py
- **Acceptance:**
  - an unknown command names the nearest registered one when there is one ("Unknown command: decisions. Did you mean: decision"; `owners` → the OWNERS.md file; `agents` → `status --agents` or the right command)
  - `review ID --approve` / `--reject` answer with the exact line to run (`--sha SHA --verdict approve`); `review ID SHA`, `status ID SHA` and `merge ID NAME` name the flag the bare word needs
  - `done ID --pr BRANCH` answers with the PR's URL command (`bash .uak/bin/wt pr`) and says a branch name is not a URL; `log --task ID` says the ID goes first
  - exit codes and UAK_CODE stay as they are; only the text gains the hint
  - Why (harvest 2026-11): review with a bare SHA ×4, `--approve` ×2, merge with a name ×2, unknown commands decisions/owners/agents/kit-hashes, `done --pr <branch>` ×2, `log --task`. docs/blackbox/harvest-2026-11.md #5
- **Tests:** unknown_command_suggests_nearest, review_approve_flag_names_verdict, bare_sha_names_the_flag, done_branch_is_not_a_url
- **Verify:** `python3 kit/.uak/tests/test_cli_spelling_hints.py`
- **Next step:** kit/.uak/bin/uak:107 (unknown command) and the argument loop at kit/.uak/bin/uak:247-258

## UAK-092 · `integrate` records a task whose reviewed code is already on main

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-087
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/tests/test_integrate_on_main.py
- **Acceptance:**
  - when the approved SHA is an ancestor of main and the branch has commits after it, `integrate` records the task INTEGRATED at the approved SHA and names the leftover commits ("1 commit after the approved SHA is not on main: <sha> <subject>"), instead of refusing
  - a CANCELLED task whose PR merge is on main can be recorded by a human (`UAK_HUMAN=NAME uak integrate ID --reason TEXT`), and its dependents can then be claimed
  - code on main with no approval at all keeps today's refusal for agents (the human record stays the only way)
  - Why (UpiixSol, 11 → 18 Nov 2026): 15 refusals "Missing verifiable approval" and two agent notes: "a task merged on the forge before its claim was cancelled… its dependents now refuse to claim"; "UPS-031 is in main (PR #50) but stays AVAILABLE… integrate blocked by an unmerged review commit". docs/blackbox/harvest-2026-11.md #6
- **Tests:** approved_ancestor_with_leftover_commit_integrates, cancelled_with_merged_pr_recorded_by_human, dependents_claimable_after, unapproved_code_still_refused
- **Verify:** `python3 kit/.uak/tests/test_integrate_on_main.py`
- **Next step:** `integrate` in kit/.uak/bin/lib/review-merge.sh (~line 862, the refusal reasons)

## UAK-093 · A design critique survives commits that touch no UI, and `done` names the fallback when the critic agent is missing

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/skills/product-ui/SKILL.md, kit/.uak/tests/test_critic_stale_ui_only.py
- **Acceptance:**
  - critic.txt about commit A stays valid at commit B when `git diff A B` touches no UI path (the same paths that make `done` ask for shots); a UI change keeps today's refusal
  - the missing-critic and stale-critic messages name the fallback: any subagent given kit's design-critic prompt file, writing the same critic.txt
  - the product-ui skill documents the fallback in one paragraph
  - Why: UpiixSol (12 and 16 Nov 2026) "design-critic is in .claude/agents but the Agent tool of the session does not list it, so done cannot get a SHIP"; private sprint on v6.4.0, "critic.txt is about another commit" ×3 in one night. docs/blackbox/harvest-2026-11.md #7
- **Tests:** critique_valid_after_non_ui_commit, critique_stale_after_ui_commit, messages_name_the_fallback
- **Verify:** `python3 kit/.uak/tests/test_critic_stale_ui_only.py`
- **Next step:** the critic-stale check at kit/.uak/bin/lib/done.sh:56

## UAK-094 · The banner's version comes from VERSION, and the lint and the checklist know it

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** scripts/make_media.py, scripts/kit_lint.py, CONTRIBUTING.md, kit/.uak/tests/test_banner_version.py
- **Acceptance:**
  - make_media.py reads major.minor from kit/.uak/VERSION for the banner's eyebrow and writes it next to the PNG (docs/media/banner.version)
  - kit_lint fails when banner.version differs from VERSION's major.minor, naming the command that regenerates it
  - the release checklist in CONTRIBUTING.md lists the banner
  - Why (release v6.4.0, 2026-11-16): the banner still said v6.1 after three releases; the version was a literal and no check read it. docs/blackbox/harvest-2026-11.md #8
- **Tests:** banner_text_uses_version_file, lint_flags_a_stale_banner
- **Verify:** `python3 kit/.uak/tests/test_banner_version.py`
- **Next step:** the eyebrow literal at scripts/make_media.py:103
