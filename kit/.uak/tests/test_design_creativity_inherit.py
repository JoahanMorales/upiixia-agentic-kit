#!/usr/bin/env python3
"""UAK-085: a bred round keeps a praised parent's motif even when the parent predates motifs (no `motif.family` in its genome, only a
`<!-- motif: -->` comment in index.html), and TASK.md does not tell a creativity 3+ child to keep the parent's layout. Why (colonIA R3,
2026-11-15): the child of R1/v1 got "specimen sheet" instead of its papel picado, which the human loved."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from test_design_breed_rules import Env
from test_hack import expect, resolve_binary

LOVED = "ESTA SUPER LINDA Y CREATIVA, una identidad muy marcada, el unico problema es que habia demasiados objetos"
FIXTURE = Path("/home/joahan/Proyectos/design-rounds/colonia/.uak/design/rounds/R1")


def old_parent(e, md="", comment="papel picado banners across the sky", note=LOVED, seed=1, extra=()):
    """A project whose R1 predates UAK-084 (no composition or motif in any genome); v1 is praised."""
    d = e.project(md)
    e.design(d, "round", "--n", "6", "--seed", str(seed), "--yes")
    base = d / ".uak/design/rounds"
    for v in base.glob("R1/v[0-9]*"):
        g = json.loads((v / "genome.json").read_text(encoding="utf-8"))
        for k in ("motif", "composition", "creativity"):
            g.pop(k, None)
        (v / "genome.json").write_text(json.dumps(g), encoding="utf-8")
    if comment:
        (base / "R1/v1/index.html").write_text("<!-- motif: %s -->\n<!doctype html><title>x</title>" % comment, encoding="utf-8")
    else:
        (base / "R1/v1/index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    (base / "R1/picks.json").write_text(json.dumps({"picked": ["v1", "v2"], "notes": {"v1": note, "v2": "esta normal"}}), encoding="utf-8")
    e.design(d, "round", "--from", "R1", "--n", "6", "--seed", str(seed), "--yes", *extra)
    out = []
    for i, g in enumerate(e.genomes(d, "R2")):
        out.append((g, (base / "R2" / ("v%d" % (i + 1)) / "TASK.md").read_text(encoding="utf-8")))
    return d, out


def inherits_motif_text_without_family(e):
    for seed in (1, 2, 3):
        d, out = old_parent(e, seed=seed)
        mine = [(g, t) for g, t in out if g["from"] and g["from"][0] == "R1/v1"]
        expect(mine, "a child of v1")
        g, t = mine[0]
        expect(g["motif"].get("inherited") and g["motif"]["family"] and g["motif"]["parent_text"] == "papel picado banners across the sky", "seed %d: %s" % (seed, g["motif"]))
        fams = [x["motif"]["family"] for x, _ in out]
        expect(len(set(fams)) == len(fams), "the family is one no sibling uses: %s" % fams)
        expect('"papel picado banners across the sky"' in t and "keep the motif, cut the objects" in t, t[-800:])
        for x, _ in out:
            if x["from"] and x["from"][0] == "R1/v2":
                expect(not x["motif"].get("inherited"), "unpraised parent")
    return "text quoted, family free"


def no_motif_comment_says_read_the_page(e):
    d, out = old_parent(e, comment=None)
    g, t = [o for o in out if o[0]["from"] and o[0]["from"][0] == "R1/v1"][0]
    expect(g["motif"].get("inherited") and "parent_text" not in g["motif"], str(g["motif"]))
    expect("no motif comment: read the page" in t, t[-800:])
    return "read the page"


def child_task_layout_sentence_by_level(e):
    old = "keep the rest of the parent's look"
    for level, kept in ((1, True), (2, True), (3, False), (4, False), (5, False)):
        for seed in (1, 2, 3, 4):
            d, out = old_parent(e, seed=seed, extra=("--creativity", str(level)))
            muts = [t for g, t in out if g["kind"] == "mutation"]
            if not muts:
                continue
            for t in muts:
                expect((old in t) == kept, "level %d seed %d: %s" % (level, seed, t[-500:]))
                if not kept:
                    expect("replace the parent's hero layout" in t and "other genes are kept" in t, t[-500:])
            break
        else:
            raise AssertionError("no mutation child at level %d" % level)
    return "old sentence at 1-2 only"


def level4_text_mentions_praised_motif(e):
    sys.path.insert(0, str(e.lib))
    import design_creativity as dc
    expect("a clearly different composition; a new motif unless the human praised the parent's" in dc.level_text(4), dc.level_text(4))
    return "level 4 text"


def real_colonia_r1_papel_picado(e):
    if not FIXTURE.is_dir():
        return "skipped: fixture absent"
    d = e.project()
    dest = d / ".uak/design/rounds/R1"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, dest)
    e.design(d, "round", "--from", "R1", "--n", "6", "--seed", "3", "--creativity", "4", "--yes")
    out = e.genomes(d, "R2")
    mine = [g for g in out if g["from"] and g["from"][0] == "R1/v1"]
    expect(mine and mine[0]["motif"].get("inherited"), "child of R1/v1 inherits: %s" % [g["motif"] for g in mine])
    expect("papel picado" in mine[0]["motif"].get("parent_text", "").lower(), str(mine[0]["motif"]))
    return "papel picado kept"


TESTS = [inherits_motif_text_without_family, no_motif_comment_says_read_the_page, child_task_layout_sentence_by_level,
         level4_text_mentions_praised_motif, real_colonia_r1_papel_picado]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-inherit-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_CREATIVITY_INHERIT_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
