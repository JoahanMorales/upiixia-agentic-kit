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
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from test_hack import expect
from test_hook_session_start_speed import (BUDGET, alive, counted_fixture, first_pending_dir, hook_functions,
                                           refresh_fixture, run_cases, settle, settle_once, start, stub_engine)


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


def killed_bb_flush_is_recovered_and_published_once(r):
    """UAK-185 review: a flush killed mid-push left uak-blackbox.pending.PID and a clone, and the lines were never
    retried. The next start puts them back and publishes them once; the clone goes with the kill."""
    f, w = counted_fixture(r, "ss-bb-kill")
    common = first_pending_dir(r, w)
    gate = Path(r.scratch) / "ss-bb-gate"
    gate.write_text("closed\n")
    hook = Path(f.remote) / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nwhile [ -f '%s' ]; do sleep 0.2; done\nexit 0\n" % gate.as_posix(), encoding="utf-8")
    hook.chmod(0o755)
    lines = "".join("2026-11-10T10:0%dZ | agent | kit | error | uak claim | kill-test-%d | - | - | - | v6.4\n" % (i, i)
                    for i in (1, 2))
    pending = common / "uak-blackbox.pending"
    pending.write_text(lines, encoding="utf-8")
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1", UAK_START_LIMIT="3")
        deadline = time.monotonic() + 40
        left = []
        while time.monotonic() < deadline:
            left = [p for p in common.glob("uak-blackbox.pending.*") if p.name.rsplit(".", 1)[1].isdigit()]
            if left and not alive(r, w, int(left[0].name.rsplit(".", 1)[1])) and not list(common.glob("uak-bb-tmp.*")):
                break
            time.sleep(0.3)
        expect(left, "a flush killed mid-push leaves its snapshot (the test needs it): %r" % list(common.glob("uak-*")))
        expect(not list(common.glob("uak-bb-tmp.*")), "the killed flush's clone directory is removed: %r"
               % list(common.glob("uak-bb-tmp.*")))
    finally:
        gate.unlink()
    settle_once(r, w)
    start(r, w, "agent-1", UAK_START_WAIT="1")
    deadline = time.monotonic() + 40
    found = ""
    while time.monotonic() < deadline:
        names = [n for n in r.g(f.remote, "ls-tree", "-r", "--name-only", "claims").stdout.split() if n.startswith("blackbox/")]
        found = "".join(r.g(f.remote, "show", "claims:" + n).stdout for n in names)
        if ("kill-test-1" in found and "kill-test-2" in found and not list(common.glob("uak-blackbox.pending.*"))
                and not list(common.glob("uak-bb-tmp.*"))):
            break
        time.sleep(0.5)
    settle_once(r, w)
    expect(found.count("kill-test-1") == 1 and found.count("kill-test-2") == 1,
           "the next start publishes the recovered lines once: %r" % found[-600:])
    expect(not list(common.glob("uak-blackbox.pending.*")), "no snapshot is left: %r" % list(common.glob("uak-*")))
    return "killed mid-push, recovered by the next start, published once"


def other_users_pending_file_is_left(r):
    """UAK-185 review: `kill -0` fails with EPERM for a process of another user, and bb_leftover read that as a dead
    owner and took the file under a live flush. PID 1 is alive and not ours: its pending file stays; a dead PID's goes."""
    f, w = counted_fixture(r, "ss-bb-eperm")
    probe = r.run([r.bash, "-c", 'kill -0 1 2>&1; echo "rc=$?"'], cwd=w, allowed=None).stdout
    if "rc=0" in probe:
        return "kill -0 1 succeeds here (same user): nothing to prove, skipped"
    if "ermission" not in probe and "not permitted" not in probe.lower():
        return "kill -0 1 does not report a permission error here (%r): skipped" % probe.strip()[:80]
    dead = r.run([r.bash, "-c", "sleep 0 & echo $!; wait"], cwd=w).stdout.split()[0]
    common = Path(r.scratch) / "ss-eperm-common"
    common.mkdir()
    foreign = common / "uak-blackbox.pending.1"
    foreign.write_text("line-of-a-live-flush\n", encoding="utf-8")
    harness = Path(r.scratch) / "ss-eperm.sh"
    harness.write_text('COMMON="$1"\n' + hook_functions(r, w, "start_pid_ok", "bb_leftover") +
                       '\nbb_leftover any; echo "any=$?"\n', encoding="utf-8")
    out = r.run([r.bash, harness.as_posix(), common.as_posix()], cwd=w, allowed=None)
    expect("any=1" in out.stdout, "a pending file of PID 1 (alive, another user) is not a dead owner's: %r %r" % (out.stdout, out.stderr))
    expect(foreign.exists() and foreign.read_text(encoding="utf-8") == "line-of-a-live-flush\n", "its file is left as it was")
    (common / ("uak-blackbox.pending." + dead)).write_text("line-of-a-dead-flush\n", encoding="utf-8")
    out = r.run([r.bash, harness.as_posix(), common.as_posix()], cwd=w, allowed=None)
    expect("any=0" in out.stdout, "a dead owner's file is still found: %r %r" % (out.stdout, out.stderr))
    return "PID 1's pending file is left; a dead PID's is taken"


def clone_listing(common):
    """What is left of the clone directories: every path under them, with its size."""
    out = []
    for d in common.glob("uak-bb-tmp.*"):
        for root, dirs, files in os.walk(str(d)):
            for n in dirs + files:
                p = os.path.join(root, n)
                try:
                    out.append("%s (%d)" % (os.path.relpath(p, str(common)), os.path.getsize(p)))
                except OSError as exc:
                    out.append("%s (%s)" % (os.path.relpath(p, str(common)), exc))
    return out[:12]


def process_listing():
    """Windows only: the git, bash and sleep processes that run with their parent and command line, to see what still
    holds a directory."""
    if os.name != "nt":
        return "no process listing here"
    import subprocess
    cmd = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'git|bash|sh|sleep' } | ForEach-Object "
           "{ '{0}<{1} {2} {3}' -f $_.ProcessId, $_.ParentProcessId, $_.Name, $_.CommandLine }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return "process listing failed: %s" % exc
    return " | ".join(l.strip()[:160] for l in out.splitlines() if l.strip())[:2500]


def kill_round(r, f, w, common, gate, n):
    """One scenario: a flush held at the remote's gate passes its 3 s limit and is killed. Returns (seconds from the
    owner's death to the clone's removal or None, diagnostics) and leaves the checkout recovered for the next round."""
    lines = "".join("2026-11-10T10:0%dZ | agent | kit | error | uak claim | kill-loop-%d-%d | - | - | - | v6.4\n" % (i, n, i)
                    for i in (1, 2))
    (common / "uak-blackbox.pending").write_text(lines, encoding="utf-8")
    gate.write_text("closed\n")
    start(r, w, "agent-1", UAK_START_WAIT="1", UAK_START_LIMIT="3")
    deadline = time.monotonic() + 40
    dead_at = gone_at = None
    while time.monotonic() < deadline:
        left = [p for p in common.glob("uak-blackbox.pending.*") if p.name.rsplit(".", 1)[1].isdigit()]
        if left and dead_at is None and not alive(r, w, int(left[0].name.rsplit(".", 1)[1])):
            dead_at = time.monotonic()
        if dead_at is not None and not list(common.glob("uak-bb-tmp.*")):
            gone_at = time.monotonic()
            break
        time.sleep(0.1)
        if dead_at is not None and time.monotonic() - dead_at > 15:
            break
    diag = ""
    if dead_at is not None and gone_at is None:
        diag = "left: %s; owner: %s; processes: %s" % (clone_listing(common), [
            (d.name, (d / "owner").read_text().strip() if (d / "owner").exists() else None) for d in common.glob("uak-bb-tmp.*")],
            process_listing())
        for d in list(common.glob("uak-bb-tmp.*")):
            try:
                shutil.rmtree(str(d))
                diag += "; rmtree after the wait worked"
            except OSError as exc:
                diag += "; rmtree after the wait: %s" % exc
    gate.unlink()
    settle_once(r, w)
    start(r, w, "agent-1", UAK_START_WAIT="1")
    again = time.monotonic() + 40
    while time.monotonic() < again and (list(common.glob("uak-blackbox.pending.*")) or list(common.glob("uak-bb-tmp.*"))):
        time.sleep(0.3)
    settle_once(r, w)
    if dead_at is None:
        return None, "the flush never passed its limit and died (left: %r)" % list(common.glob("uak-*"))
    return (None if gone_at is None else gone_at - dead_at), diag


def killed_flush_leaves_no_clone_on_windows(r):
    """UAK-190. The cause of a Windows failure is NOT found. On main at 967f794 (run 45326081765, windows (10)) the clone
    directory of a killed flush was still there when killed_bb_flush_is_recovered_and_published_once looked. It
    failed again with the retry and the sweep already in place (run 45357519599, sha 17108d62, windows (5)): the
    clone was still there after that case's 40 s wait, so the 10 s retry does not explain it. About 2 failures in 9
    Windows runs of that case. This case repeats the scenario and never reproduced it: 20 rounds before the fix (run
    45338123292, job 138255069367) and 20 after (run 45342514688, job 138269556072) on one checkout, 8 rounds on
    fresh checkouts (run 45361468655), the clone gone 0.5-0.6 s after the owner's death each time.
    What the fix is: a mitigation. bb_unclone retries the removal for up to 10 s, and the next flush removes a clone
    whose owner (the file `owner` in it) is gone, so a leftover is never read as a live clone. It does not make the
    old case pass if something still holds the directory for 40 s.
    Hypothesis, unconfirmed: a child spawned between start_kill_tree's listing and its TERM escapes the kill and
    holds the clone (for example a git push held at the remote's gate).
    UAK_KILL_ROUNDS sets the rounds (default 1 fresh checkout; about 20 s a round on Windows)."""
    rounds = int(os.environ.get("UAK_KILL_ROUNDS", "1"))
    times, bad = [], []
    for n in range(rounds):
        # A fresh checkout each round: the first session start of a checkout also starts the refresh, the pace and
        # the map build, the load under which the failure was seen (run 45326081765 and 45357519599).
        f, w, common, gate = held_push_fixture(r, "ss-bb-kill-loop-%d" % n)
        try:
            took, diag = kill_round(r, f, w, common, gate, n)
        finally:
            if gate.exists():
                gate.unlink()
        if took is None:
            bad.append("round %d: %s" % (n, diag))
        else:
            times.append(took)
    summary = "%d rounds, clone removed after %s s (max %.1f)" % (
        rounds, ",".join("%.1f" % t for t in times), max(times) if times else -1)
    print("MEASURED killed_flush_leaves_no_clone: %s; failures %d: %s" % (summary, len(bad), bad), flush=True)
    expect(not bad, "a killed flush left its clone directory in %d of %d rounds: %s" % (len(bad), rounds, bad[:3]))
    return summary


def plant_clone(common, owner, age=0, name=None):
    """A clone directory as bb_flush_job makes it: uak-bb-tmp.TIME.HOOKPID, with the PID of the process that lives as
    long as the flush in its file `owner` (UAK-190 review: the PID in the name is the hook's, gone in seconds)."""
    d = common / (name or "uak-bb-tmp.%d.%d" % (int(time.time()) - age, 4242))
    (d / "uak-bb.AAAAAA" / ".git").mkdir(parents=True)
    (d / "uak-bb.AAAAAA" / ".git" / "HEAD").write_text("ref: refs/heads/x\n")
    if owner is not None:
        (d / "owner").write_text("%s\n" % owner)
    return d


def leftover_clone_is_removed_by_the_next_flush(r):
    """UAK-190: a clone directory whose flush died stays when its removal failed (Windows refuses while a file is in
    use). The next flush removes it at once when the owner recorded in it is gone, however young it is; a live
    owner's clone stays, and so does a young one that records no owner yet."""
    f, w = counted_fixture(r, "ss-bb-leftover")
    common = first_pending_dir(r, w)
    dead = r.run([r.bash, "-c", "sleep 0 & echo $!; wait"], cwd=w).stdout.split()[0]
    mine = r.run([r.bash, "-c", "sleep 100 & echo $!; disown"], cwd=w).stdout.split()[0]
    gone = plant_clone(common, dead)
    kept = plant_clone(common, mine, name="uak-bb-tmp.%d.4243" % int(time.time()))
    fresh = plant_clone(common, None, name="uak-bb-tmp.%d.4244" % int(time.time()))
    (common / "uak-blackbox.pending").write_text(
        "2026-11-10T10:01Z | agent | kit | error | uak claim | leftover-1 | - | - | - | v6.4\n", encoding="utf-8")
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1")
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and gone.exists():
            time.sleep(0.3)
        settle_once(r, w)
        expect(not gone.exists(), "a young clone whose owner is gone is removed by the next flush: %r"
               % list(common.glob("uak-bb-tmp.*")))
        expect(kept.exists(), "a clone whose owner is alive stays")
        expect(fresh.exists(), "a young clone that records no owner yet stays")
    finally:
        r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", mine], cwd=w, allowed=None)
    return "a dead owner's clone is removed, a live one's stays"


def held_push_fixture(r, name):
    f, w = counted_fixture(r, name)
    common = first_pending_dir(r, w)
    gate = Path(r.scratch) / (name + "-gate")
    gate.write_text("closed\n")
    hook = Path(f.remote) / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nwhile [ -f '%s' ]; do sleep 0.2; done\nexit 0\n" % gate.as_posix(), encoding="utf-8")
    hook.chmod(0o755)
    return f, w, common, gate


def published(r, f):
    names = [n for n in r.g(f.remote, "ls-tree", "-r", "--name-only", "claims").stdout.split() if n.startswith("blackbox/")]
    return "".join(r.g(f.remote, "show", "claims:" + n).stdout for n in names)


def pending_line(tag):
    return "2026-11-10T10:01Z | agent | kit | error | uak claim | %s | - | - | - | v6.4\n" % tag


def recover_and_count(r, f, w, common, tags):
    """The gate is open: let every flush end, start once more to recover what a kill left, and count the lines."""
    settle_once(r, w)
    deadline = time.monotonic() + 60
    found = ""
    while time.monotonic() < deadline:
        start(r, w, "agent-1", UAK_START_WAIT="1")
        settle_once(r, w)
        found = published(r, f)
        if all(t in found for t in tags) and not list(common.glob("uak-blackbox.pending*")):
            break
        time.sleep(1)
    return found


def second_start_leaves_a_live_flushs_clone(r):
    """UAK-190 review of 34480754: the clone carried the PID of the session-start hook, gone in seconds while the flush
    lives up to 300 s, so a second start took the clone of a flush that was still pushing for a dead owner's."""
    f, w, common, gate = held_push_fixture(r, "ss-bb-second")
    (common / "uak-blackbox.pending").write_text(pending_line("second-1"), encoding="utf-8")
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1")
        deadline = time.monotonic() + 40
        first = []
        while time.monotonic() < deadline and not (first and list(common.glob("uak-blackbox.pending.*"))):
            first = list(common.glob("uak-bb-tmp.*"))
            time.sleep(0.3)
        expect(first, "the held flush has its clone: %r" % list(common.glob("uak-*")))
        (common / "uak-blackbox.pending").write_text(pending_line("second-2"), encoding="utf-8")
        start(r, w, "agent-1", UAK_START_WAIT="1")
        # UAK-197: a fixed 4 s became a bounded wait: the second flush sweeps the clone directories before it makes its
        # own, so its own directory means the sweep has run.
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not set(common.glob("uak-bb-tmp.*")) - set(first):
            time.sleep(0.2)
        expect(set(common.glob("uak-bb-tmp.*")) - set(first), "the second start's flush made its clone directory: %r"
               % list(common.glob("uak-*")))
        expect(all(p.exists() for p in first), "a second start leaves the clone of a flush that still lives: %r"
               % list(common.glob("uak-bb-tmp.*")))
    finally:
        gate.unlink()
    found = recover_and_count(r, f, w, common, ("second-1", "second-2"))
    expect(found.count("second-1") == 1 and found.count("second-2") == 1, "each line is published once: %r" % found[-500:])
    expect(not list(common.glob("uak-bb-tmp.*")), "no clone is left: %r" % list(common.glob("uak-bb-tmp.*")))
    return "a second start during a held push removes nothing; both lines published once"


def eight_starts_with_a_held_push_publish_once(r):
    """UAK-190 review: eight simultaneous starts while a push is held. Every line is published exactly once, no clone
    goes while its flush lives, none is left at the end. Off by default (UAK_STORM_ROUNDS sets the rounds; the review's
    ten rounds ran on Linux, 10 of 10; a CI run with UAK_STORM_ROUNDS set is the Windows evidence)."""
    from concurrent.futures import ThreadPoolExecutor
    rounds = int(os.environ.get("UAK_STORM_ROUNDS", "0"))
    if rounds < 1:
        return "skipped: it costs 38 s a round on Windows, 14 s on Linux; UAK_STORM_ROUNDS=10 runs the review's ten rounds"
    f, w, common, gate = held_push_fixture(r, "ss-bb-storm")
    try:
        for n in range(rounds):
            tags = ["storm-%d-%d" % (n, i) for i in (1, 2, 3)]
            gate.write_text("closed\n")
            (common / "uak-blackbox.pending").write_text("".join(pending_line(t) for t in tags[:2]), encoding="utf-8")
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: start(r, w, "agent-1", UAK_START_WAIT="1"), range(8)))
                # A line written while the first flush is held: the second wave's flush must not take the first's clone.
                # UAK-197: a fixed 2 s became a bounded wait for a held flush (its snapshot uak-blackbox.pending.PID).
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline and not [x for x in common.glob("uak-blackbox.pending.*")
                                                           if x.name.rsplit(".", 1)[1].isdigit()]:
                    time.sleep(0.2)
                (common / "uak-blackbox.pending").write_text(pending_line(tags[2]), encoding="utf-8")
                list(pool.map(lambda _: start(r, w, "agent-1", UAK_START_WAIT="1"), range(8)))
            # A flush that finds nothing pending ends at once and takes its own clone; a clone that went while its
            # owner (the PID in its file) still runs was taken from a live flush.
            seen = {}
            end = time.monotonic() + 6
            while time.monotonic() < end:
                for d in common.glob("uak-bb-tmp.*"):
                    if not seen.get(d):
                        try:
                            seen[d] = (d / "owner").read_text().strip()
                        except OSError:
                            seen[d] = ""
                time.sleep(0.3)
            lost = [str(d) for d, o in seen.items() if o and not d.exists() and alive(r, w, int(o))]
            expect(not lost, "round %d: a clone went while its flush still ran: %r" % (n, lost))
            # The flushes held at the remote each own a snapshot (uak-blackbox.pending.BBPID) and each needs its clone.
            held = [x for x in common.glob("uak-blackbox.pending.*") if x.name.rsplit(".", 1)[1].isdigit()
                    and alive(r, w, int(x.name.rsplit(".", 1)[1]))]
            clones = list(common.glob("uak-bb-tmp.*"))
            expect(len(clones) >= len(held) and held, "round %d: %d flushes are held and %d clones remain" % (n, len(held), len(clones)))
            gate.unlink()
            found = recover_and_count(r, f, w, common, tags)
            for t in tags:
                expect(found.count(t) == 1, "round %d: %s is published %d times (once)" % (n, t, found.count(t)))
            expect(not list(common.glob("uak-bb-tmp.*")), "round %d: a clone is left: %r" % (n, list(common.glob("uak-bb-tmp.*"))))
    finally:
        if gate.exists():
            gate.unlink()
    return "%d rounds of eight starts: every line once, no clone lost or left" % rounds


def sweep_harness(r, w, common, body):
    script = Path(r.scratch) / "sweep.sh"
    script.write_text('COMMON="$1"; NOW=$(date +%s)\n' + hook_functions(r, w, "epoch_age", "start_pid_ok", "bb_sweep", "bb_unclone")
                      + "\n" + body + "\n", encoding="utf-8")
    return [r.bash, script.as_posix(), common.as_posix()]


def unremovable_clone_is_retried_then_left_to_the_next_flush(r):
    """UAK-190, Windows imitated on POSIX (an imitation: a directory of mode 000 holding a file cannot be emptied, as
    a directory in use cannot on Windows): the removal is retried and succeeds once the directory can be removed;
    past 10 s it stops, leaves no process, and the next flush removes it; the hook's foreground is not delayed."""
    if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        return "mode 000 does not stop this user here: skipped"
    import threading
    f, w = counted_fixture(r, "ss-bb-unremovable")
    common = first_pending_dir(r, w)
    dead = r.run([r.bash, "-c", "sleep 0 & echo $!; wait"], cwd=w).stdout.split()[0]
    clone = plant_clone(common, dead)
    lock = clone / "uak-bb.AAAAAA" / "locked"
    lock.mkdir()
    (lock / "f").write_text("x")
    lock.chmod(0)
    cmd = sweep_harness(r, w, common, 'bb_unclone; echo "left=$(ls "$COMMON" | grep -c uak-bb-tmp)"')
    try:
        timer = threading.Timer(3, lambda: lock.chmod(0o755))
        timer.start()
        began = time.monotonic()
        out = r.run(cmd, cwd=w, allowed=None)
        took = time.monotonic() - began
        timer.join()
        first_took = took
        expect("left=0" in out.stdout and not clone.exists(), "the retry removes it once it can be removed: %r %r" % (out.stdout, out.stderr))
        expect(3 <= took < 9, "after about 3 s, not at once and not at the end of the retries: %.1f s" % took)
        clone = plant_clone(common, dead)
        lock = clone / "uak-bb.AAAAAA" / "locked"
        lock.mkdir()
        (lock / "f").write_text("x")
        lock.chmod(0)
        began = time.monotonic()
        out = r.run(cmd, cwd=w, allowed=None)
        took = time.monotonic() - began
        expect("left=1" in out.stdout and clone.exists(), "a directory that stays unremovable is left: %r" % out.stdout)
        expect(took < 16, "the retry is bounded: %.1f s" % took)
        (common / "uak-blackbox.pending").write_text(pending_line("unremovable-1"), encoding="utf-8")
        spent, _ = start(r, w, "agent-1", UAK_START_WAIT="1")
        expect(spent < BUDGET, "the session start is not delayed by it: %.1f s" % spent)
        settle_once(r, w)
        expect(clone.exists(), "the flush that could not remove it left it")
        lock.chmod(0o755)
        (common / "uak-blackbox.pending").write_text(pending_line("unremovable-2"), encoding="utf-8")
        start(r, w, "agent-1", UAK_START_WAIT="1")
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and clone.exists():
            time.sleep(0.3)
        expect(not clone.exists(), "the next flush removes it once it can be")
    finally:
        for d in common.glob("uak-bb-tmp.*"):
            for p in d.rglob("locked"):
                p.chmod(0o755)
    settle_once(r, w)
    return "retried until removable (%.1f s), bounded at %.1f s when not, removed by the next flush" % (first_took, took)


def clone_removal_stays_inside_the_clone_directories(r):
    """UAK-190: the sweep touches only directories named uak-bb-tmp.TIME.PID in the git directory: a link named like
    one is removed without its target, a plain file, a name with garbage, an owner that is not a PID and PID 1 are
    left alone."""
    f, w = counted_fixture(r, "ss-bb-safe")
    common = first_pending_dir(r, w)
    outside = Path(r.scratch) / "ss-bb-outside"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    now = int(time.time())
    link = common / ("uak-bb-tmp.%d.5001" % now)
    try:
        os.symlink(str(outside), str(link))
        linked = True
    except (OSError, NotImplementedError):
        linked = False
    plain = common / ("uak-bb-tmp.%d.5002" % now)
    plain.write_text("a file")
    dead = r.run([r.bash, "-c", "sleep 0 & echo $!; wait"], cwd=w).stdout.split()[0]
    garbage = plant_clone(common, dead, name="uak-bb-tmp.garbage.abc;rm")
    badowner = plant_clone(common, "../../x", name="uak-bb-tmp.%d.5003" % now)
    pid1 = plant_clone(common, "1", name="uak-bb-tmp.%d.5004" % now)
    out = r.run(sweep_harness(r, w, common, "bb_sweep; echo swept"), cwd=w, allowed=None)
    expect("swept" in out.stdout, "the sweep runs: %r %r" % (out.stdout, out.stderr))
    expect((outside / "keep").read_text() == "keep", "the target of a link is intact")
    if linked:
        expect(not os.path.lexists(str(link)), "a link named like a clone is removed")
    expect(plain.is_file(), "a plain file stays")
    expect(garbage.is_dir() and badowner.is_dir(), "a name with garbage and an owner that is no PID stay")
    if os.name != "nt":   # Git Bash has no PID 1
        expect(pid1.is_dir(), "PID 1 is an owner that lives: its clone stays")
    return "link removed, target intact; file, garbage, bad owner and PID 1 left alone"


# moved_cases_are_the_same_cases (UAK-197): each function moved here, as its source text was in
# test_hook_session_start_speed.py on main at 0e50f9d0 (sha256 of inspect.getsource, first 16 hex digits). Text, not an
# AST dump: identical text is an identical AST on every Python. A case changed by this task as its fix is listed in FIXED
# with each text the fix replaced (original, now): with the originals put back, the source is main's, digit for digit.
ORIGINAL = {
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
CONSTANTS = "3f63e571ebd279e2"   # repr((HUNG_UAK, ONCE_FUNCS))
FIXED = {
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
    import test_hook_session_start_speed as speed
    here = globals()
    changed, missing = [], []
    for name, digest in ORIGINAL.items():
        fn = here.get(name)
        if fn is None:
            missing.append(name)
            continue
        text = inspect.getsource(fn)
        for original, now in FIXED.get(name, ()):
            expect(text.count(now) == 1, "%s: the fix's text is in it once: %r" % (name, now[:60]))
            text = text.replace(now, original)
        if source_digest(text) != digest:
            changed.append(name)
        expect(not hasattr(speed, name), "%s is defined in one file only (it moved)" % name)
    expect(not missing, "moved here: %s" % missing)
    expect(not changed, "moved, not rewritten: the source of %s differs from main's" % changed)
    # ONCE_FUNCS gained start_limit_value, the fix of stale_lock_reclaim_runs_once; without it the pair is main's.
    once = tuple(f for f in here.get("ONCE_FUNCS", ()) if f != "start_limit_value")
    expect("start_limit_value" in here.get("ONCE_FUNCS", ()) and len(once) == len(here["ONCE_FUNCS"]) - 1,
           "ONCE_FUNCS has start_limit_value once")
    expect(source_digest(repr((here.get("HUNG_UAK"), once))) == CONSTANTS, "HUNG_UAK and ONCE_FUNCS moved unchanged but for the fix")
    mine = [t.__name__ for t in TESTS if t.__name__ != "moved_cases_are_the_same_cases"]
    theirs = [t.__name__ for t in speed.TESTS]
    expect(not set(mine) & set(theirs), "no case runs in both files: %s" % sorted(set(mine) & set(theirs)))
    new_here = {"kill_guard_refuses_an_ancestor"}   # added by UAK-197 to the speed file
    expect(sorted(set(mine + theirs) - new_here) == sorted(BEFORE) and len(mine + theirs) == len(set(mine + theirs)),
           "every case of the file before the split runs once: missing %s, new %s"
           % (sorted(set(BEFORE) - set(mine + theirs)), sorted(set(mine + theirs) - set(BEFORE) - new_here)))
    # The check sees a change: one character more in a moved case is not the original.
    probe = inspect.getsource(here["pending_line"])
    expect(source_digest(probe + " ") != ORIGINAL["pending_line"] and source_digest(probe) == ORIGINAL["pending_line"], "the digest sees one character")
    return "%d functions moved unchanged%s; %d cases here, %d in the speed file" % (
        len(ORIGINAL) - len(FIXED), (", %s changed only by its fix" % ", ".join(FIXED)) if FIXED else "", len(mine), len(theirs))


TESTS = [session_start_coalesces_aged_live_refreshes, session_start_recovers_a_dead_refresh_owner,
         session_start_concurrent_claims_launch_one_refresh, session_start_abandoned_handoff_cannot_run_or_release,
         hung_worker_is_killed, pace_and_map_run_once_under_ten_starts, cached_start_does_not_wait]
TESTS += [corrupt_time_file_does_not_end_the_hook, future_time_file_is_stale, stale_lock_reclaim_runs_once,
          once_lock_with_a_bad_time_is_stale, empty_guard_is_recovered, killed_bb_flush_is_recovered_and_published_once]
TESTS += [other_users_pending_file_is_left]
TESTS += [killed_flush_leaves_no_clone_on_windows, leftover_clone_is_removed_by_the_next_flush,
          second_start_leaves_a_live_flushs_clone, eight_starts_with_a_held_push_publish_once,
          unremovable_clone_is_retried_then_left_to_the_next_flush, clone_removal_stays_inside_the_clone_directories]
TESTS += [moved_cases_are_the_same_cases]


def main():
    return run_cases(TESTS, "SESSION_START_LOCKS", "uak-ss-locks-")


if __name__ == "__main__":
    raise SystemExit(main())
