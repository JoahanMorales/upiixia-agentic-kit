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
        no_mcp = ["--no-mcp"] if stack == "go" else []   # MCP is optional: the CLI through Bash does the same
        res = r.run([r.bash, str(r.package.parent / "install.sh"), "--mode", "sprint", "--stack", stack] + no_mcp + [str(t)], cwd=t)
        expect((t / ".claude/skills" / skill / "SKILL.md").exists(), stack + ": skill installed: " + res.stdout[-400:])
        expect((t / ".uak/stacks" / stack / "STACK.md").exists() and (t / ".uak/bin/smoke-project.example").exists(), stack)
        expect((t / ".github/workflows/uak-tick.yml.example").exists(), "the scheduled tick ships as an opt-in example")
        out[stack] = True
    expect((r.scratch / "v5-stack-ai-agent/.claude/skills/mcp-builder").exists(), "ai-agent brings mcp-builder")
    on, off = r.scratch / "v5-stack-nextjs", r.scratch / "v5-stack-go"
    expect((on / ".mcp.json").exists() and (on / ".cursor/mcp.json").exists(), "MCP server configured by default")
    expect("[mcp_servers.uak]" in (on / ".codex/config.toml").read_text(), "Codex gets the MCP server by default")
    expect(not (off / ".mcp.json").exists() and not (off / ".cursor/mcp.json").exists(), "--no-mcp: no MCP config")
    expect("mcp_servers" not in (off / ".codex/config.toml").read_text(), "--no-mcp: Codex config without the server")
    gem = json.loads((off / ".gemini/settings.json").read_text())
    expect("mcpServers" not in gem and "hooks" in gem, "--no-mcp: Gemini settings valid, hooks kept, no server")
    expect((r.scratch / "v5-stack-nextjs/.claude/skills/vercel-react-best-practices").exists(), "nextjs brings the React rules")
    return out


def code_map_and_impact(r):
    """Agents opened file after file to learn the structure; contracts reached importers by hand-picked messages."""
    f = r.fixture("v5-map", count=2, paths={"HACK-001": "lib/", "HACK-002": "app/"})
    config(f)
    w = f.worktrees[0]
    files = {
        "lib/__init__.py": "",
        "lib/config.py": "def data_path(name):\n    return name\n\nclass Settings:\n    pass\n",
        "lib/io.py": "from lib.config import data_path\nfrom . import config\n\ndef load():\n    return data_path('x')\n",
        "app/page.py": "from lib import io\nimport lib.config as c\n\ndef render():\n    return io.load()\n",
        "web/src/lib/api.ts": "export async function api(path: string) { return path }\n",
        "web/src/features/a/index.tsx": "import { api } from '../../lib/api'\nimport x from '@/lib/api'\nexport default function A() { return null }\n",
    }
    for rel, text in files.items():
        p = w / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    r.g(w, "add", "-A"); r.g(w, "commit", "-qm", "code")
    m = lambda *a: r.run([r.bash, ".uak/bin/uak", "map", *a], cwd=w)
    built = m().stdout
    expect("MAP 6 files" in built and "import edges" in built, built)
    show = m("show").stdout
    expect("lib/config.py" in show.split("## Hubs")[1].split("##")[0] and "data_path" in show, "the hub table names config.py: " + show)
    expect("app → lib" in show, "area dependencies: " + show)
    expect("lib/config.py:1  def data_path" in m("find", "data_path").stdout, "find gives file:line")
    users = m("users", "lib/config.py", "--depth", "2").stdout
    expect("lib/io.py" in users and "app/page.py" in users, "users, two levels: " + users)
    expect("app/page.py → lib/io.py" in m("path", "app/page.py", "lib/io.py").stdout, "shortest import path")
    expect("web/src/lib/api.ts" in m("deps", "web/src/features/a/index.tsx").stdout, "relative and @/ TS imports resolve")
    impact = m("impact", "HACK-001").stdout
    expect("app/page.py imports" in impact and "task HACK-002" in impact and "uak msg impact:HACK-001" in impact, impact)
    f.claim(0, "HACK-001"); f.claim(1, "HACK-002")
    sent = hack(f, 0, "msg", "impact:HACK-001", "--kind", "contract", "data_path now takes a Path", now=1000005)
    expect("task:HACK-002" in sent.stdout, "impact:ID reaches the importing task: " + sent.stdout + sent.stderr)
    both = hack(f, 0, "msg", "HACK-002,agent-2", "one line for two targets", now=1000006)
    expect("task:HACK-002,agent:agent-2" in f.show("inbox/log.md"), "comma lists are one line: " + both.stdout)
    callers = m("callers", "data_path").stdout
    expect("lib/io.py:5  in load → lib/config.py" in callers, "call edges name the enclosing function: " + callers)
    expect("→ load (lib/io.py)" in m("calls", "render").stdout, "what a function calls")
    expect("uses load" in impact or "uses data_path" in m("impact", "lib/config.py").stdout, "impact names the API surface used: " + impact)
    fake = f.base / "fake-notes.sh"
    fake.write_text("#!/usr/bin/env bash\nsed -n 's/^=== FILE: //p' | while read -r p; do\n"
                    "  case $p in lib/*) c='raw data paths, storage config';; app/*) c='page rendering, storage config';; *) c='frontend api';; esac\n"
                    "  echo \"FILE: $p | PURPOSE: does things for $p | CONCEPTS: $c\"; done\n", encoding="utf-8")
    notes = m("notes", "--agent", "bash " + str(fake), "--max", "10").stdout
    expect("with purpose and concepts" in notes, notes)
    shown = m("show").stdout
    expect("## Concepts (INFERRED" in shown and "path (3)" in shown and "does things for lib/config.py" in shown,
           "MAP.md gets purposes and concepts: " + shown)
    rel = m("related", "lib/io.py").stdout
    expect("EXTRACTED imports   → lib/config.py" in rel, "related lists extracted neighbors: " + rel)
    again = m("notes", "--agent", "bash " + str(fake), "--max", "10").stdout
    expect("already has a note" in again, "notes are cached by content: " + again)
    (w / "lib/new.py").write_text("def fresh():\n    pass\n", encoding="utf-8")
    expect("lib/new.py:1  def fresh" in m("find", "fresh").stdout, "the index rebuilds when the tree changes")
    return {"files": 6}


def lessons_follow_the_paths(r):
    """The same traps came back task after task (a shifting label: 3 tasks; numbers vs CSV: 4 rejects)."""
    f = rm.fixture(r, "v5-learn", count=2)
    rm.judge(f)
    ok = f.hack(0, "learn", "Use", "df['count']:", "the", "column", "shadows", "DataFrame.count", "--task", "HACK-001", now=1000001)
    expect("OK learn #1 on src/value-1.txt" in ok.stdout, ok.stdout + ok.stderr)
    again = f.hack(1, "learn", "Use df['count']: the column shadows DataFrame.count", "--task", "HACK-001", now=1000002)
    expect("already known" in again.stdout, "a lesson is stored once: " + again.stdout)
    f.hack(1, "learn", "Every number in a README comes from a CSV in reports/", "--path", "*", now=1000003)
    nxt = f.hack(0, "next", now=1000004).stdout
    expect("Lessons for these paths" in nxt and "DataFrame.count" in nxt and "from a CSV" in nxt,
           "next shows the lessons of the task it proposes: " + nxt)
    other = f.hack(1, "recall", "HACK-002", now=1000005).stdout
    expect("DataFrame.count" not in other and "from a CSV" in other, "lessons stay on their paths: " + other)
    tip = rm.ready(f, 0, "HACK-001")
    rm.actor(f, "judge", "review", "HACK-001", "--sha", tip, "--verdict", "reject", "--note",
             "src/value-1.txt:1 · the value is not normalized · run the check twice", "--learn", now=1000020)
    rec = f.hack(1, "recall", "HACK-001", now=1000021).stdout
    expect("not normalized" in rec and "judge · HACK-001" in rec, "review --learn turns the reject note into a lesson: " + rec)
    gone = f.hack(1, "learn", "--forget", "1", now=1000022)
    expect("OK learn forgot #1" in gone.stdout, gone.stdout + gone.stderr)
    expect("DataFrame.count" not in f.hack(1, "recall", "HACK-001", now=1000023).stdout, "a forgotten lesson is not shown")
    return {"lessons": 3}


def wait_instead_of_polling(r):
    """225 status and 172 inbox calls at MLB were mostly agents checking whether something had arrived."""
    import subprocess
    f = rm.fixture(r, "v5-wait", count=1)
    rm.judge(f)
    tip = rm.ready(f, 0, "HACK-001")
    env = dict(os.environ, UAK_AGENT="agent-1", UAK_HUMAN="", UAK_WAIT_EVERY="1", UAK_REMOTE="origin")
    proc = subprocess.Popen([r.bash, ".uak/bin/uak", "wait", "--for", "approve", "--timeout", "60"], cwd=f.worktrees[0],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(2.5)
    rm.approve(f, "HACK-001", tip, now=int(time.time()))
    out, _ = proc.communicate(timeout=90)
    expect(proc.returncode == 0 and "WAITING HACK-001 for approve" in out and "APPROVED HACK-001 by judge" in out,
           "one call returns when the approval lands: " + out)
    quick = r.run([r.bash, ".uak/bin/uak", "wait", "HACK-001", "--for", "integrated", "--timeout", "2"], cwd=f.worktrees[0],
                  env={"UAK_AGENT": "agent-1", "UAK_WAIT_EVERY": "1"}, allowed=None)
    expect(quick.returncode == 4 and "WAIT_TIMEOUT HACK-001 integrated" in quick.stdout, "a timeout says so: " + quick.stdout)
    return {"wait": True}


def latency_paths(r):
    """A `uak next` took 10-12 s on GitHub: 4-5 round trips per call, a clock call per call, every task probed."""
    f = r.fixture("v5-latency", count=1)
    config(f)
    w = f.worktrees[0]
    first = hack(f, 0, "next", now=1000001)
    expect(first.returncode == 0 and "HACK-001 | AVAILABLE" in first.stdout, "next works before claims exists: " + first.stdout + first.stderr)
    shim = f.base / "shim"
    shim.mkdir()
    (shim / "git").write_text("#!/usr/bin/env bash\nprintf '%%s\\n' \"$*\" >> %s\nexec %s \"$@\"\n" % (f.base / "git.log", r.git), encoding="utf-8")
    os.chmod(shim / "git", 0o755)
    r.run([r.bash, ".uak/bin/uak", "status"], cwd=w, env={"UAK_AGENT": "agent-1", "UAK_NOW": "1000002",
                                                          "PATH": str(shim) + os.pathsep + os.environ["PATH"]}, allowed=None)
    calls = [l for l in (f.base / "git.log").read_text(encoding="utf-8").splitlines() if re.search(r"(^| )(ls-remote|fetch|push|clone)( |$)", l)]
    expect(len(calls) == 1 and "refs/heads/claims:refs/uak/claims" in calls[0] and "refs/uak/config" in calls[0],
           "status makes one network call for claims and config: " + "\n".join(calls))
    mux = lambda url, extra="": r.run([r.bash, "-c", "git remote set-url origin '%s'; %s . .uak/bin/lib/net.sh; ssh_mux; printf %%s \"${GIT_SSH_COMMAND:-none}\"" % (url, extra)],
                                     cwd=w, env={"HOME": str(f.base)}).stdout
    expect("ControlMaster=auto" in mux("git@github.com:o/r.git"), "ssh remotes reuse one connection")
    expect(mux("https://github.com/o/r.git") == "none", "https remotes are left alone")
    expect(mux("git@github.com:o/r.git", "GIT_SSH_COMMAND='ssh -i k';") == "ssh -i k", "the user's own ssh command wins")
    r.run([r.bash, "-c", "git remote set-url origin %s" % f.remote], cwd=w)
    hack(f, 0, "msg", "all", "an old broadcast from long ago", now=1000003)
    fresh = hack(f, 0, "inbox", now=1000003 + 30000, UAK_AGENT="newcomer-1").stdout
    expect("old broadcast" not in fresh, "a new identity starts with the last 6 h: " + fresh)
    return {"one_round_trip": True}


def adoption_layer(r):
    """Rules in context were not enough: an agent with AGENTS.md loaded shipped a change another live task imports
    without a contract; at MLB agents made 486 status/inbox/board/digest calls and wrote 4 black box notes."""
    f = r.fixture("v5-adopt", count=2, paths={"HACK-001": "lib/", "HACK-002": "app/"})
    config(f)
    w = f.worktrees[0]
    seed = f.seed
    (seed / "lib").mkdir(); (seed / "app").mkdir()
    (seed / "lib/__init__.py").write_text("", encoding="utf-8"); (seed / "app/__init__.py").write_text("", encoding="utf-8")
    (seed / "lib/pricing.py").write_text("def price(a):\n    return a\n", encoding="utf-8")
    (seed / "app/checkout.py").write_text("from lib.pricing import price\n\ndef total(x):\n    return price(x)\n", encoding="utf-8")
    r.g(seed, "add", "-A"); r.g(seed, "commit", "-qm", "code"); r.g(seed, "push", "-q", "origin", "main")
    for wt in f.worktrees:
        r.g(wt, "fetch", "-q", "origin"); r.g(wt, "merge", "-q", "--ff-only", "origin/main")
    f.claim(0, "HACK-001"); f.claim(1, "HACK-002")
    (w / "lib/pricing.py").write_text("def price(a, region=None):\n    return a\n", encoding="utf-8")
    r.g(w, "commit", "-qam", "region"); r.g(w, "push", "-q", "origin", f.branches[0])
    done = hack(f, 0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1000002).stdout
    expect("uak wait HACK-001 --for approve" in done, "done says how to wait: " + done)
    expect("CONTRACT? Your diff changes files that live tasks import (HACK-002)" in done and "msg impact:HACK-001" in done,
           "done notices the missing contract: " + done)
    unchanged = [hack(f, 1, "status", now=1000010 + i, UAK_DEDUPE="on").stdout for i in range(2)][1]
    expect("uak wait ID --for" in unchanged, "= unchanged points at uak wait: " + unchanged)
    def tick(payload):
        (w / ".git-payload.json").write_text(json.dumps(payload), encoding="utf-8")
        return r.run([r.bash, "-c", "bash .uak/bin/hook tick < .git-payload.json"], cwd=w).stdout
    reads = [tick({"session_id": "s9", "tool_name": "Read", "tool_input": {"file_path": "x"}}) for _ in range(5)]
    expect(reads[3] == "" and "map show" in reads[4], "5 reads in a row bring the code map: " + str(reads))
    polls = [tick({"session_id": "s9", "tool_name": "Bash", "tool_input": {"command": "bash .uak/bin/uak inbox"}, "tool_response": {"stdout": ""}}) for _ in range(3)]
    expect("uak wait" in polls[2] and polls[1] == "", "the third look in 10 min brings uak wait: " + str(polls))
    loop = {"session_id": "s9", "tool_name": "Bash", "tool_input": {"command": "bash .uak/bin/uak claim X"}, "tool_response": {"stdout": "LOOP: the same error 3 times"}}
    expect("bb add friction" in tick(loop) and tick(loop) == "", "a repeated kit error invites one black box line, once")
    card = r.run([r.bash, "-c", "bash .uak/bin/hook session-start < /dev/null"], cwd=f.clones[0]).stdout
    expect("UAK quick card" in card and "msg impact:ID" in card and "wait ID --for" in card, "the session starts with the card: " + card[-400:])
    return {"coach": True}


class Mcp:
    """A JSON-RPC client over the server's stdio."""
    def __init__(self, r, cwd, env=None):
        import subprocess, queue
        self.q = queue.Queue()
        self.p = subprocess.Popen(["python3", ".uak/bin/uak-mcp"], cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, env=dict(os.environ, **(env or {})))
        import threading
        threading.Thread(target=self._read, daemon=True).start()
        self.n = 0
    def _read(self):
        for line in self.p.stdout:
            self.q.put(json.loads(line))
    def send(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            self.n += 1; msg["id"] = self.n
        self.p.stdin.write(json.dumps(msg) + "\n"); self.p.stdin.flush()
        return msg.get("id")
    def wait(self, rid, timeout=120, notes=None):
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = self.q.get(timeout=1)
            except Exception:  # noqa: BLE001
                continue
            if m.get("id") == rid:
                return m
            if notes is not None:
                notes.append(m)
        raise AssertionError("no answer to %s" % rid)
    def call(self, method, params=None, timeout=120):
        return self.wait(self.send(method, params), timeout)
    def close(self):
        self.p.stdin.close(); self.p.wait(timeout=10)


def mcp_server(r):
    """The harness as native MCP tools, dual-era (2026-07-28 stateless and the 2025-11-25 handshake)."""
    f = r.fixture("v5-mcp", count=2, paths={"HACK-001": "lib/", "HACK-002": "app/"})
    config(f)
    root = f.clones[0]
    (f.seed / "lib").mkdir(); (f.seed / "lib/core.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    r.g(f.seed, "add", "-A"); r.g(f.seed, "commit", "-qm", "code"); r.g(f.seed, "push", "-q", "origin", "main")
    r.g(root, "pull", "-q", "--ff-only", "origin", "main")
    import shutil
    shutil.copytree(r.package / ".claude" / "commands", root / ".claude" / "commands")   # installed by install.sh
    c = Mcp(r, root)
    init = c.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})["result"]
    expect(init["protocolVersion"] == "2025-06-18" and "uak_wait" in init["instructions"] and "tools" in init["capabilities"], str(init)[:300])
    c.send("notifications/initialized", notify=True)
    tools = c.call("tools/list")["result"]["tools"]
    names = [t["name"] for t in tools]
    expect(names[0] == "uak_next" and "uak_wait" in names and "uak_map" in names and len(names) == 14, str(names))
    expect(all(t["inputSchema"]["additionalProperties"] is False and "annotations" in t for t in tools), "strict schemas and annotations")
    expect(next(t for t in tools if t["name"] == "uak_map")["annotations"]["readOnlyHint"] is True, "map is read-only")
    expect("resultType" not in c.call("ping")["result"], "legacy results stay legacy")
    nxt = c.call("tools/call", {"name": "uak_next", "arguments": {"agent": "agent-1"}})["result"]
    expect(nxt["isError"] is False and "HACK-001 | AVAILABLE" in nxt["content"][0]["text"] and "structuredContent" not in nxt,
           "the model gets the uak text itself (clients show structuredContent instead of text): " + str(nxt)[:300])
    bad = c.call("tools/call", {"name": "uak_claim", "arguments": {"colour": "red"}})["result"]
    expect(bad["isError"] and "missing task" in bad["content"][0]["text"] and "unknown colour" in bad["content"][0]["text"], str(bad))
    claim = c.call("tools/call", {"name": "uak_claim", "arguments": {"task": "HACK-001", "agent": "agent-1"}})["result"]
    expect(claim["isError"] is False and "WT_READY: HACK-001" in claim["content"][0]["text"], str(claim)[:400])
    found = c.call("tools/call", {"name": "uak_map", "arguments": {"action": "find", "query": "helper"}})["result"]["content"][0]["text"]
    expect("lib/core.py:1  def helper" in found, found)
    learned = c.call("tools/call", {"name": "uak_memory", "arguments": {"action": "learn", "agent": "agent-1", "task": "HACK-001",
                                                                          "text": "helper() must stay pure: the cache relies on it"}})["result"]
    expect("OK learn #1" in learned["content"][0]["text"], str(learned))
    refused = c.call("tools/call", {"name": "uak_status", "arguments": {"task": "nope"}})["result"]
    expect(refused["isError"] and "Invalid ID" in refused["content"][0]["text"], "uak errors come back as actionable tool errors")
    res = [x["uri"] for x in c.call("resources/list")["result"]["resources"]]
    expect("uak://map" in res and "uak://card" in res, str(res))
    expect("| lib |" in c.call("resources/read", {"uri": "uak://map"})["result"]["contents"][0]["text"], "the map as a resource")
    expect("cache relies on it" in c.call("resources/read", {"uri": "uak://recall/HACK-001"})["result"]["contents"][0]["text"], "lessons by template")
    expect(c.call("resources/read", {"uri": "uak://nope"})["error"]["code"] == -32002, "legacy not-found code")
    pr = c.call("prompts/list")["result"]["prompts"]
    expect(any(p["name"] == "uak-ship" and p["description"].startswith("Use when") for p in pr), str(pr)[:300])
    got = c.call("prompts/get", {"name": "uak-review", "arguments": {"args": "HACK-001"}})["result"]["messages"][0]["content"]["text"]
    expect("review" in got.lower(), "slash workflows as MCP prompts")
    notes = []
    rid = c.send("tools/call", {"name": "uak_wait", "arguments": {"agent": "agent-1", "for": "message", "timeout": 60},
                                "_meta": {"progressToken": "w1"}})
    time.sleep(12)
    c.send("notifications/cancelled", {"requestId": rid}, notify=True)
    cancelled = c.wait(rid, 30, notes)
    expect(any(n.get("method") == "notifications/progress" and n["params"]["progressToken"] == "w1" for n in notes),
           "a long wait reports progress: " + str(notes)[:300])
    expect("result" in cancelled, "a cancelled call still answers: " + str(cancelled)[:200])
    c.close()
    m = Mcp(r, root)
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "1"}}
    disc = m.call("server/discover", {"_meta": meta})["result"]
    expect(disc["resultType"] == "complete" and "2026-07-28" in disc["supportedVersions"] and "2025-11-25" in disc["supportedVersions"]
           and disc["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "uak" and disc["instructions"], str(disc)[:300])
    lst = m.call("tools/list", {"_meta": meta})["result"]
    expect(lst["resultType"] == "complete" and lst["ttlMs"] > 0 and lst["cacheScope"] == "private", "modern list results are cacheable")
    old = m.call("tools/list", {"_meta": dict(meta, **{"io.modelcontextprotocol/protocolVersion": "1900-01-01"})})["error"]
    expect(old["code"] == -32022 and "2026-07-28" in old["data"]["supported"], str(old))
    expect(m.call("resources/read", {"uri": "uak://nope", "_meta": meta})["error"]["code"] == -32602, "modern not-found code")
    m.close()
    return {"tools": len(names)}


TESTS = [tokens_per_task_and_team, loop_guards_and_parallel, handover_and_assign, gemini_hooks, stacks_install,
         code_map_and_impact, lessons_follow_the_paths, wait_instead_of_polling, latency_paths, adoption_layer, mcp_server]


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
