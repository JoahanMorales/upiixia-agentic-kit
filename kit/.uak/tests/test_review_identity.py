#!/usr/bin/env python3
"""UAK-020: a reviewer sent into the author's task worktree takes the author's identity from its .uak-env (the worktree
wins over an exported UAK_AGENT, on purpose), and `uak review` refused with "The owner cannot approve their own task"
and nothing else. The only way out a reviewer found was UAK_ENV_OVERRIDE (Nov 6). The refusal now says what happened
and where to review from, and never suggests the override. Real Git, a local bare remote."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def in_review(r, name):
    """agent-1 owns HACK-001 in REVIEW, from worktree-1 with its .uak-env; agent-2 is a registered reviewer."""
    f = r.fixture(name, count=2)
    f.claim(0, "HACK-001")
    w = f.worktrees[0]
    (w / ".uak-env").write_bytes(b"UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n")
    (w / "src").mkdir(exist_ok=True)
    (w / "src" / "one.txt").write_text("a change\n", encoding="utf-8")
    r.g(w, "add", "src/one.txt")
    r.g(w, "commit", "-q", "-m", "HACK-001: a change")
    r.g(w, "push", "-q", "origin", f.branches[0])
    f.hack(0, "done", "HACK-001", "--pr", "https://example.invalid/pull/1", "--evidence", "a change", "--no-red", "fixture", now=1000010)
    f.hack(0, "register-reviewer", "agent-2", human=True, now=1000011)
    return f, r.g(w, "rev-parse", "HEAD").stdout.strip()


def review_as(r, f, cwd, tip):
    env = {"UAK_AGENT": "agent-2", "UAK_NOW": "1000020", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    return r.run([r.bash, ".uak/bin/uak", "review", "HACK-001", "--sha", tip, "--verdict", "approve"], cwd=cwd, env=env, allowed=None)


def review_in_the_authors_worktree_names_the_way_out(r):
    f, tip = in_review(r, "ri-author-wt")
    out = review_as(r, f, f.worktrees[0], tip)
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "The owner cannot approve their own task" in text, "still refused: rc %d %s" % (out.returncode, text[-500:]))
    expect(".uak-env" in text and "agent-1" in text and "agent-2" in text and "main checkout" in text,
           "the refusal says the worktree's .uak-env named agent-1 over the shell's agent-2, and to review from the main checkout: " + text[-500:])
    expect("UAK_ENV_OVERRIDE" not in text, "the refusal must not suggest UAK_ENV_OVERRIDE: " + text[-500:])
    return "refused with the way out"


def review_from_the_main_checkout_still_works(r):
    f, tip = in_review(r, "ri-own-clone")
    out = review_as(r, f, f.clones[1], tip)
    expect(out.returncode == 0 and "OK review HACK-001" in out.stdout, "agent-2's review from its own clone: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    return "approved"


TESTS = [review_in_the_authors_worktree_names_the_way_out, review_from_the_main_checkout_still_works]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-review-identity-") as tmp:
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
    print("REVIEW_IDENTITY_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
