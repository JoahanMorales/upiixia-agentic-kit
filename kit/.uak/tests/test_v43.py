#!/usr/bin/env python3
"""uak v4.3: the MLB hackathon autopsy (Oct 2026): 4 Windows laptops, Claude Code + Codex +
Cursor, 13 identities, 36 tasks over 3 days. One test per failure seen there.
Real Git, local bare remote, separate processes."""
import argparse
import base64
import concurrent.futures
import json
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack
import test_review_merge as rm


def push_main(f, files, message):
    for rel, text in files.items():
        p = f.seed / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        f.r.g(f.seed, "add", rel)
    f.r.g(f.seed, "commit", "-m", message)
    f.r.g(f.seed, "push", "origin", "main")
    for clone, worktree in zip(f.clones, f.worktrees):
        f.r.g(clone, "fetch", "origin", "main")


def approval_survives_main_merges_and_anyone_merges(r):
    """HACK-031: approved, then main merged in: 'approve the merged SHA first'. HACK-016: approved 10 h, waiting
    for its owner's `uak merge`; two agents asked the human to hurry."""
    f = rm.fixture(r, "v43-carry", count=2)
    tip_a = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip_a, now=1000021)
    tip2 = rm.ready(f, 1, "HACK-002")
    rm.approve(f, "HACK-002", tip2, now=1000022)
    expect("INTEGRATED" in f.hack(1, "merge", "HACK-002", now=1000023).stdout, "HACK-002 moves main")
    w = f.worktrees[0]
    r.g(w, "fetch", "origin")
    r.g(w, "merge", "--no-edit", "origin/main")            # a clean merge of main after the approval
    r.g(w, "push", "origin", f.branches[0])
    early = f.hack(1, "merge", "HACK-001", now=1000021 + 600, allowed=None)
    expect(early.returncode == 3 and "min left" in early.stdout + early.stderr,
           "the owner keeps the first 20 min: " + early.stdout + early.stderr)
    nxt = f.hack(1, "next", now=1000021 + 1300).stdout
    expect("approved" in nxt and "uak merge HACK-001" in nxt, "an idle agent is told to merge it: " + nxt)
    merged = f.hack(1, "merge", "HACK-001", now=1000021 + 1300, allowed=None)
    expect(merged.returncode == 0 and "INTEGRATED" in merged.stdout,
           "the approval holds over a clean merge of main, and another agent merges: " + merged.stdout + merged.stderr)
    expect("Merged-By: agent-2" in f.show("tasks/HACK-001.md"), "who merged it is recorded")
    expect("REQUIRES_RECOVERY" not in f.show("DECISIONS.md") if f.files("DECISIONS.md") else True,
           "REVIEW leases need no recovery")
    return {"carried": True, "adopted": True}


def moved_head_is_explained(r):
    """'The review must match the task's current HEAD' 7 times, with no hint of what moved."""
    f = rm.fixture(r, "v43-moved", count=1)
    tip_a = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    tip_b = rm.publish(f, 0, "HACK-001", suffix="-v2")
    stale = rm.approve(f, "HACK-001", tip_a, allowed=None)
    expect(stale.returncode == 3 and "HEAD moved" in stale.stderr and "1 commit(s)" in stale.stderr,
           "the reviewer is told what changed: " + stale.stderr)
    rm.actor(f, "judge", "review", "HACK-001", "--start", now=1000030)
    stop = rm.actor(f, "judge", "review", "HACK-001", "--stop", now=1000031)
    expect(stop.returncode == 0 and "reviews/HACK-001.reviewing" not in f.files("reviews/"),
           "a reviewer can give a review back: " + stop.stdout + stop.stderr)
    short = rm.actor(f, "judge", "review", "HACK-001", "--sha", tip_b[:9], "--verdict", "reject", now=1000032)
    expect("Rejected SHA " + tip_b[:7] in f.show("inbox/log.md"), "a short SHA of HEAD is accepted: " + short.stdout)
    return {"explained": True}


def rotation_skips_ghosts_and_asks_the_rejecter(r):
    """Three identities of one human had no session left and got 15 rotation reviews; every re-review took 3 messages."""
    f = rm.fixture(r, "v43-rotation", count=3)
    f.claim(2, "HACK-003")                              # agent-3 is active and eligible (live claim)
    hack(f, 1, "msg", "all", "--kind", "info", "agent-2 online", now=1000005)
    retire = hack(f, 1, "retire", "agent-2", now=1000006)
    expect("OK retire agent-2" in retire.stdout, retire.stdout + retire.stderr)
    tip = rm.ready(f, 0, "HACK-001")
    review_lines = [l for l in f.show("inbox/log.md").splitlines() if "| review |" in l]
    expect("agent:agent-3" in review_lines[-1] and "agent:agent-2" not in review_lines[-1],
           "a retired identity gets no rotation: " + review_lines[-1])
    to_ghost = hack(f, 0, "msg", "agent-2", "are you there", now=1000011, allowed=None)
    expect(to_ghost.returncode == 2 and "retired" in to_ghost.stderr, "messages to a retired identity are refused")
    f.hack(2, "review", "HACK-001", "--sha", tip, "--verdict", "reject", "--note", "a.txt:1 · wrong", now=1000012)
    rm.publish(f, 0, "HACK-001", suffix="-fix")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "fixed",
           "--note", "fixed a.txt:1", now=1000013)
    last = [l for l in f.show("inbox/log.md").splitlines() if "| review |" in l][-1]
    expect("agent:agent-3" in last and "you rejected the previous SHA" in last and "fixed a.txt:1" in last,
           "the re-review goes to the rejecter in ONE message with the note: " + last)
    rm.judge(f)                                          # v5.7.1: --to names someone who can review
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "fixed", "--to", "judge", now=1000014)
    last = [l for l in f.show("inbox/log.md").splitlines() if "| review |" in l][-1]
    expect("agent:judge" in last and "asked by agent-1" in last, "--to picks the reviewer: " + last)
    back = f.claim(1, "HACK-002", now=1000015)
    expect(back.returncode == 0 and "meta/retired/agent-2.md" not in f.files("meta/"), "a new claim brings an identity back")
    return {"retired_skipped": True, "rejecter_first": True}


def small_cli_fixes(r):
    """status --help, lowercase IDs, integrate/heartbeat on integrated tasks, follow-ups, REVIEW lease noise,
    and a failed deadline reconcile that broke `uak status` on Windows."""
    f = rm.fixture(r, "v43-cli", count=2)
    push_main(f, {".uak/PROJECT.md": (f.seed / ".uak/PROJECT.md").read_text(encoding="utf-8") + "Plan-Channel: claims\n"},
              "Plan channel on claims")
    for w in f.worktrees:
        r.g(w, "merge", "--no-edit", "origin/main")
    h = f.hack(0, "status", "--help")
    expect(h.returncode == 0 and h.stdout.startswith("status [ID"), "per-command help: " + h.stdout + h.stderr)
    bad = f.hack(0, "heartbeat", "task-1", allowed=None)
    expect(bad.returncode == 2 and "Invalid ID 'task-1'" in bad.stderr and "HACK-012" in bad.stderr, bad.stderr)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f); rm.approve(f, "HACK-001", tip)
    expect("INTEGRATED" in f.hack(0, "merge", "hack-001", now=1000030).stdout, "lowercase IDs work")
    again = f.hack(1, "integrate", "HACK-001", now=1000031)
    expect("already INTEGRATED" in again.stdout, "integrate on an integrated task is OK: " + again.stdout + again.stderr)
    beat = f.hack(0, "heartbeat", "HACK-001", now=1000032)
    expect("nothing to renew" in beat.stdout, "heartbeat after integration is not an error: " + beat.stdout + beat.stderr)
    fu = f.hack(0, "followup", "HACK-001", "--title", "MODELO REAL badge on the page", now=1000033)
    expect("OK followup HACK-003" in fu.stdout, fu.stdout + fu.stderr)
    backlog = f.show("backlog/TASKS.md")
    expect("## HACK-003 · MODELO REAL badge on the page (follow-up of HACK-001)" in backlog
           and "**Paths:** src/value-1.txt" in backlog and "**Depends on:** HACK-001" in backlog, backlog)
    f.claim(0, "HACK-003", now=1000034)
    not_yet = f.hack(1, "followup", "HACK-003", "--title", "x", now=1000035, allowed=None)
    expect(not_yet.returncode == 3 and "not INTEGRATED" in not_yet.stderr, "only integrated tasks get follow-ups")
    rm.ready(f, 1, "HACK-002")                           # REVIEW, then its lease expires overnight
    f.hack(1, "tick", now=1000010 + 10 ** 6)
    expect(not [p for p in f.files("deadlines/") if "HACK-002" in p], "an expired REVIEW lease writes no recovery")
    f.hack(0, "heartbeat", "HACK-003", now=1000010 + 10 ** 6 + 100)   # a new lease: the next tick has a receipt to push
    hook = f.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'policy: claims are read-only' >&2\nexit 1\n", encoding="utf-8")
    os.chmod(hook, 0o755)
    st = f.hack(1, "status", now=1000010 + 2 * 10 ** 6, allowed=None, human=False)
    expect(st.returncode == 0 and "Claims" in st.stdout and "deadline reconcile skipped" in st.stderr,
           "status answers even when the reconcile cannot push: " + st.stdout[-300:] + st.stderr)
    return {"help": True, "followup": "HACK-003"}


def merge_gate_finds_venv_and_explains_scope(r):
    """6 human-queue entries: 'Smoke red' (the clone had no .venv); 6: 'Diff outside Paths' for an empty
    __init__.py, the kit's smoke provenance and real edits, all with the same misleading hint."""
    f = rm.fixture(r, "v43-gate", count=2)
    push_main(f, {".uak/bin/smoke-project": "#!/usr/bin/env bash\nset -eu\nuakfixturetool\n"}, "Product smoke needs the venv")
    for w in f.worktrees:
        r.g(w, "merge", "--no-edit", "origin/main")
    w = f.worktrees[0]
    (w / "pkg").mkdir()
    (w / "pkg/__init__.py").write_text("", encoding="utf-8")
    r.g(w, "add", "pkg/__init__.py")
    r.g(w, "commit", "-m", "package marker")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f); rm.approve(f, "HACK-001", tip)
    red = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    out = red.stdout + red.stderr
    expect("Smoke red" in out and "uakfixturetool" in out and "(log: " in out, "the reason quotes the log: " + out)
    log = out.split("(log: ")[1].split(")")[0]
    expect(Path(log).exists(), "the gate log is kept: " + log)
    venv = f.clones[0] / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "uakfixturetool").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(venv / "uakfixturetool", 0o755)
    ok = f.hack(0, "merge", "HACK-001", now=1000031, allowed=None)
    expect(ok.returncode == 0 and "INTEGRATED" in ok.stdout,
           "the main checkout's .venv is on the gate's PATH and an empty __init__.py is fine: " + ok.stdout + ok.stderr)
    w2 = f.worktrees[1]
    r.g(w2, "fetch", "origin")
    r.g(w2, "merge", "--no-edit", "origin/main")
    (w2 / "src/value-1.txt").write_text("edited by HACK-002\n", encoding="utf-8")
    r.g(w2, "add", "src/value-1.txt")
    r.g(w2, "commit", "-m", "touch another task's file")
    tip2 = rm.ready(f, 1, "HACK-002")
    rm.approve(f, "HACK-002", tip2, now=1000040)
    out = f.hack(1, "merge", "HACK-002", now=1000041, allowed=None)
    text = out.stdout + out.stderr
    expect("Edits a file outside Paths: src/value-1.txt (Paths of HACK-001)" in text and "git checkout origin/main" in text,
           "the scope reason names the owner and the fix: " + text)
    return {"venv": True, "scope": True}


def output_cap_everywhere(r):
    """Windows laptops never got the Cursor cap; Codex's PostToolUse block cut doc reads; a reviewer could not
    read a large diff."""
    f = r.fixture("v43-cap", count=1)
    w = f.worktrees[0]
    def hook(mode, payload, *extra, env=None):
        (w / ".git-payload.json").write_text(json.dumps(payload), encoding="utf-8")
        return r.run([r.bash, "-c", "bash .uak/bin/hook " + mode + " " + " ".join(extra) + " < .git-payload.json"],
                     cwd=w, env=env or {}).stdout
    codex = lambda cmd: {"session_id": "s", "turn_id": "t", "hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": cmd}}
    d = json.loads(hook("wrap", codex("find . -name nothing; seq 1 20000; false"), "codex"))["hookSpecificOutput"]
    expect(d["permissionDecision"] == "allow" and "--b64" in d["updatedInput"]["command"], "Codex: a rewrite, not a block")
    ran = r.run([r.bash, "-c", d["updatedInput"]["command"] + '\necho "rc=$?"'], cwd=w, allowed=None).stdout
    expect("[uak: " in ran and "20000" in ran and ran.strip().endswith("rc=1") and len(ran) < 12000,
           "cut output, same exit code: %d chars" % len(ran))
    expect(hook("wrap", codex("cat docs/README.md"), "codex") == "", "reads are never cut")
    for i in (1, 2):
        (w / ("big%d.txt" % i)).write_text("".join("row %d\n" % n for n in range(3000)), encoding="utf-8")
    r.g(w, "add", "big1.txt", "big2.txt")
    r.g(w, "commit", "-m", "two big files")
    d = json.loads(hook("wrap", codex("git show HEAD"), "codex"))["hookSpecificOutput"]
    shown = r.run([r.bash, "-c", d["updatedInput"]["command"]], cwd=w).stdout
    expect("diff of 2 files" in shown and "big1.txt  +3000 -0" in shown, "a diff becomes a file index: " + shown[:600])
    rng = [l for l in shown.splitlines() if "big2.txt" in l][0].split()[0][1:]
    log = shown.split("Full output: ")[1].split(". Read")[0]
    first = r.run(["sed", "-n", rng.replace("-", ",") + "p", log], cwd=w).stdout.splitlines()[0]
    expect(first.startswith("diff --git a/big2.txt"), "the range reads exactly that file: " + first)
    bindir = f.base / "fakebin"
    bindir.mkdir()
    (bindir / "uname").write_text("#!/bin/sh\necho MINGW64_NT-10.0\n", encoding="utf-8")
    os.chmod(bindir / "uname", 0o755)
    winenv = {"PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")}
    shell = lambda cmd: {"hook_event_name": "preToolUse", "conversation_id": "c", "tool_name": "Shell",
                         "tool_input": {"command": cmd, "working_directory": str(w)}}
    win = json.loads(hook("wrap", shell("python -m pytest -q"), env=winenv))["updated_input"]["command"]
    expect(win.startswith("bash '") and " --b64 " in win and base64.b64decode(win.split()[-1]).decode() == "python -m pytest -q",
           "Cursor on Windows: one command PowerShell and bash both run: " + win)
    for skip in ["pytest $env:X", "cd src; pytest", "Get-ChildItem -Recurse", "pytest tests\\a.py"]:
        expect(hook("wrap", shell(skip), env=winenv) == "", "not wrapped on Windows: " + skip)
    q1 = r.run([r.bash, ".uak/bin/q", "false"], cwd=w, allowed=None).stdout
    q2 = r.run([r.bash, ".uak/bin/q", "false"], cwd=w, allowed=None).stdout
    expect(q1.split(" · log ")[1].splitlines()[0] != q2.split(" · log ")[1].splitlines()[0], "q keeps one log per run: " + q1 + q2)
    return {"codex": "pre-rewrite", "windows": True, "diff_index": True}


def dedupe_without_ps(r):
    """Git Bash has no `ps -o`: '= unchanged' never worked on the 4 Windows laptops."""
    f = r.fixture("v43-ps", count=1)
    config(f)
    f.claim(0, "HACK-001")
    bindir = f.base / "fakebin"
    bindir.mkdir()
    (bindir / "ps").write_text("#!/bin/sh\necho 'ps: unknown option -- o' >&2\nexit 1\n", encoding="utf-8")
    os.chmod(bindir / "ps", 0o755)
    gd = Path(f.r.g(f.worktrees[0], "rev-parse", "--absolute-git-dir").stdout.strip())
    (gd / "uak-live").write_text("cursor-conv-42 1000000\n", encoding="utf-8")
    env = {"UAK_DEDUPE": "on", "PATH": str(bindir) + os.pathsep + os.environ.get("PATH", "")}
    a = hack(f, 0, "status", now=1000010, **env).stdout
    b = hack(f, 0, "status", now=1000011, **env).stdout
    expect("Claims" in a and b.startswith("= unchanged"), "the hook's session id keys the dedupe: " + b[:200])
    return {"dedupe": True}


def busy_queue_is_not_human(r):
    """'Queue busy' sent HACK-021 to the human queue: a held queue is a wait, not a human problem."""
    f = rm.fixture(r, "v43-busy", count=1)
    project = (f.seed / ".uak/PROJECT.md").read_text(encoding="utf-8").replace("Merge-Wait-Seconds: 600", "Merge-Wait-Seconds: 2")
    push_main(f, {".uak/PROJECT.md": project}, "Short merge wait")
    rm.judge(f)
    tip = rm.ready(f, 0, "HACK-001")
    rm.approve(f, "HACK-001", tip)
    holder = f.base / "holder"
    r.g(f.base, "clone", "-q", "-b", "claims", f.remote, holder)
    (holder / "queue").mkdir(exist_ok=True)
    (holder / "queue/merge-lock.md").write_text(
        "Owner: other\nTask: HACK-999\nToken: t\nLease-Until: 9999999\nUpdated: 1000000\n", encoding="utf-8")
    r.g(holder, "add", "-A")
    r.g(holder, "-c", "user.name=x", "-c", "user.email=x@x", "commit", "-qm", "another merge holds the queue")
    r.g(holder, "push", "-q", "origin", "claims")
    busy = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    expect(busy.returncode == 3 and "MERGE_BUSY" in busy.stdout and "HACK-999" in busy.stdout, busy.stdout + busy.stderr)
    expect("human queue" not in f.show("inbox/log.md"), "nothing reaches the humans")
    return {"busy": True}


TESTS = [approval_survives_main_merges_and_anyone_merges, moved_head_is_explained,
         rotation_skips_ghosts_and_asks_the_rejecter, small_cli_fixes, merge_gate_finds_venv_and_explains_scope,
         output_cap_everywhere, dedupe_without_ps, busy_queue_is_not_human]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-v43-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("V43_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
