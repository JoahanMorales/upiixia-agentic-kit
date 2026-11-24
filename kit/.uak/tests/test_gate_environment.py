#!/usr/bin/env python3
"""UAK-189: the merge gate gives the same smoke result wherever `uak merge` runs, and says which review mode it chose.
Why (2026-11-23): the merge of UAK-157 run from its worktree failed test_manual_notes and test_task_participants, whose
fixtures recorded under the real task (UAK_TASK came from the worktree's .uak-env); from the main checkout, without the
variable, it merged. In Review-Mode: auto a project without gh reviewed on claims and never said so.
Real Git, a local bare remote; the fixture's project smoke writes the environment it was handed."""
import argparse
import os
import tempfile
import time
from pathlib import Path

import test_review_merge as rm
from test_hack import Runner, expect, resolve_binary

TASK_VARS = ("UAK_TASK", "UAK_SESSION", "UAK_AGENT", "UAK_AGENT_HUMAN")
WORKTREE_ENV = "UAK_AGENT=agent-1\nUAK_AGENT_HUMAN=somebody\nUAK_SESSION=agent-1-1795494301\nUAK_TASK=HACK-001\nUAK_PORT=8190\n"


def gate_fixture(r, name, review_mode=None):
    f = rm.fixture(r, "ge-" + name, count=1)
    log = f.base / "gate-env.log"
    seed = f.seed
    if review_mode:
        p = seed / ".uak/PROJECT.md"
        p.write_text(p.read_text(encoding="utf-8").replace("Review-Mode: claims", "Review-Mode: " + review_mode),
                     encoding="utf-8")
    lines = "".join("printf '%s=%%s\\n' \"${%s-UNSET}\" >> '%s'\n" % (v, v, log.as_posix()) for v in TASK_VARS)
    (seed / ".uak/bin/smoke-project").write_text("#!/usr/bin/env bash\nset -eu\n" + lines, encoding="utf-8")
    r.g(seed, "add", "-A")
    r.g(seed, "commit", "-q", "-m", "fixture: environment-reporting project smoke")
    r.g(seed, "push", "-q", "origin", "main")
    f.main_head = r.g(f.remote, "rev-parse", "main").stdout.strip()
    for clone, worktree in zip(f.clones, f.worktrees):
        r.g(clone, "fetch", "-q", "origin", "main")
        r.g(worktree, "reset", "-q", "--hard", "origin/main")
    return f, log


def uak(f, where, args, env=None, path=None):
    e = {"UAK_AGENT": "agent-1", "UAK_NOW": "1000030", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    e.update(env or {})
    if path is not None:
        e["PATH"] = path
    return f.r.run([f.r.bash, ".uak/bin/uak", *map(str, args)], cwd=where, env=e, allowed=None)


def reviewed(f):
    f.claim(0, "HACK-001")
    tip = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "x", "--no-red", "fixture", now=1000010)
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    return tip


def seen(log):
    return dict(l.split("=", 1) for l in log.read_text(encoding="utf-8").split("\n") if "=" in l)


def merge_ok(out):
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout, "the merge goes through: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-700:]))


def smoke_environment_has_no_task(r):
    """The variables a worktree's .uak-env sets (and a shell export of them) never reach the gate's smoke."""
    f, log = gate_fixture(r, "env")
    reviewed(f)
    out = uak(f, f.clones[0], ["merge", "HACK-001"], {"UAK_TASK": "UAK-999", "UAK_SESSION": "s-9", "UAK_AGENT_HUMAN": "someone"})
    merge_ok(out)
    got = seen(log)
    expect(got and all(got.get(v) == "UNSET" for v in TASK_VARS), "the smoke saw %r" % got)
    return "no %s in the smoke" % "/".join(TASK_VARS)


def merge_from_worktree_equals_merge_from_main(r):
    """The same merge from the task's worktree (its .uak-env loaded) and from the main checkout: one smoke environment."""
    results = []
    for place in ("main", "worktree"):
        f, log = gate_fixture(r, "eq-" + place)
        reviewed(f)
        where = f.clones[0]
        if place == "worktree":
            where = f.worktrees[0]
            (where / ".uak-env").write_text(WORKTREE_ENV, encoding="utf-8")
        out = uak(f, where, ["merge", "HACK-001"], {"UAK_AGENT": "agent-1"})
        merge_ok(out)
        results.append((seen(log), "Smoke:" in f.show("tasks/HACK-001.md")))
    expect(results[0] == results[1], "main %r vs worktree %r" % tuple(results))
    expect(results[1][0].get("UAK_TASK") == "UNSET", "the worktree's task did not reach the smoke: %r" % results[1][0])
    return "same smoke environment from both places"


def path_without_gh(r):
    """A PATH with every directory of the real one, minus gh: a dir that holds gh among other tools becomes a farm of links."""
    farm = Path(r.scratch) / "no-gh-path"
    farm.mkdir(exist_ok=True)
    parts = []
    for i, d in enumerate(os.environ.get("PATH", "").split(os.pathsep)):
        if not d or not os.path.isdir(d):
            continue
        names = os.listdir(d)
        gh = [n for n in names if n in ("gh", "gh.exe", "gh.cmd", "gh.bat")]
        if not gh:
            parts.append(d)
            continue
        rest = [n for n in names if n not in gh]
        if not rest:
            continue
        sub = farm / str(i)
        sub.mkdir(exist_ok=True)
        for n in rest:
            try:
                os.symlink(os.path.join(d, n), str(sub / n))
            except OSError:
                return None
        parts.append(str(sub))
    return os.pathsep.join(parts)


def auto_mode_says_what_it_chose(r):
    """Review-Mode: auto and no gh in PATH: `uak done` and `uak merge` each say, once, that approvals come from claims."""
    path = path_without_gh(r)
    if path is None:
        return "this system cannot link the tools of the PATH folder that holds gh: skipped"
    f, log = gate_fixture(r, "auto", review_mode="auto")
    f.claim(0, "HACK-001")
    tip = rm.publish(f, 0, "HACK-001")
    url = "https://github.com/fixture/fixture/pull/1"
    done = uak(f, f.worktrees[0], ["done", "HACK-001", "--pr", url, "--evidence", "x", "--no-red", "fixture"], {"UAK_NOW": "1000010"}, path)
    expect(done.returncode == 0, "done goes through: rc %d %s" % (done.returncode, (done.stdout + done.stderr)[-500:]))
    note = "Review-Mode is auto"
    expect((done.stdout + done.stderr).count(note) == 1 and "gh" in (done.stderr or done.stdout),
           "done says once which mode it chose: %r" % (done.stdout + done.stderr)[-700:])
    expect(note not in done.stdout, "the note is not on stdout, where other tools read OK lines: " + done.stdout[-300:])
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    out = uak(f, f.clones[0], ["merge", "HACK-001"], None, path)
    merge_ok(out)
    expect((out.stdout + out.stderr).count(note) == 1, "merge says it once: %r" % (out.stdout + out.stderr)[-900:])
    expect("claims" in out.stderr and note not in out.stdout, "on stderr, and it names claims: " + out.stderr[-500:])
    return "done and merge: one note each, on stderr"


TESTS = [merge_from_worktree_equals_merge_from_main, smoke_environment_has_no_task, auto_mode_says_what_it_chose]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-gate-env-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
            started = time.monotonic()
            try:
                note = test(runner)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started), flush=True)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]), flush=True)
    print("GATE_ENVIRONMENT_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
