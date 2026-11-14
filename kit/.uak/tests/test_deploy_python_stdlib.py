#!/usr/bin/env python3
"""UAK-095: a plain Python web app (http.server, no framework, no pyproject) got "DEPLOY: no known stack here" from
`uak deploy`, the planner had already promised a Dockerfile, and the agent hand-wrote one that copied a web/ folder
the repo did not have (QA round C, finding 5). deploy now recognises a stdlib server (`python3 -m <pkg>.server` or a
server.py), writes a Dockerfile whose CMD really serves the app on $PORT and a Render Blueprint; when nothing
matches, the message says what to add. The test runs the Dockerfile's CMD on the build context to prove it works."""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

SERVER = '''import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from %(pkg)squeue import size


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            body = json.dumps({"ok": True, "queue": size()}).encode()
            self.send_response(200)
        else:
            body = b"{}"
            self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    port = int(os.environ.get("PORT") or os.environ.get("UAK_PORT") or 8000)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
'''


def deploy(r, t, *args):
    return r.run([r.bash, str(r.package / ".uak/bin/deploy"), *args], cwd=t, allowed=None)


def repo(r, name):
    t = r.scratch / name
    t.mkdir(parents=True)
    r.g(t, "init", "-q", "-b", "main")
    return t


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def cmd_of(dockerfile):
    m = re.search(r"^CMD (\[.*\])\s*$", dockerfile, re.M)
    expect(m, "the Dockerfile has an exec-form CMD: " + dockerfile)
    return json.loads(m.group(1))


def serves(t, argv):
    """Run the image's CMD where the image runs it (WORKDIR = the build context, COPY . .) and ask /api/health."""
    expect(argv[0] in ("python3", "python"), "the CMD starts Python: %s" % argv)
    port = free_port()
    env = dict(os.environ, PORT=str(port), PYTHONDONTWRITEBYTECODE="1")
    env.pop("UAK_PORT", None)
    proc = subprocess.Popen([sys.executable] + argv[1:], cwd=str(t), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=2) as resp:
                    return resp.status, json.loads(resp.read().decode())
            except OSError:
                time.sleep(0.2)
        out, err = proc.communicate(timeout=5) if proc.poll() is not None else (b"", b"")
        raise AssertionError("the CMD %s never served $PORT %d: %s %s" % (argv, port, out[-400:], err[-800:]))
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def deploy_recognises_stdlib_python(r):
    # The QA round C app: app/server.py run as `python3 -m app.server`, app/queue.py beside it, no web/, no pyproject.
    t = repo(r, "stdlib-module")
    (t / "app").mkdir()
    (t / "app/server.py").write_text(SERVER % {"pkg": "app."}, encoding="utf-8")
    (t / "app/queue.py").write_text("def size():\n    return 0\n", encoding="utf-8")
    (t / "tests").mkdir()
    (t / "tests/test_queue.py").write_text("from http.server import HTTPServer\n\nif __name__ == '__main__':\n    pass\n", encoding="utf-8")
    (t / ".env.example").write_text("ADMIN_PIN=\nPORT=8000\n", encoding="utf-8")
    plan = deploy(r, t)
    expect(plan.returncode == 0 and "DEPLOY python-stdlib" in plan.stdout and "python3 -m app.server" in plan.stdout
           and "health /api/health" in plan.stdout and not (t / "Dockerfile").exists(),
           "a stdlib server is a known stack, nothing written yet: rc %d %s %s" % (plan.returncode, plan.stdout, plan.stderr))
    wrote = deploy(r, t, "--write")
    expect(wrote.returncode == 0, "writes: " + wrote.stdout + wrote.stderr)
    dockerfile = (t / "Dockerfile").read_text(encoding="utf-8")
    blueprint = (t / "render.yaml").read_text(encoding="utf-8")
    expect("FROM python:3" in dockerfile and "COPY . ." in dockerfile and "COPY web/" not in dockerfile
           and "pip install" not in dockerfile and "uv sync" not in dockerfile,
           "plain Python: copy the repo, install nothing it does not need: " + dockerfile)
    expect(cmd_of(dockerfile) == ["python3", "-m", "app.server"], "runs the module: " + dockerfile)
    expect("runtime: docker" in blueprint and "healthCheckPath: /api/health" in blueprint
           and "key: ADMIN_PIN\n        sync: false" in blueprint and "key: PORT" not in blueprint, "the Blueprint: " + blueprint)
    expect(".git" in (t / ".dockerignore").read_text(encoding="utf-8").split(), "a .dockerignore")
    status, body = serves(t, cmd_of(dockerfile))
    expect(status == 200 and body.get("ok") is True, "the image's CMD serves the app: %s %s" % (status, body))

    # A root server.py with requirements.txt; it listens on localhost and ignores $PORT: deploy says what to change.
    s = repo(r, "stdlib-script")
    (s / "server.py").write_text(
        "from http.server import HTTPServer, SimpleHTTPRequestHandler\n\n"
        "if __name__ == '__main__':\n    HTTPServer(('127.0.0.1', 5000), SimpleHTTPRequestHandler).serve_forever()\n",
        encoding="utf-8")
    (s / "requirements.txt").write_text("requests==2.32.3\n", encoding="utf-8")
    plan = deploy(r, s, "--write")
    dockerfile = (s / "Dockerfile").read_text(encoding="utf-8")
    expect(plan.returncode == 0 and "DEPLOY python-stdlib" in plan.stdout, "server.py is recognised: " + plan.stdout + plan.stderr)
    expect(cmd_of(dockerfile) == ["python3", "server.py"]
           and "pip install --no-cache-dir -r requirements.txt" in dockerfile, "runs the script, installs requirements: " + dockerfile)
    expect("$PORT" in plan.stdout and "0.0.0.0" in plan.stdout and "to do" in plan.stdout,
           "a server that ignores $PORT gets a to-do: " + plan.stdout)
    return "module and script recognised; the CMD serves /api/health"


def deploy_says_what_is_missing(r):
    e = repo(r, "missing-empty")
    out = deploy(r, e)
    text = out.stdout + out.stderr
    expect(out.returncode == 1 and "no known stack" in text, "no guess: rc %d %s" % (out.returncode, text))
    for needle in ("add", "pyproject.toml", "package.json", "go.mod", "server.py", "$PORT"):
        expect(needle in text, "the message names what to add (%s): %s" % (needle, text))
    expect(not (e / "Dockerfile").exists(), "nothing written")

    # Python files but no web server: say that this is the missing piece, not a generic list.
    p = repo(r, "missing-python")
    (p / "lib").mkdir()
    (p / "lib/util.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    out = deploy(r, p, "--write")
    text = out.stdout + out.stderr
    expect(out.returncode == 1 and "Python" in text and "server.py" in text and "http.server" in text
           and "$PORT" in text, "Python without a server: the message says what is missing: " + text)
    expect(not (p / "Dockerfile").exists() and not (p / "render.yaml").exists(), "nothing written")
    return "the message says what to add"


TESTS = [deploy_recognises_stdlib_python, deploy_says_what_is_missing]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-deploy-stdlib-") as tmp:
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
    print("DEPLOY_PYTHON_STDLIB_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
