#!/usr/bin/env python3
"""UAK-168: CI in two tiers. A pull request waited about forty minutes because every push paid the whole matrix (19 jobs:
macOS 15 to 19 minutes, Windows 17 to 26, plus the wait for a runner; human, 2026-11-23, run 45116515431). Now a pull
request runs the first tier (the whole suite on Linux; on macOS and Windows only what the change can affect plus a fixed
portability set) and main and tags run the second tier (the whole matrix). `scripts/ci_select.py BASE HEAD` is the one
script that decides; the workflow always runs (no path filter) and ends in one job, `ci`, that is the only required check.
These cases call the script, the lint and the workflow text; the issue logic is a plan the test reads, never a real issue."""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "test.yml"
SCRIPT = REPO / "scripts" / "ci_select.py"
FIRST_TIER_BOUND_S = 600


class Failure(Exception):
    pass


def expect(condition, message):
    if not condition:
        raise Failure("expected: " + message)


_cache = {}


def load(name, path):
    if name not in _cache:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _cache[name] = mod
    return _cache[name]


def select_module():
    expect(SCRIPT.is_file(), "scripts/ci_select.py exists (the one script that selects the first tier)")
    return load("ci_select_for_tiers", SCRIPT)


def lint_module():
    return load("kit_lint_for_tiers", REPO / "scripts" / "kit_lint.py")


def workflow():
    return WORKFLOW.read_text(encoding="utf-8")


def source_repository():
    return SCRIPT.parent.is_dir() and (REPO / "scripts" / "kit_lint.py").is_file()


def every_test():
    return sorted(p.stem for p in (REPO / "kit" / ".uak" / "tests").glob("test_*.py"))


def pull_request_runs_the_first_tier(r):
    cs = select_module()
    changed = [("M", "scripts/kit_lint.py")]
    tier, why = cs.decide("pull_request", [], "", changed)
    expect(tier == "first", "a pull request with an ordinary change runs the first tier, got %r (%s)" % (tier, why))
    m = cs.matrices(tier, cs.select(changed))
    linux = [s for s in m["shards"] if s["os"] == "ubuntu-latest"]
    expect(len(linux) == 4, "Linux runs 4 shards: %s" % linux)
    names = sorted(t for s in linux for t in s["tests"].split())
    expect(names == every_test(), "the Linux shards hold the whole suite exactly once: missing %s" % sorted(set(every_test()) - set(names)))
    mac = [s for s in m["shards"] if s["os"] == "macos-latest"]
    expect(1 <= len(mac) <= 2, "macOS has one job, two when the selection is predicted over 10 minutes: %d" % len(mac))
    expect(1 <= len(m["wshards"]) <= 2, "Windows has one job, two at most: %d" % len(m["wshards"]))
    mac_tests = [t for s in mac for t in s["tests"].split()]
    expect(0 < len(mac_tests) < len(every_test()) // 2, "macOS runs only what the change can affect: %d of %d" % (len(mac_tests), len(every_test())))
    ci = workflow()
    expect("pull_request" in ci.split("\njobs:")[0], "the workflow runs on pull_request")
    expect("needs.discover.outputs.tier" in ci or "steps.pick.outputs.tier" in ci, "the discover job prints the tier it chose")
    return "%d Linux, %d macOS, %d Windows jobs" % (len(linux), len(mac), len(m["wshards"]))


def main_runs_the_whole_matrix(r):
    cs = select_module()
    lint = lint_module()
    for event, ref in (("push", "refs/heads/main"), ("push", "refs/tags/v7.0.0")):
        tier, why = cs.decide(event, [], "", [], ref=ref)
        expect(tier == "full", "a %s of %s runs the second tier, got %r" % (event, ref, tier))
    m = cs.matrices("full", cs.select([]))
    per_os = {}
    for s in m["shards"]:
        per_os.setdefault(s["os"], []).append(s)
    expect(sorted(per_os) == ["macos-latest", "ubuntu-latest"] and all(len(v) == 4 for v in per_os.values()), "4 shards on Linux and on macOS: %s" % {k: len(v) for k, v in per_os.items()})
    expect(len(m["wshards"]) == lint.windows_shard_count(), "every Windows shard runs: %d of %d" % (len(m["wshards"]), lint.windows_shard_count()))
    for os_name, shards in per_os.items():
        names = sorted(t for s in shards for t in s["tests"].split())
        expect(names == every_test(), "%s runs the whole suite once" % os_name)
    jobs = cs.job_count(m)
    expect(jobs <= 19, "the whole matrix is at most the 19 jobs of today (discover, 8 suite shards, Windows shards): %d" % jobs)
    ci = workflow()
    head = ci.split("\njobs:")[0]
    expect(re.search(r"(?s)push:.*branches:\s*\[\s*main\s*\]", head) is not None and re.search(r"(?s)push:.*tags:", head) is not None, "main and tags are triggers")
    expect(re.search(r"cancel-in-progress:\s*\$\{\{\s*github\.event_name == 'pull_request'\s*\}\}", ci) is not None, "only a pull request run is cancelled: every commit on main keeps its result")
    return "%d jobs on main" % jobs


def selection_has_changed_tests_named_tests_and_the_portability_set(r):
    cs = select_module()
    lint = lint_module()
    sel = cs.select([("M", "kit/.uak/tests/test_policy.py"), ("M", "scripts/kit_lint.py")])
    for system in ("macos", "windows"):
        got = sel[system]
        expect("test_policy" in got and "changed test file" in got["test_policy"][0], "%s: an edited test file runs: %s" % (system, got.get("test_policy")))
        named = [t for t, why in got.items() if any("names" in x for x in why)]
        expect("test_ci_shards" in named, "%s: the tests that name a file the change touches run (kit_lint.py is named by test_ci_shards): %s" % (system, sorted(got)[:12]))
        for t in lint.PORTABILITY_SET:
            expect(t in got and any(x.startswith("portability") for x in got[t]), "%s: the portability file %s is always selected, with its reason" % (system, t))
    expect(1 <= len(lint.PORTABILITY_SET) <= 6, "at most six portability files: %d" % len(lint.PORTABILITY_SET))
    for t, why in lint.PORTABILITY_SET.items():
        expect(why.strip(), "%s has a reason" % t)
        expect(lint.ci_windows_seconds(t) < 120, "%s takes %d s on Windows, not under two minutes" % (t, lint.ci_windows_seconds(t)))
    reasons = " ".join(lint.PORTABILITY_SET.values()).lower()
    for topic in ("space", "symlink", "bash 3.2", "crlf", "case", "process group"):
        expect(topic in reasons, "the portability set says why for %r: %s" % (topic, reasons[:200]))
    expect(lint.portability_problems(lint.ci_tests()) == [], "the lint accepts the set: %s" % lint.portability_problems(lint.ci_tests()))
    for why, args in (("a missing file", ({"test_not_there": "x"},)), ("no reason", ({"test_policy": "  "},)),
                      ("over two minutes", ({"test_merge_engine_policy": "slow"},)), ("seven files", ({"test_q_string": "a", "test_policy": "b", "test_snapshot": "c",
                                                                                                         "test_gate_scope": "d", "test_smoke_env": "e", "test_metrics": "f", "test_autopsy": "g"},))):
        got = lint.portability_problems(lint.ci_tests(), *args)
        expect(len(got) >= 1 and "portability" in got[0], "the lint refuses %s: %s" % (why, got))
    return "%d portability files, selection has changed, named and fixed files" % len(lint.PORTABILITY_SET)


def selection_never_escalates_to_the_whole_suite(r):
    cs = select_module()
    total = len(every_test())
    for path in ("kit/.uak/bin/lib/core.sh", "install.sh", "kit/.uak/bin/uak", "kit/.uak/tests/test_hack.py", "kit/.uak/bin/lib/tx.sh"):
        sel = cs.select([("M", path)])
        for system in ("macos", "windows"):
            n = len(sel[system])
            expect(n < total // 3, "%s on %s must not pick the whole suite (smoke --affected would): %d of %d" % (path, system, n, total))
        expect(any(path in f or path.split("/")[-1] in f for f, _ in sel["withheld"]), "%s: what escalation withheld is listed, to run on main: %s" % (path, sel["withheld"]))
    sel = cs.select([("M", "kit/.uak/tests/test_hack.py")])
    expect("test_hack" in sel["macos"], "a changed helper test file still runs itself")
    out = subprocess.run([sys.executable, str(SCRIPT), "--changed", "M\tkit/.uak/bin/lib/core.sh"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    expect(out.returncode == 0 and "runs on main" in out.stdout and "core.sh" in out.stdout, "the report says what runs on main: rc %d %s" % (out.returncode, out.stdout[-300:]))
    return "shared engine files select nothing extra"


def ci_full_label_runs_everything(r):
    cs = select_module()
    changed = [("M", "kit/.uak/tests/test_policy.py")]
    tier, why = cs.decide("pull_request", ["ci-full"], "", changed)
    expect(tier == "full" and "ci-full" in why, "the label ci-full asks for the whole matrix: %r %r" % (tier, why))
    tier, _ = cs.decide("pull_request", ["docs", "other"], "", changed)
    expect(tier == "first", "another label does not")
    tier, why = cs.decide("workflow_dispatch", [], "full", changed)
    expect(tier == "full", "a manual run of the branch runs everything: %r" % tier)
    tier, _ = cs.decide("workflow_dispatch", [], "", changed)
    expect(tier == "full", "a manual run with no input runs everything (the default)")
    tier, _ = cs.decide("workflow_dispatch", [], "first", [("M", ".github/workflows/test.yml")])
    expect(tier == "first", "a manual run can ask for the first tier on purpose (how this tier is measured)")
    ci = workflow()
    expect("workflow_dispatch:" in ci.split("\njobs:")[0] and re.search(r"(?s)workflow_dispatch:.*?tier:", ci.split("\njobs:")[0]) is not None, "workflow_dispatch has the tier input")
    expect("labeled" in ci.split("\njobs:")[0], "adding the label starts a run")
    return "label, dispatch"


def workflow_change_runs_everything(r):
    cs = select_module()
    for path in (".github/workflows/test.yml", ".github/workflows/other.yml", "scripts/ci_select.py", "kit/.uak/bin/lib/tests.sh"):
        tier, why = cs.decide("pull_request", [], "", [("M", "docs/x.md"), ("M", path)])
        expect(tier == "full" and path in why, "a change to %s runs the whole matrix and says so: %r %r" % (path, tier, why))
    tier, _ = cs.decide("pull_request", [], "", [("M", "kit/.uak/docs/WHY.md")])
    expect(tier == "first", "a doc change does not")
    return "workflows and the selector"


def new_test_file_runs_on_three_systems(r):
    cs = select_module()
    lint = lint_module()
    sel = cs.select([("A", "kit/.uak/tests/test_brand_new_one.py")])
    for system in ("macos", "windows"):
        expect("test_brand_new_one" in sel[system] and "new test file" in sel[system]["test_brand_new_one"][0],
               "%s runs the new file, so its seconds can be measured before the tables are filled: %s" % (system, sel[system].get("test_brand_new_one")))
    m = cs.matrices("first", sel)
    linux = sorted(t for s in m["shards"] if s["os"] == "ubuntu-latest" for t in s["tests"].split())
    expect(linux == every_test(), "Linux runs the whole suite, the new file with it")
    expect(any("test_brand_new_one" in s["tests"].split() for s in m["shards"] if s["os"] == "macos-latest"), "the macOS job holds it")
    expect(any("test_brand_new_one" in s["tests"].split() for s in m["wshards"]), "the Windows job holds it")
    with tempfile.TemporaryDirectory(prefix="uak-ci-tiers-") as tmp:
        def git(*a):
            return subprocess.run(["git", "-C", tmp] + list(a), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                                  env=dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                                           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid"))
        git("init", "-q", "-b", "main")
        (Path(tmp) / "kit" / ".uak" / "tests").mkdir(parents=True)
        (Path(tmp) / "kit" / ".uak" / "tests" / "test_old.py").write_text("x = 1\n")
        git("add", "-A"); git("commit", "-q", "-m", "one")
        base = git("rev-parse", "HEAD").stdout.strip()
        (Path(tmp) / "kit" / ".uak" / "tests" / "test_old.py").write_text("x = 2\n")
        (Path(tmp) / "kit" / ".uak" / "tests" / "test_fresh_one.py").write_text("x = 1\n")
        git("add", "-A"); git("commit", "-q", "-m", "two")
        head = git("rev-parse", "HEAD").stdout.strip()
        got = cs.changed_files(tmp, base, head)
        expect(sorted(got) == [("A", "kit/.uak/tests/test_fresh_one.py"), ("M", "kit/.uak/tests/test_old.py")], "the diff against the base, from Git: %s" % got)
        out = subprocess.run([sys.executable, str(SCRIPT), base, head, "--repo", tmp], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        expect(out.returncode == 0 and "test_fresh_one" in out.stdout and "predicted" in out.stdout and "windows" in out.stdout.lower(),
               "`ci_select.py BASE HEAD` prints the files per system and the predicted seconds: rc %d %s" % (out.returncode, out.stdout[-500:]))
    return "added file on 3 systems"


def red_main_opens_one_issue(r):
    cs = select_module()
    sha = "0123456789abcdef0123456789abcdef01234567"
    failed = ["windows (3)", "suite (macos-latest, 2)"]
    both = {"windows (3)": ["test_v51"]}
    pr = {"number": 41, "title": "Add the thing"}
    first = cs.plan_issue(sha, failed, both, pr, [], "https://example.invalid/run/1")
    expect(first["action"] == "create" and first["title"] == "main is red at 0123456", "the first red opens one issue \"main is red at SHA\": %s" % first)
    for needle in ("windows (3)", "suite (macos-latest, 2)", "#41", "test_v51", "failed both times"):
        expect(needle in first["body"], "the issue names %r: %s" % (needle, first["body"]))
    open_issue = [{"number": 7, "title": "main is red at 0123456"}, {"number": 9, "title": "something else"}]
    second = cs.plan_issue("fedcba9876543210fedcba9876543210fedcba98", ["windows (1)"], {}, None, open_issue, "https://example.invalid/run/2")
    expect(second["action"] == "comment" and second["number"] == 7 and "windows (1)" in second["body"] and "fedcba9" in second["body"],
           "a second red adds to the open issue, it opens no other: %s" % second)
    green = cs.plan_issue("fedcba9876543210fedcba9876543210fedcba98", [], {}, None, open_issue, "https://example.invalid/run/3")
    expect(green["action"] == "close" and green["number"] == 7, "the first green run closes it: %s" % green)
    nothing = cs.plan_issue(sha, [], {}, None, [], "u")
    expect(nothing["action"] == "none", "green with no open issue does nothing: %s" % nothing)
    out = subprocess.run([sys.executable, str(SCRIPT), "issue", "--help"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    expect(out.returncode == 0 and "--apply" in out.stdout, "the issue command only plans unless --apply is passed: %s" % out.stdout[-200:])
    ci = workflow()
    m = re.search(r"(?s)\n  red-main:(.*?)(?=\n  [a-z][a-z-]*:\n|\Z)", ci)
    expect(m is not None, "the workflow has a red-main job")
    job = m.group(1)
    expect("issues: write" in job, "only that job may write issues: permissions issues: write")
    expect("refs/heads/main" in job and "push" in job, "it runs on a push to main only")
    expect("issues: write" not in ci.split("\njobs:")[0], "the workflow's default permissions do not write issues")
    return "create, comment, close"


def first_tier_is_at_most_nine_jobs(r):
    cs = select_module()
    lint = lint_module()
    samples = [[("M", "kit/.uak/docs/WHY.md")], [("M", "scripts/kit_lint.py")], [("M", "kit/.uak/tests/test_policy.py"), ("A", "kit/.uak/tests/test_new_a.py")],
               [("M", "kit/.uak/bin/lib/core.sh")], [("M", "install.sh"), ("M", "README.md")]]
    for changed in samples:
        sel = cs.select(changed)
        m = cs.matrices("first", sel)
        jobs = cs.job_count(m)
        expect(jobs <= 9, "%s: %d jobs on a pull request, over 9 (discover, 4 Linux, at most 2 macOS and 2 Windows)" % (changed, jobs))
        pred = cs.predict(sel)
        for system in ("macos", "windows"):
            for s in pred[system]["shards"]:
                expect(s["seconds"] < FIRST_TIER_BOUND_S, "%s: a %s job is predicted %d s, over 10 minutes" % (changed, system, s["seconds"]))
    big = [("M", "kit/.uak/tests/%s.py" % t) for t in ("test_v51", "test_review_merge")]
    sel = cs.select(big)
    pred = cs.predict(sel)
    expect(pred["windows"]["seconds"] > FIRST_TIER_BOUND_S and len(pred["windows"]["shards"]) == 2, "a Windows selection over 10 minutes gets two jobs: %s" % pred["windows"])
    for s in pred["windows"]["shards"]:
        expect(s["seconds"] < FIRST_TIER_BOUND_S, "and each of the two is under 10 minutes: %s" % pred["windows"]["shards"])
    everything = cs.matrices("first", cs.select([("M", "kit/.uak/tests/%s.py" % t) for t in every_test()]))
    expect(cs.job_count(everything) <= 9, "even a change that edits every test file stays at 9 jobs: %d" % cs.job_count(everything))
    return "at most 9 jobs, %d predicted seconds on Windows for the big sample" % pred["windows"]["seconds"]


def one_final_job_gates_the_run(r):
    cs = select_module()
    ci = workflow()
    m = re.search(r"(?s)\n  ci:\n(.*?)(?=\n  [a-z][a-z-]*:\n|\Z)", ci)
    expect(m is not None, "the workflow has a job named ci")
    job = m.group(1)
    expect(re.search(r"(?m)^    if: always\(\)\s*$", job) is not None, "ci always runs (if: always()), also when a job before it failed or was skipped")
    needs = re.search(r"(?m)^    needs: \[([^\]]*)\]", job)
    expect(needs is not None, "ci needs the other jobs")
    listed = {x.strip() for x in needs.group(1).split(",")}
    others = set(re.findall(r"(?m)^  ([a-z][a-z-]*):\n", ci.split("\njobs:", 1)[1])) - {"ci", "red-main"}
    expect(listed == others, "ci waits for every job that runs tests: needs %s, jobs %s" % (sorted(listed), sorted(others)))
    expect("ci_select.py gate" in job, "ci decides with the script the tests call")
    ok = cs.gate({"discover": {"result": "success"}, "suite": {"result": "success"}, "windows": {"result": "skipped"}})
    expect(ok == [], "success and skipped pass: %s" % ok)
    for bad in ("failure", "cancelled", "timed_out"):
        got = cs.gate({"discover": {"result": "success"}, "suite": {"result": bad}, "windows": {"result": "success"}})
        expect(got and "suite" in got[0], "a %s job fails the gate and is named: %s" % (bad, got))
    expect(cs.gate({"discover": {"result": "failure"}, "suite": {"result": "skipped"}, "windows": {"result": "skipped"}}) != [], "a failed discover (everything after it skipped) is not a pass")
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    expect("`ci`" in agents and "required" in agents and "red main" in agents.lower(), "AGENTS.md names ci as the one required check and says what follows a red main")
    return "needs %s" % sorted(listed)


def flaky_pass_is_reported_not_hidden(r):
    cs = select_module()
    calls = []

    def flaky_once(name):
        calls.append(name)
        return not (name == "test_b" and calls.count("test_b") == 1)

    res = cs.run_files(["test_a", "test_b", "test_c"], flaky_once, retry=True, log=lambda s: None)
    expect(res["failed"] == [] and res["flaky"] == ["test_b"], "a file that passes on the second run passes the job but is flaky: %s" % res)
    expect(calls.count("test_b") == 2 and calls.count("test_a") == 1, "only the failed file runs again, once: %s" % calls)
    expect(res["counts"]["test_b"] == {"runs": 2, "failures": 1}, "the count per file is kept: %s" % res["counts"])
    report = cs.flaky_report("windows (2)", res)
    expect("flaky: test_b passed on the second run" in report["summary"], "the summary says it: %s" % report["summary"])
    expect(any(a.startswith("::warning") and "flaky: test_b passed on the second run" in a for a in report["annotations"]), "an annotation says it: %s" % report["annotations"])
    expect(report["conclusion"] == "flaky", "it is never reported as a plain pass: %s" % report["conclusion"])
    calls[:] = []
    res = cs.run_files(["test_b", "test_a"], lambda n: n != "test_b", retry=True, log=lambda s: None)
    expect(res["failed"] == ["test_b"] and res["flaky"] == [], "a file that failed twice fails the job: %s" % res)
    expect(cs.flaky_report("x", res)["conclusion"] == "failed", "and the report says failed")
    calls[:] = []
    res = cs.run_files(["test_b"], flaky_once, retry=False, log=lambda s: None)
    expect(res["failed"] == ["test_b"] and calls == ["test_b"], "Linux never retries: %s %s" % (res, calls))
    clean = cs.run_files(["test_a"], lambda n: True, retry=True, log=lambda s: None)
    expect(cs.flaky_report("x", clean)["conclusion"] == "passed", "a clean pass is a plain pass")
    ci = workflow()
    expect("--retry" in ci and "upload-artifact" in ci and "matrix.shard.os != 'ubuntu-latest'" in ci.replace('"', "'"), "the workflow retries on macOS and Windows only and keeps the counts as an artifact")
    out = subprocess.run([sys.executable, str(SCRIPT), "run", "--help"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    expect(out.returncode == 0 and "--retry" in out.stdout and "--out" in out.stdout, "the run command takes --retry and --out: %s" % out.stdout[-200:])
    return "flaky, failed, clean, Linux"


def no_workflow_level_path_filter(r):
    lint = lint_module()
    ci = workflow()
    head = ci.split("\njobs:")[0]
    expect(not re.search(r"(?m)^\s*paths(-ignore)?:", head), "no trigger is filtered by path (a required check of a skipped workflow stays Pending): %s" % head[:300])
    expect(lint.path_filter_problems(ci) == [], "the lint accepts the workflow: %s" % lint.path_filter_problems(ci))
    for why, text in (("pull_request paths", "on:\n  pull_request:\n    paths: ['a/**']\njobs:\n  a: {}\n"),
                      ("push paths-ignore", "on:\n  push:\n    branches: [main]\n    paths-ignore: ['docs/**']\njobs:\n  a: {}\n"),
                      ("flow paths", "on: {pull_request: {paths: ['a']}}\njobs:\n  a: {}\n")):
        got = lint.path_filter_problems(text)
        expect(len(got) == 1, "the lint flags %s: %s" % (why, got))
    for why, text in (("a comment", "on:\n  pull_request: # paths: are not used\njobs:\n  a: {}\n"),
                      ("a job-level key", "on:\n  pull_request:\njobs:\n  a:\n    with:\n      paths: x\n")):
        expect(lint.path_filter_problems(text) == [], "the lint does not flag %s" % why)
    return "no paths filter"


TESTS = [pull_request_runs_the_first_tier, main_runs_the_whole_matrix, selection_has_changed_tests_named_tests_and_the_portability_set,
         selection_never_escalates_to_the_whole_suite, ci_full_label_runs_everything, workflow_change_runs_everything,
         new_test_file_runs_on_three_systems, red_main_opens_one_issue, first_tier_is_at_most_nine_jobs, one_final_job_gates_the_run,
         flaky_pass_is_reported_not_hidden, no_workflow_level_path_filter]


# ---- UAK-169: a retry that fits, a job that says where it was, a gate that counts a skipped job as not run -------------
# Evidence (2026-11-23, main): a Windows shard was cancelled at its 45 minute limit three times with no failing test
# (windows (1) at e4f2f83d, run 45198280141; windows (4) at 14ccdbc0, run 45232891834, checkout 36 s against 4 to 10 s in
# the other jobs and every file 9 to 10 times slower; windows (10) at eeb5f97b, run 45257335704), and each time the log
# said nothing of the file it was in. test_merge_renewer_orphan failed once on Windows at 7261ebcb ("Lock expired").
class Clock:
    """A clock the fake runners advance, so a case never sleeps."""
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def timed_runner(clock, seconds, fails=()):
    """A runner that takes the given seconds per call and fails the files in `fails` every time; records its calls."""
    calls = []

    def run(name):
        calls.append(name)
        clock.t += seconds[name]
        return name not in fails
    run.calls = calls
    return run


def slow_file_is_not_run_twice(r):
    cs = select_module()
    clock = Clock()
    table = {"test_small": 20, "test_race": 862, "test_edge": 300, "test_over": 301}
    for name, again in (("test_race", False), ("test_over", False), ("test_edge", True), ("test_small", True)):
        run = timed_runner(clock, table, fails=(name,))
        logs = []
        res = cs.run_files([name], run, retry=True, log=logs.append, seconds=table.get, bound=40 * 60, clock=clock)
        expect(run.calls == ([name, name] if again else [name]), "%s (%d s in the table) %s: %s" % (name, table[name], "runs again" if again else "is not run again", run.calls))
        expect(res["failed"] == [name], "%s failed both times or once: %s" % (name, res["failed"]))
        if not again:
            rep = cs.flaky_report("windows (1)", res)
            line = "not run again: %s takes %d s" % (name, table[name])
            expect(line in rep["summary"], "the summary says %r: %s" % (line, rep["summary"]))
            expect(any(line in a for a in rep["annotations"]), "an annotation says it: %s" % rep["annotations"])
            expect(rep["conclusion"] == "failed", "the job fails on the first failure: %s" % rep["conclusion"])
            expect(res["counts"][name]["runs"] == 1, "one run counted: %s" % res["counts"])
    # a file that passes the first time costs nothing and is not looked at
    clock = Clock()
    run = timed_runner(clock, table)
    res = cs.run_files(["test_race"], run, retry=True, log=lambda s: None, seconds=table.get, bound=2400, clock=clock)
    expect(res["failed"] == [] and res["not_rerun"] == {}, "a pass is a pass: %s" % res)
    return "300 s is retried, 301 s and 862 s are not"


def second_run_must_fit_the_bound(r):
    cs = select_module()
    # test_b (200 s in the table) fails after the job used 2300 s of a 2400 s bound: 2300 + 200 is over, so it is not run again
    for used, again in ((1000, True), (2199, True), (2200, False), (2300, False)):
        clock = Clock()
        table = {"test_a": used, "test_b": 200}

        def run(name, calls=[], clock=clock, used=used):
            calls.append(name)
            clock.t += used if name == "test_a" else 0
            return name != "test_b"
        run.__defaults__[0].clear()
        calls = run.__defaults__[0]
        res = cs.run_files(["test_a", "test_b"], run, retry=True, log=lambda s: None, seconds=table.get, bound=2400, clock=clock)
        expect(calls.count("test_b") == (2 if again else 1), "elapsed %d + entry 200 against 2400: second run %s, calls %s" % (used, again, calls))
        if not again:
            rep = cs.flaky_report("windows (2)", res)
            expect("not run again: test_b takes 200 s" in rep["summary"], "the summary names the file and its entry: %s" % rep["summary"])
            expect("2400" in rep["summary"], "and the bound: %s" % rep["summary"])
    clock = Clock()
    run = timed_runner(clock, {"test_a": 5}, fails=("test_a",))
    res = cs.run_files(["test_a"], run, retry=True, log=lambda s: None, seconds={"test_a": 5}.get, bound=None, clock=clock)
    expect(run.calls == ["test_a", "test_a"], "with no bound a short file still runs again: %s" % run.calls)
    return "elapsed + entry < bound"


def cancelled_job_names_its_file(r):
    cs = select_module()
    scripts = str(REPO / "scripts")
    with tempfile.TemporaryDirectory(prefix="uak-ci-cancel-") as tmp:
        tmp = Path(tmp)
        out = tmp / "result.json"
        driver = tmp / "driver.py"
        driver.write_text(
            "import sys, time\nsys.path.insert(0, %r)\nimport ci_select as cs\n"
            "def runner(name):\n    if name == 'test_b':\n        time.sleep(120)\n    return True\n"
            "cs.run_files(['test_a', 'test_b', 'test_c'], runner, retry=True, out=%r, job='windows (4)', seconds=lambda f: 5, bound=2400)\n"
            % (scripts, str(out)), encoding="utf-8")
        p = subprocess.Popen([sys.executable, str(driver)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        try:
            deadline = time.monotonic() + 40
            seen = None
            while time.monotonic() < deadline:
                if out.is_file():
                    try:
                        seen = json.loads(out.read_text(encoding="utf-8"))
                    except ValueError:
                        seen = None
                    if seen and seen.get("running") == "test_b":
                        break
                time.sleep(0.2)
            expect(seen and seen.get("running") == "test_b", "the partial result names the file the job is in: %s" % seen)
            expect(seen["conclusion"] == "running" and seen.get("done") == ["test_a"], "and the files done before it: %s" % seen)
        finally:
            p.kill()
            text = p.communicate()[0]
    lines = [l for l in text.splitlines() if "test_b" in l]
    expect(lines, "the job printed the name of the file it was in before it was killed (flushed, not left in a buffer): %r" % text[-300:])
    expect(any(re.search(r"\d\d:\d\d:\d\d", l) or "elapsed" in l for l in text.splitlines()), "with the clock: %r" % text[-300:])
    # the job's own bound: it stops itself and says where, instead of being cancelled blind by the platform
    clock = Clock()

    class Hang:
        timeout = None
        timed_out = False

        def __call__(self, name):
            if name == "test_b":
                clock.t += self.timeout
                self.timed_out = True
                return False
            clock.t += 30
            return True
    h = Hang()
    logs = []
    res = cs.run_files(["test_a", "test_b", "test_c"], h, retry=True, log=logs.append, seconds={"test_a": 30, "test_b": 60, "test_c": 5}.get, bound=300, clock=clock)
    expect(h.timeout == 270, "the file gets what is left of the bound (300 - 30): %s" % h.timeout)
    expect(res["stopped"] == "test_b" and res["failed"] == ["test_b"], "it stops at the file that used the bound: %s" % res)
    expect("test_c" not in "".join(logs), "and starts no other file: %s" % logs)
    rep = cs.flaky_report("windows (4)", res)
    expect("stopped at test_b" in rep["summary"] and rep["conclusion"] == "failed", "the summary says where: %s" % rep["summary"])
    return "partial result and flushed name"


def slow_runner_fails_fast_with_a_clear_line(r):
    cs = select_module()
    table = {"test_a": 10, "test_b": 10, "test_c": 10, "test_d": 10, "test_e": 10, "test_f": 200, "test_g": 200}
    names = list(table)
    # 10 times slower than the table from the first file (windows (4) at 14ccdbc0): stop when the rest cannot fit
    clock = Clock()
    run = timed_runner(clock, {k: v * 10 for k, v in table.items()})
    logs = []
    res = cs.run_files(names, run, retry=True, log=logs.append, seconds=table.get, bound=600, clock=clock)
    expect(res["slow"].startswith("slow runner, re-run"), "the line says it plainly: %r" % res["slow"])
    expect(len(run.calls) < len(names) and res["stopped"] == names[len(run.calls)], "it stops before the next file: %s %s" % (run.calls, res["stopped"]))
    rep = cs.flaky_report("windows (4)", res)
    expect("slow runner, re-run" in rep["summary"] and rep["conclusion"] == "failed", "summary: %s" % rep["summary"])
    expect(any(a.startswith("::error") and "slow runner, re-run" in a for a in rep["annotations"]), "annotation: %s" % rep["annotations"])
    # normal speed, and a slow start that still fits the bound, are not flagged
    for factor, bound in ((1.4, 600), (10, 100000)):
        clock = Clock()
        run = timed_runner(clock, {k: v * factor for k, v in table.items()})
        res = cs.run_files(names, run, retry=True, log=lambda s: None, seconds=table.get, bound=bound, clock=clock)
        expect(not res["slow"] and len(run.calls) == len(names), "factor %s with bound %s is not a slow runner: %s" % (factor, bound, res["slow"]))
    return "stops after %d of %d files" % (len(run.calls), len(names))


def ci_needs_success_not_skipped(r):
    cs = select_module()
    ok = {"discover": {"result": "success"}, "suite": {"result": "success"}, "windows": {"result": "success"}}
    planned = ["discover", "suite", "windows"]
    expect(cs.gate(ok, planned) == [], "everything planned succeeded: %s" % cs.gate(ok, planned))
    for bad in ("skipped", "cancelled", "failure", "timed_out", ""):
        got = cs.gate(dict(ok, windows={"result": bad}), planned)
        expect(got and "windows" in got[0], "a planned job that is %r fails the gate and is named: %s" % (bad, got))
    got = cs.gate(dict(ok, discover={"result": "skipped"}), planned)
    expect(got, "a skipped discover is not a pass: %s" % got)
    expect(cs.gate(dict(ok, windows={"result": "skipped"}), ["discover", "suite"]) == [], "a job the tier did not plan may be skipped")
    expect(cs.gate(dict(ok, discover={"result": "skipped"}), ["suite"]) != [], "discover is always required")
    out = cs.github_output("first", "why", {"shards": [{"n": 1}], "wshards": [{"n": 1}]})
    expect(re.search(r"(?m)^planned=discover,suite,windows$", out), "discover tells the gate what the tier planned: %s" % out[:200])
    for needs, planned_env, rc in ((ok, "discover,suite,windows", 0), (dict(ok, suite={"result": "skipped"}), "discover,suite,windows", 1),
                                   (dict(ok, windows={"result": "cancelled"}), "", 1), (dict(ok, windows={"result": "skipped"}), "discover,suite", 0)):
        p = subprocess.run([sys.executable, str(SCRIPT), "gate"], env=dict(os.environ, NEEDS=json.dumps(needs), PLANNED=planned_env, GITHUB_STEP_SUMMARY=""),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        expect(p.returncode == rc, "gate with planned=%r and %s exits %d, got %d: %s" % (planned_env, {k: v["result"] for k, v in needs.items()}, rc, p.returncode, p.stdout[-200:]))
    job = re.search(r"(?s)\n  ci:\n(.*?)(?=\n  [a-z][a-z-]*:\n|\Z)", workflow()).group(1)
    expect("needs.discover.outputs.planned" in job, "the ci job hands the gate what discover planned")
    return "skipped and cancelled fail a planned job"


def cancelled_main_does_not_close_the_issue(r):
    cs = select_module()
    sha = "0123456789abcdef0123456789abcdef01234567"
    open_issue = [{"number": 7, "title": "main is red at fedcba9"}]
    url = "https://example.invalid/run/9"
    for result in ("cancelled", "failure", "skipped"):
        plan = cs.plan_issue(sha, [], {}, None, open_issue, url, ci_result=result)
        expect(plan["action"] == "none", "a run whose ci job is %s closes nothing: %s" % (result, plan))
    plan = cs.plan_issue(sha, [], {}, None, open_issue, url, ci_result="success")
    expect(plan["action"] == "close" and plan["number"] == 7, "a run whose ci job succeeded closes it: %s" % plan)
    expect(cs.plan_issue(sha, [], {}, None, open_issue, url)["action"] == "close", "the default is the old behaviour (ci succeeded)")
    # what counts as a failed job: a failure, and a job cancelled by its own time limit; never a job cancelled by hand
    limit = {"windows (1)": 45 * 60, "suite (ubuntu-latest, 1)": 60 * 60}
    row = lambda name, concl, secs: {"name": name, "conclusion": concl, "started_at": "2026-11-23T14:49:17Z",
                                     "completed_at": cs_time(secs)}

    def cs_time(secs):
        import datetime as dt
        return (dt.datetime(2026, 11, 23, 14, 49, 17) + dt.timedelta(seconds=secs)).strftime("%Y-%m-%dT%H:%M:%SZ")
    expect(cs.job_outcome(row("windows (1)", "cancelled", 55 * 60)) == "time limit", "cancelled after 55 minutes is the 45 minute limit")
    expect(cs.job_outcome(row("windows (1)", "cancelled", 3 * 60)) == "cancelled", "cancelled after 3 minutes is a hand")
    expect(cs.job_outcome(row("suite (ubuntu-latest, 2)", "cancelled", 61 * 60)) == "time limit", "the suite's limit is 60 minutes")
    expect(cs.job_outcome(row("suite (ubuntu-latest, 2)", "cancelled", 50 * 60)) == "cancelled", "50 minutes is not past a 60 minute limit")
    expect(cs.job_outcome(row("windows (1)", "failure", 60)) == "failed" and cs.job_outcome(row("windows (1)", "success", 60)) == "success", "failure and success")
    p = subprocess.run([sys.executable, str(SCRIPT), "issue", "--help"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    expect("--ci-result" in p.stdout and "--attempt" in p.stdout, "the issue command takes the ci result and the attempt: %s" % p.stdout[-300:])
    job = re.search(r"(?s)\n  red-main:(.*?)(?=\n  [a-z][a-z-]*:\n|\Z)", workflow()).group(1)
    expect("needs.ci.result" in job and "run_attempt" in job, "red-main hands the script the result of ci and the attempt")
    return "only a ci success closes"


def red_main_says_which_kind_of_failure(r):
    cs = select_module()
    sha = "0123456789abcdef0123456789abcdef01234567"
    url = "https://example.invalid/run/1"
    twice = cs.plan_issue(sha, ["windows (3)"], {"windows (3)": ["test_v51"]}, None, [], url, causes={"windows (3)": "failed"}, attempt=1)
    expect("failed both times" in twice["body"] and "no re-run" in twice["body"].lower(), "a file that ran twice needs no re-run, and the issue says so: %s" % twice["body"])
    once = cs.plan_issue(sha, ["windows (1)"], {}, None, [], url, causes={"windows (1)": "time limit"}, attempt=1)
    expect("time limit" in once["body"] and "gh run rerun" in once["body"] and "not confirmed" in once["body"].lower(), "a time limit is not confirmed until the failed jobs run again: %s" % once["body"])
    again = cs.plan_issue(sha, ["windows (1)"], {}, None, [], url, causes={"windows (1)": "time limit"}, attempt=2)
    expect("after a re-run" in again["body"] and "not confirmed" not in again["body"].lower(), "attempt 2 is the confirmation: %s" % again["body"])
    return "two kinds"


def portability_set_has_no_intermittent_file(r):
    lint = lint_module()
    expect(isinstance(lint.KNOWN_INTERMITTENT, dict) and lint.KNOWN_INTERMITTENT, "the lint keeps a list of known intermittent files, each with its evidence")
    for t, why in lint.KNOWN_INTERMITTENT.items():
        expect(str(why).strip(), "%s has no evidence in KNOWN_INTERMITTENT" % t)
    both = sorted(set(lint.PORTABILITY_SET) & set(lint.KNOWN_INTERMITTENT))
    expect(not both, "the portability set holds a known intermittent file: %s" % both)
    expect(lint.portability_problems(lint.ci_tests()) == [], "the lint accepts the real set: %s" % lint.portability_problems(lint.ci_tests()))
    tests = lint.ci_tests()
    pick = next(t for t in lint.PORTABILITY_SET)
    got = lint.portability_problems(tests, {pick: "a reason"}, {pick: 10}, {pick: "failed once on Windows"})
    expect(len(got) == 1 and "intermittent" in got[0] and pick in got[0], "the lint refuses a member named in the list: %s" % got)
    expect(lint.portability_problems(tests, {pick: "a reason"}, {pick: 10}, {}) == [], "and accepts it when it is not named")
    why = (REPO / "kit" / ".uak" / "docs" / "WHY.md").read_text(encoding="utf-8")
    expect("UAK-169" in why and "test_merge_renewer_orphan" in why and "13 runs" in why,
           "WHY.md records the measurements that keep test_merge_renewer_orphan in the set (or why it left)")
    return "%d files, none intermittent" % len(lint.PORTABILITY_SET)


def step_of(job_id, text=None):
    """(env {KEY: value text}, script) of the step `- id: job_id`, read from the workflow as GitHub would run it."""
    text = text or workflow()
    m = re.search(r"(?ms)^      - id: %s\n(.*?)(?=^      - |^  [a-z][a-z-]*:\n|\Z)" % re.escape(job_id), text)
    expect(m is not None, "the workflow has a step with id %s" % job_id)
    block = m.group(1)
    env = dict(re.findall(r"(?m)^          ([A-Z_]+): (.*)$", block.split("run: |")[0]))
    script = block.split("run: |\n", 1)[1]
    script = "\n".join(l[10:] if l.startswith("          ") else l for l in script.splitlines()) + "\n"
    return env, script


def run_pick_step(cs, tmp, values):
    """Run the discover job's `pick` step the way the runner does (bash -e), with the values GitHub would put in its env."""
    env, script = step_of("pick")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO), stdout=subprocess.PIPE, universal_newlines=True).stdout.strip()
    given = dict(EVENT="pull_request", REF="refs/pull/1/merge", LABELS="", TIER_INPUT="", BASE="HEAD", FULL_S="", FULL_W="")
    given.update(values)
    expect(set(env) <= set(given), "the pick step reads %s, the case knows %s" % (sorted(env), sorted(given)))
    out, summary = tmp / "github_output", tmp / "summary"
    out.write_text("", encoding="utf-8")
    summary.write_text("", encoding="utf-8")
    script = script.replace("python3", '"%s"' % Path(sys.executable).as_posix())
    wenv = dict(os.environ, GITHUB_SHA=head, GITHUB_OUTPUT=out.as_posix(), GITHUB_STEP_SUMMARY=summary.as_posix(), RUNNER_TEMP=tmp.as_posix(),
                **{k: v for k, v in given.items() if k in env})
    p = subprocess.run([cs._bash(), "-e", "-c", script], cwd=str(REPO), env=wenv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    return p, out.read_text(encoding="utf-8")


def label_reaches_the_selector(r):
    cs = select_module()
    env, _ = step_of("pick")
    expect("github.event.pull_request.labels" in env.get("LABELS", "") and "name" in env["LABELS"], "the LABELS value is the labels of the pull request: %r" % env.get("LABELS"))
    with tempfile.TemporaryDirectory(prefix="uak-ci-pick-") as tmp:
        tmp = Path(tmp)
        p, got = run_pick_step(cs, tmp, {"LABELS": "docs,ci-full"})
        expect(p.returncode == 0, "the pick step runs: %s" % p.stdout[-400:])
        expect(re.search(r"(?m)^tier=full$", got) and "ci-full" in got, "the label ci-full reaches the selector and the tier is full: %s" % got[:300])
        p, got = run_pick_step(cs, tmp, {"LABELS": "docs"})
        expect(p.returncode == 0 and re.search(r"(?m)^tier=first$", got), "another label leaves the first tier: %s" % got[:200])
        p, got = run_pick_step(cs, tmp, {"LABELS": "", "EVENT": "workflow_dispatch", "TIER_INPUT": "first"})
        expect(re.search(r"(?m)^tier=first$", got), "the manual input reaches the selector: %s" % got[:200])
        p, got = run_pick_step(cs, tmp, {"LABELS": "", "EVENT": "push", "REF": "refs/heads/main"})
        expect(re.search(r"(?m)^tier=full$", got), "a push to main is the whole matrix: %s" % got[:200])
    return "label, input, push"


def linux_never_retries_by_behaviour(r):
    cs = select_module()
    ci = workflow()
    m = re.search(r"RETRY: \$\{\{ (.*?) \}\}", ci)
    expect(m is not None, "the suite job computes RETRY")
    expr = m.group(1)

    def evaluate(os_name):
        py = expr.replace("matrix.shard.os", repr(os_name)).replace("&&", " and ").replace("||", " or ")
        return eval(py, {"__builtins__": {}}, {})   # the expression is the workflow's own: strings, != , && and ||
    got = {o: evaluate(o) for o in ("ubuntu-latest", "macos-latest")}
    expect(got["ubuntu-latest"] == "" and got["macos-latest"] == "--retry", "the workflow hands --retry to macOS and not to Linux: %s" % got)
    calls = []
    real = cs._real_runner
    cs._real_runner = lambda kind: (lambda name: (calls.append(name), False)[1])
    try:
        for runner_os, flag, runs in (("Linux", got["ubuntu-latest"], 1), ("Linux", "--retry", 1), ("macOS", got["macos-latest"], 2), ("Windows", "--retry", 2)):
            calls[:] = []
            old = os.environ.get("RUNNER_OS")
            os.environ["RUNNER_OS"] = runner_os
            try:
                with tempfile.TemporaryDirectory(prefix="uak-ci-run-") as tmp:
                    rc = cs.main(["run", "--kind", "smoke"] + ([flag] if flag else []) + ["--job", "x", "--out", str(Path(tmp) / "r.json"), "test_one"])
            finally:
                if old is None:
                    os.environ.pop("RUNNER_OS", None)
                else:
                    os.environ["RUNNER_OS"] = old
            expect(rc == 1 and len(calls) == runs, "%s with %r runs a failing file %d time(s), ran %d" % (runner_os, flag, runs, len(calls)))
    finally:
        cs._real_runner = real
    return "Linux 1 run even when asked, macOS and Windows 2"


def no_event_text_in_run_lines(r):
    lint = lint_module()
    ci = workflow()
    expect(lint.event_text_problems(ci) == [], "no run: line of the workflow holds event or input text: %s" % lint.event_text_problems(ci))
    bad = [("one line", "jobs:\n  a:\n    steps:\n      - run: echo ${{ github.event.pull_request.title }}\n"),
           ("a block", "jobs:\n  a:\n    steps:\n      - name: x\n        run: |\n          set -e\n          echo \"${{ inputs.tier }}\"\n"),
           ("event name", "jobs:\n  a:\n    steps:\n      - run: test '${{ github.event_name }}' = push\n"),
           ("no space", "jobs:\n  a:\n    steps:\n      - run: echo ${{github.event.number}}\n")]
    for why, text in bad:
        got = lint.event_text_problems(text)
        expect(len(got) == 1 and "env:" in got[0], "the lint refuses %s and says to pass it through env: %s" % (why, got))
    good = [("env", "jobs:\n  a:\n    steps:\n      - run: echo \"$T\"\n        env:\n          T: ${{ github.event.pull_request.title }}\n"),
            ("with", "jobs:\n  a:\n    steps:\n      - uses: x\n        with:\n          v: ${{ inputs.tier }}\n"),
            ("if", "jobs:\n  a:\n    steps:\n      - if: github.event_name == 'push'\n        run: echo ok\n"),
            ("a comment", "jobs:\n  a:\n    steps:\n      - run: echo ok # ${{ github.event.x }} is not used\n")]
    for why, text in good:
        expect(lint.event_text_problems(text) == [], "the lint accepts %s: %s" % (why, lint.event_text_problems(text)))
    return "run lines read env"


def selector_failure_fails_discover(r):
    cs = select_module()
    expect("|| true" not in cs._BASH, "the selector's failure is not swallowed with || true")
    with tempfile.TemporaryDirectory(prefix="uak-ci-sel-") as tmp:
        tmp = Path(tmp)
        kit = tmp / "kit"
        (kit / ".uak" / "bin" / "lib").mkdir(parents=True)
        (kit / ".uak" / "tests").mkdir(parents=True)
        (kit / ".uak" / "tests" / "test_a.py").write_text("", encoding="utf-8")
        lib = kit / ".uak" / "bin" / "lib" / "tests.sh"
        # answers for one file, fails for the other
        lib.write_text('tf_affected_select() {\n  if grep -q boom "$2"; then echo "selector broke" >&2; return 3; fi\n'
                       '  printf "test_a.py\\tnames it\\n"\n}\n', encoding="utf-8", newline="\n")
        got = cs._affected(["scripts/fine.py"], kit)
        expect(got == {"scripts/fine.py": [("test_a.py", "names it")]}, "the selector answers for a file: %s" % got)
        try:
            cs._affected(["scripts/fine.py", "scripts/boom.py"], kit)
            raise Failure("expected: a selector that fails for one file stops discover")
        except SystemExit as e:
            msg = str(e)
            expect("boom.py" in msg and "3" in msg and "selector broke" in msg, "the failure names the file, the code and the selector's message: %s" % msg)
        # no test names it is an answer, not a failure
        lib.write_text('tf_affected_select() { printf -- "-\\tno test file names it\\n"; }\n', encoding="utf-8", newline="\n")
        got = cs._affected(["scripts/none.py"], kit)
        expect(got == {"scripts/none.py": [("-", "no test file names it")]}, "'no test names it' is told apart from a failure: %s" % got)
    with tempfile.TemporaryDirectory(prefix="uak-ci-pick-") as tmp:
        p, got = run_pick_step(cs, Path(tmp), {"BASE": "no-such-ref-uak169"})
        expect(p.returncode != 0, "the pick step fails when the selector fails (a pipe into tee and cut hid it): rc %d, %s" % (p.returncode, p.stdout[-300:]))
        expect("tier=" not in got, "and writes no outputs: %s" % got[:200])
    return "rc and message"


def runs_on_main_counts_both_systems(r):
    cs = select_module()
    changed = [("M", "kit/.uak/tests/test_policy.py")]
    sel = cs.select(changed)
    suite = cs.tests_on_disk()
    drop = [t for t in sorted(sel["windows"]) if t != "test_policy"][:2]
    for t in drop:
        del sel["windows"][t]
    m = cs.matrices("first", sel)
    text = cs.report("first", "why", changed, sel, m)
    mac_left = len([t for t in suite if t not in sel["macos"]])
    win_left = len([t for t in suite if t not in sel["windows"]])
    expect(win_left == mac_left + len(drop), "the case set up a difference of %d" % len(drop))
    line = next((l for l in text.splitlines() if l.startswith("runs on main")), "")
    expect("macOS %d of %d" % (mac_left, len(suite)) in line and "Windows %d of %d" % (win_left, len(suite)) in line,
           "the line counts both systems (macOS %d, Windows %d of %d): %r" % (mac_left, win_left, len(suite), line))
    return line


TESTS = TESTS + [slow_file_is_not_run_twice, second_run_must_fit_the_bound, cancelled_job_names_its_file, slow_runner_fails_fast_with_a_clear_line,
                 ci_needs_success_not_skipped, cancelled_main_does_not_close_the_issue, red_main_says_which_kind_of_failure,
                 portability_set_has_no_intermittent_file, label_reaches_the_selector, linux_never_retries_by_behaviour,
                 no_event_text_in_run_lines, selector_failure_fails_discover, runs_on_main_counts_both_systems]


# ---- UAK-169, review of 4617b86a: the fail-fast rule, the retry's bound, the group kill, the wider event lint ----------
def _replay(cs, names, table, factor, bound, actual_override=None):
    """Run `names` in order on a fake clock, each file taking factor x its table entry (or its override); returns (result, calls)."""
    clock = Clock()
    over = actual_override or {}
    run = timed_runner(clock, {n: over.get(n, table[n] * factor) for n in names})
    res = cs.run_files(names, run, retry=True, log=lambda s: None, seconds=table.get, bound=bound, clock=clock)
    return res, run.calls


def one_stale_entry_cannot_trip_the_slow_rule(r):
    cs = select_module()
    lint = lint_module()
    # the reviewer's scenario: the 13-file Windows shard that holds test_done_without_github (68 s in the table, 187 to 263 s
    # really), every other file 1.55 times its entry: the job still ends inside its bound
    shard = next(s["tests"].split() for s in lint.ci_windows_shards(lint.windows_shard_count()) if "test_done_without_github" in s["tests"].split())
    table = {t: lint.ci_windows_seconds(t) for t in shard}
    for real in (187, 225, 263):
        res, calls = _replay(cs, shard, table, 1.55, 2400, {"test_done_without_github": real})
        expect(not res["slow"] and len(calls) == len(shard), "1.55 times with test_done_without_github at %d s is not a slow runner: %s after %d of %d files" % (real, res["slow"], len(calls), len(shard)))
    # the same stale entry first, among small files: a total/total ratio is 3.3 here, the median of the ratios is 1.55
    small = {"test_done_without_github": 68, "test_s1": 5, "test_s2": 5, "test_s3": 5, "test_s4": 5, "test_s5": 600, "test_s6": 600}
    names = list(small)
    res, calls = _replay(cs, names, small, 1.55, 2400, {"test_done_without_github": 263})
    expect(not res["slow"] and len(calls) == len(names), "one stale entry among small files does not trip it: %s" % res["slow"])
    # a rule over fewer than 5 finished files, or fewer than 30 table seconds, says nothing
    few = {"test_a": 40, "test_b": 40, "test_c": 40, "test_d": 40, "test_e": 400}
    res, calls = _replay(cs, list(few), few, 10, 2400)
    expect(len(calls) >= 5 or not res["slow"], "4 files are not enough to judge: %s after %d" % (res["slow"], len(calls)))
    return "1.55x with a stale entry passes"


def truly_slow_job_trips_early(r):
    cs = select_module()
    lint = lint_module()
    # windows (4) of run 45232891834: every file 9 to 10 times its entry
    names = ["test_design_breed_rules", "test_design_brief_real", "test_design_metrics", "test_design_prior", "test_design_shoot_full",
             "test_done_without_github", "test_guard_substitution", "test_harvest_discovery", "test_integrate_unreviewed"]
    table = {t: lint.ci_windows_seconds(t) for t in names}
    res, calls = _replay(cs, names, table, 9.5, 2400)
    expect(res["slow"].startswith("slow runner, re-run"), "9.5 times slower is a slow runner: %r" % res["slow"])
    expect(len(calls) == 5 and res["stopped"] == "test_done_without_github", "it stops after the fifth file, before the long one: %s, stopped %s" % (calls, res["stopped"]))
    expect("median" in res["slow"], "the line says what it measured: %s" % res["slow"])
    return "stops after %d files" % len(calls)


def retry_gets_the_time_left_to_the_bound(r):
    cs = select_module()
    clock = Clock()
    table = {"test_a": 2000, "test_b": 100}

    class Runner:
        def __init__(self):
            self.timeout, self.timed_out, self.timeouts, self.n = None, False, [], {}

        def __call__(self, name):
            self.timeouts.append(self.timeout)
            self.n[name] = self.n.get(name, 0) + 1
            self.timed_out = False
            if name == "test_a":
                clock.t += 2000
                return True
            if self.n[name] == 1:
                clock.t += 50
                return False
            clock.t += self.timeout            # the retry hangs until it is killed
            self.timed_out = True
            return False
    h = Runner()
    res = cs.run_files(["test_a", "test_b"], h, retry=True, log=lambda s: None, seconds=table.get, bound=2400, clock=clock)
    expect(h.timeouts == [2400, 400, 350], "every run gets what is left of the bound (2400; 2400-2000 for test_b; 2400-2050 for its retry): %s" % h.timeouts)
    expect(clock() - 1000.0 <= 2400, "the job ends inside its bound, not at 2500: %s" % (clock() - 1000.0))
    expect(res["stopped"] == "test_b" and res["failed"] == ["test_b"], "the retry killed by the bound stops the job: %s" % res)
    rep = cs.flaky_report("windows (2)", res)
    expect("stopped at the job's bound" in rep["summary"] and "failed both times" not in rep["summary"].lower(), "it says the bound, not 'failed both times': %s" % rep["summary"])
    expect(not any("both times" in a for a in rep["annotations"]), "no annotation says both times: %s" % rep["annotations"])
    return "timeouts %s" % h.timeouts


def bound_kill_reaches_the_grandchild(r):
    cs = select_module()
    with tempfile.TemporaryDirectory(prefix="uak-ci-kill-") as tmp:
        pids = Path(tmp) / "pids"
        code = ("import os, subprocess, sys, time\n"
                "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
                "open(%r, 'w').write('%%d %%d' %% (os.getpid(), g.pid))\n"
                "time.sleep(300)\n" % str(pids))
        run = cs._real_runner("windows")
        run._popen = lambda name: cs._start([sys.executable, "-c", code])
        run.timeout = 6
        started = time.monotonic()
        ok = run("test_fake")
        expect(ok is False and run.timed_out, "a file that passes its timeout fails and says it timed out: %s %s" % (ok, run.timed_out))
        expect(time.monotonic() - started < 60, "and the kill does not wait for the sleep")
        expect(pids.is_file(), "the file started its grandchild before the kill")
        child, grand = [int(x) for x in pids.read_text().split()]

        def alive(pid):
            if os.name == "nt":
                out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid], stdout=subprocess.PIPE, universal_newlines=True).stdout
                return str(pid) in out
            try:
                state = Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()[0]
                return state not in ("Z", "X")
            except OSError:
                try:
                    os.kill(pid, 0)
                except OSError:
                    return False
                return True
        end = time.monotonic() + 10
        while time.monotonic() < end and (alive(child) or alive(grand)):
            time.sleep(0.2)
        left = [p for p in (child, grand) if alive(p)]
        for p in left:   # only the PIDs this case created
            try:
                os.kill(p, 9)
            except OSError:
                pass
        expect(not left, "after the kill neither the file's process nor its grandchild is alive: %s" % left)
    return "child and grandchild gone"


def event_text_lint_reads_expressions(r):
    lint = lint_module()
    for why, expr in (("toJSON", "toJSON(github.event)"), ("format", "format('{0}', github.event.pull_request.title)"), ("join", "join(github.event.pull_request.labels.*.name, ',')"),
                      ("head_ref", "github.head_ref"), ("upper case", "GitHub.Event.number"), ("inputs in a function", "fromJSON(inputs.tier)"),
                      ("inputs upper", "INPUTS.tier"), ("no spaces", "format('{0}',github.head_ref)")):
        for form in ("      - run: echo ${{ %s }}\n" % expr, "      - run: |\n          echo ${{ %s }}\n" % expr):
            got = lint.event_text_problems("jobs:\n  a:\n    steps:\n" + form)
            expect(len(got) == 1, "the lint refuses %s in a run line: %s" % (why, got))
    for why, text in (("env", "      - run: echo \"$T\"\n        env:\n          T: ${{ github.head_ref }}\n"),
                      ("a safe expression", "      - run: echo ${{ matrix.shard.n }} ${{ runner.os }}\n"),
                      ("an input named like one", "      - run: echo ${{ steps.pick.outputs.inputs_x }}\n")):
        expect(lint.event_text_problems("jobs:\n  a:\n    steps:\n" + text) == [], "the lint accepts %s" % why)
    return "expressions read"


TESTS = TESTS + [one_stale_entry_cannot_trip_the_slow_rule, truly_slow_job_trips_early, retry_gets_the_time_left_to_the_bound,
                 bound_kill_reaches_the_grandchild, event_text_lint_reads_expressions]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    parser.parse_args()
    args = parser.parse_args()
    if not source_repository():
        print("CI_TIERS_RESULT PASS passed=0 failed=0 (no kit source repository here: the selection is made by its scripts/)")
        return 0
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        started = time.monotonic()
        try:
            note = test(None)
            print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s)" % (test.__name__, str(exc)[:1500]))
    print("CI_TIERS_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(TESTS) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
