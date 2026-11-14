#!/usr/bin/env python3
"""The setup page guides the whole journey (UI-007): the journey from welcome to progress stays visible, the typed
approval says what to type, a finished step moves the person to the next one, the readiness gate and the Advanced
dashboard read in Spanish, and the page says whose Git/GitHub identity will sign the commits and PRs.
Evidence: the hackathon simulation and the PR chat (notes/handoff:PENDING-IMPROVEMENTS.md #2, #7, #13 and #17 to #20).
Contract: notes/handoff:UI-006-contract.md, section "UI-007" and amendment 8."""
import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

import test_setup_planning as tp
import test_setup_wizard as wizard

ROOT = None
MODULE = None


def lib(name):
    return (ROOT / ".uak/bin/lib" / name).read_text(encoding="utf-8")


def catalog():
    """The English → Spanish pairs of workspace.js (a pair may span lines and end with a comma)."""
    text = lib("workspace.js")
    pairs = re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)
    return {json.loads(a): json.loads(b) for a, b in pairs}


def gate_patterns():
    """The readiness gate's line patterns in workspace.js: GATE = [[regex, spanish], ...]."""
    text = lib("workspace.js")
    m = re.search(r"var GATE = (\[[\s\S]*?\n  \]);", text)
    assert m, "workspace.js defines var GATE = [[pattern, spanish], ...] for the gate's lines"
    return json.loads(re.sub(r",\s*\]", "]", m.group(1)))


class Texts(HTMLParser):
    """Visible text nodes of a page, outside script/style/code/pre and [data-no-i18n]."""

    VOID = ("input", "br", "img", "meta", "link", "hr", "source")

    def __init__(self):
        super().__init__()
        self.stack, self.out = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        skip = tag in ("script", "style", "code", "pre", "textarea", "title") or "data-no-i18n" in dict(attrs)
        self.stack.append((tag, skip))

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()[0] == tag:
                break

    def handle_data(self, data):
        if any(skip for _, skip in self.stack):
            return
        text = " ".join(data.split())
        if text and re.search(r"[A-Za-z]{2}", text):
            self.out.append(text)


def texts(html):
    parser = Texts()
    parser.feed(html)
    return parser.out


def section(html, ident):
    assert 'id="%s"' % ident in html, "the page has #%s" % ident
    start = html.index('id="%s"' % ident)
    start = html.rindex("<", 0, start)
    tag = re.match(r"<(\w+)", html[start:]).group(1)
    depth, i = 0, start
    for m in re.finditer(r"<(/?)%s\b[^>]*>" % tag, html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start:start + m.end()]
    raise AssertionError("unclosed %s" % ident)


def script(html):
    return html[html.index('<script nonce="__NONCE__">'):]


def journey_is_visible_from_welcome(root, tmp):
    html = lib("setup.html")
    journey = section(html, "journey")
    shell = html.index('id="setup-shell"')
    assert html.index('id="journey"') < shell, "the journey sits above setup and the dashboard, so it stays visible"
    steps = re.findall(r'<li[^>]*data-step="([a-z]+)"[^>]*>([\s\S]*?)</li>', journey)
    assert [s for s, _ in steps] == ["install", "prepare", "plan", "team", "progress"], steps
    where = {s: re.search(r'data-where="([a-z]+)"', body) for s, body in steps}
    assert all(where.values()), "each step says where it happens: %r" % steps
    assert {s: m.group(1) for s, m in where.items()} == {"install": "page", "prepare": "page", "plan": "page",
                                                       "team": "terminal", "progress": "agents"}
    words = " ".join(texts(journey))
    for needle in ("Install", "Prepare", "Plan", "Start the team", "Follow progress", "in this page", "in a terminal",
                   "your agents do it"):
        assert needle in words, "%r is in the journey: %r" % (needle, words)
    welcome = " ".join(texts(section(html, "welcome")))
    assert "installs the kit into this project" in welcome and "downloaded only once" in welcome, welcome
    code = script(html)
    m = re.search(r"function journeyStep\(data\) \{([\s\S]*?)\n        \}", code)
    assert m, "journeyStep(data) picks the current step from the server's state"
    for step in ("install", "prepare", "plan", "team", "progress"):
        assert '"%s"' % step in m.group(1), "journeyStep can return %s" % step
    assert re.search(r'setAttribute\("aria-current", "step"\)[\s\S]{0,400}journey|journey[\s\S]{0,600}aria-current', code), \
        "the current journey step is marked with aria-current"
    es = catalog()
    for needle in ("Start the team", "Follow progress", "in this page", "in a terminal", "your agents do it"):
        assert needle in es, "%r has a Spanish translation" % needle
    # Amendment 8: a finished step moves the person to the heading of the next one.
    focus = re.search(r"var NEXT_FOCUS = (\{[^}]*\});", code)
    assert focus, "var NEXT_FOCUS maps a finished operation to the next step's heading"
    targets = json.loads(focus.group(1))
    assert targets.get("installing") and targets.get("publishing") and targets.get("approving"), targets
    assert targets["publishing"] == "planning-heading", "after publishing the kit: Plan your project"
    for phase, ident in targets.items():
        tag = re.search(r'<(h[1-4])[^>]*id="%s"' % re.escape(ident), html)
        assert tag and 'tabindex="-1"' in html[tag.start():html.index(">", tag.start())], \
            "%s → #%s is a focusable heading" % (phase, ident)
    assert re.search(r"NEXT_FOCUS\[previous\][\s\S]{0,300}\.focus\(", code), "render focuses it when the phase ends"
    assert "Plan your project" in section(html, "planning-heading"), "the planning heading says Plan your project"


def approval_field_says_what_to_type(root, tmp):
    html = lib("setup.html")
    box = section(html, "approve-confirm")
    assert 'id="approve-hint"' in box, "a hint under the disabled button"
    assert box.index('id="approve-publish"') < box.index('id="approve-hint"'), "the hint is under the button"
    code = script(html)
    assert re.search(r'el\("approve-name"\)\.placeholder\s*=\s*[^;]*project', code), \
        "the field's placeholder is the exact folder name from the server"
    assert re.search(r'approve-hint[\s\S]{0,300}Type \{name\} to enable publishing', code), \
        "the hint says Type NAME to enable publishing"
    assert re.search(r'el\("approve-hint"\)\.hidden\s*=\s*!el\("approve-publish"\)\.disabled|approve-hint"\)\.hidden = ', code), \
        "the hint shows while the button is disabled"
    assert "Type {name} to enable publishing" in catalog(), "translated"


def shell_string(text, i):
    """The double-quoted Bash string that starts at text[i] == '"', with every $(...) (quotes inside included) and
    every $var / ${var...} replaced by the word "sample". Returns (value, index after the closing quote)."""
    out, i = [], i + 1
    while text[i] != '"':
        if text.startswith("$(", i):
            depth, i = 1, i + 2
            while depth:
                c = text[i]
                if c == "'":
                    i = text.index("'", i + 1)
                elif c == '"':
                    _, i = shell_string(text, i)
                    continue
                elif c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                i += 1
            out.append("sample")
            continue
        m = re.match(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*", text[i:])
        if m:
            out.append("sample")
            i += m.end()
            continue
        if text[i] == "\\":
            out.append(text[i + 1])
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out), i + 1


def start_templates():
    """The first line of every ok/need/note in .uak/bin/start, variables replaced by a sample word."""
    text = lib("../start")
    found = []
    for m in re.finditer(r'(?:^|[\s;{|&])(ok|need|note) (?=")', text, re.M):
        value, _ = shell_string(text, m.end())
        found.append((m.group(1), value))
    return found


def gate_lines_are_translated(root, tmp):
    patterns = gate_patterns()
    templates = start_templates()
    assert len(templates) >= 20, "the gate's lines were read from .uak/bin/start: %r" % templates
    missing = []
    for kind, line in templates:
        hit = [es for rx, es in patterns if re.fullmatch(rx, line)]
        if not hit:
            missing.append(line)
        else:
            assert hit[0] and hit[0] != line, "a Spanish line for %r" % line
    assert not missing, "gate lines with no Spanish pattern: %r" % missing
    for rx, es in patterns:
        assert rx.startswith("^") is False and not re.search(r"\(\?[<P]", rx), "JS-compatible regex, whole-line: %r" % rx
    code = script(lib("setup.html"))
    assert "UAKWorkspace.gate(" in code, "the page shows the gate's lines through UAKWorkspace.gate"
    assert re.search(r"gate: gate", lib("workspace.js")), "workspace.js exposes gate()"
    # The engine's own text stays reachable: Technical details keep the verbatim output.
    assert 'id="output"' in lib("setup.html")


def advanced_dashboard_is_translated(root, tmp):
    dash = lib("dash.html")
    es = catalog()
    calls = re.findall(r'\bT\(\s*"((?:[^"\\]|\\.)*)"', dash)
    assert len(calls) > 40, "dash.html translates its labels through T()"
    missing = sorted(set(json.loads('"%s"' % c) for c in calls) - set(es))
    assert not missing, "dash.html labels with no Spanish: %r" % missing
    static = [t for t in texts(dash) if t not in es]
    assert not static, "static dash.html text with no Spanish: %r" % static
    # Labels drawn without T() (tiles, empty states) are translated too: the frame translates its whole body.
    assert re.search(r"UAKWorkspace\.start\(document\.body\)", dash), "dash.html translates its whole body as it changes"
    code = re.sub(r"(?m)^\s*//.*$", "", dash[dash.index("function T("):])
    classes = set(w for v in re.findall(r'"class":\s*"([^"]*)"', code) for w in v.split())
    classes |= set(w for v in re.findall(r'(?:className\s*=\s*|"class":\s*|setAttribute\("class",\s*)"([^"]*)"\s*\+', code) for w in v.split())
    shown = set()
    for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', code):
        if lit.startswith("uak ") or not re.match(r"[A-Za-z]", lit) or not re.search(r"[A-Za-z]{3,}", lit) or re.search(r"[{}=;<>()$/]|\.(md|py|sh|js)\b", lit):
            continue
        if set(lit.split()) <= classes or not (" " in lit.strip() or re.fullmatch(r"[A-Z][a-z]+", lit)):
            continue
        shown.add(lit)
    left = sorted(l for l in shown if l not in es and l.strip() not in es and l not in ("None",))
    assert not left, "dashboard labels with no Spanish: %r" % left
    # Review of 949eca1 (P2): composed labels ("oldest 4 min", "online · 4 min ago") stayed English because the
    # body translation only matches whole text nodes. Every English literal that is concatenated, or chosen by a
    # ternary for a text property, goes through T().
    def wrapped(at):
        return re.search(r"T\(\s*$", code[max(0, at - 4):at]) is not None
    concat = set()
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', code):
        lit = m.group(1)
        before, after = code[:m.start()].rstrip()[-1:], code[m.end():].lstrip()[:1]
        if (before == "+" or after == "+") and re.search(r"[A-Za-z]{3,}", lit) and not wrapped(m.start()) \
                and not re.search(r"[<>=:;/(){}#]|px|--", lit) and set(lit.split()) - classes - {"uak", "dash", "min", "·"}:
            concat.add(lit)
    assert not concat, "concatenated English with no T(): %r" % sorted(concat)
    ternary = set()
    for m in re.finditer(r"\btext:\s*[^,{}]*?\?\s*\"((?:[^\"\\]|\\.)*)\"\s*:\s*\"?((?:[^\"\\,}]|\\.)*)", code):
        for lit, at in ((m.group(1), m.start(1) - 1),):
            if re.search(r"[A-Za-z]{3,}", lit) and not wrapped(at) and lit not in ("github",):
                ternary.add(lit)
    assert not ternary, "text chosen by a ternary with no T(): %r" % sorted(ternary)
    loose = sorted(set(m.group(1) for m in re.finditer(r'\)\s*,\s*"([A-Za-z][A-Za-z ]{2,})"\s*\]', code) if not wrapped(m.start(1) - 1)))
    assert not loose, "a word drawn next to an element with no T(): %r" % loose
    assert "T(a.status)" in code, "an agent's status (online, recent, away, offline) is translated"
    for status in ("online", "recent", "away", "offline", "retired"):
        assert status in es, "status %r has a Spanish label" % status
    for literal in re.findall(r'(?<![\w.])"((?:Retired|Conversation about )[^"]*)"', dash):
        assert re.search(r'T\(\s*"%s"' % re.escape(literal), dash), "%r goes through T()" % literal
    setup = lib("setup.html")
    team = section(setup, "team-step") + section(setup, "advanced-next")
    left = [t for t in texts(team) if t not in es and not re.fullmatch(r"[0-9. ]+", t)]
    assert not left, "the team step and the Advanced box have no English left: %r" % left
    heading = re.search(r'<h1>([^<]+)</h1>\s*<p class="secondary" id="dashboard-project"', setup).group(1).strip()
    status = section(setup, "dashboard-status")
    assert heading not in status and not re.search(r'dashboard-status"\)\.textContent = [^;]*"%s"' % re.escape(heading), script(setup)), \
        "the notice under the title never repeats the heading %r" % heading


class Identity:
    """Runner for the setup server: `gh auth status` answers with a token line the page must never see."""

    def __init__(self, gh_output, code=0):
        self.gh_output, self.code, self.calls = gh_output, code, []

    def __call__(self, command, cwd=None, timeout=120, group=False, env=None, **kwargs):
        name = Path(command[0]).name.lower().replace(".exe", "")
        if name == "gh":
            self.calls.append(list(command))
            assert timeout <= 15, "gh gets a short timeout: %r" % timeout
            return subprocess.CompletedProcess(command, self.code, self.gh_output, "")
        if name in ("claude", "codex"):
            return subprocess.CompletedProcess(command, 0, "", "")
        return MODULE.run_command(command, cwd=cwd, timeout=timeout, group=group, env=env)


GH_USER = "octo-friend\n"
# A token-shaped value built at run time, so the secret scan never sees a token in this file.
GH_HOSTILE = "Token: " + "gh" + "o_" + "X" * 24 + " keyring\n"


def shared_identity_is_warned(root, tmp):
    target, _ = tp.project(root, tmp, name="identity project")
    for output, login, code in ((GH_USER, "octo-friend", 0), (GH_HOSTILE, "", 0), ("", "", 1)):
        runner = Identity(output, code=code)
        live = wizard.LiveServer(str(target), run=runner)
        live.server.planning.find_binary = lambda name: "/fake/bin/" + name
        live.server.identity_run = runner
        with live as srv:
            assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
            assert tp.post(srv, "/api/human", {"name": "ana"})[0] == 200
            # Read in the background (never under the server lock): the page polls status until it arrives.
            deadline = time.time() + 10
            while True:
                status, body, _ = wizard.request(srv, "GET", "/api/status")
                if "identity" in json.loads(body.decode("utf-8")) or time.time() > deadline:
                    break
                time.sleep(0.1)
        raw = body.decode("utf-8")
        state = json.loads(raw)
        ident = state.get("identity")
        assert ident == {"git_name": "Ana Human", "git_email": "ana@example.invalid", "gh_login": login}, ident
        assert "gho_" not in raw and "ghp_" not in raw and "Token" not in raw and "keyring" not in raw, \
            "only the parsed login reaches the page"
        # gh's own hosts file, offline: `gh auth status` checks the token online and made inspecting a project wait.
        assert runner.calls and all(c[1:] == ["config", "get", "user", "-h", "github.com"] for c in runner.calls), runner.calls
    html = lib("setup.html")
    box = section(html, "identity-warning")
    assert 'role="status"' in box or 'role="alert"' in box, box[:200]
    code = script(html)
    assert re.search(r"identity-warning[\s\S]{0,1500}git_name[\s\S]{0,600}gh_login|gh_login[\s\S]{0,1500}identity-warning", code), \
        "the page names who signs the commits and the PRs"
    assert re.search(r"function sharedIdentity\(", code), "sharedIdentity() decides when the identity is someone else's"
    # Review of 949eca1 (P3): no name means a warning too, and the match works both ways.
    assert re.search(r"unnamed = !data\.human", code), "an unnamed person gets the warning"
    assert "Tell setup your name (Your name, below) so it can check that this identity is yours." in catalog()
    assert re.search(r"me\.indexOf\(w\)", code) and re.search(r"w\.indexOf\(me\)", code), "the match works in both directions"
    code_py = lib("setup.py")
    post = code_py[code_py.index("    def do_POST(self):"):code_py.index("    def read_identity(self, data):")]
    assert post.index("self.identity = self.read_identity(data)") < post.index("with self.server.lock:"), \
        "who signs is read before the server lock is taken, never under it"
    assert "threading.Thread" not in code_py[code_py.index("def signing_identity"):code_py.index("def kit_present")], \
        "and synchronously: a background git kept a process in the project (Windows WinError 32)"
    es = catalog()
    for needle in ("Commits will be signed as {git} and pull requests opened as {gh}.",
                   "This looks like someone else's identity. If this is not your computer, set your own before publishing: git config user.name and user.email, and gh auth login."):
        assert needle in es, "%r is translated" % needle


# --- UI-012 (absorbs UI-013): the identity warning per account, and no English left in the Spanish journey ------------
# Evidence: notes/handoff:qa/rounds-2026-11-13/SUMMARY.md #8 and #10 (r2, r3, r4), PENDING-IMPROVEMENTS.md #42 and #44.


def page_function(code, name):
    """The source of a top-level page function (`function NAME(` at 8 spaces, closed by `}` at the same indent)."""
    m = re.search(r"\n( *)function %s\([\s\S]*?\n\1\}" % re.escape(name), code)
    assert m, "the page defines function %s()" % name
    return m.group(0)


NODE_PROGRAM = r"""
const vm = require("vm"), fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const store = {"uak-language": input.language};
const ctx = {navigator: {language: input.language}, console: console,
             localStorage: {getItem: function (k) { return store[k] || null; }, setItem: function () {}}};
ctx.window = ctx;
vm.createContext(ctx);
input.sources.forEach(function (s) { vm.runInContext(s, ctx); });
process.stdout.write(JSON.stringify(input.calls.map(function (c) { return vm.runInContext(c, ctx); })));
"""


def page_js(functions, calls, language="en"):
    """Run page functions with the real workspace.js in Node (a fake browser: language, storage); None without Node.
    Every other check in this file reads the sources; these run the page's own logic on the inputs that failed."""
    node = shutil.which("node")
    if not node:
        print("  note: no Node.js here, so the page logic is checked by reading it only")
        return None
    code = script(lib("setup.html"))
    sources = [lib("workspace.js")] + [page_function(code, name) for name in functions]
    with tempfile.TemporaryDirectory(prefix="uak-guide-js-") as folder:
        program = Path(folder) / "run.js"
        program.write_text(NODE_PROGRAM, encoding="utf-8")
        done = subprocess.run([node, str(program)], input=json.dumps({"language": language, "sources": sources,
                                                                      "calls": calls}),
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, "the page logic runs: %s" % done.stderr[-1500:]
    return json.loads(done.stdout)


def identity_verdicts(cases, language="en"):
    """identityWarning(ident, human) for each (ident, human): {text, git, gh} as the page shows it."""
    calls = ["JSON.parse(JSON.stringify(identityWarning(%s, %s)))" % (json.dumps(ident), json.dumps(human))
             for ident, human in cases]
    return page_js(["plainWords", "sameName", "sharedIdentity", "identityWarning"], calls, language)


def github_login_is_checked_on_its_own(root, tmp):
    # The server reports both accounts as parsed (fake identity: Git = the person, gh = someone else).
    target, _ = tp.project(root, tmp, name="login project")
    runner = Identity(GH_USER)
    live = wizard.LiveServer(str(target), run=runner)
    live.server.planning.find_binary = lambda name: "/fake/bin/" + name
    live.server.identity_run = runner
    with live as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert tp.post(srv, "/api/human", {"name": "ana"})[0] == 200
        state = tp.get(srv, "/api/status")[1]
    ident = state.get("identity")
    assert ident == {"git_name": "Ana Human", "git_email": "ana@example.invalid", "gh_login": "octo-friend"}, ident
    code = script(lib("setup.html"))
    # Each account is matched on its own words: Git name and email's local part, then the GitHub login.
    shared = page_function(code, "sharedIdentity")
    assert re.search(r"git:[^,}]*sameName\(", shared) and re.search(r"gh:[^,}]*sameName\(", shared), \
        "sharedIdentity() matches the Git name/email and the GitHub login separately: %s" % shared
    assert "identityWarning(" in page_function(code, "drawIdentity"), "drawIdentity shows identityWarning()"
    es = catalog()
    for needle in ("The GitHub login {gh} does not match your name, so it looks like someone else's account: sign in as yourself with gh auth login before publishing.",
                   "The Git name and email {git} do not match your name, so they look like someone else's: set your own with git config user.name and user.email before publishing."):
        assert needle in es and es[needle] != needle, "%r has a Spanish translation" % needle
    found = identity_verdicts([(ident, "ana"),
                               (dict(ident, gh_login="ana-dev"), "ana"),
                               ({"git_name": "Carla Ruiz", "git_email": "carla@example.invalid", "gh_login": "ana-dev"}, "ana"),
                               ({"git_name": "Carla Ruiz", "git_email": "carla@example.invalid", "gh_login": "octo-friend"}, "ana"),
                               ({"git_name": "Ana Human", "git_email": "ana@example.invalid", "gh_login": ""}, "ana")])
    if found is None:
        return
    gh_other, mine, git_other, both, no_gh = found
    # r4: "ana" matched the Git name, and that one word hid that the pull requests open as someone else.
    assert gh_other["gh"] and not gh_other["git"], gh_other
    assert "GitHub login @octo-friend" in gh_other["text"] and "Git name and email" not in gh_other["text"], gh_other
    assert not mine["git"] and not mine["gh"] and "someone else" not in mine["text"], mine
    assert git_other["git"] and not git_other["gh"], git_other
    assert "Git name and email Carla Ruiz <carla@example.invalid>" in git_other["text"] and "GitHub login" not in git_other["text"], git_other
    assert both["git"] and both["gh"] and "someone else's identity" in both["text"], both
    assert not no_gh["gh"] and not no_gh["git"], "no gh login is nobody's account, not someone else's: %r" % no_gh
    spanish = identity_verdicts([(ident, "ana")], language="es")[0]["text"]
    assert "@octo-friend" in spanish and "GitHub login" not in spanish and "someone else" not in spanish, spanish


def accents_do_not_break_the_match(root, tmp):
    code = script(lib("setup.html"))
    words = page_function(code, "plainWords")
    # PENDING #44: [^a-z0-9] dropped "é", so "José" became "jos" and "Ana García" never matched "anagarcia".
    assert 'normalize("NFD")' in words, "accents are removed by decomposing the letters: %s" % words
    assert "[^a-z0-9]" not in page_function(code, "sharedIdentity") + words, "letters outside a-z are kept, not dropped"
    found = identity_verdicts([
        ({"git_name": "jose", "git_email": "jose@example.invalid", "gh_login": "jose-dev"}, "José"),
        ({"git_name": "José Pérez", "git_email": "jperez@example.invalid", "gh_login": "JOSE-p"}, "jose"),
        ({"git_name": "anagarcia", "git_email": "anagarcia@example.invalid", "gh_login": "anagarcia"}, "Ana García"),
        ({"git_name": "Íñigo Muñoz", "git_email": "inigo@example.invalid", "gh_login": "inigo-munoz"}, "iñigo"),
        ({"git_name": "Carla Ruiz", "git_email": "carla@example.invalid", "gh_login": "carla"}, "José"),
        ({"git_name": "Дмитрий", "git_email": "dmitry@example.invalid", "gh_login": "octo-friend"}, "Дмитрий"),
    ])
    if found is None:
        return
    for verdict, case in zip(found[:4], ("José = jose", "case and accents", "Ana García = anagarcia", "ñ = n")):
        assert not verdict["git"] and not verdict["gh"], "%s: %r" % (case, verdict)
    assert found[4]["git"] and found[4]["gh"], "someone else's accounts still warn: %r" % found[4]
    # A non-Latin name kept its letters: the Git name matches it, the unrelated login does not.
    assert not found[5]["git"] and found[5]["gh"], found[5]


def doctor_templates():
    """Each doctor failure line as `uak start` lists it under its preflight line ("· " + the FAIL text)."""
    text = lib("../doctor")
    found = []
    for m in re.finditer(r'(?:^|[\s;{|&])(?:bad|msg=)(?: )?(?=")', text, re.M):
        value, _ = shell_string(text, m.end())
        if value != "sample":
            found.append("· " + value)
    return found


def notes_patterns():
    text = lib("workspace.js")
    m = re.search(r"var NOTES = (\[[\s\S]*?\n  \]);", text)
    assert m, "workspace.js defines var NOTES = [[pattern, spanish], ...]"
    return json.loads(re.sub(r",\s*\]", "]", m.group(1)))


def spanish_of(line, patterns, es):
    """What translate() shows for a line in Spanish: a catalog entry, else the first whole-line pattern."""
    if line in es:
        return es[line]
    for rx, spanish in patterns:
        m = re.fullmatch(rx, line)
        if m:
            return re.sub(r"\$(\d)", lambda d: es.get(m.group(int(d.group(1))) or "", m.group(int(d.group(1))) or ""), spanish)
    return None


def spanish_journey_has_no_english(root, tmp):
    es, notes = catalog(), notes_patterns()
    code = script(lib("setup.html"))
    # The doctor sub-lines under "preflight: doctor found N failure(s)" (r3).
    lines = doctor_templates()
    assert len(lines) >= 18, "the doctor's failure lines were read: %r" % lines
    lines.append("uak start --fix does the hooks, the skills folders and, alone on the repo, Review-Mode: claims")
    missing = [l for l in lines if not spanish_of(l, notes, es) or spanish_of(l, notes, es) == l]
    assert not missing, "doctor sub-lines with no Spanish: %r" % missing
    for rx, _ in notes:
        assert not re.search(r"\(\?[<P]", rx), "JS-compatible regex: %r" % rx
    checks = code[code.index('el("checks").replaceChildren();'):code.index('el("preferences").hidden')]
    assert re.search(r"lines\.slice\(1\)[\s\S]{0,200}UAKWorkspace\.t\(", checks), \
        "the checklist translates the lines under each check too, not only the first one"
    terminal = code[code.index("var box = g.terminal;"):code.index('el("copy-terminal-cd").onclick')]
    assert "li.textContent = UAKWorkspace.t(line);" in terminal, "the terminal box's doctor lines read in Spanish too (QA of UI-012)"
    # The claim progress line (claim.sh), shown on the Advanced dashboard's cards and stalled rows (r3).
    claim = lib("claim.sh")
    at = re.search(r'put "\$RECORD" Progress (?=")', claim)
    progress, _ = shell_string(claim, at.end())
    sample = progress.replace("sample commit", "3 commit").replace("last: sample", "last: 1a2b3c4 fix the form (5 minutes ago)")
    sample = sample.replace("sample uncommitted", "2 uncommitted").replace("at sample", "at 1794600000")
    for line in (sample, re.sub(r" · at \d+$", "", sample)):
        shown = spanish_of(line, notes, es)
        assert shown and "since the claim" not in shown and "uncommitted" not in shown and "ago" not in shown, (line, shown)
        assert "1a2b3c4 fix the form" in shown, "the commit itself is shown as it is: %r" % shown
    dash = lib("dash.html")
    assert re.search(r'"class": "prog", text: T\(prog\)', dash) and re.search(r'text: t\.progress \? T\(t\.progress\)', dash), \
        "the dashboard shows the progress line through T()"
    # The status heading: the gate's line in Spanish, and no ✓ while a TODO remains (r3).
    title = page_function(code, "statusTitle")
    assert "UAKWorkspace.gate(" in title, "the heading shows the gate's line in the page's language"
    left = [lit for lit in re.findall(r'"([A-Z][^"]*[a-z][^"]*)"', title) if lit not in es]
    assert not left, "heading literals with no Spanish: %r" % left
    assert re.search(r'el\("result-title"\)\.textContent = statusTitle\(data\)', code)
    assert re.search(r'el\("status-icon"\)\.textContent = statusIcon\(data\)', code)
    # "No technical output yet." sits in a <pre>, which the body translation skips (r1).
    assert re.search(r'el\("output"\)\.textContent = data\.details \|\| UAKWorkspace\.t\("No technical output yet\."\)', code)
    # The schedule's weekday ("Fri 03:30") comes from the engine in English (r1).
    saved = code[code.index('el("schedule-form").onsubmit'):code.index("var publishDigest")]
    assert saved.count("UAKWorkspace.when(") >= 3, "the freeze, the first claim and the confirmation read in Spanish"
    todo = {"installed": True, "phase": "checked", "checks": [{"state": "ok", "text": "1. kit installed"},
                                                             {"state": "todo", "text": "2. preflight: doctor found 2 failure(s)"}],
            "guidance": {"kind": "todo", "title": "preflight: doctor found 2 failure(s)"}}
    calls = ["statusIcon(%s)" % json.dumps(todo), "statusTitle(%s)" % json.dumps(todo),
             "statusIcon(%s)" % json.dumps(dict(todo, ready=True, checks=[], guidance={})),
             "UAKWorkspace.when('Fri 03:30')", "UAKWorkspace.when('Sun 23:59')",
             "UAKWorkspace.t(%s)" % json.dumps(sample), "UAKWorkspace.t(%s)" % json.dumps(lines[0]),
             "UAKWorkspace.t('No technical output yet.')"]
    found = page_js(["isBusy", "statusIcon", "statusTitle"], calls, language="es")
    if found is None:
        return
    icon, heading, ready_icon, fri, sun, shown, doctor, output = found
    assert icon != "✓" and ready_icon == "✓", (icon, ready_icon)
    assert heading == "revisión previa: doctor encontró 2 fallo(s)", heading
    assert fri == "vie 03:30" and sun == "dom 23:59", (fri, sun)
    assert "since the claim" not in shown and "ago" not in shown and shown.startswith("3 "), shown
    assert doctor != lines[0] and output == "Todavía no hay salida técnica.", (doctor, output)
    english = page_js([], ["UAKWorkspace.when('Fri 03:30')"], language="en")
    assert english == ["Fri 03:30"], english


def never_seen_human_is_named(root, tmp):
    import test_setup_team as team
    target, remote = team.ready_project(root, tmp)
    # The person registered the reviewer and has not run anything yet (r3: "20770 d", and ana-r missing).
    team.engine_registers(target, "ana-r", "ana")
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        status, data = tp.get(srv, "/api/dashboard")
    assert status == 200, data
    people = {a["name"]: a for a in data["agents"]}
    assert "ana-r" in people, "the Agents tab lists the registered reviewer: %r" % sorted(people)
    assert people["ana-r"].get("role") == "reviewer" and people["ana-r"]["human"] == "ana", people["ana-r"]
    assert people["ana-r"]["last_seen"] == 0 and not people["ana-r"]["is_human"], people["ana-r"]
    assert people["ana"]["is_human"], "the person who registered it is shown as the human: %r" % people["ana"]
    dash = lib("dash.html")
    agents = dash[dash.index("  function agents(v, d) {"):dash.index("  // Message text:")]
    assert re.search(r'a\.last_seen \? [^:]*ago\(a\.last_seen, d\.generated\)[^:]*: T\("never seen"\)', agents), \
        "a never-seen identity says never seen, not the days since 1970"
    assert re.search(r'a\.role === "reviewer" \? h\("span", \{ "class": "tag", text: T\("reviewer"\) \}\)', agents), \
        "the reviewer is labelled"
    es = catalog()
    assert es.get("never seen") and es.get("reviewer"), "translated"
    # The plan's Approved-By names the same human as the kit's Published-By (r3: Git name vs the page's name).
    (tmp / "plan").mkdir()
    plan_target, plan_remote = tp.project(root, tmp / "plan", name="named plan")
    with tp.live(plan_target, tp.FakePlanner()) as srv:
        plan = tp.planned(srv, plan_target)
        assert tp.post(srv, "/api/human", {"name": "ana"})[0] == 200
        status, body = tp.post(srv, "/api/plan/approve", {"confirm": plan_target.name, "digest": plan["digest"]})
        assert status == 202, body
        tp.wait_idle(srv)
    message = tp.git(plan_target, "log", "-1", "--format=%B", tp.remote_main(plan_remote))
    assert "Approved-By: ana (from the setup page; committed as the local Git identity, unverified)" in message, message
    assert tp.git(plan_target, "log", "-1", "--format=%an", tp.remote_main(plan_remote)) == "Ana Human", \
        "still committed as the local Git identity"
    code_py = lib("setup.py")
    assert code_py.count("(from the setup page; committed as the local Git identity, unverified)") == 1 and \
        re.search(r'signed_line\("Approved-By", ', code_py) and re.search(r'signed_line\("Published-By", ', code_py), \
        "one wording for both lines"


# --- Review of 4af5789 (claude-Dylan-r): one shared word or a fragment must not hide the warning ------------------


def identity_needs_the_whole_name(root, tmp):
    def account(git="", mail="", gh=""):
        return {"git_name": git, "git_email": mail, "gh_login": gh}

    must_warn = [  # (ident, person, which accounts must warn)
        (account("Ana Lopez", "ana.lopez@example.invalid", "ana-lopez"), "mariana", ("git", "gh")),
        (account("Juan Garcia", "juan@example.invalid", "maria-garcia"), "maria-garcia", ("git",)),
        (account("Ana Human", "ana@example.invalid", "banana"), "ana", ("gh",)),
        (account("Ana Human", "ana@example.invalid", "mariana"), "ana", ("gh",)),
        (account("Maria Lopez", "mlopez@example.invalid", "maria"), "maria-garcia", ("git", "gh")),
        (account("Juan Garcia", "juan@example.invalid", "maria-garcia"), "Juan Garcia", ("gh",)),
        (account("Juan Garcia", "jgarcia@example.invalid", "juangarcia"), "mariana", ("git", "gh")),
    ]
    # Review of 3bc4018: an account word that STARTS with the typed (lowercase first) name is the person's own,
    # letters or digits after it allowed; camelCase, digits and separators split words.
    genuine = [
        (account("Dylan", "dylan@example.invalid", "DylanMCDS"), "dylan"),
        (account("Ana", "ana@example.invalid", "AnaLopez"), "ana"),
        (account("ana", "ana@example.invalid", "analopez"), "ana"),
        (account("Luis", "luis@example.invalid", "luisgarcia"), "luis"),
        (account("Luis", "luis@example.invalid", "luisg"), "luis"),
        (account("Ana Lopez", "ana-lopez@example.invalid", "ana-lopez"), "ana"),
        (account("Ana Garcia", "ana_garcia92@example.invalid", "ana_garcia92"), "ana"),
        (account("AnaLopez", "analopez@example.invalid", "AnaLopez"), "ana-lopez"),
        (account("José Pérez", "jperez@example.invalid", "jose"), "jose"),
        (account("Ana García", "ana.garcia@example.invalid", "anagarcia"), "ana-garcia"),
        (account("ana garcia", "ana.garcia@example.invalid", "ana-garcia"), "ana-garcia"),
        (account("Someone Else", "ana.garcia@example.invalid", "ana_garcia92"), "ana-garcia"),
        (account("ANA", "ana@example.invalid", "ana2"), "ana"),
    ]
    found = identity_verdicts([(i, h) for i, h, _ in must_warn] + genuine)
    if found is None:
        return
    for (ident, person, which), verdict in zip(must_warn, found):
        for side in ("git", "gh"):
            assert verdict[side] == (side in which), "%s for %r, %r: %r" % (side, person, ident, verdict)
    for (ident, person), verdict in zip(genuine, found[len(must_warn):]):
        assert not verdict["git"] and not verdict["gh"], "%r carries %r: %r" % (ident, person, verdict)


def progress_line_survives_git_forms(root, tmp):
    es, notes = catalog(), notes_patterns()
    head = "3 commit(s) since the claim · last: "
    lines = [head + "1a2b3c4 fix(ui): the form (1 year, 2 months ago) · 0 uncommitted tracked file(s) · at 1794600000",
             head + "1a2b3c4 " + "x" * 104 + " (5 minu · 1 uncommitted tracked file(s)",
             head + "1a2b3c4 fix the form (2 hours ago) · 0 uncommitted tracked file(s) · at 1794600000",
             head + "- · 0 uncommitted tracked file(s)"]
    for line in lines:
        shown = spanish_of(line, notes, es)
        assert shown, "a Spanish line for %r" % line
        for english in ("since the claim", " ago", "uncommitted", "year", "month", "minu", " at "):
            assert english not in shown, "%r left in %r" % (english, shown)
        assert ("1794600000" in shown) == ("1794600000" in line), "the time stamp is kept: %r" % shown
    assert "1a2b3c4 fix(ui): the form ·" in spanish_of(lines[0], notes, es), "the commit itself is kept"
    found = page_js([], ["UAKWorkspace.t(%s)" % json.dumps(l) for l in lines], language="es")
    if found is not None:
        assert "(hace 2 horas)" in found[2], found[2]
        for shown in found:
            assert "since the claim" not in shown and " ago" not in shown and "minu" not in shown, shown


def one_word_labels_stay_scoped(root, tmp):
    text = lib("workspace.js")
    words = re.search(r"var WORDS = (\[[\s\S]*?\n  \]);", text)
    assert words, "one-word labels live in var WORDS, outside the catalog the body translation reads"
    scoped = [a for a, _ in json.loads(words.group(1))]
    assert {"reviewer", "day", "second", "month"} <= set(scoped), scoped
    found = page_js([], ["[UAKWorkspace.catalog.reviewer, UAKWorkspace.catalog.day, UAKWorkspace.t('reviewer'), "
                         "UAKWorkspace.t('day')]"], language="es")
    if found is not None:
        assert found[0] == [None, None, "revisor", "día"], "not in the body catalog, translated when asked: %r" % found


def retired_reviewer_is_not_listed(root, tmp):
    import test_setup_team as team
    target, _ = team.ready_project(root, tmp)
    team.engine_registers(target, "ana-r", "ana")
    team.retire(target, "ana-r", "ana")
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        status, data = tp.get(srv, "/api/dashboard")
    assert status == 200, data
    listed = [a for a in data["agents"] if a["name"] == "ana-r"]
    assert all(a["status"] == "retired" and a.get("role") != "reviewer" for a in listed), \
        "a retired reviewer is not offered as the reviewer: %r" % listed
    assert not any(a.get("role") == "reviewer" for a in data["agents"]), data["agents"]


def approval_without_a_name_says_git_identity(root, tmp):
    target, remote = tp.project(root, tmp, name="unnamed plan")
    with tp.live(target, tp.FakePlanner()) as srv:
        plan = tp.planned(srv, target)
        status, body = tp.post(srv, "/api/plan/approve", {"confirm": target.name, "digest": plan["digest"]})
        assert status == 202, body
        tp.wait_idle(srv)
    message = tp.git(target, "log", "-1", "--format=%B", tp.remote_main(remote))
    assert "Approved-By: Ana Human (local Git identity, unverified)" in message, message
    assert "from the setup page" not in message, "the Git name never claims to come from the page: %r" % message


def dashboard_survives_a_failed_name_read(root, tmp):
    import test_setup_team as team
    target, _ = team.ready_project(root, tmp)
    team.engine_registers(target, "ana-r", "ana")

    def broken(command, cwd=None, timeout=120, **kwargs):
        if "grep" in command:
            raise OSError("git could not start")
        return wizard.MODULE.run_command(command, cwd=cwd, timeout=timeout)

    with tp.live(target, broken) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        status, data = tp.get(srv, "/api/dashboard")
    assert status == 200 and data.get("agents"), "the dashboard still answers: %r" % data


TESTS = [journey_is_visible_from_welcome, approval_field_says_what_to_type, gate_lines_are_translated,
         advanced_dashboard_is_translated, shared_identity_is_warned, github_login_is_checked_on_its_own,
         accents_do_not_break_the_match, spanish_journey_has_no_english, never_seen_human_is_named,
         identity_needs_the_whole_name, progress_line_survives_git_forms, one_word_labels_stay_scoped,
         retired_reviewer_is_not_listed, approval_without_a_name_says_git_identity, dashboard_survives_a_failed_name_read]


def main():
    global ROOT, MODULE
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    ROOT = args.package.resolve()
    spec = importlib.util.spec_from_file_location("guide_setup", ROOT / ".uak/bin/lib/setup.py")
    MODULE = wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MODULE)
    spec = importlib.util.spec_from_file_location("guide_planning", ROOT / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-guide-"))
        started = time.monotonic()
        try:
            test(ROOT, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s: %s)" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_GUIDE_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
