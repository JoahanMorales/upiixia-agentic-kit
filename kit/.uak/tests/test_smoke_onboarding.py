#!/usr/bin/env python3
"""UAK-093: the product smoke exists from the start and boots the app (QA round C, findings 1, 3 and 10).
Nothing on the onboarding path created .uak/bin/smoke-project: `uak start` said READY, then the first /uak-ship and the
merge gate failed PRODUCT_UNVERIFIED. The hand-made smoke ran only the unit tests, which forced a fake store, so two
green merges integrated an app that crashed on boot (ImportError). init-smoke also left an empty scripts/ folder.
Now start asks for the smoke (a TODO in sprint, where the kit's merge gate runs it; a NOTE in marathon, where the human
merges on GitHub) with the exact command; init-smoke with no --command boots a detected web app and requests one route
under a bounded timeout, killing the whole process tree; and it creates no stray folder.
Real Git, a real install.sh, a fake gh, a real stdlib Python server, separate processes."""
import argparse
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

TASKS = """## APP-001 · Core
- **Priority:** P0
- **Paths:** src/core.sh
- **Depends on:** None
- **Verify:** true
"""

SERVER = '''import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def load_store():
    from app.queue import %(name)s
    return %(name)s()


STORE = load_store()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"size": STORE.size()}).encode()
        self.send_response(200 if self.path == "/api/queue" else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or 8000)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
'''
QUEUE = "class QueueStore:\n    def size(self):\n        return 0\n"
# The round C unit test: it forces a fake store, so it passes whether or not the server can import the real one.
UNIT = ("import unittest\n\n\nclass Fake:\n    def size(self):\n        return 0\n\n\n"
        "class T(unittest.TestCase):\n    def test_size(self):\n        self.assertEqual(Fake().size(), 0)\n\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n")


def clean_env():
    """No UAK_* variable of the caller reaches the fixtures (an exported UAK_BASE=next broke fetches)."""
    for k in [k for k in os.environ if k.startswith("UAK_")]:
        os.environ.pop(k, None)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def serving(port):
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"], capture_output=True, text=True).stdout
        return re.search(r"\b%d\b" % pid, out) is not None
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def py_shim(r):
    """A python3 on PATH that is this interpreter (Windows runners may have only `python`)."""
    d = r.scratch / "py-shim"
    if not d.exists():
        d.mkdir()
        (d / "python3").write_text('#!/usr/bin/env bash\nexec "%s" "$@"\n' % Path(sys.executable).as_posix(), encoding="utf-8")
        os.chmod(d / "python3", 0o755)
    return d.as_posix()


def installed(r, name, mode):
    """A project installed with the real install.sh, published on main, planned and approved."""
    t = r.scratch / name
    t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.g(t, "config", "user.name", "Solo"); r.g(t, "config", "user.email", "solo@example.invalid")
    remote = r.scratch / (name + "-remote.git")
    r.g(r.scratch, "init", "-q", "--bare", remote)
    bin_dir = r.scratch / (name + "-bin")
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/usr/bin/env bash\ncase \"$1 $2\" in\n  'auth status') echo 'Token scopes: repo';;\n"
                                "  'api repos/solo/app/collaborators?per_page=2') echo 1;;\n  'api repos/solo/app') echo true,true,true;;\n"
                                "esac\nexit 0\n", encoding="utf-8")
    os.chmod(bin_dir / "gh", 0o755)
    env = {"PATH": bin_dir.as_posix() + os.pathsep + py_shim(r) + os.pathsep + r.env.get("PATH", ""),
           "GIT_CONFIG_COUNT": "3",
           "GIT_CONFIG_KEY_2": "url." + remote.as_posix() + ".insteadOf", "GIT_CONFIG_VALUE_2": "https://github.com/solo/app.git"}
    r.run([r.bash, str(r.package.parent / "install.sh"), "--mode", mode, "--harness", "claude", str(t)], cwd=t, env=env)
    git = lambda *a: r.run([r.git, *a], cwd=t, env=env)
    git("remote", "add", "origin", "https://github.com/solo/app.git")
    r.run([r.bash, ".uak/bin/uak", "start", "--fix"], cwd=t, env=env, allowed=None)
    (t / ".uak/TASKS.md").write_text(TASKS, encoding="utf-8")
    (t / ".uak/OWNERS.md").write_text("# Shared-file owners\n\n| Pattern | Owner task |\n|---|---|\n", encoding="utf-8")
    project = t / ".uak/PROJECT.md"
    text = project.read_text(encoding="utf-8").replace("Backlog-Approved: no", "Backlog-Approved: yes")
    text = re.sub(r"(?m)^Autonomy:.*$", "Autonomy: yes", text)
    if mode == "sprint":   # a sprint needs its freeze (a day from now) before lint and doctor are clean
        text = re.sub(r"(?m)^Freeze-Epoch:.*\n", "", text) + "Freeze-Epoch: %d\n" % (int(time.time()) + 86400)
    project.write_text(text, encoding="utf-8")
    git("add", "-A"); git("commit", "-qm", "chore: uak setup"); git("push", "-q", "-u", "origin", "main")
    start = lambda: r.run([r.bash, ".uak/bin/start"], cwd=t, env=env, allowed=None)
    uak = lambda *a, **kw: r.run([r.bash, ".uak/bin/uak", *a], cwd=t, env={**env, **kw.pop("env", {})}, allowed=None)
    return t, env, git, start, uak


def stdlib_app(t, broken):
    (t / "app").mkdir(exist_ok=True)
    (t / "app/__init__.py").write_text("", encoding="utf-8")
    (t / "app/server.py").write_text(SERVER % {"name": "Queue" if broken else "QueueStore"}, encoding="utf-8")
    (t / "app/queue.py").write_text(QUEUE, encoding="utf-8")
    (t / "tests").mkdir(exist_ok=True)
    (t / "tests/test_server.py").write_text(UNIT, encoding="utf-8")


def gate_spanish(r, line):
    """The setup page shows the gate's line in Spanish: the GATE row of workspace.js that matches it, filled in."""
    import json
    text = (r.package / ".uak/bin/lib/workspace.js").read_text(encoding="utf-8")
    m = re.search(r"var GATE = (\[[\s\S]*?\n  \]);", text)
    expect(m, "workspace.js has var GATE")
    rest = re.sub(r"^(TODO|NOTE|OK)\s+(\d+\.\s+)?", "", line)
    for rx, es in json.loads(re.sub(r",\s*\]", "]", m.group(1))):
        hit = re.fullmatch(rx, rest)
        if hit:
            return re.sub(r"\$(\d)", lambda g: hit.group(int(g.group(1))), es)
    return None


def smoke_line(out):
    return [l for l in out.splitlines() if "a product smoke" in l]


def start_asks_for_the_smoke(r):
    # Sprint with an app to boot: the kit's merge gate runs the product smoke, so a missing one blocks the first claim
    # with the exact command, which boots the app and requests one route.
    t, env, git, start, uak = installed(r, "onb-sprint", "sprint")
    stdlib_app(t, broken=False)
    out = start()
    line = smoke_line(out.stdout)
    expect(out.returncode == 1 and "START READY" not in out.stdout and line and line[0].startswith("TODO"),
           "sprint, an app, no smoke: a TODO, not READY: " + out.stdout)
    expect("smoke-init.sh boot" in out.stdout and "python3 -m app.server" in out.stdout
           and "/api/queue" in out.stdout and "no app yet" not in out.stdout, "a detected web app: the exact boot command: " + out.stdout)
    es = gate_spanish(r, line[0])
    expect(es and es.startswith("un smoke del producto: main no tiene"), "the setup page reads it in Spanish: %r" % es)
    cmd = re.search(r"(bash \.uak/bin/uak init-smoke --command .*)$", out.stdout, re.M)
    expect(cmd, "one line to paste: " + out.stdout)
    made = r.run([r.bash, "-c", cmd.group(1)], cwd=t, env={**env, "UAK_PORT": str(free_port())}, allowed=None)
    expect(made.returncode == 0 and "SMOKE_ADAPTER_CREATED" in made.stdout, "the pasted command works: " + made.stdout + made.stderr)
    out = start()
    expect(smoke_line(out.stdout) and "push" in out.stdout, "made here, not on main yet: still asked, with push: " + out.stdout)
    git("add", "-A")
    r.run([r.git, "commit", "-qm", "chore: product smoke"], cwd=t, env={**env, "UAK_DIRECT_MAIN": "1"})  # the human's setup commit
    git("push", "-q", "origin", "main")
    out = start()
    expect(out.returncode == 0 and "START READY" in out.stdout and not smoke_line(out.stdout),
           "the smoke on main: READY: " + out.stdout)
    # Marathon: the human merges on GitHub; the same line is a NOTE and READY stays.
    m, menv, mgit, mstart, muak = installed(r, "onb-marathon", "marathon")
    out = mstart()
    line = smoke_line(out.stdout)
    expect(out.returncode == 0 and "START READY" in out.stdout and line and line[0].startswith("NOTE")
           and "init-smoke" in out.stdout, "marathon: a NOTE with the command, READY stays: " + out.stdout)
    return "sprint TODO, marathon NOTE"


def start_notes_the_smoke_before_any_app(r):
    """A fresh sprint with no app yet: nothing to boot, so the smoke is a NOTE with the command and READY stays (the
    first claim is often the walking skeleton itself)."""
    t, env, git, start, uak = installed(r, "onb-fresh", "sprint")
    out = start()
    line = smoke_line(out.stdout)
    expect(out.returncode == 0 and "START READY" in out.stdout and line and line[0].startswith("NOTE")
           and "TODO" not in out.stdout, "no app yet: a NOTE, READY stays: " + out.stdout)
    expect("bash .uak/bin/uak init-smoke --command" in out.stdout and "no app yet" in out.stdout,
           "the NOTE gives the generic init-smoke command: " + out.stdout)
    es = gate_spanish(r, line[0])
    expect(es and es.startswith("un smoke del producto: main no tiene"), "the same Spanish row: %r" % es)
    # Any stack uak deploy knows and init-smoke can boot makes it a TODO (review: Go, Streamlit, Spring stayed a NOTE).
    (t / "go.mod").write_text("module example.com/app\n\ngo 1.22\n", encoding="utf-8")
    (t / "main.go").write_text("package main\n\nfunc main() {}\n", encoding="utf-8")
    out = start()
    line = smoke_line(out.stdout)
    expect(out.returncode == 1 and line and line[0].startswith("TODO") and "go run ." in out.stdout,
           "a Go app: a TODO with its boot command: " + out.stdout)
    return "fresh sprint READY with a NOTE; Go detected"


def web_smoke_boots_the_app(r):
    t, env, git, start, uak = installed(r, "onb-boot", "sprint")
    stdlib_app(t, broken=True)
    unit = r.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"], cwd=t, allowed=None)
    expect(unit.returncode == 0, "the unit tests pass on the broken app (round C): " + unit.stderr)
    port = free_port()
    made = uak("init-smoke", env={"UAK_PORT": str(port)})
    text = made.stdout + made.stderr
    expect(made.returncode != 0 and "PRODUCT_UNVERIFIED" in text and "ImportError" in text,
           "the generated smoke boots the app and fails on its broken import: rc %d %s" % (made.returncode, text[-600:].replace("Error", "E.")))
    adapter = (t / ".uak/bin/smoke-project").read_text(encoding="utf-8").replace("\\", "")   # the command is %q-quoted
    expect("smoke-init.sh boot" in adapter and "app.server" in adapter, "the adapter boots the app: " + adapter)
    stdlib_app(t, broken=False)
    made = uak("init-smoke", env={"UAK_PORT": str(port)})
    expect(made.returncode == 0 and "SMOKE_ADAPTER_CREATED" in made.stdout, "the fixed app boots: " + made.stdout + made.stderr)
    gate = r.run([r.bash, ".uak/bin/lib/smoke-init.sh", "gate"], cwd=t, env={**env, "UAK_PORT": str(port)}, allowed=None)
    expect(gate.returncode == 0 and "PRODUCT_PASS" in gate.stdout, "the gate boots it: " + gate.stdout + gate.stderr)
    expect(not serving(port), "nothing is left serving on the port after the smoke")
    stdlib_app(t, broken=True)
    gate = r.run([r.bash, ".uak/bin/lib/smoke-init.sh", "gate"], cwd=t, env={**env, "UAK_PORT": str(port)}, allowed=None)
    expect(gate.returncode != 0 and "PRODUCT_FAIL" in gate.stderr and "ImportError" in gate.stdout + gate.stderr,
           "the gate catches the broken boot: " + (gate.stdout + gate.stderr).replace("Error", "E."))
    # A server that never answers: bounded, and the whole process tree is gone afterwards.
    py = Path(sys.executable).as_posix()
    (t / "hang.sh").write_text('"%s" -c "import os,time; open(\'hang.pid\',\'w\').write(str(os.getpid())); time.sleep(120)" &\nwait\n' % py,
                               encoding="utf-8")
    began = time.monotonic()
    hang = r.run([r.bash, ".uak/bin/lib/smoke-init.sh", "boot", "--timeout", "4", "--path", "/", "--", "bash hang.sh"],
                 cwd=t, env=env, allowed=None, timeout=60)
    took = time.monotonic() - began
    expect(hang.returncode != 0 and took < 30 and "no answer" in hang.stderr,
           "bounded: rc %d in %.1fs: %s %s" % (hang.returncode, took, hang.stdout, hang.stderr))
    pid = int((t / "hang.pid").read_text(encoding="utf-8").strip())
    deadline = time.monotonic() + 10
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    expect(not alive(pid), "the grandchild server process was killed (pid %d)" % pid)
    return "broken import caught; bounded; tree killed"


def occupied_port_never_answers_for_the_app(r):
    """Review of UAK-093: wt gives each worktree a UAK_PORT and the dev server runs there; with a stale server still up,
    the new app could not bind it and the probe got the old server's answer: BOOT_PASS for an app that never started.
    An occupied UAK_PORT is never probed; the boot moves to a free port and says so."""
    t = r.scratch / "onb-port"
    t.mkdir()
    port = free_port()
    py = Path(sys.executable).as_posix()
    stale = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=str(t),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 15
        while not serving(port) and time.monotonic() < deadline:
            time.sleep(0.2)
        expect(serving(port), "the stale server is up on %d" % port)
        boot = lambda cmd, timeout="4": r.run([r.bash, str(r.package / ".uak/bin/lib/smoke-init.sh"), "boot", "--timeout", timeout,
                                               "--", cmd], cwd=t, env={"UAK_PORT": str(port)}, allowed=None, timeout=90)
        hang = boot('"%s" -c "import time; time.sleep(60)"' % py)
        expect(hang.returncode != 0 and "BOOT_PASS" not in hang.stdout and "already answers" in hang.stdout,
               "an app that never answers fails even with a server on UAK_PORT: rc %d %s %s" % (hang.returncode, hang.stdout, hang.stderr))
        good = boot('"%s" -m http.server $PORT --bind 127.0.0.1' % py, timeout="20")
        m = re.search(r"BOOT_PASS: / answered \d+ on port (\d+)", good.stdout)
        expect(good.returncode == 0 and m and int(m.group(1)) != port, "a real app boots on another port: " + good.stdout + good.stderr)
    finally:
        stale.kill()
        stale.wait(timeout=10)
    # The wait is bounded by default (60 s) and by UAK_SMOKE_BOOT_TIMEOUT; usage names both.
    usage = r.run([r.bash, str(r.package / ".uak/bin/lib/smoke-init.sh"), "boot"], cwd=t, allowed=None)
    expect("UAK_SMOKE_BOOT_TIMEOUT" in usage.stderr and "60" in usage.stderr, "usage: " + usage.stderr)
    began = time.monotonic()
    env_bound = r.run([r.bash, str(r.package / ".uak/bin/lib/smoke-init.sh"), "boot", "--", '"%s" -c "import time; time.sleep(60)"' % py],
                      cwd=t, env={"UAK_SMOKE_BOOT_TIMEOUT": "3"}, allowed=None, timeout=90)
    expect(env_bound.returncode != 0 and time.monotonic() - began < 30 and "within 3s" in env_bound.stderr,
           "UAK_SMOKE_BOOT_TIMEOUT bounds the wait: " + env_bound.stderr)
    return "occupied port skipped; timeout bounded"


def init_smoke_leaves_no_stray_dirs(r):
    t, env, git, start, uak = installed(r, "onb-stray", "sprint")
    before = set(p.name for p in t.iterdir())
    made = uak("init-smoke", "--command", "true")
    expect(made.returncode == 0 and "SMOKE_ADAPTER_CREATED" in made.stdout, made.stdout + made.stderr)
    after = set(p.name for p in t.iterdir())
    expect(after == before and not (t / "scripts").exists(), "no new top-level folder: %r" % sorted(after - before))
    status = r.run([r.git, "-c", "core.quotePath=false", "status", "--porcelain", "--untracked-files=all"], cwd=t).stdout
    changed = sorted(l[3:].strip() for l in status.splitlines() if l.strip())
    expect(changed == [".uak/bin/.smoke-project.provenance", ".uak/bin/smoke-project"], "only the adapter and its provenance: %r" % changed)
    # With no --command and no detected app: a clear error naming the generic command, nothing written.
    (t / ".uak/bin/smoke-project").unlink(); (t / ".uak/bin/.smoke-project.provenance").unlink()
    none = uak("init-smoke")
    expect(none.returncode != 0 and "--command" in none.stderr and not (t / ".uak/bin/smoke-project").exists()
           and not (t / "scripts").exists(), "no app: says how, writes nothing: " + none.stdout + none.stderr)
    return "no stray folder"


TESTS = [start_asks_for_the_smoke, start_notes_the_smoke_before_any_app, web_smoke_boots_the_app, occupied_port_never_answers_for_the_app, init_smoke_leaves_no_stray_dirs]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    clean_env()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-smoke-onb-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ not in args.case:
                continue
            started = time.monotonic()
            try:
                note = test(runner)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started))
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("SMOKE_ONBOARDING_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
