#!/usr/bin/env python3
"""uak design round --from R<k>: the next round is bred from the human's picks (R<k>/picks.json).

    python3 design_breed.py [round] --from R<k> [--n N] [--seed S] [--dry-run] [--yes]

About half of the N children are one-gene mutations of a pick, a third crossovers of two picks (every gene from one
parent or the other, at least one from each), and 2 are wildcards that take no pick's value where another exists.
Two children that are not kin (no parent in common) never share more than MAX_SHARED genes; kin cannot, by design
(a one-gene mutation shares 7 genes with its parent and with its siblings), so only identical genomes are refused
among them. Each genome.json records "from" (parents as "R1/v3"), "kind", and "mutated" or "taken"; the human's
notes on the parents land in the child's TASK.md. Stop rule: when the first pick is a child of the previous round's
first pick, and that one a child of the one before, the direction has converged and the command prints
a message naming R<k>/v<i> as the direction instead of breeding.
Why (roadmap F3, Nov 2026): picking among 20 unrelated designs finds a taste; bred rounds refine it, and a stop rule
keeps the human from picking the same design for ever. Imports its genome data from design_round.py (UAK-057).
Same seed, same children. Python 3.8+ standard library only."""
import itertools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pathlib import Path  # noqa: E402

from design_round import (DEFAULT_N, DEFAULT_TIER, GENES, MAX_N, MAX_SHARED, RECIPES, Rng, cfg, fmt_tokens,  # noqa: E402
                          parse_tokens, project_root, shared_genes, task_text)

WILDCARDS = 2
TRIES = 100


def _count_plan(n, npicks):
    wild = min(WILDCARDS, n // 2)
    mut = min(int(n / 2 + 0.5), n - wild)
    cross = n - mut - wild
    if npicks < 2:  # nobody to cross with
        mut, cross = mut + cross, 0
    return mut, cross, wild


def kin(a, b):
    """Children with a parent in common."""
    return bool(set(a["from"]) & set(b["from"]))


def acceptable(children):
    for a, b in itertools.combinations(children, 2):
        s = shared_genes(a, b)
        if s >= len(GENES) or (not kin(a, b) and s > MAX_SHARED):
            return False
    return True


def _fits(child, out):
    return all(shared_genes(child, o) < len(GENES) and (kin(child, o) or shared_genes(child, o) <= MAX_SHARED) for o in out)


def _attempt(picks, n, seed, salt):
    """picks: [{"ref": "R1/v3", "genes": {...}, "recipe": R}] in the human's order. Child by child, each redrawn until
    it fits the ones before; None when a child cannot (the caller restarts with another salt)."""
    rng = Rng(seed, "breed%d" % salt)
    mut, cross, wild = _count_plan(n, len(picks))
    pairs = list(itertools.combinations(range(len(picks)), 2))

    def mutation(i):
        p = picks[i % len(picks)]  # round-robin from the first pick, which the human likes best
        gene = rng.pick(list(GENES))
        genes = dict(p["genes"])
        genes[gene] = rng.pick([v for v in GENES[gene] if v != p["genes"][gene]])
        return {"kind": "mutation", "from": [p["ref"]], "mutated": gene, "genes": genes, "recipe": p["recipe"]}

    def crossover(i):
        a, b = (picks[x] for x in pairs[i % len(pairs)])
        taken = {g: rng.pick([a, b]) for g in GENES}
        genes = {g: taken[g]["genes"][g] for g in GENES}
        if len({t["ref"] for t in taken.values()}) < 2 or genes == a["genes"] or genes == b["genes"]:
            return None
        return {"kind": "crossover", "from": [a["ref"], b["ref"]], "taken": {g: taken[g]["ref"] for g in GENES}, "genes": genes, "recipe": a["recipe"]}

    def wildcard(i, attempt=0):
        genes = {}
        before = [o["genes"] for o in out if o["kind"] == "wildcard"]
        for g, vals in GENES.items():
            used = {p["genes"][g] for p in picks}
            seen = {b[g] for b in before}
            # First share nothing with the picks (two wildcards may then share a gene or two, within the rule). If the
            # rule fails 100 times, give up the second wildcard's pick-avoidance where it must differ from the first.
            tiers = [used] if attempt < 100 else [used | seen, seen, set()]
            for avoid in tiers:
                free = [v for v in vals if v not in avoid]
                if free:
                    break
            else:
                low = min(sum(1 for p in picks if p["genes"][g] == v) for v in vals)
                free = [v for v in vals if sum(1 for p in picks if p["genes"][g] == v) == low]
            genes[g] = rng.pick(free)
        return {"kind": "wildcard", "from": [], "genes": genes, "recipe": RECIPES[(i + len(picks)) % len(RECIPES)]}

    out = []
    for make, count in ((wildcard, wild), (mutation, mut), (crossover, cross)):  # the hardest constraint first
        for i in range(count):
            for attempt in range(300):
                c = make(i, attempt) if make is wildcard else make(i)
                if c and _fits(c, out):
                    out.append(c)
                    break
            else:
                return None
    order = {"mutation": 0, "crossover": 1, "wildcard": 2}
    return sorted(out, key=lambda c: order[c["kind"]])


def breed(picks, n, seed):
    for salt in range(TRIES):
        got = _attempt(picks, n, seed, salt)
        if got:
            return got
    raise RuntimeError("could not breed %d children from %d picks that keep the diversity rule (seed %s)" % (n, len(picks), seed))


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def first_pick(base, rnd):
    picks = _read(base / rnd / "picks.json") or {}
    ids = [i for i in picks.get("picked", []) if isinstance(i, str)]
    return ids[0] if ids else None


def converged(base, rnd):
    """The first pick of rnd descends from the first pick of the round before it, and that one from the one before
    it, each at most one gene away from its parent. Returns the first pick's id or None."""
    cur_round, cur = rnd, first_pick(base, rnd)
    if not cur:
        return None
    start = cur
    for _ in range(2):
        g = _read(base / cur_round / cur / "genome.json") or {}
        link = None
        for ref in g.get("from", []):
            pr, pv = ref.split("/", 1)
            pg = _read(base / pr / pv / "genome.json")
            if pg and first_pick(base, pr) == pv and shared_genes(g["genes"], pg["genes"]) >= len(GENES) - 1:
                link = (pr, pv)
        if not link:
            return None
        cur_round, cur = link
    return start


def child_task(rnd_name, i, genome, notes, parents, all_picks):
    text = task_text(rnd_name, i, genome, "landing")
    lines = ["", "## What the human said about the parents (bred from %s)" % ("/".join(parents) if parents else "no parent: a wildcard")]
    if genome["kind"] == "wildcard":
        lines.append("This is a wildcard: it shares no value with the picks where another exists. The human's notes on the picks, to avoid repeating their mistakes:")
        refs = all_picks
    else:
        refs = genome["from"]
    said = False
    for ref in refs:
        note = notes.get(ref.split("/", 1)[1], "")
        if note:
            lines.append("- %s: %s" % (ref, note))
            said = True
    if not said:
        lines.append("- (no notes)")
    if genome["kind"] == "mutation":
        lines.append("Only the gene `%s` changed from the parent; keep the rest of the parent's look." % genome["mutated"])
    elif genome["kind"] == "crossover":
        lines.append("Genes taken from: " + ", ".join("%s <- %s" % (g, genome["taken"][g]) for g in GENES))
    return text + "\n".join(lines) + "\n"


def run(argv):
    src, n, seed, dry, yes = None, DEFAULT_N, 1, False, False
    args = list(argv[1:] if argv[:1] == ["round"] else argv)
    it = iter(args)
    try:
        for a in it:
            if a == "--from":
                src = next(it)
            elif a == "--n":
                n = int(next(it))
            elif a == "--seed":
                seed = int(next(it))
            elif a == "--dry-run":
                dry = True
            elif a == "--yes":
                yes = True
            elif a == "--screen":
                if next(it) != "landing":
                    raise ValueError(a)
            else:
                raise ValueError(a)
    except (StopIteration, ValueError):
        print("Usage: design round --from R<k> [--n N] [--seed S] [--dry-run] [--yes]", file=sys.stderr)
        return 2
    if not src or not re.match(r"^R\d+$", src) or not 1 <= n <= MAX_N:
        print("design round --from: R<k> and --n 1..%d required" % MAX_N, file=sys.stderr)
        return 2
    root = project_root()
    base = root / ".uak" / "design" / "rounds"
    sdir = base / src
    sp = _read(sdir / "picks.json")
    if not sp or not sp.get("picked"):
        print("design round --from %s: no picks yet (%s); pick first: bash .uak/bin/uak design-gallery --round %s" % (src, sdir / "picks.json", src), file=sys.stderr)
        return 1
    done = converged(base, src)
    if done:
        print("DESIGN_ROUND converged: %s/%s is the direction (same line for two rounds). Lock it: /uak-design-lock step 5 fills DESIGN.md from %s/%s/genome.json." % (src, done, src, done))
        return 0
    picks = []
    for pid in sp["picked"]:
        g = _read(sdir / pid / "genome.json")
        if not g or "genes" not in g:
            print("design round --from: %s/%s has no genome.json" % (src, pid), file=sys.stderr)
            return 1
        picks.append({"ref": "%s/%s" % (src, pid), "genes": g["genes"], "recipe": g.get("recipe", RECIPES[0])})
    children = breed(picks, n, seed)
    if dry:
        for i, c in enumerate(children, 1):
            via = ("mutated " + c["mutated"]) if c["kind"] == "mutation" else ("from " + " x ".join(c["from"])) if c["kind"] == "crossover" else "no parent"
            print("v%d  %-9s %s | %s | recipe %s" % (i, c["kind"], via, " | ".join("%s=%s" % (k, c["genes"][k]) for k in GENES), c["recipe"]))
        return 0
    per = parse_tokens(cfg(root, "Design-Variant-Tokens", ""))
    tier = cfg(root, "Design-Variant-Model", DEFAULT_TIER)
    print("DESIGN_ROUND cost: %d variants x %s tokens = %s tokens, model tier %s" % (n, fmt_tokens(per), fmt_tokens(per * n), tier))
    if not yes:
        print("DESIGN_ROUND refused: nothing written. Rerun with --yes (or ask the human to run it): bash .uak/bin/uak design round --from %s --n %d --seed %d --yes" % (src, n, seed), file=sys.stderr)
        return 3
    k = 1
    while (base / ("R%d" % k)).exists():
        k += 1
    name = "R%d" % k
    rnd = base / name
    rnd.mkdir(parents=True)
    try:
        brief = (sdir / "brief.md").read_text(encoding="utf-8")
    except OSError:
        brief = "# Brief\n\n(the source round had no brief.md)\n"
    with open(str(rnd / "brief.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(brief)
    notes = sp.get("notes") if isinstance(sp.get("notes"), dict) else {}
    for i, c in enumerate(children, 1):
        v = rnd / ("v%d" % i)
        v.mkdir()
        doc = {"id": "%s-v%d" % (name, i), "round": name, "variant": i, "seed": seed, "screen": "landing"}
        doc.update(c)
        with open(str(v / "genome.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        with open(str(v / "TASK.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(child_task(name, i, c, notes, c["from"], [p["ref"] for p in picks]))
    print("DESIGN_ROUND %s: bred from %s (%d picks): %d mutations, %d crossovers, %d wildcards" % (
        name, src, len(picks), *[sum(1 for c in children if c["kind"] == kd) for kd in ("mutation", "crossover", "wildcard")]))
    print("Next: one agent per variant follows v<i>/TASK.md, then: bash .uak/bin/uak design shoot %s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
