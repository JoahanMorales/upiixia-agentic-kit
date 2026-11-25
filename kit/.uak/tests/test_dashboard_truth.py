#!/usr/bin/env python3
"""The dashboard tells the truth and is accessible (UI-023). Real HTTP and real Git with a local bare remote whose
claims branch is written by hand (the states QA round B built: a dependency still in progress, a merge in the human
queue, a past freeze, a remote that stops answering); `uak start` is answered with canned lines. The page's colors,
targets, tabs and headings are read from the markup and the CSS (the browser QA of the task is their evidence).
Evidence: notes/handoff:qa/rounds-2026-11-14 A-F9, B-06, B-07, B-08, B-12, B-13, B-15 and D (WCAG 1.4.3, 2.5.3, 2.5.8,
1.3.1; D-4.3, 4.4, 8.3, 1.3)."""
import argparse
import importlib.util
import contextlib
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
    docs = (root.parents[1] / "docs/DASHBOARD.md") if (root.parents[1] / "docs/DASHBOARD.md").is_file() else None
    if docs:
        words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
        assert "Built from %s blocks" % words[len(entries)] in docs.read_text(encoding="utf-8"), "DASHBOARD.md names the number of blocks the registry has (%d)" % len(entries)
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
    # Rendered, not only scanned: every tab drawn in Spanish from rich data shows none of the English the page is known to carry.
    out = stub_run(root, tmp, rich_data(), [{"name": "es", "tab": tab} for tab in TABS], lang="es")
    if out is not None:
        english = re.compile(r"(Waiting for|Approved|Changes requested|Re-review|Who touched|ran on|most urgent|most expensive|Search a task|Show all|No messages|Nothing is|Everything|cannot start|Needs you|Could not|Not tied|average per|median per|Integrated every|Who did what|All tasks|Tasks with|waiting for|thing, |things, |in progress|in review|changes requested|round \d)")
        leaks = sorted(set(s for r in out["results"] for s in r["texts"] + r["header"] if english.search(s)))
        assert not leaks, "English left on the Spanish page: %r" % leaks[:12]
        assert any("1 cosa, la más urgente primero" in s for r in out["results"] if r["tab"] == "sum" for s in r["texts"]) or any("cosas, la más urgente" in s for r in out["results"] if r["tab"] == "sum" for s in r["texts"]), "the count reads in Spanish"


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
    for needle in ("function drawCard(", "function shareStats(", "getContext(\"2d\")", "1200", "630", "k2 = 1,", "pngBytes(", "ClipboardItem", "toDataURL(\"image/png\")", "download:",
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
    assert ys and min(ys) >= 40 and 250 + 760 + 3 * 170 + 44 <= 1920 - 340 and max(ys) == 760, ys
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
    for needle in ('<meta name="uak-page" content="dev">', "function newerPage(", "location.href = location.pathname", "uak-page-tried", "[?&]uak=", "if (newerPage()) return;"):
        assert needle in dash, "the page lost %s" % needle
    py = (root / ".uak/bin/lib/dash.py").read_text(encoding="utf-8")
    assert 'data["page"] = page_version(tpl)' in py and "def page_version(" in py and "content=\"%s\"" in py, "dash.py writes the page version"
    out = under_node(root, """
      return [pageIsNewer("aaa", "bbb", ""), pageIsNewer("aaa", "aaa", ""), pageIsNewer("aaa", "bbb", "bbb"), pageIsNewer("dev", "bbb", ""), pageIsNewer("aaa", undefined, "")];
    """)
    if out is not None:
        assert out == [True, False, False, False, False], out
    plan = under_node(root, """
      return [reloadPlan("aaa", "bbb", "", ""), reloadPlan("aaa", "bbb", "bbb", ""), reloadPlan("aaa", "bbb", "", "?uak=bbb"), reloadPlan("aaa", "aaa", "", ""), reloadPlan("dev", "bbb", "", ""), reloadPlan("aaa", "ccc", "", "?uak=bbb")];
    """)
    if plan is not None:
        assert plan == ["reload", "notice", "notice", "stay", "stay", "reload"], "the address is a second guard when storage is blocked: %r" % plan
    assert "A newer page exists: reload this tab" in dash and "NEWER" in dash, "a page that cannot reload says so"


def one_definition_of_stalled(root, tmp):
    """The figure, the list and the board's red read one rule: no move for the stall limit, or a claim past its lease."""
    dash = dash_source(root)
    assert dash.count("stalledMin(t, g)") >= 2 and "stalledMin(t, D.generated)" in dash, "figure, list and board use stalledMin"
    out = under_node(root, """
      var now = 1000000;
      return [stalledMin({ stalled: 95 }, now), stalledMin({ state: "CLAIMED", lease: now - 600, updated: now - 3600 }, now), stalledMin({ state: "CLAIMED", lease: now + 600 }, now), stalledMin({ state: "REVIEW", lease: now - 600 }, now)];
    """)
    if out is not None:
        assert out == [95, 60, 0, 0], out
    assert "a.status === gr[0] && !a.is_human" in dash and "L('People')" in dash, "the Agents tab counts agents the way the summary does: the humans have their own group"


def no_native_select(root, tmp):
    """No native select shows a list of its own: the one left is the shared Apariencia control's hidden state holder; the page's
    listbox has a keyboard contract (arrows, Home, End, type-ahead, Escape, Enter) in pure functions."""
    dash = dash_source(root)
    assert re.findall(r"<select[^>]*>", dash) == ['<select id="workspace-theme" hidden aria-hidden="true" tabindex="-1">'], "the only native select is the hidden state holder of the shared Appearance control: hidden, aria-hidden and out of the tab order, so never visible or focusable"
    assert 'h("select"' not in dash and 'role: "listbox"' in dash and '"aria-expanded"' in dash and '"aria-activedescendant"' in dash
    assert "e.stopPropagation()" in dash[dash.index('if (e.key === "Escape") { e.preventDefault();'):][:200], "Escape closes the list, not the popover around it"
    assert "!pop.contains(e.target)" in dash, "the list does not close on its own scroll"
    for key in ("Escape", "Enter", "Tab"):
        assert 'e.key === "%s"' % key in dash, key
    out = under_node(root, """
      var L = ["Auto", "Light", "Dark"];
      return [lbMove(3, 0, "ArrowDown"), lbMove(3, 2, "ArrowDown"), lbMove(3, 1, "ArrowUp"), lbMove(3, 0, "ArrowUp"), lbMove(3, 1, "Home"), lbMove(3, 0, "End"),
              lbType(L, 0, "d"), lbType(L, 1, "l"), lbType(L, 0, "x"), lbMove(0, 0, "Home")];
    """)
    if out is not None:
        assert out == [1, 2, 0, 0, 0, 2, 2, 1, 0, -1], out


def figures_agree_across_tabs(root, tmp):
    """Two places never disagree: a count that appears in two places is computed once. Cancelled tasks are named where they are
    counted; a human-queue entry that outlived a cancelled task is not "needs a human"; the oldest review waiting reads the same
    clock in the figure and on its row; "online" is one stated window."""
    dash = dash_source(root)
    assert "d.queue.filter(" not in dash.replace("function openHumanQueue", ""), "the human queue is read only through openHumanQueue"
    assert dash.count("planCounts(d.tasks)") >= 4 and "L('cancelled')" in dash, "the plan's count and its cancelled tasks read one function"
    assert "reviewSince(o, d.tasks)" in dash and "L('online = seen in the last 30 min')" in dash
    out = under_node(root, """
      var tasks = [{ id: "A-1", state: "INTEGRATED" }, { id: "A-2", state: "CLAIMED" }, { id: "A-3", state: "CANCELLED" }, { id: "A-4", state: "REVIEW", sub: { kind: "waiting", since: 500 } }, { id: "A-5", state: "AVAILABLE" }];
      var queue = [{ task: "A-3", state: "HUMAN" }, { task: "A-5", state: "HUMAN" }, { task: "A-1", state: "HUMAN" }, { task: "A-5", state: "PENDING" }, { task: "A-9", state: "HUMAN" }];
      var tk = tokenBreak({ by_task: { "A-1": 10, "A-3": 5, "A-4": 7, main: 100 } }, tasks);
      return { counts: planCounts(tasks), queue: openHumanQueue(queue, tasks).map(function (q) { return q.task; }),
               since: reviewSince({ task: "A-4", since: 900 }, tasks), sinceOther: reviewSince({ task: "A-5", since: 900 }, tasks),
               tokTasks: tk.top.length, tokCancelled: tk.top.filter(function (x) { return x.state === "CANCELLED"; }).length };
    """)
    if out is None:
        return
    assert out["counts"] == {"plan": 4, "cancelled": 1}, out
    assert out["queue"] == ["A-5", "A-9"], "a cancelled or integrated task is not in the human queue: %r" % out["queue"]
    assert out["since"] == 500 and out["sinceOther"] == 900, out
    assert out["tokTasks"] == 3 and out["tokCancelled"] == 1 and out["counts"]["plan"] + out["counts"]["cancelled"] == 5, out


@contextlib.contextmanager
def browser_page(root, tmp, data, tab, extra="", phone=False):
    """The page opened in a real browser from file:// when Playwright is installed (yields None otherwise: the case then checks the code)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        yield None
        return
    lib = root / ".uak/bin/lib"
    shutil.copy(str(lib / "dash.html"), str(tmp / "index.html"))
    shutil.copy(str(lib / "workspace.js"), str(tmp / "workspace.js"))
    (tmp / "data.js").write_text("window.UAK_DATA = " + json.dumps(data) + ";", encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True, has_touch=True, accept_downloads=True) if phone else b.new_page(viewport={"width": 1280, "height": 900})
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        if tab:
            pg.add_init_script("localStorage.setItem('uak-dash', JSON.stringify({tab:'%s'%s}))" % (tab, extra))
        pg.goto("file://" + str(tmp / "index.html"))
        pg.wait_for_timeout(500)
        try:
            yield pg
        finally:
            b.close()



STUB_JS = r"""
var fs = require("fs"), vm = require("vm");
var cfg = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
var html = fs.readFileSync(cfg.html, "utf8");
var scripts = []; html.replace(/<script>([\s\S]*?)<\/script>/g, function (m, a) { scripts.push(a); return m; });
var mainSrc = scripts[scripts.length - 1];
var RELOADS = 0, HREF = "";
function mk(tag) {
  var el = { tag: tag, children: [], attrs: {}, style: { setProperty: function () {}, getPropertyValue: function () { return ""; } }, _text: "", nodeType: 1, hidden: false, value: "", className: "", offsetWidth: 100, scrollHeight: 0, clientHeight: 0, nextSibling: null,
    appendChild: function (c) { this.children.push(c); return c; }, append: function () { for (var i = 0; i < arguments.length; i++) this.children.push(arguments[i]); }, insertBefore: function (c) { this.children.push(c); return c; },
    remove: function () {}, setAttribute: function (k, v) { this.attrs[k] = String(v); }, getAttribute: function (k) { return this.attrs[k] === undefined ? null : this.attrs[k]; }, removeAttribute: function (k) { delete this.attrs[k]; },
    addEventListener: function () {}, removeEventListener: function () {}, contains: function () { return false; }, closest: function () { return null; }, scrollIntoView: function () {}, focus: function () {}, click: function () {}, select: function () {},
    setSelectionRange: function () {}, showModal: function () {}, close: function () {}, getBoundingClientRect: function () { return { left: 0, top: 0, right: 100, bottom: 20, width: 100, height: 20 }; },
    querySelector: function () { return mk("x"); }, querySelectorAll: function () { return []; }, classList: { add: function () {}, remove: function () {}, toggle: function () {}, contains: function () { return false; } } };
  Object.defineProperty(el, "firstChild", { get: function () { return this.children[0]; } });
  Object.defineProperty(el, "innerHTML", { get: function () { return ""; }, set: function () { this.children = []; this._text = ""; } });
  Object.defineProperty(el, "textContent", { get: function () { return this._text + this.children.map(function (c) { return c.textContent; }).join(""); }, set: function (v) { this.children = []; this._text = String(v); } });
  return el;
}
var ids = {};
var document = { createElement: mk, createElementNS: function (ns, t) { return mk(t); }, createTextNode: function (t) { return { nodeType: 3, textContent: String(t) }; }, createDocumentFragment: function () { return mk("frag"); },
  createRange: function () { return { selectNodeContents: function () {} }; }, getElementById: function (id) { return ids[id] = ids[id] || mk(id); },
  querySelector: function (sel) { return /uak-page/.test(sel) ? { content: cfg.mine || "dev" } : mk("x"); }, querySelectorAll: function () { return []; }, addEventListener: function () {}, body: mk("body"), documentElement: mk("html"), title: "", readyState: "complete", activeElement: null };
function store(throws) { return { getItem: function () { if (throws) throw new Error("blocked"); return null; }, setItem: function () { if (throws) throw new Error("blocked"); } }; }
var sandbox = { document: document, localStorage: store(false), sessionStorage: store(!!cfg.blocked), history: { replaceState: function () {} },
  location: { hash: "", search: cfg.search || "", pathname: "/x", reload: function () { RELOADS++; }, set href(v) { RELOADS++; HREF = v; }, get href() { return HREF; } },
  matchMedia: function () { return { matches: false, addEventListener: function () {} }; }, innerWidth: 1280, innerHeight: 800, requestAnimationFrame: function () {}, setInterval: function () {}, setTimeout: function () { return 0; }, clearTimeout: function () {},
  getComputedStyle: function () { return { getPropertyValue: function () { return ""; }, color: "" }; }, navigator: {}, console: { error: function () {}, log: function () {} }, XMLSerializer: function () { this.serializeToString = function () { return ""; }; },
  UAKLook: { get: function () { return { theme: "auto", pal: "lavanda" }; }, set: function () {}, onchange: function () {} },
  UAKWorkspace: { t: function (x) { return cfg.lang === "es" && cfg.catalog[x] !== undefined ? cfg.catalog[x] : x; }, language: function () { return cfg.lang; }, setLanguage: function () {}, start: function () {}, apply: function () {} },
  Date: Date, JSON: JSON, Math: Math, Object: Object, Array: Array, String: String, Number: Number, parseInt: parseInt, parseFloat: parseFloat, isNaN: isNaN, RegExp: RegExp, Error: Error, Promise: Promise, encodeURIComponent: encodeURIComponent };
sandbox.addEventListener = function () {}; sandbox.window = sandbox; sandbox.UAK_DATA = cfg.base; sandbox.UAK_ERRORS = undefined;
var ctx = vm.createContext(sandbox);
vm.runInContext(mainSrc, ctx);
function texts(el, out) { if (!el) return out; if (el.nodeType === 3) { out.push(el.textContent); return out; } if (el._text) out.push(el._text); if (el.attrs) { ["placeholder", "title", "aria-label"].forEach(function (k) { if (el.attrs[k]) out.push(el.attrs[k]); }); } (el.children || []).forEach(function (c) { texts(c, out); }); return out; }
var results = [];
(cfg.runs || []).forEach(function (run) {
  var data = JSON.parse(JSON.stringify(cfg.base)); (new Function("d", run.mutate || ""))(data);
  var r = { name: run.name, tab: run.tab, thrown: null, errors: [], texts: [] };
  sandbox.UAK_ERRORS.length = 0;
  try { var view = sandbox.UAK_TEST_RENDER(run.tab, data); r.texts = texts(view, []); r.header = texts(document.getElementById("tabs"), []); } catch (e) { r.thrown = String(e && e.stack || e); }
  r.errors = sandbox.UAK_ERRORS.slice(); results.push(r);
});
console.log(JSON.stringify({ results: results, reloads: RELOADS, href: HREF }));
"""


def stub_run(root, tmp, base, runs, lang="en", **extra):
    """Run the page's own script under node against a stub document and draw tabs from data; None when node is missing."""
    import shutil as _sh
    node = _sh.which("node")
    if not node:
        return None
    text = (root / ".uak/bin/lib/workspace.js").read_text(encoding="utf-8")
    catalog = {json.loads(a): json.loads(b) for a, b in re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)}
    cfg = dict({"html": str(root / ".uak/bin/lib/dash.html"), "base": base, "runs": runs, "lang": lang, "catalog": catalog}, **extra)
    (tmp / "stub.json").write_text(json.dumps(cfg), encoding="utf-8")
    (tmp / "stub.js").write_text(STUB_JS, encoding="utf-8")
    done = subprocess.run([node, str(tmp / "stub.js"), str(tmp / "stub.json")], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[:1200]
    return json.loads(done.stdout)



def fixture_data(agents=3, tasks=4):
    now = 1795000000
    ags = [{"name": "kit-%d" % i, "human": "ana", "is_human": False, "last_seen": now - 60 * i if i < 2 else now - 7 * 86400, "status": "online" if i < 2 else "offline",
            "tasks": [{"id": "T-1", "state": "CLAIMED"}] if i == 0 else [], "sessions": 0, "events": 0, "checkpoints": 1, "messages": 2, "verdicts": 0, "started": now - 9000, "role": "reviewer" if i == 1 else ""} for i in range(agents)]
    ts = [{"id": "T-%d" % (i + 1), "title": "task %d" % (i + 1), "priority": "P0", "depends": "None", "state": ["CLAIMED", "AVAILABLE", "REVIEW", "INTEGRATED"][i % 4], "owner": "kit-0", "pr": "-", "progress": "", "updated": now - 100,
           "stalled": 0, "lease": now + 900, "paths": "", "next": "", "away": 0, "outside": False, "participants": "", "harnesses": [{"agent": "kit-0", "harness": "claude-code", "model": "opus"}]} for i in range(tasks)]
    return {"repo": "demo", "generated": now, "mode": "", "freeze": 0, "progress": {"done": 25, "weighted": 30, "total": tasks, "states": {"CLAIMED": 1, "AVAILABLE": 1, "REVIEW": 1, "INTEGRATED": 1}, "outside": 0},
            "tasks": ts, "agents": ags, "messages": [], "reviews": [], "locks": [], "queue": [], "offers": [], "blackbox": [], "usage": {}, "decisions": [], "lessons": [],
            "tokens": {"total": 0, "by_task": {}, "by_harness": {}, "by_scope": {}}, "timelines": {}, "timeline_bound": {}, "refresh": 20, "live_url": None}


def agents_are_compact_cards(root, tmp):
    """Every agent is one small card in a grid, grouped by state, none behind "show all"; a card carries name, state, current task,
    model and harness, and last seen; the offline ones are the compact kind so the working ones lead."""
    dash = dash_source(root)
    agents = dash[dash.index("  function agents(v, d) {"):dash.index("  // Message text:")]
    for needle in ('"class": "agrid"', '"class": "ac"', "T(a.status)", "ago(a.last_seen, d.generated)", "mh(a.name)", "openStory(t.id)", "compact", "T(\"No live task\")"):
        assert needle in agents, "the agent card lost %s" % needle
    assert "ui.more[gr[0]]" not in agents and "slice(" not in agents.replace("a.tasks.slice(0, 2)", ""), "no agent is hidden behind show all"
    with browser_page(root, tmp, fixture_data(agents=40), "agents") as pg:
        if pg is None:
            return
        assert not pg.errors, pg.errors
        n = pg.evaluate("document.querySelectorAll('.agrid .ac').length")
        assert n == 40, "every agent is a card in the grid: %d" % n
        assert pg.evaluate("document.querySelectorAll('.agrid.sm .ac').length") == 38 and pg.evaluate("document.querySelector('.agrid .ac .ac-h b').textContent") == "kit-0"
        assert not pg.evaluate("Array.from(document.querySelectorAll('.more')).some(function (b) { return /Show all|Mostrar/.test(b.textContent); })"), "no show-all button"


def board_opens_on_columns(root, tmp):
    """The Board's default view is the columns; the squares are its second view; a saved preference still wins."""
    dash = dash_source(root)
    assert 'bv: "cols"' in dash and 'seg([["map", L(\'Map\')], ["cols", L(\'Cards\')]], ui.bv' in dash, "columns by default, the squares second"
    assert '"bv"' in dash.split("var saved = JSON.parse")[1].split("forEach")[0], "a saved choice is restored"
    with browser_page(root, tmp, fixture_data(), "board") as pg:
        if pg is None:
            return
        assert pg.evaluate("document.querySelectorAll('.bd .bcol').length") == 4 and pg.evaluate("document.querySelectorAll('#view .tmap').length") == 0, "fresh page: the four columns"
    with browser_page(root, tmp, fixture_data(), "board", ", bv:'map'") as pg:
        assert pg.evaluate("document.querySelectorAll('#view .tmap').length") >= 1 and pg.evaluate("document.querySelectorAll('.bd').length") == 0, "a saved preference still wins"


def memory_graph_is_readable(root, tmp):
    """On a memory shaped like this repo's (entries citing tasks, files and agents, some citing nothing): no position is clamped to a
    frame, labels never overlap each other or leave the view, entries with no visible link are grouped aside with counts, and the
    default kinds are entries and tasks."""
    dash = dash_source(root)
    assert "GHIDE = { file: true, agent: true }" in dash, "files and agents are off until their chip is on"
    assert "groupOrphans(" in dash and "fitLabels(" in dash and "clusterLayout(" in dash
    layout_src = dash[dash.index("function clusterLayout("):dash.index("function bbFilter(")]
    assert "Math.max(pad" not in layout_src and "Math.min(w - pad" not in layout_src, "the layout never clamps to a frame"
    out = under_node(root, """
      var les = [], dec = [], i;
      for (i = 0; i < 40; i++) dec.push({ text: "tasks added: T-" + (100 + i % 14) + " T-" + (100 + (i + 3) % 14) + " | Why: backlog without PR", who: "ana/ana", kind: "plan", t: i });
      for (i = 0; i < 14; i++) les.push({ text: "T-" + (100 + i % 9) + " cache keys on HEAD, see kit/x" + (i % 4) + ".sh", agent: "kit-" + (i % 3), task: "T-" + (100 + i % 9), paths: "kit/x" + (i % 4) + ".sh" });
      for (i = 0; i < 12; i++) dec.push({ text: "Why: same Paths, no scope change", who: "solo" + i, kind: "amend", t: 100 + i });
      var g = memGraph(les, dec);
      var vis = {}; g.nodes.forEach(function (n) { if (n.type !== "file" && n.type !== "agent") vis[n.id] = 1; });
      var edges = g.edges.filter(function (e) { return vis[e[0]] && vis[e[1]]; }), linked = {}; edges.forEach(function (e) { linked[e[0]] = linked[e[1]] = 1; });
      var shown = g.nodes.filter(function (n) { return vis[n.id] && linked[n.id]; });
      var lay = clusterLayout(shown, edges), P = lay.pos, bx = lay.box;
      var edgeCount = 0; shown.forEach(function (n) { var p = P[n.id]; if (Math.abs(p.x - bx.x) < 1 || Math.abs(p.x - bx.x - bx.w) < 1 || Math.abs(p.y - bx.y) < 1 || Math.abs(p.y - bx.y - bx.h) < 1) edgeCount++; });
      var view = { x: bx.x - 40, y: bx.y - 40, w: bx.w + 80, h: bx.h + 80 }, u = Math.max(1, view.w / 760);
      var items = shown.filter(function (n) { return n.type === "task"; }).map(function (n) { return { id: n.id, x: P[n.id].x, y: P[n.id].y, r: 10, w: n.label.length * 6.8 * u, h: 13 * u, below: true }; });
      var placed = fitLabels(items, view), boxes = Object.keys(placed).map(function (k) { return placed[k].box; }), overlap = 0, outside = 0;
      boxes.forEach(function (a, i) { if (a[0] < view.x || a[1] < view.y || a[0] + a[2] > view.x + view.w || a[1] + a[3] > view.y + view.h) outside++; boxes.forEach(function (b, j) { if (j > i && a[0] < b[0] + b[2] && b[0] < a[0] + a[2] && a[1] < b[1] + b[3] && b[1] < a[1] + a[3]) overlap++; }); });
      var orphans = g.entries.filter(function (e) { return !linked[e.id]; }), groups = groupOrphans(orphans.map(function (e) { return { t: "Decision: " + e.text.slice(0, 20), full: e.text }; }));
      return { nodes: shown.length, edgeCount: edgeCount, labels: boxes.length, tasks: items.length, overlap: overlap, outside: outside, orphans: orphans.length, groupSum: groups.reduce(function (a, x) { return a + x.n; }, 0), groups: groups.length,
               kinds: shown.map(function (n) { return n.type; }).filter(function (t, i, a) { return a.indexOf(t) === i; }).sort() };
    """)
    if out is None:
        return
    assert out["overlap"] == 0 and out["outside"] == 0 and out["labels"] > 0, "labels neither overlap nor leave the view: %r" % out
    assert out["edgeCount"] <= max(4, out["nodes"] * 0.12), "positions are not piled on the frame's edges: %r" % out
    assert out["orphans"] > 0 and out["groupSum"] == out["orphans"] and out["groups"] < out["orphans"], "the entries with no link are grouped with their counts: %r" % out
    assert out["kinds"] == ["decision", "lesson", "task"] or out["kinds"] == ["decision", "task"], out["kinds"]


TABS = ["sum", "board", "agents", "talk", "bb", "memory", "tokens"]


def rich_data():
    d = fixture_data(agents=5, tasks=6)
    g = d["generated"]
    d["tasks"][2].update(state="REVIEW", sub={"kind": "changes", "text": "changes requested (round 2)", "since": g - 600, "late": True, "rounds": 2, "rejects": 1})
    d["tasks"][4].update(state="REVIEW", sub={"kind": "waiting", "text": "waiting for a reviewer", "since": g - 900, "late": False, "rounds": 0, "rejects": 0})
    d["tasks"][5].update(state="BLOCKED")
    d["offers"] = [{"task": "T-5", "to": ["all"], "since": g - 900, "owner": "kit-0"}]
    d["queue"] = [{"task": "T-6", "state": "HUMAN", "reason": "needs a person", "at": g - 50}]
    d["messages"] = [{"n": 1, "t": g - 100, "from": "kit-0", "to": ["agent:kit-1"], "kind": "review", "task": "T-3", "text": "please look at this"}]
    d["lessons"] = [{"n": "1", "t": g - 90, "agent": "kit-0", "task": "T-1", "paths": "kit/x.sh", "text": "T-1 a lesson about kit/x.sh"}, {"n": "2", "t": g - 80, "agent": "kit-1", "task": "T-1", "paths": "", "text": "T-1 and T-2 again"}]
    d["decisions"] = [{"t": g - 70, "kind": "plan", "who": "ana/ana", "text": "tasks added: T-1 T-2 | Why: backlog"}, {"t": g - 60, "kind": "plan", "who": "ana/ana", "text": "tasks added: T-1 T-3 | Why: backlog"}]
    d["blackbox"] = [{"time": "2026-11-24T10:00Z", "kit": "v1", "harness": "claude-code", "source": "auto", "kind": "exit3", "command": "uak claim", "what": "CONFLICT", "fix": "-"}]
    d["usage"] = {"claude-code": {"claim": 2, "done": 1}}
    d["tokens"] = {"total": 100, "by_task": {"T-1": 40, "T-2": 30, "main": 30}, "by_harness": {"claude-code": 100}, "by_scope": {"lead": 100}, "by_model": {"opus": 100}, "by_kind": {"input": 1, "cache_write": 9, "cache_read": 80, "output": 10}}
    return d


def every_tab_renders_with_partial_data(root, tmp):
    """Each tab is drawn from empty and partial data (no agents, no tasks, one task, no tokens, a token breakdown empty, no memory, no
    black box, no messages) without an exception; one block that throws says so and the others still draw."""
    muts = {
        "empty": "d.tasks=[];d.agents=[];d.messages=[];d.offers=[];d.queue=[];d.blackbox=[];d.lessons=[];d.decisions=[];d.timelines={};d.usage={};d.tokens={total:0,by_task:{},by_harness:{},by_scope:{}};d.progress={done:0,weighted:0,total:0,states:{},outside:0};",
        "one task": "d.tasks=d.tasks.slice(0,1);d.progress.total=1;d.offers=[];d.queue=[];",
        "zero agents": "d.agents=[];",
        "no tokens": "d.tokens=null;",
        "tokens before any task": "d.tokens={total:9,by_task:{main:9},by_harness:{},by_scope:{},by_model:{}};",
        "tokens one breakdown": "d.tokens={total:9,by_task:{'T-1':9},by_harness:{x:9},by_scope:{},by_model:{}};",
        "no memory": "d.lessons=[];d.decisions=[];",
        "no black box": "d.blackbox=[];d.usage={};",
        "no messages": "d.messages=[];",
        "full": "",
    }
    runs = [{"name": n, "tab": tab, "mutate": m} for n, m in muts.items() for tab in TABS]
    out = stub_run(root, tmp, rich_data(), runs)
    if out is None:
        return
    bad = ["%s/%s: %s" % (r["name"], r["tab"], (r["thrown"] or "; ".join(r["errors"]))[:200]) for r in out["results"] if r["thrown"] or r["errors"]]
    assert not bad, "a tab threw or drew a block as failed: %s" % bad[:6]
    tok = [r for r in out["results"] if r["name"] == "tokens before any task" and r["tab"] == "tokens"][0]
    assert any("not tied" in s.lower() or "Not tied" in s for s in tok["texts"]), "tokens before any task still say where the spend is: %r" % tok["texts"][:12]
    full = [r for r in out["results"] if r["name"] == "full" and r["tab"] == "tokens"][0]
    assert any("average per integrated task" in s for s in full["texts"]), "the most-expensive list and averages are drawn"
    # the page-level guard: a block that throws does not blank the others
    broken = stub_run(root, tmp, rich_data(), [{"name": "broken", "tab": "sum", "mutate": "d.agents[0].tasks=null;"}])
    r = broken["results"][0]
    assert r["thrown"] is None and any(e.startswith("agents:") for e in r["errors"]), r["errors"]
    joined = " ".join(r["texts"])
    assert "Could not draw this block (agents)" in joined and "Needs you" in joined and "Progress" in joined, "the other blocks still render: %r" % joined[:300]


def titles_never_overflow(root, tmp):
    """A 3000-character unbroken title wraps or truncates everywhere a title is shown: no row, card or column grows past its box."""
    dash = dash_source(root)
    assert re.search(r"\.dn, \.tk p, \.mini \.it p, \.th \.tt \{[^}]*overflow-wrap: anywhere", dash), "titles in the board and lists break anywhere"
    assert ".find input { width: 220px" in dash, "the search placeholder is not clipped in Spanish"
    data = fixture_data(tasks=6)
    for t in data["tasks"]:
        t["title"] = "X" * 3000
    data["tasks"][3]["state"] = "INTEGRATED"
    with browser_page(root, tmp, data, "board") as pg:
        if pg is None:
            return
        wide = pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        assert not wide, "the board scrolls sideways with a 3000-character title"
    with browser_page(root, tmp, data, "sum") as pg:
        assert not pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"), "the summary scrolls sideways with a 3000-character title"

SHARE_ENVS = """
  var png = "iVBORw0KGgo=", file = [{ name: "x.png" }];
  function nav(o) { return o; }
  var envs = {
    iosHttp: { secure: false, coarse: true, anchorDownload: true, clipboardItem: false, files: file, nav: nav({}) },
    iosHttps: { secure: true, coarse: true, anchorDownload: true, clipboardItem: true, files: file, nav: nav({ share: function () {}, canShare: function (d) { return !!(d && d.files); }, clipboard: { write: function () {} } }) },
    chromeFile: { secure: true, coarse: false, anchorDownload: true, clipboardItem: true, files: file, nav: nav({ clipboard: { write: function () {} } }) },
    firefoxHttp: { secure: false, coarse: false, anchorDownload: true, clipboardItem: false, files: file, nav: nav({ clipboard: {} }) },
    old: { secure: false, coarse: false, anchorDownload: false, clipboardItem: false, files: null, nav: nav({}) },
    shareThatRefuses: { secure: true, coarse: true, anchorDownload: true, clipboardItem: true, files: file, nav: nav({ share: function () {}, canShare: function () { return false; } }) },
    shareThatThrows: { secure: true, coarse: true, anchorDownload: true, clipboardItem: true, files: file, nav: nav({ share: function () {}, canShare: function () { throw new Error("x"); } }) }
  };
"""


def share_buttons_follow_capability(root, tmp):
    """Share, Copy image and Download PNG are shown only where they can work, decided by testing the capability on an object that
    stands for navigator/window, never by the browser's name; with none of them the image and its sentence remain."""
    dash = dash_source(root)
    for name in ("navigator.userAgent", "userAgent", "/iPhone", "iPad", "Safari", "vendor"):
        assert name not in dash, "the page must not look at the browser's name (%s)" % name
    out = under_node(root, SHARE_ENVS + """
      var r = {}; Object.keys(envs).forEach(function (k) { r[k] = shareCaps(envs[k]); }); return r;
    """)
    if out is None:
        return
    assert out["iosHttp"] == {"share": False, "copy": False, "download": False}, "iOS over http: the image alone: %r" % out["iosHttp"]
    assert out["iosHttps"] == {"share": True, "copy": True, "download": True}, out["iosHttps"]
    assert out["chromeFile"] == {"share": False, "copy": True, "download": True}, out["chromeFile"]
    assert out["firefoxHttp"] == {"share": False, "copy": False, "download": True}, "no secure context, no copy: %r" % out["firefoxHttp"]
    assert out["old"] == {"share": False, "copy": False, "download": False}, out["old"]
    assert out["shareThatRefuses"]["share"] is False and out["shareThatThrows"]["share"] is False, "canShare saying no (or throwing) hides Share"
    # Every condition of every rule has a fake that only it decides: start from an environment where all three work and take away one thing.
    flips = under_node(root, """
      function base() { return { secure: true, coarse: true, anchorDownload: true, clipboardItem: true, files: [{}], nav: { share: function () {}, canShare: function () { return true; }, clipboard: { write: function () {} } } }; }
      var cuts = {
        none: function (e) {},
        no_share_fn: function (e) { delete e.nav.share; }, no_canShare: function (e) { delete e.nav.canShare; }, no_files: function (e) { e.files = null; }, canShare_no: function (e) { e.nav.canShare = function () { return false; }; },
        insecure: function (e) { e.secure = false; }, insecure_desktop: function (e) { e.secure = false; e.coarse = false; },
        no_clipboard: function (e) { delete e.nav.clipboard; }, no_write: function (e) { e.nav.clipboard = {}; }, no_item: function (e) { e.clipboardItem = false; },
        no_anchor: function (e) { e.anchorDownload = false; }
      };
      var r = {}; Object.keys(cuts).forEach(function (k) { var e = base(); cuts[k](e); r[k] = shareCaps(e); }); return r;
    """)
    T, F = True, False
    want = {"none": (T, T, T), "no_share_fn": (F, T, T), "no_canShare": (F, T, T), "no_files": (F, T, T), "canShare_no": (F, T, T),
            "insecure": (T, F, F), "insecure_desktop": (T, F, T), "no_clipboard": (T, F, T), "no_write": (T, F, T), "no_item": (T, F, T), "no_anchor": (T, T, F)}
    for k, (sh, cp, dl) in want.items():
        assert (flips[k]["share"], flips[k]["copy"], flips[k]["download"]) == (sh, cp, dl), "%s: %r" % (k, flips[k])




def share_refusal_says_what_to_do(root, tmp):
    """A refusal is never silent: it names the action that failed and what to do instead (press and hold the image, and
    Download PNG only where it is shown); the person closing the system sheet is not a refusal."""
    dash = dash_source(root)
    out = under_node(root, SHARE_ENVS + """
      var all = { share: true, copy: true, download: true }, none = { share: false, copy: false, download: false };
      return { c1: shareRefusal("copy", all), c2: shareRefusal("copy", none), s1: shareRefusal("share", all), s2: shareRefusal("share", none),
               d: shareRefusal("download", all), cancel: shareRefusal("share", all, { name: "AbortError" }), other: shareRefusal("share", none, { name: "NotAllowedError" }) };
    """)
    if out is None:
        return
    assert out["cancel"] is None, "closing the system sheet says nothing"
    codes = [out[k] for k in ("c1", "c2", "s1", "s2", "d")]
    assert all(codes) and len(set(codes)) == 5, "each action and each fallback has its own sentence: %r" % codes
    assert out["other"] == out["s2"], "a refusal other than a cancel is a refusal"
    said = set(re.findall(r"L\('((?:Could not (?:copy|share)|The browser did not)[^']*)'\)", dash))
    assert len(said) == 5 and all("hold" in x for x in said) and sum("Download PNG" in x for x in said) == 2, "five labelled sentences, each saying what to do: %r" % said
    for needle in ("Press and hold the image", "Use Download PNG"):
        assert needle in dash, needle
    body = dash[dash.index("function openShare("):dash.index("shareEl.addEventListener")]
    assert "shareRefusal(" in body and body.count("refuse(") >= 4, "share, copy and download each report a refusal"
    assert "copyImage(" in body and "shareImage(" in body and "msg.textContent" in body


def share_image_equals_the_download(root, tmp):
    """The image shown is the PNG the download hands over, byte for byte: one data URL per card is the image's source, the
    download's link, and (decoded) the copy and the shared file."""
    dash = dash_source(root)
    body = dash[dash.index("function openShare("):dash.index("shareEl.addEventListener")]
    assert dash.count('toDataURL("image/png")') == 1 and "exportCard(x[0]" in body, "the PNG is exported once per card"
    assert "href: img.src" in body, "the download link uses the image's own source"
    assert "copyImage(" in body and "shareImage(" in body and "pngBytes(img.src)" in body and "toBlob(" not in body, "copy and share decode that same URL"
    out = under_node(root, """
      var b = pngBytes("data:image/png;base64,iVBORw0KGgo=");
      return { n: b.length, head: Array.prototype.slice.call(b), bad: pngBytes("data:text/plain;base64,AAAA"), none: pngBytes("") };
    """)
    if out is None:
        return
    assert out["head"] == [137, 80, 78, 71, 13, 10, 26, 10], out
    assert out["bad"] is None and out["none"] is None, "only a PNG data URL decodes"
    sent = under_node(root, """
      function Blob_(parts, o) { this.parts = parts; this.type = o.type; }
      function File_(parts, n, o) { this.parts = parts; this.name = n; this.type = o.type; }
      function Item(d) { this.d = d; }
      var got = {};
      var env = { Blob: Blob_, File: File_, ClipboardItem: Item, nav: { share: function (d) { got.share = d; return { then: function () {} }; }, clipboard: { write: function (items) { got.copy = items; return { then: function () {} }; } } } };
      var res = {};
      [["h", "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"], ["v", "iVBORw0KGgoAAAANSUhEUgAAAAIAAAAC"]].forEach(function (c) {
        var url = "data:image/png;base64," + c[1], bytes = pngBytes(url);
        copyImage(env, bytes); shareImage(env, bytes, "demo-" + c[0] + ".png", "demo");
        var blob = got.copy[0].d["image/png"], file = got.share.files[0];
        res[c[0]] = { want: Array.prototype.slice.call(bytes), blob: Array.prototype.slice.call(blob.parts[0]), file: Array.prototype.slice.call(file.parts[0]), btype: blob.type, ftype: file.type, fname: file.name };
      });
      return res;
    """)
    if sent is None:
        return
    for fmt in ("h", "v"):
        r = sent[fmt]
        assert len(r["want"]) == 24 and r["blob"] == r["want"] and r["file"] == r["want"], "the copied and shared bytes are not the image's: %r" % r
        assert r["btype"] == "image/png" and r["ftype"] == "image/png" and r["fname"] == "demo-%s.png" % fmt, r
    with browser_page(root, tmp, rich_data(), "sum", phone=True) as pg:
        if pg is None:
            return
        got = pg.evaluate("""async () => { document.getElementById('share-btn').click();
          const im = Array.from(document.querySelectorAll('#share img.share-img')); await Promise.all(im.map(i => i.decode()));
          return im.map(i => ({ src: i.src.slice(0, 30), w: i.naturalWidth, h: i.naturalHeight })); }""")
        assert [(g["w"], g["h"]) for g in got] == [(1200, 630), (1080, 1920)], got
    with browser_page(root, tmp, rich_data(), "sum") as pg:  # a computer: the download is shown
        pg.evaluate("document.getElementById('share-btn').click()")
        with pg.expect_download() as dl:
            pg.click("#share .sc:not([hidden]) .acts button:last-child")
        data = open(dl.value.path(), "rb").read()
        shown = pg.evaluate("document.querySelector('#share .sc:not([hidden]) img.share-img').src")
        import base64
        assert shown == "data:image/png;base64," + base64.b64encode(data).decode("ascii"), "the downloaded file is not the image shown"


def share_dialog_shows_a_real_image(root, tmp):
    """The dialog shows each card as an <img> whose source is the exported PNG (a long press on it offers Save, Copy and Share),
    one sentence under it says so, a switch picks the format, and at 390x844 it fits without sideways scrolling."""
    dash = dash_source(root)
    body = dash[dash.index("function openShare("):dash.index("shareEl.addEventListener")]
    for needle in ('h("img"', "share-img", "L('Press and hold the image to save or share it (right-click on a computer).')", "aria-pressed", 'shareEl.addEventListener("close"', "shareCaps(env)"):
        assert needle in body or needle in dash, "the share dialog lost %s" % needle
    assert 'h("canvas"' in body and 'getElementById("share")' in dash and ".appendChild(cv)" not in body and "cvs.push(" in body, "the canvas only draws: it is never in the page"
    assert "fetch(" not in body and "XMLHttpRequest" not in body, "nothing here needs the network"
    with browser_page(root, tmp, rich_data(), "sum", phone=True) as pg:
        if pg is None:
            return
        for lang in ("en", "es"):
            pg.evaluate("localStorage.setItem('uak-language', '%s')" % lang)
            pg.reload()
            pg.wait_for_timeout(300)
            pg.evaluate("document.getElementById('share-btn').click()")
            pg.wait_for_timeout(300)
            assert pg.evaluate("document.querySelectorAll('#share img.share-img').length") == 2, "the dialog does not hold two <img> (canvas shown instead?)"
            assert pg.evaluate("document.querySelectorAll('#share canvas').length") == 0, "a canvas is in the dialog"
            for fmt in (0, 1):
                pg.evaluate("document.querySelectorAll('#share .fsw button')[%d].click()" % fmt)
                box = pg.evaluate("""() => { const d = document.getElementById('share').getBoundingClientRect(), im = (document.querySelector('#share .sc:not([hidden]) img.share-img') || document.body).getBoundingClientRect();
                  const bs = Array.from(document.querySelectorAll('#share .sc:not([hidden]) .acts button')).map(b => b.getBoundingClientRect());
                  return { dw: d.width, ih: im.height, iw: im.width, top: d.top, bottom: d.bottom, btn: bs.map(b => [b.top, b.bottom]), side: document.getElementById('share').scrollWidth > document.getElementById('share').clientWidth,
                           text: document.getElementById('share').innerText, vh: innerHeight }; }""")
                assert not box["side"] and box["dw"] <= 390, box
                assert box["iw"] >= 0.5 * (box["dw"] - 32) - 1, "the image is shown smaller than half its width allows: %r" % box
                assert all(b[1] <= box["vh"] and b[0] >= 0 for b in box["btn"]), "the actions are not visible without scrolling: %r" % box
                assert ("Mant\u00e9n pulsada" if lang == "es" else "Press and hold") in box["text"], box["text"][:300]
        pg.evaluate("localStorage.setItem('uak-language', 'en')")
        pg.reload()
        pg.wait_for_timeout(300)
        pg.focus("#share-btn")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(300)
        assert pg.evaluate("document.getElementById('share').open"), "Enter on Share does not open the dialog"
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(200)
        assert not pg.evaluate("document.getElementById('share').open") and pg.evaluate("document.activeElement && document.activeElement.id") == "share-btn", "after Escape the focus is not back on the Share button"


EXPORT_CANVAS = """
  function png(w, h) { var b = [137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, w >> 8, w & 255, 0, 0, h >> 8, h & 255], s = ""; b.forEach(function (x) { s += String.fromCharCode(x); }); return "data:image/png;base64," + btoa(s); }
"""


def share_export_failure_says_so(root, tmp):
    """When the card cannot be exported (toDataURL throws, or returns something that is not a PNG of the card's size), the dialog
    still opens, says in one sentence that the image could not be made and what to do, shows no action, and the error is kept
    in UAK_ERRORS; a broken image is never shown with Copy and Download that cannot work."""
    dash = dash_source(root)
    out = under_node(root, EXPORT_CANVAS + """
      var good = { toDataURL: function () { return png(1200, 630); } }, thrower = { toDataURL: function () { throw new Error("SecurityError"); } },
          empty = { toDataURL: function () { return "data:,"; } }, wrong = { toDataURL: function () { return png(300, 150); } }, notpng = { toDataURL: function () { return "data:image/jpeg;base64,AAAA"; } };
      function r(c) { var x = exportCard(c, 1200, 630); return { ok: !!x.url, error: !!x.error }; }
      return { good: r(good), thrower: r(thrower), empty: r(empty), wrong: r(wrong), notpng: r(notpng), v: exportCard({ toDataURL: function () { return png(1080, 1920); } }, 1080, 1920).url === png(1080, 1920) };
    """)
    if out is not None:
        assert out["good"] == {"ok": True, "error": False} and out["v"] is True, out
        for k in ("thrower", "empty", "wrong", "notpng"):
            assert out[k] == {"ok": False, "error": True}, "%s must be a failure: %r" % (k, out[k])
    body = dash[dash.index("function openShare("):dash.index("shareEl.addEventListener")]
    assert "exportCard(" in body and "ERRORS.push(" in body and "L('The image could not be made" in dash, "the export is guarded and says so"
    with browser_page(root, tmp, rich_data(), "sum", phone=True) as pg:
        if pg is None:
            return
        for label, js in (("throws", "throw new DOMException('tainted', 'SecurityError')"), ("empty", "return 'data:,'")):
            pg.evaluate("HTMLCanvasElement.prototype.toDataURL = function () { %s; }; 0" % js)
            pg.errors[:] = []
            pg.evaluate("window.UAK_ERRORS.length = 0; document.getElementById('share-btn').click()")
            pg.wait_for_timeout(300)
            st = pg.evaluate("""() => ({ open: document.getElementById('share').open, imgs: document.querySelectorAll('#share img').length, buttons: document.querySelectorAll('#share .acts button').length,
              text: document.getElementById('share').innerText, errors: window.UAK_ERRORS.length })""")
            assert st["open"] and st["imgs"] == 0 and st["buttons"] == 0 and st["errors"] >= 1 and ("could not be made" in st["text"] or "No se pudo hacer" in st["text"]), "%s: %r" % (label, st)
            assert not pg.errors, "%s: a page error escaped: %r" % (label, pg.errors)
            pg.evaluate("document.getElementById('share').close()")


TESTS = [blocked_tasks_are_not_available, frozen_is_frozen, needs_human_comes_first, offline_uses_last_claims,
         dashboard_meets_contrast_and_targets, dashboard_keeps_every_field, empty_project_says_the_next_step, no_server_no_request,
         page_is_not_heavier, both_profiles_and_languages_are_complete, messages_are_one_conversation_per_task, every_task_is_visible, square_says_why_it_waits,
         agents_show_model_and_harness, black_box_filter_finds_an_error, memory_graph_edges_come_from_data, tokens_break_down, share_card_matches_the_page,
         share_card_has_both_formats, share_dialog_shows_a_real_image, share_buttons_follow_capability, share_refusal_says_what_to_do, share_image_equals_the_download, share_export_failure_says_so, project_name_is_not_the_worktree, page_reloads_when_a_newer_page_is_written, no_native_select, one_definition_of_stalled, figures_agree_across_tabs, agents_are_compact_cards, board_opens_on_columns, memory_graph_is_readable, every_tab_renders_with_partial_data, titles_never_overflow]


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
