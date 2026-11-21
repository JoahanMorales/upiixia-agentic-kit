#!/usr/bin/env python3
"""UAK-092: `uak integrate` for code that is on main with a valid approval (UpiixSol, 11 to 18 Nov 2026: 15 refusals
"Missing verifiable approval" and two notes: a task merged on the forge before its claim was cancelled whose dependents
refused to claim; a task in main that stayed AVAILABLE because the branch had a later commit).
  - the approved SHA is an ancestor of main and the branch has later commits: recorded at the approved SHA, the leftover
    commits named;
  - a CANCELLED task whose merge is on main: a human records it (UAK_HUMAN=NAME uak integrate ID --reason TEXT), and its
    dependents can be claimed;
  - code with no valid approval stays refused for agents.
Real Git, a local bare remote."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_integrate_outside import (approve, commit_file, fx, integrate, record, seed, seed_pull, task_in_review)


def merge_branch_into_main(r, f, branch, at=None):
    """The forge's merge of a PR: a merge commit on main for `at` (default the branch)."""
    seed_pull(r, f)
    seed(r, f, "fetch", "-q", "origin")
    seed(r, f, "merge", "-q", "--no-ff", "-m", "Merge PR", at or "origin/" + branch)
    seed(r, f, "push", "-q", "origin", "main")


def leftover(r, f, rel="src/extra.txt", text="after the review\n"):
    """A commit the owner pushes after the approved SHA (a reviewer's nit, a review note)."""
    w = f.worktrees[0]
    commit_file(r, w, rel, text, "HACK-001: after the review")
    r.g(w, "push", "-q", "origin", f.branches[0])
    return r.g(w, "rev-parse", "HEAD").stdout.strip()


def approved_ancestor_with_leftover_commit_integrates(r):
    f = fx(r, "iom-leftover")
    sha = task_in_review(r, f)
    approve(r, f, "HACK-001", sha)
    merge_branch_into_main(r, f, f.branches[0], at=sha)
    late = leftover(r, f)
    out = integrate(f)
    text = out.stdout + out.stderr
    expect(out.returncode == 0, "an agent records it: rc %d %s" % (out.returncode, text[-600:]))
    rec = record(f, "HACK-001")
    expect("State: INTEGRATED" in rec, "record: " + rec)
    expect(sha in rec, "recorded at the approved SHA: " + rec)
    expect("1 commit after the approved SHA is not on main: %s HACK-001: after the review" % late[:7] in text,
           "the leftover commit is named: " + text)
    return "integrated at the approved SHA"


def unreviewed_commits_on_main_are_named(r):
    f = fx(r, "iom-unreviewed")
    sha = task_in_review(r, f)
    approve(r, f, "HACK-001", sha)
    late = leftover(r, f)
    merge_branch_into_main(r, f, f.branches[0])  # the merge brings the later commit into main too
    out = integrate(f)
    text = out.stdout + out.stderr
    expect(out.returncode == 0, "recorded, not refused: rc %d %s" % (out.returncode, text[-600:]))
    expect("1 commit after the approved SHA is on main without a review: %s HACK-001: after the review" % late[:7] in text,
           "the unreviewed commit on main is named: " + text)
    expect("State: INTEGRATED" in record(f, "HACK-001") and "@" + sha[:7] in record(f, "HACK-001"), "record names the approved SHA: " + record(f, "HACK-001"))
    return "named"


def cancelled_with_merged_pr_recorded_by_human(r):
    f = fx(r, "iom-cancelled")
    f.claim(0, "HACK-003")
    w = f.worktrees[0]
    commit_file(r, w, "src/three.txt", "merged on the forge\n", "HACK-003: the work")
    r.g(w, "push", "-q", "origin", f.branches[0])
    f.hack(0, "release", "HACK-003", "--cancel", "dropped, then merged anyway", now=1000020)
    expect("State: CANCELLED" in record(f, "HACK-003"), "cancelled: " + record(f, "HACK-003"))
    merge_branch_into_main(r, f, f.branches[0])
    agent = integrate(f, "HACK-003")
    expect(agent.returncode != 0 and "State: CANCELLED" in record(f, "HACK-003"), "an agent cannot record a cancelled task: " + agent.stdout + agent.stderr)
    noreason = r.run([r.bash, ".uak/bin/uak", "integrate", "HACK-003"], cwd=f.clones[0], allowed=None, env={
        "UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_NOW": "1000100", "UAK_REMOTE": "origin"})
    expect(noreason.returncode != 0 and "--reason" in noreason.stdout + noreason.stderr, "the human says why: " + noreason.stdout + noreason.stderr)
    out = r.run([r.bash, ".uak/bin/uak", "integrate", "HACK-003", "--reason", "merged before the cancel"], cwd=f.clones[0], allowed=None, env={
        "UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_NOW": "1000100", "UAK_REMOTE": "origin"})
    expect(out.returncode == 0, "the human records it: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    rec = record(f, "HACK-003")
    expect("State: INTEGRATED" in rec and "Recorded-By: boss" in rec, "record: " + rec)
    return "recorded by the human"


def dependents_claimable_after(r):
    f = fx(r, "iom-dependents")
    f.claim(0, "HACK-003")
    w = f.worktrees[0]
    commit_file(r, w, "src/three.txt", "merged on the forge\n", "HACK-003: the work")
    r.g(w, "push", "-q", "origin", f.branches[0])
    f.hack(0, "release", "HACK-003", "--cancel", "dropped, then merged anyway", now=1000020)
    merge_branch_into_main(r, f, f.branches[0])
    blocked = f.claim(1, "HACK-004", allowed=None, now=1000050)
    expect(blocked.returncode != 0, "HACK-004 waits while HACK-003 is cancelled: " + blocked.stdout)
    out = r.run([r.bash, ".uak/bin/uak", "integrate", "HACK-003", "--reason", "merged before the cancel"], cwd=f.clones[0], allowed=None, env={
        "UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_NOW": "1000100", "UAK_REMOTE": "origin"})
    expect(out.returncode == 0, "human record: " + out.stdout + out.stderr)
    ok = f.claim(1, "HACK-004", allowed=None, now=1000200)
    expect(ok.returncode == 0, "the dependent is claimable: " + ok.stdout + ok.stderr)
    return "dependent claimed"


def unapproved_code_still_refused(r):
    # No approval at all, the first SHA on main, a later commit on the branch: refused for an agent.
    f = fx(r, "iom-unapproved")
    sha = task_in_review(r, f)
    merge_branch_into_main(r, f, f.branches[0], at=sha)
    leftover(r, f)
    out = integrate(f)
    expect(out.returncode != 0 and "State: REVIEW" in record(f, "HACK-001"), "no approval, no record: " + out.stdout + out.stderr)
    # An approval of a SHA that is not on main does not carry main's code: refused too.
    g = fx(r, "iom-approved-not-merged")
    sha = task_in_review(r, g)
    approve(r, g, "HACK-001", sha)
    leftover(r, g)
    out = integrate(g)
    expect(out.returncode != 0 and "State: REVIEW" in record(g, "HACK-001"), "approved but not on main: " + out.stdout + out.stderr)
    # The approver is a stranger to the claims: the approval itself is not valid.
    h = fx(r, "iom-self-approval")
    sha = task_in_review(r, h)
    merge_branch_into_main(r, h, h.branches[0], at=sha)
    leftover(r, h)
    out = integrate(h, agent=0)
    expect(out.returncode != 0, "the owner cannot record its own unreviewed task: " + out.stdout + out.stderr)
    return "refused"


TESTS = [approved_ancestor_with_leftover_commit_integrates, cancelled_with_merged_pr_recorded_by_human,
         dependents_claimable_after, unapproved_code_still_refused, unreviewed_commits_on_main_are_named]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak integrate-main-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                return test.__name__, True, "%s, %.2fs" % (test(runner), time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        selected = [t for t in TESTS if not args.case or t.__name__ in args.case]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, selected))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("INTEGRATE_ON_MAIN_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
