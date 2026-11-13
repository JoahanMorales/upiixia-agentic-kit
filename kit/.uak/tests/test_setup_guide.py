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
    shown = set()
    for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', code):
        if lit.startswith("uak ") or not re.match(r"[A-Za-z]", lit) or not re.search(r"[A-Za-z]{3,}", lit) or re.search(r"[{}=;<>()$/]|\.(md|py|sh|js)\b", lit):
            continue
        if set(lit.split()) <= classes or not (" " in lit.strip() or re.fullmatch(r"[A-Z][a-z]+", lit)):
            continue
        shown.add(lit)
    left = sorted(l for l in shown if l not in es and l.strip() not in es and l not in ("None",))
    assert not left, "dashboard labels with no Spanish: %r" % left
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
            status, body, _ = wizard.request(srv, "GET", "/api/status")
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
    es = catalog()
    for needle in ("Commits will be signed as {git} and pull requests opened as {gh}.",
                   "This looks like someone else's identity. If this is not your computer, set your own before publishing: git config user.name and user.email, and gh auth login."):
        assert needle in es, "%r is translated" % needle


TESTS = [journey_is_visible_from_welcome, approval_field_says_what_to_type, gate_lines_are_translated,
         advanced_dashboard_is_translated, shared_identity_is_warned]


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
