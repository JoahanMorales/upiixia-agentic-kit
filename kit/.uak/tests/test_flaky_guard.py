#!/usr/bin/env python3
"""UAK-138: three tests that failed and passed on a rerun without a defect behind them, and what keeps them honest.

  picker_reads_the_body_before_403   the design picker reads (a bounded) request body before any early answer
  mcp_server_exits_when_stdin_closes the MCP server leaves within 2 s of its input closing; a teardown that has to kill it fails
  lease_test_uses_the_injected_clock gate_and_lease passes while the machine's own clock reads the far future and 1970
  twenty_runs_under_load             each of the three passes 20 times in a row beside a CPU hog (about 4 min; skipped
                                     only when UAK_SMOKE_FAST=1)

Why (CI of v6.5.0 to v6.7.0): these three failed and passed on a rerun on at least five pushes, and "every run green"
meant rerunning jobs by hand. Standard library only. Run: python3 kit/.uak/tests/test_flaky_guard.py [--case NAME]."""
import argparse
import concurrent.futures
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1]
REPO = KIT.parent
MCP_TEST = REPO / "tests" / "test_mcp_tools.py"
FAKE_DATE = """#!/bin/bash
# The machine's clock, wrong on purpose: only `date +%s` is changed.
for a in "$@"; do case "$a" in +%s) echo "$FAKE_EPOCH"; exit 0;; esac; done
exec /bin/date "$@"
"""
RUNS = 20


class Failure(Exception):
    pass


def expect(cond, msg):
    if not cond:
        raise Failure(msg)


def sh(cmd, env=None, timeout=600):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout, env=env, cwd=str(REPO))
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def picker_once():
    rc, out = sh([sys.executable, str(HERE / "test_design_pick.py"), "--package", str(KIT), "--case", "picker_reads_the_body_before_403"])
    expect(rc == 0 and "PASS picker_reads_the_body_before_403" in out, "picker: " + out)


def mcp_once():
    rc, out = sh([sys.executable, str(MCP_TEST), "McpProcess.test_server_exits_when_stdin_closes"])
    expect(rc == 0, "mcp: " + out)


def lease_once(epoch="4102444800"):
    """gate_and_lease in a child process whose `date +%s` says `epoch`: a deadline read from the machine's clock
    instead of the engine's injected one would expire or never expire, and the test would fail."""
    with tempfile.TemporaryDirectory(prefix="uak-lease-") as tmp:
        shim = Path(tmp) / "shim"
        shim.mkdir()
        (shim / "date").write_text(FAKE_DATE, encoding="utf-8", newline="\n")
        os.chmod(str(shim / "date"), 0o755)
        env = dict(os.environ, FAKE_EPOCH=epoch, UAK_FLAKY_SHIM=str(shim), UAK_FLAKY_WORK=str(Path(tmp) / "work"))
        rc, out = sh([sys.executable, str(Path(__file__).resolve()), "--job", "lease"], env=env)
        expect(rc == 0 and "LEASE_JOB_PASS" in out, "gate_and_lease with the clock at %s: %s" % (epoch, out))


def job_lease():
    sys.path.insert(0, str(HERE))
    import test_review_merge as trm
    from test_hack import Runner, resolve_binary
    work = Path(os.environ["UAK_FLAKY_WORK"])
    work.mkdir(parents=True)
    r = Runner(KIT.resolve(), work.resolve(), resolve_binary("bash"), resolve_binary("git"))
    r.env["PATH"] = os.environ["UAK_FLAKY_SHIM"] + os.pathsep + r.env.get("PATH", os.environ.get("PATH", ""))
    r.env["FAKE_EPOCH"] = os.environ["FAKE_EPOCH"]
    trm.gate_and_lease(r)
    print("LEASE_JOB_PASS")


def picker_reads_the_body_before_403():
    picker_once()
    return "403, 404, 415 and 413 wait for the body"


def mcp_server_exits_when_stdin_closes():
    if not MCP_TEST.is_file():
        return "skipped: tests/test_mcp_tools.py is not in this checkout (an installed kit)"
    mcp_once()
    return "left within 2 s of stdin closing"


def lease_test_uses_the_injected_clock():
    lease_once("4102444800")  # the year 2100: a real-clock lease would be long expired
    lease_once("1")  # 1970: a real-clock deadline would never come
    return "gate_and_lease passes at clock 2100 and 1970"


def twenty_runs_under_load():
    if os.environ.get("UAK_SMOKE_FAST") == "1":
        return "skipped: UAK_SMOKE_FAST=1"
    jobs = [("lease", lease_once)] * RUNS + [("mcp", mcp_once)] * RUNS + [("picker", picker_once)] * RUNS
    if not MCP_TEST.is_file():
        jobs = [j for j in jobs if j[0] != "mcp"]
    hogs = [subprocess.Popen([sys.executable, "-c", "while True: pass"]) for _ in range(max(1, (os.cpu_count() or 2) // 2))]
    started, failures = time.time(), []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fn): (i, name) for i, (name, fn) in enumerate(jobs)}
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except Exception as exc:  # noqa: BLE001
                    failures.append("%s #%d: %s" % (futures[f][1], futures[f][0], str(exc)[:400]))
    finally:
        for h in hogs:
            h.kill()
            h.wait()
    expect(not failures, "%d of %d runs failed under load: %s" % (len(failures), len(jobs), " | ".join(failures[:3])))
    return "%d runs green beside %d CPU hogs in %d s" % (len(jobs), len(hogs), time.time() - started)


TESTS = [picker_reads_the_body_before_403, mcp_server_exits_when_stdin_closes, lease_test_uses_the_injected_clock, twenty_runs_under_load]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--job")
    parser.add_argument("--package")  # smoke passes it to every test; this one reads its own tree
    args = parser.parse_args()
    if args.job == "lease":
        job_lease()
        return 0
    failed = 0
    for t in [t for t in TESTS if not args.case or t.__name__ == args.case]:
        try:
            print("PASS %s (%s)" % (t.__name__, t()), flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]), flush=True)
    print("FLAKY_GUARD_RESULT %s" % ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
