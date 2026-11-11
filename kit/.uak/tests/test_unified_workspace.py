#!/usr/bin/env python3
"""Unified workspace HTTP contracts; no browser or third-party runtime required."""
import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import test_setup_wizard as wizard


def language_and_navigation_are_available(root, tmp):
    with wizard.LiveServer() as server:
        status, page, _ = wizard.request(server, "GET", "/", token=False)
        assert status == 200 and b'id="language"' in page, "language selector must be part of the shared shell"
        assert b'id="open-dashboard"' in page, "the existing dashboard must be reachable in the same interface"
        status, script, _ = wizard.request(server, "GET", "/workspace.js", token=False)
        assert status == 200 and b"Espa" in script and b"English" in script
        assert b"localStorage" in script, "language choice must survive reloads"


def dashboard_requires_session_and_uses_real_plan(root, tmp):
    target = wizard.repository(tmp / "team project")
    (target / ".uak").mkdir()
    (target / ".uak/TASKS.md").write_text("# Plan\n\n## APP-001 · <img src=x onerror=alert(1)>\n- **Priority:** P0\n", encoding="utf-8")
    with wizard.LiveServer(str(target)) as server:
        assert wizard.request(server, "GET", "/api/dashboard", token=False)[0] == 403
        assert wizard.request(server, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        status, body, _ = wizard.request(server, "GET", "/api/dashboard")
        assert status == 200, "selected project must expose an authenticated dashboard snapshot"
        data = json.loads(body)
        assert data["source"] == "local" and data["progress"]["total"] == 1
        assert data["tasks"][0]["title"] == "<img src=x onerror=alert(1)>"
        assert not data["agents"], "do not invent a team to populate the dashboard"
        status, page, _ = wizard.request(server, "GET", "/dashboard", token=False)
        assert status == 200 and b"uak:dashboard" in page
        assert b'<script src="data.js"></script>' not in page, "embedded view receives data from the authenticated parent"


def backward_navigation_preserves_inputs_and_running_guard(root, tmp):
    text = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8")
    assert 'id="back-from-finish"' in text, "the final setup step needs Back, not only Choose another project"
    assert 'id="back-to-progress"' in text, "users reviewing choices during installation must be able to return to progress"
    assert 'id="dashboard-frame"' in text and 'sandbox="allow-scripts' in text
    assert 'allow-same-origin' not in text, "dashboard cannot access the parent session token"
    assert 'id="open-setup"' in text


TESTS = [language_and_navigation_are_available, dashboard_requires_session_and_uses_real_plan,
         backward_navigation_preserves_inputs_and_running_guard]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("unified_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    failed = 0
    for test in TESTS:
        with tempfile.TemporaryDirectory(prefix="uak-unified-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("UNIFIED_WORKSPACE_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
