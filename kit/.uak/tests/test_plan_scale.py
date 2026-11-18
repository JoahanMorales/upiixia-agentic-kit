#!/usr/bin/env python3
"""UAK-096: small events get small plans, and projects don't receive the kit's own tests.

Evidence (notes/handoff:qa/rounds-2026-11-14, A-F12, A-F18, C-17): a 3-hour, 2-person stdlib idea got 7 P0 tasks,
a human-gated design lock and a landing among them; publishing committed 532 files, the kit's own .uak/tests suite
included; headless work took 4 prompts per task because /uak-start stops after the first green criterion.

The plan skill is read from its source (.claude/commands/uak-plan.md) and from the copy Codex and Cursor load
(.agents/skills/uak-plan/SKILL.md). install.sh runs for real into fresh Git repositories.
"""
import argparse
import re
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def skill_texts(r):
    out = {}
    for rel in (".claude/commands/uak-plan.md", ".agents/skills/uak-plan/SKILL.md"):
        p = r.package / rel
        expect(p.is_file(), "missing: " + rel)
        out[rel] = p.read_text(encoding="utf-8")
    return out


def short_sprint_plans_are_small(r):
    for rel, text in skill_texts(r).items():
        # One sizing rule with numbers: tasks scale with event hours x people, and the QA case is worked out.
        m = re.search(r"Task budget:[^\n]*hours × people ÷ (\d+(?:\.\d+)?)", text)
        expect(m, "assertion failed: %s has no 'Task budget: ... hours × people ÷ N' sizing rule" % rel)
        divisor = float(m.group(1))
        expect(int(3 * 2 / divisor) <= 4, "assertion failed: %s: 3 h × 2 people allows %d tasks (at most 4)" %
               (rel, int(3 * 2 / divisor)))
        example = re.search(r"3 h × 2 people = (\d+) tasks", text)
        expect(example and int(example.group(1)) <= 4,
               "assertion failed: %s does not work out the 3 h × 2 people case at 4 tasks or fewer" % rel)
        # Under a day, nothing in the plan waits on a human: no design lock task, no landing task.
        short = re.search(r"\*\*Under a day[^\n]*", text)
        expect(short, "assertion failed: %s has no 'Under a day' rule" % rel)
        line = short.group(0)
        for word in ("human-gated", "design lock", "landing"):
            expect(word in line.lower(), "assertion failed: %s: the under-a-day rule does not mention %r" % (rel, word))
        # The design lock and landing bullets point at that exception instead of applying to every event.
        for bullet in ("**Design lock P0**", "**Landing P0**"):
            at = text.find(bullet)
            expect(at >= 0, "%s: %s bullet missing" % (rel, bullet))
            expect("a day or longer" in text[at:at + 200],
                   "assertion failed: %s: %s still applies to events under a day" % (rel, bullet))
        # One headless prompt that runs a task all the way to REVIEW.
        head = re.search(r"\*\*Headless, run to REVIEW[^\n]*\n(?:[^\n]*\n){0,6}", text)
        expect(head, "assertion failed: %s documents no headless 'run to REVIEW' prompt" % rel)
        block = head.group(0)
        for need in ("uak done", "REVIEW", "-p", "every criterion"):
            expect(need in block, "assertion failed: %s: the headless prompt lacks %r" % (rel, need))
    return "budget, under-a-day and headless prompt in both copies"


def install(r, d, *args):
    out = subprocess.run([r.bash, str(r.package.parent / "install.sh"), *args, str(d)], capture_output=True, text=True,
                         errors="replace", env=r.env, timeout=180, stdin=subprocess.DEVNULL)
    expect(out.returncode == 0, "install failed: " + out.stdout[-600:] + out.stderr[-600:])
    return out


def fresh(r, name):
    d = r.scratch / name
    d.mkdir(parents=True)
    r.g(d, "init", "-q", "-b", "main")
    return d


def install_skips_the_kit_tests(r):
    d = fresh(r, "plain")
    out = install(r, d, "--mode", "sprint")
    expect(not (d / ".uak/tests").exists(), "assertion failed: install copied the kit's own .uak/tests into the project")
    expect((d / ".uak/bin/uak").is_file() and (d / ".uak/bin/smoke").is_file() and (d / ".uak/docs").is_dir(),
           "the engine is still installed")
    expect("tests," not in out.stdout, "assertion failed: install still says it placed the kit tests: " + out.stdout[-400:])
    # A project installed by an earlier version has the suite: --update takes it out (it is the kit's, never the team's).
    old = d / ".uak/tests"
    old.mkdir()
    (old / "test_hack.py").write_text("# an earlier kit's suite\n", encoding="utf-8")
    install(r, d, "--update", "--mode", "sprint")
    expect(not old.exists(), "assertion failed: --update left the earlier kit's .uak/tests in the project")
    # The product smoke (the merge gate's) never reads .uak/tests: it still runs its syntax and secret checks.
    smoke = subprocess.run([r.bash, ".uak/bin/smoke"], cwd=d, capture_output=True, text=True, errors="replace",
                           env=r.env, timeout=180, stdin=subprocess.DEVNULL)
    expect("no .uak/tests" not in smoke.stdout + smoke.stderr,
           "the product smoke looked for the kit tests: " + (smoke.stdout + smoke.stderr)[-400:])
    return "fresh install and --update"


TESTS = [short_sprint_plans_are_small, install_skips_the_kit_tests]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-plan-scale-") as tmp:
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
    print("PLAN_SCALE_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
