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
