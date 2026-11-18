#!/usr/bin/env python3
"""UI-021: forms say what is wrong next to the field.
Evidence: QA round D of 2026-11-14 (notes/handoff:qa/rounds-2026-11-14/D-REPORT.md, top 1 and 2 and "Other findings")
and round A (A-REPORT.md F13, F14): name, schedule and idea errors went to a global box ~2,900 px below the field with
the focus on <body> and no aria-invalid; "Mars/Base" was accepted as a time zone and a Freeze-Epoch computed; the
schedule confirmation gave weekdays without dates in reversed order ("stops Wed 06:24; take the first task by Tue
11:55"); a relative folder said "does not exist"; native English validation bubbles.
Real HTTP, real Git, the engine's real `uak clock`; the page is read as text (no browser in the suite)."""
import argparse
import datetime
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import test_setup_planning as tp
import test_setup_prepare as prep
import test_setup_wizard as wizard
from test_hack import resolve_binary

ROW = re.compile(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]')
# The page's input for each field the server can name in a refusal ("field": …).
FIELDS = {"target": "target", "name": "human-name", "start": "schedule-start", "end": "schedule-end",
          "zone": "schedule-zone", "idea": "idea-text", "audience": "idea-audience", "rubric": "idea-goal",
          "goal": "idea-goal", "event_length": "idea-length", "team_size": "idea-team"}
GOOD = {"start": "2026-11-12 10:00", "end": "2026-11-12 13:00", "zone": "America/Mexico_City"}


def page():
    return Path(wizard.MODULE.__file__).with_name("setup.html").read_text(encoding="utf-8")


def catalog():
    """workspace.js: exact rows (every table) and the NOTES patterns; rows split over lines with a trailing comma too."""
    text = Path(wizard.MODULE.__file__).with_name("workspace.js").read_text(encoding="utf-8")
    exact = {json.loads(a) for a, _ in ROW.findall(text)}
    start = text.index("var NOTES = [")
    notes = text[start:text.index("\n  ];", start)]
    return exact, [json.loads(a) for a, _ in ROW.findall(notes)]


def spanish(*texts):
    exact, patterns = catalog()
    missing = [t for t in texts if t and t not in exact and not any(re.fullmatch(p, t) for p in patterns)]
    assert not missing, "no Spanish entry in workspace.js for: %r" % missing


def refused(srv, path, data, field):
    status, body = tp.post(srv, path, data)
    assert status in (400, 409), "refused: %r -> %s %r" % (data, status, body)
    assert body.get("field") == field, "the refusal names the field %r: %r" % (field, body)
    spanish(body.get("error"))
    return body


def function_body(html, name):
    start = html.index("function %s(" % name)
    depth, i = 0, html.index("{", start)
    for j in range(i, len(html)):
        depth += {"{": 1, "}": -1}.get(html[j], 0)
        if depth == 0:
            return html[start:j + 1]
    raise AssertionError("function %s is not closed" % name)


def engine_clock(target, start, end, zone):
    shown = subprocess.run([resolve_binary("bash"), str(target / ".uak/bin/uak"), "clock", start, end, zone],
                           cwd=str(target), capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items() if not k.startswith("UAK_")})
    assert shown.returncode == 0, shown.stderr
    return shown.stdout


# --- the four named tests of UI-021's forms ---------------------------------------------------------------------------


def field_errors_sit_next_to_the_field(root, tmp):
    """D top 1: every form refusal names its field; the page shows it under that field, marks it invalid and focuses it."""
    target, _ = prep.installed(root, tmp)
    with tp.live(target, tp.FakePlanner()) as srv:
        refused(srv, "/api/inspect", {"target": str(tmp / "no such folder")}, "target")
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        refused(srv, "/api/human", {"name": "Ana Maria"}, "name")
        refused(srv, "/api/schedule", dict(GOOD, start="tomorrow"), "start")
        refused(srv, "/api/schedule", dict(GOOD, end="2026-11-12 09:00"), "end")
        refused(srv, "/api/schedule", dict(GOOD, zone="x; rm -rf ~"), "zone")
        idea = tp.idea_fields()
        refused(srv, "/api/idea", dict(idea, idea="   "), "idea")
        refused(srv, "/api/idea", dict(idea, audience=""), "audience")
        refused(srv, "/api/idea", dict(idea, rubric=""), "rubric")
        refused(srv, "/api/idea", dict(idea, event_length="x" * 61), "event_length")
        refused(srv, "/api/idea", dict(idea, team_size=0), "team_size")
        assert not (target / "IDEA.md").exists(), "a refused idea writes nothing"
    html = page()
    for field, input_id in FIELDS.items():
        assert re.search(r'\b%s: "%s"' % (re.escape(field), re.escape(input_id)), html), \
            "the page maps the field %r to #%s" % (field, input_id)
        assert 'id="%s"' % input_id in html, "#%s exists" % input_id
    shown = function_body(html, "fieldError")
    for part in ('"aria-invalid"', '"aria-describedby"', ".focus()", "-error"):
        assert part in shown, "fieldError sets %s: %s" % (part, shown[:300])
    assert re.search(r"fieldError\(", function_body(html, "action").split("catch (e)", 1)[1]), \
        "a failed request with a field shows the message at the field, not only in the global box"
    # Page messages instead of native (English) bubbles: every form validates itself.
    for form in ("project-form", "schedule-form", "idea-form", "workflow-form"):
        assert re.search(r'<form[^>]*id="%s"[^>]*\bnovalidate\b' % form, html), "#%s has novalidate" % form
    checked = function_body(html, "checkFields")
    assert "fieldError(" in checked, "empty fields are named by the page, next to them"
    spanish("Fill in this field.", "Use a whole number from 1 to 50.")
    # Layout: a gap above "Save the idea" (F14) and schedule inputs that shrink instead of overlapping (F13).
    assert re.search(r"#idea-save\s*\{[^}]*margin-top:\s*(1[2-9]|2\d)px", html), "a field gap above Save the idea"
    assert re.search(r"\.prepare-row input\s*\{[^}]*min-width:\s*0", html), "schedule inputs can shrink (F13)"


def invalid_time_zone_is_refused(root, tmp):
    """D top 2: "Mars/Base" was accepted (HTTP 200) and a Freeze-Epoch computed; the zone list starts with the browser's."""
    target, _ = prep.installed(root, tmp)
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        before = (target / ".uak/PROJECT.md").read_bytes()
        # Without a zone database (Python on Windows has none unless tzdata is installed) only the IANA areas are known.
        assert hasattr(wizard.MODULE, "zone_database"), "setup knows whether this computer has a zone database"
        known = wizard.MODULE.zone_database()
        for zone in ("Mars/Base", "Moon/Tranquility") + (("America/Atlantis", "Etc/Mars") if known else ()):
            body = refused(srv, "/api/schedule", dict(GOOD, zone=zone), "zone")
            body = refused(srv, "/api/schedule", dict(GOOD, zone=zone, preview=True), "zone")
            assert zone in body["error"], "the refusal names the zone it refused: %r" % body
        assert (target / ".uak/PROJECT.md").read_bytes() == before, "a refused zone writes nothing"
        for zone in ("UTC", "Etc/GMT+6", "America/Mexico_City", "America/Argentina/Buenos_Aires"):
            status, body = tp.post(srv, "/api/schedule", dict(GOOD, zone=zone, preview=True))
            assert status == 200, "%s is a real zone: %r" % (zone, body)
    html = page()
    assert re.search(r'id="schedule-zone"[^>]*\blist="schedule-zones"', html), "the zone input offers a list"
    assert '<datalist id="schedule-zones"' in html, "the list exists"
    filled = function_body(html, "fillZones")
    assert "resolvedOptions().timeZone" in filled and "supportedValuesOf" in filled, \
        "the list starts with the browser's zone and offers the others the browser knows"


def schedule_shows_dates_in_order(root, tmp):
    """D other findings: the confirmation said "stops Wed 06:24; take the first task by Tue 11:55" (no dates, reversed)."""
    target, _ = prep.installed(root, tmp)
    start, end, zone = "2026-11-12 22:00", "2026-11-14 10:00", "America/Mexico_City"
    with tp.live(target, tp.FakePlanner()) as srv:
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        status, look = tp.post(srv, "/api/schedule", {"start": start, "end": end, "zone": zone, "preview": True})
        assert status == 200, look
        status, body = tp.post(srv, "/api/schedule", {"start": start, "end": end, "zone": zone})
        assert status == 200, body
    clock = engine_clock(target, start, end, zone)
    first_shown = re.search(r"(?m)^first claim by\s+(\S+) (\d\d:\d\d)", clock)
    freeze_shown = re.search(r"(?m)^freeze\s+(\S+) (\d\d:\d\d)", clock)
    stamp = r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\Z"
    for reply in (look, body):
        assert re.match(stamp, reply.get("freeze_at", "")), "the freeze has its date: %r" % reply
    first = re.match(stamp, body.get("first_claim_at", ""))
    freeze = re.match(stamp, body["freeze_at"])
    assert first, "the first claim has its date: %r" % body
    # The engine's weekday and time, now with the date of that weekday inside the event.
    assert (first.group(1), first.group(3)) == first_shown.groups(), (body, clock)
    assert (freeze.group(1), freeze.group(3)) == freeze_shown.groups(), (body, clock)
    as_time = lambda m: datetime.datetime.strptime(m.group(2) + " " + m.group(3), "%Y-%m-%d %H:%M")
    begin, finish = (datetime.datetime.strptime(t, "%Y-%m-%d %H:%M") for t in (start, end))
    assert begin <= as_time(first) < as_time(freeze) <= finish, "in order, inside the event: %r" % body
    assert as_time(first).strftime("%a") == first.group(1) and as_time(freeze).strftime("%a") == freeze.group(1)
    assert as_time(first) == datetime.datetime(2026, 11, 13, 0, 0), "2 h after a 22:00 start is the next day: %r" % body
    html = page()
    saved = re.search(r'"(Saved\. [^"]*\{first\}[^"]*\{freeze\}[^"]*)"', html)
    assert saved, "the confirmation names the first claim, then the freeze"
    spanish(saved.group(1))
    exact, _ = catalog()
    text = Path(wizard.MODULE.__file__).with_name("workspace.js").read_text(encoding="utf-8")
    es = dict((json.loads(a), json.loads(b)) for a, b in ROW.findall(text)).get(saved.group(1), "")
    assert es.index("{first}") < es.index("{freeze}"), "the Spanish keeps the order: %r" % es
    assert "first_claim_at" in html and "freeze_at" in html, "the page shows the dated times"


def relative_path_says_so(root, tmp):
    """D other findings: a relative folder ("my-app") said "This folder does not exist"."""
    target, _ = prep.installed(root, tmp)
    with tp.live(target, tp.FakePlanner()) as srv:
        for relative in ("my-app", "./my-app", "projects/my-app", target.name):
            body = refused(srv, "/api/inspect", {"target": relative}, "target")
            assert "full path" in body["error"] and "does not exist" not in body["error"], body
        body = refused(srv, "/api/inspect", {"target": str(tmp / "gone")}, "target")
        assert "does not exist" in body["error"], "an absolute missing folder still says so: %r" % body
        assert tp.post(srv, "/api/inspect", {"target": str(target)})[0] == 200, "the full path works"


TESTS = [field_errors_sit_next_to_the_field, invalid_time_zone_is_refused, schedule_shows_dates_in_order,
         relative_path_says_so]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    for key in [k for k in os.environ if k.startswith("UAK_")]:  # UAK_BASE/UAK_REMOTE would change the server's base
        del os.environ[key]
    spec = importlib.util.spec_from_file_location("forms_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("forms_planning", root / ".uak/bin/lib/planning.py")
    tp.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp.PLANNING)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-forms-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("SETUP_FORMS_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
