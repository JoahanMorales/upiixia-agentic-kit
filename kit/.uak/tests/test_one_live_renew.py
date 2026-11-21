#!/usr/bin/env python3
"""UAK-110: one identity = one live task also for heartbeat, log, checkpoint and handoff. An identity whose claim on X
expired and that then claimed Y renewed X's lease (a TLA+ model of claims found the trace: claim t1, lease expires,
claim t2, heartbeat t1; audit docs/audit-2026-11.md #1). A claim with a damaged Lease-Until counts as live (#10).
Real Git, a local bare remote."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

T0 = 1000000
LATER = 1100000


def second_claim(r, f, task="HACK-002", now=LATER, allowed=(0,)):
    """agent-1 claims TASK from a second worktree (the first claim keeps its own)."""
    clone = f.clones[0]
    wt = f.base / "worktree-1b"
    if not wt.exists():
        r.g(clone, "worktree", "add", "-b", "task/agent-1b", wt, "main")
    env = {"UAK_AGENT": "agent-1", "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    return r.run([r.bash, ".uak/bin/uak", "claim", task, "--branch", "task/agent-1b", "--worktree", wt.as_posix(),
                  "--next", "Ejecutar siguiente paso exacto"], cwd=wt, env=env, allowed=allowed)


def renew(f, verb, now):
    args = {"heartbeat": ["heartbeat", "HACK-001"],
            "log": ["log", "HACK-001", "--text", "still here"],
            "checkpoint": ["checkpoint", "HACK-001", "--done", "a", "--decision", "b", "--why", "c", "--fails", "d",
                           "--commands", "e", "--next", "f"],
            "handoff": ["handoff", "HACK-001"]}[verb]
    return f.hack(0, *args, now=now, allowed=None)


def lease_of(f, task):
    for line in f.show("claims/%s.md" % task).splitlines():
        if line.startswith("Lease-Until:"):
            return line.split(":", 1)[1].strip()
    return ""


def expired_claim_cannot_be_renewed_with_another_live(r):
    f = r.fixture("olr-expired", count=1)
    f.claim(0, "HACK-001", now=T0)
    before = lease_of(f, "HACK-001")
    second_claim(r, f)
    out = renew(f, "heartbeat", LATER + 10)
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "one live task" in text.lower(), "heartbeat refused: rc %d %s" % (out.returncode, text[-600:]))
    expect("HACK-002" in text and "release" in text, "names the live task and how to give up: " + text[-600:])
    expect(lease_of(f, "HACK-001") == before, "the lease of HACK-001 was not renewed: " + lease_of(f, "HACK-001"))
    # Taking it back: release Y first, then X renews.
    out = f.hack(0, "release", "HACK-002", now=LATER + 20, allowed=None)
    # release runs from the worktree of agent-1; the identity is the same.
    expect(out.returncode == 0, "release Y: " + out.stdout + out.stderr)
    out = renew(f, "heartbeat", LATER + 30)
    expect(out.returncode == 0, "renews after Y is released: " + out.stdout + out.stderr)
    return "refused"


def log_and_checkpoint_refuse_too(r):
    f = r.fixture("olr-others", count=1)
    f.claim(0, "HACK-001", now=T0)
    second_claim(r, f)
    for verb in ("log", "checkpoint", "handoff"):
        out = renew(f, verb, LATER + 10)
        text = out.stdout + out.stderr
        expect(out.returncode != 0 and "one live task" in text.lower(), "%s refused: rc %d %s" % (verb, out.returncode, text[-500:]))
    expect(int(lease_of(f, "HACK-001")) < LATER, "no renewal slipped through: " + lease_of(f, "HACK-001"))
    return "refused"


def unexpired_claim_renews(r):
    f = r.fixture("olr-live", count=1)
    f.claim(0, "HACK-001", now=T0)
    # An identity with no other live claim renews, even long after expiry (as today).
    out = renew(f, "heartbeat", LATER)
    expect(out.returncode == 0, "alone, expired: " + out.stdout + out.stderr)
    # Not expired: renews too.
    out = renew(f, "heartbeat", LATER + 10)
    expect(out.returncode == 0, "X was just renewed, so it is not expired: " + out.stdout + out.stderr)
    # UAK_MULTI_CLAIM=1 keeps its meaning: two live claims, and the expired one still renews.
    g = r.fixture("olr-multi", count=1)
    g.claim(0, "HACK-001", now=T0)
    env = {"UAK_AGENT": "agent-1", "UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_MULTI_CLAIM": "1"}
    wt = g.base / "worktree-1b"
    r.g(g.clones[0], "worktree", "add", "-b", "task/agent-1b", wt, "main")
    out = r.run([r.bash, ".uak/bin/uak", "claim", "HACK-002", "--branch", "task/agent-1b", "--worktree", wt.as_posix(),
                 "--next", "x"], cwd=wt, env=dict(env, UAK_NOW=str(LATER)), allowed=None)
    expect(out.returncode == 0, "MULTI_CLAIM claims a second task: " + out.stdout + out.stderr)
    out = r.run([r.bash, ".uak/bin/uak", "heartbeat", "HACK-001"], cwd=g.worktrees[0], env=dict(env, UAK_NOW=str(LATER + 10)), allowed=None)
    expect(out.returncode == 0, "MULTI_CLAIM renews: " + out.stdout + out.stderr)
    return "renews"


def damaged_lease_counts_as_live(r):
    f = r.fixture("olr-damaged", count=1)
    f.claim(0, "HACK-001", now=T0)
    work = f.base / "claims-edit"
    r.g(f.base, "clone", "-q", "--branch", "claims", f.remote, work)
    claim = work / "claims" / "HACK-001.md"
    text = claim.read_text(encoding="utf-8")
    claim.write_text("".join(("Lease-Until: soon\n" if l.startswith("Lease-Until:") else l) for l in text.splitlines(True)), encoding="utf-8")
    r.g(work, "-c", "user.name=X", "-c", "user.email=x@example.invalid", "commit", "-q", "-am", "damage the lease")
    r.g(work, "push", "-q", "origin", "claims")
    out = second_claim(r, f, allowed=None)
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "one live task" in text.lower(), "a damaged lease cannot be used to take a second task: rc %d %s" % (out.returncode, text[-600:]))
    out = f.hack(0, "tick", now=LATER, allowed=None)
    expect("DAMAGED LEASE HACK-001" in out.stdout + out.stderr, "tick reports the damaged lease: " + out.stdout + out.stderr)
    return "live"


TESTS = [expired_claim_cannot_be_renewed_with_another_live, log_and_checkpoint_refuse_too, unexpired_claim_renews,
         damaged_lease_counts_as_live]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-one-live-") as tmp:
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
    print("ONE_LIVE_RENEW_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
