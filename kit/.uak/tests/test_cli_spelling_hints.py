#!/usr/bin/env python3
"""UAK-091: the CLI answers a wrong spelling with the right one.
Why (harvest 2026-11): review with a bare SHA x4, `--approve` x2, merge with a name x2, unknown commands
decisions/owners/agents/kit-hashes, `done --pr <branch>` x2, `log --task`. Only the text gains the hint: the first words
of every message, the exit codes and UAK_CODE stay as they were. Real Git, a local bare remote."""
import argparse
import json
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

SHA = "3f2a9c1d"


def call(f, *args, **env):
    return f.r.run([f.r.bash, ".uak/bin/uak", *args], cwd=f.worktrees[0], allowed=None,
                   env={"UAK_AGENT": "agent-1", "UAK_NOW": "1000000", "UAK_REMOTE": "origin", "UAK_HUMAN": "", **env})


def fail(f, *args):
    out = call(f, *args)
    expect(out.returncode == 2, "exit code 2 (as before) for %s, got %s: %s" % (args, out.returncode, out.stdout + out.stderr))
    return out.stderr


def unknown_command_suggests_nearest(r):
    f = r.fixture("hint-unknown", count=1)
    err = fail(f, "decisions")
    expect(err.startswith("ERROR: Unknown command: decisions (uak help lists them)"), "the old text stays first: " + err)
    expect("Did you mean: decision" in err, "nearest command named: " + err)
    expect("OWNERS.md" in fail(f, "owners"), "owners points at the file")
    expect("kit_hashes.py" in fail(f, "kit-hashes"), "kit-hashes points at the script")
    expect("uak status" in fail(f, "agents"), "agents points at status")
    expect("Did you mean" not in fail(f, "qqqqqqqq"), "no suggestion when nothing is near")
    code = call(f, "--json", "decisions")
    expect('"code":"unknown-command"' in code.stdout.replace(" ", "") or "unknown-command" in code.stdout + code.stderr,
           "UAK_CODE unchanged: " + code.stdout + code.stderr)
    return "decision"


def review_approve_flag_names_verdict(r):
    f = r.fixture("hint-approve", count=1)
    err = fail(f, "review", "HACK-001", "--approve")
    expect("Unexpected argument: --approve" in err, "old text first: " + err)
    expect("review HACK-001 --sha SHA --verdict approve" in err, "the exact line: " + err)
    expect("--verdict reject" in fail(f, "review", "HACK-001", "--reject"), "reject too")
    return "approve/reject"


def bare_sha_names_the_flag(r):
    f = r.fixture("hint-sha", count=1)
    err = fail(f, "review", "HACK-001", SHA)
    expect("Unexpected argument: " + SHA in err and "--sha " + SHA + " --verdict" in err, "review: " + err)
    err = fail(f, "status", "HACK-001", SHA)
    expect("Unexpected argument: " + SHA in err and "review HACK-001 --sha " + SHA in err, "status: " + err)
    err = fail(f, "merge", "HACK-001", "bob-1")
    expect("Unexpected argument: bob-1" in err and "merge HACK-001" in err and "--reviewer bob-1" in err, "merge: " + err)
    err = call(f, "log", "--task", "HACK-001", "text")
    expect(err.returncode == 2 and "Invalid ID '--task': log takes the task ID first." in err.stderr
           and "uak log HACK-001" in err.stderr, "log --task: " + err.stderr)
    return "sha, merge, log"


def done_branch_is_not_a_url(r):
    f = r.fixture("hint-branch", count=1)
    err = fail(f, "done", "HACK-001", "--pr", "feat/hack-001", "--evidence", "x")
    expect(err.startswith("ERROR: done needs --pr HTTPS URL"), "old words first: " + err)
    expect("branch name, not a URL" in err and "wt pr" in err, "the hint: " + err)
    err = fail(f, "done", "HACK-001", "--pr", "feat/hack-001")
    expect("and --evidence" in err, "still names the missing evidence: " + err)
    return "branch"


TESTS = [unknown_command_suggests_nearest, review_approve_flag_names_verdict, bare_sha_names_the_flag, done_branch_is_not_a_url]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak hínts-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("CLI_SPELLING_HINTS_RESULT %s" % ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
