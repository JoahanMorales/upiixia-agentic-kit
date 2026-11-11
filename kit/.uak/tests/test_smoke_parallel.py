#!/usr/bin/env python3
"""UAK-054: every `uak merge` of the kit ran the whole suite serially (over 10 minutes per task, v6.1.0 and v6.1.1).
`smoke --package-only --jobs N` (or `Smoke-Jobs: N` in PROJECT.md; `auto` = CPUs - 1, at most 4) runs the test files in N
shards at once, balanced by the same seconds the CI split uses (scripts/kit_lint.py), each shard with its own TMPDIR and
HOME. Any failing shard fails the run and its tail is printed. Default 1 = the serial loop. Real bash, probe test files."""
import argparse
import re
import shutil
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

PROBE = (
    "import os, sys\n"
    "n = os.path.basename(__file__)[:-3]\n"
    "print('PROBE_RAN ' + n)\n"
    "print('PROBE_ENV %s tmp=%s home=%s inherit=%s' % (n, os.environ.get('TMPDIR', ''), os.environ.get('HOME', ''),\n"
    "      'SET' if 'UAK_SMOKE_TESTS' in os.environ else 'UNSET'))\n"
)
FAILING = "import sys\nprint('PROBE_RAN %s')\nprint('PROBE_BOOM the failing marker')\nsys.exit(1)\n"
NAMES = ["test_a", "test_b", "test_c", "test_d", "test_e"]


def package(r, name, failing=None, project=None):
    pkg = Path(tempfile.mkdtemp(prefix=name + "-", dir=str(r.scratch)))
    shutil.copytree(r.package / ".uak" / "bin", pkg / ".uak" / "bin")
    (pkg / ".uak" / "tests").mkdir()
    for n in NAMES:
        body = FAILING % n if n == failing else PROBE
        (pkg / ".uak" / "tests" / (n + ".py")).write_text(body, encoding="utf-8")
    if project is not None:
        (pkg / ".uak" / "PROJECT.md").write_text(project, encoding="utf-8")
    return pkg


def smoke(r, pkg, *args, env=None):
    # A fixed TMPDIR: this file may itself run inside a shard of an outer parallel smoke, whose TMPDIR would leak in.
    e = {"UAK_SMOKE_TESTS": "", "UAK_SMOKE_GATE_NONE": "", "TMPDIR": str(r.scratch)}
    e.update(env or {})
    # The variables must not exist at all, as in a plain shell: drop the empty placeholders.
    return r.run([r.bash, ".uak/bin/smoke", "--package-only"] + list(args), cwd=pkg, env={k: v for k, v in e.items() if v}, allowed=None, timeout=300)


def ran(out):
    return re.findall(r"(?m)^PROBE_RAN (\S+)$", out.stdout)


def jobs_split_runs_every_file_once(r):
    pkg = package(r, "sp-split")
    out = smoke(r, pkg, "--jobs", "3")
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "PACKAGE_PASS" in out.stdout, "3 shards must pass: rc %d %s" % (out.returncode, text[-600:]))
    expect(sorted(ran(out)) == NAMES, "every file runs exactly once: %s" % ran(out))
    envs = re.findall(r"(?m)^PROBE_ENV (\S+) tmp=(\S*) home=(\S*) inherit=(\S+)$", out.stdout)
    expect(len(envs) == 5 and all(e[3] == "UNSET" for e in envs), "a test never inherits UAK_SMOKE_TESTS: %s" % envs)
    tmps = {e[1] for e in envs}
    expect(len(tmps) >= 2 and all(t and "shard" in t for t in tmps), "each shard has its own TMPDIR: %s" % tmps)
    expect(len({e[2] for e in envs}) == len(tmps) and all(e[2] for e in envs), "each shard has its own HOME: %s" % envs)
    # Also through PROJECT.md, and a list from UAK_SMOKE_TESTS is split too.
    out = smoke(r, pkg, "--jobs", "2", env={"UAK_SMOKE_TESTS": "test_a test_c test_e"})
    expect(out.returncode == 0 and sorted(ran(out)) == ["test_a", "test_c", "test_e"], "a CI shard split again: %s" % (out.stdout + out.stderr)[-500:])
    out = smoke(r, pkg, "--jobs", "auto")
    expect(out.returncode == 0 and sorted(ran(out)) == NAMES, "--jobs auto: %s" % (out.stdout + out.stderr)[-500:])
    bad = smoke(r, pkg, "--jobs", "zero")
    expect(bad.returncode == 2 and "--jobs" in bad.stderr and not ran(bad), "a bad --jobs is refused: %s" % bad.stderr[-300:])
    return "5 files once in 3 shards, PROJECT.md, auto"


def a_failing_shard_fails_the_run(r):
    pkg = package(r, "sp-fail", failing="test_c")
    out = smoke(r, pkg, "--jobs", "3")
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "PACKAGE_PASS" not in out.stdout, "a failing shard fails the run: rc %d %s" % (out.returncode, text[-500:]))
    expect("PROBE_BOOM the failing marker" in text, "the failing shard's tail is printed: " + text[-500:])
    expect(re.search(r"(?i)shard \d+ (of \d+ )?failed", text) is not None, "the message names the failing shard: " + text[-500:])
    expect(sorted(set(ran(out)) - {"test_c"}) == [n for n in NAMES if n != "test_c"], "the other shards still ran: %s" % ran(out))
    return "rc %d" % out.returncode


def default_is_serial(r):
    pkg = package(r, "sp-serial")
    for args in ((), ("--jobs", "1")):
        out = smoke(r, pkg, *args)
        expect(out.returncode == 0 and "PACKAGE_PASS" in out.stdout, "serial run passes: " + (out.stdout + out.stderr)[-500:])
        expect(ran(out) == NAMES, "serial runs in C order: %s" % ran(out))
        talk = [l for l in out.stdout.splitlines() if not l.startswith("PROBE_ENV") and "shard" in l.lower() and "UAK_SMOKE_TESTS" not in l]
        expect(not talk, "no shard talk in a serial run: %s" % talk)
        tmps = {m for m in re.findall(r"tmp=(\S*)", out.stdout)}
        expect(tmps == {str(r.scratch)}, "serial keeps the caller's TMPDIR %s: %s" % (r.scratch, tmps))
    out = smoke(r, package(r, "sp-serial-md", project="- **Smoke-Jobs:** 1\n"))
    expect(ran(out) == NAMES, "Smoke-Jobs: 1 is serial: %s" % ran(out))
    return "serial by default"


def smoke_jobs_read_from_uak_project_md(r):
    """Projects keep PROJECT.md at .uak/PROJECT.md (guard, pace, bb read it there); the root-level file is not read."""
    out = smoke(r, package(r, "sp-md", project="# P\n\n- **Smoke-Jobs:** 2\n"))
    expect(out.returncode == 0 and sorted(ran(out)) == NAMES and "Jobs: 2 shards" in out.stdout, "Smoke-Jobs: 2 in .uak/PROJECT.md: %s" % (out.stdout + out.stderr)[-500:])
    out = smoke(r, package(r, "sp-md-sel", project="- **Smoke-Jobs:** 2\n"), env={"UAK_SMOKE_TESTS": "test_a test_b"})
    expect("Jobs: 2 shards of 2" in out.stdout, "with a CI shard list too: " + out.stdout[-400:])
    pkg = package(r, "sp-md-root")
    (pkg / "PROJECT.md").write_text("- **Smoke-Jobs:** 2\n", encoding="utf-8")
    out = smoke(r, pkg)
    expect("Jobs:" not in out.stdout, "a root-level PROJECT.md is not the project file: " + out.stdout[-300:])
    return "read from .uak/PROJECT.md"


TESTS = [jobs_split_runs_every_file_once, a_failing_shard_fails_the_run, default_is_serial, smoke_jobs_read_from_uak_project_md]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-smoke-par-") as tmp:
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
    print("SMOKE_PARALLEL_RESULT %s failed=%d" % ("FAIL" if fails else "PASS", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
