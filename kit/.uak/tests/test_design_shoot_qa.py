#!/usr/bin/env python3
"""UAK-069: the built-in capture serves the round over http (canvas reads and fetches fail on file://), launches Chromium
with software WebGL, shoots 1920x1080 besides 1280 and 390 about 3 s after load, and writes a QA report per viewport
(WebGL, page errors, overflow, content width share, upscaled rasters); `design shoot` prints the warnings and exits
non-zero on page errors; `design pick` shows the 1920 shot first with the warnings under each variant.
A fake `playwright` package drives the capture script; when UAK_TEST_NODE_PLAYWRIGHT names a folder holding Node's
playwright, the QA probe also runs in a real Chromium against a narrow page and a stretched image."""
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
import json, os, urllib.error, urllib.request
from contextlib import contextmanager
from pathlib import Path
LOG = os.environ["FAKE_PW_LOG"]
def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(list(a)) + "\\n")
class Page:
    def __init__(self, w): self.w = w; self.h = {}
    def on(self, ev, fn): self.h[ev] = fn
    def goto(self, url, **kw):
        with urllib.request.urlopen(url, timeout=10) as r:  # what a canvas read or fetch needs: a real http origin
            log("goto", self.w, url, r.status, r.read().decode("utf-8", "replace")[:200])
        if os.environ.get("FAKE_RANGE") and self.w == 1280:  # what Chromium does before it seeks a video
            rq = urllib.request.Request(url.rsplit("/", 1)[0] + "/" + os.environ["FAKE_RANGE"], headers={"Range": "bytes=100000-100999"})
            with urllib.request.urlopen(rq, timeout=10) as r:
                log("range", r.status, r.headers.get("Content-Range"), r.headers.get("Content-Length"), r.headers.get("Accept-Ranges"), len(r.read()))
            try:
                rq = urllib.request.Request(url.rsplit("/", 1)[0] + "/" + os.environ["FAKE_RANGE"], headers={"Range": "bytes=999999999-"})
                urllib.request.urlopen(rq, timeout=10)
                log("range-past-end", 200)
            except urllib.error.HTTPError as exc:
                log("range-past-end", exc.code, exc.headers.get("Content-Range"))
        for e in json.loads(os.environ.get("FAKE_ERRORS", "[]")):
            self.h["pageerror"](Exception(e))
    def wait_for_load_state(self, s): pass
    def wait_for_timeout(self, ms): log("wait", self.w, ms)
    def evaluate(self, js):
        if "innerWidth" in js:
            qa = {"w": self.w, "gl": True, "overflow": False, "share": 92, "upscaled": [], "frameMs": 17, "fps": 59}
            qa.update(json.loads(os.environ.get("FAKE_QA", "{}")).get(str(self.w), {}))
            log("qa", self.w)
            return qa
        log("media", self.w)
    def screenshot(self, path, full_page=False):
        log("screenshot", self.w, Path(path).name)
        Path(path).write_bytes(bytes.fromhex("89504e47"))
    def close(self): pass
class Browser:
    def new_page(self, viewport, **kw):
        log("new_page", viewport["width"], kw.get("device_scale_factor", 1))
        return Page(viewport["width"])
    def close(self): pass
class Chromium:
    def launch(self, **kw):
        log("launch", kw.get("args", []))
        return Browser()
class P: chromium = Chromium()
@contextmanager
def sync_playwright():
    yield P()
'''


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = Path(package) / ".uak"  # the candidate under test (smoke passes --package)
        sys.path.insert(0, str(self.pkg / "bin" / "lib"))
        fake = self.tmp / "fake-site" / "playwright"
        fake.mkdir(parents=True)
        (fake / "__init__.py").write_text("", encoding="utf-8")
        (fake / "sync_api.py").write_text(FAKE, encoding="utf-8")
        self.site = self.tmp / "fake-site"
        self.log = self.tmp / "pw.log"
        self.base = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester", UAK_NO_COLOR="1", UAK_HUMAN="", UAK_TASTE_HOME=str(self.tmp / "taste"))
        for k in ("SSH_CONNECTION", "SSH_TTY", "UAK_DESIGN_SHOOT"):
            self.base.pop(k, None)
        self.n = 0

    def project(self, n=1):
        self.n += 1
        d = self.tmp / ("p%d" % self.n)
        for i in range(1, n + 1):
            v = d / ".uak/design/rounds/R1" / ("v%d" % i)
            v.mkdir(parents=True)
            (v / "genome.json").write_text(json.dumps({"id": "R1-v%d" % i, "variant": i, "genes": GENES, "recipe": "landing-story"}), encoding="utf-8")
            (v / "index.html").write_text("<!doctype html><title>live v%d</title>" % i, encoding="utf-8")
        return d

    def design(self, cwd, *args, env=None, ok=(0,)):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design")] + list(args), cwd=str(cwd), env=dict(self.base, **(env or {})),
                             capture_output=True, text=True, timeout=180)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out

    def shoot(self, d, qa=None, errors=None, ok=(0,), env_extra=None):
        self.log.write_text("", encoding="utf-8")
        env = {"PYTHONPATH": str(self.site), "FAKE_PW_LOG": str(self.log), "FAKE_QA": json.dumps(qa or {}), "FAKE_ERRORS": json.dumps(errors or [])}
        env.update(env_extra or {})
        return self.design(d, "shoot", "R1", env=env, ok=ok)

    def calls(self):
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines() if l.strip()]


def serves_over_http_so_canvas_reads_work(e):
    d = e.project()
    e.shoot(d)
    calls = e.calls()
    gotos = [c for c in calls if c[0] == "goto"]
    expect(len(gotos) == 3 and all(re.match(r"^http://127\.0\.0\.1:\d+/v1/index\.html$", c[2]) for c in gotos), "served over http: %s" % [c[2] for c in gotos])
    expect(all(c[3] == 200 and "live v1" in c[4] for c in gotos), "and it answers with the page: %s" % gotos[0])
    launch = [c for c in calls if c[0] == "launch"][0][1]
    expect("--use-angle=swiftshader" in launch and "--enable-unsafe-swiftshader" in launch, "software WebGL: %s" % launch)
    return "http origin, swiftshader flags"


def writes_1920_shot(e):
    d = e.project()
    out = e.shoot(d)
    v = d / ".uak/design/rounds/R1/v1"
    for f in ("1920.png", "1920-full.png", "1280.png", "1280-full.png", "390.png", "390-full.png", "qa.json"):
        expect((v / f).is_file(), "%s written" % f)
    calls = e.calls()
    order = [(c[0], c[1]) for c in calls if c[0] in ("goto", "wait", "screenshot") and c[1] == 1920]
    expect(order[0] == ("goto", 1920) and order[1] == ("wait", 1920), "waits after load: %s" % order)
    waited = [c[2] for c in calls if c[0] == "wait" and c[1] == 1920]
    expect(max(waited) >= 3000, "about 3 s after load so animations are mid-cycle: %s" % waited)
    shots = [c[2] for c in calls if c[0] == "screenshot"]
    expect(shots[:2] == ["1920.png", "1920-full.png"], "the projector first: %s" % shots)
    qa = json.loads((v / "qa.json").read_text(encoding="utf-8"))
    expect(set(qa) == {"1920", "1280", "390"} and qa["1920"]["gl"] is True and qa["1920"]["errors"] == 0, "qa.json: %s" % qa)
    return "1920 first, 3 s wait"


def flags_narrow_page(e):
    d = e.project()
    out = e.shoot(d, qa={"1920": {"share": 41}, "1280": {"share": 60}, "390": {"share": 50}})
    expect("DESIGN_SHOOT QA v1 1920: narrow page, empty gutters" in out.stdout and "41%" in out.stdout, "1920 warns: " + out.stdout)
    expect("1280: narrow" not in out.stdout and "390: narrow" not in out.stdout, "below 1440 it does not")
    ok = e.project()
    quiet = e.shoot(ok, qa={"1920": {"share": 80}})
    expect("narrow page" not in quiet.stdout, "80% is fine: " + quiet.stdout)
    import design_round as dr
    expect(dr.qa_warnings({"1440": {"w": 1440, "share": 74}}) and not dr.qa_warnings({"1440": {"w": 1440, "share": 75}}), "the line is 75% at 1440")
    real = _real_probe(e, "<h1 style='width:600px;margin:0 auto'>Narrow column</h1><p style='width:600px;margin:0 auto'>text</p>", 1920)
    if real is not None:
        expect(real["share"] is not None and real["share"] < 75, "a 600 px column at 1920 is narrow in a real Chromium: %s" % real)
    return "warns under 75%% at 1920/1440%s" % ("" if real is None else " (real Chromium too)")


def flags_upscaled_raster(e):
    d = e.project()
    up = [{"file": "car.png", "natural": 400, "drawn": 1200}]
    out = e.shoot(d, qa={"1280": {"upscaled": up}})
    expect("DESIGN_SHOOT QA v1 1280: upscaled raster: car.png, 400 -> 1200 px" in out.stdout, "named, natural to drawn: " + out.stdout)
    real = _real_probe(e, "<img src='%s' style='width:900px'>" % ("data:image/png;base64," + "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="), 1280)
    if real is not None:
        expect(real["upscaled"] and real["upscaled"][0]["drawn"] == 900 and real["upscaled"][0]["natural"] == 1, "a 1 px image drawn at 900 px: %s" % real)
    return "upscaled raster reported%s" % ("" if real is None else " (real Chromium too)")


def range_requests_get_206(e):
    d = e.project()
    clip = d / ".uak/design/rounds/R1/v1/clip.mp4"
    clip.write_bytes(bytes(range(256)) * 1600)  # 400 KB: bigger than one socket buffer, like a real loop
    e.shoot(d, env_extra={"FAKE_RANGE": "clip.mp4"})
    got = {c[0]: c for c in e.calls() if c[0] in ("range", "range-past-end")}
    expect(got["range"][1:] == [206, "bytes 100000-100999/409600", "1000", "bytes", 1000], "206 with Content-Range: %s" % got["range"])
    expect(got["range-past-end"][1:] == [416, "bytes */409600"], "a range past the end is 416: %s" % got["range-past-end"])
    return "206 Partial Content, Accept-Ranges: bytes, 416 past the end"


def phone_shot_is_sharp(e):
    d = e.project()
    e.shoot(d)
    pages = {c[1]: c[2] for c in e.calls() if c[0] == "new_page"}
    expect(pages == {1920: 1, 1280: 1, 390: 2}, "the 390 shot is taken at device scale factor 2: %s" % pages)
    return "390 at DPR 2"


def page_errors_fail_the_shoot(e):
    d = e.project(n=2)
    out = e.shoot(d, errors=["ReferenceError: THREE is not defined"], ok=(1,))
    expect("page errors: 1 (first: ReferenceError: THREE is not defined)" in out.stdout, "the first error is shown: " + out.stdout)
    expect("page errors in: v1 v2" in out.stderr, "and the variants are listed: " + out.stderr)
    expect((d / ".uak/design/rounds/R1/v1/1920.png").is_file(), "the PNGs are still there to look at")
    return "rc 1, listed"


def pick_page_shows_qa_and_1920(e):
    d = e.project(n=2)
    e.shoot(d, qa={"1920": {"share": 40}, "1280": {"upscaled": [{"file": "car.png", "natural": 400, "drawn": 1200}]}})
    (d / ".uak/design/rounds/R1/v2/qa.json").unlink(missing_ok=True)
    (d / ".uak/design/rounds/R1/v2/1920.png").unlink(missing_ok=True)
    (d / ".uak/design/rounds/R1/v2/1920-full.png").unlink(missing_ok=True)
    out = subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--no-open"], cwd=str(d), env=e.base,
                         capture_output=True, text=True, timeout=90)
    m = re.search(r"http://127\.0\.0\.1:(\d+)/", out.stdout)
    expect(out.returncode == 0 and m, "start: " + out.stdout + out.stderr)
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/pick.html" % m.group(1), timeout=10) as r:
            page = r.read().decode("utf-8")
        card1, card2 = page.split('data-id="v1"')[1].split('data-id="v2"')[0], page.split('data-id="v2"')[1]
        expect('<img src="v1/1920.png"' in card1 and 'data-full="v1/1920-full.png"' in card1, "1920 is the main picture of v1")
        expect('<img src="v2/1280.png"' in card2, "a variant without a 1920 shot falls back to 1280")
        expect("narrow page, empty gutters" in card1 and "upscaled raster: car.png" in card1 and 'class="qa"' in card1, "the warnings sit under the variant")
        expect('class="qa"' not in card2, "none for the variant without a report")
        expect('href="v1/index.html"' in card1, "and the live page is linked")
    finally:
        subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--stop"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=60)
    return "1920 first, QA under each variant"


def _real_probe(e, body, width):
    """QA_JS in a real Chromium (Node playwright from UAK_TEST_NODE_PLAYWRIGHT), or None when there is none."""
    folder, node = os.environ.get("UAK_TEST_NODE_PLAYWRIGHT"), shutil.which("node")
    if not folder or not node or not (Path(folder) / "playwright").is_dir():
        return None
    import design_round as dr
    harness = """
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({viewport: {width: %d, height: 800}});
  await p.setContent(%s); const q = await p.evaluate(%s); console.log(JSON.stringify(q)); await b.close();
})().catch(e => { console.error(String(e)); process.exit(1); });
""" % (json.dumps(str(Path(folder) / "playwright")), width, json.dumps("<body style='margin:0'>" + body + "</body>"), dr.QA_JS)
    r = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=120)
    expect(r.returncode == 0, "real probe: " + r.stderr[-400:])
    return json.loads(r.stdout.strip().splitlines()[-1])


TESTS = [serves_over_http_so_canvas_reads_work, range_requests_get_206, phone_shot_is_sharp, writes_1920_shot, flags_narrow_page, flags_upscaled_raster, page_errors_fail_the_shoot,
         pick_page_shows_qa_and_1920]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-shoot-qa-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_SHOOT_QA_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
