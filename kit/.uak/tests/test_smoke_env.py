#!/usr/bin/env python3
"""smoke's shard list (UAK_SMOKE_TESTS) and the merge gate's none-signal (UAK_SMOKE_GATE_NONE) are the run's choice,
not the tests': a test that starts its own smoke inherited them and looked for files its package lacked. It bit twice
(lesson #4, then test_merge_affected in v6.1.1's CI). smoke now unsets both before running the test files."""
import argparse
import shutil
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

PROBE = (
    "import os\n"
    "print('PROBE_TESTS=' + ('SET' if 'UAK_SMOKE_TESTS' in os.environ else 'UNSET'))\n"
    "print('PROBE_NONE=' + ('SET' if 'UAK_SMOKE_GATE_NONE' in os.environ else 'UNSET'))\n"
)


def tests_do_not_inherit_the_shard_list(r):
    pkg = Path(tempfile.mkdtemp(prefix="smoke-env-", dir=str(r.scratch)))
    shutil.copytree(r.package / ".uak" / "bin", pkg / ".uak" / "bin")
    (pkg / ".uak" / "tests").mkdir()
    (pkg / ".uak" / "tests" / "test_probe.py").write_text(PROBE, encoding="utf-8")
    out = r.run([r.bash, ".uak/bin/smoke", "--package-only"], cwd=pkg,
                env={"UAK_SMOKE_TESTS": "test_probe", "UAK_SMOKE_GATE_NONE": "/nonexistent"}, allowed=None)
    text = out.stdout + out.stderr
    expect("Shard: 1 of 1" in text, "the shard list still selects the files: " + text[-400:])
    expect("PROBE_TESTS=UNSET" in text and "PROBE_NONE=UNSET" in text, "a test does not inherit them: " + text[-400:])
    return "not inherited"


TESTS = [tests_do_not_inherit_the_shard_list]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-smoke-env-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ not in args.case:
                continue
            started = time.monotonic()
            try:
                note = test(runner)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started))
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("SMOKE_ENV_RESULT %s failed=%d" % ("FAIL" if fails else "PASS", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
