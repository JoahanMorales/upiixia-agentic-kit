#!/usr/bin/env python3
"""uak design: rounds of landing-page variants whose designs differ on purpose.

    bash .uak/bin/uak design round [--screen landing] [--n N] [--seed S] [--dry-run] [--yes]
    bash .uak/bin/uak design shoot R<k> [v<i> ...]

`round` writes .uak/design/rounds/R<k>/brief.md (the landing's story beats from IDEA.md; a beat IDEA.md does not
have is listed as MISSING, never invented) and v<i>/genome.json + v<i>/TASK.md for each of N variants (default 8,
max 20). A genome is 9 genes (8 before UAK-068: older genome.json lack `stage`) with fixed value lists (GENES) plus a recipe; no two variants of a round share more than
MAX_SHARED genes, and each gene's values all appear before any repeats. The same --seed gives the same round.
It prints the cost (N x Design-Variant-Tokens from PROJECT.md, default 60k, and the model tier) and writes nothing
without --yes. `shoot` captures v<i>/1280.png and v<i>/390.png for any variant whose PNGs are missing.
GENES, RECIPES, MAX_SHARED, make_genomes and shared_genes are importable (UAK-059 reuses them).
UAK-063: a new project's round is seeded by the human's taste profile (design_taste.py; liked gene values likelier, the last
2 variants wildcards that ignore it, nothing sharing more than 5 genes with another project's winner unless --allow-repeat), by the project
(default seed from its name; brand colors from IDEA.md section 0, CSS custom properties and SVG fills go into brief.md; imagery
values the project has no material for are drawn less) and each genome.json records "why" per gene.
Why (F0, Nov 11 2026): the kit's frontends scored 2.8 / 5 because every variant of an agent looks alike; variety has to
be forced by the tool, not hoped for. Python 3.8+ standard library only; no network, no browser unless `shoot`."""
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STILL = "still (no animation)"
# The genome. Order matters (it is the order of genome.json). Scale values stay inside the F0 bounds
# (docs/design/failures.md: display type <= 96 px on a landing hero, <= 48 px at 390, body 16-18 px, buttons 40-52 px).
GENES = {
    "type": ["grotesk", "geometric", "serif display", "mono-led", "rounded", "condensed"],
    "scale": ["restrained", "standard", "bold"],
    "color": ["ink + one accent", "brand duo", "dark media", "light paper", "saturated field"],
    "layout": ["split hero", "full-bleed media", "editorial column", "product screen first", "scroll story"],
    "components": ["hairline", "solid blocks", "glass", "soft"],
    "imagery": ["product screenshot", "video loop", "3D cut-out", "illustration", "type only"],
    "motion": ["still", "entrance", "scroll", "pointer"],
    "voice": ["plain", "bold claim", "numbers first"],
    # Why (AXIA R1-R2, 2026-11-11): the hero is a stand-by screen for a hackathon projector; how it moves is a choice.
    "stage": ["three.js scene", "three.js point cloud from the team's own image", "three.js scroll-driven", "canvas 2D generative",
              "SVG/CSS animation", "real video with a live overlay", STILL],
}
AT_MOST_ONCE = {"stage": STILL}  # drawn at most once per round: a room turns its head for motion
SCALE_BOUNDS = {  # max hero display px at 1280 wide (landing-story: 96 px ceiling, 48 px at 390)
    "restrained": "hero display at most 56 px",
    "standard": "hero display at most 72 px",
    "bold": "hero display at most 96 px",
}
RECIPES = ["motionsites", "landing-story", "frontend-design", "design-taste-frontend"]
MAX_SHARED = 3
MAX_N = 20
DEFAULT_N = 8
DEFAULT_TOKENS = 60000
DEFAULT_TIER = "sonnet (standard subagent tier)"
BEATS = ["one line", "proof", "wow", "steps", "users", "ask"]


def shared_genes(a, b):
    """How many of the genes two genomes (dicts with "genes", or the gene dicts) have in common."""
    ga, gb = a.get("genes", a), b.get("genes", b)
    return sum(1 for k in GENES if ga.get(k) == gb.get(k))


class Rng:
    """Deterministic on every platform and Python version (random.Random's streams are not promised stable)."""

    def __init__(self, seed, salt):
        self.state = int(hashlib.sha256(("%s:%s" % (seed, salt)).encode("utf-8")).hexdigest(), 16)
        self.n = 0

    def pick(self, items):
        self.n += 1
        h = hashlib.sha256(("%d:%d" % (self.state, self.n)).encode("utf-8")).digest()
        return items[int.from_bytes(h[:8], "big") % len(items)]

    def weighted(self, items, weights):
        """One item, each with probability weight / total: a liked value is likelier, never certain."""
        self.n += 1
        h = hashlib.sha256(("%d:%d" % (self.state, self.n)).encode("utf-8")).digest()
        x = int.from_bytes(h[:8], "big") / float(1 << 64) * sum(weights)
        for it, w in zip(items, weights):
            x -= w
            if x < 0:
                return it
        return items[-1]


MAX_PAST_SHARED = 5  # novelty: a new project shares at most 5 of the genes with another project's winner
TASTE_FLOOR = 0.08  # added to every value's weight so a liked value is likelier, never certain, and the diversity rule stays reachable
REPEAT_PENALTY = 0.4  # a value already used more than the least-used one is this much less likely
NO_MATERIAL = 0.4  # imagery values the project has nothing behind are drawn at this fraction of the others


def _try_round(n, seed, salt, recipes, ctx):
    """ctx: {"weights": {gene: {value: w}} or None, "wild": k, "avoid": [gene dicts], "factors": {gene: {value: f}},
    "stats": dict or None}. The last `wild` variants ignore the weights; a draw is retried until it keeps the diversity
    rule (<= MAX_SHARED with every other variant) and the novelty rule (<= MAX_PAST_SHARED with every past direction)."""
    rng = Rng(seed, salt)
    weights, wild, avoid, factors = ctx.get("weights"), ctx.get("wild", 0), ctx.get("avoid") or [], ctx.get("factors") or {}
    counts = {g: {v: 0 for v in vals} for g, vals in GENES.items()}
    out = []
    for i in range(n):
        taste = bool(weights) and i < n - wild
        novelty = False
        for _ in range(400):
            genes, why = {}, {}
            for g in GENES:
                once = AT_MOST_ONCE.get(g)
                if taste:
                    cands = [v for v in GENES[g] if not (v == once and counts[g][v] >= 1)]
                    w = [(TASTE_FLOOR + weights.get(g, {}).get(v, 0.5)) * factors.get(g, {}).get(v, 1.0) for v in cands]
                    pick = rng.weighted(cands, w)
                    why[g] = "taste %.2f" % weights.get(g, {}).get(pick, 0.5)
                else:
                    ok = [v for v in GENES[g] if not (v == once and counts[g][v] >= 1)]
                    low = min(counts[g][v] for v in ok)  # spread: a value repeats only once all the others appeared
                    if g in factors:  # the project's material: all values stay possible, the unseen and the available likelier
                        cands = ok
                        pick = rng.weighted(cands, [factors[g].get(v, 1.0) * (1.0 if counts[g][v] == low else REPEAT_PENALTY) for v in cands])
                    else:
                        pick = rng.pick([v for v in ok if counts[g][v] == low])
                    why[g] = "wildcard" if weights else "spread"
                genes[g] = pick
            if not all(shared_genes(genes, o["genes"]) <= MAX_SHARED for o in out):
                continue
            if not all(shared_genes(genes, p) <= MAX_PAST_SHARED for p in avoid):
                novelty = True
                continue
            break
        else:
            return None
        for g, v in genes.items():
            counts[g][v] += 1
        out.append({"genes": genes, "recipe": recipes[i % len(recipes)], "why": why,
                    "origin": "taste" if taste else ("wildcard" if weights else "spread"), "novelty": novelty})
    return out


def make_genomes(n, seed, recipes=None, weights=None, wild=None, avoid=None, factors=None, avoid_faces=()):
    """n genomes {"genes": {...8...}, "recipe": R, "why": {gene: reason}}: spread values, pairs share <= MAX_SHARED genes,
    same seed same list. Optional (UAK-063, design_breed.py calls it without them): weights {gene: {value: w}} from the
    taste profile (liked values likelier; the last `wild` variants, default 2, or 1 when n <= 4, ignore them), avoid
    [gene dicts of past directions] (no variant shares more than MAX_PAST_SHARED genes with one), factors
    {gene: {value: f}} (the project's own material scales a value's chance). Each genome also gets "fonts", an exact Google
    Fonts pair from design_fonts.py: no display or body face twice in the round, none of avoid_faces (UAK-071)."""
    recipes = list(recipes or RECIPES)
    if wild is None:
        wild = 1 if n <= 4 else 2
    base = {"avoid": avoid, "factors": factors, "wild": min(wild, n)}
    for ctx in ([dict(base, weights=weights)] if weights else []) + [dict(base, weights=None)]:
        for salt in range(60 if ctx["weights"] else 500):  # a dead end (rare) restarts the whole draw with the next salt: still deterministic
            got = _try_round(n, seed, salt, recipes, ctx)
            if got:
                import design_fonts
                for g, f in zip(got, design_fonts.assign([g["genes"]["type"] for g in got], seed, avoid_faces)):
                    g["fonts"] = f
                return got
    raise RuntimeError("no round of %d variants satisfies the diversity rule for seed %s" % (n, seed))


# ---- what the project itself says: its seed, brand colors and material (UAK-063) ----
# Why (v6.2, the human): a new project must start from its own colors and objects, not from the last project's look.

SKIP_DIRS = {".git", ".uak", "node_modules", ".claude", "dist", "build", "__pycache__", ".venv", "venv"}
HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_-])")
MAX_SCAN = 4000
MAX_BRAND = 6


def project_seed(name):
    """A stable default seed from the project's name (the same name gives the same round; another name another round)."""
    key = re.sub(r"\s+", " ", (name or "").strip().lower())
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 100000 + 1


def _walk(base, max_files=MAX_SCAN):
    """Files under base (skipping SKIP_DIRS), at most max_files, sorted so the scan is deterministic."""
    out = []
    if not base.is_dir():
        return out
    for dp, dns, fns in os.walk(str(base)):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        for fn in sorted(fns):
            out.append(Path(dp) / fn)
            if len(out) >= max_files:
                return out
    return out


def _norm_hex(h):
    h = h.lstrip("#").upper()
    return "#" + (h if len(h) == 6 else "".join(c * 2 for c in h))


def _is_color(h):
    """Not near-white, near-black or grey: a brand color has some chroma."""
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b) > 24


def _read_text(p, limit=200000):
    try:
        with open(str(p), "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def brand_colors(root, idea_text=None):
    """Hex colors the project already has, strongest source first: IDEA.md section 0, CSS custom properties under
    web/ (and src/, public/), fills in SVGs under assets/ or web/public/. [(hex, source)], at most MAX_BRAND."""
    root = Path(root)
    found = []

    def add(text, source, pat=None, strict=True):
        for m in re.finditer(pat or HEX_RE, text):
            h = _norm_hex(m.group(1) if pat else m.group(0))
            # IDEA.md names its colors on purpose (a Midnight or Ice Gray counts); scraped files skip greys and near-black/white
            if (_is_color(h) or not strict) and h not in [x[0] for x in found]:
                found.append((h, source))

    idea = idea_text if idea_text is not None else _read_text(root / "IDEA.md")
    add("\n".join(_sections(idea).get(0, [])), "IDEA.md section 0", strict=False)
    for d in ("web", "src", "public"):
        for f in _walk(root / d):
            if f.suffix.lower() in (".css", ".scss", ".html"):
                add(_read_text(f), "CSS custom properties", r"--[\w-]+\s*:\s*(#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3}))(?![0-9a-zA-Z_-])")
    for d in ("assets", "web/public"):
        for f in _walk(root / d):
            if f.suffix.lower() == ".svg":
                add(_read_text(f), "SVG fills", r"fill\s*[=:]\s*[\"']?(#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3}))(?![0-9a-zA-Z_-])")
    return found[:MAX_BRAND]


def project_material(root):
    """{imagery value: [files]} for what the project really has: screens, video, mascot/photos, a map or drawings."""
    root = Path(root)
    mat = {}
    for d in ("assets", "web", "public", "docs", "screenshots", "media"):
        for f in _walk(root / d):
            rel = f.relative_to(root).as_posix()
            name, ext = f.name.lower(), f.suffix.lower()
            if ext in (".mp4", ".webm", ".mov", ".gif"):
                mat.setdefault("video loop", []).append(rel)
            elif ext in (".png", ".jpg", ".jpeg", ".webp") and re.search(r"screen|captur|shot|dashboard|resultado|result|panel|app|loop|demo|ui", name):
                mat.setdefault("product screenshot", []).append(rel)
            elif ext in (".png", ".jpg", ".jpeg", ".webp") and re.search(r"mascot|mascota|cutout|cut-out|vehicle|product|photo|foto|premium|3d", name):
                mat.setdefault("3D cut-out", []).append(rel)
            elif ext == ".svg" or re.search(r"map|mapa|illustr|ilustr|draw|icon|logo", name):
                mat.setdefault("illustration", []).append(rel)
    if (root / "web").is_dir() and any(f.suffix.lower() in (".html", ".js", ".jsx", ".tsx") for f in _walk(root / "web", 400)):
        mat.setdefault("product screenshot", []).append("web/ (the running app)")
    return mat


def material_factors(mat):
    """imagery values with no material behind them are drawn less (NO_MATERIAL); "type only" needs none."""
    if not mat:
        return {}
    return {"imagery": {v: (1.0 if (v in mat or v == "type only") else NO_MATERIAL) for v in GENES["imagery"]}}


# ---- IDEA.md -> brief (sections by their "## N." heading, as landing-story reads them) ----

def _sections(text):
    secs, cur = {}, None
    for line in text.replace("\r", "").split("\n"):
        m = re.match(r"^##\s+(\d+)\.", line)
        if m:
            cur = int(m.group(1))
            secs[cur] = []
        elif cur is not None:
            secs[cur].append(line)
    return secs


def _real(s):
    s = re.sub(r"\s+", " ", s.strip())
    return s if s and not re.search(r"<[^>]*>", s) else ""


def _rows(lines):
    rows = []
    for l in lines:
        l = l.strip()
        if l.startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", l):
            rows.append([c.strip() for c in l.strip("|").split("|")])
    return rows[1:]  # first row is the header


def read_beats(idea_text):
    """{beat: text or None}. None = IDEA.md does not say it (placeholders from the template count as not saying it)."""
    secs = _sections(idea_text or "")
    beats = dict.fromkeys(BEATS)
    for l in secs.get(1, []):
        if _real(l) and not l.lstrip().startswith(("Edge over", ">")):
            beats["one line"] = _real(l)
            break
    for r in _rows(secs.get(10, [])):
        fact = _real(r[0])
        if fact:
            src = _real(r[1]) if len(r) > 1 else ""
            beats["proof"] = "%s (source: %s)" % (fact, src) if src else None  # a number without a source is not a proof
            if beats["proof"]:
                break
    s4 = secs.get(4, [])
    for l in s4:
        m = re.search(r"Wow in one sentence:\s*([^·]*)", l)
        if m and _real(m.group(1)):
            beats["wow"] = _real(m.group(1))
    if not beats["wow"]:
        for r in _rows(s4):
            for c in r:
                m = re.search(r"\*\*Wow:\*\*\s*(.*)", c)
                if m and _real(m.group(1)):
                    beats["wow"] = _real(m.group(1))
    steps = ["%s -> %s" % (_real(r[1]), _real(r[2])) for r in _rows(s4) if len(r) > 2 and _real(r[1]) and _real(r[2])]
    beats["steps"] = "\n".join("  %d. %s" % (i, s) for i, s in enumerate(steps[:6], 1)) or None
    users = ["%s: %s" % (_real(r[0]), _real(r[2])) for r in _rows(secs.get(2, [])) if len(r) > 2 and _real(r[0]) and _real(r[2])]
    beats["users"] = "; ".join(users) or None
    for l in (idea_text or "").replace("\r", "").split("\n"):
        m = re.match(r"^\s*[-*]?\s*(?:\*\*)?Ask(?:\*\*)?:\s*(.+)$", l)
        if m and _real(m.group(1)):
            beats["ask"] = _real(m.group(1))
            break
    return beats


def brief_text(beats, screen, product, brand=None, material=None):
    names = {"one line": "The one line (§1)", "proof": "Proof number, with its source (§10)", "wow": "The wow (§4)",
             "steps": "How it works, steps (§4)", "users": "Who it is for (§2)", "ask": "The ask (`Ask:` line in IDEA.md)"}
    out = ["# Brief · %s · %s" % (product, screen), "",
           "The same for every variant: content comes from here, only the design changes. A beat marked MISSING is not",
           "written on the page and not made up; the human fills IDEA.md and a new round picks it up.", ""]
    for b in BEATS:
        v = beats[b]
        if v is None:
            out.append("- **%s:** MISSING (not in IDEA.md)" % names[b])
        elif "\n" in v:
            out += ["- **%s:**" % names[b]] + v.split("\n")
        else:
            out.append("- **%s:** %s" % (names[b], v))
    if brand:
        out += ["", "## Brand colors (from the project)",
                "The project already has these colors (%s). The color gene starts from them: use them as the palette's anchors, not a new palette." % brand[0][1],
                ""] + ["- %s (%s)" % (h, src) for h, src in brand]
    if material:
        out += ["", "## Material the project has", ""] + ["- %s: %s" % (k, ", ".join(v[:4]) + (" ..." if len(v) > 4 else "")) for k, v in sorted(material.items())]
    out += ["", "## Subject world",
            "The agent building each variant lists 3-5 concrete things from this project's domain (its objects, instruments, units,",
            "local vernacular) at the top of index.html in a comment, and uses at least one as a visual element (a shape, an",
            "icon, a unit on a number, a word on a label). Not decoration from the genre: things the people in IDEA.md touch."]
    return "\n".join(out) + "\n"


# ---- project files ----

def project_root():
    cwd = Path.cwd()
    if (cwd / ".uak").is_dir() or (cwd / "IDEA.md").is_file():
        return cwd
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
        if top:
            return Path(top)
    except OSError:
        pass
    return cwd


def cfg(root, key, default):
    p = root / ".uak" / "PROJECT.md"
    try:
        for l in p.read_text(encoding="utf-8").replace("\r", "").split("\n"):
            l = l.strip().lstrip("-* ").replace("`", "")
            if l.startswith(key + ":") and l[len(key) + 1:].strip():
                return l[len(key) + 1:].strip()
    except OSError:
        pass
    return default


def parse_tokens(s):
    m = re.match(r"^\s*([\d.,]+)\s*([kKmM]?)", s or "")
    if not m:
        return DEFAULT_TOKENS
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return DEFAULT_TOKENS
    return int(v * {"": 1, "k": 1000, "m": 1000000}[m.group(2).lower()]) or DEFAULT_TOKENS


def fmt_tokens(t):
    return "%dk" % (t // 1000) if t % 1000 == 0 and t >= 1000 else str(t)


def skill_dirs(root):
    return [root / ".claude" / "skills", Path(os.path.expanduser("~")) / ".claude" / "skills"]


def motionsites_installed(root):
    return any((d / "motionsites-web-builder").is_dir() for d in skill_dirs(root))


def task_text(rnd, i, genome, screen):
    genes = genome["genes"]
    lines = ["# Build variant v%d of the %s" % (i, screen), "",
             "Write ONE static file, `index.html` in this folder (`%s`): HTML, inline CSS and at most inline JS, no build step, no framework." % ("v%d/index.html" % i),
             "Content: the same in every variant, taken only from `../brief.md` (a MISSING beat is left out, never invented).",
             "Only the design changes. Your design is this genome (`genome.json`); follow every gene:", ""]
    lines += ["- %s: **%s**" % (g, genes[g]) for g in GENES]
    if genome.get("fonts"):
        f = genome["fonts"]
        lines += ["- fonts: **%s** (display, weights %s) + **%s** (body, weights %s); load exactly this, no other face:" % (
                  f["display"], f["display_weights"], f["body"], f["body_weights"]),
                  "  `<link rel=\"stylesheet\" href=\"%s\">` (design-lint warns when the page loads another pair; Inter, Roboto, Arial and Geist are never a display face)" % f["url"]]
    if genome.get("brand"):
        lines += ["- project colors: %s (`../brief.md` > Brand colors; the color gene is built from them)" % " ".join(genome["brand"])]
    lines += ["- recipe: **%s** (use that skill's method for the look)" % genome["recipe"], "",
              "## Bounds (same as landing-story; they override any size in MotionSites examples or craft.md)",
              "- Hero display type: at most 96 px at 1280 wide and at most 48 px at 390 wide. Your scale gene picks inside that: %s at 1280." % SCALE_BOUNDS[genes["scale"]],
              "- Body text 16-18 px. Primary buttons 40-52 px tall. At most 6 palette colors besides media. Colors are tokens in `:root`.",
              "- It must read at 1280x720 (the hero above the fold) and at 390 px wide with no horizontal scroll.", "",
              "## The desktop first, the stage hero (the human's rules from R3; they override anything above)",
              "- Design for 1440 and 1920 wide first, then 390. The hero is full-bleed. Content containers are at least 1200 px at 1440",
              "  (a text column may be narrower, the composition fills the screen). No section with wide empty gutters.",
              "- The hero is a stand-by loop for a projector: it runs with NO interaction in a 10-15 s cycle and tells the project to a",
              "  stranger: subject, what the product finds, the result, the wow. Your `stage` gene (**%s**) says how. Reduced motion gives a complete still." % genes.get("stage", STILL),
              "- Never show a raster upscaled. Recreate the subject (3D, points, line art, vector) or show it at or below native size. A real",
              "  result chart may be rebuilt as live SVG/HTML from its real numbers.",
              "- three.js: import map pinned to `https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js` (addons under `.../three@0.170.0/examples/jsm/`),",
              "  devicePixelRatio at most 2, pause rendering when the tab is hidden, a designed still when WebGL is missing, no branded 3D models",
              "  (build from primitives or the team's own assets), no network fetches but that CDN and fonts.",
              "- Glows, neon blurs and soft gradient haze are tells (the human: \"AI slop\"); light comes from the scene itself.",
              "- Check the page at 1920x1080 (the projector): `1920.png` if the capture wrote one, else open index.html at that size; then 1280 and 390.", "",
              "## Start from material",
              "Use the team's own material first: logo, mascot, photos, map, the real product screen. List what exists (`web/public`, `assets/`,",
              "links in IDEA.md) before designing, and build around it. Then generated material. Only then the MotionSites media shelf.",
              "Imagery %s: a \"product screenshot\" is a real capture of the running product's screen, never a fake built from divs." % ("gene is **%s**" % genes["imagery"]),
              "If the product cannot be captured yet, pick another imagery treatment and say so at the top of index.html in a comment.", "",
              "## Subject world",
              "Before designing, list 3-5 concrete things from this project's domain (objects, instruments, units, local vernacular; see",
              "`../brief.md`) in a comment at the top of index.html, and use at least one as a visual element.", "",
              "When done run `bash .uak/bin/uak design shoot %s v%d` and look at `1280.png` and `390.png`; fix what looks generic or broken." % (rnd, i),
              "Last, report what you spent: `bash .uak/bin/uak design done %s v%d --tokens N` with your real token usage (skip it if you cannot know it; never guess)." % (rnd, i)]
    return "\n".join(lines) + "\n"


def _idea_and_product(root):
    idea = ""
    try:
        idea = (root / "IDEA.md").read_text(encoding="utf-8")
    except OSError:
        pass
    m = re.match(r"^#\s*IDEA\s*[·:-]\s*(.+)$", idea.split("\n", 1)[0].strip()) if idea else None
    return idea, (m.group(1).strip() if m else root.name)


def _taste_context(root, human, product, allow_repeat):
    """(weights or None, avoid list, note) from the human's taste profile. Low confidence or no profile: no weights."""
    try:
        import design_taste
        doc, source = design_taste.effective(root, human)  # team (.uak/design/taste.json), then personal (UAK-076)
    except Exception:  # noqa: BLE001  a broken profile never blocks a round
        return None, [], "no taste profile"
    own = {root.name, product}
    avoid = [] if allow_repeat else [d["genes"] for d in design_taste.past_directions(doc)
                                     if isinstance(d.get("genes"), dict) and d.get("project") not in own]
    if design_taste.confidence(doc) == "low" or not design_taste.weights(doc):
        return None, avoid, "taste: still learning (%d picks), exploring" % design_taste.pick_count(doc)
    return design_taste.weights(doc), avoid, "taste: %s, %s (%d picks)" % (source, human, design_taste.pick_count(doc))


def _past_faces(human, product, root, allow_repeat):
    """Faces of the human's past directions in other projects (their profile's `fonts`), unless --allow-repeat."""
    if allow_repeat:
        return set()
    try:
        import design_fonts
        import design_taste
        own = {root.name, product}
        return design_fonts.past_faces([d for d in design_taste.past_directions(design_taste.load(human)) if d.get("project") not in own])
    except Exception:  # noqa: BLE001  a broken profile never blocks a round
        return set()


def cmd_round(argv):
    screen, n, seed, dry, yes = "landing", DEFAULT_N, None, False, False
    human, allow_repeat, parallel = None, False, None
    it = iter(argv)
    try:
        for a in it:
            if a == "--screen":
                screen = next(it)
            elif a == "--n":
                n = int(next(it))
            elif a == "--seed":
                seed = int(next(it))
            elif a == "--human":
                human = next(it)
            elif a == "--allow-repeat":
                allow_repeat = True
            elif a == "--parallel":
                parallel = int(next(it))
            elif a == "--dry-run":
                dry = True
            elif a == "--yes":
                yes = True
            else:
                raise ValueError(a)
    except (StopIteration, ValueError):
        print("Usage: design round [--screen landing] [--n N] [--seed S] [--human NAME] [--allow-repeat] [--dry-run] [--yes]", file=sys.stderr)
        return 2
    if screen != "landing":
        print("design round: only --screen landing exists yet", file=sys.stderr)
        return 2
    if not 1 <= n <= MAX_N:
        print("design round: --n is 1..%d (got %d)" % (MAX_N, n), file=sys.stderr)
        return 2
    root = project_root()
    recipes = [r for r in RECIPES if r != "motionsites" or motionsites_installed(root)]
    idea, product = _idea_and_product(root)
    if seed is None:
        seed = project_seed(product)  # Why (v6.2): seed 1 for everyone made every new project start the same
    if human is None:
        import design_taste
        human = design_taste.default_human()
    weights, avoid, taste_note = _taste_context(root, human, product, allow_repeat)
    brand = brand_colors(root, idea)
    material = project_material(root)
    genomes = make_genomes(n, seed, recipes, weights=weights, avoid=avoid, factors=material_factors(material),
                           avoid_faces=_past_faces(human, product, root, allow_repeat))
    for g in genomes:
        if brand:
            g["brand"] = [h for h, _ in brand]
            g["why"]["color"] += " \u00b7 project colors " + " ".join(g["brand"][:3])
        if material:
            have = material.get(g["genes"]["imagery"])
            g["why"]["imagery"] += " \u00b7 " + ("project has: " + ", ".join(have[:2]) if have else "no material for it" if g["genes"]["imagery"] != "type only" else "needs none")
    mix = {k: sum(1 for g in genomes if g["origin"] == k) for k in ("taste", "wildcard", "spread")}
    novel = sum(1 for g in genomes if g["novelty"])
    mix_line = "DESIGN_ROUND mix: %d from taste, %d wildcards, %d drawn as before; %d redrawn for novelty vs %d past directions (%s)%s" % (
        mix["taste"], mix["wildcard"], mix["spread"], novel, len(avoid), taste_note, "; seed %d from the project name" % seed)
    if dry:
        for i, g in enumerate(genomes, 1):
            print("v%d  %s  | recipe %s | %s" % (i, " | ".join("%s=%s" % (k, g["genes"][k]) for k in GENES), g["recipe"], g["origin"]))
        print(mix_line)
        return 0
    cfgd = cfg(root, "Design-Variant-Tokens", "")
    per = parse_tokens(cfgd)
    tier = cfg(root, "Design-Variant-Model", DEFAULT_TIER)
    import design_metrics
    est = design_metrics.estimate(root, human, [g["genes"].get("stage", STILL) for g in genomes], per, parallel)
    if est["parts"]:  # Why (AXIA R3): the fixed 60k per variant was off by 2x; a round's cost is what this human's rounds measured
        print("DESIGN_ROUND cost: %s = %s tokens, model tier %s" % (" + ".join(est["parts"]), design_metrics.fmt_tokens(est["tokens"]), tier))
        print("DESIGN_ROUND source: median of %d measured variants of %s's rounds, by stage family (uak design report --all)" % (est["entries"], human))
    else:
        print("DESIGN_ROUND cost: %d variants x %s tokens = %s tokens, model tier %s" % (n, fmt_tokens(per), fmt_tokens(per * n), tier))
        print("DESIGN_ROUND source: %s, no history (no round with reported tokens yet; builders report with `uak design done`)" % (
            "Design-Variant-Tokens in PROJECT.md" if cfgd else "the %s default" % fmt_tokens(DEFAULT_TOKENS)))
    if est["wall_minutes"] is not None:
        print("DESIGN_ROUND wall: ~%d min (%d variants, %d in parallel, median minutes per variant of the slowest stage family)" % (
            math.ceil(est["wall_minutes"]), n, est["parallel"]))
        warn = design_metrics.deadline_warning(root, est["wall_minutes"])
        if warn:
            print("DESIGN_ROUND " + warn)
    print(mix_line)
    again = "bash .uak/bin/uak design round --screen %s --n %d --seed %d --yes" % (screen, n, seed)
    if not yes:
        print("DESIGN_ROUND refused: nothing written. Rerun with --yes (or ask the human to run it): %s" % again, file=sys.stderr)
        return 3
    base = root / ".uak" / "design" / "rounds"
    k = 1
    while (base / ("R%d" % k)).exists():
        k += 1
    rnd = base / ("R%d" % k)
    rnd.mkdir(parents=True)
    with open(str(rnd / "brief.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(brief_text(read_beats(idea), screen, product, brand, material))
    for i, g in enumerate(genomes, 1):
        v = rnd / ("v%d" % i)
        v.mkdir()
        doc = {"id": "R%d-v%d" % (k, i), "round": "R%d" % k, "variant": i, "seed": seed, "screen": screen,
               "genes": g["genes"], "recipe": g["recipe"], "why": g["why"]}
        if g.get("fonts"):
            doc["fonts"] = g["fonts"]
        with open(str(v / "genome.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        with open(str(v / "TASK.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(task_text("R%d" % k, i, g, screen))
        design_metrics.start(v)
    print("DESIGN_ROUND R%d: brief.md + %d variants in %s" % (k, n, rnd))
    print("Next: one agent per variant follows v<i>/TASK.md, then: bash .uak/bin/uak design shoot R%d" % k)
    return 0


# ---- capture ----

# Why (AXIA R1, Nov 11 2026): two variants looked broken in their captures because a <video>'s first frame is empty, and the
# human judged six landings from that first screen alone. Before each shot every video is paused and seeked to 30% of its
# length (a video that has no frame to show keeps its poster); the page is then still, so the fold and the full page match.
MEDIA_JS = """async () => {
  const vs = Array.prototype.slice.call(document.querySelectorAll('video'));
  const wait = (el, ev, ms) => new Promise(res => { let done = false; const f = () => { if (!done) { done = true; res(); } };
    el.addEventListener(ev, f, {once: true}); setTimeout(f, ms); });
  for (const v of vs) {
    try {
      v.muted = true; v.removeAttribute('autoplay'); v.pause();
      if (v.preload === 'none') { v.preload = 'auto'; v.load(); }
      if (v.readyState < 1) await wait(v, 'loadedmetadata', 6000);
      if (isFinite(v.duration) && v.duration > 0) { v.currentTime = v.duration * 0.3; await wait(v, 'seeked', 6000); }
      v.pause();
    } catch (e) {}
  }
  await new Promise(res => setTimeout(res, 300));
  return vs.length;
}"""

# Why (AXIA R1-R3, Nov 11 2026): the lead hand-patched the capture for 1920, http and WebGL, and the human found the narrow
# pages and stretched images by eye. The probe below measures what the human judges, in the page itself: WebGL, how wide
# the content (text extents, images, media) is against the viewport, rasters drawn larger than they are, and the frame time.
QA_JS = """async () => {
  const W = innerWidth, dpr = window.devicePixelRatio || 1;
  let gl = false;
  try { const c = document.createElement('canvas'); gl = !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) {}
  const overflow = document.documentElement.scrollWidth > W + 1;
  let lo = Infinity, hi = -Infinity, n = 0;
  const all = document.body ? document.body.querySelectorAll('*') : [];
  for (let i = 0; i < all.length && i < 4000; i++) {
    const el = all[i], tag = el.tagName;
    if (/^(SCRIPT|STYLE|NOSCRIPT|META|LINK|HEAD|TITLE|SOURCE)$/i.test(tag)) continue;
    let r = null;
    if (/^(IMG|VIDEO|CANVAS|SVG|PICTURE)$/i.test(tag)) r = el.getBoundingClientRect();
    else {
      let text = false;
      for (const c of el.childNodes) { if (c.nodeType === 3 && c.textContent.trim()) { text = true; break; } }
      if (!text) continue;
      const g = document.createRange(); g.selectNodeContents(el); r = g.getBoundingClientRect();  // the text itself, not its box
    }
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) continue;
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight * 3) continue;
    lo = Math.min(lo, Math.max(0, r.left)); hi = Math.max(hi, Math.min(W, r.right)); n++;
  }
  const share = n && hi > lo ? Math.round((hi - lo) / W * 100) : null;
  const upscaled = [];
  document.querySelectorAll('img').forEach(im => {
    const src = im.currentSrc || im.src || '';
    if (!im.complete || !im.naturalWidth || /\.svg(\?|$)/i.test(src)) return;
    const r = im.getBoundingClientRect(), cs = getComputedStyle(im);
    if (r.width < 2 || cs.display === 'none' || cs.visibility === 'hidden') return;
    if (r.width > im.naturalWidth * dpr * 1.1 + 1) upscaled.push({file: src.split('/').pop().split('?')[0], natural: im.naturalWidth, drawn: Math.round(r.width)});
  });
  const frame = await new Promise(res => { const t = []; let last = performance.now(); const t0 = last;
    const f = now => { t.push(now - last); last = now; if (t.length < 200 && now - t0 < 1200) requestAnimationFrame(f);
      else res(Math.round(t.reduce((a, b) => a + b, 0) / t.length)); };
    requestAnimationFrame(f); });
  return {w: W, gl: gl, overflow: overflow, share: share, upscaled: upscaled.slice(0, 5), frameMs: frame, fps: frame ? Math.round(1000 / frame) : null};
}"""

_PLAYWRIGHT = """
import functools, http.server, json, os, re, sys, threading
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright
MEDIA = @MEDIA@
QA = @QA@
html, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
# Served over http: canvas pixel reads and fetches fail on file://. The root is the round folder (../brief.md, assets/).
class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map, **{".glb": "model/gltf-binary", ".woff2": "font/woff2", ".mjs": "text/javascript", ".js": "text/javascript"})
    def log_message(self, *a): pass
    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()
    def do_GET(self):
        # Why (UAK-067/069): Chromium will not seek a <video> over a server without byte ranges, which would undo the 30% seek.
        m = re.match(r"^bytes=(\\d*)-(\\d*)$", self.headers.get("Range") or "")
        path = self.translate_path(self.path)
        if not m or not (m.group(1) or m.group(2)) or not os.path.isfile(path):
            return super().do_GET()
        size = os.path.getsize(path)
        a, b = m.groups()
        start, end = (max(0, size - int(b)), size - 1) if not a else (int(a), min(int(b), size - 1) if b else size - 1)
        if start >= size or start > end:
            self.send_response(416); self.send_header("Content-Range", "bytes */%d" % size); self.send_header("Content-Length", "0"); self.end_headers()
            return
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            self.wfile.write(f.read(end - start + 1))
root = html.parent.parent
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = "http://127.0.0.1:%d/%s" % (srv.server_address[1], quote(html.relative_to(root).as_posix()))
report = {}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    for name, w, h in (("1920", 1920, 1080), ("1280", 1280, 720), ("390", 390, 844)):
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2 if w < 500 else 1)  # the phone is sharp on the pick page
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        try:
            pg.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as exc:
            errs.append("load: " + str(exc)[:120])
        pg.wait_for_timeout(3200)  # animations are mid-cycle, fonts and media settled
        pg.evaluate(MEDIA)
        qa = pg.evaluate(QA) or {}
        pg.screenshot(path=str(out / (name + ".png")))
        pg.evaluate(MEDIA)
        pg.screenshot(path=str(out / (name + "-full.png")), full_page=True)
        qa["errors"], qa["first"] = len(errs), (errs[0][:160] if errs else "")
        report[name] = qa
        print("QA %s webgl=%s errors=%d overflow=%s content=%s%% fps=%s upscaled=%d" % (name, qa.get("gl"), len(errs), qa.get("overflow"), qa.get("share"), qa.get("fps"), len(qa.get("upscaled", []))))
        pg.close()
    b.close()
srv.shutdown()
(out / "qa.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
""".replace("@MEDIA@", json.dumps(MEDIA_JS)).replace("@QA@", json.dumps(QA_JS))


NARROW_UNDER = 75  # percent of the viewport the content must span at 1920 and 1440 (the projector and the laptop)


def qa_warnings(qa):
    """[(viewport, text)] from a qa.json report: what the human would notice, said before they look."""
    out = []
    for name, q in (qa or {}).items():
        if not isinstance(q, dict):
            continue
        w = q.get("w") or (int(name) if str(name).isdigit() else 0)
        if q.get("errors"):
            out.append((name, "page errors: %d (first: %s)" % (q["errors"], q.get("first") or "?")))
        if q.get("gl") is False:
            out.append((name, "no WebGL in the capture browser"))
        if q.get("overflow"):
            out.append((name, "horizontal overflow at %s px" % w))
        if q.get("share") is not None and w >= 1440 and q["share"] < NARROW_UNDER:
            out.append((name, "narrow page, empty gutters: content spans %s%% of %s px" % (q["share"], w)))
        for u in q.get("upscaled", [])[:3]:
            out.append((name, "upscaled raster: %s, %s -> %s px" % (u.get("file"), u.get("natural"), u.get("drawn"))))
    return out


def read_qa(vdir):
    try:
        return json.loads((Path(vdir) / "qa.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def find_capture(root):
    """A command list taking (index.html, outdir) and writing 1280.png + 390.png there, or (None, why)."""
    env = os.environ.get("UAK_DESIGN_SHOOT", "")
    if env == "none":
        return None, "disabled by UAK_DESIGN_SHOOT=none"
    if env:
        # Why (CI, Nov 11 2026): a TMPDIR with a space and an accent split the string, and Windows cannot exec a script.
        # A value that names a file is ONE argv element, run by its interpreter; anything else is a command line.
        if os.path.isfile(env):
            ext = os.path.splitext(env)[1].lower()
            if ext == ".py":
                return [sys.executable, env], "UAK_DESIGN_SHOOT"
            if ext in (".sh", ""):
                return [shutil.which("bash") or "bash", env], "UAK_DESIGN_SHOOT"
            return [env], "UAK_DESIGN_SHOOT"
        return shlex.split(env, posix=(os.name != "nt")), "UAK_DESIGN_SHOOT"
    path_tool = shutil.which("uak-design-shoot")
    if path_tool:
        return [path_tool], "uak-design-shoot on PATH"
    try:
        import playwright  # noqa: F401  (the webapp-testing skill's way: Playwright for Python)
        return [sys.executable, "-c", _PLAYWRIGHT], "playwright (webapp-testing)"
    except ImportError:
        pass
    for d in skill_dirs(root):
        s = d / "motionsites-web-builder" / "scripts" / "shoot.py"
        if s.is_file():
            return [sys.executable, str(s), "@shoot.py"], "motionsites shoot.py"
    return None, "no capture tool"


def capture_one(cmd, html, vdir):
    if cmd[-1] == "@shoot.py":  # MotionSites' shoot.py has VIEWS hardcoded at 1440x900 and writes desktop*/mobile* PNGs
        tmp = Path(tempfile.mkdtemp(prefix="uak-shoot-"))
        try:
            src = Path(cmd[-2])
            text = src.read_text(encoding="utf-8")
            exact = '("desktop", 1440, 900)' in text
            patched = tmp / "shoot.py"  # a copy at 1280x720, so 1280.png is really 1280 wide (no Pillow needed)
            patched.write_text(text.replace('("desktop", 1440, 900)', '("desktop", 1280, 720)'), encoding="utf-8")
            out = tmp / "out"
            r = subprocess.run([cmd[0], str(patched), str(html), str(out)], capture_output=True, text=True, timeout=300)
            pngs = sorted(out.rglob("*.png"))
            for want, key in (("1280.png", "desktop"), ("390.png", "mobile")):
                hit = [p for p in pngs if key in p.name.lower() and "early" not in p.name.lower()]
                if hit:
                    # Not patchable (script changed): keep the real width in the name instead of lying with 1280.png.
                    shutil.copyfile(str(hit[0]), str(vdir / (want if exact or key == "mobile" else "desktop.png")))
            ok = r.returncode == 0 and (vdir / "1280.png").is_file() and (vdir / "390.png").is_file()
            return ok, (r.stderr or r.stdout)[-200:] if ok or exact else "shoot.py has other viewports than 1440x900; saved as desktop.png, not 1280.png"
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    try:
        (vdir / "qa.json").unlink()  # a QA report belongs to the capture that wrote it
    except OSError:
        pass
    r = subprocess.run(cmd + [str(html), str(vdir)], capture_output=True, text=True, timeout=600)
    ok = r.returncode == 0 and (vdir / "1280.png").is_file() and (vdir / "390.png").is_file()
    return ok, (r.stderr or r.stdout).strip()[-200:]


def cmd_shoot(argv):
    if not argv or not re.match(r"^R\d+$", argv[0]):
        print("Usage: design shoot R<k> [v<i> ...]", file=sys.stderr)
        return 2
    root = project_root()
    rnd = root / ".uak" / "design" / "rounds" / argv[0]
    if not rnd.is_dir():
        print("design shoot: no round %s (looked in %s)" % (argv[0], rnd), file=sys.stderr)
        return 1
    only = set(argv[1:])
    variants = sorted((p for p in rnd.glob("v*") if p.is_dir() and re.match(r"^v\d+$", p.name) and (not only or p.name in only)),
                      key=lambda p: int(p.name[1:]))
    todo = [v for v in variants if not ((v / "1280.png").is_file() and (v / "390.png").is_file())]
    done, failed = [], []
    cmd, how = find_capture(root) if todo else (None, "")
    if todo and cmd is None:
        print("DESIGN_SHOOT no capture tool (%s): install Playwright (pip install playwright && python -m playwright install chromium) "
              "or the MotionSites skill, or set UAK_DESIGN_SHOOT to a command taking index.html OUTDIR. Not captured: %s"
              % (how, " ".join(v.name for v in todo)), file=sys.stderr)
        return 1
    for v in todo:
        html = v / "index.html"
        if not html.is_file():
            failed.append((v.name, "no index.html yet"))
            continue
        try:
            ok, why = capture_one(cmd, html, v)
        except (OSError, subprocess.SubprocessError) as exc:
            ok, why = False, str(exc)[:200]
        (done if ok else failed).append(v.name if ok else (v.name, why or "capture tool failed"))
        if ok:
            try:
                import design_metrics
                design_metrics.record_capture(v)
            except Exception as exc:  # noqa: BLE001  metrics never fail a capture
                print("DESIGN_SHOOT metrics not recorded for %s: %s" % (v.name, str(exc)[:120]), file=sys.stderr)
    print("DESIGN_SHOOT %s: captured %s; already had %d" % (argv[0], " ".join(done) or "none", len(variants) - len(todo)))
    for name, why in failed:
        print("DESIGN_SHOOT not captured: %s (%s)" % (name, why.replace("\n", " ")), file=sys.stderr)
    broken = []
    for v in variants:
        warns = qa_warnings(read_qa(v)) if v.name in done else []
        for vp, text in warns:
            print("DESIGN_SHOOT QA %s %s: %s" % (v.name, vp, text))
        if any(t.startswith("page errors") for _, t in warns):
            broken.append(v.name)
    if broken:  # Why (AXIA R1-R3): a variant that throws on load is not a design to judge; the shoot fails so it is fixed first
        print("DESIGN_SHOOT page errors in: %s (see the QA lines above; fix them, delete the variant's PNGs and shoot again)" % " ".join(broken), file=sys.stderr)
    return 1 if failed or broken else 0


def main(argv):
    if argv[:1] == ["round"] and "--from" in argv:  # a bred round from the human's picks (UAK-059)
        import design_breed
        return design_breed.run(argv[1:])
    if argv[:1] == ["round"]:
        return cmd_round(argv[1:])
    if argv[:1] == ["shoot"]:
        return cmd_shoot(argv[1:])
    if argv[:1] in (["done"], ["report"]):  # tokens and minutes per variant (UAK-070)
        import design_metrics
        return design_metrics.main(argv)
    print("Usage: design round [--screen landing] [--n N] [--seed S] [--human NAME] [--allow-repeat] [--dry-run] [--yes] | design round --from R<k> [--n N] [--yes] | design shoot R<k> [v<i> ...] | design done R<k> v<i> --tokens N | design report R<k> [--all] | design pick R<k> [--k N]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
