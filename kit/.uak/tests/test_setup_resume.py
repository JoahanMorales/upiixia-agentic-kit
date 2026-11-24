#!/usr/bin/env python3
"""UI-019: coming back to a project, the setup page restores where you were.
Evidence: Dylan's live run (2026-11-14: "se me borró todo al refrescar", a stuck "Comprobar siguiente paso") and the QA
rounds of the same day (notes/handoff:qa/rounds-2026-11-14, A-F2, A-F3, A-F4, A-F8, A-F11, B-04, B-05, B-14): after a
refresh, a restart or re-picking the project the page landed on Welcome or Prepare with empty forms, offered publishing
and "Create the plan" for an approved plan, forgot the human name (the team step was silently hidden by a 400), and the
old tab after a restart showed a raw "Failed to fetch" while polling forever.
Real HTTP, real Git with a local bare remote, the engine's canned READY line (test_setup_team.Team); the page's own
resume code runs in Node against a fake DOM of setup.html (test_setup_feedback); without Node the sources are read."""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

import test_setup_feedback as tf
import test_setup_planning as tp
import test_setup_team as tt
import test_setup_wizard as wizard

ROOT = None
BEGIN = "// UI-019 resume: begin"
END = "// UI-019 resume: end"
GONE_EN = "Setup has closed: run the command again and open the new link."
GONE_ES = "Setup se cerró: vuelve a ejecutar el comando y abre el nuevo enlace."
FAR_FREEZE = 4102444800


class Recording:
    """The server's operation runner, recording every command it is given."""

    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def __call__(self, command, *args, **kwargs):
        self.calls.append(list(command))
        return self.inner(command, *args, **kwargs)


def block(code):
    assert BEGIN in code and END in code, "the page keeps its resume code between %r and %r" % (BEGIN, END)
    return code[code.index(BEGIN):code.index(END)]


def section(html, ident):
    assert 'id="%s"' % ident in html, "the page has #%s" % ident
    start = html.rindex("<", 0, html.index('id="%s"' % ident))
    tag = re.match(r"<(\w+)", html[start:]).group(1)
    depth = 0
    for m in re.finditer(r"<(/?)%s\b[^>]*>" % tag, html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start:start + m.end()]
    raise AssertionError("unclosed #%s" % ident)


def shim(language):
    """Evaluated before workspace.js: a real in-memory localStorage, a fetch the scenario controls, counted errors."""
    return """
var __store = {"uak-language": %s};
window.localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null; },
  setItem: function (k, v) { __store[k] = String(v); },
  removeItem: function (k) { delete __store[k]; },
};
var __fetchCalls = 0, __errors = 0;
window.__fetch = function () { return Promise.reject(new TypeError("Failed to fetch")); };
window.fetch = function () { __fetchCalls += 1; return window.__fetch.apply(null, arguments); };
window.console = { log: function () {}, warn: function () {}, error: function () { __errors += 1; } };
""" % json.dumps(language)


# The page's state the resume block reads, beside test_setup_feedback.PRELUDE (render is the page's; here a counter).
EXTRA = """
var token = "t", timer = null, dashboardTimer = null, rendered = 0, latestDashboard = null;
function render(data) { rendered += 1; state = data; }
async function flush() { for (var i = 0; i < 40; i++) await Promise.resolve(); }
"""


def run(scenario, language="en"):
    """SCENARIO (an async function body) over the page's api(), UI-018 feedback and UI-019 resume code; None without
    Node."""
    node = shutil.which("node")
    if not node:
        print("  note: no Node.js here, so the page logic is checked by reading it only")
        return None
    html = tf.page()
    code = tf.script(html)
    sources = [shim(language), tf.lib("workspace.js"), tf.PRELUDE, EXTRA]
    sources += [tf.page_function(code, name) for name in ("el", "isBusy", "error", "api", "journeyStep")]
    sources += [tf.block(code), block(code)]
    with tempfile.TemporaryDirectory(prefix="uak-resume-js-") as folder:
        program = Path(folder) / "run.js"
        program.write_text(tf.NODE_PROGRAM, encoding="utf-8")
        done = subprocess.run([node, str(program)], input=json.dumps({"language": language, "sources": sources,
                                                                      "tree": tf.tree(html), "scenario": scenario,
                                                                      "reduced": False}),
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, "the page logic runs: %s" % done.stderr[-2000:]
    return json.loads(done.stdout)


def status(srv):
    return tp.get(srv, "/api/status")[1]


def human_file(target):
    return Path(os.path.realpath(str(target))) / ".git/uak-setup/human.json"


def listing(folder):
    found = {}
    for base, dirs, files in os.walk(str(folder)):
        for name in dirs + files:
            path = os.path.join(base, name)
            found[path] = os.lstat(path).st_mtime_ns if name in files else 0
    return found


def can_link(tmp):
    probe = tmp / "link-probe"
    try:
        probe.symlink_to(tmp)
        probe.unlink()
        return True
    except (OSError, NotImplementedError):
        return False


# --- the five named tests of UI-019 -----------------------------------------------------------------------------------


def restart_lands_on_the_team_step(root, tmp):
    target, remote = tt.ready_project(root, tmp)
    with tp.live(target, tt.Team()) as srv:
        tt.ready_team(srv, target)
        assert tp.get(srv, "/api/team")[0] == 200
    # 1. A real restart: the command a person runs again, on the same project.
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    # UAK-153: the wizard starts only for a person at a terminal (POSIX): stdin is a pty, the output stays captured.
    master, slave = os.openpty() if os.name != "nt" else (None, subprocess.DEVNULL)
    proc = subprocess.Popen([sys.executable, str(root / ".uak/bin/lib/setup.py"), "--no-open", str(target)],
                            cwd=str(tmp), env=env, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    if master is not None:
        os.close(slave)
    try:
        box = {}
        reader = threading.Thread(target=lambda: box.update(lines=[proc.stdout.readline(), proc.stdout.readline()]), daemon=True)
        reader.start()
        reader.join(60)
        # UAK-153: the printed address holds no secret; the page opens from a launcher file with a one-time code.
        box["line"] = (box.get("lines") or [""])[0]
        match = re.search(r"UAK SETUP http://127\.0\.0\.1:(\d+)/\s*$", box.get("line", ""))
        assert match, "setup prints its address: %r" % box
        launcher = re.search(r"Launcher file: (.+\.html)\s*$", box["lines"][1])
        assert launcher, "setup names the launcher file: %r" % box
        code_in = re.search(r"#code=([A-Za-z0-9_-]+)", Path(launcher.group(1)).read_text(encoding="utf-8"))
        assert code_in, "the launcher carries a one-time code"
        server = types.SimpleNamespace(server_port=int(match.group(1)), token="")
        code, body, _ = wizard.request(server, "POST", "/api/session", {"code": code_in.group(1)}, token=False)
        assert code == 200, body
        server.token = json.loads(body)["token"]
        code, body, _ = wizard.request(server, "GET", "/api/status")
        state = json.loads(body)
        assert code == 200, state
        assert state["phase"] != "welcome", "a restart on an installed project skips the welcome screen: %r" % state["phase"]
        assert (state.get("resume") or {}).get("step") == "team", state.get("resume")
        assert state.get("human") == "ana", "the name is remembered for this project: %r" % state.get("human")
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        proc.stdout.close()
        proc.stderr.close()
        if master is not None:
            os.close(master)
    # 2. In process: local Git only, no engine and no network, even with the remote unreachable.
    team = tt.Team()
    runner = Recording(team)
    origin = tp.git(target, "remote", "get-url", "origin")
    tp.git(target, "remote", "set-url", "origin", str(tmp / "missing.git"))
    with tp.live(target, runner) as srv:
        started = time.monotonic()
        srv.open_target()
        took = time.monotonic() - started
        assert took < 5, "restoring the project is local and quick: %.1f s" % took
        assert runner.calls == [] and team.net == [], "nothing ran through the engine or the network: %r" % runner.calls
        state = status(srv)
        assert state["installed"] and state["checked"] is False and state["inspect"] == 1, state
        resume = state["resume"]
        expected = {"step": "team", "plan_approved": True, "kit_on_main": True, "freeze": FAR_FREEZE, "human": True,
                    "source": "local", "installed": True}
        assert {k: resume.get(k) for k in expected} == expected, resume
        assert len(resume.get("base_sha") or "") == 7, resume
        # 3. Without posting the name again, the team step answers once the check is done.
        tp.git(target, "remote", "set-url", "origin", origin)
        assert tp.post(srv, "/api/check", {})[0] == 202
        tp.wait_idle(srv)
        code, view = tp.get(srv, "/api/team")
        assert code == 200, view
        assert view.get("reviewer") == "ana-r" and any(c["id"] == "implement" for c in view.get("commands") or []), view
        # 4. The plan view knows the plan is approved: no "Create the plan" for it.
        code, plan = tp.get(srv, "/api/plan")
        assert code == 200 and plan.get("approved") is True, plan
    # 5. A folder without the kit keeps the welcome screen and is never written.
    plain = wizard.repository(tmp / "plain")
    before = listing(plain)
    with wizard.LiveServer(str(plain)) as srv:
        srv.open_target()
        assert status(srv)["phase"] == "welcome"
    assert listing(plain) == before, "opening setup on a folder without the kit writes nothing"
    # 6. The page lands on the furthest step.
    html = tf.page()
    code = tf.script(html)
    resume_code = block(code)
    boot = code[code.rindex('api("status")'):]
    assert "landing(" in boot, "the first status lands the page through landing()"
    assert "resume" in tf.page_function(code, "journeyStep"), "the journey reads the restored step"
    for name in ("landing", "screenFor", "allowed", "stepsDone", "planningVisible", "shouldAutoCheck", "readSaved", "writeSaved"):
        assert re.search(r"function %s\(" % name, resume_code), "the resume block defines %s()" % name
    out = run("""
        var past = {kit_on_main: true, plan_approved: true};
        return {team: landing({installed: true, human: "ana", phase: "setup", resume: Object.assign({step: "team"}, past)}, {}),
                progress: landing({installed: true, human: "ana", phase: "setup", ready: true, resume: Object.assign({step: "progress"}, past, {claims: 1})}, {}),
                prepare: landing({installed: true, phase: "setup", resume: {step: "prepare"}}, {}),
                welcome: landing({phase: "welcome"}, {}), options: landing({phase: "options"}, {}),
                planning: planningVisible({installed: true, phase: "setup", resume: {plan_approved: true}}),
                open: planningVisible({installed: true, phase: "setup", resume: {plan_approved: false}})};
    """)
    if out is None:
        return
    assert out["team"] == {"screen": "start"} and out["progress"] == {"screen": "dashboard"}, out
    assert out["prepare"] == {"screen": "rules"}, out
    assert out["welcome"] == {"screen": "project"} and out["options"] == {"screen": "project"}, out
    assert out["planning"] is False and out["open"] is True, "an approved plan is not offered again: %r" % out


def refresh_keeps_the_step_and_values(root, tmp):
    target, _ = tt.ready_project(root, tmp)
    with tp.live(target, tt.Team()) as srv:
        tt.ready(srv, target)
        keys = ("target", "human", "ready", "checks", "resume", "inspect", "checked")
        first, second = status(srv), status(srv)
        assert all(k in first for k in keys), "status carries the restore facts: %r" % sorted(first)
        assert {k: first[k] for k in keys} == {k: second[k] for k in keys}, "a reload reads the same state"
        assert first["checked"] is True and first["resume"]["step"] == "team", first
    html = tf.page()
    code = tf.script(html)
    assert "writeSaved(" in tf.page_function(code, "show"), "the active tab is remembered for the next reload"
    for ident in ("name-done", "schedule-done", "publish-done"):
        assert 'id="%s"' % ident in html, "a finished Prepare step has its done line #%s" % ident
    found = tf.rules(html)
    assert any(".prepare-step[data-done]" in s and re.search(r"display:\s*none", b) for s, b in found), \
        "a finished step folds its body"
    es = tf.catalog()
    for text in ("Published on main (commit {sha}).", "Plan approved on main (commit {sha}).", "Freeze set: {when}.",
                 "Done", "Change"):
        assert text in es, "%r has a Spanish translation" % text
    assert es["Published on main (commit {sha})."] == "Publicado en main (commit {sha}).", es.get("Published on main (commit {sha}).")
    tf.layout_is_stable_across_refresh(root, tmp)
    out = run("""
        writeSaved("/p/a", {section: "dashboard", drafts: {"schedule-start": "2026-11-20T10:00"}});
        var a = readSaved("/p/a"), b = readSaved("/p/b");
        var land = landing({installed: true, phase: "setup", resume: {step: "prepare"}}, a);
        function put(v) { __store[savedKey("/p/a")] = typeof v === "string" ? v : JSON.stringify(v); return readSaved("/p/a"); }
        var bad = [put("{nope"), put({v: 2, target: "/p/a", at: Date.now(), section: "setup"}),
                   put({v: 1, target: "/p/a", at: Date.now(), section: "evil"}),
                   put({v: 1, target: "/p/a", at: Date.now() - 8 * 864e5, section: "setup"}),
                   put({v: 1, target: "/p/b", at: Date.now(), section: "setup"})];
        var lost = landing({installed: false, can_repair: true, phase: "error"}, {section: "dashboard"});
        el("human-name").value = "ana";
        el("schedule-start").value = "";
        restoreDrafts({drafts: {"schedule-start": "2026-11-20T10:00", "human-name": "eve"}});
        writeSaved("/p/a", {drafts: {"idea-text": new Array(30001).join("x")}});
        var long = (readSaved("/p/a").drafts || {})["idea-text"].length;
        return {a: {section: a.section, drafts: a.drafts}, b: b, land: land, bad: bad, lost: lost,
                start: el("schedule-start").value, name: el("human-name").value, long: long,
                done: stepsDone({human: "ana", resume: {freeze: 4102444800, kit_on_main: true, plan_approved: true}}),
                unknown: stepsDone({human: "", resume: {freeze: 0, kit_on_main: null, plan_approved: null}})};
    """)
    if out is None:
        return
    assert out["a"] == {"section": "dashboard", "drafts": {"schedule-start": "2026-11-20T10:00"}}, out["a"]
    assert out["b"] == {}, "another project's values never apply: %r" % out["b"]
    assert out["land"] == {"screen": "rules"}, "the step the project's Git shows decides, a saved tab does not override it: %r" % out["land"]
    assert out["bad"] == [{}] * 5, "anything unexpected in storage is ignored: %r" % out["bad"]
    assert out["lost"] == {"screen": "update"}, "a project with a half-installed kit lands on Update"
    assert out["start"] == "2026-11-20T10:00" and out["name"] == "ana", out
    assert out["long"] == 20000, "a draft is capped: %r" % out["long"]
    assert out["done"] == {"name": True, "schedule": True, "publish": True, "plan": True}, out["done"]
    assert out["unknown"] == {"name": False, "schedule": False, "publish": False, "plan": False}, \
        "an unknown fact is never drawn as done: %r" % out["unknown"]


def name_persists_per_project(root, tmp):
    a, _ = tt.ready_project(root, tt.fresh(tmp, "a"), name="project a")
    b, _ = tt.ready_project(root, tt.fresh(tmp, "b"), name="project b")
    c, _ = tt.ready_project(root, tt.fresh(tmp, "c"), name="project c")
    # 1. Saved in the clone's Git folder, never in the project's files.
    with tp.live(a, tt.Team()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(a)})[0] == 200
        code, body = tp.post(srv, "/api/human", {"name": "ana"})
        assert code == 200 and body.get("persisted") is True, body
    saved = human_file(a)
    assert saved.is_file() and json.loads(saved.read_text(encoding="utf-8")) == {"version": 1, "name": "ana"}, saved
    assert "uak-setup" not in tp.git(a, "ls-files") and "uak-setup" not in tp.git(a, "status", "--porcelain", "--ignored")
    # 2. Each project keeps its own name.
    with tp.live(a, tt.Team()) as srv:
        state = tp.post(srv, "/api/inspect", {"target": str(a)})[1]
        assert state.get("human") == "ana" and state.get("human_source") == "project", state
        tp.git(b, "config", "user.name", "Bob")  # UAK-153: the name is the checkout's Git identity
        tp.post(srv, "/api/inspect", {"target": str(b)})
        assert tp.post(srv, "/api/human", {"name": "bob"})[0] == 200
        assert tp.post(srv, "/api/inspect", {"target": str(a)})[1].get("human") == "ana"
        assert tp.post(srv, "/api/inspect", {"target": str(b)})[1].get("human") == "bob"
    with tp.live(b, tt.Team()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(b)})[1].get("human") == "bob"
    # 3. A project without a saved name borrows this session's, without writing it.
    with tp.live(a, tt.Team()) as srv:
        tp.post(srv, "/api/inspect", {"target": str(a)})
        state = tp.post(srv, "/api/inspect", {"target": str(c)})[1]
        assert state.get("human") == "ana" and state.get("human_source") == "session", state
    assert not human_file(c).exists(), "inspecting never writes the name"
    # 4. Safety: links, oversized or malformed files are ignored; roles.json is left alone; worktrees share it.
    outside = tmp / "outside"
    outside.mkdir()
    if can_link(tmp):
        (outside / "eve.json").write_text('{"version": 1, "name": "eve"}\n', encoding="utf-8")
        saved.rename(saved.with_name("human.bak"))
        saved.symlink_to(outside / "eve.json")
        with tp.live(a, tt.Team()) as srv:
            assert tp.post(srv, "/api/inspect", {"target": str(a)})[1].get("human") == "", "a linked file is ignored"
        saved.unlink()
        saved.with_name("human.bak").rename(saved)
        folder = saved.parent
        folder.rename(folder.with_name("uak-setup.bak"))
        folder.symlink_to(outside / "room", target_is_directory=True)
        (outside / "room").mkdir()
        with tp.live(a, tt.Team()) as srv:
            tp.post(srv, "/api/inspect", {"target": str(a)})
            code, body = tp.post(srv, "/api/human", {"name": "ana"})
            assert code == 200 and body.get("persisted") is False, body
            assert body.get("note") and tt.translated(body["note"]), body
            assert status(srv).get("human") == "ana", "the name is kept for this session anyway"
        assert not os.listdir(str(outside / "room")), "nothing is written through a linked folder"
        folder.unlink()
        folder.with_name("uak-setup.bak").rename(folder)
    else:
        print("  note: no symbolic links here, so the link cases are skipped")
    with tp.live(a, tt.Team()) as srv:
        for content in ('{"version": 1, "name": "ana", "pad": "%s"}' % ("x" * 5000), '{"name": "Ana!"}',
                        '{"name": "ana\\n"}', "not json", '["ana"]'):
            saved.write_text(content, encoding="utf-8")
            state = tp.post(srv, "/api/inspect", {"target": str(a)})[1]
            assert state.get("human") == "", "ignored: %r → %r" % (content[:40], state.get("human"))
    roles = saved.with_name("roles.json")
    roles.write_bytes(b'{"people": {"bob": {"implement": "claude", "review": "codex"}}, "version": 1}\n')
    before = roles.read_bytes()
    with tp.live(a, tt.Team()) as srv:
        tp.post(srv, "/api/inspect", {"target": str(a)})
        assert tp.post(srv, "/api/human", {"name": "ana"})[1].get("persisted") is True
    assert roles.read_bytes() == before, "saving the name leaves the tool choices byte for byte"
    linked = tmp / "a linked"
    tp.git(a, "worktree", "add", "-q", "-b", "side", str(linked))
    with tp.live(linked, tt.Team()) as srv:
        state = tp.post(srv, "/api/inspect", {"target": str(linked)})[1]
        assert state.get("human") == "ana" and state.get("human_source") == "project", state
    # 5. The team step says what it needs instead of hiding.
    d, _ = tt.ready_project(root, tt.fresh(tmp, "d"), name="project d")
    with tp.live(d, tt.Team()) as srv:
        tt.ready(srv, d, name=None)
        code, body = tp.get(srv, "/api/team")
        assert code == 400 and body.get("need") == "human", body
        code, body = tp.post(srv, "/api/team/reviewer", {"confirm": "dan-r"})
        assert code == 400 and body.get("need") == "human", body
    tp.git(d, "config", "user.name", "Dan")  # UAK-153: the name is the checkout's Git identity
    with tp.live(d, tt.Team()) as srv:
        tp.post(srv, "/api/inspect", {"target": str(d)})
        assert tp.post(srv, "/api/human", {"name": "dan"})[0] == 200
        code, body = tp.get(srv, "/api/team")
        assert code == 400 and body.get("need") == "check", body
    # 6. The page asks for the name inside the team step.
    html = tf.page()
    team = section(html, "team-step")
    assert 'id="team-name"' in team and 'id="team-name-save"' in team, "the team step has its own name field"
    assert "need" in tf.page_function(tf.script(html), "loadTeam"), "loadTeam reads what the refusal needs"


def repick_keeps_state(root, tmp):
    a, _ = tt.ready_project(root, tt.fresh(tmp, "a"), name="project a")
    b, _ = tt.ready_project(root, tt.fresh(tmp, "b"), name="project b")
    runner = Recording(tt.Team())
    with tp.live(a, runner) as srv:
        tt.ready(srv, a)
        before = status(srv)
        runner.calls[:] = []
        assert tp.post(srv, "/api/inspect", {"target": str(a)})[0] == 200
        after = status(srv)
        assert after["ready"] is True and after["checks"] == before["checks"], after
        assert after["next_command"] == before["next_command"] and after["human"] == "ana", after
        assert after["checked"] is True and after["inspect"] == before["inspect"] + 1, after
        state = tp.post(srv, "/api/inspect", {"target": str(b)})[1]
        assert state["ready"] is False and state["checked"] is False and state["checks"] == [], \
            "another project never inherits a check: %r" % state
        state = tp.post(srv, "/api/inspect", {"target": str(a)})[1]
        assert state["ready"] is True and state["checks"] == before["checks"] and state["checked"] is True, state
        assert runner.calls == [], "re-picking runs no engine and no network: %r" % runner.calls
        for kept in srv.checks_kept.values():
            kept["at"] -= 601
        state = tp.post(srv, "/api/inspect", {"target": str(a)})[1]
        assert state["ready"] is False and state["checked"] is False and state["checks"] == [], \
            "a check older than ten minutes is not reused: %r" % state
    code = tf.script(tf.page())
    form = code[code.index('el("project-form").onsubmit'):code.index('el("workflow-form").onsubmit')]
    assert "landing(" in form, "re-picking lands where the project is"
    out = run("""
        var d = {installed: true, checked: false, target: "/p/a", inspect: 3, phase: "setup"};
        var first = shouldAutoCheck(d);
        autoCheckedFor = d.target + ":" + d.inspect;
        var again = shouldAutoCheck(d);
        var grown = shouldAutoCheck(Object.assign({}, d, {inspect: 4}));
        var checked = shouldAutoCheck(Object.assign({}, d, {checked: true, inspect: 5}));
        var busy = shouldAutoCheck(Object.assign({}, d, {phase: "checking", inspect: 5}));
        var failing = shouldAutoCheck(Object.assign({}, d, {error: "x", inspect: 5}));
        var bare = shouldAutoCheck(Object.assign({}, d, {installed: false, inspect: 5}));
        gone = true;
        var lost = shouldAutoCheck(Object.assign({}, d, {inspect: 5}));
        gone = false;
        return [first, again, grown, checked, busy, failing, bare, lost];
    """)
    if out is not None:
        assert out == [True, False, True, False, False, False, False, False], out


def server_gone_banner(root, tmp):
    html = tf.page()
    code = tf.script(html)
    banner = re.search(r'<div[^>]*id="server-gone"[^>]*>', html)
    assert banner and 'role="alert"' in banner.group(0) and "hidden" in banner.group(0), "a hidden alert banner"
    assert tf.catalog().get(GONE_EN) == GONE_ES, "the banner reads in Spanish"
    assert "serverLost(" in tf.page_function(code, "api"), "a lost server is noticed where every request goes"
    for name in ("refresh", "loadDashboard", "autoCheck"):
        assert re.search(r"\bgone\b", tf.page_function(code, name)), "%s() stops while setup is gone" % name
    out = run("""
        setBusy(el("check"), true);
        var first = {};
        try { await api("status"); } catch (e) { first = {gone: e.gone === true, message: e.message}; }
        var box = el("server-gone");
        var shown = {hidden: box.hidden, text: box.textContent.indexOf(%s) >= 0};
        var raw = nodes.some(function (n) { return /Failed to fetch/.test(n.textContent); });
        var busy = el("check").getAttribute("aria-busy"), pending = timers.length, delays = [];
        for (var i = 0; i < 10 && timers.length; i++) {
          delays.push(timers[0].ms);
          advance(timers[0].ms);
          await flush();
        }
        var calls = __fetchCalls, left = timers.length;
        fire(el("server-gone-retry"), "click");
        await flush();
        var retried = __fetchCalls - calls, afterRetry = timers.length;
        window.__fetch = function () {
          return Promise.resolve({ok: true, status: 200, json: function () { return Promise.resolve({phase: "setup", target: "/p/a"}); }});
        };
        fire(el("server-gone-retry"), "click");
        await flush();
        var back = {hidden: box.hidden, tries: probeTries, gone: gone, rendered: rendered};
        window.__fetch = function () {
          return Promise.resolve({ok: false, status: 403, json: function () {
            return Promise.resolve({error: "This setup session expired. Reopen the address printed in the terminal."}); }});
        };
        var expired = false;
        try { await api("status"); } catch (e) { expired = e.gone === true; }
        return {first: first, shown: shown, raw: raw, busy: busy, pending: pending, delays: delays, calls: calls,
                left: left, retried: retried, afterRetry: afterRetry, errors: __errors, back: back, expired: expired,
                again: !box.hidden};
    """ % json.dumps(GONE_ES), language="es")
    if out is None:
        return
    assert out["first"] == {"gone": True, "message": GONE_ES}, out["first"]
    assert out["shown"] == {"hidden": False, "text": True}, out["shown"]
    assert not out["raw"], "the raw browser error never reaches the page"
    assert out["busy"] is None, "no button stays busy once setup is gone"
    assert out["pending"] == 1, "one probe is scheduled: %r" % out["pending"]
    assert out["delays"] == [2000, 4000, 8000, 16000, 30000, 30000], out["delays"]
    assert out["calls"] == 7 and out["left"] == 0, "it backs off, then stops: %r" % out
    assert out["retried"] == 1 and out["afterRetry"] == 0, "Retry asks once: %r" % out
    assert out["errors"] == 0, "no console errors"
    assert out["back"]["hidden"] and out["back"]["tries"] == 0 and out["back"]["gone"] is False and out["back"]["rendered"] == 1, out["back"]
    assert out["expired"] and out["again"], "an expired session shows the same banner"


# --- UAK-159: the ten screens' server and resume behaviour -----------------------------------------------------------------
# Why (2026-11-23): the wizard did not say what it found in a folder, offered one blind welcome, could not be closed
# from its page (a person pressed Ctrl+C in a terminal they could not see), and its steps had no address.
import test_setup_guide as tg


def reach(page, name, timeout=15000):
    """Wait for the screen NAME; say which one the page is on when it never comes."""
    try:
        page.wait_for_selector('.screen[data-on][data-screen="%s"]' % name, timeout=timeout)
    except Exception:  # noqa: BLE001
        raise AssertionError("the page never reached %s: it shows %s at %s (%s)" % (name, page.evaluate(
            "(document.querySelector('.screen[data-on]') || {dataset: {}}).dataset.screen"), page.url, page.evaluate(
            "[...document.querySelectorAll('#error, .action-result, .toast')].map(e => e.textContent.trim()).filter(Boolean).join(' | ')")))


def kit_repo(tmp, name, mode="sprint", commits=2, version="6.8.0"):
    return tg.kit_project(tmp, name, mode, commits, version)


def inspect(srv, repo):
    status, body = tp.post(srv, "/api/inspect", {"target": str(repo)})
    assert status == 200, body
    return body


def existing_repository_is_detected(root, tmp):
    old = kit_repo(tmp, "old-one", commits=4)
    for folder in (".husky", ".github/workflows", "tests"):
        (old / folder).mkdir(parents=True, exist_ok=True)
    (old / ".github/workflows/ci.yml").write_text("name: ci\n")
    (old / "package.json").write_text('{"scripts": {"test": "vitest"}, "dependencies": {"next": "14"}}')
    (old / ".uak").rename(tmp / "kit-away")  # the folder has no kit: this is a repository the kit has not seen
    fresh = tmp / "fresh-one"
    fresh.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(fresh)], check=True)
    (fresh / "lefthook.yml").write_text("pre-commit: {}\n")
    with wizard.LiveServer("") as srv:
        found = inspect(srv, old)["detected"]
        assert found["repo"] == "existing" and found["commits"] == 4, found
        assert found["hooks"] == "husky" and found["ci"] == "GitHub Actions" and found["tests"] == "npm test" and \
            found["stack"] == "nextjs", found
        assert found["kit_files"]["base"] > 50 and found["kit_files"][".claude"] > 0, "the install is counted: %r" % found["kit_files"]
        again = inspect(srv, fresh)["detected"]
        assert again["repo"] == "new" and again["commits"] == 0 and again["hooks"] == "lefthook" and again["ci"] == "" and \
            again["tests"] == "", again
        status, body, _ = wizard.request(srv, "GET", "/api/status")
        assert json.loads(body)["detected"]["repo"] == "new", "the status carries what was found"
    assert not (fresh / ".uak").exists() and not (old / ".uak").exists(), "looking writes nothing"


def schedule_only_in_hackathon(root, tmp):
    code = tf.script(tf.page())
    assert re.search(r'mode === "sprint" && !\(resume\.freeze > 0\)', tf.page_function(code, "screenFor")) and \
        'name === "schedule") return !!data.installed && modeOf(data) === "sprint"' in tf.page_function(code, "allowed"), \
        "the page asks for a schedule only in Hackathon mode"
    out = run("""
        var base = {installed: true, human: "ana", phase: "setup", resume: {kit_on_main: null, freeze: 0, plan_approved: null}};
        function at(mode, freeze) { return screenFor(Object.assign({}, base, {settings: {Mode: mode}, resume: Object.assign({}, base.resume, {freeze: freeze}), }), {rules: true}); }
        return {marathon: at("marathon", 0), sprint: at("sprint", 0), scheduled: at("sprint", 4102444800),
                allowedMarathon: allowed("schedule", {installed: true, settings: {Mode: "marathon"}}),
                allowedSprint: allowed("schedule", {installed: true, settings: {Mode: "sprint"}})};
    """)
    if out is None:
        return
    assert out == {"marathon": "publish", "sprint": "schedule", "scheduled": "publish", "allowedMarathon": False,
                   "allowedSprint": True}, out


def rules_screen_writes_only_what_was_confirmed(root, tmp):
    repo = kit_repo(tmp, "rules", "marathon")
    config = repo / ".uak/PROJECT.md"
    original = config.read_bytes()
    with wizard.LiveServer(str(repo)) as srv:
        srv.open_target()
        for path in ("/api/status", "/api/dashboard"):
            wizard.request(srv, "GET", path)
        assert tp.post(srv, "/api/inspect", {"target": str(repo)})[0] == 200
        assert config.read_bytes() == original, "opening the screen writes nothing"
        shown = json.loads(wizard.request(srv, "GET", "/api/status")[1])["settings"]
        assert shown["Test-First"] == "yes" and shown["Review-Mode"] == "claims", shown
        for refused in ({"Review-Mode": "gh"}, {"Auto-Merge": "yes"}, {"Review-Independence": "human"}, {"Test-First": "maybe"}):
            status, _ = tp.post(srv, "/api/settings", refused)
            assert status in (400, 409), (status, refused)
            assert config.read_bytes() == original, "a line that grants authority or a value off the list changes nothing"
        status, answer = tp.post(srv, "/api/settings", {"Test-First": "no"})
        assert status == 200, (status, answer)
    changed = [(a, b) for a, b in zip(original.decode().splitlines(), config.read_text().splitlines()) if a != b]
    assert changed == [("Test-First: yes", "Test-First: no")], changed
    code = tf.script(tf.page())
    handler = code[code.index('el("rules-confirm").onclick'):]
    handler = handler[:handler.index("el(\"save\").onclick")]
    assert "Object.keys(changes).length" in handler and handler.count('api("settings"') == 1, \
        "Confirm sends only the lines that changed, and nothing when none did"
    found = tg.chromium()
    if not found:
        return
    sync_playwright, kwargs = found
    config.write_bytes(original)
    with wizard.LiveServer(str(repo)) as srv, sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"], **kwargs)
        page = browser.new_context(viewport={"width": 1280, "height": 800}, locale="en-US").new_page()
        page.goto("http://127.0.0.1:%d/?step=rules#code=%s" % (srv.server_port, srv.new_code()))
        reach(page, "rules")
        page.wait_for_selector("#rules-confirm:not([aria-disabled])")  # the readiness check the page starts on load is over
        page.click("#rules-confirm")
        reach(page, "people")
        assert config.read_bytes() == original, "Confirm with every line as it was writes nothing"
        page.goto("http://127.0.0.1:%d/?step=rules#code=%s" % (srv.server_port, srv.new_code()))
        reach(page, "rules")
        page.wait_for_selector("#rules-confirm:not([aria-disabled])")
        page.click("#rules-advanced summary")
        page.select_option("#rule-test-first", "warn")
        page.click("#rules-confirm")
        reach(page, "people")
        browser.close()
    assert config.read_text() == original.decode().replace("Test-First: yes", "Test-First: warn"), "only the confirmed line changed"


def diagnostics_are_not_prechecked(root, tmp):
    html = tf.page()
    for ident in ("blackbox", "diagnostics"):
        tag = re.search(r'<input[^>]*id="%s"[^>]*>' % ident, html).group(0)
        assert "checked" not in tag, "%s is not pre-checked: %s" % (ident, tag)
    words = " ".join(" ".join(tg.texts(tg.section(html, "installation-options"))).split())
    assert "public" in words and "Off unless you turn it on" in words and "coordination branch" in words, \
        "the screen says what is published, where, and that a public repository makes it public: %r" % words
    code = tf.script(html)
    assert "blackbox: el(\"blackbox\").checked" in code, "the install carries the person's choice, never a default"
    cmd = MODULE_FOR_CMD().install_command(Path("install.sh"), "/p", {"mode": "sprint", "harness": ["claude"], "blackbox": False})
    assert "--no-blackbox" in cmd, "an unchecked box installs with diagnostics off: %r" % cmd
    assert "--no-blackbox" not in MODULE_FOR_CMD().install_command(Path("install.sh"), "/p", {"mode": "sprint", "blackbox": True})


def MODULE_FOR_CMD():
    return wizard.MODULE


def old_kit_opens_update(root, tmp):
    old = kit_repo(tmp, "older", version="5.0.0")
    new = kit_repo(tmp, "current", version=(root / ".uak/VERSION").read_text().strip())
    odd = kit_repo(tmp, "odd", version="not a version")
    with wizard.LiveServer("") as srv:
        assert inspect(srv, old)["versions"]["older"] is True, "a kit older than this setup's is updated"
        assert inspect(srv, new)["versions"]["older"] is False
        assert inspect(srv, odd)["versions"]["older"] is False, "an unreadable version never raises an alarm"
        assert inspect(srv, old)["versions"]["current"] == (root / ".uak/VERSION").read_text().strip()
    code = tf.script(tf.page())
    assert 'return "update"' in tf.page_function(code, "screenFor") and "updateSkipped" in tf.page_function(code, "screenFor")
    out = run("""
        var d = {installed: true, human: "ana", phase: "setup", versions: {older: true}, resume: {}, settings: {}};
        return {older: screenFor(d, {rules: true}), current: screenFor(Object.assign({}, d, {versions: {older: false}}), {rules: true})};
    """)
    if out is not None:
        assert out == {"older": "update", "current": "rules" if False else out["current"]}, out
        assert out["current"] != "update", out


def spawn_wizard(root, tmp, target):
    """A real wizard process for TARGET (a pty as its terminal): (process, server-like, master fd)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_")}
    master, slave = os.openpty() if os.name != "nt" else (None, subprocess.DEVNULL)
    proc = subprocess.Popen([sys.executable, str(root / ".uak/bin/lib/setup.py"), "--no-open", str(target)],
                            cwd=str(tmp), env=env, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    if master is not None:
        os.close(slave)
    box = {}
    reader = threading.Thread(target=lambda: box.update(lines=[proc.stdout.readline(), proc.stdout.readline()]), daemon=True)
    reader.start()
    reader.join(60)
    match = re.search(r"UAK SETUP http://127\.0\.0\.1:(\d+)/", (box.get("lines") or [""])[0])
    assert match, "setup prints its address: %r" % box
    launcher = re.search(r"Launcher file: (.+\.html)\s*$", box["lines"][1])
    code = re.search(r"#code=([A-Za-z0-9_-]+)", Path(launcher.group(1)).read_text(encoding="utf-8")).group(1)
    server = types.SimpleNamespace(server_port=int(match.group(1)), token="")
    status, body, _ = wizard.request(server, "POST", "/api/session", {"code": code}, token=False)
    assert status == 200, body
    server.token = json.loads(body)["token"]
    return proc, server, master


def close_ends_the_server(root, tmp):
    repo = kit_repo(tmp, "closing")
    git_dir = Path(tp.git(repo, "rev-parse", "--absolute-git-dir"))
    # In process: an action that is running keeps its server; the page is told why, and nothing ends.
    with wizard.LiveServer(str(repo)) as srv:
        gate = threading.Event()
        busy = threading.Thread(target=gate.wait, args=(30,), daemon=True)
        busy.start()
        srv.worker = busy
        status, body = tp.post(srv, "/api/close", {})
        assert status == 409 and "still running" in body["error"] and not srv.close_asked and srv.end_reason() == "", (status, body)
        gate.set()
        busy.join(5)
        srv.worker = None
        status, body = tp.post(srv, "/api/close", {})
        assert status == 200 and body == {"closed": True} and srv.end_reason(), "an idle server ends at once"
    if os.name == "nt":
        return  # the real process below needs a pty
    # A real process: Close ends it, frees its port and leaves no file or process behind.
    proc, server, master = spawn_wizard(root, tmp, repo)
    try:
        records = sorted(p.name for p in git_dir.glob("uak-wizard.*"))
        assert "uak-wizard.port" in records and "uak-wizard.key" in records, records
        assert wizard.request(server, "GET", "/api/status")[0] == 200
        status, body, _ = wizard.request(server, "POST", "/api/close", {})
        assert status == 200, body
        assert proc.wait(20) == 0, "the process ends by itself after Close"
        refused = False
        try:
            wizard.request(server, "GET", "/api/status")
        except OSError:
            refused = True
        assert refused, "the port is free after Close"
        assert not sorted(git_dir.glob("uak-wizard.*")), "no record of the wizard is left: %r" % sorted(p.name for p in git_dir.glob("uak-wizard.*"))
        assert "UAK SETUP ended" in proc.stdout.read(), "it says why it ended and how to open it again"
        try:
            os.kill(proc.pid, 0)
            alive = True
        except OSError:
            alive = False
        assert not alive, "no process of the wizard is left"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(15)
            except subprocess.TimeoutExpired:
                proc.kill()
        proc.stdout.close()
        proc.stderr.close()
        if master is not None:
            os.close(master)


def step_survives_reload_and_back(root, tmp):
    repo = kit_repo(tmp, "steps", "sprint")
    with wizard.LiveServer(str(repo)) as srv:
        status, body, _ = wizard.request(srv, "GET", "/?step=rules", token=False)
        assert status == 200 and b'data-screen="rules"' in body, "a step has its own address"
        for bad in ("/?step=../../etc/passwd", "/?step=Rules", "/?step=", "/?step=rules&x=1", "/step/rules"):
            assert wizard.request(srv, "GET", bad, token=False)[0] == 404, bad
    code = tf.script(tf.page())
    show = tf.page_function(code, "show")
    assert 'history[!was || how === "replace" ? "replaceState" : "pushState"]' in show and '"/?step=" + name' in show, \
        "every step is pushed to the history, the first one replaces the address"
    assert 'addEventListener("popstate"' in code and 'new URLSearchParams(location.search).get("step")' in code, \
        "Back and Forward show the step of the address, and a reload reads it"
    found = tg.chromium()
    if not found:
        return
    sync_playwright, kwargs = found
    with wizard.LiveServer(str(repo)) as srv, sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"], **kwargs)
        page = browser.new_context(viewport={"width": 1280, "height": 800}, locale="en-US").new_page()

        def on(name):
            page.wait_for_selector('.screen[data-on][data-screen="%s"]' % name)
            assert page.url.endswith("/?step=%s" % name), page.url

        page.goto("http://127.0.0.1:%d/?step=rules#code=%s" % (srv.server_port, srv.new_code()))
        on("rules")
        page.click("#rules-confirm")
        on("people")
        page.reload()
        on("people")
        page.go_back()
        on("rules")
        page.go_forward()
        on("people")
        browser.close()


def last_screen_says_the_terminal_command(root, tmp):
    code = tf.script(tf.page())
    out = run("""
        return {plain: terminalCommand("/home/ana/my-app"), spaced: terminalCommand("/tmp/my app/it's"), none: terminalCommand("")};
    """)
    if out is not None:
        assert out["plain"] == "cd '/home/ana/my-app' && bash .uak/bin/uak start", out
        assert out["spaced"] == "cd '/tmp/my app/it'\\''s' && bash .uak/bin/uak start", "the path is quoted so the line can be pasted: %r" % out
        assert out["none"].startswith("bash ") and "install.sh --wizard" in out["none"], out
    html = tf.page()
    assert 'id="closed-command"' in tg.section(html, "screen-closed") and 'id="terminal-command"' in html
    assert re.search(r'el\("note-dashboard"\)\.textContent = [^;]*terminalCommand|command', tf.page_function(code, "drawScreens")), \
        "the last screen's bar says the command"
    for name in ("The wizard is closed", "Continue in the terminal"):
        assert name in tf.catalog(), "%r has a Spanish translation" % name


TESTS = [restart_lands_on_the_team_step, refresh_keeps_the_step_and_values, name_persists_per_project,
         repick_keeps_state, server_gone_banner, existing_repository_is_detected, schedule_only_in_hackathon,
         rules_screen_writes_only_what_was_confirmed, diagnostics_are_not_prechecked, old_kit_opens_update, close_ends_the_server,
         step_survives_reload_and_back, last_screen_says_the_terminal_command]


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    ROOT = tf.ROOT = args.package.resolve()
    spec = importlib.util.spec_from_file_location("resume_setup", ROOT / ".uak/bin/lib/setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wizard.MODULE = tt.MODULE = module
    spec = importlib.util.spec_from_file_location("resume_planning", ROOT / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-resume-"))
        started = time.monotonic()
        try:
            test(ROOT, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s: %s)" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_RESUME_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
