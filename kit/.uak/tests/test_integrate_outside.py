#!/usr/bin/env python3
"""UAK-033: `uak integrate ID` records work that reached main outside the gate (deus-ex-machina, 2026-11-09: 11 integrate
refusals, "tree hash does not match", "changes no task file", "is AVAILABLE, not REVIEW"; the claims said 6 of 23
integrated while the product had shipped). It compares the task's own diff (its commits that main does not have, base
merges dropped) by final file content on main, never the whole tree hash, and marks the record Integrated-Outside: yes
with the approval it had (or none). The normal `uak merge` gate and an unmerged branch are untouched.
Real Git, a local bare remote."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

DEPS = {"HACK-004": "HACK-003"}


def fx(r, name):
    return r.fixture(name, count=2, dependencies=DEPS)


def seed(r, f, *args):
    return r.g(f.seed, *args)


def seed_pull(r, f):
    seed(r, f, "fetch", "-q", "origin")
    seed(r, f, "checkout", "-q", "main")
    seed(r, f, "merge", "-q", "--ff-only", "origin/main")


def commit_file(r, cwd, rel, text, msg):
    p = Path(cwd) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    r.g(cwd, "add", rel)
    r.g(cwd, "commit", "-q", "-m", msg)


def task_in_review(r, f, task="HACK-001", rel="src/one.txt", text="the work\n"):
    f.claim(0, task)
    w = f.worktrees[0]
    (w / ".uak-env").write_bytes(("UAK_TASK=%s\nUAK_AGENT=agent-1\n" % task).encode())
    commit_file(r, w, rel, text, task + ": the work")
    r.g(w, "push", "-q", "origin", f.branches[0])
    f.hack(0, "done", task, "--pr", "https://example.invalid/pull/1", "--evidence", "x", "--no-red", "fixture", now=1000010)
    return r.g(w, "rev-parse", "HEAD").stdout.strip()


def approve(r, f, task, tip):
    f.hack(0, "register-reviewer", "agent-2", human=True, now=1000011)
    rv = r.run([r.bash, ".uak/bin/uak", "review", task, "--sha", tip, "--verdict", "approve"], cwd=f.clones[1],
               env={"UAK_AGENT": "agent-2", "UAK_NOW": "1000020", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}, allowed=None)
    expect(rv.returncode == 0, "approval: " + rv.stdout + rv.stderr)


def claimed_with_pushed_work(r, f, text, second=None):
    """HACK-001 CLAIMED by agent-1 (never done), its branch pushed with `text` in src/one.txt (and `second` in
    src/two.txt: UAK-045, a single matching file with no approval needs a human)."""
    f.claim(0, "HACK-001")
    w = f.worktrees[0]
    commit_file(r, w, "src/one.txt", text, "HACK-001: the work")
    if second:
        commit_file(r, w, "src/two.txt", second, "HACK-001: the second file")
    r.g(w, "push", "-q", "origin", f.branches[0])


def squash_into_main(r, f, branch, msg="PR 1 (squash)", also=None):
    seed_pull(r, f)
    seed(r, f, "merge", "--squash", "-q", "origin/" + branch)
    seed(r, f, "commit", "-q", "-m", msg)
    if also:
        commit_file(r, f.seed, also[0], also[1], "unrelated")
    seed(r, f, "push", "-q", "origin", "main")


def integrate(f, task="HACK-001", agent=1, **kw):
    return f.hack(agent, "integrate", task, now=1000100, allowed=None, **kw)


def integrate_human(r, f, task="HACK-001"):
    """The human who merged it records it: UAK_HUMAN with no agent name, as the refusal says."""
    return r.run([r.bash, ".uak/bin/uak", "integrate", task], cwd=f.clones[0], env={
        "UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_NOW": "1000100", "UAK_REMOTE": "origin"}, allowed=None)


def record(f, task):
    return f.show("tasks/%s.md" % task)


def squash_merged_pr_is_recorded(r):
    f = fx(r, "io-squash")
    tip = task_in_review(r, f)
    squash_into_main(r, f, f.branches[0], also=None)
    seed(r, f, "reset", "-q", "--soft", "HEAD~1")  # the squash commit also carries another change: the tree hash differs
    commit_file(r, f.seed, "docs/squash-extra.txt", "rode along in the squash\n", "PR 1 (squash)")
    seed(r, f, "push", "-q", "-f", "origin", "main")
    approve(r, f, "HACK-001", tip)
    out = integrate(f)
    expect(out.returncode == 0, "squash merge must be recorded: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    rec = record(f, "HACK-001")
    expect("State: INTEGRATED" in rec and "Integrated-Outside: yes" in rec and "Approval: agent-2@" in rec, "record: " + rec)
    expect("claims/HACK-001.md" not in f.files("claims/"), "the reservation is released: " + str(f.files("claims/")))
    return "recorded outside, approval kept"


def pr_merged_after_extra_commits_is_recorded(r):
    f = fx(r, "io-extra")
    tip = task_in_review(r, f)
    approve(r, f, "HACK-001", tip)
    w = f.worktrees[0]
    commit_file(r, w, "src/one.txt", "the work, polished\n", "HACK-001: after the approval")
    r.g(w, "push", "-q", "origin", f.branches[0])
    squash_into_main(r, f, f.branches[0])
    out = integrate(f)
    expect(out.returncode == 0, "a PR merged after more commits: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    rec = record(f, "HACK-001")
    expect("Integrated-Outside: yes" in rec and "Approval: agent-2" in rec, "the approval it had is kept: " + rec)
    return "approval kept"


def base_merges_in_the_task_branch_are_ignored(r):
    f = fx(r, "io-basemerge")
    task_in_review(r, f)
    seed_pull(r, f)
    commit_file(r, f.seed, "docs/other.txt", "someone else's work\n", "unrelated work on main")
    seed(r, f, "push", "-q", "origin", "main")
    w = f.worktrees[0]
    r.g(w, "fetch", "-q", "origin")
    r.g(w, "merge", "-q", "--no-edit", "origin/main")
    r.g(w, "push", "-q", "origin", f.branches[0])
    f.hack(0, "done", "HACK-001", "--pr", "https://example.invalid/pull/1", "--evidence", "x", "--note", "merged main", now=1000012, allowed=None)
    squash_into_main(r, f, f.branches[0], also=("docs/more.txt", "and one more unrelated file\n"))
    out = integrate(f)
    expect(out.returncode != 0, "unreviewed work under review stays a human's: " + out.stdout)
    out = integrate_human(r, f)
    expect(out.returncode == 0, "base merges in the branch: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    expect("Integrated-Outside: yes" in record(f, "HACK-001"), "outside: " + record(f, "HACK-001"))
    return "own diff only"


def equivalent_content_on_main_is_recorded(r):
    f = fx(r, "io-equiv")
    claimed_with_pushed_work(r, f, "same bytes\n", second="second\n")
    seed_pull(r, f)
    commit_file(r, f.seed, "src/one.txt", "same bytes\n", "landed by another commit")
    commit_file(r, f.seed, "src/two.txt", "second\n", "landed too")
    seed(r, f, "push", "-q", "origin", "main")
    other = integrate(f, agent=1)
    expect(other.returncode != 0, "only the owner or a human records a claimed task: " + other.stdout)
    out = integrate(f, agent=0)
    expect(out.returncode == 0, "equivalent content: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    rec = record(f, "HACK-001")
    expect("Integrated-Outside: yes" in rec and "Approval: none" in rec, "outside, no approval: " + rec)
    return "equivalent content"


def unmerged_work_is_still_refused(r):
    f = fx(r, "io-refused")
    task_in_review(r, f)
    out = integrate(f)
    expect(out.returncode != 0, "work that is not on main is not recorded: " + out.stdout)
    expect("State: REVIEW" in record(f, "HACK-001") and "Integrated-Outside" not in record(f, "HACK-001"), "still REVIEW: " + record(f, "HACK-001"))
    seed_pull(r, f)
    commit_file(r, f.seed, "src/one.txt", "different bytes\n", "other content on the same file")
    seed(r, f, "push", "-q", "origin", "main")
    out = integrate(f)
    expect(out.returncode != 0 and "State: REVIEW" in record(f, "HACK-001"), "other content on main is not the task's work: " + out.stdout + out.stderr)
    return "refused"


def merged_branch_of_an_available_task_unblocks_its_dependents(r):
    f = fx(r, "io-available")
    seed_pull(r, f)
    seed(r, f, "checkout", "-q", "-b", "feat/hack-003")
    commit_file(r, f.seed, "src/three.txt", "built by a human\n", "HACK-003: built outside the claim")
    seed(r, f, "push", "-q", "origin", "feat/hack-003")
    seed(r, f, "checkout", "-q", "main")
    seed(r, f, "merge", "-q", "--no-ff", "-m", "Merge PR 3", "feat/hack-003")
    seed(r, f, "push", "-q", "origin", "main")
    blocked = f.claim(1, "HACK-004", allowed=None)
    expect(blocked.returncode != 0, "HACK-004 waits on HACK-003: " + blocked.stdout)
    out = integrate(f, "HACK-003")
    expect(out.returncode == 0, "an AVAILABLE task with a merged feat/<id>: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    rec = record(f, "HACK-003")
    expect("State: INTEGRATED" in rec and "Integrated-Outside: yes" in rec, "record: " + rec)
    ok = f.claim(1, "HACK-004", allowed=None, now=1000200)
    expect(ok.returncode == 0, "the dependent is claimable at once: " + ok.stdout + ok.stderr)
    return "dependent claimed"


def outside_merges_are_counted_apart(r):
    f = fx(r, "io-stats")
    claimed_with_pushed_work(r, f, "stats bytes\n", second="second\n")
    seed_pull(r, f)
    commit_file(r, f.seed, "src/one.txt", "stats bytes\n", "landed by another commit")
    commit_file(r, f.seed, "src/two.txt", "second\n", "landed too")
    seed(r, f, "push", "-q", "origin", "main")
    expect(integrate(f, agent=0).returncode == 0, "integrate")
    out = f.hack(0, "stats", allowed=None)
    expect("outside the gate: 1" in out.stdout, "stats counts it apart: " + out.stdout + out.stderr)
    return "stats line"


def single_file_unapproved_match_needs_a_human(r):
    """UAK-045 (v6.1.0 review of UAK-033): one file equal on main with nobody's approval may be a coincidence."""
    f = fx(r, "io-one-unapproved")
    claimed_with_pushed_work(r, f, "coincidence\n")
    seed_pull(r, f)
    commit_file(r, f.seed, "src/one.txt", "coincidence\n", "landed by another commit")
    seed(r, f, "push", "-q", "origin", "main")
    out = integrate(f, agent=0)
    expect(out.returncode != 0 and "only one file matched main and nobody approved it" in out.stdout + out.stderr,
           "an agent is refused with the reason: rc %d %s" % (out.returncode, out.stdout + out.stderr))
    expect("UAK_HUMAN=NAME uak integrate HACK-001" in out.stdout + out.stderr, "it names the human command: " + out.stdout + out.stderr)
    expect("State: INTEGRATED" not in record(f, "HACK-001"), "not recorded: " + record(f, "HACK-001"))
    out = integrate_human(r, f)
    expect(out.returncode == 0, "a human may record it: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    expect("Integrated-Outside: yes" in record(f, "HACK-001"), "outside: " + record(f, "HACK-001"))
    return "agent refused, human records"


def single_file_match_with_approval_is_recorded(r):
    f = fx(r, "io-one-approved")
    tip = task_in_review(r, f)
    approve(r, f, "HACK-001", tip)
    commit_file(r, f.worktrees[0], "src/one.txt", "the work, polished\n", "HACK-001: after the approval")
    r.g(f.worktrees[0], "push", "-q", "origin", f.branches[0])
    squash_into_main(r, f, f.branches[0])
    out = integrate(f)
    expect(out.returncode == 0, "one file with an approval is recorded: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    expect("Integrated-Outside: yes" in record(f, "HACK-001") and "Approval: agent-2" in record(f, "HACK-001"), "record: " + record(f, "HACK-001"))
    return "approval, one file"


TESTS = [squash_merged_pr_is_recorded, pr_merged_after_extra_commits_is_recorded, base_merges_in_the_task_branch_are_ignored,
         equivalent_content_on_main_is_recorded, unmerged_work_is_still_refused,
         merged_branch_of_an_available_task_unblocks_its_dependents, outside_merges_are_counted_apart,
         single_file_unapproved_match_needs_a_human, single_file_match_with_approval_is_recorded]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-integrate-outside-") as tmp:
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
    print("INTEGRATE_OUTSIDE_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
