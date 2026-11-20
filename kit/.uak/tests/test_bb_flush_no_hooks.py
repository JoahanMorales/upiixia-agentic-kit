#!/usr/bin/env python3
"""UAK-089: the black box is published without harness hooks.
Why (the kit's own repo, 10 to 15 Nov 2026): 61 errors sat in .git/uak-blackbox.pending and none was published, because
`bb flush` only started from a harness hook and the kit is driven by subagents and plain shells. A `uak` command now
starts `bb flush --quiet` in the background when the pending lines are older than 10 minutes (the hook's own condition).
Real Git, a local bare remote."""
import argparse
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

LINE = "2026-11-10T10:00Z | agent | kit | error | uak claim | boom | - | - | - | v6.4\n"


def setup(r, name, age_min):
    f = r.fixture(name, count=1)
    w = f.worktrees[0]
    common = Path(r.g(w, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    pending = common / "uak-blackbox.pending"
    pending.write_text(LINE, encoding="utf-8")
    t = time.time() - age_min * 60
    os.utime(pending, (t, t))
    return f, pending, common


def status(f, **env):
    return f.r.run([f.r.bash, ".uak/bin/uak", "status"], cwd=f.worktrees[0], allowed=None,
                   env={"UAK_AGENT": "agent-1", "UAK_NOW": "1000000", "UAK_REMOTE": "origin", "UAK_HUMAN": "", **env})


def wait_flushed(pending, seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        if not pending.exists() or pending.stat().st_size == 0:
            time.sleep(0.5)  # the snapshot file goes after the push
            return True
        time.sleep(0.3)
    return False


def published(f):
    out = f.r.g(f.remote, "ls-tree", "-r", "--name-only", "claims").stdout
    return "blackbox/" in out


def old_pending_is_flushed_by_a_plain_command(r):
    f, pending, common = setup(r, "bb-old", 20)
    out = status(f)
    expect(wait_flushed(pending), "old pending lines were not flushed by a plain uak command: " + out.stdout[-300:] + out.stderr[-300:])
    expect(published(f), "the lines did not reach claims:blackbox/")
    return "flushed"


def fresh_pending_waits(r):
    f, pending, common = setup(r, "bb-fresh", 2)
    status(f)
    time.sleep(3)
    expect(pending.read_text(encoding="utf-8") == LINE, "fresh pending lines must wait their 10 minutes")
    expect(not (common / "uak-blackbox.flushed").exists(), "no flush stamp for a fresh file")
    return "waits"


def blackbox_off_starts_nothing(r):
    f, pending, common = setup(r, "bb-off", 20)
    status(f, UAK_BLACKBOX="off")
    time.sleep(3)
    expect(pending.read_text(encoding="utf-8") == LINE, "UAK_BLACKBOX=off must start nothing")
    expect(not (common / "uak-blackbox.flushed").exists(), "no stamp with the box off")
    return "off"


def output_and_exit_code_unchanged(r):
    f, pending, common = setup(r, "bb-same", 2)
    before = status(f)
    t = time.time() - 1200
    os.utime(pending, (t, t))
    after = status(f)
    expect(before.returncode == after.returncode, "exit code changed: %s vs %s" % (before.returncode, after.returncode))
    expect(before.stdout == after.stdout and before.stderr == after.stderr,
           "output changed:\n%s\n---\n%s" % (before.stdout + before.stderr, after.stdout + after.stderr))
    wait_flushed(pending)
    return "same"


TESTS = [old_pending_is_flushed_by_a_plain_command, fresh_pending_waits, blackbox_off_starts_nothing, output_and_exit_code_unchanged]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak bb flúsh-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("BB_FLUSH_NO_HOOKS_RESULT %s" % ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
