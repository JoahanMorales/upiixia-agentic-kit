#!/usr/bin/env python3
"""UAK-116: a ledger of every command: epoch, command, task, exit code, UAK_CODE, milliseconds, agent, harness.
Why (audit of v6.5.0, docs/audit-2026-11.md section 4): calls were names only, with no durations and no outcomes.
Every `uak` command appends one line to <git-common-dir>/uak-ledger.pending when it ends; `bb flush` publishes it
to claims as metrics/<day>-<machine>.tsv in the black box's transaction and empties it. Real Git, local bare remote."""
import argparse
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


TESTS = [a_command_appends_one_ledger_line, a_failed_command_records_its_code, flush_publishes_and_empties,
         the_file_is_capped_with_counts, blackbox_off_writes_nothing, output_and_exit_code_unchanged]


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
