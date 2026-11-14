#!/usr/bin/env python3
"""UAK-078: colors that combine. Palettes are built from the project's brand colors with harmony rules (one dominant hue,
neutrals tinted toward it, at most 2 saturated hues, no vibrating pair), with roles, area shares and exact hex, and pass
contrast before a page is built; `uak design palettes` is a palette round with no agents; the landing round uses the palettes
the human picked (light and dark kept in balance); the capture measures the 1920 fold and flags palette drift; the taste
profile learns palette features. Brand colors below are the real colonIA and AXIA ones."""
import argparse
import base64
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zlib
from pathlib import Path

from test_hack import expect, resolve_binary

COLONIA = ["#E6007E", "#FFB703", "#00A86B", "#1F3B8C", "#0B0F14", "#F4F1EA"]
AXIA = ["#0367FC", "#0B1020", "#00D5FF", "#EBF0FF"]
IDEA = "# IDEA · X\n\n## 0. Name and brand\n- Name: **X** · Brand: %s\n\n## 1. One line\nFor **a**, X helps.\n"


def png(w, h, bands):
    """A PNG of horizontal bands: bands = [(hex, share of the height)]."""
    rows, y = [], 0
    for hx, share in bands:
        r, g, b = (int(hx[i:i + 2], 16) for i in (1, 3, 5))
        rows += [b"\x00" + bytes((r, g, b)) * w] * int(round(h * share))
    rows += [rows[-1]] * (h - len(rows))
    raw = b"".join(rows[:h])

    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b"")


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = Path(package) / ".uak"  # the candidate under test (smoke passes --package)
        self.lib = self.pkg / "bin" / "lib"
        sys.path.insert(0, str(self.lib))
        os.environ["UAK_TASTE_HOME"] = str(self.tmp / "taste")
        os.environ["UAK_DESIGN_PRIOR"] = "none"
        import design_color
        import design_round
        import design_taste
        self.dc, self.dr, self.dt = design_color, design_round, design_taste
        self.base = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester", UAK_NO_COLOR="1", UAK_HUMAN="ana")
        for k in ("SSH_CONNECTION", "SSH_TTY", "UAK_DESIGN_SHOOT"):
            self.base.pop(k, None)
        self.n = 0

    def project(self, brand=COLONIA):
        self.n += 1
        d = self.tmp / ("p%d" % self.n)
        (d / ".uak").mkdir(parents=True)
        (d / "IDEA.md").write_text(IDEA % " ".join(brand), encoding="utf-8")
        return d

    def design(self, cwd, *args, env=None, ok=(0,)):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design")] + list(args), cwd=str(cwd), env=dict(self.base, **(env or {})),
                             capture_output=True, text=True, timeout=240)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out

    def genomes(self, d, rnd):
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((d / ".uak/design/rounds" / rnd).glob("v*/genome.json"), key=lambda p: int(p.parent.name[1:]))]


def dominant_hue_and_tinted_neutrals(e):
    dc = e.dc
    for brand in (COLONIA, AXIA):
        pals = dc.build_palettes(brand, 6)
        expect(len(pals) == 6 and len({(p["dominant"], p["accent_source"], p["ground"], p["name"]) for p in pals}) == 6, "six distinct palettes: %s" % [p["name"] for p in pals])
        for p in pals:
            r = p["roles"]
            L, C, h = dc.oklch(r["primary"])
            expect(set(r) >= {"ground", "surface", "ink", "primary", "button_text", "border"} and sum(p["shares"].values()) == 100, "roles and shares: %s" % p)
            for role in ("ground", "surface", "ink", "border"):
                nl, nc, nh = dc.oklch(r[role])
                rgb = dc.parse_hex(r[role])
                expect(len(set(rgb)) > 1 and r[role] not in ("#FFFFFF", "#000000"), "%s is tinted, not pure grey/black/white: %s" % (role, r[role]))
                expect(nc > 0.004 and dc.hue_gap(nh, h) < 30, "%s %s leans toward the dominant hue %.0f (is %.0f, chroma %.3f)" % (role, r[role], h, nh, nc))
    return "12 palettes, neutrals tinted"


def at_most_two_saturated_hues(e):
    dc = e.dc
    for p in dc.build_palettes(COLONIA, 6):
        loud = [c for c in [p["roles"]["primary"], p["roles"].get("accent")] + p["extras"] if c and dc.is_saturated(c)]
        expect(len(loud) <= 2, "%s: %d saturated: %s" % (p["name"], len(loud), loud))
        expect(len(p["extras"]) >= 1 and not any(dc.is_saturated(x) for x in p["extras"]), "the other brand colors stay desaturated: %s" % p["extras"])
    p = dc.build_palette("#E6007E", "#00A86B", "light", extras=COLONIA)
    p["extras"] = ["#E6007E", "#FFB703"]  # three more loud colors: not allowed
    expect(any("saturated hues" in x for x in dc.problems(p)), "problems() names it: %s" % dc.problems(p))
    return "never more than 2 saturated hues"


def no_vibrating_pairs(e):
    dc = e.dc
    blue, orange = "#2B6BFF", "#FF9A1F"  # complementary, close in lightness
    (lb, _, hb), (lo, _, ho) = dc.oklch(blue), dc.oklch(orange)
    expect(150 <= dc.hue_gap(hb, ho) <= 210 and abs(lb - lo) < 0.25, "the test pair is complementary: gap %.0f, dL %.2f" % (dc.hue_gap(hb, ho), abs(lb - lo)))
    seen = 0
    for ground in ("light", "dark"):
        for soft in (False, True):
            p = dc.build_palette(blue, orange, ground, extras=[blue, orange], soft=soft)
            (l1, c1, h1), (l2, c2, h2) = dc.oklch(p["roles"]["primary"]), dc.oklch(p["roles"]["accent"])
            expect(abs(l1 - l2) >= 0.10 and c2 <= c1 + 1e-6, "%s: primary and accent differ in lightness (%.2f vs %.2f) and the accent is quieter (%.3f vs %.3f)" % (p["name"], l1, l2, c1, c2))
            expect(not dc.problems(p), "no problems: %s" % dc.problems(p))
            seen += 1
    bad = dc.build_palette(blue, None, "light")
    bad["roles"]["accent"] = dc.from_oklch(dc.oklch(bad["roles"]["primary"])[0], 0.18, (dc.oklch(bad["roles"]["primary"])[2] + 180) % 360)
    expect(any("vibrate" in x for x in dc.problems(bad)), "problems() catches a hand-made vibrating pair: %s" % dc.problems(bad))
    return "%d complementary palettes keep their lightness apart" % seen


def contrast_checked_before_build(e):
    dc = e.dc
    pals = dc.build_palettes(["#FFD400", "#0A0A0A", "#FF3B30"], 6)  # a yellow brand: naive white-on-yellow buttons fail
    expect(len(pals) >= 4, "palettes were built: %d" % len(pals))
    for p in pals:
        r = p["roles"]
        expect(dc.contrast(r["ink"], r["ground"]) >= 7 and dc.contrast(r["ink"], r["surface"]) >= 4.5 and dc.contrast(r["button_text"], r["primary"]) >= 4.5,
               "%s passes contrast: %s" % (p["name"], p["contrast"]))
        expect(dc.contrast(r["primary"], r["ground"]) >= 3, "the primary stands out from the ground")
    broken = json.loads(json.dumps(pals[0]))
    broken["roles"]["ink"] = broken["roles"]["surface"]
    expect(any("ink on ground" in x for x in dc.problems(broken)), "problems() names the failing contrast: %s" % dc.problems(broken))
    # a picked palette that no longer passes is skipped, not built
    d = e.project()
    e.design(d, "palettes", "--n", "4")
    pj = d / ".uak/design/rounds/P1/v1/genome.json"
    g = json.loads(pj.read_text(encoding="utf-8"))
    g["palette"]["roles"]["ink"] = g["palette"]["roles"]["ground"]
    pj.write_text(json.dumps(g), encoding="utf-8")
    (d / ".uak/design/rounds/P1/picks.json").write_text(json.dumps({"picked": ["v1"], "notes": {}}), encoding="utf-8")
    out = e.design(d, "round", "--n", "4", "--seed", "3", "--yes")
    expect("skipped P1/v1: ink on ground" in out.stdout, "the round says it skipped it: " + out.stdout[-600:])
    expect(not any(x.get("palette") for x in e.genomes(d, "R1")), "no variant was built on it")
    return "contrast gates every palette"


def palette_round_needs_no_agents(e):
    d = e.project()
    out = e.design(d, "palettes", "--n", "5")
    expect("DESIGN_PALETTES P1: 5 palettes" in out.stdout and "no agents, no tokens" in out.stdout and "#E6007E" in out.stdout, "the round: " + out.stdout)
    base = d / ".uak/design/rounds/P1"
    vs = sorted(base.glob("v*"))
    expect(len(vs) == 5, "five variants")
    for v in vs:
        g = json.loads((v / "genome.json").read_text(encoding="utf-8"))
        expect(g["palette"]["roles"]["primary"] and not (v / "TASK.md").exists() and not (v / "index.html").exists() and not (v / "metrics.json").exists(), "a palette, no TASK for an agent, nothing built: %s" % v.name)
    again = e.design(d, "palettes", "--n", "2")
    expect((d / ".uak/design/rounds/P2").is_dir(), "the next palette round is P2")
    # the pick page shows swatch strips and a tiny mock
    o = subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "P1", "--no-open"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=90)
    m = re.search(r"http://127\.0\.0\.1:(\d+)/", o.stdout)
    expect(o.returncode == 0 and m, "start: " + o.stdout + o.stderr)
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/pick.html" % m.group(1), timeout=10) as r:
            page = r.read().decode("utf-8")
    finally:
        subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "P1", "--stop"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=60)
    g1 = json.loads((vs[0] / "genome.json").read_text(encoding="utf-8"))["palette"]
    expect(page.count('class="mock"') == 5 or page.count('class="mock" ') == 5 or page.count("class=\"mock\"") >= 5, "a mock per palette: %d" % page.count("mock"))
    expect('class="strip"' in page and g1["roles"]["primary"] in page and g1["roles"]["ground"] in page and "polyline" in page and ">Button<" in page, "swatch strip, headline, button and chart line")
    return "palette round without agents, strips and mock on the page"


def variants_use_picked_palette(e):
    d = e.project()
    e.design(d, "palettes", "--n", "6")
    pk = [json.loads((d / ".uak/design/rounds/P1" / v / "genome.json").read_text(encoding="utf-8"))["palette"] for v in ("v1", "v2")]
    (d / ".uak/design/rounds/P1/picks.json").write_text(json.dumps({"picked": ["v1", "v2"], "notes": {}, "by": "ana"}), encoding="utf-8")
    out = e.design(d, "round", "--n", "6", "--seed", "3", "--yes")
    expect("palettes from P1" in out.stdout, "the round names its palettes: " + out.stdout[-500:])
    gs = e.genomes(d, "R1")
    doms = {p["dominant"] for p in pk}
    for g in gs:
        expect(g["palette"]["dominant"] in doms and g["palette"]["ground"] == g["ground"], "variant uses a picked palette on its ground: %s" % g["palette"]["name"])
        expect(e.dr.ground_of(g["genes"]) == g["ground"] and "palette" in g["why"]["color"], "the color gene and the why say so: %s %s" % (g["genes"]["color"], g["why"]["color"]))
    grounds = [g["ground"] for g in gs]
    expect(grounds.count("light") >= 2 and grounds.count("dark") >= 2, "light and dark stay balanced: %s" % grounds)
    expect(len({g["palette"]["dominant"] for g in gs}) == len(doms), "both picked palettes are used")
    task = (d / ".uak/design/rounds/R1/v1/TASK.md").read_text(encoding="utf-8")
    r = gs[0]["palette"]["roles"]
    for needle in ("## Palette (picked by the human", r["ground"], r["surface"], r["ink"], r["primary"], r["button_text"], "(55% of the area)", "use exactly these hex values", "At most 2 saturated hues", "Contrast is already checked"):
        expect(needle in task, "TASK.md lacks %r" % needle)
    expect("- project colors:" not in task, "the palette replaces the loose brand list")
    plain = e.project()
    e.design(plain, "round", "--n", "4", "--seed", "3", "--yes")
    expect(not any(g.get("palette") for g in e.genomes(plain, "R1")), "no palette round, no palette: the round draws as before")
    return "picked palettes drive the variants, light/dark balanced"


def capture_flags_palette_drift(e):
    dc = e.dc
    pal = dc.build_palette("#E6007E", "#00A86B", "light", extras=COLONIA)
    r = pal["roles"]
    good = png(1920, 1080, [(r["ground"], 0.55), (r["surface"], 0.25), (r["ink"], 0.12), (r["primary"], 0.08)])
    loud = png(1920, 1080, [("#E6007E", 0.5), ("#00A86B", 0.5)])  # saturated, and a complementary pair
    dark = png(1920, 1080, [("#0B1020", 1.0)])
    m = dc.measure_png  # on files
    d = e.project()
    e.design(d, "palettes", "--n", "2")
    rnd = d / ".uak/design/rounds/R1"
    results = {}
    for i, (name, data) in enumerate((("good", good), ("loud", loud), ("dark", dark)), 1):
        v = rnd / ("v%d" % i)
        v.mkdir(parents=True)
        (v / "genome.json").write_text(json.dumps({"id": "R1-v%d" % i, "genes": {}, "palette": pal}), encoding="utf-8")
        (v / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
        (v / "metrics.json").write_text(json.dumps({"variant": v.name, "started": 1, "passes": 0, "tokens": {"value": None}}), encoding="utf-8")
        (v / "1920.png.src").write_bytes(data)
    stub = e.tmp / "stub shoot é.py"
    stub.write_text("import sys, shutil\nfrom pathlib import Path\nv = Path(sys.argv[2])\nfor n in ('1280.png', '390.png', '1920.png'):\n    shutil.copyfile(str(v / '1920.png.src'), str(v / n))\n", encoding="utf-8")
    out = e.design(d, "shoot", "R1", env={"UAK_DESIGN_SHOOT": str(stub)})
    for i, name in enumerate(("good", "loud", "dark"), 1):
        results[name] = json.loads((rnd / ("v%d" % i) / "metrics.json").read_text(encoding="utf-8")).get("color")
    expect(all(results.values()), "every variant has a color measurement: %s" % results)
    gd = results["good"]
    expect(gd["saturated"] < 12 and not gd["drift"] and gd["roles"].get("ground", 0) > 40 and gd["dominant"], "a page that follows its palette: %s" % gd)
    lo = results["loud"]
    expect(lo["saturated"] > 90 and lo["clashes"] and any("saturated" in w for w in lo["drift"]) and any("clash" in w for w in lo["drift"]), "a loud pink and green page: %s" % lo)
    expect(any("a light palette but" in w for w in results["dark"]["drift"]), "a navy page on a light palette: %s" % results["dark"])
    expect("DESIGN_SHOOT QA v2 1920: palette drift:" in out.stdout and "DESIGN_SHOOT QA v1 1920: palette drift" not in out.stdout, "the shoot says which drifted: " + out.stdout)
    # the same measurement reads the real AXIA R3 numbers: 1-3% saturated, mostly navy
    navy = png(1920, 1080, [("#0B1020", 0.77), ("#151D3A", 0.2), ("#0367FC", 0.03)])
    (e.tmp / "navy.png").write_bytes(navy)
    nv = m(e.tmp / "navy.png")
    expect(nv["saturated"] <= 4 and nv["dark"] > 95, "an almost monochrome navy fold: %s" % {k: nv[k] for k in ("saturated", "dark")})
    # the pick page shows the planned strip and the measured one, and the flag
    o = subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--no-open"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=90)
    mm = re.search(r"http://127\.0\.0\.1:(\d+)/", o.stdout)
    expect(o.returncode == 0 and mm, "start: " + o.stdout + o.stderr)
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/pick.html" % mm.group(1), timeout=10) as r2:
            page = r2.read().decode("utf-8")
    finally:
        subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--stop"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=60)
    card2 = page.split('data-id="v2"')[1].split("</article>")[0]
    expect("planned" in card2 and "measured at the fold" in card2 and "palette drift: " in card2, "planned strip, measured strip and the drift flag on the page: " + card2[-900:])
    return "measured at the 1920 fold; drift flagged"


def taste_learns_palette_features(e):
    dt, dc = e.dt, e.dc
    d = e.project()
    e.design(d, "palettes", "--n", "6")
    p1 = [json.loads((d / ".uak/design/rounds/P1" / ("v%d" % i) / "genome.json").read_text(encoding="utf-8"))["palette"] for i in range(1, 7)]
    (d / ".uak/design/rounds/P1/picks.json").write_text(json.dumps({"picked": ["v1", "v2"], "notes": {}, "by": "ana"}), encoding="utf-8")
    e.design(d, "round", "--n", "6", "--seed", "3", "--yes")
    (d / ".uak/design/rounds/R1/picks.json").write_text(json.dumps({"picked": ["v3"], "notes": {}, "by": "ana"}), encoding="utf-8")
    doc = dt.update(d, "ana")
    expect(set(doc["rounds"]) == {"%s:P1" % d.name, "%s:R1" % d.name}, "both rounds are folded: %s" % list(doc["rounds"]))
    tot = dt.totals(doc)
    for trait in dc.TRAITS:
        expect(trait in tot and sum(c["picked"] for c in tot[trait].values()) >= 2, "%s learned from the picks of both rounds: %s" % (trait, tot.get(trait)))
    want = {dc.traits_of(p1[0])["palette_hue"], dc.traits_of(p1[1])["palette_hue"]}
    expect(want & {h for h, c in tot["palette_hue"].items() if c["picked"] >= 1}, "the picked palettes' hue families are the liked ones: %s" % tot["palette_hue"])
    expect(dt.pick_count(doc) == 1, "palette picks do not make the landing taste confident: %d" % dt.pick_count(doc))
    expect("palette_hue" in dt.show("ana", doc) and "palette_neutral" in dt.show("ana", doc), "show lists them")
    expect(not any(re.search(r"#[0-9a-fA-F]{6}", json.dumps(v)) for v in doc["rounds"].values()), "traits, not hex")
    # a learned preference orders the next palette round
    first = dc.build_palettes(COLONIA, 3, prefer={"blue": 0.95, "pink": 0.1, "orange": 0.2, "green": 0.3})[0]
    expect(dc.oklch(first["dominant"])[2] and dc.hue_family(dc.oklch(first["dominant"])[2]) == "blue", "the liked hue family leads: %s" % first["name"])
    return "palette features in the profile, ordering the next round"


TESTS = [dominant_hue_and_tinted_neutrals, at_most_two_saturated_hues, no_vibrating_pairs, contrast_checked_before_build, palette_round_needs_no_agents,
         variants_use_picked_palette, capture_flags_palette_drift, taste_learns_palette_features]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-color-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_COLOR_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
