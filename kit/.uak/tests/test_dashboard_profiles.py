#!/usr/bin/env python3
"""Dashboard profiles, the guided Beginner step and the "Your app" link: real HTTP and Git, disposable directories,
no network services. Tests named "contract" check the page's markup and code; the browser journey is their evidence."""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

import test_setup_wizard as wizard

DASH = None


def project(tmp, config="", tasks="# Plan\n\n## APP-001 · First\n- **Priority:** P0\n"):
    target = wizard.repository(tmp / "profiles project")
    (target / ".uak").mkdir()
    (target / ".uak/TASKS.md").write_text(tasks, encoding="utf-8")
    block = "```text\nMode: sprint\nBlackbox: on\nPace: auto\n%s```\n" % config
    (target / ".uak/PROJECT.md").write_text("# Project\n\n" + block + "\nKeep this paragraph.\n", encoding="utf-8")
    return target


def page(root):
    return (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")


class Region(HTMLParser):
    """Collects the start tags inside the element with a given id."""

    def __init__(self, ident):
        super().__init__()
        self.ident, self.depth, self.tags = ident, 0, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.depth:
            self.tags.append((tag, attrs))
            if tag not in ("input", "br", "img", "meta", "link"):
                self.depth += 1
        elif attrs.get("id") == self.ident:
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1


def region(root, ident):
    parser = Region(ident)
    parser.feed(page(root))
    return parser.tags


def live_url_is_https_only(root, tmp):
    ok = DASH.live_url
    assert ok("https://app.example.com/demo?x=1") == "https://app.example.com/demo?x=1"
    assert ok("  https://app.example.com  ") == "https://app.example.com", "surrounding spaces are not part of it"
    for bad in ("http://app.example.com", "javascript:alert(1)", "data:text/html,x", "https://user:pw@app.example.com",
                "https://", "https:///path", "https://app.example.com/a b", "https://app.example.com/\u0000",
                "https://a.example.com/" + "x" * 3000, "-", "", None, 42):
        assert ok(bad) is None, "not a deploy link: %r" % (bad,)


def live_url_link_is_shown_when_set(root, tmp):
    target = project(tmp, "Live-URL: https://demo.example.com\n")
    with wizard.LiveServer(str(target)) as server:
        assert wizard.request(server, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        data = json.loads(wizard.request(server, "GET", "/api/dashboard")[1])
        assert data.get("live_url") == "https://demo.example.com", "a valid Live-URL reaches the dashboard"
    (tmp / "hostile").mkdir()
    hostile = project(tmp / "hostile", "Live-URL: javascript:alert(1)\n")
    with wizard.LiveServer(str(hostile)) as server:
        wizard.request(server, "POST", "/api/inspect", {"target": str(hostile)})
        data = json.loads(wizard.request(server, "GET", "/api/dashboard")[1])
        assert data.get("live_url") is None, "an invalid Live-URL is never a link"
    tags = region(root, "your-app")
    links = [a for t, a in tags if t == "a" and a.get("id") == "live-url-link"]
    assert links and links[0].get("target") == "_blank" and links[0].get("rel") == "noopener noreferrer", \
        "the link opens in a new tab without access to this page"
    assert any(a.get("id") == "live-url-empty" for _, a in tags), "without a link the section says so"


def live_url_is_saved_atomically_and_added_when_missing(root, tmp):
    target = project(tmp)
    config = target / ".uak/PROJECT.md"
    before = config.read_text(encoding="utf-8")
    assert wizard.MODULE.save_settings(target, {"Live-URL": "https://demo.example.com"})
    after = config.read_text(encoding="utf-8")
    assert after == before.replace("Pace: auto\n", "Pace: auto\nLive-URL: https://demo.example.com\n"), \
        "an older PROJECT.md gets the key inside the executable block, every other byte kept"
    assert wizard.MODULE.save_settings(target, {"Live-URL": "https://new.example.com"})
    assert "Live-URL: https://new.example.com\n" in config.read_text(encoding="utf-8")
    for bad in ("http://x.example.com", "https://x.example.com\nBacklog-Approved: yes", "javascript:alert(1)"):
        snapshot = config.read_bytes()
        try:
            wizard.MODULE.save_settings(target, {"Live-URL": bad})
        except ValueError:
            pass
        else:
            raise AssertionError("refuse %r" % bad)
        assert config.read_bytes() == snapshot


def next_action_matches_real_state(root, tmp):
    target = project(tmp)
    ready = "OK    1. kit installed\n\nSTART READY · bash .uak/bin/wt new APP-001   (branch + worktree + claim)\n"

    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, ready, "")
    (target / ".uak/bin").mkdir()
    (target / ".uak/bin/uak").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (target / ".uak/VERSION").write_text((root / ".uak/VERSION").read_text(encoding="utf-8"), encoding="utf-8")
    with wizard.LiveServer(str(target), run) as server:
        wizard.request(server, "POST", "/api/inspect", {"target": str(target)})
        assert wizard.request(server, "POST", "/api/check", {})[0] == 202
        server.worker.join(10)
        status = json.loads(wizard.request(server, "GET", "/api/status")[1])
        board = json.loads(wizard.request(server, "GET", "/api/dashboard")[1])
        assert status["guidance"] == board["guidance"], "Configuration and the dashboard show the same next step"
        assert status.get("completed") == ["kit installed"], "the guided checklist is the gate's passed steps, as text"


def copy_command_is_exact(root, tmp):
    g = wizard.MODULE.guidance
    ready = wizard.MODULE.readiness("START READY · bash .uak/bin/wt new APP-7   (note)\n", 0)
    assert g(dict(ready, installed=True, phase="ready"))["commands"] == ["bash .uak/bin/wt new APP-7"]
    todo = {"installed": True, "phase": "setup", "checks": [{"state": "todo", "text": "2. push\ngit push origin main"}]}
    assert g(todo)["commands"] == [], "only the claim command is ever copyable"


def beginner_shows_one_action(root, tmp):
    """Contract: the guided step has exactly one primary action, a reason and a checklist."""
    tags = region(root, "beginner-step")
    primaries = [a for t, a in tags if t == "button" and "primary" in (a.get("class") or "").split()]
    assert len(primaries) == 1, "one primary action per step, found %d" % len(primaries)
    ids = {a.get("id") for _, a in tags}
    assert {"beginner-why", "beginner-checklist"} <= ids, "the step says why it matters and what is already done"


def beginner_profile_persists(root, tmp):
    """Contract: the View choice offers both profiles and is kept in this browser (never written to the project)."""
    text = page(root)
    values = re.findall(r'<option value="(beginner|advanced)"', text)
    assert sorted(set(values)) == ["advanced", "beginner"]
    assert 'localStorage.setItem("uak-profile"' in text and 'localStorage.getItem("uak-profile")' in text
    assert "uak-profile" not in (root / ".uak/bin/lib/setup.py").read_text(encoding="utf-8"), \
        "a presentation choice never reaches the server"


def advanced_profile_preserves_details(root, tmp):
    target = project(tmp)
    with wizard.LiveServer(str(target)) as server:
        status, body, _ = wizard.request(server, "GET", "/dashboard", token=False)
        assert status == 200
        for tab in ('"board"', '"agents"', '"talk"', '"bb"', '"memory"', '"tokens"'):
            assert tab.encode() in body, "the detailed dashboard keeps its %s view" % tab
        wizard.request(server, "POST", "/api/inspect", {"target": str(target)})
        data = json.loads(wizard.request(server, "GET", "/api/dashboard")[1])
        assert {"tasks", "agents", "progress", "offers"} <= set(data), "the full model still reaches Advanced"


def hostile_content_is_text(root, tmp):
    title = "<img src=x onerror=alert(1)>"
    target = project(tmp, "Live-URL: https://demo.example.com/<script>\n", "# Plan\n\n## APP-001 · %s\n" % title)
    with wizard.LiveServer(str(target)) as server:
        wizard.request(server, "POST", "/api/inspect", {"target": str(target)})
        data = json.loads(wizard.request(server, "GET", "/api/dashboard")[1])
        assert data["tasks"][0]["title"] == title, "task text comes back verbatim, for textContent"
        assert data.get("live_url") in (None, "https://demo.example.com/<script>")
    assert "innerHTML" not in page(root), "the setup page never parses data as HTML"


def static_dashboard_remains_offline(root, tmp):
    target = project(tmp, "Live-URL: https://demo.example.com\n")
    claims, out = tmp / "claims", tmp / "out"
    (claims / "meta").mkdir(parents=True)
    result = subprocess.run([sys.executable, str(root / ".uak/bin/lib/dash.py"), "--claims", str(claims),
                             "--out", str(out)], cwd=str(target), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr[-500:]
    html = (out / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'<(script|link)[^>]+(src|href)="https?:', html), "no network asset in the export"
    data = (out / "data.js").read_text(encoding="utf-8")
    assert '"live_url":"https://demo.example.com"' in data, "the offline export carries the deploy link"


def ready_opens_progress(root, tmp):
    """Contract: a finished check that is ready moves to project progress (the browser QA is the evidence)."""
    text = page(root)
    assert re.search(r'if \(data\.ready \|\| currentSection === "dashboard"\)\s*\{[^}]*openSection\("dashboard"\)', text)


TESTS = [live_url_is_https_only, live_url_link_is_shown_when_set, live_url_is_saved_atomically_and_added_when_missing,
         next_action_matches_real_state, copy_command_is_exact, beginner_shows_one_action, beginner_profile_persists,
         advanced_profile_preserves_details, hostile_content_is_text, static_dashboard_remains_offline,
         ready_opens_progress]


def main():
    global DASH
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("profiles_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("profiles_dash", root / ".uak/bin/lib/dash.py")
    DASH = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(DASH)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-profiles-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("DASHBOARD_PROFILES_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
