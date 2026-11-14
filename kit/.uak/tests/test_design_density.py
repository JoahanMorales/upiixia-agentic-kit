#!/usr/bin/env python3
"""UAK-077: landings breathe. TASK.md and landing-story state the hero budget (one headline, one sentence, one or two actions,
3 secondary elements, about 45 words at the fold of 1920x1080 and 1280x720; the stage carries the story; no text over its
focal point; later sections one idea each); the capture counts visible text blocks and words at the fold and how many sit over
the stage's canvas/SVG (qa.json, metrics.json), flags `dense` over the budget, and the pick page shows the warning.
Why (colonIA R1, 2026-11-12): "too much information, things pop up everywhere and it looks saturated"; "the pink text doesn't
let you see the background". With UAK_TEST_NODE_PLAYWRIGHT the probe also runs in a real Chromium."""
import argparse
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

import shutil
import sys

from test_design_perf import Env
from test_hack import expect, resolve_binary


def budget_in_task_and_skill(e):
    d, stages = e.project()
    for v in stages.values():
        t = e.task(d, v)
        for needle in ("The hero breathes", "1920x1080 and 1280x720", "one headline, one sentence", "one or two actions", "at most 3 secondary elements",
                       "about 45 words", "the text does not repeat it", "no text block sits over the stage's focal point", "one idea each", "~4 cards or ~80 words", "`dense`"):
            expect(needle in t, "TASK.md of %s lacks %r" % (v, needle))
    s = (e.pkg / "skills" / "landing-story" / "SKILL.md").read_text(encoding="utf-8")
    for needle in ("The hero breathes", "1920x1080 and", "one headline, one sentence", "about 45 words", "focal point", "one idea each", "~4 cards or ~80 words", "flags `dense`"):
        expect(needle in s, "landing-story lacks %r" % needle)
    return "task and skill"


def capture_counts_words_and_elements(e):
    import design_round as dr
    for needle in ("overStage", "overFocal", "words", "texts", "closest('nav"):
        expect(needle in dr.QA_JS, "the probe lacks %r" % needle)
    d, stages = e.project()
    e.shoot(d, qa={"1920": {"texts": 9, "words": 41, "stage": True, "overStage": 2, "overFocal": 0},
                   "1280": {"texts": 9, "words": 41, "stage": True, "overStage": 2, "overFocal": 0}, "390": {"texts": 9, "words": 41}})
    v = stages["SVG/CSS animation"]
    dens = e.metrics(d, v)["density"]
    expect(dens["dense"] is False and dens["budget_words"] == 60 and dens["viewports"]["1920"] == {"words": 41, "texts": 9, "over_stage": 2, "over_focal": 0, "stage": True, "dense": False}, "metrics density: %s" % dens)
    qa = json.loads((d / ".uak/design/rounds/R1" / v / "qa.json").read_text(encoding="utf-8"))
    expect(qa["1920"]["words"] == 41 and qa["1920"]["dense"] is False, "qa.json: %s" % qa["1920"])
    real = _real_probe(e, "<nav><a>Home</a> <a>About us</a></nav><h1>One clear headline here</h1><p>and one short sentence beside it</p><a>Start</a>", 1280)
    if real is None:
        return "fake capture (no real Chromium: UAK_TEST_NODE_PLAYWRIGHT unset)"
    expect(real["words"] == 11 and real["texts"] == 3 and real["stage"] is False, "a real page: the menu is not counted: %s" % {k: real[k] for k in ("words", "texts", "stage")})
    return "metrics.json density (real Chromium: %d words, %d blocks)" % (real["words"], real["texts"])


def dense_flag_over_budget(e):
    d, stages = e.project()
    out = e.shoot(d, qa={"1920": {"texts": 20, "words": 110, "stage": True, "overStage": 20, "overFocal": 0},
                         "1280": {"texts": 8, "words": 60, "stage": True, "overStage": 3, "overFocal": 0},
                         "390": {"texts": 30, "words": 200}})
    svg = stages["SVG/CSS animation"]
    expect("DESIGN_SHOOT QA %s 1920: dense: 110 words in 20 text blocks at the fold, over the budget of 60 words" % svg in out.stdout, "over budget: " + out.stdout)
    expect("%s 1280: dense" % svg not in out.stdout, "60 words is the budget, not over it")
    expect("%s 390: dense" % svg not in out.stdout, "the phone is not judged by the desktop fold")
    m = e.metrics(d, svg)["density"]
    expect(m["dense"] is True and m["viewports"]["1920"]["dense"] is True and m["viewports"]["1280"]["dense"] is False, "metrics: %s" % m)
    # the pick page shows the warning
    e.design(d, "shoot", "R1")  # nothing left to shoot; the report stays
    page = _pick_page(e, d)
    card = page.split('data-id="%s"' % svg)[1].split("</article>")[0]
    expect("dense: 110 words" in card, "the pick page says dense: " + card[-900:])
    quiet = e.shoot(e.project()[0], qa={"1920": {"texts": 7, "words": 40, "stage": True, "overStage": 1, "overFocal": 0}})
    expect("dense" not in quiet.stdout, "40 words is fine: " + quiet.stdout)
    return "110 words dense, 60 not"


def overlap_with_stage_counted(e):
    d, stages = e.project()
    out = e.shoot(d, qa={"1920": {"texts": 6, "words": 30, "stage": True, "overStage": 6, "overFocal": 2}})
    svg = stages["SVG/CSS animation"]
    expect("DESIGN_SHOOT QA %s 1920: text over the stage's focal point: 2 text block(s)" % svg in out.stdout, out.stdout)
    expect(e.metrics(d, svg)["density"]["viewports"]["1920"]["over_stage"] == 6, "over_stage recorded")
    html = ("<body style='margin:0'><svg width='1280' height='720' style='position:absolute;left:0;top:0'><rect width='1280' height='720'/>"
            "<text x='5' y='30'>label inside the stage drawing</text></svg>"
            "<h1 style='position:absolute;left:560px;top:320px;margin:0'>Over the middle</h1>"
            "<p style='position:absolute;left:20px;top:660px;margin:0'>a caption at the corner</p></body>")
    real = _real_probe(e, html, 1280)
    if real is None:
        return "fake capture (no real Chromium: UAK_TEST_NODE_PLAYWRIGHT unset)"
    expect(real["stage"] is True and real["texts"] == 2 and real["words"] == 8, "stage found, its own <text> not counted: %s" % real)
    expect(real["overStage"] == 2 and real["overFocal"] == 1, "both blocks sit over the stage, one over its focal point: %s" % real)
    return "real Chromium: overStage 2, overFocal 1"


def _real_probe(e, body, width, height=720):
    """QA_JS in a real Chromium (Node Playwright from UAK_TEST_NODE_PLAYWRIGHT), or None."""
    folder, node = os.environ.get("UAK_TEST_NODE_PLAYWRIGHT"), shutil.which("node")
    if not folder or not node or not (Path(folder) / "playwright").is_dir():
        return None
    import design_round as dr
    html = body if body.startswith("<body") else "<body style='margin:0'>" + body + "</body>"
    harness = """
const { chromium } = require(%s);
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({viewport: {width: %d, height: %d}});
  await p.setContent(%s); const q = await p.evaluate(%s); console.log(JSON.stringify(q)); await b.close();
})().catch(e => { console.error(String(e)); process.exit(1); });
""" % (json.dumps(str(Path(folder) / "playwright")), width, height, json.dumps(html), dr.QA_JS)
    r = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=180)
    expect(r.returncode == 0, "real probe: " + r.stderr[-400:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def _pick_page(e, d):
    out = subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--no-open"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=90)
    m = re.search(r"http://127\.0\.0\.1:(\d+)/", out.stdout)
    expect(out.returncode == 0 and m, "start: " + out.stdout + out.stderr)
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/pick.html" % m.group(1), timeout=10) as r:
            return r.read().decode("utf-8")
    finally:
        subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--stop"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=60)


TESTS = [budget_in_task_and_skill, capture_counts_words_and_elements, dense_flag_over_budget, overlap_with_stage_counted]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-density-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_DENSITY_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
