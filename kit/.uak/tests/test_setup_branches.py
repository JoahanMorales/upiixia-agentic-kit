#!/usr/bin/env python3
"""UI-020: branches and publishing never leave a dead end.
Evidence: Dylan's live turno-cafeteria-2 (GitHub's default branch became claims) and QA round B of 2026-11-14
(notes/handoff:qa/rounds-2026-11-14/B-REPORT.md B-01, B-03, B-09, B-16): a teammate's clone landed on claims and the
kit was installed there; after the way-out `git pull`, publishing refused in English with no command; "El comando de
abajo…" was shown with no command; a quote mark in the project path blocked the way-out.
Real HTTP, real Git with local bare remotes; a fake installer and fake planner (test_setup_planning)."""
import argparse
import importlib.util
import os
import re
import subprocess
import tempfile
from pathlib import Path

import test_setup_planning as tp
import test_setup_prepare as prep
import test_setup_team as tt
import test_setup_wizard as wizard
from test_hack import resolve_binary

DEFAULT_STEPS = ("Settings", "Default branch")


class Recording(tp.FakePlanner):
    """The fake planner that also records every command the server runs (the installer among them)."""

    def __init__(self):
        super().__init__()
        self.argv = []

    def __call__(self, command, *args, **kwargs):
        self.argv.append([str(c) for c in command])
        return super().__call__(command, *args, **kwargs)


def bash(line, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    return subprocess.run([resolve_binary("bash"), "-c", line], cwd=str(cwd), env=env, capture_output=True, text=True,
                          timeout=120)


def physical(path):
    return Path(os.path.realpath(str(path)))


def page():
    return Path(wizard.MODULE.__file__).with_name("setup.html").read_text(encoding="utf-8")


def claims_default_remote(tmp):
    """A GitHub-like remote whose default branch (HEAD) is claims: main has the app, claims the coordination files."""
    remote = tmp / "origin.git"
    tp.git(tmp, "init", "-q", "--bare", "-b", "main", str(remote))
    seed = tmp / "seed"
    seed.mkdir()
    tp.git(seed, "init", "-q", "-b", "main")
    (seed / "README.md").write_text("# cafeteria\n", encoding="utf-8")
    tp.git(seed, "add", "-A")
    tp.git(seed, "-c", "user.name=x", "-c", "user.email=x@example.invalid", "commit", "-q", "-m", "app")
    tp.git(seed, "push", "-q", str(remote), "main")
    tp.git(seed, "checkout", "-q", "--orphan", "claims")
    tp.git(seed, "rm", "-q", "-rf", ".")
    (seed / "claims").mkdir()
    (seed / "claims/README.md").write_text("claims\n", encoding="utf-8")
    tp.git(seed, "add", "-A")
    tp.git(seed, "-c", "user.name=x", "-c", "user.email=x@example.invalid", "commit", "-q", "-m", "claims")
    tp.git(seed, "push", "-q", str(remote), "claims")
    tp.git(remote, "symbolic-ref", "HEAD", "refs/heads/claims")
    return remote


def teammate_clone(tmp, remote, name="teammate app"):
    clone = tmp / name
    tp.git(tmp, "clone", "-q", str(remote), str(clone))
    tp.git(clone, "config", "user.name", "Luis Human")
    tp.git(clone, "config", "user.email", "luis@example.invalid")
    return clone


def fake_installer(tmp):
    script = tmp / "install.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    return script


def server(target, runner, installer):
    srv = wizard.LiveServer(str(target), run=runner, installer=str(installer))
    srv.server.planning.find_binary = tp.found
    return srv


def spanish(*texts):
    missing = [t for t in texts if t and not tt.translated(t)]
    assert not missing, "no Spanish entry in workspace.js for: %r" % missing


# --- the five named tests of UI-020 -----------------------------------------------------------------------------------


def install_refuses_a_non_base_branch(root, tmp):
    """B-01: a clone of a remote whose default branch is claims lands on claims; inspect warns, install stops."""
    remote = claims_default_remote(tmp)
    clone = teammate_clone(tmp, remote)
    assert tp.git(clone, "symbolic-ref", "--short", "HEAD") == "claims", "the fixture reproduces B-01"
    home = physical(clone)
    runner = Recording()
    with server(clone, runner, fake_installer(tmp)) as srv:
        status, state = tp.post(srv, "/api/inspect", {"target": str(clone)})
        assert status == 200, state
        branch = state.get("branch") or {}
        assert branch.get("wrong") is True and branch.get("head") == "claims" and branch.get("base") == "main", branch
        assert "git switch main" in branch.get("message", ""), "the warning names the command: %r" % branch
        assert branch.get("command") == "cd %s && git switch main" % tt.q(home), branch
        spanish(branch["message"])
        assert tp.get(srv, "/api/status")[1].get("branch", {}).get("wrong") is True, "status keeps the warning"
        status, body = tp.post(srv, "/api/install", {"mode": "sprint", "harness": ["claude", "codex"]})
        assert status == 400 and "git switch main" in body.get("error", ""), "install stops on claims: %r" % body
        spanish(body["error"])
        assert not (clone / ".uak").exists(), "nothing was installed on claims"
        assert not [a for a in runner.argv if any(p.endswith("install.sh") for p in a)], "the installer never ran"
        # A detached HEAD is not the base branch either.
        tp.git(clone, "checkout", "-q", "--detach", "origin/main")
        state = tp.post(srv, "/api/inspect", {"target": str(clone)})[1]
        assert state["branch"].get("wrong") is True and "git switch main" in state["branch"]["message"], state["branch"]
        spanish(state["branch"]["message"])
        assert tp.post(srv, "/api/install", {"mode": "sprint", "harness": ["claude"]})[0] == 400
        # The offered command works; then inspect has no warning and install runs.
        done = bash(branch["command"], tmp)
        assert done.returncode == 0, done.stdout + done.stderr
        assert tp.git(clone, "symbolic-ref", "--short", "HEAD") == "main"
        state = tp.post(srv, "/api/inspect", {"target": str(clone)})[1]
        assert not state["branch"].get("wrong"), state["branch"]
        status, body = tp.post(srv, "/api/install", {"mode": "sprint", "harness": ["claude"]})
        assert status == 202, body
        tp.wait_idle(srv)
        assert [a for a in runner.argv if any(p.endswith("install.sh") for p in a)], "the installer ran on main"
    # A project whose only branch is master (no main anywhere): the command renames it, it never says "switch".
    solo = tmp / "solo app"
    solo.mkdir()
    tp.git(solo, "init", "-q", "-b", "master")
    (solo / "app.py").write_text("print(1)\n", encoding="utf-8")
    tp.git(solo, "add", "-A")
    tp.git(solo, "-c", "user.name=x", "-c", "user.email=x@example.invalid", "commit", "-q", "-m", "app")
    with server(solo, Recording(), fake_installer(tmp)) as srv:
        branch = tp.post(srv, "/api/inspect", {"target": str(solo)})[1]["branch"]
        assert branch.get("wrong") is True and branch["command"] == "cd %s && git branch -m master main" % \
            tt.q(physical(solo)), branch
        spanish(branch["message"])
        assert tp.post(srv, "/api/install", {"mode": "sprint", "harness": ["claude"]})[0] == 400
    # The page stops on the project step with the warning and its command.
    html = page()
    assert 'id="branch-warning"' in html and 'id="branch-warning-command"' in html, "the page has the warning box"
    script = html[html.index('el("project-form").onsubmit'):]
    script = script[:script.index('el("workflow-form").onsubmit')]
    assert "drawBranch(" in script and "branch" in script, "the project step draws the branch warning"
    for line in ("This folder is not on the main branch", "Run this in a terminal, then press Check project folder again:"):
        assert line in html, line
        spanish(line)


def warns_when_remote_default_is_claims(root, tmp):
    """Dylan's live case: GitHub's default branch became claims; new clones land there. The page says how to fix it."""
    # (a) a clone knows its remote's default branch locally (refs/remotes/origin/HEAD), even once it is on main
    remote = claims_default_remote(tmp)
    clone = teammate_clone(tmp, remote)
    tp.git(clone, "switch", "-q", "main")
    with server(clone, Recording(), fake_installer(tmp)) as srv:
        state = tp.post(srv, "/api/inspect", {"target": str(clone)})[1]
    branch = state.get("branch") or {}
    assert not branch.get("wrong") and branch.get("remote_default") == "claims", branch
    note = branch.get("remote_note", "")
    assert all(word in note for word in DEFAULT_STEPS) and "main" in note, "it says how to change it on GitHub: %r" % note
    assert "git remote set-head origin -a" in note, note
    spanish(note)
    # (b) the owner's folder never cloned (no origin/HEAD): learnt from the remote when setup reads it
    owner = tmp / "owner"
    owner.mkdir()
    target, remote = tp.project(root, owner, harnesses=("claude",), name="owner app")
    seed = owner / "seed"
    tp.git(owner, "clone", "-q", str(remote), str(seed))
    tp.git(seed, "checkout", "-q", "--orphan", "claims")
    tp.git(seed, "rm", "-q", "-rf", ".")
    (seed / "x.md").write_text("claims\n", encoding="utf-8")
    tp.git(seed, "add", "-A")
    tp.git(seed, "-c", "user.name=x", "-c", "user.email=x@example.invalid", "commit", "-q", "-m", "claims")
    tp.git(seed, "push", "-q", "origin", "claims")
    tp.git(remote, "symbolic-ref", "HEAD", "refs/heads/claims")
    with tp.live(target, tp.FakePlanner()) as srv:
        state = tp.post(srv, "/api/inspect", {"target": str(target)})[1]
        assert not state["branch"].get("remote_default"), "nothing known before reading the remote: %r" % state["branch"]
        assert tp.get(srv, "/api/plan")[0] == 200
        branch = tp.get(srv, "/api/status")[1].get("branch") or {}
    assert branch.get("remote_default") == "claims" and all(w in branch.get("remote_note", "") for w in DEFAULT_STEPS), \
        branch
    spanish(branch["remote_note"])
    html = page()
    assert 'id="remote-default-warning"' in html, "the page has a place for it"
    assert "remote_note" in html, "the page draws the server's note"


def way_out_includes_the_push(root, tmp):
    """B-03: after the way-out `git pull`, publishing refused in English with no command; git push was needed."""
    target, remote = prep.installed(root, tmp)
    tp.git(target, "add", "AGENTS.md")
    tp.git(target, "commit", "-q", "-m", "my own start")
    prep.remote_commit(remote, tmp, {"README.md": "# made on GitHub\n"}, "b")
    home = physical(target)
    with tp.live(target, tp.FakePlanner()) as srv:
        prep.ready_to_publish(srv, target)
        status, body = tp.get(srv, "/api/publish-kit")
        assert status == 400 and body.get("way_out"), body
        out = body["way_out"]
        assert out["command"].endswith("--allow-unrelated-histories origin main"), out
        assert out.get("push") == "cd %s && git push origin main" % tt.q(home), "the second command: %r" % out
        assert any("git push origin main" in s for s in out["steps"]), out["steps"]
        tt.spanish_for(body)
        done = bash(out["command"], tmp)
        assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
        # Between the two commands: the refusal names the exact command, in both languages.
        status, body = tp.get(srv, "/api/publish-kit")
        assert status == 400 and not body.get("way_out"), body
        assert "git push origin main" in body["error"], "the refusal gives the exact command: %r" % body["error"]
        tt.spanish_for(body)
        done = bash(out["push"], tmp)
        assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
        prep.publish(srv)
    assert prep.remote_head(remote) == tp.git(target, "rev-parse", "HEAD"), "the kit is on origin/main"
    # An unborn folder needs no push after the pull: no second command.
    (tmp / "a").mkdir()
    target, remote = prep.installed(root, tmp / "a")
    prep.remote_commit(remote, tmp / "a", {"README.md": "# made on GitHub\n"}, "a")
    with tp.live(target, tp.FakePlanner()) as srv:
        prep.ready_to_publish(srv, target)
        out = tp.get(srv, "/api/publish-kit")[1]["way_out"]
    assert out["command"] and not out.get("push"), out
    # Diverged (shared history, both sides moved): pull, then push, never a bare "push or move them".
    (tmp / "d").mkdir()
    target, remote = prep.installed(root, tmp / "d")
    tp.git(target, "add", "AGENTS.md")
    tp.git(target, "commit", "-q", "-m", "first")
    tp.git(target, "push", "-q", "origin", "main")
    (target / "mine.txt").write_text("mine\n", encoding="utf-8")
    tp.git(target, "add", "mine.txt")
    tp.git(target, "commit", "-q", "-m", "mine")
    prep.remote_commit(remote, tmp / "d", {"README.md": "theirs\n"}, "d")
    with tp.live(target, tp.FakePlanner()) as srv:
        prep.ready_to_publish(srv, target)
        status, body = tp.get(srv, "/api/publish-kit")
    assert status == 400 and "git pull --no-rebase origin main" in body["error"] and "git push origin main" in \
        body["error"], body
    tt.spanish_for(body)
    html = page()
    assert 'id="publish-way-out-push"' in html and "out.push" in html, "the page shows the second command"


def no_promise_without_a_command(root, tmp):
    """B-09: "El comando de abajo…" shown with no command below it."""
    (tmp / "f").mkdir()
    target, remote = prep.installed(root, tmp / "f")
    (target / "docs").mkdir()
    (target / "docs/note.md").write_text("mine\n", encoding="utf-8")
    prep.remote_commit(remote, tmp / "f", {"docs": "remote file\n"}, "f")
    with tp.live(target, tp.FakePlanner()) as srv:
        prep.ready_to_publish(srv, target)
        status, body = tp.get(srv, "/api/publish-kit")
    assert status == 400 and body["way_out"]["command"] == "", body
    assert "below" not in body["error"].replace("steps below", ""), "no command, no 'command below': %r" % body["error"]
    tt.spanish_for(body)
    # With a command, the sentence stays.
    (tmp / "c").mkdir()
    target, remote = prep.installed(root, tmp / "c")
    prep.remote_commit(remote, tmp / "c", {"README.md": "# on GitHub\n"}, "c")
    with tp.live(target, tp.FakePlanner()) as srv:
        prep.ready_to_publish(srv, target)
        body = tp.get(srv, "/api/publish-kit")[1]
    assert body["way_out"]["command"] and "command below" in body["error"], body
    # The team step with no coding tool available: the command it talks about is in the sentence itself.
    (tmp / "t").mkdir()
    target, _ = tt.ready_project(root, tmp / "t")
    team = tt.Team()
    team.tools = {"claude": 1, "codex": 1}
    with tp.live(target, team) as srv:
        team.srv = srv
        tt.ready(srv, target)
        status, view = tp.get(srv, "/api/team")
    assert status == 200 and not view.get("commands"), view
    note = view.get("note", "")
    assert note.startswith("No coding tool can start here"), view
    assert "command below" not in note, "no command is shown below: %r" % note
    assert "cd %s && bash .uak/bin/wt new APP-001" % tt.q(physical(target)) in note, "the exact command: %r" % note
    tt.spanish_for(view)


def quote_in_path_gets_a_command(root, tmp):
    """B-16: a quote mark in the project path blocked the way-out though shell_quote handles it."""
    target, remote = prep.installed(root, tmp, name="proj d'Ana é")
    tp.git(target, "add", "AGENTS.md")
    tp.git(target, "commit", "-q", "-m", "my own start")
    prep.remote_commit(remote, tmp, {"README.md": "# made on GitHub\n"}, "q")
    home = physical(target)
    with tp.live(target, tp.FakePlanner()) as srv:
        prep.ready_to_publish(srv, target)
        out = prep.way_out(srv)
        assert out["command"] == ("cd %s && git pull --no-rebase --no-edit --allow-unrelated-histories origin main"
                                  % tt.q(home)), out
        assert "'\\''" in out["command"], "the quote mark is escaped inside single quotes: %r" % out["command"]
        assert out.get("push") == "cd %s && git push origin main" % tt.q(home), out
        for line in (out["command"], out["push"]):
            done = bash(line, tmp)
            assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
        prep.publish(srv)
    assert prep.remote_head(remote) == tp.git(target, "rev-parse", "HEAD")
    # A control character is still never put in a command.
    assert not wizard.MODULE.printable("a\nb") and wizard.MODULE.printable("d'Ana é")


TESTS = [install_refuses_a_non_base_branch, warns_when_remote_default_is_claims, way_out_includes_the_push,
         no_promise_without_a_command, quote_in_path_gets_a_command]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("branches_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    tt.MODULE = wizard.MODULE
    spec = importlib.util.spec_from_file_location("branches_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-branches-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("SETUP_BRANCHES_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
