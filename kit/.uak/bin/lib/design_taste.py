#!/usr/bin/env python3
"""The per-human taste profile: what a person likes in design, as traits, never as templates.

    python3 design_taste.py update [--human NAME]      fold every round of this project into the profile
    python3 design_taste.py show [--human NAME]        the values per gene, most to least liked, and past directions
    python3 design_taste.py forget PROJECT [--human NAME]

The profile lives in ~/.uak/taste/<human>.json (UAK_TASTE_HOME overrides the folder). Per round (keyed
"<project>:R<k>") it keeps, for each gene value, how often it was shown, picked first, picked, and the human's notes;
a re-fold replaces that round's entry, so folding twice changes nothing and `forget` drops a project cleanly. The
totals are summed on read. weights() gives each value (picked + 1) / (shown + 2), Laplace-smoothed. Only rounds with a
picks.json count (a round nobody judged teaches nothing). Past directions (the final genome of each project) are kept
only so a new project can avoid copying them (UAK-063); no hex value or page is ever stored (hex in notes is dropped).
Under MIN_PICKS picks the profile says `confidence: low` and rounds keep exploring.
Why (v6.2, the human): once a genome wins, every project must not come out the same; the kit learns what the human
likes, not what one page looked like. Python 3.8+ standard library only."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design_breed import _read, converged, first_pick  # noqa: E402
from design_round import GENES, project_root  # noqa: E402

MIN_PICKS = 10
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def default_human():
    name = os.environ.get("UAK_HUMAN", "").strip()
    if not name:
        try:
            name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        except OSError:
            name = ""
    return name or "human"


def taste_home():
    return Path(os.environ.get("UAK_TASTE_HOME") or os.path.join(os.path.expanduser("~"), ".uak", "taste"))


def profile_path(human):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", human.strip()).strip("-.") or "human"
    return taste_home() / (safe + ".json")


def load(human):
    doc = _read(profile_path(human))
    if not isinstance(doc, dict):
        doc = {}
    doc.setdefault("human", human)
    doc.setdefault("rounds", {})
    doc.setdefault("directions", {})
    return doc


def save(human, doc):
    p = profile_path(human)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(str(tmp), "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(str(tmp), str(p))


def _fold_round(rdir):
    """Per-gene-value counts of one round with picks, or None when nobody judged it."""
    picks = _read(rdir / "picks.json")
    if not isinstance(picks, dict):
        return None
    picked = [i for i in picks.get("picked", []) if isinstance(i, str)]
    notes = picks.get("notes") if isinstance(picks.get("notes"), dict) else {}
    genes = {}
    shown = 0
    for vdir in sorted(rdir.glob("v*")):
        g = _read(vdir / "genome.json")
        if not isinstance(g, dict) or not isinstance(g.get("genes"), dict):
            continue
        shown += 1
        for gene in GENES:
            val = g["genes"].get(gene)
            if not isinstance(val, str):
                continue
            c = genes.setdefault(gene, {}).setdefault(val, {"shown": 0, "first": 0, "picked": 0, "notes": []})
            c["shown"] += 1
            if vdir.name in picked:
                c["picked"] += 1
                if vdir.name == picked[0]:
                    c["first"] += 1
            note = HEX.sub("", str(notes.get(vdir.name, ""))).strip()
            if note:
                c["notes"].append(note)
    return {"picks": len(picked), "shown": shown, "genes": genes}


def _direction(base, rounds):
    """The project's final direction: the converged line, else the first pick of the last judged round."""
    for rnd in reversed(rounds):
        vid = converged(base, rnd) or first_pick(base, rnd)
        g = _read(base / rnd / vid / "genome.json") if vid else None
        if isinstance(g, dict) and isinstance(g.get("genes"), dict):
            return {"round": rnd, "variant": vid, "genes": g["genes"]}
    return None


def update(root, human, project=None, now=None):
    """Fold every judged round of root into human's profile. Returns the profile."""
    root = Path(root)
    project = project or root.name
    base = root / ".uak" / "design" / "rounds"
    doc = load(human)
    judged = []
    names = sorted((p.name for p in base.glob("R*") if re.match(r"^R\d+$", p.name)), key=lambda s: int(s[1:])) if base.is_dir() else []
    for rnd in names:
        folded = _fold_round(base / rnd)
        if folded:
            doc["rounds"]["%s:%s" % (project, rnd)] = folded
            judged.append(rnd)
    for key in [k for k in doc["rounds"] if k.startswith(project + ":") and k.split(":", 1)[1] not in judged]:
        del doc["rounds"][key]  # a round that no longer exists or lost its picks
    d = _direction(base, judged) if judged else None
    if d:
        old = doc["directions"].get(project, {})
        same = old.get("genes") == d["genes"] and old.get("round") == d["round"] and old.get("variant") == d["variant"]
        d["date"] = old["date"] if same else (now or time.strftime("%Y-%m-%d", time.gmtime()))
        d["project"] = project
        doc["directions"][project] = d
    else:
        doc["directions"].pop(project, None)
    save(human, doc)
    return doc


def forget(human, project):
    doc = load(human)
    n = len([k for k in doc["rounds"] if k.startswith(project + ":")])
    doc["rounds"] = {k: v for k, v in doc["rounds"].items() if not k.startswith(project + ":")}
    had = doc["directions"].pop(project, None) is not None
    save(human, doc)
    return n, had


def totals(doc):
    out = {}
    for r in doc.get("rounds", {}).values():
        for gene, vals in r.get("genes", {}).items():
            for val, c in vals.items():
                t = out.setdefault(gene, {}).setdefault(val, {"shown": 0, "first": 0, "picked": 0, "notes": []})
                for k in ("shown", "first", "picked"):
                    t[k] += c.get(k, 0)
                t["notes"].extend(c.get("notes", []))
    return out


def pick_count(doc):
    return sum(r.get("picks", 0) for r in doc.get("rounds", {}).values())


def confidence(doc):
    return "low" if pick_count(doc) < MIN_PICKS else "ok"


def weights(doc):
    """{gene: {value: (picked + 1) / (shown + 2)}} for the values seen; unseen values are not listed."""
    return {g: {v: (c["picked"] + 1.0) / (c["shown"] + 2.0) for v, c in vals.items()} for g, vals in totals(doc).items()}


def past_directions(doc):
    return list(doc.get("directions", {}).values())


def show(human):
    doc = load(human)
    tot = totals(doc)
    w = weights(doc)
    lines = ["TASTE %s: %d picks in %d rounds, confidence: %s%s" % (
        human, pick_count(doc), len(doc["rounds"]), confidence(doc), " (still learning: rounds keep exploring)" if confidence(doc) == "low" else "")]
    for gene in GENES:
        vals = tot.get(gene)
        if not vals:
            continue
        order = sorted(vals, key=lambda v: (-w[gene][v], v))
        lines.append("%-10s %s" % (gene, "; ".join("%s %.2f (%d/%d, first %d)" % (v, w[gene][v], vals[v]["picked"], vals[v]["shown"], vals[v]["first"]) for v in order)))
    dirs = past_directions(doc)
    if dirs:
        lines.append("past directions:")
        for d in sorted(dirs, key=lambda d: d.get("date", "")):
            lines.append("- %s (%s %s/%s): %s" % (d["project"], d.get("date", "?"), d["round"], d["variant"], ", ".join(str(d["genes"].get(g)) for g in GENES)))
    return "\n".join(lines[:40])


def main(argv):
    args = list(argv)
    human = None
    if "--human" in args:
        i = args.index("--human")
        human = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    human = human or default_human()
    if args[:1] == ["update"]:
        doc = update(project_root(), human)
        print("TASTE updated: %s now has %d picks in %d rounds (confidence: %s)" % (human, pick_count(doc), len(doc["rounds"]), confidence(doc)))
        return 0
    if args[:1] == ["show"]:
        print(show(human))
        return 0
    if args[:1] == ["forget"] and len(args) == 2:
        n, had = forget(human, args[1])
        print("TASTE forgot %s: %d rounds%s" % (args[1], n, " and its direction" if had else ""))
        return 0
    print("Usage: design_taste.py update|show|forget PROJECT [--human NAME]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
