#!/usr/bin/env python3
"""UAK-150: the second half of test_flaky_guard.py, so no single file takes a whole Windows shard.

  twenty_lease_runs_under_load       gate_and_lease passes 20 times in a pool of 4 beside CPU hogs, with mcp and picker runs
                                     as background (skipped only when UAK_SMOKE_FAST=1)

UAK-151 split the former twenty_runs_under_load by kind: picker and mcp are in test_flaky_guard.py, lease is here.

Why a file of its own: test_flaky_guard.py took 1500 s on Windows (11 samples, 1232 to 1628 s) and 508 s on macOS, alone in a
shard 15 s under its planned limit. The per-case seconds of a Windows job (run 45073300004) showed the renewer race is not
the long part (3 s): twenty_runs_under_load was (898 s of that run's 1050 s), so it is what moved here, with the same
`RUNS = 20`; the other four cases (the renewer race with `RACE_RUNS = 60` among them) stay in test_flaky_guard.py.
The helpers (picker_once, mcp_once, lease_once, sh, expect) are imported from there, not copied.
Standard library only. Run: python3 kit/.uak/tests/test_flaky_guard_race.py [--case NAME]."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_flaky_guard import run_kind_under_load  # noqa: E402


def twenty_lease_runs_under_load():
    return run_kind_under_load("lease")


TESTS = [twenty_lease_runs_under_load]


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
