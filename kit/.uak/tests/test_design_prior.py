#!/usr/bin/env python3
"""UAK-075: the kit ships a default design prior learned from real rounds, so every team starts from it, not from nothing.
Traits only (no names, project names, hex, pages, notes); a value enters when it was picked in 2+ distinct projects and is
clearly off neutral, a stylistic gene (type, scale, color, ground) only with 3+; a round draws from the prior when the human
has no profile, with the profile on top when there is one; --no-prior turns it off; the "why" of each gene says prior,
taste or spread."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect, resolve_binary


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = Path(package) / ".uak"  # the candidate under test (smoke passes --package)
        self.lib = self.pkg / "bin" / "lib"
        sys.path.insert(0, str(self.lib))
        os.environ["UAK_TASTE_HOME"] = str(self.tmp / "taste")
        import design_prior
        import design_round
        import design_taste
        self.dp, self.dr, self.dt = design_prior, design_round, design_taste
        self.n = 0

    def cells(self, **picked_by_project):
        """A profile whose rounds, per project, picked the given {gene: value} of 8 shown: every other value of the gene shown
        8 times and never picked there."""
        rounds = {}
        for project, picks in picked_by_project.items():
            genes = {}
            for gene, vals in self.dr.GENES.items():
                genes[gene] = {v: {"shown": 4, "first": 0, "picked": 4 if picks.get(gene) == v else 0, "notes": ["me gusto #0367FC en %s" % project]} for v in vals}
            rounds["%s:R1" % project] = {"picks": 4, "shown": 4 * len(self.dr.GENES["type"]), "genes": genes}
        return {"human": "ana", "rounds": rounds, "directions": {p: {"project": p, "round": "R1", "variant": "v1", "genes": {}, "date": "2026-11-01"} for p in picked_by_project}}

    def project(self):
        self.n += 1
        d = self.tmp / ("p%d" % self.n)
        (d / ".uak").mkdir(parents=True)
        (d / "IDEA.md").write_text("# IDEA · X\n\n## 1. One line\nFor **a**, X helps.\n", encoding="utf-8")
        return d

    def round(self, d, *args, prior=None, home=None, ok=(0,)):
        env = dict(os.environ, UAK_NO_COLOR="1", UAK_HUMAN="ana", UAK_TASTE_HOME=str(home or self.tmp / "taste"))
        env["UAK_DESIGN_PRIOR"] = str(prior) if prior else "none"
        out = subprocess.run([sys.executable, str(self.lib / "design_round.py"), "round"] + list(args), cwd=str(d), env=env, capture_output=True, text=True, timeout=120)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out


def prior_has_traits_only(e):
    prof = e.cells(axia={"layout": "scroll story", "motion": "entrance"}, colonia={"layout": "scroll story", "motion": "entrance"})
    doc = e.dp.build([prof], today="2026-11-13")
    text = json.dumps(doc)
    expect(doc["genes"]["layout"]["scroll story"]["projects"] == 2, "evidence: %s" % doc["genes"])
    expect(set(doc) == {"version", "generated", "evidence", "rules", "genes"} and set(doc["evidence"]) == {"profiles", "projects", "rounds", "picks"}, "shape: %s" % list(doc))
    for bad in ("axia", "colonia", "0367", "#", "gusto", "notes", "human", "ana", "directions", "<html"):
        expect(bad not in text, "the prior leaks %r: %s" % (bad, text[:300]))
    for gene, vals in doc["genes"].items():
        for value, c in vals.items():
            expect(gene in e.dr.GENES and value in e.dr.GENES[gene] and set(c) == {"weight", "lift", "picked", "shown", "projects"}, "only gene values and counts: %s %s" % (gene, c))
    # the file the kit ships
    shipped = (e.pkg / "settings" / "design-prior.json").read_text(encoding="utf-8")
    sd = json.loads(shipped)
    expect(sd["version"] == 1 and sd["evidence"]["projects"] >= 2, "shipped prior: %s" % sd["evidence"])
    for bad in ("axia", "colonia", "pulso", "#", "notes", "<html", "joahan", "morales"):
        expect(bad not in shipped.lower(), "the shipped prior names %r" % bad)
    for gene, vals in sd["genes"].items():
        expect(gene in e.dr.GENES and all(v in e.dr.GENES[gene] for v in vals), "shipped traits are real gene values: %s" % gene)
        expect(all(c["projects"] >= (3 if gene in e.dp.STYLISTIC else 2) for c in vals.values()), "shipped traits obey the bar: %s" % gene)
    return "traits only; shipped prior clean"


def needs_two_projects_to_enter(e):
    one = e.dp.build([e.cells(solo={"layout": "scroll story", "motion": "entrance"})])
    expect(one["genes"] == {}, "one project is an opinion, not a prior: %s" % one["genes"])
    two = e.dp.build([e.cells(a={"layout": "scroll story", "motion": "entrance"}, b={"layout": "scroll story", "motion": "pointer"})])
    expect(set(two["genes"]) == {"layout"} and "scroll story" in two["genes"]["layout"], "layout picked in both projects enters, motion split does not: %s" % two["genes"])
    # two profiles (two maintainers) of the same project count once
    same = e.dp.build([e.cells(a={"layout": "scroll story"}), e.cells(a={"layout": "scroll story"})])
    expect(same["genes"] == {} and same["evidence"]["projects"] == 1 and same["evidence"]["profiles"] == 2, "the same project twice is one project: %s" % same)
    # clearly off neutral: a value picked as often as chance is not a trait
    flat = e.cells(a={}, b={})
    for r in flat["rounds"].values():
        for gene in r["genes"]:
            for c in r["genes"][gene].values():
                c["picked"] = 2  # every value of every gene picked half the time
    expect(e.dp.build([flat])["genes"] == {}, "weights at neutral stay out")
    return "2 distinct projects and a clear weight"


def stylistic_genes_stay_neutral(e):
    two = e.dp.build([e.cells(a={"type": "serif display", "scale": "bold", "color": "dark media", "layout": "scroll story"},
                              b={"type": "serif display", "scale": "bold", "color": "dark media", "layout": "scroll story"})])
    expect(set(two["genes"]) == {"layout"}, "two projects: layout yes; type, scale and color stay neutral: %s" % list(two["genes"]))
    three = e.dp.build([e.cells(a={"type": "serif display", "scale": "bold", "layout": "scroll story"},
                                b={"type": "serif display", "scale": "bold", "layout": "scroll story"},
                                c={"type": "serif display", "scale": "bold", "layout": "scroll story"})])
    expect({"type", "scale", "layout"} <= set(three["genes"]) and "serif display" in three["genes"]["type"], "three projects agree: type and scale enter: %s" % list(three["genes"]))
    return "type, scale, color need 3 projects"


def _prior_doc(layout=0.95, motion=0.95):
    return {"version": 1, "generated": "2026-11-13", "evidence": {"profiles": 1, "projects": 3, "rounds": 5, "picks": 12}, "rules": {},
            "genes": {"layout": {"scroll story": {"weight": layout, "lift": 3.0, "picked": 9, "shown": 10, "projects": 3}},
                      "motion": {"entrance": {"weight": motion, "lift": 3.0, "picked": 9, "shown": 10, "projects": 3}}}}


def round_uses_prior_without_profile(e):
    pf = e.tmp / "prior-test.json"
    pf.write_text(json.dumps(_prior_doc()), encoding="utf-8")
    w, doc = e.dp.load(pf)
    hits = base = total = 0
    for seed in range(1, 41):  # the draw itself, 40 rounds of 8
        for g in e.dr.make_genomes(8, seed, prior=w):
            total += 1
            hits += g["genes"]["layout"] == "scroll story"
        base += sum(1 for g in e.dr.make_genomes(8, seed) if g["genes"]["layout"] == "scroll story")
    expect(hits > base * 1.15 and hits < total * 0.6, "the prior makes scroll story likelier (%d against %d without it), never certain (of %d)" % (hits, base, total))
    why_seen = set()
    for seed in range(1, 5):  # through the command: the mix line and the why
        d = e.project()
        out = e.round(d, "--n", "8", "--seed", str(seed), "--yes", prior=pf, home=e.tmp / ("empty%d" % seed))
        expect("6 from the kit prior" in out.stdout and "kit prior v1: 5 rounds, 3 projects, 12 picks" in out.stdout, "the mix line names the prior: " + out.stdout[-500:])
        for v in sorted((d / ".uak/design/rounds/R1").glob("v*")):
            gw = json.loads((v / "genome.json").read_text(encoding="utf-8"))["why"]
            why_seen.add(gw["layout"].split(" ")[0])
            expect(gw["type"] in ("spread", "wildcard"), "a gene the prior says nothing about is spread (or a wildcard): %s" % gw)
    expect({"prior", "spread", "wildcard"} <= why_seen, "why says prior, spread or wildcard: %s" % why_seen)
    return "prior draws without a profile (%d against %d of %d)" % (hits, base, total)


def profile_blends_over_prior(e):
    pf = e.tmp / "prior-blend.json"
    pf.write_text(json.dumps(_prior_doc(0.9, 0.9)), encoding="utf-8")
    home = e.tmp / "blend-home"
    prof = e.cells(a={"layout": "scroll story"}, b={"layout": "scroll story"}, c={"layout": "scroll story"})
    for r in prof["rounds"].values():  # a profile that has only judged the layout
        r["genes"] = {"layout": r["genes"]["layout"]}
    expect(e.dt.confidence(prof) == "ok", "the profile has enough picks: %d" % e.dt.pick_count(prof))
    os.environ["UAK_TASTE_HOME"] = str(home)
    e.dt.save("ana", prof)
    whys = []
    for seed in (4, 5, 6):
        d = e.project()
        out = e.round(d, "--n", "8", "--seed", str(seed), "--yes", prior=pf, home=home)
        expect("from taste" in out.stdout and "kit prior v1" in out.stdout, "taste on top, the prior still named: " + out.stdout[-500:])
        whys += [json.loads((v / "genome.json").read_text(encoding="utf-8"))["why"] for v in sorted((d / ".uak/design/rounds/R1").glob("v*"))]
    expect(any(w["layout"].startswith("taste") and "prior" in w["layout"] for w in whys), "values both know are blended: %s" % [w["layout"] for w in whys])
    expect(any(w["motion"].startswith("prior") for w in whys), "values only the prior knows still come from it: %s" % [w["motion"] for w in whys])
    pick = e.dp.blend({"layout": {"editorial column": 0.8}}, {"layout": {"editorial column": 0.4, "scroll story": 0.9}, "motion": {"entrance": 0.9}})
    w, src, a, b = pick("layout", "editorial column")
    expect(src == "both" and abs(w - (0.75 * 0.8 + 0.25 * 0.4)) < 1e-9, "75%% profile, 25%% prior: %s" % w)
    expect(pick("layout", "scroll story")[1] == "prior" and pick("motion", "entrance")[1] == "prior" and pick("type", "grotesk")[1] is None, "sources")
    os.environ["UAK_TASTE_HOME"] = str(e.tmp / "taste")
    return "taste on top of the prior"


def no_prior_flag(e):
    prior = {"version": 1, "generated": "2026-11-13", "evidence": {"profiles": 1, "projects": 3, "rounds": 5, "picks": 12}, "rules": {},
             "genes": {"layout": {"scroll story": {"weight": 0.95, "lift": 3.0, "picked": 9, "shown": 10, "projects": 3}}}}
    pf = e.tmp / "prior-off.json"
    pf.write_text(json.dumps(prior), encoding="utf-8")
    d = e.project()
    out = e.round(d, "--n", "8", "--seed", "2", "--yes", "--no-prior", prior=pf, home=e.tmp / "off-home")
    expect("0 from taste, 0 wildcards, 8 drawn as before" in out.stdout and "kit prior off (--no-prior)" in out.stdout, "off: " + out.stdout[-500:])
    for v in (d / ".uak/design/rounds/R1").glob("v*"):
        why = json.loads((v / "genome.json").read_text(encoding="utf-8"))["why"]
        expect(not any("prior" in x or x.startswith("taste") for x in why.values()), "no prior in any why: %s" % why)
    # the same project with the prior on differs: it is the flag that turned it off
    d2 = e.project()
    out2 = e.round(d2, "--n", "8", "--seed", "2", "--yes", prior=pf, home=e.tmp / "off-home2")
    expect("from the kit prior" in out2.stdout, "and on: " + out2.stdout[-300:])
    # no prior at all (none shipped / broken file): the round draws as before
    bad = e.tmp / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    out3 = e.round(e.project(), "--n", "4", "--seed", "2", "--yes", prior=bad, home=e.tmp / "off-home3")
    expect("0 from taste, 0 wildcards, 4 drawn as before" in out3.stdout and "no kit prior shipped" in out3.stdout, "a broken prior is no prior: " + out3.stdout[-400:])
    return "--no-prior, and a broken file"


TESTS = [prior_has_traits_only, needs_two_projects_to_enter, stylistic_genes_stay_neutral, round_uses_prior_without_profile, profile_blends_over_prior, no_prior_flag]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-prior-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_PRIOR_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
