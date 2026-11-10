#!/usr/bin/env python3
"""UAK-032: a fresh laptop has no git identity, and `wt new ID` answered "--human: letters, digits, dot, dash or
underscore only", about a flag the person never passed (v6.0 review). It now says what to run, and doctor FAILs on a
missing user.name or user.email with the same command. Real Git, a local bare remote."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

FIX = 'git config --global user.name "Your Name" && git config --global user.email you@example.com'


def without_identity(r, f):
    """The main clone with no local identity, and HOME and the global config pointing at nothing."""
    clone = f.clones[0]
    r.run([r.git, "config", "--unset", "user.name"], cwd=clone, allowed=None)
    r.run([r.git, "config", "--unset", "user.email"], cwd=clone, allowed=None)
    home = r.scratch / "no-home"
    home.mkdir(exist_ok=True)
    empty = home / "empty-gitconfig"
    empty.write_text("", encoding="utf-8")
    env = {"HOME": str(home), "USERPROFILE": str(home), "GIT_CONFIG_GLOBAL": str(empty), "UAK_HUMAN": "", "UAK_AGENT": "",
           "GIT_AUTHOR_NAME": "", "GIT_AUTHOR_EMAIL": ""}
    return clone, env


def wt_new_without_git_identity_names_the_fix(r):
    f = r.fixture("gi-wt", count=1)
    clone, env = without_identity(r, f)
    out = r.run([r.bash, ".uak/bin/wt", "new", "HACK-001"], cwd=clone, env=env, allowed=None)
    text = out.stdout + out.stderr
    expect(out.returncode == 2, "exits 2: rc %d %s" % (out.returncode, text[-400:]))
    expect(FIX in text, "says the exact command: " + text[-500:])
    expect("--human" not in text, "no word about a flag nobody passed: " + text[-500:])
    # A person who passes --human is not asked for a git identity by this check.
    named = r.run([r.bash, ".uak/bin/wt", "new", "HACK-001", "--human", "ana"], cwd=clone, env=env, allowed=None)
    expect("git has no identity" not in named.stdout + named.stderr, "--human ana is a name already: " + (named.stdout + named.stderr)[-300:])
    return "message names the fix"


def doctor_flags_missing_git_identity(r):
    f = r.fixture("gi-doctor", count=1)
    clone, env = without_identity(r, f)
    out = r.run([r.bash, ".uak/bin/doctor"], cwd=clone, env=env, allowed=None)
    lines = [l for l in out.stdout.splitlines() if l.startswith("FAIL") and "user.name" in l]
    expect(lines and FIX in lines[0], "a FAIL line with the command: " + out.stdout[-800:])
    expect(out.returncode != 0, "doctor fails: rc %d" % out.returncode)
    r.run([r.git, "config", "user.name", "Ana"], cwd=clone)
    r.run([r.git, "config", "user.email", "ana@example.invalid"], cwd=clone)
    ok = r.run([r.bash, ".uak/bin/doctor"], cwd=clone, env=env, allowed=None)
    expect(not [l for l in ok.stdout.splitlines() if l.startswith("FAIL") and "user.name" in l], "no identity FAIL once it is set: " + ok.stdout[-600:])
    return "doctor fails then passes"


TESTS = [wt_new_without_git_identity_names_the_fix, doctor_flags_missing_git_identity]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-git-identity-") as tmp:
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
    print("GIT_IDENTITY_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
