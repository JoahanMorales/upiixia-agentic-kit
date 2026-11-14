#!/usr/bin/env python3
"""Colors that combine: palettes built from the project's brand with harmony rules, picked before any page is built, and
measured on the page at the fold.

    uak design palettes [--n 6] [--seed S] [--human NAME]     a palette round: N palettes, no agents, no tokens (P<k>, picked with `design pick P<k>`)

A palette is roles with exact hex and area shares (ground 55, surface 25, ink 10, primary 7, accent 3), not a list of colors:
one dominant hue; ground, surface, ink and border are neutrals tinted toward it; at most 2 saturated hues (every other brand
color is kept desaturated); a second hue that is near-complementary to the first never sits at the same lightness (no
vibrating pair); ink on ground >= 7:1 and ink on surface, button text on primary >= 4.5:1, checked before a page is built.
Colors are measured in OKLab/OKLCH (Ottosson), by hand. measure_png() reads the 1920 fold of a capture (8-bit RGB/RGBA PNG,
zlib) for the saturated share, the dark share, the dominant colors, how much each role covers and the hue clashes.
Why (2026-11-12, the human: "the taste profile uses colors very badly ... it doesn't combine them correctly and it isn't
pretty"): measured at the fold, AXIA R3 pages were 1-3% saturated, an almost monochrome navy; colonIA v4 put a washed pink on
cream; the color gene said "ink + one accent" with no roles or harmony and the profile learned labels, not combinations.
Python 3.8+ standard library only."""
import json
import math
import os
import re
import struct
import sys
import time
import zlib
from pathlib import Path

SAT_C = 0.10          # OKLCH chroma from which a color counts as saturated
CHROMATIC_C = 0.04    # below this a brand color is a neutral
DARK_L = 0.35
SHARES = {"ground": 55, "surface": 25, "ink": 10, "primary": 7, "accent": 3}
ROLES = ("ground", "surface", "ink", "primary", "accent", "border")
FALLBACK = ["#2F5BEA", "#E2557B", "#1E9E6A"]
TRAITS = ("palette_hue", "palette_sat_hues", "palette_neutral", "palette_sat_share")  # what the taste profile learns


# ---- color math (OKLab, Bjorn Ottosson 2020) ----
def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    c = max(0.0, min(1.0, c))
    return int(round(255 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)))


def parse_hex(h):
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def to_hex(r, g, b):
    return "#%02X%02X%02X" % (r, g, b)


def oklab(rgb):
    r, g, b = (_lin(c) for c in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3.0)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3.0)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3.0)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _from_lab(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def oklch(h):
    L, a, b = oklab(parse_hex(h))
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def from_oklch(L, C, hue):
    """The hex nearest to (L, C, hue) inside sRGB: chroma is reduced until the color fits."""
    lo, hi = 0.0, max(0.0, C)
    def rgb(c):
        return _from_lab(L, c * math.cos(math.radians(hue)), c * math.sin(math.radians(hue)))
    if all(-0.001 <= v <= 1.001 for v in rgb(hi)):
        lo = hi
    else:
        for _ in range(24):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if all(-0.001 <= v <= 1.001 for v in rgb(mid)) else (lo, mid)
    return to_hex(*(_gam(v) for v in rgb(lo)))


def luminance(h):
    r, g, b = (_lin(c) for c in parse_hex(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hue_family(h):
    for top, name in ((15, "pink"), (45, "red"), (85, "orange"), (115, "yellow"), (170, "green"), (225, "cyan"), (285, "blue"), (330, "purple"), (361, "pink")):
        if h < top:
            return name
    return "pink"


def temperature(h):
    return "warm" if (h < 115 or h >= 330) else "cool" if 170 <= h < 300 else "neutral"


def hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def is_saturated(h):
    return oklch(h)[1] >= SAT_C


# ---- palettes ----
def _chromatic(brand):
    seen, out = set(), []
    for h in brand or []:
        try:
            hx = to_hex(*parse_hex(h))
        except (ValueError, IndexError):
            continue
        L, C, hue = oklch(hx)
        if hx not in seen and C >= CHROMATIC_C:
            seen.add(hx)
            out.append(hx)
    return sorted(out, key=lambda x: -oklch(x)[1]) or list(FALLBACK)


def _fit_text_on(bg, light, dark):
    """The better of the two text colors on bg, and whether it reaches 4.5:1."""
    best = max((light, dark), key=lambda t: contrast(bg, t))
    return best, contrast(bg, best)


def build_palette(dominant, accent=None, ground="light", extras=(), soft=False):
    """One palette from a dominant brand color and at most one accent. Roles, shares and contrast included."""
    L0, C0, h0 = oklch(dominant)
    dark = ground == "dark"
    ink_l = 0.95 if dark else 0.20
    base = {"ground": (0.17, 0.03) if dark else (0.975, 0.012), "surface": (0.23, 0.035) if dark else (0.94, 0.02),
            "border": (0.33, 0.03) if dark else (0.86, 0.02), "ink": (ink_l, 0.012 if dark else 0.025)}
    roles = {k: from_oklch(L, C, h0) for k, (L, C) in base.items()}  # neutrals tinted toward the dominant hue, never pure grey
    for _ in range(30):  # ink on ground >= 7:1
        if contrast(roles["ink"], roles["ground"]) >= 7.0 and contrast(roles["ink"], roles["surface"]) >= 4.5:
            break
        ink_l += 0.02 if dark else -0.02
        roles["ink"] = from_oklch(min(ink_l, 0.99) if dark else max(ink_l, 0.0), base["ink"][1], h0)
    pc = max(0.08, min(0.22, C0 * (0.7 if soft else 1.0)))
    pl = min(max(L0, 0.62 if dark else 0.42), 0.78 if dark else 0.62)
    light_txt, dark_txt = from_oklch(0.985, 0.01, h0), from_oklch(0.18, 0.02, h0)
    primary = from_oklch(pl, pc, h0)
    for _ in range(40):  # button text on primary >= 4.5:1 and primary against the ground >= 3:1
        txt, c = _fit_text_on(primary, light_txt, dark_txt)
        if c >= 4.5 and contrast(primary, roles["ground"]) >= 3.0:
            break
        pl += (0.02 if txt == dark_txt else -0.02) if c < 4.5 else (0.02 if dark else -0.02)
        pl = min(max(pl, 0.2), 0.9)
        primary = from_oklch(pl, pc, h0)
    roles["primary"], roles["button_text"] = primary, _fit_text_on(primary, light_txt, dark_txt)[0]
    roles["accent"] = None
    if accent:
        _, ac, ah = oklch(accent)
        al = oklch(accent)[0]
        al = min(max(al, 0.55 if dark else 0.45), 0.85 if dark else 0.7)
        c2 = max(0.06, min(ac, 0.7 * pc))  # the accent is quieter than the primary
        for _ in range(20):
            if hue_gap(ah, h0) < 150 or abs(al - pl) >= 0.15:  # near-complementary pairs never share a lightness
                break
            al += 0.04 if al + 0.04 <= 0.88 else -0.04
        roles["accent"] = from_oklch(al, c2, ah)
    extra = [from_oklch(oklch(x)[0], oklch(x)[1] * 0.25, oklch(x)[2]) for x in extras if x not in (dominant, accent)][:3]  # other brand colors stay desaturated
    sat = [c for c in (roles["primary"], roles["accent"]) if c and is_saturated(c)]
    pal = {"name": "%s on %s%s" % (hue_family(h0), ground, ", soft" if soft else ""), "ground": ground, "dominant": dominant, "accent_source": accent,
           "roles": roles, "shares": dict(SHARES) if accent else {"ground": 58, "surface": 25, "ink": 10, "primary": 7}, "extras": extra, "saturated": sat}
    pal["traits"] = traits_of(pal)
    pal["contrast"] = {"ink_on_ground": round(contrast(roles["ink"], roles["ground"]), 1), "ink_on_surface": round(contrast(roles["ink"], roles["surface"]), 1),
                       "button_text_on_primary": round(contrast(roles["button_text"], roles["primary"]), 1)}
    return pal


def traits_of(pal):
    """What a profile learns from a palette: dominant hue family, number of saturated hues, neutral temperature, saturation share."""
    L, C, h = oklch(pal["roles"]["primary"])
    gh = oklch(pal["roles"]["ground"])[2]
    share = sum(pal["shares"].get(r, 0) for r in ("primary", "accent") if pal["roles"].get(r) and is_saturated(pal["roles"][r]))
    return {"palette_hue": hue_family(h), "palette_sat_hues": str(len(pal.get("saturated") or [])), "palette_neutral": temperature(gh),
            "palette_sat_share": "low" if C < 0.10 else "mid" if C < 0.17 else "high"}


def problems(pal):
    """What is wrong with a palette (empty = fine): contrast, too many saturated hues, a vibrating pair, brand colors all at full chroma."""
    r, out = pal.get("roles") or {}, []
    try:
        if contrast(r["ink"], r["ground"]) < 7.0:
            out.append("ink on ground %.1f:1 (needs 7:1)" % contrast(r["ink"], r["ground"]))
        if contrast(r["ink"], r["surface"]) < 4.5:
            out.append("body text on surface %.1f:1 (needs 4.5:1)" % contrast(r["ink"], r["surface"]))
        if contrast(r["button_text"], r["primary"]) < 4.5:
            out.append("button text on primary %.1f:1 (needs 4.5:1)" % contrast(r["button_text"], r["primary"]))
        sat = [c for c in (r.get("primary"), r.get("accent")) + tuple(pal.get("extras") or []) if c and is_saturated(c)]
        if len(sat) > 2:
            out.append("%d saturated hues in one view (at most 2)" % len(sat))
        if r.get("accent") and is_saturated(r["primary"]) and is_saturated(r["accent"]):
            (l1, _, h1), (l2, _, h2) = oklch(r["primary"]), oklch(r["accent"])
            if 150 <= hue_gap(h1, h2) <= 210 and abs(l1 - l2) < 0.10:
                out.append("primary and accent are near-complementary at equal lightness (they vibrate)")
    except (KeyError, ValueError, TypeError):
        out.append("palette is missing roles")
    return out


def build_palettes(brand, n=6, prefer=None):
    """N distinct palettes from the brand colors (hex list); `prefer` {hue family: weight} (what the profile learned) orders the dominants."""
    chroma = _chromatic(brand)
    if prefer:
        chroma = sorted(chroma, key=lambda x: -prefer.get(hue_family(oklch(x)[2]), 0.5))
    out, seen = [], set()
    for i in range(n * 12):
        dom = chroma[i % len(chroma)]
        others = [c for c in chroma if hue_gap(oklch(c)[2], oklch(dom)[2]) >= 25]
        k = (i // len(chroma)) % (len(others) + 1)
        acc = others[k] if k < len(others) else None
        ground = ("light", "dark")[(i + i // len(chroma)) % 2]
        soft = (i // (2 * len(chroma) * (len(others) + 1))) % 2 == 1
        key = (dom, acc, ground, soft)
        if key in seen:
            continue
        seen.add(key)
        pal = build_palette(dom, acc, ground, extras=chroma, soft=soft)
        if not problems(pal):
            out.append(pal)
        if len(out) == n:
            break
    return out


# ---- measuring a capture ----
def read_png(path, step=3):
    """[(r, g, b)] sampled every `step` pixels of an 8-bit non-interlaced RGB/RGBA PNG, or None when it cannot be read."""
    try:
        data = Path(path).read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        pos, idat, w = 8, b"", 0
        while pos < len(data):
            n, kind = struct.unpack(">I4s", data[pos:pos + 8])
            body = data[pos + 8:pos + 8 + n]
            if kind == b"IHDR":
                w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body[:13])
                if depth != 8 or ctype not in (2, 6) or inter:
                    return None
            elif kind == b"IDAT":
                idat += body
            pos += 12 + n
        bpp = 3 if ctype == 2 else 4
        raw, stride, prev, px = zlib.decompress(idat), w * bpp, bytearray(w * bpp), []
        for y in range(h):
            f, row, o = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)]), 0
            if f == 1:
                for i in range(bpp, stride):
                    row[i] = (row[i] + row[i - bpp]) & 255
            elif f == 2:
                row = bytearray((a + b) & 255 for a, b in zip(row, prev))
            elif f == 3:
                for i in range(stride):
                    row[i] = (row[i] + (((row[i - bpp] if i >= bpp else 0) + prev[i]) >> 1)) & 255
            elif f == 4:
                for i in range(stride):
                    a, b, c = (row[i - bpp] if i >= bpp else 0), prev[i], (prev[i - bpp] if i >= bpp else 0)
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            if y % step == 0:
                for x in range(0, w, step):
                    px.append((row[x * bpp], row[x * bpp + 1], row[x * bpp + 2]))
            prev = row
        return px
    except (OSError, struct.error, zlib.error, ValueError, IndexError):
        return None


def measure_pixels(px, palette=None):
    """{saturated, dark, dominant [(hex, share)], roles {role: share}, other, clashes [..]}: shares are percentages of the sample."""
    n = len(px)
    if not n:
        return None
    sat = dark = 0
    buckets, roles = {}, {}
    cols = {r: oklab(parse_hex(palette["roles"][r])) for r in ROLES if palette and palette["roles"].get(r)} if palette else {}
    other = 0
    for rgb in px:
        L, a, b = oklab(rgb)
        C = math.hypot(a, b)
        sat += C >= SAT_C
        dark += L < DARK_L
        k = (rgb[0] >> 4, rgb[1] >> 4, rgb[2] >> 4)
        e = buckets.setdefault(k, [0, 0, 0, 0])
        e[0] += 1
        e[1] += rgb[0]
        e[2] += rgb[1]
        e[3] += rgb[2]
        if cols:
            r, d = min(((r, math.dist((L, a, b), c)) for r, c in cols.items()), key=lambda t: t[1])
            if d <= 0.06:
                roles[r] = roles.get(r, 0) + 1
            else:
                other += 1
    top = sorted(buckets.values(), key=lambda e: -e[0])[:4]
    dominant = [(to_hex(e[1] // e[0], e[2] // e[0], e[3] // e[0]), round(100.0 * e[0] / n, 1)) for e in top if e[0] * 100.0 / n >= 2]
    loud = [(h, s) for h, s in dominant if s >= 3 and is_saturated(h)]
    clashes = []
    for i in range(len(loud)):
        for j in range(i + 1, len(loud)):
            (l1, _, h1), (l2, _, h2) = oklch(loud[i][0]), oklch(loud[j][0])
            if 150 <= hue_gap(h1, h2) <= 210 and abs(l1 - l2) < 0.08:
                clashes.append("%s and %s" % (loud[i][0], loud[j][0]))
    return {"saturated": round(100.0 * sat / n, 1), "dark": round(100.0 * dark / n, 1), "dominant": dominant,
            "roles": {r: round(100.0 * c / n, 1) for r, c in roles.items()}, "other": round(100.0 * other / n, 1) if cols else None, "clashes": clashes}


def drift(measured, palette):
    """Why a page drifted from its planned palette: [] when it did not."""
    if not measured or not palette:
        return []
    out, ro = [], measured.get("roles") or {}
    if measured.get("other") is not None and measured["other"] > 55 and (ro.get("ground", 0) + ro.get("surface", 0)) < 20:
        out.append("%.0f%% of the fold matches no role of its palette" % measured["other"])
    want = sum(palette["shares"].get(r, 0) for r in ("primary", "accent"))
    if measured["saturated"] > want * 3 + 5:
        out.append("%.0f%% saturated against %d%% planned" % (measured["saturated"], want))
    if (palette["ground"] == "light" and measured["dark"] > 60) or (palette["ground"] == "dark" and measured["dark"] < 25):
        out.append("a %s palette but %.0f%% of the fold is dark" % (palette["ground"], measured["dark"]))
    if measured.get("clashes"):
        out.append("hues clash: " + "; ".join(measured["clashes"]))
    return out


def measure_png(path, palette=None):
    px = read_png(path)
    m = measure_pixels(px, palette) if px else None
    if m is not None and palette:
        m["drift"] = drift(m, palette)
    return m


# ---- the palette round (no agents) ----
def mock_html(pal, esc=lambda s: s):
    """A tiny mock of a palette: ground, a headline, a button, a chart line, a surface card."""
    r = pal["roles"]
    acc = r.get("accent") or r["primary"]
    strip = "".join('<i style="background:%s;flex:%d" title="%s %s"></i>' % (r[k], pal["shares"].get(k, 3), k, r[k]) for k in ("ground", "surface", "ink", "primary", "accent", "border") if r.get(k))
    return ('<div class="pal"><div class="strip">%s</div><div class="mock" style="background:%s;color:%s;border-color:%s">'
            '<b style="color:%s">%s</b><span>Headline in ink on the ground</span><em style="background:%s;color:%s">Button</em>'
            '<div class="card" style="background:%s">card</div><svg viewBox="0 0 80 24"><polyline fill="none" stroke="%s" stroke-width="2" points="0,20 16,14 32,16 48,6 64,9 80,2"/></svg></div></div>'
            % (strip, r["ground"], r["ink"], r["border"], r["primary"], esc(pal["name"]), r["primary"], r["button_text"], r["surface"], acc))


def cmd_palettes(argv, root):
    n, seed, human = 6, None, None
    it = iter(argv)
    try:
        for a in it:
            if a == "--n":
                n = int(next(it))
            elif a == "--human":
                human = next(it)
            elif a == "--seed":
                seed = int(next(it))
            else:
                raise ValueError(a)
    except (StopIteration, ValueError):
        print("Usage: design palettes [--n 6] [--human NAME]", file=sys.stderr)
        return 2
    from design_round import brand_colors
    root = Path(root)
    brand = [h for h, _ in brand_colors(root)]
    prefer = None
    try:
        import design_taste
        doc, _ = design_taste.effective(root, human or design_taste.default_human())
        prefer = {k: v for k, v in design_taste.weights(doc).get("palette_hue", {}).items()}
    except Exception:  # noqa: BLE001  a broken profile never blocks a palette round
        pass
    pals = build_palettes(brand, max(1, min(n, 20)), prefer)
    if not pals:
        print("design palettes: no palette passed the harmony and contrast checks", file=sys.stderr)
        return 1
    base = root / ".uak" / "design" / "rounds"
    k = 1
    while (base / ("P%d" % k)).exists():
        k += 1
    rnd = base / ("P%d" % k)
    for i, p in enumerate(pals, 1):
        v = rnd / ("v%d" % i)
        v.mkdir(parents=True)
        (v / "genome.json").write_text(json.dumps({"id": "P%d-v%d" % (k, i), "round": "P%d" % k, "variant": i, "genes": {}, "palette": p}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    src = ("the brand colors of the project (%s)" % " ".join(brand[:6])) if brand else "no brand colors found: the kit's neutral starter hues"
    print("DESIGN_PALETTES P%d: %d palettes from %s; no agents, no tokens" % (k, len(pals), src))
    for i, p in enumerate(pals, 1):
        r = p["roles"]
        print("  v%d %-22s ground %s surface %s ink %s primary %s accent %s (ink %.1f:1, button %.1f:1)" % (
            i, p["name"], r["ground"], r["surface"], r["ink"], r["primary"], r.get("accent") or "-", p["contrast"]["ink_on_ground"], p["contrast"]["button_text_on_primary"]))
    print("Next: pick 1-2 (the human): bash .uak/bin/uak design pick P%d --k 2 ; then `uak design round` builds the landing with them" % k)
    return 0


def picked_palettes(root):
    """The palettes the human picked in the latest palette round that has picks, valid ones only: ([palette], note)."""
    base = Path(root) / ".uak" / "design" / "rounds"
    rounds = sorted((p for p in base.glob("P*") if re.match(r"^P\d+$", p.name)), key=lambda p: -int(p.name[1:])) if base.is_dir() else []
    for r in rounds:
        try:
            picks = json.loads((r / "picks.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out, skipped = [], []
        for vid in [i for i in picks.get("picked", []) if isinstance(i, str)]:
            try:
                p = json.loads((r / vid / "genome.json").read_text(encoding="utf-8"))["palette"]
            except (OSError, ValueError, KeyError):
                continue
            bad = problems(p)
            (skipped.append("%s/%s: %s" % (r.name, vid, "; ".join(bad))) if bad else out.append(p))
        if out or skipped:
            return out, ("palettes from %s%s" % (r.name, ("; skipped " + " | ".join(skipped)) if skipped else ""))
    return [], ""


def with_ground(pal, ground):
    """The same palette on the other ground (same dominant and accent), for the light/dark split."""
    return pal if pal["ground"] == ground else build_palette(pal["dominant"], pal.get("accent_source"), ground, extras=pal.get("extras") or (), soft=pal["name"].endswith("soft"))


def palette_lines(pal):
    """The TASK.md section for a variant's palette."""
    r, s = pal["roles"], pal["shares"]
    lines = ["## Palette (picked by the human before building; use exactly these hex values as `:root` tokens)",
             "- ground %s (%d%% of the area) · surface %s (%d%%) · ink %s (%d%%) · primary %s (%d%%, buttons and links; button text %s)" % (
                 r["ground"], s["ground"], r["surface"], s["surface"], r["ink"], s["ink"], r["primary"], s["primary"], r["button_text"])]
    if r.get("accent"):
        lines.append("- accent %s (%d%%, one small thing: a number, a chart line, a mark) · border %s" % (r["accent"], s["accent"], r["border"]))
    lines += ["- Contrast is already checked: ink on ground %.1f:1, body text on surface %.1f:1, button text on primary %.1f:1. Do not change a role to \"fix\" a look." % (
        pal["contrast"]["ink_on_ground"], pal["contrast"]["ink_on_surface"], pal["contrast"]["button_text_on_primary"]),
        "- At most 2 saturated hues in one view (the primary%s). Nothing else saturated; media may bring its own color." % (" and the accent" if r.get("accent") else ""),
        "- Never put the primary and the accent side by side at the same lightness; neutrals stay tinted, never pure black, white or grey.", ""]
    return lines
