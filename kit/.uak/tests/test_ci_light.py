#!/usr/bin/env python3
"""UAK-090: pull requests run a light CI (Ubuntu suite + the Windows per-file job); main and workflow_dispatch keep the
full matrix with macOS. Why: approved PRs #19-#21 waited hours for macOS arm64 runners GitHub could not provide
(2026-11-13), while Ubuntu and Windows had passed. Reads the workflow text (no YAML library on every runner)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXCLUDE = "${{ github.event_name == 'pull_request' && 'macos-latest' || 'none' }}"


def workflow():
    return (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")


def job(text, name):
    m = re.search(r"(?ms)^  %s:\n(.*?)(?=^  [A-Za-z_-]+:\n|\Z)" % re.escape(name), text)
    assert m, "test.yml has the %s job" % name
    return m.group(1)


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def pull_requests_skip_macos():
    suite = job(workflow(), "suite")
    expect("os: [ubuntu-latest, macos-latest]" in suite, "the suite still lists both OSes (main runs them)")
    strategy = suite[suite.index("strategy:"):suite.index("runs-on:")]
    expect(re.search(r"(?m)^\s+exclude:\s*$", strategy), "the suite matrix has an exclude list: %r" % strategy)
    expect("- os: " + EXCLUDE in strategy,
           "macOS is excluded exactly when the event is pull_request: %r" % strategy)
    expect("capacity" in strategy, "a comment next to the exclusion cites the macOS capacity incident")


def main_runs_macos():
    text = workflow()
    # The exclusion matches only on pull_request: on push (main) and workflow_dispatch it names 'none', no OS.
    for event, excluded in (("pull_request", "macos-latest"), ("push", "none"), ("workflow_dispatch", "none")):
        value = "macos-latest" if event == "pull_request" else "none"
        expect(value == excluded, event)
    expect(EXCLUDE in text, "the exclusion expression is the event test, so main keeps macOS")
    windows = job(text, "windows")
    expect("pull_request" not in windows and "event_name" not in windows, "the Windows job is unchanged on every event")
    on = re.search(r"(?ms)^on:\n(.*?)^\S", text).group(1)
    expect(re.search(r"(?m)^  push:\n    branches: \[main\]", on), "main still runs on push")
    expect(re.search(r"(?m)^  workflow_dispatch:", on), "workflow_dispatch still runs the full matrix on demand")


def main():
    failed = 0
    for test in (pull_requests_skip_macos, main_runs_macos):
        try:
            test()
            print("PASS " + test.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL %s: %s" % (test.__name__, exc))
    print("CI_LIGHT_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
