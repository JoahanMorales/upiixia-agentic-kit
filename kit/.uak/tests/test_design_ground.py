#!/usr/bin/env python3
"""UAK-072: every genome has a `ground` (light or dark) derived from its color gene; a round of 4 or more keeps at least a
third of each, in drawn, taste-seeded and bred rounds; a flipped child says so in "because". Why (AXIA R1-R3): dark won 4
of 5 picks and breeding drifted every later round to dark; the human: "the dark ones gained too much ground over the white ones"."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect


class Env:
    def __init__(self, tmp, package):
        self.tmp = Path(tmp)
        self.lib = Path(package) / ".uak" / "bin" / "lib"
        sys.path.insert(0, str(self.lib))
        import design_round
        self.dr = design_round


def count(gs):
    return sum(1 for g in gs if g["ground"] == "light"), sum(1 for g in gs if g["ground"] == "dark")


def ground_derived_from_color(e):
    dr = e.dr
    expect(dr.ground_of({"color": "dark media"}) == "dark" and dr.ground_of({"color": "light paper"}) == "light", "fixed colors")
    for c in ("ink + one accent", "brand duo", "saturated field"):
        expect(dr.ground_of({"color": c}) is None, c + " is drawn")
    for seed in range(1, 8):
        for g in dr.make_genomes(8, seed):
            expect(g["ground"] in ("light", "dark"), "every genome has a ground")
            fixed = dr.ground_of(g["genes"])
            expect(fixed is None or fixed == g["ground"], "a fixed color decides: %s %s" % (g["genes"]["color"], g["ground"]))
    task = dr.task_text("R1", 1, dict(dr.make_genomes(4, 1)[0]), "landing")
    expect("- ground: **" in task, task)
    return "ok"


def round_has_third_light_and_dark(e):
    dr = e.dr
    for n in (4, 5, 6, 8, 12, 20):
        k = -(-n // 3)
        for seed in range(1, 25):
            gs = dr.make_genomes(n, seed)
            light, dark = count(gs)
            expect(light >= k and dark >= k, "n=%d seed=%d: %d light %d dark" % (n, seed, light, dark))
            expect(all(dr.shared_genes(a, b) <= dr.MAX_SHARED for i, a in enumerate(gs) for b in gs[:i]), "diversity kept after flips")
    return "ok"


def taste_cannot_make_all_dark(e):
    dr = e.dr
    w = {"color": {"dark media": 1.0, "light paper": 0.0, "ink + one accent": 0.0, "brand duo": 0.0, "saturated field": 0.0}}
    flips = 0
    for seed in range(1, 15):
        gs = dr.make_genomes(9, seed, weights=w, wild=1)
        light, dark = count(gs)
        expect(light >= 3 and dark >= 3, "seed %d taste for dark: %d light %d dark" % (seed, light, dark))
        flips += sum(1 for g in gs if "flipped" in g["why"]["color"])
    expect(flips > 0, "taste drifted dark and had to be flipped at least once")
    return "%d flips" % flips


def bred_round_flips_to_keep_balance(e):
    dr = e.dr
    d = e.tmp / "bred"
    r1 = d / ".uak/design/rounds/R1"
    base = dr.make_genomes(6, 2)
    for i, g in enumerate(base, 1):
        genes = dict(g["genes"])
        if i <= 3:
            genes["color"] = "dark media"  # three dark picks: the AXIA drift
        (r1 / ("v%d" % i)).mkdir(parents=True)
        (r1 / ("v%d" % i) / "genome.json").write_text(json.dumps({"id": "R1-v%d" % i, "genes": genes, "recipe": g["recipe"], "ground": "dark" if i <= 3 else None}), encoding="utf-8")
    (r1 / "picks.json").write_text(json.dumps({"picked": ["v1", "v2", "v3"], "notes": {}}), encoding="utf-8")
    flipped = 0
    for seed in range(1, 11):
        r = subprocess.run([sys.executable, str(e.lib / "design_breed.py"), "--from", "R1", "--n", "9", "--seed", str(seed), "--yes"], cwd=str(d), capture_output=True, text=True)
        expect(r.returncode == 0, r.stdout + r.stderr)
        rnd = d / (".uak/design/rounds/R%d" % (seed + 1))
        kids = [json.loads((v / "genome.json").read_text(encoding="utf-8")) for v in sorted(rnd.glob("v*"))]
        light, dark_n = count(kids)
        expect(light >= 3 and dark_n >= 3, "seed %d: %d light %d dark" % (seed, light, dark_n))
        for k in kids:
            fixed = dr.ground_of(k["genes"])
            expect(fixed is None or fixed == k["ground"], "ground follows color")
            if "ground flipped" in k.get("because", ""):
                flipped += 1
                expect(k["genes"]["color"] in ("light paper", "dark media"), "flipped to a fixed color")
                if k["kind"] == "mutation":
                    expect(k["mutated"] == "color", "a flipped mutation changed only its color")
    expect(flipped > 0, "dark parents had to be flipped at least once")
    return "%d flipped" % flipped


TESTS = [ground_derived_from_color, round_has_third_light_and_dark, bred_round_flips_to_keep_balance, taste_cannot_make_all_dark]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-ground-") as tmp:
        e = Env(tmp, args.package.resolve())
        tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_GROUND_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
