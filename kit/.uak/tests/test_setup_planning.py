#!/usr/bin/env python3
"""Planning from the setup UI (UI-004): real HTTP, real Git with a local bare remote, the engine's real `uak lint`,
and a fake planner in place of the coding tool (it writes the plan files, or misbehaves on purpose)."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import test_setup_wizard as wizard
from test_hack import resolve_binary

PLANNING = None
GOOD_PLAN = """# TASKS

## APP-001 · Set up the app

- **Type:** setup
- **Priority:** P0
- **Estimate:** 30 min
- **Depends on:** None
- **Paths:** app/main.py
- **Test-First:** no (scaffold)
- **Verify:** `test -f app/main.py`

## APP-002 · Show the list of <b>items</b>

- **Type:** feature
- **Priority:** P1
- **Estimate:** 45 min
- **Depends on:** APP-001
- **Paths:** app/list.py
- **Tests:** shows_items, hides_empty_list
- **Verify:** `test -f app/list.py`
"""
CYCLE_PLAN = GOOD_PLAN.replace("- **Depends on:** None", "- **Depends on:** APP-002", 1)
OWNERS = "# OWNERS\n"
BYPASS = ("--dangerously-skip-permissions", "bypassPermissions", "--yolo", "--force", "-f",
          "--dangerously-bypass-approvals-and-sandbox", "danger-full-access", "--approve-for-me", "--not-so-yolo",
          "--skip-git-repo-check", "--bare", "--setting-sources")


def git(cwd, *args, check=True):
    result = subprocess.run([resolve_binary("git"), "-C", str(cwd)] + list(args), capture_output=True, text=True)
    if check and result.returncode:
        raise AssertionError("git %s: %s" % (" ".join(args), result.stderr[-400:]))
    return result.stdout.strip()


def project(root, tmp, harnesses=("claude",), name="demo plan"):
    """An installed, pushed sprint project: the package's engine, a bare origin with main, no plan yet."""
    remote = tmp / "origin.git"
    git(tmp, "init", "-q", "--bare", "-b", "main", str(remote))
    target = tmp / name
    target.mkdir()
    git(target, "init", "-q", "-b", "main")
    git(target, "config", "user.name", "Ana Human")
    git(target, "config", "user.email", "ana@example.invalid")
    git(target, "config", "core.hooksPath", str(tmp / "no-hooks"))
    shutil.copytree(str(root / ".uak"), str(target / ".uak"), ignore=shutil.ignore_patterns("tests", "__pycache__"))
    shutil.copy(str(root / "AGENTS.md"), str(target / "AGENTS.md"))
    (target / ".github").mkdir()
    shutil.copy(str(root / ".github/pull_request_template.md"), str(target / ".github/pull_request_template.md"))
    config = (root / ".uak/templates/PROJECT.sprint.md").read_text(encoding="utf-8")
    (target / ".uak/PROJECT.md").write_text(config.replace("Freeze-Epoch: 0", "Freeze-Epoch: 4102444800"), encoding="utf-8")
    (target / ".gitignore").write_text("build/\n", encoding="utf-8")
    for harness in harnesses:
        folder = target / (".claude" if harness == "claude" else ".codex")
        folder.mkdir(exist_ok=True)
        (folder / "README.md").write_text("harness settings\n", encoding="utf-8")
    git(target, "add", "-A")
    git(target, "commit", "-q", "-m", "chore: uak setup")
    git(target, "remote", "add", "origin", str(remote))
    git(target, "push", "-q", "origin", "main")
    return target, remote


class FakePlanner:
    """Stands in for the coding tool: records each command and writes the plan, or misbehaves when told to."""

    def __init__(self, plan=GOOD_PLAN, misbehave=None, gate=None, on_push=None):
        self.plan, self.misbehave, self.gate, self.calls, self.on_push = plan, misbehave, gate, [], on_push

    def __call__(self, command, cwd=None, timeout=120, **kwargs):
        name = Path(command[0]).name.lower().replace(".exe", "").replace(".cmd", "")
        if name not in ("claude", "codex"):
            if self.on_push and "push" in command:
                hook, self.on_push = self.on_push, None
                hook(Path(cwd))  # something else changes the repository between the checks and the push
            return wizard.MODULE.run_command(command, cwd=cwd, timeout=timeout)
        if command[1:3] in (["auth", "status"], ["login", "status"]):
            return subprocess.CompletedProcess(command, 0, "logged in", "")
        self.calls.append({"argv": list(command), "cwd": cwd})
        if self.gate:
            self.gate.wait(30)
        root = Path(cwd)
        (root / ".uak/TASKS.md").write_text(self.plan, encoding="utf-8")
        (root / ".uak/OWNERS.md").write_text(OWNERS, encoding="utf-8")
        if self.misbehave == "approve-and-commit":
            config = root / ".uak/PROJECT.md"
            config.write_text(config.read_text(encoding="utf-8").replace("Backlog-Approved: no", "Backlog-Approved: yes"),
                              encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "plan: approved by the agent")
        if self.misbehave == "edit-other":
            (root / "AGENTS.md").write_text("changed by the planner\n", encoding="utf-8")
        if self.misbehave == "assume-unchanged":
            git(root, "update-index", "--assume-unchanged", "AGENTS.md")
            (root / "AGENTS.md").write_text("hidden from git status by the planner\n", encoding="utf-8")
        if self.misbehave == "edit-flagged":
            (root / "AGENTS.md").write_text("hidden from git status by a flag set before the run\n", encoding="utf-8")
        if self.misbehave == "git-config":
            git(root, "config", "core.hooksPath", ".evil-hooks")
        if self.misbehave == "hook":
            hooks = Path(git(root, "rev-parse", "--absolute-git-dir")) / "hooks"
            hooks.mkdir(exist_ok=True)
            (hooks / "pre-push").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        if self.misbehave == "ignored":
            (root / "build").mkdir(exist_ok=True)
            (root / "build/payload.sh").write_text("echo hidden\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, '{"type":"result","result":"plan written"}\n', "")


def found(name):
    return "/fake/bin/" + name


def live(target, planner):
    server = wizard.LiveServer(str(target), run=planner)
    server.server.planning.find_binary = found
    return server


def post(srv, path, data):
    status, body, _ = wizard.request(srv, "POST", path, data)
    return status, json.loads(body or b"{}")


def get(srv, path):
    status, body, _ = wizard.request(srv, "GET", path)
    return status, json.loads(body or b"{}")


def wait_idle(srv, seconds=120):
    if srv.worker:
        srv.worker.join(seconds)
    assert not (srv.worker and srv.worker.is_alive()), "the background operation finished"


def planned(srv, target, harness="claude"):
    """Inspect the project, save the idea and run the planner to completion; returns GET /api/plan."""
    assert post(srv, "/api/inspect", {"target": str(target)})[0] == 200
    status, body = post(srv, "/api/idea", idea_fields(overwrite=True))
    assert status == 200, "the idea is saved: %r" % body
    status, body = post(srv, "/api/plan", {"harness": harness})
    assert status == 202, "planning starts: %r" % body
    wait_idle(srv)
    status, plan = get(srv, "/api/plan")
    assert status == 200, plan
    return plan


def idea_fields(**extra):
    fields = {"idea": "A queue board for <b>school</b> cafeterias", "audience": "students who wait 20 min",
              "rubric": "Impact 40%, demo 30%, tech 30%", "event_length": "24 hours", "team_size": 3}
    fields.update(extra)
    return fields


def remote_main(remote):
    return git(remote, "rev-parse", "main")


def idea_is_saved_as_plain_text(root, tmp):
    target, _ = project(root, tmp)
    with live(target, FakePlanner()) as srv:
        assert post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        hostile = idea_fields(idea="Line one\n## Injected heading <script>alert(1)</script> `x`",
                              audience="cooks\r\nand waiters")
        status, body = post(srv, "/api/idea", hostile)
        assert status == 200, body
        text = (target / "IDEA.md").read_text(encoding="utf-8")
        assert "\n## Injected heading" not in text, "a one-line field stays on one line"
        assert "Line one ## Injected heading <script>alert(1)</script> `x`" in text, "the idea is kept verbatim"
        assert "cooks and waiters" in text and "Impact 40%, demo 30%, tech 30%" in text
        assert "24 hours" in text and "3" in text
        assert post(srv, "/api/idea", idea_fields(extra="x"))[0] == 400, "unknown fields are refused"
        assert post(srv, "/api/idea", idea_fields(team_size="3; rm -rf /"))[0] == 400, "team size is a number"
        assert post(srv, "/api/idea", idea_fields(goal="a spec goal"))[0] == 400, "a sprint asks for the rubric"
        before = (target / "IDEA.md").read_bytes()
        status, body = post(srv, "/api/idea", idea_fields(idea="Something else"))
        assert status == 409 and (target / "IDEA.md").read_bytes() == before, \
            "an existing IDEA.md is kept until the person confirms the overwrite"
        status, body = post(srv, "/api/idea", idea_fields(idea="Something else", overwrite=True))
        assert status == 200 and "Something else" in (target / "IDEA.md").read_text(encoding="utf-8")


def planner_command_is_fixed_and_literal(root, tmp):
    prompt = PLANNING.PLANNER_PROMPT
    for ch in '%^&|<>"`':
        assert ch not in prompt, "the constant prompt survives a Windows shim: no %r" % ch
    for words in ("Backlog-Approved", "git commit", "git push", "uak plan", ".uak/TASKS.md", ".uak/OWNERS.md",
                  "uak lint", "uak graph"):
        assert words in prompt, "the prompt names %r" % words
    target, _ = project(root, tmp, harnesses=("claude", "codex"))
    claude = PLANNING.planner_command("claude", target, binary="/fake/bin/claude")
    assert claude[:3] == ["/fake/bin/claude", "-p", "/uak-plan " + prompt], "the prompt follows -p, before the rules"
    for rule in ("Bash(git commit *)", "Bash(git push *)", "Bash(git add *)", "Bash(bash .uak/bin/uak plan *)",
                 "mcp__uak"):
        assert rule in claude[claude.index("--disallowedTools"):], "denied: %s" % rule
    for flag, value in (("--permission-mode", "acceptEdits"), ("--permission-prompts", "none"),
                        ("--output-format", "stream-json")):
        assert claude[claude.index(flag) + 1] == value, "%s %s" % (flag, value)
    assert "--strict-mcp-config" in claude, "project MCP servers are not loaded for a planning run"
    assert "--tools" in claude and "WebFetch" not in claude[claude.index("--tools") + 1], "the tool set is explicit"
    assert "--max-turns" not in claude, "no flag the installed CLI does not list (an unknown flag aborts the run)"
    codex = PLANNING.planner_command("codex", target, binary="/fake/bin/codex")
    assert codex == ["/fake/bin/codex", "exec", "--cd", str(target), "--sandbox", "workspace-write", "--json",
                     "$uak-plan " + prompt]
    for argv in (claude, codex):
        assert not set(argv) & set(BYPASS), "no permission-bypass flag: %r" % (set(argv) & set(BYPASS))
    for bad in ("gemini", "cursor", "claude; whoami", "", None):
        try:
            PLANNING.planner_command(bad, target, binary="/fake/bin/x")
        except ValueError:
            continue
        raise AssertionError("only Claude Code and Codex can plan: %r" % (bad,))
    planner = FakePlanner()
    with live(target, planner) as srv:
        assert post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert post(srv, "/api/idea", idea_fields(idea="$(touch pwned) ; rm -rf ~"))[0] == 200
        assert post(srv, "/api/plan", {"harness": "claude", "argv": ["sh"]})[0] == 400, "the browser sends no argv"
        assert post(srv, "/api/plan", {"harness": "gemini"})[0] == 400
        assert post(srv, "/api/plan", {"harness": "codex"})[0] == 202
        wait_idle(srv)
        call = planner.calls[-1]
        # The server resolves the folder physically (macOS temp dirs are links: /var -> /private/var).
        assert call["argv"] == PLANNING.planner_command("codex", target.resolve(), binary="/fake/bin/codex")
        assert Path(call["cwd"]).resolve() == target.resolve()
        assert not any("touch pwned" in arg for arg in call["argv"]), "the idea never reaches the argument list"
    (tmp / "only claude").mkdir()
    only_claude, _ = project(root, tmp / "only claude")
    with live(only_claude, FakePlanner()) as srv:
        assert post(srv, "/api/inspect", {"target": str(only_claude)})[0] == 200
        offered = {p["harness"]: p["available"] for p in get(srv, "/api/plan")[1]["planners"]}
        assert offered.get("claude") is True and offered.get("codex") is False, \
            "only harnesses installed in the project are offered: %r" % offered
        assert post(srv, "/api/plan", {"harness": "codex"})[0] == 400


def planner_never_approves_or_pushes(root, tmp):
    target, remote = project(root, tmp)
    pushed = remote_main(remote)
    for misbehave in ("approve-and-commit", "edit-other", "git-config", "hook", "ignored", "assume-unchanged",
                      "edit-flagged"):
        if misbehave == "edit-flagged":
            git(target, "update-index", "--skip-worktree", "AGENTS.md")  # set before the run (review of dce95aa)
        with live(target, FakePlanner(misbehave=misbehave)) as srv:
            plan = planned(srv, target)
            assert plan["violations"], "the server notices what the planner did (%s): %r" % (misbehave, plan)
            status, body = post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
            assert status in (400, 409), "no approval while the run broke the rules (%s): %r" % (misbehave, body)
        assert remote_main(remote) == pushed, "nothing reaches the remote (%s)" % misbehave
        git(target, "update-index", "--no-assume-unchanged", "--no-skip-worktree", "AGENTS.md")
        git(target, "reset", "-q", "--hard", pushed)
        git(target, "clean", "-qfdx", "-e", "IDEA.md")
        git(target, "config", "core.hooksPath", str(tmp / "no-hooks"))
        for hook in (Path(git(target, "rev-parse", "--absolute-git-dir")) / "hooks").glob("pre-push"):
            hook.unlink()


def duplicate_planning_is_rejected(root, tmp):
    target, _ = project(root, tmp)
    gate = threading.Event()
    planner = FakePlanner(gate=gate)
    with live(target, planner) as srv:
        assert post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert post(srv, "/api/idea", idea_fields())[0] == 200
        try:
            assert post(srv, "/api/plan", {"harness": "claude"})[0] == 202
            assert post(srv, "/api/plan", {"harness": "claude"})[0] == 409, "one planning run at a time"
            assert post(srv, "/api/plan/approve", {"confirm": target.name, "digest": "0" * 64})[0] == 409
            assert post(srv, "/api/check", {})[0] == 409
        finally:
            gate.set()
        wait_idle(srv)
        assert len(planner.calls) == 1, "the planner ran once"


def approval_requires_typed_confirmation(root, tmp):
    target, remote = project(root, tmp)
    pushed = remote_main(remote)
    with live(target, FakePlanner()) as srv:
        plan = planned(srv, target)
        assert not plan["violations"] and plan["lint"]["ok"], plan
        config = (target / ".uak/PROJECT.md").read_bytes()
        for wrong in ({"confirm": "yes", "digest": plan["digest"]},
                      {"confirm": target.name.upper(), "digest": plan["digest"]},
                      {"confirm": target.name, "digest": "0" * 64},
                      {"confirm": target.name},
                      {"confirm": target.name, "digest": plan["digest"], "push": False}):
            status, body = post(srv, "/api/plan/approve", wrong)
            assert status == 400, "refused without the typed name and the reviewed plan: %r -> %r" % (wrong, body)
        assert (target / ".uak/PROJECT.md").read_bytes() == config and remote_main(remote) == pushed
        for name, extra in (("IDEA.md", "\nadded after review\n"), (".uak/TASKS.md", "\n<!-- edited after review -->\n")):
            path = target / name
            original = path.read_text(encoding="utf-8")
            path.write_text(original + extra, encoding="utf-8")
            status, body = post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
            assert status == 400 and remote_main(remote) == pushed, "%s changed after review: a new review" % name
            path.write_text(original, encoding="utf-8")


def approval_commits_only_plan_files(root, tmp):
    target, remote = project(root, tmp)
    (target / "notes.txt").write_text("my own work in progress\n", encoding="utf-8")

    def concurrent_commit(repo):
        (repo / "unreviewed.py").write_text("print('not reviewed')\n", encoding="utf-8")
        git(repo, "add", "unreviewed.py")
        git(repo, "commit", "-q", "-m", "unreviewed work")

    # Review of dce95aa: a commit made between the checks and the push must not be published with the plan.
    with live(target, FakePlanner(on_push=concurrent_commit)) as srv:
        plan = planned(srv, target)
        cards = {c["id"]: c for c in plan["cards"]}
        assert cards["APP-002"]["title"] == "Show the list of <b>items</b>", "plan text comes back verbatim"
        assert cards["APP-001"]["wave"] == 1 and cards["APP-002"]["wave"] == 2
        assert cards["APP-002"]["depends"] == ["APP-001"] and cards["APP-002"]["tests"] == ["shows_items", "hides_empty_list"]
        base = git(target, "rev-parse", "HEAD")
        (target / "local.txt").write_text("not pushed\n", encoding="utf-8")
        git(target, "add", "local.txt")
        git(target, "commit", "-q", "-m", "local work")
        status, body = post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
        assert status == 400 and remote_main(remote) == base, "an approval never pushes other unpushed commits"
        git(target, "reset", "-q", "--mixed", base)
        (target / "local.txt").unlink()
        (target / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(target, "add", "staged.txt")
        status, body = post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
        assert status == 400 and "staged.txt" in body.get("error", ""), "other staged files block the approval"
        git(target, "rm", "-q", "--cached", "staged.txt")
        status, body = post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
        assert status == 202, body
        wait_idle(srv)
        state = get(srv, "/api/status")[1]
        assert not state.get("error"), state
    head = remote_main(remote)
    assert git(target, "rev-parse", "HEAD^") == head, "the verified approval commit is what reached the base branch"
    assert subprocess.run([resolve_binary("git"), "-C", str(remote), "cat-file", "-e", "main:unreviewed.py"],
                          capture_output=True).returncode != 0, "a commit made after the checks is never published"
    changed = sorted(git(target, "diff-tree", "--no-commit-id", "--name-only", "-r", head).splitlines())
    assert changed == [".uak/OWNERS.md", ".uak/PROJECT.md", ".uak/TASKS.md", "IDEA.md"], changed
    message = git(target, "log", "-1", "--format=%B", head)
    assert message.startswith("plan: backlog v1") and "Approved-By: Ana Human" in message, message
    assert "unverified" in message, "the approver is the local Git identity, labelled as such"
    assert git(target, "rev-parse", head + "^") == base, "the approval commit sits on the reviewed base"
    assert git(target, "log", "-1", "--format=%an", head) == "Ana Human", "committed as the local Git identity"
    assert "Backlog-Approved: yes" in git(target, "show", "main:.uak/PROJECT.md")
    status = git(target, "status", "--porcelain")
    assert "notes.txt" in status and "staged.txt" in status, "the person's other files stay untouched"


def approval_refuses_failing_lint(root, tmp):
    target, remote = project(root, tmp)
    pushed = remote_main(remote)
    with live(target, FakePlanner(plan=CYCLE_PLAN)) as srv:
        plan = planned(srv, target)
        assert not plan["lint"]["ok"] and any("CYCLE" in line for line in plan["lint"]["lines"]), plan["lint"]
        status, body = post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
        assert status == 400 and "lint" in body.get("error", "").lower(), body
    assert remote_main(remote) == pushed
    assert "Backlog-Approved: no" in (target / ".uak/PROJECT.md").read_text(encoding="utf-8")
    assert git(target, "status", "--porcelain", "--", ".uak/PROJECT.md") == ""


class NoPlanPlanner(FakePlanner):
    """The coding tool ends cleanly (exit 0) and writes no plan, as in test round r3."""

    def __call__(self, command, cwd=None, timeout=120, **kwargs):
        name = Path(command[0]).name.lower().replace(".exe", "").replace(".cmd", "")
        if name not in ("claude", "codex") or command[1:3] in (["auth", "status"], ["login", "status"]):
            return super().__call__(command, cwd=cwd, timeout=timeout, **kwargs)
        self.calls.append({"argv": list(command), "cwd": cwd})
        return subprocess.CompletedProcess(command, 0, '{"type":"result","result":"done"}\n', "")


class ChattyPlanner(FakePlanner):
    """The coding tool prints a line before it writes the plan (the page shows the last one)."""

    def __call__(self, command, cwd=None, timeout=120, **kwargs):
        name = Path(command[0]).name.lower().replace(".exe", "").replace(".cmd", "")
        if name in ("claude", "codex") and command[1:3] not in (["auth", "status"], ["login", "status"]):
            kwargs["on_line"]('{"type":"assistant","message":{"content":[{"type":"text","text":"Reading IDEA.md now"}]}}')
        return super().__call__(command, cwd=cwd, timeout=timeout, **kwargs)


def catalog_of(root):
    text = (root / ".uak/bin/lib/workspace.js").read_text(encoding="utf-8")
    pairs = re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)
    return {json.loads(a): json.loads(b) for a, b in pairs}


def missing_tasks_file_is_a_failed_plan(root, tmp):
    """Evidence (round r3): a run that wrote no TASKS.md showed a green lint line and an approve button."""
    target, remote = project(root, tmp)
    pushed = remote_main(remote)
    with live(target, NoPlanPlanner()) as srv:
        plan = planned(srv, target)
        state = get(srv, "/api/status")[1]
        assert state.get("phase") == "error", "no plan file is a failed run, not 'planned': %r" % state.get("phase")
        error = state.get("error", "")
        assert "TASKS.md" in error and error in catalog_of(root), "a translated message names the missing plan: %r" % error
        assert plan["planned"] is False and plan.get("failed") is True, "the plan view says it failed: %r" % plan
        assert plan["lint"]["lines"] == [] and not plan["lint"]["ok"], "no lint verdict for a plan that does not exist"
        assert plan["cards"] == [] and plan["tasks"] == "", plan
        assert post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})[0] == 400, \
            "approving a missing plan is refused"
        status, body = post(srv, "/api/plan", {"harness": "claude"})
        assert status == 202, "the retry button runs the planner again: %r" % body
        wait_idle(srv)
    assert remote_main(remote) == pushed
    page = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")
    assert "view.failed" in page, "the page draws a failed plan differently"
    assert re.search(r"plan-approve\"\)\.disabled\s*=\s*blocked[^;]*failed", page), "no approve button for a failed plan"


def planning_shows_progress(root, tmp):
    """Evidence (round r1): planning took 4 to 8 minutes with no cue; the page shows elapsed time and the last line."""
    reader = PLANNING.progress_line
    assert reader('{"type":"assistant","message":{"content":[{"type":"text","text":"Reading IDEA.md now"}]}}') == "Reading IDEA.md now"
    tool = reader('{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"/p/.uak/TASKS.md"}}]}}')
    assert "Write" in tool and "TASKS.md" in tool, tool
    assert reader("plain output line") == "plain output line"
    assert reader('{"type":"system","subtype":"init"}') == "", "lines with nothing to read give no cue"
    assert "ghp_" not in reader("token ghp_" + "a" * 30), "a secret is never shown"
    assert len(reader("x" * 900)) <= 240, "a long line is cut"
    seen = []
    done = wizard.MODULE.run_command([sys.executable, "-c",
                                      "print('first'); print('second', flush=True)"], timeout=30, group=True,
                                     on_line=seen.append)
    assert [x.strip() for x in seen] == ["first", "second"], "run_command reports each output line: %r" % seen
    assert "first" in done.stdout and "second" in done.stdout, "and still returns the whole output"
    target, _ = project(root, tmp)
    gate = threading.Event()
    with live(target, ChattyPlanner(gate=gate)) as srv:
        assert post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert post(srv, "/api/idea", idea_fields(overwrite=True))[0] == 200
        assert post(srv, "/api/plan", {"harness": "claude"})[0] == 202
        progress = {}
        for _ in range(100):
            progress = get(srv, "/api/status")[1].get("plan_progress") or {}
            if progress.get("last"):
                break
            threading.Event().wait(0.1)
        assert progress.get("last") == "Reading IDEA.md now", "the last output line is in the status: %r" % progress
        assert isinstance(progress.get("elapsed"), int) and progress["elapsed"] >= 0, progress
        gate.set()
        wait_idle(srv)
        assert not get(srv, "/api/status")[1].get("plan_progress"), "the cue ends with the run"
    page = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")
    assert "plan_progress" in page and 'id="plan-progress"' in page, "the page shows the progress line"
    es = catalog_of(root)
    assert "Planning for {time}. Last output: {line}" in es, "the progress line has Spanish"


def run_command_stops_a_descendant_holding_the_pipe(root, tmp):
    """Review of 31b9a2d (P2): a tool that exits while a child still holds its output must not leave that child running
    (the same class as the WinError 32 incident); the group is stopped, as on a timeout."""
    code = ("import subprocess, sys\n"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "print(p.pid, flush=True)\n")
    seen = []
    done = wizard.MODULE.run_command([sys.executable, "-c", code], timeout=60, group=True, on_line=seen.append)
    assert done.returncode == 0 and seen, "the tool exited cleanly and its line was read: %r %r" % (done, seen)
    pid = int(seen[0].strip())

    def alive():
        if sys.platform == "win32":
            listing = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid], capture_output=True, text=True).stdout
            return str(pid) in listing
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        return bool(stat) and not stat.startswith("Z")

    for _ in range(50):
        if not alive():
            break
        threading.Event().wait(0.1)
    left = alive()
    if left and sys.platform != "win32":
        os.kill(pid, 9)  # never leave it behind, whatever the verdict
    assert not left, "the descendant holding the pipe was left running after run_command returned"


def one_grace_period_for_both_pipe_readers(root, tmp):
    """UI-015 (Windows QA of UI-010, qa/windows/UI-010-1401.md): a descendant holding stdout AND stderr made run_command
    wait 10 s per reader thread (20 s) before stopping the group; one 10 s grace covers both."""
    import time
    code = ("import subprocess, sys\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "print('started', flush=True)\n")
    start = time.monotonic()
    done = wizard.MODULE.run_command([sys.executable, "-c", code], timeout=60, group=True, on_line=lambda line: None)
    elapsed = time.monotonic() - start
    assert done.returncode == 0, done
    assert elapsed < 15, "one grace period for both readers, not 10 s each: run_command took %.1f s" % elapsed


TESTS = [idea_is_saved_as_plain_text, planner_command_is_fixed_and_literal, planner_never_approves_or_pushes,
         duplicate_planning_is_rejected, approval_requires_typed_confirmation, approval_commits_only_plan_files,
         approval_refuses_failing_lint, missing_tasks_file_is_a_failed_plan, planning_shows_progress,
         run_command_stops_a_descendant_holding_the_pipe, one_grace_period_for_both_pipe_readers]


def main():
    global PLANNING
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("planning_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("planning_module", root / ".uak/bin/lib/planning.py")
    PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(PLANNING)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-planning-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("SETUP_PLANNING_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
