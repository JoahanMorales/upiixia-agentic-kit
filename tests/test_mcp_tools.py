#!/usr/bin/env python3
"""The uak MCP server, tool by tool, in a real project.

Installs the kit into a fresh Git repo with a local bare remote, starts `.uak/bin/uak-mcp` over stdio and calls
every declared tool through JSON-RPC, the way an MCP client does: discovery, then a full task (claim, ship, review,
merge) plus messages, memory, the code map, checkpoints, tokens, waits and the CLI passthrough. Standard library
only; no network. Run: python3 tests/test_mcp_tools.py (the deeper protocol suite is kit/.uak/tests/, 158 scenarios).
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Git Bash on Windows: a bare "bash" there resolves to WSL's launcher in System32 first.
BASH = str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "bin" / "bash.exe") if os.name == "nt" else "bash"
TOOLS = ["uak_next", "uak_status", "uak_claim", "uak_ship", "uak_wait", "uak_review", "uak_merge", "uak_message",
         "uak_inbox", "uak_map", "uak_memory", "uak_checkpoint", "uak_tokens", "uak_cli"]
TASKS = """## APP-001 · Greeting API
- **Priority:** P0
- **Paths:** src/greet.py, tests/test_greet.py
- **Depends on:** None
- **Verify:** python3 tests/test_greet.py

## APP-002 · Docs
- **Priority:** P1
- **Paths:** docs/
- **Depends on:** APP-001
- **Verify:** true
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


class Server:
    """A JSON-RPC client over the server's stdio (newline-delimited JSON)."""

    def __init__(self, cwd, env, argv=None, stderr=subprocess.DEVNULL):
        self.p = subprocess.Popen(argv or [sys.executable, ".uak/bin/uak-mcp"], cwd=cwd, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=stderr, text=True, encoding="utf-8", env=env)
        self.q, self.n = queue.Queue(), 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            self.q.put(json.loads(line))

    def call(self, method, params=None, timeout=180):
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = self.q.get(timeout=1)
            except queue.Empty:
                continue
            if msg.get("id") == self.n:
                return msg
        raise AssertionError("no answer to %s" % method)

    def tool(self, name, timeout=180, **arguments):
        msg = self.call("tools/call", {"name": name, "arguments": arguments}, timeout)
        assert "error" not in msg, "%s: JSON-RPC error %s" % (name, msg)
        result = msg["result"]
        text = "".join(c.get("text", "") for c in result.get("content", []))
        return result.get("isError", False), text

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=30)


class McpTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="uak-mcp-tools-"))
        cls.env = dict(os.environ, GIT_TERMINAL_PROMPT="0", UAK_DEDUPE="off", UAK_HARNESS="test", UAK_BLACKBOX="off")
        for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "UAK_AGENT", "UAK_HUMAN", "UAK_TASK"):
            cls.env.pop(k, None)
        remote = cls.tmp / "remote.git"
        git(cls.tmp, "init", "-q", "--bare", str(remote))
        cls.repo = repo = cls.tmp / "app"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.name", "Test"); git(repo, "config", "user.email", "test@example.invalid")
        subprocess.run([BASH, str(REPO / "install.sh"), "--mode", "sprint", "--harness", "claude", str(repo)],
                       check=True, capture_output=True, text=True, env=cls.env)
        git(repo, "remote", "add", "origin", str(remote))
        (repo / ".uak/TASKS.md").write_text(TASKS, encoding="utf-8")
        project = repo / ".uak/PROJECT.md"
        text = project.read_text(encoding="utf-8").replace("Backlog-Approved: no", "Backlog-Approved: yes")
        project.write_text(text.replace("Plan-Channel: claims", "Plan-Channel: main").replace("Freeze-Epoch: 0", "Freeze-Epoch: 9999999999"), encoding="utf-8")
        (repo / ".uak/OWNERS.md").write_text("# Shared-file owners\n\n| Pattern | Owner task |\n|---|---|\n", encoding="utf-8")
        (repo / "src").mkdir(); (repo / "src/greet.py").write_text("def greet(name):\n    return 'hi'\n", encoding="utf-8")
        git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "setup"); git(repo, "push", "-q", "-u", "origin", "main")
        human = dict(cls.env, UAK_HUMAN="tester", UAK_AGENT="")
        subprocess.run([BASH, ".uak/bin/uak", "register-reviewer", "rev-1"], cwd=repo, check=True, capture_output=True, env=human)
        cls.mcp = Server(repo, cls.env)

    @classmethod
    def tearDownClass(cls):
        cls.mcp.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_1_discovery(self):
        init = self.mcp.call("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                            "clientInfo": {"name": "tests", "version": "1"}})["result"]
        self.assertEqual(init["protocolVersion"], "2025-11-25")
        self.assertIn("tools", init["capabilities"])
        tools = self.mcp.call("tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], TOOLS, "every declared tool, in order")
        for t in tools:
            self.assertTrue(t["description"], t["name"])
            self.assertEqual(t["inputSchema"]["type"], "object", t["name"])
            self.assertFalse(t["inputSchema"].get("additionalProperties", True), t["name"] + " rejects unknown arguments")
            self.assertIn("readOnlyHint", t.get("annotations", {}), t["name"])

    def test_2_unknown_arguments_are_refused(self):
        bad, text = self.mcp.tool("uak_claim", colour="red")
        self.assertTrue(bad, text)

    def test_3_a_task_end_to_end(self):
        bad, text = self.mcp.tool("uak_next", agent="dev-1")
        self.assertFalse(bad, text); self.assertIn("APP-001 | AVAILABLE", text)
        bad, text = self.mcp.tool("uak_status")
        self.assertFalse(bad, text); self.assertIn("AVAILABLE=2", text)
        bad, text = self.mcp.tool("uak_claim", task="APP-001", agent="dev-1")
        self.assertFalse(bad, text); self.assertIn("OK claim APP-001", text)
        wt = Path(next(l.split(" · worktree ", 1)[1].strip() for l in text.splitlines() if l.startswith("WT_READY")))
        (wt / "tests").mkdir(exist_ok=True)
        (wt / "src/greet.py").write_text("def greet(name):\n    return 'hi ' + name\n", encoding="utf-8")
        (wt / "tests/test_greet.py").write_text("import sys; sys.path.insert(0, 'src')\nfrom greet import greet\nassert greet('ana') == 'hi ana'\n", encoding="utf-8")
        git(wt, "add", "-A"); git(wt, "commit", "-q", "-m", "feat: greet"); git(wt, "push", "-q", "-u", "origin", "HEAD")
        bad, text = self.mcp.tool("uak_checkpoint", task="APP-001", agent="dev-1", done="greet", decision="-", why="-",
                                  fails="-", commands="python3 tests/test_greet.py", next="ship")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_ship", task="APP-001", agent="dev-1", pr="https://example.test/pull/1",
                                  evidence="python3 tests/test_greet.py exit 0")
        self.assertFalse(bad, text); self.assertIn("REVIEW", text)
        sha = git(wt, "rev-parse", "HEAD").strip()
        bad, text = self.mcp.tool("uak_review", task="APP-001", agent="rev-1", action="start")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_review", task="APP-001", agent="rev-1", action="approve", sha=sha,
                                  note="src/greet.py:2 · verified with python3 tests/test_greet.py")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_wait", task="APP-001", agent="dev-1", **{"for": "approve", "timeout": 5})
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_merge", timeout=600, task="APP-001", agent="dev-1")  # the gate forks a lot: slow on Windows
        self.assertTrue("INTEGRATED" in text or "MERGE_HUMAN" in text, text)   # the gate answers either way, never a crash

    def test_4_messages_memory_map_tokens_cli(self):
        bad, text = self.mcp.tool("uak_message", agent="dev-2", to="all", text="docs wait on APP-001 · nothing to do yet", kind="info")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_inbox", agent="dev-1")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_memory", agent="dev-1", action="learn", text="greet() joins with one space · src/greet.py · keep it", paths="src/")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_memory", agent="dev-1", action="recall", paths="src/greet.py")
        self.assertFalse(bad, text); self.assertIn("one space", text)
        bad, text = self.mcp.tool("uak_map", action="show")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_tokens")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_cli", args=["version"])
        self.assertFalse(bad, text); self.assertEqual(text.strip(), (REPO / "kit/.uak/VERSION").read_text(encoding="utf-8").strip())

    def test_6_text_arrives_as_written(self):
        """Windows: Git Bash re-parsed the command line, so df['count'] reached uak as df[count] and * was globbed."""
        tricky = "df['count'] shadows * and [x] · \"quoted\" C:\\tmp\\ · don't · niño"
        bad, text = self.mcp.tool("uak_memory", agent="dev-1", action="learn", text=tricky, paths="docs/")
        self.assertFalse(bad, text)
        bad, text = self.mcp.tool("uak_memory", agent="dev-1", action="recall", paths="docs/a.md")
        self.assertFalse(bad, text); self.assertIn(tricky, text)

    def test_5_started_as_the_harness_starts_it(self):
        """Windows: "bash" from .mcp.json was WSL's launcher in System32, and so was every tool's bash."""
        cfg = json.loads((self.repo / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["uak"]
        env = dict(self.env)
        if os.name == "nt":  # a user's PATH: Git for Windows adds only Git\cmd, not Git\bin or usr\bin
            win = os.environ.get("SystemRoot", "C:\\Windows")
            git_cmd = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Git" / "cmd"
            py = Path(sys.executable).parent
            env["PATH"] = os.pathsep.join([win + "\\System32", win, win + "\\System32\\WindowsPowerShell\\v1.0", str(git_cmd), str(py), str(py / "Scripts")])
        exe = shutil.which(cfg["command"], path=env["PATH"]) or cfg["command"]  # what a harness's spawn finds on PATH
        sub = self.repo / "src"; sub.mkdir(exist_ok=True)
        for cwd in (self.repo, sub):
            err = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
            s = Server(cwd, env, [exe] + cfg["args"], stderr=err)
            try:
                s.call("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "tests", "version": "1"}})
                bad, text = s.tool("uak_status")
            except AssertionError as e:
                err.seek(0)
                raise AssertionError("%s · PATH=%s · stderr: %s" % (e, env["PATH"], err.read()[-1500:]))
            finally:
                s.close()
            self.assertFalse(bad, text)
            self.assertIn("APP-001", text, "the tool ran uak, from %s: %s" % (cwd, text[:300]))
            self.assertNotIn("Windows Subsystem", text.replace("\x00", ""))


class Manifest(unittest.TestCase):
    def test_server_json_matches_the_kit(self):
        manifest = json.loads((REPO / "server.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], (REPO / "kit/.uak/VERSION").read_text(encoding="utf-8").strip())
        self.assertTrue(manifest["name"].startswith("io.github.JoahanMorales/"))
        self.assertLessEqual(len(manifest["description"]), 100, "the registry caps descriptions at 100 characters")
        self.assertTrue((REPO / manifest["repository"]["subfolder"] / "uak-mcp").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
