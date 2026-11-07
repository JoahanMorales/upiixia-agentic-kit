#!/usr/bin/env python3
"""UAK-019: plan's owner checks match claim's.
- `uak plan` warned "can never be claimed" for a path whose OWNERS row belongs to a task already INTEGRATED, while
  claim allows it (the row is advice then): UAK-018 got the warning and was claimed fine.
- `plan FILE --amend` checked every Path of the amended task against the other live claims, so an amend that only
  changed Depends waited for every claim under those Paths to integrate (UAK-006 waited on UAK-008). It now checks
  only the Paths the amend adds.
Real Git, a local bare remote."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack

WARN = "can never be claimed"


def task(tid, paths, verify=".uak/bin/smoke --package-only"):
    return ("## %s — a task\n\n- **Priority:** P1\n- **Paths:** %s\n- **Depends on:** None\n- **Verify:** %s\n\n"
            % (tid, paths, verify))


def plan(f, body, *extra, allowed=None):
    path = f.worktrees[0] / ("plan-%d.md" % time.monotonic_ns())
    path.write_text(body, encoding="utf-8")
    return hack(f, 0, "plan", path, *extra, UAK_HUMAN="joahan", allowed=allowed)


def set_state(r, f, tid, state):
    """A raw edit of claims (what a merge leaves): the task record's State becomes `state`; INTEGRATED drops its claim."""
    clone = f.base / ("raw-%d" % time.monotonic_ns())
    r.g(f.base, "clone", "-q", "-b", "claims", f.remote, clone)
    rec = clone / "tasks" / (tid + ".md")
    rec.write_text("".join(("State: %s\n" % state) if l.startswith("State: ") else l
                           for l in rec.read_text(encoding="utf-8").splitlines(True)), encoding="utf-8")
    if state == "INTEGRATED" and (clone / "claims" / (tid + ".md")).exists():
        r.g(clone, "rm", "-q", "claims/%s.md" % tid)  # integration releases the claim's files
    r.g(clone, "-c", "user.name=raw", "-c", "user.email=raw@example.invalid", "commit", "-qam", "raw state")
    r.g(clone, "push", "-q", "origin", "claims")


def owned_fixture(r, name):
    f = r.fixture(name, paths={"HACK-001": "src/one/", "HACK-002": "src/two/"}, count=2, owners={"src/one/": "HACK-001"})
    config(f, Plan_Channel="claims")
    return f


def plan_does_not_warn_for_an_integrated_owner(r):
    f = owned_fixture(r, "po-integrated")
    f.claim(0, "HACK-001")
    set_state(r, f, "HACK-001", "INTEGRATED")
    out = plan(f, "# Wave\n\n" + task("HACK-005", "src/one/new.txt"))
    expect(out.returncode == 0 and "OK plan" in out.stdout, "plan must publish: " + out.stdout + out.stderr)
    expect(WARN not in out.stdout + out.stderr, "an INTEGRATED owner's row is advice: no warning, got: " + out.stdout + out.stderr)
    claimed = f.claim(1, "HACK-005", allowed=None)
    expect(claimed.returncode == 0, "and the task is claimable: " + claimed.stdout + claimed.stderr)
    return "no warning, claimed"


def plan_still_warns_for_a_live_owner(r):
    f = owned_fixture(r, "po-live")
    f.claim(0, "HACK-001")
    out = plan(f, "# Wave\n\n" + task("HACK-005", "src/one/new.txt"))
    expect(out.returncode == 0 and WARN in out.stdout + out.stderr, "a live owner still warns: " + out.stdout + out.stderr)
    return "warned"


def amend_with_the_same_paths_passes_a_live_claim(r):
    f = r.fixture("po-amend-same", paths={"HACK-001": "src/one/", "HACK-002": "src/"}, count=2)
    config(f, Plan_Channel="claims")
    f.claim(0, "HACK-001")
    out = plan(f, "# Amend\n\n" + task("HACK-002", "src/", verify="true"), "--amend")
    expect(out.returncode == 0 and "OK plan --amend" in out.stdout,
           "an amend that keeps the Paths must pass a live claim under them: rc %d %s" % (out.returncode, out.stdout + out.stderr))
    return "amended"


def amend_adding_a_claimed_path_is_refused(r):
    f = r.fixture("po-amend-add", paths={"HACK-001": "src/one/", "HACK-002": "src/two/"}, count=2)
    config(f, Plan_Channel="claims")
    f.claim(0, "HACK-001")
    out = plan(f, "# Amend\n\n" + task("HACK-002", "src/two/, src/one/"), "--amend")
    expect(out.returncode == 3 and "overlap HACK-001" in out.stderr, "a newly added claimed path is refused: rc %d %s" % (out.returncode, out.stdout + out.stderr))
    return "refused"


TESTS = [plan_does_not_warn_for_an_integrated_owner, plan_still_warns_for_a_live_owner,
         amend_with_the_same_paths_passes_a_live_claim, amend_adding_a_claimed_path_is_refused]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-plan-owners-") as tmp:
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
    print("PLAN_OWNERS_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
