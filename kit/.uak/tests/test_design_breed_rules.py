#!/usr/bin/env python3
"""UAK-083: a bred round follows the rules a fresh one does. Why (colonIA R2, 2026-11-14): bred from R1, the round had no
palettes (the human's picks of P1 were ignored), v1/v3 were both Anton and v2/v4 both Fraunces ("las fuentes en todos ya
son las mismas"), and 4 of 6 stages were three.js ("no gastar cantidades exageradas de recursos en el three js"); the lead
fixed all three by hand. Also `design shoot --again` and the install hint when Python Playwright is missing."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect, resolve_binary

IDEA = "# IDEA · X\n\n## 0. Name and brand\n- Name: **X** · Brand: #E6007E #FFB703 #1F3B8C #0B0F14 #F4F1EA\n\n## 1. One line\nFor **a**, X helps.\n"


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = Path(package) / ".uak"
        self.lib = self.pkg / "bin" / "lib"
        sys.path.insert(0, str(self.lib))
        self.base = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester", UAK_NO_COLOR="1", UAK_HUMAN="ana", UAK_DESIGN_PRIOR="none")
        for k in ("SSH_CONNECTION", "SSH_TTY", "UAK_DESIGN_SHOOT"):
            self.base.pop(k, None)
        self.n = 0

    def project(self, project_md=""):
        self.n += 1
        d = self.tmp / ("p é%d" % self.n)  # a space and an accent on purpose (CI TMPDIR)
        self.base["UAK_TASTE_HOME"] = str(self.tmp / ("taste%d" % self.n))
        (d / ".uak").mkdir(parents=True)
        (d / "IDEA.md").write_text(IDEA, encoding="utf-8")
        if project_md:
            (d / ".uak/PROJECT.md").write_text(project_md, encoding="utf-8")
        return d

    def design(self, cwd, *args, env=None, ok=(0,)):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design")] + list(args), cwd=str(cwd), env=dict(self.base, **(env or {})),
                             capture_output=True, text=True, timeout=240)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out

    def genomes(self, d, rnd):
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((d / ".uak/design/rounds" / rnd).glob("v*/genome.json"), key=lambda p: int(p.parent.name[1:]))]

    def bred(self, seed, n=6, project_md="", palettes=True):
        """R1 (fresh) -> the human picks v1 v2 v3 (and palettes P1 v1 v2) -> R2 bred."""
        d = self.project(project_md)
        self.design(d, "round", "--n", str(n), "--seed", str(seed), "--yes")
        base = d / ".uak/design/rounds"
        (base / "R1/picks.json").write_text(json.dumps({"picked": ["v1", "v2", "v3"], "notes": {}}), encoding="utf-8")
        if palettes:
            self.design(d, "palettes", "--n", "4")
            (base / "P1/picks.json").write_text(json.dumps({"picked": ["v1", "v2"], "notes": {}}), encoding="utf-8")
        self.design(d, "round", "--from", "R1", "--n", str(n), "--seed", str(seed), "--yes")
        return d


def three(g):
    return str(g["genes"]["stage"]).lower().startswith("three.js")


def bred_round_uses_picked_palettes(e):
    for seed in (1, 2, 3):
        d = e.bred(seed)
        picked = {json.loads(p.read_text(encoding="utf-8"))["palette"]["dominant"] for p in (d / ".uak/design/rounds/P1").glob("v*/genome.json")
                  if p.parent.name in ("v1", "v2")}
        kids = e.genomes(d, "R2")
        for g in kids:
            expect(g.get("palette"), "seed %d %s has no palette (the human's picks of P1 were ignored)" % (seed, g["id"]))
            expect(g["palette"]["dominant"] in picked, "seed %d %s: palette %s is not one the human picked %s" % (seed, g["id"], g["palette"]["dominant"], sorted(picked)))
            ground = g["palette"]["ground"]
            expect(e_ground(g) == ground, "seed %d %s: color gene %s says %s, the palette is %s" % (seed, g["id"], g["genes"]["color"], e_ground(g), ground))
    none = e.genomes(e.bred(1, palettes=False), "R2")
    expect(not any(g.get("palette") for g in none), "no picked palettes -> no palette (as before)")
    return "every child has a picked palette on the ground its color gene names"


def e_ground(g):
    import design_round
    return design_round.ground_of(g["genes"])


def bred_round_fonts_distinct(e):
    for seed in (1, 2, 3, 4):
        kids = e.genomes(e.bred(seed, palettes=False), "R2")
        faces = [g["fonts"]["display"].lower() for g in kids]
        expect(len(set(faces)) == len(faces), "seed %d: display faces repeat: %s" % (seed, faces))
    return "no two children of a bred round share a display face"


def webgl_cap_fresh_and_bred(e):
    import design_round
    items = [{"genes": {"stage": "three.js scene"}} for _ in range(5)] + [{"genes": {"stage": "canvas 2D generative"}}]
    expect(design_round.cap_webgl(items, 2) == 3 and sum(three(i) for i in items) == 2, "unit: 3 of 5 moved")
    expect(all("Design-Max-WebGL" in i["because"] for i in items[2:5]), "because says why: %s" % items[2].get("because"))
    for seed in range(1, 6):
        fresh = e.project()
        e.design(fresh, "round", "--n", "8", "--seed", str(seed), "--yes")
        expect(sum(three(g) for g in e.genomes(fresh, "R1")) <= 2, "fresh seed %d: at most 2 three.js" % seed)
        kids = e.genomes(e.bred(seed, n=8, palettes=False), "R2")
        expect(sum(three(g) for g in kids) <= 2, "bred seed %d: at most 2 three.js" % seed)
    one = e.genomes(e.bred(2, n=8, project_md="- Design-Max-WebGL: 1\n", palettes=False), "R2")
    expect(sum(three(g) for g in one) <= 1, "PROJECT.md Design-Max-WebGL: 1 is honoured")
    return "fresh and bred rounds keep at most Design-Max-WebGL three.js stages"


STUB = """import sys, os
from pathlib import Path
v = Path(sys.argv[2])
Path(v, "1280.png").write_text("png")
Path(v, "390.png").write_text("png")
with open(os.environ["SHOOT_LOG"], "a") as f:
    f.write(v.name + "\\n")
"""


def shoot_again_recaptures(e):
    d = e.project()
    e.design(d, "round", "--n", "2", "--seed", "1", "--yes")
    stub, log = e.tmp / "stub shoot é.py", e.tmp / "shoot.log"
    stub.write_text(STUB, encoding="utf-8")
    log.write_text("", encoding="utf-8")
    env = {"UAK_DESIGN_SHOOT": str(stub), "SHOOT_LOG": str(log)}
    for v in (d / ".uak/design/rounds/R1").glob("v*"):
        (v / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    e.design(d, "shoot", "R1", env=env)
    expect(len(log.read_text().split()) == 2, "first shoot captures both")
    again = e.design(d, "shoot", "R1", env=env)
    expect(len(log.read_text().split()) == 2 and "--again" in again.stdout, "without the flag nothing is recaptured and the line names it: " + again.stdout)
    e.design(d, "shoot", "R1", "v1", "--again", env=env)
    expect(log.read_text().split()[2:] == ["v1"], "--again recaptures v1 only: %s" % log.read_text().split())
    e.design(d, "shoot", "R1", "--again", env=env)
    expect(len(log.read_text().split()) == 5, "--again on the round recaptures all")
    return "--again recaptures variants that already have PNGs"


def shoot_says_how_to_install_playwright(e):
    d = e.project()
    e.design(d, "round", "--n", "1", "--seed", "1", "--yes")
    v = d / ".uak/design/rounds/R1/v1"
    (v / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    sk = d / ".claude/skills/motionsites-web-builder/scripts"
    sk.mkdir(parents=True)
    (sk / "shoot.py").write_text("import sys\nfrom pathlib import Path\nVIEWS = [(\"desktop\", 1440, 900), (\"mobile\", 390, 844)]\n"
                                 "out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)\n"
                                 "(out / 'desktop.png').write_text('png'); (out / 'mobile.png').write_text('png')\n", encoding="utf-8")
    shim = e.tmp / "noplaywright" / "playwright"
    shim.mkdir(parents=True)
    (shim / "__init__.py").write_text("raise ImportError('blocked by the test')\n", encoding="utf-8")
    out = e.design(d, "shoot", "R1", env={"PYTHONPATH": str(shim.parent), "PATH": os.environ["PATH"]}, ok=(0, 1))
    text = out.stdout + out.stderr
    expect("pip install playwright && python -m playwright install chromium" in text and "QA report" in text, "the install hint: " + text)
    return "the fallback names how to install Playwright"


TESTS = [bred_round_uses_picked_palettes, bred_round_fonts_distinct, webgl_cap_fresh_and_bred, shoot_again_recaptures, shoot_says_how_to_install_playwright]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-breed-rules-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_BREED_RULES_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
