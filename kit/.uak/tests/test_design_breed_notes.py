#!/usr/bin/env python3
"""UAK-065: `uak design round --from R<k>` reads the human's notes. A note that names a gene ("podria mejorar los
colores", "el fondo deberia ser blanco") picks the gene mutated for that parent's children; a negative note on a
variant the human did not pick marks its values rejected, wildcards never use them and fall back to a picked value
when nothing else is left; "because" records why a gene was chosen. Fixture: the real AXIA R1 (genomes + picks.json
with the human's notes, Nov 11 2026), copied read-only into a temp project. Why (AXIA R2): breeding mutated scale where
the note asked for colors and both wildcards landed on the saturated fields that "hurt the eyes"."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect

REAL = Path("/home/joahan/Proyectos/design-rounds/axia/.uak/design/rounds/R1")
REJECTED = {"color": {"saturated field", "brand duo"}, "type": {"rounded"}}  # v3 / v1 / v5 as the human annotated them

# Verbatim from the real picks.json, kept inline so the test still runs where /home/joahan is absent.
NOTES = {
    "v1": "los colores lastiman demasiado la vista",
    "v2": "la tipografia y la ambientacion me gustaron bastante, describe muy bien el proyecto pero podria mejorar los colores y el dlujo",
    "v3": "no me gusto nada",
    "v4": "muy informativa soreprendente bonita pero poco creativa",
    "v5": "es la peor de todas, mucho espacio perdido mala acomodacion, muy fea",
    "v6": "muy bonita creativa, divertida poco formal y el fondo deberia ser completamente blanco, con ese fondo se ve mal",
}
GENOMES = {
    "v1": ("condensed", "restrained", "brand duo", "product screen first", "solid blocks", "type only", "still", "bold claim"),
    "v2": ("serif display", "standard", "dark media", "scroll story", "glass", "illustration", "entrance", "numbers first"),
    "v3": ("geometric", "bold", "saturated field", "split hero", "hairline", "product screenshot", "scroll", "plain"),
    "v4": ("grotesk", "standard", "light paper", "full-bleed media", "soft", "3D cut-out", "pointer", "numbers first"),
    "v5": ("rounded", "restrained", "ink + one accent", "editorial column", "soft", "video loop", "still", "bold claim"),
    "v6": ("mono-led", "bold", "ink + one accent", "editorial column", "solid blocks", "illustration", "scroll", "plain"),
}
KEYS = ("type", "scale", "color", "layout", "components", "imagery", "motion", "voice")


class Env:
    def __init__(self, tmp, package):
        self.tmp = Path(tmp)
        self.lib = Path(package) / ".uak" / "bin" / "lib"

    def project(self, name, notes=None, picked=("v2", "v6", "v4")):
        """R1 of the real AXIA project: copied from the real folder when present (genomes + picks), else rebuilt."""
        d = self.tmp / name
        r1 = d / ".uak" / "design" / "rounds" / "R1"
        r1.mkdir(parents=True)
        for v, vals in GENOMES.items():
            (r1 / v).mkdir()
            src = REAL / v / "genome.json"
            if src.is_file():
                shutil.copyfile(str(src), str(r1 / v / "genome.json"))
            else:
                doc = {"id": "R1-" + v, "round": "R1", "genes": dict(zip(KEYS, vals)), "recipe": "motionsites"}
                (r1 / v / "genome.json").write_text(json.dumps(doc), encoding="utf-8")
        (r1 / "picks.json").write_text(json.dumps({"picked": list(picked), "notes": NOTES if notes is None else notes, "by": "joahan", "at": "2026-11-11T20:22:41Z"}), encoding="utf-8")
        return d

    def breed(self, d, *args):
        r = subprocess.run([sys.executable, str(self.lib / "design_breed.py"), "--from", "R1", "--yes"] + list(args), cwd=str(d), capture_output=True, text=True)
        expect(r.returncode == 0, "rc %d: %s" % (r.returncode, r.stdout + r.stderr))
        base = d / ".uak" / "design" / "rounds" / "R2"
        return {p.name: json.loads((p / "genome.json").read_text(encoding="utf-8")) for p in sorted(base.glob("v*"))}


def note_naming_color_mutates_color(e):
    for seed in ("1", "2", "3", "7"):
        d = e.project("color" + seed)
        kids = e.breed(d, "--n", "8", "--seed", seed)
        muts = {k: g for k, g in kids.items() if g["kind"] == "mutation"}
        parents = {g["from"][0] for g in muts.values()}
        expect({"R1/v2", "R1/v6"} <= parents, "seed %s: mutations of v2 and v6: %s" % (seed, parents))
        for k, g in muts.items():
            if g["from"][0] in ("R1/v2", "R1/v6"):
                expect(g["mutated"] == "color", "seed %s %s (from %s) mutated %s, not color" % (seed, k, g["from"][0], g["mutated"]))
    # the pick whose note names no gene stays random: across seeds v4's children do not always mutate one gene
    seen = set()
    for seed in range(1, 8):
        d = e.project("free%d" % seed)
        for g in e.breed(d, "--n", "8", "--seed", str(seed)).values():
            if g["kind"] == "mutation" and g["from"] == ["R1/v4"]:
                seen.add(g["mutated"])
    expect(len(seen) > 1, "v4 has no named gene, so it mutates freely: " + str(seen))
    return "v2 and v6 children mutate color, v4 stays free"


def rejected_values_never_reach_wildcards(e):
    for seed in range(1, 13):
        d = e.project("rej%d" % seed)
        for k, g in e.breed(d, "--n", "8", "--seed", str(seed)).items():
            if g["kind"] == "wildcard":
                for gene, bad in REJECTED.items():
                    expect(g["genes"][gene] not in bad, "seed %d %s got %s=%s" % (seed, k, gene, g["genes"][gene]))
    return "no wildcard in 12 seeds got saturated field, brand duo or rounded"


def wildcard_falls_back_to_a_picked_value(e):
    # every non-picked color (brand duo, saturated field) is rejected, so the wildcard takes a picked color; it stays
    # a wildcard on the other genes.
    d = e.project("fall")
    kids = e.breed(d, "--n", "8", "--seed", "4")
    picked_colors = {GENOMES[v][2] for v in ("v2", "v6", "v4")}
    wild = [g for g in kids.values() if g["kind"] == "wildcard"]
    expect(len(wild) == 2, "two wildcards")
    for g in wild:
        expect(g["genes"]["color"] in picked_colors, "color falls back to a picked value: " + g["genes"]["color"])
    # nothing rejected -> the old rule: no pick's value where another exists
    d = e.project("plain", notes={})
    for g in e.breed(d, "--n", "8", "--seed", "4").values():
        if g["kind"] == "wildcard":
            expect(g["genes"]["color"] not in picked_colors, "without notes a wildcard avoids the picks' colors")
    return "color falls back to a picked value; without notes nothing changes"


def because_is_recorded(e):
    d = e.project("because")
    kids = e.breed(d, "--n", "8", "--seed", "2")
    seen = {}
    for g in kids.values():
        if g["kind"] == "mutation" and g["from"][0] in ("R1/v2", "R1/v6"):
            expect(g["because"].startswith("note on %s: " % g["from"][0]) and g["because"].endswith(" → color"), "because: " + g.get("because", "(none)"))
            seen[g["from"][0]] = g["because"]
        else:
            expect("because" not in g, "only a gene chosen by a note has because: %s" % g["kind"])
    expect(seen["R1/v6"] == "note on R1/v6: el fondo deberia ser completamente blanco → color", "v6: " + seen["R1/v6"])
    expect("mejorar los colores" in seen["R1/v2"], "v2: " + seen["R1/v2"])
    return seen["R1/v6"]


R2_NOTES = {
    "v1": "Super lindo y explicativo solamente las imagenes se podrian mostrar mejor pq se ven feas, o recrearlas en animaci\u00f3n para q n se vean redimensiondas y feas",
    "v2": "esta normal",
    "v3": "igual esta bastante bien pero se ve simple y esos difuminados neon y todo eso parece completamente ai slop",
    "v4": "el mejor de esta ronda, bonitas guentes colores paletas texto explicativo solamente el mismo comentario con las imagenes",
    "v5": "horrilble ai slop",
    "v6": "horrible ai slopp",
}
R2_GENOMES = {  # AXIA R2 as the human saw it (picked v4 and v1, which share 5 genes); R1 is not needed to breed from R2
    "v1": ("serif display", "standard", "dark media", "full-bleed media", "glass", "illustration", "entrance", "numbers first"),
    "v2": ("mono-led", "bold", "light paper", "editorial column", "solid blocks", "illustration", "scroll", "plain"),
    "v3": ("grotesk", "standard", "light paper", "editorial column", "soft", "3D cut-out", "pointer", "numbers first"),
    "v4": ("serif display", "standard", "ink + one accent", "scroll story", "glass", "illustration", "entrance", "plain"),
    "v5": ("geometric", "restrained", "ink + one accent", "product screen first", "hairline", "product screenshot", "still", "bold claim"),
    "v6": ("condensed", "standard", "light paper", "split hero", "soft", "type only", "scroll", "numbers first"),
}


def real_r2_still_breeds(e):
    """The real AXIA R2: two overlapping picks, notes naming colors and animation, a variant rejected on all 8 genes
    ("horrible ai slopp"). It raised 'could not breed' in the first UAK-065 cut; it must always give N children."""
    d = e.tmp / "r2"
    r2 = d / ".uak" / "design" / "rounds" / "R2"
    r2.mkdir(parents=True)
    for v, vals in R2_GENOMES.items():
        (r2 / v).mkdir()
        (r2 / v / "genome.json").write_text(json.dumps({"id": "R2-" + v, "round": "R2", "genes": dict(zip(KEYS, vals)), "recipe": "landing-story"}), encoding="utf-8")
    (r2 / "picks.json").write_text(json.dumps({"picked": ["v4", "v1"], "notes": R2_NOTES, "by": "joahan", "at": "2026-11-11T20:39:41Z"}), encoding="utf-8")
    for n in (4, 6):
        for seed in (1, 2, 3):
            r = subprocess.run([sys.executable, str(e.lib / "design_breed.py"), "--from", "R2", "--n", str(n), "--seed", str(seed), "--dry-run"], cwd=str(d), capture_output=True, text=True)
            expect(r.returncode == 0 and len([l for l in r.stdout.splitlines() if l.startswith("v")]) == n, "n=%d seed=%d: %s" % (n, seed, r.stdout + r.stderr))
    return "R2 breeds 4 and 6 children for 3 seeds"


def slop_and_short_stems(e):
    sys.path.insert(0, str(e.lib))
    import design_breed as b
    allg = set(b.GENES)
    for note in (R2_NOTES["v3"], R2_NOTES["v5"], R2_NOTES["v6"]):
        expect(set(b.note_rejects(note)) == allg, "a slop verdict rejects every gene: " + note)
    for note in ("this feature is fine", "material y malla", "the fonts are fine"):
        expect(b.note_rejects(note) == [], "no negative word in: " + note)
    expect(b.note_rejects("muy fea") == list(b.GENES) and b.note_genes("the font should change")[0] == ["type"], "whole short stems still count")
    return "slop counts, feature/material/malla do not"


TESTS = [real_r2_still_breeds, slop_and_short_stems, note_naming_color_mutates_color, rejected_values_never_reach_wildcards, wildcard_falls_back_to_a_picked_value, because_is_recorded]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-breed-notes-") as tmp:
        e = Env(tmp, args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_BREED_NOTES_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
