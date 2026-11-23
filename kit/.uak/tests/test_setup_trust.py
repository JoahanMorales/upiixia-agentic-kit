#!/usr/bin/env python3
"""Workspace trust from the setup UI (UI-008): in a new folder Claude Code ignores the project's allow rules until the
folder is trusted once interactively. The page says so before planning, names that cause when a planning run fails on
it, and the planner reads files with its Read tool so one denied command does not end the run.
Real HTTP, real Git with a local bare remote, and a fake planner in place of the coding tool."""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import test_setup_planning as plans
import test_setup_prepare as prep
import test_setup_team as team_tests
import test_setup_wizard as wizard
from test_hack import resolve_binary

UNTRUSTED = ("Ignoring 51 permissions.allow entries from .claude/settings.json: this workspace has not been trusted. "
             "Run Claude Code interactively here once and accept the trust dialog.\n")


class UntrustedPlanner(plans.FakePlanner):
    """The coding tool in an untrusted folder: it prints Claude Code's trust warning, and writes the plan or not."""

    def __init__(self, writes):
        super().__init__()
        self.writes = writes

    def __call__(self, command, cwd=None, timeout=120, **kwargs):
        name = Path(command[0]).name.lower().replace(".exe", "").replace(".cmd", "")
        if name not in ("claude", "codex") or command[1:3] in (["auth", "status"], ["login", "status"]):
            return super().__call__(command, cwd=cwd, timeout=timeout, **kwargs)
        if self.writes:
            result = super().__call__(command, cwd=cwd, timeout=timeout, **kwargs)
            return subprocess.CompletedProcess(command, 0, result.stdout, UNTRUSTED)
        self.calls.append({"argv": list(command), "cwd": cwd})
        return subprocess.CompletedProcess(command, 0, '{"type":"result","result":"Bash(cat IDEA.md) was denied"}\n',
                                           UNTRUSTED)


def lib(root, name):
    return (root / ".uak/bin/lib" / name).read_text(encoding="utf-8")


def catalog(root):
    text = lib(root, "workspace.js")
    pairs = re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)
    return {json.loads(a): json.loads(b) for a, b in pairs}


def section(html, ident):
    start = html.rindex("<", 0, html.index('id="%s"' % ident))
    tag = re.match(r"<(\w+)", html[start:]).group(1)
    depth = 0
    for m in re.finditer(r"<(/?)%s\b[^>]*>" % tag, html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start:start + m.end()]
    raise AssertionError("unclosed #%s" % ident)


def visible(fragment):
    fragment = re.sub(r"<(code|script|style)\b[\s\S]*?</\1>", " ", fragment)
    return [" ".join(t.split()) for t in re.split(r"<[^>]+>", fragment) if re.search(r"[A-Za-z]{2}", t)]


def trust_step_is_shown_before_planning(root, tmp):
    target, _ = plans.project(root, tmp)
    with plans.live(target, plans.FakePlanner()) as srv:
        assert plans.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        status, view = plans.get(srv, "/api/plan")
        assert status == 200, view
        expected = "cd '%s' && claude" % target.resolve().as_posix()
        assert view.get("trust_command") == expected, "the plan view gives the exact trust command: %r" % view.get(
            "trust_command")
    (tmp / "codex only").mkdir()
    codex, _ = plans.project(root, tmp / "codex only", harnesses=("codex",))
    with plans.live(codex, plans.FakePlanner()) as srv:
        assert plans.post(srv, "/api/inspect", {"target": str(codex)})[0] == 200
        assert not plans.get(srv, "/api/plan")[1].get("trust_command"), "a Codex-only project shows no trust notice"
    html = lib(root, "setup.html")
    planning = section(html, "planning")
    assert 'id="plan-trust"' in planning, "the planning step has a trust notice"
    assert planning.index('id="plan-trust"') < planning.index('id="plan-create"'), "it comes before Create the plan"
    trust = section(html, "plan-trust")
    assert 'id="plan-trust-command"' in trust and 'id="copy-plan-trust"' in trust, "the command has a Copy button"
    words = " ".join(visible(trust)).lower()
    assert "trust" in words and "once" in words, "it says to accept the trust question once: %r" % words
    es = catalog(root)
    missing = [t for t in visible(trust) if t not in es]
    assert not missing, "every line of the trust notice has Spanish: %r" % missing
    team = " ".join(visible(section(html, "team-implement"))).lower()
    assert "trust" in team, "the team step says Claude Code asks to trust the worktree folder the first time"
    readme = (root.parent / "README.md").read_text(encoding="utf-8") if (root.parent / "README.md").is_file() else ""
    assert re.search(r"trust", readme, re.I) and "not been trusted" in readme, \
        "README says to open Claude Code once in the folder and accept trust"


def untrusted_planning_run_names_the_cause(root, tmp):
    target, _ = plans.project(root, tmp)
    with plans.live(target, UntrustedPlanner(writes=False)) as srv:
        plans.planned(srv, target)
        status, state = plans.get(srv, "/api/status")
        assert status == 200
        assert state.get("phase") == "error", "a run that wrote no plan is not 'planned': %r" % state.get("phase")
        error = state.get("error", "")
        assert "trust" in error.lower() and "Claude Code" in error, "the cause is named: %r" % error
        assert error in catalog(root), "the trust error has Spanish: %r" % error
        assert "not been trusted" in state.get("details", ""), "Technical details keep the tool's own line"
    (tmp / "second").mkdir()
    target2, _ = plans.project(root, tmp / "second")
    with plans.live(target2, UntrustedPlanner(writes=True)) as srv:
        plans.planned(srv, target2)
        status, state = plans.get(srv, "/api/status")
        assert state.get("phase") == "planned" and not state.get("error"), \
            "the warning alone does not fail a run that wrote the plan: %r" % state


def planner_survives_a_denied_read(root, tmp):
    prompt = plans.PLANNING.PLANNER_PROMPT
    assert "Read tool" in prompt, "the planner reads files with its Read tool, not shell commands"
    assert "stop and report" not in prompt, "a denied command no longer ends the run"
    assert re.search(r"denied.{0,80}continue", prompt), "a denied command is skipped and the run continues: %r" % prompt
    assert not re.search(r"[%^&|<>\"`]", prompt), "the prompt still survives a Windows .cmd shim"
    argv = plans.PLANNING.planner_command("claude", tmp, binary="/fake/bin/claude")
    tools = argv[argv.index("--tools") + 1].split(",")
    assert "Read" in tools and "Glob" in tools, tools


# UAK-153: the wizard acts for the human only when a human runs it (audit, 2026-11-22).
def human_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    env.update(extra)
    return env


def terminal_input():
    """What a person's terminal gives a process on POSIX: stdin is a terminal (a pty). (None, DEVNULL) elsewhere: on
    Windows the wizard asks for no terminal."""
    if os.name == "nt":
        return None, subprocess.DEVNULL
    master, slave = os.openpty()
    return master, slave


def popen_with_terminal(argv, **kwargs):
    master, slave = terminal_input()
    proc = subprocess.Popen(argv, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace", **kwargs)
    if master is not None:
        os.close(slave)
    proc.master = master
    return proc


def start_wizard(root, cwd, target, env, args=("--no-open",)):
    """The wizard as a person starts it: a real process with a terminal on its input."""
    return popen_with_terminal([sys.executable, str(root / ".uak/bin/lib/setup.py")] + list(args) + [str(target)],
                               cwd=str(cwd), env=env)


def stop(proc):
    proc.terminate()
    try:
        proc.wait(15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(15)
    out, err = proc.stdout.read(), proc.stderr.read()
    proc.stdout.close()
    proc.stderr.close()
    if getattr(proc, "master", None) is not None:
        os.close(proc.master)
    # A killed wizard cannot remove its launcher folder: the test does, so nothing accumulates in the temp folder.
    for line in (getattr(proc, "seen", []) + out.splitlines()):
        found = re.match(r"Launcher file: (.+)open\.html\s*$", line)
        if found:
            shutil.rmtree(found.group(1), ignore_errors=True)
    return out, err


def first_lines(proc, count=3, seconds=60):
    box = []

    def read():
        for _ in range(count):
            line = proc.stdout.readline()
            if not line:
                return
            box.append(line)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    reader.join(seconds)
    proc.seen = [line.rstrip("\n") for line in box]
    return box


def launcher_code(lines):
    """The one-time code, read from the launcher file the terminal names (never printed itself)."""
    for line in lines:
        match = re.search(r"(?:file|File):?\s*(\S.*?(?:\.html))\s*$", line.strip())
        if match and Path(match.group(1)).is_file():
            text = Path(match.group(1)).read_text(encoding="utf-8")
            found = re.search(r"#code=([A-Za-z0-9_-]+)", text)
            if found:
                return found.group(1)
    return ""


def agent_identity_cannot_start_the_wizard(root, tmp):
    target, _ = plans.project(root, tmp)
    elsewhere = tmp / "elsewhere"
    elsewhere.mkdir()
    cases = []
    cases.append(("UAK_AGENT in the environment", target, human_env(UAK_AGENT="kit-a1"), "UAK_AGENT"))
    # A .uak-env naming an agent, in the project.
    (tmp / "x1").mkdir()
    env_target, _ = plans.project(root, tmp / "x1")
    (env_target / ".uak-env").write_text("UAK_AGENT=kit-b2\n", encoding="utf-8")
    cases.append((".uak-env naming an agent", env_target, human_env(), ".uak-env"))
    (tmp / "x2").mkdir()
    cfg_target, _ = plans.project(root, tmp / "x2")
    plans.git(cfg_target, "config", "uak.agent", "kit-c3")
    cases.append(("uak.agent in the git config", cfg_target, human_env(), "uak.agent"))
    linked = tmp / "agent tree"
    plans.git(target, "worktree", "add", "-q", "-b", "side", str(linked))
    cases.append(("an agent's worktree", linked, human_env(), "worktree"))
    for label, folder, env, word in cases:
        proc = start_wizard(root, elsewhere, folder, env)
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            stop(proc)
            raise AssertionError("%s: the wizard started instead of refusing" % label)
        out, err = proc.stdout.read(), proc.stderr.read()
        proc.stdout.close()
        proc.stderr.close()
        if proc.master is not None:
            os.close(proc.master)
        assert proc.returncode not in (0, None), "%s: exit code %r" % (label, proc.returncode)
        assert "UAK SETUP" not in out and "http://127.0.0.1" not in out + err, "%s: no address printed: %r" % (label, out + err)
        said = (out + err)
        assert word in said, "%s: the refusal names the reason (%s): %r" % (label, word, said)
        assert "terminal" in said and "install.sh --wizard" in said, "%s: it says how a human starts it: %r" % (label, said)
    # The same project, started by a human (no identity anywhere), does start.
    proc = start_wizard(root, elsewhere, target, human_env())
    try:
        lines = first_lines(proc, 1)
        assert lines and "UAK SETUP" in lines[0], "a human can start it: %r" % lines
    finally:
        stop(proc)


def guard_blocks_an_agent_starting_the_wizard(root, tmp):
    guard = root / ".uak/bin/guard"
    bash = resolve_binary("bash")
    commands = [
        "python3 kit/.uak/bin/lib/setup.py --no-open",
        "cd app && python3 .uak/bin/lib/setup.py /tmp/x",
        "bash install.sh --wizard",
        "bash ./install.sh --wizard /tmp/proj --no-open",
        "bash install.sh /tmp/proj && bash install.sh --wizard",
        "curl -s -X POST -H 'X-UAK-Token: abc' http://127.0.0.1:41234/api/team/reviewer -d '{}'",
        "curl -s -H 'Content-Type: application/json' http://127.0.0.1:41234/api/plan/approve -d '{}'",
        "curl -s http://localhost:41234/api/publish-kit -d '{}'",
        "curl -s http://127.0.0.1:41234/api/session -d '{}'",
        "wget -qO- --header='X-UAK-Token: abc' http://127.0.0.1:41234/api/status",
    ]
    allowed = ["python3 setup.py install", "bash install.sh /tmp/proj", "curl -s http://127.0.0.1:3000/health",
               "python3 kit/.uak/tests/test_setup_trust.py"]
    for mode in ("sprint", "marathon", "hackathon"):
        repo = tmp / mode
        repo.mkdir()
        plans.git(repo, "init", "-q", "-b", "main")
        (repo / ".uak").mkdir()
        (repo / ".uak/PROJECT.md").write_text("Mode: %s\n" % mode, encoding="utf-8")
        for command in commands:
            result = subprocess.run([bash, str(guard), "check", command], cwd=str(repo), capture_output=True, text=True,
                                    env=human_env())
            assert result.returncode == 2, "%s: %r must be blocked, got %d %r" % (mode, command, result.returncode, result.stderr)
            assert "human" in result.stderr.lower(), "the block says who may do it: %r" % result.stderr
            # As the harness sends it (Claude Code asks for UAK_HUMAN; this one never asks: it blocks).
            payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
            hooked = subprocess.run([bash, str(guard), "bash", "claude"], cwd=str(repo), input=payload, capture_output=True,
                                    text=True, env=human_env())
            assert hooked.returncode == 2, "%s: the hook blocks %r too: %d %r" % (mode, command, hooked.returncode, hooked.stdout)
        for command in allowed:
            result = subprocess.run([bash, str(guard), "check", command], cwd=str(repo), capture_output=True, text=True,
                                    env=human_env())
            assert result.returncode == 0, "%s: %r stays allowed: %r" % (mode, command, result.stderr)


def token_is_not_printed_or_in_argv(root, tmp):
    target, _ = plans.project(root, tmp)
    seen = tmp / "browser argv.txt"
    # Python's webbrowser picks a program by machine (BROWSER, DISPLAY, the registered order), so the test does not
    # depend on one: the wizard runs under a wrapper that records what it hands to webbrowser.open(), the one place
    # it opens a browser. Nothing else of the wizard changes (runpy runs setup.py as __main__).
    wrapper = tmp / "wrapper.py"
    wrapper.write_text(
        "import runpy, sys, webbrowser\n"
        "log, setup = sys.argv[1], sys.argv[2]\n"
        "def record(url, *args, **kwargs):\n"
        "    with open(log, 'a', encoding='utf-8') as handle:\n"
        "        handle.write(url + '\\n')\n"
        "    return True\n"
        "webbrowser.open = record\n"
        "sys.argv = [setup] + sys.argv[3:]\n"
        "runpy.run_path(setup, run_name='__main__')\n", encoding="utf-8")
    proc = popen_with_terminal([sys.executable, str(wrapper), str(seen), str(root / ".uak/bin/lib/setup.py"), str(target)],
                               cwd=str(tmp), env=human_env())
    try:
        lines = first_lines(proc, 3)
        assert lines and "UAK SETUP" in lines[0], lines
        port = int(re.search(r"127\.0\.0\.1:(\d+)", lines[0]).group(1))
        deadline = time.time() + 20
        while time.time() < deadline and not seen.is_file():
            time.sleep(0.1)
        opened = seen.read_text(encoding="utf-8").split() if seen.is_file() else []
        assert len(opened) == 1 and opened[0].startswith("file:") and opened[0].endswith("/open.html"), \
            "the browser is opened on the launcher file: %r" % opened
        code = launcher_code(lines)
        assert code, "the one-time code is in the launcher page, which the terminal names: %r" % lines
        assert code not in opened[0] and code not in "".join(lines), "the code is neither printed nor in the browser's argument"
        sess = types_namespace(port, "")
        status, body, _ = wizard.request(sess, "POST", "/api/session", {"code": code}, token=False)
        assert status == 200, body
        token = json.loads(body)["token"]
        assert token not in opened[0] and token not in "".join(lines), "the session token is never printed"
        if os.path.isdir("/proc/%d" % proc.pid):
            cmdline = Path("/proc/%d/cmdline" % proc.pid).read_bytes().decode("utf-8", "replace")
            assert token not in cmdline and code not in cmdline, "the server's own arguments hold no secret"
        sess = types_namespace(port, token)
        assert wizard.request(sess, "GET", "/api/status")[0] == 200, "the exchanged session works"
    finally:
        out, err = stop(proc)
    assert token not in out + err and code not in out + err, "nothing printed later holds the token or the code"


def types_namespace(port, token):
    import types
    return types.SimpleNamespace(server_port=port, token=token)


def one_time_code_works_once(root, tmp):
    target, _ = plans.project(root, tmp)
    with plans.live(target, plans.FakePlanner()) as srv:
        code = srv.code
        assert code and code != srv.token, "the code is not the session token"
        fake = types_namespace(srv.server_port, "")
        assert wizard.request(fake, "GET", "/api/status", token=False)[0] == 403, "no session, no data"
        assert wizard.request(fake, "POST", "/api/session", {"code": "wrong"}, token=False)[0] in (400, 403)
        status, body, _ = wizard.request(fake, "POST", "/api/session", {"code": code}, token=False)
        assert status == 200 and json.loads(body)["token"] == srv.token, body
        assert wizard.request(fake, "POST", "/api/session", {"code": code}, token=False)[0] in (400, 403), \
            "the second exchange of the same code is refused"
        # A code the person never used expires.
        srv.new_code()
        stale = srv.code
        srv.clock = lambda: time.monotonic() + 10000
        assert wizard.request(fake, "POST", "/api/session", {"code": stale}, token=False)[0] in (400, 403), "an old code is refused"
        # The exchange is still a same-origin request on the right Host.
        srv.clock = time.monotonic
        srv.new_code()
        assert wizard.request(fake, "POST", "/api/session", {"code": srv.code}, token=False, origin=False)[0] == 403
        assert wizard.request(fake, "POST", "/api/session", {"code": srv.code}, token=False,
                              extra={"Host": "evil.example"})[0] == 403


def idle_session_ends(root, tmp):
    target, _ = plans.project(root, tmp)
    with plans.live(target, plans.FakePlanner()) as srv:
        said = []
        srv.notify = said.append
        now = [1000.0]
        srv.clock = lambda: now[0]
        srv.touch()
        assert wizard.request(srv, "GET", "/api/status")[0] == 200
        now[0] += 29 * 60
        assert plans.post(srv, "/api/inspect", {"target": str(target)})[0] == 200, "activity inside 30 minutes keeps it"
        now[0] += 29 * 60
        assert wizard.request(srv, "GET", "/api/status")[0] == 200, "30 minutes counted from the last action"
        now[0] += 31 * 60
        status, body, _ = wizard.request(srv, "GET", "/api/status")
        assert status == 403, "an idle session ends: %d" % status
        assert "30 minutes" in json.loads(body)["error"], body
        assert said and "30 minutes" in said[0] and "install.sh --wizard" in said[0], \
            "the terminal says how to open a new one: %r" % said
        assert wizard.request(srv, "GET", "/api/status")[0] == 403, "the old token stays dead"
        assert wizard.request(srv, "POST", "/api/session", {"code": srv.code}, token=False)[0] in (400, 403), \
            "an ended session is not reopened by an old code"


def human_name_is_the_git_identity(root, tmp):
    target, _ = plans.project(root, tmp)
    with plans.live(target, plans.FakePlanner()) as srv:
        status, state = plans.post(srv, "/api/inspect", {"target": str(target)})
        assert status == 200 and state.get("git_human") == "ana", "the page is shown the identity: %r" % state.get("git_human")
        for other in ("bob", "root", "ana-human", "Ana", ""):
            status, body = plans.post(srv, "/api/human", {"name": other})
            assert status == 400, "%r is not this checkout's identity: %d %r" % (other, status, body)
            assert plans.get(srv, "/api/status")[1].get("human") in ("", None), "nothing was saved"
        status, body = plans.post(srv, "/api/human", {"name": "ana"})
        assert status == 200 and body["human"] == "ana", body
    # No Git name: nobody can be named.
    (tmp / "nameless").mkdir()
    bare, _ = plans.project(root, tmp / "nameless")
    plans.git(bare, "config", "--unset", "user.name")
    with plans.live(bare, plans.FakePlanner()) as srv:
        isolated = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        old = {k: os.environ.get(k) for k in isolated}
        os.environ.update(isolated)
        try:
            assert plans.post(srv, "/api/inspect", {"target": str(bare)})[0] == 200
            status, body = plans.post(srv, "/api/human", {"name": "ana"})
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        assert status == 400 and "git config user.name" in body.get("error", ""), body


def log_lines(target):
    gd = Path(plans.git(target, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    path = gd / "uak-direct-main.log"
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def human_acts_are_logged(root, tmp):
    # Publishing the kit.
    target, remote = prep.installed(root, tmp)
    with plans.live(target, plans.FakePlanner()) as srv:
        prep.ready_to_publish(srv, target)
        before = len(log_lines(target))
        prep.publish(srv)
    lines = log_lines(target)[before:]
    head = prep.remote_head(remote)
    assert len(lines) == 1, "publishing writes one line: %r" % lines
    fields = lines[0].split()
    assert fields[0].isdigit() and abs(int(fields[0]) - time.time()) < 600, lines[0]
    assert fields[1:] == ["ana", "publish-kit", head], "who, what and the commit: %r (remote %s)" % (lines[0], head)
    # Approving the plan.
    (tmp / "plan").mkdir()
    target, remote = plans.project(root, tmp / "plan")
    with plans.live(target, plans.FakePlanner()) as srv:
        plan = plans.planned(srv, target)
        assert plans.post(srv, "/api/human", {"name": "ana"})[0] == 200
        before = len(log_lines(target))
        status, body = plans.post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
        assert status == 202, body
        plans.wait_idle(srv)
        assert not plans.get(srv, "/api/status")[1].get("error")
    lines = log_lines(target)[before:]
    assert len(lines) == 1 and lines[0].split()[1:] == ["ana", "approve-plan", plans.git(target, "rev-parse", "HEAD")], lines
    # Registering a reviewer (the engine's own command).
    (tmp / "team").mkdir()
    team_tests.MODULE = wizard.MODULE
    target, remote = team_tests.ready_project(root, tmp / "team")
    team = team_tests.Team()
    with plans.live(target, team) as srv:
        team_tests.ready(srv, target)
        before = len(log_lines(target))
        status, body, state = team_tests.register(srv, "ana-r")
        assert status in (200, 202) and not state.get("error"), (status, body, state)
    lines = log_lines(target)[before:]
    assert len(lines) == 1 and lines[0].split()[1:3] == ["ana", "register-reviewer"], lines
    assert len(lines[0].split()) == 5 and re.fullmatch(r"[0-9a-f]{40}", lines[0].split()[4]), lines
    assert lines[0].split()[3] == "ana-r", "it names who was registered: %r" % lines


# UAK-153 (review of 9c0bc32): the barrier is the wizard's own refusals and a guard that reads what a command mentions.
BLOCKED = [
    # driving a running wizard: other clients
    "python3 -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:41234/api/publish-kit', b'x')\"",
    "python3 -c 'import requests; requests.post(\"http://localhost:41234/api/team/reviewer\", json={})'",
    "node -e \"fetch('http://127.0.0.1:41234/api/plan/approve', {method: 'POST'})\"",
    "printf 'POST /api/publish-kit HTTP/1.0\\r\\n\\r\\n' | nc 127.0.0.1 41234",
    "exec 3<>/dev/tcp/127.0.0.1/41234; echo 'POST /api/human HTTP/1.0' >&3",
    # address forms
    "curl -s http://[::1]:41234/api/session -d '{}'",
    "curl -s http://127.1:41234/api/session -d '{}'",
    "curl -s http://127.0.0.2:41234/api/publish-kit -d '{}'",
    "curl -s http://2130706433:41234/api/publish-kit -d '{}'",
    "curl -s http://0x7f000001:41234/api/publish-kit -d '{}'",
    "curl -s http://0.0.0.0:41234/api/human -d '{}'",
    # path forms
    "curl -s http://127.0.0.1:41234//api/publish-kit -d '{}'",
    "curl -s http://127.0.0.1:41234/./api/publish-kit -d '{}'",
    "curl -s http://127.0.0.1:41234/%61pi/publish-kit -d '{}'",
    "curl -s http://127.0.0.1:41234/api/./session -d '{}'",
    "curl -s http://127.0.0.1:41234/API/Publish-Kit -d '{}'",
    # the token header in any case, and a path held in variables
    "curl -s -H 'x-uak-token: abc' http://127.0.0.1:41234/api/status",
    "curl -s -H 'X-Uak-Token: abc' http://127.0.0.1:41234/api/status",
    "U=http://127.0.0.1:41234/api/publish-kit; curl -s -d '{}' $U",
    "A=/api; B=/publish-kit; curl -s -d '{}' http://127.0.0.1:41234${A}${B}",
    "curl -s -d '{}' http://127.0.0.1:41234/api/pub''lish-kit",
    # starting it: other forms
    "cd .uak/bin/lib && python3 setup.py",
    "cd kit/.uak/bin/lib; python3 setup.py --no-open",
    "python3 -m setup",
    "python3 -c \"import setup; setup.main()\"",
    "python3 -c \"import runpy; runpy.run_path('.uak/bin/lib/setup.py', run_name='__main__')\"",
    "python3 -c \"exec(open('.uak/bin/lib/setup.py').read())\"",
    "python3 -c \"import importlib; importlib.import_module('setup').main()\"",
    "python3 kit/.uak/bin/lib/*up.py",
    "python3 kit/.uak/bin/lib/s[e]tup.py",
    "python3 kit/.uak/bin/lib/?etup.py",
    "python3 kit/.uak/bin/lib/setu\\p.py",
    "python3 kit/.uak/bin/lib/se''tup.py",
    "P=kit/.uak/bin/lib/set; python3 ${P}up.py",
    "P=kit/.uak/bin/lib; python3 $P/setup.py",
    "./kit/.uak/bin/lib/setup.py --no-open",
    "nohup python3 kit/.uak/bin/lib/setup.py &",
    "W=--wizard; bash install.sh $W",
    "W=--wiz''ard; bash install.sh ${W}",
    "bash install.sh --wizard=1",
    "bash install.sh '--wizard'",
    "bash -c 'bash install.sh --wizard'",
    "env UAK_SETUP_BASH=bash bash install.sh --wizard /tmp/proj",
]
ALLOWED = [
    "curl -s http://localhost:3000/health",
    "curl -s http://127.0.0.1:3000/api/orders",
    "python3 setup.py install",
    "python3 -m json.tool data.json",
    "python3 -c \"import setuptools; print(setuptools.__version__)\"",
    "bash install.sh /tmp/proj",
    "bash install.sh --mode sprint --stack none /tmp/proj",
    "python3 kit/.uak/tests/test_setup_trust.py",
    "cd kit/.uak/tests && python3 test_setup_wizard.py",
    "python3 -m py_compile kit/.uak/bin/lib/setup.py",
    "cd kit/.uak/bin/lib && python3 -m py_compile setup.py",
    "grep -n 'api/publish-kit' kit/.uak/bin/lib/setup.py",
    "cat kit/.uak/bin/lib/setup.py",
    "git commit -m 'fix: /api/session is exchanged once and --wizard says why'",
    "rg -n wizard docs/DASHBOARD.md",
    "bash .uak/bin/uak status",
]


def run_guard(bash, guard, repo, command, hook=False):
    if hook:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return subprocess.run([bash, str(guard), "bash", "claude"], cwd=str(repo), input=payload, capture_output=True,
                              text=True, env=human_env())
    return subprocess.run([bash, str(guard), "check", command], cwd=str(repo), capture_output=True, text=True,
                          env=human_env())


def guard_reads_what_a_command_mentions(root, tmp):
    guard = root / ".uak/bin/guard"
    bash = resolve_binary("bash")
    for mode in ("sprint", "marathon"):
        repo = tmp / mode
        repo.mkdir()
        plans.git(repo, "init", "-q", "-b", "main")
        (repo / ".uak").mkdir()
        (repo / ".uak/PROJECT.md").write_text("Mode: %s\n" % mode, encoding="utf-8")
        for command in BLOCKED:
            result = run_guard(bash, guard, repo, command)
            assert result.returncode == 2, "%s: %r must be blocked, got %d %r" % (mode, command, result.returncode, result.stderr)
            assert "human" in result.stderr.lower(), "the block says who may do it: %r" % result.stderr
        for command in ALLOWED:
            result = run_guard(bash, guard, repo, command)
            assert result.returncode == 0, "%s: %r stays allowed: %d %r" % (mode, command, result.returncode, result.stderr)
    # As the harness sends it, on a sample of both lists.
    for command in BLOCKED[::5]:
        assert run_guard(bash, guard, repo, command, hook=True).returncode == 2, "the hook blocks %r too" % command
    for command in ALLOWED[::4]:
        assert run_guard(bash, guard, repo, command, hook=True).returncode == 0, "the hook allows %r too" % command


def wizard_refuses_without_a_terminal(root, tmp):
    if os.name == "nt":
        return  # no terminal check on Windows (SECURITY.md): its barrier is the identity refusal and the guard
    target, _ = plans.project(root, tmp)
    proc = subprocess.Popen([sys.executable, str(root / ".uak/bin/lib/setup.py"), "--no-open", str(target)], cwd=str(tmp),
                            env=human_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    try:
        out, err = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise AssertionError("the wizard started with no terminal")
    said = out + err
    assert proc.returncode == 2, (proc.returncode, said)
    assert "UAK SETUP http" not in said and "Launcher file" not in said, "nothing was started: %r" % said
    assert "terminal" in said and "install.sh --wizard" in said, "it says how a person starts it: %r" % said
    # A pipe on stdin (how an agent's tool runs a command) is no terminal either.
    piped = subprocess.run([sys.executable, str(root / ".uak/bin/lib/setup.py"), "--no-open", str(target)], cwd=str(tmp),
                           env=human_env(), input="\n", capture_output=True, text=True, timeout=30)
    assert piped.returncode == 2 and "Launcher file" not in piped.stdout, piped
    # A person's launch: stdin is the terminal, and the output may go to a pipe or a file (`| tee`, `> log`).
    proc = start_wizard(root, tmp, target, human_env())
    try:
        lines = first_lines(proc, 2)
        assert lines and "UAK SETUP" in lines[0], "a terminal on stdin starts it: %r" % lines
    finally:
        stop(proc)


def launcher_is_removed_on_sigterm_and_sighup(root, tmp):
    if os.name == "nt":
        return  # SIGHUP does not exist there; the folder is removed on a normal exit
    import signal
    target, _ = plans.project(root, tmp)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        proc = start_wizard(root, tmp, target, human_env())
        try:
            lines = first_lines(proc, 2)
            folder = Path(re.match(r"Launcher file: (.+)open\.html\s*$", lines[1]).group(1))
            assert folder.is_dir() and (folder / "open.html").is_file(), "the launcher exists while it runs"
            proc.send_signal(sig)
            proc.wait(20)
            assert not folder.exists(), "%s removed the launcher folder" % sig.name
            assert proc.returncode == 0, "it ends cleanly on %s: %r" % (sig.name, proc.returncode)
        finally:
            stop(proc)


def register_is_logged_before_it_acts(root, tmp):
    team_tests.MODULE = wizard.MODULE
    target, remote = team_tests.ready_project(root, tmp)
    team = team_tests.Team()
    with plans.live(target, team) as srv:
        team_tests.ready(srv, target)
        gd = Path(plans.git(target, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        (gd / "uak-direct-main.log").mkdir()  # the log cannot be written
        before = team_tests.claims_head(remote)
        status, body, state = team_tests.register(srv, "ana-r")
        assert status in (200, 202), (status, body)
        assert state.get("phase") == "error" and "uak-direct-main.log" in state.get("error", ""), state
        assert "ana-r is not registered" in state.get("error", ""), state
        assert not [c for c in team.calls if "register-reviewer" in c["argv"]], "the engine did not run: %r" % team.calls
        assert team_tests.claims_head(remote) == before, "nothing was registered"
        assert not (team_tests.record(remote, "roles/reviewers/ana-r.md")), "no reviewer file on claims"


TESTS = [trust_step_is_shown_before_planning, untrusted_planning_run_names_the_cause, planner_survives_a_denied_read]
TESTS += [agent_identity_cannot_start_the_wizard, guard_blocks_an_agent_starting_the_wizard, token_is_not_printed_or_in_argv,
          one_time_code_works_once, idle_session_ends, human_name_is_the_git_identity, human_acts_are_logged,
          guard_reads_what_a_command_mentions, wizard_refuses_without_a_terminal, launcher_is_removed_on_sigterm_and_sighup,
          register_is_logged_before_it_acts]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("trust_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("trust_planning", root / ".uak/bin/lib/planning.py")
    plans.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plans.PLANNING)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-trust-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("SETUP_TRUST_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
