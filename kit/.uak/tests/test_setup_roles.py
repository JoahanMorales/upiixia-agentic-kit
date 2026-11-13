#!/usr/bin/env python3
"""Who implements and who reviews (UI-009, absorbs UI-014): each person picks a role for each coding tool that is
installed in the project and signed in on this computer; one tool can do both jobs under two identities. Real HTTP,
real Git with a local bare remote, the engine's real `wt new`; the tools are stubs that record their arguments.
Evidence: Dylan, after the test rounds of 2026-11-13: many people have only Claude or only Codex, and the team step
always said "Claude Code implements, Codex reviews". Contract: notes/handoff:UI-009-contract.md."""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import test_setup_planning as tp
import test_setup_team as team
import test_setup_wizard as wizard

READY_OUT = team.READY_OUT


def timed(call, method, path, *args):
    """A request that names itself and its time when it fails (the Windows CI once timed out without saying where)."""
    started = time.monotonic()
    try:
        return call(*args)
    except Exception as exc:
        raise AssertionError("%s %s failed after %.1f s: %s: %s" % (method, path, time.monotonic() - started,
                                                                      type(exc).__name__, exc))


def get(srv, path):
    return timed(lambda: tp.get(srv, path), "GET", path)


def post(srv, path, data):
    return timed(lambda: tp.post(srv, path, data), "POST", path)


def roles_project(root, tmp, harnesses, name="roles project"):
    """team.ready_project with the coding tools this test chooses (an installed folder per tool)."""
    target, remote = tp.project(root, tmp, harnesses=harnesses, name=name)
    (target / ".uak/TASKS.md").write_text(tp.GOOD_PLAN, encoding="utf-8")
    (target / ".uak/OWNERS.md").write_text(tp.OWNERS, encoding="utf-8")
    config = target / ".uak/PROJECT.md"
    config.write_text(config.read_text(encoding="utf-8").replace("Backlog-Approved: no", "Backlog-Approved: yes"),
                      encoding="utf-8")
    tp.git(target, "add", "-A")
    tp.git(target, "commit", "-q", "-m", "plan: approved")
    tp.git(target, "push", "-q", "origin", "main")
    return target, remote


def expected(role, tool, home, worktree=None, task="APP-001", agent="claude-ana", who="ana-r"):
    """The commands, written out literally (amendment 11a)."""
    q, gitdir = team.q, home / ".git"
    flags = "--sandbox workspace-write --add-dir %s -c sandbox_workspace_write.network_access=true" % q(gitdir)
    if role == "implement":
        start = "cd %s && UAK_HUMAN= bash .uak/bin/wt new %s --agent %s --human ana && cd %s && " % (
            q(home), task, agent, q(worktree))
        if tool == "claude":
            return start + "UAK_HUMAN= claude 'Run /uak-start for %s. Work only in this worktree.'" % task
        return start + "UAK_HUMAN= codex %s 'Run $uak-start for %s. Work only in this worktree.'" % (flags, task)
    if tool == "claude":
        return ("cd %s && UAK_HUMAN= UAK_AGENT=%s claude 'You are the reviewer %s. Run bash .uak/bin/uak next; when it "
                "names a task to review, run /uak-review with that task ID. Never write code for a task.'" % (q(home), who, who))
    return ("cd %s && UAK_HUMAN= UAK_AGENT=%s codex %s 'You are the reviewer %s. Run bash .uak/bin/uak next; when it "
            "names a task to review, run $uak-review with that task ID. Never write code for a task.'" % (q(home), who, flags, who))


def roles_file(target):
    return Path(os.path.realpath(str(target))) / ".git" / "uak-setup" / "roles.json"


def roles_follow_the_tools_you_have(root, tmp):
    target, remote = roles_project(root, tmp, ("claude", "codex"))
    home = team.physical(target)
    worktree = home.parent / (home.name + "-wt") / "app-001"
    with tp.live(target, team.Team()) as srv:
        team.ready(srv, target)
        status, view = get(srv, "/api/team")
        assert status == 200, view
        tools = {t["id"]: t for t in view.get("tools") or []}
        assert set(tools) == {"claude", "codex"} and all(t["available"] for t in tools.values()), view.get("tools")
        assert tools["claude"]["role"] == "implement" and tools["codex"]["role"] == "review", tools
        assert view["roles"]["implement"] == "claude" and view["roles"]["review"] == "codex", view["roles"]
        assert view["roles"]["saved"] is False and view["roles"]["same_tool"] is False, view["roles"]
        before = tp.git(target, "status", "--porcelain")
        status, body = post(srv, "/api/team/roles", {"implement": "codex", "review": "claude"})
        assert status == 200 and body["roles"]["implement"] == "codex" and body["roles"]["saved"] is True, body
        view = get(srv, "/api/team")[1]
        commands = team.by_id(view)
        assert commands["implement"]["command"] == expected("implement", "codex", home, worktree, agent="codex-ana"), commands
        assert commands["review"]["command"] == expected("review", "claude", home), commands
        assert commands["implement"]["tool"] == "Codex" and commands["review"]["tool"] == "Claude Code", commands
        written = roles_file(target).read_bytes()
        for bad in ({"implement": "codex", "review": "claude", "x": 1}, {"implement": "gemini", "review": "claude"},
                    ["codex", "claude"], {"implement": "codex"}, {"implement": 1, "review": "claude"}):
            status, body = post(srv, "/api/team/roles", bad)
            assert status == 400, (bad, body)
            assert roles_file(target).read_bytes() == written, "a refused pick writes nothing: %r" % (bad,)
        # Another person on the same clone starts from the defaults and keeps her pick apart.
        assert post(srv, "/api/human", {"name": "bob"})[0] == 200
        bob = get(srv, "/api/team")[1]["roles"]
        assert (bob["implement"], bob["review"], bob["saved"]) == ("claude", "codex", False), bob
        assert post(srv, "/api/team/roles", {"implement": "claude", "review": "claude"})[0] == 200
        assert post(srv, "/api/human", {"name": "ana"})[0] == 200
        ana = get(srv, "/api/team")[1]["roles"]
        assert (ana["implement"], ana["review"]) == ("codex", "claude"), "her pick survives bob's: %r" % ana
        assert tp.git(target, "status", "--porcelain") == before, "the choice never shows in git status"
    saved = json.loads(roles_file(target).read_text(encoding="utf-8"))
    assert set(saved["people"]) == {"ana", "bob"}, saved
    # Remembered for the project: a new server on the same folder.
    with tp.live(target, team.Team()) as srv:
        team.ready(srv, target)
        roles = get(srv, "/api/team")[1]["roles"]
        assert (roles["implement"], roles["review"], roles["saved"]) == ("codex", "claude", True), roles
        # wt new and a second worktree never change or show it
        stubs, _ = team.stub_tools(tmp)
        line = team.by_id(get(srv, "/api/team")[1])["implement"]["command"]
        done = team.run_line(line, stubs, tmp)
        assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
    tp.git(target, "worktree", "add", "-q", "-b", "side", str(tmp / "second tree"))
    assert json.loads(roles_file(target).read_text(encoding="utf-8")) == saved
    assert "uak-setup" not in tp.git(target, "ls-files") and "uak-setup" not in tp.git(target, "status", "--porcelain")
    assert "uak-setup" not in tp.git(tmp / "second tree", "status", "--porcelain")
    # Not shared: a teammate's fresh clone has the defaults.
    clone = tmp / "teammate"
    tp.git(tmp, "clone", "-q", str(remote), str(clone))
    tp.git(clone, "config", "user.name", "Bob")
    tp.git(clone, "config", "user.email", "bob@example.invalid")
    with tp.live(clone, team.Team()) as srv:
        team.ready(srv, clone)
        roles = get(srv, "/api/team")[1]["roles"]
        assert (roles["implement"], roles["review"], roles["saved"]) == ("claude", "codex", False), roles
    # An unreadable file is replaced only when it is a regular file in a real folder; a link is refused.
    roles_file(target).write_text("{not json", encoding="utf-8")
    with tp.live(target, team.Team()) as srv:
        team.ready(srv, target)
        assert get(srv, "/api/team")[1]["roles"]["saved"] is False
        assert post(srv, "/api/team/roles", {"implement": "claude", "review": "codex"})[0] == 200
        assert json.loads(roles_file(target).read_text(encoding="utf-8"))["people"]["ana"]["review"] == "codex"
        outside = tmp / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        roles_file(target).unlink()
        try:
            roles_file(target).symlink_to(outside)
        except OSError:
            return
        status, body = post(srv, "/api/team/roles", {"implement": "claude", "review": "claude"})
        assert status == 400 and outside.read_text(encoding="utf-8") == "{}", body


def one_tool_does_both_roles(root, tmp):
    for tool, label in (("claude", "Claude Code"), ("codex", "Codex")):
        folder = tmp / tool
        folder.mkdir()
        target, _ = roles_project(root, folder, (tool,), name="%s only" % tool)
        home = team.physical(target)
        worktree = home.parent / (home.name + "-wt") / "app-001"
        with tp.live(target, team.Team()) as srv:
            team.ready(srv, target)
            view = get(srv, "/api/team")[1]
        roles = view.get("roles") or {}
        assert (roles.get("implement"), roles.get("review"), roles.get("same_tool")) == (tool, tool, True), roles
        assert [t["id"] for t in view["tools"] if t["available"]] == [tool], view["tools"]
        assert {t["id"]: t["role"] for t in view["tools"]}[tool] == "both", view["tools"]
        commands = team.by_id(view)
        assert commands["implement"]["command"] == expected("implement", tool, home, worktree, agent=tool + "-ana")
        assert commands["review"]["command"] == expected("review", tool, home)
        assert commands["implement"]["tool"] == commands["review"]["tool"] == label
        stubs, log = team.stub_tools(folder)
        for line in (commands["implement"]["command"], commands["review"]["command"]):
            done = team.run_line(line, stubs, folder)
            assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
        runs = [r.splitlines() for r in log.read_text(encoding="utf-8").split("--- ")[1:]]
        assert [r[0] for r in runs] == [tool, tool], runs
        assert "UAK_AGENT=%s-ana" % tool in (worktree / ".uak-env").read_text(encoding="utf-8")
        prompt = team.REVIEW_CLAUDE if tool == "claude" else team.REVIEW_CODEX
        assert "UAK_AGENT=[ana-r]" in runs[1] and runs[1][-1] == "arg=" + prompt % "ana-r", runs[1]
        team.spanish_for(view)
    html = team.page()
    sentence = "The reviewer never reviews its own identity's work."
    assert sentence in html and team.translated(sentence), "the page says it, in both languages"
    assert team.translated("{tool} does both jobs under two names: {impl} writes the code and {who} reviews it in a "
                           "separate session.")


def any_tool_can_review(root, tmp):
    target, _ = roles_project(root, tmp, ("claude", "codex"))
    home = team.physical(target)
    worktree = home.parent / (home.name + "-wt") / "app-001"
    stubs, log = team.stub_tools(tmp)
    with tp.live(target, team.Team()) as srv:
        team.ready(srv, target)
        for impl, rev in (("claude", "codex"), ("codex", "claude"), ("claude", "claude"), ("codex", "codex")):
            assert post(srv, "/api/team/roles", {"implement": impl, "review": rev})[0] == 200
            commands = team.by_id(get(srv, "/api/team")[1])
            assert commands["implement"]["command"] == expected("implement", impl, home, worktree, agent=impl + "-ana"), commands
            assert commands["review"]["command"] == expected("review", rev, home), commands
            log.write_text("", encoding="utf-8")
            done = team.run_line(commands["review"]["command"], stubs, tmp)
            assert done.returncode == 0, done.stderr[-600:]
            run = log.read_text(encoding="utf-8").split("--- ")[1].splitlines()
            args = [l[len("arg="):] for l in run if l.startswith("arg=")]
            prompt = (team.REVIEW_CLAUDE if rev == "claude" else team.REVIEW_CODEX) % "ana-r"
            want = [prompt] if rev == "claude" else ["--sandbox", "workspace-write", "--add-dir", (home / ".git").as_posix(),
                                                     "-c", "sandbox_workspace_write.network_access=true", prompt]
            assert run[0] == rev and args == want and "UAK_AGENT=[ana-r]" in run and "UAK_HUMAN=[]" in run, run
        # A .uak-env in the main checkout naming another agent would run the review under that name: no command.
        (target / ".uak-env").write_text("UAK_AGENT=claude-ana\n", encoding="utf-8")
        view = get(srv, "/api/team")[1]
        assert "review" not in team.by_id(view) and ".uak-env" in view.get("note", ""), view
        team.spanish_for(view)
        (target / ".uak-env").unlink()


def unavailable_tool_is_not_offered(root, tmp):
    reasons = {"project": "Not installed in this project.", "computer": "Not found on this computer.",
               "signed out": "Sign in to it in a terminal first."}
    for case, reason in sorted(reasons.items()):
        folder = tmp / case.replace(" ", "-")
        folder.mkdir()
        target, _ = roles_project(root, folder, ("claude",) if case == "project" else ("claude", "codex"))
        runner = team.Team()
        if case == "signed out":
            runner.tools["codex"] = 1
        with tp.live(target, runner) as srv:
            if case == "computer":
                srv.planning.find_binary = lambda name: None if name == "codex" else "/fake/bin/" + name
            # A pick saved while Codex was available falls back when it is not.
            path = roles_file(target)
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps({"version": 1, "people": {"ana": {"implement": "codex", "review": "codex"}}}),
                            encoding="utf-8")
            team.ready(srv, target)
            view = get(srv, "/api/team")[1]
            codex = {t["id"]: t for t in view.get("tools") or []}.get("codex") or {}
            assert codex.get("available") is False and codex["reason"] == reason and codex["role"] == "none", codex
            assert not [c for c in view["commands"] if "codex" in c["command"]], view["commands"]
            assert view["roles"]["implement"] == view["roles"]["review"] == "claude", view["roles"]
            assert view["roles"]["note"] == "Your saved choice used a tool that is not available now, so setup chose again."
            team.spanish_for(view)
            status, body = post(srv, "/api/team/roles", {"implement": "claude", "review": "codex"})
            assert status == 400 and reason in body.get("error", ""), body
            assert team.translated("That coding tool is not available here: " + reason), "Spanish for the refusal"
    # Cursor only: nothing setup can start, both reasons named, the bare claim stays in the guide.
    folder = tmp / "cursor"
    folder.mkdir()
    target, _ = roles_project(root, folder, ())
    (target / ".cursor").mkdir()
    with tp.live(target, team.Team()) as srv:
        team.ready(srv, target)
        view = get(srv, "/api/team")[1]
    assert view["commands"] == [], view
    assert "Claude Code: Not installed in this project." in view["note"] and "Codex: Not installed in this project." \
        in view["note"], view["note"]
    team.spanish_for(view)


TESTS = [roles_follow_the_tools_you_have, one_tool_does_both_roles, any_tool_can_review, unavailable_tool_is_not_offered]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("roles_setup", root / ".uak/bin/lib/setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    team.MODULE = wizard.MODULE = module  # amendment 11e: the imported helpers use this package's setup.py
    spec = importlib.util.spec_from_file_location("roles_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-roles-"))
        started = time.monotonic()
        try:
            test(root, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s: %s)" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_ROLES_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
