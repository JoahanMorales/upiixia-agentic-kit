# TASKS · the kit's own backlog (dogfooding)

State lives on the `claims` branch of this repository (`bash .uak/bin/uak status`); this file holds only tasks.
Format: `kit/.uak/templates/TASKS.template.md`. Every task is test-first (`Test-First: yes` in PROJECT.md): its
`Tests:` fail on an assertion before the code (`uak red ID`).

Phase: the claims transaction without the process storm (docs/ROADMAP.md, "Next"). On Git Bash a process costs
20–50 ms and `uak next` starts about 200 of them: 4–8 s per call on a Windows laptop. Targets: `next` ≤ 40 processes,
`status` ≤ 30, `heartbeat` ≤ 20, with every command's output and the resulting claims tree unchanged.

## UAK-001 · Count the processes of next, status and heartbeat in the suite

- **Type:** feature
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/tests/test_claims_perf.py, scripts/perf_claims.sh, kit/.uak/bin/smoke, .github/workflows/test.yml
- **Acceptance:**
  - the test counts the processes each command starts on Linux (PIDs under `PS4`), on a fixture with 12 tasks and 3 claims
  - the targets are written as the test's assertions; until the redesign lands they are marked expected-to-fail in one place (an `XFAIL` set in the test, removed by UAK-006), never skipped
  - `scripts/perf_claims.sh` times the same commands on the machine it runs on (Windows: Git Bash)
- **Tests:** next_starts_at_most_40_processes, status_starts_at_most_30_processes, heartbeat_starts_at_most_20_processes
- **Verify:** `python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** read kit/.uak/tests/test_v592.py (processes()) and reuse its counter

## UAK-002 · A persistent claims repo per clone

- **Type:** feature
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-001
- **Paths:** kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_claims_repo.py
- **Acceptance:**
  - `<git-common-dir>/uak-claims/` replaces `git init` per call: one `git fetch` refreshes it; its config is set once
  - a `mkdir` lock serializes the processes of one machine; a stale lock (dead PID, older than the lease) is taken over
  - a corrupt or locked repo (antivirus, OneDrive) falls back to today's temporary clone and says so once
- **Tests:** reuses_the_claims_repo_between_calls, serializes_two_processes_on_one_machine, falls_back_to_a_temp_clone_when_the_repo_is_corrupt
- **Verify:** `python3 kit/.uak/tests/test_claims_repo.py`
- **Next step:** fresh_state in kit/.uak/bin/lib/tx.sh

## UAK-003 · Reads without a checkout: one cat-file pass, one awk program

- **Type:** feature
- **Priority:** P0
- **Estimate:** 6 h
- **Depends on:** UAK-002
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/state.awk, kit/.uak/tests/test_claims_read.py
- **Acceptance:**
  - `status`, `next`, `inbox --peek` and `board` read `tasks/`, `claims/` and the messages through one `git cat-file --batch` into one awk pass that builds the state in memory
  - no `field()` call (one `sed` or loop per key) on the read path
- **Tests:** status_reads_the_state_in_one_pass, next_reads_the_state_in_one_pass, a_record_with_crlf_reads_like_lf
- **Verify:** `python3 kit/.uak/tests/test_claims_read.py`
- **Next step:** list every field status and next read today (grep field in lib/status.sh and uak-coordination)

## UAK-004 · A tip-keyed cache of the parsed state

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-003
- **Paths:** kit/.uak/bin/lib/cache.sh, kit/.uak/tests/test_claims_cache.py
- **Acceptance:**
  - a read whose claims tip is unchanged reuses the parsed state; leases, the freeze and every "min ago" are recomputed from the clock
  - a mutation, or a different tip, never reads a stale cache
- **Tests:** reuses_the_state_when_the_tip_is_unchanged, recomputes_leases_from_the_clock, never_serves_a_stale_tip
- **Verify:** `python3 kit/.uak/tests/test_claims_cache.py`
- **Next step:** the hook's uak-claims.tip (kit/.uak/bin/hook) is the tip to key on

## UAK-005 · Mutations on a reused worktree of the claims repo

- **Type:** feature
- **Priority:** P1
- **Estimate:** 4 h
- **Depends on:** UAK-002
- **Paths:** kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_claims_write.py
- **Acceptance:**
  - `checkout -f refs/uak/claims`, write, commit, push in the persistent repo; a rejected push retries on the new tip
  - each retry keeps today's semantics: a fresh clock, the secret check before the commit, the append-only lint on `HEAD^`
- **Tests:** a_rejected_push_retries_on_the_new_tip, every_retry_reads_a_fresh_clock, a_secret_is_refused_before_the_commit
- **Verify:** `python3 kit/.uak/tests/test_claims_write.py`
- **Next step:** transaction in kit/.uak/bin/lib/tx.sh

## UAK-006 · Proof of no change, and the targets turned on

- **Type:** integration
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-003, UAK-004, UAK-005
- **Paths:** scripts/claims_diff.py, kit/.uak/tests/test_claims_perf.py, kit/.uak/bin/lib/, kit/.uak/bin/uak, kit/.uak/bin/uak-coordination, docs/perf-windows.md
- **Acceptance:**
  - the protocol suites run the old and the new engine side by side on the same fixtures: every command's stdout and the resulting claims tree are identical
  - the XFAIL set of test_claims_perf.py is empty: next ≤ 40, status ≤ 30, heartbeat ≤ 20 processes
  - docs/perf-windows.md has the before and after times from `scripts/perf_claims.sh` on Windows
- **Tests:** old_and_new_engines_print_the_same_and_write_the_same_tree
- **Verify:** `python3 scripts/claims_diff.py && python3 kit/.uak/tests/test_claims_perf.py`
- **Next step:** reuse the guard differential of v5.9.2 (docs/perf-windows.md)

## UAK-007 · hook stop and session-start on the new read path

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-006
- **Paths:** kit/.uak/bin/hook, kit/.uak/tests/test_hook_claims.py
- **Acceptance:**
  - `hook stop` (one `inbox --peek` per turn, 19 git calls today) and `session-start` read through the cache
  - every 5 min `tick` runs `pace --caps` in the background, like the poll
- **Tests:** stop_reads_the_inbox_from_the_cache, tick_runs_pace_in_the_background
- **Verify:** `python3 kit/.uak/tests/test_hook_claims.py`
- **Next step:** the stop branch of kit/.uak/bin/hook
