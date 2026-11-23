#!/usr/bin/env python3
"""UI-021 (absorbs UI-022): the setup page speaks plain Spanish all the way.
Evidence: QA rounds of 2026-11-14 (notes/handoff:qa/rounds-2026-11-14): A-F10 ("the kit's GitHub", the update command,
"Nada que probar primero: no (static …)", plan titles and tests in English for a Spanish idea), B-11 (FREEZE line, git
ls-remote hint, CLAIMED, human, publish refusals), D-4.1 (English in the Spanish UI: gate lines, violation list, raw git
stderr when offline with a misleading "check your connection", native validation bubbles), D-2.1/2.2/2.4 (jargon for
novices, ustedes/tú mix), A-F20 (one control with three labels).
The Spanish catalog is workspace.js; this file reads it as data and applies it the way the page does (gate() for a
check's first line, t() for everything else). Real HTTP and real Git for the git failures; no browser."""
import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import test_setup_planning as tp
import test_setup_wizard as wizard

ROW = re.compile(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]')
# Words that only an English sentence has; a command or a path never needs them.
ENGLISH = re.compile(r"\b(the|and|has|then|keeps|your|when|must|blocking|purpose|after|needs|waits|offered|here|stay|"
                     r"agrees|CLAIMED|BLOCKED|fatal|could not|cannot)\b")
# Every refusal setup.py and planning.py can send to the page: these classes and the "error" of a reply.
REFUSALS = {"ValueError", "Need", "WayOut", "Conflict", "FieldError", "GitFailure"}


def lib(name):
    return Path(wizard.MODULE.__file__).with_name(name)


class Catalog:
    """workspace.js as data: the exact pairs, the NOTES patterns, the gate's patterns and the one-word labels."""

    def __init__(self):
        text = lib("workspace.js").read_text(encoding="utf-8")

        def table(name):
            start = text.index("var %s = [" % name)
            return [(json.loads(a), json.loads(b)) for a, b in ROW.findall(text[start:text.index("\n  ];", start)])]

        self.notes, self.gates, self.words = table("NOTES"), table("GATE"), dict(table("WORDS"))
        self.es = dict((json.loads(a), json.loads(b)) for a, b in ROW.findall(text[:text.index("var NOTES = [")]))
        self.text = text

    def sub(self, template, match):
        return re.sub(r"\$(\d)", lambda m: self.word(match.group(int(m.group(1))) or ""), template)

    def word(self, value):
        return self.es.get(value) or self.words.get(value) or value

    def t(self, text):
        """The page's UAKWorkspace.t in Spanish: an exact entry, a one-word label, or a NOTES pattern."""
        if text in self.es:
            return self.es[text]
        if text in self.words:
            return self.words[text]
        for pattern, template in self.notes:
            match = re.fullmatch(pattern, text)
            if match:
                return self.sub(template, match)
        return text

    def gate(self, line):
        """UAKWorkspace.gate in Spanish: the gate's line, its values through the catalog too."""
        number = re.match(r"\d+\.\s+", line)
        number = number.group(0) if number else ""
        rest = line[len(number):]
        for pattern, template in self.gates:
            match = re.fullmatch(pattern, rest)
            if match:
                return number + self.sub(template, match)
        return line

    def known(self, text):
        return self.t(text) != text or text in self.es


def english(text):
    found = ENGLISH.search(text)
    return found.group(0) if found else ""


def sample(node):
    """A refusal's message with a sample value in place of each %s/%d, or None when it is not a literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        left = sample(node.left)
        return None if left is None else re.sub(r"%[sdr]", "x", left).replace("%%", "%")
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = sample(node.left), sample(node.right)
        return None if left is None or right is None else left + right
    return None


def refusal_messages(path):
    """Each literal message a refusal class gets, and each literal "error"/"note"/"message" of a reply dict."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) in REFUSALS \
                and node.args:
            text = sample(node.args[0])
            if text is not None:
                found.append((node.lineno, text))
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value in ("error", "note", "message"):
                    text = sample(value)
                    if text:
                        found.append((node.lineno, text))
    return found


def page():
    return lib("setup.html").read_text(encoding="utf-8")


# --- the four named tests of UI-021's language half ------------------------------------------------------------------


def spanish_page_has_no_engine_english(root, tmp):
    cat = Catalog()
    # (1) Every refusal setup and the planning module can send has Spanish (publish refusals among them, B-11).
    missing = ["%s:%d %s" % (name, line, text[:120]) for name in ("setup.py", "planning.py")
               for line, text in refusal_messages(lib(name)) if not cat.known(text)]
    assert not missing, "%d refusal(s) with no Spanish:\n  %s" % (len(missing), "\n  ".join(missing))
    # (2) The engine lines the QA rounds saw in English inside the Spanish page, as the page draws them.
    gates = [
        "2. update the kit: this project has uak 6.2.0 and the kit's GitHub has 6.3.0",
        "reviews: no reviewer is registered, so the first PR waits until a second agent holds a claim. Working alone? "
        "Register one from this checkout: UAK_HUMAN=<you> UAK_AGENT= bash .uak/bin/uak register-reviewer <you>-r, and "
        "a second session as <you>-r runs /uak-review.",
    ]
    for line in gates:
        shown = cat.gate(line)
        assert shown != line and not english(shown), "gate line still English (%r): %r" % (english(shown), shown)
    hints = [
        "not blocking: this project already works on uak 6.2.0; update when the team agrees",
        "git -C /Users/ana/.uak-kit pull --ff-only, then bash /Users/ana/.uak-kit/install.sh --mode sprint --update .   "
        "(keeps PROJECT.md, TASKS.md and OWNERS.md; commit and push it)",
        "bash '/Users/ana/my kit'/install.sh --mode marathon --update .   (keeps PROJECT.md, TASKS.md and OWNERS.md; "
        "commit and push it)",
        "to stay on 6.2.0 on purpose: UAK_KIT_PIN=1 uak start",
        "git ls-remote origin must work: check credentials (gh auth login) or the network",
        "git remote add origin <URL of the empty GitHub repo>",
        "open your agent here and run /uak-plan (it publishes with uak plan on claims; no PR)",
        "open your agent here and run /uak-plan, then push TASKS.md to main",
        "set Autonomy: yes in .uak/PROJECT.md and push it to main",
        "you are the human: read the backlog (uak graph, or .uak/TASKS.md plus what uak plan published), set "
        "Backlog-Approved: yes in .uak/PROJECT.md, push it to main",
        "commit them, then merge feature-x into main and push main",
        "· FREEZE in 27 min: finish the criterion and run uak done, or release; after the freeze a task needs a human "
        "uak allow.",
        "FREEZE: APP-002 is not allowed after the freeze (human: uak allow APP-002 --reason TEXT)",
        "· Waiting on dependencies: 2 task(s); HACK-003 waits on HACK-002 (CLAIMED).",
    ]
    for line in hints:
        shown = cat.t(line)
        assert shown != line and not english(shown), "engine line still English (%r): %r" % (english(shown), shown)
    for token in ("CLAIMED", "BLOCKED", "REVIEW", "human", "all"):
        assert cat.word(token) != token, "the token %s has a Spanish label" % token
    # (3) "Nada que probar primero: no (static …)": no double negative on the plan cards.
    html = page()
    assert "Nothing to test first:" not in html, "the plan card's Test-First label is not a double negative"
    assert re.search(r'UAKWorkspace\.t\("Tests first:"\)', html) and "Tests first:" in cat.es
    # (4) Tú throughout: no ustedes or vosotros in the Spanish column.
    plural = re.compile(r"\b(ustedes|vosotros|revisen|elijan|escriban|pulsen|abran|copien|ejecuten|guarden|pidan|"
                        r"esperen|confirmen|registren|publiquen|cambien|sigan|tomen|hagan|aprueben|instalen|"
                        r"configuren|agreguen|quiten|eliminen|sepan|vean)\b", re.I)
    spanish = list(cat.es.values()) + [t for _, t in cat.notes + cat.gates]
    mixed = [t for t in spanish if plural.search(t)]
    assert not mixed, "ustedes in the Spanish page: %r" % mixed[:5]
    # (5) Beginner view explains the jargon it shows: a glossary, every term with its Spanish.
    glossary = re.search(r'<details[^>]*id="glossary"[^>]*>([\s\S]*?)</details>', html)
    assert glossary and "beginner-only" in glossary.group(0)[:200], "a glossary in the beginner view"
    terms = re.findall(r"<dt>\s*<dfn>([^<]+)</dfn>\s*</dt>\s*<dd>([^<]+)</dd>", glossary.group(1))
    named = {t.strip().lower() for t, _ in terms}
    for word in ("lint", "worktree", "wave", "mcp", "freeze", "origin", "claim", "pr"):
        assert word in named, "the glossary explains %s: %r" % (word, sorted(named))
    for term, meaning in terms:
        text = " ".join(meaning.split())
        assert text in cat.es, "no Spanish for the glossary entry %r" % text
    assert re.search(r'\.beginner-only\s*\{[^}]*display:\s*none', html) and \
        re.search(r'body\[data-profile="beginner"\]\s*\.beginner-only\s*\{', html), "the glossary is the beginner's"


def git_failures_are_plain(root, tmp):
    """D-4.1: the page showed "fatal: '…/gone.git' does not appear to be a git repository …" with "check your
    connection"; each common failure is one plain sentence with the right advice, git's words under Technical details."""
    module, cat = wizard.MODULE, Catalog()
    done = subprocess.CompletedProcess
    cases = {
        "repo": done([], 128, "", "fatal: '/tmp/x/gone.git' does not appear to be a git repository\nfatal: Could not "
                                  "read from remote repository.\n\nPlease make sure you have the correct access rights\n"
                                  "and the repository exists.\n"),
        "missing": done([], 128, "", "remote: Repository not found.\nfatal: repository "
                                     "'https://github.com/ana/app.git/' not found\n"),
        "auth": done([], 128, "", "fatal: could not read Username for 'https://github.com': terminal prompts disabled\n"),
        "key": done([], 255, "", "git@github.com: Permission denied (publickey).\r\nfatal: Could not read from remote "
                                 "repository.\r\n"),
        "dns": done([], 128, "", "fatal: unable to access 'https://github.com/ana/app.git/': Could not resolve host: "
                                 "github.com\n"),
        "timeout": done([], 124, "", ""),
        "slow": done([], 128, "", "fatal: unable to access 'https://github.com/ana/app.git/': Failed to connect to "
                                  "github.com port 443 after 21002 ms: Timed out\n"),
    }
    assert hasattr(module, "git_failure"), "setup turns a failed network Git into a plain sentence"
    seen = {}
    for name, result in cases.items():
        failure = module.git_failure(result)
        reason, advice, technical = failure["reason"], failure["advice"], failure["technical"]
        seen[name] = reason
        for text in (reason, advice):
            assert text and "fatal" not in text and "github.com" not in text and "/tmp/x" not in text, (name, failure)
            assert text in cat.es, "no Spanish for %r" % text
        assert "connection" not in advice or name in ("dns", "timeout", "slow"), \
            "only a network failure says to check the connection: %r" % failure
        if result.stderr:
            assert result.stderr.strip().splitlines()[0].strip() in technical, "git's own words stay in technical"
    assert seen["repo"] == seen["missing"] and seen["auth"] == seen["key"] and seen["timeout"] == seen["slow"], seen
    assert len({seen["repo"], seen["auth"], seen["dns"], seen["timeout"]}) == 4, "four different plain sentences"
    # The real thing: a remote that is gone, through POST /api/plan (a refusal) and GET /api/plan (a note).
    target, remote = tp.project(root, tmp)
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        assert tp.post(srv, "/api/idea", tp.idea_fields())[0] == 200
        tp.git(target, "remote", "set-url", "origin", str(tmp / "gone.git"))
        status, body = tp.post(srv, "/api/plan", {"harness": "claude"})
        assert status == 400 and body["error"].startswith("Could not reach origin: "), body
        assert "fatal" not in body["error"] and "gone.git" not in body["error"], body
        assert "gone.git" in body.get("technical", ""), "git's message is kept for Technical details: %r" % body
        shown = cat.t(body["error"])
        assert shown != body["error"] and not english(shown), shown
        plan = tp.get(srv, "/api/plan")[1]
        note = plan.get("remote_note", "")
        assert note.startswith("Could not reach origin") and "fatal" not in note, plan
        assert "gone.git" in plan.get("remote_technical", ""), plan
        assert cat.t(note) != note and not english(cat.t(note)), cat.t(note)
    html = page()
    assert re.search(r"function technical\(", html) and "Technical details" in html, "the page has Technical details"
    assert re.search(r"e\.body\s*&&\s*e\.body\.technical", html), "a refusal's technical text is shown under it"
    assert "remote_technical" in html and "view.technical" in html, "the plan and team notes show theirs"


def planner_follows_the_idea_language(root, tmp):
    """A-F10: a Spanish idea got a plan with English titles, criteria and test names."""
    planning = tp.PLANNING
    prompt = planning.PLANNER_PROMPT
    assert re.search(r"language", prompt, re.I) and "IDEA.md" in prompt, prompt
    said = re.search(r"[^.]*\blanguage\b[^.]*\.", prompt).group(0)
    for part in ("title", "criteria", "test"):
        assert part in said, "the language rule covers %s: %r" % (part, said)
    assert re.search(r"Spanish idea[^.]*Spanish", prompt), "an example makes the rule concrete: %r" % said
    # The prompt stays one line that a Windows .cmd shim passes untouched (the module's own rule).
    assert not re.search(r'[%^&|<>"`\n\r]', prompt), "a character a .cmd shim or a shell would change"
    for harness in ("claude", "codex"):
        argv = planning.planner_command(harness, tmp, binary="/fake/bin/" + harness)
        assert any(prompt in a for a in argv), "the %s run gets the prompt" % harness
    # IDEA.md keeps the person's words as they wrote them (the planner reads the language from there).
    target, _ = tp.project(root, tmp)
    text = planning.save_idea(target, {"idea": "una fila virtual para la cafetería", "audience": "estudiantes",
                                       "rubric": "impacto 40 %", "event_length": "3 h", "team_size": 2}, "sprint")
    assert "una fila virtual para la cafetería" in text and "estudiantes" in text, text


def one_label_per_action(root, tmp):
    """A-F20 and D top 9: "View" on the screen, "Interface profile" for a screen reader; the theme had no visible label."""
    html, cat = page(), Catalog()
    labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', html))
    both = []
    for tag in re.finditer(r"<(input|select|textarea|button)\b([^>]*)>", html):
        found = re.search(r'\bid="([^"]+)"', tag.group(2))
        if found and found.group(1) in labelled and "aria-label=" in tag.group(2):
            both.append(found.group(1))
    assert not both, "a control with a visible label and a different aria-label: %r" % both
    for select in re.findall(r'<select\b[^>]*\bid="([^"]+)"', html):
        assert select in labelled, "#%s has a visible label" % select
    assert re.search(r'<label[^>]*for="profile"[^>]*>\s*View\s*</label', html), "one name for the profile control"
    assert re.search(r'<label[^>]*for="workspace-theme"[^>]*>\s*Theme\s*</label', html), "the theme says what it is"
    assert "Interface profile" not in re.sub(r"<script[\s\S]*?</script>", "", html), "no second name for View"
    # One label per action: a button keeps the name its step gives it, in both languages.
    for name in ("View", "Theme", "Save name", "Save schedule", "Save the idea"):
        assert name in cat.es, "%s has its Spanish" % name


TESTS = [spanish_page_has_no_engine_english, git_failures_are_plain, planner_follows_the_idea_language,
         one_label_per_action]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    for key in [k for k in os.environ if k.startswith("UAK_")]:  # UAK_BASE/UAK_REMOTE would change the server's base
        del os.environ[key]
    spec = importlib.util.spec_from_file_location("language_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("language_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-language-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("SETUP_LANGUAGE_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
