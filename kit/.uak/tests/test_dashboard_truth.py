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
    themes = {"dash light": css_tokens(dash, ":root"), "dash dark": css_tokens(dash, ':root[data-theme="dark"]'),
              "dash auto dark": css_tokens(dash, ':root:not([data-theme="light"])')}
    for name, t in themes.items():
        for text in ("ink", "ink-2", "muted", "accent-ink"):
            for back in ("page", "surface", "raised", "hover"):
                if contrast(t[text], t[back]) < 4.5:
                    low.append("%s --%s on --%s %.2f" % (name, text, back, contrast(t[text], t[back])))
        for text, back in (("warn-ink", "warn-wash"), ("crit-ink", "crit-wash"), ("accent-ink", "accent-wash"),
                           ("muted", "accent-wash"), ("muted", "warn-wash"), ("muted", "crit-wash")):
            if contrast(t[text], t[back]) < 4.5:
                low.append("%s --%s on --%s %.2f" % (name, text, back, contrast(t[text], t[back])))
    themes = {"setup light": css_tokens(page, ":root"), "setup dark": css_tokens(page, ':root[data-theme="dark"]'),
              "setup auto dark": css_tokens(page, ':root:not([data-theme="light"]):not([data-theme="dark"])')}
    for name, t in themes.items():
        for text in ("ink", "secondary", "muted"):
            for back in ("bg", "paper", "wash"):
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


TESTS = [blocked_tasks_are_not_available, frozen_is_frozen, needs_human_comes_first, offline_uses_last_claims,
         dashboard_meets_contrast_and_targets]


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
