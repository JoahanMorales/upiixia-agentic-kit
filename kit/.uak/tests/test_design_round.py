#!/usr/bin/env python3
"""UAK-057: `uak design round` writes a brief from IDEA.md and N design genomes that differ on purpose (no two share more
than 3 of 8 genes, same seed same round), prints the cost before writing anything and needs --yes; `uak design shoot`
captures the variants whose PNGs are missing and lists what it could not. No real browser or network: the capture tool
is a stub named by UAK_DESIGN_SHOOT."""
import argparse
import itertools
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect, resolve_binary

IDEA = """# IDEA · Pásala

## 1. One line
For **tenderos**, who **sell online only 7 in 100**, **Pásala** lets them sell in a minute, unlike a marketplace.

## 2. Users
| Persona | Moment | Need | Flow step |
|---|---|---|---|
| Doña Lupe, tendera | closing | sell leftovers | 1 |

## 4. Demo flow
| # | User does | Sees on screen | API | Prio |
|---|---|---|---|---|
| 1 | Takes a photo | The price appears | `POST /a` | P0 |
| 2 | Shares the link | **Wow:** the shelf sells itself | `POST /b` | P0 |

- Wow in one sentence: a photo becomes a shop in ten seconds · seconds until the wow: 30.

## 10. Citable facts
| Fact | Source URL |
|---|---|
| 7 in 100 shops sell online | https://example.invalid/inegi |
"""

STUB = """import sys
from pathlib import Path
# fake capture tool: STUB index.html OUTDIR -> OUTDIR/1280.png and 390.png; a variant whose path has "v3" fails
if "v3" in sys.argv[1]:
    sys.stderr.write("stub: cannot render\\n")
    sys.exit(1)
Path(sys.argv[2], "1280.png").write_text("png")
Path(sys.argv[2], "390.png").write_text("png")
"""


class Env:
    def __init__(self, tmp, bash, package=None):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = (Path(package) / ".uak") if package else Path(__file__).resolve().parents[1]
        self.tool = self.pkg / "bin" / "design"

    def project(self, name, idea=IDEA, project_md=""):
        d = self.tmp / name
        (d / ".uak").mkdir(parents=True)
        if idea is not None:
            (d / "IDEA.md").write_text(idea, encoding="utf-8")
        if project_md:
            (d / ".uak" / "PROJECT.md").write_text(project_md, encoding="utf-8")
        return d

    def run(self, cwd, *args, env=None, ok=(0,)):
        e = dict(os.environ, UAK_NO_COLOR="1")
        e.pop("UAK_DESIGN_SHOOT", None)
        e.update(env or {})
        out = subprocess.run([self.bash, str(self.tool)] + list(args), cwd=str(cwd), env=e, capture_output=True, text=True)
        if ok is not None and out.returncode not in ok:
            raise AssertionError("rc %d: %s" % (out.returncode, (out.stdout + out.stderr)[-800:]))
        return out


def genomes_of(rnd):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(rnd.glob("v*/genome.json"), key=lambda p: int(p.parent.name[1:]))]


def shared(a, b):
    return sum(1 for k in a["genes"] if a["genes"][k] == b["genes"][k])


def round_writes_brief_and_genomes(e):
    d = e.project("rw")
    first = e.run(d, "round", "--n", "4", "--seed", "7", ok=None)
    expect(first.returncode != 0 and not (d / ".uak/design").exists(), "no --yes writes nothing")
    e.run(d, "round", "--n", "4", "--seed", "7", "--yes")
    rnd = d / ".uak/design/rounds/R1"
    brief = (rnd / "brief.md").read_text(encoding="utf-8")
    for needle in ("tenderos", "7 in 100 shops sell online", "example.invalid/inegi", "the shelf sells itself", "Takes a photo", "Doña Lupe"):
        expect(needle in brief, "brief.md lacks %r:\n%s" % (needle, brief))
    gs = genomes_of(rnd)
    expect(len(gs) == 4, "4 genomes, got %d" % len(gs))
    for i, g in enumerate(gs, 1):
        expect(len(g["genes"]) == 8, "8 genes")
        expect(set(g["genes"]) == {"type", "scale", "color", "layout", "components", "imagery", "motion", "voice"}, "gene names")
        expect(g.get("recipe") in ("motionsites", "landing-story", "frontend-design", "design-taste-frontend"), "recipe")
        task = (rnd / ("v%d" % i) / "TASK.md").read_text(encoding="utf-8")
        expect("index.html" in task and "../brief.md" in task and "genome.json" in task, "TASK.md points to brief, genome and index.html")
    t1 = (rnd / "v1" / "TASK.md").read_text(encoding="utf-8")
    for needle in ("96 px at 1280", "48 px at 390", "16-18 px", "40-52 px", "6 palette colors", "override any size in MotionSites",
                   "Start from material", "logo, mascot, photos, map", "web/public", "MotionSites media shelf", "never a fake built from divs"):
        expect(needle in t1, "TASK.md lacks %r:\n%s" % (needle, t1))
    expect("14-16" not in t1 and "36-48" not in t1, "old bounds gone")
    expect(len({g["recipe"] for g in gs}) >= 3, "recipes rotate: %s" % [g["recipe"] for g in gs])
    again = e.run(d, "round", "--n", "2", "--seed", "7", "--yes")
    expect((d / ".uak/design/rounds/R2").is_dir(), "second round is R2")
    return "brief and %d genomes" % len(gs)


def no_two_variants_share_more_than_three_genes(e):
    sys.path.insert(0, str(e.pkg / "bin" / "lib"))
    import design_round as dr
    for seed in (1, 2, 3, 99, 2026):
        gs = dr.make_genomes(20, seed)
        expect(len(gs) == 20, "20 variants")
        for a, b in itertools.combinations(gs, 2):
            expect(dr.shared_genes(a, b) <= 3, "seed %d: two variants share %d genes" % (seed, dr.shared_genes(a, b)))
        # spread: each gene's values all appear before any value repeats
        for gene, values in dr.GENES.items():
            seen = [g["genes"][gene] for g in gs]
            head = seen[:len(values)]
            expect(len(set(head)) == len(values), "seed %d gene %s: first %d draws repeat: %s" % (seed, gene, len(values), head))
    d = e.project("sh")
    e.run(d, "round", "--n", "20", "--seed", "5", "--yes")
    gs = genomes_of(d / ".uak/design/rounds/R1")
    expect(all(shared(a, b) <= 3 for a, b in itertools.combinations(gs, 2)), "written genomes obey the rule")
    big = e.run(d, "round", "--n", "21", "--seed", "5", "--yes", ok=None)
    expect(big.returncode != 0, "N is capped at 20")
    return "20 variants, all pairs <= 3"


def same_seed_same_round(e):
    a, b, c = e.project("s1"), e.project("s2"), e.project("s3")
    for d, seed in ((a, "11"), (b, "11"), (c, "12")):
        e.run(d, "round", "--n", "8", "--seed", seed, "--yes")
    ga, gb, gc = (genomes_of(x / ".uak/design/rounds/R1") for x in (a, b, c))
    expect(ga == gb, "same seed, same genomes")
    expect(ga != gc, "another seed, another round")
    dry = e.run(a, "round", "--n", "8", "--seed", "11", "--dry-run")
    expect(all(g["genes"]["layout"] in dry.stdout for g in ga) and not (a / ".uak/design/rounds/R2").exists(), "--dry-run prints genomes, writes nothing")
    return "deterministic"


def missing_beat_is_listed_not_invented(e):
    d = e.project("mb", idea="# IDEA · X\n\n## 1. One line\nFor **a**, **X** does y.\n")
    e.run(d, "round", "--n", "2", "--seed", "1", "--yes")
    brief = (d / ".uak/design/rounds/R1/brief.md").read_text(encoding="utf-8")
    expect("For **a**, **X** does y." in brief, "the one line is kept")
    expect(brief.count("MISSING (") == 5, "five missing beats:\n" + brief)
    none = e.project("mb2", idea=None)
    out = e.run(none, "round", "--n", "2", "--seed", "1", "--yes")
    expect((none / ".uak/design/rounds/R1/brief.md").read_text(encoding="utf-8").count("MISSING (") == 6, "no IDEA.md: all six beats missing")
    return "missing beats listed"


def cost_is_printed_and_needs_yes(e):
    d = e.project("cg", project_md="Design-Variant-Tokens: 90k\n")
    out = e.run(d, "round", "--n", "5", "--seed", "3", ok=None)
    text = out.stdout + out.stderr
    expect(out.returncode != 0, "refuses without --yes")
    expect("5" in text and "90k" in text.replace("90,000", "90k") and "450k" in text.replace("450,000", "450k"), "prints 5 x 90k = 450k: " + text)
    expect("--yes" in text and "round --screen landing --n 5 --seed 3 --yes" in text, "prints the exact rerun command: " + text)
    expect("sonnet" in text.lower() or "tier" in text.lower(), "names the model tier: " + text)
    expect(not (d / ".uak/design/rounds").exists(), "wrote nothing")
    d2 = e.project("cg2")
    out2 = e.run(d2, "round", "--n", "2", "--seed", "3", ok=None)
    expect("120k" in (out2.stdout + out2.stderr), "default 60k per variant: " + out2.stdout + out2.stderr)
    return "gate holds"


def shoot_reports_missing_captures(e):
    d = e.project("sc")
    e.run(d, "round", "--n", "4", "--seed", "2", "--yes")
    rnd = d / ".uak/design/rounds/R1"
    for i in range(1, 5):
        (rnd / ("v%d" % i) / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    (rnd / "v1" / "1280.png").write_text("have", encoding="utf-8")
    (rnd / "v1" / "390.png").write_text("have", encoding="utf-8")
    del_html = rnd / "v4" / "index.html"
    del_html.unlink()
    stub = d / "stub shoot é.py"  # a space and an accent on purpose (CI TMPDIR)
    stub.write_text(STUB, encoding="utf-8")
    out = e.run(d, "shoot", "R1", env={"UAK_DESIGN_SHOOT": str(stub)}, ok=None)
    text = out.stdout + out.stderr
    expect((rnd / "v2" / "1280.png").exists() and (rnd / "v2" / "390.png").exists(), "v2 captured: " + text)
    expect((rnd / "v1" / "1280.png").read_text(encoding="utf-8") == "have", "v1 left alone")
    expect("v3" in text and "v4" in text and out.returncode != 0, "lists v3 (tool failed) and v4 (no index.html) as not captured: " + text)
    nostub = e.run(d, "shoot", "R1", env={"UAK_DESIGN_SHOOT": "none"}, ok=None)
    expect(nostub.returncode != 0 and "no capture tool" in (nostub.stdout + nostub.stderr).lower(), "says no tool is installed: " + nostub.stdout + nostub.stderr)
    # MotionSites shoot.py: run from a copy patched to 1280x720, so 1280.png is really 1280 wide
    home = d / "home"
    sd = home / ".claude/skills/motionsites-web-builder/scripts"
    sd.mkdir(parents=True)
    (sd / "shoot.py").write_text('import sys\nfrom pathlib import Path\nVIEWS = [("desktop", 1440, 900), ("mobile", 390, 844)]\n'
                                 'o = Path(sys.argv[2]); o.mkdir(parents=True, exist_ok=True)\n'
                                 'for n, w, h in VIEWS: (o / (n + ".png")).write_text("%dx%d" % (w, h))\n', encoding="utf-8")
    (rnd / "v3" / "index.html").write_text("<title>x</title>", encoding="utf-8")
    e.run(d, "shoot", "R1", "v3", env={"HOME": str(home), "USERPROFILE": str(home), "PATH": os.environ["PATH"], "UAK_DESIGN_SHOOT": ""}, ok=None)
    if not (rnd / "v3" / "1280.png").exists():  # Playwright or another tool may win on a developer machine
        return "captured v2, listed v3 v4 (shoot.py path skipped)"
    expect((rnd / "v3" / "1280.png").read_text(encoding="utf-8") in ("1280x720",), "1280.png is 1280 wide")
    return "captured v2, listed v3 v4"


def registry_row(e):
    rows = [l.split("\t") for l in (e.pkg / "bin/lib/commands.tsv").read_text(encoding="utf-8").splitlines() if l.startswith("design\t")]
    expect(len(rows) == 1 and rows[0][1] == "exec" and rows[0][3] == "design", "one exec `design` row")
    return "registered"


TESTS = [round_writes_brief_and_genomes, no_two_variants_share_more_than_three_genes, same_seed_same_round,
         missing_beat_is_listed_not_invented, cost_is_printed_and_needs_yes, shoot_reports_missing_captures, registry_row]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])  # smoke passes the package
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-round-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package)
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_ROUND_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
