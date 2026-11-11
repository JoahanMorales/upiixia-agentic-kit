#!/usr/bin/env python3
"""The visual setup journey end to end (UI-003): a clean project to an installed, checked dashboard, an interrupted
installation that recovers, and missing prerequisites that stay actionable. Real HTTP and Git, disposable folders,
a local bare remote, no network. Inside an installed project (no install.sh next to the package) the fixture is
installed by copying the package, and only the steps that need the kit's installer are skipped, with a note."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import traceback
from pathlib import Path

import test_setup_wizard as wizard
from test_hack import resolve_binary

START_NEXT = "Start the next task"


def git(cwd, *args):
    result = subprocess.run([resolve_binary("git"), "-C", str(cwd)] + list(args), capture_output=True, text=True)
    if result.returncode:
        raise AssertionError("git %s: %s" % (" ".join(args), result.stderr[-400:]))
    return result.stdout.strip()


def installer_of(root):
    """The kit's real installer, next to the package in the kit's checkout; None inside an installed project."""
    installer = root.parent / "install.sh"
    return installer if installer.is_file() else None


def copy_install(root, target):
    """What a sprint installation leaves behind, copied from the package (as test_setup_planning.project does)."""
    shutil.copytree(str(root / ".uak"), str(target / ".uak"), ignore=shutil.ignore_patterns("tests", "__pycache__"),
                    dirs_exist_ok=True)
    shutil.copy(str(root / "AGENTS.md"), str(target / "AGENTS.md"))
    template = root / ".github/pull_request_template.md"
    if template.is_file():
        (target / ".github").mkdir(exist_ok=True)
        shutil.copy(str(template), str(target / ".github/pull_request_template.md"))
    config = (root / ".uak/templates/PROJECT.sprint.md").read_text(encoding="utf-8")
    (target / ".uak/PROJECT.md").write_text(config, encoding="utf-8")


def tree(path, with_git=False):
    """Every file and folder under path with a digest of its bytes: equal snapshots mean nothing was written."""
    if not path.exists():
        return None
    found = {}
    for folder, dirs, files in os.walk(str(path)):
        if not with_git and ".git" in dirs:
            dirs.remove(".git")
        rel = Path(folder).relative_to(path).as_posix()
        found[rel + "/"] = ""
        for name in files:
            found[rel + "/" + name] = hashlib.sha256((Path(folder) / name).read_bytes()).hexdigest()
    return found


def call(srv, method, path, data=None):
    status, body, headers = wizard.request(srv, method, path, data)
    return status, json.loads(body or b"{}"), headers


def post(srv, path, data):
    return call(srv, "POST", path, data)


def status_of(srv):
    status, state, _ = call(srv, "GET", "/api/status")
    assert status == 200, "status answers: %r" % state
    return state


def wait(srv, seconds=120):
    if srv.worker:
        srv.worker.join(seconds)
    assert not (srv.worker and srv.worker.is_alive()), "the background operation finished"


def actionable(answer, *words):
    """A 4xx JSON error the page can show: a sentence that says what to do, never a traceback."""
    status, body, headers = answer
    assert 400 <= status < 500, "a missing prerequisite is a client error, not %d: %r" % (status, body)
    assert headers.get("Content-Type", "").startswith("application/json"), "the page reads a JSON error"
    error = body.get("error")
    assert isinstance(error, str) and len(error) > 15, "the error is a sentence the page can show: %r" % body
    assert "Traceback" not in error and "Error:" not in error, "no internals reach the page: %r" % error
    for word in words:
        assert word.lower() in error.lower(), "the error says %r: %r" % (word, error)
    return error


def ready_to_check(srv, target):
    """Readiness through the server: `uak start` runs, blockers come back as steps, never as Start the next task."""
    assert post(srv, "/api/check", {})[0] == 202, "the readiness check starts"
    wait(srv)
    state = status_of(srv)
    assert not state.get("error"), "the readiness check completed: %r" % state.get("details", "")[-600:]
    assert state["phase"] == "setup" and state["installed"] and not state["ready"], "blockers are not Ready: %r" % state
    todo = [c for c in state["checks"] if c["state"] == "todo"]
    assert todo, "uak start lists what is missing: %r" % state["checks"]
    guidance = state["guidance"]
    assert guidance["kind"] == "todo" and guidance["title"] != START_NEXT, "the next step is a blocker: %r" % guidance
    assert guidance["title"] in todo[0]["text"] and not guidance["commands"], "the first blocker, shown as text"
    status, dashboard, _ = call(srv, "GET", "/api/dashboard")
    assert status == 200, "the dashboard answers: %r" % dashboard
    assert dashboard["guidance"]["title"] == guidance["title"], "the dashboard and setup give the same next step"
    assert dashboard["guidance"]["kind"] == "todo"
    return state


def new_project_visual_setup_journey(root, tmp):
    installer = installer_of(root)
    target = wizard.repository(tmp / "new project")
    before = tree(target, with_git=True)
    with wizard.LiveServer(str(target)) as srv:
        status, html, _ = wizard.request(srv, "GET", "/", token=False, origin=False)
        assert status == 200 and b"<html" in html, "the welcome page renders"
        state = status_of(srv)
        assert state["phase"] == "welcome" and not state["installed"] and not state["ready"]
        assert tree(target, with_git=True) == before, "opening setup writes nothing to the project"
        status, state, _ = post(srv, "/api/inspect", {"target": str(target)})
        assert status == 200 and Path(state["target"]).resolve() == target.resolve(), state
        assert state["phase"] == "options" and not state["installed"] and not state["can_repair"], \
            "a project without the kit is offered a fresh installation: %r" % state
        assert tree(target, with_git=True) == before, "inspecting writes nothing to the project"
        assert status_of(srv)["guidance"]["kind"] == "install", "the next step is installing the kit"
        if installer:
            status, body, _ = post(srv, "/api/install", {"mode": "sprint", "harness": ["claude"]})
            assert status == 202 and body["phase"] == "installing", body
            wait(srv)
            state = status_of(srv)
            if state["phase"] != "installed":
                print("INSTALL_DETAILS " + state.get("details", "")[-2000:])
            assert state["phase"] == "installed" and state["installed"], "the installation completes"
            assert (target / ".claude").is_dir() and (target / ".uak/bin/uak").is_file()
            assert state["settings"].get("Mode") == "sprint", state["settings"]
            note = ""
        else:
            copy_install(root, target)
            assert post(srv, "/api/inspect", {"target": str(target)})[0] == 200
            state = status_of(srv)
            assert state["phase"] == "setup" and state["installed"], state
            note = "no install.sh next to the package: the installation was copied, /api/install not exercised"
        assert not state["ready"], "Installed is not Ready"
        assert state["guidance"]["kind"] != "ready" and state["guidance"]["title"] != START_NEXT, state["guidance"]
        first = ready_to_check(srv, target)
        assert any("origin" in c["text"] for c in first["checks"] if c["state"] == "todo"), \
            "without a remote, the remote is a blocker: %r" % first["checks"]
        # Later, the project has a remote: setup sees the existing installation and offers repair, not a fresh install.
        remote = tmp / "origin.git"
        git(tmp, "init", "-q", "--bare", str(remote))
        git(target, "remote", "add", "origin", str(remote))
        status, state, _ = post(srv, "/api/inspect", {"target": str(target)})
        assert status == 200 and state["can_repair"] and state["installed"] and state["phase"] == "setup", \
            "an existing installation is offered repair: %r" % state
        installed = tree(target)
        # Without the kit's installer, setup names where to run it before anything else.
        actionable(post(srv, "/api/install", {"mode": "sprint", "harness": ["claude"]}),
                   "Repair" if installer else "install.sh --wizard")
        assert srv.worker is None or not srv.worker.is_alive()
        assert tree(target) == installed, "a refused fresh install writes nothing"
        state = ready_to_check(srv, target)
        blocker = first["guidance"]["title"]
        assert state["guidance"]["title"] != blocker and any(c["state"] == "ok" and "origin" in c["text"]
                                                             for c in state["checks"]), \
            "the local remote now counts, so the next blocker moves on: %r" % state["checks"]
    return note


class Installer:
    """Stands in for install.sh: each call plays the next scripted outcome; other commands run for real."""

    def __init__(self, path, outcomes):
        self.path, self.outcomes, self.calls = str(Path(path).resolve()), list(outcomes), []

    def __call__(self, command, **kwargs):
        if self.path not in command:
            return wizard.MODULE.run_command(command, **kwargs)
        self.calls.append(list(command))
        return self.outcomes.pop(0)(command, Path(kwargs["cwd"]))


def interrupted_install_can_recover(root, tmp):
    target = wizard.repository(tmp / "interrupted project")
    fake = tmp / "kit checkout" / "install.sh"
    fake.parent.mkdir()
    fake.write_text("", encoding="utf-8")

    def fails_halfway(command, cwd):
        (cwd / ".uak/bin").mkdir(parents=True)  # the copy stopped after the first folder
        return subprocess.CompletedProcess(command, 1, "  + .uak/bin\n", "cp: write error: No space left on device\n")

    def interrupted(command, cwd):
        raise subprocess.TimeoutExpired(command, 120)

    def completes(command, cwd):
        copy_install(root, cwd)
        return subprocess.CompletedProcess(command, 0, "Installed.\n", "")

    runner = Installer(fake, [fails_halfway, interrupted, completes])
    options = {"mode": "sprint", "harness": ["claude"]}
    with wizard.LiveServer(str(target), run=runner, installer=fake) as srv:
        assert post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert post(srv, "/api/install", options)[0] == 202
        wait(srv)
        state = status_of(srv)
        assert state["phase"] == "error" and not state["installed"] and not state["ready"], state
        assert "retry" in state["error"].lower() and "No space left" in state["details"], \
            "the error says what to do and the details say why: %r" % state
        assert state["guidance"]["kind"] == "error" and state["guidance"]["detail"] == state["error"]
        actionable(post(srv, "/api/check", {}), "Install the kit")
        status, state, _ = post(srv, "/api/inspect", {"target": str(target)})
        assert status == 200 and state["phase"] == "error" and not state["installed"] and state["can_repair"], \
            "inspecting again keeps the failure and offers repair: %r" % state
        actionable(post(srv, "/api/install", options), "Repair")
        assert post(srv, "/api/repair", options)[0] == 202
        wait(srv)
        state = status_of(srv)
        assert state["phase"] == "error" and not state["installed"] and "stopped" in state["error"], \
            "an interrupted repair is an error, never installed: %r" % state
        assert post(srv, "/api/repair", options)[0] == 202
        wait(srv)
        state = status_of(srv)
        assert state["phase"] == "installed" and state["installed"] and not state["ready"] and not state["error"], state
        assert len(runner.calls) == 3 and all("--update" in c for c in runner.calls[1:]), "repair runs --update"
        assert "--update" not in runner.calls[0]
        ready_to_check(srv, target)
    installer = installer_of(root)
    if not installer:
        return "no install.sh next to the package: the real blocked-folder failure was not exercised"
    # The real installer meets a file where the kit needs a folder: an actionable error, the user's file untouched.
    target = wizard.repository(tmp / "blocked project")
    (target / ".claude").write_text("Keep this user file", encoding="utf-8")
    with wizard.LiveServer(str(target)) as srv:
        assert post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert post(srv, "/api/install", options)[0] == 202
        wait(srv)
        state = status_of(srv)
        assert state["phase"] == "error" and not state["installed"] and not state["ready"], state
        assert ".claude" in state["error"] and "Repair" in state["error"], "the error names the blocking file"
        # The engine files were copied before the failure, yet the unfinished install is never taken as installed
        # (UAK-010: install.sh leaves .uak/INSTALLING until its last step succeeds).
        assert (target / ".uak/VERSION").is_file() and not wizard.MODULE.kit_present(target), \
            "the engine files were copied before the failure, and the unfinished install is not installed"
        status, state, _ = post(srv, "/api/inspect", {"target": str(target)})
        assert status == 200 and not state["installed"] and state["can_repair"] and state["phase"] == "error", \
            "files on disk never make a failed installation look installed: %r" % state
        actionable(post(srv, "/api/check", {}), "Repair or update")  # how to finish the unfinished install (UAK-010)
        actionable(post(srv, "/api/repair", dict(options, mode="marathon")), "sprint")
        assert post(srv, "/api/repair", options)[0] == 202
        wait(srv)
        state = status_of(srv)
        assert state["phase"] == "error" and not state["installed"], "repair fails again while the cause remains"
        (target / ".claude").rename(target / ".claude.saved")
        assert post(srv, "/api/repair", options)[0] == 202
        wait(srv)
        state = status_of(srv)
        if state["phase"] != "installed":
            print("REPAIR_DETAILS " + state.get("details", "")[-2000:])
        assert state["phase"] == "installed" and state["installed"] and not state["ready"], state
        assert (target / ".claude").is_dir()
        assert (target / ".claude.saved").read_text(encoding="utf-8") == "Keep this user file"
        ready_to_check(srv, target)
    return ""


def missing_prerequisites_remain_actionable(root, tmp):
    plain = tmp / "plain folder"
    plain.mkdir()
    repo = wizard.repository(tmp / "repository")
    (repo / "sub").mkdir()
    missing = tmp / "does not exist"
    with wizard.LiveServer() as srv:
        actionable(call(srv, "GET", "/api/dashboard"), "project")
        actionable(call(srv, "GET", "/api/plan"), "project")
        actionable(post(srv, "/api/check", {}), "Install the kit")
        actionable(post(srv, "/api/install", {"mode": "sprint", "harness": ["claude"]}))
        actionable(post(srv, "/api/inspect", {"target": ""}), "full path")
        actionable(post(srv, "/api/inspect", {"target": str(missing)}), "does not exist")
        assert not missing.exists(), "a missing folder is never created"
        for folder in (plain, repo / "sub"):
            before = tree(folder)
            actionable(post(srv, "/api/inspect", {"target": str(folder)}), "root of a Git repository")
            assert tree(folder) == before
        state = status_of(srv)
        assert state["phase"] == "welcome" and not state["installed"], "a refused folder is never selected: %r" % state
        assert srv.worker is None, "nothing started"
    # A Git repository without the kit: readiness and planning need the installation first.
    with wizard.LiveServer(str(repo)) as srv:
        before = tree(repo)
        assert post(srv, "/api/inspect", {"target": str(repo)})[0] == 200
        actionable(post(srv, "/api/check", {}), "Install the kit")
        actionable(post(srv, "/api/idea", {"idea": "A board", "audience": "students", "rubric": "demo",
                                           "event_length": "24 hours", "team_size": 3}), "Install the kit")
        actionable(post(srv, "/api/plan", {"harness": "claude"}), "Install the kit")
        assert srv.worker is None and tree(repo) == before, "nothing ran and nothing was written"
    # An installed kit of another version: this setup's engine does not certify it.
    older = wizard.repository(tmp / "older project")
    copy_install(root, older)
    (older / ".uak/VERSION").write_text("0.0.1\n", encoding="utf-8")
    with wizard.LiveServer(str(older)) as srv:
        before = tree(older)
        status, state, _ = post(srv, "/api/inspect", {"target": str(older)})
        assert status == 200 and state["can_repair"], state
        actionable(post(srv, "/api/check", {}), "version", "Repair")
        actionable(post(srv, "/api/plan", {"harness": "claude"}), "version")
        assert srv.worker is None and tree(older) == before, "nothing ran and nothing was written"
    # An installed kit without IDEA.md: planning asks for the idea first.
    current = wizard.repository(tmp / "current project")
    copy_install(root, current)
    with wizard.LiveServer(str(current)) as srv:
        before = tree(current)
        assert post(srv, "/api/inspect", {"target": str(current)})[0] == 200
        actionable(post(srv, "/api/plan", {"harness": "claude"}), "Describe what you are building")
        actionable(post(srv, "/api/plan/approve", {"confirm": current.name, "digest": "0" * 64}), "Create the plan")
        status, plan, _ = call(srv, "GET", "/api/plan")
        assert status == 200 and not plan["idea"] and not plan["planned"], plan
        assert srv.worker is None and tree(current) == before, "nothing ran and nothing was written"
        assert not (current / "IDEA.md").exists()
    return ""


TESTS = [new_project_visual_setup_journey, interrupted_install_can_recover, missing_prerequisites_remain_actionable]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("uak_journey_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-journey-") as folder:
            try:
                note = test(root, Path(folder))
                print("PASS " + test.__name__ + (" (%s)" % note if note else ""))
            except Exception as exc:
                failed += 1
                frame = traceback.extract_tb(exc.__traceback__)[-1]
                print("FAIL %s: %s: %s (line %s: %s)" % (test.__name__, type(exc).__name__, exc, frame.lineno, frame.line))
    print("DASHBOARD_JOURNEY_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
