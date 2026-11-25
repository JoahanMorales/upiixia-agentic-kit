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


# --- UAK-160: the page's Spanish is written, not translated from the engine's sentences -------------------------------
# The engine (`uak start`) says what each check is as a code with its values; workspace.js owns the sentence in each
# language. These tests read the real engine, the real catalog and the real page; the page's sentences are rendered by
# the catalog's own functions in Node (CI has it) and the screens are read in Chromium when Playwright is here.
import shutil
import sys

import test_setup_guide as guide

BIN = None  # the package's .uak/bin, set in main()
KIT_URL = "https://github.com/JoahanMorales/upiixia-agentic-kit"


def workspace_json(name):
    """GLOSSARY or CODES of workspace.js, read as JSON (the file says: no comments inside them)."""
    text = lib("workspace.js").read_text(encoding="utf-8")
    found = re.search(r"var %s = (\{[\s\S]*?\n  \});" % name, text)
    assert found, "workspace.js defines var %s = {...}" % name
    return json.loads(found.group(1))


def node_catalog(calls, language="es"):
    """The catalog's own functions run in Node: UAKWorkspace.code(...), .t(...) in `language`; None without Node."""
    node = shutil.which("node")
    if not node:
        print("  note: no Node.js here, so the catalog's functions are checked by reading it only")
        return None
    with tempfile.TemporaryDirectory(prefix="uak-lang-js-") as folder:
        program = Path(folder) / "run.js"
        program.write_text(guide.NODE_PROGRAM, encoding="utf-8")
        done = subprocess.run([node, str(program)], input=json.dumps({"language": language, "sources": [lib("workspace.js").read_text(encoding="utf-8")],
                                                                      "calls": calls}),
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, "the catalog runs in Node: %s" % done.stderr[-1500:]
    return json.loads(done.stdout)


def git_env(tmp):
    """A Git that never reaches the network: the kit's GitHub address is an empty local repository."""
    empty = tmp / "kit-github.git"
    if not empty.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(empty)], check=True)
    config = tmp / "gitconfig"
    config.write_text("[user]\n\tname = T\n\temail = t@example.invalid\n[url \"%s\"]\n\tinsteadOf = %s\n"
                      % (empty.as_posix(), KIT_URL), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("UAK_", "GIT_"))}
    env.update(GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0", LC_ALL="C",
               PYTHONDONTWRITEBYTECODE="1")
    return env


def run_start(cwd, tmp, extra=None, script=None, codes=True):
    """`start` (the package's, or a reworded copy) in `cwd`; returns (exit code, output)."""
    env = git_env(tmp)
    if codes:
        env["UAK_START_CODES"] = "1"
    env.update(extra or {})
    from test_hack import resolve_binary
    done = subprocess.run([resolve_binary("bash"), Path(script or BIN / "start").as_posix()], cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=240)
    return done.returncode, done.stdout


def repo(tmp, name, installed=True, remote=None, freeze=False):
    d = tmp / name
    d.mkdir()
    env = git_env(tmp)
    subprocess.run(["git", "init", "-q", "-b", "main", str(d)], check=True, env=env)
    if installed:
        (d / ".uak").mkdir()
        (d / ".uak/PROJECT.md").write_text("Mode: sprint\nAutonomy: yes\n%s" % ("Freeze-Epoch: 1\n" if freeze else ""), encoding="utf-8")
    if remote:
        subprocess.run(["git", "-C", str(d), "remote", "add", "origin", remote], check=True, env=env)
    return d


def kit_home(tmp, version):
    d = tmp / ("kit-" + version)
    (d / "kit/.uak").mkdir(parents=True)
    (d / "kit/.uak/VERSION").write_text(version + "\n", encoding="utf-8")
    (d / "install.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    return d


def scenarios(tmp):
    """Real runs of the engine that reach every kind of check the first screens show: (name, exit code, output)."""
    own = (BIN.parent / "VERSION").read_text(encoding="utf-8").strip()
    major, minor, patch = (int(n) for n in own.split("."))
    out = []
    plain = tmp / "plain"
    plain.mkdir()
    out.append(("not a repository",) + run_start(plain, tmp))
    out.append(("not installed",) + run_start(repo(tmp, "bare", installed=False), tmp))
    out.append(("no remote",) + run_start(repo(tmp, "noremote"), tmp))
    out.append(("remote unreachable",) + run_start(repo(tmp, "gone", remote=str(tmp / "gone.git")), tmp))
    live = tmp / "live.git"
    subprocess.run(["git", "init", "-q", "--bare", str(live)], check=True)
    out.append(("remote reachable, kit not published",) + run_start(repo(tmp, "reach", remote=str(live)), tmp))
    out.append(("a newer major version",) + run_start(
        repo(tmp, "major", freeze=True), tmp, {"UAK_KIT_HOME": str(kit_home(tmp, "%d.0.0" % (major + 1)))}))
    out.append(("a newer minor version",) + run_start(
        repo(tmp, "minor", freeze=True), tmp, {"UAK_KIT_HOME": str(kit_home(tmp, "%d.%d.0" % (major, minor + 1)))}))
    return out


def code_lines(output):
    return [json.loads(line[5:]) for line in output.splitlines() if line.startswith("CODE {")]


def placeholders(template):
    return sorted(set(re.findall(r"\{([a-z]+)", template)))


def start_codes():
    """Every code the engine can say: the H calls of start (the dynamic names written out) plus its READY codes."""
    source = (BIN / "start").read_text(encoding="utf-8")
    names = set(re.findall(r'\b(?:C|HC|spec) "?([a-z][a-z_]+)(?=[ ";)\n]|$)', source))
    names |= {"update_kit_github", "update_kit_clone", "update_command", "update_pull_command", "push_command",
              "push_command_branch", "ready_claim", "ready_hold"}
    names -= {"update_kit_", "update", "push_command_", "update_command_", "push_command"} - {"push_command"}
    return names, source


def texts_are_keyed_by_code(root, tmp):
    codes = workspace_json("CODES")
    used, source = start_codes()
    missing = sorted(used - set(codes))
    assert not missing, "codes the engine says that the catalog has no text for: %r" % missing
    dead = sorted(set(codes) - used)
    assert not dead, "texts for codes the engine never says: %r" % dead
    # Every check and every line under it goes through H (a code); a bare string would reach the page as prose only.
    lines = source.splitlines()
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#") or re.match(r"(ok|need|note)\(\)", stripped):
            continue
        if re.search(r'(?<![\w$-])(ok|need|note) "', line):
            near = " ".join(lines[max(0, number - 5):number])
            assert re.search(r'(?:^|[;{ ])C "?[a-z$]', near), "start line %d says a check with no code: %s" % (number, stripped[:120])
    # The real engine, in every situation the first screens show: each CODE line has text in both languages and the
    # values its sentence needs; the prose line above it is the same check.
    seen = set()
    for name, rc, output in scenarios(tmp):
        lines = code_lines(output)
        assert lines, "%s: the engine said no codes:\n%s" % (name, output[-600:])
        prose = [l for l in output.splitlines() if re.match(r"(OK|TODO|NOTE)\s", l)]
        checks = [l for l in lines if l["state"] in ("ok", "todo", "note")]
        assert len(prose) == len(checks), "%s: a CODE line for each check: %r vs %r" % (name, prose, checks)
        for line in lines:
            for item in ([line["check"]] if "check" in line else []) + line["hints"]:
                code = item["code"]
                seen.add(code)
                assert code in codes, "%s: code %r has no text" % (name, code)
                for language in ("en", "es"):
                    need = placeholders(codes[code][language])
                    absent = [k for k in need if k not in item["values"] and k not in ("count",)]
                    assert not absent, "%s: %s needs %r in %s, the engine gave %r" % (name, code, absent, language, item["values"])
    assert {"no_git_repository", "install_kit", "kit_installed", "remote_missing", "remote_unreachable", "remote_reachable",
            "push_kit", "update_kit_clone", "update_major", "update_command", "not_blocking_update"} <= seen, sorted(seen)
    # The setup module reads them: a check keeps its prose for the technical details and gains its code and values.
    module = wizard.MODULE
    _, output = run_start(repo(tmp, "readiness", remote=str(tmp / "gone2.git")), tmp)
    state = module.readiness(output, 1)
    todo = [c for c in state["checks"] if c["state"] == "todo"][0]
    assert todo["code"] == "remote_unreachable" and todo["values"]["remote"] == "origin", todo
    assert todo["hints"][0]["code"] == "remote_ls_remote" and "ls-remote" in todo["text"], todo
    # What does not look like a code is dropped, never trusted.
    for bad in ('CODE {"state":"todo","check":{"code":"Bad Code","values":{}}}', 'CODE {"state":"todo","check":{"code":"ok","values":{"a":1}}}',
                'CODE not json', 'CODE {"state":"todo","check":{"code":"x","values":[]}}', 'CODE []'):
        checked = module.readiness("TODO  1. a thing\n" + bad + "\n", 1)["checks"][0]
        assert "code" not in checked or checked["code"] == "ok" and checked["values"] == {}, (bad, checked)
    # The page draws a coded check from its code (the catalog), the others as before.
    html = page()
    assert re.search(r"check\.code\s*\?\s*\[UAKWorkspace\.code\(check\.code, check\.values \|\| \{\}\)\]\.concat\(\(check\.hints \|\| \[\]\)\.map\(", html), \
        "the checklist writes a coded check and its lines from their codes"
    assert re.search(r"g\.code \? UAKWorkspace\.code\(g\.code, g\.values \|\| \{\}\)", html), \
        "the heading of the next step is written from the code"
    assert "UAKWorkspace.code(" in html and "completed_items" in html


def rewording_the_engine_changes_nothing(root, tmp):
    module = wizard.MODULE
    base = repo(tmp, "reworded", remote=str(tmp / "gone3.git"))
    plain = repo(tmp, "reworded-major", freeze=True)
    # (1) The engine's own sentences reworded in a copy of start: the codes and values are the same, the prose is not.
    copy = tmp / "kit-copy/.uak/bin"
    shutil.copytree(str(BIN), str(copy), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(str(BIN.parent / "VERSION"), str(copy.parent / "VERSION"))
    source = (copy / "start").read_text(encoding="utf-8")
    words = {"install the kit": "set the kit up first", "a remote named $remote": "no remote called $remote exists",
             "git remote add $remote <URL of the empty GitHub repo>": "run git remote add $remote with your URL",
             "reach $remote ($url)": "$remote does not answer ($url)",
             "update the kit: this project has uak": "newer kit available, you have uak",
             "a new major version: it blocks until the kit is updated": "major upgrade, blocking",
             "git ls-remote $remote must work: check credentials (gh auth login) or the network": "fix your network or login"}
    for old, new in words.items():
        assert old in source, "the sentence to reword is still in start: %r" % old
        source = source.replace(old, new)
    (copy / "start").write_text(source, encoding="utf-8")
    env = {"UAK_KIT_HOME": str(kit_home(tmp, "99.0.0"))}
    for project in (base, plain):
        rc1, original = run_start(project, tmp, env if project is plain else None)
        rc2, reworded = run_start(project, tmp, env if project is plain else None, script=copy / "start")
        assert rc1 == rc2 and code_lines(original) == code_lines(reworded), (code_lines(original), code_lines(reworded))
        prose = lambda text: [l for l in text.splitlines() if not l.startswith("CODE ")]
        assert prose(original) != prose(reworded), "the copy really says other words"
        a, b = module.readiness(original, rc1), module.readiness(reworded, rc2)
        key = lambda s: [(c["state"], c.get("code"), c.get("values"), [(h.get("code"), h.get("values")) for h in c.get("hints", [])])
                         for c in s["checks"]]
        assert key(a) == key(b) and key(a), "the page's view of the checks is the same: %r %r" % (key(a), key(b))
        assert [c["text"] for c in a["checks"]] != [c["text"] for c in b["checks"]], "only the prose to technical details differs"
        # What the page decides from the checks does not read the prose either.
        state = dict(installed=True, phase="setup", ready=False, target=str(project))
        ga, gb = (module.guidance(dict(state, checks=s["checks"])) for s in (a, b))
        pick = lambda g: (g["kind"], g.get("code"), g.get("values"), g.get("action"), [(i["code"], i["values"]) for i in g.get("items", [])])
        assert pick(ga) == pick(gb), (pick(ga), pick(gb))
        # And the Spanish the person reads is the same, word for word.
        shown = lambda s: [node_catalog(["UAKWorkspace.code(%s, %s)" % (json.dumps(c["code"]), json.dumps(c["values"]))])
                           for c in s["checks"] if c.get("code")]
        assert shown(a) == shown(b), "the page's Spanish does not depend on the engine's sentence"
    # (2) Without Node the same holds for the text the catalog builds from a code: a template and its values only.
    sentences = [(c["code"], c["values"]) for c in module.readiness(run_start(base, tmp)[1], 1)["checks"] if c.get("code")]
    assert sentences, "the fixture has coded checks"
    # (3) A check with no code (an older kit's `uak start`) still works, from its text: nothing is lost on an older kit.
    old = module.readiness("OK    1. kit installed (sprint, uak 6.2.0)\nTODO  2. a remote named origin\n         git remote add origin <URL of the empty GitHub repo>\n", 1)
    assert [c["state"] for c in old["checks"]] == ["ok", "todo"] and "code" not in old["checks"][0], old
    guide_old = module.guidance(dict(installed=True, phase="setup", ready=False, target="/x", checks=old["checks"]))
    assert guide_old["kind"] == "todo" and "code" not in guide_old and guide_old["title"] == "a remote named origin", guide_old


def no_missing_text_in_either_language(root, tmp):
    codes, cat = workspace_json("CODES"), Catalog()
    # Both languages, every code, the same placeholders in both: a missing one is a failure, never English in Spanish.
    for name, entry in codes.items():
        assert set(entry) == {"en", "es"} and entry["en"].strip() and entry["es"].strip(), "%s has both languages" % name
        assert placeholders(entry["en"]) == placeholders(entry["es"]), "%s: the same values in both languages" % name
        assert entry["en"] != entry["es"] or "{line:t}" in entry["en"] or entry["en"].startswith("Run:"), name
        assert entry["es"].count("[[") == entry["es"].count("]]") and entry["es"].count("{") == entry["es"].count("}"), name
    # A duplicated English key with two different Spanish texts: the last one silently wins.
    seen = {}
    for english, spanish in re.findall(ROW, lib("workspace.js").read_text(encoding="utf-8").split("var NOTES = [")[0].split("var pairs = [")[1]):
        english, spanish = json.loads(english), json.loads(spanish)
        assert spanish.strip(), "empty Spanish for %r" % english
        assert seen.setdefault(english, spanish) == spanish, "two Spanish texts for %r: %r and %r" % (english, seen[english], spanish)
    # The catalog's functions, run for real: every code in both languages with sample values, an unknown code, a missing
    # value, singular and plural, and names with regex characters; never blank, never "undefined", never a template.
    names = sorted(codes)
    sample = {"mode": "sprint", "version": "6.8.0", "mine": "6.7.0", "newest": "6.8.0", "where": "/home/ana/kit (v1)",
              "remote": "origin", "url": "https://github.com/ana/tienda-api", "count": "2", "base": "main", "files": ".uak/PROJECT.md",
              "tasks": "3", "command": "git add -A", "id": "APP-001", "state": "CLAIMED", "title": "Pagos $1 (.*) [a-z]",
              "install": "bash install.sh", "pull": "git pull --ff-only", "clone": "git clone x y", "branch": "feat/x",
              "line": "FAIL core.hooksPath is not set", "worktree": "/w/APP-001"}
    for language in ("en", "es"):
        rendered = node_catalog(["UAKWorkspace.code(%s, %s)" % (json.dumps(n), json.dumps(sample)) for n in names] +
                                ["UAKWorkspace.code('no_such_code', {})", "UAKWorkspace.code('__proto__', {})",
                                 "UAKWorkspace.code('kit_on_main', {remote: 'origin', base: 'main', version: ''})",
                                 "UAKWorkspace.code('kit_on_main', {remote: 'origin', base: 'main', version: '6.8.0'})",
                                 "UAKWorkspace.code('preflight_failures', {count: '1'})", "UAKWorkspace.code('preflight_failures', {count: '2'})",
                                 "UAKWorkspace.code('plan_ok', {tasks: '1'})", "UAKWorkspace.code('plan_ok', {tasks: '12'})",
                                 "UAKWorkspace.code('first_task', {id: 'APP-001', title: '$& $1 (a|b)* \\\\d'})",
                                 "UAKWorkspace.code('first_task', {id: 'APP-001'})",
                                 "UAKWorkspace.code('remote_reachable', {})"], language)
        if rendered is None:
            break
        *known, nope, proto, no_version, with_version, one, two, plan_one, plan_many, tricky, no_title, empty = rendered
        for name, text in zip(names, known):
            assert text and "{" not in text and "undefined" not in text and "[[" not in text, (language, name, text)
        fallback = {"en": "This check has no description", "es": "Esta comprobación no tiene descripción"}[language]
        assert nope.startswith(fallback) and proto.startswith(fallback), "an unknown code is said, never blank: %r %r" % (nope, proto)
        assert "(uak" not in no_version and "(uak 6.8.0)" in with_version, (no_version, with_version)
        assert ("1 fallo" in one and "2 fallos" in two) if language == "es" else ("1 failure" in one and "2 failures" in two), (one, two)
        assert ("1 tarea," in plan_one and "12 tareas," in plan_many) if language == "es" else ("1 task," in plan_one and "12 tasks," in plan_many), (plan_one, plan_many)
        assert "$& $1 (a|b)* \\d" in tricky and "APP-001" in tricky, "a task title is data, never read as a pattern: %r" % tricky
        assert "()" not in no_title and "APP-001" in no_title, no_title
        assert "undefined" not in empty and "{" not in empty, empty
    # What a person reads in Spanish never carries the engine's English sentence for a coded check.
    for name, entry in codes.items():
        spanish = entry["es"]
        assert not english_left(spanish), "%s: English in the Spanish sentence: %r" % (name, english_left(spanish))
    # Every screen of the page, as it is written: each text, in Spanish, has no English left (static and dynamic).
    html = page()
    for screen_id, texts in screen_texts(html).items():
        left = [(t, english_left(cat.es.get(t, t))) for t in texts if english_left(cat.es.get(t, t))]
        assert not left, "screen %s has English in Spanish: %r" % (screen_id, left[:6])
    code = guide.script(html)
    literals = set(re.findall(r'UAKWorkspace\.(?:t|format)\(\s*"([^"]{2,})"', code))
    absent = sorted(l for l in literals if english_left(cat.es.get(l, l)) and l not in cat.es)
    assert not absent, "page sentences with no Spanish: %r" % absent[:8]
    # The skill field is marked invalid when its name is refused, and read with the message (UAK-192 review).
    assert re.search(r'if \(local\.field\) \{ input\.setAttribute\("aria-invalid", "true"\); input\.setAttribute\("aria-describedby", "run-status-"', html) \
        and 'status.id = "run-status-"' in html and 'field: !!(e.body && e.body.field === "name")' in html, "the skill field says it is invalid"
    # The panel's task drawer reads in Spanish: its texts are plain text nodes the catalog translates.
    for text in ("Owner", "Rounds", "Moves", "Claimed", "Who took part", "Every move, in order", "PLANNED", "AMENDED",
                 "waiting to be claimed", "Review: approved, waiting for a human merge", "Reviews file history"):
        assert cat.es.get(text) and cat.es[text] != text, "the drawer's %r has Spanish" % text
    browser_screens(root, tmp)


def english_left(text):
    """The English words of a Spanish sentence outside what the glossary keeps, quoted text, commands and values."""
    glossary = workspace_json("GLOSSARY")
    keep = set(glossary["keep"])
    if not ENGLISH_WORDS:
        cat = Catalog()
        ENGLISH_WORDS.append(set(w.lower() for a in list(cat.es) + [c["en"] for c in workspace_json("CODES").values()]
                                 for w in re.findall(r"[A-Za-z]{3,}", re.sub(r"\{[^}]*\}", "", a))))
    vocabulary = ENGLISH_WORDS[0]
    text = re.sub(r"«[^»]*»|\"[^\"]*\"|`[^`]*`", " ", text)
    text = re.sub(r"\b(git|uak|bash|gh|npm|node|winget|brew|cd|python3?)\b( +[-\w./<>|=:~$*'\"\\@]+)*", " ", text)
    text = re.sub(r"\{[^}]*\}|\$\d", " ", text)
    found = []
    for token in text.split():
        if re.search(r"[/._\-0-9:=<>$\\()@#|+*]", token):
            continue
        for word in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñÑüÜ]{3,}", token):
            if word.lower() in vocabulary and word.lower() not in keep and word.lower() not in COGNATES:
                found.append(word)
    return found


# English words (from the catalog's own English side) and the Spanish words that look English: both are data.
ENGLISH_WORDS = []
COGNATES = {"solo", "decide", "describe", "final", "roles", "next", "español", "english", "control", "base", "error",
            "local", "demo", "plan", "idea", "app", "web", "sí", "no"}


def screen_texts(html):
    """The text of each screen of the page: every text node and the words in its attributes, by screen id."""
    from html.parser import HTMLParser

    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.screens, self.stack, self.skip = {}, [], 0

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag in ("script", "style", "pre", "code", "textarea", "title", "dfn") or "data-no-i18n" in attrs:
                self.skip += 1
                self.stack.append((tag, True))
                return
            if tag in ("br", "input", "meta", "link", "img", "hr", "path", "use"):
                for key in ("placeholder", "title", "aria-label"):
                    if attrs.get(key) and self.current():
                        self.screens.setdefault(self.current(), []).append(" ".join(attrs[key].split()))
                return
            self.stack.append((tag, False, attrs.get("id") if attrs.get("data-screen") else None))
            for key in ("placeholder", "title", "aria-label"):
                if attrs.get(key) and self.current():
                    self.screens.setdefault(self.current(), []).append(" ".join(attrs[key].split()))

        def current(self):
            for item in reversed(self.stack):
                if len(item) == 3 and item[2]:
                    return item[2]
            return "page"

        def handle_endtag(self, tag):
            while self.stack:
                item = self.stack.pop()
                if item[1] is True:
                    self.skip -= 1
                if item[0] == tag:
                    break

        def handle_data(self, data):
            text = " ".join(data.split())
            if text and not self.skip:
                self.screens.setdefault(self.current(), []).append(text)

    reader = Reader()
    reader.feed(re.sub(r"<!--[\s\S]*?-->", "", html))
    return reader.screens


def browser_screens(root, tmp):
    """Chromium, when Playwright is here: the page in Spanish, each screen as a person sees it, no English UI string."""
    found = guide.chromium()
    if not found:
        print("  note: no Playwright with a Chromium here (CI has none): the screens are read from the page's source")
        return
    import test_setup_run_here as here
    sync_playwright, kwargs = found
    here.MODULE = here.team.MODULE = wizard.MODULE
    target, remote, runner = here.ready_server(root, tmp)
    with tp.live(target, runner) as srv, sync_playwright() as p:
        here.team.ready_team(srv, target)
        browser = p.chromium.launch(args=["--no-sandbox"], **kwargs)
        for width in (1280, 390):
            context = browser.new_context(viewport={"width": width, "height": 800}, locale="es-MX", reduced_motion="reduce")
            page_ = context.new_page()
            for step in ("project", "install", "rules", "people", "schedule", "publish", "plan", "start", "dashboard", "closed"):
                page_.goto("http://127.0.0.1:%d/?step=%s#code=%s" % (srv.server_port, step, srv.new_code()))
                page_.wait_for_selector("#content:not([data-loading])")
                shown = page_.evaluate("""() => [...document.querySelectorAll('.screen:not([hidden]) *')].filter(e => !e.closest('[hidden],pre,code,dfn,[data-no-i18n],script,style') && e.offsetParent !== null)
                    .flatMap(e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue.trim())).filter(Boolean)""")
                left = [(t, english_left(t)) for t in shown if english_left(t)]
                assert not left, "%s at %d px shows English in Spanish: %r" % (step, width, left[:6])
            context.close()
        browser.close()


def one_voice_in_spanish(root, tmp):
    cat = Catalog()
    glossary = workspace_json("GLOSSARY")
    codes = workspace_json("CODES")
    spanish = list(cat.es.values()) + [t for _, t in cat.notes + cat.gates] + [c["es"] for c in codes.values()]
    english = list(cat.es) + [c["en"] for c in codes.values()]
    # "tú" and the usage of Mexico: no ustedes, vosotros, voseo or "usted"; the avoided words are the glossary's.
    voice = re.compile(r"\b(ustedes|vosotros|usted|tenés|podés|querés|hacé|andá|mirá|elegí|confirmá|escribí|ejecutá|abrí|"
                       r"vuestr[oa]s?|haced|pulsad|abrid|escribid)\b", re.I)
    bad = [t for t in spanish if voice.search(t)]
    assert not bad, "not the voice of 'tú' in Mexico: %r" % bad[:5]
    for entry in glossary["avoid"]:
        pattern, use = entry["re"], entry["use"]
        bad = [t for t in spanish if re.search(pattern, t, re.I)]
        assert not bad, "%r is not used (say %r): %r" % (pattern, use, bad[:4])
    # No exclamation marks and no filler, in either language.
    bad = [t for t in spanish + english if "!" in t or "¡" in t]
    assert not bad, "no exclamation marks: %r" % bad[:4]
    filler = re.compile(r"\b(simplemente|fácilmente|facilmente|sencillamente|potente|poderos[oa]|increíble|"
                        r"simply|easily|powerful|seamless(ly)?|effortless(ly)?|blazing)\b", re.I)
    bad = [t for t in spanish + english if filler.search(t)]
    assert not bad, "no filler words: %r" % bad[:4]
    # No sentence mixes languages: a Spanish text has no English words outside the glossary's.
    mixed = [(t[:90], english_left(t)) for t in spanish if english_left(t)]
    assert not mixed, "%d Spanish sentence(s) with English words: %r" % (len(mixed), mixed[:8])
    # Headings and buttons in sentence case: only the first word and names have a capital.
    names = {"Git", "GitHub", "Claude", "Code", "Codex", "Cursor", "Gemini", "CLI", "PROJECT", "main", "UAK", "Español", "English",
             "Python", "Windows", "Node", "IDEA", "AGENTS", "MCP", "PR", "CI", "OK", "FAQ", "Enter", "Ctrl", "Escape", "TASKS"}
    from html.parser import HTMLParser

    class Heads(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.open, self.found, self.depth = None, [], 0

        def handle_starttag(self, tag, attrs):
            if tag in ("h1", "h2", "h3", "h4", "button", "summary"):
                self.open, self.text = tag, ""

        def handle_data(self, data):
            if self.open:
                self.text += data

        def handle_endtag(self, tag):
            if self.open == tag:
                self.found.append(" ".join(self.text.split()))
                self.open = None

    reader = Heads()
    reader.feed(re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<!--[\s\S]*?-->", "", page()))
    loud = []
    for title in reader.found:
        shown = cat.es.get(title)
        if not shown:
            continue
        words = [w for w in re.findall(r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ.]*", shown.split(":")[0])[1:] if "." not in w]
        loud += [(title, shown) for w in words if w.strip(".") not in names and not w.isupper()][:1]
    assert not loud, "Title Case in a heading or a button (sentence case: only the first word has a capital): %r" % loud[:6]


def glossary_is_respected(root, tmp):
    glossary = workspace_json("GLOSSARY")
    cat = Catalog()
    spanish = " \n".join(list(cat.es.values()) + [t for _, t in cat.notes + cat.gates] + [c["es"] for c in workspace_json("CODES").values()]).lower()
    # The terms the glossary translates are used, and the ones it keeps are written as they are.
    for entry in glossary["use"]:
        english_word, chosen = entry["en"], entry["es"]
        first = chosen.split()[0].rstrip("s")
        assert first.lower()[:5] in spanish, "the glossary's %r = %r is never used" % (english_word, chosen)
    for kept in ("commit", "merge", "pull request", "worktree", "main"):
        assert kept in glossary["keep"], "the glossary keeps %r in English" % kept
        assert kept in spanish, "%r appears in the Spanish as it is" % kept
    # A Git word is never translated, and the one decision about the verb is stated once and kept.
    for translated in ("confirmación de cambios", "fusionar", "solicitud de extracción", "rama principal", "árbol de trabajo",
                       "hacer un commit", "hacemos commit", "commiteado", "mergeado"):
        assert translated not in spanish, "%r: a Git word that stays in English" % translated
    verbs = re.findall(r"\b(?:haz|hacer|hazle|hacemos) (?:un )?(commit|merge)\b", spanish)
    assert "commit" in verbs and "merge" in verbs, "the verb for a commit and a merge is 'hacer', stated: %r" % set(verbs)
    # Claim = "tomar una tarea", dashboard = panel, reviewer = revisor: one word each, in the engine's codes too.
    assert "panel" in spanish and not re.search(r"\b(tablero|dashboard)\b", spanish), "dashboard is 'panel'"
    assert re.search(r"toma(r|da|das)? (una |la |esta )?tarea", spanish), "claim is 'tomar una tarea'"
    assert not re.search(r"\b(reclam\w+|reserv\w+)", spanish), "no other word for claim"
    # No English word outside the glossary: the whole catalog, each Spanish text, by the same rule the screens use.
    outside = {}
    for text in spanish.split(" \n"):
        for word in english_left(text):
            outside.setdefault(word.lower(), text[:80])
    assert not outside, "words outside the glossary in the Spanish: %r" % dict(list(outside.items())[:12])
    # Task titles, paths, branches and commands are data: no catalog row may rewrite them. Every NOTES/GATE pattern is
    # whole-string, and the values it captures come out as they went in.
    for pattern, template in cat.notes + cat.gates:
        assert not pattern.startswith(".*") and not pattern.endswith(".*"), "a pattern that matches too much: %r" % pattern
    probe = "Could not reach origin/feat\\x $1 (a|b)[c]: fatal. Check it."
    shown = cat.t(probe)
    assert "$1 (a|b)[c]" in shown or shown == probe, "a captured value is never changed: %r" % shown
    title = "APP-001 · Pagos $& (1) {n}"
    assert cat.t(title) == title and cat.gate(title) == title, "a task title stays as it is"


TESTS += [texts_are_keyed_by_code, rewording_the_engine_changes_nothing, no_missing_text_in_either_language,
          one_voice_in_spanish, glossary_is_respected]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    globals()["BIN"] = root / ".uak/bin"
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
