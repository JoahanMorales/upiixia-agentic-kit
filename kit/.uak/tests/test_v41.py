#!/usr/bin/env python3
"""uak v4.1: black box, plan pacing, multi-harness guard and the UpiixSol fixes. Real Git, local bare remote."""
import argparse
import concurrent.futures
import json
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack
import test_review_merge as rm


def common(f, i=0):
    return Path(f.r.g(f.worktrees[i], "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())


def blackbox_records_and_publishes(r):
    f = r.fixture("v41-bb", count=2)
    config(f)
    bad = hack(f, 0, "done", "HACK-001", "unquoted", allowed=None)
    expect(bad.returncode != 0, "a bad command still fails")
    pending = common(f) / "uak-blackbox.pending"
    text = pending.read_text(encoding="utf-8")
    expect("| auto | exit" in text and "uak done" in text, "errors are recorded automatically: " + text)
    expect(str(f.base) not in text and "agent-1" not in text, "no paths or identities in the black box: " + text)
    note = r.run([r.bash, ".uak/bin/uak", "bb", "add", "friction", "wt new needs --agent twice",
                  "--fix", "read it from .uak-env"], cwd=f.worktrees[0], env={"UAK_AGENT": "agent-1"})
    expect("BB: recorded (friction)" in note.stdout, "agents add notes: " + note.stdout + note.stderr)
    secret = r.run([r.bash, ".uak/bin/uak", "bb", "add", "bug", "token ghp_" + "a" * 36],
                   cwd=f.worktrees[0], allowed=None)
    expect(secret.returncode == 2 and "secret" in secret.stderr, "lines that look like secrets are dropped")
    published = [p for p in f.files("blackbox/") if p.endswith(".md")]
    expect(published, "bb add flushes to claims:blackbox/")
    body = f.show(published[0])
    expect("wt new needs --agent twice" in body and "fix: read it from .uak-env" in body and "exit2" in body, body)
    calls = r.run([r.bash, ".uak/bin/uak", "bb", "export"], cwd=f.worktrees[1])
    exported = (f.worktrees[1] / ".uak/BLACKBOX.md").read_text(encoding="utf-8")
    expect("Top recurring" in exported and "friction" in exported, "export builds the crawlable file: " + calls.stdout)
    (f.worktrees[1] / ".uak/PROJECT.md").write_text("Mode: sprint\nBlackbox: off\n", encoding="utf-8")
    off_pending = common(f, 1) / "uak-blackbox.pending"
    before = off_pending.read_text(encoding="utf-8") if off_pending.exists() else ""
    hack(f, 1, "done", "HACK-002", "x", allowed=None)
    after = off_pending.read_text(encoding="utf-8") if off_pending.exists() else ""
    expect(before == after, "Blackbox: off records nothing")
    return {"auto": True, "agent_note": True, "secret_dropped": True, "published": published[0]}


def pace_levels_and_guard(r):
    f = r.fixture("v41-pace", count=1)
    w = f.worktrees[0]
    (w / ".uak/PROJECT.md").write_text("Mode: sprint\nMax-Parallel-Subagents: 4\nOpus-Subagents-Per-Session: 2\n", encoding="utf-8")
    now = 2000000000
    env = {"UAK_NOW": str(now), "UAK_PACE_CODEX": "0"}
    pace = lambda *a: r.run([r.bash, ".uak/bin/pace", *a], cwd=w, env=env)
    expect(pace("--caps").stdout.split()[0] == "unknown", "no data → unknown, default caps")
    surge = pace("set", "30", "--resets", "+1h").stdout
    expect("PACE surge" in surge and "parallel 8, strong 4" in surge, "1 h left, 70% left → surge: " + surge)
    cons = pace("set", "50", "--resets", "+3h").stdout
    expect("PACE conserve" in cons and "parallel 2, strong 1" in cons, "3 h left, 50% left → conserve: " + cons)
    # Claude Code statusline JSON feeds the cache; the tightest window decides.
    sl = {"context_window": {"used_percentage": 12},
          "rate_limits": {"five_hour": {"used_percentage": 96, "resets_at": now + 3600},
                          "seven_day": {"used_percentage": 20, "resets_at": now + 500000}}}
    line = r.run([r.bash, "-c", "printf '%s' \"$1\" | bash .uak/bin/statusline", "_", json.dumps(sl)], cwd=w, env=env).stdout
    expect("5h 96%" in line and "pace critical" in line, "statusline shows usage and pace: " + line)
    expect(pace("--caps").stdout.split() == ["critical", "1", "0"], "96% used → critical")
    spawn = lambda kind, model=None, extra=None: r.run(
        [r.bash, "-c", "printf '%s' \"$1\" | bash .uak/bin/guard agent", "_",
         json.dumps({"session_id": "s1", "tool_name": "Agent", "tool_input": {"subagent_type": kind, **({"model": model} if model else {})}})],
        cwd=w, env={**env, **(extra or {})}, allowed=None)
    expect(spawn("general-purpose", "haiku").returncode == 0, "critical still allows one fast subagent")
    second = spawn("general-purpose", "haiku")
    expect(second.returncode == 2 and "pace critical" in second.stderr, "critical caps parallel at 1: " + second.stderr)
    r.run([r.bash, "-c", "printf '{}' | bash .uak/bin/guard agent-stop"], cwd=w)
    strong = spawn("general-purpose", "opus")
    expect(strong.returncode == 2 and "Opus subagent budget" in strong.stderr, "critical forbids the strong tier")
    r.run([r.bash, ".uak/bin/pace", "clear"], cwd=w, env=env)
    (w / ".uak/PROJECT.md").write_text("Mode: sprint\nPace: off\n", encoding="utf-8")
    expect(pace("--caps").stdout.split()[0] == "off", "Pace: off disables pacing")
    return {"surge": True, "conserve": True, "critical_caps": [1, 0]}


def guard_every_harness(r):
    f = r.fixture("v41-harness", count=1)
    w = f.worktrees[0]
    (w / ".uak/PROJECT.md").write_text("Mode: sprint\nMax-Parallel-Subagents: 3\nOpus-Subagents-Per-Session: 1\n", encoding="utf-8")
    run = lambda mode, payload: r.run([r.bash, "-c", "printf '%s' \"$1\" | bash .uak/bin/guard " + mode, "_", json.dumps(payload)],
                                      cwd=w, env={"UAK_PACE_CODEX": "0"}, allowed=None)
    force = "cd x && git push --force origin main"
    cases = {
        "claude": ("bash", {"tool_name": "Bash", "tool_input": {"command": force}}),
        "codex": ("bash", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": force}}),
        "gemini": ("bash", {"hook_event_name": "BeforeTool", "tool_name": "run_shell_command", "tool_input": {"command": force}}),
        "cursor": ("shell", {"hook_event_name": "beforeShellExecution", "command": force, "cwd": "/x"}),
    }
    for name, (mode, payload) in cases.items():
        res = run(mode, payload)
        expect(res.returncode == 2 and "forced push" in res.stderr, name + " shell payload is guarded: " + res.stderr)
    expect(run("bash", {"tool_name": "Read", "tool_input": {"file_path": "x"}}).returncode == 0, "other tools pass")
    pk = run("shell", {"command": "pkill -f 'uvicorn --port 8220'"})
    expect(pk.returncode == 2 and "exact PIDs" in pk.stderr, "pkill -f is blocked (it killed agents' own shells)")
    (w / ".codex/agents").mkdir(parents=True, exist_ok=True)
    (w / ".codex/agents/uak-architect.toml").write_text('name = "uak-architect"\nmodel = "gpt-6-astra"\n', encoding="utf-8")
    (w / ".cursor/agents").mkdir(parents=True, exist_ok=True)
    (w / ".cursor/agents/uak-scout.md").write_text("---\nname: uak-scout\nmodel: composer-2.5\n---\n", encoding="utf-8")
    codex_start = {"hook_event_name": "SubagentStart", "session_id": "c1", "agent_type": "uak-architect", "model": "gpt-6.1-sol"}
    expect(run("agent", codex_start).returncode == 0, "first strong Codex subagent allowed")
    r.run([r.bash, "-c", "printf '{}' | bash .uak/bin/guard agent-stop"], cwd=w)
    again = run("agent", codex_start)
    expect(again.returncode == 2 and "Opus subagent budget" in again.stderr,
           "Astra counts as strong from .codex/agents (the parent model in the payload is ignored): " + again.stderr)
    cursor_start = {"hook_event_name": "subagentStart", "conversation_id": "k1", "subagent_type": "uak-scout", "model": "claude-opus-5-5"}
    expect(run("agent", cursor_start).returncode == 0, "Cursor scout on composer is fast, not strong")
    gd = Path(r.g(w, "rev-parse", "--path-format=absolute", "--git-dir").stdout.strip())
    log = (gd / "uak-agents.log").read_text(encoding="utf-8")
    expect("strong uak-architect" in log and "fast uak-scout" in log, "tiers are harness-neutral in the log: " + log)
    tiers = {m: r.run([r.bash, ".uak/bin/guard", "tier", m], cwd=w).stdout.strip() for m in
             ["gpt-6-astra", "gpt-6.1-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna",
              "claude-opus-5-5", "sonnet", "haiku", "composer-2.5", "gemini-3-flash-preview"]}
    expect(tiers == {"gpt-6-astra": "strong", "gpt-6.1-sol": "balanced", "gpt-6-luna": "fast", "gpt-5.6-sol": "strong",
                     "gpt-5.6-terra": "balanced", "gpt-5.6-luna": "fast", "claude-opus-5-5": "strong", "sonnet": "balanced",
                     "haiku": "fast", "composer-2.5": "fast", "gemini-3-flash-preview": "fast"}, "tier map: " + str(tiers))
    return {"harnesses": list(cases), "tiers": len(tiers)}


def integrate_when_owner_offline(r):
    f = r.fixture("v41-integrate", count=3, dependencies={"HACK-002": "HACK-001"})
    config(f)
    f.claim(0, "HACK-001")
    (f.worktrees[0] / "src").mkdir(exist_ok=True)
    (f.worktrees[0] / "src/one.txt").write_text("done\n", encoding="utf-8")
    r.g(f.worktrees[0], "add", "src/one.txt")
    r.g(f.worktrees[0], "commit", "-m", "one")
    r.g(f.worktrees[0], "push", "origin", f.branches[0])
    pr = "https://example.invalid/pull/7"
    # Unquoted evidence words are accepted (UpiixSol's most common uak error).
    done = hack(f, 0, "done", "HACK-001", "--pr", pr, "--evidence", "tests", "pass", "on", "main", now=1000010)
    expect("REVIEW" in done.stdout and "Evidence: tests pass on main" in f.show("tasks/HACK-001.md"), done.stdout + done.stderr)
    tip = r.g(f.remote, "rev-parse", f.branches[0]).stdout.strip()
    # agent-2 holds a claim, so it can review.
    f.claim(1, "HACK-003", now=1000011)
    hack(f, 1, "review", "HACK-001", "--sha", tip, "--verdict", "approve", now=1000012)
    blocked = f.claim(2, "HACK-002", now=1000013, allowed=None)
    expect(blocked.returncode == 3 and "uak integrate HACK-001" in blocked.stderr, "the dependency hint names the fix")
    # A human merges on the forge; the owner agent is gone.
    r.g(f.seed, "fetch", "origin", f.branches[0])
    r.g(f.seed, "merge", "--no-ff", "FETCH_HEAD", "-m", "Merge PR 7")
    r.g(f.seed, "push", "origin", "main")
    rec = hack(f, 2, "integrate", "HACK-001", now=1000014)
    expect("INTEGRATED" in rec.stdout and "State: INTEGRATED" in f.show("tasks/HACK-001.md"), rec.stdout + rec.stderr)
    expect("recorded by agent-3" in f.show(f.worklog("HACK-001")), "the worklog says who recorded it")
    f.claim(2, "HACK-002", now=1000015)
    # agent-1 has no active claim now, but its task was integrated minutes ago: it may still review.
    f.claim(1, "HACK-004", allowed=None, now=1000016)
    state = f.show("STATE.md")
    expect("INTEGRATED: HACK-001" in state, "STATE lists integrated tasks: " + state)
    return {"integrated_by": "agent-3", "dependent_claimed": True}


def wt_identity_and_ports(r):
    f = r.fixture("v41-wt", count=1)
    config(f)
    root = f.clones[0]
    env = {"UAK_AGENT": "lead-agent", "UAK_HUMAN": "joahan", "UAK_PORT_BASE": "8100"}
    res = r.run([r.bash, ".uak/bin/wt", "new", "HACK-002", "--agent", "scout-2"], cwd=root, env=env)
    expect("WT_READY" in res.stdout, res.stdout + res.stderr)
    wt = Path(res.stdout.split("worktree ")[-1].split("\n")[0].strip())
    expect("Owner: scout-2" in f.show("claims/HACK-002.md"), "wt claims with --agent, not the exported identity")
    # Inside the worktree, .uak-env wins over an inherited export.
    hb = r.run([r.bash, ".uak/bin/uak", "heartbeat", "HACK-002"], cwd=wt, env=env, allowed=None)
    expect(hb.returncode == 0 and "using UAK_AGENT=scout-2" in hb.stderr, "worktree identity wins: " + hb.stdout + hb.stderr)
    port = int([l for l in (wt / ".uak-env").read_text().splitlines() if l.startswith("UAK_PORT=")][0].split("=")[1])
    expect(port >= 8100, "a port was assigned")
    stop = r.run([r.bash, ".uak/bin/wt", "stop"], cwd=wt)
    expect("WT_STOPPED" in stop.stdout, "wt stop runs without killing anything else")
    ident = r.run([r.bash, ".uak/bin/uak", "heartbeat", "HACK-002"], cwd=root, env={"UAK_AGENT": "", "UAK_HUMAN": ""}, allowed=None)
    expect(ident.returncode == 2 and "git config uak.agent" in ident.stderr, "a missing identity explains the fix: " + ident.stderr)
    return {"owner": "scout-2", "port": port}


def additive_paths_and_recent_reviewer(r):
    f = rm.fixture(r, "v41-additive", count=2)
    project = f.seed / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8") + "Additive-Paths: e2e/\n", encoding="utf-8")
    r.g(f.seed, "add", ".uak/PROJECT.md")
    r.g(f.seed, "commit", "-m", "Additive tests dir")
    r.g(f.seed, "push", "origin", "main")
    for clone, worktree in zip(f.clones, f.worktrees):
        r.g(clone, "fetch", "origin", "main")
        r.g(worktree, "merge", "--ff-only", "origin/main")
    f.claim(0, "HACK-001")
    (f.worktrees[0] / "e2e").mkdir()
    (f.worktrees[0] / "e2e/test_new.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    r.g(f.worktrees[0], "add", "e2e/test_new.py")
    tip = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1000010)
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    merged = f.hack(0, "merge", "HACK-001", now=1000033, allowed=None)
    expect("INTEGRATED" in merged.stdout, "a NEW file under Additive-Paths merges: " + merged.stdout + merged.stderr)
    # agent-1 has no claim now, but its task was just integrated: it can review agent-2's task.
    f.claim(1, "HACK-002", now=1000034)
    tip2 = rm.publish(f, 1, "HACK-002")
    f.hack(1, "done", "HACK-002", "--pr", "https://example.test/pull/2", "--evidence", "ok", now=1000035)
    rm.approve(f, "HACK-002", tip2, name="agent-1", now=1000036)
    expect("Eligible-Via: recent:HACK-001" in f.show("reviews/HACK-002.md"), "a recently integrated agent may review")
    stranger = rm.approve(f, "HACK-002", tip2, name="ghost", now=1000037, allowed=None)
    expect(stranger.returncode == 3, "an identity with no recent work still cannot review")
    return {"additive_merge": True, "recent_reviewer": True}


def hard_caps_beat_pacing(r):
    f = r.fixture("v41-hard", count=2, shared_repo=True)
    w = f.worktrees[0]
    (w / ".uak/PROJECT.md").write_text("Mode: sprint\nMax-Parallel-Subagents: 4\nOpus-Subagents-Per-Session: 2\n"
                                       "Subagent-Hard-Cap: 5\nStrong-Hard-Cap: 3\nSubagents-Per-Session: 9\n"
                                       "Subagent-Burst-Per-Minute: 100\nSubagents-Per-Machine: 7\nMax-Worktree-Agents: 3\n", encoding="utf-8")
    now = 2000000000
    env = {"UAK_PACE_CODEX": "0"}
    pace = lambda *a, t=now: r.run([r.bash, ".uak/bin/pace", *a], cwd=w, env={**env, "UAK_NOW": str(t)})
    pace("set", "10", "--resets", "+30m")  # 90% left with 10% of the window: a big surge (8 parallel, 4 strong)
    expect(pace("--caps").stdout.split()[0] == "surge", "fresh data gives surge")
    pace("set", "10", "--resets", "+2d", "--window", "30d", "--source", "cursor")
    stale = pace(t=now + 13 * 3600).stdout
    expect("PACE normal" in stale and "stale reading" in stale, "a 13-hour-old reading never gives surge: " + stale)
    pace("set", "10", "--resets", "+30m")
    def spawn(kind, model, t, sid="s1", wt=w, extra=None):
        payload = json.dumps({"session_id": sid, "tool_name": "Agent", "tool_input": {"subagent_type": kind, "model": model}})
        return r.run([r.bash, "-c", "printf '%s' \"$1\" | bash .uak/bin/guard agent", "_", payload], cwd=wt,
                     env={**env, "UAK_NOW": str(t), **(extra or {})}, allowed=None)
    stop = lambda wt=w: r.run([r.bash, "-c", "printf '{}' | bash .uak/bin/guard agent-stop"], cwd=wt)
    for i in range(5):
        expect(spawn("general-purpose", "haiku", now + i).returncode == 0, "surge allows up to the hard cap")
    over = spawn("general-purpose", "haiku", now + 5)
    expect(over.returncode == 2 and "Max-Parallel-Subagents: 5" in over.stderr, "surge (8) is clipped to Subagent-Hard-Cap 5: " + over.stderr)
    for _ in range(5):
        stop()
    for i in range(3):
        expect(spawn("uak-architect", "opus", now + 10 + i).returncode == 0, "strong up to Strong-Hard-Cap")
        stop()
    strong = spawn("uak-architect", "opus", now + 20)
    expect(strong.returncode == 2 and "3/3" in strong.stderr, "surge strong (4) is clipped to Strong-Hard-Cap 3: " + strong.stderr)
    expect(spawn("general-purpose", "haiku", now + 21).returncode == 0, "9th spawn of the session is allowed")
    stop()
    total = spawn("general-purpose", "haiku", now + 22)
    expect(total.returncode == 2 and "Subagents-Per-Session: 9" in total.stderr, "total spawns per session are capped: " + total.stderr)
    # Burst: a fresh session, 3 spawns per minute max.
    (w / ".uak/PROJECT.md").write_text("Mode: sprint\nSubagent-Burst-Per-Minute: 3\nSubagents-Per-Machine: 3\n", encoding="utf-8")
    for i in range(3):
        spawn("general-purpose", "haiku", now + 100 + i, sid="b1"); stop()
    burst = spawn("general-purpose", "haiku", now + 104, sid="b1")
    expect(burst.returncode == 2 and "last minute" in burst.stderr, "a spawn burst is blocked: " + burst.stderr)
    # Machine-wide: subagents running in another worktree of the same repo count too.
    w2 = f.worktrees[1]
    (w2 / ".uak/PROJECT.md").write_text("Mode: sprint\nSubagents-Per-Machine: 3\n", encoding="utf-8")
    spawn("general-purpose", "haiku", now + 200, sid="m1"); spawn("general-purpose", "haiku", now + 201, sid="m1")
    other = spawn("general-purpose", "haiku", now + 202, sid="m2", wt=w2)
    third = spawn("general-purpose", "haiku", now + 203, sid="m3", wt=w2)
    expect(other.returncode == 0 and third.returncode == 2 and "across all worktrees" in third.stderr,
           "Subagents-Per-Machine counts every worktree: " + third.stderr)
    (w / ".uak/PROJECT.md").write_text("Mode: sprint\nMax-Worktree-Agents: 3\n", encoding="utf-8")
    up = r.run([r.bash, ".uak/bin/uak", "up", "4"], cwd=w, env={"UAK_HUMAN": "ana"}, allowed=None)
    expect(up.returncode == 2 and "Max-Worktree-Agents (3)" in up.stderr, "uak up is capped: " + up.stderr)
    return {"hard_parallel": 5, "hard_strong": 3, "per_session": 9, "burst": 3, "machine": 3, "up": 3}


def mode_is_human_only(r):
    f = rm.fixture(r, "v41-mode", count=1)
    tasks = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8").replace("- **Paths:** src/value-1.txt", "- **Paths:** src/value-1.txt, .uak/PROJECT.md")
    (f.seed / ".uak/TASKS.md").write_text(tasks, encoding="utf-8")
    r.g(f.seed, "add", ".uak/TASKS.md"); r.g(f.seed, "commit", "-m", "task may touch PROJECT"); r.g(f.seed, "push", "origin", "main")
    r.g(f.clones[0], "fetch", "origin", "main"); r.g(f.worktrees[0], "merge", "--ff-only", "origin/main")
    f.claim(0, "HACK-001")
    project = f.worktrees[0] / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8").replace("Review-Mode: claims", "Mode: marathon\nReview-Mode: claims"), encoding="utf-8")
    r.g(f.worktrees[0], "add", ".uak/PROJECT.md")
    tip = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1000010)
    rm.judge(f); rm.approve(f, "HACK-001", tip)
    merged = f.hack(0, "merge", "HACK-001", now=1000033, allowed=None)
    expect(merged.returncode == 3 and "needs a human" in (merged.stdout + merged.stderr),
           "an agent's change to PROJECT.md (the mode) goes to the human queue: " + merged.stdout + merged.stderr)
    inst = r.run([r.bash, str(r.package.parent / "install.sh"), str(f.seed)], allowed=None) if (r.package.parent / "install.sh").exists() else None
    if inst is not None:
        expect(inst.returncode == 2 and "the human chooses" in inst.stderr, "install.sh has no default mode")
    return {"project_md_protected": True}


TESTS = [hard_caps_beat_pacing, mode_is_human_only, blackbox_records_and_publishes, pace_levels_and_guard, guard_every_harness, integrate_when_owner_offline,
         wt_identity_and_ports, additive_paths_and_recent_reviewer]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-v41-") as tmp:
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
    print("V41_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
