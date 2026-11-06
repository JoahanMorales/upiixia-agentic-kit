#!/usr/bin/env python3
"""UAK-017: `uak next` hid an AVAILABLE task when a task listed before it in the backlog depended on it.
coord_next's prefilter (uak-coordination) is one awk program: it reads each dependency's state as `st[x]`, and in awk
reading an array element creates it. A task with no claims record yet (never claimed) then looked like it had a
state, "", and the later `t in st && st[t] != "AVAILABLE"` dropped it: neither offered nor counted as waiting.
Found when UAK-006 (listed first) came to depend on UAK-015 and UAK-016: next said "No eligible candidate".
Real Git, a local bare remote."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

NOW = 1000060


def next_for(f, index):
    out = f.hack(index, "next", "--full", now=NOW, allowed=None)
    expect(out.returncode == 0, "uak next failed: %s" % (out.stdout + out.stderr)[-600:])
    return out.stdout


def a_dependency_listed_later_is_still_offered(r):
    """HACK-001 (first) depends on HACK-002, which nobody has claimed: next offers HACK-002, not HACK-003."""
    f = r.fixture("prefilter-later", paths={"HACK-001": "src/a/", "HACK-002": "src/b/", "HACK-003": "src/c/",
                                            "HACK-004": "src/d/"},
                  count=2, dependencies={"HACK-001": "HACK-002"})
    f.claim(1, "HACK-004")  # the claims branch exists, and HACK-002 still has no record
    out = next_for(f, 0)
    expect("HACK-002 | AVAILABLE | P0" in out,
           "next must offer HACK-002, the dependency of HACK-001 that comes later in the backlog; got:\n%s" % out[:800])
    return out.splitlines()[0]


def the_dependent_still_waits(r):
    """HACK-001 needs HACK-002, HACK-002 needs HACK-003, HACK-003 is CLAIMED by someone else: no candidate, and next
    counts both waiting tasks; HACK-002 (no record, listed after its dependent) was dropped from the count."""
    f = r.fixture("prefilter-waits", paths={"HACK-001": "src/a/", "HACK-002": "src/b/", "HACK-003": "src/c/"},
                  count=2, dependencies={"HACK-001": "HACK-002", "HACK-002": "HACK-003"})
    f.claim(1, "HACK-003")
    out = next_for(f, 0)
    expect("No eligible candidate" in out, "nothing is eligible; got:\n%s" % out[:800])
    expect("HACK-001 | AVAILABLE" not in out and "HACK-002 | AVAILABLE" not in out,
           "a task with a dependency not INTEGRATED must not be offered; got:\n%s" % out[:800])
    expect("Waiting on dependencies: 2 task(s); HACK-001 waits on HACK-002 (AVAILABLE)." in out,
           "expected: both HACK-001 and HACK-002 waiting, HACK-001 on HACK-002 (AVAILABLE); got:\n%s" % out[:800])
    return "2 waiting"


def closed_tasks_are_never_offered(r):
    """A CLAIMED or CANCELLED task stays out of next, also when a task listed before it depends on it (the path that
    now reads a dependency's state without creating it)."""
    f = r.fixture("prefilter-closed", paths={"HACK-001": "src/a/", "HACK-002": "src/b/", "HACK-003": "src/c/",
                                             "HACK-004": "src/d/", "HACK-005": "src/e/"},
                  count=3, dependencies={"HACK-001": "HACK-002, HACK-003"})
    f.claim(1, "HACK-002")
    f.claim(2, "HACK-003")
    f.hack(2, "release", "HACK-003", "--cancel", "not needed", now=NOW)
    out = next_for(f, 0)
    for task in ("HACK-001", "HACK-002", "HACK-003"):
        expect("%s | AVAILABLE" % task not in out, "%s must not be offered; got:\n%s" % (task, out[:800]))
    expect("HACK-004 | AVAILABLE | P0" in out, "next must offer HACK-004, the first open task; got:\n%s" % out[:800])
    return out.splitlines()[0]


def a_task_in_review_is_never_offered(r):
    """REVIEW too (kit-r1 on d8abec4: the tests left it out): HACK-002 waits on its review, and HACK-001, listed
    first, depends on it; next offers neither and moves on to HACK-003."""
    f = r.fixture("prefilter-review", paths={"HACK-001": "src/a/", "HACK-002": "src/b/", "HACK-003": "src/c/"},
                  count=2, dependencies={"HACK-001": "HACK-002"})
    f.claim(1, "HACK-002")
    f.hack(1, "done", "HACK-002", "--pr", "https://example.invalid/pull/2", "--evidence", "fixture",
           "--no-red", "fixture task", now=NOW)
    expect("State: REVIEW" in f.show("tasks/HACK-002.md"), "HACK-002 must be in REVIEW: %s" % f.show("tasks/HACK-002.md")[:400])
    out = next_for(f, 0)
    for task in ("HACK-001", "HACK-002"):
        expect("%s | AVAILABLE" % task not in out, "%s must not be offered; got:\n%s" % (task, out[:800]))
    expect("HACK-003 | AVAILABLE | P0" in out, "next must offer HACK-003; got:\n%s" % out[:800])
    return out.splitlines()[0]


TESTS = [a_dependency_listed_later_is_still_offered, the_dependent_still_waits, closed_tasks_are_never_offered,
         a_task_in_review_is_never_offered]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-next-prefilter-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        tests = [t for t in TESTS if not args.case or t.__name__ in args.case]

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("NEXT_PREFILTER_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
