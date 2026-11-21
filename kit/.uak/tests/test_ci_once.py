#!/usr/bin/env python3
"""UAK-067: every feature SHA ran the full CI matrix twice, once for `push` and once for `pull_request` (172 checks,
8 macOS jobs). With GitHub's macOS arm64 capacity short, UAK-013's last macOS job was cancelled about 7 times with 0
steps and a ready task waited ~2 h (notes/handoff:PENDING-IMPROVEMENTS.md #24, 2026-11-12).

The matrix now runs once per feature SHA, on pull_request; pushes to main still run it in full after every merge and
workflow_dispatch runs it on demand. A newer push to a pull request cancels that pull request's older runs; runs on
main are never cancelled. scripts/kit_lint.py fails when the duplication or the missing cancellation comes back.

The checks read ../.github/workflows/test.yml of the kit's source repository; an installed project has neither the
workflow nor kit_lint.py, and the tests say so instead of failing."""
import argparse
import importlib.util
import inspect
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "test.yml"


class Skip(Exception):
    pass


def expect(cond, message):
    if not cond:
        raise AssertionError(message)


def kit_lint():
    p = REPO / "scripts" / "kit_lint.py"
    if not p.is_file() or not WORKFLOW.is_file():
        raise Skip("no kit source repository here: the CI workflow and kit_lint.py live there")
    spec = importlib.util.spec_from_file_location("kit_lint_for_ci_once", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    expect(hasattr(mod, "ci_once_problems") and hasattr(mod, "check_ci_once"),
           "kit_lint.py has no ci_once_problems(text) / check_ci_once(findings)")
    return mod


def workflow():
    return WORKFLOW.read_text(encoding="utf-8")


def on_block(text):
    """The workflow's top-level `on:` (a flow list or a block), as text."""
    m = re.search(r"(?m)^on:[ \t]*(\[[^\]\n]*\])?[ \t]*\n((?:[ \t]+.*\n|\n)*)", text)
    expect(m is not None, "test.yml has no top-level on:")
    return m.group(0)


def replace_on(text, new):
    return text.replace(on_block(text), new, 1)


def without_concurrency(text):
    return re.sub(r"(?m)^concurrency:.*\n(?:[ \t]+.*\n)*", "", text)


def problems(lint, text):
    found = lint.ci_once_problems(text)
    expect(isinstance(found, list), "ci_once_problems returns a list of findings: %r" % (found,))
    return found


def ci_runs_the_matrix_once_per_sha():
    lint = kit_lint()
    text = workflow()
    expect(problems(lint, text) == [], "the repository's test.yml passes the rule: %s" % problems(lint, text))
    block = on_block(text)
    expect(re.search(r"(?m)^  pull_request:", block), "the matrix runs on pull_request: %r" % block)
    expect(re.search(r"(?m)^  workflow_dispatch:", block), "workflow_dispatch runs it on demand: %r" % block)
    # The matrix is unchanged: the three jobs, both suite OSes, the discovered shards and the Windows file list.
    for needle in ("\n  discover:\n", "\n  suite:\n", "\n  windows:\n", "os: [ubuntu-latest, macos-latest]",
                   "fromJSON(needs.discover.outputs.shards)", "fromJSON(needs.discover.outputs.tests)", "fail-fast: false"):
        expect(needle in text, "the matrix is unchanged: %r is missing from test.yml" % needle.strip())
    # Every way of running the suite on both events is refused.
    for bad in ("on: [push, pull_request]\n", "on: [pull_request, push, workflow_dispatch]\n",
                "on:\n  push:\n  pull_request:\n  workflow_dispatch:\n",
                "on:\n  push:\n    branches: ['**']\n  pull_request:\n",
                "on:\n  push:\n    branches-ignore: [gh-pages]\n  pull_request:\n"):
        found = problems(lint, replace_on(text, bad))
        expect(any("push" in f for f in found), "on %r the suite runs twice per feature SHA; no finding: %s" % (bad, found))
    # The rule is wired into the lint run (check_structure), so CI fails on a duplicated trigger.
    expect("check_ci_once" in inspect.getsource(lint.check_structure), "check_structure does not call check_ci_once")
    findings = []
    lint.check_ci_once(findings)
    expect(findings == [], "check_ci_once on the repository's test.yml: %s" % findings)
    return "pull_request + push to main + workflow_dispatch; 5 duplicated triggers refused"


def obsolete_pull_request_runs_are_cancelled():
    lint = kit_lint()
    text = workflow()
    m = re.search(r"(?m)^concurrency:\n((?:[ \t]+.*\n)+)", text)
    expect(m is not None, "test.yml has no top-level concurrency block")
    conc = m.group(1)
    expect("github.event.pull_request.number" in conc, "runs are grouped by pull request number: %r" % conc)
    expect(re.search(r"(?m)^\s+cancel-in-progress:\s*\$\{\{\s*github\.event_name\s*==\s*'pull_request'\s*\}\}\s*$", conc),
           "cancel-in-progress is on for pull_request runs: %r" % conc)
    for name, bad in (("no concurrency", without_concurrency(text)),
                      ("cancel off", text.replace(conc, re.sub(r"cancel-in-progress:.*", "cancel-in-progress: false", conc))),
                      ("cancel missing", text.replace(conc, re.sub(r"(?m)^\s+cancel-in-progress:.*\n", "", conc))),
                      ("group by ref", text.replace(conc, re.sub(r"group:.*", "group: test-${{ github.ref }}", conc)))):
        found = problems(lint, bad)
        expect(any("concurrency" in f or "cancel" in f for f in found), "%s: older pull request runs are not cancelled; no finding: %s" % (name, found))
    return "grouped by pull request number, cancel-in-progress on pull_request"


def main_keeps_its_full_run():
    lint = kit_lint()
    text = workflow()
    block = on_block(text)
    m = re.search(r"(?m)^  push:\n((?:    .*\n)+)", block)
    expect(m is not None, "pushes still trigger the suite: %r" % block)
    expect(re.search(r"(?m)^    branches:\s*\[\s*main\s*\]\s*$", m.group(1)), "push runs only on main: %r" % m.group(1))
    conc = re.search(r"(?m)^concurrency:\n((?:[ \t]+.*\n)+)", text).group(1)
    group = re.search(r"group:\s*(.*)", conc).group(1)
    # A run that is not a pull request gets its own group: two merges in a row both finish, nothing queues or cancels.
    expect(re.search(r"github\.event\.pull_request\.number\s*\|\|\s*github\.(run_id|sha)\b", group),
           "a run on main has a group of its own (run_id or sha): %r" % group)
    for name, bad in (("no push", replace_on(text, "on:\n  pull_request:\n  workflow_dispatch:\n")),
                      ("push to a release branch only", replace_on(text, "on:\n  push:\n    branches: [release]\n  pull_request:\n  workflow_dispatch:\n")),
                      ("cancel everywhere", text.replace(conc, re.sub(r"cancel-in-progress:.*", "cancel-in-progress: true", conc))),
                      ("main shares a group", text.replace(group, "test-${{ github.event.pull_request.number || github.ref }}"))):
        found = problems(lint, bad)
        expect(found, "%s: main would lose its full run; no finding" % name)
    return "push: branches [main], never cancelled; 4 variants refused"


TESTS = [ci_runs_the_matrix_once_per_sha, obsolete_pull_request_runs_are_cancelled, main_keeps_its_full_run]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.parse_args()
    passed = failed = 0
    for test in TESTS:
        try:
            print("PASS %s (%s)" % (test.__name__, test()))
            passed += 1
        except Skip as exc:
            print("PASS %s (skipped: %s)" % (test.__name__, exc))
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print("FAIL %s (%s)" % (test.__name__, str(exc)[:1500]))
            failed += 1
    print("CI_ONCE_RESULT %s passed=%d failed=%d" % ("FAIL" if failed else "PASS", passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
