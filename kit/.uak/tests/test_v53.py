#!/usr/bin/env python3
"""uak v5.3: `uak start`, the way from install to the first claim (Oct 2026). A solo marathon project spent two hours
before its first claim: the kit was not on main, the plan was not approved, Review-Mode gh waited for a second GitHub
account, and `uak next` only said "No eligible candidate". One scenario walks that project from an empty repo to its
first merge with `uak start` naming each step; the others pin the reasons next now gives and small wording fixes.
Real Git, local bare remote behind a github.com URL, a fake gh, separate processes."""
import argparse
import concurrent.futures
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


TASKS = """## APP-001 · Core
- **Priority:** P0
- **Paths:** src/core.sh, tests/core_test.sh, pkg/mocks/Mocks.sh
- **Depends on:** None
- **Verify:** bash tests/core_test.sh

## APP-002 · Mocks
- **Priority:** P1
- **Paths:** pkg/mocks/
- **Depends on:** APP-001
- **Verify:** true

## APP-003 · Docs
- **Priority:** P1
- **Paths:** docs/
- **Depends on:** APP-001
- **Verify:** true

## APP-004 · Core cache
- **Priority:** P1
- **Paths:** src/core.sh
- **Depends on:** None
- **Verify:** true
"""


def solo_project(r, name):
    """An empty repo whose origin is a github.com URL served by a local bare remote; gh says one collaborator."""
    t = r.scratch / name; t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.g(t, "config", "user.name", "Solo"); r.g(t, "config", "user.email", "solo@example.invalid")
    remote = r.scratch / (name + "-remote.git")
    r.g(r.scratch, "init", "-q", "--bare", remote)
    bin_dir = r.scratch / (name + "-bin"); bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/usr/bin/env bash\ncase \"$1 $2\" in\n  'auth status') echo 'Token scopes: repo';;\n"
                                "  'api repos/solo/app/collaborators?per_page=2') echo 1;;\n  'api repos/solo/app') echo true,true,true;;\n"
                                "esac\nexit 0\n", encoding="utf-8")
    os.chmod(bin_dir / "gh", 0o755)
    env = {"PATH": bin_dir.as_posix() + os.pathsep + r.env.get("PATH", ""),
           "GIT_CONFIG_COUNT": "3", "GIT_CONFIG_KEY_2": "url." + remote.as_posix() + ".insteadOf",
           "GIT_CONFIG_VALUE_2": "https://github.com/solo/app.git"}
    return t, env


def solo_marathon_from_zero_to_merge(r):
    """From an empty repo to the first merge, alone on the GitHub repo, with `uak start` naming each step."""
    pkg = r.package.parent
    t, env = solo_project(r, "v53-solo")
    r.run([r.bash, str(pkg / "install.sh"), "--mode", "marathon", "--harness", "claude", str(t)], cwd=t, env=env)
    start = lambda *a: r.run([r.bash, ".uak/bin/uak", "start", *a], cwd=t, env=env, allowed=None)
    git = lambda *a: r.run([r.git, *a], cwd=t, env=env)
    uak = lambda who, *a, cwd=t, allowed=(0,): r.run([r.bash, ".uak/bin/uak", *a], cwd=cwd, env={**env, "UAK_AGENT": who}, allowed=allowed)

    out = start()
    expect(out.returncode == 1 and "TODO  2. a remote named origin" in out.stdout, "no remote yet: " + out.stdout)
    git("remote", "add", "origin", "https://github.com/solo/app.git")

    out = start()
    expect("only collaborator of solo/app" in out.stdout and "uak start --fix" in out.stdout, "alone with Review-Mode gh: " + out.stdout)
    out = start("--fix")
    expect("fixed: Review-Mode: claims" in out.stdout, "--fix: " + out.stdout)
    expect("Review-Mode: claims" in (t / ".uak/PROJECT.md").read_text(encoding="utf-8"), "PROJECT.md now reviews on claims")
    expect("push the kit to main" in out.stdout and "git push -u origin HEAD:main" in out.stdout, "kit not on main: " + out.stdout)
    git("add", "-A"); git("commit", "-qm", "chore: uak setup"); git("push", "-q", "-u", "origin", "main")

    out = start()
    expect("a plan: no tasks in .uak/TASKS.md on main" in out.stdout and "/uak-plan" in out.stdout, "no plan: " + out.stdout)
    (t / ".uak/TASKS.md").write_text(TASKS, encoding="utf-8")
    git("add", "-A"); git("commit", "-qm", "plan"); git("push", "-q", "origin", "main")

    # The template's OWNERS rows name HACK-001/HACK-002: one grouped lint line each, with the fix.
    out = start()
    expect("owner not in TASKS: HACK-001 owns" in out.stdout and "Point them to the task" in out.stdout, "template owners: " + out.stdout)
    expect(out.stdout.count("owner not in TASKS: HACK-001") == 1, "one line per owner: " + out.stdout)
    expect("approve the plan: Backlog-Approved is not yes on main" in out.stdout, "unapproved plan: " + out.stdout)
    nxt = uak("solo-1", "next")
    expect("Why not APP-001, APP-004: Backlog pending approval" in nxt.stdout and "min left" in nxt.stdout, "next says why: " + nxt.stdout)
    expect("Waiting on dependencies: 2 task(s); APP-002 waits on APP-001 (AVAILABLE)" in nxt.stdout, "next names the dependency: " + nxt.stdout)

    # The friend's shape: the root task writes a file under a directory its dependent owns.
    (t / ".uak/OWNERS.md").write_text("# Shared-file owners\n\n| Pattern | Owner task |\n|---|---|\n| pkg/mocks/ | APP-002 |\n", encoding="utf-8")
    project = t / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8").replace("Backlog-Approved: no", "Backlog-Approved: yes"), encoding="utf-8")
    out = start()
    expect("push your changes to .uak/PROJECT.md .uak/OWNERS.md" in out.stdout and "approve the plan" not in out.stdout, "approved here, not pushed: " + out.stdout)
    git("add", "-A"); git("commit", "-qm", "approve"); git("push", "-q", "origin", "main")

    out = start()
    expect(out.returncode == 0 and "START READY · bash .uak/bin/wt new APP-001" in out.stdout, "ready: " + out.stdout)
    expect("register-reviewer <you>-r" in out.stdout, "alone: who reviews the first PR: " + out.stdout)
    again = start()
    expect("START READY · bash .uak/bin/wt new APP-001" in again.stdout, "a second start is not '= unchanged': " + again.stdout)

    r.run([r.bash, ".uak/bin/uak", "register-reviewer", "solo-r"], cwd=t, env={**env, "UAK_HUMAN": "solo", "UAK_AGENT": ""})
    r.run([r.bash, ".uak/bin/wt", "new", "APP-001", "--agent", "solo-1"], cwd=t, env=env)
    w = r.scratch / "v53-solo-wt/app-001"
    for d in ("src", "tests", "pkg/mocks"):
        (w / d).mkdir(parents=True, exist_ok=True)
    (w / "src/core.sh").write_text("echo core\n", encoding="utf-8")
    (w / "tests/core_test.sh").write_text("bash src/core.sh\n", encoding="utf-8")
    (w / "pkg/mocks/Mocks.sh").write_text("echo mock\n", encoding="utf-8")
    wgit = lambda *a: r.run([r.git, *a], cwd=w, env=env)
    wgit("add", "-A"); wgit("commit", "-qm", "feat: core"); wgit("push", "-q", "-u", "origin", "HEAD")

    nxt = uak("solo-2", "next")
    expect("Why not APP-004: its Paths overlap APP-001 of solo-1 (CLAIMED)" in nxt.stdout, "overlap reason: " + nxt.stdout)
    uak("solo-1", "done", "APP-001", "--pr", "https://github.com/solo/app/pull/1", "--evidence", "bash tests/core_test.sh exit 0", cwd=w)
    sha = wgit("rev-parse", "HEAD").stdout.strip()
    uak("solo-r", "review", "APP-001", "--sha", sha, "--verdict", "approve")
    merge = uak("solo-1", "merge", "APP-001", cwd=w, allowed=None)
    expect("MERGE_HUMAN APP-001" in merge.stdout + merge.stderr and "uak integrate APP-001" in merge.stdout + merge.stderr,
           "marathon: the human merges on GitHub: " + merge.stdout + merge.stderr)
    git("fetch", "-q", "origin"); git("merge", "-q", "--no-ff", "origin/feat/app-001", "-m", "Merge pull request #1")
    git("push", "-q", "origin", "main")
    uak("solo-1", "integrate", "APP-001", cwd=w)
    out = start()
    expect("START READY · bash .uak/bin/wt new APP-002" in out.stdout, "the dependent owner opens after the merge: " + out.stdout)
    return {"solo": True}


def start_outside_and_before(r):
    """start in a folder that is no Git repo, and in a repo without the kit, names the first step and exits 1."""
    plain = r.scratch / "v53-plain"; plain.mkdir()
    out = r.run([r.bash, str(r.package / ".uak/bin/start")], cwd=plain, allowed=None)
    expect(out.returncode == 1 and "a Git repository" in out.stdout, out.stdout + out.stderr)
    r.g(plain, "init", "-q", "-b", "main")
    out = r.run([r.bash, str(r.package / ".uak/bin/start")], cwd=plain, allowed=None)
    expect(out.returncode == 1 and "install the kit" in out.stdout and "--solo" in out.stdout, out.stdout)
    bad = r.run([r.bash, str(r.package / ".uak/bin/start"), "--now"], cwd=plain, allowed=None)
    expect(bad.returncode == 2 and "Usage: uak start" in bad.stderr, bad.stderr)
    return {"start": True}


def wording(r):
    """The clock lists design lock before the first claim; stats ends the human-queue line with no stray dot."""
    clock = r.run([r.bash, str(r.package / ".uak/bin/clock"), "2026-11-01 09:00", "2026-11-02 09:00", "UTC"])
    lines = clock.stdout.splitlines()
    at = lambda key: next(i for i, l in enumerate(lines) if l.startswith(key))
    expect(at("design lock") < at("first claim by") < at("walking skeleton"), clock.stdout)
    stats = (r.package / ".uak/bin/stats").read_text(encoding="utf-8")
    expect('printf "%s ×%d ·"' not in stats, "human-queue reasons joined with ' · '")
    return {"wording": True}


TESTS = [solo_marathon_from_zero_to_merge, start_outside_and_before, wording]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v53-") as tmp:
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
    print("V53_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
