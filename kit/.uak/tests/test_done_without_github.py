#!/usr/bin/env python3
"""UAK-092: a project without GitHub can finish a task. QA round C (2026-11-14, C-2): on a local bare remote
`wt pr` said "Not a GitHub remote" and `uak done --pr file://...` said "needs --pr HTTPS URL (... wt pr)", a dead
loop; one tester invented an https URL to get out. With Review-Mode: claims or a non-GitHub remote, `--pr none`
(or the task's branch) is accepted and recorded, and both messages name it. A GitHub remote in PR review mode
still needs a real PR URL. Real Git, a local bare remote."""
import argparse
import concurrent.futures
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary



def github_url(f):
    return "https://github.com/fixture-org/%s.git" % f.base.name


def env_for(r, f, index, github=False):
    """UAK_* for agent N; on a GitHub-looking origin, every Git process maps that URL to the local bare remote."""
    env = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": "1000010", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    if github:
        n = int(r.env.get("GIT_CONFIG_COUNT", "0"))
        env.update({"GIT_CONFIG_COUNT": str(n + 1), "GIT_CONFIG_KEY_%d" % n: "url.%s.insteadOf" % f.remote.as_posix(),
                    "GIT_CONFIG_VALUE_%d" % n: github_url(f)})
    return env


def uak(r, f, index, *args, github=False, allowed=(0,)):
    return r.run([r.bash, ".uak/bin/uak", *map(str, args)], cwd=f.worktrees[index], env=env_for(r, f, index, github), allowed=allowed)


def ready(r, f, index, task, github=False):
    uak(r, f, index, "claim", task, "--branch", f.branches[index], "--worktree", f.worktrees[index].as_posix(),
        "--next", "Ship it", github=github)
    w = f.worktrees[index]
    (w / ".uak-env").write_bytes(("UAK_TASK=%s\nUAK_AGENT=agent-%d\n" % (task, index + 1)).encode())
    (w / "src").mkdir(exist_ok=True)
    (w / "src" / ("%s.txt" % task)).write_text("a change\n", encoding="utf-8")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", task + ": a change")
    r.run([r.git, "push", "-q", "origin", f.branches[index]], cwd=w, env=env_for(r, f, index, github))


def as_github(r, f, index):
    """The clone's origin reads as a GitHub URL (env_for maps it back to the local bare remote)."""
    r.g(f.clones[index], "remote", "set-url", "origin", github_url(f))


def done(r, f, index, task, pr, github=False):
    return uak(r, f, index, "done", task, "--pr", pr, "--evidence", "fixture exit 0", "--no-red", "fixture",
               github=github, allowed=None)


def record_field(f, task, key):
    m = re.search(r"^%s:\s*(.*)$" % re.escape(key), f.show("tasks/%s.md" % task), re.M)
    return m.group(1).strip() if m else ""


def done_accepts_no_pr_without_github(r):
    f = r.fixture("dn-accept", count=3)
    # A local bare remote, Review-Mode: claims (the fixture's PROJECT.md): --pr none.
    ready(r, f, 0, "HACK-001")
    out = done(r, f, 0, "HACK-001", "none")
    expect(out.returncode == 0, "--pr none is accepted on a local remote: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(record_field(f, "HACK-001", "State") == "REVIEW", "HACK-001 is in REVIEW")
    expect(record_field(f, "HACK-001", "PR") == "none", "PR none is recorded: %r" % record_field(f, "HACK-001", "PR"))
    expect("reviews none" not in f.show("tasks/HACK-001.md"), "the review hint names the branch, not 'none'")
    # The task's branch instead of a PR URL.
    ready(r, f, 1, "HACK-002")
    out = done(r, f, 1, "HACK-002", f.branches[1])
    expect(out.returncode == 0, "--pr BRANCH is accepted: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(record_field(f, "HACK-002", "PR") == f.branches[1], "the branch is recorded: %r" % record_field(f, "HACK-002", "PR"))
    # A GitHub remote with Review-Mode: claims needs no PR either.
    as_github(r, f, 2)
    ready(r, f, 2, "HACK-003", github=True)
    out = done(r, f, 2, "HACK-003", "none", github=True)
    expect(out.returncode == 0, "Review-Mode: claims on GitHub accepts --pr none: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(record_field(f, "HACK-003", "PR") == "none", "PR none recorded on HACK-003")
    return "none, branch, claims on GitHub"


def wt_pr_names_the_fallback(r):
    f = r.fixture("dn-wtpr", count=1)
    ready(r, f, 0, "HACK-001")
    w = f.worktrees[0]
    env = {"UAK_AGENT": "agent-1", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    out = r.run([r.bash, ".uak/bin/wt", "pr"], cwd=w, env=env, allowed=None)
    text = out.stdout + out.stderr
    expect("Not a GitHub remote" in text, "wt pr still says it is not GitHub: " + text[-500:])
    expect("--pr none" in text and "uak done HACK-001" in text, "wt pr names the no-PR fallback with the task: " + text[-500:])
    # The done error for a URL it cannot use names the same fallback, not only wt pr.
    bad = done(r, f, 0, "HACK-001", "file://%s#%s" % (f.remote.as_posix(), f.branches[0]))
    btext = bad.stdout + bad.stderr
    expect(bad.returncode != 0 and "HTTPS" in btext, "a file:// URL is still refused: " + btext[-500:])
    expect("--pr none" in btext, "the done error names --pr none: " + btext[-500:])
    expect(record_field(f, "HACK-001", "State") == "CLAIMED", "still CLAIMED after the refusal")
    return "both messages"


def github_still_needs_a_pr(r):
    f = r.fixture("dn-github", count=2)
    # PROJECT.md on main says Review-Mode: auto: GitHub reviews the PR.
    project = f.seed / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8").replace("Review-Mode: claims", "Review-Mode: auto"), encoding="utf-8")
    r.g(f.seed, "commit", "-q", "-am", "Review-Mode: auto")
    r.g(f.seed, "push", "-q", "origin", "main")
    as_github(r, f, 0)
    ready(r, f, 0, "HACK-001", github=True)
    for pr in ("none", f.branches[0]):
        out = done(r, f, 0, "HACK-001", pr, github=True)
        text = out.stdout + out.stderr
        expect(out.returncode != 0, "--pr %s is refused on GitHub with Review-Mode auto: %s" % (pr, text[-500:]))
        expect("wt pr" in text and "Review-Mode: claims" in text, "the refusal says how to get a PR or switch mode: " + text[-500:])
        expect(record_field(f, "HACK-001", "State") == "CLAIMED", "still CLAIMED after --pr %s" % pr)
    # Another branch name is never a stand-in, even where no PR is needed.
    ready(r, f, 1, "HACK-002")
    out = done(r, f, 1, "HACK-002", "some-other-branch")
    expect(out.returncode != 0 and "--pr none" in out.stdout + out.stderr, "a branch that is not the task's is refused: " + (out.stdout + out.stderr)[-500:])
    return "PR still required"


TESTS = [done_accepts_no_pr_without_github, wt_pr_names_the_fallback, github_still_needs_a_pr]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-done-nogh-") as tmp:
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
    print("DONE_WITHOUT_GITHUB_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
