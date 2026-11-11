#!/usr/bin/env python3
"""UAK-038: a registered reviewer is offered the REVIEW tasks it may review before any coding task (DevDay: a review-only
Codex agent missed a REVIEW task because `next` offered coding work and `wait` did not wake it), `uak wait --for message`
also wakes when such a task enters REVIEW, and `uak status --summary ID` works like `status ID --summary` (Codex hit
"--summary needs --task ID" 3 times in deus-ex-machina). Real Git, a local bare remote."""
import argparse
import concurrent.futures
import tempfile
import threading
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def to_review(r, f, task="HACK-001", index=0, now=1000010, to=None):
    f.claim(index, task)
    w = f.worktrees[index]
    (w / ".uak-env").write_bytes(("UAK_TASK=%s\nUAK_AGENT=agent-%d\n" % (task, index + 1)).encode())
    (w / "src").mkdir(exist_ok=True)
    (w / "src" / ("%s.txt" % task)).write_text("a change\n", encoding="utf-8")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", task + ": a change")
    r.g(w, "push", "-q", "origin", f.branches[index])
    f.hack(index, "done", task, "--pr", "https://example.invalid/pull/1", "--evidence", "a change", "--no-red", "fixture", *(["--to", to] if to else []), now=now)


def reviewer_env(**extra):
    e = {"UAK_AGENT": "agent-3", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_DEDUPE": "off"}
    e.update(extra)
    return e


def three(r, name, *reviewers):
    f = r.fixture(name, count=3)
    f.hack(0, "register-reviewer", *(reviewers or ("agent-3", "agent-2")), human=True, now=1000005)
    return f


def reviewer_next_offers_review_first(r):
    f = three(r, "rn-first", "agent-3")
    to_review(r, f)
    out = r.run([r.bash, ".uak/bin/uak", "next"], cwd=f.clones[2], env=reviewer_env(UAK_NOW="1000020"))
    first = out.stdout.splitlines()
    text = "\n".join(first[:6])
    expect("review" in text.lower() and "HACK-001" in text and "/uak-review HACK-001" in text,
           "a registered reviewer is offered the REVIEW task first: " + out.stdout[:600])
    expect("| AVAILABLE |" not in "\n".join(first[:2]), "not the coding task first: " + out.stdout[:600])
    # Not a registered reviewer, no claim: coding work stays the offer.
    other = r.run([r.bash, ".uak/bin/uak", "next"], cwd=f.clones[1], env=reviewer_env(UAK_AGENT="agent-2", UAK_NOW="1000020"))
    expect("| AVAILABLE |" in other.stdout, "an unregistered agent keeps the coding offer: " + other.stdout[:400])
    return "review first"


def wait_wakes_on_new_review_work(r):
    f = three(r, "rn-wait")
    box = {}

    def waiter():
        box["out"] = r.run([r.bash, ".uak/bin/uak", "wait", "--for", "message", "--timeout", "40"], cwd=f.clones[2],
                           env=reviewer_env(UAK_WAIT_EVERY="1"), allowed=None)
    t = threading.Thread(target=waiter)
    t.start()
    time.sleep(6)
    expect(t.is_alive(), "the wait is still waiting before any task is in REVIEW")
    to_review(r, f, now=int(time.time()), to="agent-2")  # asked another reviewer: no message for agent-3
    t.join(60)
    expect(not t.is_alive(), "the wait returned")
    out = box["out"]
    expect(out.returncode == 0 and "HACK-001" in out.stdout and "review" in out.stdout.lower(), "woken by the REVIEW task: rc %d %s" % (out.returncode, out.stdout[-500:] + out.stderr[-300:]))
    return "woken"


def status_id_summary_works(r):
    f = three(r, "rn-summary")
    f.claim(0, "HACK-001")
    for args in (["status", "--summary", "HACK-001"], ["status", "HACK-001", "--summary"], ["status", "--task", "HACK-001", "--summary"]):
        out = r.run([r.bash, ".uak/bin/uak", *args], cwd=f.clones[2], env=reviewer_env(UAK_NOW="1000020"), allowed=None)
        expect(out.returncode == 0 and "Live summary:" in out.stdout, "%s: rc %d %s" % (args, out.returncode, (out.stdout + out.stderr)[-400:]))
    return "three forms"


TESTS = [reviewer_next_offers_review_first, wait_wakes_on_new_review_work, status_id_summary_works]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-reviewer-next-") as tmp:
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
    print("REVIEWER_NEXT_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
