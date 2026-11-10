#!/usr/bin/env python3
"""UAK-029: `q` given the task's Verify as ONE quoted string ran it as a command name (exit 127, DevDay hackathon).
One argument with a space or shell operator now runs with `bash -c`; several arguments keep running as "$@".
Real git repo in a temp dir; q is run from the package under test."""
import argparse
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def repo(r, name):
    d = r.scratch / name
    d.mkdir(parents=True)
    r.g(d, "init", "-q")
    return d


def q(r, d, *args, env=None):
    return r.run([r.bash, str(r.package / ".uak" / "bin" / "q"), *args], cwd=d, env=env, allowed=None)


def a_quoted_compound_verify_runs(r):
    d = repo(r, "qs-compound")
    out = q(r, d, "echo one && echo two | tr a-z A-Z > made.txt && test -s made.txt")
    expect(out.returncode == 0 and out.stdout.startswith("OK exit=0"), "compound string: expected exit 0 and OK, got rc %d" % out.returncode)
    expect((d / "made.txt").read_text().strip() == "TWO", "the redirection and pipe ran inside the string")
    return "bash -c"


def a_quoted_failing_verify_keeps_its_exit_code(r):
    d = repo(r, "qs-fail")
    out = q(r, d, "echo boom && exit 7")
    expect(out.returncode == 7, "exit code is the command's: expected 7, got %d" % out.returncode)
    expect("FAIL exit=7" in out.stdout and "boom" in out.stdout and "log " in out.stdout, "expected a FAIL exit=7 line with the output tail and the log path")
    again = q(r, d, "echo boom && exit 7")
    expect("LOOP:" in again.stdout, "expected the LOOP signature on the second identical failure")
    return "exit 7 + LOOP"


def argv_form_is_unchanged(r):
    d = repo(r, "qs-argv")
    out = q(r, d, "printf", "%s|", "a b", "c")
    expect(out.returncode == 0 and "a b|c|" in out.stdout, "argv kept as is: " + out.stdout + out.stderr)
    out = q(r, d, "sh", "-c", "exit 3")
    expect(out.returncode == 3, "argv exit code: %d" % out.returncode)
    one = q(r, d, "true")
    expect(one.returncode == 0, "single word is still a command: " + one.stdout)
    logs = list((d / ".git" / "uak-out").glob("q-*.log"))
    expect(logs, "log files stay under <git dir>/uak-out")
    return "argv ok"


TESTS = [a_quoted_compound_verify_runs, a_quoted_failing_verify_keeps_its_exit_code, argv_form_is_unchanged]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="uak-q-string-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ != args.case:
                continue
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("Q_STRING_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
