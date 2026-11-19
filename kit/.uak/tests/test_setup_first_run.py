#!/usr/bin/env python3
"""UI-024: the team step leads a beginner through the first run. Real HTTP, real Git with a local bare remote, the
engine's real register-reviewer; `uak start` is canned (and can hang or time out on demand); the page's own code runs
in Node over a fake DOM of setup.html (test_setup_feedback), or is read only without Node.
Evidence (QA rounds 2026-11-14, notes/handoff:qa/rounds-2026-11-14): A-F6 Claude Code's trust dialog starts on
"No, exit" and prints an English "Ignoring 51 permissions.allow entries" warning the page never mentioned; D-3.2 and
A-F11 launch commands copyable before the reviewer was registered; A-F7 "Check what's next" emptied and redrew the list
(the button jumped 1,014 px); B-10 a hanging remote made the check take 75 s with every view answering 409; A-F15 one
blocked reason shown 3 times; A-F16 two 1-5 numberings; D-10.1 the main button below the fold; D-6.1 buttons natively
disabled during an operation with no reason; D-7.1 a planner rule break read "Done" with a green lint box; A-F19 the
second person was never addressed. Contract: notes/handoff:UI-024-contract.md."""
import argparse
import ast
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import test_setup_feedback as tf
import test_setup_planning as tp
import test_setup_team as team
import test_setup_trust as trust
import test_setup_wizard as wizard
from test_hack import resolve_binary

MODULE = None


class CheckTeam(team.Team):
    """team.Team whose `uak start` can hang (check_gate) or end as a timeout (check_code = 124), and records how
    setup ran it (timeout, process group, extra environment)."""

    def __init__(self, ready=team.READY_OUT):
        super().__init__(ready)
        self.check_gate, self.check_entered, self.check_code, self.starts = None, threading.Event(), None, []

    def __call__(self, command, cwd=None, timeout=120, group=False, env=None, **kwargs):
        if len(command) >= 3 and command[-1] == "start" and str(command[-2]).endswith("uak"):
            self.starts.append({"timeout": timeout, "group": group, "env": dict(env or {})})
            self.check_entered.set()
            if self.check_gate:
                self.check_gate.wait(30)
            if self.check_code is not None:
                return subprocess.CompletedProcess(command, self.check_code, "", "The run took too long and was stopped.")
        return super().__call__(command, cwd=cwd, timeout=timeout, group=group, env=env, **kwargs)


def raw(srv, path):
    status, body, _ = wizard.request(srv, "GET", path)
    return status, body


def timed_get(srv, path, limit=3.0):
    started = time.monotonic()
    status, body = raw(srv, path)
    took = time.monotonic() - started
    assert took < limit, "%s answered in %.1f s during a check (limit %.0f s)" % (path, took, limit)
    return status, json.loads(body or b"{}")


def config_file(tmp, projects):
    """A Claude Code config (CLAUDE_CONFIG_DIR) with private values around the trust flags."""
    folder = tmp / "cfg"
    folder.mkdir(exist_ok=True)
    path = folder / ".claude.json"
    data = {"projects": {k: {"hasTrustDialogAccepted": v, "mcpServers": {"x": {"env": {"TOKEN": "tok-SECRET-123"}}}}
                         for k, v in projects.items()},
            "oauthAccount": {"emailAddress": "ana@example.invalid"}}
    path.write_text(json.dumps(data), encoding="utf-8")
    os.environ["CLAUDE_CONFIG_DIR"] = str(folder)
    return path


def posix_real(path):
    return Path(os.path.realpath(str(path))).as_posix()


def catalog():
    return trust.catalog(ROOT)


def html():
    return tf.page()


def code():
    return tf.script(html())


ROOT = None


# --- trust_step_is_explicit -------------------------------------------------------------------------------------------


def trust_step_is_explicit(root, tmp):
    target, _ = team.ready_project(root, tmp)
    path = config_file(tmp, {posix_real(target): True})
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    runner = team.Team()
    with tp.live(target, runner) as srv:
        runner.srv = srv
        team.ready(srv, target)
        assert team.register(srv)[0] == 202
        for _ in range(3):
            status, body = raw(srv, "/api/team")
            assert status == 200, body
            for secret in (b"tok-SECRET-123", b"example.invalid", b".claude.json"):
                assert secret not in body, "the team view carries nothing of Claude's config: %r" % secret
        view = json.loads(body)
        assert view.get("trust") == {"project": True, "worktree": False}, \
            "Claude Code implements here: the page knows whether it trusts each folder: %r" % view.get("trust")
        for page in ("/api/status", "/api/plan"):
            status, body = raw(srv, page)
            assert not [s for s in (b"tok-SECRET-123", b"example.invalid", b".claude.json") if s in body], page
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before, "Claude's config is never written"
        assert os.listdir(str(path.parent)) == [".claude.json"], "no lock or temp file beside it"

        # A parent of the worktree counts (Claude Code walks up); the cache notices the change.
        config_file(tmp, {posix_real(target) + "-wt": True})
        view = tp.get(srv, "/api/team")[1]
        assert view["trust"]["worktree"] is True, "a trusted <project>-wt covers the task folder: %r" % view["trust"]
        path.write_text("{not json", encoding="utf-8")
        status, view = tp.get(srv, "/api/team")
        assert status == 200 and view["trust"] == {"project": None, "worktree": None}, view.get("trust")
        path.unlink()
        status, view = tp.get(srv, "/api/team")
        assert status == 200 and view["trust"] == {"project": None, "worktree": None}, view.get("trust")

        config_file(tmp, {posix_real(target): True})
        status, plan = tp.get(srv, "/api/plan")
        assert status == 200 and plan.get("trust") is True, "the planning step knows it too: %r" % plan.get("trust")
        status, body = tp.post(srv, "/api/team/roles", {"implement": "codex", "review": "codex"})
        assert status == 200, body
        assert "trust" not in tp.get(srv, "/api/team")[1], "Codex only: no Claude trust line"

    page, script = html(), code()
    es = catalog()
    for ident in ("team-implement", "team-review", "plan-trust"):
        assert 'class="trust-help"' in trust.section(page, ident), "#%s has the trust help block" % ident
    line = tf.page_function(script, "trustLine")
    for word in ("↓", "Enter", "No, exit", "Yes, proceed", "permissions.allow"):
        assert word in line, "the trust help names %r: %s" % (word, line[:300])
    keys = [k for k in es if "No, exit" in k or "permissions.allow" in k]
    assert len(keys) >= 3, "the keyboard lines and the warning line have Spanish: %r" % keys
    for key in keys:
        if "Yes, proceed" in key:
            assert "↓" in es[key] and "Enter" in es[key] and "«Yes, proceed»" in es[key], es[key]
        if key.startswith("If you pressed Enter"):
            assert "«No, exit»" in es[key], es[key]
    for text in ("Claude Code already trusts this folder.",
                 "Claude Code does not trust this folder yet, so it will ask first.",
                 "Setup could not read whether Claude Code trusts this folder. If it asks, answer as below.",
                 "Then approve this project's uak server (MCP).", "Check again"):
        assert text in es, "Spanish for %r" % text
    assert re.search(r'el\("plan-trust"\)\.hidden = [^;]*selectedPlanner\(\) !== "claude"', script), \
        "the planning trust note shows only when Claude Code drafts the plan"

    # Read-only by construction: only open(…, "rb"), nothing that writes, renames or touches a file.
    tree = ast.parse(textwrap.dedent(inspect.getsource(MODULE.claude_trust)))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        owner = getattr(getattr(node.func, "value", None), "id", "")
        assert name not in ("write", "write_text", "write_bytes", "rename", "unlink", "utime", "touch", "mkdir",
                            "chmod", "truncate"), "claude_trust calls %s" % name
        assert not (owner == "os" and name in ("replace", "remove")), "claude_trust calls os.%s" % name
        if name == "open":
            modes = [a.value for a in node.args[1:] if isinstance(a, ast.Constant)]
            modes += [k.value.value for k in node.keywords if k.arg == "mode" and isinstance(k.value, ast.Constant)]
            assert modes == ["rb"], "claude_trust opens its file read-only: %r" % modes

    out = tf.run_page("""
        var box = el("team-implement-trust");
        trustLine(box, false);
        var off = {text: box.textContent, en: box.querySelectorAll("[lang]").length, kbd: box.querySelectorAll("kbd").length};
        trustLine(box, true);
        var on = {text: box.textContent, hidden: box.hidden};
        trustLine(box, null);
        var unknown = box.textContent;
        trustLine(box, undefined);
        return {off: off, on: on, unknown: unknown, gone: box.hidden};
    """, language="es")
    if out is not None:
        assert "↓" in out["off"]["text"] and "«No, exit»" in out["off"]["text"] and "«Yes, proceed»" in out["off"]["text"], out
        assert "Ignoring 51 permissions.allow" in out["off"]["text"], out
        assert out["off"]["en"] >= 2 and out["off"]["kbd"] >= 2, "dialog labels stay English, keys are <kbd>: %r" % out
        assert out["on"]["text"].startswith("✓") and "↓" not in out["on"]["text"] and not out["on"]["hidden"], out
        assert es["Claude Code already trusts this folder."] in out["on"]["text"], out
        assert "↓" in out["unknown"] and out["gone"], out


# --- commands_wait_for_the_reviewer -----------------------------------------------------------------------------------


def commands_wait_for_the_reviewer(root, tmp):
    target, _ = team.ready_project(root, tmp)
    (target / "IDEA.md").write_text("# Idea\n\n- Team size: 2 people\n", encoding="utf-8")
    runner = team.Team()
    with tp.live(target, runner) as srv:
        runner.srv = srv
        team.ready(srv, target)
        status, body = raw(srv, "/api/team")
        view = json.loads(body)
        assert status == 200 and view.get("commands") == [], "no command before the reviewer: %r" % view.get("commands")
        locked = view.get("locked") or {}
        assert "ana-r" in locked.get("reason", "") and locked.get("target") == "team-register", view
        assert [w["id"] for w in view.get("waiting") or []] == ["implement", "review"], view.get("waiting")
        assert b"wt new" not in body and b"UAK_AGENT=" not in body, "nothing copyable leaks: %r" % body[:400]
        assert view.get("note") != locked["reason"], "the reason is shown once"
        assert team.translated(locked["reason"]), "the lock has Spanish: %r" % locked["reason"]
        assert view.get("people") == 2, "IDEA.md says two people: %r" % view.get("people")
        assert team.register(srv)[0] == 202
        view = tp.get(srv, "/api/team")[1]
        assert set(team.by_id(view)) == {"implement", "review"} and "locked" not in view, view
        team.retire(target, "ana-r", "ana")
        team.check(srv)
        view = tp.get(srv, "/api/team")[1]
        assert view["commands"] == [] and view["locked"]["reason"] == view["registered"]["message"], view
    page = html()
    block = trust.section(page, "team-two-people")
    words = " ".join(trust.visible(block))
    assert "own computer" in words, words
    es = catalog()
    missing = [t for t in trust.visible(block) if t not in es]
    assert not missing, "the two-person note has Spanish: %r" % missing
    team_step = trust.section(page, "team-step")
    assert team_step.index('id="team-two-people"') < team_step.index('id="team-reviewer"'), "first in the team step"
    out = tf.run_page("""
        function shown(registered) {
          checksKey = "";
          drawChecks({ready: true, guidance: {commands: ["bash .uak/bin/wt new APP-001"]},
                      reviewer: {registered: registered}, checks: []});
          return el("checks").querySelectorAll("code").filter(function (c) {
            return !c.hidden && c.textContent.indexOf("wt new") >= 0; }).length;
        }
        return {before: shown(false), text: el("checks").textContent, after: shown(true)};
    """)
    if out is not None:
        assert out["before"] == 0 and out["after"] == 1, "the bare claim line waits for the reviewer: %r" % out
        assert "register your reviewer" in out["text"], out


# --- check_does_not_jump ----------------------------------------------------------------------------------------------


def check_does_not_jump(root, tmp):
    target, _ = team.ready_project(root, tmp)
    runner = CheckTeam()
    with tp.live(target, runner) as srv:
        runner.srv = srv
        team.ready(srv, target)
        first = tp.get(srv, "/api/status")[1]["checks"]
        assert len(first) == 2, first
        runner.check_gate = threading.Event()
        runner.check_entered.clear()
        try:
            assert tp.post(srv, "/api/check", {})[0] == 202
            assert runner.check_entered.wait(10)
            state = tp.get(srv, "/api/status")[1]
            assert state["phase"] == "checking" and state.get("checks") == first and state.get("checks_stale") is True, \
                "the last result stays (dimmed) while a check runs: %r" % {k: state.get(k) for k in ("phase", "checks", "checks_stale")}
        finally:
            runner.check_gate.set()
        tp.wait_idle(srv)
        state = tp.get(srv, "/api/status")[1]
        assert state.get("checks_stale") is False and len(state["checks"]) == 2, state

    script = code()
    reasons = re.search(r"var BUSY_REASON = (\{[\s\S]*?\});", tf.block(script))
    assert reasons, "the feedback block has BUSY_REASON"
    busy = json.loads(re.sub(r"(\{|,)\s*([a-z][\w-]*):", r'\1"\2":', re.sub(r",\s*\}", "}", reasons.group(1))))
    assert set(busy) == {"installing", "checking", "planning", "approving", "publishing", "registering"}, busy
    es = catalog()
    assert all(es.get(text, "").startswith("Espera: ") for text in busy.values()), "six Spanish reasons"
    left = re.findall(r'el\("(check|next-check|change-project|repair|save|human-save|schedule-save|publish-preview|'
                      r'publish-kit|idea-save|plan-create|plan-change|plan-recheck|team-register|team-retry|team-check|'
                      r'refresh-dashboard)"\)\.disabled = (?:busy|blocked|operationBusy\(\))', script)
    assert not left, "busy buttons say why instead of a native disable: %r" % left
    assert not re.search(r"button\.disabled = busy;", script), "the install and form buttons say why too"
    assert "Your last result stays below until the new one arrives." in es

    page = html()
    assert 'id="plan-onmain-note"' not in page, "the publish-first reason has one place: its button's line"
    blocks = tf.page_function(script, "planBlock") + tf.page_function(script, "nameBlock")
    markup = page[:page.index('<script nonce="__NONCE__">')]
    notices = re.findall(r'<(?:p|div)[^>]*class="notice[^"]*"[^>]*>[\s\S]*?</(?:p|div)>', markup)
    for reason in re.findall(r'text: "([^"]+)"', blocks):
        assert not [n for n in notices if reason in " ".join(" ".join(trust.visible(n)).split())], \
            "a notice repeats %r" % reason
    assert not re.search(r'<span class="step-number">[1-5]<', page), "the wizard rail has no second 1-5 numbering"
    assert any(re.search(r"body\.installed \.sidebar", s) and re.search(r"display:\s*none", b) for s, b in tf.rules(page)), \
        "after install the rail is hidden"
    welcome = trust.section(page, "welcome")
    intros = [m.start() for m in re.finditer(r'class="intro"', welcome)]
    assert len(intros) >= 2 and welcome.index('id="begin"') < min(welcome.index('class="benefit"'), intros[1]), \
        "Set up my project comes right after the first intro"

    out = tf.run_page("""
        var data = {checks: [{state: "ok", text: "1. kit"}, {state: "ok", text: "2. plan"}]}, list = el("checks");
        drawChecks(data);
        var count = list.replaced;
        drawChecks({phase: "checking", checks: data.checks});
        drawChecks({phase: "checking", checks: []});
        var during = {replaced: list.replaced - count, rows: list.children.length, stale: list.classList.contains("stale"),
                      busy: list.getAttribute("aria-busy")};
        drawChecks({checks: data.checks.slice(0, 1)});
        var after = {replaced: list.replaced - count, rows: list.children.length, stale: list.classList.contains("stale"),
                     busy: list.getAttribute("aria-busy")};
        var save = el("save");
        setWaiting(save, "checking");
        var waiting = {aria: save.getAttribute("aria-disabled"), native: save.disabled};
        fire(save, "click");
        waiting.toast = el("toast-text").textContent;
        setWaiting(save, "");
        waiting.free = save.getAttribute("aria-disabled");
        return {during: during, after: after, waiting: waiting};
    """)
    if out is not None:
        assert out["during"] == {"replaced": 0, "rows": 2, "stale": True, "busy": "true"}, out
        assert out["after"] == {"replaced": 1, "rows": 1, "stale": False, "busy": None}, out
        w = out["waiting"]
        assert w["aria"] == "true" and not w["native"] and w["toast"] == busy["checking"] and w["free"] is None, w


# --- views_answer_during_a_check --------------------------------------------------------------------------------------


def views_answer_during_a_check(root, tmp):
    target, _ = team.ready_project(root, tmp)
    runner = CheckTeam()
    with tp.live(target, runner) as srv:
        runner.srv = srv
        team.ready(srv, target)
        assert team.register(srv)[0] == 202
        assert tp.get(srv, "/api/dashboard")[0] == 200
        assert tp.get(srv, "/api/team")[0] == 200
        runner.check_gate = threading.Event()
        runner.check_entered.clear()
        try:
            assert tp.post(srv, "/api/check", {})[0] == 202
            assert runner.check_entered.wait(10)
            status, dash = timed_get(srv, "/api/dashboard")
            assert status == 200 and dash.get("stale") is True, "the dashboard answers during a check: %s %r" % (status, dash)
            status, view = timed_get(srv, "/api/team")
            assert status == 200 and view.get("stale") is True, (status, view)
            assert timed_get(srv, "/api/plan")[0] == 200
            assert timed_get(srv, "/api/status")[0] == 200
        finally:
            runner.check_gate.set()
        tp.wait_idle(srv)
        call = runner.starts[-1]
        assert call["timeout"] <= 45 and call["group"] is True, "the check is bounded and stops its tree: %r" % call
        assert call["env"].get("GIT_HTTP_LOW_SPEED_LIMIT") == "1000" and call["env"].get("GIT_HTTP_LOW_SPEED_TIME") == "10", call

        before = tp.get(srv, "/api/status")[1]["checks"]
        runner.check_code = 124
        team.check(srv)
        state = tp.get(srv, "/api/status")[1]
        assert "45 s" in state.get("error", "") and "origin" in state["error"], state.get("error")
        assert state["checks"] == before and state["phase"] == "setup", state
        assert team.translated(state["error"]), "the timeout has Spanish: %r" % state["error"]
        runner.check_code = None

    second, _ = team.ready_project(root, team.fresh(tmp, "second"), name="second project")
    runner = CheckTeam()
    with tp.live(second, runner) as srv:
        runner.srv = srv
        assert tp.post(srv, "/api/inspect", {"target": str(second)})[0] == 200
        assert tp.post(srv, "/api/human", {"name": "ana"})[0] == 200
        runner.check_gate = threading.Event()
        try:
            assert tp.post(srv, "/api/check", {})[0] == 202
            assert runner.check_entered.wait(10)
            status, view = timed_get(srv, "/api/team")
            assert status == 200 and view.get("checking") is True and view.get("commands") == [], (status, view)
            assert team.translated(view.get("note", "")), view.get("note")
            status, dash = timed_get(srv, "/api/dashboard")
            assert status == 200 and dash.get("stale") is True and dash.get("connection") == "checking", (status, dash)
        finally:
            runner.check_gate.set()
        tp.wait_idle(srv)
        assert not [n for n in runner.net if n["beside_worker"]], "no fetch beside the engine: %r" % runner.net


# --- rule_break_is_not_done -------------------------------------------------------------------------------------------


def bash_line(line, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    return subprocess.run([resolve_binary("bash"), "-c", line], cwd=str(cwd), env=env, capture_output=True, text=True,
                          timeout=120)


def reset(target, tmp, head):
    tp.git(target, "reset", "-q", "--hard", head)
    tp.git(target, "clean", "-qfdx", "-e", "IDEA.md")
    tp.git(target, "config", "core.hooksPath", str(tmp / "no-hooks"))


def rule_break_is_not_done(root, tmp):
    target, _ = tp.project(root, tmp)
    before = tp.git(target, "rev-parse", "HEAD")
    home = team.q(target.resolve())
    with tp.live(target, tp.FakePlanner(misbehave="edit-other")) as srv:
        plan = tp.planned(srv, target)
        state = tp.get(srv, "/api/status")[1]
        assert state.get("outcome") == "problems" and state.get("error") == "" and state.get("problem"), \
            "a rule break is not done: %r" % {k: state.get(k) for k in ("phase", "outcome", "error", "problem")}
        assert team.translated(state["problem"]), state["problem"]
    undo = plan.get("undo") or {}
    assert undo.get("command") == "cd %s && git restore --source=%s --worktree -- 'AGENTS.md'" % (home, before), undo
    assert team.translated(undo.get("text", "")), undo
    done = bash_line(undo["command"], tmp)
    assert done.returncode == 0, done.stderr
    assert tp.git(target, "-c", "core.quotePath=false", "status", "--porcelain", "--", "AGENTS.md") == "", \
        "AGENTS.md is back to its committed content"
    assert (target / ".uak/TASKS.md").read_text(encoding="utf-8") == tp.GOOD_PLAN, "the plan stays"
    reset(target, tmp, before)

    with tp.live(target, tp.FakePlanner(misbehave="approve-and-commit")) as srv:
        plan = tp.planned(srv, target)
    command = (plan.get("undo") or {}).get("command", "")
    assert command.startswith("cd %s && git reset -q %s && git restore --source=%s --worktree -- " % (home, before, before)), command
    assert "'.uak/PROJECT.md'" in command and ".uak/TASKS.md" not in command, command
    done = bash_line(command, tmp)
    assert done.returncode == 0, done.stderr
    assert tp.git(target, "rev-parse", "HEAD") == before, "HEAD is back"
    assert "Backlog-Approved: no" in (target / ".uak/PROJECT.md").read_text(encoding="utf-8")
    reset(target, tmp, before)

    with tp.live(target, tp.FakePlanner(misbehave="git-config")) as srv:
        plan = tp.planned(srv, target)
        status, body = tp.post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
        assert status == 400 and "Undo them with the instruction under Proposed plan" in body.get("error", ""), body
        assert team.translated(body["error"]), body
    undo = plan.get("undo") or {}
    assert undo.get("command") == "" and undo.get("text") == "Undo these changes by hand, then press Create the plan again.", undo
    assert undo["text"] in catalog()
    reset(target, tmp, before)

    script = code()
    draw = tf.page_function(script, "drawPlan")
    for ident in ("plan-lint", "plan-ask"):
        assert re.search(r'el\("%s"\)\.hidden = [^;]*violations\.length' % ident, draw), "%s hides on a rule break" % ident
    box = trust.section(html(), "plan-violations")
    assert "Ask for changes" not in box and "Undo those changes" not in box, box
    assert 'id="plan-undo-command"' in box and 'id="copy-plan-undo"' in box, box
    es = catalog()
    assert es.get("Finished with problems at {time}: {problem}", "").startswith("Terminó con problemas"), "Spanish"
    out = tf.run_page("""
        state = {phase: "planning"};
        drawPhaseButtons({phase: "planned", outcome: "problems",
                          problem: "The planner changed things only you may change."}, "planning");
        var line = el("plan-create-result");
        return {text: line.textContent, error: line.classList.contains("error")};
    """, language="es")
    if out is not None:
        assert out["text"].startswith("Terminó con problemas") and out["error"] and "Listo" not in out["text"], out


TESTS = [trust_step_is_explicit, commands_wait_for_the_reviewer, check_does_not_jump, views_answer_during_a_check,
         rule_break_is_not_done]


def main():
    global MODULE, ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    ROOT = tf.ROOT = root
    for key in [k for k in os.environ if k.startswith("UAK_")]:
        del os.environ[key]  # the remote and base, and who acts, are the fixtures' own
    spec = importlib.util.spec_from_file_location("first_run_setup", root / ".uak/bin/lib/setup.py")
    MODULE = wizard.MODULE = team.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MODULE)
    spec = importlib.util.spec_from_file_location("first_run_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    saved = os.environ.get("CLAUDE_CONFIG_DIR")
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        tmp = Path(tempfile.mkdtemp(prefix="uak-first-run-"))
        # No test ever reads the developer's own ~/.claude.json.
        os.environ["CLAUDE_CONFIG_DIR"] = str(tmp / "no-claude-config")
        started = time.monotonic()
        try:
            test(root, tmp)
            print("PASS %s (%.1fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
        finally:
            if saved is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = saved
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_FIRST_RUN_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
