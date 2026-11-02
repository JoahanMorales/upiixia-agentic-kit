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

from test_hack import Runner, expect, resolve_binary

TARGETS = {"next": 40, "status": 30, "heartbeat": 20}


def fixture(r, name):
    """12 tasks, 3 of them claimed by three agents: the state every call reads."""
    f = r.fixture(name, paths={"HACK-%03d" % i: "src/t%02d/" % i for i in range(1, 13)}, count=3)
    for i in range(3):
        f.claim(i, "HACK-%03d" % (i + 1))
    return f


def count(r, f, args):
    """Processes one uak call starts (a stub until the counter exists)."""
    return 10 ** 6


def check(r, command, args):
    f = fixture(r, "perf-" + command)
    n = count(r, f, args)
    expect(n <= TARGETS[command], "uak %s: expected: at most %d processes, got: %d" % (command, TARGETS[command], n))
    return n


def next_starts_at_most_40_processes(r):
    return check(r, "next", ["next"])


def status_starts_at_most_30_processes(r):
    return check(r, "status", ["status"])


def heartbeat_starts_at_most_20_processes(r):
    return check(r, "heartbeat", ["heartbeat", "HACK-001"])


TESTS = [next_starts_at_most_40_processes, status_starts_at_most_30_processes, heartbeat_starts_at_most_20_processes]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-claims-perf-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
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
