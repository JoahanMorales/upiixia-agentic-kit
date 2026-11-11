#!/usr/bin/env python3
"""Loopback-only visual installation and setup; Python 3.8 standard library.

The existing installer owns installation and `uak start` owns readiness. This service
never publishes a plan, approves a backlog, registers identities, or changes a remote.
"""
import argparse
import hmac
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HARNESS = ("claude", "codex", "cursor", "gemini")
STACKS = ("none", "fastapi-react", "nextjs", "django", "go", "expo", "python-data", "ai-agent", "spring-boot")
SETTINGS = {"Blackbox": ("on", "off"), "Pace": ("auto", "off")}
# Keys the browser may also add when an older PROJECT.md lacks them; their values are validated, never free text.
ADDABLE = ("Live-URL",)
LIMIT = 65536


def bash_binary():
    # install.sh --wizard passes the Bash that runs it: Git for Windows may live anywhere (scoop, another drive),
    # and a PATH lookup on Windows can find WSL's bash.exe instead.
    # Only an absolute path to a program named bash; Git Bash reports its own path without ".exe".
    launched = os.environ.get("UAK_SETUP_BASH", "")
    for candidate in ((launched, launched + ".exe") if os.name == "nt" else (launched,)):
        path = Path(candidate)
        if candidate and path.is_absolute() and path.name.lower() in ("bash", "bash.exe") and path.is_file():
            return str(path)
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("LOCALAPPDATA", "")):
            for tail in ("Git/bin/bash.exe", "Programs/Git/bin/bash.exe"):
                path = Path(base) / tail
                if path.is_file():
                    return str(path)
        raise ValueError("Install Git for Windows, including Git Bash, then restart setup.")
    binary = shutil.which("bash")
    if not binary:
        raise ValueError("Install Bash 3.2 or newer, then restart setup.")
    return binary


def safe_environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_") and k not in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX", "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")}
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    # Windows Store aliases can precede the interpreter that launched the wizard.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def run_command(command, cwd=None, timeout=120, **kwargs):
    return subprocess.run(command, cwd=cwd, timeout=timeout, env=safe_environment(),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def redact(text):
    text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", str(text))
    text = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})", "[redacted]", text)
    text = re.sub(r"(?i)((?:token|password|secret|api[_-]?key)\s*[=:]\s*)\S+", r"\1[redacted]", text)
    return text[-18000:]


def project_root(target):
    if not isinstance(target, str) or not target.strip() or len(target) > 4096 or "\x00" in target:
        raise ValueError("Enter the full path to an existing Git repository.")
    path = Path(target).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("This folder does not exist. Choose an existing project folder.")
    result = run_command(["git", "-C", str(path), "rev-parse", "--show-toplevel"], timeout=10)
    if result.returncode or Path(result.stdout.strip()).resolve() != path:
        raise ValueError("Choose the root of a Git repository. Create the repository first if needed.")
    if (path / ".uak").is_symlink():
        raise ValueError("The kit folder must be local to this project, not a symbolic link.")
    return path


def install_command(installer, target, options):
    if not isinstance(options, dict) or set(options) - {"mode", "harness", "stack", "blackbox", "solo"}:
        raise ValueError("Unknown installation option.")
    mode = options.get("mode")
    harness = options.get("harness", ["claude", "codex"])
    stack = options.get("stack", "none")
    if mode not in ("sprint", "marathon"):
        raise ValueError("Choose Hackathon or Product before installing.")
    if not isinstance(harness, list) or not harness or any(h not in HARNESS for h in harness) or len(set(harness)) != len(harness):
        raise ValueError("Choose at least one supported coding tool.")
    if stack not in STACKS or any(not isinstance(options.get(k, False), bool) for k in ("blackbox", "solo")):
        raise ValueError("Invalid stack or installation preference.")
    cmd = [bash_binary(), str(Path(installer).resolve()), "--mode", mode, "--harness", ",".join(harness), "--stack", stack]
    if options.get("blackbox", True) is False:
        cmd.append("--no-blackbox")
    if options.get("solo", False):
        cmd.append("--solo")
    return cmd + [str(target)]


def dashboard_module():
    spec = importlib.util.spec_from_file_location("uak_dashboard", Path(__file__).with_name("dash.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_setting(key, value):
    if key == "Live-URL":
        # The deploy link: only what the dashboard would render as a link (https, a host, no credentials).
        return isinstance(value, str) and dashboard_module().live_url(value) == value
    return value in SETTINGS[key]


def save_settings(target, settings):
    if not isinstance(settings, dict) or not settings or set(settings) - set(SETTINGS) - set(ADDABLE):
        raise ValueError("Only anonymous diagnostics, usage pacing and the deploy link can be changed here.")
    if any(not valid_setting(key, value) for key, value in settings.items()):
        raise ValueError("Invalid project preference.")
    path = Path(target) / ".uak/PROJECT.md"
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Project configuration must be a regular local file.")
    text = path.read_bytes().decode("utf-8")
    # Read/write only the executable config block, leaving prose and all other fields intact.
    matches = list(re.finditer(r"(?ms)^```text\r?\n(.*?)^```", text))
    if len(matches) != 1:
        raise ValueError("Expected one executable configuration block in .uak/PROJECT.md.")
    block = matches[0]
    content = block.group(1)
    for key, value in settings.items():
        found = len(re.findall(r"(?m)^[-* ]*" + re.escape(key) + r":", text))
        if found == 0 and key in ADDABLE:
            # A PROJECT.md from before this key: add it as the block's last line, in the block's line ending.
            newline = "\r\n" if "\r\n" in content else "\n"
            content = content + key + ": " + value + newline
            continue
        if found != 1:
            raise ValueError("Ambiguous %s setting. Keep a single setting in the executable configuration block." % key)
        pattern = r"(?m)^" + re.escape(key) + r": [^\r\n]*"
        if len(re.findall(pattern, content)) != 1:
            raise ValueError("Expected exactly one %s setting. Restore the project configuration first." % key)
        content = re.sub(pattern, lambda match: key + ": " + value, content)
    updated = text[:block.start(1)] + content + text[block.end(1):]
    fd, name = tempfile.mkstemp(prefix=".uak-setup-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(updated.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, path.stat().st_mode)
        if path.read_bytes().decode("utf-8") != text:
            raise ValueError("Project configuration changed while saving. Reload and try again.")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return True


def read_config(target):
    path = Path(target) / ".uak/PROJECT.md"
    if not path.is_file():
        return {}
    # Use the engine's reader, including its Markdown and first-match semantics.
    keys = ("Mode", "Blackbox", "Pace", "Live-URL")
    script = '. "$1"; file=$2; for key in %s; do uak_cfg "$file" "$key"; done' % " ".join(keys)
    result = run_command([bash_binary(), "-c", script, "uak-setup-config",
                          str(Path(__file__).with_name("config.sh")), str(path)], timeout=10)
    if result.returncode:
        raise ValueError("Could not read the project configuration. Check technical details in the terminal.")
    values = dict(zip(keys, result.stdout.splitlines()))
    # Only a link the dashboard would render is shown back; "-" or anything invalid reads as no link.
    values["Live-URL"] = dashboard_module().live_url(values.get("Live-URL")) or ""
    return values


def kit_present(target):
    return all((Path(target) / path).is_file() for path in (".uak/PROJECT.md", ".uak/bin/uak", ".uak/VERSION"))


def readiness(output, code):
    lines = redact(output).splitlines()
    checks = []
    for line in lines:
        match = re.match(r"^(OK|TODO|NOTE)\s+(.*)$", line)
        if match:
            checks.append({"state": match.group(1).lower(), "text": match.group(2)})
        elif line.startswith("         ") and checks:
            checks[-1]["text"] += "\n" + line.strip()
    ready_lines = [line[len("START READY · "):].strip() for line in lines if line.startswith("START READY · ")]
    ready = code == 0 and bool(ready_lines)
    # Only the exact claim command is ever offered to copy; anything else on the READY line (the engine's note,
    # "cd <worktree> and open your agent there…") is prose shown as text.
    claim = CLAIM_COMMAND.match(ready_lines[-1]) if ready else None
    return {"ready": ready, "checks": checks, "next_command": claim.group(0) if claim else "",
            "next_note": ready_lines[-1] if ready and not claim else ""}


# `uak start`'s READY line when a task is free: the command, then the engine's note after spaces.
CLAIM_COMMAND = re.compile(r"^bash \.uak/bin/wt new ([A-Z][A-Z0-9]*-[0-9]+)(?=\s|$)")


def completed_steps(state):
    """The guided checklist: what the last readiness check passed, as plain text (first line, no number)."""
    return [re.sub(r"^\d+\.\s*", "", c.get("text", "").split("\n")[0])
            for c in state.get("checks") or [] if c.get("state") == "ok"]


def guidance(state, dashboard=None, now=None):
    """The one next action. Readiness comes only from `uak start` (the same gate Configuration shows), so the
    dashboard never offers to start work that the gate still blocks; an active freeze overrides everything.
    `commands` (copyable) is only ever the exact claim command; the gate's fix lines are `steps`, shown as text,
    because they are prose that can carry project values (branch names, remote URLs)."""
    now = time.time() if now is None else now
    dashboard = dashboard or {}

    def step(kind, title, detail, commands=(), steps=()):
        return {"kind": kind, "title": title, "detail": detail, "commands": list(commands), "steps": list(steps)}

    if state.get("phase") in ("installing", "checking"):
        return step("busy", "Working in the background", "Keep this window and the terminal open.")
    if state.get("phase") == "error" and state.get("error"):
        return step("error", "Something needs your attention", state["error"])
    freeze = dashboard.get("freeze") or state.get("freeze") or 0
    if freeze and freeze <= now:
        return step("frozen", "Project changes are frozen",
                    "The change window has closed. Review the project with the responsible human before starting new work.")
    if not state.get("installed"):
        return step("install", "Install the kit in this project", "Choose your workflow and coding tools in Configuration.")
    if state.get("ready"):
        claim = CLAIM_COMMAND.match(state.get("next_command") or "")
        tasks = {t.get("id"): t.get("state") for t in dashboard.get("tasks") or []}
        if claim and tasks.get(claim.group(1), "AVAILABLE") != "AVAILABLE":
            return step("check", "Check what's next",
                        "The task suggested by the last check is no longer available.")
        if claim:
            return step("ready", "Start the next task",
                        "Your project passed the readiness checks. Run this in your coding tool's terminal.",
                        [claim.group(0)])
        return step("ready", "Your project is ready", state.get("next_note") or
                    "Your project passed the readiness checks.")
    for check in state.get("checks") or []:
        if check.get("state") == "todo":
            lines = check.get("text", "").split("\n")
            title = re.sub(r"^\d+\.\s*", "", lines[0])
            return step("todo", title, "This is the first thing the readiness check needs.",
                        steps=[l for l in lines[1:] if l])
    return step("check", "Check what your project needs",
                "The readiness check lists what is missing before agents can start, in order.")


class SetupServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, target, installer, run):
        self.token = secrets.token_urlsafe(32)
        self.nonce = secrets.token_urlsafe(24)
        self.installer = Path(installer).resolve()
        self.run = run or run_command
        self.lock = threading.Lock()
        self.worker = None
        self.target = ""
        self.failed_target = ""
        self.state = {"phase": "welcome", "target": str(target), "ready": False, "checks": [], "details": "", "installed": False}
        super().__init__(("127.0.0.1", 0), SetupHandler)

    def config(self):
        return read_config(self.target)

    def launch(self, operation, command):
        self.state.update(phase=operation, ready=False, checks=[], next_command="", next_note="", details="", error="")

        def work():
            try:
                result = self.run(command, cwd=self.target, timeout=120)
                output = redact(result.stdout + "\n" + result.stderr)
                with self.lock:
                    installed = kit_present(self.target)
                    if operation == "installing":
                        success = result.returncode == 0 and installed
                        self.failed_target = "" if success else self.target
                        error = "Installation did not finish. Check details, correct the issue, and retry."
                        for name in (".claude", ".codex", ".cursor", ".gemini", ".agents", ".github"):
                            path = Path(self.target) / name
                            if path.exists() and not path.is_dir():
                                error = "A file named %s is blocking a folder the kit needs. Rename or move that file yourself, then choose Repair or update kit." % name
                                break
                        self.state.update(phase="installed" if success else "error", installed=success, can_repair=True, ready=False,
                                          error="" if success else error, details=output)
                    else:
                        self.state.update(readiness(output, result.returncode))
                        self.state.update(phase="ready" if self.state["ready"] else "setup", details=output)
                        if not self.state["checks"] and not self.state["ready"]:
                            self.state["error"] = "The readiness check could not complete. Check connection and technical details, then retry."
            except Exception as exc:
                with self.lock:
                    if operation == "installing":
                        self.failed_target = self.target
                        self.state["installed"] = False
                    self.state.update(phase="error", ready=False, error="The operation stopped. Correct the issue and retry.", details=redact(exc))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()


class SetupHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # Requests and tokens never appear in the terminal log.

    def reply(self, code, payload, html=False, javascript=False):
        data = payload.encode("utf-8") if html or javascript else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8" if html else "text/javascript; charset=utf-8" if javascript else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'nonce-%s'; style-src 'unsafe-inline'; connect-src 'self'; frame-src 'self'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors %s" % (self.server.nonce, "'self'" if self.path == "/dashboard" else "'none'"))
        try:
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Closing a tab does not cancel an installation or print session data.

    def authorized(self, write=False):
        origin = "http://127.0.0.1:%d" % self.server.server_port
        if self.headers.get("Host") != origin[len("http://"):] or (write and self.headers.get("Origin") != origin):
            self.reply(403, {"error": "This request must come from the local setup page."})
            return False
        if self.path.startswith("/api/") and not hmac.compare_digest(self.headers.get("X-UAK-Token", "").encode("utf-8"), self.server.token.encode("utf-8")):
            self.reply(403, {"error": "This setup session expired. Reopen the address printed in the terminal."})
            return False
        return True

    def do_GET(self):
        if not self.authorized():
            return
        if self.path == "/":
            html = Path(__file__).with_name("setup.html").read_text(encoding="utf-8")
            self.reply(200, html.replace("__NONCE__", self.server.nonce), html=True)
        elif self.path == "/workspace.js":
            self.reply(200, Path(__file__).with_name("workspace.js").read_text(encoding="utf-8"), javascript=True)
        elif self.path == "/dashboard":
            html = Path(__file__).with_name("dash.html").read_text(encoding="utf-8")
            bridge = ('<script nonce="%s">window.UAK_EMBEDDED=true;'
                      'window.addEventListener("message",function(e){'
                      'if(e.source!==window.parent||!e.data||e.data.type!=="uak:dashboard")return;'
                      'window.UAK_DATA=e.data.snapshot;'
                      'window.UAK_DASH_LANGUAGE=e.data.language;'
                      'window.UAK_DASH_THEME=e.data.theme;'
                      'document.dispatchEvent(new Event("uak:state"));});</script>') % self.server.nonce
            html = html.replace('<script src="data.js"></script>', bridge)
            html = html.replace('<script src="workspace.js">', '<script nonce="%s" src="workspace.js">' % self.server.nonce)
            html = html.replace('<script>', '<script nonce="%s">' % self.server.nonce)
            self.reply(200, html, html=True)
        elif self.path == "/api/dashboard":
            try:
                with self.server.lock:
                    root = self.server.target
                    busy = self.server.worker and self.server.worker.is_alive()
                if not root:
                    raise ValueError("Choose a project first.")
                if busy:
                    self.reply(409, {"error": "An operation is running. Wait for it to finish."})
                    return
                spec = importlib.util.spec_from_file_location("uak_dashboard", Path(__file__).with_name("dash.py"))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                data = module.workspace_data(root)
                data["mode"] = read_config(root).get("Mode", "")
                with self.server.lock:
                    self.server.state["freeze"] = data.get("freeze") or 0
                    data["guidance"] = guidance(self.server.state, data)
                self.reply(200, data)
            except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
                self.reply(400, {"error": redact(exc)})
        elif self.path == "/api/status":
            try:
                with self.server.lock:
                    self.reply(200, dict(self.server.state, settings=self.server.config() if self.server.target else {},
                                         guidance=guidance(self.server.state),
                                         completed=completed_steps(self.server.state)))
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                self.reply(400, {"error": redact(exc)})
        else:
            self.reply(404, {"error": "Page not found."})

    def do_POST(self):
        if not self.authorized(write=True):
            return
        if self.headers.get("Content-Type") != "application/json":
            self.reply(415, {"error": "Expected JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > LIMIT:
                self.reply(413, {"error": "Request is too large or empty."})
                return
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Unsupported transfer encoding.")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected a settings object.")
            with self.server.lock:
                if self.server.worker and self.server.worker.is_alive():
                    self.reply(409, {"error": "An operation is running. Wait for it to finish."})
                    return
                self.dispatch(data)
        except RecursionError:
            # Deeply nested JSON: a bad request, never a dropped connection with a traceback in the terminal.
            self.reply(400, {"error": "The request is nested too deeply."})
        except (ValueError, TypeError, UnicodeError, OSError, subprocess.SubprocessError) as exc:
            self.reply(400, {"error": redact(exc)})

    def require_installer(self):
        if not self.server.installer.is_file():
            raise ValueError("This copy of setup has no kit installer next to it. Run it from the kit's folder: "
                             "bash path/to/upiixia-agentic-kit/install.sh --wizard")

    def dispatch(self, data):
        s = self.server
        if self.path == "/api/inspect":
            if set(data) != {"target"}:
                raise ValueError("Provide only the project folder.")
            root = project_root(data["target"])
            previous = dict(s.state) if s.failed_target == str(root) else {}
            s.target = str(root)
            installed = kit_present(root) and s.failed_target != str(root)
            repair = (root / ".uak").exists()
            s.state.update(target=str(root), installed=installed, can_repair=repair, phase="error" if previous else "setup" if repair else "options", ready=False, checks=[], next_command="", next_note="", freeze=0, details=previous.get("details", ""), error=previous.get("error", ""))
            self.reply(200, dict(s.state, settings=s.config()))
        elif self.path in ("/api/install", "/api/repair"):
            self.require_installer()
            cmd = install_command(s.installer, s.target, data)
            if not s.target:
                raise ValueError("Check the project folder before installing.")
            project_root(s.target)
            if self.path == "/api/repair":
                existing_mode = s.config().get("Mode")
                if existing_mode and existing_mode != data["mode"]:
                    raise ValueError("Repair must preserve the existing %s workflow. Change the mode in PROJECT.md separately." % existing_mode)
                cmd.insert(-1, "--update")
            elif (Path(s.target) / ".uak/bin").exists() or (Path(s.target) / ".uak/PROJECT.md").exists():
                raise ValueError("Kit files already exist. Use Repair or update to continue safely.")
            s.launch("installing", cmd)
            self.reply(202, {"phase": "installing"})
        elif self.path == "/api/settings":
            if not s.target:
                raise ValueError("Choose a project first.")
            save_settings(project_root(s.target), data)
            s.state.update(phase="setup", ready=False, checks=[], next_command="", next_note="", details="", error="")
            self.reply(200, {"saved": True, "settings": s.config()})
        elif self.path == "/api/check":
            if data:
                raise ValueError("The readiness check accepts no options.")
            if not s.target or not kit_present(s.target) or s.failed_target == s.target:
                raise ValueError("Install the kit before checking readiness.")
            project_root(s.target)
            # The engine that checks readiness is the one shipped with this setup (kit/.uak in the kit's checkout,
            # .uak in an installed project), so the check needs no installer and never certifies another version.
            package = Path(__file__).resolve().parents[2]
            installed_version = (Path(s.target) / ".uak/VERSION").read_text(encoding="utf-8").strip()
            source_version = (package / "VERSION").read_text(encoding="utf-8").strip()
            if installed_version != source_version:
                raise ValueError("The installed kit version differs from this setup. Use Repair or update first so the correct engine checks readiness.")
            cmd = [bash_binary(), str(package / "bin/uak"), "start"]
            s.launch("checking", cmd)
            self.reply(202, {"phase": "checking"})
        else:
            self.reply(404, {"error": "Action not found."})


def make_server(target="", installer=None, run=None):
    installer = installer or Path(__file__).resolve().parents[4] / "install.sh"
    return SetupServer(target, installer, run)


def main():
    parser = argparse.ArgumentParser(description="Configure the kit in a local browser. Keep this terminal open.")
    parser.add_argument("target", nargs="?", default=str(Path.cwd()))
    parser.add_argument("--no-open", action="store_true", help="print the local address without opening a browser")
    args = parser.parse_args()
    server = make_server(args.target)
    url = "http://127.0.0.1:%d/#%s" % (server.server_port, server.token)
    print("UAK SETUP " + url, flush=True)
    print("Keep this terminal open. Configure the kit in your browser; press Ctrl+C here to stop.", flush=True)
    if not args.no_open:
        try:
            webbrowser.open(url)
        except (OSError, webbrowser.Error):
            print("Could not open a browser. Open the local address above manually.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
