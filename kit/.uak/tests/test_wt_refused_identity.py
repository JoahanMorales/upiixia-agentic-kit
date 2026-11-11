#!/usr/bin/env python3
"""UAK-049: `wt new ID` whose claim is refused (overlap, dependency, freeze, owners) left a new identity registered on
the claims branch and, retried, took the next number: joahanmorales-6, -7, -9 and -11 never held a task (v6.1.0
session). A refused claim now registers nothing, leaves no branch or worktree, and the retry reuses the same free
identity. Real Git, a local bare remote."""
import argparse
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def agents_on_claims(r, f):
    out = r.g(f.remote, "ls-tree", "--name-only", "claims", "meta/agents/", allowed=(0, 128)).stdout
    return sorted(re.sub(r"^meta/agents/|\.md$", "", l) for l in out.split())


def wt_new(r, f, task):
    env = {"UAK_AGENT": "", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000100"}
    return r.run([r.bash, ".uak/bin/wt", "new", task], cwd=f.clones[1], env=env, allowed=None)


def blocked_fixture(r, name):
    """HACK-001 and HACK-002 share src/one.txt; agent-1 holds HACK-001, so HACK-002's claim is refused (overlap)."""
    f = r.fixture(name, paths={"HACK-001": "src/one.txt", "HACK-002": "src/one.txt"}, count=2)
    f.claim(0, "HACK-001")
    return f


def refused_claim_registers_no_identity(r):
    f = blocked_fixture(r, "wr-refused")
    before = agents_on_claims(r, f)
    out = wt_new(r, f, "HACK-002")
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "WT_CLAIM_FAILED" in text, "the claim is refused: rc %d %s" % (out.returncode, text[-500:]))
    after = agents_on_claims(r, f)
    expect(after == before, "no identity registered by the refusal: %s -> %s" % (before, after))
    wts = r.g(f.clones[1], "worktree", "list", "--porcelain").stdout
    expect("hack-002" not in wts, "no worktree left: " + wts)
    expect(r.g(f.clones[1], "branch", "--list", "feat/hack-002").stdout.strip() == "", "no branch left")
    return "nothing registered"


def retry_reuses_the_free_identity(r):
    f = blocked_fixture(r, "wr-retry")
    first = wt_new(r, f, "HACK-002")
    expect(first.returncode != 0, "first try refused")
    named = re.search(r"new identity (\S+)", first.stdout + first.stderr)
    expect(named, "the first try named an identity: " + (first.stdout + first.stderr)[-400:])
    f.hack(0, "release", "HACK-001", now=1000050)
    again = wt_new(r, f, "HACK-002")
    text = again.stdout + again.stderr
    expect(again.returncode == 0 and "WT_READY" in text, "the retry succeeds: rc %d %s" % (again.returncode, text[-600:]))
    env_file = (r.scratch / "wr-retry").glob("agent-2-wt/hack-002/.uak-env")
    env_text = next(iter(env_file)).read_text(encoding="utf-8")
    expect("UAK_AGENT=" + named.group(1) in env_text, "same identity %s after the retry: %s" % (named.group(1), env_text))
    return "same identity " + named.group(1)


TESTS = [refused_claim_registers_no_identity, retry_reuses_the_free_identity]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-wt-refused-") as tmp:
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
    print("WT_REFUSED_IDENTITY_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
