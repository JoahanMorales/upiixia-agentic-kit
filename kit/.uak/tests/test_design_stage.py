#!/usr/bin/env python3
"""UAK-068: the `stage` gene (how the hero moves on a projector) and the desktop-first rules in every TASK.md and in
landing-story. Why (AXIA R1-R2, 2026-11-11): every variant sat in a 600-900 px column; resized rasters looked stretched;
the human wants a stand-by hero that turns heads, with three.js when it fits, and called glows and haze "AI slop"."""
import argparse
import sys
import tempfile
import time
from pathlib import Path

from test_hack import expect


class Env:
    def __init__(self, package):
        self.package = Path(package)
        sys.path.insert(0, str(self.package / ".uak" / "bin" / "lib"))
        import design_round
        self.dr = design_round

    def task(self, genes=None):
        g = {"genes": {k: v[0] for k, v in self.dr.GENES.items()}, "recipe": "landing-story"}
        g["genes"].update(genes or {})
        return self.dr.task_text("R1", 1, g, "landing")


def stage_gene_drawn_with_still_at_most_once(e):
    dr = e.dr
    expect(len(dr.GENES["stage"]) == 7 and dr.STILL in dr.GENES["stage"], "seven stage values incl. still")
    t0 = time.monotonic()
    for seed in range(1, 16):
        for n in (8, 20):
            gs = dr.make_genomes(n, seed)
            expect(len(gs) == n, "n=%d seed=%d gave %d" % (n, seed, len(gs)))
            expect(sum(1 for g in gs if g["genes"]["stage"] == dr.STILL) <= 1, "still drawn once at most (seed %d n %d)" % (seed, n))
            expect(all(dr.shared_genes(a, b) <= dr.MAX_SHARED for i, a in enumerate(gs) for b in gs[:i]), "<= 3 shared")
            expect(len({g["genes"]["stage"] for g in gs}) >= min(n, 7) - 1, "values spread")
    expect(time.monotonic() - t0 < 60, "rounds of 20 come quickly: %.1fs" % (time.monotonic() - t0))
    w = {"stage": {dr.STILL: 1.0}}  # taste that loves still: still stays at most once
    gs = dr.make_genomes(12, 3, weights=w, wild=2)
    expect(sum(1 for g in gs if g["genes"]["stage"] == dr.STILL) <= 1, "taste cannot repeat still")
    return "ok"


def task_states_desktop_first_bounds(e):
    t = e.task()
    for needle in ("1440 and 1920", "full-bleed", "at least 1200 px at 1440", "wide empty gutters", "then 390"):
        expect(needle in t, "TASK.md lacks %r" % needle)
    return "ok"


def task_states_standby_loop(e):
    t = e.task({"stage": "canvas 2D generative"})
    for needle in ("stand-by loop for a projector", "NO interaction", "10-15 s", "stranger", "wow", "Reduced motion", "canvas 2D generative"):
        expect(needle in t, "TASK.md lacks %r" % needle)
    return "ok"


def task_forbids_upscaled_rasters(e):
    t = e.task()
    expect("Never show a raster upscaled" in t and "native size" in t and "live SVG/HTML from its real numbers" in t, "raster rule")
    return "ok"


def three_rules_pinned_cdn(e):
    t = e.task()
    for needle in ("three@0.170.0/build/three.module.js", "import map", "devicePixelRatio at most 2", "pause rendering when the tab is hidden",
                   "WebGL is missing", "no branded 3D models", "no network fetches but that CDN and fonts", "AI slop", "glows, neon blurs".capitalize()):
        expect(needle in t, "TASK.md lacks %r" % needle)
    return "ok"


def landing_story_has_the_same_rules(e):
    s = (e.package / ".uak" / "skills" / "landing-story" / "SKILL.md").read_text(encoding="utf-8")
    for needle in ("1440 and 1920", "full-bleed", "1200 px at 1440", "stand-by loop for a projector", "10-15 s", "upscaled",
                   "three@0.170.0", "DPR at most 2", "AI slop"):
        expect(needle in s, "landing-story lacks %r" % needle)
    return "ok"


TESTS = [stage_gene_drawn_with_still_at_most_once, task_states_desktop_first_bounds, task_states_standby_loop, task_forbids_upscaled_rasters,
         three_rules_pinned_cdn, landing_story_has_the_same_rules]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-stage-"):
        e = Env(args.package.resolve())
        tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_STAGE_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
