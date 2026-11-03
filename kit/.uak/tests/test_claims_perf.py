#!/usr/bin/env python3
"""The claims redesign's targets, as tests: the processes `uak next`, `uak status` and `uak heartbeat` start.
On Git Bash a process costs 20-50 ms and `next` started about 220 of them: 4-8 s per call on a Windows laptop
(docs/ROADMAP.md, "Next"). The targets are the assertions; the redesign (UAK-002 … UAK-006) turns them green.
Real Git, a local bare remote, 12 tasks and 3 live claims."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Failure, Runner, expect, resolve_binary
from test_v592 import bash_major, processes, shims

TARGETS = {"next": 40, "status": 30, "heartbeat": 20}
# Expected to fail until the redesign lands; UAK-006 empties this set. Strict: a test in it that meets its target
# fails, so the set never hides a win. Nothing here is skipped: every count runs and is printed.
XFAIL = {"next_starts_at_most_40_processes", "status_starts_at_most_30_processes", "heartbeat_starts_at_most_20_processes"}


def fixture(r, name):
    """12 tasks, 3 of them claimed by three agents: the state every call reads."""
    f = r.fixture(name, paths={"HACK-%03d" % i: "src/t%02d/" % i for i in range(1, 13)}, count=3)
    for i in range(3):
        f.claim(i, "HACK-%03d" % (i + 1))
    return f


def count(r, f, args):
    """Processes one uak call starts, with test_v592's counter: every program runs through a traced shim, so each
    process leaves its own PID (bash 3.2 has no $BASHPID: there it counts 0). The second call is measured: the first
    one of a fresh clone also writes its session file."""
    env = {"UAK_AGENT": "agent-1", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000060", "UAK_DEDUPE": "off"}
    r.run([r.bash, ".uak/bin/uak"] + args, cwd=f.worktrees[0], env=env)
    n, out = processes(r, f.worktrees[0], [".uak/bin/uak"] + args, "", env)
    expect(out.returncode == 0, "uak %s failed: %s" % (" ".join(args), (out.stdout + out.stderr)[-400:]))
    return n


def check(r, name, command, args):
    f = fixture(r, "perf-" + command)
    n = count(r, f, args)
    if bash_major(r) < 4:
        return "not counted on bash %d (no $BASHPID); Linux and Windows count" % bash_major(r)
    try:
        expect(n <= TARGETS[command], "uak %s: expected: at most %d processes, got: %d" % (command, TARGETS[command], n))
    except Failure as exc:
        if name in XFAIL:
            return "XFAIL %s" % exc
        raise
    expect(name not in XFAIL, "uak %s: %d processes meets its target of %d: take %s out of XFAIL" % (command, n, TARGETS[command], name))
    return "%d processes (target %d)" % (n, TARGETS[command])


def next_starts_at_most_40_processes(r):
    return check(r, "next_starts_at_most_40_processes", "next", ["next"])


def status_starts_at_most_30_processes(r):
    return check(r, "status_starts_at_most_30_processes", "status", ["status"])


def heartbeat_starts_at_most_20_processes(r):
    return check(r, "heartbeat_starts_at_most_20_processes", "heartbeat", ["heartbeat", "HACK-001"])


TESTS = [next_starts_at_most_40_processes, status_starts_at_most_30_processes, heartbeat_starts_at_most_20_processes]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-claims-perf-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        shims(runner)  # once, before the threads: three of them creating it at once would race
        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("CLAIMS_PERF_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
