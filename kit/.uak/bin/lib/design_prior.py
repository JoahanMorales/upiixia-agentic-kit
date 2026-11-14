#!/usr/bin/env python3
"""The kit's default design prior: what real rounds taught, as traits, shipped in kit/.uak/settings/design-prior.json.

    python3 design_prior.py build --from PROFILE.json [--from ...] [--out FILE]      (maintainers, at release; scripts/design_prior.py)
    python3 design_prior.py show [FILE]

A prior is {gene: {value: weight}} with its evidence: per value, how often it was picked and shown and across how many
distinct projects. Only traits: no names, no project names, no hex, no pages, no notes text. A value enters only when it
was picked in at least MIN_PROJECTS distinct projects (STYLE_PROJECTS for the stylistic genes: type, scale, color, ground, so
the prior never pushes every team to the same look) and its weight is clearly off neutral (lift over the gene's own pick
rate: >= LIFT_UP or <= LIFT_DOWN). Everything else stays neutral, i.e. absent. `uak design round` draws from it when the
human has no personal or team profile, and under one when there is (the profile wins on the values it has seen).
Why (2026-11-12, the human): "I thought this was becoming a default of the kit: these iterations are so that anyone gets the
best version on GitHub, not that everyone builds their own model"; the profile lived only in ~/.uak/taste of one machine.
Python 3.8+ standard library only."""
import json
import os
import sys
import time
from pathlib import Path

MIN_PROJECTS = 2
STYLE_PROJECTS = 3
# Palette traits (UAK-078) are style too: they need 3 projects, like type, scale, color and ground.
STYLISTIC = ("type", "scale", "color", "ground", "palette_hue", "palette_neutral", "palette_sat_hues", "palette_sat_share")
LIFT_UP = 1.25
LIFT_DOWN = 0.8
VERSION = 1
NEUTRAL = 0.5  # the weight of a value the prior says nothing about; a trait's weight is NEUTRAL x its lift
BLEND_PROFILE = 0.75  # when both know a value: this share profile, the rest prior


def default_path():
    return Path(os.path.dirname(os.path.abspath(__file__))).parents[1] / "settings" / "design-prior.json"


def build(profiles, today=None):
    """profiles: personal/team taste profile dicts (design_taste's schema). Returns the prior document."""
    cells = {}  # (gene, value) -> {"shown", "picked", "projects": set of projects that picked it}
    gene_tot = {}
    projects, rounds, picks = set(), 0, 0
    for doc in profiles:
        for key, r in (doc.get("rounds") or {}).items():
            project = str(key).split(":", 1)[0]
            projects.add(project)
            rounds += 1
            picks += int(r.get("picks") or 0)
            for gene, vals in (r.get("genes") or {}).items():
                for value, c in vals.items():
                    cell = cells.setdefault((gene, value), {"shown": 0, "picked": 0, "projects": set()})
                    cell["shown"] += int(c.get("shown") or 0)
                    cell["picked"] += int(c.get("picked") or 0)
                    if c.get("picked"):
                        cell["projects"].add(project)
                    t = gene_tot.setdefault(gene, [0, 0])
                    t[0] += int(c.get("picked") or 0)
                    t[1] += int(c.get("shown") or 0)
    genes = {}
    for (gene, value), c in sorted(cells.items()):
        need = STYLE_PROJECTS if gene in STYLISTIC else MIN_PROJECTS
        if len(c["projects"]) < need or not c["shown"]:
            continue
        base = (gene_tot[gene][0] / float(gene_tot[gene][1])) if gene_tot[gene][1] else 0
        lift = (c["picked"] / float(c["shown"])) / base if base else 0
        if not (lift >= LIFT_UP or lift <= LIFT_DOWN):
            continue
        w = max(0.05, min(0.95, NEUTRAL * lift))  # neutral is 0.5, what a draw gives a value nobody knows
        genes.setdefault(gene, {})[value] = {"weight": round(w, 3), "lift": round(lift, 2), "picked": c["picked"], "shown": c["shown"], "projects": len(c["projects"])}
    return {"version": VERSION, "generated": today or time.strftime("%Y-%m-%d", time.gmtime()),
            "evidence": {"profiles": len(profiles), "projects": len(projects), "rounds": rounds, "picks": picks},
            "rules": {"min_projects": MIN_PROJECTS, "stylistic_genes": list(STYLISTIC), "stylistic_min_projects": STYLE_PROJECTS,
                      "lift_up": LIFT_UP, "lift_down": LIFT_DOWN},
            "genes": genes}


def load(path=None):
    """The prior's weights {gene: {value: weight}} and its document, or (None, None) when there is none or it is broken."""
    p = Path(path or os.environ.get("UAK_DESIGN_PRIOR") or default_path())
    if str(p) == "none":  # tests and maintainers: draw as before the prior existed
        return None, None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        genes = doc["genes"]
        w = {g: {v: float(e["weight"]) for v, e in vals.items()} for g, vals in genes.items() if isinstance(vals, dict)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None, None
    return (w or None), doc


def describe(doc):
    ev = doc.get("evidence", {})
    return "kit prior v%s: %d rounds, %d projects, %d picks (%s)" % (doc.get("version"), ev.get("rounds", 0), ev.get("projects", 0), ev.get("picks", 0), doc.get("generated"))


def blend(profile_w, prior_w):
    """The weight of gene/value and where it came from: (weight, "taste"|"prior"|"both"|None)."""
    def get(table, g, v):
        return (table or {}).get(g, {}).get(v)
    def pick(g, v):
        a, b = get(profile_w, g, v), get(prior_w, g, v)
        if a is not None and b is not None:
            return BLEND_PROFILE * a + (1 - BLEND_PROFILE) * b, "both", a, b
        if a is not None:
            return a, "taste", a, None
        if b is not None:
            return b, "prior", None, b
        return 0.5, None, None, None
    return pick


def main(argv):
    args = list(argv)
    if args[:1] == ["build"]:
        srcs, out, i = [], None, 1
        while i < len(args):
            if args[i] == "--from" and i + 1 < len(args):
                srcs.append(args[i + 1])
                i += 2
            elif args[i] == "--out" and i + 1 < len(args):
                out = args[i + 1]
                i += 2
            else:
                print("Usage: design_prior.py build --from PROFILE.json [--from ...] [--out FILE]", file=sys.stderr)
                return 2
        if not srcs:
            print("design_prior: --from PROFILE.json is required (a personal profile from ~/.uak/taste/ or a team .uak/design/taste.json)", file=sys.stderr)
            return 2
        docs = []
        for s in srcs:
            try:
                docs.append(json.loads(Path(os.path.expanduser(s)).read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                print("design_prior: cannot read %s: %s" % (s, exc), file=sys.stderr)
                return 1
        doc = build(docs)
        target = Path(out) if out else default_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8", newline="\n")
        print("DESIGN_PRIOR written %s: %s" % (target, describe(doc)))
        for g, vals in doc["genes"].items():
            print("  %-10s %s" % (g, "; ".join("%s %.2f (lift %.2f, %d/%d, %d projects)" % (v, e["weight"], e["lift"], e["picked"], e["shown"], e["projects"]) for v, e in vals.items())))
        if not doc["genes"]:
            print("  no trait reached the bar: the prior stays neutral (%d projects; a value needs %d, a stylistic gene %d)" % (doc["evidence"]["projects"], MIN_PROJECTS, STYLE_PROJECTS))
        return 0
    if args[:1] == ["show"]:
        w, doc = load(args[1] if len(args) > 1 else None)
        print(describe(doc) if doc else "no prior")
        return 0
    print("Usage: design_prior.py build --from PROFILE.json [--from ...] [--out FILE] | show [FILE]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
