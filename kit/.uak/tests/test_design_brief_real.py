#!/usr/bin/env python3
"""UAK-074: the brief finds material and story beats the way teams write them (colonIA R1, Nov 11 2026: wow and ask MISSING
although IDEA.md had both, four real product screens called "3D cut-out", the real hex.geojson not found). Wide 16:9/16:10
PNG/JPG are product screens, a PNG with a transparent background is a cut-out, .geojson/.json with coordinates is real data
(a map), video is video; the wow comes from "Wow in one sentence:", "Wow en una frase:" or a **Wow N:** mark in the flow table;
the ask from an `Ask:` line or the CTA of the live product; Spanish headings count; the name comes from section 0 or the
<title>. The IDEA.md below is an excerpt of a real Spanish one (Pulso Barrial / colonIA, Chilangaton 2026), copied here."""
import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

from test_hack import expect, resolve_binary

IDEA_ES = """# IDEA · Pulso Barrial

## 0. Nombre y marca (fijo desde T0)

- Nombre: **Pulso Barrial** · repo: `pulso-barrial` · tagline: **"La red viva de la economía de barrio"** (7 palabras). [Decided]
- Idioma de la interfaz: español de México.

## 1. Una línea

Para **la SEDECO, el vecino y el comerciante de barrio de la CDMX**, donde **solo 6.7% de los negocios vende en línea**, **Pulso Barrial** les permite **ver dónde se mueve el dinero**, a diferencia de **los mapas estáticos de tianguis**.

## 2. Usuarios

| Persona | Momento | Necesidad | Paso del flujo |
|---|---|---|---|
| **Mtra. Rocío**, JUD de Mercados y Tianguis (alcaldía) | Recibe solicitudes de tianguis nuevos | Ver dónde y qué día falta comercio barrial | 1, 2, 6 |
| **Doña Lupe, 63 años, tianguista** | Pone su puesto de nopales | Que la encuentren sin llenar formularios | 4, 5 |

## 4. Flujo de la demo (6 pasos, 3 minutos; cada paso = una tarea vertical)

| # | Quien presenta hace | Se ve en pantalla | API | Prio |
|---|---|---|---|---|
| 1 | Abre la vista **SEDECO** | **Wow 1:** hexágonos 3D de Coyoacán e Iztapalapa; altura = actividad estimada de pago con tarjeta | `GET /api/hex` | P0 |
| 2 | Mueve la barra de domingo a martes | Los tianguis se apagan; aparecen los desiertos del martes | `GET /api/dinero` | P0 |

- Segundos hasta el primer wow: **≤ 15** (el mapa 3D aparece al abrir).

## 10. Datos citables (verificados el 25-oct-2026)

| Dato | Fuente |
|---|---|
| 339 mercados públicos, ~7 millones de clientes por semana | Presentación de retos del Chilangatón 2026 (SEDECO, SECTEI, SAF), documento del evento |
"""
WOW_SENTENCE = '- Wow en una frase: *"Una nota de voz de una tianguista la pone en el mapa del gobierno, en menos de un minuto."*\n'


def png(w, h, kind="rgb"):
    """A solid PNG: rgb (opaque), rgba_opaque (alpha 255 everywhere), rgba_clear (corners transparent)."""
    bpp = 3 if kind == "rgb" else 4
    ctype = 2 if kind == "rgb" else 6
    row = bytearray(b"\x00")
    for x in range(w):
        a = 0 if kind == "rgba_clear" and (x < w // 3 or x >= 2 * w // 3) else 255
        row += bytes((40, 90, 200) + (() if kind == "rgb" else (a,)))
    clear_row = bytes(row)
    data = b"".join(clear_row for _ in range(h))

    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(data, 6)) + chunk(b"IEND", b"")


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.lib = Path(package) / ".uak" / "bin" / "lib"  # the candidate under test (smoke passes --package)
        sys.path.insert(0, str(self.lib))
        self.n = 0
        os.environ["UAK_TASTE_HOME"] = str(self.tmp / "taste")  # no history from the real home
        import design_round
        self.dr = design_round

    def project(self, idea=IDEA_ES, files=None):
        self.n += 1
        d = self.tmp / ("proj%d" % self.n)
        (d / ".uak").mkdir(parents=True)
        if idea is not None:
            (d / "IDEA.md").write_text(idea, encoding="utf-8")
        for rel, data in (files or {}).items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return d

    def brief(self, d):
        r = subprocess.run([sys.executable, str(self.lib / "design_round.py"), "round", "--n", "4", "--seed", "3", "--yes"], cwd=str(d),
                           capture_output=True, text=True, timeout=120)
        expect(r.returncode == 0, "round: " + r.stdout + r.stderr)
        return (d / ".uak/design/rounds/R1/brief.md").read_text(encoding="utf-8")


def screens_vs_cutouts(e):
    d = e.project(files={
        "assets/producto-0.png": png(1280, 800),            # 16:10 capture whose name says "producto": a screen, not a cut-out
        "assets/captura-1.png": png(1920, 1080),            # 16:9
        "assets/foto-pagina.jpg": b"\xff\xd8\xff\xc0\x00\x11\x08\x03\xe8\x06\x40\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01",  # JPEG header: 1600 x 1000
        "assets/auto.png": png(900, 600, "rgba_clear"),     # transparent corners: a cut-out
        "assets/solid-rgba.png": png(1280, 720, "rgba_opaque"),  # alpha channel but opaque: still a screen
        "assets/mascota-chica.png": png(300, 300),          # small opaque, named mascot: a cut-out by name
        "assets/loop.mp4": b"x", "assets/intro.webm": b"x"})
    mat = e.dr.project_material(d)
    shots = mat.get("product screenshot", [])
    expect(set(shots) == {"assets/producto-0.png", "assets/captura-1.png", "assets/foto-pagina.jpg", "assets/solid-rgba.png"}, "screens: %s" % shots)
    expect(set(mat.get("3D cut-out", [])) == {"assets/auto.png", "assets/mascota-chica.png"}, "cut-outs: %s" % mat.get("3D cut-out"))
    expect(set(mat.get("video loop", [])) == {"assets/loop.mp4", "assets/intro.webm"}, "video: %s" % mat.get("video loop"))
    w, h, clear = e.dr.image_info(d / "assets/auto.png")
    expect((w, h, clear) == (900, 600, True), "dimensions and transparent corners read without Pillow: %s" % ((w, h, clear),))
    expect(e.dr.image_info(d / "assets/foto-pagina.jpg")[:2] == (1600, 1000), "JPEG size from its header")
    expect(e.dr.is_screen_shape(1280, 800) and e.dr.is_screen_shape(1920, 1080) and not e.dr.is_screen_shape(900, 600) and not e.dr.is_screen_shape(800, 450), "16:9 and 16:10 from 1000 px up")
    brief = e.brief(d)
    expect("product screenshot: assets/captura-1.png" in brief or "assets/captura-1.png" in brief.split("## Material")[1], "the brief lists the screens: " + brief[-900:])
    return "screens, cut-outs, video"


def geojson_is_real_data(e):
    gj = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": 1}, "geometry": {"type": "Polygon", "coordinates": [[[-99.16, 19.35], [-99.15, 19.35], [-99.15, 19.36], [-99.16, 19.35]]]}}]})
    d = e.project(files={"assets/hex.geojson": gj, "data/puestos.json": json.dumps([{"name": "x", "lat": 19.3, "lng": -99.1}]), "data/config.json": json.dumps({"theme": "dark"})})
    mat = e.dr.project_material(d)
    expect(set(mat.get("real data (map)", [])) == {"assets/hex.geojson", "data/puestos.json"}, "real data: %s" % mat)
    expect("data/config.json" not in str(mat), "a .json with no coordinates is not map data: %s" % mat)
    brief = e.brief(d)
    expect("real data (map): " in brief and "assets/hex.geojson" in brief, "brief.md lists the real data: " + brief[brief.index("## Material"):][:500])
    f = e.dr.material_factors(mat)["imagery"]
    expect(f["illustration"] == 1.0, "a map rebuilt live from the data counts as vector art for the imagery gene: %s" % f)
    return "geojson and coordinate json"


def wow_inside_flow_table(e):
    b = e.dr.read_beats(IDEA_ES)
    expect(b["wow"] and b["wow"].startswith("hexágonos 3D de Coyoacán"), "the **Wow 1:** cell of the flow table: %r" % b["wow"])
    spanish = e.dr.read_beats(IDEA_ES.replace("- Segundos hasta", WOW_SENTENCE + "- Segundos hasta"))
    expect(spanish["wow"].startswith("Una nota de voz de una tianguista"), "'Wow en una frase:' wins over the table: %r" % spanish["wow"])
    expect(not spanish["wow"].startswith(("*", '"')), "no markdown around it: %r" % spanish["wow"])
    plain = e.dr.read_beats(IDEA_ES.replace("**Wow 1:**", "**Wow:**"))
    expect(plain["wow"].startswith("hexágonos"), "**Wow:** with no number")
    english = e.dr.read_beats("## 4. Demo flow\n\n| # | User does | Sees | Prio |\n|---|---|---|---|\n| 1 | x | y | P0 |\n\n- Wow in one sentence: it learns. · seconds until the wow: 30\n")
    expect(english["wow"] == "it learns.", "the English line still works: %r" % english["wow"])
    expect(e.dr.read_beats("## 4. Flujo\n\n| # | a | b |\n|---|---|---|\n| 1 | x | y |\n")["wow"] is None, "no mark, no wow: MISSING, never invented")
    web = e.project(files={"web/index.html": '<html><head><title>Pulso Barrial · mapa</title></head><body><a class="hero-cta primary" href="/s">Ver el mapa de SEDECO</a><button>Otro</button></body></html>'})
    ask = e.dr.read_beats(IDEA_ES, web)["ask"]
    expect(ask and ask.startswith("Ver el mapa de SEDECO") and "CTA of the live product" in ask, "the ask from the live CTA: %r" % ask)
    said = e.dr.read_beats(IDEA_ES + "\n- Ask: Escríbenos\n", web)["ask"]
    expect(said == "Escríbenos", "an Ask: line wins over the CTA: %r" % said)
    expect(e.dr.read_beats(IDEA_ES)["ask"] is None, "no Ask line and no product: MISSING")
    return "wow from the flow table, ask from the CTA"


def spanish_headings(e):
    b = e.dr.read_beats(IDEA_ES)
    expect(b["one line"].startswith("Para **la SEDECO") and "Pulso Barrial" in b["one line"], "Una línea: %r" % b["one line"])
    expect(b["users"] and "Mtra. Rocío" in b["users"] and "Doña Lupe" in b["users"], "Usuarios: %r" % b["users"])
    expect(b["steps"] and "Abre la vista **SEDECO**" in b["steps"], "Flujo de la demo: %r" % b["steps"])
    expect(b["proof"] and "339 mercados públicos" in b["proof"] and "source: Presentación de retos" in b["proof"], "Datos citables: %r" % b["proof"])
    # the same headings without numbers
    bare = IDEA_ES
    for old, new in (("## 0. ", "## "), ("## 1. ", "## "), ("## 2. ", "## "), ("## 4. ", "## "), ("## 10. ", "## ")):
        bare = bare.replace(old, new)
    nb = e.dr.read_beats(bare)
    expect(nb["one line"] == b["one line"] and nb["users"] == b["users"] and nb["steps"] == b["steps"] and nb["proof"] == b["proof"], "unnumbered Spanish headings count the same: %r" % nb)
    expect(e.dr.product_name(Path("/x"), bare) == "Pulso Barrial", "and §0 without its number")
    brief = e.brief(e.project())
    missing = [l for l in brief.splitlines() if "MISSING (not in IDEA.md)" in l]
    expect(len(missing) == 1 and "The ask" in missing[0], "only the ask is missing (this IDEA.md has none and no product to take a CTA from): %s" % missing)
    return "numbered and unnumbered Spanish headings"


def name_from_title(e):
    expect(e.dr.product_name(e.tmp, IDEA_ES) == "Pulso Barrial", "§0's name line: %r" % e.dr.product_name(e.tmp, IDEA_ES))
    expect(e.dr.product_name(e.tmp, "# IDEA · Axia\n\n## 0. Name and brand\n- Name: **AXIA by Kavak** (product: Inspector)\n") == "AXIA by Kavak", "English name line, product note cut off")
    d = e.project(idea="# IDEA · Old name\n\n## 1. One line\nx\n", files={"web/index.html": "<!doctype html><title>colonIA — mapa vivo de tianguis</title>"})
    expect(e.dr.product_name(d, (d / "IDEA.md").read_text(encoding="utf-8")) == "colonIA", "no §0 name: the <title> of the live product, without its tagline")
    plain = e.project(idea="# IDEA · From Heading\n\n## 1. One line\nx\n")
    expect(e.dr.product_name(plain, (plain / "IDEA.md").read_text(encoding="utf-8")) == "From Heading", "then the heading")
    none = e.project(idea=None)
    expect(e.dr.product_name(none, "") == none.name, "then the folder")
    expect("# Brief · colonIA · landing" in e.brief(d), "the brief header carries it")
    return "§0, <title>, heading, folder"


TESTS = [screens_vs_cutouts, geojson_is_real_data, wow_inside_flow_table, spanish_headings, name_from_title]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-brief-real-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_BRIEF_REAL_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
