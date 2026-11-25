#!/usr/bin/env python3
"""UAK-197: the cases of test_hook_session_start_speed.py about locks, simultaneous starts and the clones of the black
box flush, moved here unchanged (same bodies, same assertions; moved_cases_are_the_same_cases proves it from the source
of each case as it was in that file on main at 0e50f9d0). Why: that file took 339 to 536 s on Windows, over the 300 s
under which a failed file runs a second time in its job, so a failure of it was never retried and cost a manual re-run
of main. Split, each file takes about half (their timing files hold the measured seconds).
What these cases check is described in test_hook_session_start_speed.py (UAK-174, UAK-157, UAK-185, UAK-190): the
session-start hook answers within its budget and its background jobs run once, under a limit, without losing a line."""
import hashlib
import inspect
import os
import re
import subprocess
import time
from pathlib import Path

from test_hack import expect
from test_hook_session_start_speed import (alive, counted_fixture, hook_functions, refresh_fixture, run_cases, settle,
                                           settle_once, start, stub_engine)


def session_start_orphan_output_cannot_change_replacement_cache(r):
    gd, control = refresh_fixture(r, "orphan-output", '''
new_read() { printf 'Next: NEW snapshot\\n'; }
if [ "${3:-}" = recover ]; then
  trap - EXIT
  start_bg next start_capture next new_read
  wait
  exit 0
fi
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next bash "$case_dir/backend.sh" OLD "$case_dir" Next
old_pid=$!
wait_file "$case_dir/old-ready"
kill -KILL "$old_pid"
wait "$old_pid" 2>/dev/null || true
age_refresh
# Windows may defer recovery while an orphan holds an output handle; it must fail closed in that case.
bash "$0" "$gd" "$case_dir" recover
: > "$case_dir/release-old"
wait_file "$case_dir/old-done"
cat "$gd/uak-start.next.txt" > "$case_dir/after-orphan"
# Once the orphan closes, either recovery path must finish normally.
start_bg next start_capture next new_read
wait
''')
    after = (control / "after-orphan").read_text(encoding="utf-8")
    expect(after in ("Next: KEPT snapshot\n", "Next: NEW snapshot\n"),
           "assertion failed: orphan output changed the committed cache: %r" % after)
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n",
           "recovery succeeds after the orphan closes its output")
    expect(not list(gd.glob("uak-start.next*.running")), "no crashed generation marker remains")
    return "orphan output cannot write into the replacement's cache inode"


def session_start_orphan_inbox_output_cannot_change_cache(r):
    gd, control = refresh_fixture(r, "orphan-inbox", '''
export UAK_BACKEND_DIR="$case_dir"
mv .uak/bin/uak .uak/bin/uak-real
cat > .uak/bin/uak <<'INBOX'
#!/usr/bin/env bash
if [ "$1" = inbox ]; then
  if mkdir "$UAK_BACKEND_DIR/selected" 2>/dev/null; then
    exec bash "$UAK_BACKEND_DIR/backend.sh" OLD "$UAK_BACKEND_DIR" Inbox
  fi
  printf 'Inbox: NEW snapshot\\n'; exit 0
fi
exec bash "$(dirname "$0")/uak-real" "$@"
INBOX
printf 'Inbox: KEPT snapshot\\n' > "$gd/uak-inbox.txt"
inbox_kept &
old_pid=$!
wait_file "$case_dir/old-ready"
kill -KILL "$old_pid"
wait "$old_pid" 2>/dev/null || true
inbox_kept
cat "$gd/uak-inbox.txt" > "$case_dir/before-orphan"
: > "$case_dir/release-old"
wait_file "$case_dir/old-done"
''')
    before = (control / "before-orphan").read_text(encoding="utf-8")
    after = (gd / "uak-inbox.txt").read_text(encoding="utf-8")
    expect(before == after == "Inbox: NEW snapshot\n",
           "assertion failed: orphan inbox output changed a committed cache: %r -> %r" % (before, after))
    return "inbox readers use private publication sources"


def session_start_revokes_a_dead_owners_pending_move(r):
    gd, control = refresh_fixture(r, "pending-move", '''
export UAK_MOVE_CASE="$case_dir" UAK_MOVE_CACHE="$gd/uak-start.next.txt"
UAK_REAL_MV=$(type -P mv); export UAK_REAL_MV
cat > "$case_dir/move.sh" <<'MOVE'
#!/usr/bin/env bash
src= dst=
for arg in "$@"; do src=$dst; dst=$arg; done
if [ "$dst" = "$UAK_MOVE_CACHE" ] && grep -q '^Next: OLD' "$src"; then
  : > "$UAK_MOVE_CASE/move-ready"
  n=0
  while [ ! -f "$UAK_MOVE_CASE/release-move" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
  "$UAK_REAL_MV" "$@"; status=$?
  : > "$UAK_MOVE_CASE/move-done"
  exit "$status"
fi
exec "$UAK_REAL_MV" "$@"
MOVE
mv() { bash "$case_dir/move.sh" "$@"; }
old_read() { printf 'Next: OLD snapshot\\n'; }
new_read() { printf 'Next: NEW snapshot\\n'; }
new_publish() {
  start_capture next new_read
  : > "$case_dir/new-ready"
  wait_file "$case_dir/release-new"
}
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next old_read
old_pid=$!
wait_file "$case_dir/move-ready"
kill -KILL "$old_pid"
wait "$old_pid" 2>/dev/null || true
age_refresh
start_bg next new_publish
new_pid=$!
wait_file "$case_dir/new-ready"
cat "$gd/uak-start.next.txt" > "$case_dir/before-move"
find "$gd" -name 'uak-start.next*.running' | sort > "$case_dir/markers-before"
: > "$case_dir/release-move"
wait_file "$case_dir/move-done"
cat "$gd/uak-start.next.txt" > "$case_dir/after-move"
find "$gd" -name 'uak-start.next*.running' | sort > "$case_dir/markers-after"
: > "$case_dir/release-new"
wait "$new_pid"
''')
    before = (control / "before-move").read_text(encoding="utf-8")
    after = (control / "after-move").read_text(encoding="utf-8")
    expect(before == after == "Next: NEW snapshot\n",
           "assertion failed: a dead owner's delayed rename overwrote NEW: %r -> %r" % (before, after))
    marks = (control / "markers-before").read_text(encoding="utf-8")
    expect(marks and marks == (control / "markers-after").read_text(encoding="utf-8"),
           "the dead generation cannot remove the current generation's marker")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n", "NEW stays committed")
    return "dead generation's rename source is revoked before replacement"


def session_start_finishes_an_interrupted_reap(r):
    gd, control = refresh_fixture(r, "interrupted-reap", '''
old_gen=$(mktemp -d "$gd/uak-start.next.XXXXXX")
printf '%s\\n' "$old_gen" > "$case_dir/old-generation"
printf 'private OLD output\\n' > "$old_gen/output"
printf '%s\\n' "$NOW" > "$old_gen.running"
(exit 0) &
dead_pid=$!
wait "$dead_pid"
owner=$(printf 'REAP %s %s\\n' "$dead_pid" "${old_gen##*/}" | git hash-object -w --stdin)
git update-ref --no-deref refs/worktree/uak-start/next "$owner"
new_read() {
  local expected_old=
  IFS= read -r expected_old < "$case_dir/old-generation"
  [ ! -e "$expected_old" ] || : > "$case_dir/started-before-revocation"
  printf 'Next: NEW snapshot\\n'
}
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next new_read
wait
''')
    old = Path((control / "old-generation").read_text(encoding="utf-8").strip())
    expect(not old.exists() and not old.is_symlink(), "interrupted REAP revokes the old generation")
    expect(not (control / "started-before-revocation").exists(), "replacement starts only after revocation")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n",
           "an interrupted REAP cannot strand refresh ownership")
    expect(not list(gd.glob("uak-start.next*.running")), "REAP and replacement markers are cleaned")
    return "dead reaper adopted without losing old-generation cleanup"


def session_start_failed_reap_is_closed_and_retryable(r):
    gd, control = refresh_fixture(r, "failed-reap", '''
rm() {
  local expected_old= arg candidate=
  [ ! -f "$case_dir/old-generation" ] || IFS= read -r expected_old < "$case_dir/old-generation"
  if [ -f "$case_dir/fail-cleanup" ]; then
    expected_old=$(CDPATH= cd -- "$expected_old" && pwd -P) || return 1
    for arg in "$@"; do
      candidate=${arg%/}
      [ ! -d "$candidate" ] || candidate=$(CDPATH= cd -- "$candidate" && pwd -P) || return 1
      if [ "$candidate" = "$expected_old" ]; then : > "$case_dir/cleanup-blocked"; return 1; fi
    done
  fi
  command rm "$@"
}
new_read() { printf 'NEW\\n' >> "$case_dir/calls"; printf 'Next: NEW snapshot\\n'; }
if [ "${3:-}" = failed-attempt ]; then
  trap - EXIT
  start_bg next start_capture next new_read
  wait
  exit 0
fi
old_gen=$(mktemp -d "$gd/uak-start.next.XXXXXX")
printf '%s\\n' "$old_gen" > "$case_dir/old-generation"
printf 'private OLD output\\n' > "$old_gen/output"
printf '%s\\n' "$NOW" > "$old_gen.running"
(exit 0) &
dead_pid=$!
wait "$dead_pid"
owner=$(printf 'REAP %s %s\\n' "$dead_pid" "${old_gen##*/}" | git hash-object -w --stdin)
git update-ref --no-deref refs/worktree/uak-start/next "$owner"
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
: > "$case_dir/fail-cleanup"
bash "$0" "$gd" "$case_dir" failed-attempt
cat "$gd/uak-start.next.txt" > "$case_dir/after-failure"
[ ! -f "$case_dir/calls" ] || cp "$case_dir/calls" "$case_dir/early-calls"
command rm "$case_dir/fail-cleanup"
start_bg next start_capture next new_read
wait
''')
    expect((control / "cleanup-blocked").exists(), "the cleanup fault actually ran")
    expect((control / "after-failure").read_text(encoding="utf-8") == "Next: KEPT snapshot\n"
           and not (control / "early-calls").exists(), "failed revocation cannot start or publish a replacement")
    expect((control / "calls").read_text(encoding="utf-8").splitlines() == ["NEW"], "one retry runs after cleanup works")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n", "REAP recovery finishes")
    expect(not list(gd.glob("uak-start.next*.running")), "recovered cleanup leaves no old markers")
    return "cleanup failure stays closed and a later caller finishes REAP"


def session_start_corrupt_owner_records_cannot_delete_paths(r):
    gd, control = refresh_fixture(r, "corrupt-owner", '''
mkdir -p "$gd/../../victim"
printf 'KEEP\\n' > "$gd/../../victim/sentinel"
printf '%s\\n' "$gd/../../victim/sentinel" > "$case_dir/victim-path"
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
new_read() { printf 'BAD\\n' >> "$case_dir/calls"; printf 'Next: BAD snapshot\\n'; }
(exit 0) &
dead_pid=$!
wait "$dead_pid"
for record in 'REAP 0 uak-start.next.ABC123' 'REAP nope uak-start.next.ABC123' \
              'UNKNOWN 999999 uak-start.next.ABC123' 'REAP 999999 ../../victim' \
              'REAP 999999 uak-start.next.ABC123/../../victim' 'RUNNING 999999 uak-start.next.ABC123 extra' \
              'REAP 999999 uak-start.next.ABC123
RUNNING 1 uak-start.next.DEF456'; do
  record=${record//999999/$dead_pid}
  owner=$(printf '%s\\n' "$record" | git hash-object -w --stdin)
  git update-ref --no-deref refs/worktree/uak-start/next "$owner"
  start_bg next start_capture next new_read
  wait
  after=$(git rev-parse --verify refs/worktree/uak-start/next 2>/dev/null || true)
  [ "$after" = "$owner" ] || : > "$case_dir/corrupt-ref-mutated"
done
''')
    victim = Path((control / "victim-path").read_text(encoding="utf-8").strip())
    expect(victim.read_text(encoding="utf-8") == "KEEP\n", "corrupt paths cannot escape gitdir")
    expect(not (control / "calls").exists(), "invalid ownership records must fail closed without a backend")
    expect(not (control / "corrupt-ref-mutated").exists(), "invalid records cannot claim or clear ownership")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: KEPT snapshot\n", "corruption keeps last cache")
    return "invalid schema, PID and traversal tokens fail closed"


def session_start_internal_owner_refs_bypass_user_hooks(r):
    gd, control = refresh_fixture(r, "reference-hook", '''
mkdir "$case_dir/user-hooks"
cat > "$case_dir/user-hooks/reference-transaction" <<'HOOK'
#!/usr/bin/env bash
: > "$UAK_REFERENCE_HOOK_MARKER"
exit 1
HOOK
chmod +x "$case_dir/user-hooks/reference-transaction"
export UAK_REFERENCE_HOOK_MARKER="$case_dir/reference-hook-ran"
git config core.hooksPath "$case_dir/user-hooks"
new_read() { printf 'Next: NEW snapshot\\n'; }
start_bg next start_capture next new_read
wait
''')
    expect(not (control / "reference-hook-ran").exists(), "private ownership CAS must not invoke project hooks")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n", "internal ref claim succeeds")
    return "reference-transaction hook is excluded from internal ownership updates"


def session_start_inbox_failure_preserves_cache_and_status(r):
    gd, control = refresh_fixture(r, "inbox-failure", '''
mv .uak/bin/uak .uak/bin/uak-real
cat > .uak/bin/uak <<'INBOX'
#!/usr/bin/env bash
exit 7
INBOX
printf 'Inbox: KEPT snapshot\\n' > "$gd/uak-inbox.txt"
if inbox_kept; then status=0; else status=$?; fi
printf '%s\\n' "$status" > "$case_dir/status"
''')
    expect((control / "status").read_text(encoding="utf-8").strip() == "7",
           "assertion failed: private inbox cleanup masked the failed read's status")
    expect((gd / "uak-inbox.txt").read_text(encoding="utf-8") == "Inbox: KEPT snapshot\n", "failed read keeps cache")
    expect(not list(gd.glob("uak-inbox.??????")), "failed private inbox output is removed")
    return "inbox read failure survives cleanup without replacing cached output"


def session_start_coalesces_aged_live_refreshes(r):
    for order in ("new-first", "old-first"):
        gd, control = refresh_fixture(r, "live-" + order, '''
old_read() {
  printf 'OLD\\n' >> "$case_dir/calls"; : > "$case_dir/old-ready"
  wait_file "$case_dir/release-old"
  printf 'Next: OLD task\\n'
}
new_read() {
  printf 'NEW\\n' >> "$case_dir/calls"; : > "$case_dir/new-ready"
  wait_file "$case_dir/release-new"
  printf 'Next: NEW task\\n'
}
printf 'Next: KEPT task\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next old_read
old_pid=$!
wait_file "$case_dir/old-ready"
age_refresh
start_bg next start_capture next new_read
new_pid=$!
''' + ('''
: > "$case_dir/release-new"
[ "$new_pid" = "$old_pid" ] || wait "$new_pid"
: > "$case_dir/release-old"
wait "$old_pid"
''' if order == "new-first" else '''
: > "$case_dir/release-old"
wait "$old_pid"
: > "$case_dir/release-new"
[ "$new_pid" = "$old_pid" ] || wait "$new_pid"
'''))
        calls = (control / "calls").read_text(encoding="utf-8").splitlines()
        expect(calls == ["OLD"], "assertion failed: %s started a second live refresh: %r" % (order, calls))
        expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: OLD task\n",
               "the sole live owner publishes its result")
        expect(not list(gd.glob("uak-start.next*.running")), "the completed sole owner leaves no running marker")
    return "aged live owners coalesce in both attempted completion orders"


def session_start_recovers_a_dead_refresh_owner(r):
    gd, control = refresh_fixture(r, "dead", '''
old_read() { : > "$case_dir/old-ready"; wait_file "$case_dir/release-old"; printf 'Next: OLD task\\n'; }
new_read() { printf 'NEW\\n' >> "$case_dir/calls"; printf 'Next: NEW task\\n'; }
printf 'Next: KEPT task\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next old_read
old_pid=$!
wait_file "$case_dir/old-ready"
kill -KILL "$old_pid"
wait "$old_pid" 2>/dev/null || true
# Do not age the marker: proven death must be recoverable immediately.
start_bg next start_capture next new_read
wait
''')
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW task\n",
           "assertion failed: a dead owner with a fresh marker prevented recovery")
    expect((control / "calls").read_text(encoding="utf-8").splitlines() == ["NEW"], "one replacement runs")
    expect(not list(gd.glob("uak-start.next*.running")), "dead and replacement markers are cleaned up")
    return "dead owner recovered without waiting for marker age"


def session_start_concurrent_claims_launch_one_refresh(r):
    gd, control = refresh_fixture(r, "claim-race", '''
real_git=$(type -P git)
git() {
  local arg last= is_update= is_owner=
  for arg in "$@"; do
    last=$arg
    [ "$arg" != update-ref ] || is_update=1
    [ "$arg" != refs/worktree/uak-start/next ] || is_owner=1
  done
  if [ -n "$is_update" ] && [ -n "$is_owner" ] && [ -z "$last" ]; then
    if mkdir "$case_dir/first-claim" 2>/dev/null; then : > "$case_dir/claim-one-ready"
    else : > "$case_dir/claim-two-ready"; fi
    wait_file "$case_dir/release-claim"
  fi
  command "$real_git" "$@"
}
backend() {
  printf '%s\\n' "$1" >> "$case_dir/calls"
  : > "$case_dir/backend-ready"
  wait_file "$case_dir/release-backend"
  printf 'Next: %s snapshot\\n' "$1"
}
if [ "${3:-}" != '' ]; then
  trap - EXIT
  start_bg next start_capture next backend "$3"
  wait
  exit 0
fi
bash "$0" "$gd" "$case_dir" FIRST &
first=$!
wait_file "$case_dir/claim-one-ready"
bash "$0" "$gd" "$case_dir" SECOND &
second=$!
wait_file "$case_dir/claim-two-ready"
: > "$case_dir/release-claim"
wait_file "$case_dir/backend-ready"
: > "$case_dir/release-backend"
wait "$first"
wait "$second"
''')
    calls = (control / "calls").read_text(encoding="utf-8").splitlines()
    expect(len(calls) == 1 and calls[0] in ("FIRST", "SECOND"), "exactly one concurrent CAS claimant may run")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: %s snapshot\n" % calls[0],
           "the winning claimant publishes its output")
    expect(not list(gd.glob("uak-start.next*.running")), "losing claimant cannot strand a marker")
    return "real concurrent absent-ref claims are atomic"


def session_start_abandoned_handoff_cannot_run_or_release(r):
    gd, control = refresh_fixture(r, "handoff-race", '''
real_git=$(type -P git)
git() {
  local arg previous= last= is_update= is_owner= is_delete= record= state= pid= token=
  for arg in "$@"; do
    previous=$last; last=$arg
    [ "$arg" != update-ref ] || is_update=1
    [ "$arg" != refs/worktree/uak-start/next ] || is_owner=1
    [ "$arg" != -d ] || is_delete=1
  done
  if [ -n "$is_update" ] && [ -n "$is_owner" ] && [ -z "$is_delete" ] && [ -n "$last" ]; then
    record=$(command "$real_git" cat-file blob "$previous" 2>/dev/null) || record=
    IFS=' ' read -r state pid token <<< "$record"
    if [ "$state" = RUNNING ] && mkdir "$case_dir/first-handoff" 2>/dev/null; then
      printf '%s\\n' "$pid" > "$case_dir/old-worker-pid"
      : > "$case_dir/handoff-ready"
      wait_file "$case_dir/release-handoff"
    fi
  fi
  command "$real_git" "$@"
}
old_read() { printf 'OLD\\n' >> "$case_dir/calls"; printf 'Next: OLD snapshot\\n'; }
new_read() { printf 'NEW\\n' >> "$case_dir/calls"; printf 'Next: NEW snapshot\\n'; }
new_publish() { start_capture next new_read; : > "$case_dir/new-ready"; wait_file "$case_dir/release-new"; }
if [ "${3:-}" = old-parent ]; then
  trap - EXIT
  printf '%s\\n' "$$" > "$case_dir/old-parent-pid"
  start_bg next start_capture next old_read
  wait
  exit 0
fi
bash "$0" "$gd" "$case_dir" old-parent &
parent_job=$!
wait_file "$case_dir/handoff-ready"
IFS= read -r parent_pid < "$case_dir/old-parent-pid"
IFS= read -r old_worker < "$case_dir/old-worker-pid"
kill -KILL "$parent_pid"
wait "$parent_job" 2>/dev/null || true
start_bg next new_publish
new_pid=$!
wait_file "$case_dir/new-ready"
find "$gd" -name 'uak-start.next*.running' | sort > "$case_dir/markers-before"
: > "$case_dir/release-handoff"
n=0
while kill -0 "$old_worker" 2>/dev/null && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
kill -0 "$old_worker" 2>/dev/null && { printf 'assertion failed: abandoned worker did not exit\\n' >&2; exit 1; }
find "$gd" -name 'uak-start.next*.running' | sort > "$case_dir/markers-after"
: > "$case_dir/release-new"
wait "$new_pid"
''')
    expect((control / "calls").read_text(encoding="utf-8").splitlines() == ["NEW"],
           "an abandoned STARTING handoff must not run its backend")
    marks = (control / "markers-before").read_text(encoding="utf-8")
    expect(marks and marks == (control / "markers-after").read_text(encoding="utf-8"),
           "abandoned handoff cannot release a replacement's marker")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n", "NEW stays committed")
    return "dead parent handoff loses CAS without touching replacement"


HUNG_UAK = """case "$1" in next)
  sleep 300 &
  printf '%s\\n' "$$" > "$UAK_HUNG_DIR/uak.pid"
  printf '%s\\n' "$!" > "$UAK_HUNG_DIR/child.pid"
  wait;;
esac"""


def hung_worker_is_killed(r):
    """UAK-157: a `git` that hangs in the refresh must not outlive the session start's worker. The stub `uak next`
    starts a child that sleeps for 300 s, as a git waiting on a dead remote does."""
    f, w = counted_fixture(r, "ss-hung")
    control = Path(r.scratch) / "ss-hung-control"
    control.mkdir()
    stub_engine(r, w, uak=HUNG_UAK)
    pids = []
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1", UAK_START_LIMIT="2", UAK_HUNG_DIR=control.as_posix())
        deadline = time.monotonic() + 20
        while not (control / "child.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        pids = [int((control / n).read_text().strip()) for n in ("uak.pid", "child.pid") if (control / n).exists()]
        expect(len(pids) == 2, "the stub refresh started: %r" % pids)
        # The limit is 2 s here (60 s by default); the kill needs a moment more.
        deadline = time.monotonic() + 15
        while any(alive(r, w, p) for p in pids) and time.monotonic() < deadline:
            time.sleep(0.5)
        left = [p for p in pids if alive(r, w, p)]
        expect(not left, "after the time limit the hung refresh and its child still run (PIDs %r)" % left)
        settle(r, w)
        gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
        expect(not list(gd.glob("uak-start.*.running")), "the killed worker leaves no running marker")
    finally:
        for p in pids:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(p)], cwd=w, allowed=None)
        for p in pids:
            expect(not alive(r, w, p), "test cleanup: PID %d is gone" % p)
    return "a refresh that hangs is killed with its child after the limit"


def pace_and_map_run_once_under_ten_starts(r):
    """UAK-157: `pace` and `map build` are single-flight like `next`: ten starts in a row run each at most once."""
    f, w = counted_fixture(r, "ss-once")
    control = Path(r.scratch) / "ss-once-control"
    control.mkdir()
    stub_engine(r, w, uak='case "$1" in next) echo "Next: stub";; esac',
                pace='echo x >> "$UAK_ONCE_DIR/pace.calls"; sleep 1; echo "PACE normal: stub"',
                map='[ "$1" != build ] || { echo x >> "$UAK_ONCE_DIR/map.calls"; sleep 1; }')
    began = time.monotonic()
    for _ in range(10):
        start(r, w, "agent-1", UAK_START_WAIT="1", UAK_ONCE_DIR=control.as_posix())
    elapsed = time.monotonic() - began
    settle(r, w)
    calls = {n: len((control / (n + ".calls")).read_text().split()) if (control / (n + ".calls")).exists() else 0
             for n in ("pace", "map")}
    expect(calls["pace"] == 1 and calls["map"] == 1,
           "ten starts in %.0f s ran pace %d and map build %d times (once each)" % (elapsed, calls["pace"], calls["map"]))
    return "ten starts in %.0f s: one pace and one map build" % elapsed


def cached_start_does_not_wait(r):
    """UAK-157: with a cached copy the hook answers without waiting for the refresh and says how old the copy is;
    without one it waits for the refresh (bounded) and shows it."""
    f, w = counted_fixture(r, "ss-cached")
    control = Path(r.scratch) / "ss-cached-control"
    control.mkdir()
    stub_engine(r, w, uak='case "$1" in next) d=$(cat "$UAK_DELAY_FILE"); sleep "$d"; echo "Next: stub $d";; esac')
    delay = control / "delay"
    extra = {"UAK_DELAY_FILE": delay.as_posix()}
    delay.write_text("1\n")
    # No copy yet: the hook waits (up to 3 s here) for the 1 s refresh and shows it.
    _, out = start(r, w, "agent-1", UAK_START_WAIT="30", **extra)
    expect("Next: stub 1" in out, "without a cached copy the hook waits for the refresh and shows it: " + out[:400])
    settle(r, w)
    # A copy exists: a 6 s refresh does not hold the hook, which shows the copy and its age.
    delay.write_text("6\n")
    time.sleep(1.2)
    took, out = start(r, w, "agent-1", UAK_START_WAIT="80", **extra)
    expect(took < 5, "with a cached copy the hook waited for the refresh (%.1f s)" % took)
    expect("Next: stub 1" in out, "the cached copy is shown: " + out[:400])
    expect(re.search(r"\b\d+ s ago", out), "the hook says how old the copy is: " + out[:600])
    settle(r, w)
    return "no copy: waits; copy: %.1f s with its age" % took


# UAK-197: start_limit_value added (the hook's start_limited and start_once call it since fcf79edd; without it every job of
# the harness was killed at once). See stale_lock_reclaim_runs_once.
ONCE_FUNCS = ("epoch_age", "start_pid_ok", "start_children", "start_tree", "start_kill_tree", "start_limit_value",
              "start_limited", "start_once_live", "start_once_recent", "start_once_mine", "start_once")


def once_harness(r, w, name, body):
    """A Bash script with start_once and what it needs from the hook, NOW as the hook has it, then BODY."""
    script = Path(r.scratch) / name
    script.write_text("NOW=$(date +%s)\n" + hook_functions(r, w, *ONCE_FUNCS) + "\n" + body + "\n", encoding="utf-8")
    return script


def live_process(r, w):
    """A process that stays alive for the test; its PID as Bash sees it. Stopped by PID in `stop_live`."""
    import subprocess
    proc = subprocess.Popen([r.bash, "-c", "echo $$; exec sleep 120"], stdout=subprocess.PIPE, text=True)
    pid = int(proc.stdout.readline().strip())
    return proc, pid


def stop_live(r, w, proc, pid):
    r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(pid)], cwd=w, allowed=None)
    proc.wait(timeout=20)
    proc.stdout.close()
    expect(not alive(r, w, pid), "test cleanup: PID %d is gone" % pid)


def bash_counts(control, *names):
    return {n: len((control / (n + ".calls")).read_text().split()) if (control / (n + ".calls")).exists() else 0
            for n in names}


def counting_stubs(r, w, control):
    stub_engine(r, w, uak='case "$1" in next) echo "Next: stub";; esac',
                pace='echo x >> "$UAK_ONCE_DIR/pace.calls"; echo "PACE normal: stub"',
                map='[ "$1" != build ] || echo x >> "$UAK_ONCE_DIR/map.calls"')


def corrupt_time_file_does_not_end_the_hook(r):
    """UAK-185: a time file that holds `08`, letters, nothing or twenty digits made the hook stop at an arithmetic
    error: the output ended at the identity line. Now the value is stale, and the start prints what it always does."""
    f, w = counted_fixture(r, "ss-corrupt")
    control = Path(r.scratch) / "ss-corrupt-control"
    control.mkdir()
    counting_stubs(r, w, control)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    extra = {"UAK_START_WAIT": "1", "UAK_ONCE_DIR": control.as_posix()}
    _, reference = start(r, w, "agent-1", **dict(extra, UAK_START_WAIT="60"))
    settle_once(r, w)
    tail = [l for l in reference.splitlines() if l.strip()][-1]
    expect("Next: stub" in reference and tail, "the reference start prints the list: " + reference[-300:])
    seen = bash_counts(control, "pace", "map")
    for value in ("08", "abc", "", "9" * 20):
        for name in ("uak-start.next.at", "uak-once.pace.at", "uak-once.map.at"):
            (gd / name).write_text(value + "\n", encoding="utf-8")
        (gd / "uak-pace.start").write_text(value + "\nPACE critical: kept from a corrupt time\n", encoding="utf-8")
        _, out = start(r, w, "agent-1", **extra)
        settle_once(r, w)
        expect("UAK: agent=agent-1" in out and "Next: stub" in out and tail in out,
               "with %r in the time files the start still prints everything (its last line %r): %s"
               % (value, tail, out[-400:]))
        now = bash_counts(control, "pace", "map")
        expect(now["pace"] == seen["pace"] + 1 and now["map"] == seen["map"] + 1,
               "with %r in the time files pace and map build still run: before %r, after %r" % (value, seen, now))
        seen = now
    return "08, letters, nothing and twenty digits: the whole output, pace and map build run"


def future_time_file_is_stale(r):
    """UAK-185: a time an hour ahead blocked pace and map build for that hour, and a negative age was printed."""
    f, w = counted_fixture(r, "ss-future")
    control = Path(r.scratch) / "ss-future-control"
    control.mkdir()
    counting_stubs(r, w, control)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    extra = {"UAK_START_WAIT": "1", "UAK_ONCE_DIR": control.as_posix()}
    start(r, w, "agent-1", **dict(extra, UAK_START_WAIT="60"))
    settle_once(r, w)
    before = bash_counts(control, "pace", "map")
    ahead = str(int(time.time()) + 3600)
    proc, pid = live_process(r, w)
    try:
        for name in ("uak-start.next.at", "uak-once.pace.at", "uak-once.map.at"):
            (gd / name).write_text(ahead + "\n", encoding="utf-8")
        for name in ("pace", "map"):  # a live owner whose start lies in the future is not a live owner
            (gd / ("uak-once.%s.running" % name)).write_text("%d %s\n" % (pid, ahead), encoding="utf-8")
        (gd / "uak-pace.start").write_text(ahead + "\nPACE critical: kept from the future\n", encoding="utf-8")
        _, out = start(r, w, "agent-1", **extra)
        settle_once(r, w)
    finally:
        stop_live(r, w, proc, pid)
    after = bash_counts(control, "pace", "map")
    expect(after["pace"] == before["pace"] + 1 and after["map"] == before["map"] + 1,
           "a time an hour ahead does not block pace or map build: before %r, after %r" % (before, after))
    expect("PACE critical: kept from the future" not in out, "a pace reading stamped in the future is not shown")
    expect("Next: stub" in out, "the list is shown: " + out[-300:])
    expect(not re.search(r"-\d+ s ago", out), "an age is never negative: " + out[-400:])
    return "a time an hour ahead is stale: pace and map build run, no negative age"


def stale_lock_reclaim_runs_once(r):
    """UAK-185: reclaiming a stale lock deleted the lock another start had just taken (pace ran twice in 1 of 3
    rounds of 8 simultaneous starts). Ten rounds of eight starts, all released together on a stale lock.
    UAK-197: the merge gate's smoke of UAK-191 (Linux, four shards at once, 2026-11-24, gate-UAK-191-smoke-1795553245)
    failed it with "ran pace 1 and map build 0 times" in round 5. The cause, found with the kill guard's log: the harness
    (once_harness, ONCE_FUNCS) lacked start_limit_value, which the hook added after this case was written (fcf79edd), so
    LIM was empty, start_limited saw its limit passed at its first look and killed every job at once (20 TERMs from
    race.sh's start_kill_tree in one run of this case). A job counted only when its `echo x` ran before that TERM: under
    load it did not. ONCE_FUNCS now has start_limit_value (the jobs run their second, 0 TERMs), and the scripts wait for
    the jobs they started, so the count comes after every job: no lock file left does not prove that every job ended."""
    import subprocess
    f, w = counted_fixture(r, "ss-race")
    base = Path(r.scratch) / "ss-race-control"
    base.mkdir()
    script = once_harness(r, w, "race.sh", r"""gd=$1
while [ ! -f "$gd/go" ]; do :; done
for n in pace map; do start_once "$n" 60 bash -c 'echo x >> "$1/$2.calls"; sleep 1' _ "$gd" "$n"; done
# UAK-197: wait for the jobs started here; the test counts once every script has ended.
wait""")
    stale = int(time.time()) - 1000
    totals = []
    for rnd in range(10):
        gd = base / ("round%d" % rnd)
        gd.mkdir()
        for name in ("pace", "map"):
            (gd / ("uak-once.%s.running" % name)).write_text("999999 %d\n" % stale, encoding="utf-8")
        procs = [subprocess.Popen([r.bash, script.as_posix(), gd.as_posix()], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(8)]
        (gd / "go").write_text("go\n")
        for p in procs:
            p.wait(timeout=60)
        deadline = time.monotonic() + 30
        while list(gd.glob("uak-once.*.running")) and time.monotonic() < deadline:
            time.sleep(0.2)
        counts = bash_counts(gd, "pace", "map")
        totals.append(counts)
        expect(counts == {"pace": 1, "map": 1},
               "round %d: eight simultaneous starts on a stale lock ran pace %d and map build %d times (once each); "
               "rounds so far %r" % (rnd + 1, counts["pace"], counts["map"], totals))
        expect(not list(gd.glob("uak-once.*.running")) and not list(gd.glob("uak-once.*.reclaim")),
               "round %d leaves no lock behind" % (rnd + 1))
    return "ten rounds of eight starts: each job ran once in every round"


def once_lock_with_a_bad_time_is_stale(r):
    f, w = counted_fixture(r, "ss-lock-time")
    gd = Path(r.scratch) / "ss-lock-time-gd"
    gd.mkdir()
    script = once_harness(r, w, "lock.sh", r"""gd=$1
start_once pace 0 bash -c 'echo x >> "$1/pace.calls"' _ "$gd"
sleep 1""")
    proc, pid = live_process(r, w)
    try:
        for value in ("08", "abc", "9" * 20, str(int(time.time()) + 3600)):
            before = bash_counts(gd, "pace")["pace"]
            (gd / "uak-once.pace.running").write_text("%d %s\n" % (pid, value), encoding="utf-8")
            r.run([r.bash, script.as_posix(), gd.as_posix()], cwd=w, allowed=None)
            deadline = time.monotonic() + 15
            while bash_counts(gd, "pace")["pace"] == before and time.monotonic() < deadline:
                time.sleep(0.2)
            expect(bash_counts(gd, "pace")["pace"] == before + 1,
                   "a live owner whose lock says %r is stale and pace runs" % value)
            deadline = time.monotonic() + 15
            while (gd / "uak-once.pace.running").exists() and time.monotonic() < deadline:
                time.sleep(0.2)
    finally:
        stop_live(r, w, proc, pid)
    return "08, letters, twenty digits and a time ahead in a lock: stale"


def empty_guard_is_recovered(r):
    """UAK-185 review: a reclaimer killed between creating its guard and writing it left an empty guard that nothing
    judged stale: pace and map build never ran again. An empty guard is judged by the file's own age."""
    f, w = counted_fixture(r, "ss-empty-guard")
    gd = Path(r.scratch) / "ss-empty-guard-gd"
    gd.mkdir()
    script = once_harness(r, w, "emptyguard.sh", r"""gd=$1
start_once pace 0 bash -c 'echo x >> "$1/pace.calls"; sleep 1' _ "$gd"
""")
    (gd / "uak-once.pace.running").write_text("999999 %d 60\n" % (int(time.time()) - 1000), encoding="utf-8")
    guard = gd / "uak-once.pace.reclaim"
    guard.write_text("", encoding="utf-8")
    old = time.time() - 600
    os.utime(str(guard), (old, old))
    for _ in range(3):
        r.run([r.bash, script.as_posix(), gd.as_posix()], cwd=w, allowed=None)
        time.sleep(0.3)
    deadline = time.monotonic() + 15
    while (gd / "uak-once.pace.running").exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    expect(bash_counts(gd, "pace")["pace"] == 1, "an old empty guard on a stale lock: pace ran %d times in 3 starts (once)"
           % bash_counts(gd, "pace")["pace"])
    expect(not guard.exists(), "the old empty guard is removed")
    return "an empty guard older than a minute no longer blocks the job"


# moved_cases_are_the_same_cases (UAK-197): each function moved here, as its source text was in
# test_hook_session_start_speed.py on main at 0e50f9d0 (sha256 of inspect.getsource, first 16 hex digits). Text, not an
# AST dump: identical text is an identical AST on every Python. A case changed by this task as its fix is listed in FIXED
# with each text the fix replaced (original, now): with the originals put back, the source is main's, digit for digit.
ORIGINAL = {
    "session_start_orphan_output_cannot_change_replacement_cache": "8dfe58b99c9d4eef",
    "session_start_orphan_inbox_output_cannot_change_cache": "00b82cc7aa7e8b3c",
    "session_start_revokes_a_dead_owners_pending_move": "de76503ea7e233e2",
    "session_start_finishes_an_interrupted_reap": "b0dc929145fa32a2",
    "session_start_failed_reap_is_closed_and_retryable": "8905fc1b8eb6963f",
    "session_start_corrupt_owner_records_cannot_delete_paths": "ff673063949742cb",
    "session_start_internal_owner_refs_bypass_user_hooks": "55e95d88f86660f0",
    "session_start_inbox_failure_preserves_cache_and_status": "6b423d8559850e80",
    "every_background_job_has_a_limit": "0cd8090d1afd4c65",
    "limited_jobs_poll_coarsely": "4d3a77a0dadc445f",
    "first_pending_dir": "efdbf245471de5f8",
    "lens_tick": "5e0747dc919acea5",
    "killed_map_build_is_not_a_built_map": "3357121e355aa88b",
    "killed_tokens_publish_is_retried": "45bb1062e791e3e7",
    "counter_files_are_validated": "ecc1ec1ddaf87072",
    "session_start_coalesces_aged_live_refreshes": "85a78f02cda948b3",
    "session_start_recovers_a_dead_refresh_owner": "ef2467b8377e6368",
    "session_start_concurrent_claims_launch_one_refresh": "c70d5e3cf25c4e99",
    "session_start_abandoned_handoff_cannot_run_or_release": "e1d7ddca202d2b19",
    "hung_worker_is_killed": "ab0c36f5e7456e73",
    "pace_and_map_run_once_under_ten_starts": "25863d832d74a6f1",
    "cached_start_does_not_wait": "cff980abbe294bca",
    "once_harness": "5e932a3526f49c26",
    "live_process": "ed14048d5dec2b9d",
    "stop_live": "4002b8234f61361a",
    "bash_counts": "08ccc4dd80886a49",
    "counting_stubs": "783d98fc26f7e9bf",
    "corrupt_time_file_does_not_end_the_hook": "1b2cde66069fc878",
    "future_time_file_is_stale": "13a8abc7ff365605",
    "stale_lock_reclaim_runs_once": "bf7cbf92322f36e2",
    "once_lock_with_a_bad_time_is_stale": "6007ef21bb2fc3c0",
    "empty_guard_is_recovered": "0854febc9e16fcf8",
    "killed_bb_flush_is_recovered_and_published_once": "e6d3bdd3b460a05f",
    "other_users_pending_file_is_left": "2ceef526b6e72279",
    "clone_listing": "eaa3ac368bde0c05",
    "process_listing": "d88ba59fc51cd888",
    "kill_round": "d92b994ac2640dad",
    "killed_flush_leaves_no_clone_on_windows": "ea34eabe38a68490",
    "plant_clone": "2736936721b6d4cf",
    "leftover_clone_is_removed_by_the_next_flush": "822914d665c2c430",
    "held_push_fixture": "ab4204128d0a14a4",
    "published": "4a4a09e9bab4bad6",
    "pending_line": "cd6c1e2ada9844b9",
    "recover_and_count": "ba99ddff5646e665",
    "second_start_leaves_a_live_flushs_clone": "de7134dbbf5a4412",
    "eight_starts_with_a_held_push_publish_once": "6257982f20d14e02",
    "sweep_harness": "1ddd9883fc11e1b8",
    "unremovable_clone_is_retried_then_left_to_the_next_flush": "4417ad537fd680fb",
    "clone_removal_stays_inside_the_clone_directories": "76afc3bf936fe22b",
}
CONSTANTS = "3f63e571ebd279e2"   # repr((HUNG_UAK, ONCE_FUNCS)), here
CLONE_CONSTANTS = "da58833e90bd03fb"   # repr((HANG, LENS_STUB)), in test_hook_session_start_clones.py
FIXED = {
    'lens_tick': [
        ("""    time.sleep(2)   # the tick's own background jobs (drift fetch, heartbeat, pr-sync) are short; the directory is removed next
""",
         """    # UAK-197: no fixed 2 s here any more. It waited for the tick's own background jobs (drift fetch, heartbeat, pr-sync)
    # before the directory was removed; the case that calls this ends with settle_once, a bounded wait until no process
    # works in the checkout, and polls for what it checks.
"""),
    ],
    'stale_lock_reclaim_runs_once': [
        ('for n in pace map; do start_once "$n" 60 bash -c \'echo x >> "$1/$2.calls"; sleep 1\' _ "$gd" "$n"; done""")',
         'for n in pace map; do start_once "$n" 60 bash -c \'echo x >> "$1/$2.calls"; sleep 1\' _ "$gd" "$n"; done\n# UAK-197: wait for the jobs started here; the test counts once every script has ended.\nwait""")'),
        ('    rounds of 8 simultaneous starts). Ten rounds of eight starts, all released together on a stale lock."""',
         '    rounds of 8 simultaneous starts). Ten rounds of eight starts, all released together on a stale lock.\n    UAK-197: the merge gate\'s smoke of UAK-191 (Linux, four shards at once, 2026-11-24, gate-UAK-191-smoke-1795553245)\n    failed it with "ran pace 1 and map build 0 times" in round 5. The cause, found with the kill guard\'s log: the harness\n    (once_harness, ONCE_FUNCS) lacked start_limit_value, which the hook added after this case was written (fcf79edd), so\n    LIM was empty, start_limited saw its limit passed at its first look and killed every job at once (20 TERMs from\n    race.sh\'s start_kill_tree in one run of this case). A job counted only when its `echo x` ran before that TERM: under\n    load it did not. ONCE_FUNCS now has start_limit_value (the jobs run their second, 0 TERMs), and the scripts wait for\n    the jobs they started, so the count comes after every job: no lock file left does not prove that every job ended."""'),
    ],
    'second_start_leaves_a_live_flushs_clone': [
        ('        start(r, w, "agent-1", UAK_START_WAIT="1")\n        time.sleep(4)\n',
         '        start(r, w, "agent-1", UAK_START_WAIT="1")\n        # UAK-197: a fixed 4 s became a bounded wait: the second flush sweeps the clone directories before it makes its\n        # own, so its own directory means the sweep has run.\n        deadline = time.monotonic() + 40\n        while time.monotonic() < deadline and not set(common.glob("uak-bb-tmp.*")) - set(first):\n            time.sleep(0.2)\n        expect(set(common.glob("uak-bb-tmp.*")) - set(first), "the second start\'s flush made its clone directory: %r"\n               % list(common.glob("uak-*")))\n'),
    ],
    'eight_starts_with_a_held_push_publish_once': [
        ("                # A line written while the first flush is held: the second wave's flush must not take the first's clone.\n                time.sleep(2)\n",
         '                # A line written while the first flush is held: the second wave\'s flush must not take the first\'s clone.\n                # UAK-197: a fixed 2 s became a bounded wait for a held flush (its snapshot uak-blackbox.pending.PID).\n                deadline = time.monotonic() + 40\n                while time.monotonic() < deadline and not [x for x in common.glob("uak-blackbox.pending.*")\n                                                           if x.name.rsplit(".", 1)[1].isdigit()]:\n                    time.sleep(0.2)\n'),
    ],
}
# The 40 cases of test_hook_session_start_speed.py on main at 0e50f9d0: after the split each runs in exactly one file.
BEFORE = ["session_start_returns_within_budget", "session_start_output_is_unchanged", "session_start_marks_only_the_inbox_snapshot_it_prints",
          "session_start_coalesces_aged_live_refreshes", "session_start_recovers_a_dead_refresh_owner",
          "session_start_orphan_output_cannot_change_replacement_cache", "session_start_orphan_inbox_output_cannot_change_cache",
          "session_start_revokes_a_dead_owners_pending_move", "session_start_finishes_an_interrupted_reap",
          "session_start_failed_reap_is_closed_and_retryable", "session_start_corrupt_owner_records_cannot_delete_paths",
          "session_start_internal_owner_refs_bypass_user_hooks", "session_start_concurrent_claims_launch_one_refresh",
          "session_start_abandoned_handoff_cannot_run_or_release", "session_start_inbox_failure_preserves_cache_and_status",
          "session_start_launches_half_the_processes_on_startup", "session_start_launches_half_the_processes_on_resume",
          "session_start_keeps_reporting_the_pace_level", "hung_worker_is_killed", "pace_and_map_run_once_under_ten_starts",
          "cached_start_does_not_wait", "corrupt_time_file_does_not_end_the_hook", "future_time_file_is_stale",
          "stale_lock_reclaim_runs_once", "once_lock_with_a_bad_time_is_stale", "every_background_job_has_a_limit",
          "cached_copy_always_says_its_age", "empty_guard_is_recovered", "limited_jobs_poll_coarsely",
          "killed_bb_flush_is_recovered_and_published_once", "killed_map_build_is_not_a_built_map",
          "killed_tokens_publish_is_retried", "counter_files_are_validated", "other_users_pending_file_is_left",
          "killed_flush_leaves_no_clone_on_windows", "leftover_clone_is_removed_by_the_next_flush",
          "second_start_leaves_a_live_flushs_clone", "eight_starts_with_a_held_push_publish_once",
          "unremovable_clone_is_retried_then_left_to_the_next_flush", "clone_removal_stays_inside_the_clone_directories"]


def source_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def moved_cases_are_the_same_cases(r):
    import test_hook_session_start_clones as clones
    import test_hook_session_start_speed as speed
    files = {"locks": globals(), "clones": vars(clones), "speed": vars(speed)}
    changed, missing = [], []
    for name, digest in ORIGINAL.items():
        homes = [k for k, ns in files.items() if callable(ns.get(name)) and getattr(ns[name], "__module__", "") in
                 ("__main__", "test_hook_session_start_locks", "test_hook_session_start_clones", "test_hook_session_start_speed")
                 and inspect.getsourcefile(ns[name]).endswith("test_hook_session_start_%s.py" % k)]
        if len(homes) != 1:
            (missing if not homes else changed).append("%s (defined in %s)" % (name, homes or "none"))
            continue
        text = inspect.getsource(files[homes[0]][name])
        for original, now in FIXED.get(name, ()):
            expect(text.count(now) == 1, "%s: the fix's text is in it once: %r" % (name, now[:60]))
            text = text.replace(now, original)
        if source_digest(text) != digest:
            changed.append(name)
        expect(homes[0] != "speed", "%s moved out of the speed file" % name)
    expect(not missing, "moved: %s" % missing)
    expect(not changed, "moved, not rewritten, and defined in one file only: %s" % changed)
    once = tuple(f for f in globals().get("ONCE_FUNCS", ()) if f != "start_limit_value")
    expect("start_limit_value" in globals().get("ONCE_FUNCS", ()) and len(once) == len(ONCE_FUNCS) - 1,
           "ONCE_FUNCS has start_limit_value once (the fix of stale_lock_reclaim_runs_once)")
    expect(source_digest(repr((globals().get("HUNG_UAK"), once))) == CONSTANTS, "HUNG_UAK and ONCE_FUNCS moved unchanged but for the fix")
    expect(source_digest(repr((vars(clones).get("HANG"), vars(clones).get("LENS_STUB")))) == CLONE_CONSTANTS, "HANG and LENS_STUB moved unchanged")
    lists = {"locks": [t.__name__ for t in TESTS if t.__name__ != "moved_cases_are_the_same_cases"],
             "clones": [t.__name__ for t in clones.TESTS], "speed": [t.__name__ for t in speed.TESTS]}
    every = [n for v in lists.values() for n in v]
    new_here = {"kill_guard_refuses_an_ancestor"}   # added by UAK-197 to the speed file
    expect(len(every) == len(set(every)), "no case runs in two files: %s" % sorted({n for n in every if every.count(n) > 1}))
    expect(sorted(set(every) - new_here) == sorted(BEFORE), "every case of the file before the split runs once: missing %s, new %s"
           % (sorted(set(BEFORE) - set(every)), sorted(set(every) - set(BEFORE) - new_here)))
    # The check sees a change: one character more in a moved case is not the original.
    probe = inspect.getsource(vars(clones)["pending_line"])
    expect(source_digest(probe + " ") != ORIGINAL["pending_line"] and source_digest(probe) == ORIGINAL["pending_line"], "the digest sees one character")
    return "%d functions moved unchanged%s; cases: %s" % (
        len(ORIGINAL) - len(FIXED), (", %s changed only by its fix" % ", ".join(FIXED)) if FIXED else "",
        ", ".join("%d in %s" % (len(v), k) for k, v in lists.items()))

TESTS = [session_start_orphan_output_cannot_change_replacement_cache, session_start_orphan_inbox_output_cannot_change_cache,
         session_start_revokes_a_dead_owners_pending_move, session_start_finishes_an_interrupted_reap,
         session_start_failed_reap_is_closed_and_retryable, session_start_corrupt_owner_records_cannot_delete_paths,
         session_start_internal_owner_refs_bypass_user_hooks, session_start_inbox_failure_preserves_cache_and_status]
TESTS += [session_start_coalesces_aged_live_refreshes, session_start_recovers_a_dead_refresh_owner,
          session_start_concurrent_claims_launch_one_refresh, session_start_abandoned_handoff_cannot_run_or_release,
          hung_worker_is_killed, pace_and_map_run_once_under_ten_starts, cached_start_does_not_wait]
TESTS += [corrupt_time_file_does_not_end_the_hook, future_time_file_is_stale, stale_lock_reclaim_runs_once,
          once_lock_with_a_bad_time_is_stale, empty_guard_is_recovered]
TESTS += [moved_cases_are_the_same_cases]


def main():
    return run_cases(TESTS, "SESSION_START_LOCKS", "uak-ss-locks-")


if __name__ == "__main__":
    raise SystemExit(main())
