#!/usr/bin/env python3
"""UAK-086: `design shoot` no longer loses a variant to a 30 s screenshot timeout after the QA pass. Why (colonIA R3, 2026-11-15):
R3/v4 never got a 390.png in 5 runs (`Page.screenshot: Timeout 30000ms exceeded`): after MEDIA_JS + QA_JS the full page took 35 s;
alone it took 3.4 s. Six variants shooting at once (load average ~17) also starved each other. No real browser here: the generated
capture script runs against a stub of Playwright's sync API that logs every call."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from test_design_breed_rules import Env
from test_hack import expect, resolve_binary

FAKE = '''import json, os
from pathlib import Path
LOG = Path(os.environ["FAKE_LOG"])
def log(*a):
    with open(str(LOG), "a", encoding="utf-8") as f:
        f.write(json.dumps(a) + "\\n")
class Page:
    def __init__(self, vp): self.vp = vp
    def on(self, *a): pass
    def goto(self, *a, **k): pass
    def wait_for_timeout(self, ms): pass
    def close(self): pass
    def evaluate(self, script, arg=None):
        if "scrollHeight" in script:
            return int(os.environ.get("FAKE_HEIGHT", "800"))
        kind = "MEDIA" if "v.currentTime = v.duration" in script else "MASS" if arg else "QA"
        log("evaluate", kind)
        if kind == "QA":
            return {"gl": True, "sig": {"head": [0, 0, 1, 1]}, "textRects": []}
        return {} if kind == "MASS" else 0
    def screenshot(self, path=None, timeout=30000, full_page=False):
        label = Path(path).stem
        log("screenshot", label, timeout)
        if label in os.environ.get("FAKE_TIMEOUT", "").split(","):
            raise Exception("Page.screenshot: Timeout %dms exceeded" % timeout)
        Path(path).write_bytes(b"png")
class Browser:
    def new_page(self, viewport=None, device_scale_factor=1): return Page(viewport)
    def close(self): pass
class Chromium:
    def launch(self, args=None): return Browser()
class PW:
    chromium = Chromium()
class sync_playwright:
    def __enter__(self): return PW()
    def __exit__(self, *a): return False
'''


def run_script(e, tmp, height=800, timeout=""):
    sys.path.insert(0, str(e.lib))
    import design_round
    stubs = tmp / "pw stub é"
    (stubs / "playwright").mkdir(parents=True, exist_ok=True)
    (stubs / "playwright" / "__init__.py").write_text("", encoding="utf-8")
    (stubs / "playwright" / "sync_api.py").write_text(FAKE, encoding="utf-8")
    d = e.project()
    v = d / ".uak/design/rounds/R1/v1"
    v.mkdir(parents=True)
    (v / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    log = tmp / ("calls%d.jsonl" % e.n)
    env = dict(os.environ, PYTHONPATH=str(stubs), FAKE_LOG=str(log), FAKE_HEIGHT=str(height), FAKE_TIMEOUT=timeout)
    r = subprocess.run([sys.executable, "-c", design_round._PLAYWRIGHT, str(v / "index.html"), str(v)], env=env, capture_output=True, text=True, timeout=120)
    calls = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
    return r, calls, v


def screenshots_before_qa(e):
    r, calls, v = run_script(e, e.tmp)
    expect(r.returncode == 0, r.stdout + r.stderr)
    seq = [c[1] for c in calls if c[0] == "screenshot" or c[:2] == ["evaluate", "QA"]]
    want = []
    for vp in ("1920", "1280", "390"):
        want += [vp, vp + "-full", "QA"]
    expect(seq == want, "each viewport's screenshots precede its QA: %s" % seq)
    expect(json.loads((v / "qa.json").read_text(encoding="utf-8")).get("1920", {}).get("sig"), "qa.json still carries the signature")
    return "screenshots first, QA after"


def timeout_scales_with_height(e):
    def full(height):
        r, calls, _ = run_script(e, e.tmp, height=height)
        expect(r.returncode == 0, r.stderr)
        return {c[1]: c[2] for c in calls if c[0] == "screenshot"}
    short, tall = full(800), full(40000)
    expect(all(short[k] >= 90000 for k in short if k.endswith("-full")), "at least 90 s for a full page: %s" % short)
    expect(tall["390-full"] > short["390-full"] and tall["390-full"] >= 90000 * 2, "grows with the page: %s vs %s" % (short, tall))
    expect(all(short[k] > 30000 for k in short), "never the 30 s default: %s" % short)
    return "90 s floor, grows with height"


def timeout_names_viewport_keeps_others(e):
    r, calls, v = run_script(e, e.tmp, height=12620, timeout="390-full")
    expect(r.returncode == 0, r.stdout + r.stderr)
    expect("SHOOT_TIMEOUT 390-full timed out after" in r.stdout and "pause loops off screen" in r.stdout, r.stdout)
    for n in ("1920.png", "1280.png", "390.png", "1920-full.png", "1280-full.png", "qa.json"):
        expect((v / n).is_file(), "%s kept" % n)
    expect(not (v / "390-full.png").exists(), "the timed-out shot is absent")
    qa = json.loads((v / "qa.json").read_text(encoding="utf-8"))
    expect(all(k in qa for k in ("1920", "1280", "390")) and "390-full" in " ".join(qa.get("timeouts", [])), str(qa))
    # a viewport shot that times out fails the variant, and the shoot's message names it and what was kept
    r2, _, v2 = run_script(e, e.tmp, timeout="390")
    expect("SHOOT_TIMEOUT 390 timed out" in r2.stdout and (v2 / "1280.png").is_file() and (v2 / "qa.json").is_file(), r2.stdout)
    return "named, others kept"


def shoot(e, d, *args, env=None):
    return subprocess.Popen([e.bash, str(e.pkg / "bin" / "design"), "shoot", "R1", *args], cwd=str(d), env=dict(e.base, **env),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def parallel_shoots_serialized(e):
    stub = e.tmp / "slow shoot é.py"
    stub.write_text('''import os, sys, time
from pathlib import Path
v = Path(sys.argv[2])
with open(os.environ["TRACE"], "a") as f: f.write("start %s %f\\n" % (v.name, time.time()))
time.sleep(1.5)
Path(v, "1280.png").write_text("png"); Path(v, "390.png").write_text("png")
with open(os.environ["TRACE"], "a") as f: f.write("end %s %f\\n" % (v.name, time.time()))
''', encoding="utf-8")
    d = e.project()
    e.design(d, "round", "--n", "2", "--seed", "1", "--yes")
    for v in (d / ".uak/design/rounds/R1").glob("v[0-9]*"):
        (v / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    trace = e.tmp / "trace.txt"
    trace.write_text("", encoding="utf-8")
    env = {"UAK_DESIGN_SHOOT": str(stub), "TRACE": str(trace)}
    procs = [shoot(e, d, "v1", env=env), shoot(e, d, "v2", env=env)]
    outs = [p.communicate(timeout=120) for p in procs]
    expect(all(p.returncode == 0 for p in procs), str(outs))
    rows = [l.split() for l in trace.read_text(encoding="utf-8").splitlines()]
    t = {(k, n): float(x) for k, n, x in rows}
    a, b = sorted(("v1", "v2"), key=lambda n: t[("start", n)])
    expect(t[("end", a)] <= t[("start", b)], "the second shoot starts after the first ends: %s" % rows)
    expect(any("waiting for another shoot" in o[1] for o in outs), "the waiting one says so: %s" % [o[1] for o in outs])
    expect(not (d / ".uak/design/rounds/R1/.shoot.lock").exists(), "the lock is released")
    # a dead shoot's lock is broken once stale
    lock = d / ".uak/design/rounds/R1/.shoot.lock"
    lock.write_text("999999\n", encoding="utf-8")
    old = time.time() - 3600
    os.utime(str(lock), (old, old))
    for v in ("v1", "v2"):
        for n in ("1280.png", "390.png"):
            (d / ".uak/design/rounds/R1" / v / n).unlink()
    p = shoot(e, d, "v1", env=dict(env, UAK_SHOOT_LOCK_STALE="60"))
    p.communicate(timeout=60)
    expect(p.returncode == 0 and not lock.exists(), "a stale lock is taken over")
    return "serialized, stale lock broken"


TESTS = [screenshots_before_qa, timeout_scales_with_height, timeout_names_viewport_keeps_others, parallel_shoots_serialized]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-shoot-timeout-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_SHOOT_TIMEOUT_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
