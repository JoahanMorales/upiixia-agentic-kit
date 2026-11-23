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
import importlib.util
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
    if grandchild:
        body = ('"%s" -c "import os,time; open(r\'%s\',\'w\').write(str(os.getpid())); time.sleep(300)" &\n'
                'echo $$ > "%s"\nwait\n') % (python, (pids / "grand").as_posix(), (pids / "child").as_posix())
    else:
        body = 'echo $$ > "%s"\nexec "%s" -c "import time; time.sleep(300)"\n' % ((pids / "child").as_posix(), python)
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
    assert not (folder / "uak-wizard.port").exists(), "and removed when it ends"
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


TESTS = [second_start_reuses_the_first, idle_server_ends, closed_page_ends_the_server, no_child_survives_sigterm,
         no_child_survives_sigkill_on_linux, stale_record_is_reaped, idle_page_starts_no_process,
         hidden_page_does_not_poll, dashboard_refresh_is_one_ls_remote]


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
