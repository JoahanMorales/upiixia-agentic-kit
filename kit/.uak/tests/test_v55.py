#!/usr/bin/env python3
"""uak v5.5: the Hacktoberfest autopsy (Oct 2026): 5 humans, 13 identities on macOS and Windows (Claude Code and
Codex), 35 tasks overnight. One test per kit failure seen there: review offers to a human whose name the Mac file
system folded, a reject erased by another reviewer's approve, a verdict over a held review, gate false positives,
and errors that did not say the whole command. Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import os
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm
from test_v43 import push_main


def write_claims(f, files, message):
    """Commit files straight onto the claims branch, as another machine would have pushed them."""
    work = f.base / ("claims-edit-%d" % time.monotonic_ns())
    f.r.g(f.base, "clone", "-q", "--branch", "claims", str(f.remote), str(work))
    for rel, text in files.items():
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        f.r.g(work, "add", rel)
    f.r.g(work, "commit", "-q", "-m", message)
    f.r.g(work, "push", "-q", "origin", "claims")


def offers_skip_a_human_the_mac_folded(r):
    """22 review offers went to a human's name: on macOS meta/agents/Ana.md opened the ana.md already there, so
    `Role: human` was recorded for "ana" while the human signed "Ana". Each offer waited 15 min."""
    f = rm.fixture(r, "v55-folded", count=2)
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")
    log = f.show("inbox/log.md").rstrip("\n") if "inbox/log.md" in f.files("inbox") else "# Agent messages\n"
    write_claims(f, {
        "meta/agents/boss.md": "# boss\nAgent: boss\nStarted: 1000001\nRole: human\nUpdated: 1000006\n",
        "inbox/log.md": log + "\n- 900 | 1000006 | Boss | all | info | - | Backlog: new tasks published by Boss.\n",
    }, "a Mac wrote the human's file under its folded name")
    rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance", now=1000010)
    offer = [l for l in f.show("inbox/log.md").splitlines() if "| review | HACK-001 |" in l][-1]
    expect("agent:Boss" not in offer and "| agent:agent-2 |" in offer, "the offer skips the human: " + offer)
    return {"reviewer": "agent-2"}


def a_reject_stands_until_a_new_commit(r):
    """HACK-018 was rejected for a real SSE bug; 15 min later another reviewer approved the same SHA, the approve
    replaced the reject, the task merged, and the bug surfaced 10 h later in the end-to-end test."""
    f = rm.fixture(r, "v55-reject", count=1)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.actor(f, "human-registrar", "register-reviewer", "judge2", human=True)
    rm.approve(f, "HACK-001", tip, verdict="reject", now=1000021)
    over = rm.approve(f, "HACK-001", tip, name="judge2", now=1000040, allowed=None)
    expect(over.returncode == 3 and "rejected HACK-001 at this SHA" in over.stderr, over.stdout + over.stderr)
    expect("Verdict: reject" in f.show("reviews/HACK-001.md"), "the reject stays on record")
    again = rm.approve(f, "HACK-001", tip, now=1000050, allowed=None)
    expect(again.returncode == 0 and "Verdict: approve" in f.show("reviews/HACK-001.md"), "the rejecter may change it: " + again.stderr)
    return {"reject": "kept"}


def a_held_review_takes_no_other_verdict(r):
    """`review --start` said CONFLICT (someone else held it), the reviewer's chained command still sent its approve,
    and it was recorded while the holder was reviewing."""
    f = rm.fixture(r, "v55-held", count=1)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.actor(f, "human-registrar", "register-reviewer", "judge2", human=True)
    rm.actor(f, "judge2", "review", "HACK-001", "--start", now=1000030)
    late = rm.approve(f, "HACK-001", tip, now=1000040, allowed=None)
    expect(late.returncode == 3 and "judge2 is reviewing HACK-001" in late.stderr, late.stdout + late.stderr)
    expect("Verdict" not in f.show("reviews/HACK-001.md") if "reviews/HACK-001.md" in f.files("reviews") else True, "nothing recorded")
    after = rm.approve(f, "HACK-001", tip, now=1000040 + 1300, allowed=None)
    expect(after.returncode == 0, "an expired hold no longer blocks: " + after.stderr)
    return {"held": True}


def gate_takes_fixtures_and_gives_a_port(r):
    """HACK-012's test repo had supabase/migrations/*.sql under app/fixtures/ and went to the human queue as a
    shared resource; HACK-029's approved e2e Verify failed in the gate with "no UAK_PORT" (main checkout)."""
    f = rm.fixture(r, "v55-gate", count=1)
    sql = "app/fixtures/bad/supabase/migrations/init.sql"
    tasks = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8")
    start = tasks.index("## HACK-001"); end = tasks.find("\n## ", start + 1); end = len(tasks) if end < 0 else end
    section = tasks[start:end]
    section = section.replace("- **Paths:** src/value-1.txt", "- **Paths:** src/value-1.txt, app/fixtures/")
    section = section.replace('test "$(cat src/value-1.txt)" = ready-HACK-001',
                              'test "$(cat src/value-1.txt)" = ready-HACK-001 && test "$UAK_PORT" -ge 9100')
    push_main(f, {".uak/TASKS.md": tasks[:start] + section + tasks[end:]}, "HACK-001 owns app/fixtures and checks its port")
    for wt in f.worktrees:
        r.g(wt, "reset", "--hard", "origin/main")
    f.claim(0, "HACK-001")
    target = f.worktrees[0] / sql
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("create table t (id int);\n", encoding="utf-8")
    r.g(f.worktrees[0], "add", sql)
    tip = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance", now=1000010)
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    merged = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    out = merged.stdout + merged.stderr
    expect(merged.returncode == 0 and "INTEGRATED" in out and "Shared resource" not in out, out)
    return {"merged": True}


def a_carried_file_names_its_task(r):
    """HACK-010 merged HACK-002's branch before HACK-002 integrated; the gate said "New file outside Paths:
    app/fixtures/demo/run.jsonl" and sent it to the human, with nothing about whose file it was."""
    f = rm.fixture(r, "v55-carried", count=2)
    f.claim(1, "HACK-002")
    rm.publish(f, 1, "HACK-002")
    f.claim(0, "HACK-001")
    r.g(f.worktrees[0], "fetch", "-q", "origin", f.branches[1])
    r.g(f.worktrees[0], "merge", "--no-edit", "-q", "FETCH_HEAD")
    tip = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance", now=1000010)
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    merged = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    out = merged.stdout + merged.stderr
    expect("src/value-2.txt belongs to HACK-002" in out and "Merge HACK-002 first" in out, out)
    return {"carried": True}


def errors_name_the_whole_command(r):
    """`done` failed 3 times in a row (first --pr, then --evidence); `status --task` said AVAILABLE for a task whose
    claim had landed, and `wt new` then failed; claims of blocked tasks were retried 14 times in 40 min."""
    f = rm.fixture(r, "v55-errors", count=2)
    f.claim(0, "HACK-001")
    bare = f.hack(0, "done", "HACK-001", allowed=None)
    expect(bare.returncode == 2 and "--pr HTTPS URL and --evidence" in bare.stderr and
           "uak done HACK-001 --pr URL --evidence" in bare.stderr, bare.stderr)
    write_claims(f, {"claims/HACK-009.md": "# HACK-009\nID: HACK-009\nState: CLAIMED\nOwner: agent-9\n"
                     "Branch: feat/hack-009\nWorktree: /elsewhere/hack-009\nPaths: src/value-2.txt\nLease-Until: 9999999\n"},
                 "a claim in flight, on HACK-002's file")
    st = f.hack(1, "status", "--task", "HACK-009", allowed=None)
    expect("HACK-009 | CLAIMED | agent-9" in st.stdout and "AVAILABLE" not in st.stdout, st.stdout + st.stderr)
    over = f.claim(1, "HACK-002", allowed=None)
    expect(over.returncode == 3 and "uak wait HACK-009 --for integrated" in over.stderr, over.stderr)
    return {"errors": True}


def wt_stop_finds_a_windows_listener(r):
    """Codex on Windows: `wt stop` said "nothing listening" while the task's API kept serving (Git Bash has no lsof
    or ss). netstat is on every Windows; its state word is localized, so it is not what we match."""
    wt = (r.package / ".uak/bin/wt").read_text(encoding="utf-8")
    funcs = wt[wt.index("wt_windows()"):wt.index("kill_pid()")]
    shims = r.scratch / "v55-netstat"; shims.mkdir(parents=True, exist_ok=True)
    (shims / "uname").write_text("#!/bin/sh\necho MINGW64_NT-10.0\n", encoding="utf-8")
    (shims / "netstat").write_text("#!/bin/sh\nprintf '%s\\r\\n' "
        "'  Proto  Local  Remote  Estado  PID' "
        "'  TCP    0.0.0.0:8100     0.0.0.0:0        ESCUCHANDO   4242' "
        "'  TCP    127.0.0.1:8100   127.0.0.1:51000  ESTABLISHED  4242' "
        "'  TCP    0.0.0.0:18100    0.0.0.0:0        LISTENING    999' "
        "'  TCP    [::]:8101        [::]:0           LISTENING    5151'\n", encoding="utf-8")
    for s in ("uname", "netstat"):
        os.chmod(shims / s, 0o755)
    script = funcs + '\nprintf "%s|" $(port_pids 8100); printf "%s|" $(port_pids 8101)\n'
    env = dict(os.environ, PATH=str(shims) + os.pathsep + os.environ.get("PATH", ""))
    out = subprocess.run([r.bash, "-c", script], env=env, capture_output=True, text=True, timeout=30).stdout
    expect(out == "4242|5151|", "listeners on 8100 and 8101 only: " + out)
    return {"pids": out}


def rules_cover_the_holes(r):
    """The pipeline looked up `run_stage` in 8 service modules and no task wrote one: every run replayed the same
    recorded project, whatever the judge typed. `.env.example` (no secrets) was unreadable to agents."""
    sprint = (r.package / ".uak/modes/sprint.md").read_text(encoding="utf-8")
    expect("A contract with no task behind it is a hole" in sprint and "A fallback to the recording is a fallback" in sprint, "sprint rules")
    demo = (r.package / ".claude/commands/uak-demo.md").read_text(encoding="utf-8")
    expect("NOT in the fixtures" in demo, "the rehearsal tries an input of its own")
    for mode in ("sprint", "marathon"):
        s = (r.package / (".uak/settings/settings.%s.json" % mode)).read_text(encoding="utf-8")
        expect("Read(./.env.*)" not in s and "Read(./.env.local)" in s and "Read(./.env)" in s, mode + ": .env.example readable")
    expect("--add-dir" in (r.package / ".uak/bin/wt").read_text(encoding="utf-8"), "wt new tells Codex about the shared .git")
    return {"rules": True}


def doctor_repairs_a_checkout_made_bare(r):
    """uak-mcp 5.4.5-5.5.0, started through its git alias in a task worktree, inherited GIT_DIR and its temp
    `git init` set core.bare=true on the main repository: every git command there failed, and doctor said
    "not a Git repository"."""
    t = r.scratch / "v55-bare"; t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.g(t, "config", "core.bare", "true")
    doctor = str(r.package / ".uak/bin/doctor")
    seen = subprocess.run([r.bash, doctor], cwd=t, env=r.env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    expect(seen.returncode == 1 and "core.bare=true on a checkout" in seen.stdout and "config core.bare false" in seen.stdout, seen.stdout + seen.stderr)
    fixed = subprocess.run([r.bash, doctor, "--fix"], cwd=t, env=r.env, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    expect("core.bare=false restored" in fixed.stdout, fixed.stdout + fixed.stderr)
    expect(r.g(t, "config", "core.bare").stdout.strip() == "false", "the checkout works again")
    return {"bare": "repaired"}


TESTS = [offers_skip_a_human_the_mac_folded, a_reject_stands_until_a_new_commit, a_held_review_takes_no_other_verdict,
         gate_takes_fixtures_and_gives_a_port, a_carried_file_names_its_task, errors_name_the_whole_command,
         wt_stop_finds_a_windows_listener, rules_cover_the_holes, doctor_repairs_a_checkout_made_bare]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v55-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("V55_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
