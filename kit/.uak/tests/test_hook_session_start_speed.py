#!/usr/bin/env python3
"""UAK-174: the session-start hook answers within 3 seconds. Claude Code's /doctor on Dylan's Mac (22 sessions over
18 days, 2026-11-11) measured the kit's SessionStart hook at about 9.5 s typical on startup, 12.6 s on resume and up
to 28 s: it waited for the network (`uak next --full`, the inbox read, `uak digest`) before every session could start.
A slow remote is simulated with remote.origin.uploadpack ('sleep N; git-upload-pack'), so no real network is used."""
import argparse
import json
import os
import re
import shutil
import time
from collections import Counter
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

BUDGET = 3.0
SLOW = 3


def start(r, cwd, agent=None, source="startup", **extra):
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": agent or ""}
    env.update(extra)
    payload = '{"session_id":"s-%s","source":"%s"}' % (source, source)
    began = time.monotonic()
    out = r.run([r.bash, "-c", "printf '%s' \"$1\" | bash .uak/bin/hook session-start", "_", payload],
                cwd=cwd, env=env, allowed=None)
    return time.monotonic() - began, out.stdout


def slow_remote(r, f, seconds=SLOW):
    for clone in set(f.clones):
        r.g(clone, "config", "remote.origin.uploadpack", "sleep %d; git-upload-pack" % seconds)


def fast_remote(r, f):
    for clone in set(f.clones):
        r.g(clone, "config", "--unset", "remote.origin.uploadpack", allowed=(0, 5))


def settle(r, cwd, seconds=40):
    """Wait, bounded, until no background refresh started by the hook is still running in this checkout."""
    gd = Path(r.g(cwd, "rev-parse", "--absolute-git-dir").stdout.strip())
    deadline = time.monotonic() + seconds
    while list(gd.glob("uak-start.*.running")):
        if time.monotonic() >= deadline:
            raise AssertionError("a background refresh never finished within %d s" % seconds)
        time.sleep(0.25)
    # No process works in the checkout any more (Windows refuses to rename a folder in use; the UAK-170 probe).
    probe = Path(str(cwd) + ".released")
    while True:
        try:
            os.rename(str(cwd), str(probe))
            os.rename(str(probe), str(cwd))
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise AssertionError("background processes still work in %s after %d s" % (cwd, seconds))
            time.sleep(0.25)


def session_start_returns_within_budget(r):
    f = r.fixture("ss-budget", count=1)
    f.claim(0, "HACK-001")
    slow_remote(r, f)
    w, main = f.worktrees[0], f.clones[0]
    for cwd, agent, what in ((w, "agent-1", "an agent's worktree"), (main, None, "the main checkout")):
        took, out = start(r, cwd, agent)
        expect(took < BUDGET, "session-start in %s took %.1f s with a slow remote (budget %.0f s): %s"
               % (what, took, BUDGET, out[-300:]))
        settle(r, cwd)
    took, _ = start(r, w, "agent-1", source="resume")
    expect(took < BUDGET, "resume took %.1f s (budget %.0f s)" % (took, BUDGET))
    settle(r, w)
    return "startup and resume under %.0f s with a %d s remote" % (BUDGET, SLOW)


def session_start_output_is_unchanged(r):
    f = r.fixture("ss-output", count=1)
    f.claim(0, "HACK-001")
    w = f.worktrees[0]
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1"}
    expected = r.run([r.bash, ".uak/bin/uak", "next", "--full"], cwd=w, env=env, allowed=None).stdout.splitlines()[:3]
    expect(expected, "uak next prints something for the fixture")
    # A first start shows the fresh lines when they arrive within the wait, or says where they are (slower machines,
    # Git Bash on Windows); the second start shows them either way, from the kept copy.
    _, out = start(r, w, "agent-1")
    settle(r, w)
    expect("UAK: agent=agent-1" in out, "the identity line is shown: " + out[:300])
    expect(all(line in out for line in expected) or "uak next" in out,
           "a first start shows the `uak next` lines or how to get them: " + out[:600])
    _, out = start(r, w, "agent-1")
    settle(r, w)
    for line in expected:
        expect(line in out, "a later start shows the `uak next` lines (%r) at once: %s" % (line, out[:600]))
    slow_remote(r, f)
    # A refresh that outlasts the wait (forced here with a 0.1 s wait) still shows the last lines, with a note.
    took, out = start(r, w, "agent-1", UAK_START_WAIT="1")
    expect(took < BUDGET, "a slow remote does not hold the session (%.1f s)" % took)
    for line in expected:
        expect(line in out, "a slow remote still shows the last `uak next` lines (%r): %s" % (line, out[:600]))
    expect("refreshing" in out, "the agent is told the list is being refreshed: " + out[:600])
    settle(r, w)
    fast_remote(r, f)
    return "identity, next and the refresh note"


def session_start_marks_only_the_inbox_snapshot_it_prints(r):
    """A refresh after the first inbox print must leave its unseen request for the next tick."""
    from test_hook_claims import hook

    f = r.fixture("ss-inbox-snapshot", count=2)
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")
    w = f.worktrees[0]
    (w / ".uak-env").write_bytes(b"UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    f.hack(1, "msg", "HACK-001", "first snapshot request", "--kind", "request", now=int(time.time()))
    first = f.hack(0, "inbox", "--peek", now=int(time.time())).stdout
    (gd / "uak-inbox.txt").write_bytes(first.encode("utf-8"))
    f.hack(1, "msg", "HACK-001", "second request must reach the next tick", "--kind", "request", now=int(time.time()))
    # The real inbox read waits until head has printed the old copy. Head then waits for that refresh to finish,
    # forcing the replacement between printing and recording shown-n without relying on runner speed.
    release = r.scratch / "ss-inbox-printed"
    b = w / ".uak/bin"
    (b / "uak").rename(b / "uak-real")
    (b / "uak").write_bytes(b'''#!/usr/bin/env bash
if [ "$1" = next ]; then printf 'Next: fixture task\\n'; exit 0; fi
if [ "$1" = inbox ]; then
  n=0
  while [ ! -e "$UAK_RACE_RELEASE" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
fi
exec bash "$(dirname "$0")/uak-real" "$@"
''')
    shim = r.scratch / "ss-inbox-shim"
    shim.mkdir()
    head = shim / "head"
    head.write_bytes(b'''#!/usr/bin/env bash
printed=$("$UAK_RACE_HEAD" "$@")
printf '%s\\n' "$printed"
case "$printed" in *'first snapshot request'*)
  if mkdir "$UAK_RACE_RELEASE" 2>/dev/null; then
    n=0
    while ! grep -q '^#2 ' "$UAK_RACE_INBOX" && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
  fi;;
esac
''')
    r.run([r.bash, "-c", 'chmod +x "$1"', "_", head.as_posix()], cwd=w)
    real_head = r.run([r.bash, "-c", "type -P head"], cwd=w).stdout.strip()
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1", "UAK_RACE_HEAD": real_head,
           "UAK_RACE_RELEASE": release.as_posix(), "UAK_RACE_INBOX": (gd / "uak-inbox.txt").as_posix(),
           "UAK_START_WAIT": "1"}
    # Build PATH in Bash from its physical POSIX directory: a native Windows drive/semicolon PATH must not hide the
    # extensionless shim. Prove selection before a background job waits on that shim's release barrier.
    prefix = 'shim_dir=$(CDPATH= cd -- "$1" && pwd -P) || exit 1; PATH="$shim_dir:$PATH"; export PATH; '
    setup = r.run([r.bash, "-c", prefix + 'printf "%s\\n" "$shim_dir/head"; command -v head; '
                   '[ -d "$(dirname "$UAK_RACE_RELEASE")" ]', "_", shim.as_posix()], cwd=w, env=env)
    paths = setup.stdout.splitlines()
    expect(len(paths) == 2 and paths[0] == paths[1], "the inbox race must select its head shim: %r" % paths)
    out = hook(r, w, ["-c", prefix + 'exec bash .uak/bin/hook session-start', "_", shim.as_posix()],
               json.dumps({"session_id": "s-resume", "source": "resume"}), env).stdout
    released = release.is_dir()
    if not released:
        release.mkdir()  # unblock cleanup before reporting a failed fault-injection precondition
    settle(r, w)
    expect(released, "the head shim must release the inbox refresh after printing: " + out[-500:])
    shown = (gd / "uak-inbox.shown-n").read_text(encoding="utf-8").strip()
    expect("#2 " in (gd / "uak-inbox.txt").read_text(encoding="utf-8"), "the real refresh loaded request #2")
    # Keep tick's unrelated network/pace jobs fresh so only the inbox delivery is exercised and Windows can clean up.
    for name in ("uak-inbox.poll", "uak-pace.seen", "uak-heartbeat", "uak-heartbeat.reviews"):
        (gd / name).write_bytes(b"%d\n" % int(time.time()))
    tick = hook(r, w, [".uak/bin/hook", "tick"], json.dumps({"session_id": "s-resume", "tool_name": "Bash",
                "tool_input": {"command": "true"}, "tool_response": {"stdout": "", "stderr": ""}}), env)
    observed = ("#1 " in out, "#2 " in out, shown, "#2 " in tick.stdout)
    expect(observed == (True, False, "1", True),
           "assertion failed: printed #1/#2, shown-n, next tick #2: %r" % (observed,))
    return "unseen refreshed request delivered on the next tick"


def refresh_fixture(r, name, body):
    """Run the actual refresh helpers in a real worktree, with barriers and waitable Bash child processes."""
    f = r.fixture("ss-owner-" + name, count=1)
    w = f.worktrees[0]
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    case_dir = r.scratch / ("ss-owner-control-" + name)
    case_dir.mkdir()
    (case_dir / "backend.sh").write_bytes(b'''#!/usr/bin/env bash
mode=$1 case_dir=$2 kind=$3
printf '%s\\n' "$mode" >> "$case_dir/backend-calls"
if [ "$mode" = OLD ]; then
  : > "$case_dir/old-ready"
  n=0
  while [ ! -f "$case_dir/release-old" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
fi
printf '%s: %s snapshot\\n' "$kind" "$mode"
[ "$mode" != OLD ] || : > "$case_dir/old-done"
''')
    source = (r.package / ".uak/bin/hook").read_text(encoding="utf-8")
    first = source.index("fresh() {")
    fresh = source[first:source.index("\n}\n", first) + 3]
    rd = next(line for line in source.splitlines() if line.startswith("rd() {"))
    first = source.index("# The inbox as tick keeps it:")
    helpers = source[first:source.index("# A small file's first line", first)]
    script = case_dir / "refresh.sh"
    script.write_bytes(('''set -u
gd=$1 case_dir=$2
NOW=$(date +%s)
NL='\n'
CR=$(printf '\\r')
''' + fresh + "\n" + rd + "\n" + helpers + '''
wait_file() {
  local n=0
  while [ ! -f "$1" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
  [ -f "$1" ] || { printf 'assertion failed: barrier missing: %s\\n' "$1" >&2; exit 1; }
}
age_refresh() {
  for marker in "$gd"/uak-start.next*.running; do
    [ -f "$marker" ] || continue
    { printf '%s\\n' "$((NOW - 121))"; sed '1d' "$marker"; } > "$case_dir/aged"
    cat "$case_dir/aged" > "$marker"
  done
}
trap 'for release in old new move claim backend handoff recovery; do : > "$case_dir/release-$release"; done; wait' EXIT
''' + body).encode("utf-8"))
    out = r.run([r.bash, script.as_posix(), gd.as_posix(), case_dir.as_posix()], cwd=w, allowed=None, timeout=180)
    expect(out.returncode == 0, "refresh harness: " + out.stdout[-1000:] + out.stderr[-1000:])
    # A killed owner's backend can outlive that owner briefly; Windows cannot remove its working directory yet.
    deadline = time.monotonic() + 40
    probe = Path(str(w) + ".released")
    while True:
        try:
            os.rename(str(w), str(probe))
            os.rename(str(probe), str(w))
            break
        except PermissionError:
            if time.monotonic() >= deadline:
                raise AssertionError("a refresh backend still holds its worktree after cleanup")
            time.sleep(0.25)
    return gd, case_dir


# UAK-177: on GitHub's Windows runners the 3 s budget failed at 3.1-3.2 s (a Git Bash process costs 20-50 ms), while
# the same SHAs passed elsewhere. The work session-start makes the agent wait for is counted instead of timed: shims
# on PATH log every external process while UAK_FG_LOG is set; each background launch in the hook clears it.
COUNTED = ("git", "bash", "awk", "sed", "grep", "head", "tail", "sort", "uniq", "cat", "tr", "cut", "date", "mkdir",
           "mktemp", "rm", "mv", "sleep", "find", "touch", "wc", "basename", "dirname", "cksum", "ls")
# At main a5f38f1 (with only the UAK_FG_LOG clears added) the hook launched these counted processes on this fixture
# before returning, measured on Bash 3.2 (macOS), the most: Bash 4+ reads the payload and the clock with builtins.
# UAK-177 asks for at most half of each.
STARTUP_BEFORE = 41
RESUME_BEFORE = 42


def real_bash(r):
    """The Bash that runs scripts. On Windows r.bash is Git's bin/bash.exe, a launcher that puts its own folders first
    on PATH, so a shim that called it would hide the other shims from the hook (UAK-177, Windows verification)."""
    if os.name != "nt":
        return r.bash
    return r.run([r.bash, "-c", 'cygpath -m "$(type -P bash)"']).stdout.strip() or r.bash


def shims(r, where):
    where.mkdir(parents=True, exist_ok=True)
    bash = real_bash(r)
    for name in COUNTED:
        real = bash if name == "bash" else r.git if name == "git" else shutil.which(name, path=r.env.get("PATH"))
        if not real:
            continue
        shim = where / name
        shim.write_text('#!/bin/sh\n[ -z "$UAK_FG_LOG" ] || echo %s >> "$UAK_FG_LOG"\nexec "%s" "$@"\n'
                        % (name, Path(real).as_posix()), encoding="utf-8")
        shim.chmod(0o755)
    return where


def counted_start(r, f, w, source, tag):
    """Processes session-start launches before it returns, by name; the remote answers only after the hook returned,
    so the bounded wait always runs to its end and the count does not depend on the runner's speed."""
    gate = Path(r.scratch) / ("gate-" + tag)
    if gate.exists():
        gate.unlink()
    for clone in set(f.clones):
        r.g(clone, "config", "remote.origin.uploadpack",
            "while [ ! -f '%s' ]; do sleep 0.1; done; git-upload-pack" % gate.as_posix())
    log = Path(r.scratch) / ("count-%s.log" % tag)
    log.write_text("", encoding="utf-8")
    shim_dir = shims(r, Path(r.scratch) / "count-shims")
    # No machine usage logs (UAK-173): the count is the same on every machine.
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1", "UAK_FG_LOG": log.as_posix(),
           "CODEX_HOME": str(Path(r.scratch) / "no-codex")}
    payload = '{"session_id":"s-%s","source":"%s"}' % (source, source)
    # PATH is built inside Bash from the shims' physical POSIX folder, as the inbox race test does: Git Bash's
    # launcher and a native Windows PATH would otherwise put /ucrt64/bin and /usr/bin first.
    prefix = 'shim_dir=$(CDPATH= cd -- "$1" && pwd -P) || exit 1; PATH="$shim_dir:$PATH"; export PATH; '
    try:
        r.run([r.bash, "-c", prefix + "printf '%s' \"$2\" | bash .uak/bin/hook session-start", "_",
               shim_dir.as_posix(), payload], cwd=w, env=env, allowed=None)
        before = [n for n in log.read_text(encoding="utf-8").split() if n]
        # Review of cdbb934 (P2): on Git Bash the shims logged nothing and the limits passed with 0. The hook always
        # runs git (rev-parse), so an empty count means the count is broken, never that the hook is fast.
        expect("git" in before, "the count saw the hook's own git call (shims on PATH and UAK_FG_LOG work here): %r"
               % before[:10])
    finally:
        # Opened whatever happened: a closed gate leaves upload-pack loops behind and Windows cannot clean up.
        gate.write_text("open\n", encoding="utf-8")
    settle(r, w)
    after = [n for n in log.read_text(encoding="utf-8").split() if n]
    expect(after == before, "no background work is counted (a launcher left UAK_FG_LOG set): %s"
           % Counter(after[len(before):]).most_common(6))
    return before


def counted_fixture(r, name):
    f = r.fixture(name, count=1)
    f.claim(0, "HACK-001")
    return f, f.worktrees[0]


def session_start_launches_half_the_processes_on_startup(r):
    f, w = counted_fixture(r, "ss-count-start")
    calls = counted_start(r, f, w, "startup", "startup")
    limit = (STARTUP_BEFORE or 0) // 2
    expect(STARTUP_BEFORE and len(calls) <= limit, "startup launched %d processes before returning (at most %s, half of %s): %s"
           % (len(calls), limit, STARTUP_BEFORE, Counter(calls).most_common(8)))
    return "%d processes (limit %d)" % (len(calls), limit)


def session_start_launches_half_the_processes_on_resume(r):
    f, w = counted_fixture(r, "ss-count-resume")
    counted_start(r, f, w, "startup", "first")
    calls = counted_start(r, f, w, "resume", "resume")
    limit = (RESUME_BEFORE or 0) // 2
    expect(RESUME_BEFORE and len(calls) <= limit, "resume launched %d processes before returning (at most %s, half of %s): %s"
           % (len(calls), limit, RESUME_BEFORE, Counter(calls).most_common(8)))
    return "%d processes (limit %d)" % (len(calls), limit)


def session_start_keeps_reporting_the_pace_level(r):
    """Review of cdbb934 (P2): a level that stays critical must still reach the agent when sessions are more than
    30 min apart. Before UAK-177 session start printed it every time; now it may come from the first tick instead."""
    f = r.fixture("ss-pace-level", count=1)
    f.claim(0, "HACK-001")
    w = f.worktrees[0]
    (w / ".uak/bin/pace").write_text('#!/usr/bin/env bash\ncase "${1:-}" in --caps) echo "critical 1 0";; '
                                     '*) echo "PACE critical: stop spending (test)";; esac\n', encoding="utf-8")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    (gd / "uak-pace.level").write_text("critical", encoding="utf-8")
    (gd / "uak-pace.start").write_text("%d\nPACE critical: an old reading\n" % (int(time.time()) - 7200), encoding="utf-8")
    took, out = start(r, w, "agent-1", UAK_START_WAIT="1")
    settle(r, w)
    seen = "PACE critical" in out
    for _ in range(2):
        if seen:
            break
        for name in ("uak-pace.seen", "uak-inbox.poll"):
            if (gd / name).exists():
                (gd / name).unlink()
        tick = r.run([r.bash, "-c", "printf '%s' '{\"session_id\":\"s-pace\"}' | bash .uak/bin/hook tick"], cwd=w,
                     env={"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1"}, allowed=None)
        seen = "PACE critical" in tick.stdout
        settle(r, w)
    expect(seen, "a critical pace level reaches the agent at session start or its first tick: start printed %r"
           % out[-400:])
    return "critical level reported"


def alive(r, cwd, pid):
    """Whether this PID still runs, asked of Bash so that a Git Bash PID on Windows means the same thing."""
    return r.run([r.bash, "-c", 'kill -0 "$1" 2>/dev/null', "_", str(pid)], cwd=cwd, allowed=None).returncode == 0


def stub_engine(r, w, **bodies):
    """Replace engine scripts of the worktree by small stubs: NAME -> Bash body."""
    b = w / ".uak/bin"
    for name, body in bodies.items():
        (b / name).write_bytes(("#!/usr/bin/env bash\n" + body + "\n").encode("utf-8"))


def hook_functions(r, w, *names):
    """The text of these hook functions, as the hook defines them, so a small Bash harness can run them without a
    whole session start. A name the hook does not define yet is left out (the test then fails on what it checks)."""
    text = (w / ".uak/bin/hook").read_text(encoding="utf-8")
    found = []
    for name in names:
        m = re.search(r"^%s\(\) \{.*?^\}$|^%s\(\) \{.*\}$" % (name, name), text, re.S | re.M)
        if m:
            found.append(m.group(0))
    return "\n".join(found)


def settle_once(r, w, seconds=40):
    """Also wait for the single-flight jobs (pace, map build), which settle() does not see."""
    settle(r, w, seconds)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    deadline = time.monotonic() + seconds
    while list(gd.glob("uak-once.*.running")):
        expect(time.monotonic() < deadline, "a pace or map build job never finished within %d s" % seconds)
        time.sleep(0.25)
    settle(r, w, seconds)


def cached_copy_always_says_its_age(r):
    """UAK-185: the age of a cached copy was said only while a refresh ran. Now whenever the copy is shown, and a
    copy without a (usable) time file says "age unknown"."""
    f, w = counted_fixture(r, "ss-age")
    gd = Path(r.scratch) / "ss-age-gd"
    gd.mkdir()
    (gd / "uak-start.next.txt").write_text("Next: copy\n", encoding="utf-8")
    script = Path(r.scratch) / "show.sh"
    script.write_text("NOW=$(date +%s)\n" + hook_functions(r, w, "epoch_age", "start_once_live", "start_busy", "start_show")
                      + '\ngd=$1\nstart_show next 18 next\n', encoding="utf-8")
    now = int(time.time())
    for value, want in ((str(now - 42), r"\b4[2-9] s ago"), (None, "age unknown"), ("", "age unknown"),
                        ("abc", "age unknown"), (str(now + 3600), "age unknown"), ("9" * 20, "age unknown"),
                        ("08", "age unknown"), ("0", "age unknown")):
        at = gd / "uak-start.next.at"
        if at.exists():
            at.unlink()
        if value is not None:
            at.write_text(value + "\n", encoding="utf-8")
        out = r.run([r.bash, script.as_posix(), gd.as_posix()], cwd=w, allowed=None)
        expect("Next: copy" in out.stdout and re.search(want, out.stdout) and not re.search(r"-\d+ s", out.stdout),
               "with the time file %r, a shown copy (no refresh running) says its age (%s): %r %r"
               % (value, want, out.stdout, out.stderr[:200]))
    # And in the real hook: a copy with no time file next to it, shown while the refresh (3 s) runs.
    control = Path(r.scratch) / "ss-age-control"
    control.mkdir()
    stub_engine(r, w, uak='case "$1" in next) sleep 3; echo "Next: stub";; esac')
    real = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    (real / "uak-start.next.txt").write_text("Next: old copy\n", encoding="utf-8")
    _, out = start(r, w, "agent-1", UAK_START_WAIT="1")
    settle_once(r, w)
    expect("Next: old copy" in out and "age unknown" in out, "a copy without a time file says so: " + out[-500:])
    return "age said with and without a refresh; a copy without a time file says age unknown"


TESTS = [session_start_returns_within_budget, session_start_output_is_unchanged,
         session_start_marks_only_the_inbox_snapshot_it_prints, session_start_launches_half_the_processes_on_startup,
         session_start_launches_half_the_processes_on_resume, session_start_keeps_reporting_the_pace_level]
TESTS += [cached_copy_always_says_its_age]
# UAK-197: this file took 339 to 536 s on Windows, over the 300 s under which a failed file runs again in its job. Its
# cases moved unchanged to two files: locks, refresh owners and simultaneous starts to test_hook_session_start_locks.py;
# the black box flush's clones and the jobs killed at their limit to test_hook_session_start_clones.py.


# UAK-197: windows (3) of run 45645537660 (job 139315504846) ended with exit code 3840 and no FAIL line while this file
# (then one file with test_hook_session_start_locks.py) ran: 3840 = 15 << 8, which MSYS reports for a Bash ended by
# SIGTERM, so the step's own Bash most likely got a TERM. The only TERM these files cause is start_kill_tree in the hook
# (kit/.uak/bin/hook, `kill -TERM` per PID of a job's tree, listed with pgrep or `ps -e` on Git Bash) and the cleanup
# `kill -KILL` of PIDs the cases recorded. Reading the code found no line that can name the step's Bash: no `kill 0`,
# no negative PID, no empty variable in a kill line (every kill quotes one PID read from `$!`, a pid file or a ps column
# filtered to digits). Not found: whether a PID the tree listing returns on Git Bash can be one this test did not start
# (PID reuse, or a parent PID MSYS reports for processes started by a native Windows program). So every Bash these files
# start sources KILL_GUARD (BASH_ENV): a signal to one of the test's own ancestors (the CI step's Bash among them), to
# PID 0 or to a process group is refused and written down with the script and function that sent it, the file fails
# naming it, and every other signal is written down and sent. A mitigation and a detector, not a fix of a found cause.
KILL_GUARD = r"""# BASH_ENV of test_hook_session_start_speed/_locks (UAK-197): every signal goes through here; see KILL_GUARD there.
kill_guard_started() { # PID [MSYS STIME]: KG_STARTED = the epoch the process started; fails when it cannot be told
  local et= d=0 a= b= c= now=
  KG_STARTED=
  if [ -n "${UAK_KILL_GUARD_WINPIDS:-}" ]; then
    # Git Bash's ps gives STIME: HH:MM:SS for a process of today, a date for an older one (started before the test).
    case "${2:-}" in
      [0-9][0-9]:[0-9][0-9]:[0-9][0-9]) KG_STARTED=$(date -d "$2" +%s 2>/dev/null) || return 1;;
      '') return 1;;
      *) KG_STARTED=0;;
    esac
    return 0
  fi
  et=$(ps -o etime= -p "$1" 2>/dev/null) || return 1
  et=${et// /}
  [ -n "$et" ] || return 1
  case "$et" in *-*) d=${et%%-*}; et=${et#*-};; esac
  IFS=: read -r a b c <<KGEOF
$et
KGEOF
  if [ -z "$c" ]; then c=$b; b=$a; a=0; fi
  now=$(date +%s)
  KG_STARTED=$((now - ((10#$d * 24 + 10#$a) * 60 + 10#$b) * 60 - 10#$c))
}
kill() {
  local first=${1:-} opt= targets= refused= t= rc=0 line= seen=
  case "$first" in -0|-s0|-l|-L) builtin kill "$@"; return;; esac
  if [ "$first" = -s ] && [ "${2:-}" = 0 ]; then builtin kill "$@"; return; fi
  case "$first" in -s|-n) opt="$1 ${2:-}"; shift; shift;; -[A-Za-z0-9]*) opt=$1; shift;; esac
  if [ "${1:-}" = "--" ]; then shift; fi
  local all="$*"
  for t in $all; do
    case "$t" in
      0|-*) refused="$refused $t";;
      *[!0-9]*|'') targets="$targets $t";;
      *) case " ${UAK_KILL_GUARD_PIDS:-} " in *" $t "*) refused="$refused $t"; continue;; esac
         # Git Bash: the Windows process an MSYS PID stands for (`ps -p`: [flag] PID PPID PGID WINPID ...). A signal whose
         # target is one of the test's ancestors under another MSYS PID (a stale or reused entry) is refused too; the ps
         # line of every target is written down.
         if [ -n "${UAK_KILL_GUARD_WINPIDS:-}" ]; then
           line=$(ps -p "$t" 2>/dev/null); line=${line##*$'\n'}
           case "$line" in *PID*PPID*) line=;; esac   # the header alone: no such process any more
           set -- $line
           case "${1:-}" in [0-9]*) ;; *) [ "$#" -eq 0 ] || shift;; esac
           seen="$seen [$t: ${line:-no such process}]"
           case " $UAK_KILL_GUARD_WINPIDS " in *" ${4:-x} "*) refused="$refused $t(winpid ${4})"; continue;; esac
         fi
         # Only a process started after this test file began may get a signal: a PID that names an older process (an
         # ancestor, the human's session, a PID reused by something else) is refused.
         if [ -n "${UAK_KILL_GUARD_SINCE:-}" ] && kill_guard_started "$t" "${7:-}" && [ "$KG_STARTED" -lt $((UAK_KILL_GUARD_SINCE - 2)) ]; then
           refused="$refused $t(started $((UAK_KILL_GUARD_SINCE - KG_STARTED)) s before the test)"; continue
         fi
         targets="$targets $t";;
    esac
  done
  if [ -n "$refused" ]; then
    printf 'REFUSED kill %s%s from %s %s (pid %s)%s\n' "${opt:--TERM}" "$refused" "${0##*/}" "${FUNCNAME[1]:-main}" "$$" "$seen" >> "${UAK_KILL_GUARD_LOG:-/dev/null}"
    rc=1
  fi
  if [ -z "$targets" ]; then return "$rc"; fi
  printf 'SENT kill %s%s from %s %s%s\n' "${opt:--TERM}" "$targets" "${0##*/}" "${FUNCNAME[1]:-main}" "$seen" >> "${UAK_KILL_GUARD_LOG:-/dev/null}"
  if [ -n "${UAK_KILL_GUARD_DRY:-}" ]; then return "$rc"; fi   # the guard's own test: written down, never sent
  builtin kill $opt $targets || return
  return "$rc"
}
"""


def ancestors():
    """PIDs of this process and its ancestors, as a Bash `kill` would name them: on Git Bash both the Windows PIDs of the
    chain (Toolhelp snapshot) and the MSYS PIDs whose WINPID is one of them (`ps -e`)."""
    import subprocess
    chain, pid = [], os.getpid()
    if os.name != "nt":
        while pid > 1 and pid not in chain and len(chain) < 64:
            chain.append(pid)
            out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
            pid = int(out) if out.isdigit() else 0
        return chain
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    parent, e = {}, Entry()
    e.dwSize = ctypes.sizeof(Entry)
    ok = k32.Process32First(snap, ctypes.byref(e))
    while ok:
        parent[e.th32ProcessID] = e.th32ParentProcessID
        ok = k32.Process32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    while pid and pid not in chain and len(chain) < 64:
        chain.append(pid)
        pid = parent.get(pid, 0)
    ancestors.winpids = list(chain)
    msys = []
    bash = resolve_binary("bash")
    listing = subprocess.run([bash, "-c", "ps -e"], capture_output=True, text=True).stdout
    for line in listing.splitlines():
        cols = line.split()
        if cols and not cols[0].isdigit():
            cols = cols[1:]
        if len(cols) >= 4 and cols[0].isdigit() and cols[3].isdigit() and int(cols[3]) in chain:
            msys.append(int(cols[0]))
    return chain + msys


def kill_guard(r):
    """Install KILL_GUARD for every Bash this test starts (the Runner's env and os.environ, for Popen); returns the log."""
    guard, log = Path(r.scratch) / "kill-guard.sh", Path(r.scratch) / "kill-guard.log"
    guard.write_text(KILL_GUARD, encoding="utf-8")
    log.write_text("", encoding="utf-8")
    env = {"BASH_ENV": guard.as_posix(), "UAK_KILL_GUARD_LOG": log.as_posix(),
           "UAK_KILL_GUARD_PIDS": " ".join(str(p) for p in sorted(set(ancestors()))),
           "UAK_KILL_GUARD_SINCE": str(int(time.time()))}
    if os.name == "nt":
        env["UAK_KILL_GUARD_WINPIDS"] = " ".join(str(p) for p in getattr(ancestors, "winpids", []))
    print("KILL_GUARD protects %s (Windows PIDs of the chain: %s)" % (env["UAK_KILL_GUARD_PIDS"], env.get("UAK_KILL_GUARD_WINPIDS", "-")),
          flush=True)
    os.environ.update(env)
    r.env.update(env)
    return log


def stream_kill_log(log, stop):
    """Print each line the guard writes as it comes (flushed): a run whose step dies still shows the last signals."""
    import threading

    def follow():
        done = 0
        while True:
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            lines = text.splitlines()
            if len(lines) < done:      # the guard's own case puts the log back as it was
                done = len(lines)
            for line in lines[done:]:
                print("KILL_GUARD " + line[:600], flush=True)
            done = len(lines)
            if stop.wait(0.2):
                return
    t = threading.Thread(target=follow, daemon=True)
    t.start()
    return t


def kill_guard_report(log):
    """(line to print, refused lines): what the Bashes of this file signalled."""
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    refused = [l for l in lines if l.startswith("REFUSED")]
    sent = [l for l in lines if l.startswith("SENT")]
    by = Counter(" ".join(l.split(" [")[0].split()[2:3] + l.split(" [")[0].split()[-2:]) for l in sent)
    return ("KILL_GUARD sent=%d refused=%d protected=%s; signals sent: %s" % (
        len(sent), len(refused), os.environ.get("UAK_KILL_GUARD_PIDS", ""), dict(by.most_common(8)))), refused


def kill_guard_refuses_an_ancestor(r):
    """UAK-197: the guard every Bash of these files sources refuses a signal to a protected process (an ancestor of the
    test in a real run), to PID 0 and to a process group, writes it down, and still sends every other signal. Forced with
    processes this case starts: its own `victim` stands for a protected ancestor, and the refused kills run with
    UAK_KILL_GUARD_DRY set, so a broken guard would only write SENT, never signal anything."""
    import subprocess
    log = Path(os.environ.get("UAK_KILL_GUARD_LOG", ""))
    expect(os.environ.get("BASH_ENV") and log.is_file(), "the guard is installed for this file's Bashes")
    before = log.read_text(encoding="utf-8", errors="replace")
    procs = [subprocess.Popen([r.bash, "-c", "echo $$; exec sleep 60"], stdout=subprocess.PIPE, text=True) for _ in range(2)]
    victim, other = (p.stdout.readline().strip() for p in procs)
    try:
        dry = r.run([r.bash, "-c", 'kill -TERM "$1"; echo "a=$?"; kill -TERM 0; echo "b=$?"; kill -TERM -- -"$1"; echo "c=$?"', "_",
                     victim], env={"UAK_KILL_GUARD_PIDS": victim, "UAK_KILL_GUARD_DRY": "1"}, allowed=None)
        # Git Bash's view, forced with a ps that answers as MSYS does: the target's WINPID is a protected Windows PID.
        msys = r.run([r.bash, "-c", 'ps() { printf "      PID    PPID    PGID     WINPID   TTY         UID    STIME COMMAND\\n'
                      'I    %s       1    %s       4242  cons0     197108 10:00:00 /usr/bin/sleep\\n" "$2" "$2"; }; '
                      'kill -TERM "$1"; echo "f=$?"', "_", other],
                     env={"UAK_KILL_GUARD_PIDS": "", "UAK_KILL_GUARD_WINPIDS": "4242", "UAK_KILL_GUARD_DRY": "1"}, allowed=None)
        # A process older than the test file (forced: the file "began" 100 s from now) is refused, whatever its PID.
        older = r.run([r.bash, "-c", 'kill -TERM "$1"; echo "g=$?"', "_", other],
                      env={"UAK_KILL_GUARD_PIDS": "", "UAK_KILL_GUARD_SINCE": str(int(time.time()) + 100), "UAK_KILL_GUARD_DRY": "1"},
                      allowed=None)
        real = r.run([r.bash, "-c", 'kill -0 "$1"; echo "d=$?"; kill -KILL "$2"; echo "e=$?"', "_", victim, other],
                     env={"UAK_KILL_GUARD_PIDS": victim}, allowed=None)
        procs[1].wait(timeout=20)
        victim_alive = procs[0].poll() is None
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=20)
            p.stdout.close()
    new = log.read_text(encoding="utf-8", errors="replace")[len(before):].splitlines()
    log.write_text(before, encoding="utf-8")   # the forced refusals are this case's, not the file's
    expect(all(x in dry.stdout for x in ("a=1", "b=1", "c=1")), "refused kills fail: %r" % dry.stdout)
    expect("d=0" in real.stdout and "e=0" in real.stdout, "kill -0 and a kill of another process work: %r" % real.stdout)
    refused = [l for l in new if l.startswith("REFUSED")]
    expect(len(refused) >= 4 and " %s " % victim in refused[0] + " " and " 0 " in refused[1] + " " and "-" + victim in refused[2],
           "the refusals are written down, with the target: %r" % new)
    expect("f=1" in msys.stdout and "%s(winpid 4242)" % other in refused[3] and "/usr/bin/sleep" in refused[3],
           "a target whose Windows PID is protected is refused, its ps line written down: %r %r" % (msys.stdout, refused[3:]))
    expect("g=1" in older.stdout and len(refused) == 5 and "%s(started" % other in refused[4] and "before the test)" in refused[4],
           "a process older than the test is refused: %r %r" % (older.stdout, refused[4:]))
    expect(not [l for l in new if l.startswith("SENT") and victim in l], "nothing was sent to the protected process: %r" % new)
    expect(any(l.startswith("SENT kill -KILL %s" % other) for l in new), "the allowed kill is written down: %r" % new)
    expect(victim_alive and procs[1].returncode is not None, "the protected process lives, the other got its signal")
    return "a protected PID, PID 0, a group, a protected Windows PID and an older process refused; another process killed"


def run_cases(tests, label, prefix):
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    import tempfile
    with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
        r = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        log = kill_guard(r)
        import threading
        stop = threading.Event()
        follower = stream_kill_log(log, stop)
        # UAK_SS_REPEAT=CASE:N[,CASE:N] runs those cases N times in a row, each round in a scratch folder of its own
        # (UAK-197: the 20 runs in a row a fix is judged by, opt-in; off by default).
        repeat = dict(x.partition(":")[::2] for x in os.environ.get("UAK_SS_REPEAT", "").split(",") if ":" in x)
        failed = 0
        for test in tests:
            if args.case and test.__name__ not in args.case:
                continue
            rounds = int(repeat[test.__name__]) if repeat.get(test.__name__, "").isdigit() else 1
            for k in range(rounds):
                here = r if k == 0 else Runner(r.package, Path(tmp) / ("round-%d" % (k + 1)), r.bash, r.git)
                shown = test.__name__ + (" round %d of %d" % (k + 1, rounds) if rounds > 1 else "")
                began = time.monotonic()
                try:
                    note = test(here)
                    print("PASS %s (%s, %.2fs)" % (shown, note, time.monotonic() - began), flush=True)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print("FAIL %s (%s)" % (shown, str(exc)[:1500]), flush=True)
        stop.set()
        follower.join(5)
        line, refused = kill_guard_report(log)
        print(line)
        if refused:
            failed += 1
            print("FAIL kill_guard (a Bash of this file signalled an ancestor of the test, PID 0 or a group: %s)" % refused[:5])
    print("%s_RESULT %s failed=%d" % (label, "PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


TESTS += [kill_guard_refuses_an_ancestor]


def main():
    return run_cases(TESTS, "SESSION_START_SPEED", "uak-ss-speed-")


if __name__ == "__main__":
    raise SystemExit(main())
