#!/usr/bin/env python3
"""uak v5: token accounting, stronger loops, handover, graph --assign, Gemini hooks, stack presets.
Real Git, local bare remote, separate processes; transcripts are synthetic files in a temp HOME."""
import argparse
import concurrent.futures
import json
import os
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack
import test_review_merge as rm


def enc(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def claude_line(msg_id, model, i, w, c, o, sidechain=False):
    return json.dumps({"type": "assistant", "isSidechain": sidechain, "sessionId": "s", "cwd": "/x",
                       "message": {"id": msg_id, "model": model, "role": "assistant", "content": [{"type": "text", "text": "\"input_tokens\":999"}],
                                   "usage": {"input_tokens": i, "cache_creation_input_tokens": w, "cache_read_input_tokens": c,
                                             "output_tokens": o, "output_tokens_details": {"thinking_tokens": 1},
                                             "cache_creation": {"ephemeral_1h_input_tokens": w}, "iterations": [{"input_tokens": 77}]}}})


def tokens_per_task_and_team(r):
    """The kit counted calls, not tokens; 'it burns tokens reading the same stuff' needs the real bill."""
    f = r.fixture("v5-tokens", count=2)
    config(f)
    main = f.clones[0].resolve()
    home = f.base / "home"
    proj = home / ".claude" / "projects"
    lead = proj / enc(main)
    wt = proj / (enc(main) + "-wt-hack-002-app")             # a session started in a subfolder of a worktree
    for d in (lead, wt / "sess" / "subagents"):
        d.mkdir(parents=True, exist_ok=True)
    lines = [claude_line("msg_a", "claude-opus-5-5", 10, 1000, 50000, 300),
             claude_line("msg_a", "claude-opus-5-5", 10, 1000, 50000, 300),   # streaming duplicate: counted once
             claude_line("msg_b", "claude-opus-5-5", 5, 0, 20000, 200)]
    (lead / "s1.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (wt / "s2.jsonl").write_text(claude_line("msg_c", "claude-sonnet-5-5", 1, 100, 9000, 900) + "\n", encoding="utf-8")
    (wt / "sess" / "subagents" / "agent-1.jsonl").write_text(
        claude_line("msg_d", "claude-haiku-5-5", 2, 50, 4000, 400, True) + "\n", encoding="utf-8")
    codex = home / ".codex" / "sessions" / "2026" / "10" / "15"
    codex.mkdir(parents=True)
    rollout = [json.dumps({"type": "session_meta", "payload": {"cwd": str(main) + "-wt/hack-001"}}),
               json.dumps({"type": "turn_context", "payload": {"model": "gpt-5.5-codex"}}),
               json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage":
                          {"input_tokens": 1000, "cached_input_tokens": 600, "output_tokens": 50, "reasoning_output_tokens": 10}}}}),
               json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage":
                          {"input_tokens": 3000, "cached_input_tokens": 2000, "output_tokens": 120, "reasoning_output_tokens": 30}}}})]
    (codex / "rollout-x.jsonl").write_text("\n".join(rollout) + "\n", encoding="utf-8")
    other = home / ".codex" / "sessions" / "2026" / "10" / "14"
    other.mkdir(parents=True)
    (other / "rollout-y.jsonl").write_text(json.dumps({"type": "session_meta", "payload": {"cwd": "/somewhere/else"}}) + "\n" +
                                           rollout[3] + "\n", encoding="utf-8")
    env = {"HOME": str(home), "CLAUDE_CONFIG_DIR": str(home / ".claude"), "CODEX_HOME": str(home / ".codex")}
    run = lambda *a: r.run([r.bash, ".uak/bin/uak", "tokens", *a], cwd=f.clones[0], env=env)
    data = {row["key"]: row for row in json.loads(run("--json").stdout)}
    expect(set(data) == {"main", "HACK-002", "HACK-001"}, "tasks from the transcript folder and the Codex cwd: " + str(data))
    expect(data["main"]["cache_read"] == 70000 and data["main"]["output"] == 500, "duplicates of one message count once: " + str(data["main"]))
    expect(data["HACK-002"]["output"] == 1300, "a worktree subfolder and its subagents belong to the task")
    expect(data["HACK-001"]["input"] == 1000 and data["HACK-001"]["cache_read"] == 2000 and data["HACK-001"]["output"] == 120,
           "Codex: the last cumulative count, uncached = input - cached: " + str(data["HACK-001"]))
    scope = {row["key"]: row for row in json.loads(run("--json", "--by", "scope").stdout)}
    expect(scope["subagent"]["output"] == 400, "lead vs subagent: " + str(scope))
    model = run("--by", "model").stdout
    expect("claude-haiku-5-5" in model and "gpt-5.5-codex" in model and "cache hit" in model, model)
    pub = run("--publish")
    expect("published to claims:tokens/" in pub.stdout, pub.stdout + pub.stderr)
    expect([p for p in f.files("tokens/") if p.endswith(".md")], "one file per machine on claims")
    f.claim(1, "HACK-002")
    team = r.run([r.bash, ".uak/bin/uak", "tokens", "--team", "--by", "agent", "--json"], cwd=f.clones[0], env=env).stdout
    agents = {row["key"] for row in json.loads(team)}
    expect("agent-2" in agents and "main" in agents, "--team names the task owner from claims: " + team)
    stats = r.run([r.bash, ".uak/bin/stats"], cwd=f.clones[0], env=env).stdout
    expect("tokens:" in stats and "by harness:" in stats and "top task" in stats, "stats shows the bill: " + stats)
    digest = r.run([r.bash, ".uak/bin/uak", "digest"], cwd=f.clones[0], env=dict(env, UAK_HUMAN="ana", UAK_DEDUPE="off")).stdout
    expect("Tokens: " in digest and "top task HACK-002" in digest, "the human digest carries one line: " + digest)
    return {"tasks": len(data)}


def loop_guards_and_parallel(r):
    """LOOPS.md rules 3 and 5 were text: stop on no progress and on an edited verifier. Parallel per test file."""
    f = r.fixture("v5-loop", count=1)
    w = f.worktrees[0]
    (w / "tests").mkdir(exist_ok=True)
    (w / "tests/test_a.py").write_text("assert True\n", encoding="utf-8")
    r.g(w, "add", "tests/test_a.py"); r.g(w, "commit", "-qm", "test file")
    cheat = r.run([r.bash, ".uak/bin/uak", "loop", "--verify", "echo FAILED; exit 1", "--agent", "echo '# skip' >> tests/test_a.py"],
                  cwd=w, allowed=None)
    expect(cheat.returncode == 3 and "verifier edited" in cheat.stdout and "tests/test_a.py" in cheat.stdout,
           "an agent that edits an existing test stops the loop: " + cheat.stdout)
    r.g(w, "checkout", "--", "tests/test_a.py")
    idle = r.run([r.bash, ".uak/bin/uak", "loop", "--verify", "exit 1", "--agent", "true"], cwd=w, allowed=None)
    expect(idle.returncode == 3 and "no progress" in idle.stdout, "an agent that changes nothing stops it: " + idle.stdout)
    for name in ("a", "b"):
        (w / ("src_%s.txt" % name)).write_text("bad\n", encoding="utf-8")
    (w / "check.sh").write_text(
        "#!/usr/bin/env bash\nrc=0\nfor t in ${1:-tests/test_a.py tests/test_b.py}; do n=${t#tests/test_}; n=${n%.py}\n"
        "grep -q good src_$n.txt || { echo \"FAILED tests/test_$n.py::t - src_$n bad\"; rc=1; }; done\nexit $rc\n",
        encoding="utf-8")
    (w / "fix.sh").write_text("#!/usr/bin/env bash\nf=$(sed -n 's/^Check: bash check.sh tests\\/test_\\(.\\)\\.py$/\\1/p' \"$UAK_PROMPT_FILE\")\necho good > src_$f.txt\n",
                              encoding="utf-8")
    r.g(w, "add", "-A"); r.g(w, "commit", "-qm", "two failing parts")
    par = r.run([r.bash, ".uak/bin/uak", "loop", "--verify", "bash check.sh", "--parallel", "2",
                 "--each", "bash check.sh {}", "--agent", "bash " + str(w / "fix.sh")], cwd=w, allowed=None)
    expect("LOOP_PARALLEL 2 sub-loop(s)" in par.stdout, par.stdout + par.stderr)
    expect(par.returncode == 0 and "LOOP_PASS parallel" in par.stdout, "both fixes come back and Verify passes: " + par.stdout)
    expect((w / "src_a.txt").read_text() == "good\n" and (w / "src_b.txt").read_text() == "good\n", "patches applied here")
    left = r.g(w, "worktree", "list").stdout
    expect("uak-out" not in left, "temporary worktrees are removed: " + left)
    return {"parallel": 2}


def handover_and_assign(r):
    """Tasks of abandoned identities were redistributed by messages; nobody suggested who takes what."""
    f = rm.fixture(r, "v5-handover", count=3)
    rm.judge(f)
    tip = rm.ready(f, 0, "HACK-001")
    rm.approve(f, "HACK-001", tip)
    f.hack(0, "merge", "HACK-001", now=1000030)
    f.claim(1, "HACK-002", now=1000040)
    denied = f.hack(2, "handover", "HACK-002", "--to", "agent-3", now=1000041, allowed=None)
    expect(denied.returncode == 3 and "live lease" in denied.stderr, "only the owner or a human, while the lease is live")
    ok = f.hack(1, "handover", "HACK-002", "--to", "agent-3", now=1000042)
    expect("OK handover HACK-002 → agent-3" in ok.stdout, ok.stdout + ok.stderr)
    expect("Owner: agent-3" in f.show("claims/HACK-002.md") and "Owner: agent-3" in f.show("tasks/HACK-002.md"), "owner changed")
    env = (f.worktrees[1] / ".uak-env")
    if env.exists():
        expect("UAK_AGENT=agent-3" in env.read_text(encoding="utf-8"), "the worktree's identity follows")
    expect("is yours now (from agent-2)" in f.show("inbox/log.md"), "the new owner is told in one message")
    beat = f.hack(2, "heartbeat", "HACK-002", now=1000043)
    expect("OK heartbeat HACK-002" in beat.stdout, "the new owner can renew it: " + beat.stdout + beat.stderr)
    assign = r.run([r.bash, ".uak/bin/graph", "--assign"], cwd=f.clones[0]).stdout
    expect("ASSIGN suggestion" in assign and "HACK-003 (P0) → agent-1" in assign and "knows src/" in assign,
           "the idle agent that integrated work in src/ gets the ready task: " + assign)
    return {"handover": True}


def gemini_hooks(r):
    """Gemini CLI documents BeforeTool/SessionStart hooks: guard, session context and the output cap."""
    f = r.fixture("v5-gemini", count=1)
    w = f.worktrees[0]
    settings = json.loads((r.package / ".gemini/settings.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for g in settings["hooks"]["BeforeTool"] for h in g["hooks"]]
    expect(any("guard\" bash" in c for c in cmds) and any("wrap gemini" in c for c in cmds), str(cmds))
    def hook(mode, payload, env=None):
        (w / ".git-payload.json").write_text(json.dumps(payload), encoding="utf-8")
        return r.run([r.bash, "-c", "bash .uak/bin/hook " + mode + " < .git-payload.json"], cwd=w, env=env or {}, allowed=None)
    base = {"session_id": "g1", "cwd": str(w), "hook_event_name": "BeforeTool", "tool_name": "run_shell_command"}
    (w / ".git-payload.json").write_text(json.dumps(dict(base, tool_input={"command": "git push --force origin main"})), encoding="utf-8")
    blocked = r.run([r.bash, "-c", "bash .uak/bin/guard bash < .git-payload.json"], cwd=w, allowed=None)
    expect(blocked.returncode == 2, "the guard blocks a force push from Gemini: %d %s" % (blocked.returncode, blocked.stderr))
    out = json.loads(hook("wrap gemini", dict(base, tool_input={"command": "python -m pytest -q"})).stdout)
    expect(out["decision"] == "allow" and "--b64" in out["hookSpecificOutput"]["tool_input"]["command"], str(out))
    start = hook("session-start gemini", {"session_id": "g1", "hook_event_name": "SessionStart", "source": "startup"})
    data = json.loads(start.stdout)
    expect("UAK" in data["hookSpecificOutput"]["additionalContext"], "Gemini gets the session context as JSON: " + start.stdout[:200])
    return {"gemini": True}


def stacks_install(r):
    """Stack presets beyond FastAPI + React: each installs its skill and the smoke example."""
    out = {}
    for stack, skill in [("nextjs", "stack-nextjs"), ("django", "stack-django"), ("go", "stack-go"), ("expo", "stack-expo"),
                         ("python-data", "stack-data"), ("ai-agent", "stack-ai-agent")]:
        t = r.scratch / ("v5-stack-" + stack)
        t.mkdir()
        r.g(t, "init", "-q", "-b", "main")
        res = r.run([r.bash, str(r.package.parent / "install.sh"), "--mode", "sprint", "--stack", stack, str(t)], cwd=t)
        expect((t / ".claude/skills" / skill / "SKILL.md").exists(), stack + ": skill installed: " + res.stdout[-400:])
        expect((t / ".uak/stacks" / stack / "STACK.md").exists() and (t / ".uak/bin/smoke-project.example").exists(), stack)
        expect((t / ".github/workflows/uak-tick.yml.example").exists(), "the scheduled tick ships as an opt-in example")
        out[stack] = True
    expect((r.scratch / "v5-stack-ai-agent/.claude/skills/mcp-builder").exists(), "ai-agent brings mcp-builder")
    expect((r.scratch / "v5-stack-nextjs/.claude/skills/vercel-react-best-practices").exists(), "nextjs brings the React rules")
    return out


TESTS = [tokens_per_task_and_team, loop_guards_and_parallel, handover_and_assign, gemini_hooks, stacks_install]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-v5-") as tmp:
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
    print("V5_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
