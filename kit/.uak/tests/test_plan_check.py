#!/usr/bin/env python3
"""UAK-125: `uak plan FILE --check` (and `--amend --check`) runs every validation of the publish and writes nothing:
no commit, no push, no message; it needs no UAK_HUMAN and reports EVERY problem of the file in one run.
Why (2026-11-20 and 21): the v6.5 plan failed at publish on a missing `Depends on` and the human ran the command twice;
an amend of UAK-083 was refused for a task in REVIEW; the only way to validate a plan was to publish it, and publishing
is reserved to the human. Real Git, local bare remotes."""
import argparse
import concurrent.futures
import itertools
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack

COUNTER = itertools.count(1)


def section(tid, paths="src/new.txt", priority="P0", depends="None", verify="echo ok", title="check"):
    lines = ["## %s — %s" % (tid, title), ""]
    if priority is not None:
        lines.append("- **Priority:** %s" % priority)
    if paths is not None:
        lines.append("- **Paths:** %s" % paths)
    if depends is not None:
        lines.append("- **Depends on:** %s" % depends)
    lines += ["- **Acceptance:** salida comprobable", "- **Verify:** %s" % verify, "", ""]
    return "\n".join(lines)


def plan_file(f, *sections):
    path = f.worktrees[0] / ("plan-check-%d.md" % next(COUNTER))
    path.write_text("# Plan\n\n" + "".join(sections), encoding="utf-8")
    return path


def refs(r, f):
    return r.g(f.remote, "for-each-ref", "--format=%(refname) %(objectname)").stdout


def run_check(f, path, *flags, human=""):
    return hack(f, 0, "plan", path, *flags, "--check", UAK_HUMAN=human, allowed=None)


def check_passes_a_valid_plan(r):
    f = r.fixture("pc-valid", count=1)
    config(f, Plan_Channel="claims")
    out = run_check(f, plan_file(f, section("HACK-010"), section("HACK-011", "src/other.txt", depends="HACK-010")))
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "OK plan --check | 2 tasks would be published" in out.stdout, "a valid plan passes: rc %d %s" % (out.returncode, text[-500:]))
    expect("board can change" in text, "it says what it cannot promise: " + text[-500:])
    return "OK line"


def check_writes_nothing(r):
    f = r.fixture("pc-writes", count=1)
    config(f, Plan_Channel="claims")
    f.claim(0, "HACK-001")
    before = refs(r, f)
    path = plan_file(f, section("HACK-010"))
    out = run_check(f, path)
    expect(out.returncode == 0, "check passes: " + out.stdout + out.stderr)
    expect(refs(r, f) == before, "no commit or push reached the remote: %s vs %s" % (before, refs(r, f)))
    inbox = f.hack(0, "inbox", "--peek", allowed=None)
    expect("HACK-010" not in inbox.stdout + inbox.stderr, "no message to anyone: " + inbox.stdout)
    # the same file then publishes for real (and only a human can)
    nohuman = hack(f, 0, "plan", path, UAK_HUMAN="", allowed=None)
    expect(nohuman.returncode != 0 and "needs UAK_HUMAN" in nohuman.stdout + nohuman.stderr, "the publish still needs a human: " + nohuman.stderr)
    pub = hack(f, 0, "plan", path, UAK_HUMAN="joahan", allowed=None)
    expect(pub.returncode == 0 and "OK plan | tasks published" in pub.stdout, "the publish keeps its output: " + pub.stdout + pub.stderr)
    return "refs unchanged"


def check_needs_no_human(r):
    f = r.fixture("pc-human", count=1)
    config(f, Plan_Channel="claims")
    out = run_check(f, plan_file(f, section("HACK-010")), human="")
    expect(out.returncode == 0 and "OK plan --check" in out.stdout, "an agent without UAK_HUMAN may check: " + out.stdout + out.stderr)
    out = run_check(f, plan_file(f, section("HACK-010")), human="joahan")
    expect(out.returncode == 0, "a human may too: " + out.stdout + out.stderr)
    return "agent and human"


def check_reports_every_problem(r):
    f = r.fixture("pc-every", count=1)
    config(f, Plan_Channel="claims")
    path = plan_file(f,
                     section("HACK-001", title="dup"),
                     section("HACK-011", paths=None, priority=None),
                     section("HACK-012", verify="bash -c 'echo broken"),
                     section("HACK-013", depends="HACK-099"),
                     section("HACK-014"))
    out = run_check(f, path)
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "OK plan --check" not in out.stdout, "problems fail the check: rc %d %s" % (out.returncode, text[-800:]))
    for needle in ("HACK-001 already exists in the backlog or is duplicated", "HACK-011 needs Priority.", "HACK-011 needs Paths.",
                   "HACK-012's Verify does not parse", "HACK-013's Depends on names HACK-099"):
        expect(needle in text, "reported: %s in %s" % (needle, text[-1200:]))
    expect("HACK-014" not in text, "a valid task is not named: " + text[-800:])
    return "all problems in one run"


def amend_check_names_a_task_in_review(r):
    f = r.fixture("pc-review", count=2)
    config(f, Plan_Channel="claims")
    f.claim(0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.invalid/pull/1", "--evidence", "fixture", now=1000010)
    before = refs(r, f)
    path = plan_file(f, section("HACK-001", "src/one.txt"), section("HACK-077", "src/x.txt"))
    out = run_check(f, path, "--amend")
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "HACK-001 is in REVIEW: its review covers the old criteria" in text, "REVIEW is named: " + text[-800:])
    expect("HACK-077 is not in the backlog" in text, "every problem, not the first: " + text[-800:])
    expect(refs(r, f) == before and "State: REVIEW" in f.show("tasks/HACK-001.md"), "still REVIEW, nothing written")
    return "REVIEW named"


TESTS = [check_passes_a_valid_plan, check_writes_nothing, check_needs_no_human, check_reports_every_problem,
         amend_check_names_a_task_in_review]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-plan-check-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        selected = [t for t in TESTS if not args.case or t.__name__ in args.case]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, selected))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("PLAN_CHECK_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
