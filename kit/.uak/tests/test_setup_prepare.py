#!/usr/bin/env python3
"""Preparing the project from the page (UI-005): the event schedule, publishing the kit to main, the terminal box,
planning only with the kit on main, lint reasons and rechecking a plan. Real HTTP, real Git with a local bare
remote, the engine's real `uak clock` and `uak lint`; a fake planner stands in for the coding tool.
Evidence: the hackathon simulation of 2026-11-11 (notes/handoff:PENDING-IMPROVEMENTS.md #5, #6 and #8 to #10, plus #12)."""
import argparse
import datetime
import importlib.util
import json
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

PLAN_FILES = ("IDEA.md", ".uak/TASKS.md", ".uak/OWNERS.md")


def installed(root, tmp, name="prep project"):
    """An installed sprint project that was never committed, with an EMPTY bare origin (a fresh GitHub repo)."""
    remote = tmp / "origin.git"
    tp.git(tmp, "init", "-q", "--bare", "-b", "main", str(remote))
    target = tmp / name
    target.mkdir()
    tp.git(target, "init", "-q", "-b", "main")
    tp.git(target, "config", "user.name", "Ana Human")
    tp.git(target, "config", "user.email", "ana@example.invalid")
    tp.git(target, "config", "core.hooksPath", str(tmp / "no-hooks"))
    shutil.copytree(str(root / ".uak"), str(target / ".uak"), ignore=shutil.ignore_patterns("tests", "__pycache__"))
    shutil.copy(str(root / "AGENTS.md"), str(target / "AGENTS.md"))
    (target / ".github").mkdir()
    shutil.copy(str(root / ".github/pull_request_template.md"), str(target / ".github/pull_request_template.md"))
    (target / ".uak/PROJECT.md").write_text((root / ".uak/templates/PROJECT.sprint.md").read_text(encoding="utf-8"),
                                           encoding="utf-8")
    (target / ".claude").mkdir()
    (target / ".claude/README.md").write_text("harness settings\n", encoding="utf-8")
    # The manifest install.sh writes: every file this fixture placed, as the real installer lists them.
    placed = sorted(str(f.relative_to(target)).replace("\\", "/") for f in target.rglob("*")
                    if f.is_file() and ".git" not in f.relative_to(target).parts)
    (target / ".uak/installed-files.txt").write_text("# fixture manifest\n" + "\n".join(placed + [".uak/installed-files.txt"]) + "\n",
                                                    encoding="utf-8")
    tp.git(target, "remote", "add", "origin", str(remote))
    return target, remote


def really_installed(root, tmp, name="real project", before=None):
    """A project installed by the real install.sh (empty bare origin), or None in an installed project (no installer)."""
    installer = root.parent / "install.sh"
    if not installer.is_file():
        return None, None
    remote = tmp / "origin.git"
    tp.git(tmp, "init", "-q", "--bare", "-b", "main", str(remote))
    target = tmp / name
    target.mkdir()
    tp.git(target, "init", "-q", "-b", "main")
    tp.git(target, "config", "user.name", "Ana Human")
    tp.git(target, "config", "user.email", "ana@example.invalid")
    tp.git(target, "config", "core.hooksPath", str(tmp / "no-hooks"))
    tp.git(target, "remote", "add", "origin", str(remote))
    for rel, text in (before or {}).items():  # the person's own files, there before the kit is installed
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        (target / rel).write_text(text, encoding="utf-8")
    done = subprocess.run([resolve_binary("bash"), str(installer), "--mode", "sprint", "--harness", "claude,codex",
                           "--no-mcp", str(target)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-600:]
    return target, remote


def catalog_of_page(root):
    return tp.catalog_of(root)


def remote_files(remote):
    shown = subprocess.run([resolve_binary("git"), "-C", str(remote), "ls-tree", "-r", "--name-only", "main"],
                           capture_output=True, text=True)
    return set(shown.stdout.split()) if shown.returncode == 0 else set()


def remote_head(remote):
    shown = subprocess.run([resolve_binary("git"), "-C", str(remote), "rev-parse", "-q", "--verify", "refs/heads/main"],
                           capture_output=True, text=True)
    return shown.stdout.strip()


def ready_to_publish(srv, target, name="ana"):
    assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
    status, body = tp.post(srv, "/api/human", {"name": name})
    assert status == 200, body
    status, body = tp.post(srv, "/api/schedule", {"start": "2026-11-12 10:00", "end": "2026-11-12 13:00",
                                                  "zone": "America/Mexico_City"})
    assert status == 200, body


def publish(srv):
    status, preview = tp.get(srv, "/api/publish-kit")
    assert status == 200, preview
    status, body = tp.post(srv, "/api/publish-kit", {"digest": preview["digest"]})
    assert status == 202, body
    tp.wait_idle(srv)
    state = tp.get(srv, "/api/status")[1]
    assert not state.get("error"), state
    return preview


def schedule_form_writes_freeze_epoch(root, tmp):
    target, _ = installed(root, tmp)
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        before = (target / ".uak/PROJECT.md").read_bytes()
        for bad in ({"start": "tomorrow", "end": "2026-11-12 13:00", "zone": "America/Mexico_City"},
                    {"start": "2026-11-12 10:00", "end": "2026-11-12 13:00", "zone": "x; rm -rf ~"},
                    {"start": "2026-11-12 10:00", "end": "2026-11-12 09:00", "zone": "America/Mexico_City"},
                    {"start": "2026-11-12 10:00", "end": "2026-11-12 13:00", "zone": "America/Mexico_City", "x": 1}):
            assert tp.post(srv, "/api/schedule", bad)[0] == 400, "refused: %r" % (bad,)
        assert (target / ".uak/PROJECT.md").read_bytes() == before, "a refused schedule writes nothing"
        status, body = tp.post(srv, "/api/schedule", {"start": "2026-11-12 10:00", "end": "2026-11-12 13:00",
                                                      "zone": "America/Mexico_City"})
        assert status == 200, body
        assert body.get("freeze") and body.get("first_claim"), "the page shows the freeze and the first claim: %r" % body
    expected = subprocess.run([resolve_binary("bash"), str(target / ".uak/bin/uak"), "clock", "2026-11-12 10:00",
                               "2026-11-12 13:00", "America/Mexico_City"], cwd=str(target), capture_output=True, text=True)
    epoch = re.search(r"Freeze-Epoch: (\d+)", expected.stdout).group(1)
    written = re.search(r"(?m)^Freeze-Epoch: (\d+)", (target / ".uak/PROJECT.md").read_text(encoding="utf-8")).group(1)
    assert written == epoch, "the form writes what uak clock --write writes: %s vs %s" % (written, epoch)


def publish_kit_excludes_unapproved_plan_files(root, tmp):
    target, remote = installed(root, tmp)
    (target / "IDEA.md").write_text("# IDEA · not approved yet\n", encoding="utf-8")
    (target / ".uak/TASKS.md").write_text(tp.GOOD_PLAN, encoding="utf-8")
    (target / ".uak/OWNERS.md").write_text(tp.OWNERS, encoding="utf-8")
    (target / "notes.txt").write_text("my own work in progress\n", encoding="utf-8")
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        status, body = tp.get(srv, "/api/publish-kit")
        assert status == 400 and "name" in body.get("error", "").lower(), "publishing needs the human's name first"
        ready_to_publish(srv, target)
        preview = publish(srv)
        listed = set(preview["files"])
        for name in PLAN_FILES + ("notes.txt",):
            assert name not in listed, "the preview never lists %s" % name
        assert {"AGENTS.md", ".uak/PROJECT.md"} <= listed, preview["files"][:10]
    files = remote_files(remote)
    assert {"AGENTS.md", ".uak/PROJECT.md", ".uak/bin/uak"} <= files, "the kit reached main"
    for name in PLAN_FILES + ("notes.txt",):
        assert name not in files, "%s never reaches main before its approval" % name
    message = tp.git(target, "log", "-1", "--format=%B", remote_head(remote))
    assert message.startswith("chore: uak setup") and "Published-By: ana" in message, message
    status = tp.git(target, "status", "--porcelain")
    for name in ("IDEA.md", "notes.txt"):
        assert name in status, "the person's other files stay untouched (%s)" % name


def publish_kit_pushes_only_the_verified_commit(root, tmp):
    target, remote = installed(root, tmp)

    def concurrent_commit(repo):
        (repo / "unreviewed.py").write_text("print('not reviewed')\n", encoding="utf-8")
        tp.git(repo, "add", "unreviewed.py")
        tp.git(repo, "commit", "-q", "-m", "unreviewed work")

    with tp.live(target, tp.FakePlanner(on_push=concurrent_commit)) as srv:
        ready_to_publish(srv, target)
        (target / "staged.txt").write_text("staged\n", encoding="utf-8")
        tp.git(target, "add", "staged.txt")
        status, preview = tp.get(srv, "/api/publish-kit")
        status, body = tp.post(srv, "/api/publish-kit", {"digest": preview.get("digest", "")})
        assert status == 400 and "staged.txt" in body.get("error", ""), "other staged files block publishing: %r" % body
        tp.git(target, "rm", "-q", "--cached", "staged.txt")
        status, body = tp.post(srv, "/api/publish-kit", {"digest": "0" * 64})
        assert status == 400, "the files shown in the preview are the ones published"
        publish(srv)
    head = remote_head(remote)
    assert head and tp.git(target, "rev-parse", "HEAD^") == head, "the verified commit, not HEAD, reached main"
    assert "unreviewed.py" not in remote_files(remote)
    (tmp / "second").mkdir()
    other, other_remote = installed(root, tmp / "second")
    clone = tmp / "second" / "someone else"
    tp.git(tmp, "clone", "-q", str(other_remote), str(clone))
    (clone / "README.md").write_text("pushed by someone else\n", encoding="utf-8")
    tp.git(clone, "add", "README.md")
    tp.git(clone, "-c", "user.name=x", "-c", "user.email=x@example.invalid", "commit", "-q", "-m", "other")
    tp.git(clone, "push", "-q", "origin", "HEAD:main")
    with tp.live(other, tp.FakePlanner()) as srv:
        ready_to_publish(srv, other)
        status, preview = tp.get(srv, "/api/publish-kit")
        status, body = tp.post(srv, "/api/publish-kit", {"digest": preview.get("digest", "")})
        assert status == 400 and "git pull" in body.get("error", ""), "a remote main ahead says how to recover: %r" % body


def terminal_step_is_shown_with_its_command(root, tmp):
    g = tp.wizard.MODULE.guidance
    base = {"installed": True, "phase": "setup", "target": str(tmp / "my project")}
    freeze = g(dict(base, checks=[{"state": "todo", "text": "3. preflight: doctor found 1 failure(s)\n"
                                   "· sprint without Freeze-Epoch: uak clock \"START\" \"DEADLINE\" [ZONE] --write sets it"}]))
    assert freeze.get("action") == "schedule", "the freeze is set in the page, not a terminal: %r" % freeze
    push = g(dict(base, checks=[{"state": "todo", "text": "4. push the kit to main: agents read .uak/PROJECT.md\n"
                                 "git add -A && git commit -m 'chore: uak setup' && git push -u origin HEAD:main"}]))
    assert push.get("action") == "publish", "publishing the kit happens in the page: %r" % push
    mixed = g(dict(base, checks=[{"state": "todo", "text": "3. preflight: doctor found 2 failure(s)\n"
                                  "· push rejected in dry-run: no push means no claims or branches\n"
                                  "· .agents/skills is a stale copy: bash .uak/bin/doctor --fix"}]))
    assert mixed.get("action") == "publish", "an empty remote is fixed by publishing the kit: %r" % mixed
    assert (mixed.get("terminal") or {}).get("steps") == ["· .agents/skills is a stale copy: bash .uak/bin/doctor --fix"], \
        "what the page cannot do still reaches a terminal box, and only that: %r" % mixed
    remote = g(dict(base, checks=[{"state": "todo", "text": "2. a remote named origin\n"
                                   "git remote add origin <URL of the empty GitHub repo>"}]))
    box = remote.get("terminal") or {}
    assert box.get("cd") == "cd '%s'" % (tmp / "my project"), "the box starts with the exact cd: %r" % box
    assert box.get("steps") == ["git remote add origin <URL of the empty GitHub repo>"], box
    assert remote.get("commands") == [], "gate lines stay text; only the cd and the claim command are copyable"
    page = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")
    assert 'id="terminal-step"' in page and 'id="terminal-cd"' in page and 'id="copy-terminal-cd"' in page
    assert "Check again" in page and "Do this in a terminal" in page


def planning_waits_for_the_kit_on_main(root, tmp):
    target, _ = installed(root, tmp)
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert tp.post(srv, "/api/idea", tp.idea_fields())[0] == 200
        view = tp.get(srv, "/api/plan")[1]
        assert view.get("kit_on_main") is False, "the plan view says the kit is not on main yet"
        status, body = tp.post(srv, "/api/plan", {"harness": "claude"})
        assert status == 400 and "Publish the kit" in body.get("error", ""), body
        status, body = tp.post(srv, "/api/human", {"name": "ana"})
        status, body = tp.post(srv, "/api/schedule", {"start": "2026-11-12 10:00", "end": "2026-11-12 13:00",
                                                      "zone": "America/Mexico_City"})
        publish(srv)
        assert tp.get(srv, "/api/plan")[1].get("kit_on_main") is True
        assert tp.post(srv, "/api/plan", {"harness": "claude"})[0] == 202
        tp.wait_idle(srv)


def lint_failure_reason_reaches_the_page(root, tmp):
    target, _ = installed(root, tmp)
    (target / ".uak/TASKS.md").write_text(tp.GOOD_PLAN, encoding="utf-8")
    checked = tp.PLANNING.lint(wizard.MODULE.run_command, target, root / ".uak/bin/uak", wizard.MODULE.bash_binary())
    assert not checked["ok"], checked
    assert checked["lines"] and any("main" in line for line in checked["lines"]), \
        "a failure that is not a LINT: line still says why: %r" % checked


def plan_can_be_rechecked_without_the_planner(root, tmp):
    target, _ = installed(root, tmp)
    planner = tp.FakePlanner(plan=tp.CYCLE_PLAN)
    with tp.live(target, planner) as srv:
        ready_to_publish(srv, target)
        assert tp.post(srv, "/api/plan/check", {})[0] == 400, "nothing to recheck before a plan exists"
        publish(srv)
        plan = tp.planned(srv, target)
        assert not plan["lint"]["ok"], plan["lint"]
        (target / ".uak/TASKS.md").write_text(tp.GOOD_PLAN, encoding="utf-8")
        status, body = tp.post(srv, "/api/plan/check", {})
        assert status == 200, body
        view = tp.get(srv, "/api/plan")[1]
        assert view["lint"]["ok"] and view["digest"] != plan["digest"], view["lint"]
        assert len(planner.calls) == 1, "the planner did not run again"
        status, body = tp.post(srv, "/api/plan/approve", {"confirm": target.name, "digest": view["digest"]})
        assert status == 202, "the rechecked plan can be approved: %r" % body
        tp.wait_idle(srv)


def human_name_is_asked_once(root, tmp):
    target, _ = installed(root, tmp)
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert tp.get(srv, "/api/status")[1].get("human") == "", "no name until the person gives one"
        for bad in ("", "ana; rm -rf ~", "x" * 60, "Ana Human", "-ana", 7, "ana\n", "ana\nPublished-By: root", "an\u0661a"):
            assert tp.post(srv, "/api/human", {"name": bad})[0] == 400, "refused name: %r" % (bad,)
        assert tp.post(srv, "/api/human", {"name": "ana", "extra": 1})[0] == 400
        assert tp.post(srv, "/api/human", {"name": "ana"})[0] == 200
        assert tp.get(srv, "/api/status")[1].get("human") == "ana", "the name is kept for every human act"
    page = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")
    assert 'id="human-name"' in page, "the page asks for the name"
    assert "UAK_HUMAN=" not in page, "the page never asks a person to type UAK_HUMAN into a command"


def publish_never_includes_files_the_installer_did_not_place(root, tmp):
    """Review of 0386bec (P1): a directory prefix is not ownership. A file the person adds under .github/ or .uak/
    after installing is never listed nor pushed; the installer's own manifest decides."""
    target, remote = really_installed(root, tmp)
    if target is None:
        return
    manifest = target / ".uak/installed-files.txt"
    assert manifest.is_file(), "install.sh writes the manifest of the files it placed"
    (target / ".github/private-note.txt").write_text("not for the kit\n", encoding="utf-8")
    (target / ".uak/private.json").write_text('{"secret": true}\n', encoding="utf-8")
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        preview = publish(srv)
        for name in (".github/private-note.txt", ".uak/private.json"):
            assert name not in preview["files"], "%s is not a kit file" % name
    files = remote_files(remote)
    assert ".uak/PROJECT.md" in files and ".uak/installed-files.txt" in files
    assert ".github/private-note.txt" not in files and ".uak/private.json" not in files


def publish_verifies_the_whole_committed_tree(root, tmp):
    """Review of 0386bec (P1): a previewed deletion that a pre-commit hook recreates with other content never reaches
    main. The committed tree must equal the preview: blob, type and mode for each path, absence for deletions."""
    target, remote = really_installed(root, tmp)
    if target is None:
        return
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        publish(srv)
        first = remote_head(remote)
        (target / ".github/pull_request_template.md").unlink()
        hooks = tmp / "evil-hooks"
        hooks.mkdir()
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'UNREVIEWED PAYLOAD' > .github/pull_request_template.md\n"
                        "git add .github/pull_request_template.md\n", encoding="utf-8")
        hook.chmod(0o755)
        tp.git(target, "config", "core.hooksPath", str(hooks))
        status, preview = tp.get(srv, "/api/publish-kit")
        assert status == 200 and ".github/pull_request_template.md" in preview["files"], preview
        status, body = tp.post(srv, "/api/publish-kit", {"digest": preview["digest"]})
        assert status == 202, body
        tp.wait_idle(srv)
        state = tp.get(srv, "/api/status")[1]
        assert state.get("error"), "a commit that differs from the preview is reported, not pushed: %r" % state
    assert remote_head(remote) == first, "nothing reached main"
    assert tp.git(target, "rev-parse", "HEAD") == first, "the refused local commit is undone: refs as before publishing"
    assert tp.git(target, "diff", "--cached", "--name-only") == "", "the index is as before publishing"
    shown = subprocess.run([resolve_binary("git"), "-C", str(remote), "show", "main:.github/pull_request_template.md"],
                           capture_output=True, text=True)
    assert "UNREVIEWED PAYLOAD" not in shown.stdout


def schedule_never_follows_links(root, tmp):
    """Review of 0386bec (P1): the schedule never writes through a symlinked .uak/PROJECT.md, and never through a
    predictable temporary file such as .uak/PROJECT.md.tmp."""
    target, _ = installed(root, tmp)
    outside = tmp / "outside.md"
    outside.write_text("external file\n", encoding="utf-8")
    config = target / ".uak/PROJECT.md"
    original = config.read_text(encoding="utf-8")
    good = {"start": "2026-11-12 10:00", "end": "2026-11-12 13:00", "zone": "America/Mexico_City"}
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        config.unlink()
        try:
            config.symlink_to(outside)
        except OSError as exc:  # Windows without Developer Mode: WinError 1314, no symlink can exist to follow
            config.write_text(original, encoding="utf-8")
            print("SKIP schedule_never_follows_links: %s" % exc)
            return
        assert tp.post(srv, "/api/schedule", good)[0] == 400, "a symlinked PROJECT.md is refused"
        assert outside.read_text(encoding="utf-8") == "external file\n", "the external file is untouched"
        config.unlink()
        config.write_text(original, encoding="utf-8")
        tmp_link = target / ".uak/PROJECT.md.tmp"
        tmp_link.symlink_to(outside)
        status, body = tp.post(srv, "/api/schedule", good)
        assert status == 200, body
        assert outside.read_text(encoding="utf-8") == "external file\n", "no write through a predictable temp file"
        assert re.search(r"(?m)^Freeze-Epoch: [1-9]", config.read_text(encoding="utf-8")), "PROJECT.md got the freeze"
        assert tmp_link.is_symlink(), "the stray link is left as it was"


PERSONAL = {".github/private-note.txt": "my secret note\n", ".uak/private.json": '{"secret": true}\n',
            ".claude/my-notes.md": "mine\n", ".cursor/zz-mine.txt": "mine\n", ".github/workflows/my-ci.yml": "on: push\n",
            ".github/my file.txt": "mine\n"}


def publish_ignores_personal_files_present_before_install(root, tmp):
    """Review of 57ef048 (claude-Dylan-r, P1): files that were there BEFORE the install are not the kit's either. The
    manifest compared snapshots sorted by name with `comm`, which needs whole-line order, so they leaked into it."""
    target, remote = really_installed(root, tmp, before=PERSONAL)
    if target is None:
        return
    listed = (target / ".uak/installed-files.txt").read_text(encoding="utf-8").splitlines()
    for name in PERSONAL:
        assert name not in listed, "%s was there before the install, so it is not in the manifest" % name
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        preview = publish(srv)
        for name in PERSONAL:
            assert name not in preview["files"], "%s is never offered for publishing" % name
    files = remote_files(remote)
    for name in PERSONAL:
        assert name not in files, "%s never reaches main" % name


def failed_commit_leaves_index_and_refs_as_before(root, tmp):
    """Review of 57ef048 (claude-Dylan-r, P2): when the commit itself fails (a pre-commit hook that rejects), nothing
    stays staged and no ref moves, on an empty repository too; the message says what to do."""
    target, remote = really_installed(root, tmp)
    if target is None:
        return
    hooks = tmp / "rejecting-hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'blocked by a test hook' >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    tp.git(target, "config", "core.hooksPath", str(hooks))
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        status, preview = tp.get(srv, "/api/publish-kit")
        assert status == 200, preview
        assert tp.post(srv, "/api/publish-kit", {"digest": preview["digest"]})[0] == 202
        tp.wait_idle(srv)
        state = tp.get(srv, "/api/status")[1]
        assert state.get("error") and "hook" in state["error"].lower(), "the failure names the hook: %r" % state.get("error")
        assert tp.git(target, "diff", "--cached", "--name-only") == "", "nothing stays staged after a failed commit"
        assert subprocess.run([resolve_binary("git"), "-C", str(target), "rev-parse", "-q", "--verify", "HEAD"],
                              capture_output=True).returncode != 0, "the empty repository still has no commit"
        status, again = tp.get(srv, "/api/publish-kit")
        assert status == 200 and again["files"] == preview["files"], "publishing can be retried as it was"
    assert remote_head(remote) == "", "nothing reached main"


def refused_push_says_nothing_was_published(root, tmp):
    """Review of f8d5d84 (claude-Dylan-r, P2): when the remote refuses the push (a pre-push hook that exits 1 with no
    message), the commit is undone, so the page must say nothing was committed or published and offer no push
    command; nothing stays staged, no ref moves, and publishing works again once the cause is gone."""
    target, remote = installed(root, tmp)
    hooks = tmp / "refusing-push-hooks"
    hooks.mkdir()
    hook = hooks / "pre-push"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    tp.git(target, "config", "core.hooksPath", str(hooks))
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        status, preview = tp.get(srv, "/api/publish-kit")
        assert status == 200, preview
        assert tp.post(srv, "/api/publish-kit", {"digest": preview["digest"]})[0] == 202
        tp.wait_idle(srv)
        error = tp.get(srv, "/api/status")[1].get("error") or ""
        assert "refused the push" in error and "nothing was published" in error.lower(), \
            "the page says the push was refused and nothing was published: %r" % error
        assert "git push" not in error, "no push command for a commit that was undone: %r" % error
        assert "  " not in error and "): " not in error.replace("(no message)", ""), "an empty reason reads as such: %r" % error
        assert tp.git(target, "diff", "--cached", "--name-only") == "", "nothing stays staged"
        assert subprocess.run([resolve_binary("git"), "-C", str(target), "rev-parse", "-q", "--verify", "HEAD"],
                              capture_output=True).returncode != 0, "the commit was undone: the empty repository has none"
        assert remote_head(remote) == "", "nothing reached main"
        hook.unlink()
        publish(srv)
    assert remote_head(remote), "publishing works again once the remote accepts the push"


def long_messages_wrap_at_390(root, tmp):
    """Contract (browser QA of the f8d5d84 fix): Git's messages carry long unbroken paths and URLs (a refused push names
    the remote); the notices that show them wrap anywhere, so a 390 px screen never scrolls sideways (it did by 117 px)."""
    page = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", page)
    assert any(re.search(r"(^|[\s,])\.notice\s*$", sel.strip()) and re.search(r"overflow-wrap:\s*anywhere", body)
               for sel, body in rules), "the .notice rule wraps long words"


def schedule_is_never_guessed(root, tmp):
    """Evidence (round r1): the form defaulted to today, and saving it untouched froze a next-day hackathon. The fields
    start empty, a date is required, and a freeze in the past or within the hour asks first (preview writes nothing)."""
    page = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")
    assert not re.search(r'id="schedule-(start|end)"[^>]*\bvalue=', page), "no preset date in the markup"
    assert not re.search(r'el\("schedule-(start|end)"\)\.value\s*=\s*localInput', page), "no date is made up by the script"
    assert "Choose the start and end dates of the event." in page, "saving without a date says so"
    assert "That freeze is in the past or less than an hour away. Save it anyway?" in page, "a near freeze asks first"
    es = catalog_of_page(root)
    for line in ("Choose the start and end dates of the event.",
                 "That freeze is in the past or less than an hour away. Save it anyway?"):
        assert line in es, "Spanish for %r" % line
    target, _ = installed(root, tmp)
    now = datetime.datetime.fromtimestamp(time.time(), datetime.timezone.utc).replace(tzinfo=None)

    def fmt(moment):
        return moment.strftime("%Y-%m-%d %H:%M")

    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        before = (target / ".uak/PROJECT.md").read_bytes()
        assert tp.post(srv, "/api/schedule", {"start": "", "end": "", "zone": "UTC"})[0] == 400, "an empty date is refused"
        assert tp.post(srv, "/api/schedule", {"start": "2026-11-12 10:00", "end": "2026-11-12 13:00", "zone": "UTC",
                                              "preview": "yes"})[0] == 400, "preview is a boolean"

        def preview(start, end):
            status, body = tp.post(srv, "/api/schedule", {"start": fmt(start), "end": fmt(end), "zone": "UTC",
                                                          "preview": True})
            assert status == 200, body
            return body

        past = preview(now - datetime.timedelta(days=2), now - datetime.timedelta(days=2) + datetime.timedelta(hours=3))
        assert past["soon"] is True and past["epoch"] < now.timestamp() + 3600, "a past freeze asks first: %r" % past
        near = preview(now, now + datetime.timedelta(minutes=20))
        assert near["soon"] is True, "a freeze within the hour asks first: %r" % near
        later = preview(now + datetime.timedelta(days=1), now + datetime.timedelta(days=1, hours=5))
        assert later["soon"] is False, "a freeze tomorrow does not ask: %r" % later
        assert (target / ".uak/PROJECT.md").read_bytes() == before, "a preview writes nothing"


# --- UI-009 (absorbs UI-011): network Git outside the server lock, and a way out of unrelated history -------------


class GatedPlanner(tp.FakePlanner):
    """Holds the first `ls-remote` until the test opens the gate (at most 6 s); records every network call."""

    def __init__(self):
        super().__init__()
        self.gate, self.entered, self.net = threading.Event(), threading.Event(), []

    def __call__(self, command, cwd=None, timeout=120, **kwargs):
        if "ls-remote" in command or "fetch" in command or "push" in command:
            self.net.append({"argv": list(command), "timeout": timeout})
        if "ls-remote" in command and not self.entered.is_set():
            self.entered.set()
            self.gate.wait(6)
        return super().__call__(command, cwd=cwd, timeout=timeout, **kwargs)


def timed_status(srv):
    """One status request (not a mean), timed."""
    started = time.monotonic()
    status, body = tp.get(srv, "/api/status")
    return status, body, time.monotonic() - started


def in_thread(call):
    box = {}
    thread = threading.Thread(target=lambda: box.update(result=call()), daemon=True)
    thread.start()
    return thread, box


def status_answers_during_network_git(root, tmp):
    target, _ = installed(root, tmp)
    planner = GatedPlanner()
    with tp.live(target, planner) as srv:
        ready_to_publish(srv, target)
        thread, box = in_thread(lambda: tp.get(srv, "/api/publish-kit"))
        assert planner.entered.wait(10), "the preview reached ls-remote"
        status, body, seconds = timed_status(srv)
        assert status == 200 and seconds < 1.0, "status answers while Git talks to the remote: %.2f s" % seconds
        assert body.get("phase") not in wizard.MODULE.BUSY, body.get("phase")
        planner.gate.set()
        thread.join(15)
        assert box["result"][0] == 200, box
    for net in planner.net:
        assert net["timeout"] <= 30, net
    # The reviewer registration's own read of claims, then a tool probe: status never waits; POSTs queue.
    import test_setup_team as team_tests
    team_tests.MODULE = wizard.MODULE
    project, _ = team_tests.ready_project(root, team_tests.fresh(tmp, "team"))
    team = team_tests.Team()
    team.probe_gate = threading.Event()
    with tp.live(project, team) as srv:
        team.srv = srv
        team_tests.ready(srv, project)
        thread, box = in_thread(lambda: tp.get(srv, "/api/team"))
        assert team.probe_entered.wait(10), "the tool probe started"
        status, _, seconds = timed_status(srv)
        assert status == 200 and seconds < 1.0, "status answers during a tool probe: %.2f s" % seconds
        team.probe_gate.set()
        thread.join(15)
        assert box["result"][0] == 200, box
        team.net_entered.clear()
        team.net_gate = threading.Event()
        team.gate = threading.Event()  # the registration worker stays alive until released
        reviewer, reviewer_box = in_thread(lambda: tp.post(srv, "/api/team/reviewer", {"confirm": "ana-r"}))
        assert team.net_entered.wait(10), "the registration reads claims first"
        status, _, seconds = timed_status(srv)
        assert status == 200 and seconds < 1.0, "status answers during the claims read: %.2f s" % seconds
        human, human_box = in_thread(lambda: tp.post(srv, "/api/human", {"name": "ana"}))
        queued, queued_box = in_thread(lambda: tp.get(srv, "/api/team"))
        time.sleep(0.5)
        assert human.is_alive(), "a POST waits for the slow lane instead of racing it"
        team.net_gate.set()
        reviewer.join(15)
        human.join(15)
        queued.join(15)
        assert reviewer_box["result"][0] == 202, reviewer_box
        assert human_box["result"][0] in (200, 409), human_box  # 409: the registration it waited for is running
        assert queued_box["result"][0] in (200, 409), queued_box
        if queued_box["result"][0] == 200:
            assert queued_box["result"][1].get("stale") is True, "while the engine runs, the last view is shown"
        assert tp.get(srv, "/api/publish-kit")[0] == 409, "no fetch while the engine runs"
        status, plan = tp.get(srv, "/api/plan")
        assert status == 200, plan
        assert not [n for n in team.net if n["beside_worker"]], \
            "no request fetched while the worker ran: %r" % [n["argv"] for n in team.net if n["beside_worker"]]
        team.gate.set()
        tp.wait_idle(srv)
    for net in team.net:
        assert net["timeout"] <= 30, net


def bash_line(line, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    return subprocess.run([resolve_binary("bash"), "-c", line], cwd=str(cwd), env=env, capture_output=True, text=True,
                          timeout=120)


def remote_commit(remote, tmp, files, label):
    """Someone else creates the remote's own first commit (a README or .gitignore made on GitHub)."""
    clone = tmp / ("clone " + label)
    tp.git(tmp, "clone", "-q", str(remote), str(clone))
    for rel, text in files.items():
        (clone / rel).parent.mkdir(parents=True, exist_ok=True)
        (clone / rel).write_text(text, encoding="utf-8")
    tp.git(clone, "add", "-A")
    tp.git(clone, "-c", "user.name=x", "-c", "user.email=x@example.invalid", "commit", "-q", "-m", "on GitHub")
    tp.git(clone, "push", "-q", "origin", "HEAD:main")
    return tp.git(clone, "rev-parse", "HEAD")


def way_out(srv):
    status, body = tp.get(srv, "/api/publish-kit")
    assert status == 400 and body.get("way_out"), "the preview explains the way out: %r" % body
    assert "git pull" in body["error"], "the message names git pull (amendment 1): %r" % body["error"]
    status, posted = tp.post(srv, "/api/publish-kit", {"digest": "0" * 64})
    assert status == 400 and posted.get("way_out") == body["way_out"], posted
    import test_setup_team as team_tests
    team_tests.spanish_for(body)
    for word in ("--force", " -f", "reset", "clean", "rm ", "checkout --", "branch -D", "+refs", "push"):
        assert word not in body["way_out"]["command"], "no destructive word in %r" % body["way_out"]["command"]
    return body["way_out"]


def q(path):
    return "'" + Path(str(path)).as_posix().replace("'", "'\\''") + "'"


def unrelated_remote_history_has_a_way_out(root, tmp):
    # (a) the round-4 incident: an unborn folder, GitHub made .gitignore and README.md
    (tmp / "a").mkdir()
    target, remote = installed(root, tmp / "a")
    (target / ".gitignore").write_text("mine\n", encoding="utf-8")
    theirs = remote_commit(remote, tmp / "a", {".gitignore": "remote\n", "README.md": "# made on GitHub\n"}, "a")
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        out = way_out(srv)
        home = Path(os.path.realpath(str(target)))
        assert out["command"] == ("cd %s && test ! -e '.gitignore.mine' && test ! -L '.gitignore.mine' && "
                                  "mv -- '.gitignore' '.gitignore.mine' && git pull --no-rebase --no-edit "
                                  "--allow-unrelated-histories origin main" % q(home)), out["command"]
        assert out["renamed"] == [".gitignore"], out
        assert any("new empty repository" in s for s in out["steps"]), out["steps"]
        assert any(".gitignore.mine" in s for s in out["steps"]), out["steps"]
        done = bash_line(out["command"], tmp)
        assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
        assert (target / ".gitignore.mine").read_text(encoding="utf-8") == "mine\n"
        assert (target / ".gitignore").read_text(encoding="utf-8") == "remote\n"
        assert tp.git(target, "rev-parse", "HEAD") == theirs
        publish(srv)
    assert tp.git(target, "rev-parse", "HEAD^") == theirs and remote_head(remote) == tp.git(target, "rev-parse", "HEAD"), \
        "the kit is published on top of the remote's commit"
    # (b) local commits with no common ancestor: the plain pull, two roots after it
    (tmp / "b").mkdir()
    target, remote = installed(root, tmp / "b")
    tp.git(target, "add", "AGENTS.md")
    tp.git(target, "commit", "-q", "-m", "my own start")
    remote_commit(remote, tmp / "b", {"README.md": "# made on GitHub\n"}, "b")
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        out = way_out(srv)
    home = Path(os.path.realpath(str(target)))
    assert out["command"] == ("cd %s && git pull --no-rebase --no-edit --allow-unrelated-histories origin main" % q(home)), out
    done = bash_line(out["command"], tmp)
    assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
    assert len(tp.git(target, "rev-list", "--max-parents=0", "HEAD").split()) == 2, "both histories are kept"
    # (c) and amendment 8: names it cannot quote, a folder against a file, a .mine already there: no command, no change
    cases = {"quote": ({"a'b": "remote\n"}, {"a'b": "mine\n"}),
             "folder": ({"docs": "remote file\n"}, {"docs/note.md": "mine\n"}),
             "mine": ({".gitignore": "remote\n"}, {".gitignore": "mine\n", ".gitignore.mine": "older\n"})}
    for label, (remote_files_, local) in sorted(cases.items()):
        (tmp / label).mkdir()
        target, remote = installed(root, tmp / label)
        for rel, text in local.items():
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            (target / rel).write_text(text, encoding="utf-8")
        remote_commit(remote, tmp / label, remote_files_, label)
        with tp.live(target, tp.FakePlanner()) as srv:
            ready_to_publish(srv, target)
            out = way_out(srv)
        assert out["command"] == "", "%s: no command it cannot make safe: %r" % (label, out)
        assert any("new empty repository" in s for s in out["steps"]), out["steps"]
        for rel, text in local.items():
            assert (target / rel).read_text(encoding="utf-8") == text, "%s: %s untouched" % (label, rel)
    # an ignored file the remote also has: renamed, never silently overwritten by the merge
    (tmp / "ignored").mkdir()
    target, remote = installed(root, tmp / "ignored")
    (target / ".gitignore").write_text("build/\n", encoding="utf-8")
    (target / "build").mkdir()
    (target / "build/out.txt").write_text("my build\n", encoding="utf-8")
    remote_commit(remote, tmp / "ignored", {"build/out.txt": "their build\n"}, "ignored")
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        out = way_out(srv)
    assert "build/out.txt" in out["renamed"], out
    done = bash_line(out["command"], tmp)
    assert done.returncode == 0, done.stdout[-600:] + done.stderr[-600:]
    assert (target / "build/out.txt.mine").read_text(encoding="utf-8") == "my build\n", "the ignored file is kept"
    # (e) simply behind (the local branch has the remote's older commit): today's git pull advice, no way out
    (tmp / "e").mkdir()
    target, remote = installed(root, tmp / "e")
    tp.git(target, "add", "AGENTS.md")
    tp.git(target, "commit", "-q", "-m", "first")
    tp.git(target, "push", "-q", "origin", "main")
    remote_commit(remote, tmp / "e", {"README.md": "newer\n"}, "e")
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        status, body = tp.get(srv, "/api/publish-kit")
    assert status == 400 and "git pull" in body.get("error", "") and not body.get("way_out"), body


def way_out_with_tracked_modified_gitignore(root, tmp):
    """Windows QA of 993e112 (notes/handoff:qa/windows/UI-009-1549.md, b): a project with commits whose tracked
    .gitignore the installer changed. The offered `git pull --allow-unrelated-histories` aborted ("Your local changes
    ... would be overwritten by merge"). Now: no pull while a tracked file the remote also has is uncommitted; a step
    says to commit it; once committed, the offered command works and the conflict is explained."""
    target, remote = installed(root, tmp)
    (target / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    tp.git(target, "add", ".gitignore", "AGENTS.md")
    tp.git(target, "commit", "-q", "-m", "my project")
    (target / ".gitignore").write_text("node_modules/\n# uak\n.uak-env\n", encoding="utf-8")  # the installer's lines
    remote_commit(remote, tmp, {".gitignore": "dist/\n", "README.md": "# on GitHub\n"}, "gh")
    before = (target / ".gitignore").read_bytes()
    with tp.live(target, tp.FakePlanner()) as srv:
        ready_to_publish(srv, target)
        out = way_out(srv)
        assert out["command"] == "", "no pull over an uncommitted tracked file: %r" % out
        assert any("Commit them first" in s and ".gitignore" in s for s in out["steps"]), out["steps"]
        assert any("new empty repository" in s for s in out["steps"]), out["steps"]
        assert (target / ".gitignore").read_bytes() == before
        tp.git(target, "add", ".gitignore")
        tp.git(target, "commit", "-q", "-m", "Keep my changes")
        out = way_out(srv)
    assert out["command"].endswith("git pull --no-rebase --no-edit --allow-unrelated-histories origin main"), out
    assert any("conflict in them" in s and ".gitignore" in s for s in out["steps"]), out["steps"]
    done = bash_line(out["command"], tmp)
    output = done.stdout + done.stderr
    assert "would be overwritten" not in output, "the offered command gets past the merge: %s" % output[-600:]
    assert "CONFLICT" in output and ".gitignore" in output, "the conflict the step explains: %s" % output[-600:]
    assert b"node_modules/" in (target / ".gitignore").read_bytes(), "nothing of yours is lost"


TESTS = [schedule_form_writes_freeze_epoch, publish_kit_excludes_unapproved_plan_files,
         publish_kit_pushes_only_the_verified_commit, terminal_step_is_shown_with_its_command,
         planning_waits_for_the_kit_on_main, lint_failure_reason_reaches_the_page,
         plan_can_be_rechecked_without_the_planner, human_name_is_asked_once,
         publish_never_includes_files_the_installer_did_not_place, publish_verifies_the_whole_committed_tree,
         schedule_never_follows_links, publish_ignores_personal_files_present_before_install,
         failed_commit_leaves_index_and_refs_as_before, refused_push_says_nothing_was_published,
         long_messages_wrap_at_390, schedule_is_never_guessed, status_answers_during_network_git,
         unrelated_remote_history_has_a_way_out, way_out_with_tracked_modified_gitignore]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("prepare_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("prepare_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-prepare-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("SETUP_PREPARE_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
