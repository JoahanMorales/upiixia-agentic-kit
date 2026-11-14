#!/usr/bin/env python3
"""UAK-069: `uak next` run as a registered reviewer never offers implementation work. Test round 2026-11-13 (r3
P3-6): `UAK_AGENT=luis-r uak next` offered HACK-001 to claim to the registered reviewer identity. Real Git, a local bare
remote."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_reviewer_next import reviewer_env, three, to_review


def reviewer_is_not_offered_implementation(r):
    f = three(r, "nr-reviewer", "agent-3")
    out = r.run([r.bash, ".uak/bin/uak", "next"], cwd=f.clones[2], env=reviewer_env(UAK_NOW="1000020"))
    text = out.stdout
    expect("| AVAILABLE |" not in text and "wt new" not in text and "HACK-001" not in text,
           "a registered reviewer is not offered a task to claim: " + text[:600])
    expect("nothing to review" in text.lower() and "uak wait" in text, "it says there is nothing to review and how to wait: " + text[:600])
    # With work waiting for review, the review is still offered (UAK-038).
    to_review(r, f)
    out = r.run([r.bash, ".uak/bin/uak", "next"], cwd=f.clones[2], env=reviewer_env(UAK_NOW="1000020"))
    expect("/uak-review HACK-001" in out.stdout and "wt new" not in out.stdout, "the review is offered: " + out.stdout[:600])
    return "review only"


def implementer_output_is_unchanged(r):
    f = three(r, "nr-implementer", "agent-3")
    out = r.run([r.bash, ".uak/bin/uak", "next"], cwd=f.clones[1], env=reviewer_env(UAK_AGENT="agent-2", UAK_NOW="1000020"))
    text = out.stdout
    expect("HACK-001 | AVAILABLE |" in text and "Before editing: bash .uak/bin/wt new HACK-001 --agent agent-2" in text,
           "an identity that is not a reviewer is still offered the task: " + text[:600])
    expect("nothing to review" not in text.lower(), "no reviewer wording for an implementer: " + text[:600])
    return "unchanged"


TESTS = [reviewer_is_not_offered_implementation, implementer_output_is_unchanged]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-next-reviewer-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        results = []
        for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
            started = time.monotonic()
            try:
                note = test(runner)
                results.append((test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)))
            except Exception as exc:  # noqa: BLE001
                results.append((test.__name__, False, str(exc)[:2500]))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("NEXT_REVIEWER_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
