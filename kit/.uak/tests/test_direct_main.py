#!/usr/bin/env python3
"""UAK-035: in a repo with a backlog, a commit on the base branch in the main checkout is refused by the kit's pre-commit
hook. Why (deus-ex-machina): 120 of 155 first-parent commits on main came from agents working in the main checkout. The
guard blocked one push to main, but the commits were already made, so none of that work had a task, a review, token
attribution or a black box line. `uak merge`, `wt` and task worktrees are not affected; a human's hotfix says
UAK_DIRECT_MAIN=1 and is logged; `uak stats` counts what went around the tasks. Real Git, a local bare remote."""
import argparse
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm


def with_hook(r, name, count=2):
    f = rm.fixture(r, name, count=count)
    r.g(f.clones[0], "pull", "-q", "--ff-only", "origin", "main")   # the fixture rewrote main after the clone
    r.g(f.clones[0], "config", "core.hooksPath", ".githooks")
    return f


def commit_in(r, cwd, rel, text, env=None):
    p = cwd / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    r.g(cwd, "add", "--", rel)
    return r.run([r.git, "commit", "-q", "-m", "a change"], cwd=cwd, env=env, allowed=None)


def commit_on_main_with_a_backlog_is_refused(r):
    f = with_hook(r, "dm-refuse")
    clone = f.clones[0]
    head = r.g(clone, "rev-parse", "HEAD").stdout
    out = commit_in(r, clone, "notes.txt", "hello\n", env={"UAK_DIRECT_MAIN": ""})
    text = out.stdout + out.stderr
    expect(out.returncode != 0, "refused: rc %d %s" % (out.returncode, text[-300:]))
    expect("main takes work through tasks" in text and "wt new ID" in text and "UAK_DIRECT_MAIN=1" in text, "says the way: " + text[-400:])
    expect(r.g(clone, "rev-parse", "HEAD").stdout == head, "no commit was made")
    ok = commit_in(r, f.worktrees[0], "src/value-1.txt", "work\n", env={"UAK_DIRECT_MAIN": ""})
    expect(ok.returncode == 0, "a task worktree commits freely: " + (ok.stdout + ok.stderr)[-300:])
    # The backlog and the kit's own files are not product work: a plan or a kit update still commits on main.
    r.g(clone, "reset", "-q", "HEAD", "--", "notes.txt")   # the refused commit left it staged
    plan =commit_in(r, clone, ".uak/TASKS.md", r.g(clone, "show", "HEAD:.uak/TASKS.md").stdout + "\n<!-- next wave -->\n", env={"UAK_DIRECT_MAIN": ""})
    expect(plan.returncode == 0, "a plan commit on main is not refused: " + (plan.stdout + plan.stderr)[-300:])
    # No backlog yet (the template's example task only): main is open, as before.
    r.g(clone, "reset", "-q", "--soft", "HEAD")
    (clone / ".uak/TASKS.md").write_text("# TASKS\n\n## HACK-001 · <one visible result>\n", encoding="utf-8")
    r.g(clone, "add", "-A")
    free = r.run([r.git, "commit", "-q", "-m", "empty backlog"], cwd=clone, env={"UAK_DIRECT_MAIN": ""}, allowed=None)
    expect(free.returncode == 0, "no real task in the backlog: " + (free.stdout + free.stderr)[-300:])
    return "refused"


def hotfix_override_is_allowed_and_logged(r):
    f = with_hook(r, "dm-hotfix")
    clone = f.clones[0]
    out = commit_in(r, clone, "hotfix.txt", "fix\n", env={"UAK_DIRECT_MAIN": "1"})
    expect(out.returncode == 0, "UAK_DIRECT_MAIN=1 commits: " + (out.stdout + out.stderr)[-300:])
    common = r.g(clone, "rev-parse", "--git-common-dir").stdout.strip()
    log = (clone / common / "uak-direct-main.log")
    expect(log.is_file() and "main" in log.read_text(encoding="utf-8"), "the override is logged in the git dir")
    return "allowed and logged"


def uak_merge_still_commits(r):
    f = with_hook(r, "dm-merge")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    f.r.g(f.clones[0], "config", "core.hooksPath", ".githooks")
    out = f.hack(0, "merge", "HACK-001", now=1000023)
    expect("INTEGRATED" in out.stdout, "uak merge works with the hook on: " + (out.stdout + out.stderr)[-400:])
    return "merged"


def stats_counts_direct_commits(r):
    f = with_hook(r, "dm-stats")
    clone = f.clones[0]
    f.claim(1, "HACK-002")   # stats reads the claims branch, which exists once something is claimed
    pat = re.compile(r"Direct to main: (\d+) of (\d+) first-parent commits")
    stats = lambda: pat.search(r.run([r.bash, ".uak/bin/uak", "stats"], cwd=clone, env={"UAK_AGENT": "agent-1", "UAK_REMOTE": "origin"}, allowed=None).stdout)
    before = stats()
    expect(before is not None, "stats prints the line")
    d0, m0 = int(before.group(1)), int(before.group(2))
    for i in range(2):
        commit_in(r, clone, "direct-%d.txt" % i, "x\n", env={"UAK_DIRECT_MAIN": "1"})
    # A squash-merged task PR is not direct, and neither is the root commit.
    commit_in(r, clone, "squash.txt", "x\n", env={"UAK_DIRECT_MAIN": "1"})
    r.run([r.git, "commit", "-q", "--amend", "-m", "HACK-018 · x (#80)"], cwd=clone, env={"UAK_DIRECT_MAIN": "1"})
    commit_in(r, clone, "plain.txt", "x\n", env={"UAK_DIRECT_MAIN": "1"})
    r.run([r.git, "commit", "-q", "--amend", "-m", "fix: y"], cwd=clone, env={"UAK_DIRECT_MAIN": "1"})
    commit_in(r, clone, "pr.txt", "x\n", env={"UAK_DIRECT_MAIN": "1"})
    r.run([r.git, "commit", "-q", "--amend", "-m", "tidy the docs (#81)"], cwd=clone, env={"UAK_DIRECT_MAIN": "1"})
    r.g(clone, "push", "-q", "origin", "main")
    after = stats()
    expect(after and (int(after.group(1)), int(after.group(2))) == (d0 + 3, m0 + 5), "2 direct and 1 plain counted, 2 squash PRs not: %s" % (after and after.group(0)))
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    f.hack(0, "merge", "HACK-001", now=1000023)
    r.g(clone, "fetch", "-q", "origin")
    merged = stats()
    expect(merged and (int(merged.group(1)), int(merged.group(2))) == (d0 + 3, m0 + 6), "a task merge is not direct: %s" % (merged and merged.group(0)))
    return "counted"


TESTS = [commit_on_main_with_a_backlog_is_refused, hotfix_override_is_allowed_and_logged, uak_merge_still_commits, stats_counts_direct_commits]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-direct-main-") as tmp:
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
    print("DIRECT_MAIN_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
