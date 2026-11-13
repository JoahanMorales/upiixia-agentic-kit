#!/usr/bin/env python3
"""UAK-073: TASK.md states the animation budget (three.js: low-power, DPR <= 1.5, <= ~40k points / ~10k instances, render only
while visible, hero <= 30 fps, drop detail when slow; SVG/canvas/CSS: transform and opacity, not layout); the capture's
frame-time probe (3 s of requestAnimationFrame, long tasks, JS heap) goes into qa.json and metrics.json, and a frame over
`Design-Frame-Budget-Ms` (default 50 WebGL / 20 the rest) is flagged heavy; the pick page shows frame time and heavy. The
upscaled-raster check also covers CSS background-image, <video> and canvas backing stores. A fake `playwright` drives the
capture script; with UAK_TEST_NODE_PLAYWRIGHT (a folder holding Node's playwright) the probe also runs in a real Chromium."""
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

FAKE = '''
import json, os
from contextlib import contextmanager
from pathlib import Path
class Page:
    def __init__(self, w): self.w = w
    def on(self, ev, fn): pass
    def goto(self, url, **kw): pass
    def wait_for_load_state(self, s): pass
    def wait_for_timeout(self, ms): pass
    def evaluate(self, js):
        if "innerWidth" in js:
            qa = {"w": self.w, "gl": True, "overflow": False, "share": 92, "upscaled": [], "frameMs": 17, "fps": 59, "longTasks": 0, "heapMB": 12}
            qa.update(json.loads(os.environ.get("FAKE_QA", "{}")).get(str(self.w), {}))
            return qa
    def screenshot(self, path, full_page=False): Path(path).write_bytes(bytes.fromhex("89504e47"))
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
PX = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


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
        self.base = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester", UAK_NO_COLOR="1", UAK_HUMAN="ana", UAK_TASTE_HOME=str(self.tmp / "taste"))
        for k in ("SSH_CONNECTION", "SSH_TTY", "UAK_DESIGN_SHOOT"):
            self.base.pop(k, None)
        self.n = 0

    def project(self, project_md=""):
        """A round of 8 variants (every stage value once) with a page each; returns (dir, {stage: variant})."""
        self.n += 1
        d = self.tmp / ("p%d" % self.n)
        (d / ".uak").mkdir(parents=True)
        (d / "IDEA.md").write_text("# IDEA · X\n\n## 1. One line\nFor **a**, X helps.\n", encoding="utf-8")
        if project_md:
            (d / ".uak/PROJECT.md").write_text(project_md, encoding="utf-8")
        self.design(d, "round", "--n", "8", "--seed", "3", "--yes")
        stages = {}
        for v in sorted((d / ".uak/design/rounds/R1").glob("v*")):
            g = json.loads((v / "genome.json").read_text(encoding="utf-8"))
            stages.setdefault(g["genes"]["stage"], v.name)
            (v / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
        return d, stages

    def design(self, cwd, *args, env=None, ok=(0,)):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design")] + list(args), cwd=str(cwd), env=dict(self.base, **(env or {})),
                             capture_output=True, text=True, timeout=240)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out

    def shoot(self, d, qa=None):
        return self.design(d, "shoot", "R1", env={"PYTHONPATH": str(self.site), "FAKE_QA": json.dumps(qa or {})})

    def task(self, d, v):
        return (d / ".uak/design/rounds/R1" / v / "TASK.md").read_text(encoding="utf-8")

    def metrics(self, d, v):
        return json.loads((d / ".uak/design/rounds/R1" / v / "metrics.json").read_text(encoding="utf-8"))


def budget_in_task_for_webgl_stage(e):
    d, stages = e.project()
    three = [v for s, v in stages.items() if s.startswith("three.js")]
    expect(three, "the round draws three.js stages: %s" % list(stages))
    t = e.task(d, three[0])
    for needle in ("powerPreference: 'low-power'", "Math.min(devicePixelRatio, 1.5)", "~40k points", "~10k instances", "InstancedMesh", "visibilitychange",
                   "IntersectionObserver", "30 fps", "drop detail", "Design-Frame-Budget-Ms", "default 50 ms for WebGL"):
        expect(needle in t, "three.js TASK.md lacks %r" % needle)
    expect("devicePixelRatio at most 2" in t, "the older rules are still there")
    other = [v for s, v in stages.items() if s.startswith(("SVG", "canvas"))]
    o = e.task(d, other[0])
    expect("`transform` and `opacity` only, never layout" in o and "default 20 ms for the rest" in o and "40k points" not in o, "SVG/canvas stage: the lighter budget, not the three.js one")
    still = stages.get("still (no animation)")
    expect(still and "## Animation budget" not in e.task(d, still), "a still page has no animation budget")
    return "three.js, SVG/canvas and still"


def frame_time_recorded(e):
    import design_round as dr
    for needle in ("now - t0 < 3000", "longtask", "usedJSHeapSize", "requestAnimationFrame"):
        expect(needle in dr.QA_JS, "the probe lacks %r" % needle)
    d, stages = e.project()
    e.shoot(d, qa={"1920": {"frameMs": 22, "fps": 45, "longTasks": 3, "heapMB": 80}, "1280": {"frameMs": 18}, "390": {"frameMs": 16}})
    v = stages["SVG/CSS animation"]
    qa = json.loads((d / ".uak/design/rounds/R1" / v / "qa.json").read_text(encoding="utf-8"))
    expect(qa["1920"]["frameMs"] == 22 and qa["1920"]["longTasks"] == 3 and qa["1920"]["heapMB"] == 80, "qa.json: %s" % qa["1920"])
    perf = e.metrics(d, v)["perf"]
    expect(perf["frame_ms"] == {"1920": 22, "1280": 18, "390": 16} and perf["long_tasks"]["1920"] == 3 and perf["heap_mb"]["1920"] == 80, "metrics.json perf: %s" % perf)
    expect(perf["budget_ms"] == 20 and perf["webgl"] is False, "the default for the rest is 20 ms: %s" % perf)
    node = shutil.which("node")
    folder = os.environ.get("UAK_TEST_NODE_PLAYWRIGHT")
    if node and folder and (Path(folder) / "playwright").is_dir():
        real = _real_probe(e, "<h1>hi</h1>", 1280)
        expect(isinstance(real["frameMs"], int) and real["frameMs"] > 0 and real["longTasks"] >= 0 and "heapMB" in real, "a real Chromium measures 3 s of frames: %s" % real)
        return "qa.json and metrics.json (real Chromium frame %s ms)" % real["frameMs"]
    return "qa.json and metrics.json"


def heavy_flag_over_threshold(e):
    d, stages = e.project()
    three, svg = stages["three.js scene"], stages["SVG/CSS animation"]
    out = e.shoot(d, qa={"1920": {"frameMs": 122, "fps": 8}, "1280": {"frameMs": 30, "fps": 33}})
    expect("DESIGN_SHOOT QA %s 1920: heavy: 122 ms a frame (~8 fps), over the 50 ms budget" % three in out.stdout, "WebGL stage over 50: " + out.stdout)
    expect("DESIGN_SHOOT QA %s 1280: heavy" % three not in out.stdout, "30 ms is within a WebGL budget of 50")
    expect("DESIGN_SHOOT QA %s 1280: heavy: 30 ms a frame (~33 fps), over the 20 ms budget" % svg in out.stdout, "the same 30 ms is heavy for an SVG stage: " + out.stdout)
    expect(e.metrics(d, three)["perf"]["heavy"] is True and e.metrics(d, three)["perf"]["budget_ms"] == 50, "metrics: %s" % e.metrics(d, three)["perf"])
    expect(json.loads((d / ".uak/design/rounds/R1" / three / "qa.json").read_text(encoding="utf-8"))["1920"]["heavy"] is True, "qa.json flags it too")
    quiet = e.shoot(e.project()[0], qa={"1920": {"frameMs": 17}})
    expect("heavy" not in quiet.stdout, "17 ms is fine everywhere: " + quiet.stdout)
    # the project's own budget: one number for every stage, or WebGL/other
    loose, st = e.project("Design-Frame-Budget-Ms: 200\n")
    expect("heavy" not in e.shoot(loose, qa={"1920": {"frameMs": 122}}).stdout, "a budget of 200 ms: 122 is within it")
    both, st = e.project("Design-Frame-Budget-Ms: 130/25\n")
    out = e.shoot(both, qa={"1920": {"frameMs": 122}})
    expect("DESIGN_SHOOT QA %s 1920: heavy" % st["three.js scene"] not in out.stdout and "over the 25 ms budget" in out.stdout, "130 for WebGL, 25 for the rest: " + out.stdout)
    return "122 ms heavy at 50, 30 ms heavy only below 20 ms stages"


def pick_shows_frame_time(e):
    d, stages = e.project()
    three, svg = stages["three.js scene"], stages["SVG/CSS animation"]
    e.shoot(d, qa={"1920": {"frameMs": 122, "fps": 8}, "1280": {"frameMs": 17, "fps": 59}})
    out = subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--no-open"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=90)
    m = re.search(r"http://127\.0\.0\.1:(\d+)/", out.stdout)
    expect(out.returncode == 0 and m, "start: " + out.stdout + out.stderr)
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/pick.html" % m.group(1), timeout=10) as r:
            page = r.read().decode("utf-8")
    finally:
        subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--stop"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=60)
    card = lambda v: page.split('data-id="%s"' % v)[1].split("</article>")[0]
    expect("frame 122 ms (~8 fps)" in card(three) and "HEAVY: over the 50 ms budget" in card(three) and 'class="cost heavy"' in card(three), "three.js: " + card(three)[-700:])
    expect("frame 122 ms" in card(svg) and "HEAVY: over the 20 ms budget" in card(svg), "the slowest viewport counts: " + card(svg)[-500:])
    ok = [v for v in stages.values() if v not in (three, svg)]
    return "frame time and HEAVY under each variant"


def upscaled_covers_background_video_canvas(e):
    import design_round as dr
    for needle in ("backgroundImage", "backgroundSize", "videoWidth", "querySelectorAll('canvas')", "c.width"):
        expect(needle in dr.QA_JS, "the probe lacks %r" % needle)
    w = dr.qa_warnings({"1280": {"w": 1280, "upscaled": [{"file": "hero.jpg", "natural": 400, "drawn": 1280, "kind": "background"},
                                                       {"file": "loop.mp4", "natural": 640, "drawn": 1280, "kind": "video"},
                                                       {"file": "canvas#gl", "natural": 600, "drawn": 1280, "kind": "canvas"}]}})
    text = " | ".join(t for _, t in w)
    expect("upscaled raster (background): hero.jpg, 400 -> 1280 px" in text and "upscaled raster (video): loop.mp4, 640 -> 1280 px" in text
           and "canvas#gl backing store is 600 px, drawn at 1280 px" in text, "messages: " + text)
    real = _real_probe(e, "<div style=\"width:900px;height:300px;background:url(%s) center/cover\"></div><canvas id=gl width=100 height=50 style=\"width:800px;height:400px\"></canvas>"
                       "<div style=\"width:50px;height:50px;background:url(%s)\"></div>" % (PX, PX), 1280)
    if real is None:
        return "messages (no real Chromium: UAK_TEST_NODE_PLAYWRIGHT unset)"
    kinds = {u["kind"]: u for u in real["upscaled"]}
    expect("background" in kinds and kinds["background"]["natural"] == 1 and kinds["background"]["drawn"] >= 900, "a 1 px background covering 900 px: %s" % real["upscaled"])
    expect("canvas" in kinds and kinds["canvas"]["natural"] == 100 and kinds["canvas"]["drawn"] == 800, "a 100 px canvas drawn at 800: %s" % real["upscaled"])
    expect(len([u for u in real["upscaled"] if u["kind"] == "background"]) == 1, "a 1 px background drawn at natural size is not upscaled: %s" % real["upscaled"])
    return "background, video and canvas (real Chromium too)"


def _real_probe(e, body, width):
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
    r = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=180)
    expect(r.returncode == 0, "real probe: " + r.stderr[-400:])
    return json.loads(r.stdout.strip().splitlines()[-1])


TESTS = [budget_in_task_for_webgl_stage, frame_time_recorded, heavy_flag_over_threshold, pick_shows_frame_time, upscaled_covers_background_video_canvas]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-perf-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_PERF_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
