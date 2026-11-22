#!/usr/bin/env python3
"""UAK-129: `smoke --affected [BASE]` runs the lint, the secret scan, the task's Verify and only the test files the diff
against BASE touches or names; a change to the shared engine files or the test helpers, or a file it cannot classify, runs
everything. It prints which files it chose and why, and how many it left for the merge gate. The gate never passes the flag
and nothing an agent sets makes its run partial. Why (audit section 1): the suite took 8-10 minutes and ran three times per
task (author, reviewer, gate), 152 review rounds in 105 tasks each paid a whole run.
Real Git; the fixture is a tiny package whose test files print a marker when they run."""
import argparse
import shutil
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

GATE_SOURCES = ("lib/review-merge.sh", "smoke")


def package(r, name, tests=None):
    """A git repo whose top is the package: the real engine's bin, fake test files, one base commit."""
    base = Path(tempfile.mkdtemp(prefix="sa-%s-" % name, dir=str(r.scratch)))
    shutil.copytree(r.package / ".uak" / "bin", base / ".uak" / "bin")
    (base / ".uak" / "tests").mkdir(parents=True)
    files = {
        "test_alpha.py": "print('RAN alpha')  # exercises .uak/bin/autopsy\n",
        "test_beta.py": "print('RAN beta')  # exercises .uak/bin/guard\n",
        "test_gamma.py": "print('RAN gamma')  # exercises nothing in particular\n",
        "test_hack.py": "print('RAN hack')\n",
        "test_user.py": "import test_hack\nprint('RAN user')\n",
    }
    files.update(tests or {})
    for n, text in files.items():
        (base / ".uak" / "tests" / n).write_text(text, encoding="utf-8")
    (base / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")  # test_user imports test_hack: Python writes a cache
    (base / "docs").mkdir()
    (base / "docs" / "guide.md").write_text("# guide, see test_beta\n", encoding="utf-8")
    r.g(base, "init", "-q")
    r.g(base, "config", "user.name", "t")
    r.g(base, "config", "user.email", "t@example.test")
    r.g(base, "add", "-A")
    r.g(base, "commit", "-q", "-m", "base")
    return base


def touch(r, base, rel, text="# changed\n"):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(str(p), "a", encoding="utf-8") as fh:
        fh.write(text)


def smoke(r, base, *args, env=None):
    # `env -u` first, then the caller's variables: a test that exports UAK_SMOKE_TESTS means it (CI shards leak theirs).
    cmd = ["env", "-u", "UAK_SMOKE_TESTS", "-u", "UAK_SMOKE_GATE_NONE"] + ["%s=%s" % kv for kv in (env or {}).items()] + [r.bash, ".uak/bin/smoke"] + list(args)
    return r.run(cmd, cwd=base, allowed=None, timeout=600)


def ran(out):
    return sorted(set(l.split()[1] for l in out.stdout.splitlines() if l.startswith("RAN ")))


def affected_runs_changed_test_files(r):
    base = package(r, "changed")
    touch(r, base, ".uak/tests/test_gamma.py", "# edited\n")
    out = smoke(r, base, "--package-only", "--affected", "HEAD")
    expect(out.returncode == 0, "rc %d: %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(ran(out) == ["gamma"], "only the changed test file ran: %s | %s" % (ran(out), out.stdout[-500:]))
    expect("test_gamma.py" in out.stdout and "changed" in out.stdout, "it says why: " + out.stdout[-500:])
    # A new, untracked test file is a changed test file too.
    (base / ".uak" / "tests" / "test_delta.py").write_text("print('RAN delta')\n", encoding="utf-8")
    out = smoke(r, base, "--package-only", "--affected", "HEAD")
    expect(ran(out) == ["delta", "gamma"], "an untracked test file runs: %s" % ran(out))
    return "changed and new test files only"


def engine_change_selects_its_tests(r):
    base = package(r, "engine")
    touch(r, base, ".uak/bin/autopsy")
    out = smoke(r, base, "--package-only", "--affected", "HEAD")
    expect(out.returncode == 0, "rc %d: %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(ran(out) == ["alpha"], "only the test that names autopsy: %s" % ran(out))
    expect("test_alpha.py" in out.stdout and ".uak/bin/autopsy" in out.stdout, "it names the file behind the choice: " + out.stdout[-500:])
    # A docs file that a test names selects that test; one nothing names selects none and says so.
    base2 = package(r, "docs")
    touch(r, base2, "docs/guide.md")
    out = smoke(r, base2, "--package-only", "--affected", "HEAD")
    expect(ran(out) == [], "docs/guide.md is named by no test file (the basename): %s" % ran(out))
    # An engine file no test names and the map does not know runs everything.
    base3 = package(r, "unnamed")
    touch(r, base3, ".uak/bin/pace")
    out = smoke(r, base3, "--package-only", "--affected", "HEAD")
    expect(ran(out) == ["alpha", "beta", "gamma", "hack", "user"], "an engine file no test names runs everything: %s" % ran(out))
    return "engine file selects the tests naming it"


def core_change_runs_everything(r):
    every = ["alpha", "beta", "gamma", "hack", "user"]
    for rel in (".uak/bin/lib/core.sh", ".uak/bin/lib/tx.sh", ".uak/bin/lib/cache.sh", ".uak/bin/uak", ".uak/bin/uak-coordination",
                "install.sh", ".uak/tests/test_hack.py", "weird/file.xyz"):
        base = package(r, "core")
        touch(r, base, rel)
        out = smoke(r, base, "--package-only", "--affected", "HEAD")
        expect(out.returncode == 0, "%s: rc %d %s" % (rel, out.returncode, (out.stdout + out.stderr)[-400:]))
        expect(ran(out) == every, "%s runs everything: %s" % (rel, ran(out)))
        expect("all 5" in out.stdout, "%s: it says it chose all: %s" % (rel, out.stdout[-400:]))
    # A test module another test imports is a helper.
    base = package(r, "helper")
    touch(r, base, ".uak/tests/test_hack.py")
    out = smoke(r, base, "--package-only", "--affected", "HEAD")
    expect(ran(out) == every and "helper" in out.stdout, "a helper runs everything and says why: " + out.stdout[-400:])
    return "core, helpers, install.sh and the unknown run everything"


def gate_ignores_the_shortcut(r):
    base = package(r, "gate")
    touch(r, base, ".uak/tests/test_gamma.py", "# edited\n")
    agent_env = {"UAK_SMOKE_AFFECTED": "1", "UAK_AFFECTED": "1", "UAK_SMOKE_BASE": "HEAD", "UAK_AFFECTED_BASE": "HEAD",
                 "UAK_SMOKE_MODE": "affected", "UAK_SMOKE_SHORTCUT": "1", "SMOKE_AFFECTED": "1"}
    out = smoke(r, base, "--package-only", env=agent_env)
    expect(out.returncode == 0, "rc %d: %s" % (out.returncode, (out.stdout + out.stderr)[-400:]))
    expect(ran(out) == ["alpha", "beta", "gamma", "hack", "user"], "the gate's call (no flag) runs the whole suite whatever is exported: %s" % ran(out))
    # A stale token or shard list of an agent's own does not make --affected skip the lint or run another list.
    out = smoke(r, base, "--package-only", "--affected", "HEAD", env={"UAK_SMOKE_TESTS": "test_beta"})
    expect(ran(out) == ["gamma"], "--affected does not take its list from UAK_SMOKE_TESTS: %s" % ran(out))
    # The gate's code never passes the flag, and neither file reads a variable to turn it on.
    gate = (r.package / ".uak" / "bin" / "lib" / "review-merge.sh").read_text(encoding="utf-8")
    expect("--affected" not in gate, "the merge gate never passes --affected")
    smoke_src = (r.package / ".uak" / "bin" / "smoke").read_text(encoding="utf-8")
    flag = [l for l in smoke_src.splitlines() if "--affected" in l and not l.lstrip().startswith("#")]
    expect(flag and all("UAK_" not in l for l in flag), "the flag is an argument, not a variable: %s" % flag)
    expect("affected=1" in smoke_src and smoke_src.count("affected=1") == 1, "one place turns it on")
    return "no environment variable makes the gate partial"


def prints_what_it_left(r):
    base = package(r, "left")
    touch(r, base, ".uak/bin/autopsy")
    out = smoke(r, base, "--package-only", "--affected", "HEAD")
    expect("left 4 of 5 test files for the merge gate" in out.stdout, "it counts what it left: " + out.stdout[-600:])
    expect("Affected: 1 of 5" in out.stdout, "and what it chose: " + out.stdout[-600:])
    # --list prints the choice and runs no test: a person or an agent reads it first.
    out = smoke(r, base, "--package-only", "--affected", "--list", "HEAD")
    expect(out.returncode == 0 and ran(out) == [] and "test_alpha.py" in out.stdout, "--list only prints: " + out.stdout[-400:])
    # The task's Verify always runs, and a red Verify fails the run.
    for verify, rc in (("echo VERIFY_RAN", 0), ("echo VERIFY_RED; exit 3", 1)):
        vb = package(r, "verify")
        (vb / ".uak" / "TASKS.md").write_text("## T-1 · fixture\n- **Verify:** `%s`\n" % verify, encoding="utf-8")
        with open(str(vb / ".gitignore"), "a", encoding="utf-8") as fh:
            fh.write(".uak-env\n")
        r.g(vb, "add", "-A"); r.g(vb, "commit", "-q", "-m", "task")
        (vb / ".uak-env").write_text("UAK_TASK=T-1\n", encoding="utf-8")
        touch(r, vb, ".uak/tests/test_gamma.py", "# edited\n")
        out = smoke(r, vb, "--package-only", "--affected", "HEAD")
        expect(out.returncode == rc and ("VERIFY_RAN" if rc == 0 else "VERIFY_RED") in out.stdout and ran(out) == ["gamma"],
               "Verify %r: rc %d, %s" % (verify, out.returncode, (out.stdout + out.stderr)[-500:]))
    # The real suite: a one-file diff selects under a quarter of the files.
    pkg = Path(tempfile.mkdtemp(prefix="sa-real-", dir=str(r.scratch)))
    shutil.copytree(r.package / ".uak" / "bin", pkg / ".uak" / "bin")
    shutil.copytree(r.package / ".uak" / "tests", pkg / ".uak" / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    r.g(pkg, "init", "-q"); r.g(pkg, "config", "user.name", "t"); r.g(pkg, "config", "user.email", "t@example.test")
    r.g(pkg, "add", "-A"); r.g(pkg, "commit", "-q", "-m", "base")
    touch(r, pkg, ".uak/bin/autopsy")
    out = smoke(r, pkg, "--package-only", "--affected", "--list", "HEAD")
    import re
    m = re.search(r"Affected: (\d+) of (\d+) test files", out.stdout)
    expect(m is not None, "a count line: " + out.stdout[-500:])
    n, total = int(m.group(1)), int(m.group(2))
    expect(0 < n and n * 4 < total, "a one-file diff selects under a quarter of the files: %d of %d" % (n, total))
    return "%d of %d test files for a one-file diff" % (n, total)


def select_real(r, package, rel):
    """What the selector picks on the real package for one changed engine file: (everything?, [test files])."""
    tests = sorted(t.name for t in (package / ".uak" / "tests").glob("test_*.py"))
    work = Path(tempfile.mkdtemp(prefix="sa-sel-", dir=str(r.scratch)))
    (work / "tests").write_text("\n".join(tests) + "\n", encoding="utf-8")
    (work / "changed").write_text(rel + "\n", encoding="utf-8")
    out = r.run([r.bash, "-c", '. "$1/.uak/bin/lib/tests.sh"; tf_affected_select "$1" "$2/changed" "$2/tests"', "sel", package.as_posix(), work.as_posix()],
                cwd=work, allowed=None).stdout
    rows = [l.split("\t") for l in out.splitlines() if l.strip()]
    if any(row[0] == "ALL" for row in rows):
        return True, tests
    return False, [row[0] for row in rows if row[0] != "-"]


# (engine file, tests that must be selected or everything must run): the cases kit-r1 found on tip b3b43b83, then one
# command family each. A library is tested through the commands that use it, not through its own file name.
MUST_SELECT = [
    (".uak/bin/lib/claim.sh", ["test_coordination.py"]),
    (".uak/bin/lib/plan.sh", ["test_plan_check.py", "test_plan_owners.py"]),
    (".uak/bin/lib/dash.py", ["test_task_timeline.py"]),
    (".uak/bin/lib/status.sh", ["test_coordination.py"]),
    (".uak/bin/lib/review-merge.sh", ["test_review_merge.py", "test_merge_affected.py"]),
    (".uak/bin/lib/done.sh", ["test_v510.py"]),
    (".uak/bin/lib/lint.sh", ["test_lint_paths_hint.py"]),
    (".uak/bin/demo", ["test_demo.py"]),
    (".uak/bin/autopsy", ["test_autopsy.py"]),
]


def selector_keeps_the_commands_tests(r):
    known = {t.name for t in (r.package / ".uak" / "tests").glob("test_*.py")}
    checked = 0
    for rel, must in MUST_SELECT:
        everything, picked = select_real(r, r.package, rel)
        for t in must:
            if t not in known:
                continue  # a renamed test file is not this selector's defect: the pair is skipped, the others still run
            expect(everything or t in picked, "%s must select %s (or run everything): %s" % (rel, t, picked))
            checked += 1
    expect(checked >= 8, "the self-check covers real pairs: %d" % checked)
    # Shared plumbing no command is implemented in runs everything.
    for rel in (".uak/bin/lib/net.sh", ".uak/bin/lib/state.awk", ".uak/bin/lib/engines.awk", ".uak/bin/lib/config.sh"):
        expect(select_real(r, r.package, rel)[0], "%s is shared plumbing: everything" % rel)
    # A selection under the floor of 3 test files for an engine file is widened or full, never 1 or 2.
    for rel in (".uak/bin/lib/net.sh", ".uak/bin/demo", ".uak/bin/lib/smoke-init.sh", ".uak/bin/lib/security.sh"):
        everything, picked = select_real(r, r.package, rel)
        expect(everything or len(picked) >= 3, "%s: fewer than 3 test files is too few to trust: %s" % (rel, picked))
    return "%d pairs, plumbing runs everything, floor of 3" % checked


def a_broken_claim_lib_reds_a_selected_test(r):
    """The reviewer's mutation: UNTIL=$((NOW + LEASE)) -> NOW - 5 in claim_mutate. test_merge_affected still passes and
    test_coordination fails, so the selector must hand the second one over."""
    pkg = Path(tempfile.mkdtemp(prefix="sa-mut-", dir=str(r.scratch)))
    shutil.copytree(r.package / ".uak" / "bin", pkg / ".uak" / "bin", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(r.package / ".uak" / "tests", pkg / ".uak" / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    claim = pkg / ".uak" / "bin" / "lib" / "claim.sh"
    text = claim.read_text(encoding="utf-8")
    expect("UNTIL=$((NOW + LEASE))" in text, "the mutated line exists in claim.sh")
    claim.write_text(text.replace("UNTIL=$((NOW + LEASE))", "UNTIL=$((NOW - 5))", 1), encoding="utf-8", newline="\n")
    everything, picked = select_real(r, pkg, ".uak/bin/lib/claim.sh")
    expect(everything or "test_coordination.py" in picked, "claim.sh selects test_coordination: %s" % picked)
    ran = r.run(["env", "-u", "UAK_SMOKE_TESTS", sys_python(), ".uak/tests/test_coordination.py", "--package", pkg.as_posix()], cwd=pkg, allowed=None, timeout=600)
    expect(ran.returncode != 0 and "FAIL lease_boundary_preserves_summary" in ran.stdout, "the selected test goes red on the mutation: " + (ran.stdout + ran.stderr)[-500:])
    return "claim.sh mutation: test_coordination selected and red"


def sys_python():
    import sys
    return sys.executable or "python3"


def both_mode_files_carry_the_same_sentence(r):
    modes = [(r.package / ".uak" / "modes" / n).read_text(encoding="utf-8") for n in ("sprint.md", "marathon.md")]
    sentences = []
    for text in modes:
        found = [l.split(". ", 1)[1] for l in text.splitlines() if "smoke --affected" in l and l[:1].isdigit()]
        expect(len(found) == 1, "one numbered line names smoke --affected: %s" % found)
        sentences.append(found[0])
    expect(sentences[0] == sentences[1], "sprint and marathon carry the same sentence:\n%s\n%s" % tuple(sentences))
    expect("approval note says which was run" in sentences[0] and "gate never passes it" in sentences[0], "it covers the note and the gate")
    reviewer = (r.package.parent / ".claude" / "agents" / "uak-reviewer.md")
    reviewer = reviewer if reviewer.exists() else r.package / ".claude" / "agents" / "uak-reviewer.md"
    if reviewer.exists():
        expect("smoke --affected" in reviewer.read_text(encoding="utf-8"), "the reviewer's instructions name it")
    return "same sentence in both mode files"


TESTS = [affected_runs_changed_test_files, engine_change_selects_its_tests, core_change_runs_everything, gate_ignores_the_shortcut, prints_what_it_left,
         selector_keeps_the_commands_tests, a_broken_claim_lib_reds_a_selected_test, both_mode_files_carry_the_same_sentence]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-smoke-affected-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
            started = time.monotonic()
            try:
                note = test(runner)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started), flush=True)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (AssertionError: %s)" % (test.__name__, str(exc)[:2500]), flush=True)
    print("SMOKE_AFFECTED_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
