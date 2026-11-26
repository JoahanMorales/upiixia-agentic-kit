#!/usr/bin/env python3
"""UAK-197: the cases of test_hook_session_start_speed.py about the black box flush's clones and the background jobs
killed at their limit, moved here unchanged (moved_cases_are_the_same_cases, in test_hook_session_start_locks.py, proves
it from the source of each case on main at 0e50f9d0). Why: that file took 339 to 536 s on Windows, over the 300 s under
which a failed file runs a second time in its job; two files were not enough (a half measured 270 s on a slow Windows
runner, run 45683968328), so it is three, each with its measured timing file.
What these cases check is described where they came from (UAK-185, UAK-190): every background job of a session start has a
limit, a killed job leaves nothing half done, and a killed flush's lines are published once with no clone left behind."""
import os
import re
import shutil
import time
from pathlib import Path

from test_hack import expect
from test_hook_session_start_speed import (BUDGET, alive, counted_fixture, hook_functions, run_cases, settle_once, start,
                                           stub_engine)


HANG = 'echo "$0 $*" >> "$UAK_HUNG_DIR/jobs"; sleep 300 & echo "$$ $!" >> "$UAK_HUNG_DIR/pids"; wait'


def every_background_job_has_a_limit(r):
    """UAK-185: tokens --publish, bb flush, the lens `map build`, pr-sync and heartbeat were plain nohup jobs. Each
    is stubbed to hang with a child that sleeps for 300 s; with a 2 s limit none of them may be left."""
    import subprocess
    f, w = counted_fixture(r, "ss-limits")
    control = Path(r.scratch) / "ss-limits-control"
    control.mkdir()
    gh = Path(r.scratch) / "ss-limits-gh"
    gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gh.chmod(0o755)
    stub_engine(r, w, uak='case "$1" in next) echo "Next: stub";; pr-sync|heartbeat) %s;; esac' % HANG,
                tokens=HANG, bb='case "$1" in flush) %s;; esac' % HANG,
                map='case "$1" in build) %s;; esac' % HANG, pace='echo "PACE normal: stub"')
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    common = (gd / "commondir")
    cdir = (gd / common.read_text().strip()).resolve() if common.exists() else gd
    (cdir / "uak-blackbox.pending").write_text('{"x":1}\n', encoding="utf-8")
    (w / "README.md").write_text("x\n", encoding="utf-8")
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    env = {"UAK_START_WAIT": "1", "UAK_START_LIMIT": "2", "UAK_HUNG_DIR": control.as_posix(), "UAK_GH": gh.as_posix()}
    pids = []
    try:
        start(r, w, "agent-1", **env)
        lens_tick(r, w, "s-limits", env)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            jobs = (control / "jobs").read_text() if (control / "jobs").exists() else ""
            if all(k in jobs for k in ("tokens", "flush", "build", "pr-sync", "heartbeat")):
                break
            time.sleep(0.3)
        jobs = (control / "jobs").read_text() if (control / "jobs").exists() else ""
        for key in ("tokens", "flush", "build", "pr-sync", "heartbeat"):
            expect(key in jobs, "the hook started the %s job: %s" % (key, jobs))
        pids = [int(x) for line in (control / "pids").read_text().splitlines() for x in line.split()]
        deadline = time.monotonic() + 25
        while any(alive(r, w, p) for p in pids) and time.monotonic() < deadline:
            time.sleep(0.5)
        left = [p for p in pids if alive(r, w, p)]
        expect(not left, "after the 2 s limit these background jobs (and children) still run: PIDs %r of %r; jobs:\n%s"
               % (left, pids, jobs))
        settle_once(r, w)
    finally:
        for p in pids:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(p)], cwd=w, allowed=None)
        for p in pids:
            expect(not alive(r, w, p), "test cleanup: PID %d is gone" % p)
    return "tokens, bb flush, lens map build, pr-sync and heartbeat killed with their children at the limit"


def limited_jobs_poll_coarsely(r):
    """UAK-185 review: a detached job polled once a second for its whole limit, a process each on Git Bash."""
    f, w = counted_fixture(r, "ss-poll")
    gd = Path(r.scratch) / "ss-poll-gd"
    gd.mkdir()
    script = Path(r.scratch) / "poll.sh"
    script.write_text(hook_functions(r, w, "start_pid_ok", "start_children", "start_tree", "start_kill_tree",
                                     "start_limit_value", "start_limited") + r"""
gd=$1
sleep() { echo "$1" >> "$gd/sleeps"; SECONDS=$((SECONDS + ${1%%.*})); command sleep 0.01; }
UAK_START_LIMIT=300 start_limited bash -c 'echo $$ > "$1/pid"; exec sleep 600' _ "$gd"
echo "status=$?" > "$gd/status"
""", encoding="utf-8")
    pid = None
    try:
        r.run([r.bash, script.as_posix(), gd.as_posix()], cwd=w, allowed=None)
        pid = int((gd / "pid").read_text().strip())
        sleeps = len((gd / "sleeps").read_text().split())
        expect((gd / "status").read_text().strip() == "status=1", "a job that passes the limit makes start_limited fail")
        expect(20 <= sleeps <= 90, "a 300 s limit costs %d sleeps (at most 90, was about 300)" % sleeps)
        expect(not alive(r, w, pid), "the killed job is gone")
    finally:
        if pid:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(pid)], cwd=w, allowed=None)
    return "a 300 s limit: %d sleeps" % sleeps


def first_pending_dir(r, w):
    return Path(r.run([r.bash, "-c", "git rev-parse --path-format=absolute --git-common-dir"], cwd=w).stdout.strip())


LENS_STUB = 'case "$1" in build) %s;; esac'


def lens_tick(r, w, sid, env):
    tick = '{"session_id":"%s","tool_name":"Read","tool_input":{"file_path":"%s"}}' % (sid, (w / "README.md").as_posix())
    # The payload goes through the environment: Windows drops the double quotes of a command-line argument.
    out = r.run([r.bash, "-c", "printf '%s' \"$TICK_PAYLOAD\" | bash .uak/bin/hook tick"], cwd=w,
                 env=dict({"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1", "TICK_PAYLOAD": tick}, **env),
                 allowed=None)
    # UAK-197: no fixed 2 s here any more. It waited for the tick's own background jobs (drift fetch, heartbeat, pr-sync)
    # before the directory was removed; the case that calls this ends with settle_once, a bounded wait until no process
    # works in the checkout, and polls for what it checks.
    return out


def killed_map_build_is_not_a_built_map(r):
    """UAK-185 review: a lens `map build` killed mid-way left a partial symbols.tsv that counted as built."""
    f, w = counted_fixture(r, "ss-map-kill")
    control = Path(r.scratch) / "ss-map-kill-control"
    control.mkdir()
    (w / "README.md").write_text("x\n", encoding="utf-8")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    shutil.rmtree(str(gd / "uak-map"), ignore_errors=True)
    stub_engine(r, w, map=LENS_STUB % ('mkdir -p "$(git rev-parse --absolute-git-dir)/uak-map"; '
                                       'echo partial > "$(git rev-parse --absolute-git-dir)/uak-map/symbols.tsv"; ' + HANG))
    pids = []
    env = {"UAK_START_LIMIT": "2", "UAK_HUNG_DIR": control.as_posix()}
    try:
        t = lens_tick(r, w, "s-map-a", env)
        deadline = time.monotonic() + 15
        while not (control / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        expect((control / "pids").exists(), "the lens started a map build; tick said %r %r; git dir holds %r"
               % (t.stdout[-300:], t.stderr[-300:], sorted(p.name for p in gd.glob("uak-*"))[:40]))
        pids = [int(x) for line in (control / "pids").read_text().splitlines() for x in line.split()]
        deadline = time.monotonic() + 25
        while (any(alive(r, w, p) for p in pids) or (gd / "uak-map/symbols.tsv").exists()) and time.monotonic() < deadline:
            time.sleep(0.5)
        expect(not any(alive(r, w, p) for p in pids), "the killed map build is gone")
        expect(not (gd / "uak-map/symbols.tsv").exists() and not (gd / "uak-map/stamp").exists(),
               "a killed build leaves no partial index: %r" % list((gd / "uak-map").glob("*")))
        # A partial symbols.tsv without a stamp is not a built map: the lens starts a build.
        (gd / "uak-map").mkdir(exist_ok=True)
        (gd / "uak-map/symbols.tsv").write_text("x\tfunction\tREADME.md\t1\n", encoding="utf-8")
        stub_engine(r, w, map=LENS_STUB % 'echo "$0 $*" >> "$UAK_HUNG_DIR/jobs"')
        lens_tick(r, w, "s-map-b", env)
        deadline = time.monotonic() + 15
        while not (control / "jobs").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        expect((control / "jobs").exists() and "build" in (control / "jobs").read_text(),
               "an index without a stamp starts a build")
    finally:
        for p in pids:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(p)], cwd=w, allowed=None)
    settle_once(r, w)
    return "no partial index after a kill; an unstamped index is rebuilt"


def killed_tokens_publish_is_retried(r):
    """UAK-185 review: tokens --publish stamped before it ran, so a kill meant no retry for 30 minutes."""
    f, w = counted_fixture(r, "ss-tokens-kill")
    control = Path(r.scratch) / "ss-tokens-kill-control"
    control.mkdir()
    common = first_pending_dir(r, w)
    stub_engine(r, w, tokens=HANG)
    pids = []
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1", UAK_START_LIMIT="2", UAK_HUNG_DIR=control.as_posix())
        deadline = time.monotonic() + 15
        while not (control / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        pids = [int(x) for line in (control / "pids").read_text().splitlines() for x in line.split()]
        deadline = time.monotonic() + 25
        while (any(alive(r, w, p) for p in pids) or (common / "uak-tokens.published").exists()) and time.monotonic() < deadline:
            time.sleep(0.5)
        expect(not any(alive(r, w, p) for p in pids), "the killed tokens job is gone")
        expect(not (common / "uak-tokens.published").exists(), "a killed publish is not stamped as published")
    finally:
        for p in pids:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(p)], cwd=w, allowed=None)
    settle_once(r, w)
    return "a killed tokens --publish is retried at the next start"


def counter_files_are_validated(r):
    """UAK-185 review: `08` in a counter aborted the tick, and `a[$(cmd)]` in one ran cmd (arithmetic expansion)."""
    f, w = counted_fixture(r, "ss-counters")
    (w / "README.md").write_text("x\n", encoding="utf-8")
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    stub_engine(r, w, uak="exit 0", map="exit 0")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    project = w / ".uak/PROJECT.md"
    base = project.read_text(encoding="utf-8") if project.exists() else ""
    evil = "a[$(touch PWNED)]"
    try:
        for value in ("08", evil):
            coach = gd / "uak-coach-s-count"
            coach.mkdir(exist_ok=True)
            for name in ("calls", "explore", "fired.explore"):
                (coach / name).write_text(value + "\n", encoding="utf-8")
            (gd / "uak-inbox.poll").write_text(value + "\n", encoding="utf-8")
            project.write_text(base + "\nLease-Seconds: %s\n" % value, encoding="utf-8")
            out = lens_tick(r, w, "s-count", {})
            settle_once(r, w)
            expect(out.returncode == 0, "a counter holding %r does not abort the tick: %r" % (value, out.stderr[-300:]))
            expect(not (w / "PWNED").exists() and not (gd / "PWNED").exists(), "%r ran a command" % value)
            want = "9" if value == "08" else "1"   # 08 is eight, anything that is not digits starts again from 0
            expect((coach / "calls").read_text().strip() == want, "the call counter after %r is %r, not %s; tick said %r %r; "
                   "git dir %s holds %r" % (value, (coach / "calls").read_text(), want, out.stdout[-300:], out.stderr[-300:],
                                           gd, sorted(p.name for p in gd.glob("uak-*"))[:40]))
            poll = (gd / "uak-inbox.poll").read_text().strip()
            expect(poll.isdigit() and int(poll) > 10**9, "the tick went on to poll and stamped %r (held %r)" % (poll, value))
    finally:
        if base:
            project.write_text(base, encoding="utf-8")
    return "08 and a[$(cmd)] in counters, the poll stamp and Lease-Seconds: no abort, no command"



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


TESTS = [every_background_job_has_a_limit, limited_jobs_poll_coarsely, killed_map_build_is_not_a_built_map,
         killed_tokens_publish_is_retried, counter_files_are_validated]
TESTS += [killed_bb_flush_is_recovered_and_published_once, other_users_pending_file_is_left]
TESTS += [killed_flush_leaves_no_clone_on_windows, leftover_clone_is_removed_by_the_next_flush,
          second_start_leaves_a_live_flushs_clone, eight_starts_with_a_held_push_publish_once,
          unremovable_clone_is_retried_then_left_to_the_next_flush, clone_removal_stays_inside_the_clone_directories]


def main():
    return run_cases(TESTS, "SESSION_START_CLONES", "uak-ss-clones-")


if __name__ == "__main__":
    raise SystemExit(main())
