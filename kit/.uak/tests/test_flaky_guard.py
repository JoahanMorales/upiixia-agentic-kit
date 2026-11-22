#!/usr/bin/env python3
"""UAK-138: three tests that failed and passed on a rerun without a defect behind them, and what keeps them honest.

  picker_reads_the_body_before_403   the design picker reads (a bounded) request body before any early answer
  mcp_server_exits_when_stdin_closes the MCP server leaves within 2 s of its input closing; a teardown that has to kill it fails
  lease_test_uses_the_injected_clock gate_and_lease passes while the machine's own clock reads the far future and 1970
  engine_renewer_never_runs_the_owners_cleanup  a lease renewer killed right after the fork removes nothing (60 runs)
  (twenty_runs_under_load, 20 runs of each of the three beside a CPU hog, lives in test_flaky_guard_race.py since UAK-150:
  on Windows it takes about nine tenths of the time of the whole file, so it is the half of its own shard.)

Why (CI of v6.5.0 to v6.7.0): these three failed and passed on a rerun on at least five pushes, and "every run green"
meant rerunning jobs by hand. Standard library only. Run: python3 kit/.uak/tests/test_flaky_guard.py [--case NAME]."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hack import resolve_binary  # noqa: E402

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
RACE_RUNS = 60  # without the engine fix about 4 in 10 of them remove the parent's temp dir


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


def lease_once(epoch="4102444800", spy=False):
    """gate_and_lease in a child process whose `date +%s` says `epoch`: a deadline read from the machine's clock
    instead of the engine's injected one would expire or never expire. With `spy`, every process the test starts must
    carry UAK_NOW."""
    with tempfile.TemporaryDirectory(prefix="uak-lease-") as tmp:
        shim = Path(tmp) / "shim"
        shim.mkdir()
        (shim / "date").write_text(FAKE_DATE, encoding="utf-8", newline="\n")
        os.chmod(str(shim / "date"), 0o755)
        env = dict(os.environ, FAKE_EPOCH=epoch, UAK_FLAKY_SHIM=str(shim), UAK_FLAKY_WORK=str(Path(tmp) / "work"))
        cmd = [sys.executable, str(Path(__file__).resolve()), "--job", "lease"] + (["--spy"] if spy else [])
        rc, out = sh(cmd, env=env)
        expect(rc == 0 and "LEASE_JOB_PASS" in out, "gate_and_lease with the clock at %s: %s" % (epoch, out))


def job_lease(spy):
    sys.path.insert(0, str(HERE))
    import test_review_merge as trm
    from test_hack import Runner, resolve_binary
    calls = []

    class Spy(Runner):
        def run(self, command, cwd=None, env=None, allowed=(0,), timeout=240):
            effective = dict(self.env, **(env or {}))
            calls.append((list(map(str, command))[:4], effective.get("UAK_NOW")))
            return super().run(command, cwd=cwd, env=env, allowed=allowed, timeout=timeout)

    work = Path(os.environ["UAK_FLAKY_WORK"])
    work.mkdir(parents=True)
    r = (Spy if spy else Runner)(KIT.resolve(), work.resolve(), resolve_binary("bash"), resolve_binary("git"))
    r.env["PATH"] = os.environ["UAK_FLAKY_SHIM"] + os.pathsep + r.env.get("PATH", os.environ.get("PATH", ""))
    r.env["FAKE_EPOCH"] = os.environ["FAKE_EPOCH"]
    trm.gate_and_lease(r)
    if spy:
        loose = [c for c, now in calls if not now]
        expect(calls and not loose, "%d of %d processes of gate_and_lease would read the machine's clock (no UAK_NOW), e.g. %s"
               % (len(loose), len(calls), loose[:2]))
    print("LEASE_JOB_PASS")


HARNESS = r'''# $1 the package, $2 the temp dir standing for the merge's $TXROOT, $3 a log. The merge's own traps (the lines
# of merge_run, checked by the test), the real rm_exit_cleanup, and a lease renewer that is killed in the window before
# it sets any trap of its own: the parent kills it right after the fork, as `kill "$RM_RENEWER"` does when the merge
# fails at once. Whether the kill lands before the subshell resets its traps is a race: the test repeats it.
set -u
. "$1/.uak/bin/lib/review-merge.sh"
TXROOT=$2; LOG=$3; RM_HELD=yes RM_FINISHED=no
cleanup() { echo "cleanup $$" >> "$LOG"; rm -rf "$TXROOT"; }
rm_coord_update() { echo "coord-update $1" >> "$LOG"; }
trap 'rm_exit_cleanup $?' EXIT
trap 'exit 130' INT; trap 'exit 143' TERM
( sleep 5 ) </dev/null >/dev/null 2>&1 &
RM_RENEWER=$!
kill -TERM "$RM_RENEWER" 2>/dev/null
wait "$RM_RENEWER" 2>/dev/null
if [ -d "$TXROOT" ]; then echo ALIVE; else echo REMOVED; fi
if [ -s "$LOG" ]; then echo "LOG $(tr '\n' ';' < "$LOG")"; fi
trap - EXIT; rm -rf "$TXROOT"
'''


def engine_renewer_never_runs_the_owners_cleanup():
    """The lease renewer is a subshell forked while the merge's EXIT and TERM traps are set. Killed before its own first
    `trap` line (a merge that fails at once, as Autonomy revoked and a freeze do), it ran the inherited handlers, and
    rm_exit_cleanup released the lock, queued the task for a human and removed the PARENT's temp dir: the merge then
    said "Cannot create transaction" and exited 1 where the gate says 3 (gate_and_lease failed in about 1 run in 10
    beside CPU hogs). The cleanup now runs only in the process that installed the traps."""
    src = (KIT / ".uak/bin/lib/review-merge.sh").read_text(encoding="utf-8")
    expect("  trap 'rm_exit_cleanup $?' EXIT\n  trap 'exit 130' INT; trap 'exit 143' TERM\n" in src, "merge_run's trap lines are not the ones this harness copies")
    with tempfile.TemporaryDirectory(prefix="uak-renewer-") as tmp:
        script = Path(tmp) / "harness.sh"
        script.write_text(HARNESS, encoding="utf-8", newline="\n")
        bash = resolve_binary("bash")
        for i in range(RACE_RUNS):
            work, log = Path(tmp) / ("tx%d" % i), Path(tmp) / ("log%d" % i)
            work.mkdir()
            rc, out = sh([bash, str(script), str(KIT), str(work), str(log)])
            expect(rc == 0 and "ALIVE" in out and "LOG" not in out, "run %d of %d: the killed renewer ran the merge's cleanup: %s" % (i + 1, RACE_RUNS, out))
    return "a renewer killed right after the fork removes nothing, %d of %d (bash %s)" % (RACE_RUNS, RACE_RUNS, sh([resolve_binary("bash"), "-c", "echo $BASH_VERSION"])[1].strip())


def picker_reads_the_body_before_403():
    picker_once()
    return "403, 404, 415 and 413 wait for the body"


def mcp_server_exits_when_stdin_closes():
    if not MCP_TEST.is_file():
        return "skipped: tests/test_mcp_tools.py is not in this checkout (an installed kit)"
    mcp_once()
    return "left within 2 s of stdin closing"


def lease_test_uses_the_injected_clock():
    # spy: every process of the test carries UAK_NOW, so none can read the clock. Without gate_and_lease's own default
    # clock (its git calls and any call that forgot `now=`) this fails: main's test_review_merge.py before UAK-138.
    lease_once("4102444800", spy=True)  # the year 2100: a real-clock lease would be long expired
    lease_once("1", spy=True)  # 1970: a real-clock deadline would never come
    return "gate_and_lease passes at clock 2100 and 1970 with UAK_NOW on every process"


TESTS = [picker_reads_the_body_before_403, mcp_server_exits_when_stdin_closes, engine_renewer_never_runs_the_owners_cleanup, lease_test_uses_the_injected_clock]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--job")
    parser.add_argument("--spy", action="store_true")
    parser.add_argument("--package")  # smoke passes it to every test; this one reads its own tree
    args = parser.parse_args()
    if args.job == "lease":
        job_lease(args.spy)
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
