#!/usr/bin/env python3
"""UAK-088: `wt new ID --agent NAME` refused with "already has claims/ID.md" when the claim already belonged to NAME
(after `uak handover ID --to NAME`, or a claim made on another machine): the agent had to `git worktree add` by hand
(UpiixSol, Nov 2026). It now resumes the claim on the task's existing branch; another identity's claim keeps the
refusal. Real Git, a local bare remote."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def wt_new(r, f, task, agent, index=1):
    env = {"UAK_AGENT": "", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000200"}
    return r.run([r.bash, ".uak/bin/wt", "new", task, "--agent", agent], cwd=f.clones[index], env=env, allowed=None)


def handed_over(r, name):
    """ana-1 claims HACK-001 with wt new in clone 0, pushes one commit, and hands it to bob-1."""
    f = r.fixture(name, paths={"HACK-001": "src/one.txt"}, count=2)
    first = wt_new(r, f, "HACK-001", "ana-1", index=0)
    expect(first.returncode == 0 and "WT_READY" in first.stdout + first.stderr, "ana's wt new: " + first.stdout + first.stderr)
    wt = next(iter((r.scratch / name).glob("*-wt/hack-001")))
    (wt / "src").mkdir(exist_ok=True)
    (wt / "src" / "one.txt").write_text("work by ana\n", encoding="utf-8")
    r.g(wt, "add", "src/one.txt")
    r.g(wt, "commit", "-q", "-m", "HACK-001: first part")
    r.g(wt, "push", "-q", "origin", "feat/hack-001")
    out = r.run([r.bash, ".uak/bin/uak", "handover", "HACK-001", "--to", "bob-1"], cwd=wt,
                env={"UAK_AGENT": "ana-1", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000100"}, allowed=None)
    expect(out.returncode == 0, "handover: " + out.stdout + out.stderr)
    return f


def resumes_own_claim_after_handover(r):
    f = handed_over(r, "wrc-resume")
    out = wt_new(r, f, "HACK-001", "bob-1")
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "WT_READY" in text and "resumed the claim" in text, "resumed: rc %d %s" % (out.returncode, text[-700:]))
    expect("already has claims" not in text, "no refusal: " + text)
    wt = next(iter((r.scratch / "wrc-resume").glob("*-wt/hack-001")))
    expect(wt.exists() and (wt / "src" / "one.txt").read_text(encoding="utf-8") == "work by ana\n", "starts from the task's branch")
    expect("UAK_AGENT=bob-1" in (wt / ".uak-env").read_text(encoding="utf-8"), "the .uak-env names bob-1")
    claim = f.show("claims/HACK-001.md")
    expect("Owner: bob-1" in claim and wt.as_posix() in claim.replace("\\", "/"), "the claim points at the new worktree: " + claim)
    return "resumed"


def refuses_claim_of_another_identity(r):
    f = handed_over(r, "wrc-other")
    out = wt_new(r, f, "HACK-001", "carol-1")
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "already has claims/HACK-001.md" in text, "refused: rc %d %s" % (out.returncode, text[-500:]))
    expect("bob-1" in text, "the refusal names the owner bob-1: " + text[-500:])
    return "refused"


def fetches_the_remote_branch(r):
    f = handed_over(r, "wrc-fetch")
    expect(r.g(f.clones[1], "branch", "--list", "feat/hack-001").stdout.strip() == "", "the branch is only on origin for clone 1")
    out = wt_new(r, f, "HACK-001", "bob-1")
    expect(out.returncode == 0, "wt new: " + out.stdout + out.stderr)
    expect(r.g(f.clones[1], "branch", "--list", "feat/hack-001").stdout.strip() != "", "the branch now exists locally")
    return "fetched"


TESTS = [resumes_own_claim_after_handover, refuses_claim_of_another_identity, fetches_the_remote_branch]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-wt-resume-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("WT_RESUME_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
