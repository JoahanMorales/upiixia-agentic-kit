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
