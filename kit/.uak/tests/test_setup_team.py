#!/usr/bin/env python3
"""Starting the team from the page (UI-006): after Ready, the page registers the reviewer (a human act) and shows one
exact Copy command per agent. Real HTTP, real Git with a local bare remote, the engine's real `register-reviewer` and
`wt new`; `uak start` is answered with a canned READY line so the fixture stays small.
Evidence: the hackathon simulation (notes/handoff:PENDING-IMPROVEMENTS.md #11 and #14 to #16): the person asked which
terminal runs Claude or Codex and needed the worktree cd, the first prompt and the reviewer variables explained.
Contract: notes/handoff:UI-006-contract.md (v2 + the reviewer's 9 amendments)."""
import argparse
import importlib.util
import os
import re
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

    def __call__(self, command, cwd=None, timeout=120, group=False, env=None, **kwargs):
        if len(command) >= 3 and command[-1] == "start" and str(command[-2]).endswith("uak"):
            return subprocess.CompletedProcess(command, 0, self.ready, "")
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
    assert call["argv"][-2:] == ["register-reviewer", "ana-r"] and call["argv"][1].endswith("bin/uak"), call["argv"]
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
    assert review["command"] == "cd %s && UAK_HUMAN= UAK_AGENT=ana-r codex '%s'" % (q(physical), MODULE.REVIEW_PROMPT % "ana-r"), review
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
    assert codex[:1] + codex[2:] == ["codex", "UAK_HUMAN=[]", "UAK_AGENT=[ana-r]",
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
        assert status == 400 and source in body.get("error", "") and str(target / ".git") in body.get("error", ""), body
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
        assert status == 400 and str(glob) in body.get("error", "") and "--global" in body.get("error", ""), body
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


TESTS = [reviewer_is_registered_from_the_page, agent_launch_commands_are_exact, advanced_view_shows_the_next_step,
         tool_roles_are_explained, registration_is_idempotent_and_honest, registration_env_is_exact,
         registration_self_grant_is_explained, registration_timeout_reports_remote_truth, team_api_keeps_the_protections,
         concurrent_registration_is_busy]


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
