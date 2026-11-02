#!/usr/bin/env python3
"""uak v5.10: test-first that agents cannot short-cut, and a harness that gets pruned. Agents optimize toward green:
stuck on red they edit the assertion, add a skip or delete the test; a test written after the code passes by
construction; a mock-only test passes whatever the code does. Each rule is a check here: done refuses weakened tests
and missing named tests and asks for the red (uak red), a human allows a test change. Also: uak garden, the 2026
anti-slop tells in design-lint, and marathon's full design chain. Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_v57 import set_project

PROJECT = "Backlog-Approved: yes\nAutonomy: yes\nAuto-Merge: yes\nReview-Mode: claims\nEvents-Per-Session: 100\nCheckpoint-Percent: 60\n"
PY = Path(sys.executable).as_posix()


def commit_push(f, wt, msg, branch):
    f.r.g(wt, "add", "-A"); f.r.g(wt, "commit", "-q", "-m", msg); f.r.g(wt, "push", "-q", "origin", branch)


def on_main(f, files, task_lines=None):
    """Put files (and Tests: lines per task) on main, then bring the agents' worktrees up to it."""
    for rel, text in files.items():
        p = f.seed / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    if task_lines:
        tasks = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8")
        for task, line in task_lines.items():
            tasks = tasks.replace("## " + task + " — Fixture verificable\n\n", "## " + task + " — Fixture verificable\n\n" + line + "\n", 1)
        (f.seed / ".uak/TASKS.md").write_text(tasks, encoding="utf-8")
    f.r.g(f.seed, "add", "-A"); f.r.g(f.seed, "commit", "-q", "-m", "main: tests"); f.r.g(f.seed, "push", "-q", "origin", "main")
    for wt in f.worktrees:
        f.r.g(wt, "fetch", "-q", "origin"); f.r.g(wt, "merge", "-q", "--no-edit", "origin/main")


def done(f, i, *extra, now=1000010):
    return f.hack(i, "done", "HACK-00%d" % (i + 1), "--pr", "https://example.test/pull/%d" % (i + 1), "--evidence", "ok", *extra,
                  now=now, allowed=None)


def done_refuses_weakened_tests(r):
    """An agent stuck on red changed the assertion; nothing between it and the merge noticed."""
    f = r.fixture("v510-weak", paths={"HACK-001": "src/one.txt, tests/"}, count=1)
    on_main(f, {"tests/test_one.py": "def test_total():\n    assert total([2, 2]) == 4\n\n\ndef test_empty():\n    assert total([]) == 0\n"})
    f.claim(0, "HACK-001")
    wt = f.worktrees[0]
    text = (wt / "tests/test_one.py").read_text(encoding="utf-8")
    (wt / "tests/test_one.py").write_text(text.replace("== 4", "== 5"), encoding="utf-8")
    commit_push(f, wt, "make it pass", f.branches[0])
    weak = done(f, 0)
    expect(weak.returncode == 3 and "Tests only grow" in weak.stderr and "assert total([2, 2]) == 4" in weak.stderr, weak.stdout + weak.stderr)
    # An agent cannot allow it; a human can, and done says so to the reviewer.
    agent = f.hack(0, "allow", "HACK-001", "--tests", "--reason", "spec changed", allowed=None)
    expect(agent.returncode == 3 and "human decision" in agent.stderr, agent.stdout + agent.stderr)
    ok = f.hack(0, "allow", "HACK-001", "--tests", "--reason", "the total now includes tax", human=True, allowed=None)
    expect(ok.returncode == 0 and "OK allow --tests" in ok.stdout, ok.stdout + ok.stderr)
    after = done(f, 0)
    expect(after.returncode == 0 and "with a human's approval" in f.show("tasks/HACK-001.md"), after.stdout + after.stderr)
    expect("test change: HACK-001" in f.show("DECISIONS.md"), f.show("DECISIONS.md"))
    return {"weakened": "refused, then human-allowed"}


def test_findings_see_skips_deletes_deselects_and_mocks(r):
    """The quieter short cuts: a skip, a deleted file, a deselect in the runner's config, a mock-only test. A moved
    line is not a change."""
    d = r.scratch / "v510-findings"
    d.mkdir()
    r.g(d, "init", "-q", "-b", "main")
    r.g(d, "config", "user.name", "t"); r.g(d, "config", "user.email", "t@example.invalid")
    (d / "tests").mkdir()
    (d / "tests/test_a.py").write_text("def test_a():\n    assert a() == 1\n\n\ndef test_b():\n    assert b() == 2\n", encoding="utf-8")
    (d / "tests/test_gone.py").write_text("def test_gone():\n    assert gone()\n", encoding="utf-8")
    (d / "pytest.ini").write_text("[pytest]\naddopts = -q\n", encoding="utf-8")
    r.g(d, "add", "-A"); r.g(d, "commit", "-q", "-m", "base")
    r.g(d, "checkout", "-q", "-b", "feat")
    # test_b moves above test_a and gets re-indented the same way: not a change. A skip on a new test is.
    (d / "tests/test_a.py").write_text("def test_b():\n    assert b() == 2\n\n\ndef test_a():\n    assert  a() == 1\n\n\n"
                                       "@pytest.mark.skip(reason='flaky')\ndef test_c():\n    assert c() == 3\n", encoding="utf-8")
    (d / "tests/test_gone.py").unlink()
    (d / "pytest.ini").write_text("[pytest]\naddopts = -q --deselect tests/test_a.py::test_a\n", encoding="utf-8")
    (d / "tests/test_mock.py").write_text("def test_charges():\n    pay.charge.assert_called_once()\n    mail.send.assert_called_once()\n", encoding="utf-8")
    r.g(d, "add", "-A"); r.g(d, "commit", "-q", "-m", "feat")
    out = r.run([r.bash, "-c", '. "$1"; tf_findings . main...HEAD "$2"', "_", (r.package / ".uak/bin/lib/tests.sh").as_posix(), d.as_posix()],
                cwd=d).stdout
    expect("FAIL tests/test_gone.py: an existing test file was deleted" in out, out)
    expect("FAIL tests/test_a.py: a skip, only or todo was added" in out and "changed or removed" not in out, out)
    expect("FAIL pytest.ini: tests taken out of the run" in out, out)
    expect("WARN tests/test_mock.py: its new assertions only check that mocks were called" in out, out)
    return {"findings": out.count("\n")}


def done_wants_the_named_tests(r):
    """A task's Tests: line is its spec; nothing checked that the branch wrote them."""
    f = r.fixture("v510-named", paths={"HACK-001": "src/one.txt, tests/"}, count=1)
    on_main(f, {}, {"HACK-001": "- **Tests:** returns_the_total_for_two_items, rejects a negative quantity"})
    claim = f.claim(0, "HACK-001")
    # The rule reaches the agent when it applies: at claim, with the names, not first at done.
    expect("TEST FIRST: write the tests returns_the_total_for_two_items, rejects a negative quantity" in claim.stdout
           and "uak red HACK-001" in claim.stdout, claim.stdout)
    card = (r.package / ".uak/reminders.md").read_text(encoding="utf-8")
    expect("then red ID (it must fail on its assertion)" in card, "the session card says when to run red")
    wt = f.worktrees[0]
    (wt / "tests").mkdir(exist_ok=True)
    (wt / "tests/test_cart.py").write_text("def test_returns_the_total_for_two_items():\n    assert total([2, 2]) == 4\n", encoding="utf-8")
    commit_push(f, wt, "first test", f.branches[0])
    one = done(f, 0)
    expect(one.returncode == 3 and "rejects a negative quantity" in one.stderr and "returns_the_total" not in one.stderr, one.stdout + one.stderr)
    with (wt / "tests/test_cart.py").open("a", encoding="utf-8") as h:
        h.write("\n\ndef test_rejects_a_negative_quantity():\n    with raises(ValueError):\n        total([-1])\n")
    commit_push(f, wt, "second test", f.branches[0])
    both = done(f, 0)
    expect(both.returncode == 0 and "No red recorded" in both.stderr, "warn mode: done passes and says the red is missing: " + both.stdout + both.stderr)
    return {"named": 2}


def red_wants_an_assertion(r):
    """A red on a missing module says nothing; a test that passes before the code tests nothing new."""
    f = r.fixture("v510-red", count=1)
    set_project(f, PROJECT + "Test-First: yes\n")   # next says TEST FIRST where the gate is on
    f.claim(0, "HACK-001")
    wt = f.worktrees[0]
    red = lambda *cmd: r.run([r.bash, ".uak/bin/uak", "red", "HACK-001", "--", *cmd], cwd=wt, allowed=None)
    wrong = red(PY, "-c", "import cart_that_does_not_exist")
    expect(wrong.returncode == 1 and "RED_WRONG" in wrong.stdout and "ModuleNotFoundError" in wrong.stdout, wrong.stdout + wrong.stderr)
    passed = red("true")
    expect(passed.returncode == 1 and "RED_PASSED" in passed.stdout, passed.stdout)
    before = f.hack(0, "next").stdout
    expect("TEST FIRST:" in before and "uak red HACK-001" in before, "a session on the claimed task hears it: " + before)
    right = red(PY, "-c", "assert 2 + 2 == 5, 'total'")
    expect(right.returncode == 0 and "RED_OK HACK-001" in right.stdout and "AssertionError" in right.stdout, right.stdout + right.stderr)
    gd = Path(r.g(wt, "rev-parse", "--absolute-git-dir").stdout.strip())
    rec = (gd / "uak-red/HACK-001.txt").read_text(encoding="utf-8")
    expect(rec.startswith("SHA: " + r.g(wt, "rev-parse", "HEAD").stdout.strip()) and "Reason: AssertionError" in rec, rec)
    expect("uak-red" not in r.g(wt, "status", "--porcelain").stdout, "the evidence is never committed")
    expect("TEST FIRST:" not in f.hack(0, "next").stdout, "once the red is recorded, next stops saying it")
    return {"red": "right only"}


def done_requires_the_red_when_test_first_is_yes(r):
    """Test-First: yes makes the red a gate; --no-red says why to the reviewer; a red before the code passes."""
    f = r.fixture("v510-tf", count=2)
    set_project(f, PROJECT + "Test-First: yes\n")
    for i in (0, 1):
        f.claim(i, "HACK-00%d" % (i + 1))
    wt = f.worktrees[0]
    (wt / "src").mkdir(exist_ok=True); (wt / "src/one.txt").write_text("docs\n", encoding="utf-8")
    commit_push(f, wt, "one", f.branches[0])
    bare = done(f, 0)
    expect(bare.returncode == 3 and "No red recorded for HACK-001" in bare.stderr and "uak red HACK-001" in bare.stderr, bare.stdout + bare.stderr)
    why = done(f, 0, "--no-red", "a copy change, nothing to assert")
    expect(why.returncode == 0 and "no red: a copy change" in f.show("tasks/HACK-001.md"), why.stdout + why.stderr)
    wt2 = f.worktrees[1]
    red = r.run([r.bash, ".uak/bin/uak", "red", "HACK-002", "--", PY, "-c", "assert 1 == 2"], cwd=wt2, allowed=None)
    expect(red.returncode == 0, red.stdout + red.stderr)
    (wt2 / "src").mkdir(exist_ok=True); (wt2 / "src/two.txt").write_text("code\n", encoding="utf-8")
    commit_push(f, wt2, "two", f.branches[1])
    ok = done(f, 1, now=1000020)
    expect(ok.returncode == 0 and "red at " in f.show("tasks/HACK-002.md"), ok.stdout + ok.stderr)
    return {"gate": "red or a reason"}


def lint_asks_feature_tasks_for_test_names(r):
    f = r.fixture("v510-lint", count=1)
    set_project(f, PROJECT + "Test-First: yes\n")
    tasks = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8").replace("- **Type:** vertical", "- **Type:** feature", 1)
    (f.seed / ".uak/TASKS.md").write_text(tasks, encoding="utf-8")
    out = r.run([r.bash, ".uak/bin/uak", "lint"], cwd=f.seed, allowed=None)
    expect("HACK-001 (feature) lists no Tests" in out.stderr, out.stdout + out.stderr)
    return {"lint": "warns"}


def design_lint_flags_the_2026_tells(r):
    """Gradient text, glows, italic serif display, the hero chip, icon-tile grids, em dashes and filler all passed."""
    d = r.scratch / "v510-dlint"
    (d / "web/src/features/home").mkdir(parents=True)
    r.g(d, "init", "-q")
    (d / "web/src/index.css").write_text(":root{\n  --bg:#ffffff; --text:#111111;\n}\n", encoding="utf-8")
    dash = "—"
    (d / "web/src/features/home/index.tsx").write_text(
        'export const Home = ({ items }) => <main>\n'
        '<span className="rounded-full px-3 py-1 text-xs">New in 2026</span>\n'
        '<h1 className="font-serif italic text-6xl bg-clip-text">Seamlessly elevate your workflow</h1>\n'
        '<p style={{ textShadow: "0 0 20px" }} className="[text-shadow:0_0_8px]">Fast ' + dash + ' simple ' + dash + ' yours ' + dash + ' now ' + dash + ' go</p>\n'
        '{items.map((it) => (\n<div>\n'
        '<div className="flex h-10 w-10 items-center justify-center rounded-xl">{it.icon}</div>\n'
        '<h3>{it.title}</h3>\n</div>))}\n</main>;\n', encoding="utf-8")
    out = r.run([r.bash, str(r.package / ".uak/bin/design-lint")], cwd=d, allowed=None)
    for what in ("gradient text", "glow or text shadow", "italic serif display", "pill chip above the hero heading",
                 "icon tiles stacked above headings", "4 em dashes", 'marketing filler "Seamlessly"'):
        expect(what in out.stdout, "design-lint names %s: %s" % (what, out.stdout))
    expect(out.returncode == 1, "and fails")
    return {"tells": 7}


def garden_finds_drift_stale_lessons_and_corrections(r):
    """Rules go stale and docs drift; a correction a human typed twice is a check the harness lacks."""
    f = r.fixture("v510-garden", count=1)
    wt = f.worktrees[0]
    f.claim(0, "HACK-001")
    f.hack(0, "learn", "the cache lies after a deploy · purge it", "--path", "legacy/cache/", "--task", "HACK-001")
    f.r.g(wt, "fetch", "-q", "origin", "claims:refs/remotes/origin/claims")
    with (wt / ".uak/docs/LOOPS.md").open("a", encoding="utf-8") as h:
        h.write("\nRun `uak frobnicate` before the loop.\n")
    home = r.scratch / "v510-claude"
    main = r.run([r.bash, "-c", 'cd "$(git rev-parse --git-common-dir)/.." && pwd -P'], cwd=wt).stdout.strip()
    # One folder, named as Claude Code names it: after the Windows path where there is one (C:/…), else the path.
    win = r.run([r.bash, "-c", 'cygpath -m "$1" 2>/dev/null', "_", main], cwd=wt, allowed=None).stdout.strip()
    names = {re.sub(r"[^A-Za-z0-9]", "-", win or main)}
    line = lambda text: json.dumps({"type": "user", "message": {"role": "user", "content": text}, "uuid": "u"}, separators=(",", ":"))
    for n in names:
        (home / "projects" / n).mkdir(parents=True)
        (home / "projects" / n / "s.jsonl").write_text("\n".join([line("no, otra vez borraste el test"), line("add the login page"),
                                                                   line("no, otra vez borraste el test")]) + "\n", encoding="utf-8")
    out = r.run([r.bash, ".uak/bin/uak", "garden"], cwd=wt, env={"CLAUDE_CONFIG_DIR": str(home)}, allowed=None)
    expect(out.returncode == 0, out.stdout + out.stderr)
    expect("names `frobnicate`" in out.stdout, out.stdout)
    expect("(legacy/cache/)" in out.stdout and "uak learn --forget" in out.stdout, out.stdout)
    expect("×2 no, otra vez borraste el test" in out.stdout and "add the login page" not in out.stdout, out.stdout)
    expect("AGENTS.md:" in out.stdout and "GARDEN:" in out.stdout, out.stdout)
    return {"garden": True}


def both_modes_get_test_first_and_the_design_chain(r):
    """Marathon had no design critic while UI-Paths made done ask for its verdict; TDD reached marathon only."""
    if not (r.package.parent / "install.sh").is_file():
        return {"skipped": "an installed project has no install.sh"}
    for mode in ("marathon", "sprint"):
        t = r.scratch / ("v510-install-" + mode)
        t.mkdir()
        r.g(t, "init", "-q", "-b", "main")
        r.run([r.bash, str(r.package.parent / "install.sh"), "--mode", mode, "--stack", "fastapi-react", "--harness", "claude,codex", str(t)], cwd=t)
        for skill in ("test-first", "frontend-design", "product-ui", "landing-story", "redesign-existing-projects"):
            expect((t / ".claude/skills" / skill / "SKILL.md").is_file(), "%s: skill %s" % (mode, skill))
        expect(not (t / ".claude/skills/test-driven-development").exists(), mode + ": test-first replaces it")
        expect((t / ".claude/agents/design-critic.md").is_file() and (t / ".codex/agents/design-critic.toml").is_file(), mode + ": the critic")
        expect((t / ".claude/commands/uak-design-lock.md").is_file(), mode + ": the design lock")
        project = (t / ".uak/PROJECT.md").read_text(encoding="utf-8")
        expect("Test-First: yes" in project and "UI-Paths: web/src/" in project, project)
    return {"modes": 2}


def guard_stays_fast_on_html_and_tabs(r):
    """kit_lint found it: `<` and tabs were replaced by ${s//…}, which costs matches × length on bash 3.2 (437 s at
    18 KB); a heredoc of HTML or of a Makefile has one on every line. Past 1 KB (always on bash 3.2) awk does it."""
    f = r.fixture("v510-html", count=1)
    body = "\n".join("\t<div class=\"row\"><span>%d</span>\t<b>x</b></div>" % i for i in range(1500))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat > page.html <<'H'\n" + body + "\nH\ngit push --force"}})
    started = time.monotonic()
    stdin = f.base / "html.json"
    stdin.write_text(payload, encoding="utf-8")
    out = r.run([r.bash, "-c", 'exec < "$1"; exec bash .uak/bin/guard bash claude', "_", stdin.as_posix()], cwd=f.worktrees[0], allowed=None)
    took = time.monotonic() - started
    expect(out.returncode == 2 and "forced push" in out.stderr and took < 4, "rc %d in %.1f s: %s" % (out.returncode, took, out.stderr[-200:]))
    return {"seconds": round(took, 1)}


TESTS = [done_refuses_weakened_tests, test_findings_see_skips_deletes_deselects_and_mocks, done_wants_the_named_tests,
         red_wants_an_assertion, done_requires_the_red_when_test_first_is_yes, lint_asks_feature_tasks_for_test_names,
         design_lint_flags_the_2026_tells, garden_finds_drift_stale_lessons_and_corrections,
         both_modes_get_test_first_and_the_design_chain, guard_stays_fast_on_html_and_tabs]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v510-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("V510_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
