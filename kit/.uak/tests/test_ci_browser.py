#!/usr/bin/env python3
"""UAK-195: the kit's CI has a browser, and a case that did not run says so. Why: on 2026-11-24 and 25 the reviews of UAK-159,
UAK-162, UAK-192 and UAK-194 found defects only a browser shows (a click refused in the first second after load, a tab that
stopped drawing on partial data, a dialog that opened nothing), while every case that needs Playwright passed in CI without
running: it found no browser, returned early and printed PASS.

The convention (scripts/ci_select.py reads it; AGENTS.md states the rule):
  PASS <case> (browser, <detail>)    the case ran in a real Chromium
  SKIP <case> (no browser)           the case needs a browser and found none: not a pass
  <FILE>_RESULT PASS failed=<n> skipped=<k>   the result line counts the skips
A Linux suite job of the kit's CI installs Playwright and Chromium (pinned, cached) and declares it with UAK_CI_BROWSER=1:
there the runner checks that Chromium launches before any file, and a SKIP for lack of a browser fails its file. macOS,
Windows and a developer's machine without Playwright keep a skip a skip. This file follows the convention itself."""
import argparse
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
KIT = REPO / "kit"
WORKFLOW = REPO / ".github" / "workflows" / "test.yml"
SCRIPT = REPO / "scripts" / "ci_select.py"
ENV_NAMES = ("UAK_CI_BROWSER", "UAK_CI_BROWSER_CHECKED", "UAK_TEST_NODE_PLAYWRIGHT", "GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "RUNNER_OS")


class Failure(Exception):
    pass


class NoBrowser(Exception):
    """The case needs a real Chromium and there is none here: printed as `SKIP name (no browser)`, never as PASS."""


def expect(condition, message):
    if not condition:
        raise Failure("expected: " + message)


_cache = {}


def cs():
    if "cs" not in _cache:
        expect(SCRIPT.is_file(), "scripts/ci_select.py exists")
        spec = importlib.util.spec_from_file_location("ci_select_for_browser", str(SCRIPT))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _cache["cs"] = mod
    return _cache["cs"]


def source_repository():
    return SCRIPT.is_file() and WORKFLOW.is_file() and (REPO / "install.sh").is_file()


def clean_env(**extra):
    """The caller's environment without the CI's browser declaration or step files: a case sets what it tests."""
    env = {k: v for k, v in os.environ.items() if k not in ENV_NAMES}
    env.update(extra)
    return env


def job_block(text, name):
    m = re.search(r"(?ms)^  %s:\n(.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)" % re.escape(name), text)
    expect(m is not None, "the workflow has a job %s" % name)
    return m.group(1)


def steps_of(block):
    """[(text of the step)] in order: each begins at a line `      - `."""
    parts = re.split(r"(?m)^      - ", block)
    return ["- " + p for p in parts[1:]]


# ---- fixtures: small test files the real runner runs ----------------------------------------------------------------
FAKE_OK = '''
class _Page:
    def set_content(self, html):
        pass
    def text_content(self, sel):
        return "ok"
class _Browser:
    version = "0.0-fake"
    def new_page(self):
        return _Page()
    def close(self):
        pass
class _Chromium:
    def launch(self, **kw):
        return _Browser()
class _PW:
    chromium = _Chromium()
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
def sync_playwright():
    return _PW()
'''
FAKE_BROKEN = FAKE_OK.replace("        return _Browser()", "        raise Exception(\"BrowserType.launch: Executable doesn't exist at /ms-playwright/chromium_headless_shell-0/chrome-headless-shell\")")


def fake_playwright(root, kind):
    """A folder for PYTHONPATH holding a stand-in `playwright`: ok (launches), broken (Chromium missing), missing (no import)."""
    d = root / ("pw-" + kind)
    (d / "playwright").mkdir(parents=True, exist_ok=True)
    if kind == "missing":
        (d / "playwright" / "__init__.py").write_text("raise ImportError(\"No module named 'playwright' (stand-in)\")\n", encoding="utf-8")
    else:
        (d / "playwright" / "__init__.py").write_text("__version__ = '0.0-fake'\n", encoding="utf-8")
        (d / "playwright" / "sync_api.py").write_text(FAKE_OK if kind == "ok" else FAKE_BROKEN, encoding="utf-8")
    return d


def write_case_file(folder, name, lines, code=0, before=""):
    folder.mkdir(parents=True, exist_ok=True)
    body = before + "".join("print(%r, flush=True)\n" % l for l in lines) + "raise SystemExit(%d)\n" % code
    (folder / (name + ".py")).write_text(body, encoding="utf-8")


REAL_BROWSER_CASE = '''
import time
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    page = b.new_page()
    page.set_content("<button id=b onclick=\\"this.textContent='clicked'\\">go</button>")
    page.click("#b")
    said = page.text_content("#b")
    time.sleep(0.6)   # the runner looks for the browser every 0.1 s
    b.close()
assert said == "clicked", said
'''


def run_one(folder, name, declared=False, kind="windows"):
    """The real runner with its output read (the explicit switch: the job's runner reads only where a browser is declared),
    stdout read line by line and, on Linux, Chromium launches watched, on one fixture file."""
    mod = cs()
    runner = mod._RealRunner(kind, tests_dir=folder, read_output=True)
    logs = []
    # the runner copies the file's lines to stdout: kept here, or this file's own output would carry the fixtures' SKIP lines
    real, sys.stdout = sys.stdout, io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    try:
        res = mod.run_files([name], runner, retry=False, log=logs.append, browser_declared=declared, job="suite (ubuntu-latest, 9)")
        sys.stdout.flush()
        logs.append(sys.stdout.buffer.getvalue().decode("utf-8", "replace"))
    finally:
        sys.stdout = real
    return res, logs


def cli_run(folder, names, env, out=None, job="suite (ubuntu-latest, 9)"):
    cmd = [sys.executable, str(SCRIPT), "run", "--kind", "windows", "--tests-dir", str(folder), "--job", job]
    if out:
        cmd += ["--out", str(out)]
    return subprocess.run(cmd + list(names), cwd=str(REPO), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True, errors="replace", timeout=300)


# ---- the cases ------------------------------------------------------------------------------------------------------
def browser_cases_run_on_the_linux_job(tmp):
    text = WORKFLOW.read_text(encoding="utf-8")
    suite = job_block(text, "suite")
    steps = steps_of(suite)
    names = [re.search(r"(?m)^- (?:name|uses): (.*)$", s).group(1) if re.search(r"(?m)^- (?:name|uses): (.*)$", s) else s[:40] for s in steps]
    tests_at = next((i for i, s in enumerate(steps) if "ci_select.py run --kind smoke" in s), -1)
    expect(tests_at > 0, "the suite job runs its files with ci_select.py run: %r" % names)
    cache_at = next((i for i, s in enumerate(steps) if "actions/cache@" in s), -1)
    install_at = next((i for i, s in enumerate(steps) if "ci_select.py browser-install" in s), -1)
    expect(0 <= cache_at < install_at < tests_at, "a cache step, then the browser install, both before the tests: %r" % names)
    for i in (cache_at, install_at):
        expect(re.search(r"(?m)^        if: runner\.os == 'Linux'\s*$", steps[i]), "only Linux installs the browser: %s" % steps[i][:300])
    py = re.search(r"(?m)^      UAK_PLAYWRIGHT: \"(\d+\.\d+\.\d+)\"\s*$", suite)
    node = re.search(r"(?m)^      UAK_NODE_PLAYWRIGHT: \"(\d+\.\d+\.\d+)\"\s*$", suite)
    expect(py and node, "the suite job pins Playwright to exact versions (UAK_PLAYWRIGHT, UAK_NODE_PLAYWRIGHT)")
    key = re.search(r"(?m)^          key: (.*)$", steps[cache_at])
    expect(key and "env.UAK_PLAYWRIGHT" in key.group(1) and "env.UAK_NODE_PLAYWRIGHT" in key.group(1) and "runner.os" in key.group(1),
           "the cache key names both pinned versions and the system: %s" % (key.group(1) if key else steps[cache_at][:200]))
    expect('--playwright "$UAK_PLAYWRIGHT"' in steps[install_at] and '--node-playwright "$UAK_NODE_PLAYWRIGHT"' in steps[install_at]
           and '--github-env "$GITHUB_ENV"' in steps[install_at], "the install uses the pinned versions and exports where they are: %s" % steps[install_at][:400])
    expect(re.search(r"(?m)^          UAK_CI_BROWSER: \$\{\{ matrix\.shard\.os == 'ubuntu-latest' && '1' \|\| '' \}\}\s*$", steps[tests_at]),
           "the tests step declares the browser on Linux only (UAK_CI_BROWSER)")
    win = job_block(text, "windows")
    expect("UAK_CI_BROWSER" not in win and "browser-install" not in win and "playwright" not in win.lower(), "Windows has no browser and declares none")
    # the real thing: a case that drives Chromium runs through the runner, which counts it and sees the launch
    mod = cs()
    ok, said = mod.browser_check(env=clean_env())
    if not ok:
        if mod.browser_declared(os.environ):
            raise Failure("this job declares a browser (UAK_CI_BROWSER=%s) and none launches: %s" % (os.environ.get("UAK_CI_BROWSER"), said))
        raise NoBrowser(said)
    folder = tmp / "real"
    write_case_file(folder, "fx_real", ["PASS clicks_a_button (browser, clicked)", "FX_REAL_RESULT PASS failed=0 skipped=0"], before=REAL_BROWSER_CASE)
    res, logs = run_one(folder, "fx_real", declared=True)
    seen = res["browser"].get("fx_real") or {}
    expect(res["failed"] == [] and seen.get("ran") == ["clicks_a_button"] and seen.get("skipped") == [], "the case ran in Chromium and passed: %r %s" % (res, logs[-3:]))
    if sys.platform.startswith("linux"):
        expect((seen.get("launches") or 0) >= 1, "the runner saw Chromium start under the file: %r" % seen)
        write_case_file(folder, "fx_none", ["PASS reads_the_source (0.01s)", "FX_NONE_RESULT PASS failed=0 skipped=0"], before="import time\ntime.sleep(0.4)\n")
        res2, _ = run_one(folder, "fx_none", declared=True)
        expect(res2["browser"]["fx_none"].get("launches") == 0, "a file that starts no browser shows 0 launches: %r" % res2["browser"])
    return "browser, %s; launches seen %s" % (said, seen.get("launches"))


def skip_without_browser_is_not_a_pass(tmp):
    mod = cs()
    lines = ["PASS reads_the_page (0.01s)", "SKIP clicks_the_button (no browser)", "PASS drags_a_card (browser, 1.2s)",
             "SKIP opens_the_dialog (no browser)", "PASS opens_the_dialog (browser, 0.3s)", "SKIP schedule_never_follows_links: no symlinks here",
             "SKIP review HACK-001 | already approved", "FX_RESULT PASS failed=0 skipped=2"]
    got = mod.read_browser_lines(lines)
    expect(got["skipped"] == ["clicks_the_button", "opens_the_dialog"], "two cases skipped for lack of a browser: %r" % got)
    expect(got["ran"] == ["drags_a_card"], "only the browser PASS counts as run in a browser; a SKIP then a PASS of the same case is a skip: %r" % got)
    expect(got["result_skipped"] == 2 and got["problems"] == [], "the result line counts both: %r" % got)
    short = mod.read_browser_lines(lines[:-1] + ["FX_RESULT PASS failed=0"])
    expect(short["problems"] and "skipped=" in short["problems"][0], "a result line that does not count the skips is a problem: %r" % short)
    under = mod.read_browser_lines(lines[:-1] + ["FX_RESULT PASS failed=0 skipped=1"])
    expect(under["problems"], "a result line that counts fewer skips than were printed is a problem: %r" % under)
    today = mod.read_browser_lines(["PASS flow_has_the_ten_screens (28.43s)", "SETUP_GUIDE_RESULT PASS failed=0"])
    expect(today == {"ran": [], "skipped": [], "result_skipped": None, "problems": [], "converted": False}, "today's output: nothing ran in a browser, nothing skipped, no problem: %r" % today)
    # through the real runner, with no browser declared (macOS, Windows, a developer's machine): the file passes, the case is a skip
    folder = tmp / "skip"
    write_case_file(folder, "fx_skip", ["PASS reads_the_page (0.01s)", "SKIP clicks_the_button (no browser)", "FX_SKIP_RESULT PASS failed=0 skipped=1"])
    res, _ = run_one(folder, "fx_skip", declared=False)
    seen = res["browser"].get("fx_skip") or {}
    expect(res["failed"] == [] and seen.get("skipped") == ["clicks_the_button"] and seen.get("ran") == [], "a skip stays a skip where no browser is declared: %r" % res)
    rep = mod.flaky_report("macos (1)", res)
    expect("1 skipped (no browser)" in rep["summary"] and "0 ran in a browser" in rep["summary"], "the summary says it was skipped, not run: %s" % rep["summary"])
    # a file that prints the SKIP and a result line that hides it fails on every system
    write_case_file(folder, "fx_hidden", ["SKIP clicks_the_button (no browser)", "FX_HIDDEN_RESULT PASS failed=0"])
    res, _ = run_one(folder, "fx_hidden", declared=False)
    expect(res["failed"] == ["fx_hidden"] and "skipped=" in res["no_browser"].get("fx_hidden", ""), "a skip the result line does not count fails: %r" % res)
    # the CLI passes the file's lines through and says the same
    out = cli_run(folder, ["fx_skip"], clean_env())
    expect(out.returncode == 0 and "SKIP clicks_the_button (no browser)" in out.stdout and "browser cases:" not in out.stdout,
           "no browser declared: the file runs as before (its output not read), it passes and shows the skip: rc %d %s" % (out.returncode, out.stdout[-800:]))
    expect(mod._real_runner("windows").read_output is False and mod._real_runner("smoke").read_output is False,
           "the job's runner reads no output unless a browser is declared")
    return "a skip is counted as a skip"


def skip_fails_where_a_browser_is_declared(tmp):
    mod = cs()
    for value, want in (("1", True), ("", False), ("0", False), (None, False)):
        env = {} if value is None else {"UAK_CI_BROWSER": value}
        expect(mod.browser_declared(env) is want, "UAK_CI_BROWSER=%r declares a browser: %s" % (value, want))
    folder = tmp / "declared"
    write_case_file(folder, "fx_skip", ["PASS reads_the_page (0.01s)", "SKIP clicks_the_button (no browser)", "FX_SKIP_RESULT PASS failed=0 skipped=1"])
    write_case_file(folder, "fx_plain", ["PASS reads_the_page (0.01s)", "FX_PLAIN_RESULT PASS failed=0 skipped=0"])
    res, _ = run_one(folder, "fx_skip", declared=True)
    expect(res["failed"] == ["fx_skip"] and "clicks_the_button" in res["no_browser"].get("fx_skip", ""), "declared: the skip fails its file: %r" % res)
    rep = mod.flaky_report("suite (ubuntu-latest, 1)", res)
    expect(rep["conclusion"] == "failed" and any("title=no browser" in a and "fx_skip" in a and "clicks_the_button" in a for a in rep["annotations"]),
           "the annotation names the file and the case: %r" % rep["annotations"])
    res, _ = run_one(folder, "fx_plain", declared=True)
    expect(res["failed"] == [], "declared: a file with no skip passes: %r" % res)
    # the CLI: a stand-in Playwright that launches, so the check before the files passes and the skip is what fails
    ok_pw, broken_pw, missing_pw = (fake_playwright(tmp, k) for k in ("ok", "broken", "missing"))
    out = cli_run(folder, ["fx_skip"], clean_env(UAK_CI_BROWSER="1", PYTHONPATH=str(ok_pw)))
    expect(out.returncode == 1 and "fx_skip" in out.stdout and "clicks_the_button" in out.stdout and "UAK_CI_BROWSER" in out.stdout,
           "declared, a skip fails the job and says which case: rc %d %s" % (out.returncode, out.stdout[-900:]))
    out = cli_run(folder, ["fx_skip"], clean_env(PYTHONPATH=str(missing_pw)))
    expect(out.returncode == 0 and "browser cases:" not in out.stdout, "not declared, the same skip passes and nothing is read: rc %d %s" % (out.returncode, out.stdout[-600:]))
    out = cli_run(folder, ["fx_skip"], clean_env(UAK_CI_BROWSER="1", UAK_CI_BROWSER_CHECKED="Chromium 1"))
    expect("browser cases: 0 ran in a browser, 1 skipped (no browser)" in out.stdout, "declared: the output is read and counted: %s" % out.stdout[-600:])
    # declared on a job without a browser: the job fails before any file, saying what is missing
    for pw, says in ((missing_pw, "cannot import Playwright"), (broken_pw, "Chromium does not launch")):
        out = cli_run(folder, ["fx_plain"], clean_env(UAK_CI_BROWSER="1", PYTHONPATH=str(pw)))
        expect(out.returncode == 1 and says in out.stdout and "FX_PLAIN_RESULT" not in out.stdout,
               "declared without a browser (%s): fails before the files: rc %d %s" % (pw.name, out.returncode, out.stdout[-900:]))
    # a run started inside a file of a job whose run checked the browser (test_ci_tiers drives this runner) does not launch it again
    out = cli_run(folder, ["fx_skip"], clean_env(UAK_CI_BROWSER="1", UAK_CI_BROWSER_CHECKED="Chromium 1", PYTHONPATH=str(missing_pw)))
    expect(out.returncode == 1 and "checked by the job's run" in out.stdout and "clicks_the_button" in out.stdout,
           "a nested run trusts the job's check and still fails the skip: rc %d %s" % (out.returncode, out.stdout[-600:]))
    out = cli_run(folder, ["fx_plain"], clean_env(UAK_CI_BROWSER="1", PYTHONPATH=str(ok_pw), UAK_TEST_NODE_PLAYWRIGHT=str(tmp / "no-node-modules")))
    expect(out.returncode == 1 and "UAK_TEST_NODE_PLAYWRIGHT" in out.stdout and "FX_PLAIN_RESULT" not in out.stdout,
           "a Node Playwright folder that is not there fails the check: rc %d %s" % (out.returncode, out.stdout[-900:]))
    return "a skip fails where a browser is declared; a declared job without one fails first"


def summary_counts_browser_cases(tmp):
    mod = cs()
    res = {"ran": ["a", "b", "c"], "failed": [], "flaky": [], "counts": {"a": {"runs": 1, "failures": 0}, "b": {"runs": 1, "failures": 0}, "c": {"runs": 1, "failures": 0}},
           "not_rerun": {}, "slow": "", "stopped": "", "no_browser": {},
           "browser": {"a": {"ran": ["x", "y"], "skipped": [], "launches": 3}, "b": {"ran": ["z"], "skipped": ["w"], "launches": 1}, "c": {"ran": [], "skipped": [], "launches": 0}}}
    rep = mod.flaky_report("suite (ubuntu-latest, 2)", res)
    expect("- browser cases: 3 ran in a browser, 1 skipped (no browser); Chromium launches seen: 4 in 2 files" in rep["summary"], "the job's summary counts them: %s" % rep["summary"])
    out = tmp / "result.json"
    mod.write_result(str(out), "suite (ubuntu-latest, 2)", dict(res, conclusion="passed"))
    body = json.loads(out.read_text(encoding="utf-8"))
    expect(body["browser"] == res["browser"] and body.get("system") in ("Linux", "macOS", "Windows"), "the result JSON keeps the counts and the system: %r" % body)
    results = [dict(body, system="Linux"), {"job": "suite (macos-latest, 1)", "system": "macOS", "browser": {"a": {"ran": [], "skipped": ["x", "y"], "launches": None}}},
               {"job": "suite (ubuntu-latest, 3)", "browser": {"d": {"ran": ["q"], "skipped": [], "launches": 2}}}]
    text = mod.browser_summary(results)
    for line in ("- Linux: 4 ran in a browser, 1 skipped (no browser); Chromium launches seen: 6 in 3 files",
                 "- macOS: 0 ran in a browser, 2 skipped (no browser); Chromium launches not counted on this system",
                 "- Windows: no result files"):
        expect(line in text, "per system: %r in %s" % (line, text))
    unread = mod.browser_summary([{"job": "windows (1)", "system": "Windows", "browser_read": False, "browser": {}}])
    expect("- Windows: output not read (no browser declared there" in unread, "a system whose output was not read says so, not 0 of 0: %s" % unread)
    # the gate writes it to the run's summary, from the result artifacts, and still judges only the jobs
    rd = tmp / "results" / "result-ubuntu-latest-2"
    rd.mkdir(parents=True)
    (rd / "result.json").write_text(json.dumps(dict(body, system="Linux")), encoding="utf-8")
    summary = tmp / "summary.md"
    needs = {"discover": {"result": "success"}, "suite": {"result": "success"}, "windows": {"result": "success"}}
    g = subprocess.run([sys.executable, str(SCRIPT), "gate", "--results", str(tmp / "results")], cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, env=clean_env(NEEDS=json.dumps(needs), PLANNED="discover,suite,windows", GITHUB_STEP_SUMMARY=str(summary)), timeout=60)
    written = summary.read_text(encoding="utf-8") if summary.exists() else ""
    expect(g.returncode == 0 and "- Linux: 3 ran in a browser, 1 skipped (no browser); Chromium launches seen: 4 in 2 files" in written,
           "the gate's summary counts per system: rc %d %s %s" % (g.returncode, written, g.stdout[-400:]))
    g = subprocess.run([sys.executable, str(SCRIPT), "gate", "--results", str(tmp / "results")], cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, env=clean_env(NEEDS=json.dumps(dict(needs, suite={"result": "failure"})), PLANNED="discover,suite,windows"), timeout=60)
    expect(g.returncode == 1, "the counts never turn a failed job green: rc %d %s" % (g.returncode, g.stdout[-300:]))
    ci = job_block(WORKFLOW.read_text(encoding="utf-8"), "ci")
    expect("actions/download-artifact@" in ci and "pattern: result-*" in ci and "ci_select.py gate --results" in ci, "the ci job reads the jobs' results: %s" % ci[-600:])
    return "per job and per system"


def install_gains_no_file(tmp):
    words = ("UAK_CI_BROWSER", "browser-install", "PLAYWRIGHT_BROWSERS_PATH", "ms-playwright", "playwright==", "UAK_PLAYWRIGHT", "uak-ci-browser")
    install_text = (REPO / "install.sh").read_text(encoding="utf-8")
    expect(not any(w in install_text for w in words) and "playwright install" not in install_text, "install.sh downloads no browser")
    target = tmp / "project"
    target.mkdir()
    subprocess.run(["git", "-C", str(target), "init", "-q", "-b", "main"], check=True, stdout=subprocess.DEVNULL)
    env = clean_env(UAK_EXTERNAL_SKILLS="off")
    out = subprocess.run([cs()._bash(), str(REPO / "install.sh"), "--mode", "marathon", str(target)], cwd=str(REPO), env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, errors="replace", timeout=300)
    expect(out.returncode == 0 and (target / ".uak" / "PROJECT.md").is_file(), "the kit installs: %s" % out.stdout[-600:])
    placed = [p for p in target.rglob("*") if p.is_file() and ".git" not in p.relative_to(target).parts]
    expect(placed, "the install placed files")
    names = {p.name for p in placed}
    for forbidden in ("test_ci_browser.py", "test_ci_browser.txt", "ci_select.py", "test.yml", "package.json", "package-lock.json", "requirements.txt"):
        expect(forbidden not in names, "an installed project gains no %s" % forbidden)
    for p in placed:
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit = [w for w in words if w in body]
        expect(not hit, "%s names the CI's browser (%s): the browser is the kit's CI's, not the product's" % (p.relative_to(target), hit))
    # the files this task adds or changes are the kit's CI's: none of them is installed (a fixed list, not "nothing new against main")
    own = (".uak/tests/test_ci_browser.py", ".uak/tests/timings/test_ci_browser.txt", "scripts/ci_select.py", ".github/workflows/test.yml")
    rel = {q.relative_to(target).as_posix() for q in placed}
    expect(not [x for x in own if x in rel], "this task's own files are not installed: %s" % [x for x in own if x in rel])
    return "%d files placed, none of this task's files, none naming the CI's browser" % len(placed)


TESTS = [browser_cases_run_on_the_linux_job, skip_without_browser_is_not_a_pass, skip_fails_where_a_browser_is_declared,
         summary_counts_browser_cases, install_gains_no_file]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    if not source_repository():
        print("CI_BROWSER_RESULT PASS failed=0 skipped=0 (no kit source repository here: the CI is its scripts/ and .github/)")
        return 0
    failed = skipped = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        started = time.monotonic()
        tmp = Path(tempfile.mkdtemp(prefix="uak-ci-browser-"))
        try:
            note = test(tmp)
            print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started), flush=True)
        except NoBrowser as why:
            skipped += 1
            print("SKIP %s (no browser)" % test.__name__, flush=True)
            print("  why: %s" % str(why)[:300], flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s: %s)" % (test.__name__, type(exc).__name__, str(exc)[:1500]), flush=True)
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("CI_BROWSER_RESULT %s failed=%d skipped=%d" % ("PASS" if not failed else "FAIL", failed, skipped))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
