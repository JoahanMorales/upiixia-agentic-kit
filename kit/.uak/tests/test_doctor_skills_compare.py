#!/usr/bin/env python3
"""UAK-046: doctor's stale check of .agents/skills against .claude/skills used `diff --strip-trailing-cr`, a GNU
option BSD diff lacks before macOS 13: on an older Mac every doctor run called the skills stale (v6.1.0 review of
UAK-041). The check now uses POSIX tools only; CRLF-only differences are not stale. Real install.sh and real Git."""
import argparse
import stat
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_skills_windows_clone import doctor, installer, repo, skill_lines


def fresh(r, name):
    d = repo(r, name)
    installer(r)("--mode", "sprint", d)
    return d


def stale_lines(out):
    return [l for l in skill_lines(out) if l.startswith("FAIL") and "stale" in l]


def crlf_only_difference_is_not_stale(r):
    d = fresh(r, "cmp-crlf")
    f = d / ".agents/skills/test-first/SKILL.md"
    f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    out = doctor(r, d)
    expect(not stale_lines(out), "a CRLF-only copy is not stale: " + out.stdout[-600:])
    return "not stale"


def real_difference_is_stale(r):
    d = fresh(r, "cmp-real")
    (d / ".agents/skills/test-first/SKILL.md").write_text("an older version\r\n", encoding="utf-8")
    expect(stale_lines(doctor(r, d)), "an edited copy is stale")
    d2 = fresh(r, "cmp-missing")
    subprocess_rm = d2 / ".agents/skills/test-first/SKILL.md"
    subprocess_rm.unlink()
    expect(stale_lines(doctor(r, d2)), "a missing file is stale")
    d3 = fresh(r, "cmp-extra")
    (d3 / ".agents/skills/test-first/EXTRA.md").write_text("extra\n", encoding="utf-8")
    expect(stale_lines(doctor(r, d3)), "an extra file in a kit skill is stale")
    return "stale"


def works_without_diff_strip_flag(r):
    """A diff that refuses --strip-trailing-cr, as BSD diff on macOS < 13 does: a fresh install is still not stale."""
    d = fresh(r, "cmp-bsd")
    shim = r.scratch / "cmp-bsd-bin"
    shim.mkdir()
    real = r.run(["sh", "-c", "command -v diff"]).stdout.strip()
    tool = shim / "diff"
    tool.write_text('#!/bin/sh\nfor a in "$@"; do case "$a" in --strip-trailing-cr) echo "diff: unrecognized option $a" >&2; exit 2;; esac; done\nexec %s "$@"\n' % real, encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    path = str(shim) + ":" + r.env["PATH"]
    out = r.run([r.bash, ".uak/bin/doctor"], cwd=d, env={"PATH": path}, allowed=None)
    expect(not stale_lines(out), "a fresh install is not stale on a diff without the flag: " + out.stdout[-600:])
    return "not stale"


TESTS = [crlf_only_difference_is_not_stale, real_difference_is_stale, works_without_diff_strip_flag]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-doctor-cmp-") as tmp:
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
    print("DOCTOR_SKILLS_COMPARE_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
