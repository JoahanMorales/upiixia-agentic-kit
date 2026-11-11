#!/usr/bin/env python3
"""UAK-051: 4 of 16 tasks of the v6.1.0 session needed a Paths amend because the function they changed lived in another
file than the Paths said. `uak lint` now warns when a task's `Next step:` or Acceptance names a function or a file the
code map places outside its Paths. No map yet: silent. Real Git, a local bare remote."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def project(r, name, next_step, paths="src/api.py", acceptance="salida comprobable"):
    """Two code files: src/api.py (handler) and src/coord.py (coord_next, claimNext); HACK-001 lists `paths`."""
    f = r.fixture(name, paths={"HACK-001": paths}, count=1)
    c = f.clones[0]
    (c / "src").mkdir(exist_ok=True)
    (c / "src/api.py").write_text("def handler():\n    return 1\n", encoding="utf-8")
    (c / "src/coord.py").write_text("def coord_next():\n    return 2\n\n\ndef claimNext():\n    return 3\n", encoding="utf-8")
    tasks = c / ".uak/TASKS.md"
    text = tasks.read_text(encoding="utf-8").replace("- **Acceptance:** salida comprobable", "- **Acceptance:** " + acceptance)
    text = text.replace("- **Verify:**", "- **Next step:** " + next_step + "\n- **Verify:**")
    tasks.write_text(text, encoding="utf-8")
    return f, c


def lint(r, c):
    out = r.run([r.bash, ".uak/bin/uak", "lint"], cwd=c, env={"UAK_AGENT": "agent-1", "UAK_REMOTE": "origin"}, allowed=None)
    return out, [l for l in (out.stdout + out.stderr).splitlines() if "outside its Paths" in l]


def build_map(r, c):
    r.run([r.bash, ".uak/bin/uak", "map"], cwd=c, env={"UAK_AGENT": "agent-1"})


def next_step_function_outside_paths_warns(r):
    f, c = project(r, "lh-warn", "change coord_next so it skips released tasks", acceptance="claimNext() returns the id")
    out, none = lint(r, c)
    expect(not none, "no map yet: silent: " + (out.stdout + out.stderr)[-500:])
    build_map(r, c)
    out, lines = lint(r, c)
    expect(any(l.startswith("LINT WARNING: HACK-001 mentions coord_next (src/coord.py), outside its Paths") for l in lines),
           "the Next step function is named with its file: " + (out.stdout + out.stderr)[-800:])
    expect(any("claimNext (src/coord.py)" in l for l in lines), "and so is the Acceptance one: " + str(lines))
    expect("LINT_FAILED" not in out.stdout, "a warning does not fail lint: " + out.stdout[-300:])
    out2, lines2 = lint(r, c)
    expect(lines2 == lines, "the same answer twice")
    return "warned"


def mention_inside_paths_is_silent(r):
    f, c = project(r, "lh-quiet", "change coord_next in src/coord.py", paths="src/api.py, src/coord.py")
    build_map(r, c)
    out, lines = lint(r, c)
    expect(not lines, "a function and a file inside the Paths: silent: " + str(lines))
    f2, c2 = project(r, "lh-dir", "change coord_next and handler", paths="src/")
    build_map(r, c2)
    out2, lines2 = lint(r, c2)
    expect(not lines2, "a directory in Paths covers its files: " + str(lines2))
    f3, c3 = project(r, "lh-words", "update the claim and handler words, nothing about code", paths="src/api.py")
    build_map(r, c3)
    out3, lines3 = lint(r, c3)
    expect(not lines3, "plain words that happen to be symbol names are not mentions: " + str(lines3))
    return "silent"


TESTS = [next_step_function_outside_paths_warns, mention_inside_paths_is_silent]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-lint-hint-") as tmp:
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
    print("LINT_PATHS_HINT_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
