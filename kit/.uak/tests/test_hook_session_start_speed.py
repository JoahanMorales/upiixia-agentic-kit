#!/usr/bin/env python3
"""UAK-013: the session-start hook answers within 3 seconds. Claude Code's /doctor on Dylan's Mac (22 sessions over
18 days, 2026-11-11) measured the kit's SessionStart hook at about 9.5 s typical on startup, 12.6 s on resume and up
to 28 s: it waited for the network (`uak next --full`, the inbox read, `uak digest`) before every session could start.
A slow remote is simulated with remote.origin.uploadpack ('sleep N; git-upload-pack'), so no real network is used."""
import argparse
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
    while time.monotonic() < deadline:
        if not list(gd.glob("uak-start.*.running")):
            return
        time.sleep(0.25)
    raise AssertionError("a background refresh never finished within %d s" % seconds)


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
    _, out = start(r, w, "agent-1")
    settle(r, w)
    expect("UAK: agent=agent-1" in out, "the identity line is shown: " + out[:300])
    for line in expected:
        expect(line in out, "a fast remote shows the fresh `uak next` lines (%r) at once: %s" % (line, out[:600]))
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


TESTS = [session_start_returns_within_budget, session_start_output_is_unchanged]


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
