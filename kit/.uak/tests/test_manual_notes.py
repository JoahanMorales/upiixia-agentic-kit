#!/usr/bin/env python3
"""UAK-121 "I had to do this by hand": `uak bb note manual TEXT --fix IDEA` records a note of kind manual, and the output
hook records one `manual` line (auto) per kind per session for the manual moves the black boxes show most: git worktree
add, a commit on the base branch from the main checkout, gh pr merge after a MERGE_HUMAN, a push to claims refused by
the guard. Only the KIND is recorded, never the command. Real Git, a local bare remote."""
import argparse
import json
import re
import shutil
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_v592 import call

LINE = re.compile(r"^- (\S+) \| v(\S*) \| (\S+) \| (\S+) \| (\S+) \| (\S+) \| (.*?) \| (.*?) \| fix: (.*)$")


def setup(r, name):
    f = r.fixture(name, count=1)
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    common = Path(r.g(w, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    return f, w, common


def pending(common):
    p = common / "uak-blackbox.pending"
    return [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def manual_lines(common):
    out = []
    for l in pending(common):
        m = LINE.match(l)
        expect(m, "a line the harvest cannot read: " + l)
        if m.group(6) == "manual":
            out.append(m)
    return out


def payload(cmd, out="", sid="s1"):
    return json.dumps({"session_id": sid, "tool_name": "Bash", "tool_input": {"command": cmd},
                       "tool_response": {"stdout": out, "stderr": "", "interrupted": False}})


def hook(r, w, cmd, out="", sid="s1", env=None, which="output"):
    e = {"UAK_POLL_SECONDS": "100000"}
    e.update(env or {})
    res = call(r, w, [".uak/bin/hook", which], payload(cmd, out, sid), e)
    expect(res.returncode == 0, "hook %s: %s" % (which, res.stderr[-300:]))


def manual_note_is_recorded_with_task(r):
    f, w, common = setup(r, "mn-note")
    out = r.run([r.bash, ".uak/bin/bb", "note", "manual", "pushed the branch by hand", "--fix", "uak push ID"], cwd=w,
                env={"UAK_BLACKBOX": ""}, allowed=None)
    expect(out.returncode == 0 and "recorded (manual)" in out.stdout, "note: " + out.stdout + out.stderr)
    lines = manual_lines(common)
    if not lines:   # a flush in the fixture may already have published it: the claims branch holds it then
        shown = r.run([r.bash, ".uak/bin/bb", "show", "5"], cwd=w, allowed=None).stdout
        lines = [m for m in (LINE.match(l) for l in shown.splitlines()) if m and m.group(6) == "manual"]
    expect(len(lines) == 1, "one manual line: %r" % lines)
    m = lines[0]
    expect(m.group(5) == "agent" and "pushed the branch by hand" in m.group(8) and "HACK-001" in m.group(8)
           and m.group(9) == "uak push ID", "task and fix: " + m.group(0))
    bad = r.run([r.bash, ".uak/bin/bb", "note", "weird", "x"], cwd=w, allowed=None)
    expect(bad.returncode != 0 and "manual" in bad.stderr, "the usage names the kind: " + bad.stderr)
    st = r.run([r.bash, ".uak/bin/bb", "status"], cwd=w, allowed=None).stdout
    expect("bb note manual" in st, "status asks for the note: " + st)
    return "recorded"


def worktree_add_by_hand_is_noticed_once(r):
    f, w, common = setup(r, "mn-wt")
    secret = "wt-secret-branch-name"
    hook(r, w, "ls -la")
    hook(r, w, "git worktree add ../elsewhere-x -b " + secret)
    hook(r, w, "git worktree add ../elsewhere-y -b " + secret + "2")
    lines = manual_lines(common)
    expect(len(lines) == 1 and lines[0].group(5) == "auto", "once per session: %r" % [l.group(0) for l in lines])
    expect(secret not in lines[0].group(0) and "elsewhere" not in lines[0].group(0), "no command text: " + lines[0].group(0))
    expect("worktree" in lines[0].group(8) and "HACK-001" in lines[0].group(8), "kind and task: " + lines[0].group(0))
    hook(r, w, "git worktree add ../elsewhere-z", sid="s2", which="tick")
    expect(len(manual_lines(common)) == 2, "a new session notices it again")
    return "once"


def human_merge_after_merge_human_is_counted(r):
    f, w, common = setup(r, "mn-merge")
    hook(r, w, "gh pr merge 7 --squash")
    expect(not manual_lines(common), "no MERGE_HUMAN before: not counted")
    hook(r, w, "bash .uak/bin/uak merge HACK-001", "MERGE_HUMAN HACK-001 | needs a human")
    hook(r, w, "gh pr merge 7 --squash")
    hook(r, w, "gh pr merge 8 --squash")
    lines = manual_lines(common)
    expect(len(lines) == 1 and "MERGE_HUMAN" in lines[0].group(8), "counted once: %r" % [l.group(0) for l in lines])
    expect("7" not in lines[0].group(0).split("|")[7], "no arguments: " + lines[0].group(0))
    return "counted"


def prose_is_never_a_move(r):
    f, w, common = setup(r, "mn-prose")
    prose = ['git commit -m "docs: explain git worktree add usage"', "echo see git worktree add for details",
             "grep -rn 'x git worktree add' docs", 'echo "a;git worktree add b"',
             "git commit -F - <<'EOF'\nnote\n git worktree add ../x\nEOF", 'echo "x gh pr merge 5"']
    hook(r, w, "bash .uak/bin/uak merge HACK-001", "MERGE_HUMAN HACK-001 | needs a human")
    prose += ["echo run gh pr merge later", 'git commit -m "do not gh pr merge by hand"']
    for i, cmd in enumerate(prose):
        hook(r, w, cmd, sid="p%d" % i)
    expect(not manual_lines(common), "prose recorded: %r" % [l.group(0) for l in manual_lines(common)])
    return "none"


def real_moves_at_command_position(r):
    for i, cmd in enumerate(["git worktree add ../x feat/y", "cd a && git worktree add b", "git -C /repo worktree add b",
                             "FOO=1 git worktree add b", "cd a;\r\ngit worktree add b"]):
        f, w, common = setup(r, "mn-real%d" % i)
        hook(r, w, cmd)
        expect(len(manual_lines(common)) == 1, "not counted: %r" % cmd)
    f, w, common = setup(r, "mn-realgh")
    hook(r, w, "bash .uak/bin/uak merge HACK-001", "MERGE_HUMAN HACK-001 | x")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    expect((gd / "uak-merge-human").exists(), "one small state file per git dir")
    hook(r, w, "gh -R o/r pr merge 5 --merge")
    expect(len(manual_lines(common)) == 1 and not (gd / "uak-merge-human").exists(), "counted, and the state is consumed")
    return "counted"


def other_moves_and_off(r):
    f, w, common = setup(r, "mn-other")
    # A commit on the base branch from the main checkout: the pre-commit log has it.
    main = f.clones[0]
    log = common / "uak-direct-main.log"
    expect(main.exists(), "main checkout")
    hook(r, w, "git commit -m x")
    expect(not manual_lines(common), "a task worktree commit is not manual")
    hook(r, w, "git push origin HEAD:claims", "pre-push: refs/heads/claims refused (a human, for a hotfix)")
    lines = manual_lines(common)
    expect(len(lines) == 1 and "claims" in lines[0].group(8), "claims push: %r" % [l.group(0) for l in lines])
    # The guard's own refusal comes through bb auto.
    r.run([r.bash, ".uak/bin/bb", "auto", "guard", "guard", "the claims branch is written only by uak commands, never by a push of yours."],
          cwd=w, allowed=None)
    expect(len([l for l in manual_lines(common) if "claims" in l.group(8)]) == 2, "bb auto adds the kind too")
    # Off records nothing.
    before = len(pending(common))
    hook(r, w, "git worktree add ../off", sid="s9", env={"UAK_BLACKBOX": "off"})
    expect(len(pending(common)) == before, "UAK_BLACKBOX=off records nothing")
    return "ok"


def direct_main_commit_is_noticed(r):
    f, w, common = setup(r, "mn-direct")
    main = f.clones[0]
    (main / ".uak-env").write_text("UAK_AGENT=agent-1\n", encoding="utf-8")
    gd = Path(r.g(main, "rev-parse", "--path-format=absolute", "--git-dir").stdout.strip())
    (gd / "uak-direct-main.log").write_text("%d agent-1 main\n" % int(time.time()), encoding="utf-8")
    hook(r, main, "git commit -m hotfix")
    lines = manual_lines(gd)
    expect(len(lines) == 1 and "base branch" in lines[0].group(8), "direct main: %r" % [l.group(0) for l in lines])
    return "noticed"


TESTS = [prose_is_never_a_move, real_moves_at_command_position, manual_note_is_recorded_with_task, worktree_add_by_hand_is_noticed_once, human_merge_after_merge_human_is_counted,
         other_moves_and_off, direct_main_commit_is_noticed]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    tmp = tempfile.mkdtemp(prefix="uak-manual-")
    try:
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("MANUAL_NOTES_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
