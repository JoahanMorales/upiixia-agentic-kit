#!/usr/bin/env python3
"""UAK-018: CI waited 15.6 min for one job, `suite (macos-latest)`, which runs the 31 test files one after another
(run 42310349789 on 4854882; Windows, one job per file, ended by 7 min). The suite now runs in shards per OS:
`scripts/kit_lint.py --ci-shards N` splits the discovered test files by their measured seconds, and smoke runs only the
files named in UAK_SMOKE_TESTS. Every test runs in exactly one shard; a name that is not a test fails the shard instead
of quietly running less. Without the variable smoke runs every test, as the merge gate and a laptop do."""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

REPO = Path(__file__).resolve().parents[3]


def kit_lint():
    """scripts/kit_lint.py of the kit's source repository; an installed project has none."""
    p = REPO / "scripts" / "kit_lint.py"
    if not p.is_file():
        return None
    spec = importlib.util.spec_from_file_location("kit_lint_for_shards", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def discovered(r):
    return sorted(p.stem for p in (r.package / ".uak" / "tests").glob("test_*.py"))


def shards_cover_every_test_once(r):
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here: the shards are made by its scripts/kit_lint.py"
    tests = sorted(t.stem for t in (REPO / "kit" / ".uak" / "tests").glob("test_*.py"))
    expect(hasattr(lint, "ci_shards") and hasattr(lint, "ci_seconds"), "kit_lint.py has no ci_shards(n) / ci_seconds(test)")
    for n in (1, 3, 4, 6):
        shards = lint.ci_shards(n)
        expect(len(shards) == n and all(s["tests"] for s in shards), "%d shards, none empty: %s" % (n, shards))
        expect([s["n"] for s in shards] == list(range(1, n + 1)), "shards are numbered 1..%d: %s" % (n, [s["n"] for s in shards]))
        names = [t for s in shards for t in s["tests"].split()]
        expect(sorted(names) == tests, "with %d shards every test file must run exactly once: missing %s, twice %s"
               % (n, sorted(set(tests) - set(names)), sorted({t for t in names if names.count(t) > 1})))
    shards = lint.ci_shards(4)
    w = lint.ci_seconds
    loads = [sum(w(t) for t in s["tests"].split()) for s in shards]
    total, biggest = sum(w(t) for t in tests), max(w(t) for t in tests)
    expect(max(loads) <= total / 4 + biggest, "balanced by measured seconds: loads %s, total %d" % (loads, total))
    expect(w("test_not_measured_yet") == 60, "a test with no measured time counts 60 s: %r" % w("test_not_measured_yet"))
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "kit_lint.py"), "--ci-shards", "4"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    m = re.fullmatch(r"shards=(\[.*\])\n", out.stdout)
    expect(out.returncode == 0 and m is not None, "--ci-shards prints one shards=JSON line: %r" % out.stdout[:300])
    expect(json.loads(m.group(1)) == shards, "the printed shards are ci_shards(4)")
    return "4 shards, loads %s s" % loads


def smoke(r, tests):
    """smoke --package-only on this package with UAK_SMOKE_TESTS. A smoke that ignored the variable would run every
    test, this file included, which would run smoke again: it is checked first, and a nested run stops at once."""
    expect("UAK_SMOKE_TESTS" in (r.package / ".uak" / "bin" / "smoke").read_text(encoding="utf-8"),
           "smoke does not read UAK_SMOKE_TESTS: it would run the whole suite")
    return r.run([r.bash, ".uak/bin/smoke", "--package-only"], cwd=r.package,
                 env={"UAK_SMOKE_TESTS": tests, "UAK_CI_SHARDS_NESTED": "1"}, allowed=None, timeout=600)


def smoke_runs_only_its_shard(r):
    out = smoke(r, "test_policy test_gate_scope")
    results = re.findall(r"(?m)^([A-Z0-9_]+)_RESULT ", out.stdout)
    expect(out.returncode == 0 and "PACKAGE_PASS" in out.stdout, "the shard must pass: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(sorted(results) == ["GATE_SCOPE", "POLICY"], "only the shard's two files run: %s" % results)
    expect("2 of %d test files" % len(discovered(r)) in out.stdout, "smoke says how much of the suite it ran: %r" % out.stdout[-400:])
    return "ran %s" % results


def a_name_that_is_not_a_test_fails_the_shard(r):
    for bad, why in (("test_policy test_no_such_file", "test_no_such_file"), ("test_policy *", "*"), ("", "empty"),
                     ("test_policy.py", "test_policy.py")):
        out = smoke(r, bad)
        text = out.stdout + out.stderr
        expect(out.returncode != 0, "UAK_SMOKE_TESTS=%r must fail the shard: rc 0 %s" % (bad, text[-300:]))
        expect("POLICY_RESULT" not in out.stdout, "UAK_SMOKE_TESTS=%r: nothing runs before the names are checked" % bad)
        expect("UAK_SMOKE_TESTS" in text and (why == "empty" or why in text), "UAK_SMOKE_TESTS=%r: the error names it: %r" % (bad, text[-300:]))
    return "4 bad lists refused"


TESTS = [shards_cover_every_test_once, smoke_runs_only_its_shard, a_name_that_is_not_a_test_fails_the_shard]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    if os.environ.get("UAK_CI_SHARDS_NESTED") == "1":
        print("CI_SHARDS_RESULT PASS passed=0 failed=0 (run by its own smoke: not again)")
        return 0
    with tempfile.TemporaryDirectory(prefix="uak-ci-shards-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("CI_SHARDS_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
