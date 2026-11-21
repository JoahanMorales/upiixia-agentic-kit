#!/usr/bin/env python3
"""Starting the team from the page (UI-006): after Ready, the page registers the reviewer (a human act) and shows one
exact Copy command per agent. Real HTTP, real Git with a local bare remote, the engine's real `register-reviewer` and
`wt new`; `uak start` is answered with a canned READY line so the fixture stays small.
Evidence: the hackathon simulation (notes/handoff:PENDING-IMPROVEMENTS.md #11 and #14 to #16): the person asked which
terminal runs Claude or Codex and needed the worktree cd, the first prompt and the reviewer variables explained.
Contract: notes/handoff:UI-006-contract.md (v2 + the reviewer's 9 amendments)."""
import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import test_setup_planning as tp
import test_setup_wizard as wizard
from test_hack import resolve_binary

MODULE = wizard.MODULE
READY_OUT = ("OK    1. kit installed\nOK    5. plan: 2 task(s), lint clean\n\n"
             "START READY · bash .uak/bin/wt new APP-001   (branch + worktree + claim; then your agent in it)\n")


class Team:
    """The setup server's runner: `uak start` answers READY; register-reviewer runs for real and is recorded with the
    extra environment setup gives it; `slow`/`fake_timeout` change how a registration ends."""

    def __init__(self, ready=READY_OUT):
        self.ready, self.calls, self.gate, self.fake_timeout, self.skip = ready, [], None, False, False
        # UI-009: the auth probes of the coding tools (exit code per tool: 0 signed in), the exit code of the canned
        # `uak start`, every network Git call (gated on demand) and whether it ran beside a live worker.
        self.tools, self.ready_code, self.net, self.srv = {"claude": 0, "codex": 0}, 0, [], None
        self.net_gate, self.net_entered, self.net_code = None, threading.Event(), None
        self.probe_gate, self.probe_entered = None, threading.Event()

    def __call__(self, command, cwd=None, timeout=120, group=False, env=None, **kwargs):
        if len(command) >= 3 and command[-1] == "start" and str(command[-2]).endswith("uak"):
            return subprocess.CompletedProcess(command, self.ready_code, self.ready, "")
        tool = Path(str(command[0])).name.lower().replace(".exe", "").replace(".cmd", "")
        if tool in self.tools and list(command[1:3]) in (["auth", "status"], ["login", "status"]):
            self.probe_entered.set()
            if self.probe_gate:
                self.probe_gate.wait(6)
            return subprocess.CompletedProcess(command, self.tools[tool], "", "")
        if "ls-remote" in command or "fetch" in command:
            srv = self.srv
            worker = srv.worker if srv else None
            self.net.append({"argv": list(command), "timeout": timeout, "group": group,
                             "beside_worker": bool(worker and worker.is_alive() and threading.current_thread() is not worker)})
            if "ls-remote" in command:
                self.net_entered.set()
                if self.net_gate:
                    self.net_gate.wait(6)
                if self.net_code is not None:
                    return subprocess.CompletedProcess(command, self.net_code, "", "The run took too long and was stopped.")
        if "register-reviewer" in command:
            self.calls.append({"argv": list(command), "cwd": cwd, "env": dict(env or {}), "group": group,
                               "timeout": timeout})
            if self.gate:
                self.gate.wait(30)
            if self.skip:
                return subprocess.CompletedProcess(command, 124, "", "The run took too long and was stopped.")
            done = MODULE.run_command(command, cwd=cwd, timeout=timeout, group=group, env=env)
            if self.fake_timeout:
                return subprocess.CompletedProcess(command, 124, done.stdout, done.stderr + "\nThe run took too long and was stopped.")
            return done
        return MODULE.run_command(command, cwd=cwd, timeout=timeout, group=group, env=env)


def ready_project(root, tmp, name="team project"):
    """An installed, pushed sprint project with an approved two-task plan on main (APP-001 is claimable)."""
    target, remote = tp.project(root, tmp, harnesses=("claude", "codex"), name=name)
    (target / ".uak/TASKS.md").write_text(tp.GOOD_PLAN, encoding="utf-8")
    (target / ".uak/OWNERS.md").write_text(tp.OWNERS, encoding="utf-8")
    config = target / ".uak/PROJECT.md"
    config.write_text(config.read_text(encoding="utf-8").replace("Backlog-Approved: no", "Backlog-Approved: yes"),
                      encoding="utf-8")
    tp.git(target, "add", "-A")
    tp.git(target, "commit", "-q", "-m", "plan: approved")
    tp.git(target, "push", "-q", "origin", "main")
    return target, remote


def fresh(tmp, name):
    """A new folder for a second project in the same test (each project has its own origin.git)."""
    path = tmp / name
    path.mkdir()
    return path


def ready(srv, target, name="ana"):
    assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
    if name:
        status, body = tp.post(srv, "/api/human", {"name": name})
        assert status == 200, body
    assert tp.post(srv, "/api/check", {})[0] == 202
    tp.wait_idle(srv)
    state = tp.get(srv, "/api/status")[1]
    assert state["ready"], "the canned gate is READY: %r" % state


def claims_head(remote):
    shown = subprocess.run([resolve_binary("git"), "-C", str(remote), "rev-parse", "-q", "--verify", "refs/heads/claims"],
                           capture_output=True, text=True)
    return shown.stdout.strip()


def record(remote, path):
    shown = subprocess.run([resolve_binary("git"), "-C", str(remote), "show", "claims:" + path],
                           capture_output=True, text=True)
    return shown.stdout if shown.returncode == 0 else ""


def register(srv, confirm="ana-r"):
    status, body = tp.post(srv, "/api/team/reviewer", {"confirm": confirm})
    if status == 202:
        tp.wait_idle(srv)
    return status, body, tp.get(srv, "/api/status")[1]


def engine_registers(target, who, human):
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    env.update(UAK_HUMAN=human, UAK_AGENT="")
    done = subprocess.run([resolve_binary("bash"), ".uak/bin/uak", "register-reviewer", who], cwd=str(target), env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


# --- the four named tests of UI-006 -----------------------------------------------------------------------------------


def reviewer_is_registered_from_the_page(root, tmp):
    target, remote = ready_project(root, tmp)
    team = Team()
    with tp.live(target, team) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert tp.post(srv, "/api/human", {"name": "ana"})[0] == 200
        assert tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})[0] == 400, "not READY yet: refused"
        ready(srv, target)
        for bad in ({}, {"confirm": "ana"}, {"confirm": "bob-r"}, {"confirm": "ana-r "}, {"confirm": ["ana-r"]},
                    {"confirm": "ana-r", "name": "bob"}, {"confirm": "ana-r\n"}):
            status, body = tp.post(srv, "/api/team/reviewer", bad)
            assert status == 400, "refused: %r → %r" % (bad, body)
        assert not team.calls and not claims_head(remote), "a refused request runs nothing and writes nothing"
        status, body, state = register(srv)
        assert status == 202, body
        assert not state.get("error"), state
        assert (state.get("reviewer") or {}).get("registered") is True, "the page says ana-r is registered: %r" % state
    text = record(remote, "roles/reviewers/ana-r.md")
    assert "Reviewer: ana-r" in text and "Registered-By: ana" in text, "the role file is on claims: %r" % text
    assert len(team.calls) == 1
    call = team.calls[0]
    assert call["argv"][-2:] == ["register-reviewer", "ana-r"] and Path(call["argv"][1]).as_posix().endswith("bin/uak"), call["argv"]
    assert Path(call["cwd"]).resolve() == target.resolve(), "it runs in the project's main checkout"

    # No saved name: refused, nothing runs.
    target2, remote2 = ready_project(root, fresh(tmp, "x"), name="no name")
    team2 = Team()
    with tp.live(target2, team2) as srv:
        ready(srv, target2, name=None)
        status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        assert status == 400 and "name" in body.get("error", "").lower(), body
        assert tp.get(srv, "/api/team")[0] == 400, "no commands without the human's name"
    assert not team2.calls and not claims_head(remote2)

    # A linked worktree is never the place a human registers from.
    linked = tmp / "linked tree"
    tp.git(target, "worktree", "add", "-q", "-b", "side", str(linked))
    team3 = Team()
    with tp.live(linked, team3) as srv:
        ready(srv, linked)
        before = claims_head(remote)
        status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        assert status == 400 and "main checkout" in body.get("error", "").lower(), body
        assert not team3.calls and claims_head(remote) == before


def stub_tools(tmp):
    """claude and codex stand-ins that record their argv, folder and identity variables."""
    stubs = tmp / "stub bin"
    stubs.mkdir(exist_ok=True)
    log = tmp / "tools.log"
    for name in ("claude", "codex"):
        script = stubs / name
        script.write_text("#!/usr/bin/env bash\n{ printf '%%s\\n' '--- %s'; printf 'cwd=%%s\\n' \"$(pwd -W 2>/dev/null || pwd -P)\"; "
                          "printf 'UAK_HUMAN=[%%s]\\n' \"${UAK_HUMAN-unset}\"; printf 'UAK_AGENT=[%%s]\\n' \"${UAK_AGENT-unset}\"; "
                          "for a in \"$@\"; do printf 'arg=%%s\\n' \"$a\"; done; } >> '%s'\n" % (name, str(log).replace("'", "'\\''")),
                          encoding="utf-8")
        script.chmod(0o755)
    return stubs, log


def run_line(line, stubs, tmp):
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    env.update(PATH=str(stubs) + os.pathsep + env.get("PATH", ""), UAK_HUMAN="boss", UAK_AGENT="someone-else")
    return subprocess.run([resolve_binary("bash"), "-c", line], cwd=str(tmp), env=env, capture_output=True, text=True,
                          timeout=180)


def agent_launch_commands_are_exact(root, tmp):
    real = tmp / "real root"
    real.mkdir()
    linked = tmp / "link root"
    try:  # macOS temp dirs are symlinks already; this adds one the test controls (Windows may refuse it)
        linked.symlink_to(real, target_is_directory=True)
    except OSError:
        linked = real
    target, _ = ready_project(root, linked, name="team space é")
    team = Team()
    with tp.live(target, team) as srv:
        ready(srv, target)
        status, body = tp.get(srv, "/api/team")
        assert status == 200, body
    physical = Path(os.path.realpath(str(target)))
    assert body.get("task") == "APP-001", body
    commands = {c["id"]: c for c in body.get("commands", [])}
    assert set(commands) == {"implement", "review"}, body
    impl, review = commands["implement"], commands["review"]
    worktree = physical.parent / (physical.name + "-wt") / "app-001"
    q = lambda p: "'" + p.as_posix().replace("'", "'\\''") + "'"
    assert impl["command"] == ("cd %s && UAK_HUMAN= bash .uak/bin/wt new APP-001 --agent claude-ana --human ana && cd %s "
                               "&& UAK_HUMAN= claude '%s'" % (q(physical), q(worktree), MODULE.IMPL_PROMPT % "APP-001")), impl
    assert impl["resume"] == "cd %s && UAK_HUMAN= claude" % q(worktree), impl
    assert review["command"] == ("cd %s && UAK_HUMAN= UAK_AGENT=ana-r codex --sandbox workspace-write --add-dir %s "
                                 "-c sandbox_workspace_write.network_access=true '%s'"
                                 % (q(physical), q(physical / ".git"), MODULE.REVIEW_PROMPT % "ana-r")), review
    for c in (impl, review):
        assert c.get("terminal") and c.get("tool") in ("Claude Code", "Codex"), "each block names its terminal and tool: %r" % c
    for prompt in (MODULE.IMPL_PROMPT % "APP-001", MODULE.REVIEW_PROMPT % "ana-r"):
        assert not re.search(r"[%^&|<>\"`'\n]", prompt), "a prompt is a constant with no shell metacharacters: %r" % prompt
        assert not prompt.startswith("/"), "Git Bash rewrites a leading / into a Windows path: %r" % prompt
    assert MODULE.IMPL_PROMPT.startswith("Run /uak-start for "), MODULE.IMPL_PROMPT
    assert "$uak-review" in MODULE.REVIEW_PROMPT and "uak next" in MODULE.REVIEW_PROMPT, MODULE.REVIEW_PROMPT

    # The lines work as pasted: wt creates exactly the worktree the command enters, and each tool starts where it should.
    stubs, log = stub_tools(tmp)
    done = run_line(impl["command"], stubs, tmp)
    assert done.returncode == 0, done.stdout[-800:] + done.stderr[-800:]
    listed = tp.git(target, "worktree", "list", "--porcelain")
    trees = [l[len("worktree "):] for l in listed.splitlines() if l.startswith("worktree ")]
    assert any(os.path.normcase(os.path.realpath(t)) == os.path.normcase(str(worktree)) for t in trees), "the command's worktree is the one wt created: %s vs %s" % (worktree, trees)
    done = run_line(review["command"], stubs, tmp)
    assert done.returncode == 0, done.stderr[-800:]
    done = run_line(impl["resume"], stubs, tmp)
    assert done.returncode == 0, done.stderr[-800:]
    def same(a, b):
        return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))

    runs = [r.splitlines() for r in log.read_text(encoding="utf-8").split("--- ")[1:]]
    assert len(runs) == 3, runs
    claude, codex, resumed = runs
    assert same(claude[1][len("cwd="):], worktree) and same(codex[1][len("cwd="):], physical) \
        and same(resumed[1][len("cwd="):], worktree), "each tool starts in its folder: %r" % [r[1] for r in runs]
    assert claude[:1] + claude[2:] == ["claude", "UAK_HUMAN=[]", "UAK_AGENT=[someone-else]",
                                       "arg=%s" % (MODULE.IMPL_PROMPT % "APP-001")], claude
    assert codex[:1] + codex[2:] == ["codex", "UAK_HUMAN=[]", "UAK_AGENT=[ana-r]", "arg=--sandbox", "arg=workspace-write",
                                     "arg=--add-dir", "arg=%s" % (physical / ".git").as_posix(), "arg=-c",
                                     "arg=sandbox_workspace_write.network_access=true",
                                     "arg=%s" % (MODULE.REVIEW_PROMPT % "ana-r")], codex
    assert resumed[:1] + resumed[2:] == ["claude", "UAK_HUMAN=[]", "UAK_AGENT=[someone-else]"], resumed
    env_file = (worktree / ".uak-env").read_text(encoding="utf-8")
    assert "UAK_AGENT=claude-ana" in env_file, "the worktree's identity is claude-ana: %r" % env_file

    # Only server values reach a command: a hostile READY line, a short task ID, an unsafe folder name.
    for line in ("START READY · bash .uak/bin/wt new APP-001$(touch x)\n", "START READY · bash .uak/bin/wt new APP-001;id\n",
                 "START READY · bash .uak/bin/wt new APP-7\n", "START READY · cd somewhere and open your agent\n"):
        hostile = Team(ready="OK    1. kit installed\n\n" + line)
        with tp.live(target, hostile) as srv:
            ready(srv, target)
            status, body = tp.get(srv, "/api/team")
        assert status == 200 and not body.get("commands") and body.get("note"), "%r: no command, a note: %r" % (line, body)
    for bad in ("it's mine",) + (() if os.name == "nt" else ("tab\there",)):
        odd, _ = ready_project(root, fresh(tmp, "u%d" % len(bad)), name=bad)
        with tp.live(odd, Team()) as srv:
            ready(srv, odd)
            status, body = tp.get(srv, "/api/team")
        assert status == 200 and not body.get("commands") and "rename" in body.get("note", "").lower(), (bad, body)


def page():
    return (Path(MODULE.__file__).with_name("setup.html")).read_text(encoding="utf-8")


def catalog():
    return (Path(MODULE.__file__).with_name("workspace.js")).read_text(encoding="utf-8")


def advanced_view_shows_the_next_step(root, tmp):
    import test_dashboard_profiles as profiles
    tags = profiles.region(root, "advanced-next")
    assert tags, "the Advanced view has an advanced-next box"
    codes = [a for t, a in tags if t == "code"]
    buttons = [a for t, a in tags if t == "button"]
    assert codes and all("data-no-i18n" in a for a in codes), "the command is shown as literal text: %r" % codes
    assert any(a.get("id") == "copy-advanced-next" for a in buttons), "with its own Copy button: %r" % buttons
    html = page()
    shell = html.index('id="dashboard-shell"')
    assert shell < html.index('id="advanced-next"') < html.index('id="dashboard-frame"'), "above the dashboard frame"
    script = html[html.index("<script nonce=\"__NONCE__\">"):]
    filler = re.search(r"function (\w+)\(guide\) \{[\s\S]{0,600}?el\(\"advanced-next-command\"\)", script)
    assert filler and re.search(r"%s\(\s*data\.guidance" % filler.group(1), script), \
        "the box is filled from the dashboard's guidance, the same one Beginner draws"
    assert "team-step" in script and "/api/team" in script, "the team step is loaded from /api/team"


def tool_roles_are_explained(root, tmp):
    html = page()
    tools = html[html.index("Which coding tools do you use?"):html.index('id="installation-options"')]
    text = " ".join(re.sub(r"<[^>]+>", " ", tools).split())
    for needle in ("One tool implements", "the other reviews", "second identity", "We recommend Claude Code + Codex"):
        assert needle in text, "the tools step explains the roles: %r missing from %r" % (needle, text[:600])
    assert "nobody else reviews" in text.lower() or "no other person" in text.lower(), \
        "'only human' says in plain words what it changes: %r" % text[-400:]
    es = catalog()
    for needle in ("One tool implements", "We recommend Claude Code + Codex", "Start your team", "Register the reviewer"):
        assert needle in es, "%r has a Spanish translation in workspace.js" % needle


# --- the reviewer's and the mentor's additions (contract v2, amendments 1-6) -----------------------------------------


def registration_is_idempotent_and_honest(root, tmp):
    target, remote = ready_project(root, tmp)
    team = Team()
    with tp.live(target, team) as srv:
        ready(srv, target)
        assert register(srv)[0] == 202
        head = claims_head(remote)
        status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        assert status == 200 and body.get("registered") and body.get("registered_by") == "ana", body
        assert "already" in body.get("message", "").lower(), body
        assert len(team.calls) == 1 and claims_head(remote) == head, "a second click runs nothing and commits nothing"
    # Registered earlier by another human: the page says who, and runs nothing.
    target2, remote2 = ready_project(root, fresh(tmp, "b"), name="other human")
    engine_registers(target2, "ana-r", "boss")
    team2 = Team()
    with tp.live(target2, team2) as srv:
        ready(srv, target2)
        head = claims_head(remote2)
        status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        assert status == 200 and body.get("registered_by") == "boss" and "boss" in body.get("message", ""), body
        assert not team2.calls and claims_head(remote2) == head
    # Retired: refused before the engine runs (it would write the role file and it still could not review).
    target3, remote3 = ready_project(root, fresh(tmp, "c"), name="retired one")
    engine_registers(target3, "ana-r", "ana")
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    env.update(UAK_HUMAN="ana", UAK_AGENT="")
    retired = subprocess.run([resolve_binary("bash"), ".uak/bin/uak", "retire", "ana-r"], cwd=str(target3), env=env,
                             capture_output=True, text=True)
    assert retired.returncode == 0 and record(remote3, "meta/retired/ana-r.md"), retired.stdout + retired.stderr
    team3 = Team()
    with tp.live(target3, team3) as srv:
        ready(srv, target3)
        head = claims_head(remote3)
        status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        assert status == 400 and "retired" in body.get("error", "").lower(), body
        assert not team3.calls and claims_head(remote3) == head, "no engine run, the claims ref is unchanged"


def registration_env_is_exact(root, tmp):
    target, _ = ready_project(root, tmp)
    team = Team()
    saved = {k: os.environ.get(k) for k in ("UAK_TASK", "UAK_AGENT", "UAK_HUMAN")}
    os.environ.update(UAK_TASK="X-001", UAK_AGENT="leaked", UAK_HUMAN="leaked")
    try:
        with tp.live(target, team) as srv:
            ready(srv, target)
            assert register(srv)[0] == 202
        extra = team.calls[0]["env"]
        allowed = {"UAK_HUMAN": "ana", "UAK_AGENT": ""}
        for key in ("UAK_REMOTE", "UAK_BASE"):
            if saved.get(key) is None and os.environ.get(key):
                allowed[key] = os.environ[key]
        assert {k: v for k, v in extra.items() if k.startswith("UAK_")} == allowed, extra
        assert team.calls[0]["group"] is True, "the engine and its Git children stop together on a timeout"
        shown = MODULE.run_command([resolve_binary("bash"), "-c", "env"], timeout=30, env={"UAK_HUMAN": "ana", "UAK_AGENT": ""})
        uak = sorted(l for l in shown.stdout.splitlines() if l.startswith("UAK_"))
        assert uak == ["UAK_AGENT=", "UAK_HUMAN=ana"], "the child sees exactly these UAK_ variables: %r" % uak
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def registration_self_grant_is_explained(root, tmp):
    target, remote = ready_project(root, tmp)
    cases = []
    tp.git(target, "config", "uak.agent", "ana-r")
    cases.append(("uak.agent", lambda: tp.git(target, "config", "--unset", "uak.agent")))
    for source, undo in cases:
        team = Team()
        with tp.live(target, team) as srv:
            ready(srv, target)
            status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        where = os.path.normcase(os.path.realpath(str(target / ".git" / "config")))
        assert status == 400 and source in body.get("error", "") and where in os.path.normcase(body.get("error", "")), body
        assert not team.calls and not claims_head(remote)
        undo()
    (target / ".uak-env").write_text("UAK_AGENT=ana-r\n", encoding="utf-8")
    team = Team()
    with tp.live(target, team) as srv:
        ready(srv, target)
        status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
    assert status == 400 and ".uak-env" in body.get("error", ""), body
    assert not team.calls
    (target / ".uak-env").unlink()
    glob = tmp / "global gitconfig"
    glob.write_text("[uak]\n\tagent = ana-r\n", encoding="utf-8")
    saved = os.environ.get("GIT_CONFIG_GLOBAL")
    os.environ["GIT_CONFIG_GLOBAL"] = str(glob)
    try:
        team = Team()
        with tp.live(target, team) as srv:
            ready(srv, target)
            status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        assert status == 400 and os.path.normcase(str(glob)) in os.path.normcase(body.get("error", "")) \
            and "--global" in body.get("error", ""), body
        assert not team.calls and not claims_head(remote)
    finally:
        if saved is None:
            os.environ.pop("GIT_CONFIG_GLOBAL", None)
        else:
            os.environ["GIT_CONFIG_GLOBAL"] = saved


def registration_timeout_reports_remote_truth(root, tmp):
    target, remote = ready_project(root, tmp)
    team = Team()
    team.fake_timeout = True  # the push landed, then the run was stopped
    with tp.live(target, team) as srv:
        ready(srv, target)
        status, _, state = register(srv)
        assert status == 202
        assert (state.get("reviewer") or {}).get("registered") is True and not state.get("error"), state
    assert "Registered-By: ana" in record(remote, "roles/reviewers/ana-r.md")
    target2, remote2 = ready_project(root, fresh(tmp, "t"), name="never pushed")
    team2 = Team()
    team2.skip = True  # stopped before anything reached claims
    with tp.live(target2, team2) as srv:
        ready(srv, target2)
        status, _, state = register(srv)
        assert status == 202
        assert not (state.get("reviewer") or {}).get("registered") and state.get("error"), state
        assert "not registered" in state["error"].lower(), state["error"]
    assert not record(remote2, "roles/reviewers/ana-r.md")


def team_api_keeps_the_protections(root, tmp):
    target, _ = ready_project(root, tmp)
    with tp.live(target, Team()) as srv:
        ready(srv, target)
        status, _, headers = wizard.request(srv, "GET", "/api/team", token=False)
        assert status == 403, "no token, no paths"
        status, _, _ = wizard.request(srv, "GET", "/api/team", extra={"Host": "evil.example:%d" % srv.server_port})
        assert status == 403, "a rebinding Host is refused"
        status, _, headers = wizard.request(srv, "GET", "/api/team")
        assert status == 200 and headers.get("Cache-Control") == "no-store", headers
        status, _, _ = wizard.request(srv, "POST", "/api/team/reviewer", {"confirm": "ana-r"}, origin=False)
        assert status == 403, "a cross-site POST is refused"
        status, _, _ = wizard.request(srv, "POST", "/api/team/reviewer", {"confirm": "ana-r"}, token=False)
        assert status == 403


def concurrent_registration_is_busy(root, tmp):
    target, remote = ready_project(root, tmp)
    team = Team()
    team.gate = threading.Event()
    with tp.live(target, team) as srv:
        ready(srv, target)
        assert "registering" in MODULE.BUSY
        busy = re.search(r"function isBusy\(phase\) \{\s*return (\[[^\]]*\])", page())
        assert busy and '"registering"' in busy.group(1), "the page keeps polling while the reviewer registers: %r" % (busy and busy.group(1))
        first = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        assert first[0] == 202, first
        deadline = time.time() + 10
        while not team.calls and time.time() < deadline:
            time.sleep(0.05)
        second = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
        assert second[0] == 409, "a second registration while one runs is busy: %r" % (second,)
        team.gate.set()
        tp.wait_idle(srv)
    assert len(team.calls) == 1, "one engine run"


def team_step_needs_main_checkout_and_kit_on_main(root, tmp):
    """Review of 98507da (claude-Dylan-r, P3): no command from a linked worktree (wt puts the task worktree next to the
    main checkout, so the second cd would fail) or when main does not have the kit; a symlinked .uak-env is refused
    in plain words."""
    target, remote = ready_project(root, tmp)
    linked = tmp / "linked tree"
    tp.git(target, "worktree", "add", "-q", "-b", "side", str(linked))
    with tp.live(linked, Team()) as srv:
        ready(srv, linked)
        status, body = tp.get(srv, "/api/team")
    assert status == 200 and not body.get("commands") and "main project folder" in body.get("note", "").lower(), body
    bare = fresh(tmp, "nokit")
    empty_remote = bare / "origin.git"
    tp.git(bare, "init", "-q", "--bare", "-b", "main", str(empty_remote))
    tp.git(target, "remote", "set-url", "origin", str(empty_remote))
    try:
        with tp.live(target, Team()) as srv:
            ready(srv, target)
            status, body = tp.get(srv, "/api/team")
        assert status == 200 and not body.get("commands") and "publish the kit" in body.get("note", "").lower(), body
    finally:
        tp.git(target, "remote", "set-url", "origin", str(remote))
    outside = tmp / "elsewhere.env"
    outside.write_text("UAK_AGENT=someone\n", encoding="utf-8")
    try:
        (target / ".uak-env").symlink_to(outside)
    except OSError:  # Windows without the symlink privilege: nothing to refuse there
        return
    team = Team()
    with tp.live(target, team) as srv:
        ready(srv, target)
        status, body = tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"})
    assert status == 400 and ".uak-env" in body.get("error", "") and "link" in body.get("error", "").lower(), body
    assert not team.calls and not claims_head(remote)


# --- UI-009 (absorbs UI-011 and UI-014): the team step, right for every person ----------------------------------------
# Contract: notes/handoff:UI-009-contract.md (Fable mentor pass + the reviewer's 11 binding amendments + amendment 12:
# Codex runs with the network on inside its workspace-write sandbox). Expected commands are written out literally here.

CODEX_FLAGS = "--sandbox workspace-write --add-dir %s -c sandbox_workspace_write.network_access=true"
REVIEW_CODEX = ("You are the reviewer %s. Run bash .uak/bin/uak next; when it names a task to review, run $uak-review with "
                "that task ID. Never write code for a task.")
REVIEW_CLAUDE = ("You are the reviewer %s. Run bash .uak/bin/uak next; when it names a task to review, run /uak-review with "
                 "that task ID. Never write code for a task.")
IMPL_CLAUDE = "Run /uak-start for %s. Work only in this worktree."
IMPL_CODEX = "Run $uak-start for %s. Work only in this worktree."
WAITING_OUT = ("OK    1. kit installed\nOK    5. plan: 2 task(s), lint clean\n"
               "TODO  7. a claimable task: uak next offers none\n"
               "         · Waiting on APP-002: depends on APP-001 (CLAIMED)\n\n"
               "START · 1 thing to do before the first claim. Then run uak start again.\n")
HOSTILE = ("START READY · bash .uak/bin/wt new APP-001$(touch x)\n", "START READY · bash .uak/bin/wt new APP-001;id\n",
           "START READY · bash .uak/bin/wt new APP-7\n", "START READY · cd somewhere and open your agent\n")
DESTRUCTIVE = ("--force", " -f", "reset", "clean", "rm ", "checkout --", "branch -D", "+refs", "push")


def q(path):
    return "'" + Path(str(path)).as_posix().replace("'", "'\\''") + "'"


def physical(path):
    return Path(os.path.realpath(str(path)))


def by_id(view):
    return {c["id"]: c for c in view.get("commands") or []}


def catalog_rows():
    """The Spanish catalog of workspace.js: exact entries and whole-string pattern rows (server notes with values)."""
    text = catalog()
    exact = set()
    for m in re.finditer(r'\[\s*"((?:[^"\\]|\\.)*)",\s*"(?:[^"\\]|\\.)*"\s*\]', text):
        exact.add(json.loads('"%s"' % m.group(1)))
    notes = text[text.index("var NOTES = ["):] if "var NOTES = [" in text else ""
    notes = notes[:notes.index("];")] if notes else ""
    patterns = [json.loads('"%s"' % m.group(1)) for m in re.finditer(r'\[\s*"((?:[^"\\]|\\.)*)",\s*"(?:[^"\\]|\\.)*"\s*\]', notes)]
    return exact, patterns


def translated(text):
    exact, patterns = catalog_rows()
    return text in exact or any(re.fullmatch(p, text) for p in patterns)


def spanish_for(body):
    """Every server text the page shows from this reply (notes, messages, reasons, way-out steps) has Spanish."""
    texts = [body.get("note"), (body.get("registered") or {}).get("message"), (body.get("roles") or {}).get("note"),
             body.get("error")]
    texts += [t.get("reason") for t in body.get("tools") or []]
    texts += [c.get("terminal") for c in body.get("commands") or []]
    way = body.get("way_out") or {}
    texts += list(way.get("steps") or [])
    missing = [t for t in texts if t and not translated(t)]
    assert not missing, "no Spanish entry in workspace.js for: %r" % missing


def retire(target, who, human):
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    env.update(UAK_HUMAN=human, UAK_AGENT="")
    done = subprocess.run([resolve_binary("bash"), ".uak/bin/uak", "retire", who], cwd=str(target), env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def check(srv):
    assert tp.post(srv, "/api/check", {})[0] == 202
    tp.wait_idle(srv)
    return tp.get(srv, "/api/status")[1]


def reviewer_state_follows_project_and_name(root, tmp):
    a, _ = ready_project(root, fresh(tmp, "a"), name="project a")
    b, _ = ready_project(root, fresh(tmp, "b"), name="project b")
    team = Team()
    with tp.live(a, team) as srv:
        team.srv = srv
        ready(srv, a)
        assert register(srv)[0] == 202
        status, view = tp.get(srv, "/api/team")
        assert status == 200 and view["registered"]["registered"] is True, view
        assert tp.get(srv, "/api/status")[1]["reviewer"]["registered"] is True
        ready(srv, b)
        status, view = tp.get(srv, "/api/team")
        assert status == 200 and view["registered"]["registered"] is False, \
            "another project never inherits a registration: %r" % view.get("registered")
        assert not (tp.get(srv, "/api/status")[1].get("reviewer") or {}).get("registered")
        assert not view["registered"].get("message"), view["registered"]
        runs = len(team.calls)
        ready(srv, a)
        view = tp.get(srv, "/api/team")[1]
        assert view["registered"]["registered"] is True and view["registered"]["registered_by"] == "ana", view
        assert len(team.calls) == runs, "read from claims: no engine run"
        assert tp.post(srv, "/api/human", {"name": "bob"})[0] == 200
        view = tp.get(srv, "/api/team")[1]
        assert view["reviewer"] == "bob-r" and view["registered"]["registered"] is False, view
        assert not (tp.get(srv, "/api/status")[1].get("reviewer") or {}).get("registered")
        assert tp.post(srv, "/api/human", {"name": "ana"})[0] == 200
        retire(a, "ana-r", "ana")
        check(srv)
        view = tp.get(srv, "/api/team")[1]
        assert view["registered"]["retired"] is True and view["registered"]["registered"] is False, view
        assert "review" not in by_id(view), "a retired reviewer gets no command: %r" % view["commands"]
        assert "retired" in view["registered"]["message"], view["registered"]
        spanish_for(view)
        assert not (tp.get(srv, "/api/status")[1].get("reviewer") or {}).get("registered")
        assert "reviewer" not in srv.state, "no server-wide reviewer flag"


def codex_command_can_write_git(root, tmp):
    real = tmp / "real root"
    real.mkdir()
    linked = tmp / "link root"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError:
        linked = real
    target, _ = ready_project(root, linked, name="team space é")
    home = physical(target)
    gitdir = home / ".git"
    worktree = home.parent / (home.name + "-wt") / "app-001"
    team = Team()
    with tp.live(target, team) as srv:
        ready(srv, target)
        status, view = tp.get(srv, "/api/team")
        assert status == 200, view
        review = by_id(view).get("review") or {}
        assert review.get("command") == (
            "cd %s && UAK_HUMAN= UAK_AGENT=ana-r codex --sandbox workspace-write --add-dir %s "
            "-c sandbox_workspace_write.network_access=true 'You are the reviewer ana-r. Run bash .uak/bin/uak next; "
            "when it names a task to review, run $uak-review with that task ID. Never write code for a task.'"
            % (q(home), q(gitdir))), review
        status, body = tp.post(srv, "/api/team/roles", {"implement": "codex", "review": "codex"})
        assert status == 200, body
        impl = by_id(tp.get(srv, "/api/team")[1])["implement"]
    assert impl["command"] == ("cd %s && UAK_HUMAN= bash .uak/bin/wt new APP-001 --agent codex-ana --human ana && cd %s && "
                               "UAK_HUMAN= codex --sandbox workspace-write --add-dir %s "
                               "-c sandbox_workspace_write.network_access=true 'Run $uak-start for APP-001. Work only in "
                               "this worktree.'" % (q(home), q(worktree), q(gitdir))), impl["command"]
    stubs, log = stub_tools(tmp)
    for line in (review["command"], impl["command"]):
        done = run_line(line, stubs, tmp)
        assert done.returncode == 0, done.stdout[-800:] + done.stderr[-800:]
    runs = [r.splitlines() for r in log.read_text(encoding="utf-8").split("--- ")[1:]]
    assert len(runs) == 2, runs
    for run, prompt, where in ((runs[0], REVIEW_CODEX % "ana-r", home), (runs[1], IMPL_CODEX % "APP-001", worktree)):
        args = [l[len("arg="):] for l in run if l.startswith("arg=")]
        assert args == ["--sandbox", "workspace-write", "--add-dir", gitdir.as_posix(), "-c",
                        "sandbox_workspace_write.network_access=true", prompt], args
        assert Path(args[3]).is_dir(), "--add-dir names one existing directory: %r" % args[3]
        assert os.path.normcase(os.path.realpath(run[1][len("cwd="):])) == os.path.normcase(str(where)), run[1]
        assert "UAK_HUMAN=[]" in run, run
        assert not [a for a in args[:-1] if a.startswith("-") and a not in ("--sandbox", "--add-dir", "-c")], args
        for bad in tp.BYPASS:
            assert bad not in args, "no approval or sandbox bypass: %r" % args
    assert "UAK_AGENT=[ana-r]" in runs[0], runs[0]
    assert (worktree / ".git").is_file(), "the worktree's .git is a file; Codex gets the main checkout's Git folder"
    assert "UAK_AGENT=codex-ana" in (worktree / ".uak-env").read_text(encoding="utf-8")
    # The Git folder must be quotable too (a separate Git dir with a quote mark): no command at all.
    odd, _ = ready_project(root, fresh(tmp, "sep"), name="sep project")
    moved = tmp / "sep" / "it's git"
    shutil.move(str(odd / ".git"), str(moved))
    (odd / ".git").write_text("gitdir: %s\n" % moved.as_posix(), encoding="utf-8")
    with tp.live(odd, Team()) as srv:
        ready(srv, odd)
        status, view = tp.get(srv, "/api/team")
    assert status == 200 and not view.get("commands") and view.get("note"), view
    spanish_for(view)
    # A Windows path is one quoted word.
    flags = MODULE.codex_flags("C:/Users/Ana Pérez/team/.git")
    assert shlex.split(flags) == ["--sandbox", "workspace-write", "--add-dir", "C:/Users/Ana Pérez/team/.git", "-c",
                                  "sandbox_workspace_write.network_access=true"], flags


def team_step_survives_the_first_claim(root, tmp):
    target, _ = ready_project(root, tmp)
    home = physical(target)
    worktree = home.parent / (home.name + "-wt") / "app-001"
    start = (root / ".uak/bin/start").read_text(encoding="utf-8")
    assert "a claimable task: uak next offers none" in start, "the waiting line is the engine's own"
    team = Team()
    stubs, _ = stub_tools(tmp)
    with tp.live(target, team) as srv:
        ready(srv, target)
        impl = by_id(tp.get(srv, "/api/team")[1])["implement"]
        done = run_line(impl["command"], stubs, tmp)
        assert done.returncode == 0, done.stdout[-800:] + done.stderr[-800:]
        # (a) the same READY line again (round 3: the claimed task was offered a second time)
        check(srv)
        status, view = tp.get(srv, "/api/team")
        assert status == 200, view
        assert view["task"] == "" and "implement" not in by_id(view) and view.get("can_check") is True, \
            "a claimed task is never offered again: %r" % view
        assert "APP-001" in view.get("note", "") and "claimed" in view.get("note", ""), view.get("note")
        rows = {r["task"]: r for r in view.get("claimed") or []}
        assert rows.get("APP-001", {}).get("state") == "CLAIMED" and rows["APP-001"].get("owner") == "claude-ana", rows
        assert rows["APP-001"].get("resume") == "cd %s && UAK_HUMAN= claude" % q(worktree), rows["APP-001"]
        assert "review" in by_id(view), "the reviewer command stays"
        spanish_for(view)
        # (b) the engine's real waiting output: not ready, but the team step stays
        team.ready, team.ready_code = WAITING_OUT, 1
        state = check(srv)
        assert state["ready"] is False and state.get("team") == "waiting", state
        guide = state.get("guidance") or {}
        assert guide.get("kind") == "waiting" and not guide.get("terminal") and not guide.get("commands"), guide
        assert any("Waiting on APP-002" in s for s in guide.get("steps") or []), guide
        status, view = tp.get(srv, "/api/team")
        assert status == 200, "the team step survives the first claim: %r" % view
        assert view.get("phase") == "waiting" and "review" in by_id(view) and "implement" not in by_id(view), view
        assert {r["task"]: r for r in view["claimed"]}["APP-001"].get("resume"), view["claimed"]
        spanish_for(view)
        # (c) another free task: the next free identity of the same tool
        team.ready, team.ready_code = READY_OUT.replace("APP-001", "APP-003"), 0
        check(srv)
        view = tp.get(srv, "/api/team")[1]
        assert "--agent claude-ana-2 " in by_id(view)["implement"]["command"], view["commands"]
        # hostile or unparsable READY lines: no command at all, a note
        for line in HOSTILE:
            team.ready = "OK    1. kit installed\n\n" + line
            check(srv)
            status, view = tp.get(srv, "/api/team")
            assert status == 200 and not view.get("commands") and view.get("note"), (line, view)
    # (d) the page keeps the step after the first claim
    html = page()
    assert re.search(r"function journeyStep\(data\) \{[\s\S]{0,400}data\.team", html), "journeyStep reads team"
    assert re.search(r"async function loadTeam\(\) \{[\s\S]{0,300}state\.team", html), "loadTeam reads team"


def offline_team_step_says_offline(root, tmp):
    target, remote = ready_project(root, tmp)
    team = Team()
    with tp.live(target, team) as srv:
        ready(srv, target)
        assert register(srv)[0] == 202
        tp.git(target, "remote", "set-url", "origin", str(tmp / "gone.git"))
        check(srv)  # a finished check forgets the last read of the remote (an ok read is reused for 15 s)
        status, view = tp.get(srv, "/api/team")
        assert status == 200, view
        assert (view.get("remote") or {}).get("state") == "offline" and view.get("retry") is True, view
        assert not view.get("commands") and view["registered"]["registered"] is None, view
        assert "cannot reach" in view["note"] and "publish" not in view["note"].lower(), view["note"]
        assert (tp.get(srv, "/api/status")[1].get("reviewer") or {}).get("registered") is None, \
            "offline is unknown, never a remembered true"
        spanish_for(view)
        tp.git(target, "remote", "set-url", "origin", str(remote))
        view = tp.get(srv, "/api/team")[1]
        assert view["remote"]["state"] == "ok" and by_id(view).get("implement"), "a failure is not cached: %r" % view
        # A timeout reads as offline, says so, and is not cached either.
        tp.post(srv, "/api/inspect", {"target": str(target)})
        ready(srv, target)
        team.net_code = 124
        view = tp.get(srv, "/api/team")[1]
        assert view["remote"]["state"] == "offline" and "timed out after 30 s" in view["note"], view
        spanish_for(view)
        team.net_code = None
        view = tp.get(srv, "/api/team")[1]
        assert view["remote"]["state"] == "ok" and view.get("commands"), view
        # No remote at all: its own note, Retry, never "publish".
        tp.git(target, "remote", "remove", "origin")
        check(srv)
        try:
            view = tp.get(srv, "/api/team")[1]
            assert view["remote"]["state"] == "none" and view.get("retry") is True and not view.get("commands"), view
            assert "publish" not in view["note"].lower(), view["note"]
            spanish_for(view)
        finally:
            tp.git(target, "remote", "add", "origin", str(remote))
        # A remote or base name that is not a plain name never reaches a refspec (amendment 7): a plain 400.
        for key, bad in (("UAK_BASE", "main..x"), ("UAK_BASE", "x.lock"), ("UAK_REMOTE", "origin/"), ("UAK_BASE", "@{-1}")):
            saved = os.environ.get(key)
            os.environ[key] = bad
            try:
                status, body = tp.get(srv, "/api/team")
                assert status == 400 and "UAK_REMOTE and UAK_BASE" in body.get("error", ""), (bad, body)
                spanish_for(body)
            finally:
                if saved is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = saved
    for net in team.net:
        assert net["timeout"] <= 30 and net["group"] is True, net


def claims_reading_ignores_git_config(root, tmp):
    """Review of 993e112 (claude-Dylan-r, P2): a global grep.lineNumber or grep.column changed `git grep`'s output, so
    the reviewer showed as not registered, the claimed list was empty and claude-ana was offered twice. Also the
    review's P3s: the .uak-env note is never hidden by an earlier note, offline planning never says "publish", and the
    engine's waiting lines read in Spanish."""
    target, remote = ready_project(root, tmp)
    home = physical(target)
    glob = tmp / "global gitconfig"
    glob.write_text("[grep]\n\tlineNumber = true\n\tcolumn = true\n\tfullName = false\n[color]\n\tgrep = always\n",
                    encoding="utf-8")
    saved = os.environ.get("GIT_CONFIG_GLOBAL")
    os.environ["GIT_CONFIG_GLOBAL"] = str(glob)
    try:
        team = Team()
        stubs, _ = stub_tools(tmp)
        with tp.live(target, team) as srv:
            ready(srv, target)
            assert register(srv)[0] == 202
            impl = by_id(tp.get(srv, "/api/team")[1])["implement"]
            done = run_line(impl["command"], stubs, tmp)
            assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
            team.ready = READY_OUT.replace("APP-001", "APP-003")
            check(srv)
            view = tp.get(srv, "/api/team")[1]
            assert view["registered"]["registered"] is True, "registered despite grep.lineNumber: %r" % view["registered"]
            rows = {r["task"]: r for r in view["claimed"]}
            assert rows.get("APP-001", {}).get("owner") == "claude-ana", "the claimed list is read: %r" % view["claimed"]
            assert "--agent claude-ana-2 " in by_id(view)["implement"]["command"], "claude-ana is not offered twice"
            # P3: a claimed task's note and the .uak-env reason are both shown
            team.ready = READY_OUT
            check(srv)
            (target / ".uak-env").write_text("UAK_AGENT=claude-ana\n", encoding="utf-8")
            view = tp.get(srv, "/api/team")[1]
            assert "claimed" in view["note"] and ".uak-env" in view.get("review_note", ""), view
            assert "review" not in by_id(view)
            spanish_for(dict(view, note=view["review_note"]))
            (target / ".uak-env").unlink()
            # P3: offline planning says it cannot reach the remote, never "publish"
            tp.git(target, "remote", "set-url", "origin", str(tmp / "gone.git"))
            check(srv)
            plan = tp.get(srv, "/api/plan")[1]
            assert plan["kit_on_main"] is False and plan["remote_note"].startswith("Could not reach origin"), plan
            assert translated(plan["remote_note"])
            tp.git(target, "remote", "set-url", "origin", str(remote))
    finally:
        if saved is None:
            os.environ.pop("GIT_CONFIG_GLOBAL", None)
        else:
            os.environ["GIT_CONFIG_GLOBAL"] = saved
    # P3: the engine's waiting lines and a probe failure have Spanish
    for line in ("· Waiting on dependencies: 1 task(s); APP-002 waits on APP-001 (CLAIMED).", "· Waiting on APP-002",
                 "· Why not APP-002: depends on APP-001", "Could not run it: [Errno 13] Permission denied"):
        assert translated(line), line
    assert home.is_dir()


TESTS = [reviewer_is_registered_from_the_page, agent_launch_commands_are_exact, advanced_view_shows_the_next_step,
         tool_roles_are_explained, registration_is_idempotent_and_honest, registration_env_is_exact,
         registration_self_grant_is_explained, registration_timeout_reports_remote_truth, team_api_keeps_the_protections,
         concurrent_registration_is_busy, team_step_needs_main_checkout_and_kit_on_main,
         reviewer_state_follows_project_and_name, codex_command_can_write_git, team_step_survives_the_first_claim,
         offline_team_step_says_offline, claims_reading_ignores_git_config]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    global MODULE
    spec = importlib.util.spec_from_file_location("team_setup", root / ".uak/bin/lib/setup.py")
    MODULE = wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MODULE)
    spec = importlib.util.spec_from_file_location("team_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-team-"))
        started = time.monotonic()
        try:
            test(root, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s: %s)" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_TEAM_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
