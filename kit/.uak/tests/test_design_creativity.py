#!/usr/bin/env python3
"""UAK-084: the creativity index. Every variant has a hero composition and a motif family; siblings differ; a bred child changes
composition at creativity 3+; a praised parent's motif is kept and quoted; the capture records a signature and `design shoot`
flags clones and scores the round. Why (colonIA R2, 2026-11-14): six variants bred from R1 all came out the same (headline left,
hex map right) and lost R1/v1's papel picado, an identity no gene carried."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from test_design_breed_rules import Env
from test_hack import expect, resolve_binary

STUB = """import json, os, sys
from pathlib import Path
v = Path(sys.argv[2])
Path(v, "1280.png").write_text("png")
Path(v, "390.png").write_text("png")
sig = json.loads(os.environ.get("SIGS", "{}")).get(v.name)
if sig:
    Path(v, "qa.json").write_text(json.dumps({"1920": {"w": 1920, "sig": sig}}))
"""
A = {"head": [0.05, 0.3, 0.45, 0.6], "stage": [0.5, 0.0, 1.0, 1.0], "focal": [0.75, 0.5], "lum": 0.05, "hue": 330,
     "mass": {"centroid": [0.75, 0.5], "box": [0.5, 0.0, 1.0, 1.0], "share": 0.3}}
B = {"head": [0.2, 0.3, 0.8, 0.7], "stage": [0.0, 0.0, 1.0, 1.0], "focal": [0.5, 0.5], "lum": 0.9, "hue": 40,
     "mass": {"centroid": [0.5, 0.5], "box": [0.05, 0.05, 0.95, 0.95], "share": 0.5}}
# The six heroes of the real colonIA R2 (1920 fold, measured from its PNGs, 2026-11-14) that the human called "todos son iguales".
R2 = {
    "v1": {"head": [0.03, 0.44, 0.24, 0.75], "stage": [0, 0, 1, 1], "focal": [0.5, 0.5], "mass": {"centroid": [0.71, 0.48], "box": [0.23, 0.32, 0.9, 0.63]}},
    "v2": {"head": [0.05, 0.47, 0.34, 0.68], "stage": [0, 0, 1, 1], "focal": [0.5, 0.5], "mass": {"centroid": [0.7, 0.7], "box": [0.49, 0.51, 0.9, 0.9]}},
    "v3": {"head": [0.07, 0.35, 0.47, 0.51], "stage": [0, 0, 1, 1], "focal": [0.5, 0.5], "mass": {"centroid": [0.7, 0.48], "box": [0.21, 0.26, 0.93, 0.71]}},
    "v4": {"head": [0.18, 0.34, 0.45, 0.55], "stage": [0.43, 0.3, 0.98, 0.77], "focal": [0.71, 0.54], "mass": {"centroid": [0.69, 0.57], "box": [0.45, 0.43, 0.93, 0.74]}},
    "v5": {"head": [0.05, 0.25, 0.34, 0.6], "stage": [0.43, 0.07, 0.95, 0.93], "focal": [0.69, 0.5], "mass": {"centroid": [0.75, 0.5], "box": [0.55, 0.29, 0.9, 0.71]}},
    "v6": {"head": [0.09, 0.31, 0.35, 0.55], "stage": None, "focal": [0.22, 0.43], "mass": {"centroid": [0.65, 0.43], "box": [0.18, 0.04, 0.91, 0.79]}},
}
POSTER = {"head": [0.2, 0.3, 0.8, 0.7], "stage": [0, 0, 1, 1], "focal": [0.5, 0.5], "mass": {"centroid": [0.5, 0.5], "box": [0.05, 0.05, 0.95, 0.95]}}
BAND = {"head": [0.05, 0.72, 0.6, 0.95], "stage": [0, 0, 1, 1], "focal": [0.5, 0.5], "mass": {"centroid": [0.5, 0.35], "box": [0, 0, 1, 0.7]}}


def gen(d, rnd, v):
    return json.loads((d / ".uak/design/rounds" / rnd / v / "genome.json").read_text(encoding="utf-8"))


def kids(e, d, rnd):
    return e.genomes(d, rnd)


def breed_with(e, seed, notes, n=6, args=(), md=""):
    d = e.project(md)
    e.design(d, "round", "--n", str(n), "--seed", str(seed), "--yes")
    base = d / ".uak/design/rounds"
    (base / "R1/picks.json").write_text(json.dumps({"picked": ["v1", "v2", "v3"], "notes": notes}), encoding="utf-8")
    e.design(d, "round", "--from", "R1", "--n", str(n), "--seed", str(seed), "--yes", *args)
    return d


def creativity_from_project_and_flag(e):
    d = e.project()
    e.design(d, "round", "--n", "3", "--seed", "1", "--yes")
    expect({g["creativity"] for g in kids(e, d, "R1")} == {3}, "default 3")
    d = e.project("- Design-Creativity: 4\n")
    e.design(d, "round", "--n", "3", "--seed", "1", "--yes")
    expect({g["creativity"] for g in kids(e, d, "R1")} == {4}, "PROJECT.md 4")
    expect("creativity: **4/5**" in (d / ".uak/design/rounds/R1/v1/TASK.md").read_text(encoding="utf-8"), "TASK.md says what 4 asks for")
    e.design(d, "round", "--n", "3", "--seed", "1", "--creativity", "1", "--yes")
    expect({g["creativity"] for g in kids(e, d, "R2")} == {1}, "the flag overrides PROJECT.md")
    bad = e.design(d, "round", "--creativity", "9", "--yes", ok=(2,))
    expect("--creativity" in bad.stderr, "out of range refused: " + bad.stderr)
    return "1-5 from PROJECT.md, flag, default 3"


def compositions_distinct_across_siblings(e):
    for seed in (1, 2, 3):
        d = e.project()
        e.design(d, "round", "--n", "6", "--seed", str(seed), "--yes")
        comps = [g["composition"] for g in kids(e, d, "R1")]
        expect(len(set(comps)) == 6, "seed %d: compositions repeat: %s" % (seed, comps))
    import design_creativity
    expect(len(design_creativity.ARCHETYPES) >= 6, "at least 6 archetypes")
    return "6 variants, 6 compositions"


def bred_child_changes_composition_at_creativity_3(e):
    for seed in (1, 2, 3):
        d = breed_with(e, seed, {})
        for g in [k for k in kids(e, d, "R2") if k["from"]]:
            parent = gen(d, "R1", g["from"][0].split("/")[1])
            expect(g["composition"] != parent["composition"], "seed %d %s keeps its parent's composition %s" % (seed, g["id"], g["composition"]))
    d = breed_with(e, 1, {"v1": "me encanta la composicion, muy linda"})
    same = [g for g in kids(e, d, "R2") if g["from"] and g["from"][0] == "R1/v1" and g["composition"] == gen(d, "R1", "v1")["composition"]]
    expect(same, "a note praising the layout lets a child keep it")
    d = breed_with(e, 1, {}, args=("--creativity", "1"))
    expect(any(g["composition"] == gen(d, "R1", g["from"][0].split("/")[1])["composition"] for g in kids(e, d, "R2") if g["from"]), "creativity 1 refines the parent")
    return "differs at 3+, kept when praised or at 1"


def motif_families_distinct(e):
    import design_creativity
    for seed in (1, 2):
        d = e.project()
        e.design(d, "round", "--n", "6", "--seed", str(seed), "--yes")
        fams = [g["motif"]["family"] for g in kids(e, d, "R1")]
        expect(len(set(fams)) == 6 and set(fams) <= set(design_creativity.MOTIFS), "fresh seed %d: %s" % (seed, fams))
        expect("ONE motif carried strongly" in (d / ".uak/design/rounds/R1/v1/TASK.md").read_text(encoding="utf-8")
               and "identity, not quantity" in (d / ".uak/design/rounds/R1/v1/TASK.md").read_text(encoding="utf-8"), "TASK.md asks for one motif")
        b = breed_with(e, seed, {})
        fams = [g["motif"]["family"] for g in kids(e, b, "R2")]
        expect(len(set(fams)) == len(fams), "bred seed %d: %s" % (seed, fams))
    return "distinct families, one motif asked"


def praised_parent_motif_inherited_and_quoted(e):
    for seed in (1, 2, 3):
        d = e.project()
        e.design(d, "round", "--n", "6", "--seed", str(seed), "--yes")
        base = d / ".uak/design/rounds"
        (base / "R1/v1/index.html").write_text("<!-- motif: papel picado banners across the sky -->\n<!doctype html><title>x</title>", encoding="utf-8")
        (base / "R1/picks.json").write_text(json.dumps({"picked": ["v1", "v2", "v3"], "notes": {
            "v1": "ESTA SUPER LINDA Y CREATIVA, una identidad muy marcada, el unico problema es que habia demasiados objetos",
            "v2": "esta normal"}}), encoding="utf-8")
        e.design(d, "round", "--from", "R1", "--n", "6", "--seed", str(seed), "--yes")
        out = kids(e, d, "R2")
        mine = [g for g in out if g["from"] and g["from"][0] == "R1/v1"]
        expect(mine and mine[0]["motif"].get("inherited") and mine[0]["motif"]["family"] == gen(d, "R1", "v1")["motif"]["family"], "seed %d: v1's first child keeps its family: %s" % (seed, mine and mine[0]["motif"]))
        task = (base / "R2" / ("v%d" % (out.index(mine[0]) + 1)) / "TASK.md").read_text(encoding="utf-8")
        expect('"papel picado banners across the sky"' in task and "keep the motif, cut the objects" in task, "TASK.md quotes the parent's motif: " + task[-900:])
        for g in out:
            if g["from"] and g["from"][0] == "R1/v2":
                expect(not g["motif"].get("inherited"), "an unpraised parent's motif is not kept")
    return "praised motif kept, quoted, objects cut"


def run_shoot(e, d, sigs=None, *extra):
    stub, env = e.tmp / "stub shoot é.py", {}
    stub.write_text(STUB, encoding="utf-8")
    env = {"UAK_DESIGN_SHOOT": str(stub), "SIGS": json.dumps(sigs or {})}
    for v in (d / ".uak/design/rounds/R1").glob("v*"):
        if not (v / "index.html").exists():
            (v / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    return e.design(d, "shoot", "R1", *extra, env=env)


def shoot_reads_motif_comment(e):
    d = e.project()
    e.design(d, "round", "--n", "2", "--seed", "1", "--yes")
    (d / ".uak/design/rounds/R1/v1/index.html").write_text("<!-- motif:  a lucha libre mask\n as the hero -->\n<!doctype html><title>x</title>", encoding="utf-8")
    run_shoot(e, d)
    m = gen(d, "R1", "v1")["motif"]
    expect(m.get("text") == "a lucha libre mask as the hero" and m.get("family"), "the comment is copied next to the family: %s" % m)
    expect("text" not in gen(d, "R1", "v2")["motif"], "no comment, no text")
    return "motif text copied"


def clone_warning_on_same_signature(e):
    d = e.project()
    e.design(d, "round", "--n", "3", "--seed", "1", "--yes")
    out = run_shoot(e, d, {"v1": A, "v2": dict(A, lum=0.06), "v3": B})
    expect("DESIGN_SHOOT QA v2 1920: clone of v1: same hero composition (headline [0.05,0.30,0.45,0.60], visual mass [0.50,0.00,1.00,1.00])" in out.stdout, "the warning: " + out.stdout)
    expect("QA v3 1920: clone" not in out.stdout, "v3 is different: " + out.stdout)
    import design_creativity
    expect(design_creativity.distance(A, B) > design_creativity.CLONE_UNDER * 1.5, "different heroes are far apart")
    return "v2 flagged as a clone of v1"


def real_colonia_r2_is_flagged_as_clones(e):
    import design_creativity as dc
    score, clones = dc.analyze_sigs(R2)
    expect(score <= 35, "the six look-alikes score low: %d" % score)
    expect(len({v for v, _ in clones}) >= 4, "at least 4 of the 6 are flagged as clones of another: %s" % clones)
    near = min(dc.distance(R2[a], other) for a in R2 for other in (POSTER, BAND))
    expect(near > dc.CLONE_UNDER, "a poster or bottom-band hero sits clearly apart from left-text/right-visual: %.3f" % near)
    spread, flagged = dc.analyze_sigs({"v1": R2["v1"], "v2": POSTER, "v3": BAND})
    expect(not flagged and spread > score, "three different compositions: no clone, higher score (%d)" % spread)
    return "R2 scores %d with %d clones; poster and band apart (%.2f)" % (score, len({v for v, _ in clones}), near)


def creativity_score_in_report(e):
    d = e.project()
    e.design(d, "round", "--n", "3", "--seed", "1", "--yes")
    same = run_shoot(e, d, {"v1": A, "v2": A, "v3": A})
    expect("DESIGN_SHOOT creativity R1: 0/100" in same.stdout, "identical heroes score 0: " + same.stdout)
    d = e.project()
    e.design(d, "round", "--n", "3", "--seed", "1", "--yes")
    far = run_shoot(e, d, {"v1": A, "v2": B, "v3": BAND})
    score = int(far.stdout.split("DESIGN_SHOOT creativity R1: ")[1].split("/")[0])
    expect(score >= 50, "different heroes score high: %d" % score)
    rep = e.design(d, "report", "R1")
    expect("creativity: %d/100" % score in rep.stdout, "design report prints it: " + rep.stdout)
    return "score %d" % score


TESTS = [creativity_from_project_and_flag, compositions_distinct_across_siblings, bred_child_changes_composition_at_creativity_3, motif_families_distinct,
         praised_parent_motif_inherited_and_quoted, shoot_reads_motif_comment, clone_warning_on_same_signature, creativity_score_in_report, real_colonia_r2_is_flagged_as_clones]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-creativity-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_CREATIVITY_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
