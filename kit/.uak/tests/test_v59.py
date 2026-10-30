#!/usr/bin/env python3
"""uak v5.9: the HackADA autopsy (Oct 2026). The repo began as a copy of the previous hackathon's and ran uak 5.3.0;
a published Verify had an unbalanced quote; a negated rg passed where rg was missing; uv was not on a Windows PATH;
and the map asked for a key in every worktree because the keys lived only in the main checkout. One test per fix.
Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import shutil
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack
from test_v571 import push_tasks
import test_review_merge as rm

BROKEN = """# Wave 2

## HACK-005 · Broken quotes

- **Priority:** P0
- **Paths:** src/five.txt
- **Depends on:** None
- **Verify:** `bash -c '! grep -q old src' && test -s src/five.txt'`
"""


def a_verify_that_does_not_parse_is_refused(r):
    """CO-018's Verify had an unbalanced quote: published, approved, then red at the gate as "unexpected end of file"."""
    f = r.fixture("v59-parse", count=1)
    config(f, Plan_Channel="claims")
    path = f.worktrees[0] / "plan-broken.md"
    path.write_text(BROKEN, encoding="utf-8")
    out = hack(f, 0, "plan", path, UAK_HUMAN="joahan", allowed=None)
    expect(out.returncode != 0 and "HACK-005's Verify does not parse" in out.stderr, out.stdout + out.stderr)
    expect("HACK-005" not in f.r.g(f.remote, "show", "claims:backlog/TASKS.md", allowed=None).stdout, "not published")
    push_tasks(f, lambda t: t.replace("- **Verify:** .uak/bin/smoke --package-only",
                                      "- **Verify:** `bash -c '! rg -n old src' && true'`", 1))
    lint = hack(f, 0, "lint", allowed=None)
    expect(lint.returncode != 0 and "HACK-001's Verify does not parse" in lint.stderr, lint.stdout + lint.stderr)
    push_tasks(f, lambda t: t.replace("`bash -c '! rg -n old src' && true'`", "`bash -c '! rg -n old src'`", 1))
    warn = hack(f, 0, "lint", allowed=None)
    expect("does not parse" not in warn.stderr and "HACK-001's Verify negates rg" in warn.stderr, warn.stdout + warn.stderr)
    return {"refused": True}


def a_green_verify_with_a_missing_command_is_red(r):
    """`! rg -n -i "pulso barrial" …` passed on every machine without rg, whatever the code said."""
    f = rm.fixture(r, "v59-missing", count=1)
    push_tasks(f, lambda t: t.replace('test "$(cat src/value-1.txt)" = ready-HACK-001',
                                      '! uak-no-such-tool -n old src && test "$(cat src/value-1.txt)" = ready-HACK-001', 1))
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    out = rm.actor(f, "agent-1", "merge", "HACK-001", now=1000030, allowed=None, timeout=300)
    expect(out.returncode != 0 and "uak-no-such-tool was missing" in out.stdout + out.stderr, out.stdout + out.stderr)
    return {"red": True}


def doctor_names_the_verify_tools_this_machine_lacks(r):
    """uv was not on PATH on a Windows laptop; agents found out one task at a time."""
    f = r.fixture("v59-doctor", count=1)
    push_tasks(f, lambda t: t.replace("- **Verify:** .uak/bin/smoke --package-only", "- **Verify:** `bun test && git status`", 1))
    out = f.r.run([f.r.bash, ".uak/bin/doctor"], cwd=f.seed, allowed=None)
    lacks = shutil.which("bun") is None
    expect(("Verify commands run bun, missing on this machine" in out.stdout) == lacks, out.stdout)
    expect(lacks or "the tools the plan's Verify commands run are on PATH" in out.stdout, out.stdout)
    return {"bun_missing": lacks}


def start_says_the_kit_is_older_than_the_installed_one(r):
    """HackADA's repo was a copy of the previous one and ran uak 5.3.0 while ~/.uak-kit had 5.8.0."""
    f = r.fixture("v59-start", count=1)
    home = f.base / "kit-home"
    (home / "kit/.uak").mkdir(parents=True)
    (home / "kit/.uak/VERSION").write_text("99.0.0\n", encoding="utf-8")
    (f.seed / ".uak/PROJECT.md").write_text((f.seed / ".uak/PROJECT.md").read_text(encoding="utf-8") + "Mode: sprint\n", encoding="utf-8")
    out = f.r.run([f.r.bash, ".uak/bin/start"], cwd=f.seed, env={"UAK_KIT_HOME": str(home)}, allowed=None)
    expect("update the kit: this project has uak" in out.stdout and "has 99.0.0" in out.stdout
           and "install.sh --mode sprint --update ." in out.stdout, out.stdout)
    pinned = f.r.run([f.r.bash, ".uak/bin/start"], cwd=f.seed, env={"UAK_KIT_HOME": str(home), "UAK_KIT_PIN": "1"}, allowed=None)
    expect("update the kit" not in pinned.stdout, pinned.stdout)
    return {"told": True}


def a_new_worktree_finds_the_keys(r):
    """The map said "needs a key" in every worktree: .env lived only in the main checkout."""
    f = r.fixture("v59-env", count=1)
    main = f.clones[0]
    (main / ".gitignore").write_text(((main / ".gitignore").read_text(encoding="utf-8") if (main / ".gitignore").exists() else "")
                                     + "\n.env\n", encoding="utf-8")
    f.r.g(main, "add", ".gitignore"); f.r.g(main, "commit", "-q", "-m", "ignore .env"); f.r.g(main, "push", "-q", "origin", "HEAD:main")
    (main / ".env").write_text("VITE_KEY=" + "fixture\n", encoding="utf-8")
    out = f.r.run([f.r.bash, ".uak/bin/wt", "new", "HACK-002", "--agent", "agent-9"], cwd=main,
                  env={"UAK_REMOTE": "origin", "UAK_NOW": "1000000", "UAK_HUMAN": ""}, allowed=None)
    expect(out.returncode == 0, out.stdout + out.stderr)
    wt = [line.split("worktree ", 1)[1].strip() for line in out.stdout.splitlines() if line.startswith("WT_READY")][0]
    env = Path(wt) / ".env"
    expect(env.exists() and "VITE_KEY" in env.read_text(encoding="utf-8"), "the worktree reads the main checkout's .env")
    status = f.r.g(Path(wt), "status", "--porcelain").stdout
    expect(".env" not in status, "and git does not see it: " + status)
    return {"linked": env.is_symlink()}


TESTS = [a_verify_that_does_not_parse_is_refused, a_green_verify_with_a_missing_command_is_red,
         doctor_names_the_verify_tools_this_machine_lacks, start_says_the_kit_is_older_than_the_installed_one,
         a_new_worktree_finds_the_keys]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v59-") as tmp:
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
    print("V59_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
