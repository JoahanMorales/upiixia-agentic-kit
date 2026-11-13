#!/usr/bin/env python3
"""UAK-063: the first round of a project is seeded by taste and shaped by the project. Liked gene values are drawn more
often (never certain); wildcards ignore taste; no variant copies a past direction (> 5 of 8 genes) unless --allow-repeat;
the default seed comes from the project's name; the project's colors reach brief.md; imagery follows the material the
project has; genome.json records why each gene was chosen."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect

IDEA = """# IDEA · %s

## 0. Name and brand
- Brand: Blue #0367FC, Midnight #0B1020.

## 1. One line
For **tenderos**, **Pasala** lets them sell in a minute.
"""


class Env:
    def __init__(self, tmp, package):
        os.environ.setdefault("UAK_DESIGN_PRIOR", "none")  # these cases are about the profile or the capture, not the kit's default prior (UAK-075)
        self.tmp = Path(tmp)
        self.lib = Path(package) / ".uak" / "bin" / "lib"  # the candidate under test (smoke passes --package)
        sys.path.insert(0, str(self.lib))
        self.home = self.tmp / "taste"
        os.environ["UAK_TASTE_HOME"] = str(self.home)
        import design_round
        import design_taste
        self.dr, self.dt = design_round, design_taste

    def project(self, name, idea=True, files=None):
        d = self.tmp / name
        (d / ".uak").mkdir(parents=True)
        if idea:
            (d / "IDEA.md").write_text(IDEA % name, encoding="utf-8")
        for rel, text in (files or {}).items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(text, encoding="utf-8")
        return d

    def run(self, cwd, *args, ok=(0,)):
        env = dict(os.environ, UAK_TASTE_HOME=str(self.home), UAK_HUMAN="")
        out = subprocess.run([sys.executable, str(self.lib / "design_round.py"), "round"] + list(args), cwd=str(cwd), env=env,
                             capture_output=True, text=True)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out

    def profile(self, human, liked, shown=6, picks=12, directions=()):
        """A profile with enough picks: every value of every gene was shown `shown` times, the liked ones picked every time."""
        genes = {}
        for g, vals in self.dr.GENES.items():
            genes[g] = {v: {"shown": shown, "first": 0, "picked": shown if liked.get(g) == v else 0, "notes": []} for v in vals}
        doc = {"human": human, "rounds": {"old:R1": {"picks": picks, "shown": shown, "genes": genes}},
               "directions": {p: {"project": p, "round": "R1", "variant": "v1", "genes": gn, "date": "2026-11-01"} for p, gn in directions}}
        self.dt.save(human, doc)

    def genomes(self, d, rnd="R1"):
        base = d / ".uak/design/rounds" / rnd
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(base.glob("v*/genome.json"), key=lambda p: int(p.parent.name[1:]))]


LIKED = {"type": "serif display", "color": "dark media", "layout": "scroll story", "voice": "numbers first"}


def liked_values_drawn_more_often(e):
    e.profile("ana", LIKED)
    hits = {g: 0 for g in LIKED}
    total = 0
    for seed in range(1, 13):
        gs = e.dr.make_genomes(8, seed, weights=e.dt.weights(e.dt.load("ana")))
        expect(len(gs) == 8, "8 genomes")
        for g in gs:
            total += 1
            for k, v in LIKED.items():
                hits[k] += g["genes"][k] == v
    for k, v in LIKED.items():
        base = total / float(len(e.dr.GENES[k]))
        expect(hits[k] > base * 1.2, "%s=%s drawn %d of %d (uniform would be %.0f)" % (k, v, hits[k], total, base))
        expect(hits[k] < total, "never certain: %s=%s in every variant" % (k, v))
    # through the command: the dry run counts the variants that come from taste
    d = e.project("liked1")
    out = e.run(d, "--dry-run", "--human", "ana", "--n", "8")
    expect("6 from taste, 2 wildcards" in out.stdout, "mix line: " + out.stdout[-400:])
    # low confidence draws as before, and says so
    e.profile("bea", LIKED, picks=4)
    out = e.run(d, "--dry-run", "--human", "bea", "--n", "8")
    expect("0 from taste, 0 wildcards, 8 drawn as before" in out.stdout and "still learning" in out.stdout, "low confidence: " + out.stdout[-400:])
    return "liked values %s" % hits


def wildcards_ignore_taste(e):
    e.profile("ana", LIKED)
    w = e.dt.weights(e.dt.load("ana"))
    for n, want in ((8, 2), (4, 1), (12, 2)):
        wild_liked = taste_liked = wc = ts = 0
        for seed in range(1, 25):
            gs = e.dr.make_genomes(n, seed, weights=w)
            kinds = [g["origin"] for g in gs]
            expect(kinds.count("wildcard") == want, "n=%d has %d wildcards: %s" % (n, kinds.count("wildcard"), kinds))
            for g in gs:
                lk = sum(g["genes"][k] == v for k, v in LIKED.items())
                if g["origin"] == "wildcard":
                    wc, wild_liked = wc + 1, wild_liked + lk
                    expect(set(g["why"].values()) == {"wildcard"}, "wildcard why: %r" % g["why"])
                else:
                    ts, taste_liked = ts + 1, taste_liked + lk
        expect(wild_liked / float(wc) < taste_liked / float(ts) - 0.5, "wildcards (%.2f liked genes) look like taste (%.2f)" % (wild_liked / float(wc), taste_liked / float(ts)))
    return "2 wildcards (1 when n<=4) draw uniformly"


def never_repeats_a_past_direction(e):
    past = {"type": "serif display", "scale": "standard", "color": "dark media", "layout": "scroll story", "components": "glass",
            "imagery": "illustration", "motion": "entrance", "voice": "numbers first"}
    liked = dict(past)  # the human loves exactly that: the pull to copy it is at its strongest
    e.profile("ana", liked, directions=[("axia", past)])
    d = e.project("novel1")
    for seed in ("1", "2", "3", "4", "5", "6"):
        e.run(d, "--n", "8", "--seed", seed, "--human", "ana", "--yes")
    for r in range(1, 7):
        for g in e.genomes(d, "R%d" % r):
            expect(e.dr.shared_genes(g, past) <= 5, "R%d-v%d shares %d genes with the past direction" % (r, g["variant"], e.dr.shared_genes(g, past)))
    out = e.run(d, "--dry-run", "--human", "ana", "--n", "8")
    expect("vs 1 past directions" in out.stdout, "the mix line counts them: " + out.stdout[-300:])
    # the same project's own earlier direction does not block it, and --allow-repeat lifts the rule
    same = 0
    for seed in range(1, 30):
        for g in e.dr.make_genomes(8, seed, weights=e.dt.weights(e.dt.load("ana"))):
            same += e.dr.shared_genes(g, past) > 5
    expect(same > 0, "without the rule, the liked genome does come back (so the test means something)")
    out = e.run(d, "--dry-run", "--human", "ana", "--allow-repeat")
    expect("vs 0 past directions" in out.stdout, "--allow-repeat: " + out.stdout[-300:])
    return "no variant shares > 5 genes with a past direction"


def seed_comes_from_project_name(e):
    a, b = e.project("Alfa"), e.project("Bravo")
    sa = e.dr.project_seed("Alfa")
    expect(sa == e.dr.project_seed("alfa  ") and sa != e.dr.project_seed("Bravo") and sa != 1, "seed is a function of the name")
    e.run(a, "--n", "4", "--yes")
    e.run(b, "--n", "4", "--yes")
    ga, gb = e.genomes(a), e.genomes(b)
    expect(ga[0]["seed"] == sa, "seed %r" % ga[0]["seed"])
    expect(gb[0]["seed"] == e.dr.project_seed("Bravo") and ga != gb and [g["genes"] for g in ga] != [g["genes"] for g in gb], "two projects, two rounds")
    e.run(a, "--n", "4", "--yes")
    expect([g["genes"] for g in e.genomes(a, "R2")] == [g["genes"] for g in ga], "same name, same round")
    e.run(a, "--n", "4", "--seed", "9", "--dry-run")
    return "seed %d for Alfa" % sa


def project_colors_reach_the_brief(e):
    d = e.project("colors1", files={
        "web/styles.css": ":root { --brand: #FF3366; --bg: #ffffff; --ink: #111; --accent: #22CCAA; }\n",
        "assets/logo.svg": '<svg><path fill="#7B2CBF" d="M0 0"/><path fill="#FFFFFF" d="M1 1"/></svg>'})
    cols = [h for h, _ in e.dr.brand_colors(d)]
    expect(cols[:2] == ["#0367FC", "#0B1020"], "IDEA.md section 0 first, greys kept there: %r" % cols)
    expect("#FF3366" in cols and "#22CCAA" in cols and "#7B2CBF" in cols, "css vars and svg fills: %r" % cols)
    expect("#FFFFFF" not in cols and "#111111" not in cols, "white and near-black scraped from files are skipped: %r" % cols)
    e.run(d, "--n", "4", "--yes")
    brief = (d / ".uak/design/rounds/R1/brief.md").read_text(encoding="utf-8")
    expect("Brand colors (from the project)" in brief and "#0367FC" in brief and "#FF3366" in brief, "brief: " + brief[-700:])
    g = e.genomes(d)[0]
    expect("#0367FC" in g["why"]["color"], "why color: %r" % g["why"])
    expect("#0367FC" in (d / ".uak/design/rounds/R1/v1/TASK.md").read_text(encoding="utf-8"), "TASK.md carries them")
    plain = e.project("nocolors", idea=False, files={"README.md": "x"})
    e.run(plain, "--n", "4", "--yes")
    expect("Brand colors" not in (plain / ".uak/design/rounds/R1/brief.md").read_text(encoding="utf-8"), "no colors, no section")
    expect("## Subject world" in brief and "3-5 concrete things" in brief, "Subject world beat in the brief")
    expect("Subject world" in (d / ".uak/design/rounds/R1/v1/TASK.md").read_text(encoding="utf-8"), "and in TASK.md")
    return "colors: %s" % " ".join(cols)


def imagery_follows_available_material(e):
    rich = e.project("rich", files={"assets/dashboard.png": "x", "assets/demo.mp4": "x"})
    bare = e.project("bare", files={"README.md": "x"})
    mat = e.dr.project_material(rich)
    expect(set(mat) >= {"product screenshot", "video loop"} and "3D cut-out" not in mat, "material found: %r" % mat)
    expect(e.dr.project_material(bare) == {}, "nothing to find")
    f = e.dr.material_factors(mat)["imagery"]
    expect(f["video loop"] == 1.0 and f["3D cut-out"] < 1.0 and f["type only"] == 1.0, "factors: %r" % f)
    count = {v: 0 for v in e.dr.GENES["imagery"]}
    for seed in range(1, 41):
        for g in e.dr.make_genomes(8, seed, factors=e.dr.material_factors(mat)):
            count[g["genes"]["imagery"]] += 1
    have = min(count["product screenshot"], count["video loop"])
    lack = max(count["3D cut-out"], count["illustration"])
    expect(have > lack * 1.3, "values with material are drawn more: %r" % count)
    expect(lack > 0, "but values without it still appear: %r" % count)
    e.run(rich, "--n", "8", "--yes")
    gs = e.genomes(rich)
    shot = [g for g in gs if g["genes"]["imagery"] == "product screenshot"]
    expect(not shot or "project has: assets/dashboard.png" in shot[0]["why"]["imagery"], "why names the material: %r" % [g["why"]["imagery"] for g in gs])
    return "counts %r" % count


def why_is_recorded(e):
    e.profile("ana", LIKED)
    d = e.project("why1", files={"assets/screen.png": "x"})
    e.run(d, "--n", "8", "--human", "ana", "--yes")
    gs = e.genomes(d)
    for g in gs:
        expect(set(g["why"]) == set(e.dr.GENES), "why for every gene: %r" % g["why"])
        expect("#0367FC" in g["why"]["color"], "color why names project colors: %r" % g["why"]["color"])
    taste = [g for g in gs if not all(w.startswith("wildcard") for k, w in g["why"].items() if k not in ("color", "imagery"))]
    expect(len(taste) == 6 and all(g["why"]["type"].startswith("taste 0.") for g in taste), "6 variants with taste weights: %r" % [g["why"]["type"] for g in gs])
    wild = [g for g in gs if g["why"]["type"] == "wildcard"]
    expect(len(wild) == 2, "2 wildcards")
    out = e.run(d, "--n", "8", "--human", "ana", ok=(3,))
    expect("6 from taste, 2 wildcards" in out.stdout.split("DESIGN_ROUND cost")[1], "cost line is followed by the mix: " + out.stdout, )
    return "why: %r" % gs[0]["why"]["type"]


TESTS = [liked_values_drawn_more_often, wildcards_ignore_taste, never_repeats_a_past_direction, seed_comes_from_project_name,
         project_colors_reach_the_brief, imagery_follows_available_material, why_is_recorded]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-round-taste-") as tmp:
        e = Env(tmp, args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_ROUND_TASTE_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
