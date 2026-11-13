#!/usr/bin/env python3
"""UAK-070: every design variant records metrics.json (started, first page, done, wall seconds, passes, load, tokens with
their source or null with a reason, never 0); `design done R<k> v<i> --tokens N` is how the builder reports its usage;
`design report` prints rows and totals (tokens, wall in parallel, tokens per picked variant); the next round's cost line
uses the measured median by stage family and warns, in sprint, when the round will not fit before the freeze; the pick page
shows tokens and minutes. No real browser: the capture tool is a stub named by UAK_DESIGN_SHOOT."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from test_hack import expect, resolve_binary

STUB = """import sys
from pathlib import Path
Path(sys.argv[2], "1280.png").write_text("png")
Path(sys.argv[2], "390.png").write_text("png")
"""
T0 = 1800000000


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = Path(package) / ".uak"  # the candidate under test (smoke passes --package)
        self.lib = self.pkg / "bin" / "lib"
        sys.path.insert(0, str(self.lib))
        self.stub = self.tmp / "stub shoot é.py"  # a space and an accent on purpose (CI TMPDIR)
        self.stub.write_text(STUB, encoding="utf-8")
        self.base = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester", UAK_NO_COLOR="1", UAK_HUMAN="ana", UAK_TASTE_HOME=str(self.tmp / "taste"),
                         UAK_METRICS_NOW=str(T0))
        for k in ("SSH_CONNECTION", "SSH_TTY", "UAK_DESIGN_SHOOT"):
            self.base.pop(k, None)
        self.n = 0

    def project(self, project_md="", name=None):
        self.n += 1
        d = self.tmp / (name or "p%d" % self.n)
        self.base["UAK_TASTE_HOME"] = str(self.tmp / ("taste%d" % self.n))  # one human history per project: no cross-talk between cases
        (d / ".uak").mkdir(parents=True)
        (d / "IDEA.md").write_text("# IDEA · X\n\n## 1. One line\nFor **a**, X helps.\n", encoding="utf-8")
        if project_md:
            (d / ".uak/PROJECT.md").write_text(project_md, encoding="utf-8")
        return d

    def design(self, cwd, *args, env=None, ok=(0,)):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design")] + list(args), cwd=str(cwd), env=dict(self.base, **(env or {})),
                             capture_output=True, text=True, timeout=180)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out

    def rnd(self, d, n=4, seed=3, env=None):
        self.design(d, "round", "--n", str(n), "--seed", str(seed), "--yes", env=env)

    def mj(self, d, rnd, v):
        expect((d / ".uak/design/rounds" / rnd / v / "metrics.json").is_file(), "%s/%s has a metrics.json" % (rnd, v))
        return json.loads((d / ".uak/design/rounds" / rnd / v / "metrics.json").read_text(encoding="utf-8"))

    def measured(self, d, rnd, spec):
        """Write metrics.json for variants: spec {v: (family stage text, tokens or None, seconds)} into an existing round."""
        for v, (stage, tokens, secs) in spec.items():
            vd = d / ".uak/design/rounds" / rnd / v
            vd.mkdir(parents=True, exist_ok=True)
            (vd / "genome.json").write_text(json.dumps({"genes": {"stage": stage}}), encoding="utf-8")
            (vd / "metrics.json").write_text(json.dumps({"variant": v, "family": "three.js" if stage.startswith("three.js") else "light", "started": T0, "done": T0 + secs,
                "wall_seconds": secs, "passes": 2, "tokens": {"value": tokens, "source": "reported by the builder (design done --tokens)" if tokens else None,
                "reason": None if tokens else "x"}}), encoding="utf-8")


def variant_metrics_written(e):
    d = e.project()
    e.rnd(d)
    m = e.mj(d, "R1", "v1")
    expect(m["started"] == T0 and m["passes"] == 0 and m["done"] is None and m["first_page"] is None, "at the start: %s" % m)
    expect("load_start" in m and "load_end" in m and m["family"] in ("light", "three.js"), "load and family recorded: %s" % m)
    task = (d / ".uak/design/rounds/R1/v1/TASK.md").read_text(encoding="utf-8")
    expect("design done R1 v1 --tokens N" in task, "TASK.md tells the agent to report its usage")
    for v in ("v1", "v2"):
        (d / ".uak/design/rounds/R1" / v / "index.html").write_text("<!doctype html><title>x</title>", encoding="utf-8")
    later = str(T0 + 300)
    e.design(d, "shoot", "R1", "v1", "v2", env={"UAK_DESIGN_SHOOT": str(e.stub), "UAK_METRICS_NOW": later})
    m = e.mj(d, "R1", "v1")
    expect(m["passes"] == 1 and m["done"] == T0 + 300 and m["wall_seconds"] == 300, "after one capture: %s" % m)
    expect(m["first_page"] is not None and m["first_page"] >= m["started"], "first page: %s" % m)
    for f in ("1280.png", "390.png"):
        (d / ".uak/design/rounds/R1/v1" / f).unlink()
    e.design(d, "shoot", "R1", "v1", env={"UAK_DESIGN_SHOOT": str(e.stub), "UAK_METRICS_NOW": str(T0 + 420)})
    m = e.mj(d, "R1", "v1")
    expect(m["passes"] == 2 and m["wall_seconds"] == 420, "a second look-and-fix pass: %s" % m)
    expect(e.mj(d, "R1", "v3")["passes"] == 0, "a variant never captured stays at 0 passes")
    e.design(d, "done", "R1", "v2", "--tokens", "61234", env={"UAK_METRICS_NOW": str(T0 + 600)})
    t = e.mj(d, "R1", "v2")["tokens"]
    expect(t["value"] == 61234 and "builder" in t["source"] and t["reason"] is None, "reported tokens and where they come from: %s" % t)
    return "started, first page, passes, done, tokens"


def tokens_null_with_reason_when_unknown(e):
    d = e.project()
    e.rnd(d, n=2)
    t = e.mj(d, "R1", "v1")["tokens"]
    expect(t["value"] is None and "design done R1 v1 --tokens N" in t["reason"] and "uak tokens" in t["reason"], "null with the reason: %s" % t)
    expect(t["source"] is None, "no source for a number nobody gave")
    for bad in ("0", "-5", "abc", "1.5k"):
        out = e.design(d, "done", "R1", "v1", "--tokens", bad, ok=(2,))
        expect("Usage" in out.stderr, "%r refused" % bad)
    expect(e.mj(d, "R1", "v1")["tokens"]["value"] is None, "refusals changed nothing")
    out = e.design(d, "report", "R1")
    expect("n/a" in out.stdout and "tokens n/a" in out.stdout and " 0 " not in out.stdout.split("totals")[1].splitlines()[0], "the report says n/a, not 0: " + out.stdout)
    # the lead's hand-written round-level metrics.json is read when a variant has none of its own
    d2 = e.project()
    e.rnd(d2, n=2)
    for v in ("v1", "v2"):
        (d2 / ".uak/design/rounds/R1" / v / "metrics.json").unlink()
    (d2 / ".uak/design/rounds/R1/metrics.json").write_text(json.dumps({"variants": {"v1": {"tokens": 78305, "seconds": 29}, "v2": {"tokens": 72421, "seconds": None}}}), encoding="utf-8")
    out = e.design(d2, "report", "R1")
    expect("78k" in out.stdout and "151k" in out.stdout, "bonus: round-level file read: " + out.stdout)
    return "null with reason, never 0"


def report_totals_and_parallel_wall(e):
    d = e.project()
    e.rnd(d, n=3)
    e.measured(d, "R1", {"v1": ("SVG/CSS animation", 60000, 150), "v2": ("three.js scene", 140000, 3240), "v3": ("canvas 2D generative", 70000, 180)})
    (d / ".uak/design/rounds/R1/picks.json").write_text(json.dumps({"picked": ["v2", "v1"], "notes": {}}), encoding="utf-8")
    out = e.design(d, "report", "R1").stdout
    expect(re.search(r"v1\s+light\s+60k\s+2\.5\s+2", out) and re.search(r"v2\s+three\.js\s+140k\s+54\.0\s+2", out), "one row per variant: " + out)
    expect("totals: 270k tokens" in out, "tokens added up: " + out)
    expect("wall in parallel (longest variant): 54.0 min" in out, "the longest variant, not the sum: " + out)
    expect("tokens per picked variant: 135k (2 picked)" in out, "270k / 2 picked: " + out)
    # a second round and --all
    e.rnd(d, n=2)
    e.measured(d, "R2", {"v1": ("still (no animation)", 50000, 60), "v2": ("still (no animation)", None, 90)})
    allr = e.design(d, "report", "--all").stdout
    expect("R1: 3 variants" in allr and "R2: 2 variants" in allr and "(only 1 of 2 variants reported)" in allr, "every round: " + allr)
    expect("ALL 2 rounds: 320k tokens (4 of 5 variants reported)" in allr, "cumulative: " + allr)
    bad = e.design(d, "report", ok=(2,))
    expect("Usage" in bad.stderr, "usage")
    return "totals, parallel wall, per picked, --all"


def estimate_uses_measured_median_by_stage(e):
    d = e.project()
    cold = e.design(d, "round", "--n", "4", "--seed", "3", ok=(3,))
    expect("4 variants x 60k tokens = 240k tokens" in cold.stdout and "no history" in cold.stdout and "60k default" in cold.stdout, "no history is said: " + cold.stdout)
    e.rnd(d, n=5, seed=9)
    e.measured(d, "R1", {"v1": ("SVG/CSS animation", 50000, 120), "v2": ("canvas 2D generative", 60000, 150), "v3": ("still (no animation)", 70000, 180),
                         "v4": ("three.js scene", 120000, 1800), "v5": ("three.js scroll-driven", 140000, 2400)})
    out = e.design(d, "round", "--n", "6", "--seed", "4", ok=(3,))
    m = re.search(r"DESIGN_ROUND cost: (.+) = (\d+)k tokens", out.stdout)
    expect(m, "the cost line: " + out.stdout)
    total = 0
    for c, fam, k in re.findall(r"(\d+) (light|three\.js) x (\d+)k", m.group(1)):
        expect(int(k) == (60 if fam == "light" else 130), "median by family (light 60k, three.js 130k): " + m.group(1))
        total += int(c) * int(k)
    expect(total == int(m.group(2)) and sum(int(c) for c in re.findall(r"(\d+) (?:light|three\.js) x", m.group(1))) == 6, "the parts add up to the total over 6 variants: " + out.stdout)
    expect("DESIGN_ROUND source: median of 5 measured variants of ana's rounds, by stage family" in out.stdout, "says where it comes from: " + out.stdout)
    wall = re.search(r"DESIGN_ROUND wall: ~(\d+) min \(6 variants, 6 in parallel", out.stdout)
    fams = re.findall(r"(light|three\.js) x", m.group(1))
    expect(wall and int(wall.group(1)) == (35 if "three.js" in fams else 3), "wall = the slowest family median minutes (three.js 35, light 3): " + out.stdout)
    two = e.design(d, "round", "--n", "6", "--seed", "4", "--parallel", "3", ok=(3,))
    expect(("~%d min" % (70 if "three.js" in fams else 6)) in two.stdout and "3 in parallel" in two.stdout, "two waves at --parallel 3: " + two.stdout)
    return "median by family with its source"


def deadline_warning_in_sprint(e):
    hist = {"v1": ("three.js scene", 120000, 1800), "v2": ("three.js scene", 140000, 2400)}  # 30 and 40 min: a median of 35 min
    freeze_soon = T0 + 20 * 60
    sprint = e.project("Mode: sprint\nFreeze-Epoch: %d\n" % freeze_soon)
    e.rnd(sprint, n=2, seed=5)
    e.measured(sprint, "R1", hist)
    # 6 variants with three.js in the mix: ~35 min of wall against 20 minutes to the freeze
    out = e.design(sprint, "round", "--n", "6", "--seed", "4", ok=(3,))
    expect("three.js x" in out.stdout, "seed 4 draws three.js variants: " + out.stdout)
    expect("DESIGN_ROUND WARNING: ~35 min of wall time will not fit before the freeze" in out.stdout and "20 min left" in out.stdout, "warns: " + out.stdout)
    far = e.project("Mode: sprint\nFreeze-Epoch: %d\n" % (T0 + 6 * 3600))
    e.rnd(far, n=2, seed=5)
    e.measured(far, "R1", hist)
    ok = e.design(far, "round", "--n", "6", "--seed", "4", ok=(3,))
    expect("WARNING" not in ok.stdout, "plenty of time, no warning: " + ok.stdout)
    marathon = e.project("Mode: marathon\nFreeze-Epoch: %d\n" % freeze_soon)
    e.rnd(marathon, n=2, seed=5)
    e.measured(marathon, "R1", hist)
    quiet = e.design(marathon, "round", "--n", "6", "--seed", "4", ok=(3,))
    expect("WARNING" not in quiet.stdout, "only sprint has a deadline to warn about: " + quiet.stdout)
    import design_metrics as dm
    w = dm.deadline_warning(sprint, 35, now_epoch=T0)
    expect(w and "35 min" in w and "20 min left" in w, "the function: %s" % w)
    expect(dm.deadline_warning(sprint, 35, now_epoch=freeze_soon + 60).startswith("WARNING: the freeze"), "after the freeze")
    expect(dm.deadline_warning(sprint, None) is None, "no minutes measured, no warning")
    return "warns in sprint only, when it will not fit"


def pick_page_shows_tokens_and_minutes(e):
    d = e.project()
    e.rnd(d, n=3)
    e.measured(d, "R1", {"v1": ("SVG/CSS animation", 61000, 150), "v2": ("three.js scene", 140000, 3240), "v3": ("still (no animation)", None, 90)})
    (d / ".uak/design/rounds/R1/picks.json").write_text(json.dumps({"picked": ["v1"], "notes": {}}), encoding="utf-8")
    for v in ("v1", "v2", "v3"):
        (d / ".uak/design/rounds/R1" / v / "1280.png").write_bytes(b"x")
    out = subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--no-open"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=90)
    m = re.search(r"http://127\.0\.0\.1:(\d+)/", out.stdout)
    expect(out.returncode == 0 and m, "start: " + out.stdout + out.stderr)
    try:
        with urllib.request.urlopen("http://127.0.0.1:%s/pick.html" % m.group(1), timeout=10) as r:
            page = r.read().decode("utf-8")
    finally:
        subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--stop"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=60)
    card = lambda v: page.split('data-id="%s"' % v)[1].split("</article>")[0]
    expect("tokens 61k" in card("v1") and "2.5 min" in card("v1") and "2 look-and-fix passes" in card("v1"), "v1: " + card("v1")[-500:])
    expect("tokens 140k" in card("v2") and "54.0 min" in card("v2"), "v2")
    expect("tokens not reported" in card("v3"), "an unreported variant says so, not 0")
    expect("Round cost: 201k tokens (2 of 3 variants reported)" in page and "54.0 min wall in parallel" in page and "201k per picked variant" in page, "header totals: " + re.sub(r"\s+", " ", page.split("Round cost")[1][:250]) if "Round cost" in page else "no header totals")
    return "tokens and minutes under each variant, totals in the header"


TESTS = [variant_metrics_written, tokens_null_with_reason_when_unknown, report_totals_and_parallel_wall, estimate_uses_measured_median_by_stage,
         deadline_warning_in_sprint, pick_page_shows_tokens_and_minutes]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-metrics-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_METRICS_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
