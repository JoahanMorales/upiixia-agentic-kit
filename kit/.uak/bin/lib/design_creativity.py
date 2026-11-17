#!/usr/bin/env python3
"""UAK-084: the creativity index. Every variant has a hero `composition` (measurable geometry) and a `motif` (the page's one
identity idea, from a family that does not depend on the domain); the capture records a composition signature and
`design shoot` flags siblings that came out the same and scores the round 0-100.
Why (colonIA R2, 2026-11-14): six variants bred from R1 all came out the same (headline left, hex map right); R1/v1 had
won with its papel picado, an identity no gene carried, so the children lost it. Standard library only."""
import itertools
import math
import re
from pathlib import Path

DEFAULT = 3
ARCHETYPES = {
    "poster": "the headline is the image: centered, at least 40% of the fold; the stage sits behind or around it",
    "full-bleed + bottom band": "the stage fills the fold edge to edge; the copy sits in a band along the bottom",
    "stage left, copy right": "the stage takes the left half; headline and actions on the right",
    "monument": "one object centered as a monument; the copy sits under it",
    "number grid": "an editorial grid led by one huge number; the copy hangs off its edges",
    "copy left, stage right": "headline and actions on the left; the stage takes the right half",
    "diagonal": "the headline runs on a diagonal or staircase across the fold; the stage fills the opposite corner",
    "frame": "the stage is a framed window in the middle; the headline wraps around its edges",
}
MOTIFS = {
    "craft or pattern of the place": "a craft, textile or pattern the place is known for, as the hero element",
    "everyday object": "one everyday object, drawn large, as the hero",
    "typographic poster": "letters as the image: one word or glyph set at poster scale",
    "cartography": "a map, route or grid treated as the picture",
    "documentary photography": "one photographic subject treated like a documentary frame",
    "illustrated character": "one illustrated character or mascot with a gesture",
    "specimen sheet": "a catalog or specimen layout: one thing, labeled",
    "signage": "painted or enamel signage: the page reads like a sign on a wall",
}
PRAISE = re.compile(r"\b(linda|lindo|bonit[ao]|creativ[ao]|identidad|me encanta|hermos[ao]|genial|excelente|love|beautiful|great)\b", re.I)
PRAISE_LAYOUT = re.compile(r"(layout|composici[oó]n|acomodaci[oó]n|distribuci[oó]n|estructura|orden)", re.I)
TOO_MANY = re.compile(r"(demasiad|muchos objetos|muchas cosas|too many|saturad|sobrecarg)", re.I)
# Calibrated on the real colonIA R2 (2026-11-14), six heroes the human called "todos son iguales" (headline left, visual right):
# their pairwise distances run 0.07-0.20 (mean 0.12, score 27) and four of the six sit under CLONE_UNDER; a poster hero or a
# bottom-band hero sits 0.19-0.32 from them. Color is the palette's job: it is not part of the distance.
CLONE_UNDER = 0.14  # signature distance below which two siblings count as the same hero
SCALE = 0.45        # a mean pairwise distance of this scores 100


def clamp(v):
    try:
        return max(1, min(5, int(v)))
    except (TypeError, ValueError):
        return DEFAULT


def creativity(cfg_value, flag=None):
    """The round's index 1-5: --creativity N over Design-Creativity in PROJECT.md over 3."""
    return clamp(flag) if flag is not None else clamp(cfg_value) if cfg_value else DEFAULT


def level_text(level):
    ask = {1: "refine the parent: keep its look and motif, change the details", 2: "stay close to the parent: same composition family, new details",
           3: "same family, a new identity: keep what the human liked, change the hero's composition", 4: "a clearly different composition; a new motif unless the human praised the parent's",
           5: "a new direction: nothing about the hero's layout or motif is borrowed"}
    return "- creativity: **%d/5** (%s)" % (level, ask[level])


def praised(note):
    return bool(note and PRAISE.search(note))


def praises_layout(note):
    return praised(note) and bool(PRAISE_LAYOUT.search(note))


def too_many_objects(note):
    return bool(note and TOO_MANY.search(note))


def _pool(names, used, avoid, rng):
    free = [n for n in names if n not in used and n not in avoid] or [n for n in names if n not in used] or list(names)
    return rng.pick(free)


def assign(children, level, seed, parents=None, notes=None):
    """Sets composition and motif on genomes or bred children (dicts; bred ones have "from" refs). parents: {"R1/v1": {"composition":
    ..., "motif": {...}, "motif_text": str or None}}; notes: {"R1/v1": note}. Siblings get distinct compositions and motif families
    while any remain; at level 3+ a bred child's composition differs from its parent's unless the human's note praises the layout;
    a child of a praised parent keeps its literal motif (the parent's family, and its text quoted in TASK.md)."""
    from design_round import Rng
    parents, notes = parents or {}, notes or {}
    comps, fams = [], []
    names, fam_names = list(ARCHETYPES), list(MOTIFS)
    for i, c in enumerate(children):
        rng = Rng(seed, "creativity%d" % i)
        refs = c.get("from") or []
        par = parents.get(refs[0]) if refs else None
        note = notes.get(refs[0], "") if refs else ""
        keep_comp = bool(par and par.get("composition") and (level <= 2 or praises_layout(note)))
        avoid = {par["composition"]} if par and par.get("composition") and level >= 3 and not keep_comp else set()
        if keep_comp and par["composition"] not in comps:
            comp = par["composition"]
        else:
            comp = _pool(names, set(comps), avoid, rng)
        comps.append(comp)
        c["composition"] = comp
        # a pre-084 parent has no genome family: it still passes its page's motif comment on (the family is then a free one)
        pfam = ((par or {}).get("motif") or {}).get("family")
        fam = (pfam if pfam in MOTIFS else next((f for f in fam_names if f not in fams), None)) if par and praised(note) else None
        if fam and fam not in fams:
            c["motif"] = {"family": fam, "inherited": True, "from": refs[0]}
            if par.get("motif_text"):
                c["motif"]["parent_text"] = par["motif_text"]
            if too_many_objects(note):
                c["motif"]["cut"] = "keep the motif, cut the objects"
        else:
            fam = _pool(fam_names, set(fams), set(), rng)
            c["motif"] = {"family": fam}
        fams.append(fam)
        c["creativity"] = level
    return children


def task_lines(genome):
    """The TASK.md section for a genome's composition and motif."""
    out = []
    if genome.get("creativity"):
        out.append(level_text(genome["creativity"]))
    comp = genome.get("composition")
    if comp in ARCHETYPES:
        out.append("- composition: **%s** (the hero's geometry, measured by the capture: %s)" % (comp, ARCHETYPES[comp]))
    m = genome.get("motif") or {}
    if m.get("family") in MOTIFS:
        out.append("- motif: **%s** (%s). ONE motif carried strongly, few objects: identity, not quantity. Write it as the first line of "
                   "`index.html`: `<!-- motif: <the idea in one sentence> -->`" % (m["family"], MOTIFS[m["family"]]))
        if m.get("inherited"):
            quote = m.get("parent_text")
            out.append("- the human praised %s: keep ITS motif%s%s" % (m.get("from"), (' as written in its index.html: "%s"' % quote) if quote else " (its index.html has no motif comment: read the page)",
                                                                  "; the human said it had too many objects: keep the motif, cut the objects" if m.get("cut") else ""))
    return out


MOTIF_COMMENT = re.compile(r"<!--\s*motif:\s*(.*?)\s*-->", re.S | re.I)


def read_motif(html_path):
    """The `<!-- motif: ... -->` comment of an index.html (first 4 KB), or None."""
    try:
        text = Path(html_path).read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return None
    m = MOTIF_COMMENT.search(text)
    return " ".join(m.group(1).split())[:300] if m else None


def _mass(sig):
    """The visual mass {centroid, box} the capture measured in the screenshot; a signature without it (no browser pixels) falls
    back to the stage rect and its focal point."""
    m = sig.get("mass")
    if isinstance(m, dict) and m.get("centroid") and m.get("box"):
        return m
    if sig.get("stage"):
        return {"centroid": sig.get("focal") or [0.5, 0.5], "box": sig["stage"]}
    return None


def _head(sig):
    h = sig["head"]
    return ((h[0] + h[2]) / 2.0, (h[1] + h[3]) / 2.0, h[2] - h[0], h[3] - h[1])


def distance(a, b):
    """0 (the same hero) to ~1: the headline's center and size (0.4) plus where the visual mass sits (centroid 0.35, box 0.25).
    Needs {"head": [l, t, r, b], "mass": {"centroid", "box"}} normalized to the fold."""
    (ax, ay, aw, ah), (bx, by, bw, bh) = _head(a), _head(b)
    head = 0.3 * math.hypot(ax - bx, ay - by) + 0.1 * (abs(aw - bw) + abs(ah - bh)) / 2.0
    ma, mb = _mass(a), _mass(b)
    if ma and mb:
        mass = 0.35 * math.hypot(ma["centroid"][0] - mb["centroid"][0], ma["centroid"][1] - mb["centroid"][1]) \
            + 0.25 * sum(abs(x - y) for x, y in zip(ma["box"], mb["box"])) / 4.0
    else:
        mass = 0.0 if not (ma or mb) else 0.3
    return head + mass


def signatures(rnd):
    """{variant: signature at 1920} for the captured variants of a round folder."""
    import json
    out = {}
    for v in sorted(Path(rnd).glob("v[0-9]*"), key=lambda p: int(p.name[1:]) if p.name[1:].isdigit() else 0):
        try:
            sig = (json.loads((v / "qa.json").read_text(encoding="utf-8")).get("1920") or {}).get("sig")
        except (OSError, ValueError):
            continue
        if isinstance(sig, dict) and sig.get("head"):
            out[v.name] = sig
    return out


def _fmt(r):
    return "[" + ",".join("%.2f" % x for x in r) + "]" if r else "none"


def analyze_sigs(sigs):
    """(score 0-100 or None, [(variant, clone warning)]). A variant is a clone of the nearest EARLIER sibling closer than
    CLONE_UNDER; the score is the mean pairwise distance scaled so SCALE is 100."""
    names = list(sigs)
    if len(names) < 2:
        return None, []
    dists, warns = [], []
    for j, b in enumerate(names):
        near = None
        for a in names[:j]:
            d = distance(sigs[a], sigs[b])
            dists.append(d)
            if d < CLONE_UNDER and (near is None or d < near[0]):
                near = (d, a)
        if near:
            mb = _mass(sigs[b])
            warns.append((b, "clone of %s: same hero composition (headline %s, visual mass %s)" % (near[1], _fmt(sigs[b].get("head")), _fmt(mb["box"]) if mb else "none")))
    return min(100, int(round(100.0 * (sum(dists) / len(dists)) / SCALE))), warns


def analyze(rnd):
    return analyze_sigs(signatures(rnd))
