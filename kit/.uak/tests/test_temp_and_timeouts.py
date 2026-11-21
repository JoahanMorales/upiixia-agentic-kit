#!/usr/bin/env python3
"""UAK-115: temp files made with mktemp (not `$$` names under a shared temp dir) and removed on every exit path;
every git call of `uak dash` has a timeout and ends in one message (audit of v6.5.0, #8 #9). The scratch TMPDIR has a
space and an accent, as on the Windows runner. No network: dash runs against a patched subprocess.run."""
import argparse
import importlib.util
import io
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

PREFIXES = ("wt-add.", "uak-doctor-verify.", "uak-bb-export.")


def no_pid_named_temp_files(r):
    bad = []
    for f in sorted((r.package / ".uak" / "bin").rglob("*")):
        if not f.is_file() or f.suffix in (".pyc", ".png", ".svg"):
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.search(r"TMPDIR[^\"\s]*/[^\"\s]*\.\$\$", line) or re.search(r"/tmp/[^\"\s]*\.\$\$", line):
                bad.append("%s:%d" % (f.name, n))
    expect(not bad, "a temp file named with $$ under the temp dir: %s" % bad)
    for name in ("wt", "doctor", "bb"):
        text = (r.package / ".uak" / "bin" / name).read_text(encoding="utf-8")
        expect('mktemp "${TMPDIR:-/tmp}/' in text, name + " makes its temp file with mktemp \"${TMPDIR:-/tmp}/…XXXXXX\"")
        expect("trap " in text and "EXIT" in text, name + " removes it on every exit path (trap … EXIT)")
    return "mktemp + trap"


def temp_files_removed_on_error(r):
    f = r.fixture("tt-clean", count=1)
    clone = f.clones[0]
    tmp = r.scratch / "tmp dir ñé-tt"
    tmp.mkdir()
    env = {"TMPDIR": str(tmp), "UAK_AGENT": "agent-1"}
    bad = r.run([r.bash, ".uak/bin/bb", "export", str(r.scratch / "no such dir" / "out.md")], cwd=clone, env=env, allowed=None)
    expect(bad.returncode is not None, "bb export ran")
    r.run([r.bash, ".uak/bin/doctor"], cwd=clone, env=env, allowed=None)
    r.run([r.bash, ".uak/bin/wt", "new", "HACK-001", "--agent", "agent-1"], cwd=clone, env=env, allowed=None)
    r.run([r.bash, ".uak/bin/wt", "new", "HACK-001", "--agent", "agent-1"], cwd=clone, env=env, allowed=None)  # fails: held
    left = [p.name for p in tmp.iterdir() if p.name.startswith(PREFIXES)]
    expect(not left, "temp files left in TMPDIR: %s" % left)
    ok = r.run([r.bash, ".uak/bin/bb", "export", str(r.scratch / "tt-out.md")], cwd=clone, env=env)
    expect((r.scratch / "tt-out.md").is_file() and "BB: wrote" in ok.stdout, "bb export still writes: " + ok.stdout + ok.stderr)
    left = [p.name for p in tmp.iterdir() if p.name.startswith(PREFIXES)]
    expect(not left, "temp files left after a good export: %s" % left)
    return "TMPDIR clean"


def dash_times_out_on_a_dead_remote(r):
    spec = importlib.util.spec_from_file_location("uak_dash_under_test", str(r.package / ".uak" / "bin" / "lib" / "dash.py"))
    dash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dash)
    seen = []

    def fake_run(cmd, *a, **k):
        seen.append((list(cmd), k.get("timeout")))
        if cmd[1] == "rev-parse":
            return subprocess.CompletedProcess(cmd, 0, b"/tmp\n", b"")
        raise subprocess.TimeoutExpired(cmd, k.get("timeout"))

    real = dash.subprocess.run
    dash.subprocess.run = fake_run
    try:
        err = io.StringIO()
        old = sys.argv
        sys.argv = ["dash", "--out", str(r.scratch / "tt-dash")]
        try:
            with redirect_stderr(err):
                code = dash.run()
        finally:
            sys.argv = old
        text = err.getvalue()
        expect(code == 1, "exit 1 on a timeout: %r" % code)
        expect(text.count("\n") == 1 and text.startswith("DASH_ERROR:") and "timed out after 30 s" in text, "one line: %r" % text)
        expect(seen and all(t == 30 for _, t in seen), "every git call has the 30 s timeout: %s" % seen)
        try:
            dash.run_git("ls-remote", "origin", cwd=None)
            expect(False, "run_git should raise on a timeout")
        except RuntimeError as exc:
            expect("timed out" in str(exc) and "\n" not in str(exc), "run_git message: %s" % exc)
    finally:
        dash.subprocess.run = real
    return "30 s, one line"


TESTS = [no_pid_named_temp_files, temp_files_removed_on_error, dash_times_out_on_a_dead_remote]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="uak-temp-timeouts-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ != args.case:
                continue
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("TEMP_AND_TIMEOUTS_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
