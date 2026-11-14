#!/usr/bin/env python3
"""UAK-080: picks that share most of their genes (AXIA R3: v5 and v3, 8 of 9) no longer stop the round: their children are
one line (they only must not be identical), the round adds wildcards (at least a third, each unlike every pick in 4+
genes), every relaxation is in "because", ground balance and distinct wildcard fonts still hold, and the human sees why.
Fixture: the real AXIA R3 genomes of v3 and v5 and its picks.json (copied, never read from the user's folder)."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect

G = {"type": "serif display", "scale": "standard", "color": "dark media", "layout": "full-bleed media", "components": "glass",
     "imagery": "illustration", "motion": "entrance", "voice": "numbers first"}
R3 = {  # genome.json of the real R3 variants the human picked: the same eight genes; only the (then separate) stage differed
    "v3": {"id": "R3-v3", "round": "R3", "variant": 3, "screen": "landing", "genes": G, "stage": "three.js · 3D car + HUD",
           "recipe": "motionsites", "from": ["R2/v1"], "kind": "mutation"},
    "v5": {"id": "R3-v5", "round": "R3", "variant": 5, "screen": "landing", "genes": G, "stage": "three.js · scroll-driven",
           "recipe": "motionsites", "from": ["R2/v4", "R2/v1"], "kind": "crossover"},
}
PICKS = {"picked": ["v5", "v3"], "notes": {}, "by": "joahan", "at": "2026-11-11T22:52:57Z"}


class Env:
    def __init__(self, tmp, package):
        self.tmp = Path(tmp)
        self.lib = Path(package) / ".uak" / "bin" / "lib"
        sys.path.insert(0, str(self.lib))
        import design_round
        self.dr = design_round

    def project(self, name):
        d = self.tmp / name
        r3 = d / ".uak/design/rounds/R3"
        for v, g in R3.items():
            (r3 / v).mkdir(parents=True)
            (r3 / v / "genome.json").write_text(json.dumps(g), encoding="utf-8")
        (r3 / "picks.json").write_text(json.dumps(PICKS), encoding="utf-8")
        return d

    def breed(self, d, n, seed, *extra):
        r = subprocess.run([sys.executable, str(self.lib / "design_breed.py"), "--from", "R3", "--n", str(n), "--seed", str(seed)] + list(extra),
                           cwd=str(d), capture_output=True, text=True)
        expect(r.returncode == 0, "n=%d seed=%d rc %d: %s" % (n, seed, r.returncode, (r.stdout + r.stderr)[-600:]))
        return r

    def kids(self, d, k=1):
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((d / (".uak/design/rounds/R%d" % k)).glob("v*/genome.json"))]


def shared(a, b):
    return sum(1 for k in a if a[k] == b[k])


def twins_still_breed(e):
    for n in (4, 6, 9, 12):
        for seed in (1, 2, 3, 4, 5):
            d = e.project("t%d-%d" % (n, seed))
            e.breed(d, n, seed, "--yes")
            ks = e.kids(d)
            expect(len(ks) == n, "n=%d seed=%d: %d children" % (n, seed, len(ks)))
            gs = [k["genes"] for k in ks]
            expect(all(shared(a, b) < len(a) for i, a in enumerate(gs) for b in gs[:i]), "no two children identical")
    return "ok"


def twins_round_has_explorers(e):
    dr = e.dr
    full = [dict(G, stage="SVG/CSS animation"), dict(G, stage="canvas 2D generative")]  # as the picks are read: 8 of 9 shared
    for n in (6, 9):
        for seed in (1, 2, 3):
            d = e.project("x%d-%d" % (n, seed))
            e.breed(d, n, seed, "--yes")
            ks = e.kids(d)
            need = -(-n // 3)
            far = [k for k in ks if all(sum(1 for g in dr.GENES if k["genes"].get(g) != p.get(g)) >= 4 for p in full)]
            expect(len(far) >= need, "n=%d seed=%d: %d explorers, need %d" % (n, seed, len(far), need))
            expect(sum(1 for k in ks if k["kind"] == "wildcard") >= need, "wildcards")
    return "explorers"


def ground_and_fonts_hold_for_twins(e):
    for seed in (1, 2, 3, 4):
        d = e.project("g%d" % seed)
        e.breed(d, 9, seed, "--yes")
        ks = e.kids(d)
        light = sum(1 for k in ks if k.get("ground") == "light")
        dark = sum(1 for k in ks if k.get("ground") == "dark")
        expect(light >= 3 and dark >= 3, "seed %d: %d light %d dark" % (seed, light, dark))
        wild = [k for k in ks if k["kind"] == "wildcard"]
        expect(len({k["fonts"]["display"] for k in wild}) == len(wild) and len({k["fonts"]["body"] for k in wild}) == len(wild), "wildcards keep distinct fonts")
        expect(all(k.get("fonts", {}).get("url") for k in ks), "every child has a pair")
    return "ok"


def because_explains_twins(e):
    d = e.project("why")
    out = e.breed(d, 6, 2, "--yes").stdout
    expect("picks nearly identical (8/9 genes): exploring with 2 wildcards" in out, out)
    for k in e.kids(d):
        expect("picks nearly identical (8/9 genes)" in k.get("because", ""), "because on %s: %s" % (k["id"], k.get("because")))
    dry = e.breed(e.project("why2"), 6, 2, "--dry-run").stdout
    expect("picks nearly identical (8/9 genes)" in dry, "the dry run says it too: " + dry)
    return "explained"


TESTS = [twins_still_breed, twins_round_has_explorers, ground_and_fonts_hold_for_twins, because_explains_twins]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-twins-") as tmp:
        e = Env(tmp, args.package.resolve())
        tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_BREED_TWINS_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
