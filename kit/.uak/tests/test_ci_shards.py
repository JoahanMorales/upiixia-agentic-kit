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


def windows_shards_of(lint, n):
    return lint.ci_windows_shards(n)


def windows_matrix_is_shards(r):
    """The Windows job is a matrix of shards, not of test files: the count is the smallest that meets the bound."""
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    ci = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    n = lint.windows_shard_count()
    expect(1 <= n <= 15, "the Windows shard count leaves room for 24 jobs a commit: %r" % n)
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "kit_lint.py"), "--ci-windows"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    m = re.fullmatch(r"wshards=(\[.*\])\n", out.stdout)
    expect(out.returncode == 0 and m is not None, "--ci-windows prints one wshards=JSON line: %r" % out.stdout[:300])
    expect(json.loads(m.group(1)) == lint.ci_windows_shards(n), "the printed shards are ci_windows_shards(%d)" % n)
    expect(len(json.loads(m.group(1))) == n, "as many Windows shards as windows_shard_count(): %d" % n)
    expect("fromJSON(needs.discover.outputs.wshards)" in ci, "the windows job's matrix is the discover job's wshards")
    expect("fromJSON(needs.discover.outputs.tests)" not in ci, "no job per test file is left")
    expect("--ci-windows" in ci, "discover prints the Windows shards")
    if n > 1:
        expect(len(lint.ci_windows_shards(n - 1)) == n - 1 and windows_load(lint, n - 1) > lint.WINDOWS_BOUND_S * lint.WINDOWS_MARGIN,
               "one shard fewer must break the bound with its margin (UAK-141): %d shards give %d s" % (n - 1, windows_load(lint, n - 1)))
    return "%d Windows shards" % n


def windows_load(lint, n):
    """The longest Windows shard in seconds: the files' measured Windows seconds plus the job's setup."""
    return max(lint.WINDOWS_SETUP_S + sum(lint.ci_windows_seconds(t) for t in s["tests"].split())
               for s in lint.ci_windows_shards(n))


def shards_cover_every_test_file_once(r):
    """Linux, macOS and Windows each run every test file, and the MCP tools of tests/, exactly once."""
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    tests = sorted(t.stem for t in (REPO / "kit" / ".uak" / "tests").glob("test_*.py"))
    for n in (1, 2, lint.windows_shard_count(), 15):
        shards = lint.ci_windows_shards(n)
        expect(len(shards) == n and all(s["tests"] for s in shards), "%d Windows shards, none empty" % n)
        expect([s["n"] for s in shards] == list(range(1, n + 1)), "Windows shards are numbered 1..%d" % n)
        names = [t for s in shards for t in s["tests"].split()]
        expect(sorted(names) == sorted(tests + ["mcp_tools"]),
               "with %d Windows shards every file and mcp_tools run exactly once: missing %s, twice %s"
               % (n, sorted(set(tests + ["mcp_tools"]) - set(names)), sorted({t for t in names if names.count(t) > 1})))
    ci = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    expect("matrix.w.tests" in ci or "matrix.shard.tests" in ci, "the shard's file list reaches the job")
    expect(not set(re.findall(r"\btest_v?\w+\b", ci)) & set(tests), "no test file is named in the workflow: a new file needs no edit")
    return "every file once in each of the Windows splits"


def longest_shard_under_the_bound(r):
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    n = lint.windows_shard_count()
    longest = windows_load(lint, n)
    expect(lint.WINDOWS_BOUND_S == 30 * 60, "the bound is 30 minutes (test_flaky_guard alone took 25 min on Windows): %r" % lint.WINDOWS_BOUND_S)
    expect(longest <= lint.WINDOWS_BOUND_S, "%d Windows shards: the longest takes %d s, over %d" % (n, longest, lint.WINDOWS_BOUND_S))
    expect(n == 1 or windows_load(lint, n - 1) > lint.WINDOWS_BOUND_S * lint.WINDOWS_MARGIN, "%d is not the smallest count that keeps the margin" % n)
    ci = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    m = re.search(r"(?s)\n  windows:.*?timeout-minutes: (\d+)", ci)
    expect(m is not None and int(m.group(1)) >= 45 and int(m.group(1)) * 60 >= lint.WINDOWS_BOUND_S * 1.4,
           "the Windows job's timeout (not raised: 45) leaves a clear margin over the bound")
    return "%d shards, longest %d s" % (n, longest)


def workflow_runs_once_per_commit(r):
    """on: push + pull_request ran the suite twice for a branch with a PR; a commit on main starts at most 24 jobs."""
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    ci = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    head = ci.split("\njobs:")[0]
    expect("pull_request" in head, "the workflow runs on pull_request: %r" % head)
    expect(re.search(r"(?s)push:.*branches:\s*\[\s*main\s*\]", head) is not None, "pushes run on main only: %r" % head)
    expect(re.search(r"(?s)push:.*tags:", head) is not None, "and on tags: %r" % head)
    expect("on: [push, pull_request]" not in head, "the bare push trigger is gone")
    jobs = 1 + 2 * 4 + lint.windows_shard_count()
    expect(jobs <= 24, "a commit on main starts %d jobs (discover, 4 shards x 2 OS, Windows shards), over 24" % jobs)
    expect("GITHUB_STEP_SUMMARY" in ci, "a failing shard names its test file in the job summary")
    return "%d jobs on main" % jobs


# UAK-144. Measured on main (the 12 latest runs up to 45037067147 and five before them; the median of each
# test file's group in the job logs): Windows seconds and macOS seconds. Before, test_flaky_guard had no entry and counted
# 60 s: it took 1496 s on Windows (shard 5: 34m39s) and about 495 s on macOS (shard 4: 25m31s).
MEASURED_WINDOWS_S = {"test_flaky_guard": 208, "test_flaky_guard_race": 1278, "test_merge_engine_policy": 905, "test_review_merge": 380, "test_claims_perf": 385,
                      "test_v51": 374, "test_review_substates": 330, "test_read_cache": 192, "test_hooks_health": 194, "mcp_tools": 104}
MEASURED_MACOS_S = {"test_flaky_guard": 101, "test_flaky_guard_race": 441, "test_design_pick": 439, "test_merge_engine_policy": 186, "test_review_merge": 93,
                    "test_v51": 73, "test_read_cache": 35, "test_hooks_health": 34}


def tables_match_the_measured_runs(r):
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    for t, w in MEASURED_WINDOWS_S.items():
        got = lint.ci_windows_seconds(t)
        expect(w * 0.85 <= got <= w * 1.15, "%s took %d s on Windows, the table says %r" % (t, w, got))
    for t, m in MEASURED_MACOS_S.items():
        got = lint.ci_seconds(t)
        expect(m * 0.85 <= got <= m * 1.15, "%s took %d s on macOS, the table says %r" % (t, m, got))
    return "%d Windows and %d macOS anchors" % (len(MEASURED_WINDOWS_S), len(MEASURED_MACOS_S))


def every_test_file_has_a_timing(r):
    """A file with no entry counted 60 s: test_flaky_guard took 25 min of Windows behind that guess (UAK-144)."""
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    f = getattr(lint, "timing_problems", None)
    expect(f is not None, "kit_lint.py has no timing_problems(tests)")
    real = lint.ci_tests()
    expect(f(real) == [], "every test file has a macOS and a Windows entry: %s" % f(real))
    got = f(real + ["test_added_later"])
    expect(len(got) == 1 and "test_added_later" in got[0] and "CI_SECONDS" in got[0], "a file with no entry is named: %s" % got)
    expect(len(f(["test_ci_shards", "test_gate_scope"])) == 0, "files with entries pass")
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "kit_lint.py")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True)
    expect("no-timing" not in out.stdout, "the lint reports no file without timing: %s" % out.stdout[-300:])
    src = (REPO / "scripts" / "kit_lint.py").read_text(encoding="utf-8")
    expect("timing_problems(" in src.split("def check_test_discovery", 1)[1].split("def check_structure", 1)[0],
           "check_test_discovery runs timing_problems, so the lint refuses a file with no entry")
    return "%d files, all timed" % len(real)


BEFORE_THE_SPLIT = ["picker_reads_the_body_before_403", "mcp_server_exits_when_stdin_closes", "engine_renewer_never_runs_the_owners_cleanup",
                    "lease_test_uses_the_injected_clock", "twenty_runs_under_load"]


def flaky_guard_cases_are_all_kept(r):
    """UAK-150: test_flaky_guard is two files; every case is in exactly one, none lost, no count lowered, helpers imported."""
    d = REPO / "kit" / ".uak" / "tests"
    texts = [(d / n).read_text(encoding="utf-8") for n in ("test_flaky_guard.py", "test_flaky_guard_race.py")]
    cases = []
    for t in texts:
        m = re.search(r"(?m)^TESTS = \[(.*?)\]$", t)
        expect(m is not None, "a file has no TESTS list")
        cases.append([x.strip() for x in m.group(1).split(",")])
    expect(sorted(cases[0] + cases[1]) == sorted(BEFORE_THE_SPLIT), "the two files' cases are the five before the split: %s" % cases)
    expect(set(cases[0]).isdisjoint(cases[1]), "no case runs twice: %s" % cases)
    expect(re.search(r"(?m)^RUNS = 20\b", texts[0]) and re.search(r"(?m)^RACE_RUNS = 60\b", texts[0]), "RUNS is 20 and RACE_RUNS 60")
    expect(not re.search(r"(?m)^(RUNS|RACE_RUNS) =", texts[1]), "the second file imports the counts, it does not copy them")
    for helper in ("picker_once", "mcp_once", "lease_once", "sh", "expect", "Failure"):
        expect(not re.search(r"(?m)^def %s\(|^class %s\b" % (helper, helper), texts[1]), "%s is imported, not copied" % helper)
    expect("from test_flaky_guard import" in texts[1], "the helpers come from test_flaky_guard")
    out = subprocess.run([sys.executable, str(d / "test_flaky_guard_race.py"), "--case", "no_such_case"], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, universal_newlines=True)
    expect(out.returncode == 0 and "FLAKY_GUARD_RACE_RESULT PASS" in out.stdout, "the new file imports and runs the way smoke runs it: %s" % out.stdout[-300:])
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    for t in ("test_flaky_guard", "test_flaky_guard_race"):
        expect(t in lint.CI_SECONDS and t in lint.CI_WINDOWS_SECONDS, "%s has a macOS and a Windows entry" % t)
    jobs = 1 + 2 * 4 + lint.windows_shard_count()
    expect(jobs <= 19, "a commit starts %d jobs (discover, 4 shards x 2 OS, Windows shards), over 19" % jobs)
    return "5 cases in 2 files, %d jobs per commit" % jobs


def flaky_guard_load_is_proved(r):
    """UAK-151: twenty_runs_under_load is run with its pool, hogs and job functions replaced by recorders. It must submit
    20 jobs of each of the three kinds (60), start at least one CPU hog and kill it, and use a pool of 4 workers. A case
    with a cut job list or RUNS, the hogs set to 0 or the pool to 1 worker fails here; the constants must be the ones it uses."""
    d = REPO / "kit" / ".uak" / "tests"
    sys.path.insert(0, str(d))
    import test_flaky_guard_race as race
    expect(race.RUNS >= 20 and race.POOL_WORKERS >= 4, "the load constants: RUNS %s, POOL_WORKERS %s" % (race.RUNS, race.POOL_WORKERS))
    expect(race.hog_count() >= 1, "at least one hog: %r" % race.hog_count())
    saved = {n: getattr(race, n) for n in ("start_hog", "make_pool", "lease_once", "mcp_once", "picker_once", "hog_count")}
    hogs, pools, killed = [], [], []
    expect(race.MCP_TEST.is_file(), "tests/test_mcp_tools.py is the third kind of the load")

    class Hog:
        def kill(self):
            killed.append(1)

        def wait(self):
            return 0

    class Fut:
        def result(self):
            return None

    class Pool:
        def __init__(self, workers):
            self.workers, self.fns = workers, []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, fn):
            self.fns.append(fn)
            return Fut()
    fast = os.environ.pop("UAK_SMOKE_FAST", None)
    saved_as = race.concurrent.futures.as_completed
    try:
        race.start_hog = lambda: hogs.append(1) or Hog()
        race.make_pool = lambda w: pools.append(Pool(w)) or pools[-1]
        for k in ("lease", "mcp", "picker"):
            setattr(race, k + "_once", (lambda name: lambda *a, **kw: name)(k))
        race.concurrent.futures.as_completed = lambda futures: list(futures)
        race.twenty_runs_under_load()
    finally:
        race.concurrent.futures.as_completed = saved_as
        for n, v in saved.items():
            setattr(race, n, v)
        if fast is not None:
            os.environ["UAK_SMOKE_FAST"] = fast
    expect(len(pools) == 1 and pools[0].workers == 4, "a pool of 4 workers: %r" % [p.workers for p in pools])
    expect(len(hogs) >= 1 and len(killed) == len(hogs), "at least one CPU hog is started and killed: %d started, %d killed" % (len(hogs), len(killed)))
    names = [fn() for fn in pools[0].fns]
    counts = {k: names.count(k) for k in ("lease", "mcp", "picker")}
    expect(all(c == 20 for c in counts.values()) and len(names) == 60, "20 jobs of each of the three kinds, 60 in all: %s" % counts)
    body = (d / "test_flaky_guard_race.py").read_text(encoding="utf-8").split("def twenty_runs_under_load", 1)[1].split("\nTESTS = [", 1)[0]
    for ref in ("RUNS", "POOL_WORKERS", "hog_count()", "start_hog()", "make_pool("):
        expect(ref in body, "twenty_runs_under_load uses %s" % ref)
    return "%d jobs (%s), %d workers, %d hogs" % (len(names), ", ".join("%d %s" % (c, k) for k, c in sorted(counts.items())), pools[0].workers, len(hogs))


def no_file_over_half_the_bound(r):
    """UAK-150: a test file over half of WINDOWS_BOUND_S cannot share a shard with anything else: the lint says to split it."""
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    half = lint.WINDOWS_BOUND_S // 2
    win = dict(lint.CI_WINDOWS_SECONDS, test_ci_shards=half + 1)
    got = lint.timing_problems(["test_ci_shards"], windows=win)
    expect(len(got) == 1 and "test_ci_shards" in got[0] and "split" in got[0] and "over-half" in got[0], "a file over half the bound is refused: %s" % got)
    expect(lint.timing_problems(["test_ci_shards"], windows=dict(lint.CI_WINDOWS_SECONDS, test_ci_shards=half)) == [], "exactly half passes")
    exc = lint.HALF_BOUND_EXCEPTIONS
    expect(exc and all(isinstance(why, str) and len(why) > 40 for why in exc.values()), "each exception says why and what follows: %r" % exc)
    expect(lint.timing_problems(["test_ci_shards"], windows=win, exceptions={"test_ci_shards": "x" * 50}) == [], "a listed exception passes")
    over = sorted(t for t in lint.ci_tests() if lint.ci_windows_seconds(t) > half)
    expect(sorted(over) == sorted(exc), "the files over half the bound are exactly the excepted ones: over %s, excepted %s" % (over, sorted(exc)))
    expect(lint.timing_problems(lint.ci_tests()) == [], "the real tables pass: %s" % lint.timing_problems(lint.ci_tests()))
    return "limit %d s, %d excepted: %s" % (half, len(exc), ", ".join(sorted(exc)))


def stale_timing_entry_is_reported(r):
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    got = lint.timing_problems(["test_ci_shards"], windows=dict(lint.CI_WINDOWS_SECONDS, test_removed_long_ago=50))
    expect(len(got) == 1 and "test_removed_long_ago" in got[0] and "stale" in got[0] and "CI_WINDOWS_SECONDS" in got[0], "a Windows entry of a missing file is stale: %s" % got)
    got = lint.timing_problems(["test_ci_shards"], seconds=dict(lint.CI_SECONDS, test_removed_long_ago=50))
    expect(len(got) == 1 and "stale" in got[0] and "CI_SECONDS" in got[0], "a macOS entry of a missing file is stale: %s" % got)
    expect(lint.timing_problems(lint.ci_tests()) == [], "the real tables have no stale entry")
    return "both tables checked against the files on disk"


def message_names_both_tables(r):
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    got = lint.timing_problems(["test_added_later"])
    expect(len(got) == 1 and "CI_SECONDS" in got[0] and "CI_WINDOWS_SECONDS" in got[0], "a file in neither table names both: %s" % got)
    only = lint.timing_problems(["test_added_later"], seconds=dict(lint.CI_SECONDS, test_added_later=5))
    only = [x for x in only if "no-timing" in x]
    expect(len(only) == 1 and "CI_WINDOWS_SECONDS" in only[0] and "no entry in CI_SECONDS" not in only[0], "a file missing from one names that one: %s" % only)
    return "named: %s" % got[0][:60]


def windows_longest_shard_keeps_a_margin(r):
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    expect(getattr(lint, "WINDOWS_MARGIN", None) == 0.85, "WINDOWS_MARGIN is 0.85: %r" % getattr(lint, "WINDOWS_MARGIN", None))
    n = lint.windows_shard_count()
    longest = windows_load(lint, n)
    expect(longest <= lint.WINDOWS_BOUND_S * 0.85, "%d shards: the longest is predicted at %d s, over 85%% of the bound (%d s)"
           % (n, longest, lint.WINDOWS_BOUND_S * 0.85))
    expect(windows_load(lint, n - 1) > lint.WINDOWS_BOUND_S * 0.85, "%d is not the smallest count with the margin" % n)
    return "%d shards, longest %d s of %d" % (n, longest, lint.WINDOWS_BOUND_S)


GOOD_ON = "on:\n  pull_request:\n  push:\n    branches: [main]\n    tags: ['*']\npermissions:\n  contents: read\n"


def lint_flags_a_push_trigger_without_a_filter(r):
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    f = getattr(lint, "push_trigger_problems", None)
    expect(f is not None, "kit_lint.py has no push_trigger_problems(workflow_text)")
    expect(f("name: t\n" + GOOD_ON + "jobs:\n  a: {}\n") == [], "branches and tags named: no finding: %s" % f("name: t\n" + GOOD_ON))
    for why, text in (("bare push:", "on:\n  pull_request:\n  push:\npermissions: {}\n"),
                      ("push with only paths", "on:\n  push:\n    paths: ['a']\npermissions: {}\n"),
                      ("list form", "on: [push, pull_request]\npermissions: {}\n"),
                      ("push last in the block", "on:\n  pull_request:\n  push:\njobs:\n  a: {}\n")):
        expect(len(f(text)) >= 1, "%s must be flagged: %s" % (why, f(text)))
    expect(f("on:\n  push:\n    tags: ['v*']\njobs:\n  a: {}\n") == [], "tags alone are a filter")
    expect(f("on:\n  push:\n    branches:\n      - main\njobs:\n  a: {}\n") == [], "a branches block list is a filter")
    ci = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    expect(f(ci) == [], "the real workflow passes: %s" % f(ci))
    # Variants (kit-r1 review): comments and values are not filters; the key may be quoted; other keys are not triggers.
    for why, text in (("a comment naming branches", "on:\n  push: # branches later\njobs:\n  a: {}\n"),
                      ("a path glob naming branches", "on:\n  push:\n    paths: ['branches/**']\njobs:\n  a: {}\n"),
                      ("a quoted on key", '"on": [push]\njobs:\n  a: {}\n'),
                      ("a quoted on key, block", '"on":\n  push:\njobs:\n  a: {}\n'),
                      ("a bare scalar", "on: push\njobs:\n  a: {}\n")):
        expect(len(f(text)) >= 1, "%s must be flagged: %s" % (why, f(text)))
    for why, text in (("a pull_request list", "on: [pull_request]\njobs:\n  a: {}\n"),
                      ("a top-level env key named push", "on:\n  pull_request:\nenv:\n  push:\n    x: 1\njobs:\n  a: {}\n"),
                      ("a top-level permissions key named push", "on:\n  pull_request:\npermissions:\n  push: write\njobs:\n  a: {}\n"),
                      ("a flow filter", "on: {push: {branches: [main]}}\njobs:\n  a: {}\n"),
                      ("a filter after a comment", "on:\n  push: # only these\n    branches: [main]\njobs:\n  a: {}\n")):
        expect(f(text) == [], "%s must pass: %s" % (why, f(text)))
    return "bare push flagged, filtered push passes"


def an_empty_shard_fails_instead_of_passing(r):
    """A shard with no files ran no test and went green. Each job that runs a shard stops on an empty list."""
    ci = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    guards = [l.strip() for l in ci.splitlines() if l.strip().startswith('[ -n "$(echo $SHARD_TESTS)" ]')]
    expect(len(guards) == 2, "the suite and the Windows job each guard an empty SHARD_TESTS: %s" % guards)
    suite = ci.split("mkfifo", 1)[0]
    expect(guards[0] in suite, "the suite's guard comes before the stdin holder (sleep 7200) starts")
    for g in guards:
        for empty in ("", "   ", "\n"):
            out = subprocess.run([resolve_binary("bash"), "-c", g], env=dict(os.environ, SHARD_TESTS=empty), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, universal_newlines=True)
            expect(out.returncode != 0 and "no test files" in out.stdout, "SHARD_TESTS=%r must fail with a message: rc %d %r" % (empty, out.returncode, out.stdout))
        ok = subprocess.run([resolve_binary("bash"), "-c", g], env=dict(os.environ, SHARD_TESTS="test_a test_b"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        expect(ok.returncode == 0, "a shard with files goes on: rc %d" % ok.returncode)
    return "2 guards"


TESTS = [flaky_guard_cases_are_all_kept, flaky_guard_load_is_proved, no_file_over_half_the_bound, stale_timing_entry_is_reported, message_names_both_tables, tables_match_the_measured_runs, every_test_file_has_a_timing, windows_longest_shard_keeps_a_margin, lint_flags_a_push_trigger_without_a_filter,
         an_empty_shard_fails_instead_of_passing, windows_matrix_is_shards, shards_cover_every_test_file_once, longest_shard_under_the_bound, workflow_runs_once_per_commit,
         shards_cover_every_test_once, smoke_runs_only_its_shard, a_name_that_is_not_a_test_fails_the_shard]


# UAK-168: the second tier keeps the bounds above; the first tier (a pull request) has its own.
def ci_select():
    p = REPO / "scripts" / "ci_select.py"
    spec = importlib.util.spec_from_file_location("ci_select_for_shards", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def first_tier_keeps_its_bounds(r):
    """A pull request: at most 9 jobs, each macOS and Windows job predicted under 10 minutes, for diffs of every kind."""
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    cs = ci_select()
    samples = [[("M", "README.md")], [("M", "kit/.uak/docs/WHY.md")], [("M", "scripts/kit_lint.py")], [("M", "kit/.uak/bin/lib/core.sh")],
               [("A", "kit/.uak/tests/test_brand_new.py")], [("M", "kit/.uak/tests/test_v51.py")], [("M", "kit/.uak/bin/smoke")]]
    worst = 0
    for changed in samples:
        sel = cs.select(changed)
        m = cs.matrices("first", sel)
        expect(cs.job_count(m) <= 9, "%s: %d jobs on a pull request, over 9" % (changed, cs.job_count(m)))
        for system, p in cs.predict(sel).items():
            for s in p["shards"]:
                worst = max(worst, s["seconds"])
                expect(s["seconds"] < 600, "%s: a %s job is predicted %d s, not under 10 minutes" % (changed, system, s["seconds"]))
    whole = cs.matrices("full", cs.select([]))
    expect(cs.job_count(whole) <= 19, "the second tier is still at most the 19 jobs of today: %d" % cs.job_count(whole))
    return "at most 9 jobs, longest first-tier job %d s" % worst


def first_tier_matrix_reaches_the_jobs(r):
    """The discover job's tier output feeds the suite and Windows matrices; the portability set is checked by the lint."""
    lint = kit_lint()
    if lint is None:
        return "no kit source repository here"
    ci = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    expect("fromJSON(needs.discover.outputs.shards)" in ci and "fromJSON(needs.discover.outputs.wshards)" in ci, "both matrices come from discover")
    expect("runs-on: ${{ matrix.shard.os }}" in ci, "a suite shard names its own runner (the first tier has no macOS job when nothing is selected there)")
    expect(lint.portability_problems(lint.ci_tests()) == [], "the portability set passes the lint")
    expect(lint.portability_problems(lint.ci_tests(), {"test_policy": ""}) != [], "a file with no reason is refused")
    return "matrices from discover"


TESTS = TESTS + [first_tier_keeps_its_bounds, first_tier_matrix_reaches_the_jobs]


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
