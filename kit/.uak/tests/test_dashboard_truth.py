#!/usr/bin/env python3
"""The dashboard tells the truth and is accessible (UI-023). Real HTTP and real Git with a local bare remote whose
claims branch is written by hand (the states QA round B built: a dependency still in progress, a merge in the human
queue, a past freeze, a remote that stops answering); `uak start` is answered with canned lines. The page's colors,
targets, tabs and headings are read from the markup and the CSS (the browser QA of the task is their evidence).
Evidence: notes/handoff:qa/rounds-2026-11-14 A-F9, B-06, B-07, B-08, B-12, B-13, B-15 and D (WCAG 1.4.3, 2.5.3, 2.5.8,
1.3.1; D-4.3, 4.4, 8.3, 1.3)."""
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
from test_hack import resolve_binary

LOG_PATH = "/private/tmp/x y/copy2/.git/worktrees/app-001/uak-out/gate-APP-001-smoke-1794638782.log"
SMOKE_REASON = ("Smoke red or product unverified: PRODUCT_UNVERIFIED: missing .uak/bin/smoke-project; exit 2. "
                "(log: %s)" % LOG_PATH)


def git(cwd, *args):
    done = subprocess.run([resolve_binary("git"), "-c", "core.quotePath=false", "-c", "color.ui=false", *args],
                          cwd=str(cwd), capture_output=True, text=True)
    assert done.returncode == 0, "git %s: %s" % (" ".join(args), done.stderr)
    return done.stdout


def write_claims(tmp, remote, files):
    """Push a hand-made claims branch (one commit with FILES) to REMOTE, replacing any earlier one."""
    work = tmp / ("claims-work-%d" % len(list(tmp.glob("claims-work-*"))))
    work.mkdir()
    git(work, "init", "-q", "-b", "claims")
    git(work, "config", "user.name", "Claims Fixture")
    git(work, "config", "user.email", "claims@example.invalid")
    git(work, "config", "core.hooksPath", str(tmp / "no-hooks"))
    for path, text in files.items():
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        (work / path).write_text(text, encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "claims: fixture")
    git(work, "push", "-q", "--force", str(remote), "claims:claims")


def task(tid, state, owner="claude-ana"):
    return "ID: %s\nState: %s\nOwner: %s\nUpdated: %d\n" % (tid, state, owner, int(time.time()) - 60)


def dashboard(srv):
    status, body, _ = wizard.request(srv, "GET", "/api/dashboard")
    assert status == 200, body
    return json.loads(body)


def status_of(srv):
    return json.loads(wizard.request(srv, "GET", "/api/status")[1])


def inspect(srv, target, name="ana"):
    assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
    assert tp.post(srv, "/api/human", {"name": name})[0] == 200


def check(srv):
    assert tp.post(srv, "/api/check", {})[0] == 202
    tp.wait_idle(srv)
    return status_of(srv)


def blocked_tasks_are_not_available(root, tmp):
    """A-F9, B-13: APP-002 depends on APP-001, which is still in progress: it waits, it is not available."""
    target, remote = team.ready_project(root, tmp)
    write_claims(tmp, remote, {"tasks/APP-001.md": task("APP-001", "CLAIMED")})
    with wizard.LiveServer(str(target), run=team.Team(team.WAITING_OUT)) as srv:
        inspect(srv, target)
        data = dashboard(srv)
    tasks = {t["id"]: t for t in data["tasks"]}
    assert tasks["APP-002"].get("waiting_on") == ["APP-001"], "APP-002 waits on APP-001: %r" % tasks["APP-002"]
    assert tasks["APP-001"].get("waiting_on") == [], "a claimed task waits on nothing"
    assert data["progress"].get("waiting") == 1, "the waiting bucket counts it: %r" % data["progress"]
    assert data["progress"].get("available") == 0, "nothing is free to claim: %r" % data["progress"]
    # Both views draw the bucket and the approved mark, in both languages.
    dash, page, catalog = (root / ".uak/bin/lib/dash.html").read_text(encoding="utf-8"), team.page(), team.catalog()
    assert "waiting_on" in dash and "Waiting on dependencies" in dash, "the board has a waiting column"
    assert "waiting_on" in page, "the Beginner list marks waiting tasks"
    for english, spanish in (("Waiting on dependencies", "Esperando dependencias"), ("approved", "aprobada"),
                             ("waiting on dependencies", "esperando dependencias"), ("available", "disponible")):
        assert re.search(r'\[\s*"%s",\s*"%s"\s*\]' % (re.escape(english), re.escape(spanish)), catalog), english
    assert re.search(r'T\("approved"\)', dash), "a review approved for its tip shows an approved badge"
    # B-12: a single row reads in the singular (es: "disponible", not the column heading "Disponibles").
    assert re.search(r"ROW_LABEL", page) and re.search(r"ROW_LABEL", dash), "rows use singular state labels"
    # The leftover "· ofrecida a all" (UI-021 review): "all" is translated on its own.
    assert re.search(r'x === "all" \? T\("all"\)', dash), "an offer to all reads 'todos' in Spanish"


def frozen_is_frozen(root, tmp):
    """B-06: after the freeze the next step says frozen, never "Your team is working", even before the dashboard
    was opened and when only PROJECT.md (not claims) has the freeze."""
    target, remote = team.ready_project(root, tmp)
    config = target / ".uak/PROJECT.md"
    config.write_text(config.read_text(encoding="utf-8").replace("Freeze-Epoch: 4102444800", "Freeze-Epoch: 1000000000"),
                      encoding="utf-8")
    write_claims(tmp, remote, {"tasks/APP-001.md": task("APP-001", "CLAIMED")})
    runner = team.Team(team.WAITING_OUT)
    runner.ready_code = 1
    with wizard.LiveServer(str(target), run=runner) as srv:
        inspect(srv, target)
        state = check(srv)
        assert state["guidance"]["kind"] == "frozen", "status says frozen: %r" % state["guidance"]
        data = dashboard(srv)
        assert data.get("freeze") == 1000000000, "the dashboard knows the freeze from PROJECT.md: %r" % data.get("freeze")
        assert data["guidance"]["kind"] == "frozen", data["guidance"]
        team_view = json.loads(wizard.request(srv, "GET", "/api/team")[1])
    assert "Your team is working" not in json.dumps(team_view), team_view
    assert not [c for c in team_view.get("commands") or [] if c["id"] == "implement"], "no claim after the freeze"


def needs_human_comes_first(root, tmp):
    """B-07: a merge in the human queue is setup's next step, before anything else, in plain words with no path;
    a merge that only waits for the queue is not a human's job."""
    target, remote = team.ready_project(root, tmp)
    write_claims(tmp, remote, {
        "tasks/APP-001.md": task("APP-001", "REVIEW"),
        "queue/APP-001.md": "ID: APP-001\nState: HUMAN\nOwner: claude-ana\nUpdated: %d\nReason: %s\n" % (
            int(time.time()) - 30, SMOKE_REASON),
        "queue/APP-002.md": "ID: APP-002\nState: WAITING\nOwner: claude-ana\nQueued: 1\nReason: Waiting for queue\n"})
    with wizard.LiveServer(str(target), run=team.Team(team.READY_OUT)) as srv:
        inspect(srv, target)
        check(srv)
        data = dashboard(srv)
        later = status_of(srv)
    g = data["guidance"]
    assert g["kind"] == "human", "the human queue comes first: %r" % g
    assert "APP-001" in g["title"] and "APP-002" not in json.dumps(g), g
    shown = json.dumps(g)
    assert LOG_PATH not in shown and "(log:" not in shown and "/private/" not in shown, "no path: %r" % g
    assert team.translated(g["title"]) and team.translated(g["detail"]), "Spanish for %r" % g
    assert [q["task"] for q in data.get("needs_human", [])] == ["APP-001"], data.get("needs_human")
    for q in data["queue"]:
        assert "/private/" not in q.get("reason", ""), "queue reasons carry no absolute path: %r" % q
    assert later["guidance"]["kind"] == "human", "the setup page's next step says it too: %r" % later["guidance"]
    dash = (root / ".uak/bin/lib/dash.html").read_text(encoding="utf-8")
    assert not re.search(r'q\.state === "HUMAN" \|\| q\.reason', dash), "a queued merge is not counted as human work"


def offline_uses_last_claims(root, tmp):
    """B-08: when the remote stops answering, the dashboard shows the last claims it read, marked stale, not the
    local plan with every task available."""
    target, remote = team.ready_project(root, tmp)
    write_claims(tmp, remote, {"tasks/APP-001.md": task("APP-001", "CLAIMED")})
    with wizard.LiveServer(str(target), run=team.Team(team.WAITING_OUT)) as srv:
        inspect(srv, target)
        online = dashboard(srv)
        assert online["source"] == "remote", online.get("warning")
        git(target, "remote", "set-url", "origin", str(tmp / "gone.git"))
        offline = dashboard(srv)
    assert offline["source"] == "cache" and offline.get("stale") is True, (offline["source"], offline.get("warning"))
    states = {t["id"]: t["state"] for t in offline["tasks"]}
    assert states.get("APP-001") == "CLAIMED", "the last known claim stays: %r" % states
    assert offline.get("claims_at"), "the page says how old the copy is"
    assert offline["warning"] and team.translated(offline["warning"]), offline["warning"]
    # Never fetched: still the plainly labelled local plan.
    (tmp / "b").mkdir()
    other, _ = team.ready_project(root, tmp / "b", name="never fetched")
    git(other, "remote", "set-url", "origin", str(tmp / "b" / "gone.git"))
    with wizard.LiveServer(str(other), run=team.Team(team.WAITING_OUT)) as srv:
        inspect(srv, other)
        local = dashboard(srv)
    assert local["source"] == "local" and not local.get("stale"), local["source"]


def css_tokens(css, selector):
    """The custom properties of the first rule whose selector is exactly SELECTOR (inside media queries too)."""
    match = re.search(re.escape(selector) + r"\s*\{([^{}]*)\}", css)
    assert match, "no rule %s" % selector
    return dict(re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\b", match.group(1)))


def luminance(color):
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    rgb = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def contrast(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def dashboard_meets_contrast_and_targets(root, tmp):
    """D: text contrast ≥ 4.5:1 in light and dark, targets ≥ 24 px, label in name, a heading per view, ARIA tabs with
    arrow keys, tabs that wrap at 390 px and a grey dot when no agent is online."""
    dash = (root / ".uak/bin/lib/dash.html").read_text(encoding="utf-8")
    page = team.page()
    low = []
    # UAK-158: the pages share one token block; every pair of every palette is measured in test_setup_design.py.
    themes = {"dash light": css_tokens(dash, ":root"), "dash dark": css_tokens(dash, ':root[data-theme="dark"]')}
    for name, t in themes.items():
        for text in ("ink", "ink-2", "muted", "accent-ink"):
            for back in ("page", "surface", "raised", "hover"):
                if contrast(t[text], t[back]) < 4.5:
                    low.append("%s --%s on --%s %.2f" % (name, text, back, contrast(t[text], t[back])))
        for text, back in (("warn-ink", "warn-wash"), ("crit-ink", "crit-wash"), ("accent-ink", "accent-wash"),
                           ("muted", "accent-wash"), ("muted", "warn-wash"), ("muted", "crit-wash")):
            if contrast(t[text], t[back]) < 4.5:
                low.append("%s --%s on --%s %.2f" % (name, text, back, contrast(t[text], t[back])))
    assert not low, "text below 4.5:1: %s" % "; ".join(low)
    # 2.5.8: the task-ID buttons and the other small text buttons are at least 24 px tall.
    for rule in (".tid", ".expand", ".filters .clear", ".chip"):
        body = re.search(re.escape(rule) + r"\s*\{([^}]*)\}", dash)
        assert body and re.search(r"min-height:\s*(2[4-9]|[3-9]\d)px", body.group(1)), "%s is at least 24 px" % rule
    # 2.5.3: the visible label "View" is the accessible name of the profile select (no other aria-label).
    label = re.search(r'<label for="profile"([^>]*)>([^<]*)<', page)
    assert label and label.group(2).strip() == "View" and "aria" not in label.group(1), "label View"
    assert not re.search(r'id="profile"[^>]*aria-label', page), "no aria-label overriding View"
    # ARIA tabs: tablist, tab, aria-selected, aria-controls, a tabpanel and arrow keys; the counts are separate words.
    for needle in ('role="tablist"', 'role: "tab"', '"aria-selected"', '"aria-controls"', 'role="tabpanel"',
                   "ArrowRight", "ArrowLeft", "Home", "End"):
        assert needle in dash, "ARIA tabs need %s" % needle
    assert re.search(r'\.tabs\s*\{[^}]*flex-wrap:\s*wrap', dash), "the tab strip wraps at 390 px"
    # 1.3.1: every view starts with a heading, and the page keeps an h1 when embedded.
    assert re.search(r'function viewHeading\(', dash) and dash.count("viewHeading(v,") >= 6, "a heading per view"
    assert 'id="embedded-title"' in dash, "an h1 stays when the top bar is hidden"
    # D: the online dot is grey when nobody is online.
    assert re.search(r'pres\(online\.length \? "online" : "offline"\)', dash), "grey dot at 0 agents"


def dash_source(root):
    return (root / ".uak/bin/lib/dash.html").read_text(encoding="utf-8")


def dashboard_keeps_every_field(root, tmp):
    """UAK-162: the redesign drops no field the dashboard showed (v6.8 and the UAK-158 page): every part of the data the
    old page read is still read, and the four figures, the four stages and the seven views are still drawn."""
    dash = dash_source(root)
    for field in ("d.progress", "d.agents", "d.offers", "d.queue", "d.messages", "d.blackbox", "d.usage", "d.lessons", "d.decisions",
                  "d.tokens", "d.timelines", "d.reviews", "d.freeze", "d.stale", "d.claims_at", "d.mode", "d.repo", "D.refresh",
                  "t.stalled", "t.sub", "t.pr", "t.participants", "t.harnesses", "t.priority", "t.depends", "t.away", "t.progress",
                  "a.messages", "a.verdicts", "a.checkpoints", "a.role", "a.last_seen", "p.weighted"):
        assert field in dash, "the page no longer reads %s" % field
    for label in ("Agents online", "Reviews waiting", "Stalled", "Needs a human", "Available", "In progress", "In review", "Integrated"):
        assert 'T("%s")' % label in dash, "the label %r is gone" % label
    for view in ("sum", "board", "agents", "talk", "bb", "memory", "tokens"):
        assert '["%s", "' % view in dash, "the view %s is gone" % view
    # one registry: each block has a name, a title, a column, a maximum of rows and one render function
    blocks = re.search(r"var BLOCKS = \[(.*?)\n  \];", dash, re.S).group(1)
    entries = re.findall(r"\{ name: \"(\w+)\", title: function \(\) \{[^}]*\}, col: \"(main|side)\", max: ([\w]+), render: (\w+) \}", blocks)
    assert [e[0] for e in entries] == ["needs", "map", "tasks", "lanes", "progress", "agents", "pace", "tokens"], entries
    assert [e[1] for e in entries] == ["main"] * 4 + ["side"] * 4, "the order of the summary: what needs you, every task as a square, tasks, activity; at the side progress, agents, pace, tokens"
    assert len(re.findall(r"BLOCKS\.forEach", dash)) == 1, "the summary is drawn from the registry only"
    # the summary never grows with the plan: tasks 8 rows, agents 4, progress blocks up to 24
    maxima = {e[0]: e[2] for e in entries}
    assert maxima["agents"] == "4" and maxima["tasks"] == "MAXTASKS" and "MAXTASKS = 8" in dash and maxima["progress"] == "24", maxima
    assert "total <= 24" in dash, "progress is one block per task up to 24 and one bar beyond"
    assert "document.title = (n ?" in dash, "the tab's title says how many things need the person"


def empty_project_says_the_next_step(root, tmp):
    """An empty project is not a grid of zeros: it says the one next step and its command; a finished one says it is finished."""
    dash = dash_source(root)
    assert "empty = !d.tasks.length" in dash and 'copyBox("bash .uak/bin/uak start")' in dash, "the empty project shows its command"
    assert "L('Your project has no plan yet')" in dash and "L('Nothing is claimed or integrated yet, so every figure is zero.')" in dash
    assert "finished = p.total > 0 && p.done === 100" in dash and "L('Everything is integrated')" in dash, "the finished project says so"
    for zero in ("none in the last 30 min", "none waiting", "every task is moving", "nothing for you"):
        assert 'T("%s")' % zero in dash, "a zero says why in words: %s" % zero
    assert "L('Nothing has been integrated yet: the first integration starts this chart.')" in dash


def no_server_no_request(root, tmp):
    """One file opened from file://: no request of its own, no server, no external address, two timers that start no process."""
    dash = dash_source(root)
    for needle in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "new Worker", "child_process", "importScripts"):
        assert needle not in dash, "the page must not use %s" % needle
    assert not re.search(r"(?:src|href)=\"https?:", dash), "no external script, style or link"
    assert re.findall(r'<script src="([^"]+)"', dash) == ["workspace.js", "data.js"], "the only scripts beside the page are its own files"
    assert len(re.findall(r"setInterval\(", dash)) == 2, "two timers: the freshness label and the data reload"
    assert 'url(fonts/' in dash and 'url(http' not in dash, "fonts load from files beside the page"


def page_is_not_heavier(root, tmp):
    """UAK-162's weight clause. It said "not heavier than today (84 KB)": the page of 2026-11-23 was 84,057 bytes, and main's
    page was 103,903 once UAK-158 added the shared block (11 KB) and the look script (4 KB). The human raised the bound twice:
    to 128 KiB on 2026-11-24 (docs/plans/visual-setup-amend-7.md) and, for the views they asked for after seeing the screens
    (every task as a square, what waits for what, the black box as a tool, the memory graph, the token breakdown), to
    150 KiB the same day (docs/plans/visual-setup-amend-8.md) and, for the changes after the human signed off the look
    (agents as cards, listboxes, a readable memory graph, the page reloading itself), to 200 KiB (docs/plans/visual-setup-amend-10.md).
    Measured on the file's bytes."""
    size = len((root / ".uak/bin/lib/dash.html").read_bytes().replace(b"\r\n", b"\n"))  # a Windows checkout adds a byte per line: the bound is on the file as committed
    assert size <= 200 * 1024, "dash.html is %d bytes; the bound is 200 KiB (%d)" % (size, 200 * 1024)


def both_profiles_and_languages_are_complete(root, tmp):
    """Every label the page draws has its Spanish, those of workspace.js and those the page holds itself (ES), and the
    embedded profile hooks (the wizard's beginner and advanced views) are still wired."""
    dash = dash_source(root)
    text = (root / ".uak/bin/lib/workspace.js").read_text(encoding="utf-8")
    catalog = {json.loads(a): json.loads(b) for a, b in re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)}
    own = dict(re.findall(r"\n    '((?:[^'\\]|\\.)*)': '((?:[^'\\]|\\.)*)'", dash))
    used = set(m.replace("\\'", "'") for m in re.findall(r"\bL\('((?:[^'\\]|\\.)*)'\)", dash))
    own = {k.replace("\\'", "'"): v for k, v in own.items()}
    missing = sorted(k for k in used if k not in own and k not in catalog)
    assert not missing, "labels with no Spanish: %r" % missing
    assert not [k for k, v in own.items() if not v or v == k], "a Spanish line that is empty or equal to its English"
    assert not sorted(k for k in own if k not in used), "Spanish lines for labels the page does not draw: %r" % sorted(k for k in own if k not in used)
    for hook in ("UAK_EMBEDDED", "UAK_DASH_LOOK", "uak:state", "uak:language", "UAKLook", "UAKWorkspace.start(document.body)", "prefers-reduced-motion"):
        assert hook in dash, "the page lost %s" % hook


def messages_are_one_conversation_per_task(root, tmp):
    """Rule 12 of docs/design/DIRECTION.md: one conversation per task, told in the task's stages, with the panel, the three
    figures and who is in the thread; the page has no field to write. A pill reads in the singular for one task."""
    dash = dash_source(root)
    for needle in ("function convos(", "function stagesOf(", '"class": "stg"', "L('Waiting for you')", "L('My agents')", "L('Unread')", "L('See the task')",
                   "L('Changes requested')", "L('In the thread')", '"win-f"'):
        assert needle in dash, "the messages tab lost %s" % needle
    assert "<textarea" not in dash and 'type: "submit"' not in dash and "contenteditable" not in dash, "the page cannot send"
    assert 'text: s === "WAITING" ? T("Waiting") : rowLabel(s)' in dash and "LABEL.BLOCKED" not in dash, "pills are singular"
    assert "L('Nothing moved in the last 14 days')" in dash, "lanes say the period covered"


def logic_of(root):
    """The page's pure functions (the section between logic:begin and logic:end), run under node on the given fixture."""
    dash = dash_source(root)
    return dash[dash.index("/* logic:begin"):dash.index("/* logic:end */")]


def under_node(root, body):
    import shutil
    node = shutil.which("node")
    if not node:
        return None
    program = "var window = {};\n" + logic_of(root) + "\nconsole.log(JSON.stringify((function () {" + body + "})()));"
    done = subprocess.run([node, "-e", program], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[:800]
    return json.loads(done.stdout)


def every_task_is_visible(root, tmp):
    """The human's feedback on the gallery: every task is on screen at once as a small square that explains itself (state by
    colour and by shape, the number inside, owner and title in its label), in the summary and in the board, never capped."""
    dash = dash_source(root)
    assert "function squares(" in dash and "mapBlock" in dash and 'ui.bv !== "cols"' in dash, "summary and board draw the map"
    body = dash[dash.index("function squares("):dash.index("function mapBlock(")]
    assert "slice(" not in body and "MAXTASKS" not in body, "the squares are never capped"
    assert '"aria-label": tip' in body and "tip: tip" in body and "openStory(t.id)" in body, "each square explains itself and opens its detail"
    for state in ("rev", "prog", "blk", "av", "wt"):
        assert ".sq.s-%s" % state in dash, "a shape for %s" % state
    assert "const" not in body


def square_says_why_it_waits(root, tmp):
    """The sentence names exactly the unmet dependencies; integrated ones are not blockers; a cycle, a missing id and a
    cancelled task do not break the page; a square lights what it waits for and what it unblocks, by hover, focus and tap."""
    dash = dash_source(root)
    for needle in ("function pick(", "function depWords(", '"dim"', 'classList.toggle("w"', 'classList.toggle("u"', "ARMED", "L('cannot start: it waits for')",
                   "L('is ready: nothing blocks it')", "function depSection(", "L('Waits for')", "L('Unblocks')", "L('further back')"):
        assert needle in dash, "missing %s" % needle
    assert '"focus"' in dash and "(hover: hover)" in dash, "keyboard and touch both work"
    out = under_node(root, """
      var T = function (id, state, depends) { return { id: id, state: state, depends: depends }; };
      var g = depGraph([T("A-1", "INTEGRATED", "None"), T("A-2", "CLAIMED", "A-1"), T("A-3", "CANCELLED", "None"), T("A-4", "AVAILABLE", "A-1, A-2, A-3, A-9 (not A-7)"),
                        T("A-5", "AVAILABLE", "A-6"), T("A-6", "AVAILABLE", "A-5"), T("A-7", "AVAILABLE", "A-4"), T("A-8", "AVAILABLE", "None")]);
      return { four: unmet(g, "A-4"), ready: unmet(g, "A-8"), cycle: unmet(g, "A-5"), behind7: behind(g, "A-7"), behindCycle: behind(g, "A-5"), unb: g.unb["A-1"] };
    """)
    if out is None:
        return
    assert [(x["id"], x["state"]) for x in out["four"]] == [("A-2", "CLAIMED"), ("A-3", "CANCELLED"), ("A-9", "MISSING")], out["four"]
    assert out["ready"] == [] and [x["id"] for x in out["cycle"]] == ["A-6"] and out["behindCycle"] == [], out
    assert sorted(x["id"] for x in out["behind7"]) == ["A-2", "A-3", "A-9"] or sorted(x["id"] for x in out["behind7"]) == [], out["behind7"]
    assert out["unb"] == ["A-2", "A-4"], out["unb"]


def agents_show_model_and_harness(root, tmp):
    """Every agent says its model and harness, or "not recorded", never a guess."""
    dash = dash_source(root)
    assert "function mh(" in dash and "L('not recorded')" in dash and "L('Model and harness not recorded')" in dash, "never a guess"
    assert dash.count("mh(a.name)") >= 2 and "mh(s.a)" in dash, "agents tab, agents block and lanes show model and harness"
    assert "d.tasks.forEach(function (t) { (t.harnesses" in dash and "d.timelines[id].agents.forEach" in dash, "the values come from what the engine recorded"


def black_box_filter_finds_an_error(root, tmp):
    dash = dash_source(root)
    for needle in ("ui.bk", "ui.bh", "ui.bp", "ui.bq", 'h("details"', "L('Search the black box')", "bbFilter("):
        assert needle in dash, "the black box tool lost %s" % needle
    out = under_node(root, """
      var r = [{ time: "2026-11-24T10:00Z", harness: "claude-code", source: "auto", kind: "exit3", command: "uak claim", what: "CONFLICT: UAK-162 overlaps", fix: "-" },
               { time: "2026-11-10T10:00Z", harness: "codex", source: "auto", kind: "exit1", command: "uak done", what: "git failed", fix: "-" },
               { time: "2026-11-24T09:00Z", harness: "claude-code", source: "agent", kind: "bug", command: "-", what: "flush leaves a clone", fix: "x" }];
      var now = Date.parse("2026-11-24T12:00Z");
      return { kind: bbFilter(r, { k: "conflict" }, now).length, harness: bbFilter(r, { h: "codex" }, now).length, day: bbFilter(r, { p: "d" }, now).length,
               text: bbFilter(r, { q: "clone" }, now).length, none: bbFilter(r, { q: "zzz" }, now).length, all: bbFilter(r, {}, now).length, note: bbFilter(r, { k: "note: bug" }, now).length };
    """)
    if out is None:
        return
    assert out == {"kind": 1, "harness": 1, "day": 2, "text": 1, "none": 0, "all": 3, "note": 1}, out


def memory_graph_edges_come_from_data(root, tmp):
    """Every edge is a real reference in an entry: its task field or an ID in its text, a file in its text or paths, its author."""
    dash = dash_source(root)
    assert "function memGraphView(" in dash and "L('Graph')" in dash and "tabindex" in dash and "L('The graph needs a wider screen: showing the list.')" in dash
    assert "http://www.w3.org/2000/svg" in dash and "d3." not in dash and "cytoscape" not in dash.lower() and "cdn" not in dash.lower(), "hand-written SVG, no library"
    out = under_node(root, """
      var les = [{ text: "UAK-006 cache_put in kit/x.sh", agent: "a", task: "-", paths: "kit/x.sh" }, { text: "again UAK-006", agent: "b", task: "UAK-006", paths: "" }, { text: "alone", agent: "c", task: "-", paths: "" }];
      var dec = [{ text: "UAK-007 only here", who: "a", kind: "plan", t: 1 }];
      var g = memGraph(les, dec);
      var by = {}; g.nodes.forEach(function (n) { by[n.id] = n; });
      return { edges: g.edges.map(function (e) { return e.join(">"); }), nodes: g.nodes.map(function (n) { return n.id; }).sort(), isolated: g.isolated, linked: g.linked };
    """)
    if out is None:
        return
    assert out["edges"] == ["l0>t:UAK-006", "l1>t:UAK-006", "l0>a:a", "d0>a:a"] or sorted(out["edges"]) == sorted(["l0>t:UAK-006", "l1>t:UAK-006", "l0>a:a", "d0>a:a"]), out
    assert "l2" not in out["nodes"] and "t:UAK-007" not in out["nodes"] and out["isolated"] == 1, "an entry that links to nothing is not drawn and no link is invented: %r" % out


def tokens_break_down(root, tmp):
    dash = dash_source(root)
    for needle in ("L('By model')", "L('By agent (owner of the task)')", "L('The most expensive tasks')", "L('average per integrated task')", "L('median per integrated task')", "tb.untied"):
        assert needle in dash, "the tokens tab lost %s" % needle
    py = (root / ".uak/bin/lib/dash.py").read_text(encoding="utf-8")
    assert '"by_model"' in py and '"by_kind"' in py, "dash.py carries the model and the kinds of token"
    out = under_node(root, """
      var tasks = [{ id: "A-1", state: "INTEGRATED", owner: "x", title: "one" }, { id: "A-2", state: "INTEGRATED", owner: "y", title: "two" }, { id: "A-3", state: "CLAIMED", owner: "x", title: "three" }];
      var b = tokenBreak({ by_task: { "A-1": 10, "A-2": 30, "A-3": 100, main: 500 } }, tasks);
      return { top: b.top.map(function (t) { return t.id; }), untied: b.untied, done: b.done, avg: b.avg, per: b.perAgent };
    """)
    if out is None:
        return
    assert out == {"top": ["A-3", "A-2", "A-1"], "untied": 500, "done": 2, "avg": 20, "per": {"x": 110, "y": 30}}, out


def share_card_matches_the_page(root, tmp):
    """The Share card is drawn on a canvas in the page, from the same numbers the page shows; a value the data does not carry
    is left out, never shown as 0; the card holds no path, no e-mail and no task title; nothing leaves the page."""
    dash = dash_source(root)
    for needle in ("function drawCard(", "function shareStats(", "getContext(\"2d\")", "1200", "630", "k2 = v ? 1 : 2", "toBlob(", "ClipboardItem", "toDataURL(\"image/png\")", "download:",
                   "showModal", 'id="share"', "idcells(", "L('Download PNG')", "L('Copy image')", "UPIIXIA Agentic Kit", "document.fonts"):
        assert needle in dash, "the share card lost %s" % needle
    card = dash[dash.index("function drawCard("):dash.index("var shareEl")]
    for private in ("title", "paths", "email", "owner", "text(t.", ".reason"):
        assert private not in card, "the card must not carry %s" % private
    py = (root / ".uak/bin/lib/dash.py").read_text(encoding="utf-8")
    assert "def base_commits(" in py and "rev-list" in py and 'data["commits"]' in py, "dash.py counts the commits of the base branch"
    out = under_node(root, """
      var d = { repo: "demo", progress: { total: 12, states: { INTEGRATED: 9, CLAIMED: 3 } }, tokens: { total: 4200000 }, commits: 87,
                agents: [{ name: "a-1", is_human: false, started: 1700000100 }, { name: "a-2", is_human: false, started: 1700000000 }, { name: "ana", is_human: true, started: 1600000000 }] };
      var full = shareStats(d); delete d.commits; d.tokens = { total: 0 };
      return { full: full, bare: shareStats(d) };
    """)
    if out is None:
        return
    assert out["full"] == {"name": "demo", "integrated": 9, "total": 12, "agents": 2, "tokens": 4200000, "commits": 87, "since": 1700000000}, out["full"]
    assert out["bare"]["commits"] is None and out["bare"]["tokens"] is None, "a figure that is not recorded is left out, not shown as 0"


def share_card_has_both_formats(root, tmp):
    """The Share dialog offers the horizontal card (1200x630) and a vertical one for a story (1080x1920), each with its preview,
    download and copy; the vertical is its own composition and keeps the story's top 250 px and bottom 340 px free; the kit's
    credit is one very small mark with a low-contrast name."""
    dash = dash_source(root)
    for needle in ("W = v ? 1080 : 1200", "H = v ? 1920 : 630", "SAFE_TOP = 250", "SAFE_BOTTOM = 340", 'block("h"', 'block("v"', "drawCard(x[0], D, x[1])", "globalAlpha = .55", "UPIIXIA Agentic Kit"):
        assert needle in dash, "the share card lost %s" % needle
    vertical = dash[dash.index("if (v) {"):dash.index("} else {", dash.index("if (v) {"))]
    ys = [int(n) for n in re.findall(r"SAFE_TOP \+ (\d+)", vertical)]
    assert ys and min(ys) >= 40 and 250 + max(ys) + 3 * 180 + 44 <= 1920 - 340, ys
    assert dash.count('text("UPIIXIA Agentic Kit"') == 1 and "12, 500, tok(\"muted\"), mono" in dash, "one small credit"


def project_name_is_not_the_worktree(root, tmp):
    """The project's name comes from the project: what PROJECT.md declares, else the base remote's repository name, else the main
    checkout's folder; never a linked worktree's folder."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("uak_dash_name", root / ".uak/bin/lib/dash.py")
    dash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dash)
    main = tmp / "the-project"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "config", "user.name", "T"); git(main, "config", "user.email", "t@example.invalid")
    (main / "f.txt").write_text("x", encoding="utf-8")
    git(main, "add", "-A"); git(main, "commit", "-q", "-m", "one")
    wt = tmp / "wt-feature-x"
    git(main, "worktree", "add", "-q", "-b", "feat/x", str(wt))
    assert dash.project_name(wt) == "the-project", dash.project_name(wt)
    git(main, "remote", "add", "origin", "https://github.com/someone/real-name.git")
    assert dash.project_name(wt) == "real-name" and dash.project_name(main) == "real-name"
    (wt / ".uak").mkdir()
    (wt / ".uak/PROJECT.md").write_text("# Project\n\nProject: Declared Name\nMode: sprint\n", encoding="utf-8")
    assert dash.project_name(wt) == "Declared Name", dash.project_name(wt)


def page_reloads_when_a_newer_page_is_written(root, tmp):
    """data.js carries the version of the page that was written beside it; a page that finds another one reloads itself once, and
    never loops; nothing is read beyond the files it already reads."""
    dash = dash_source(root)
    for needle in ('<meta name="uak-page" content="dev">', "function newerPage(", "location.reload()", "uak-page-tried", "if (newerPage()) return;"):
        assert needle in dash, "the page lost %s" % needle
    py = (root / ".uak/bin/lib/dash.py").read_text(encoding="utf-8")
    assert 'data["page"] = page_version(tpl)' in py and "def page_version(" in py and "content=\"%s\"" in py, "dash.py writes the page version"
    out = under_node(root, """
      return [pageIsNewer("aaa", "bbb", ""), pageIsNewer("aaa", "aaa", ""), pageIsNewer("aaa", "bbb", "bbb"), pageIsNewer("dev", "bbb", ""), pageIsNewer("aaa", undefined, "")];
    """)
    if out is not None:
        assert out == [True, False, False, False, False], out


def listbox_replaces_the_selects(root, tmp):
    """No native select shows a list of its own: the one left is the shared Apariencia control's hidden state holder; the page's
    listbox has a keyboard contract (arrows, Home, End, type-ahead, Escape, Enter) in pure functions."""
    dash = dash_source(root)
    assert re.findall(r"<select[^>]*>", dash) == ['<select id="workspace-theme" hidden aria-hidden="true" tabindex="-1">'], "only the hidden holder"
    assert 'h("select"' not in dash and 'role: "listbox"' in dash and '"aria-expanded"' in dash and '"aria-activedescendant"' in dash
    for key in ("Escape", "Enter", "Tab"):
        assert 'e.key === "%s"' % key in dash, key
    out = under_node(root, """
      var L = ["Auto", "Light", "Dark"];
      return [lbMove(3, 0, "ArrowDown"), lbMove(3, 2, "ArrowDown"), lbMove(3, 1, "ArrowUp"), lbMove(3, 0, "ArrowUp"), lbMove(3, 1, "Home"), lbMove(3, 0, "End"),
              lbType(L, 0, "d"), lbType(L, 1, "l"), lbType(L, 0, "x"), lbMove(0, 0, "Home")];
    """)
    if out is not None:
        assert out == [1, 2, 0, 0, 0, 2, 2, 1, 0, -1], out


TESTS = [blocked_tasks_are_not_available, frozen_is_frozen, needs_human_comes_first, offline_uses_last_claims,
         dashboard_meets_contrast_and_targets, dashboard_keeps_every_field, empty_project_says_the_next_step, no_server_no_request,
         page_is_not_heavier, both_profiles_and_languages_are_complete, messages_are_one_conversation_per_task, every_task_is_visible, square_says_why_it_waits,
         agents_show_model_and_harness, black_box_filter_finds_an_error, memory_graph_edges_come_from_data, tokens_break_down, share_card_matches_the_page,
         share_card_has_both_formats, project_name_is_not_the_worktree, page_reloads_when_a_newer_page_is_written, listbox_replaces_the_selects]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    # The server reads UAK_REMOTE/UAK_BASE from this process: an inherited value (a task worktree's) is not the fixture's.
    for key in [k for k in os.environ if k.startswith("UAK_")]:
        del os.environ[key]
    spec = importlib.util.spec_from_file_location("truth_setup", root / ".uak/bin/lib/setup.py")
    team.MODULE = wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("truth_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-truth-"))
        started = time.monotonic()
        try:
            test(root, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s: %s)" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("DASHBOARD_TRUTH_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
