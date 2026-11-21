#!/usr/bin/env python3
"""UAK-118: every task records who touched it and which model and harness each one ran. The task-session record holds
`Harness:` and `Model:`, the worklog event line of every mutation ends with `| Harness: H | Model: M` (parsers read the
first four columns and ignore the tail), and the task record lists participants by role. The model comes from
UAK_MODEL, else what the session-start hook saw, else `unknown`. STATE.md keeps its format.
Why (the human, 2026-11-21): nothing said which model reviewed or wrote a task. Real Git, local bare remotes."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack

SESSION = "meta/task-sessions/HACK-001/agent-agent-1/session-stable.md"


def gitdir(f, i=0):
    return Path(f.r.g(f.worktrees[i], "rev-parse", "--absolute-git-dir").stdout.strip())


def session_record_has_harness_and_model(r):
    f = r.fixture("tp-session", count=1)
    config(f)
    hack(f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(),
         UAK_MODEL="model-a", UAK_HARNESS="codex")
    rec = f.show(SESSION)
    expect("Harness: codex" in rec and "Model: model-a" in rec, "session record: " + rec)
    return "Harness and Model"


def events_carry_the_model(r):
    f = r.fixture("tp-events", count=1)
    config(f)
    hack(f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(),
         UAK_MODEL="model-a", UAK_HARNESS="codex")
    hack(f, 0, "done", "HACK-001", "--pr", "https://example.invalid/pull/1", "--evidence", "fixture", now=1000010,
         UAK_MODEL="model-b", UAK_HARNESS="codex")
    body = f.show(f.worklog("HACK-001"))
    events = [l for l in body.splitlines() if l.startswith("- 1000")]
    expect(len(events) >= 2, "events exist: " + body)
    expect(events[0].endswith("| Harness: codex | Model: model-a"), "claim event: " + events[0])
    expect(events[-1].endswith("| Harness: codex | Model: model-b"), "done event: " + events[-1])
    expect(" | CLAIMED | agent-1 | " in events[0] or " | CLAIMED | agent-1 |" in events[0], "first columns unchanged: " + events[0])
    return "events end with the fields"


def participants_by_role(r):
    f = r.fixture("tp-roles", count=2)
    config(f)
    hack(f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(),
         UAK_MODEL="model-a", UAK_HARNESS="codex")
    hack(f, 0, "register-reviewer", "agent-2", UAK_HUMAN="joahan", now=1000005)
    hack(f, 1, "review", "HACK-001", "--sha", f.main_head if hasattr(f, "main_head") else "x", "--verdict", "approve",
         now=1000011, UAK_MODEL="model-r", UAK_HARNESS="claude-code", allowed=None)
    rec = f.show("tasks/HACK-001.md")
    line = [l for l in rec.splitlines() if l.startswith("Participants: ")]
    expect(line, "task record has Participants: " + rec)
    expect("author agent-1 (model-a)" in line[0], "author: " + line[0])
    expect("reviewer agent-2 (model-r) approve" in line[0], "reviewer with verdict: " + line[0])
    return line[0]


def unknown_when_nothing_tells(r):
    f = r.fixture("tp-unknown", count=1)
    config(f)
    hack(f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(),
         UAK_MODEL="", UAK_HARNESS="")
    rec = f.show(SESSION)
    expect("Model: unknown" in rec, "unknown model: " + rec)
    (gitdir(f) / "uak-model").write_text("claude-seen-by-hook\n", encoding="utf-8")
    hack(f, 0, "heartbeat", "HACK-001", now=1000020, UAK_MODEL="", UAK_HARNESS="")
    expect("Model: claude-seen-by-hook" in f.show(SESSION), "hook-seen model: " + f.show(SESSION))
    # the hook itself writes it from the payload at session start
    w = f.worktrees[0]
    (w / "payload.json").write_text('{"hook_event_name":"SessionStart","source":"startup","model":"claude-opus-9"}', encoding="utf-8")
    (gitdir(f) / "uak-model").unlink()
    r.run([r.bash, "-c", "bash .uak/bin/hook session-start < payload.json"], cwd=w, env={"UAK_AGENT": "agent-1"}, allowed=None)
    seen = (gitdir(f) / "uak-model").read_text(encoding="utf-8").strip() if (gitdir(f) / "uak-model").exists() else ""
    expect(seen == "claude-opus-9", "the hook recorded the payload's model: " + seen)
    return "unknown, then hook-seen"


def snapshot_unchanged(r):
    f = r.fixture("tp-state", count=1)
    config(f)
    hack(f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(),
         UAK_MODEL="model-a", UAK_HARNESS="codex")
    state = f.show("STATE.md")
    expect("model-a" not in state and "Harness" not in state and "Participants" not in state, "STATE.md has no new fields: " + state)
    return "STATE.md untouched"


TESTS = [session_record_has_harness_and_model, events_carry_the_model, participants_by_role,
         unknown_when_nothing_tells, snapshot_unchanged]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-participants-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        selected = [t for t in TESTS if not args.case or t.__name__ in args.case]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, selected))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("TASK_PARTICIPANTS_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
