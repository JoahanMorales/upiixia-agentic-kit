#!/usr/bin/env python3
"""UAK-050: `plan --amend` checks overlaps the way claims do. An AVAILABLE task holds no reservation, so its amend never
fails on overlap (it warns and publishes; the claim gate still refuses the claim later); several tasks amended in one
file are checked against each other's NEW Paths; a CLAIMED or REVIEW task whose new Paths overlap another live claim is
still refused. Why (v6.1.0 session): four amends in a fixed order, and an AVAILABLE task refused twice for tasks only
waiting for review. Real Git, a local bare remote."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack


def section(tid, paths):
    return ("## %s — amended\n\n- **Priority:** P0\n- **Paths:** %s\n- **Depends on:** None\n"
            "- **Acceptance:** salida comprobable\n- **Verify:** echo amended\n\n" % (tid, paths))


def amend(f, *sections):
    path = f.worktrees[0] / ("amend-%d.md" % time.monotonic_ns())
    path.write_text("# Amend\n\n" + "".join(section(t, p) for t, p in sections), encoding="utf-8")
    return hack(f, 0, "plan", path, "--amend", UAK_HUMAN="joahan", allowed=None)


def available_task_amend_overlap_warns_and_publishes(r):
    f = r.fixture("pa-available", count=2)
    config(f, Plan_Channel="claims")
    f.claim(0, "HACK-001")
    out = amend(f, ("HACK-003", "src/one.txt"))
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "OK plan" in out.stdout, "an AVAILABLE task's amend publishes: rc %d %s" % (out.returncode, text[-500:]))
    expect("HACK-003's new Paths overlap HACK-001 (CLAIMED/REVIEW): its claim will wait for it" in text, "it warns: " + text[-500:])
    shown = f.hack(1, "status", "--task", "HACK-003", allowed=None)
    expect("src/one.txt" in shown.stdout + shown.stderr, "the amend is published: " + shown.stdout + shown.stderr)
    late = f.claim(1, "HACK-003", allowed=None)
    expect(late.returncode != 0, "the claim gate still refuses the overlapping claim: " + late.stdout + late.stderr)
    return "warned, published, claim refused"


def one_file_amend_uses_the_new_paths_of_the_others(r):
    f = r.fixture("pa-swap", count=2)
    config(f, Plan_Channel="claims")
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")
    # HACK-002 takes the file HACK-001 drops, in the order that fails when the others' OLD Paths are checked.
    out = amend(f, ("HACK-002", "src/one.txt"), ("HACK-001", "src/three.txt"))
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "OK plan" in out.stdout, "an amend that drops a file frees it for another in the same file: rc %d %s" % (out.returncode, text[-500:]))
    return "new Paths of the others"


def claimed_task_amend_overlap_is_still_refused(r):
    f = r.fixture("pa-claimed", count=2)
    config(f, Plan_Channel="claims")
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")
    out = amend(f, ("HACK-001", "src/two.txt"))
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "overlap HACK-002" in text, "a claimed task's overlap is refused: rc %d %s" % (out.returncode, text[-500:]))
    out = amend(f, ("HACK-001", "src/two.txt"), ("HACK-002", "src/two.txt"))
    expect(out.returncode != 0, "two claimed tasks given the same new file are refused: " + out.stdout + out.stderr)
    return "refused"


def plan_prints_hints_but_publishes(r):
    """The lead's note (UAK-051 on the base): `uak plan FILE` prints the Paths hints and never fails on them."""
    f = r.fixture("pa-hint", count=1)
    config(f, Plan_Channel="claims")
    w = f.worktrees[0]
    (w / "src").mkdir(exist_ok=True)
    (w / "src/api.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    (w / "src/coord.py").write_text("def coord_next():\n    return 2\n", encoding="utf-8")
    r.g(w, "add", "src"); r.g(w, "commit", "-q", "-m", "code")
    r.run([r.bash, ".uak/bin/uak", "map"], cwd=w, env={"UAK_AGENT": "agent-1"})
    body = section("HACK-007", "src/api.py").replace("- **Verify:**", "- **Next step:** change coord_next to skip released tasks\n- **Verify:**")
    path = w / "plan-hint.md"
    path.write_text("# Wave\n\n" + body, encoding="utf-8")
    out = hack(f, 0, "plan", path, UAK_HUMAN="joahan", allowed=None)
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "OK plan" in out.stdout, "it publishes: rc %d %s" % (out.returncode, text[-500:]))
    expect("LINT HINT: HACK-007 mentions coord_next (src/coord.py), outside its Paths" in text, "it prints the hint: " + text[-500:])
    return "hint printed, published"


TESTS = [available_task_amend_overlap_warns_and_publishes, one_file_amend_uses_the_new_paths_of_the_others,
         claimed_task_amend_overlap_is_still_refused, plan_prints_hints_but_publishes]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-plan-amend-") as tmp:
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
    print("PLAN_AMEND_OVERLAP_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
