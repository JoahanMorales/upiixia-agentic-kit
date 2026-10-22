#!/usr/bin/env python3
"""uak v4.2: the Reap x AI Builders buildathon autopsy (Oct 2026). One test per failure seen there.
Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack
import test_review_merge as rm


def common(f, i=0):
    return Path(f.r.g(f.worktrees[i], "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())


def gitdir(f, i=0):
    return Path(f.r.g(f.worktrees[i], "rev-parse", "--absolute-git-dir").stdout.strip())


def scope_uses_current_base(r):
    """HACK-005, 003, 007, 010, 011, 018: a branch that merged origin/main inherited files of other tasks."""
    f = rm.fixture(r, "v42-scope", count=2)
    f.claim(0, "HACK-001")                                  # Task-Base = the old main
    tip2 = rm.ready(f, 1, "HACK-002")
    rm.judge(f)
    rm.approve(f, "HACK-002", tip2)
    first = f.hack(1, "merge", "HACK-002", now=1000033)
    expect("INTEGRATED" in first.stdout, first.stdout + first.stderr)
    w = f.worktrees[0]
    r.g(w, "fetch", "origin")
    r.g(w, "merge", "--no-edit", "origin/main")            # inherits src/value-2.txt from HACK-002
    tip1 = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1000040)
    rm.approve(f, "HACK-001", tip1, now=1000041)
    merged = f.hack(0, "merge", "HACK-001", now=1000042, allowed=None)
    expect(merged.returncode == 0 and "INTEGRATED" in merged.stdout,
           "files already in main are not 'outside Paths': " + merged.stdout + merged.stderr)
    return {"inherited_file_ignored": True}


def freeze_next_and_allow(r):
    """153 FREEZE lines from `next` probes; no human command to allow a task (PRs #10, #11, #14)."""
    f = r.fixture("v42-freeze", count=2)
    config(f, Freeze_Epoch="1000005")
    nxt = hack(f, 0, "next", now=1000010)
    expect("FREEZE since" in nxt.stdout and "uak allow" in nxt.stdout, "next says what to do after the freeze: " + nxt.stdout)
    pending = common(f) / "uak-blackbox.pending"
    text = pending.read_text(encoding="utf-8") if pending.exists() else ""
    expect("FREEZE" not in text, "candidate probes are not black box errors: " + text)
    denied = f.claim(0, "HACK-001", now=1000011, allowed=None)
    expect(denied.returncode == 3 and "uak allow HACK-001" in denied.stderr, "the refusal names the fix: " + denied.stderr)
    agent_only = hack(f, 0, "allow", "HACK-001", "--reason", "demo fix", now=1000012, allowed=None)
    expect(agent_only.returncode == 3 and "human decision" in agent_only.stderr, "an agent cannot allow itself")
    ok = hack(f, 0, "allow", "HACK-001", "HACK-002", "--reason", "login breaks the demo", now=1000013, UAK_HUMAN="ana")
    expect("OK allow HACK-001 HACK-002" in ok.stdout, ok.stdout + ok.stderr)
    allow = f.show("backlog/ALLOW.md")
    expect("- HACK-001 | 1000013 | ana | login breaks the demo" in allow, "audited with the human's name: " + allow)
    expect("freeze exception: HACK-001 HACK-002" in f.show("DECISIONS.md"), "recorded in DECISIONS.md")
    f.claim(0, "HACK-001", now=1000014)
    again = hack(f, 0, "allow", "HACK-001", "--reason", "x", now=1000015, UAK_HUMAN="ana")
    expect("already allowed" in again.stdout, "allow is idempotent: " + again.stdout)
    return {"probe_quiet": True, "allow_audited": True}


def one_identity_one_task(r):
    """Two sessions shared agent-2 on two tasks and overwrote each other's claims."""
    f = r.fixture("v42-identity", count=2, shared_repo=True)
    config(f)
    anon = hack(f, 0, "next", UAK_AGENT="", allowed=None)
    expect(anon.returncode == 0 and "AVAILABLE" in anon.stdout and "wt new HACK-001 (branch" in anon.stdout,
           "next works with no identity (Reap's top error): " + anon.stdout + anon.stderr)
    f.claim(0, "HACK-001")
    args = ("claim", "HACK-002", "--branch", f.branches[1], "--worktree", f.worktrees[1].as_posix())
    second = hack(f, 0, *args, now=1000001, allowed=None)
    expect(second.returncode == 3 and "already holds HACK-001" in second.stderr, "a second live task is refused: " + second.stderr)
    after_lease = hack(f, 0, *args, now=1000000 + 1800 + 5, allowed=None)
    expect(after_lease.returncode == 0, "an expired claim does not count: " + after_lease.stderr)
    return {"second_claim_refused": True}


def messages_without_noise(r):
    """63 copied contract lines, 11 'Recibido' replies, 4 refused messages to Ana-N, 295 inbox calls."""
    f = r.fixture("v42-msg", count=3, dependencies={"HACK-001": "ninguna (contract with HACK-002 HACK-003)"})
    config(f)
    f.claim(0, "HACK-001"); f.claim(1, "HACK-002"); f.claim(2, "HACK-003")
    hack(f, 0, "msg", "related:HACK-001", "--kind", "contract", "Signal v2: direction up/down", now=1000001)
    log = f.show("inbox/log.md")
    lines = [l for l in log.splitlines() if "Signal v2" in l]
    expect(len(lines) == 1 and "task:HACK-002,task:HACK-003" in lines[0], "one line for many targets: " + log)
    for i in (1, 2):
        inbox = hack(f, i, "inbox", now=1000002).stdout
        expect("Signal v2" in inbox, "every target still receives it: " + inbox)
    up = hack(f, 1, "msg", "Ana-1", "PR 21 ready at 6e96359", now=1000003)
    expect("agent:Ana-1" in f.show("inbox/log.md"), "an uppercase agent name is an agent: " + up.stdout + up.stderr)
    ack = hack(f, 1, "msg", "agent-1", "--kind", "reply", "Recibido, gracias", now=1000004, allowed=None)
    expect(ack.returncode == 2 and "inbox --ack" in ack.stderr, "acks are refused: " + ack.stderr)
    info = hack(f, 1, "msg", "agent-1", "--kind", "reply", "Recibido: merged main at 18c8db2, tests 32 pass", now=1000005)
    expect(info.returncode == 0, "a reply with information goes through")
    one = hack(f, 2, "inbox", now=1000006, UAK_DEDUPE="on").stdout
    two = hack(f, 2, "inbox", now=1000007, UAK_DEDUPE="on").stdout
    full = hack(f, 2, "inbox", "--full", now=1000008, UAK_DEDUPE="on").stdout
    expect("Signal v2" in one and "already shown" in two and "Signal v2" not in two and "Signal v2" in full,
           "unread messages are shown once per session: " + two)
    return {"fanout_lines": 1, "ack_refused": True}


def reviews_once(r):
    """HACK-005 had 7 approvals; each verdict came with a second detail message; 5 self-registrations."""
    f = rm.fixture(r, "v42-review", count=2)
    tip = rm.ready(f, 0, "HACK-001")
    reg = rm.actor(f, "lead-human", "register-reviewer", "judge", "judge-2", human=True)
    expect("OK register-reviewer" in reg.stdout and "roles/reviewers/judge-2.md" in f.files("roles/"), reg.stdout + reg.stderr)
    rm.actor(f, "judge", "review", "HACK-001", "--sha", tip, "--verdict", "approve", "--note", "Verify 4 passed, smoke PASS")
    msgs = [l for l in f.show("inbox/log.md").splitlines() if "| approve |" in l]
    expect(len(msgs) == 1 and "Verify 4 passed" in msgs[0], "the note is in the one approval message: " + str(msgs))
    dup = rm.actor(f, "judge-2", "review", "HACK-001", "--sha", tip, "--verdict", "approve")
    expect("already approved by judge" in dup.stdout and "Reviewer: judge\n" in f.show("reviews/HACK-001.md"),
           "a second approval of the same SHA records nothing: " + dup.stdout)
    st = f.hack(0, "status", "HACK-001")
    expect("HACK-001 | REVIEW" in st.stdout, "status takes the ID positionally: " + st.stdout)
    selfreg = r.run([r.bash, ".uak/bin/uak", "register-reviewer", "agent-1"], cwd=f.worktrees[0],
                    env={"UAK_AGENT": "agent-1", "UAK_HUMAN": "ana", "UAK_NOW": "1000050"}, allowed=None)
    expect(selfreg.returncode == 3 and "main checkout" in selfreg.stderr, "self-registration explains the fix: " + selfreg.stderr)
    merged = f.hack(0, "merge", "HACK-001", now=1000060)
    expect("INTEGRATED" in merged.stdout, merged.stdout + merged.stderr)
    return {"approval_messages": 1, "duplicate_noop": True}


def repeated_reads_and_loops(r):
    """status 258 calls, the same refusal retried in a loop."""
    f = r.fixture("v42-reads", count=1)
    config(f)
    f.claim(0, "HACK-001")
    on = {"UAK_DEDUPE": "on"}
    a = hack(f, 0, "status", now=1000010, **on).stdout
    b = hack(f, 0, "status", now=1000011, **on).stdout
    c = hack(f, 0, "status", "--full", now=1000012, **on).stdout
    expect("Claims" in a and b.startswith("= unchanged") and "Claims" in c, "an identical status prints one line: " + b)
    hack(f, 0, "heartbeat", "HACK-001", now=1000013)
    d = hack(f, 0, "status", now=1000014, **on).stdout
    expect("Claims" in d, "a real change prints the full status again")
    errs = [hack(f, 0, "done", "HACK-001", "--pr", "nope", "--evidence", "x", now=1000020 + i, allowed=None) for i in range(3)]
    expect("LOOP:" not in errs[1].stderr and "LOOP:" in errs[2].stderr, "the third identical error says LOOP: " + errs[2].stderr)
    return {"dedupe": True, "loop": True}


def huge_output_is_capped(r):
    """'Tool calling hogs the context': PostToolUse replaces a huge Bash output with head + tail + log path."""
    f = r.fixture("v42-output", count=1)
    w = f.worktrees[0]
    def post(stdout, command="pytest -q"):
        payload = json.dumps({"session_id": "s1", "hook_event_name": "PostToolUse", "tool_name": "Bash",
                              "tool_input": {"command": command},
                              "tool_response": {"stdout": stdout, "stderr": "warn", "interrupted": False, "isImage": False}})
        (w / ".git-payload.json").write_text(payload, encoding="utf-8")
        return r.run([r.bash, "-c", "bash .uak/bin/hook output < .git-payload.json"], cwd=w).stdout
    big = "\n".join('line %d "quoted" \\ back\tslash \x1b[31mred\x1b[0m' % i for i in range(4000))
    out = post(big)
    data = json.loads(out)["hookSpecificOutput"]["updatedToolOutput"]
    expect(len(data["stdout"]) < 12000 and "line 0 " in data["stdout"] and "line 3999 " in data["stdout"],
           "head and tail survive, the middle does not: %d chars" % len(data["stdout"]))
    log = data["stdout"].split("Full output: ")[1].split(". ")[0]
    expect(Path(w, log).exists() or Path(log).exists(), "the full output is saved: " + log)
    expect(data["stderr"] == "warn" and data["interrupted"] is False, "the other fields are kept")
    expect(post("short output") == "", "small outputs pass untouched")
    expect(post(big, command="UAK_RAW=1 pytest -q") == "", "UAK_RAW=1 opts out")
    (w / ".uak/PROJECT.md").write_text("Mode: sprint\nOutput-Cap-Chars: off\n", encoding="utf-8")
    expect(post(big) == "", "Output-Cap-Chars: off disables it")
    return {"from_chars": len(big), "to_chars": len(data["stdout"])}


def guard_prose_and_clock(r):
    f = r.fixture("v42-guard", count=1)
    w = f.worktrees[0]
    g = lambda c: r.run([r.bash, ".uak/bin/guard", "check", c], cwd=w, allowed=None).returncode
    expect(g('codex exec "Never cat .env; read .env.example only"') == 0, "a safety rule inside a prompt is not a .env read")
    expect(g('cat .env') == 2 and g('cat ".env"') == 2 and g("grep KEY '.env'") == 2, "real .env reads stay blocked")
    expect(g('bash -c "cat .env && echo done now"') == 2, "code run through bash -c is still checked")
    out = r.run([r.bash, ".uak/bin/uak", "clock", "2026-10-09 23:00", "2026-10-10 03:00", "UTC", "--write"], cwd=w).stdout
    deadline = int(datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc).timestamp())
    expect("Freeze-Epoch: %d" % (deadline - 2160) in out and "SHORT EVENT" in out, "4 h event: freeze 36 min before: " + out)
    expect("Freeze-Epoch: %d" % (deadline - 2160) in (w / ".uak/PROJECT.md").read_text(encoding="utf-8"), "--write sets it")
    long = r.run([r.bash, ".uak/bin/uak", "clock", "2026-10-10 09:00", "2026-10-12 09:00", "UTC"], cwd=w).stdout
    end = int(datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc).timestamp())
    expect("Freeze-Epoch: %d" % (end - 21600) in long, "48 h event keeps the 6 h cap: " + long)
    return {"prose": True, "clock": True}


def blackbox_dedupe_and_harness(r):
    f = r.fixture("v42-bb", count=1)
    config(f)
    w = f.worktrees[0]
    line = "- 2026-10-10T02:35Z | v4.2.0 | codex | sprint | auto | exit3 | uak claim | CONFLICT: FREEZE | fix: -\n"
    (common(f) / "uak-blackbox.pending").write_text(line * 3, encoding="utf-8")
    r.run([r.bash, ".uak/bin/uak", "bb", "flush"], cwd=w)
    body = "".join(f.show(p) for p in f.files("blackbox/") if p.endswith(".md"))
    expect(body.count("CONFLICT: FREEZE") == 1 and "(x3)" in body, "identical lines are published once with a count: " + body)
    (gitdir(f) / "uak-harness").write_text("codex\n", encoding="utf-8")
    h = r.run([r.bash, ".uak/bin/bb", "harness"], cwd=w, env={"UAK_HARNESS": ""}).stdout.strip()
    expect(h == "codex", "the harness recorded at session start is reused: " + h)
    return {"dedupe": "x3", "harness": h}


def output_cap_cursor_and_codex(r):
    """A teammate on Cursor: "tool calling hogs the whole context". Cursor and Codex get the cap too."""
    f = r.fixture("v42-cap", count=1)
    w = f.worktrees[0]
    (w / "src").mkdir(exist_ok=True)
    def hook(mode, payload, *extra):
        (w / ".git-payload.json").write_text(json.dumps(payload), encoding="utf-8")
        return r.run([r.bash, "-c", "bash .uak/bin/hook " + mode + " " + " ".join(extra) + " < .git-payload.json"], cwd=w).stdout
    shell = lambda cmd: {"hook_event_name": "preToolUse", "conversation_id": "c1", "tool_name": "Shell",
                         "tool_input": {"command": cmd, "working_directory": str(w)}}
    noisy = "find . -name nothing; seq 1 20000 1>&2; cd src && export UAKT=5; false"
    out = json.loads(hook("wrap", shell(noisy)))
    expect(out["permission"] == "allow" and out["updated_input"]["working_directory"] == str(w), "Cursor gets updated_input: " + str(out))
    ran = r.run([r.bash, "-c", out["updated_input"]["command"] + '\necho "rc=$? dir=$(basename "$PWD") v=$UAKT"'], cwd=w, allowed=None).stdout
    lines = ran.splitlines()
    expect("[uak: " in ran and "20000" in ran and len(lines) < 120, "the output is head + tail + log path: %d lines" % len(lines))
    expect(lines[-1] == "rc=1 dir=src v=5", "exit code, cd and export survive the wrap: " + lines[-1])
    small = json.loads(hook("wrap", shell("git status --short")))["updated_input"]["command"]
    expect(r.run([r.bash, "-c", small], cwd=w).stdout == r.run([r.bash, "-c", "git status --short"], cwd=w).stdout,
           "a small output prints unchanged")
    for skip in ["npm run dev", "pytest &", "echo hi", "cat .env && pytest", "UAK_RAW=1 pytest"]:
        expect(hook("wrap", shell(skip)) == "", "not wrapped: " + skip)
    big = "\n".join("test %d passed" % i for i in range(5000))
    for resp in (big, {"stdout": big, "stderr": "", "exit_code": 0}):
        codex = {"session_id": "s", "turn_id": "t", "hook_event_name": "PostToolUse", "tool_name": "Bash",
                 "tool_input": {"command": "pytest"}, "tool_response": resp}
        d = json.loads(hook("output", codex, "codex"))
        expect(d["decision"] == "block" and "test 0 passed" in d["reason"] and "test 4999 passed" in d["reason"]
               and len(d["reason"]) < 12000, "Codex: the result is replaced by head + tail + log path")
    tiny = {"session_id": "s", "turn_id": "t", "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_input": {"command": "pytest"}, "tool_response": "1 passed"}
    expect(hook("output", tiny, "codex") == "", "Codex: small results pass untouched")
    return {"cursor_lines": len(lines)}


def review_lock_wait_and_contracts(r):
    """Parallel reviews of one SHA, merges before any review, superseded contracts, the pre-freeze warning."""
    f = rm.fixture(r, "v42-lock", count=2)
    tip = rm.ready(f, 0, "HACK-001")
    rm.actor(f, "lead-human", "register-reviewer", "judge", "judge-2", human=True)
    early = f.hack(0, "merge", "HACK-001", now=1000015, allowed=None)
    expect(early.returncode == 3 and "MERGE_WAIT" in early.stdout and "nothing was queued" in early.stdout,
           "merge before any review waits instead of going to humans: " + early.stdout + early.stderr)
    expect("Merge of HACK-001 in human queue" not in f.show("inbox/log.md"), "no human-queue message")
    one = rm.actor(f, "judge", "review", "HACK-001", "--start", now=1000020)
    expect("OK review --start HACK-001" in one.stdout, one.stdout + one.stderr)
    two = rm.actor(f, "judge-2", "review", "HACK-001", "--start", now=1000021, allowed=None)
    expect(two.returncode == 3 and "judge is already reviewing" in two.stderr, "a second reviewer is turned away: " + two.stderr)
    rm.approve(f, "HACK-001", tip, now=1000030)
    expect("reviews/HACK-001.reviewing" not in f.files("reviews/"), "the verdict releases the review lock")
    three = rm.actor(f, "judge-2", "review", "HACK-001", "--start", now=1000031)
    expect("SKIP review HACK-001" in three.stdout, "an approved SHA needs no reviewer: " + three.stdout)
    late = rm.ready(f, 1, "HACK-002")
    rm.actor(f, "judge", "review", "HACK-002", "--start", now=1000040)
    expired = rm.actor(f, "judge-2", "review", "HACK-002", "--start", now=1000040 + 1300)
    expect("OK review --start" in expired.stdout, "an expired review lock can be taken over")
    integ = f.hack(1, "integrate", "HACK-001", now=1000050, allowed=None)
    expect(integ.returncode == 3, "integrate refuses a task not in REVIEW")

    g = r.fixture("v42-contract", count=2, dependencies={"HACK-001": "ninguna (contract with HACK-002)"})
    config(g, Freeze_Epoch="1000600")
    g.claim(0, "HACK-001"); g.claim(1, "HACK-002")
    hack(g, 0, "msg", "related:HACK-001", "--kind", "contract", "--task", "HACK-001", "POST /x body {a}", now=1000001)
    hack(g, 0, "msg", "related:HACK-001", "--kind", "contract", "--task", "HACK-001", "POST /x body {a, b} FINAL", now=1000002)
    inbox = hack(g, 1, "inbox", now=1000003).stdout
    expect("FINAL" in inbox and "body {a}" not in inbox, "only the current contract is shown: " + inbox)
    thread = hack(g, 1, "inbox", "--task", "HACK-002", now=1000004).stdout
    expect("superseded by #" in thread and "body {a}" in thread, "the thread keeps the old one, marked: " + thread)
    nxt = hack(g, 1, "next", now=1000000 + 600 - 540).stdout
    expect("FREEZE in 9 min" in nxt, "30 min before the freeze, next warns: " + nxt)
    return {"lock": True, "merge_wait": True, "superseded": True}


TESTS = [scope_uses_current_base, freeze_next_and_allow, one_identity_one_task, messages_without_noise, reviews_once,
         repeated_reads_and_loops, huge_output_is_capped, guard_prose_and_clock, blackbox_dedupe_and_harness,
         output_cap_cursor_and_codex, review_lock_wait_and_contracts]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-v42-") as tmp:
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
    print("V42_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
