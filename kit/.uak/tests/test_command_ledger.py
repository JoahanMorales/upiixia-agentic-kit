#!/usr/bin/env python3
"""UAK-116: a ledger of every command: epoch, command, task, exit code, UAK_CODE, milliseconds, agent, harness.
Why (audit of v6.5.0, docs/audit-2026-11.md section 4): calls were names only, with no durations and no outcomes.
Every `uak` command appends one line to <git-common-dir>/uak-ledger.pending when it ends; `bb flush` publishes it
to claims as metrics/<day>-<machine>.tsv in the black box's transaction and empties it. Real Git, local bare remote."""
import argparse
import os
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

ENV = {"UAK_AGENT": "agent-1", "UAK_NOW": "1000000", "UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_HARNESS": "codex"}


def common_of(r, w):
    return Path(r.g(w, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())


def uak(f, *args, **env):
    e = dict(ENV)
    e.update(env)
    return f.r.run([f.r.bash, ".uak/bin/uak"] + list(args), cwd=f.worktrees[0], allowed=None, env=e)


def rows(common):
    p = common / "uak-ledger.pending"
    if not p.exists():
        return []
    return [ln.rstrip("\r").split("\t") for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def a_command_appends_one_ledger_line(r):
    f = r.fixture("ledger-one", count=1)
    common = common_of(r, f.worktrees[0])
    out = uak(f, "status")
    expect(out.returncode == 0, "status failed: " + out.stderr[-300:])
    got = rows(common)
    expect(len(got) == 1, "expected one ledger line, got %r" % got)
    row = got[0]
    expect(len(row) == 8, "expected 8 fields (epoch cmd task rc code ms agent harness), got %r" % row)
    expect(row[0].isdigit() and row[1] == "status" and row[3] == "0", "epoch/cmd/rc wrong: %r" % row)
    # The 3.2 path (forced by UAK_LEDGER_CLOCK=seconds; the real thing on macOS): the engine's NOW, whole seconds.
    uak(f, "status", UAK_LEDGER_CLOCK="seconds")
    row = rows(common)[-1]
    expect(row[0].isdigit() and row[5].isdigit() and int(row[5]) % 1000 == 0, "bash 3.2 path: epoch and whole-second ms expected: %r" % row)
    f.r.run([f.r.bash, "-c", ": > uak-ledger.pending"], cwd=common, allowed=None, env={})
    uak(f, "status")
    expect(row[5].isdigit(), "milliseconds must be a number: %r" % row)
    expect(row[6] == "agent-1" and row[7] == "codex", "agent/harness wrong: %r" % row)
    uak(f, "status", "--task", "NOPE-999", UAK_CALLER="hook")
    got = rows(common)
    expect(len(got) == 2 and got[1][1] == "hook-status", "UAK_CALLER prefix missing: %r" % got)
    expect(got[1][2] == "NOPE-999" or got[1][2] == "-", "task field: %r" % got[1])
    return "one line per command"


def a_failed_command_records_its_code(r):
    f = r.fixture("ledger-fail", count=1)
    common = common_of(r, f.worktrees[0])
    out = uak(f, "frobnicate")
    expect(out.returncode == 2, "unknown command should exit 2, got %d" % out.returncode)
    got = rows(common)
    expect(len(got) == 1 and got[0][1] == "frobnicate" and got[0][3] == "2", "failed command row: %r" % got)
    expect(got[0][4] == "unknown-command", "UAK_CODE missing: %r" % got[0])
    # An exec'd script cannot report its end (nothing is left to catch it): it is recorded at launch, exit unknown.
    uak(f, "doctor", "--help")
    return "rc and code recorded"


def flush_publishes_and_empties(r):
    f = r.fixture("ledger-flush", count=1)
    w = f.worktrees[0]
    common = common_of(r, w)
    uak(f, "status")
    uak(f, "frobnicate")
    expect(len(rows(common)) == 2, "two lines expected before the flush")
    out = r.run([r.bash, ".uak/bin/bb", "flush"], cwd=w, allowed=None, env=ENV)
    expect(out.returncode == 0, "flush failed: " + out.stderr[-300:])
    tree = r.g(f.remote, "ls-tree", "-r", "--name-only", "claims").stdout.split()
    files = [t for t in tree if t.startswith("metrics/") and t.endswith(".tsv")]
    expect(len(files) == 1, "expected one metrics file on claims, got %r" % tree)
    body = r.g(f.remote, "show", "claims:" + files[0]).stdout
    expect("status" in body and "frobnicate" in body, "published rows missing: " + body[-300:])
    expect(not rows(common), "pending must be empty after the flush: %r" % rows(common))
    # a flush that fails keeps the lines
    uak(f, "status")
    r.g(w, "remote", "set-url", "origin", str(f.remote) + "-gone")
    out = r.run([r.bash, ".uak/bin/bb", "flush"], cwd=w, allowed=None, env=dict(ENV, UAK_REMOTE="origin"))
    expect(len(rows(common)) >= 1, "a failed flush must keep the lines")
    return "published, emptied, kept on failure"


def the_file_is_capped_with_counts(r):
    f = r.fixture("ledger-cap", count=1)
    w = f.worktrees[0]
    for _ in range(4):
        uak(f, "frobnicate")
    r.run([r.bash, ".uak/bin/bb", "flush"], cwd=w, allowed=None, env=dict(ENV, UAK_LEDGER_CAP="2"))
    tree = [t for t in r.g(f.remote, "ls-tree", "-r", "--name-only", "claims").stdout.split() if t.startswith("metrics/")]
    body = r.g(f.remote, "show", "claims:" + tree[0]).stdout
    data = [ln for ln in body.splitlines() if ln and not ln.startswith("#")]
    sums = [ln.split("\t") for ln in body.splitlines() if ln.startswith("#sum")]
    expect(len(data) == 2, "expected 2 data lines under cap 2: " + body)
    expect(sums and sums[0][1] == "frobnicate" and sums[0][2] == "fail" and sums[0][3].strip() == "2", "summary row: %r" % sums)
    return "capped"


def a_session_with_no_errors_still_publishes(r):
    import time
    f = r.fixture("ledger-idle", count=1)
    w = f.worktrees[0]
    common = common_of(r, w)
    old = int(time.time()) - 1200
    pending = common / "uak-ledger.pending"
    pending.write_text("%d\tstatus\t-\t0\t-\t5\tagent-1\tcodex\n" % old, encoding="utf-8")
    t = time.time() - 1200
    os.utime(pending, (t, t))
    expect(not (common / "uak-blackbox.pending").exists(), "the session must have no black box lines")
    uak(f, "status")
    end = time.time() + 40
    while time.time() < end:
        tree = r.g(f.remote, "ls-tree", "-r", "--name-only", "claims").stdout
        if "metrics/" in tree:
            break
        time.sleep(0.5)
    expect("metrics/" in tree, "a ledger 20 min old was not published by a plain command: " + tree)
    expect((common / "uak-blackbox.flushed").exists(), "the stamp is taken first")
    # a first line without epoch (bash 3.2) is due by the file's age
    f3 = r.fixture("ledger-noepoch", count=1)
    c3 = common_of(r, f3.worktrees[0])
    p3 = c3 / "uak-ledger.pending"
    p3.write_text("-\tstatus\t-\t0\t-\t0\tagent-1\tcodex\n", encoding="utf-8")
    os.utime(p3, (t, t))
    uak(f3, "status")
    end = time.time() + 40
    while time.time() < end and "metrics/" not in r.g(f3.remote, "ls-tree", "-r", "--name-only", "claims").stdout:
        time.sleep(0.5)
    expect("metrics/" in r.g(f3.remote, "ls-tree", "-r", "--name-only", "claims").stdout, "a line without epoch, 20 min old, was never due")
    # fresh ledger lines wait
    f2 = r.fixture("ledger-fresh", count=1)
    c2 = common_of(r, f2.worktrees[0])
    uak(f2, "status")
    uak(f2, "status")
    time.sleep(2)
    expect(not (c2 / "uak-blackbox.flushed").exists() and len(rows(c2)) == 2, "a fresh ledger must wait its 10 minutes")
    return "published when old, waits when fresh"


def blackbox_off_writes_nothing(r):
    f = r.fixture("ledger-off", count=1)
    common = common_of(r, f.worktrees[0])
    uak(f, "status", UAK_BLACKBOX="off")
    expect(not rows(common), "UAK_BLACKBOX=off must write no ledger line")
    return "off"


def output_and_exit_code_unchanged(r):
    f = r.fixture("ledger-same", count=1)
    w = f.worktrees[0]
    a = uak(f, "status")
    b = uak(f, "status", UAK_BLACKBOX="off")
    expect(a.returncode == b.returncode, "exit code changed")
    expect(a.stdout == b.stdout and a.stderr == b.stderr, "output changed:\n%s\n---\n%s" % (a.stdout + a.stderr, b.stdout + b.stderr))
    a = uak(f, "frobnicate")
    b = uak(f, "frobnicate", UAK_BLACKBOX="off")
    expect(a.returncode == b.returncode and a.stderr == b.stderr, "failure output changed")
    return "same"


def exec_commands_record_code_and_ms(r):
    """UAK-136: a command the dispatcher runs as a script of its own (run=exec) ends with its exit code and milliseconds."""
    f = r.fixture("ledger-exec", count=1)
    common = common_of(r, f.worktrees[0])
    ok = uak(f, "pace")
    expect(ok.returncode == 0, "pace failed: " + ok.stderr[-300:])
    bad = uak(f, "metrics", "--since", "0")   # a bad option: exit 2
    expect(bad.returncode != 0, "metrics --since 0 should fail")
    got = rows(common)
    expect(len(got) == 2, "expected one line per exec'd command, got %r" % got)
    expect(got[0][1] == "pace" and got[0][3] == "0" and got[0][5].isdigit(), "pace must record exit 0 and ms: %r" % got[0])
    expect(got[1][1] == "metrics" and got[1][3] == str(bad.returncode) and got[1][5].isdigit(), "metrics must record its exit code and ms: %r" % got[1])
    # The bash 3.2 path (whole seconds, no start time handed over): the script must still close its line under `set -u`.
    sec = uak(f, "pace", UAK_LEDGER_CLOCK="seconds")
    expect(sec.returncode == 0, "pace failed on the seconds clock: " + sec.stderr[-300:])
    last = rows(common)[-1]
    expect(last[1] == "pace" and last[3] == "0" and last[5].isdigit() and int(last[5]) % 1000 == 0, "seconds clock: %r" % last)
    expect(len(rows(common)) == 3, "expected 3 lines before the off run: %r" % rows(common))
    # The same output and exit code with the ledger off.
    off = uak(f, "metrics", "--since", "0", UAK_BLACKBOX="off")
    expect(off.returncode == bad.returncode and off.stdout == bad.stdout and off.stderr == bad.stderr, "exec'd command output changed")
    expect(len(rows(common)) == 3, "UAK_BLACKBOX=off must write nothing")
    return "exec'd commands record exit code and ms"


PROBE = """#!/usr/bin/env bash
set -u
[ -z "${UAK_LG_OWED:-}" ] || { . "${0%/*}/lib/ledger.sh"; ledger_owed; }
trap 'printf "own-trap\\n" >> "$PROBE_OUT"' EXIT
printf '%s %s\\n' "$$" "$PPID" >> "$PROBE_OUT"
case "${1:-}" in
  loop) sleep 30 & wait $!;;
  nested) bash .uak/bin/uak status > /dev/null 2>&1;;
  code) exit 7;;
esac
"""


def probe(f):
    """A scripted exec row of the fixture's own engine: it calls ledger_owed like the engine's scripts do."""
    w = f.worktrees[0]
    b = w / ".uak" / "bin"
    (b / "lgprobe").write_text(PROBE, encoding="utf-8", newline="\n")
    with open(str(b / "lib" / "commands.tsv"), "a", encoding="utf-8", newline="\n") as t:
        t.write("lgprobe\texec\t-\tlgprobe\tuak_cli\tlgprobe   test row\n")
    return w, w / "probe.out"


def exec_script_keeps_the_callers_process(r):
    """UAK-136: the dispatcher execs the script: no waiting `uak` wrapper, its own EXIT trap still runs, one line with its code."""
    f = r.fixture("ledger-tree", count=1)
    w, out = probe(f)
    common = common_of(r, w)
    pidfile = w / "pid.txt"
    res = f.r.run([f.r.bash, "-c", 'echo $$ > pid.txt; exec bash .uak/bin/uak lgprobe code'], cwd=w, allowed=None,
                  env=dict(ENV, PROBE_OUT=str(out)))
    expect(res.returncode == 7, "exit code must pass through: %d" % res.returncode)
    lines = out.read_text(encoding="utf-8").split()
    expect(lines[0] == pidfile.read_text().strip(), "the script must be the caller's own process (no wrapper): %r vs %s" % (lines, pidfile.read_text()))
    expect("own-trap" in lines, "the script's own EXIT trap must still run: %r" % lines)
    got = rows(common)
    expect(len(got) == 1 and got[0][1] == "lgprobe" and got[0][3] == "7" and got[0][5].isdigit(), "one line with the real code: %r" % got)
    return "exec keeps the process; own trap chained"


def term_stops_an_exec_script_at_once(r):
    """UAK-136: TERM on the process stops the script within a second (it is not held by a wrapper or a deferred trap)."""
    import signal
    import subprocess
    import time
    f = r.fixture("ledger-term", count=1)
    w, out = probe(f)
    env = dict(os.environ, **dict(ENV, PROBE_OUT=str(out)))
    p = subprocess.Popen([f.r.bash, ".uak/bin/uak", "lgprobe", "loop"], cwd=str(w), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if out.exists() and out.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.1)
    t0 = time.time()
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(timeout=5)
    finally:
        if p.poll() is None:
            p.kill()
    expect(time.time() - t0 < 1.5 and p.returncode != 0, "TERM must stop the script at once: rc %s after %.1f s" % (p.returncode, time.time() - t0))
    return "TERM stops it"


def one_line_when_the_script_calls_uak_again(r):
    """UAK-136: a `uak` call inside an exec'd script writes its own line, and the outer line is closed once."""
    f = r.fixture("ledger-nested", count=1)
    w, out = probe(f)
    common = common_of(r, w)
    res = f.r.run([f.r.bash, ".uak/bin/uak", "lgprobe", "nested"], cwd=w, allowed=None, env=dict(ENV, PROBE_OUT=str(out)))
    expect(res.returncode == 0, res.stderr[-300:])
    cmds = sorted(x[1] for x in rows(common))
    expect(cmds == ["lgprobe", "status"], "one line for the script and one for the nested uak: %r" % cmds)
    return "no second line"


TESTS = [a_command_appends_one_ledger_line, a_failed_command_records_its_code, flush_publishes_and_empties,
         the_file_is_capped_with_counts, a_session_with_no_errors_still_publishes, blackbox_off_writes_nothing, output_and_exit_code_unchanged, exec_commands_record_code_and_ms,
         exec_script_keeps_the_callers_process, term_stops_an_exec_script_at_once, one_line_when_the_script_calls_uak_again]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak ledgér-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("COMMAND_LEDGER_RESULT %s" % ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
