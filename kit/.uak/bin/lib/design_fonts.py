#!/usr/bin/env python3
"""Exact Google Fonts pairs for the variants of a design round (UAK-071).

    python3 design_fonts.py check DIR     DIR is a round (v*/index.html + genome.json) or one variant; prints a warning per
                                          page whose loaded Google Fonts differ from the pair its genome.json assigned

Why (AXIA R3, 2026-11-11): the `type` gene said "serif display" and all six builders picked the same pair (Fraunces + Geist);
the human: "the fonts in all of them are the same now, they need more variety". A pair is now assigned, not left to the agent:
every `type` value has a pool of vetted pairs, a round never repeats a display or a body face, a bred child keeps its parent's
pair unless `type` mutated, and a new project's round 1 avoids the faces of past directions. Inter, Roboto, Arial, Geist and
Helvetica are never a display face; Syne is left out (the human called it "horrible").
Each pair: (display face, its weights, body face, its weights). Weights are ';'-separated, as in the css2 URL.
Same seed, same pairs. Python 3.8+ standard library only."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

B = "400;600"
POOLS = {
    "grotesk": [
        ("Schibsted Grotesk", "700", "Source Serif 4", B), ("Space Grotesk", "700", "Public Sans", B),
        ("Bricolage Grotesque", "700", "Newsreader", B), ("Familjen Grotesk", "700", "Libre Franklin", B),
        ("Darker Grotesque", "800", "Literata", B), ("Archivo", "800", "Lora", B),
    ],
    "geometric": [
        ("Outfit", "700", "Figtree", B), ("Poppins", "700", "DM Sans", B), ("Urbanist", "700", "Nunito Sans", B),
        ("Lexend", "700", "Mulish", B), ("Sora", "700", "Manrope", B), ("Plus Jakarta Sans", "800", "Open Sans", B),
    ],
    "serif display": [
        ("DM Serif Display", "400", "Albert Sans", B), ("Fraunces", "700", "Hanken Grotesk", B),
        ("Playfair Display", "700", "Jost", B), ("Instrument Serif", "400", "Barlow", B),
        ("Young Serif", "400", "Be Vietnam Pro", B), ("Gloock", "400", "Crimson Pro", B),
    ],
    "mono-led": [
        ("IBM Plex Mono", "600", "IBM Plex Sans", B), ("JetBrains Mono", "700", "Red Hat Text", B),
        ("Space Mono", "700", "Spline Sans", B), ("DM Mono", "500", "Commissioner", B),
        ("Fira Code", "600", "Overpass", B), ("Martian Mono", "600", "Noto Sans", B),
    ],
    "rounded": [
        ("M PLUS Rounded 1c", "700", "Karla", B), ("Nunito", "800", "Rubik", B), ("Quicksand", "700", "Cabin", B),
        ("Fredoka", "600", "Mukta", B), ("Baloo 2", "700", "Sarabun", B), ("Comfortaa", "700", "Kumbh Sans", B),
    ],
    "condensed": [
        ("Big Shoulders Display", "800", "Work Sans", B), ("Barlow Condensed", "700", "Chivo", B),
        ("Oswald", "600", "Heebo", B), ("Anton", "400", "Titillium Web", B),
        ("Bebas Neue", "400", "Fira Sans", B), ("Saira Condensed", "700", "Hind", B),
    ],
}
NEVER_DISPLAY = {"inter", "roboto", "arial", "geist", "helvetica", "syne"}
GF = re.compile(r"fonts\.googleapis\.com/css2?\?([^\"'\s)>]+)", re.I)


def _key(name):
    return re.sub(r"\s+", " ", str(name)).strip().lower()


def pair_dict(p):
    d, dw, b, bw = p
    return {"display": d, "display_weights": dw, "body": b, "body_weights": bw, "url": url(p)}


def _fam(name, weights):
    q = name.replace(" ", "+")
    return "family=%s:wght@%s" % (q, weights) if ";" in weights or weights != "400" else "family=" + q


def url(p):
    """The css2 URL for a pair (a single regular weight takes no axis)."""
    d, dw, b, bw = p
    return "https://fonts.googleapis.com/css2?%s&%s&display=swap" % (_fam(d, dw), _fam(b, bw))


def faces(fonts):
    return {_key(fonts.get("display", "")), _key(fonts.get("body", ""))} - {""}


def all_pairs():
    return [p for pool in POOLS.values() for p in pool]


def _rng(seed, salt):
    from design_round import Rng
    return Rng(seed, salt)


def assign(types, seed, avoid_faces=()):
    """One pair per entry of `types` (the `type` gene value of each variant, in order): the pool of that value, no display or
    body face used twice in the round, none of avoid_faces (past directions). If a pool runs dry the other pools lend pairs; if
    the avoided faces leave nothing, they are given up before the round repeats a face. Returns pair dicts."""
    avoid = {_key(a) for a in avoid_faces}
    used, out = set(), []
    for i, t in enumerate(types):
        rng = _rng(seed, "fonts%d" % i)
        own = POOLS.get(t, [])
        rest = [p for p in all_pairs() if p not in own]
        pick = None
        for pool, banned in ((own, used | avoid), (rest, used | avoid), (own, used), (rest, used), (own + rest, set())):
            free = [p for p in pool if not ({_key(p[0]), _key(p[2])} & banned)]
            if free:
                pick = rng.pick(free)
                break
        used |= {_key(pick[0]), _key(pick[2])}
        out.append(pair_dict(pick))
    return out


def for_type(type_value, seed, avoid_faces=()):
    """A pair of the type's pool that avoids the given faces (a bred child whose `type` mutated)."""
    return assign([type_value], seed, avoid_faces)[0]


def inherit(children, parents, seed):
    """Sets child["fonts"] on bred children (design_breed.py). parents: {"R1/v3": {"genes": {...}, "fonts": {...} or None}}.
    A mutation keeps its parent's pair unless `type` mutated (then a new pair from the new type's pool, not the parent's
    faces); a crossover keeps the pair of the parent its `type` came from; a wildcard gets a pair no pick has. A parent from
    before fonts existed gets one from its type's pool, the same for all its children."""
    def parent_fonts(ref):
        par = parents[ref]
        if not isinstance(par.get("fonts"), dict) or not par["fonts"].get("display"):
            par["fonts"] = for_type(par["genes"]["type"], seed + sum(map(ord, ref)))
        return par["fonts"]
    picked = set()
    for ref in parents:
        picked |= faces(parent_fonts(ref))
    used = set()
    for i, c in enumerate(children):
        if c["kind"] == "mutation" and c.get("mutated") != "type":
            c["fonts"] = dict(parent_fonts(c["from"][0]))
        elif c["kind"] == "crossover":
            c["fonts"] = dict(parent_fonts(c["taken"]["type"]))
        else:
            avoid = used | (faces(parent_fonts(c["from"][0])) if c["kind"] == "mutation" else picked)
            c["fonts"] = for_type(c["genes"]["type"], seed + 7 * i, avoid)
            used |= faces(c["fonts"])
    return children


def parse_url_families(text):
    """Family names a page loads from Google Fonts (<link> or @import), in order."""
    out = []
    for m in GF.finditer(text or ""):
        for fam in re.findall(r"family=([^&:;]+)", m.group(1).replace("&amp;", "&")):
            name = re.sub(r"\s+", " ", fam.replace("+", " ")).strip()
            if name and name not in out:
                out.append(name)
    return out


def page_fonts(path):
    try:
        return parse_url_families(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []


def winning_fonts(base, rnd, vid):
    """The pair a winning variant's page loads, {display, body} or None: what the taste profile records for a direction."""
    g = _read(Path(base) / rnd / vid / "genome.json") or {}
    if isinstance(g.get("fonts"), dict) and g["fonts"].get("display"):
        return {"display": g["fonts"]["display"], "body": g["fonts"].get("body", "")}
    got = page_fonts(Path(base) / rnd / vid / "index.html")
    return {"display": got[0], "body": got[1] if len(got) > 1 else ""} if got else None


def past_faces(directions):
    """Faces of past directions (dicts with an optional `fonts`), for assign(avoid_faces=...)."""
    out = set()
    for d in directions:
        f = d.get("fonts") if isinstance(d, dict) else None
        if isinstance(f, dict):
            out |= faces(f)
    return out


def _read(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def check(path):
    """[(file, message)]: pages whose loaded Google Fonts differ from the pair genome.json assigned."""
    p = Path(path)
    vdirs = [p] if (p / "genome.json").is_file() else sorted(d for d in p.glob("v*") if (d / "genome.json").is_file())
    out = []
    for d in vdirs:
        g = _read(d / "genome.json") or {}
        want = g.get("fonts")
        page = d / "index.html"
        if not isinstance(want, dict) or not want.get("display") or not page.is_file():
            continue
        got = page_fonts(page)
        want_set = {w for w in (want["display"], want.get("body")) if w}
        if {_key(x) for x in got} != {_key(x) for x in want_set}:
            out.append((str(page), "%s loads %s, TASK.md assigned %s + %s: load the assigned pair (%s)" % (
                d.name, " + ".join(got) or "no Google Fonts", want["display"], want.get("body", "-"), want.get("url", ""))))
    return out


def main(argv):
    if len(argv) == 2 and argv[0] == "check":
        for f, msg in check(argv[1]):
            print("%s:1 · %s" % (f, msg))
        return 0
    print("Usage: design_fonts.py check DIR", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
