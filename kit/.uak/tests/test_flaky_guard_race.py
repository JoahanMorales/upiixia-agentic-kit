#!/usr/bin/env python3
"""UAK-150: the second half of test_flaky_guard.py, so no single file takes a whole Windows shard.

  twenty_runs_under_load             each of the three tests of test_flaky_guard (picker, mcp, lease) passes 20 times in a
                                     row beside CPU hogs (skipped only when UAK_SMOKE_FAST=1)

Why a file of its own: test_flaky_guard.py took 1500 s on Windows (11 samples, 1232 to 1628 s) and 508 s on macOS, alone in a
shard 15 s under its planned limit. The per-case seconds of a Windows job (run 45073300004) showed the renewer race is not
the long part (3 s): twenty_runs_under_load is (898 s of that run's 1050 s), so it is what moved here, with the same
`RUNS = 20`; the other four cases (the renewer race with `RACE_RUNS = 60` among them) stay in test_flaky_guard.py.
The helpers (picker_once, mcp_once, lease_once, sh, expect) are imported from there, not copied.
Standard library only. Run: python3 kit/.uak/tests/test_flaky_guard_race.py [--case NAME]."""
import argparse
import concurrent.futures
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_flaky_guard import MCP_TEST, POOL_WORKERS, RUNS, expect, hog_count, lease_once, make_pool, mcp_once, picker_once, start_hog  # noqa: E402


def twenty_runs_under_load():
    if os.environ.get("UAK_SMOKE_FAST") == "1":
        return "skipped: UAK_SMOKE_FAST=1"
    jobs = [("lease", lease_once)] * RUNS + [("mcp", mcp_once)] * RUNS + [("picker", picker_once)] * RUNS
    if not MCP_TEST.is_file():
        jobs = [j for j in jobs if j[0] != "mcp"]
    hogs = [start_hog() for _ in range(hog_count())]
    started, failures = time.time(), []
    try:
        with make_pool(POOL_WORKERS) as pool:
            futures = {pool.submit(fn): (i, name) for i, (name, fn) in enumerate(jobs)}
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as exc:  # noqa: BLE001
                    failures.append("%s #%d: %s" % (futures[f][1], futures[f][0], str(exc)[:400]))
    finally:
        for h in hogs:
            h.kill()
            h.wait()
    expect(not failures, "%d of %d runs failed under load: %s" % (len(failures), len(jobs), " | ".join(failures[:3])))
    return "%d runs green beside %d CPU hogs in %d s" % (len(jobs), len(hogs), time.time() - started)


TESTS = [twenty_runs_under_load]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--package")  # smoke passes it to every test; this one reads its own tree
    args = parser.parse_args()
    failed = 0
    for t in [t for t in TESTS if not args.case or t.__name__ == args.case]:
        try:
            print("PASS %s (%s)" % (t.__name__, t()), flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]), flush=True)
    print("FLAKY_GUARD_RACE_RESULT %s" % ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
