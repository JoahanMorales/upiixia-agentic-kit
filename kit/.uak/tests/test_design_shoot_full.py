#!/usr/bin/env python3
"""UAK-067: the built-in Playwright capture waits for media (every <video> is paused and seeked to 30% of its length before
a shot, so a capture never shows an empty first frame) and writes 1280-full.png and 390-full.png beside the fold shots;
the pick page shows the fold by default, the full page on a toggle, and links each variant's live index.html served by the
same server. No real browser: a fake `playwright` package records what the capture script does, and when node exists the
media function itself runs against a fake <video>."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from test_hack import expect, resolve_binary

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000" "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
GENES = {"type": "grotesk", "scale": "bold", "color": "dark media", "layout": "split hero", "components": "glass",
         "imagery": "video loop", "motion": "entrance", "voice": "plain"}

FAKE = '''
import json, os
from contextlib import contextmanager
from pathlib import Path
LOG = os.environ["FAKE_PW_LOG"]
def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(list(a)) + "\\n")
class Page:
    def __init__(self, w): self.w = w; self.h = {}
    def on(self, ev, fn): self.h[ev] = fn
    def goto(self, url, **kw): log("goto", self.w)
    def wait_for_load_state(self, s): pass
    def wait_for_timeout(self, ms): pass
    def evaluate(self, js):
        if "innerWidth" in js: return {"w": self.w, "gl": True, "overflow": False, "share": 90, "upscaled": [], "fps": 60}  # the QA probe
        log("evaluate", self.w, js)
    def screenshot(self, path, full_page=False):
        log("screenshot", self.w, Path(path).name, full_page)
        Path(path).write_bytes(bytes.fromhex("89504e47"))
    def close(self): pass
class Browser:
    def new_page(self, viewport, **kw): return Page(viewport["width"])
    def close(self): pass
class Chromium:
    def launch(self, **kw): return Browser()
class P: chromium = Chromium()
@contextmanager
def sync_playwright():
    yield P()
'''


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = Path(package) / ".uak"  # the candidate under test (smoke passes --package)
        self.lib = self.pkg / "bin" / "lib"
        sys.path.insert(0, str(self.lib))
        fake = self.tmp / "fake-site" / "playwright"
        fake.mkdir(parents=True)
        (fake / "__init__.py").write_text("", encoding="utf-8")
        (fake / "sync_api.py").write_text(FAKE, encoding="utf-8")
        self.site = self.tmp / "fake-site"
        self.log = self.tmp / "pw.log"
        self.home = self.tmp / "taste"
        self.base = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester", UAK_NO_COLOR="1", UAK_TASTE_HOME=str(self.home), UAK_HUMAN="")
        for k in ("SSH_CONNECTION", "SSH_TTY", "UAK_DESIGN_SHOOT"):
            self.base.pop(k, None)

    def project(self, name, n=2, captures=False, index=True):
        d = self.tmp / name
        rnd = d / ".uak/design/rounds/R1"
        for i in range(1, n + 1):
            v = rnd / ("v%d" % i)
            v.mkdir(parents=True)
            (v / "genome.json").write_text(json.dumps({"id": "R1-v%d" % i, "variant": i, "genes": GENES, "recipe": "landing-story"}), encoding="utf-8")
            if index:
                (v / "index.html").write_text("<!doctype html><title>live v%d</title><video src=a.mp4 autoplay loop></video>" % i, encoding="utf-8")
            if captures:
                for f in ("1280.png", "390.png", "1280-full.png", "390-full.png"):
                    (v / f).write_bytes(PNG)
        return d

    def design(self, cwd, *args, env=None, ok=(0,)):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design")] + list(args), cwd=str(cwd),
                             env=dict(self.base, **(env or {})), capture_output=True, text=True, timeout=120)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out

    def shoot_fake(self, d):
        self.log.write_text("", encoding="utf-8")
        return self.design(d, "shoot", "R1", env={"PYTHONPATH": str(self.site), "FAKE_PW_LOG": str(self.log)})

    def calls(self):
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines() if l.strip()]


def video_is_not_captured_blank(e):
    import design_round as dr
    d = e.project("vid", n=1)
    e.shoot_fake(d)
    calls = e.calls()
    for w in (1920, 1280, 390):
        seq = [c[0] + (":" + c[2] if c[0] == "screenshot" else "") for c in calls if c[1] == w]
        # media is handled before the fold shot and again before the full-page shot
        want = ["goto", "evaluate", "screenshot:%d.png" % w, "evaluate", "screenshot:%d-full.png" % w]
        expect(seq == want, "%d: %s" % (w, seq))
    js = [c[2] for c in calls if c[0] == "evaluate"]
    expect(all(j == dr.MEDIA_JS for j in js), "the script that ran is MEDIA_JS")
    for needle in ("querySelectorAll('video')", "currentTime = v.duration * 0.3", "'seeked'", "pause()"):
        expect(needle in dr.MEDIA_JS, "MEDIA_JS lacks %r" % needle)
    node = shutil.which("node")
    if not node:
        return "order verified (node absent: the media function itself was not run)"
    harness = """
const fn = eval('(' + %s + ')');
let seeked = [], paused = 0;
const mk = (dur, rs) => { const L = {}; return { duration: dur, readyState: rs, preload: 'auto', _t: 0, muted: false,
  addEventListener(ev, f) { L[ev] = f; }, removeAttribute() {}, pause() { paused++; }, load() {},
  set currentTime(t) { this._t = t; seeked.push(t); setTimeout(() => L.seeked && L.seeked(), 5); }, get currentTime() { return this._t; } }; };
const vids = [mk(10, 4), mk(NaN, 0)];
global.document = { querySelectorAll: (q) => q === 'video' ? vids : [] };
fn().then(n => console.log(JSON.stringify({ n, seeked, paused })));
""" % json.dumps(dr.MEDIA_JS)
    r = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=60)
    expect(r.returncode == 0, "node: " + r.stderr[-400:])
    got = json.loads(r.stdout.strip().splitlines()[-1])
    expect(got["n"] == 2 and got["seeked"] == [3.0] and got["paused"] >= 2, "a 10 s video seeks to 3 s, one without duration keeps its poster: %s" % got)
    return "seeks to 30%, before both shots"


def full_page_captures_written(e):
    d = e.project("full", n=2)
    out = e.shoot_fake(d)
    for v in ("v1", "v2"):
        for f in ("1280.png", "390.png", "1280-full.png", "390-full.png"):
            expect((d / ".uak/design/rounds/R1" / v / f).is_file(), "%s/%s written" % (v, f))
    shots = [c for c in e.calls() if c[0] == "screenshot"]
    expect(all(c[3] == (c[2].endswith("-full.png")) for c in shots), "only the -full files are full_page: %s" % shots)
    expect("captured v1 v2" in out.stdout, out.stdout)
    # a variant that already has its fold shots is left alone (the stub tools of other tests write only two PNGs)
    again = e.shoot_fake(d)
    expect("captured none; already had 2" in again.stdout and not e.calls(), "second run captures nothing: " + again.stdout)
    return "4 PNGs per variant"


def pick_page_links_live_variant(e):
    d = e.project("pick", n=2, captures=True)
    (d / ".uak/design/rounds/R1/v2/index.html").unlink()
    (d / ".uak/design/rounds/R1/v2/1280-full.png").unlink()
    out = subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--no-open"], cwd=str(d), env=e.base,
                         capture_output=True, text=True, timeout=90)
    m = re.search(r"http://127\.0\.0\.1:(\d+)/", out.stdout)
    expect(out.returncode == 0 and m, "start: " + out.stdout + out.stderr)
    port = int(m.group(1))
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/pick.html" % port, timeout=10) as r:
            page = r.read().decode("utf-8")
        expect('src="v1/1280.png"' in page and 'data-fold="v1/1280.png"' in page and 'data-full="v1/1280-full.png"' in page,
               "the fold is the default, the full capture is one toggle away")
        expect('data-full="v2/1280.png"' in page, "no full capture: the toggle falls back to the fold")
        expect('data-full="v1/390-full.png"' in page, "phone shot too")
        expect('id="full"' in page and "Full page" in page, "the toggle")
        expect('href="v1/index.html"' in page and 'href="v2/index.html"' not in page, "a link to each variant that has a live page")
        with urllib.request.urlopen("http://127.0.0.1:%d/v1/index.html" % port, timeout=10) as r:
            expect(r.status == 200 and "live v1" in r.read().decode("utf-8"), "the same server serves it")
        with urllib.request.urlopen("http://127.0.0.1:%d/v1/1280-full.png" % port, timeout=10) as r:
            expect(r.read() == PNG, "and the full-page capture")
    finally:
        subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--stop"], cwd=str(d), env=e.base,
                       capture_output=True, text=True, timeout=60)
    return "fold by default, full on toggle, live link"


TESTS = [video_is_not_captured_blank, full_page_captures_written, pick_page_links_live_variant]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-shoot-full-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_SHOOT_FULL_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
