#!/usr/bin/env python3
"""UAK-071: every variant of a round gets an exact Google Fonts pair. Pools of at least 6 pairs per type value, none with
Inter/Roboto/Arial/Geist as display; no two variants of a round share a display or body face; a bred child keeps its
parent's pair unless `type` mutated; the faces of the human's past directions are not reused in a new project's round
(--allow-repeat lifts it); design-lint warns when a page loads another pair than the one assigned.
Why (AXIA R3, 2026-11-11): all six variants used Fraunces + Geist; the human: "they need more variety"."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect, resolve_binary


class Env:
    def __init__(self, tmp, package):
        self.tmp = Path(tmp)
        self.package = Path(package)
        self.lib = self.package / ".uak" / "bin" / "lib"
        sys.path.insert(0, str(self.lib))
        import design_fonts
        import design_round
        self.df, self.dr = design_fonts, design_round


def pools_have_six_pairs(e):
    df, dr = e.df, e.dr
    expect(set(df.POOLS) == set(dr.GENES["type"]), "a pool per type value")
    for t, pool in df.POOLS.items():
        expect(len(pool) >= 6, "%s has %d pairs" % (t, len(pool)))
        for d, dw, b, bw in pool:
            expect(d.lower() not in df.NEVER_DISPLAY, "%s is no display face" % d)
            expect(dw and bw, "weights for " + d)
    expect(len({p[0] for p in df.all_pairs()}) == len(df.all_pairs()), "displays are unique across pools")
    expect("Syne" not in {p[0] for p in df.all_pairs()}, "Syne stays out")
    expect(df.url(df.POOLS["condensed"][0]).startswith("https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@800&family=Work+Sans:wght@400;600"), df.url(df.POOLS["condensed"][0]))
    return "%d pairs" % len(df.all_pairs())


def round_pairs_all_distinct(e):
    dr = e.dr
    for n in (6, 12, 20):
        for seed in (1, 2, 3, 9):
            gs = dr.make_genomes(n, seed)
            ds = [g["fonts"]["display"] for g in gs]
            bs = [g["fonts"]["body"] for g in gs]
            expect(len(set(ds)) == n and len(set(bs)) == n, "n=%d seed=%d repeats a face: %s / %s" % (n, seed, ds, bs))
            for g in gs:
                expect(g["fonts"]["display"] in [p[0] for p in e.df.POOLS[g["genes"]["type"]]] or n > 12, "pair from the type's pool (n=%d)" % n)
    task = dr.task_text("R1", 1, dr.make_genomes(6, 1)[0], "landing")
    g0 = dr.make_genomes(6, 1)[0]
    expect(g0["fonts"]["url"] in task and g0["fonts"]["display"] in task and "never a display face" in task, task)
    return "distinct up to 20"


def child_keeps_parent_pair(e):
    d = e.tmp / "breed"
    r1 = d / ".uak/design/rounds/R1"
    gs = e.dr.make_genomes(6, 4)
    for i, g in enumerate(gs, 1):
        (r1 / ("v%d" % i)).mkdir(parents=True)
        (r1 / ("v%d" % i) / "genome.json").write_text(json.dumps({"id": "R1-v%d" % i, "genes": g["genes"], "recipe": g["recipe"], "fonts": g["fonts"]}), encoding="utf-8")
    (r1 / "picks.json").write_text(json.dumps({"picked": ["v1", "v2"], "notes": {}}), encoding="utf-8")
    seen = {"kept": 0, "type": 0}
    for seed in range(1, 15):
        r = subprocess.run([sys.executable, str(e.lib / "design_breed.py"), "--from", "R1", "--n", "8", "--seed", str(seed), "--yes"], cwd=str(d), capture_output=True, text=True)
        expect(r.returncode == 0, r.stdout + r.stderr)
        rnd = d / (".uak/design/rounds/R%d" % (seed + 1))
        for v in sorted(rnd.glob("v*")):
            c = json.loads((v / "genome.json").read_text(encoding="utf-8"))
            expect(c.get("fonts", {}).get("url"), "every child has a pair: " + v.name)
            expect(c["fonts"]["display"] in (v / "TASK.md").read_text(encoding="utf-8"), "TASK.md names it")
            if c["kind"] == "mutation":
                par = gs[int(c["from"][0].split("/v")[1]) - 1]
                if c["mutated"] != "type":
                    expect(c["fonts"] == par["fonts"], "%s keeps its parent's pair" % v.name)
                    seen["kept"] += 1
                else:
                    expect(c["fonts"]["display"] != par["fonts"]["display"] and c["fonts"]["display"] in [p[0] for p in e.df.POOLS[c["genes"]["type"]]], "type mutated: a new pair of the new type")
                    seen["type"] += 1
    expect(seen["kept"] > 3 and seen["type"] > 0, "children kept pairs: %s" % seen)
    # an old parent without fonts still breeds
    for v in (r1).glob("v*"):
        doc = json.loads((v / "genome.json").read_text(encoding="utf-8"))
        doc.pop("fonts")
        (v / "genome.json").write_text(json.dumps(doc), encoding="utf-8")
    r = subprocess.run([sys.executable, str(e.lib / "design_breed.py"), "--from", "R1", "--n", "6", "--seed", "9", "--yes"], cwd=str(d), capture_output=True, text=True)
    expect(r.returncode == 0, "old parents: " + r.stdout + r.stderr)
    return seen


def past_direction_fonts_not_reused(e):
    dr, df = e.dr, e.df
    base = dr.make_genomes(8, 5)
    past = {base[0]["fonts"]["display"], base[0]["fonts"]["body"], base[1]["fonts"]["display"]}
    got = dr.make_genomes(8, 5, avoid_faces=past)
    used = {x for g in got for x in (g["fonts"]["display"], g["fonts"]["body"])}
    expect(not ({p.lower() for p in past} & {u.lower() for u in used}), "past faces reused: %s" % (past & used))
    # through the profile: a direction of another project with `fonts` is avoided in round 1, --allow-repeat lifts it
    home = e.tmp / "taste"
    home.mkdir()
    (home / "ana.json").write_text(json.dumps({"human": "ana", "rounds": {}, "directions": {"old": {
        "project": "old", "genes": {}, "fonts": {"display": base[0]["fonts"]["display"], "body": base[0]["fonts"]["body"]}}}}), encoding="utf-8")
    os.environ["UAK_TASTE_HOME"] = str(home)
    try:
        import design_taste  # noqa: F401
        root = Path(e.tmp / "newproj")
        root.mkdir(exist_ok=True)
        faces = dr._past_faces("ana", "newproj", root, False)
        expect({base[0]["fonts"]["display"].lower()} <= faces, "profile faces read: %s" % faces)
        expect(dr._past_faces("ana", "newproj", root, True) == set(), "--allow-repeat lifts it")
        expect(dr._past_faces("ana", "old", root, False) == set(), "the project's own direction is not avoided")
    finally:
        os.environ.pop("UAK_TASTE_HOME", None)
    html = '<link href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@800&amp;family=Work+Sans:wght@400;600&amp;display=swap" rel="stylesheet">'
    expect(df.parse_url_families(html) == ["Big Shoulders Display", "Work Sans"], "reads the page link: %s" % df.parse_url_families(html))
    return "avoided"


def lint_flags_wrong_pair(e):
    d = e.tmp / "lint" / ".uak/design/rounds/R1"
    pairs = e.df.assign(["condensed", "serif display"], 3)
    for i, (p, loaded) in enumerate(zip(pairs, (None, ("Fraunces", "Geist"))), 1):
        v = d / ("v%d" % i)
        v.mkdir(parents=True)
        (v / "genome.json").write_text(json.dumps({"genes": {}, "fonts": p}), encoding="utf-8")
        link = p["url"] if loaded is None else "https://fonts.googleapis.com/css2?family=Fraunces:wght@700&family=Geist&display=swap"
        (v / "index.html").write_text('<!doctype html><html><head><link rel="stylesheet" href="%s"><style>:root{--ink:#111}h1{font-size:40px}</style></head><body><h1>x</h1></body></html>\n' % link, encoding="utf-8")
    root = d.parents[3]
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(root), check=True)
    out = subprocess.run([resolve_binary("bash"), str(e.package / ".uak/bin/design-lint"), ".uak/design/rounds/R1"], cwd=str(root), capture_output=True, text=True)
    warns = [l for l in out.stdout.splitlines() if l.startswith("DESIGN_LINT_WARN")]
    expect(out.returncode == 0 and len(warns) == 1 and "v2/index.html" in warns[0].replace("\\", "/") and "loads Fraunces + Geist" in warns[0] and pairs[1]["display"] in warns[0], out.stdout + out.stderr)
    expect(not any("v1/index.html" in w for w in warns), "the right pair is silent")
    return "v2 flagged"


TESTS = [pools_have_six_pairs, round_pairs_all_distinct, child_keeps_parent_pair, past_direction_fonts_not_reused, lint_flags_wrong_pair]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-fonts-") as tmp:
        e = Env(tmp, args.package.resolve())
        tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_FONTS_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
