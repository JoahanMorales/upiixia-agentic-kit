#!/usr/bin/env python3
"""UAK-013: the session-start hook answers within 3 seconds. Claude Code's /doctor on Dylan's Mac (22 sessions over
18 days, 2026-11-11) measured the kit's SessionStart hook at about 9.5 s typical on startup, 12.6 s on resume and up
to 28 s: it waited for the network (`uak next --full`, the inbox read, `uak digest`) before every session could start.
A slow remote is simulated with remote.origin.uploadpack ('sleep N; git-upload-pack'), so no real network is used."""
import argparse
import json
import os
import time
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
    # No process works in the checkout any more (Windows refuses to rename a folder in use; the UAK-009 probe).
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
    while [ -f "$UAK_RACE_RUNNING" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
  fi;;
esac
''')
    r.run([r.bash, "-c", 'chmod +x "$1"', "_", head.as_posix()], cwd=w)
    real_head = r.run([r.bash, "-c", "type -P head"], cwd=w).stdout.strip()
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1", "UAK_RACE_HEAD": real_head,
           "UAK_RACE_RELEASE": release.as_posix(), "UAK_RACE_RUNNING": (gd / "uak-start.next.running").as_posix(),
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


TESTS = [session_start_returns_within_budget, session_start_output_is_unchanged,
         session_start_marks_only_the_inbox_snapshot_it_prints]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    import tempfile
    with tempfile.TemporaryDirectory(prefix="uak-ss-speed-") as tmp:
        r = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        failed = 0
        for test in TESTS:
            if args.case and test.__name__ not in args.case:
                continue
            began = time.monotonic()
            try:
                note = test(r)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - began))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:1500]))
    print("SESSION_START_SPEED_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
