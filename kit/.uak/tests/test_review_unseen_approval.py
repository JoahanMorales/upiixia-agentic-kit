#!/usr/bin/env python3
"""UAK-087: reviews/ID.md approving the current SHA by an identity never seen on claims (no meta/agents file, or retired)
made `uak review --start` answer SKIP and `--verdict approve` record nothing, while `uak merge` rejected that same
approval as "never seen on claims or retired": the task could only go to the human. A valid reviewer now replaces it.
Real Git, local bare remotes."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm
from test_v55 import write_claims


def ghost_approved(r, name):
    f = rm.fixture(r, name, count=1)
    tip = rm.ready(f, 0, "HACK-001")
    write_claims(f, {"reviews/HACK-001.md": "# Review HACK-001\nID: HACK-001\nSHA: %s\nOwner: agent-1\nReviewer: ghost\n"
                     "Verdict: approve\nReviewed: 1000015\nCommand: uak review\nEligible-Via: role:ghost\n" % tip},
                 "forged approval")
    rm.judge(f)
    return f, tip


def unseen_approval_does_not_skip_start(r):
    f, tip = ghost_approved(r, "ua-start")
    out = rm.actor(f, "judge", "review", "HACK-001", "--start", allowed=None)
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "SKIP" not in text, "--start must not skip an unseen approval: " + text)
    return "started"


def valid_reviewer_replaces_unseen_approval(r):
    f, tip = ghost_approved(r, "ua-replace")
    out = rm.approve(f, "HACK-001", tip)
    expect("replaces an approval by ghost, never seen on claims" in out.stdout, "the replaced approval is named: " + out.stdout + out.stderr)
    review = f.show("reviews/HACK-001.md")
    expect("Reviewer: judge" in review and "ghost" not in review, "judge's verdict is recorded: " + review)
    return "replaced"


def seen_approval_still_skips(r):
    f = rm.fixture(r, "ua-seen", count=1)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.actor(f, "human-registrar", "register-reviewer", "judge-2", human=True)
    rm.approve(f, "HACK-001", tip)
    start = rm.actor(f, "judge-2", "review", "HACK-001", "--start", allowed=None)
    expect("SKIP review HACK-001 | already approved by judge on this SHA" in start.stdout, "start: " + start.stdout + start.stderr)
    dup = rm.approve(f, "HACK-001", tip, name="judge-2")
    expect("already approved by judge on this SHA; nothing recorded" in dup.stdout, "verdict: " + dup.stdout)
    expect("Reviewer: judge\n" in f.show("reviews/HACK-001.md"), "nothing recorded")
    return "skips"


def merge_accepts_the_replacement(r):
    f, tip = ghost_approved(r, "ua-merge")
    rm.approve(f, "HACK-001", tip)
    out = rm.actor(f, "agent-1", "merge", "HACK-001", now=1000030, allowed=None, timeout=300)
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout, "merge: " + out.stdout + out.stderr)
    return "merged"


TESTS = [unseen_approval_does_not_skip_start, valid_reviewer_replaces_unseen_approval, seen_approval_still_skips,
         merge_accepts_the_replacement]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-unseen-approval-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("UNSEEN_APPROVAL_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
