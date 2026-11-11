#!/usr/bin/env python3
"""Visual setup behavior: real HTTP and Git, disposable directories, no network services."""
import argparse
import http.client
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
import traceback
from html.parser import HTMLParser
from pathlib import Path

from test_hack import resolve_binary

MODULE = None


def request(server, method, path, data=None, token=True, origin=True, extra=None):
    host = "127.0.0.1:%d" % server.server_port
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-UAK-Token"] = server.token
    if origin:
        headers["Origin"] = "http://" + host
    headers.update(extra or {})
    body = json.dumps(data).encode() if data is not None else None
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        conn.request(method, path, body, headers)
        res = conn.getresponse()
        return res.status, res.read(), dict(res.getheaders())
    finally:
        conn.close()


class LiveServer:
    def __init__(self, target="", run=None, installer=None):
        self.server = MODULE.make_server(target, installer=installer, run=run)
        assert self.server is not None, "AssertionError: wizard must provide a loopback server before installation"

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.server

    def __exit__(self, *args):
        if self.server.worker:
            self.server.worker.join(125)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)


def repository(path):
    path.mkdir()
    subprocess.run([resolve_binary("git"), "init", "-q", str(path)], check=True, capture_output=True)
    return path


def wizard_starts_before_installation(root, tmp):
    missing = tmp / "not-created"
    with LiveServer(str(missing)) as srv:
        status, html, headers = request(srv, "GET", "/", token=False, origin=False)
        assert status == 200 and b"<html" in html, "AssertionError: welcome renders before repository validation"
        assert not missing.exists(), "AssertionError: opening welcome must not write to the target"
        assert srv.server_address[0] == "127.0.0.1", "AssertionError: bind only to loopback"
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        assert request(srv, "GET", "/.env")[0] == 404
        assert request(srv, "GET", "/../install.sh")[0] == 404
        state = json.loads(request(srv, "GET", "/api/status")[1])
        assert state["phase"] == "welcome" and not state["ready"]


def legacy_install_remains_noninteractive(root, tmp):
    installer = root.parent / "install.sh"
    if not installer.is_file():
        # An installed project ships the engine without the kit's installer: check what setup says there instead.
        return installer_absent_package_is_explicit(root, tmp)
    text = installer.read_text(encoding="utf-8")
    assert "--wizard" in text, "AssertionError: installer needs an explicit visual entry point"
    result = subprocess.run([resolve_binary("bash"), str(installer), "--help"], capture_output=True, timeout=15)
    assert result.returncode == 0 and b"--mode" in result.stdout
    result = subprocess.run([resolve_binary("bash"), str(installer)], capture_output=True, timeout=15)
    assert result.returncode == 2 and b"Missing --mode" in result.stderr


def invalid_requests_cannot_mutate(root, tmp):
    target = repository(tmp / "secure target")
    with LiveServer(str(target)) as srv:
        for kwargs in ({"token": False}, {"extra": {"X-UAK-Token": "wrong"}},
                       {"extra": {"Origin": "https://evil.example"}}, {"origin": False},
                       {"extra": {"Host": "evil.example"}},
                       {"extra": {"Content-Type": "text/plain"}}):
            assert request(srv, "POST", "/api/install", {"mode": "sprint"}, **kwargs)[0] in (400, 403, 415)
        assert request(srv, "GET", "/api/status", token=False)[0] == 403
        assert request(srv, "POST", "/api/install", {"mode": "sprint", "command": "whoami"})[0] == 400
        assert request(srv, "POST", "/api/inspect", {"target": "x" * 70000})[0] == 413
        assert not (target / ".uak").exists(), "AssertionError: rejected requests must not install"


def installer_arguments_are_literal(root, tmp):
    target = str(tmp / "space & $(touch should-not-exist)")
    cmd = MODULE.install_command(root.parent / "install.sh", target,
                                 {"mode": "marathon", "harness": ["codex", "claude"], "stack": "none", "blackbox": False, "solo": True})
    assert target in cmd, "AssertionError: target must be a literal subprocess argument"
    assert "--mode" in cmd and "--solo" in cmd and "--no-blackbox" in cmd
    assert cmd[cmd.index("--harness") + 1] == "codex,claude"
    for options in ({"mode": "invalid"}, {"mode": "sprint", "harness": ["codex;whoami"]},
                    {"mode": "sprint", "blackbox": "false"}, {"mode": "sprint", "extra": "--update"}):
        try:
            MODULE.install_command(root.parent / "install.sh", target, options)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid options must be refused before execution")


def duplicate_install_is_rejected(root, tmp):
    target = repository(tmp / "duplicate target")
    started, release = threading.Event(), threading.Event()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        started.set()
        release.wait(8)
        return subprocess.CompletedProcess(command, 1, "", "Installation failed")

    # The fake runner never executes the installer; it only has to exist (an installed project has none).
    installer = tmp / "kit checkout" / "install.sh"
    installer.parent.mkdir()
    installer.write_text("", encoding="utf-8")
    with LiveServer(str(target), fake_run, installer=installer) as srv:
        assert request(srv, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        try:
            assert request(srv, "POST", "/api/install", {"mode": "sprint", "harness": ["codex"]})[0] == 202
            assert started.wait(3), "AssertionError: installer must start asynchronously"
            assert request(srv, "POST", "/api/install", {"mode": "sprint"})[0] == 409
            assert request(srv, "POST", "/api/inspect", {"target": str(tmp)})[0] == 409
        finally:
            release.set()
            srv.worker.join(5)
        state = json.loads(request(srv, "GET", "/api/status")[1])
        assert len(calls) == 1 and state["phase"] == "error" and not state["ready"]


def setup_preserves_unrelated_settings(root, tmp):
    target = repository(tmp / "settings target")
    config = target / ".uak/PROJECT.md"
    config.parent.mkdir()
    original = "# My project\n\n```text\nMode: marathon\nBlackbox: on\nBacklog-Approved: no\nReview-Mode: gh\n```\n\nKeep this custom paragraph.\n"
    config.write_text(original, encoding="utf-8")
    assert MODULE.save_settings(target, {"Blackbox": "off"}), "AssertionError: allowlisted setup settings must persist"
    assert config.read_text(encoding="utf-8") == original.replace("Blackbox: on", "Blackbox: off")
    for settings in ({"Backlog-Approved": "yes"}, {"Mode": "sprint"}, {"Review-Mode": "claims"},
                     {"Blackbox": "off\nBacklog-Approved: yes"}, {"UAK_HUMAN": "someone"}):
        before = config.read_bytes()
        try:
            MODULE.save_settings(target, settings)
        except ValueError:
            pass
        else:
            raise AssertionError("browser settings cannot grant authority")
        assert before == config.read_bytes()


def installed_is_not_ready(root, tmp):
    result = MODULE.readiness("OK 1. kit installed\nTODO 2. add remote\nSTART · 1 thing to do\n", 0)
    assert result["checks"] and not result["ready"], "AssertionError: expose existing readiness blockers"
    assert MODULE.readiness("START READY · bash .uak/bin/wt new APP-001\n", 0)["ready"]
    assert not MODULE.readiness("START READY · bash .uak/bin/wt new APP-001\n", 1)["ready"]
    assert not MODULE.readiness("NOTE output contains START READY somewhere\n", 0)["ready"]


def partial_install_can_recover(root, tmp):
    if not (root.parent / "install.sh").is_file():
        return installer_absent_package_is_explicit(root, tmp)
    target = repository(tmp / "recover target")
    (target / ".claude").write_text("Keep this user file", encoding="utf-8")
    with LiveServer(str(target)) as srv:
        assert request(srv, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        options = {"mode": "marathon", "harness": ["claude"], "blackbox": False}
        assert request(srv, "POST", "/api/install", options)[0] == 202
        srv.worker.join(90)
        assert not srv.worker.is_alive()
        state = json.loads(request(srv, "GET", "/api/status")[1])
        assert state["phase"] == "error" and not state["installed"], "a failed installation is never completed"
        state = json.loads(request(srv, "POST", "/api/inspect", {"target": str(target)})[1])
        assert state.get("can_repair"), "a partial installation needs an explicit repair path"
        assert (target / ".claude").read_text(encoding="utf-8") == "Keep this user file"
        assert request(srv, "POST", "/api/repair", dict(options, mode="sprint"))[0] == 400
        # The user resolves the actual collision; setup must never move their files for them.
        (target / ".claude").rename(target / ".claude.saved")
        assert request(srv, "POST", "/api/repair", dict(options, harness=["codex"]))[0] == 202
        srv.worker.join(90)
        state = json.loads(request(srv, "GET", "/api/status")[1])
        if state["phase"] != "installed":
            print("REPAIR_DETAILS " + state.get("details", "")[-2000:])
        assert state["phase"] == "installed" and state["installed"] and not state["ready"]
        assert (target / ".claude.saved").read_text(encoding="utf-8") == "Keep this user file"


def ambiguous_settings_are_not_reported_saved(root, tmp):
    target = repository(tmp / "ambiguous target")
    config = target / ".uak/PROJECT.md"
    config.parent.mkdir()
    original = "Blackbox: on\n```text\nMode: marathon\nBlackbox: off\nPace: auto\n```\n"
    config.write_text(original, encoding="utf-8")
    try:
        MODULE.save_settings(target, {"Blackbox": "off"})
    except ValueError:
        pass
    else:
        raise AssertionError("refuse duplicate effective settings outside the executable block")
    assert config.read_text(encoding="utf-8") == original
    config.write_text("```text\n- **Mode:** `marathon`\n- **Blackbox:** `off`\n- **Pace:** `auto`\n```\n", encoding="utf-8")
    with LiveServer(str(target)) as srv:
        inspected = json.loads(request(srv, "POST", "/api/inspect", {"target": str(target)})[1])
        assert inspected["settings"]["Blackbox"] == "off", "display uses the authoritative configuration reader"


def an_older_installed_engine_is_not_ready(root, tmp):
    target = repository(tmp / "older target")
    (target / ".uak/bin").mkdir(parents=True)
    (target / ".uak/PROJECT.md").write_text("```text\nMode: marathon\nBlackbox: on\nPace: auto\n```\n", encoding="utf-8")
    (target / ".uak/VERSION").write_text("0.0.1\n", encoding="utf-8")
    (target / ".uak/bin/uak").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    with LiveServer(str(target)) as srv:
        assert request(srv, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        status, body, _ = request(srv, "POST", "/api/check", {})
        assert status == 400 and b"version" in body.lower(), "trusted source engine cannot certify a different installed version"


def all_stack_presets_are_selectable(root, tmp):
    class Options(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack = False
            self.values = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "select":
                self.stack = attrs.get("id") == "stack"
            if self.stack and tag == "option":
                self.values.append(attrs.get("value"))

        def handle_endtag(self, tag):
            if tag == "select":
                self.stack = False

    parser = Options()
    parser.feed((root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8"))
    assert set(parser.values) == set(MODULE.STACKS), "every supported preset must be a real option element"


def installer_absent_package_is_explicit(root, tmp):
    target = repository(tmp / "no installer target")
    missing = tmp / "kit checkout" / "install.sh"
    with LiveServer(str(target), installer=missing) as srv:
        assert request(srv, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        status, body, _ = request(srv, "POST", "/api/install", {"mode": "sprint", "harness": ["claude"]})
        assert status == 400 and b"install.sh --wizard" in body, "without the kit's installer, setup names where to run it"
        assert srv.worker is None and not (target / ".uak").exists(), "nothing starts and nothing is written"


def nested_json_is_rejected(root, tmp):
    with LiveServer() as srv:
        conn = raw_connection(srv)
        body = b"[" * 60000
        conn.request("POST", "/api/inspect", body, {"Host": "127.0.0.1:%d" % srv.server_port, "X-UAK-Token": srv.token,
                                                    "Origin": "http://127.0.0.1:%d" % srv.server_port,
                                                    "Content-Type": "application/json"})
        try:
            status = conn.getresponse().status
        except http.client.HTTPException as exc:
            raise AssertionError("deeply nested JSON must get an answer, not a dropped connection (%s)" % type(exc).__name__)
        finally:
            conn.close()
        assert status == 400, "deeply nested JSON is a bad request"
        assert request(srv, "GET", "/api/status")[0] == 200, "the server keeps serving"


def raw_connection(srv):
    return http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)


def installer_bash_is_preferred(root, tmp):
    fake = tmp / "Git" / "bin" / ("bash.exe" if os.name == "nt" else "bash")
    fake.parent.mkdir(parents=True)
    fake.write_text("", encoding="utf-8")
    saved = os.environ.get("UAK_SETUP_BASH")
    try:
        os.environ["UAK_SETUP_BASH"] = str(fake)
        assert MODULE.bash_binary() == str(fake), "the Bash that launched install.sh --wizard is used, wherever Git lives"
        os.environ["UAK_SETUP_BASH"] = str(tmp / "missing" / fake.name)
        assert MODULE.bash_binary() != os.environ["UAK_SETUP_BASH"], "a Bash path that does not exist is ignored"
    finally:
        if saved is None:
            os.environ.pop("UAK_SETUP_BASH", None)
        else:
            os.environ["UAK_SETUP_BASH"] = saved
    text = (root.parent / "install.sh").read_text(encoding="utf-8") if (root.parent / "install.sh").is_file() else ""
    assert not text or "UAK_SETUP_BASH" in text, "install.sh passes its own Bash to setup"


def install_with(root, target, options, repair=False):
    """One install (or repair) through a setup server; returns its final status."""
    with LiveServer(str(target)) as srv:
        assert request(srv, "POST", "/api/inspect", {"target": str(target)})[0] == 200
        assert request(srv, "POST", "/api/repair" if repair else "/api/install", options)[0] == 202
        srv.worker.join(120)
        assert not srv.worker.is_alive()
        return json.loads(request(srv, "GET", "/api/status")[1])


def fresh_view(target):
    """What a NEW setup server (a restarted install.sh --wizard) reports for the folder, and its readiness answer."""
    with LiveServer(str(target)) as srv:
        state = json.loads(request(srv, "POST", "/api/inspect", {"target": str(target)})[1])
        status, body, _ = request(srv, "POST", "/api/check", {})
        return state, status, json.loads(body)


def partial_install_is_not_installed_after_restart(root, tmp):
    """UAK-010: install.sh copied .uak/ and VERSION, then failed on a file named .claude; a restarted setup server read
    the files left on disk and reported the project installed (only the first server's memory said otherwise)."""
    if not (root.parent / "install.sh").is_file():
        return installer_absent_package_is_explicit(root, tmp)
    target = repository(tmp / "partial target")
    (target / ".claude").write_text("Keep this user file", encoding="utf-8")
    state = install_with(root, target, {"mode": "sprint", "harness": ["claude"], "blackbox": False})
    assert state["phase"] == "error" and not state["installed"]
    assert (target / ".uak/VERSION").is_file(), "the failure happens after the engine is copied (the case to cover)"
    state, status, body = fresh_view(target)
    assert not state["installed"], "a restarted setup never reports a partial install as installed"
    assert state.get("can_repair"), "a partial install is offered Repair or update"
    assert status == 400 and "Repair" in body.get("error", ""), "readiness says how to recover: %r" % body
    assert (target / ".claude").read_text(encoding="utf-8") == "Keep this user file"
    (target / ".claude").rename(target / ".claude.saved")
    state = install_with(root, target, {"mode": "sprint", "harness": ["claude"], "blackbox": False}, repair=True)
    assert state["phase"] == "installed" and state["installed"]
    assert fresh_view(target)[0]["installed"], "after the repair a restarted setup sees it installed"


def failed_update_stays_incomplete(root, tmp):
    """An --update that stops halfway leaves the project visibly incomplete, not a mix reported as installed."""
    if not (root.parent / "install.sh").is_file():
        return installer_absent_package_is_explicit(root, tmp)
    target = repository(tmp / "update target")
    options = {"mode": "sprint", "harness": ["claude"], "blackbox": False}
    assert install_with(root, target, options)["installed"]
    shutil.rmtree(str(target / ".claude"))
    (target / ".claude").write_text("a file where the kit needs a folder", encoding="utf-8")
    state = install_with(root, target, options, repair=True)
    assert state["phase"] == "error" and not state["installed"]
    state, status, body = fresh_view(target)
    assert not state["installed"] and state.get("can_repair"), "a failed update is incomplete after a restart"
    assert status == 400 and "Repair" in body.get("error", ""), body


def complete_install_is_still_installed(root, tmp):
    """No regression: a complete install, and one made before this change (no completion stamp at all), are installed."""
    if (root.parent / "install.sh").is_file():
        target = repository(tmp / "complete target")
        assert install_with(root, target, {"mode": "sprint", "harness": ["claude"], "blackbox": False})["installed"]
        state, status, _ = fresh_view(target)
        assert state["installed"] and status == 202, "a complete install is installed for a new setup server"
    legacy = repository(tmp / "legacy target")
    shutil.copytree(str(root / ".uak"), str(legacy / ".uak"), ignore=shutil.ignore_patterns("tests", "__pycache__"))
    (legacy / ".uak/PROJECT.md").write_text((root / ".uak/templates/PROJECT.sprint.md").read_text(encoding="utf-8"),
                                            encoding="utf-8")
    assert fresh_view(legacy)[0]["installed"], "an install from before the completion stamp is still installed"


TESTS = [wizard_starts_before_installation, legacy_install_remains_noninteractive, invalid_requests_cannot_mutate,
         installer_arguments_are_literal, duplicate_install_is_rejected, setup_preserves_unrelated_settings, installed_is_not_ready,
         partial_install_can_recover, ambiguous_settings_are_not_reported_saved, an_older_installed_engine_is_not_ready,
         all_stack_presets_are_selectable, installer_absent_package_is_explicit, nested_json_is_rejected,
         installer_bash_is_preferred, partial_install_is_not_installed_after_restart, failed_update_stays_incomplete,
         complete_install_is_still_installed]


def main():
    global MODULE
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("uak_visual_setup", root / ".uak/bin/lib/setup.py")
    MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MODULE)
    fails = 0
    for case in TESTS:
        if args.case and case.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-wizard-test-") as folder:
            try:
                case(root, Path(folder))
                print("PASS " + case.__name__)
            except Exception as exc:
                fails += 1
                frame = traceback.extract_tb(exc.__traceback__)[-1]
                print("FAIL %s: %s: %s (line %s: %s)" % (case.__name__, type(exc).__name__, exc, frame.lineno, frame.line))
    print("SETUP_WIZARD_RESULT failed=%d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
