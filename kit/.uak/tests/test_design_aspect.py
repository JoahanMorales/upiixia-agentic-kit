#!/usr/bin/env python3
"""UAK-081: the capture's QA flags `distorted image: file, natural WxH -> drawn WxH` when an <img>, <video>, <canvas> or a CSS
background sized on both axes is drawn more than 8% off its natural aspect ratio and nothing preserves it (object-fit cover,
contain, none, scale-down). TASK.md and landing-story say images keep their ratio. Why (AXIA R1, found by the UAK-073 review): the
human called the images "stretched and ugly"; loop.png (900x620) was drawn at 532x620 and resultados-60.png (900x520) at
612x520 with object-fit: fill, and no check caught it. Real Chromium with UAK_TEST_NODE_PLAYWRIGHT; a fake capture otherwise."""
import argparse
import base64
import json
import os
import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

from test_design_perf import Env
from test_hack import expect, resolve_binary


def png(w, h):
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


URI = "data:image/png;base64," + base64.b64encode(png(90, 62)).decode()  # a 900x620 file in miniature: ratio 1.45


def probe(body, width=1280, height=720):
    folder, node = os.environ.get("UAK_TEST_NODE_PLAYWRIGHT"), shutil.which("node")
    if not folder or not node or not (Path(folder) / "playwright").is_dir():
        return None
    import design_round as dr
    harness = """
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({viewport: {width: %d, height: %d}});
  await p.setContent(%s); await p.waitForTimeout(300); const q = await p.evaluate(%s); console.log(JSON.stringify(q)); await b.close();
})().catch(e => { console.error(String(e)); process.exit(1); });
""" % (json.dumps(str(Path(folder) / "playwright")), width, height, json.dumps("<body style='margin:0'>" + body + "</body>"), dr.QA_JS)
    r = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=180)
    expect(r.returncode == 0, "real probe: " + r.stderr[-400:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def squashed_img_flagged(e):
    real = probe('<img src="%s" style="width:53px;height:62px;object-fit:fill"><img src="%s" style="width:61px;height:52px">' % (URI, URI))
    if real is not None:
        d = {x["file"]: x for x in real["distorted"]}
        expect(len(real["distorted"]) == 2 and all(x["kind"] == "img" and x["nw"] == 90 and x["nh"] == 62 for x in real["distorted"]), "both squashed images: %s" % real["distorted"])
        expect((real["distorted"][0]["dw"], real["distorted"][0]["dh"]) == (53, 62), real["distorted"])
    # the message, through the capture script (a fake Playwright answers with the probe's shape)
    d, stages = e.project()
    out = e.shoot(d, qa={"1920": {"distorted": [{"file": "loop.png", "nw": 900, "nh": 620, "dw": 532, "dh": 620, "kind": "img"}]}})
    v = stages["SVG/CSS animation"]
    expect("DESIGN_SHOOT QA %s 1920: distorted image: loop.png, natural 900×620 → drawn 532×620 (img)" % v in out.stdout, out.stdout)
    return "flagged" + (" (real Chromium)" if real else " (fake capture)")


def cover_and_contain_not_flagged(e):
    real = probe("".join('<img src="%s" style="width:53px;height:62px;object-fit:%s">' % (URI, fit) for fit in ("cover", "contain", "none", "scale-down"))
                 + '<img src="%s" style="width:90px;height:62px"><img src="%s" style="width:96px;height:62px">' % (URI, URI))
    if real is None:
        return "no real Chromium: UAK_TEST_NODE_PLAYWRIGHT unset"
    expect(real["distorted"] == [], "cover/contain/none/scale-down, the natural ratio and 4%% off are fine: %s" % real["distorted"])
    return "four fits and two near ratios pass"


def stretched_background_flagged(e):
    real = probe('<div style="width:200px;height:200px;background:url(%s) 0 0/100%% 100%%"></div>'
                 '<div style="width:200px;height:200px;background:url(%s) center/cover"></div>'
                 '<div style="width:200px;height:200px;background:url(%s) center/contain no-repeat"></div>'
                 '<div style="width:200px;height:200px;background:url(%s) 0 0/100%% auto"></div>' % (URI, URI, URI, URI))
    if real is None:
        return "no real Chromium: UAK_TEST_NODE_PLAYWRIGHT unset"
    bad = real["distorted"]
    expect(len(bad) == 1 and bad[0]["kind"] == "background" and (bad[0]["dw"], bad[0]["dh"]) == (200, 200), "only 100%% 100%% is stretched: %s" % bad)
    return "100% 100% flagged; cover, contain and 100% auto not"


def rule_in_task_and_skill(e):
    d, stages = e.project()
    for v in stages.values():
        t = e.task(d, v)
        expect("Raster images keep their aspect ratio: `object-fit: cover` (crop) or `contain` (fit), never `fill`" in t and "distorted image" in t, "TASK.md of %s" % v)
    s = (e.pkg / "skills" / "landing-story" / "SKILL.md").read_text(encoding="utf-8")
    expect("Raster images keep their aspect ratio" in s and "never `fill`" in s and "distorted image" in s, "landing-story")
    return "task and skill"


TESTS = [squashed_img_flagged, cover_and_contain_not_flagged, stretched_background_flagged, rule_in_task_and_skill]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-aspect-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_ASPECT_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
