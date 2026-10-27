#!/usr/bin/env python3
"""uak v5.4: the Chilangatón autopsy (Oct 2026): 5 humans, 10 Claude Code identities on macOS and Windows, 35
tasks in 7 hours on venue Wi-Fi. One test per kit failure seen there: a merge that lost a race, a base fetch with
no retry, a done after a cross-machine handover, and reviewers who could not clean up their review checkouts.
Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm
from test_v43 import push_main


def merge_of_a_merged_task_is_done(r):
    """PB-024: an adopter merged the approved task; 19 s later its owner's `uak merge` went to the human queue as
    "Task without claim; cannot merge", wrote "Humano: …" on the INTEGRATED record and messaged the human."""
    f = rm.fixture(r, "v54-merged", count=2)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    f.claim(1, "HACK-002")                                  # the adopter is an agent with work of its own
    adopted = f.hack(1, "merge", "HACK-001", now=1000021 + 1300, allowed=None)
    expect(adopted.returncode == 0 and "INTEGRATED" in adopted.stdout, "the adopter merges: " + adopted.stdout + adopted.stderr)
    late = f.hack(0, "merge", "HACK-001", now=1000021 + 1320, allowed=None)
    out = late.stdout + late.stderr
    expect(late.returncode == 0 and "already INTEGRATED by agent-2" in out, "the owner's late merge is done: " + out)
    expect("MERGE_HUMAN" not in out, "no human queue: " + out)
    record = f.show("tasks/HACK-001.md")
    expect("Humano" not in record and "State: INTEGRATED" in record, "the record stays clean: " + record)
    expect("in human queue" not in f.show("inbox/log.md"), "no message to the human")
    expect("State: HUMAN" not in f.show("queue/HACK-001.md"), "no HUMAN queue entry")
    return {"merged": True}


def merge_that_loses_the_queue_race_is_done(r):
    """The PB-024 order: the adopter holds the merge lock (its candidate's smoke runs) while the owner's merge waits
    on "Queue busy"; when the adopter finalizes, the owner's next lock finds the task INTEGRATED."""
    f = rm.fixture(r, "v54-race", count=2)
    slow = (f.seed / ".uak/bin/smoke-project").read_text(encoding="utf-8")
    push_main(f, {".uak/bin/smoke-project": "sleep 6\n" + slow}, "slow product smoke")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    f.claim(1, "HACK-002")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        adopter = pool.submit(f.hack, 1, "merge", "HACK-001", now=1000021 + 1300, allowed=None)
        deadline = time.monotonic() + 60
        while "merge-lock.md" not in " ".join(f.files("queue")):
            expect(time.monotonic() < deadline and not adopter.done(), "the adopter takes the lock")
            time.sleep(0.2)
        owner = f.hack(0, "merge", "HACK-001", now=1000021 + 1310, allowed=None)
        adopted = adopter.result(timeout=240)
    expect(adopted.returncode == 0 and "INTEGRATED" in adopted.stdout, "the adopter merges: " + adopted.stdout + adopted.stderr)
    out = owner.stdout + owner.stderr
    expect(owner.returncode == 0 and "already INTEGRATED by agent-2" in out and "MERGE_HUMAN" not in out,
           "the owner who lost the race is done: " + out)
    expect("Humano" not in f.show("tasks/HACK-001.md"), "the record stays clean")
    expect("in human queue" not in f.show("inbox/log.md"), "no message to the human")
    expect("State: HUMAN" not in f.show("queue/HACK-001.md"), "no HUMAN queue entry")
    return {"race": True}


def base_fetch_retries_and_says_why(r):
    """10 `done` failed as "Could not read PROJECT.md on remote main" on venue Wi-Fi: one try, git's error hidden."""
    f = rm.fixture(r, "v54-flaky", count=1)
    f.claim(0, "HACK-001")
    rm.publish(f, 0, "HACK-001")
    shim = f.base / "shim"; shim.mkdir()
    flag = f.base / "failures"
    (shim / "git").write_text(
        "#!/usr/bin/env bash\n"
        "case \" $* \" in *' fetch '*refs/uak/config*)\n"
        "  n=$(cat \"$SHIM_FLAG\" 2>/dev/null || echo 0)\n"
        "  if [ \"$n\" -lt \"$SHIM_FAILS\" ]; then echo $((n + 1)) > \"$SHIM_FLAG\"\n"
        "    echo \"fatal: unable to access 'https://example.test/x.git/': Could not resolve host: example.test\" >&2; exit 128; fi;;\n"
        "esac\nexec \"$REAL_GIT\" \"$@\"\n", encoding="utf-8")
    os.chmod(shim / "git", 0o755)
    env = {"PATH": shim.as_posix() + os.pathsep + r.env.get("PATH", ""), "REAL_GIT": r.git,
           "SHIM_FLAG": flag.as_posix(), "UAK_AGENT": "agent-1", "UAK_NOW": "1000010", "UAK_HUMAN": ""}
    done = lambda fails, allowed: r.run([r.bash, ".uak/bin/uak", "done", "HACK-001", "--pr", "https://example.test/pull/1",
                                         "--evidence", "Fixture product acceptance"], cwd=f.worktrees[0],
                                        env={**env, "SHIM_FAILS": str(fails)}, allowed=allowed)
    down = done(9, None)
    out = down.stdout + down.stderr
    expect(down.returncode != 0 and "3 tries" in out and "Could not resolve host" in out, "the real reason: " + out)
    flag.unlink()
    once = done(1, None)
    expect(once.returncode == 0 and "REVIEW" in once.stdout, "one dropped fetch is retried: " + once.stdout + once.stderr)
    return {"retried": True}


def done_after_a_cross_machine_handover(r):
    """PB-027 moved from a Windows laptop to a Mac: done read the Windows path and died with "Missing worktree to
    record Task-Tip"; release and re-claim were the way out."""
    f = rm.fixture(r, "v54-handover", count=1)
    f.claim(0, "HACK-001")
    tip = rm.publish(f, 0, "HACK-001")
    moved = f.base / "other-machine"
    r.g(f.clones[0], "worktree", "move", f.worktrees[0], moved)
    f.worktrees[0] = moved
    done = f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance",
                  now=1000010, allowed=None)
    expect(done.returncode == 0 and "REVIEW" in done.stdout, "done from the new checkout: " + done.stdout + done.stderr)
    record = f.show("tasks/HACK-001.md")
    expect("Task-Tip: " + tip in record, "the tip of this checkout: " + record)
    expect("Worktree: " + moved.resolve().as_posix() in record, "the new path is recorded: " + record)
    return {"handover": True}


def review_checkout_is_removed_safely(r):
    """11 guard blocks on `worktree remove --force`: reviewers' detached checkouts kept Verify's build output, so a
    plain remove refused, and the guard's hint (`wt rm ID`) named the owner's worktree."""
    f = rm.fixture(r, "v54-review-rm", count=1)
    clone = f.clones[0]
    wt = lambda *a: r.run([r.bash, ".uak/bin/wt", "rm", *map(str, a)], cwd=clone, allowed=None)
    review = f.base / "review-HACK-001"
    r.g(clone, "worktree", "add", "-q", review, "origin/main")
    (review / "build.log").write_text("vite build\n", encoding="utf-8")
    plain = r.g(clone, "worktree", "remove", review, allowed=None)
    expect(plain.returncode != 0, "the plain remove refuses untracked output")
    gone = wt("--review", review)
    expect(gone.returncode == 0 and "WT_REMOVED" in gone.stdout and not review.exists(), gone.stdout + gone.stderr)

    r.g(clone, "worktree", "add", "-q", review, "origin/main")
    (review / ".uak/TASKS.md").write_text("edited\n", encoding="utf-8")
    edited = wt("--review", review)
    expect(edited.returncode == 2 and "edits to tracked files" in edited.stderr and review.exists(), edited.stderr)

    r.g(review, "checkout", "-q", "--", ".uak/TASKS.md")
    r.g(review, "-c", "user.name=R", "-c", "user.email=r@example.invalid", "commit", "-q", "--allow-empty", "-m", "local")
    stray = wt("--review", review)
    expect(stray.returncode == 2 and "commits on no branch" in stray.stderr and review.exists(), stray.stderr)

    branch = wt("--review", f.worktrees[0])
    expect(branch.returncode == 2 and "is on a branch" in branch.stderr and f.worktrees[0].exists(), branch.stderr)
    main = wt("--review", clone)
    expect(main.returncode == 2 and "not a worktree" in main.stderr, main.stderr)
    guard = lambda cmd: r.run([r.bash, ".uak/bin/guard", "check", cmd], cwd=clone, allowed=None)
    ok = guard("bash .uak/bin/wt rm --review ../review-HACK-001")
    expect(ok.returncode == 0 and "allowed" in ok.stdout, "the review cleanup passes the guard: " + ok.stdout + ok.stderr)
    blocked = guard("git worktree remove --force ../review-HACK-001")
    expect(blocked.returncode != 0 and "wt rm --review PATH" in blocked.stdout + blocked.stderr,
           "--force is still blocked, and the block names the review cleanup: " + blocked.stdout + blocked.stderr)
    return {"review_rm": True}


TESTS = [merge_of_a_merged_task_is_done, merge_that_loses_the_queue_race_is_done, base_fetch_retries_and_says_why, done_after_a_cross_machine_handover,
         review_checkout_is_removed_safely]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v54-") as tmp:
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
    print("V54_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
