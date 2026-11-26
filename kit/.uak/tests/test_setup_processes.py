#!/usr/bin/env python3
"""UAK-156: the wizard is one process that ends by itself, leaves no child and no port behind, and an open page
costs nothing while nothing happens.
Measured 2026-11-22 before this task: one /api/check costs about 950 forks and 1.25 CPU-s and the page ran it every
minute for ever; two starts gave two servers on two ports, neither ended; a planner survived SIGTERM, SIGKILL and
SIGHUP of the server with PPID 1.
Real processes (the wizard as a person starts it, a project whose `uak` is a script that sleeps, so a child exists
while the signal arrives), real HTTP, real Git with a local bare remote. The page's timers are read in its source and
its scheduling functions run in Node when there is one. Every process this file starts is stopped by its PID."""
import argparse
import contextlib
import gc
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import test_setup_planning as plans
import test_setup_trust as trust
import test_setup_wizard as wizard

WINDOWS = os.name == "nt"
LINUX = sys.platform.startswith("linux")
GRACE = 1  # CLOSE_GRACE_SECONDS the test processes run with
IDLE = 3   # IDLE_EXIT_SECONDS the test processes run with

LAUNCH = ("import sys; sys.path.insert(0, %r); import setup; setup.IDLE_EXIT_SECONDS = %s; "
          "setup.CLOSE_GRACE_SECONDS = %s; sys.argv = ['setup.py', '--no-open', %r]; raise SystemExit(setup.main())")


def lib(root, name):
    return (root / ".uak/bin/lib" / name).read_text(encoding="utf-8")


def alive(pid):
    if WINDOWS:
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:  # a zombie is gone for this purpose
        with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def wait_until(check, seconds, step=0.1):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(step)
    return bool(check())


def listening(port):
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def gitdir(target):
    return Path(plans.git(target, "rev-parse", "--path-format=absolute", "--git-common-dir"))


def package_copy(root, tmp):
    """A copy of the engine the wizard runs from (the check runs the engine shipped with setup, not the project's)."""
    copy = tmp / "pkg"
    shutil.copytree(str(root / ".uak"), str(copy / ".uak"), ignore=shutil.ignore_patterns("tests", "__pycache__"))
    return copy


def sleeper(target, tmp, grandchild=False):
    """The engine's `uak` becomes a script that records its PID and sleeps: the readiness check then runs a child."""
    pids = tmp / "pids"
    pids.mkdir(exist_ok=True)
    python = Path(sys.executable).as_posix()
    record = "import os,time; open(r'%s','w').write(str(os.getpid())); time.sleep(300)"
    if grandchild:
        body = '"%s" -c "%s" &\nwait\n' % (python, record % (pids / "grand").as_posix())
        body = body.replace("&\nwait", "&\necho $$ > \"%s\"\nwait" % (pids / "child").as_posix())
    else:
        body = 'exec "%s" -c "%s"\n' % (python, record % (pids / "child").as_posix())
    (target / ".uak/bin/uak").write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")  # target: the package copy
    return pids


def pid_of(path):
    wait_until(path.is_file, 20)
    wait_until(lambda: path.is_file() and path.read_text(encoding="utf-8").strip().isdigit(), 5)
    return int(path.read_text(encoding="utf-8").strip())


class Wizard:
    """The wizard as a person starts it: a real process with a terminal on its input."""

    def __init__(self, root, tmp, target, idle=900, grace=8, plain=False):
        self.root, self.target, self.tmp = root, target, tmp
        env = trust.human_env()
        if plain:
            argv = [sys.executable, str(root / ".uak/bin/lib/setup.py"), "--no-open", str(target)]
        else:
            argv = [sys.executable, "-c", LAUNCH % (str(root / ".uak/bin/lib"), idle, grace, str(target))]
        self.proc = trust.popen_with_terminal(argv, cwd=str(tmp), env=env)
        self.out = []
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()
        wait_until(lambda: any("UAK SETUP http" in line or "already running" in line or "refused" in line
                               for line in self.out), 60)
        found = re.search(r"127\.0\.0\.1:(\d+)", " ".join(self.out))
        self.port = int(found.group(1)) if found else 0
        self.token = ""

    def read(self):
        for line in self.proc.stdout:
            self.out.append(line.rstrip("\n"))

    def launcher(self):
        wait_until(lambda: any(line.startswith("Launcher file:") for line in self.out), 20)
        line = [x for x in self.out if x.startswith("Launcher file:")][-1]
        return Path(line.split(":", 1)[1].strip())

    def session(self):
        page = self.launcher().read_text(encoding="utf-8")
        code = re.search(r"#code=([A-Za-z0-9_\-]+)", page).group(1)
        status, body = self.call("POST", "/api/session", {"code": code}, token=False)
        assert status == 200, (status, body)
        self.token = body["token"]
        return self.token

    def call(self, method, path, data=None, token=True, extra=None):
        import http.client
        host = "127.0.0.1:%d" % self.port
        headers = {"Content-Type": "application/json", "Origin": "http://" + host}
        if token:
            headers["X-UAK-Token"] = self.token
        headers.update(extra or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request(method, path, json.dumps(data).encode() if data is not None else None, headers)
            res = conn.getresponse()
            raw = res.read()
            try:
                return res.status, json.loads(raw or b"{}")
            except ValueError:
                return res.status, raw
        finally:
            conn.close()

    def check_running(self, pids):
        """Inspect the project and start the readiness check: a child exists until the test ends it."""
        self.session()
        assert self.call("POST", "/api/inspect", {"target": str(self.target)})[0] == 200
        assert self.call("POST", "/api/check", {})[0] == 202
        return pid_of(pids / "child")

    def files(self):
        folder = gitdir(self.target)
        return {name: folder / ("uak-wizard." + name) for name in ("port", "key", "children")}

    def ended(self, seconds=20):
        try:
            self.proc.wait(seconds)
        except subprocess.TimeoutExpired:
            return False
        self.reader.join(5)
        return True

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(15)
        self.reader.join(5)
        for stream in (self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
        if getattr(self.proc, "master", None) is not None:
            try:
                os.close(self.proc.master)
            except OSError:
                pass
            self.proc.master = None
        for line in self.out:
            found = re.match(r"Launcher file: (.+)open\.html\s*$", line)
            if found:
                shutil.rmtree(found.group(1), ignore_errors=True)


def project(root, tmp, name="demo plan"):
    target, _ = plans.project(root, tmp, name=name)
    return target


def second_start_reuses_the_first(root, tmp):
    target = project(root, tmp)
    first = Wizard(root, tmp, target)
    second = None
    try:
        assert first.port, first.out
        record = first.files()["port"].read_text(encoding="utf-8").split()
        assert record == [str(first.proc.pid), str(first.port)], record
        second = Wizard(root, tmp, target, plain=True)
        assert second.ended(30), "the second start ends by itself: %r" % second.out
        assert second.proc.returncode == 0, (second.proc.returncode, second.out)
        said = " ".join(second.out)
        assert "already running" in said and str(first.port) in said, "it says it opened the first one: %r" % said
        assert first.files()["port"].read_text(encoding="utf-8").split() == record, "the record is still the first one's"
        # Its launcher is a fresh code of the FIRST server: the person lands in the running one.
        page = second.launcher().read_text(encoding="utf-8")
        code = re.search(r"#code=([A-Za-z0-9_\-]+)", page).group(1)
        assert ":%d/" % first.port in page, "the launcher points at the first server's port"
        assert first.call("POST", "/api/session", {"code": code}, token=False)[0] == 200, "the first server honours it"
        assert not alive(second.proc.pid), "the second process is gone"
        assert first.proc.poll() is None, "the first server was not disturbed"
    finally:
        if second:
            second.stop()
        first.stop()
    assert not listening(first.port), "the port is free once the first ends"


def stale_record_is_reaped(root, tmp):
    target = project(root, tmp)
    folder = gitdir(target)
    # A record whose process is dead and whose port is something that is not a wizard.
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    with socket.socket() as stranger:
        stranger.bind(("127.0.0.1", 0))
        stranger.listen(1)
        (folder / "uak-wizard.port").write_text("%d %d\n" % (dead.pid, stranger.getsockname()[1]), encoding="ascii")
        fresh = Wizard(root, tmp, target)
        try:
            assert "UAK SETUP http" in " ".join(fresh.out), "a stale record is replaced, not obeyed: %r" % fresh.out
            assert fresh.port != stranger.getsockname()[1]
            assert (folder / "uak-wizard.port").read_text(encoding="utf-8").split() == [str(fresh.proc.pid), str(fresh.port)]
        finally:
            fresh.stop()
    assert WINDOWS or not (folder / "uak-wizard.port").exists(), "and removed when it ends"  # Windows: a hard stop
    if not (LINUX or sys.platform == "darwin"):
        return  # Windows keeps its children in a job that closes with the server; there is no record to reap from
    # A server killed with SIGKILL leaves a grandchild (pdeathsig reaches the direct child only): the next start reaps it.
    pkg = package_copy(root, tmp)
    pids = sleeper(pkg, tmp, grandchild=True)
    first = Wizard(pkg, tmp, target)
    survivor = None
    try:
        first.check_running(pids)
        survivor = pid_of(pids / "grand")
        assert alive(survivor)
        first.proc.kill()
        first.proc.wait(15)
        assert alive(survivor), "the grandchild of a killed server is orphaned (what the record is for)"
        assert (folder / "uak-wizard.children").is_file(), "the record names the group"
    finally:
        first.stop()
    second = Wizard(pkg, tmp, target)
    try:
        assert wait_until(lambda: not alive(survivor), 20), "the next start reaped what the killed server left"
        assert "UAK SETUP http" in " ".join(second.out), second.out
    finally:
        second.stop()
        if survivor and alive(survivor):
            os.kill(survivor, signal.SIGKILL)  # by PID, only if the assertion above failed


def idle_server_ends(root, tmp):
    # The decision, with a clock the test moves.
    target = project(root, tmp)
    with wizard.LiveServer(str(target)) as srv:
        assert wizard.MODULE.IDLE_EXIT_SECONDS == 15 * 60, "15 minutes with no request"
        now = [1000.0]
        srv.clock = lambda: now[0]
        srv.last_request = srv.clock()
        now[0] += 14 * 60
        assert not srv.end_reason(), "14 minutes is not idle"
        wizard.request(srv, "GET", "/api/status")
        now[0] += 14 * 60
        assert not srv.end_reason(), "a request starts the 15 minutes again"
        now[0] += 2 * 60
        reason = srv.end_reason()
        assert reason and "15 minutes" in reason, reason
        srv.last_request = srv.clock() - 16 * 60
        srv.worker = threading.Thread(target=time.sleep, args=(5,), daemon=True)
        srv.worker.start()
        assert not srv.end_reason(), "an action that runs is not idle"
        srv.worker.join(10)
    # The process: it exits by itself, says why and the one command that opens it again, and frees the port.
    wiz = Wizard(root, tmp, target, idle=IDLE)
    try:
        port, files = wiz.port, wiz.files()
        assert files["port"].is_file()
        assert wiz.ended(30), "the idle wizard ends by itself"
        assert wiz.proc.returncode == 0, wiz.proc.returncode
        said = " ".join(wiz.out)
        assert re.search(r"no request|idle|without", said) and "install.sh --wizard" in said, said
        assert not listening(port) and not files["port"].exists(), "the port is free and the record is gone"
        assert not files["key"].exists() and not files["children"].exists()
    finally:
        wiz.stop()


def closed_page_ends_the_server(root, tmp):
    target = project(root, tmp)
    pkg = package_copy(root, tmp)
    pids = sleeper(pkg, tmp)
    wiz = Wizard(pkg, tmp, target, grace=GRACE)
    try:
        wiz.session()
        assert wiz.call("POST", "/api/closing", {})[0] == 200, "the page says it was closed"
        # A reload says it too, and asks again at once: the server stays.
        assert wiz.call("GET", "/api/status")[0] == 200
        time.sleep(GRACE + 2)
        assert wiz.proc.poll() is None, "a page that came back keeps the server"
        assert wiz.call("POST", "/api/closing", {})[0] == 200
        assert wiz.ended(20), "a closed page ends the server"
        assert wiz.proc.returncode == 0
        said = " ".join(wiz.out)
        assert "closed" in said and "install.sh --wizard" in said, said
        assert not listening(wiz.port)
    finally:
        wiz.stop()
    # With an action running the page may close and the server stays until the action ends.
    wiz = Wizard(pkg, tmp, target, grace=GRACE)
    try:
        child = wiz.check_running(pids)
        assert wiz.call("POST", "/api/closing", {})[0] == 200
        time.sleep(GRACE + 2)
        assert wiz.proc.poll() is None, "a running action keeps the server open"
        assert alive(child)
    finally:
        wiz.stop()
    assert wait_until(lambda: not alive(child), 20), "and its child ends with it"


def no_child_survives_sigterm(root, tmp):
    target = project(root, tmp)
    pkg = package_copy(root, tmp)
    names = [None] if WINDOWS else ["TERM", "HUP", "INT"]
    for name in names:
        pids = sleeper(pkg, tmp)
        for old in pids.iterdir():
            old.unlink()
        wiz = Wizard(pkg, tmp, target)
        try:
            child = wiz.check_running(pids)
            assert alive(child) and wiz.files()["children"].is_file(), "a child runs and the server records it"
            port = wiz.port
            if name is None:
                wiz.proc.terminate()
            else:
                wiz.proc.send_signal(getattr(signal, "SIG" + name))
            assert wiz.ended(30), "SIG%s ends the wizard" % name
            assert wait_until(lambda: not alive(child), 10), "SIG%s: the child is gone" % name
            assert not listening(port), "SIG%s: the port is free" % name
            if not WINDOWS:  # there the stop is TerminateProcess: nothing runs after it, the job ends the child
                assert not any(path.exists() for path in wiz.files().values()), "SIG%s: no record is left" % name
                said = " ".join(wiz.out)
                assert "install.sh --wizard" in said and "ended" in said, "it says why and how to open it again: %r" % said
        finally:
            wiz.stop()
            if not WINDOWS and (pids / "child").is_file() and alive(int((pids / "child").read_text().strip())):
                os.kill(int((pids / "child").read_text().strip()), signal.SIGKILL)  # by PID, only when an assertion failed


def no_child_survives_sigkill_on_linux(root, tmp):
    if not LINUX:
        return
    target = project(root, tmp)
    pkg = package_copy(root, tmp)
    pids = sleeper(pkg, tmp)
    child = 0
    wiz = Wizard(pkg, tmp, target)
    try:
        child = wiz.check_running(pids)
        assert alive(child)
        wiz.proc.kill()
        wiz.proc.wait(15)
        assert wait_until(lambda: not alive(child), 10), "the child dies with a server killed by SIGKILL (parent-death signal)"
    finally:
        wiz.stop()
        if child and alive(child):
            os.kill(child, signal.SIGKILL)  # by PID, only when the assertion failed
    # stop() above removed nothing of the project's: the record is stale, and the next start cleans it
    again = Wizard(root, tmp, target)
    try:
        assert "UAK SETUP http" in " ".join(again.out), again.out
    finally:
        again.stop()


# --- the page: what runs while it is open and nothing happens ---------------------------------------------------------
class Counted:
    """Counts every process the in-process server starts (and, on POSIX, every `git` through a counting shim in PATH)."""

    def __init__(self, tmp):
        self.calls, self.tmp = [], tmp
        self.original = subprocess.Popen
        counted = self

        class Popen(self.original):
            def __init__(self, args, *more, **kwargs):
                counted.calls.append(list(args) if isinstance(args, (list, tuple)) else [str(args)])
                super().__init__(args, *more, **kwargs)

        self.popen = Popen

    def __enter__(self):
        subprocess.Popen = self.popen
        return self

    def __exit__(self, *args):
        subprocess.Popen = self.original

    def mark(self):
        return len(self.calls)

    def since(self, mark):
        return self.calls[mark:]


def git_calls(calls):
    return [c for c in calls if c and Path(str(c[0])).name.lower().replace(".exe", "") == "git"]


def page_code(root):
    html = lib(root, "setup.html")
    return html[html.index('<script nonce="__NONCE__">'):]


def idle_page_starts_no_process(root, tmp):
    """A visible page that is merely open runs no readiness check: 0 processes in 60 s after its first load, on the
    welcome screen and on the setup screen; the page's timers are read in its source."""
    code = page_code(root)
    assert not re.search(r"setInterval\(\s*autoCheck", code), "no timer runs the readiness check"
    for match in re.finditer(r"setInterval\(\s*(\w+)", code):
        assert match.group(1) not in ("autoCheck", "refresh", "loadDashboard", "probe", "loadTeam"), \
            "an interval that polls: %s" % match.group(0)
    assert not re.search(r"setTimeout\(\s*autoCheck", code)
    target = project(root, tmp)
    with Counted(tmp) as counted, wizard.LiveServer(str(target)) as srv:
        # The first load of the page: the shell, the status, the project, one readiness check by its own page load.
        assert wizard.request(srv, "GET", "/", token=False, origin=False)[0] == 200
        wizard.request(srv, "GET", "/api/status")
        wizard.request(srv, "POST", "/api/inspect", {"target": str(target)})
        wizard.request(srv, "POST", "/api/check", {})
        if srv.worker:
            srv.worker.join(120)
        wizard.request(srv, "GET", "/api/status")
        mark = counted.mark()
        started = time.monotonic()
        time.sleep(60)  # the idle visible page: no timer of it asks the server for anything
        lingering = counted.since(mark)
        assert not lingering, "an idle page starts no process in 60 s (950 before): %r" % lingering[:5]
        print("  measured: %d processes in %.0f s of an idle page after its first load" % (len(lingering), time.monotonic() - started))
        # The 200 quick requests of the same server leave no thread behind.
        before = threading.active_count()

        def hammer(count):
            for _ in range(count):
                wizard.request(srv, "GET", "/api/status")

        workers = [threading.Thread(target=hammer, args=(20,)) for _ in range(10)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(120)
        assert wait_until(lambda: threading.active_count() <= before, 30), \
            "200 quick requests leave no extra thread after 30 s: %d -> %d" % (before, threading.active_count())


def dashboard_refresh_is_one_ls_remote(root, tmp):
    target = project(root, tmp)
    with Counted(tmp) as counted, wizard.LiveServer(str(target)) as srv:
        wizard.request(srv, "POST", "/api/inspect", {"target": str(target)})
        first = counted.mark()
        status, body, _ = wizard.request(srv, "GET", "/api/dashboard")
        assert status == 200, body[:300]
        full = counted.since(first)
        assert json.loads(body).get("source") == "remote", "the dashboard reads the remote"
        assert len(full) > 1, "the first read costs what it costs: %d" % len(full)
        module = srv.dash
        again = counted.mark()
        status, body2, _ = wizard.request(srv, "GET", "/api/dashboard")
        assert status == 200
        cost = counted.since(again)
        assert len(cost) == 1 and "ls-remote" in cost[0], "a refresh when the claims tip did not move is one git ls-remote: %r" % cost
        assert json.loads(body2).get("source") == "remote" and json.loads(body2)["progress"] == json.loads(body)["progress"]
        wizard.request(srv, "GET", "/api/dashboard")
        assert srv.dash is module, "dash.py is imported once per server"
        # A claims tip that moved is read in full again.
        plans.git(target, "checkout", "-q", "--orphan", "claims")
        plans.git(target, "rm", "-rfq", ".")
        (target / "meta").mkdir()
        (target / "meta/config.md").write_text("Lease: 1800\n", encoding="utf-8")
        plans.git(target, "add", "-A")
        plans.git(target, "commit", "-q", "-m", "claims")
        plans.git(target, "push", "-q", "origin", "claims")
        plans.git(target, "checkout", "-q", "-f", "main")
        moved = counted.mark()
        assert wizard.request(srv, "GET", "/api/dashboard")[0] == 200
        assert len(counted.since(moved)) > 1, "a moved tip is read in full"
        print("  measured: first read %d processes, refresh with nothing moved %d (%s)" % (len(full), len(cost), " ".join(cost[0][:4])))


def window_function(code, name):
    match = re.search(r"\n( *)(?:async )?function %s\([\s\S]*?\n\1\}" % re.escape(name), code)
    assert match, "the page defines %s()" % name
    return match.group(0)


def hidden_page_does_not_poll(root, tmp):
    code = page_code(root)
    assert re.search(r"DASH_BACKOFF\s*=\s*\[\s*20000\s*,\s*60000\s*,\s*120000\s*\]", code), "20 s, 60 s, 120 s"
    schedule = window_function(code, "scheduleDashboard")
    assert "document.hidden" in schedule, "the dashboard poll stops while the page is hidden"
    refresh = window_function(code, "refresh")
    assert "document.hidden" in refresh, "the progress poll stops while the page is hidden"
    assert re.search(r"pagehide", code) and "api/closing" in code or re.search(r'api\("closing"', code), \
        "the page says on pagehide that it closed"
    assert re.search(r"1200", refresh), "a running action may poll every 1.2 s"
    probe = window_function(code, "scheduleProbe")
    assert "document.hidden" in probe, "the lost-server probe waits while the page is hidden"
    node = shutil.which("node")
    if not node:
        print("  note: no Node.js here, so the schedule is checked by reading it only")
        return
    program = r"""
const vm = require("vm");
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const timers = [];
const ctx = {document: {hidden: false}, gone: false, currentSection: "dashboard", dashboardTimer: null, dashboardUnchanged: 0,
  loadDashboard: function () {}, setTimeout: (fn, ms) => { timers.push(ms); return timers.length; }, clearTimeout: () => {}};
vm.createContext(ctx);
vm.runInContext(input.backoff + input.delay + input.schedule, ctx);
const out = {hidden: null, delays: []};
ctx.document.hidden = true; ctx.scheduleDashboard(false); out.hidden = timers.length;
ctx.document.hidden = false;
[0, 1, 2, 3, 9].forEach((n) => { ctx.dashboardUnchanged = n; ctx.scheduleDashboard(false); });
out.delays = timers.slice();
ctx.gone = true; ctx.scheduleDashboard(false); out.gone = timers.length;
process.stdout.write(JSON.stringify(out));
"""
    backoff = re.search(r"(?:var|const|let) DASH_BACKOFF[^;]*;", code).group(0) + "\n"
    payload = {"backoff": backoff, "delay": window_function(code, "dashboardDelay"), "schedule": schedule}
    done = subprocess.run([node, "-e", program], input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-1500:]
    out = json.loads(done.stdout)
    assert out["hidden"] == 0, "a hidden page sets no timer: %r" % out
    assert out["delays"] == [20000, 60000, 120000, 120000, 120000], "it backs off while nothing changes: %r" % out
    assert out["gone"] == 5, "a lost server sets no dashboard timer"


# --- pre-review of UAK-156 (kit-r2): a bad record, two tabs, time in the cached dashboard, a silent reopen ---------------
def bad_record_signals_nothing_and_is_removed(root, tmp):
    line = wizard.MODULE.RECORD_LINE  # a start time as `ps -o lstart=` prints it (macOS) and as /proc gives it (Linux)
    assert line.fullmatch("4242 Mon Nov 23 22:28:28 2026") and line.fullmatch("4242 98765432")
    assert not line.fullmatch("0 ") and not line.fullmatch("4242 ") and not line.fullmatch("\u00b2 x")
    if WINDOWS:
        return  # nothing reads the record there
    target = project(root, tmp)
    folder = gitdir(target)
    sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])  # in this test's own group
    try:
        own = wizard.MODULE.process_stamp(os.getpgrp())
        parent = wizard.MODULE.process_stamp(os.getppid())
        lines = ["0 123", "1 123", "-5 abc", "99999999999999999999 x", "\u00b2 x", "garbage", "", "%d %s" % (os.getpgrp(), own),
                 "%d %s" % (os.getpid(), own), "%d %s" % (os.getppid(), parent), "%d " % os.getpgrp()]
        record = folder / "uak-wizard.children"
        record.write_text("\n".join(lines) + "\n", encoding="utf-8")
        wiz = Wizard(root, tmp, target)
        try:
            assert "UAK SETUP http" in " ".join(wiz.out), "a corrupt record does not stop the start: %r" % wiz.out
            assert sentinel.poll() is None, "nothing in this test's own group was signalled"
            assert os.getpgid(os.getpid()) == os.getpgrp()
            assert not record.exists(), "the record is gone"
        finally:
            wiz.stop()
    finally:
        sentinel.kill()
        sentinel.wait(10)


def two_tabs_one_closes(root, tmp):
    target = project(root, tmp)
    # The decision, with a clock the test moves.
    with wizard.LiveServer(str(target)) as srv:
        now = [1000.0]
        srv.clock = lambda: now[0]
        srv.seen_request("aaaaaaaa11")
        srv.seen_request("bbbbbbbb22")
        srv.page_closed("aaaaaaaa11")
        now[0] += wizard.MODULE.CLOSE_GRACE_SECONDS + 4
        assert not srv.end_reason(), "the other tab is open: the server stays"
        srv.page_closed("bbbbbbbb22")
        now[0] += wizard.MODULE.CLOSE_GRACE_SECONDS + 1
        assert "closed" in srv.end_reason(), "both closed: it ends"
        srv.seen_request("cccccccc33")  # a reload: a new page within the grace
        assert not srv.end_reason(), "a new page keeps it"
    # The process, over HTTP.
    wiz = Wizard(root, tmp, target, grace=GRACE)
    try:
        wiz.session()
        one, two = {"X-UAK-Page": "pageone0001"}, {"X-UAK-Page": "pagetwo0002"}
        assert wiz.call("GET", "/api/status", extra=one)[0] == 200
        assert wiz.call("GET", "/api/status", extra=two)[0] == 200
        assert wiz.call("POST", "/api/closing", {}, extra=one)[0] == 200
        time.sleep(GRACE + 4)
        assert wiz.proc.poll() is None, "closing one tab leaves the server under the other"
        assert wiz.call("POST", "/api/closing", {}, extra=two)[0] == 200
        assert wiz.ended(20), "both closed: it ends"
    finally:
        wiz.stop()


def cached_dashboard_keeps_time_moving(root, tmp):
    import test_dashboard_truth as truth
    target, remote = plans.project(root, tmp)
    t0 = 1800000000
    stamp = lambda: "Updated: %d\n" % t0  # noqa: E731
    truth.write_claims(tmp, remote, {
        "meta/config.md": "Lease-Seconds: 1800\nStall-Seconds: 5400\n",
        "tasks/APP-001.md": "ID: APP-001\nState: CLAIMED\nOwner: claude-ana\nProgress-Changed: %d\n%s" % (t0, stamp()),
        "meta/agents/claude-ana.md": "Name: claude-ana\n" + stamp()})
    with Counted(tmp) as counted, wizard.LiveServer(str(target)) as srv:
        wizard.request(srv, "POST", "/api/inspect", {"target": str(target)})
        old = os.environ.get("UAK_NOW")
        try:
            os.environ["UAK_NOW"] = str(t0 + 60)
            first = json.loads(wizard.request(srv, "GET", "/api/dashboard")[1])
            assert first["generated"] == t0 + 60
            agent = [a for a in first["agents"] if a["name"] == "claude-ana"][0]
            assert agent["status"] == "online", agent
            assert not [t for t in first["tasks"] if t["id"] == "APP-001"][0].get("stalled", 0), "not stalled a minute in"
            os.environ["UAK_NOW"] = str(t0 + 4 * 3600)  # four hours later, the tip has not moved
            mark = counted.mark()
            second = json.loads(wizard.request(srv, "GET", "/api/dashboard")[1])
            cost = counted.since(mark)
        finally:
            if old is None:
                os.environ.pop("UAK_NOW", None)
            else:
                os.environ["UAK_NOW"] = old
        assert len(cost) == 1 and "ls-remote" in cost[0], "still one git ls-remote: %r" % cost
        assert second["generated"] == t0 + 4 * 3600, "the time-derived part is computed again: %r" % second["generated"]
        agent = [a for a in second["agents"] if a["name"] == "claude-ana"][0]
        assert agent["status"] == "offline", "the agent went idle on the same tip: %r" % agent
        assert [t for t in second["tasks"] if t["id"] == "APP-001"][0].get("stalled", 0) > 0, "the task is stalled on the same tip"


def reopen_is_never_silent(root, tmp):
    target = project(root, tmp)
    first = Wizard(root, tmp, target)
    second = None
    try:
        first.session()
        page = {"X-UAK-Page": "openpage0001"}
        status, _ = first.call("GET", "/api/status", extra=page)
        assert status == 200
        before = len(first.out)
        second = Wizard(root, tmp, target, plain=True)
        assert second.ended(30) and second.proc.returncode == 0, second.out
        assert wait_until(lambda: any("second start" in line for line in first.out[before:]), 10), \
            "the first terminal says a second start asked for a new page: %r" % first.out[before:]
        said = [line for line in first.out[before:] if "second start" in line][0]
        assert re.search(r"\d\d:\d\d", said) and "Ctrl" in said, said
        register = (gitdir(target) / "uak-direct-main.log").read_text(encoding="utf-8")
        assert "reopen" in register, "the register of acts has the line: %r" % register
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", first.port, timeout=10)
        conn.request("GET", "/api/status", headers={"Host": "127.0.0.1:%d" % first.port, "X-UAK-Token": first.token,
                                                      "X-UAK-Page": "openpage0001"})
        answer = conn.getresponse()
        answer.read()
        assert answer.getheader("X-UAK-Reopens") == "1", "the open page's next answer carries the counter: %r" % answer.getheader("X-UAK-Reopens")
        assert re.fullmatch(r"\d\d:\d\d", answer.getheader("X-UAK-Reopened-At") or ""), answer.getheader("X-UAK-Reopened-At")
        conn.close()
        # A page that began after the reopen sees no counter.
        conn = http.client.HTTPConnection("127.0.0.1", first.port, timeout=10)
        conn.request("GET", "/api/status", headers={"Host": "127.0.0.1:%d" % first.port, "X-UAK-Token": first.token,
                                                      "X-UAK-Page": "latepage0002"})
        answer = conn.getresponse()
        answer.read()
        assert answer.getheader("X-UAK-Reopens") == "1", answer.getheader("X-UAK-Reopens")  # a page no reopen created is told
        conn.close()
        # The session ended: the reopen is refused and the second start says how to start again.
        first.call("POST", "/api/closing", {}, extra=page)  # not relevant to the refusal below
        with wizard.LiveServer(str(target)) as srv:
            srv.ended = True
            host = "127.0.0.1:%d" % srv.server_port
            status, body, _ = wizard.request(srv, "POST", "/api/reopen", {}, token=False,
                                             extra={"X-UAK-Reopen": srv.key})
            assert status == 409 and "ended" in json.loads(body)["error"], (status, body)
    finally:
        if second:
            second.stop()
        first.stop()


def two_simultaneous_starts_leave_one_server(root, tmp):
    target = project(root, tmp)
    boxes = [[], []]

    def start(slot):
        boxes[slot].append(Wizard(root, tmp, target))

    threads = [threading.Thread(target=start, args=(slot,)) for slot in (0, 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(90)
    wizards = [box[0] for box in boxes if box]
    try:
        assert len(wizards) == 2
        winners = [w for w in wizards if w.proc.poll() is None]
        for loser in [w for w in wizards if w not in winners]:
            assert loser.ended(30) and loser.proc.returncode == 0, loser.out
        assert len(winners) == 1 or wait_until(lambda: len([w for w in wizards if w.proc.poll() is None]) == 1, 30), \
            "two simultaneous starts leave one server: %r" % [w.out for w in wizards]
        live = [w for w in wizards if w.proc.poll() is None][0]
        assert listening(live.port)
        others = [w for w in wizards if w is not live]
        assert others and not listening(others[0].port) or others[0].port == live.port
    finally:
        for wiz in wizards:
            wiz.stop()


# --- pre-review 2 of UAK-156 ---------------------------------------------------------------------------------------------
def invented_page_ids_are_not_kept(root, tmp):
    target = project(root, tmp)
    with wizard.LiveServer(str(target)) as srv:
        now = [1000.0]
        srv.clock = lambda: now[0]
        for n in range(1000):  # no session: every one is refused, none is remembered, none delays anything
            status = wizard.request(srv, "GET", "/api/status", token=False, extra={"X-UAK-Page": "invented%06d" % n})[0]
            assert status == 403
        assert not srv.pages, "unauthenticated ids are not kept: %d" % len(srv.pages)
        for bad in ("short", "UPPERCASE123", "has space 123", "x" * 80, "a-b-c-d-e-f-g"):
            wizard.request(srv, "GET", "/api/status", extra={"X-UAK-Page": bad})
        assert not srv.pages, "a malformed id is not kept: %r" % list(srv.pages)
        for n in range(200):  # a session: ids are kept, at most 64, the one silent the longest goes first
            now[0] += 1
            wizard.request(srv, "GET", "/api/status", extra={"X-UAK-Page": "authentic%05d" % n})
        assert len(srv.pages) <= 64, len(srv.pages)
        assert "authentic00199" in srv.pages and "authentic00000" not in srv.pages
    wiz = Wizard(root, tmp, target, grace=GRACE)
    try:
        wiz.session()
        real = {"X-UAK-Page": "realtab00001"}
        assert wiz.call("GET", "/api/status", extra=real)[0] == 200
        for n in range(300):
            wiz.call("GET", "/api/status", token=False, extra={"X-UAK-Page": "invented%06d" % n})
        assert wiz.call("POST", "/api/closing", {}, extra=real)[0] == 200
        assert wiz.ended(GRACE + 12), "invented ids do not keep the server after the real tab closed"
    finally:
        wiz.stop()


def reopen_before_the_first_request_is_shown(root, tmp):
    target = project(root, tmp)
    first = Wizard(root, tmp, target)
    second = None
    try:
        launcher_page = first.launcher().read_text(encoding="utf-8")
        code = re.search(r"#code=([A-Za-z0-9_\-]+)", launcher_page).group(1)
        human = {"X-UAK-Page": "humanpage001"}
        # The person's page exchanges the original code (its first request carries its id) ...
        status, body = first.call("POST", "/api/session", {"code": code}, token=False, extra=human)
        assert status == 200
        first.token = body["token"]
        # ... a second start reopens before that page asks anything else ...
        second = Wizard(root, tmp, target, plain=True)
        assert second.ended(30) and second.proc.returncode == 0, second.out
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", first.port, timeout=10)
        conn.request("GET", "/api/status", headers={"Host": "127.0.0.1:%d" % first.port, "X-UAK-Token": first.token,
                                                      "X-UAK-Page": "humanpage001"})
        answer = conn.getresponse()
        answer.read()
        assert answer.getheader("X-UAK-Reopens") == "1", "the person's page is told: %r" % answer.getheader("X-UAK-Reopens")
        conn.close()
        # The page that the reopen itself created is not.
        page = second.launcher().read_text(encoding="utf-8")
        code2 = re.search(r"#code=([A-Za-z0-9_\-]+)", page).group(1)
        status, body = first.call("POST", "/api/session", {"code": code2}, token=False, extra={"X-UAK-Page": "reopenpage02"})
        assert status == 200, (status, body)
        conn = http.client.HTTPConnection("127.0.0.1", first.port, timeout=10)
        conn.request("GET", "/api/status", headers={"Host": "127.0.0.1:%d" % first.port, "X-UAK-Token": first.token,
                                                      "X-UAK-Page": "reopenpage02"})
        answer = conn.getresponse()
        answer.read()
        assert answer.getheader("X-UAK-Reopens") == "0", "the page the reopen made is not told about its own reopen"
        conn.close()
    finally:
        if second:
            second.stop()
        first.stop()


def reopen_notice_says_what_happened(root, tmp):
    text = lib(root, "workspace.js")
    page = lib(root, "setup.html")
    sentence = re.search(r'"(Another page of setup was opened at \{time\}[^"]*)"', page)
    assert sentence, "the page's notice names what happened"
    english = sentence.group(1)
    for part in ("second start", "terminal", "If you did", "nothing to do", "press Ctrl+C"):
        assert part in english, (part, english)
    assert "not you" not in english.split("If you did")[0], "what happened comes before the warning"
    pairs = dict(re.findall(r'\[\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)"\s*,?\s*\]', text))
    spanish = pairs.get(english)
    assert spanish and "segundo inicio" in spanish and "Ctrl+C" in spanish and "{time}" in spanish, spanish
    assert "!" not in spanish


# --- UAK-196: every kill checks the start time; the sweep removes only its own folders; the refused record is bounded ---
# The "unrelated program" of these cases is a bystander this test starts itself (its own group or session), checked by
# start time; every process the test ends is one it started, ended by its PID.
SPAWNER = ("import subprocess, sys, time\n"
           "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)\n"
           "print(g.pid, flush=True)\n"
           "g.wait()\n"  # reaped when it ends (no zombie that still has its start time, as on macOS)
           "time.sleep(120)\n")


def bystander():
    extra = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], **extra)
    stamp = wizard.MODULE.process_stamp(proc.pid)
    assert stamp, "the start time of a process this test started is read on %s" % sys.platform
    return proc, stamp


def end(proc):
    if proc.poll() is None:
        proc.kill()
    proc.wait(15)


def end_pid(pid, stamp):
    """A grandchild this test's own child started: ended by PID only while it is still that process."""
    if pid and stamp and wizard.MODULE.process_stamp(pid) == stamp:
        os.kill(pid, signal.SIGKILL)


def still_running_pid(pid):
    return wizard.MODULE.read_stamp(pid) is not None


def still_running(proc, seconds=0.6):
    time.sleep(seconds)
    return proc.poll() is None


class Recorded:
    """The server's record of children, replaced for one case (and the module's read of start times, when given)."""

    def __init__(self, entries, unreadable=()):
        self.entries, self.unreadable = entries, set(unreadable)

    def __enter__(self):
        m = wizard.MODULE
        with m.CHILD_LOCK:
            self.saved = dict(m.CHILDREN)
            m.CHILDREN.clear()
            m.CHILDREN.update(self.entries)
        self.file, m.CHILD_FILE[0] = m.CHILD_FILE[0], None
        self.real = getattr(m, "read_stamp", None)
        if self.unreadable:
            m.read_stamp = lambda pid: "" if pid in self.unreadable else self.real(pid)
        self.out = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.out)
        self.redirect.__enter__()
        return self

    def __exit__(self, *args):
        m = wizard.MODULE
        self.redirect.__exit__(*args)
        if self.real is not None:
            m.read_stamp = self.real
        with m.CHILD_LOCK:
            m.CHILDREN.clear()
            m.CHILDREN.update(self.saved)
        m.CHILD_FILE[0] = self.file

    def said(self, pid):
        return "did not end process %d" % pid in self.out.getvalue()


def stop_children_checks_the_start_time(root, tmp):
    m = wizard.MODULE
    other, other_stamp = bystander()
    mine, mine_stamp = bystander()
    try:
        assert m.process_stamp(other.pid) == other_stamp, "read twice, the start time is the same"
        assert other_stamp != mine_stamp or other.pid != mine.pid
        # The number of `other` recorded with a start time that is not its own: a child of the server that ended and
        # whose number was given to another program.
        with Recorded({other.pid: "1" + other_stamp, mine.pid: mine_stamp}) as rec:
            m.stop_children()
        assert wait_until(lambda: mine.poll() is not None, 15), "the recorded child, the same start time, is ended"
        assert still_running(other), "a number whose start time differs is never signalled"
        assert rec.said(other.pid) and "another program" in rec.out.getvalue(), "and it is said: %r" % rec.out.getvalue()
        assert not rec.said(mine.pid)
        # A start time that cannot be read means: do not kill, and say so.
        with Recorded({other.pid: other_stamp}, unreadable=[other.pid]) as rec:
            m.stop_children()
        assert still_running(other), "a start time that cannot be read signals nothing"
        assert rec.said(other.pid) and "could not read its start time" in rec.out.getvalue(), rec.out.getvalue()
        # Nothing recorded as a start time (a garbled entry): the same.
        with Recorded({other.pid: ""}) as rec:
            m.stop_children()
        assert still_running(other) and rec.said(other.pid), "an entry with no start time signals nothing"
        # A number nobody has any more is forgotten without a word.
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait(15)
        gone_pid = gone.pid
        del gone  # Windows: the handle Popen holds keeps the number (and its start time) until it is closed
        gc.collect()
        with Recorded({gone_pid: "123"}) as rec:
            m.stop_children()
        assert not m.CHILDREN, "it is forgotten"
        assert not rec.said(gone_pid) or not still_running_pid(gone_pid), rec.out.getvalue()
    finally:
        end(other)
        end(mine)


def start_time_check_is_pinned_in_three_places(root, tmp):
    """Each of stop_children, reap_children and TreeWatch.kill compares the start time itself: a case per place goes red
    when the comparison is removed from that place alone."""
    m = wizard.MODULE
    other, stamp = bystander()
    try:
        with Recorded({other.pid: "9" + stamp}):
            m.stop_children()
        assert still_running(other), "stop_children: a recorded number with another start time is not signalled"
    finally:
        end(other)
    if WINDOWS:
        return  # reap_children and TreeWatch do not run there: the children are in a job that closes with the server
    # reap_children: a record a killed server left, with a stranger's start time, garbage, and an unreadable one.
    other, stamp = bystander()
    victim, victim_stamp = bystander()
    unread, unread_stamp = bystander()
    try:
        record = tmp / "uak-wizard.children"
        record.write_text("garbage\n\n0 1\n%d 7%s\n%d %s\n%d %s\n" % (other.pid, stamp, victim.pid, victim_stamp, unread.pid,
                                                                    unread_stamp), encoding="utf-8")
        with Recorded({}, unreadable=[unread.pid]) as rec:
            m.reap_children(record)
        assert wait_until(lambda: victim.poll() is not None, 15), "reap_children: the same start time is ended"
        assert still_running(other), "reap_children: a number with another start time is not signalled"
        assert still_running(unread, 0) and rec.said(unread.pid), "reap_children: unreadable is not signalled, and said"
        assert not record.exists()
    finally:
        for proc in (other, victim, unread):
            end(proc)
    # TreeWatch.kill: what it saw below the run is ended, a number it saw that is now another program's is not.
    other, stamp = bystander()
    parent = subprocess.Popen([sys.executable, "-c", SPAWNER], stdout=subprocess.PIPE, text=True, start_new_session=True)
    grand, grand_stamp = 0, ""
    try:
        grand = int(parent.stdout.readline().strip())
        grand_stamp = m.process_stamp(grand)
        with Recorded({}):
            watch = m.TreeWatch(parent.pid)
            assert wait_until(lambda: grand in watch.seen, 15), "the watch sees the run's grandchild"
            watch.seen[other.pid] = "5" + stamp
            watch.kill()
        assert wait_until(lambda: not m.pid_alive(grand) or m.process_stamp(grand) != grand_stamp, 15), \
            "TreeWatch.kill ends what it saw below the run"
        assert still_running(other), "TreeWatch.kill: a number it saw, now with another start time, is not signalled"
    finally:
        end(other)
        end(parent)
        end_pid(grand, grand_stamp)


def sweep_removes_only_its_own_folders(root, tmp):
    m = wizard.MODULE
    base = Path(tempfile.gettempdir())
    record = tmp / "uak-wizard.launchers"
    keys = getattr(m, "LAUNCH_KEY", [None])  # (before UAK-196 there was none: the case then fails on its assertion)
    saved = (m.LAUNCHERS[0], keys[0])
    made = []
    link = None
    try:
        m.LAUNCHERS[0] = record
        mine = m.write_launcher("true").parent
        made.append(mine)
        foreign = Path(tempfile.mkdtemp(prefix="uak-agent-"))  # empty, another program's
        made.append(foreign)
        foreign_sh = Path(tempfile.mkdtemp(prefix="uak-agent-"))  # a start.sh, another wizard's
        (foreign_sh / "start.sh").write_text("true\n", encoding="utf-8")
        made.append(foreign_sh)
        mine_line = record.read_text(encoding="utf-8").splitlines()[0]
        info = os.lstat(str(foreign))
        hand = [str(foreign), str(foreign_sh), "%s %d %d %s" % ("0" * 64, info.st_dev, info.st_ino, foreign),
                "%s %d %d %s" % (mine_line.split(" ")[0], info.st_dev, info.st_ino, foreign), "1 2", "x y z", "\x00\x01"]
        if not WINDOWS:
            pointed = Path(tempfile.mkdtemp(prefix="uak-agent-"))
            made.append(pointed)
            link = base / ("uak-agent-link-%d" % os.getpid())
            os.symlink(str(pointed), str(link))
            hand.append(str(link))
        with open(str(record), "a", encoding="utf-8") as handle:
            handle.write("\n".join(hand) + "\n")
        m.sweep_launchers(record)
        assert foreign.is_dir(), "an empty uak-agent-* folder that a hand-written record names is left alone"
        assert foreign_sh.is_dir() and (foreign_sh / "start.sh").is_file(), "another wizard's launcher is left alone"
        assert not mine.exists(), "the launcher this wizard made, never run by a terminal, is removed"
        assert not record.exists(), "the record goes with it"
        if link is not None:
            assert link.is_symlink() and pointed.is_dir(), "a link in the record is neither followed nor removed"
        # A line of another wizard's key proves nothing.
        mine = m.write_launcher("true").parent
        made.append(mine)
        m.sweep_launchers(record, key="another-wizards-key-0123456789")
        assert mine.is_dir(), "a line signed with another key removes nothing"
        # A proved line whose folder is now another one at the same path (another inode): left alone.
        stale = m.write_launcher("true").parent
        made.append(stale)
        si = os.lstat(str(stale))
        record.write_text("%s %d %d %s\n" % (m.launcher_proof(m.LAUNCH_KEY[0], stale, si.st_dev, si.st_ino + 1),
                                             si.st_dev, si.st_ino + 1, stale), encoding="utf-8")
        m.sweep_launchers(record)
        assert stale.is_dir(), "a folder whose inode is not the recorded one is left alone"
        # The record file is a link: it is not read through, only the link goes.
        if not WINDOWS:
            mine = m.write_launcher("true").parent
            made.append(mine)
            elsewhere = tmp / "elsewhere"
            os.replace(str(record), str(elsewhere))
            os.symlink(str(elsewhere), str(record))
            m.sweep_launchers(record)
            assert mine.is_dir() and elsewhere.is_file() and not os.path.lexists(str(record)), \
                "a record that is a link is not followed"
            m.remember_launcher(mine)
            assert not os.path.lexists(str(record)) or not record.is_symlink(), "and nothing is appended through a link"
    finally:
        m.LAUNCHERS[0], keys[0] = saved
        if link is not None and os.path.lexists(str(link)):
            os.unlink(str(link))
        for folder in made:
            shutil.rmtree(str(folder), ignore_errors=True)
    # Across a restart: the next start proves the folders of the wizard that left the record with the key it left.
    target = project(root, tmp)
    folder = gitdir(target)
    key = "previous-wizard-key-" + "a" * 20
    old = Path(tempfile.mkdtemp(prefix="uak-agent-"))
    (old / "start.sh").write_text("true\n", encoding="utf-8")
    stranger = Path(tempfile.mkdtemp(prefix="uak-agent-"))
    try:
        oi, si = os.lstat(str(old)), os.lstat(str(stranger))
        (folder / "uak-wizard.launchers").write_text("%s %d %d %s\n%s\n%s %d %d %s\n" % (
            m.launcher_proof(key, old, oi.st_dev, oi.st_ino), oi.st_dev, oi.st_ino, old, stranger,
            m.launcher_proof("not-the-key-0123456789", stranger, si.st_dev, si.st_ino), si.st_dev, si.st_ino, stranger),
            encoding="utf-8")
        (folder / "uak-wizard.key").write_text(key + "\n", encoding="ascii")
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait(15)
        (folder / "uak-wizard.port").write_text("%d 1\n" % dead.pid, encoding="ascii")
        wiz = Wizard(root, tmp, target)
        try:
            assert "UAK SETUP http" in " ".join(wiz.out), wiz.out
            assert not old.exists(), "the previous wizard's launcher, proved by the key it left, is removed at the next start"
            assert stranger.is_dir(), "a folder the record names without that proof is left alone"
            assert not (folder / "uak-wizard.launchers").exists()
        finally:
            wiz.stop()
    finally:
        shutil.rmtree(str(old), ignore_errors=True)
        shutil.rmtree(str(stranger), ignore_errors=True)


def refused_record_is_bounded(root, tmp):
    m = wizard.MODULE
    target = project(root, tmp)
    log = gitdir(target) / m.REFUSED_LOG
    log.write_text("".join("%d refused-run old-%d\n" % (1700000000, n) for n in range(500)), encoding="utf-8")
    with wizard.LiveServer(str(target)) as srv:
        with srv.lock:
            srv.target = str(target)

        def refuse():
            status, body, _ = wizard.request(srv, "POST", "/api/run", {"action": "remove-everything"})
            assert status == 400 and json.loads(body)["error"] == m.RUN_REFUSAL, (status, body)

        refuse()
        lines = log.read_text(encoding="utf-8").splitlines()
        assert len(lines) == getattr(m, "REFUSED_KEEP", 0) == 200, "it keeps its last 200 lines: %d" % len(lines)
        assert lines[-1].endswith("refused-run remove-everything") and lines[0].endswith("old-301"), (lines[0], lines[-1])
        for _ in range(3):
            refuse()
        assert len(log.read_text(encoding="utf-8").splitlines()) == 200, "and stays at 200"
        assert not [p for p in log.parent.iterdir() if p.name.startswith(m.REFUSED_LOG + ".")], "no temporary file is left"
        # A huge record (a long line with no end) is cut from its tail, not read whole.
        log.write_bytes(b"x" * 300000)
        refuse()
        assert log.read_text(encoding="utf-8").splitlines()[-1].endswith("refused-run remove-everything")
        assert log.stat().st_size < 300000
        if not WINDOWS:
            # A link standing at the record's name is not followed; the refusal stands.
            victim = tmp / "a person's file.txt"
            victim.write_text("keep me\n", encoding="utf-8")
            log.unlink()
            os.symlink(str(victim), str(log))
            refuse()
            assert victim.read_text(encoding="utf-8") == "keep me\n", "nothing is written through a link"
            log.unlink()
            if os.geteuid() != 0:
                # A record that cannot be written: the refusal stands, nothing breaks.
                log.write_text("1 refused-run x\n", encoding="utf-8")
                log.chmod(0o400)
                try:
                    refuse()
                    assert log.read_text(encoding="utf-8") == "1 refused-run x\n"
                finally:
                    log.chmod(0o600)


TESTS = [second_start_reuses_the_first, idle_server_ends, closed_page_ends_the_server, no_child_survives_sigterm,
         no_child_survives_sigkill_on_linux, stale_record_is_reaped, idle_page_starts_no_process,
         hidden_page_does_not_poll, dashboard_refresh_is_one_ls_remote, bad_record_signals_nothing_and_is_removed,
         two_tabs_one_closes, cached_dashboard_keeps_time_moving, reopen_is_never_silent,
         two_simultaneous_starts_leave_one_server, invented_page_ids_are_not_kept,
         reopen_before_the_first_request_is_shown, reopen_notice_says_what_happened]
TESTS += [stop_children_checks_the_start_time, start_time_check_is_pinned_in_three_places,  # UAK-196
          sweep_removes_only_its_own_folders, refused_record_is_bounded]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("processes_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("processes_planning", root / ".uak/bin/lib/planning.py")
    plans.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plans.PLANNING)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-proc-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("SETUP_PROCESSES_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
