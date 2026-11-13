#!/usr/bin/env python3
"""Loopback-only visual installation and setup; Python 3.8 standard library.

The existing installer owns installation and `uak start` owns readiness. This service never registers identities
or changes a remote. Its one act of human authority is approving the plan (planning.py): the person types the
project name, and only the reviewed plan files are committed and pushed (WHY.md, UI-004).
"""
import argparse
import hmac
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
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


def windows_job(proc):
    """A Windows Job Object holding the process, or None (not Windows, or any call failed: the caller falls back to
    taskkill). `taskkill /T` cannot walk a tree whose parent already exited, a job can (UI-010 review). Descendants
    created after the assignment join the job by themselves; one spawned in the tiny window between Popen and the
    assignment is not in it."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Counters), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            return None
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) or \
                not kernel.AssignProcessToJobObject(job, int(proc._handle)):
            kernel.CloseHandle(job)
            return None
        return job
    except Exception:
        return None


def windows_job_end(job, kill):
    """Terminate (when `kill`) and close the job; closing it also kills anything left (KILL_ON_JOB_CLOSE)."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    if kill:
        kernel.TerminateJobObject(job, 1)
    kernel.CloseHandle(job)


def run_command(command, cwd=None, timeout=120, group=False, env=None, on_line=None, **kwargs):
    """`env` adds a few named variables to the sanitized environment (UI-006: UAK_HUMAN for one human act).
    `on_line` (group runs, UI-010) receives each line of standard output while the process runs."""
    environment = safe_environment()
    environment.update(env or {})
    if not group:
        return subprocess.run(command, cwd=cwd, timeout=timeout, env=environment,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
    # A coding tool starts its own children (shells, tests): on timeout the whole process group stops.
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **extra)
    job = windows_job(proc)
    holder = [job]  # the job is closed once, by whichever of stop_group or the final cleanup gets there first
    readers, lines, errors = [], [], []
    if on_line:  # both pipes are drained by threads, so a chatty stderr never blocks the tool
        def read_out():
            for line in proc.stdout:
                lines.append(line)
                try:
                    on_line(line)
                except Exception:
                    pass
        readers = [threading.Thread(target=read_out, daemon=True),
                   threading.Thread(target=lambda: errors.extend(proc.stderr), daemon=True)]
        for thread in readers:
            thread.start()

    def stop_group():
        if os.name == "nt":
            if holder[0]:
                windows_job_end(holder[0], True)
                holder[0] = None
            else:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass

    def finish(wait=None):
        if not readers:
            return proc.communicate(timeout=wait)
        proc.wait(timeout=wait)
        for thread in readers:
            thread.join(10)
        if any(thread.is_alive() for thread in readers):
            # A descendant still holds the pipe after the tool exited: stop the group, never leave it running (UI-010 review).
            stop_group()
            for thread in readers:
                thread.join(10)
        return "".join(lines), "".join(errors)

    try:
        try:
            out, err = finish(timeout)
        except subprocess.TimeoutExpired:
            stop_group()
            out, err = finish()
            return subprocess.CompletedProcess(command, 124, out, err + "\nThe run took too long and was stopped.")
        return subprocess.CompletedProcess(command, proc.returncode, out, err)
    finally:
        if holder[0]:
            windows_job_end(holder[0], False)


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


def install_unfinished(target):
    """install.sh writes .uak/INSTALLING first and removes it last (UAK-010): present means it stopped halfway."""
    return (Path(target) / ".uak/INSTALLING").exists()


GH_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\Z")


def signing_identity(run, root):
    """Who will sign this project's commits and pull requests (UI-007): the project's Git name and email, and the GitHub
    login of `gh`. Only those parsed values leave this function; gh's output (it prints token details) never does."""
    def value(*args):
        try:
            result = run(["git", "-C", str(root), "config"] + list(args), cwd=str(root), timeout=10)
        except (OSError, subprocess.SubprocessError):
            return ""
        return (result.stdout or "").strip()[:200] if result.returncode == 0 else ""

    # `gh config get user` reads gh's own hosts file: no network (auth status validates the token online and made
    # inspecting a project wait), and nothing but the login. Anything that is not one login is ignored.
    login = ""
    try:
        shown = run(["gh", "config", "get", "user", "-h", "github.com"], cwd=str(root), timeout=10)
        text = (shown.stdout or "").strip()
        login = text if shown.returncode == 0 and GH_LOGIN.fullmatch(text) else ""
    except (OSError, subprocess.SubprocessError):
        login = ""
    return {"git_name": value("user.name"), "git_email": value("user.email"), "gh_login": login}


def kit_present(target):
    return not install_unfinished(target) and \
        all((Path(target) / path).is_file() for path in (".uak/PROJECT.md", ".uak/bin/uak", ".uak/VERSION"))


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


BUSY = ("installing", "checking", "planning", "approving", "publishing", "registering")
# Whole-string matches over ASCII only: `$` lets a trailing newline through and \d takes non-ASCII digits (review of
# 57ef048: "ana\n" could add a line to the Published-By commit message).
HUMAN_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SCHEDULE_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}\Z")
TIME_ZONE = re.compile(r"(UTC|[A-Za-z]+(/[A-Za-z0-9_+-]+){1,2})\Z")
# `uak start`'s READY line when a task is free: the command, then the engine's note after spaces.
# The first prompts of the two agents the team step starts (UI-006). Constants with no shell metacharacters, and they
# start with a word: Git Bash rewrites an argument that starts with / into a Windows path.
IMPL_PROMPT = "Run /uak-start for %s. Work only in this worktree."
REVIEW_PROMPT = ("You are the reviewer %s. Run bash .uak/bin/uak next; when it names a task to review, run $uak-review "
                 "with that task ID. Never write code for a task.")
# A task wt accepts (wt: [A-Z][A-Z0-9]*-[0-9]{3,}); the READY line's claim is offered to agents only when it is one.
TEAM_TASK = re.compile(r"[A-Z][A-Z0-9]*-[0-9]{3,}\Z")
CLAIM_COMMAND = re.compile(r"^bash \.uak/bin/wt new ([A-Z][A-Z0-9]*-[0-9]+)(?=\s|$)")
# UI-009 (absorbs UI-014): any available tool takes either role; a role is only an identity (UAK_AGENT).
TOOL_LABEL = {"claude": "Claude Code", "codex": "Codex"}
IMPL_PROMPT_CODEX = "Run $uak-start for %s. Work only in this worktree."
REVIEW_PROMPT_CLAUDE = REVIEW_PROMPT.replace("$uak-review", "/uak-review")
# Codex: the ONE place its sandbox flags live. workspace-write, because Codex ignores --add-dir in a read-only sandbox;
# --add-dir GITDIR, because the sandbox keeps .git read-only and the engine writes refs (rounds 1 and 3: "Operation not
# permitted"); network_access, because workspace-write has no network and uak next fetches claims ("Could not resolve
# host: github.com"). Verified on macOS with codex-cli 0.167.1 (`codex exec`, WHY.md UI-009); not yet in Windows Git Bash.
# No approval or sandbox bypass is ever added.
CODEX_FLAGS = "--sandbox workspace-write --add-dir %s -c sandbox_workspace_write.network_access=true"
# The engine's own TODO when every task is taken (bin/start): the team is working, the team step stays (UI-009).
WAITING_TODO = "a claimable task: uak next offers none"
# Network Git from a request: its own timeout, the whole process tree stops (UI-011). Tool probes: 20 s each.
NET_TIMEOUT = 30
PROBE_TIMEOUT = 20
REMOTE_TTL = 15
TOOLS_TTL = 60
SETUP_BASE, SETUP_CLAIMS = "refs/uak/setup-base", "refs/uak/setup-claims"
REF_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}\Z")
CLAIM_FILE = re.compile(r"[A-Za-z0-9_.-]+\.md\Z")
SAFE_PATH = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._/-]{0,199}\Z")
LIVE_STATES = ("CLAIMED", "BLOCKED", "REVIEW")


class Busy(Exception):
    """A worker runs: the request answers 409 (or the last view) instead of touching the network or the engine."""


class WayOut(ValueError):
    """A refusal that carries one safe way forward for the page (unrelated remote history, UI-011)."""

    def __init__(self, message, way_out):
        super().__init__(message)
        self.way_out = way_out


def team_phase(state):
    """"ready" after a READY check; "waiting" when the check's only TODO is that no task is free (the team is working);
    "" otherwise. Derived from the last check, never stored."""
    if state.get("ready"):
        return "ready"
    todos = [c for c in state.get("checks") or [] if c.get("state") == "todo"]
    if state.get("installed") and len(todos) == 1 and \
            re.sub(r"^\d+\.\s*", "", todos[0].get("text", "").split("\n")[0]).strip() == WAITING_TODO:
        return "waiting"
    return ""


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

    if state.get("phase") in BUSY:
        return step("busy", "Working in the background", "Keep this window and the terminal open.")
    if state.get("phase") == "error" and state.get("error"):
        return step("error", "Something needs your attention", state["error"])
    freeze = dashboard.get("freeze") or state.get("freeze") or 0
    if freeze and freeze <= now:
        return step("frozen", "Project changes are frozen",
                    "The change window has closed. Review the project with the responsible human before starting new work.")
    if not state.get("installed"):
        return step("install", "Install the kit in this project", "Choose your workflow and coding tools in Configuration.")
    if team_phase(state) == "waiting":
        todo = next(c for c in state.get("checks") or [] if c.get("state") == "todo")
        return step("waiting", "Your team is working", "No task is free to start right now.",
                    steps=[l for l in todo.get("text", "").split("\n")[1:] if l])
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
            g = step("todo", title, "This is the first thing the readiness check needs.",
                     steps=[l for l in lines[1:] if l])
            # The page does what it can itself; anything else becomes a terminal box with the exact cd (UI-005).
            # Why (simulation, Nov 2026): the next action lived only in Technical details and looked like loading.
            # A preflight groups several doctor failures: each goes where it is fixed, the page or a terminal.
            page_lines = {"schedule": r"Freeze-Epoch", "publish": r"push rejected in dry-run"}
            rest = []
            for line in g["steps"]:
                kind = next((k for k, pattern in page_lines.items() if re.search(pattern, line)), None)
                if kind and "action" not in g:
                    g["action"] = kind
                elif not kind:
                    rest.append(line)
            if "action" not in g:
                if re.search(r"push the kit to |push your changes to", title):
                    g["action"], rest = "publish", []
                elif re.search(r"^(a plan|approve the plan|fix the plan)", title):
                    g["action"], rest = "plan", []
            if rest:
                g["terminal"] = {"cd": "cd '%s'" % str(state.get("target", "")).replace("'", "'\\''"), "steps": rest}
            return g
    return step("check", "Check what your project needs",
                "The readiness check lists what is missing before agents can start, in order.")


def planning_module():
    spec = importlib.util.spec_from_file_location("uak_planning", Path(__file__).with_name("planning.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SetupServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, target, installer, run):
        self.planning = planning_module()
        self.plan = None
        self.token = secrets.token_urlsafe(32)
        self.nonce = secrets.token_urlsafe(24)
        self.installer = Path(installer).resolve()
        self.run = run or run_command
        # Reading who signs (git config, gh's hosts file) is local and read-only: it never goes through the operation
        # runner, whose callers count and pace their own commands.
        self.identity_run = run_command
        self.lock = threading.Lock()
        # The slow lane (UI-011): every POST and every GET that may reach the network, the engine or a coding tool holds
        # it; /api/status never does. Order: slow, then lock; never the reverse.
        self.slow = threading.Lock()
        self.remote_cache, self.tools_cache, self.team_cache, self.plan_known = {}, {}, {}, {}
        self.worker = None
        self.plan_started, self.plan_last = 0, ""
        self.target = ""
        self.failed_target = ""
        self.state = {"phase": "welcome", "target": str(target), "ready": False, "checks": [], "details": "",
                      "installed": False, "human": ""}
        super().__init__(("127.0.0.1", 0), SetupHandler)

    def config(self):
        return read_config(self.target)

    def engine(self):
        """The engine shipped with this setup (kit/.uak or an installed .uak), refused when the project's differs."""
        if self.target and install_unfinished(self.target):
            raise ValueError("The last install or update did not finish. Choose Repair or update kit to complete it.")
        if not self.target or not kit_present(self.target) or self.failed_target == self.target:
            raise ValueError("Install the kit before planning or checking readiness.")
        project_root(self.target)
        package = Path(__file__).resolve().parents[2]
        installed_version = (Path(self.target) / ".uak/VERSION").read_text(encoding="utf-8").strip()
        source_version = (package / "VERSION").read_text(encoding="utf-8").strip()
        if installed_version != source_version:
            raise ValueError("The installed kit version differs from this setup. Use Repair or update first so the correct engine checks readiness.")
        return package / "bin/uak"

    def forget(self, root=None):
        """Drop what setup remembers about a project's remote, tools and team view (caller holds the lock)."""
        root = str(root or self.target)
        for cache in (self.remote_cache, self.team_cache):
            for key in [k for k in cache if k[0] == root]:
                del cache[key]

    def start_worker(self, work):
        """Start the one background operation. It waits for the slow lane to drain first, so no request-side network
        section overlaps the engine; the thread is assigned and started under one lock (amendment 3)."""
        def drained():
            with self.slow:
                pass
            work()

        with self.lock:
            self.worker = threading.Thread(target=drained, daemon=True)
            self.worker.start()

    def apply_readiness(self, result):
        self.forget()
        output = redact(result.stdout + "\n" + result.stderr)
        self.state.update(readiness(output, result.returncode))
        self.state.update(phase="ready" if self.state["ready"] else "setup", details=output)
        if not self.state["checks"] and not self.state["ready"]:
            self.state["error"] = "The readiness check could not complete. Check connection and technical details, then retry."

    def plan_run(self, harness, command, note):
        """The planning run, then the server's own check of what changed and its own lint."""
        planning, root, uak = self.planning, Path(self.target), self.engine()
        with self.lock:
            self.plan = None
            self.state.update(phase="planning", error="", details="")
            self.plan_started, self.plan_last = time.time(), ""

        def seen(line):  # the last readable line of the tool's output, for the page (UI-010)
            shown = planning.progress_line(line)
            if shown:
                with self.lock:
                    self.plan_last = shown

        def work():
            try:
                note_path = planning.regular_file(root, planning.NOTE_FILE)
                if note:
                    planning.write_atomic(note_path, ("# Changes the human asked for\n\n" + note + "\n").encode("utf-8"))
                before = planning.snapshot(self.run, root)
                result = self.run(command, cwd=str(root), timeout=planning.PLAN_TIMEOUT, group=True, on_line=seen)
                after = planning.snapshot(self.run, root)
                if note_path.is_file() and not note_path.is_symlink():
                    note_path.unlink()
                found = planning.violations(before, after)
                tasks = planning.regular_file(root, ".uak/TASKS.md")
                missing = not tasks.is_file()
                text = tasks.read_text(encoding="utf-8", errors="replace") if tasks.is_file() else ""
                # No plan file: nothing to check, so no lint verdict (a green "passes" there was shown in round r3).
                checked = {"ok": False, "lines": []} if missing else planning.lint(self.run, root, uak, bash_binary())
                plan = {"harness": harness, "violations": found, "lint": checked, "cards": planning.cards(text),
                        "digest": planning.digest(root), "head": after["head"], "exit": result.returncode,
                        "failed": missing}
                output = (result.stdout or "") + "\n" + (result.stderr or "")
                # An untrusted folder (UI-008): the tool ran, wrote no plan, and said why; name that cause.
                untrusted = not tasks.is_file() and planning.UNTRUSTED in output
                with self.lock:
                    self.plan = plan
                    failed = result.returncode != 0 or missing
                    # The trust line names the specific cause of a missing plan; any other missing plan says so plainly.
                    self.state.update(phase="error" if failed else "planned", details=redact(output),
                                      error=planning.UNTRUSTED_ERROR if untrusted else
                                      planning.MISSING_PLAN_ERROR if missing and result.returncode == 0 else
                                      "The coding tool stopped with an error. Check Technical details, then try again." if failed else "")
                    self.plan_started = 0
            except Exception as exc:
                with self.lock:
                    self.plan_started = 0
                    self.state.update(phase="error", error="Planning stopped. Correct the issue and retry.", details=redact(exc))

        self.start_worker(work)

    def approve_run(self, root, approved, approver, base_head, remote, base):
        """Commit exactly the reviewed plan files with Backlog-Approved: yes, check the commit, push, re-check."""
        planning, uak = self.planning, self.engine()
        with self.lock:
            self.state.update(phase="approving", error="", details="")

        def git(*args, timeout=60):
            return planning.git_out(self.run, root, *args, timeout=timeout)

        def work():
            pushed = False
            try:
                with self.lock:
                    if planning.digest(root) != approved:
                        raise ValueError("The plan files changed while approving. Nothing was committed; review the plan again.")
                    planning.approve_config(root)
                    blobs = {name: git("hash-object", "--path=" + name, "--", name).strip() for name in planning.PLAN_FILES}
                git("add", "--", *planning.PLAN_FILES)
                git("commit", "-q", "-m", "plan: backlog v1", "-m",
                    "Approved-By: %s (local Git identity, unverified) in local setup, with a typed confirmation." % approver,
                    "--", *planning.PLAN_FILES)
                commit = git("rev-parse", "HEAD").strip()
                changed = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).split())
                if git("rev-parse", commit + "^").strip() != base_head or not changed <= set(planning.PLAN_FILES) or \
                        any(git("rev-parse", "%s:%s" % (commit, name)).strip() != blob for name, blob in blobs.items()):
                    raise ValueError("The commit does not match the plan you approved (a Git hook may have changed it). "
                                     "Nothing was pushed. Undo it with: git reset --soft HEAD^")
                # The verified commit by its SHA, never HEAD: a commit made meanwhile is not published (review of dce95aa).
                target_ref = "%s:refs/heads/%s" % (commit, base)
                result = self.run(list(planning.GIT) + ["-C", str(root), "push", remote, target_ref], cwd=str(root), timeout=120)
                if result.returncode:
                    raise ValueError("Your approval is committed here (%s) but %s refused the push: %s Fix the cause, then run: "
                                     "git push %s %s" % (commit[:7], remote, (result.stderr or result.stdout).strip()[-300:], remote, target_ref))
                pushed = True
                check = self.run([bash_binary(), str(uak), "start"], cwd=str(root), timeout=120)
                with self.lock:
                    self.plan = None
                    self.apply_readiness(check)
            except Exception as exc:
                with self.lock:
                    self.state.update(phase="error", ready=False, details=redact(exc),
                                      error=redact(exc) if isinstance(exc, ValueError) else
                                      ("The plan was published, but the readiness check stopped. Check again." if pushed else
                                       "The approval stopped. Correct the issue and retry."))

        self.start_worker(work)

    def publish_run(self, root, files, approved, human, base_head, remote, base):
        """Commit exactly the previewed kit files (never the plan before its approval), check the commit, push its SHA."""
        planning, uak = self.planning, self.engine()
        with self.lock:
            self.state.update(phase="publishing", error="", details="")

        def git(*args, timeout=60):
            return planning.git_out(self.run, root, *args, timeout=timeout)

        def reason(result):
            """What Git said, on one line; a hook that exits without a word reads as "(no message)"."""
            text = " ".join(redact((result.stderr or result.stdout or "").strip()).split())[-300:].rstrip(". ")
            return text or "(no message)"

        def restore():
            """Refs and index as they were before publishing (contract #46; review of 57ef048: a rejected commit left
            505 files staged on an empty repository)."""
            head = planning.git(self.run, root, "rev-parse", "-q", "--verify", "HEAD").stdout.strip()
            if base_head:
                planning.git(self.run, root, "reset", "-q", "--mixed", base_head)
            else:
                if head:
                    planning.git(self.run, root, "update-ref", "-d", "HEAD")
                planning.git(self.run, root, "read-tree", "--empty")

        def work():
            pushed = False
            try:
                with self.lock:
                    if planning.publish_digest(root, files) != approved:
                        raise ValueError("The kit files changed after the preview. Nothing was committed; open the preview again.")
                    git("add", "-A", "--", *files)
                    # The tree the person approved: mode and blob of each staged path; a deletion is staged as absent.
                    expected = {}
                    for entry in git("ls-files", "-s", "-z", "--", *files).split("\0"):
                        if entry:
                            meta, name = entry.split("\t", 1)
                            mode, blob = meta.split()[:2]
                            expected[name] = (mode, blob)
                committed = planning.git(self.run, root, "commit", "-q", "-m", "chore: uak setup", "-m",
                                         "Published-By: %s (from the setup page; committed as the local Git identity, "
                                         "unverified)" % human, "--", *files, timeout=120)
                if committed.returncode:
                    restore()
                    raise ValueError("Git did not create the commit (a pre-commit hook or Git refused it): %s. Nothing was "
                                     "published and nothing stays staged. Fix the cause, then publish again."
                                     % reason(committed))
                commit = git("rev-parse", "HEAD").strip()
                parents = git("rev-list", "--parents", "-n", "1", commit).split()[1:]
                changed = set(n for n in git("diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z", commit).split("\0") if n)
                tree = {}
                for entry in git("ls-tree", "-r", "-z", commit, "--", *files).split("\0"):
                    if entry:
                        meta, name = entry.split("\t", 1)
                        mode, kind, blob = meta.split()[:3]
                        tree[name] = (mode, blob)
                # Every previewed path as approved (blob, type and mode), every deletion absent, nothing else changed.
                if parents != ([base_head] if base_head else []) or changed != set(files) or tree != expected:
                    restore()  # refs and index as they were before publishing (review of 0386bec, contract #46)
                    raise ValueError("The commit did not match the files you reviewed (a Git hook changed it), so it was "
                                     "undone and nothing was published. Check your pre-commit hooks, then publish again.")
                ref = "%s:refs/heads/%s" % (commit, base)
                result = self.run(list(planning.GIT) + ["-C", str(root), "push", remote, ref], cwd=str(root), timeout=120)
                if result.returncode:
                    # Review of f8d5d84 (P2): a refused push is a failure before publishing, so the commit is undone
                    # (contract #46) and the page must not offer a push of a commit that no ref holds any more.
                    restore()
                    raise ValueError("%s refused the push: %s. Nothing was published, and nothing stays committed or "
                                     "staged here. Fix the cause (for example a pre-push hook or a protected branch), "
                                     "then publish again." % (remote, reason(result)))
                pushed = True
                check = self.run([bash_binary(), str(uak), "start"], cwd=str(root), timeout=120)
                with self.lock:
                    self.apply_readiness(check)
            except Exception as exc:
                if not pushed:
                    try:
                        restore()
                    except Exception:  # noqa: BLE001 - the original failure is what the person needs to see
                        pass
                with self.lock:
                    self.state.update(phase="error", ready=False, details=redact(exc),
                                      error=redact(exc) if isinstance(exc, ValueError) else
                                      ("The kit was published, but the readiness check stopped. Check again." if pushed else
                                       "Publishing stopped. Correct the issue and retry."))

        self.start_worker(work)

    def register_run(self, root, name, who, uak):
        """Run the engine's register-reviewer as NAME (UAK_HUMAN), then read the result back from claims. The result
        lives in the remote cache of this project (UI-009), never in a server-wide flag."""
        with self.lock:
            back = "ready" if self.state.get("ready") else "setup"
            self.state.update(phase="registering", error="", details="")

        def work():
            try:
                result = self.run([bash_binary(), str(uak), "register-reviewer", who], cwd=str(root), timeout=180,
                                  group=True, env=registration_env(name))
                output = redact((result.stdout or "") + "\n" + (result.stderr or "")).strip()
                found = reviewer_record(remote_state(self, root, fresh=True), who, name)
                with self.lock:
                    if found["registered"]:
                        self.state.update(phase=back, details=output)
                    else:
                        last = (output.splitlines() or ["(no message)"])[-1][-300:]
                        self.state.update(phase="error", details=output,
                                          error="%s is not registered: %s. Check the connection, then register again."
                                          % (who, last))
            except Exception as exc:  # noqa: BLE001 - the page needs one plain message
                with self.lock:
                    self.state.update(phase="error", details=redact(exc),
                                      error="%s is not registered: %s" % (who, redact(exc) if isinstance(exc, ValueError)
                                                                           else "the registration stopped. Try again."))

        self.start_worker(work)

    def launch(self, operation, command):
        with self.lock:
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
                        self.apply_readiness(result)
            except Exception as exc:
                with self.lock:
                    if operation == "installing":
                        self.failed_target = self.target
                        self.state["installed"] = False
                    self.state.update(phase="error", ready=False, error="The operation stopped. Correct the issue and retry.", details=redact(exc))

        self.start_worker(work)


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
        elif self.path in ("/api/publish-kit", "/api/team", "/api/plan"):
            try:
                if self.path == "/api/publish-kit":
                    def preview():
                        _, files, digest, _, _, _ = publish_checks(self.server)
                        return {"files": files, "digest": digest}
                    self.reply(200, self.slow_lane(preview, self.busy))
                elif self.path == "/api/team":
                    self.reply(200, self.slow_lane(self.fresh_team, self.cached_team))
                else:
                    self.reply(200, self.slow_lane(lambda: self.plan_view(True), lambda: self.plan_view(False)))
            except Busy:
                self.reply(409, {"error": "An operation is running. Wait for it to finish."})
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                self.reply(400, refusal(exc))
        elif self.path == "/api/status":
            # Never waits on the slow lane (UI-011): a copy of the state under the lock, everything else outside it.
            try:
                s = self.server
                with s.lock:
                    state = dict(s.state)
                    target = s.target
                    running = state.get("phase") == "planning" and s.plan_started
                    progress = {"elapsed": max(0, int(time.time() - s.plan_started)), "last": s.plan_last} if running else {}
                self.reply(200, dict(state, plan_progress=progress, settings=read_config(target) if target else {},
                                     guidance=guidance(state), completed=completed_steps(state), team=team_phase(state),
                                     reviewer=reviewer_status(s, target, state.get("human") or "")))
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                self.reply(400, {"error": redact(exc)})
        else:
            self.reply(404, {"error": "Page not found."})

    def slow_lane(self, compute, when_busy):
        """Run `compute` in the slow lane, or `when_busy` when a worker runs, checked again after waiting (amendment 3)."""
        s = self.server
        with s.lock:
            busy = s.worker and s.worker.is_alive()
        if busy:
            return when_busy()
        with s.slow:
            with s.lock:
                busy = s.worker and s.worker.is_alive()
            return when_busy() if busy else compute()

    def busy(self):
        raise Busy()

    def team_key(self):
        with self.server.lock:
            return (self.server.target, self.server.state.get("human") or "")

    def fresh_team(self):
        key = self.team_key()
        view = team_view(self.server)
        with self.server.lock:
            self.server.team_cache[key] = view
        return view

    def cached_team(self):
        """While the engine runs: the last view of this project and name, marked stale; never a fetch."""
        key = self.team_key()
        with self.server.lock:
            view = self.server.team_cache.get(key)
        if not view:
            raise Busy()
        return dict(view, stale=True)

    def plan_view(self, probe=True):
        """The planning page: what can plan here, the idea, and the last proposed plan with its check and lint. Without
        `probe` (a worker runs) the last known tools and kit state are shown: no probe, no fetch."""
        s, planning = self.server, self.server.planning
        with s.lock:
            target, plan = s.target, dict(s.plan or {})
        if not target:
            raise ValueError("Choose a project first.")
        root = project_root(target)
        remote_note = ""
        if probe:
            offers = planners(s, root)
            known = remote_state(s, root) if kit_present(root) else {}
            kit = bool(known.get("kit"))
            if known.get("state") == "offline":
                # Offline is not "publish the kit" (review of 993e112): the same words as POST /api/plan.
                remote_note = "Could not reach %s: %s" % (remote_and_base()[0], known["detail"])
            with s.lock:
                s.plan_known[str(root)] = (offers, kit, remote_note)
        else:
            with s.lock:
                offers, kit, remote_note = s.plan_known.get(str(root), ([], False, ""))

        def text(name):
            path = planning.regular_file(root, name)
            return path.read_text(encoding="utf-8", errors="replace")[:200000] if path.is_file() else ""

        return {"project": root.name, "mode": read_config(root).get("Mode", ""), "planners": offers,
                "idea": text("IDEA.md"), "violations": plan.get("violations", []),
                "lint": plan.get("lint", {"ok": False, "lines": []}), "cards": plan.get("cards", []),
                "digest": plan.get("digest", ""), "failed": bool(plan.get("failed")),
                "tasks": text(".uak/TASKS.md") if plan else "",
                "owners": text(".uak/OWNERS.md") if plan else "", "planned": bool(plan) and not plan.get("failed"),
                "kit_on_main": kit, "remote_note": remote_note,
                # Only Claude Code has the one-time folder trust (UI-008); a Codex-only project shows no notice.
                "trust_command": planning.trust_command(root) if (root / ".claude").is_dir() else ""}

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
            # Who signs is read before taking the lock (review of 949eca1: it blocked status polling) and synchronously
            # (a background read kept a process inside the project, and Windows could not delete it: WinError 32).
            self.identity = self.read_identity(data)
            with self.server.lock:
                busy = self.server.worker and self.server.worker.is_alive()
            if busy:
                self.reply(409, {"error": "An operation is running. Wait for it to finish."})
                return
            # POSTs stay one at a time (the slow lane), but no longer under the state lock: network Git, the engine and
            # tool probes never block /api/status (UI-011). The worker check is repeated after waiting.
            with self.server.slow:
                with self.server.lock:
                    busy = self.server.worker and self.server.worker.is_alive()
                if busy:
                    self.reply(409, {"error": "An operation is running. Wait for it to finish."})
                    return
                self.dispatch(data)
        except RecursionError:
            # Deeply nested JSON: a bad request, never a dropped connection with a traceback in the terminal.
            self.reply(400, {"error": "The request is nested too deeply."})
        except (ValueError, TypeError, UnicodeError, OSError, subprocess.SubprocessError) as exc:
            # The planning module's Conflict: valid, but it would replace something the person has not confirmed.
            self.reply(409 if type(exc).__name__ == "Conflict" else 400, refusal(exc))

    def read_identity(self, data):
        """signing_identity() for the project an inspect names, or the current one on a readiness check; None otherwise."""
        try:
            if self.path == "/api/inspect" and set(data) == {"target"} and isinstance(data["target"], str):
                root = project_root(data["target"])
            elif self.path == "/api/check" and not data:
                with self.server.lock:
                    target = self.server.target
                if not target:
                    return None
                root = project_root(target)
            else:
                return None
        except ValueError:
            return None
        return signing_identity(self.server.identity_run, root)

    def schedule(self, data):
        """The event schedule: what `uak clock START DEADLINE ZONE --write` does, from a form (UI-005)."""
        s = self.server
        # `preview` (UI-010) computes the schedule and writes nothing, so the page can ask before a past freeze is saved.
        preview = data.pop("preview", False) if isinstance(data, dict) else False
        if preview not in (True, False) or not isinstance(preview, bool):
            raise ValueError("Give the event's start, end and time zone.")
        if set(data) != {"start", "end", "zone"} or not all(isinstance(v, str) for v in data.values()):
            raise ValueError("Give the event's start, end and time zone.")
        if not SCHEDULE_TIME.fullmatch(data["start"]) or not SCHEDULE_TIME.fullmatch(data["end"]):
            raise ValueError("Write dates as YYYY-MM-DD HH:MM (for example 2026-11-12 10:00).")
        if data["end"] <= data["start"]:
            raise ValueError("The event must end after it starts.")
        if not TIME_ZONE.fullmatch(data["zone"]):
            raise ValueError("Choose a time zone such as America/Mexico_City or UTC.")
        uak = s.engine()
        root = project_root(s.target)
        # The engine computes the schedule; setup writes Freeze-Epoch itself, never through a symlinked PROJECT.md or
        # the engine's predictable PROJECT.md.tmp (UI-005 review).
        s.planning.regular_file(root, ".uak/PROJECT.md")
        result = s.run([bash_binary(), str(uak), "clock", data["start"], data["end"], data["zone"]],
                       cwd=str(root), timeout=60)
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        freeze = re.search(r"(?m)^freeze\s+(.+?)\s+Freeze-Epoch: (\d+)", output)
        first = re.search(r"(?m)^first claim by\s+(\S+ \S+)", output)
        if result.returncode or not freeze:
            raise ValueError("The schedule could not be set: %s" % redact(output.strip())[-400:])
        if preview:
            self.reply(200, {"freeze": freeze.group(1).strip(), "epoch": int(freeze.group(2)),
                             "soon": int(freeze.group(2)) < time.time() + 3600})
            return
        s.planning.set_freeze(root, int(freeze.group(2)))
        with s.lock:
            s.state.update(phase="setup", ready=False, checks=[], next_command="", next_note="", error="")
        self.reply(200, {"freeze": freeze.group(1).strip(), "epoch": int(freeze.group(2)),
                         "first_claim": first.group(1) if first else "", "details": redact(output.strip())})

    def recheck_plan(self):
        """Lint, cards and digest of the current plan files again, without running the planner (UI-005)."""
        s = self.server
        planning = s.planning
        if not s.plan or s.plan.get("failed"):
            raise ValueError("Create the plan first, then check it again.")
        uak = s.engine()
        root = project_root(s.target)
        tasks = planning.regular_file(root, ".uak/TASKS.md")
        text = tasks.read_text(encoding="utf-8", errors="replace") if tasks.is_file() else ""
        checked = planning.lint(s.run, root, uak, bash_binary())
        with s.lock:
            s.plan.update(lint=checked, cards=planning.cards(text), digest=planning.digest(root))
            s.state.update(phase="planned", error="")
        self.reply(200, {"lint": s.plan["lint"], "digest": s.plan["digest"]})

    def approve(self, data):
        root, approver, head, remote, base = approval_checks(self.server, data)
        self.server.approve_run(root, data["digest"], approver, head, remote, base)
        self.reply(202, {"phase": "approving"})

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
            installed = kit_present(root) and s.failed_target != str(root)
            repair = (root / ".uak").exists()
            with s.lock:
                previous = dict(s.state) if s.failed_target == str(root) else {}
                s.target = str(root)
                s.forget(root)
                s.tools_cache.pop(str(root), None)
                if self.identity is not None:
                    s.state["identity"] = self.identity
                s.state.update(target=str(root), installed=installed, can_repair=repair, phase="error" if previous else "setup" if repair else "options", ready=False, checks=[], next_command="", next_note="", freeze=0, details=previous.get("details", ""), error=previous.get("error", ""))
                state = dict(s.state)
            self.reply(200, dict(state, settings=s.config()))
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
            with s.lock:
                s.state.update(phase="setup", ready=False, checks=[], next_command="", next_note="", details="", error="")
            self.reply(200, {"saved": True, "settings": s.config()})
        elif self.path == "/api/check":
            if data:
                raise ValueError("The readiness check accepts no options.")
            # The engine that checks readiness is the one shipped with this setup (kit/.uak in the kit's checkout,
            # .uak in an installed project), so the check needs no installer and never certifies another version.
            uak = s.engine()
            with s.lock:
                s.tools_cache.pop(s.target, None)
                if self.identity is not None:
                    s.state["identity"] = self.identity
            s.launch("checking", [bash_binary(), str(uak), "start"])
            self.reply(202, {"phase": "checking"})
        elif self.path == "/api/idea":
            s.engine()
            root = project_root(s.target)
            s.planning.save_idea(root, data, read_config(root).get("Mode", ""))
            with s.lock:
                s.plan = None
            self.reply(200, {"saved": True})
        elif self.path == "/api/plan":
            if set(data) - {"harness", "note"} or "harness" not in data:
                raise ValueError("Choose the coding tool that creates the plan.")
            note = data.get("note", "")
            if not isinstance(note, str) or len(note) > 4000:
                raise ValueError("Keep the requested changes under 4000 characters.")
            s.engine()
            root = project_root(s.target)
            if not (root / "IDEA.md").is_file():
                raise ValueError("Describe what you are building first.")
            known = remote_state(s, root, fresh=True)
            if known["state"] == "offline":
                raise ValueError("Could not reach %s: %s" % (remote_and_base()[0], known["detail"]))
            if not known.get("kit"):
                raise ValueError("Publish the kit to main first (Prepare: Publish the kit to main), then create the plan. "
                                 "The plan's checks read the kit from main.")
            offered = {o["harness"] for o in planners(s, root) if o["available"]}
            if data["harness"] not in offered:
                raise ValueError("That coding tool cannot create the plan here. Choose one that setup offers.")
            s.plan_run(data["harness"], s.planning.planner_command(data["harness"], root), note.strip())
            self.reply(202, {"phase": "planning"})
        elif self.path == "/api/plan/approve":
            self.approve(data)
        elif self.path == "/api/human":
            if set(data) != {"name"} or not isinstance(data["name"], str) or not HUMAN_NAME.fullmatch(data["name"]):
                raise ValueError("Use a short name in lowercase letters, digits, - or _ (for example: ana).")
            with s.lock:
                s.state["human"] = data["name"]
            self.reply(200, {"human": data["name"]})
        elif self.path == "/api/schedule":
            self.schedule(data)
        elif self.path == "/api/publish-kit":
            if set(data) != {"digest"} or not isinstance(data["digest"], str):
                raise ValueError("Open the preview of the kit files, then publish them.")
            root, files, digest, base_head, remote, base = publish_checks(s)
            if not hmac.compare_digest(data["digest"], digest):
                raise ValueError("The kit files changed after the preview. Open the preview again before publishing.")
            s.publish_run(root, files, digest, s.state.get("human"), base_head, remote, base)
            self.reply(202, {"phase": "publishing"})
        elif self.path == "/api/team/reviewer":
            root, name, who = registration_checks(s, data)
            # Read fresh from claims (never the cache) before the engine runs; the slow lane, not the state lock.
            known = remote_state(s, root, fresh=True)
            if known["state"] != "ok":
                raise ValueError("Could not reach %s: %s" % (remote_and_base()[0], known.get("detail") or "no such remote"))
            found = reviewer_record(known, who, name)
            if found["retired"]:
                raise ValueError(found["message"])
            if found["registered"]:
                self.reply(200, dict(found, message="%s was already registered by %s." % (who, found["registered_by"])))
                return
            s.register_run(root, name, who, s.engine())
            self.reply(202, {"phase": "registering"})
        elif self.path == "/api/team/roles":
            self.reply(200, {"roles": save_roles(s, data)})
        elif self.path == "/api/plan/check":
            if data:
                raise ValueError("Checking the plan again accepts no options.")
            self.recheck_plan()
        else:
            self.reply(404, {"error": "Action not found."})


def approval_checks(server, data):
    """Everything that must hold before the person's approval is committed; each failure says how to recover."""
    planning, run = server.planning, server.run
    if set(data) != {"confirm", "digest"} or not all(isinstance(v, str) for v in data.values()):
        raise ValueError("Type the project name to approve the plan you reviewed.")
    server.engine()
    root = project_root(server.target)
    plan = server.plan
    if not plan or plan.get("failed"):
        raise ValueError("Create the plan first, then review it.")
    if plan["violations"]:
        raise ValueError("The last planning run changed files it may not change. Undo those changes, then create the plan again.")
    if data["confirm"] != root.name:
        raise ValueError("Type the project folder name exactly as shown: %s" % root.name)
    for name in planning.PLAN_FILES:
        if not planning.regular_file(root, name).is_file():
            raise ValueError("%s is missing. Create the plan again." % name)
    if not hmac.compare_digest(data["digest"], planning.digest(root)):
        raise ValueError("The plan files changed since you reviewed them. Review the plan again before approving.")
    checked = planning.lint(run, root, server.engine(), bash_binary())
    if not checked["ok"]:
        raise ValueError("The plan does not pass uak lint: %s. Ask for changes." % "; ".join(checked["lines"][:3] or ["see Technical details"]))

    def git(*args, timeout=60):
        return planning.git(run, root, *args, timeout=timeout)

    approver = git("config", "user.name").stdout.strip()
    if not approver or not git("config", "user.email").stdout.strip():
        raise ValueError('Set your Git identity first: git config user.name "Your Name" and git config user.email you@example.com')
    staged = [n for n in git("diff", "--cached", "--name-only", "-z").stdout.split("\0") if n]
    if staged:
        raise ValueError("Other files are staged: %s. Unstage them with git restore --staged -- %s, then approve again."
                         % (", ".join(staged[:5]), " ".join(staged[:5])))
    remote, base = remote_and_base()
    if git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip() != base:
        raise ValueError("The plan is published on %s. Switch to it first: git switch %s" % (base, base))
    # Into setup's own ref, never FETCH_HEAD (the engine reads its own), with the network timeout (UI-011).
    fetched = net_git(server, root, "fetch", "-q", "--no-tags", "--no-write-fetch-head", remote,
                      "+refs/heads/%s:%s" % (base, SETUP_BASE))
    if fetched.returncode:
        raise ValueError("Could not reach %s: %s" % (remote, offline_detail(fetched)))
    head = git("rev-parse", "HEAD").stdout.strip()
    upstream = git("rev-parse", SETUP_BASE).stdout.strip()
    if head != upstream:
        if git("merge-base", "--is-ancestor", head, upstream).returncode == 0:
            raise ValueError("%s/%s has newer commits. Run git pull --ff-only %s %s, then review the plan again." % (remote, base, remote, base))
        raise ValueError("This branch has commits that are not on %s/%s. Push or move them first, so the approval "
                         "publishes only the plan." % (remote, base))
    if git("diff", "--quiet", "HEAD", "--", ".uak/PROJECT.md").returncode:
        raise ValueError("You have your own uncommitted changes in .uak/PROJECT.md. Commit or discard them first.")
    return root, approver, head, remote, base


def publish_checks(server):
    """Everything that must hold before the kit is published from the page; each failure says how to recover."""
    planning, run = server.planning, server.run
    if not server.state.get("human"):
        raise ValueError("Tell setup your name first (Your name, in Prepare): publishing is a human act.")
    server.engine()
    root = project_root(server.target)

    def git(*args, timeout=60):
        return planning.git(run, root, *args, timeout=timeout)

    if not git("config", "user.name").stdout.strip() or not git("config", "user.email").stdout.strip():
        raise ValueError('Set your Git identity first: git config user.name "Your Name" and git config user.email you@example.com')
    staged = [n for n in git("diff", "--cached", "--name-only", "-z").stdout.split("\0") if n]
    if staged:
        raise ValueError("Other files are staged: %s. Unstage them with git restore --staged -- %s, then publish again."
                         % (", ".join(staged[:5]), " ".join(staged[:5])))
    remote, base = remote_and_base()
    if git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip() != base:
        raise ValueError("The kit is published on %s. Switch to it first: git switch %s" % (base, base))
    if git("remote", "get-url", remote).returncode:
        raise ValueError("This project has no remote named %s. Create an empty repository and run: "
                         "git remote add %s <its URL>" % (remote, remote))
    head = git("rev-parse", "-q", "--verify", "HEAD").stdout.strip()
    listed = net_git(server, root, "ls-remote", "--heads", remote, "refs/heads/" + base)
    if listed.returncode:
        raise ValueError("Could not reach %s: %s" % (remote, offline_detail(listed)))
    if heads_of(listed.stdout).get("refs/heads/" + base):
        fetched = net_git(server, root, "fetch", "-q", "--no-tags", "--no-write-fetch-head", remote,
                          "+refs/heads/%s:%s" % (base, SETUP_BASE))
        if fetched.returncode:
            raise ValueError("Could not read %s/%s: %s" % (remote, base, offline_detail(fetched)))
        upstream = git("rev-parse", SETUP_BASE).stdout.strip()
        if head != upstream:
            if head and git("merge-base", "--is-ancestor", head, upstream).returncode == 0:
                raise ValueError("%s/%s already has commits this folder lacks. Run git pull %s %s, then publish again."
                                 % (remote, base, remote, base))
            if not head or not git("merge-base", head, upstream).stdout.strip():
                raise unrelated_history(server, root, head, remote, base)
            raise ValueError("This branch has commits that are not on %s/%s. Push or move them first, so publishing "
                             "sends only the kit." % (remote, base))
    elif head:
        raise ValueError("This branch has commits and %s has no %s yet. Push them yourself first "
                         "(git push -u %s HEAD:%s), then publish the kit." % (remote, base, remote, base))
    files = planning.publish_files(run, root)
    if not files:
        raise ValueError("Nothing to publish: the kit is already on %s." % base)
    return root, files, planning.publish_digest(root, files), head, remote, base

def unrelated_history(server, root, head, remote, base):
    """The remote base has its own first commits and no common ancestor with this folder (round 4: a GitHub repository
    created with a .gitignore). One exact command that keeps both histories, or a new empty repository. Files that
    exist here and would be overwritten (untracked or ignored: a merge overwrites ignored files silently) are renamed to
    NAME.mine first; anything setup cannot make safe gives no command at all. Setup never runs any of it."""
    planning = server.planning

    def git(*args):
        return planning.git(server.run, root, *args, timeout=60)

    folded = sys.platform == "darwin" or os.name == "nt"  # case-insensitive file systems
    fold = (lambda p: p.lower()) if folded else (lambda p: p)
    tracked = {fold(p) for p in git("ls-files", "-z").stdout.split("\0") if p} if head else set()
    collide, unsafe = [], False
    for path in [p for p in git("ls-tree", "-r", "--name-only", "-z", SETUP_BASE).stdout.split("\0") if p]:
        parts = path.split("/")
        for depth in range(1, len(parts)):
            parent = root.joinpath(*parts[:depth])
            if parent.is_symlink() or (os.path.lexists(str(parent)) and not parent.is_dir()):
                unsafe = True  # a file here where the remote has a folder
        local = root.joinpath(*parts)
        if fold(path) in tracked or not os.path.lexists(str(local)):
            continue
        if local.is_dir() and not local.is_symlink():
            unsafe = True  # a folder here where the remote has a file
        else:
            collide.append(path)
    text = root.as_posix()
    if unsafe or len(collide) > 8 or not quotable(text) or any(
            not SAFE_PATH.fullmatch(p) or ".." in p.split("/") or os.path.lexists(str(root / (p + ".mine")))
            for p in collide):
        command = ""
    else:
        parts = ["cd " + shell_quote(text)]
        for p in collide:
            mine = shell_quote(p + ".mine")
            # mv -n would exit 0 without moving: the tests stop the chain before git pull instead (amendment 8).
            parts += ["test ! -e " + mine, "test ! -L " + mine, "mv -- %s %s" % (shell_quote(p), mine)]
        command = " && ".join(parts + ["git pull --no-rebase --no-edit --allow-unrelated-histories %s %s" % (remote, base)])
    steps = []
    if command:
        steps.append("If Git reports a conflict, open the files it names, keep what you need from both, then run git add "
                     "on them and git commit.")
        if collide:
            steps.append("Your copies are kept with .mine added to their names: %s. Choose Repair or update kit so the kit "
                         "adds its lines to .gitignore again, then compare and delete the .mine files."
                         % ", ".join(p + ".mine" for p in collide))
        steps.append("Or publish to a new empty repository (no README, no .gitignore, no license): git remote set-url %s "
                     "<its URL>" % remote)
    else:
        steps.append("Setup cannot write a safe command for the files this folder and %s/%s both have. Publish to a new "
                     "empty repository instead (no README, no .gitignore, no license): git remote set-url %s <its URL>"
                     % (remote, base, remote))
    return WayOut("%s/%s already has its own first commits (for example a README or .gitignore created on GitHub), and they "
                  "do not share history with this folder. Nothing was changed. The command below runs git pull to join "
                  "both histories; read it before you run it." % (remote, base),
                  {"command": command, "renamed": collide if command else [], "steps": steps})


def refusal(exc):
    body = {"error": redact(exc)}
    if isinstance(exc, WayOut):
        body["way_out"] = exc.way_out
    return body


def shell_quote(path):
    """A path as one single-quoted Bash word (forward slashes, as Git Bash and wt write it)."""
    return "'" + path.replace("'", "'\\''") + "'"


def quotable(text):
    """A path setup shows inside a command: no quote mark and no control character (it never escapes them)."""
    return "'" not in text and not any(ord(c) < 32 or ord(c) == 127 for c in text)


def codex_flags(gitdir):
    return CODEX_FLAGS % shell_quote(gitdir)


def valid_ref_name(name):
    """A remote or branch name setup puts into a refspec: plain, and never a path trick (amendment 7)."""
    return bool(REF_NAME.fullmatch(name)) and ".." not in name and "//" not in name and "@{" not in name and \
        not name.endswith(("/", ".")) and not any(part.startswith(".") or part.endswith(".lock") for part in name.split("/"))


def remote_and_base():
    """UAK_REMOTE / UAK_BASE or origin / main: the one place every setup reader takes them from (PENDING #41)."""
    remote, base = os.environ.get("UAK_REMOTE") or "origin", os.environ.get("UAK_BASE") or "main"
    if not valid_ref_name(remote) or not valid_ref_name(base):
        raise ValueError("UAK_REMOTE and UAK_BASE must be plain names such as origin and main. Fix them in the terminal "
                         "that started setup, then restart it.")
    return remote, base


def net_git(server, root, *args):
    """Git that talks to the remote: 30 s, and a timeout stops the whole tree (git-remote-https)."""
    return server.run(list(server.planning.GIT) + ["-C", str(root)] + list(args), cwd=str(root), timeout=NET_TIMEOUT,
                      group=True)


def offline_detail(result):
    if result.returncode == 124:
        return "timed out after %d s" % NET_TIMEOUT
    text = " ".join(redact((result.stderr or result.stdout or "").strip()).split())[-300:].rstrip(". ")
    return text or "(no message)"


def heads_of(text):
    """ls-remote output as {exact ref name: sha}; a tail match would take refs/heads/x/main for main (amendment 6)."""
    heads = {}
    for line in (text or "").splitlines():
        parts = line.strip().split("\t")
        if len(parts) == 2:
            heads[parts[1].strip()] = parts[0].strip()
    return heads


def read_remote(server, root, remote, base):
    """What the team and plan views need from the remote, read into setup's own refs (never FETCH_HEAD)."""
    planning = server.planning
    now = time.monotonic()

    def git(*args):
        return planning.git(server.run, root, *args, timeout=60)

    if git("remote", "get-url", remote).returncode:
        return {"state": "none", "detail": "", "at": now}
    listed = net_git(server, root, "ls-remote", "--heads", remote, "refs/heads/" + base, "refs/heads/claims")
    if listed.returncode:
        return {"state": "offline", "detail": offline_detail(listed), "at": now}
    heads = heads_of(listed.stdout)

    result = {"state": "ok", "detail": "", "kit": False, "reviewers": {}, "retired": [], "claims": {}, "files": [],
              "at": now}
    # What setup already holds in its private refs (one process); one fetch for every branch that moved.
    held = {}
    for line in git("for-each-ref", "--format=%(refname) %(objectname)", "refs/uak/").stdout.splitlines():
        name, _, sha = line.strip().partition(" ")
        held[name] = sha
    pairs = [(base, SETUP_BASE), ("claims", SETUP_CLAIMS)]
    present = [(branch, ref) for branch, ref in pairs if heads.get("refs/heads/" + branch)]
    moved = ["+refs/heads/%s:%s" % (branch, ref) for branch, ref in present
             if held.get(ref) != heads["refs/heads/" + branch]]
    if moved:
        got = net_git(server, root, "fetch", "-q", "--no-tags", "--no-write-fetch-head", remote, *moved)
        if got.returncode:
            return {"state": "offline", "detail": offline_detail(got), "at": now}
    for branch, ref in present:
        if ref == SETUP_BASE:
            result["kit"] = git("cat-file", "-e", SETUP_BASE + ":.uak/PROJECT.md").returncode == 0
        else:
            read_claims(git, result)
    return result


def read_claims(git, result):
    """Reviewer roles, retired identities and claims from setup's copy of the claims branch: two local commands.
    Everything read is data; only files named like NAME.md count, and each line feeds only its own folder's fields."""
    # The person's Git config must not change the output this parses (review of 993e112: grep.lineNumber or
    # grep.column in a global config turned every line into ref:path:N:Field and nothing was read).
    found = git("grep", "--no-color", "--no-line-number", "--no-column", "--full-name", "-E",
                "^(Reviewer|Registered-By|ID|State|Owner): ", SETUP_CLAIMS, "--", "roles/reviewers", "claims")
    records = {}
    prefix = SETUP_CLAIMS + ":"
    for line in (found.stdout or "").splitlines() if found.returncode == 0 else []:
        if not line.startswith(prefix):
            continue
        path, _, text = line[len(prefix):].partition(":")
        folder, _, name = path.rpartition("/")
        match = re.match(r"([A-Za-z-]+): *(.*?) *\r?$", text)
        if folder not in ("roles/reviewers", "claims") or not CLAIM_FILE.fullmatch(name) or not match:
            continue
        records.setdefault((folder, name[:-3]), {}).setdefault(match.group(1), match.group(2))
    for (folder, stem), fields in records.items():
        if folder == "roles/reviewers" and fields.get("Reviewer") == stem and fields.get("Registered-By"):
            result["reviewers"][stem] = fields["Registered-By"][:64]
        elif folder == "claims" and fields.get("ID") == stem:
            result["claims"][stem] = {"state": fields.get("State", ""), "owner": fields.get("Owner", "")[:64]}
    listed = git("ls-tree", "--name-only", SETUP_CLAIMS, "claims/", "meta/retired/")
    for path in (listed.stdout or "").splitlines():
        folder, _, name = path.strip().rpartition("/")
        if CLAIM_FILE.fullmatch(name):
            (result["files"] if folder == "claims" else result["retired"] if folder == "meta/retired" else []).append(name[:-3])


def remote_state(server, root, fresh=False):
    """The only reader of the remote for the team and plan views. Results are kept per project, remote and base (status
    reads the last one); only an `ok` younger than 15 s is reused, and never for a decision (`fresh`)."""
    remote, base = remote_and_base()
    key = (str(root), remote, base)
    if not fresh:
        with server.lock:
            hit = server.remote_cache.get(key)
        if hit and hit["state"] == "ok" and time.monotonic() - hit["at"] < REMOTE_TTL:
            return hit
    result = read_remote(server, root, remote, base)
    with server.lock:
        server.remote_cache[key] = result
    return result


def reviewer_record(known, who, human):
    """Whether NAME-r reviews in this project, from its claims (roles/reviewers minus meta/retired); None when unknown."""
    record = {"name": who, "registered": False, "registered_by": "", "retired": False, "message": ""}
    if known.get("state") != "ok":
        return dict(record, registered=None)
    by = known["reviewers"].get(who, "")
    if who in known["retired"]:
        return dict(record, retired=True, registered_by=by,
                    message="%s was retired, so it cannot review. Choose another name in Your name, or ask the human "
                            "who retired it." % who)
    if by:
        record.update(registered=True, registered_by=by,
                      message="%s is registered: it reviews your agents' work." % who if by == human else
                      "%s was already registered by %s." % (who, by))
    return record


def reviewer_status(server, target, human):
    """/api/status's reviewer: derived from the last read of this project's claims, for this name; {} before any."""
    if not target or not human:
        return {}
    try:
        key = (target,) + remote_and_base()
    except ValueError:
        return {}
    with server.lock:
        known = server.remote_cache.get(key)
    return reviewer_record(known, human + "-r", human) if known else {}


def planners(server, root):
    """available_planners, probed in the slow lane with the whole tree stopped after 20 s (amendment 5); cached 60 s."""
    key = str(root)
    with server.lock:
        hit = server.tools_cache.get(key)
    if hit and time.monotonic() - hit[0] < TOOLS_TTL:
        return hit[1]

    def probe(command, cwd=None, timeout=PROBE_TIMEOUT, **kwargs):
        return server.run(command, cwd=cwd, timeout=min(timeout, PROBE_TIMEOUT), group=True)

    offers = server.planning.available_planners(root, probe)
    with server.lock:
        server.tools_cache[key] = (time.monotonic(), offers)
    return offers


def team_context(server):
    """The team step needs the human's name (UI-005), a READY or waiting check and an installed kit; returns
    (root, name, phase)."""
    with server.lock:
        state = dict(server.state)
    name = state.get("human") or ""
    if not HUMAN_NAME.fullmatch(name):
        raise ValueError("Tell setup your name first (Your name, in Prepare): registering the reviewer is a human act.")
    phase = team_phase(state)
    if not phase:
        raise ValueError("Press Check what's next first: the team starts after the readiness check says Ready.")
    server.engine()
    return project_root(server.target), name, phase


def git_dirs(server, root):
    """(this checkout's Git dir, the common Git dir), physical; the main checkout is where they are the same."""
    lines = server.planning.git(server.run, root, "rev-parse", "--absolute-git-dir", "--git-common-dir").stdout.splitlines()
    paths = [(Path(t.strip()) if os.path.isabs(t.strip()) else root / t.strip()).resolve() if t.strip() else None
             for t in lines[:2]]
    return tuple(paths + [None] * (2 - len(paths)))


def main_checkout(server, root):
    """True in the project's main checkout (its Git dir is the common dir), false in a linked task worktree."""
    git_dir, common = git_dirs(server, root)
    return bool(git_dir and common) and git_dir == common


def read_roles(gitdir):
    """Each person's saved picks in <git common dir>/uak-setup/roles.json: per clone, never committed or shared.
    Anything unexpected (a link, too big, not JSON, an unknown tool or name) is ignored."""
    folder = Path(gitdir) / "uak-setup"
    path = folder / "roles.json"
    try:
        if folder.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    people = data.get("people") if isinstance(data, dict) else None
    if not isinstance(people, dict):
        return {}
    tools = ("claude", "codex")
    return {name: {"implement": pick["implement"], "review": pick["review"]} for name, pick in people.items()
            if isinstance(name, str) and HUMAN_NAME.fullmatch(name) and isinstance(pick, dict)
            and pick.get("implement") in tools and pick.get("review") in tools}


def write_roles(planning, gitdir, name, implement, review):
    folder = Path(gitdir) / "uak-setup"
    path = folder / "roles.json"
    refused = ValueError("Setup keeps your choice in .git/uak-setup/roles.json, and that is a link or not a regular "
                         "file. Remove it, then choose again.")
    if folder.is_symlink() or (os.path.lexists(str(folder)) and not folder.is_dir()):
        raise refused
    folder.mkdir(exist_ok=True)
    if path.is_symlink() or (os.path.lexists(str(path)) and not path.is_file()):
        raise refused
    people = read_roles(gitdir)  # other people's picks are kept
    people[name] = {"implement": implement, "review": review}
    planning.write_atomic(path, (json.dumps({"version": 1, "people": people}, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def effective_roles(saved, available):
    """The saved pick when both its tools are available now; otherwise Claude Code implements and Codex reviews, or the
    only available tool does both (UI-014)."""
    tools = [t for t in ("claude", "codex") if t in available]
    if not tools:
        return {"implement": "", "review": "", "saved": False, "same_tool": False, "note": ""}
    note = ""
    if saved and saved["implement"] in tools and saved["review"] in tools:
        implement, review, kept = saved["implement"], saved["review"], True
    else:
        implement, review, kept = tools[0], tools[-1], False
        if saved:
            note = "Your saved choice used a tool that is not available now, so setup chose again."
    return {"implement": implement, "review": review, "saved": kept, "same_tool": implement == review, "note": note}


def tool_view(server, root):
    """The coding tools setup can start here: the same detection planning uses (installed in the project, found on
    this computer, signed in), Claude Code and Codex only."""
    rows = []
    for offer in planners(server, root):
        if offer["harness"] in TOOL_LABEL:  # reasons are planning's own texts, each with a Spanish entry
            rows.append({"id": offer["harness"], "label": TOOL_LABEL[offer["harness"]], "available": offer["available"],
                         "reason": offer["reason"], "role": "none"})
    return rows


def save_roles(server, data):
    """POST /api/team/roles: who implements and who reviews, for this person, in this clone."""
    tools = ("claude", "codex")
    if set(data) != {"implement", "review"} or not all(isinstance(v, str) and v in tools for v in data.values()):
        raise ValueError("Choose which coding tool implements and which one reviews.")
    root, name, _ = team_context(server)
    git_dir, common = git_dirs(server, root)
    if not common or git_dir != common:
        raise ValueError("Choose the main project folder in this page (not a task worktree): agents start from there.")
    rows = {row["id"]: row for row in tool_view(server, root)}
    for tool in (data["implement"], data["review"]):
        if not rows[tool]["available"]:
            raise ValueError("That coding tool is not available here: %s" % rows[tool]["reason"])
    write_roles(server.planning, common, name, data["implement"], data["review"])
    with server.lock:
        server.forget(root)
    return effective_roles(read_roles(common).get(name), {t for t, r in rows.items() if r["available"]})


def implement_command(tool, root, worktree, gitdir, task, identity, name):
    head = "cd %s && UAK_HUMAN= bash .uak/bin/wt new %s --agent %s --human %s && cd %s && UAK_HUMAN= " % (
        shell_quote(root), task, identity, name, shell_quote(worktree))
    if tool == "claude":
        return head + "claude " + shell_quote(IMPL_PROMPT % task)
    return head + "codex %s %s" % (codex_flags(gitdir), shell_quote(IMPL_PROMPT_CODEX % task))


def resume_command(tool, worktree, gitdir):
    return "cd %s && UAK_HUMAN= %s" % (shell_quote(worktree), "claude" if tool == "claude" else "codex " + codex_flags(gitdir))


def review_command(tool, root, gitdir, who):
    if tool == "claude":
        return "cd %s && UAK_HUMAN= UAK_AGENT=%s claude %s" % (shell_quote(root), who, shell_quote(REVIEW_PROMPT_CLAUDE % who))
    return "cd %s && UAK_HUMAN= UAK_AGENT=%s codex %s %s" % (shell_quote(root), who, codex_flags(gitdir),
                                                            shell_quote(REVIEW_PROMPT % who))


def checkout_agent_note(root, who):
    """R3 (amendment 10): .uak-env in the main checkout overrides UAK_AGENT, so the review would not run as NAME-r."""
    env_file = root / ".uak-env"
    if env_file.is_symlink():
        return (".uak-env in the project folder is a symbolic link, so setup cannot tell which agent a reviewer started "
                "there would be. Remove the link, then press Retry.")
    if not env_file.is_file():
        return ""
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        value = line.strip().rstrip("\r")
        if value.startswith("UAK_AGENT=") and value != "UAK_AGENT=" + who:
            return (".uak-env in the project folder says this checkout is the agent %s, so a reviewer started there "
                    "would not be %s. Remove that line (or the file), then press Retry." % (value[len("UAK_AGENT="):][:64], who))
    return ""


def team_view(server):
    """GET /api/team: who implements and who reviews (per person), the reviewer's state in this project's claims, the
    tasks already claimed, and the Copy commands. Commands are built only from server values (the READY line's task,
    the name, enum tools, constant prompts, paths from Git here) and never run by setup."""
    root, name, phase = team_context(server)
    who = name + "-r"
    view = {"task": "", "human": name, "reviewer": who, "phase": phase, "stale": False,
            "remote": {"state": "", "detail": ""}, "commands": [], "note": "", "review_note": "", "claimed": [], "tools": [],
            "roles": effective_roles(None, set()), "retry": False, "can_check": False,
            "registered": {"name": who, "registered": False, "registered_by": "", "retired": False, "message": ""}}
    text = root.as_posix()
    if not quotable(text) or root.parent == root:
        view["note"] = ("Rename the project folder (no quote mark or control character, and not a drive's root), then "
                        "press Check again: setup only shows commands it can quote exactly.")
        return view
    git_dir, common = git_dirs(server, root)  # one look at Git (each process costs on Windows)
    if not (git_dir and common) or git_dir != common:
        view["note"] = ("Choose the main project folder in this page (not a task worktree): agents start from there.")
        return view
    gitdir = common.as_posix()
    if not quotable(gitdir):
        view["note"] = ("The project's Git folder has a quote mark or control character in its path, so setup cannot "
                        "quote the commands exactly. Move it to a path without them, then press Check again.")
        return view
    remote, base = remote_and_base()
    known = remote_state(server, root)
    view["remote"] = {"state": known["state"], "detail": known.get("detail", "")}
    if known["state"] == "offline":
        view.update(retry=True, registered=dict(view["registered"], registered=None),
                    note="Setup cannot reach %s right now (%s). Check your connection, then press Retry."
                         % (remote, known["detail"]))
        return view
    if known["state"] == "none":
        view.update(retry=True, registered=dict(view["registered"], registered=None),
                    note="This project has no remote named %s. Add one, then press Retry." % remote)
        return view
    if not known["kit"]:
        view["note"] = "Publish the kit to main first (Prepare: Publish the kit to main): agents read the kit from there."
        return view
    view["registered"] = reviewer_record(known, who, name)
    tools = tool_view(server, root)
    available = {t["id"] for t in tools if t["available"]}
    roles = effective_roles(read_roles(gitdir).get(name), available)
    for tool in tools:
        picked = [role for role in ("implement", "review") if roles[role] == tool["id"]]
        tool["role"] = "both" if len(picked) == 2 else picked[0] if picked else "none"
    view.update(tools=tools, roles=roles)
    wt_root = root.parent / (root.name + "-wt")
    claims = known["claims"]
    owner = re.compile(r"(claude|codex)-%s(-[1-9])?\Z" % re.escape(name))
    for task in sorted(claims):
        claim = claims[task]
        if claim["state"] not in LIVE_STATES or not TEAM_TASK.fullmatch(task):
            continue
        mine = owner.fullmatch(claim["owner"])
        folder = wt_root / task.lower()
        row = {"task": task, "state": claim["state"], "owner": claim["owner"], "mine": bool(mine),
               "here": folder.is_dir(), "tool": TOOL_LABEL[mine.group(1)] if mine else "", "resume": ""}
        if mine and row["here"] and mine.group(1) in available:
            row["resume"] = resume_command(mine.group(1), folder.as_posix(), gitdir)
        view["claimed"].append(row)
    if not available:
        view["note"] = ("No coding tool can start here: Claude Code: %s Codex: %s With Cursor or Gemini, claim the task "
                        "with the command below and open the tool in its folder yourself."
                        % tuple(next(t["reason"] for t in tools if t["id"] == i) for i in ("claude", "codex")))
        return view
    commands = []
    with server.lock:
        claim = CLAIM_COMMAND.match(server.state.get("next_command") or "")
    task = claim.group(1) if claim and TEAM_TASK.fullmatch(claim.group(1)) else ""
    if phase == "waiting":
        view["note"] = "No task is free to start right now."
    elif not task:
        # A READY line that does not parse to a valid task: no command at all (amendment 2).
        view["note"] = "No task is free to start right now. Press Check what's next again in a moment."
        return view
    elif task in known["files"] or (wt_root / task.lower()).exists():
        # claim.sh refuses a claim whenever claims/ID.md exists, in any state (amendment 6).
        view.update(can_check=True, note="%s was claimed since the last check. Press Check what's next to find a free "
                                         "task." % task)
    else:
        # One identity holds one live task (claim.sh): the first free TOOL-NAME, TOOL-NAME-2 … TOOL-NAME-9. Lease
        # expiry is ignored on purpose: a stale claim keeps its name until the engine frees it.
        held = {c["owner"] for c in claims.values() if c["state"] in ("CLAIMED", "BLOCKED")}
        tool = roles["implement"]
        identity = next((i for i in ["%s-%s" % (tool, name)] + ["%s-%s-%d" % (tool, name, n) for n in range(2, 10)]
                         if i not in held and i not in known["retired"]), "")
        if identity:
            folder = (wt_root / task.lower()).as_posix()
            view["task"] = task
            commands.append({"id": "implement", "harness": tool, "tool": TOOL_LABEL[tool], "identity": identity,
                             "task": task, "terminal": "Terminal 1: a new terminal window, any folder",
                             "command": implement_command(tool, text, folder, gitdir, task, identity, name),
                             "resume": resume_command(tool, folder, gitdir)})
        else:
            view["note"] = ("Each of your implementer names (%s-%s to %s-%s-9) already holds a task. Finish or release one, "
                            "then press Check what's next." % (tool, name, tool, name))
    env_note = checkout_agent_note(root, who)
    if env_note:
        # Its own field, so an earlier note never hides it (review of 993e112); the page shows both.
        view["review_note"] = env_note
        view["note"] = view["note"] or env_note
        view["retry"] = True
    elif not view["registered"]["retired"]:
        tool = roles["review"]
        commands.append({"id": "review", "harness": tool, "tool": TOOL_LABEL[tool], "identity": who,
                         "terminal": "Terminal 2: another new terminal window, any folder",
                         "command": review_command(tool, text, gitdir, who)})
    view["commands"] = commands
    return view


def registration_checks(server, data):
    """Everything that must hold before the reviewer is registered from the page (UI-006 contract, amendments 1-2)."""
    if set(data) != {"confirm"} or not isinstance(data["confirm"], str):
        raise ValueError("Confirm the reviewer's name to register it.")
    root, name, _ = team_context(server)
    who = name + "-r"
    if not hmac.compare_digest(data["confirm"].encode("utf-8"), who.encode("utf-8")):
        raise ValueError("Confirm exactly the reviewer shown on the page: %s" % who)
    planning = server.planning

    def git(*args, timeout=60):
        return planning.git(server.run, root, *args, timeout=timeout)

    if not main_checkout(server, root):
        raise ValueError("Register the reviewer from the project's main checkout, not from a task worktree. Choose the "
                         "main project folder in this page.")
    # The engine names the registrar from .uak-env, then git config uak.agent; registering yourself is refused
    # (review-merge.sh: "cannot grant a role to themselves"), so setup says where that name comes from first.
    env_file = root / ".uak-env"
    if env_file.is_symlink():
        raise ValueError("%s is a symbolic link, so setup cannot tell which agent this checkout is. Remove the link, "
                         "then register again." % env_file)
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().rstrip("\r") == "UAK_AGENT=" + who:
                raise ValueError("%s in this folder says this checkout is the agent %s, so it cannot register itself. "
                                 "Remove that line (or the file), then register again." % (env_file, who))
    # -z: the origin path is printed as is (without it Git quotes and octal-escapes a path with an accent).
    origin = git("config", "-z", "--show-scope", "--show-origin", "--get", "uak.agent")
    if origin.returncode == 0 and origin.stdout.strip("\0\n"):
        parts = re.split(r"[\t\0]", origin.stdout.rstrip("\0\n"), maxsplit=2)
        scope, source, value = (parts + ["", "", ""])[:3]
        value = value.rstrip("\0\n")
        if value == who:
            source = source[len("file:"):] if source.startswith("file:") else source
            if source and not os.path.isabs(source):
                source = str(root / source)
            flag = "--global " if scope == "global" else "--system " if scope == "system" else ""
            raise ValueError("Git config uak.agent = %s (set in %s) makes this checkout the agent %s, so it cannot "
                             "register itself. Remove it: git config %s--unset uak.agent, then register again."
                             % (value, source or scope, who, flag))
    return root, name, who


def registration_env(name):
    env = {"UAK_HUMAN": name, "UAK_AGENT": ""}
    for key in ("UAK_REMOTE", "UAK_BASE"):  # the same remote and base publish_checks uses
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


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
