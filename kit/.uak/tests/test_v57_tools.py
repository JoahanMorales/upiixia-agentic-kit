#!/usr/bin/env python3
"""uak v5.7 tools: what the v5.6 audit and the Hacktoberfest second autopsy left open in guard, hook, wt and loop.
Human authority and the clock set from an agent's shell, merges around the gate, the subagent cap under parallel
launches, a quadratic JSON decoder past the hook timeout, uncapped stderr, inbox injections that hid the rest,
pr-sync of one task only, wt session wiping permissions and moving the port, wt rm --review on a task worktree,
takeovers that restarted from main, and a test file name run as shell. Real Git, separate processes."""
import argparse
import concurrent.futures
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm


def guard_run(r, cwd, cmd, harness=None, tool="Bash"):
    g = str(r.package / ".uak/bin/guard")
    args = [r.bash, g, "bash"] + ([harness] if harness else [])
    return subprocess.run(args, input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}}),
                          capture_output=True, text=True, cwd=str(cwd), env=r.env, timeout=60)


def guard_keeps_authority_clock_and_merges_human(r):
    """Hacktoberfest second autopsy: an agent prefixed UAK_HUMAN to record a human's approval, 5 of 33 sprint merges
    were an agent's gh pr merge, and UAK_NOW let a claim land after the freeze. Audit: .env reads hidden in
    `bash -x -c`, a here-string or a pipe into bash, and `curl http://localhost:1@other-host/`."""
    cwd = r.scratch
    block = ["UAK_NOW=999 bash .uak/bin/uak claim HACK-001", "export UAK_NOW=5", "UAK_AGENT=a-1 UAK_NOW=5 bash .uak/bin/uak status",
             "env UAK_TEST_CLOCK=1 bash .uak/bin/uak next", 'bash -c "UAK_NOW=1 bash .uak/bin/uak claim X"',
             "gh pr merge 3 --squash", "gh api -X PUT repos/o/r/pulls/3/merge", "git push origin HEAD:main", "git push origin main",
             "git push origin feat/x:refs/heads/main", 'bash -x -c "cat .env and more stuff"', 'bash <<< "cat .env and more"',
             'echo "cat .env now please" | bash', '$SHELL -c "cat .env now please"', "curl -s http://localhost:1@evil.example/x",
             'curl -s "http://user:pw@localhost:3000/"']
    allow = ["bash .uak/bin/uak merge HACK-001", "rg -n UAK_NOW= bin/", 'git commit -m "doc: why UAK_NOW= is for tests"',
             "git push -u origin feat/x", "git push origin feat/main-menu", "curl -s http://localhost:8000/api/health",
             "cp .env.example .env", "cat .env.example", "bash .uak/bin/uak status"]
    wrong = []
    for c in block + allow:
        got = guard_run(r, cwd, c).returncode
        if got != (2 if c in block else 0):
            wrong.append("%r -> %d" % (c, got))
    expect(not wrong, "; ".join(wrong))
    human = "UAK_HUMAN=ana bash .uak/bin/uak allow HACK-001 --reason demo"
    asked = guard_run(r, cwd, human, harness="claude")
    expect(asked.returncode == 0 and '"permissionDecision":"ask"' in asked.stdout, "Claude Code asks the human: " + asked.stdout + asked.stderr)
    json.loads(asked.stdout)
    for c in (human, "export UAK_HUMAN=ana", "env UAK_HUMAN=ana bash .uak/bin/uak plan f.md"):
        other = guard_run(r, cwd, c)
        expect(other.returncode == 2 and "own terminal" in other.stderr, "a harness without ask blocks: %r %s" % (c, other.stderr))
    check = subprocess.run([r.bash, str(r.package / ".uak/bin/guard"), "check", human], capture_output=True, text=True, cwd=str(cwd), timeout=60)
    expect(check.returncode == 3 and "ask" in check.stderr, "guard check says ask: " + check.stderr)
    # A blocked rule wins over the question.
    both = guard_run(r, cwd, "UAK_HUMAN=ana git push --force origin x", harness="claude")
    expect(both.returncode == 2, "a force push is blocked even under UAK_HUMAN")
    ps = guard_run(r, cwd, "git push --force origin x", tool="PowerShell")
    expect(ps.returncode == 2, "Claude Code's PowerShell tool is guarded")
    for mode in ("sprint", "marathon"):
        s = json.loads((r.package / (".uak/settings/settings.%s.json" % mode)).read_text(encoding="utf-8"))
        pre = [h for h in s["hooks"]["PreToolUse"] if "guard" in json.dumps(h) and "agent" not in json.dumps(h)][0]
        expect(pre["matcher"] == "Bash|PowerShell" and pre["hooks"][0]["command"].endswith("bash claude"), mode + ": " + json.dumps(pre))
        post = [h for h in s["hooks"]["PostToolUse"] if "output" in json.dumps(h)][0]
        expect(post["matcher"] == "Bash|PowerShell", mode + " output cap on PowerShell")
        expect("Bash(gh pr merge:*)" not in s["permissions"]["allow"] and "Bash(gh pr merge:*)" in s["permissions"]["deny"], mode + ": gh pr merge denied")
    return {"guard": True}


def subagent_cap_holds_under_parallel_launches(r):
    """Audit: 12 concurrent subagent launches with Max-Parallel 4 let 6 through and lost reservations (read, check
    and append had no lock)."""
    g = str(r.package / ".uak/bin/guard")
    def repo(name):
        t = r.scratch / name; t.mkdir()
        r.g(t, "init", "-q", "-b", "main")
        (t / ".uak").mkdir()
        (t / ".uak/PROJECT.md").write_text("Mode: sprint\nMax-Parallel-Subagents: 4\nSubagent-Burst-Per-Minute: 99\nSubagents-Per-Machine: 99\n", encoding="utf-8")
        return t
    def launch(t, i):
        payload = json.dumps({"tool_name": "Agent", "session_id": "s%d" % i, "tool_input": {"subagent_type": "uak-scout"}})
        return subprocess.run([r.bash, g, "agent"], input=payload, capture_output=True, text=True, cwd=str(t), env=r.env, timeout=60).returncode
    seq = repo("v57-cap-seq")
    cap = sum(1 for i in range(12) if launch(seq, i) == 0)
    expect(1 <= cap < 12, "a cap applies: %d" % cap)
    par = repo("v57-cap-par")
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        codes = list(pool.map(lambda i: launch(par, i), range(12)))
    allowed = codes.count(0)
    active = (par / ".git/uak-agents.active").read_text(encoding="utf-8").splitlines()
    expect(allowed == cap and len(active) == cap, "parallel launches respect the cap: %d allowed, %d active, cap %d" % (allowed, len(active), cap))
    expect(not (par / ".git/uak-agents.lock").exists(), "the lock is released")
    return {"cap": cap}


def stub_project(r, name, inbox_lines=None, review_tasks=()):
    """A git repo with the real hook and a stub uak: inbox --peek prints INBOX, status --full lists REVIEW tasks,
    every call is logged. Nothing else of the kit runs."""
    t = r.scratch / name; t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.g(t, "remote", "add", "origin", str(t / "nowhere.git"))
    b = t / ".uak/bin"; b.mkdir(parents=True)
    shutil.copy2(r.package / ".uak/bin/hook", b / "hook")
    shutil.copy2(r.package / ".uak/bin/cap", b / "cap")
    (t / ".uak/PROJECT.md").write_text("Mode: sprint\n", encoding="utf-8")
    (t / "inbox.txt").write_text("\n".join(inbox_lines or []) + ("\n" if inbox_lines else ""), encoding="utf-8")
    status = "".join("%s | REVIEW | agent-1 | feat/x | - \n" % tid for tid in review_tasks)
    (t / "status.txt").write_text(status + "HACK-009 | REVIEW | bob-1 | feat/y | - \n", encoding="utf-8")
    (b / "uak").write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$(git rev-parse --show-toplevel)/calls.log"\n'
                           'case "$1 ${2:-}" in "inbox --peek") cat "$(git rev-parse --show-toplevel)/inbox.txt";; '
                           '"status --full") cat "$(git rev-parse --show-toplevel)/status.txt";; esac\nexit 0\n', encoding="utf-8")
    for s in ("pace", "map", "bb", "tokens"):
        (b / s).write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    return t


def requests(n):
    out = []
    for i in range(1, n + 1):
        out += ["#%d · 1m ago · bob-1 → agent:agent-1 · request · HACK-001" % i, "  please change line %d" % i]
    return out


def hook(r, t, event, payload, env=None):
    e = {"UAK_AGENT": "agent-1", "UAK_POLL_SECONDS": "999999", "UAK_COACH": "off", "UAK_LENS": "off"}
    e.update(env or {})
    return r.run([r.bash, ".uak/bin/hook", event], cwd=t, env=e, allowed=None) if payload is None else \
        subprocess.run([r.bash, ".uak/bin/hook", event], input=json.dumps(payload), capture_output=True, text=True, cwd=str(t),
                       env={**r.env, **e}, timeout=120)


def injections_say_what_is_left(r):
    """Audit: 15 requests, the tick injected 12 and marked all 15 seen; session start printed 10 and marked all.
    The other messages never reached the agent."""
    t = stub_project(r, "v57-inject", requests(15))
    gd = t / ".git"
    (gd / "uak-inbox.poll").write_text(str(int(time.time())), encoding="utf-8")
    shutil.copy2(t / "inbox.txt", gd / "uak-inbox.txt")
    tick = {"session_id": "s", "tool_name": "Read", "tool_input": {"file_path": "x"}}
    one = hook(r, t, "tick", tick)
    ctx = json.loads(one.stdout)["hookSpecificOutput"]["additionalContext"]
    expect("#12 " in ctx and "#13 " not in ctx and "+3 more" in ctx, "the first tick names the rest: " + ctx[-300:])
    expect((gd / "uak-inbox.shown-n").read_text(encoding="utf-8").strip() == "12", "shown-n is the last injected")
    two = hook(r, t, "tick", tick)
    ctx2 = json.loads(two.stdout)["hookSpecificOutput"]["additionalContext"]
    expect("#13 " in ctx2 and "#15 " in ctx2 and "#12 " not in ctx2, "the next tick brings the rest: " + ctx2[-300:])
    (gd / "uak-inbox.shown-n").unlink()
    start = hook(r, t, "session-start", {"session_id": "s2", "source": "startup"})
    shown = (gd / "uak-inbox.shown-n").read_text(encoding="utf-8").strip()
    expect("more: uak inbox" in start.stdout and shown != "15" and ("#%s " % shown) in start.stdout,
           "session start marks only what it printed (%s): %s" % (shown, start.stdout[-400:]))
    return {"shown": shown}


def pr_sync_follows_every_review_task(r):
    """Hacktoberfest second autopsy: pr-sync followed only the worktree's task, so one pr-sync in 16 h; a PR merged
    on GitHub stayed in REVIEW for 14 min."""
    t = stub_project(r, "v57-prsync", review_tasks=("HACK-001", "HACK-002"))
    (t / ".uak-env").write_text("UAK_AGENT=agent-1\nUAK_TASK=HACK-003\n", encoding="utf-8")
    gh = t / "gh"; gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8"); os.chmod(gh, 0o755)
    hook(r, t, "tick", {"session_id": "s", "tool_name": "Read", "tool_input": {"file_path": "x"}}, env={"UAK_GH": str(gh)})
    deadline = time.monotonic() + 20
    calls = ""
    while time.monotonic() < deadline:
        calls = (t / "calls.log").read_text(encoding="utf-8") if (t / "calls.log").exists() else ""
        if all("pr-sync %s" % x in calls for x in ("HACK-001", "HACK-002", "HACK-003")):
            break
        time.sleep(0.2)
    expect(all("pr-sync %s" % x in calls for x in ("HACK-001", "HACK-002", "HACK-003")) and "pr-sync HACK-009" not in calls,
           "every REVIEW task of this identity: " + calls)
    return {"synced": 3}


def output_cap_is_linear_and_counts_stderr(r):
    """Audit: the JSON decoder took 70 s on a 1.3 MB output (hook timeout 10 s: the whole output reached the model),
    and 150 KB of warnings on stderr were never capped."""
    t = stub_project(r, "v57-output")
    text = "".join('line %d "quoted" \\ tab\there C:\\Users\\x\n' % i for i in range(32000))
    payload = {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "pytest -q"},
               "tool_response": {"stdout": text, "stderr": "", "interrupted": False}}
    started = time.monotonic()
    big = hook(r, t, "output", payload)
    took = time.monotonic() - started
    out = json.loads(big.stdout)["hookSpecificOutput"]["updatedToolOutput"]
    # About 2.6 s alone (the quadratic decoder took 75 s); a loaded runner with 8 suites in parallel took 10.5 s.
    expect(len(json.dumps(payload)) > 1200000 and took < 25 and "[uak:" in out["stdout"], "%.1f s for %d bytes" % (took, len(json.dumps(payload))))
    logs = sorted((t / ".git/uak-out").glob("*.log"))
    expect(logs and logs[-1].read_text(encoding="utf-8") == text, "the full output is kept byte for byte")
    payload["tool_response"] = {"stdout": "ok\n", "stderr": "warning: unused variable\n" * 6000, "interrupted": False}
    err = hook(r, t, "output", payload)
    o2 = json.loads(err.stdout)["hookSpecificOutput"]["updatedToolOutput"]
    expect(o2["stdout"].strip() == "ok" and "[uak:" in o2["stderr"] and len(o2["stderr"]) < 40000, "stderr is capped: %d" % len(o2["stderr"]))
    payload["tool_response"] = {"stdout": "x" * 9000, "stderr": "y" * 3500, "interrupted": False}
    expect(hook(r, t, "output", payload).stdout == "", "nothing to cut is left alone")
    return {"seconds": round(took, 2)}


def wt_new(r, f, index, task, agent):
    return r.run([r.bash, ".uak/bin/wt", "new", task, "--agent", agent], cwd=f.clones[index], allowed=None)


def wt_session_keeps_port_and_permissions(r):
    """Audit: wt session moved UAK_PORT off the worktree's own running server (orphaning it) and rewrote
    .claude/settings.local.json, where Claude Code keeps "don't ask again" permissions."""
    f = r.fixture("v57-session", count=1)
    made = wt_new(r, f, 0, "HACK-001", "ana-1")
    expect(made.returncode == 0, made.stdout + made.stderr)
    w = f.base / "agent-1-wt/hack-001"
    env_file = w / ".uak-env"
    port = [l.split("=", 1)[1] for l in env_file.read_text(encoding="utf-8").splitlines() if l.startswith("UAK_PORT=")][0]
    session = [l for l in env_file.read_text(encoding="utf-8").splitlines() if l.startswith("UAK_SESSION=")][0]
    local = w / ".claude/settings.local.json"
    data = json.loads(local.read_text(encoding="utf-8"))
    data["permissions"] = {"allow": ["Bash(npm test:*)"]}
    local.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("127.0.0.1", int(port))); srv.listen(1)
        time.sleep(1.1)  # a new session id (it carries the second)
        r.run([r.bash, ".uak/bin/wt", "session"], cwd=w)
    finally:
        srv.close()
    after = env_file.read_text(encoding="utf-8")
    expect("UAK_PORT=%s\n" % port in after and session not in after, "same port, new session: " + after)
    kept = json.loads(local.read_text(encoding="utf-8"))
    expect(kept["permissions"] == {"allow": ["Bash(npm test:*)"]} and kept["env"]["UAK_PORT"] == port, json.dumps(kept))
    # A pre-v5.1 file named UAK_HUMAN there: it granted human authority in the worktree.
    local.write_text('{\n  "env": {"UAK_AGENT": "ana-1", "UAK_HUMAN": "ana"},\n  "model": "sonnet"\n}\n', encoding="utf-8")
    r.run([r.bash, ".uak/bin/wt", "session"], cwd=w)
    old = json.loads(local.read_text(encoding="utf-8"))
    expect("UAK_HUMAN" not in old["env"] and old["env"].get("UAK_AGENT_HUMAN") and old["model"] == "sonnet", json.dumps(old))
    return {"port": port}


def wt_rm_review_spares_task_worktrees(r):
    """Audit: `wt rm --review` force-removed a task worktree whose HEAD was detached (git rebase leaves one), with
    a new untracked file in it."""
    f = r.fixture("v57-rmreview", count=1)
    expect(wt_new(r, f, 0, "HACK-001", "ana-1").returncode == 0, "wt new")
    w = f.base / "agent-1-wt/hack-001"
    (w / "feature.py").write_text("print('new work')\n", encoding="utf-8")
    r.g(w, "switch", "-q", "--detach")
    refused = r.run([r.bash, ".uak/bin/wt", "rm", "--review", str(w)], cwd=f.clones[0], allowed=None)
    expect(refused.returncode == 2 and ".uak-env" in refused.stderr and (w / "feature.py").exists(), refused.stderr)
    review = f.base / "review-HACK-001"
    r.g(f.clones[0], "worktree", "add", "-q", "--detach", review, "origin/main")
    (review / "notes.txt").write_text("x\n", encoding="utf-8")
    gone = r.run([r.bash, ".uak/bin/wt", "rm", "--review", str(review)], cwd=f.clones[0], allowed=None)
    expect(gone.returncode == 0 and "notes.txt" in gone.stdout and not review.exists(), "the dropped files are named: " + gone.stdout + gone.stderr)
    return {"refused": True}


def wt_new_continues_the_released_branch(r):
    """Hacktoberfest second autopsy: 7 takeovers started from main; one agent redid work already on
    origin/feat/hack-012."""
    f = r.fixture("v57-takeover", count=2)
    expect(wt_new(r, f, 0, "HACK-001", "ana-1").returncode == 0, "wt new")
    w = f.base / "agent-1-wt/hack-001"
    (w / "src").mkdir(exist_ok=True)
    (w / "src/one.txt").write_text("earlier work\n", encoding="utf-8")
    r.g(w, "add", "src/one.txt")
    r.g(w, "-c", "user.name=A", "-c", "user.email=a@example.invalid", "commit", "-q", "-m", "wip: earlier work")
    r.g(w, "push", "-q", "-u", "origin", "HEAD")
    r.run([r.bash, ".uak/bin/uak", "checkpoint", "HACK-001", "--done", "one.txt", "--decision", "d", "--why", "w", "--fails", "none",
           "--commands", "c", "--next", "finish"], cwd=w, allowed=None)
    rel = r.run([r.bash, ".uak/bin/uak", "release", "HACK-001"], cwd=w, allowed=None)
    expect(rel.returncode == 0, "release: " + rel.stdout + rel.stderr)
    again = wt_new(r, f, 1, "HACK-001", "bob-1")
    w2 = f.base / "agent-2-wt/hack-001"
    expect(again.returncode == 0 and "already on origin" in again.stderr, again.stdout + again.stderr)
    expect((w2 / "src/one.txt").read_text(encoding="utf-8") == "earlier work\n", "the new worktree has the earlier work")
    return {"continued": True}


def wt_pr_reads_host_aliases(r):
    """Audit: a remote through an SSH host alias (git@github.com-work:o/r.git) gave a broken compare URL."""
    t = r.scratch / "v57-pr"; t.mkdir()
    r.g(t, "init", "-q", "-b", "feat/x")
    urls = {"git@github.com-work:o/r.git": "o/r", "ssh://git@github.com:22/o/r.git": "o/r", "https://u@github.com/o/r": "o/r",
            "git@github.com:o/r.git": "o/r"}
    for url, repo in urls.items():
        r.g(t, "remote", "remove", "origin", allowed=None)
        r.g(t, "remote", "add", "origin", url)
        out = r.run([r.bash, str(r.package / ".uak/bin/wt"), "pr"], cwd=t).stdout
        expect("https://github.com/%s/compare/main...feat/x?expand=1" % repo in out, url + " -> " + out)
    return {"urls": len(urls)}


def loop_never_runs_a_file_name(r):
    """Audit: loop --parallel put file names parsed from test output into a bash -c string, so a crafted test file
    name ran as shell."""
    f = rm.fixture(r, "v57-loop", count=1)
    w = f.worktrees[0]
    marker = r.scratch / "v57-loop-PWNED"
    verify = "echo 'FAILED tests/a$(touch${IFS}%s).py::t'; exit 1" % marker
    r.run([r.bash, ".uak/bin/loop", "--verify", verify, "--parallel", "1", "--each", "echo {}", "--agent", "true", "--max", "1"],
          cwd=w, allowed=None)
    expect(not marker.exists(), "the file name was run as a command")
    return {"injected": False}


TESTS = [guard_keeps_authority_clock_and_merges_human, subagent_cap_holds_under_parallel_launches, injections_say_what_is_left,
         pr_sync_follows_every_review_task, output_cap_is_linear_and_counts_stderr, wt_session_keeps_port_and_permissions,
         wt_rm_review_spares_task_worktrees, wt_new_continues_the_released_branch, wt_pr_reads_host_aliases,
         loop_never_runs_a_file_name]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v57t-") as tmp:
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
    print("V57T_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
