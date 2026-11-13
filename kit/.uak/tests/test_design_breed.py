#!/usr/bin/env python3
"""UAK-059: `uak design round --from R<k>` breeds the next round from the human's picks: about half the children are
one-gene mutations of a pick, a third crossovers of two picks, 2 wildcards that share nothing with the picks; children
that are not kin (no parent in common) never share more than 3 genes; each genome.json records its parents and what
changed; the human's notes reach each child's TASK.md; a direction that won twice in a row is called converged.
The routing from design_round.py is one line outside this task's Paths, so the tests run lib/design_breed.py directly."""
import argparse
import itertools
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect


class Env:
    def __init__(self, tmp, package):
        self.tmp = Path(tmp)
        self.lib = Path(package) / ".uak" / "bin" / "lib"  # the candidate under test (smoke passes --package)
        sys.path.insert(0, str(self.lib))

    def py(self, cwd, script, *args):
        out = subprocess.run([sys.executable, str(self.lib / script)] + list(args), cwd=str(cwd), capture_output=True, text=True)
        return out

    def project(self, name, picks=("v1", "v4"), notes=None, n=8, seed=3):
        d = self.tmp / name
        (d / ".uak").mkdir(parents=True)
        r = self.py(d, "design_round.py", "round", "--n", str(n), "--seed", str(seed), "--yes")
        expect(r.returncode == 0, "source round: " + r.stdout + r.stderr)
        self.picks(d, "R1", list(picks), notes or {})
        return d

    def picks(self, d, rnd, picked, notes):
        (d / ".uak/design/rounds" / rnd / "picks.json").write_text(
            json.dumps({"picked": picked, "notes": notes, "by": "ana", "at": "2026-11-11T00:00:00Z"}), encoding="utf-8")

    def breed(self, d, *args, ok=0):
        r = self.py(d, "design_breed.py", *args)
        if ok is not None:
            expect(r.returncode == ok, "rc %d: %s" % (r.returncode, r.stdout + r.stderr))
        return r

    def genomes(self, d, rnd):
        base = d / ".uak/design/rounds" / rnd
        return {p.name: json.loads((p / "genome.json").read_text(encoding="utf-8")) for p in base.glob("v*") if (p / "genome.json").exists()}


def shared(a, b):
    return sum(1 for k in a["genes"] if a["genes"][k] == b["genes"][k])


def kinds(gs):
    out = {"mutation": 0, "crossover": 0, "wildcard": 0}
    for g in gs.values():
        out[g["kind"]] += 1
    return out


def children_follow_mutation_crossover_wildcard_mix(e):
    import design_round as dr
    for n, want in ((8, {"mutation": 4, "crossover": 2, "wildcard": 2}), (12, {"mutation": 6, "crossover": 4, "wildcard": 2})):
        d = e.project("mix%d" % n, picks=("v1", "v4"))
        e.breed(d, "--from", "R1", "--n", str(n), "--seed", "5", "--yes")
        src = e.genomes(d, "R1")
        kids = e.genomes(d, "R2")
        expect(len(kids) == n and kinds(kids) == want, "mix for n=%d: %s" % (n, kinds(kids)))
        picks = [src["v1"], src["v4"]]
        for name, g in kids.items():
            expect(len(g["genes"]) == len(dr.GENES) and all(g["genes"][k] in dr.GENES[k] for k in dr.GENES), "valid genes")
            if g["kind"] == "mutation":
                par = src[g["from"][0].split("/")[1]]
                expect(len(dr.GENES) - shared(g, par) == 1 and [k for k in dr.GENES if g["genes"][k] != par["genes"][k]] == [g["mutated"]], "%s: exactly one gene changed (%s)" % (name, g["mutated"]))
            elif g["kind"] == "crossover":
                a, b = (src[x.split("/")[1]] for x in g["from"])
                expect(a is not b and all(g["genes"][k] in (a["genes"][k], b["genes"][k]) for k in dr.GENES), "genes come from the two parents")
                expect(shared(g, a) < len(dr.GENES) and shared(g, b) < len(dr.GENES), "a crossover is neither parent")
            else:
                expect(all(shared(g, p) == 0 for p in picks) , "%s: a wildcard shares no gene with a pick" % name)
        for (an, a), (bn, b) in itertools.combinations(kids.items(), 2):
            kin = set(a["from"]) & set(b["from"])
            expect(shared(a, b) < len(dr.GENES), "%s and %s are the same design" % (an, bn))
            expect(kin or shared(a, b) <= dr.MAX_SHARED, "non-kin %s %s share %d genes" % (an, bn, shared(a, b)))
    for seed in range(1, 25):  # the diversity rule on many seeds, 3 picks, N=20
        d = e.project("many%d" % seed, picks=("v2", "v5", "v7"), n=8, seed=seed)
        e.breed(d, "--from", "R1", "--n", "20", "--seed", str(seed), "--yes")
        kids = list(e.genomes(d, "R2").values())
        expect(len(kids) == 20, "20 children")
        for a, b in itertools.combinations(kids, 2):
            expect(set(a["from"]) & set(b["from"]) or shared(a, b) <= dr.MAX_SHARED, "seed %d: non-kin pair shares %d" % (seed, shared(a, b)))
    d = e.project("det")
    e.breed(d, "--from", "R1", "--n", "8", "--seed", "9", "--yes")
    first = e.genomes(d, "R2")
    e.breed(d, "--from", "R1", "--n", "8", "--seed", "9", "--yes")
    expect(e.genomes(d, "R3") == {k: dict(v, id=v["id"].replace("R2", "R3"), round="R3") for k, v in first.items()}, "same seed, same children")
    dry = e.breed(d, "--from", "R1", "--n", "8", "--seed", "9", "--dry-run")
    expect("mutation" in dry.stdout and "wildcard" in dry.stdout and not (d / ".uak/design/rounds/R4").exists(), "--dry-run prints, writes nothing")
    gate = e.breed(d, "--from", "R1", "--n", "8", "--seed", "9", ok=None)
    expect(gate.returncode != 0 and "--yes" in gate.stdout + gate.stderr and "8 variants x 60k" in gate.stdout + gate.stderr and not (d / ".uak/design/rounds/R4").exists(),
           "cost gate: " + gate.stdout + gate.stderr)
    return "mix 4/2/2 and 6/4/2, diversity on 24 seeds"


def parents_recorded(e):
    d = e.project("par", picks=("v3", "v6"))
    e.breed(d, "--from", "R1", "--n", "8", "--seed", "2", "--yes")
    for name, g in e.genomes(d, "R2").items():
        expect(g["round"] == "R2" and g["kind"] in ("mutation", "crossover", "wildcard"), name)
        if g["kind"] == "mutation":
            expect(len(g["from"]) == 1 and g["from"][0] in ("R1/v3", "R1/v6") and g["mutated"] in ("type", "scale", "color", "layout", "components", "imagery", "motion", "voice"),
                   "mutation records its parent and gene: %s" % g)
        elif g["kind"] == "crossover":
            expect(sorted(g["from"]) == ["R1/v3", "R1/v6"] and set(g["taken"].values()) == {"R1/v3", "R1/v6"}, "crossover records both parents and who gave which gene: %s" % g)
        else:
            expect(g["from"] == [], "a wildcard has no parent: %s" % g)
    return "parents and changes recorded"


def notes_reach_children(e):
    d = e.project("nt", picks=("v1", "v2"), notes={"v1": "keep this type", "v2": "hate the color", "v5": "never the glass look"})
    e.breed(d, "--from", "R1", "--n", "8", "--seed", "4", "--yes")
    kids = e.genomes(d, "R2")
    for name, g in kids.items():
        task = (d / ".uak/design/rounds/R2" / name / "TASK.md").read_text(encoding="utf-8")
        expect("index.html" in task and "96 px at 1280" in task, "still the normal TASK.md")
        if g["kind"] == "wildcard":
            expect("keep this type" in task and "hate the color" in task, "a wildcard sees every note: " + task)
            continue
        for ref in g["from"]:
            note = {"R1/v1": "keep this type", "R1/v2": "hate the color"}[ref]
            expect(note in task and ref in task, "%s: the note on %s travels: %s" % (name, ref, task))
    expect((d / ".uak/design/rounds/R2/brief.md").read_text(encoding="utf-8") == (d / ".uak/design/rounds/R1/brief.md").read_text(encoding="utf-8"), "same brief")
    return "notes in TASK.md"


def converged_round_stops(e):
    d = e.project("cv", picks=("v2", "v3"))
    e.breed(d, "--from", "R1", "--n", "6", "--seed", "1", "--yes")
    kids = e.genomes(d, "R2")
    mut = sorted(k for k, g in kids.items() if g["kind"] == "mutation" and g["from"] == ["R1/v2"])[0]
    e.picks(d, "R2", [mut, "v1" if mut != "v1" else "v2"], {})
    r2 = e.breed(d, "--from", "R2", "--n", "6", "--seed", "1", "--dry-run")
    expect("converged" not in r2.stdout.lower(), "one round of the same direction is not convergence: " + r2.stdout)
    e.breed(d, "--from", "R2", "--n", "6", "--seed", "1", "--yes")
    kids3 = e.genomes(d, "R3")
    mut3 = sorted(k for k, g in kids3.items() if g["kind"] == "mutation" and g["from"] == ["R2/" + mut])[0]
    e.picks(d, "R3", [mut3], {})
    before = sorted(p.name for p in (d / ".uak/design/rounds").iterdir())
    out = e.breed(d, "--from", "R3", "--n", "6", "--seed", "1", "--yes")
    text = out.stdout + out.stderr
    expect("DESIGN_ROUND converged: R3/%s is the direction (same line for two rounds)" % mut3 in text and "/uak-design-lock step 5 fills DESIGN.md from R3/%s/genome.json" % mut3 in text and "uak design lock" not in text, "says converged and where to lock it: " + text)
    expect(sorted(p.name for p in (d / ".uak/design/rounds").iterdir()) == before, "breeds nothing")
    # a different first pick breaks the chain
    e.picks(d, "R3", [[k for k in kids3 if k != mut3 and kids3[k]["kind"] == "wildcard"][0]], {})
    ok = e.breed(d, "--from", "R3", "--n", "6", "--seed", "1", "--dry-run")
    expect("converged" not in ok.stdout.lower(), "a wildcard as first pick is not convergence")
    return "converged after two rounds"


TESTS = [children_follow_mutation_crossover_wildcard_mix, parents_recorded, notes_reach_children, converged_round_stops]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-breed-") as tmp:
        e = Env(tmp, args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_BREED_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
