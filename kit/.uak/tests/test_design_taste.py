#!/usr/bin/env python3
"""UAK-062: design_taste.py folds a project's judged rounds into ~/.uak/taste/<human>.json as traits (weights per gene
value, never hex or a page), idempotently, keeps each project's final genome as a "past direction", and says
`confidence: low` under 10 picks."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect


class Env:
    def __init__(self, tmp, package):
        self.tmp = Path(tmp)
        self.lib = Path(package) / ".uak" / "bin" / "lib"  # the candidate under test (smoke passes --package)
        sys.path.insert(0, str(self.lib))
        os.environ["UAK_TASTE_HOME"] = str(self.tmp / "taste")
        import design_taste
        self.dt = design_taste

    def project(self, name, picked=("v1", "v2"), notes=None, n=8, seed=3, rounds=1):
        d = self.tmp / name
        (d / ".uak").mkdir(parents=True)
        r = subprocess.run([sys.executable, str(self.lib / "design_round.py"), "round", "--n", str(n), "--seed", str(seed), "--yes"],
                           cwd=str(d), capture_output=True, text=True)
        expect(r.returncode == 0, "round: " + r.stdout + r.stderr)
        self.picks(d, "R1", list(picked), notes or {})
        return d

    def picks(self, d, rnd, picked, notes):
        (d / ".uak/design/rounds" / rnd / "picks.json").write_text(
            json.dumps({"picked": picked, "notes": notes, "by": "ana", "at": "2026-11-11T00:00:00Z"}), encoding="utf-8")

    def genome(self, d, rnd, v):
        return json.loads((d / ".uak/design/rounds" / rnd / v / "genome.json").read_text(encoding="utf-8"))


def folds_picks_into_weights(e):
    d = e.project("alfa", picked=["v2", "v1"], notes={"v2": "me gusto la tipografia", "v3": "no me gusto"})
    doc = e.dt.update(d, "ana")
    g2, g1 = e.genome(d, "R1", "v2")["genes"], e.genome(d, "R1", "v1")["genes"]
    tot = e.dt.totals(doc)
    c = tot["type"][g2["type"]]
    expect(c["first"] >= 1 and c["picked"] >= 1 and c["shown"] >= c["picked"], "counts: %r" % c)
    expect(any("tipografia" in n for n in tot["type"][g2["type"]]["notes"]), "note kept per gene value")
    w = e.dt.weights(doc)
    picked_val = g2["color"]
    never = [v for v, cc in tot["color"].items() if cc["picked"] == 0 and cc["shown"] > 0]
    expect(never, "some color value was shown and never picked")
    expect(w["color"][picked_val] > w["color"][never[0]], "a picked value weighs more than a never-picked one")
    expect(abs(w["color"][picked_val] - (tot["color"][picked_val]["picked"] + 1.0) / (tot["color"][picked_val]["shown"] + 2.0)) < 1e-9, "Laplace-smoothed")
    out = e.dt.show("ana")
    expect("type" in out and "confidence: low" in out and len(out.splitlines()) < 40, "show: " + out)
    return "weights follow picks"


def folding_twice_is_idempotent(e):
    d = e.project("beta")
    e.dt.update(d, "bea")
    p = e.dt.profile_path("bea")
    first = p.read_bytes()
    e.dt.update(d, "bea")
    expect(p.read_bytes() == first, "second fold changed the file")
    # a changed pick replaces the round, it does not add to it
    e.picks(d, "R1", ["v3"], {})
    doc = e.dt.update(d, "bea")
    expect(e.dt.pick_count(doc) == 1 and len(doc["rounds"]) == 1, "round replaced: %r" % doc["rounds"].keys())
    return "same round, same file"


def stores_traits_not_hex(e):
    d = e.project("gama", notes={"v1": "el azul #0367FC lastima", "v2": "bonita"})
    e.dt.update(d, "gus")
    text = e.dt.profile_path("gus").read_text(encoding="utf-8")
    expect("#0367" not in text and "0367FC" not in text, "hex in the profile")
    import re
    expect(not re.search(r"#[0-9a-fA-F]{3,8}\b", text), "no hex anywhere")
    expect("<html" not in text.lower() and "TASK" not in text, "no page content")
    return "no hex, no pages"


def past_directions_recorded(e):
    a = e.project("delta", picked=["v4", "v1"])
    b = e.project("eps", picked=["v2"], seed=5)
    e.dt.update(a, "dan")
    doc = e.dt.update(b, "dan")
    dirs = {x["project"]: x for x in e.dt.past_directions(doc)}
    expect(set(dirs) == {"delta", "eps"}, "two directions: %r" % list(dirs))
    expect(dirs["delta"]["genes"] == e.genome(a, "R1", "v4")["genes"] and dirs["delta"]["variant"] == "v4", "delta's final is its first pick")
    expect(dirs["eps"]["date"] and dirs["eps"]["round"] == "R1", "date and round kept")
    expect("delta" in e.dt.show("dan") and "past directions" in e.dt.show("dan"), "show lists them")
    return "directions kept per project"


def low_confidence_under_ten_picks(e):
    d = e.project("zeta", picked=["v1", "v2", "v3", "v4", "v5"])
    doc = e.dt.update(d, "lia")
    expect(e.dt.confidence(doc) == "low" and "confidence: low" in e.dt.show("lia"), "5 picks is low")
    e.picks(d, "R1", ["v%d" % i for i in range(1, 9)], {})
    e2 = e.project("eta", picked=["v1", "v2", "v3"], seed=9)
    e.dt.update(d, "lia")
    doc = e.dt.update(e2, "lia")
    expect(e.dt.pick_count(doc) == 11 and e.dt.confidence(doc) == "ok", "11 picks is ok: %d" % e.dt.pick_count(doc))
    expect("confidence: low" not in e.dt.show("lia"), "no longer learning")
    return "low under 10 picks"


TESTS = [folds_picks_into_weights, folding_twice_is_idempotent, stores_traits_not_hex, past_directions_recorded, low_confidence_under_ten_picks]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-taste-") as tmp:
        e = Env(tmp, args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_TASTE_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
