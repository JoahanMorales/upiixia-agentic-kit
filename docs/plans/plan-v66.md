## UAK-110 · One identity, one live task also holds for heartbeat, log, checkpoint and handoff

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/claim.sh, kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_one_live_renew.py
- **Acceptance:**
  - an identity whose claim on X expired and that then claimed Y cannot renew X: `heartbeat`, `log`, `checkpoint` and `handoff` on X refuse with UAK_CODE one-live-task and say which task is live and how to give X up (release) or take it back (release Y first)
  - a claim that is not expired, or an identity with no other live claim, renews as today; UAK_MULTI_CLAIM=1 keeps its meaning
  - a claim file whose Lease-Until is empty or not a number counts as live for the one-live-task check (it cannot be used to take a second task), and `tick` reports it
  - Why (audit of v6.5.0, docs/audit-2026-11.md #1 and #10; first found by a TLA+ model of claims in a fork: trace claim t1, lease expires, claim t2, heartbeat t1): heartbeat_mutate checks only the owner and refresh_lease rewrites Lease-Until
- **Tests:** expired_claim_cannot_be_renewed_with_another_live, log_and_checkpoint_refuse_too, unexpired_claim_renews, damaged_lease_counts_as_live
- **Verify:** `python3 kit/.uak/tests/test_one_live_renew.py`
- **Next step:** heartbeat_mutate at kit/.uak/bin/lib/claim.sh:250, check_collisions at claim.sh:44, refresh_lease at kit/.uak/bin/lib/tx.sh:117

## UAK-111 · The guard treats a substitution inside quotes as code, sees `gh … merge` with flags, and refuses a plain push to claims

- **Type:** bug
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/guard, kit/.uak/tests/test_guard_substitution.py
- **Acceptance:**
  - a double-quoted span that contains a command substitution (`$(` or a backtick) is not dropped as prose: the rules see its contents, so a blocked command inside a commit message or an echo is blocked
  - the merge rule matches `gh` with flags between the words (`gh -R o/r pr merge`, `gh pr --repo o/r merge`)
  - a `git push` whose destination is the claims branch (`claims`, `refs/heads/claims`, `HEAD:claims`) is blocked with the reason (claims is written only by uak commands); the engine's own pushes are not affected (they do not pass through the hook)
  - a `git` or `gh` segment that pushes or merges and contains a variable, a substitution or a backslash in the ref answers `ask` (the human decides), not allow
  - every existing guard test still passes and `guard bash` on `ls` and on a plain commit stays within the process counts of test_v592 (builtins only)
  - Why (audit of v6.5.0, docs/audit-2026-11.md #3, #4, #5): reproduced with `guard check`; the guard is a text filter, so each rule is a speed bump that must at least see what runs
- **Tests:** substitution_in_double_quotes_is_checked, gh_merge_with_flags_is_blocked, push_to_claims_is_blocked, dynamic_ref_asks, plain_commands_stay_on_builtins
- **Verify:** `python3 kit/.uak/tests/test_guard_substitution.py`
- **Next step:** strip_prose and the gh rule (~line 100) in kit/.uak/bin/guard

## UAK-112 · The MCP `uak_cli` tool cannot run a passed command the guard does not see

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak-mcp, kit/.uak/tests/test_mcp_runs_commands.py
- **Acceptance:**
  - the refusal of commands that run a passed command looks past a leading `--json` (and any other global flag) to the command name
  - `red` is in the set (it runs `-- CMD` and `--cmd CMD`), and the set is derived from commands.tsv plus the explicit list, with a test that fails when a new command of that kind is added without it
  - the refusal names the terminal as the place to run it, as today
  - Why (audit of v6.5.0, docs/audit-2026-11.md #2): `["--json","loop",…]` and `red ID -- CMD` reached eval without the guard
- **Tests:** json_prefix_does_not_hide_the_command, red_is_refused, registry_and_set_agree
- **Verify:** `python3 kit/.uak/tests/test_mcp_runs_commands.py`
- **Next step:** RUNS_COMMANDS at kit/.uak/bin/uak-mcp:394 and the test at line 401

## UAK-113 · The merge lock's renewer stops when the merge that started it dies

- **Type:** bug
- **Priority:** P1
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/review-merge.sh, kit/.uak/tests/test_merge_renewer_orphan.py
- **Acceptance:**
  - the background loop that renews merge-lock.md exits within one interval after its parent process is gone (kill -9 of the merge), without pushing again
  - a normal merge still renews and releases the lock as today
  - Why (audit of v6.5.0, docs/audit-2026-11.md #6): the EXIT trap does not run on SIGKILL (a harness timeout, the OOM killer) and the orphan kept the queue locked
- **Tests:** renewer_exits_after_parent_is_killed, normal_merge_releases_the_lock
- **Verify:** `python3 kit/.uak/tests/test_merge_renewer_orphan.py`
- **Next step:** the renewer subshell at kit/.uak/bin/lib/review-merge.sh:~926

## UAK-114 · An unapproved task cannot be recorded INTEGRATED by its owner

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/lib/done.sh, kit/.uak/tests/test_integrate_unreviewed.py
- **Acceptance:**
  - `integrate` of a CLAIMED, BLOCKED or AVAILABLE task whose content is on main, with no valid approval, needs a human (`UAK_HUMAN=NAME … --reason TEXT`); an agent gets the same refusal as from REVIEW, with the line the human runs
  - the record of such an integrate says `Integrated-Outside: unreviewed`, and `stats` counts it
  - with a valid approval of that SHA by another seen identity, an agent integrates as today (UAK-092 behaviour kept)
  - Why (audit of v6.5.0, docs/audit-2026-11.md #7): integrate_mutate required a human only when the task was in REVIEW, so an owner could unlock dependents on unreviewed code
- **Tests:** owner_cannot_integrate_unapproved_claimed_task, human_records_it_as_unreviewed, approved_sha_still_integrates
- **Verify:** `python3 kit/.uak/tests/test_integrate_unreviewed.py`
- **Next step:** integrate_mutate at kit/.uak/bin/lib/done.sh:203-241

## UAK-115 · Temp files get unpredictable names and Python helpers get timeouts

- **Type:** bug
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/wt, kit/.uak/bin/doctor, kit/.uak/bin/bb, kit/.uak/bin/lib/dash.py, kit/.uak/tests/test_temp_and_timeouts.py
- **Acceptance:**
  - `wt` (wt-add), `doctor` (doctor-verify) and `bb export` create their temp files with mktemp (or under the git dir) and remove them on every exit path
  - every `subprocess.run` of git in dash.py has a timeout (30 s) and a TimeoutExpired ends with a one-line message, not a hang or a traceback
  - a lint check (in the test) finds no `.$$` temp name under ${TMPDIR:-/tmp} in kit/.uak/bin
  - Why (audit of v6.5.0, docs/audit-2026-11.md #8, #9): predictable names in a shared temp dir, and `uak dash` hanging on an unreachable remote
- **Tests:** no_pid_named_temp_files, temp_files_removed_on_error, dash_times_out_on_a_dead_remote
- **Verify:** `python3 kit/.uak/tests/test_temp_and_timeouts.py`
- **Next step:** kit/.uak/bin/wt:288, kit/.uak/bin/doctor:206, kit/.uak/bin/bb:161, the `git` helper of kit/.uak/bin/lib/dash.py
