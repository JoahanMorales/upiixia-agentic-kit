#!/usr/bin/env python3
"""The per-human taste profile: what a person likes in design, as traits, never as templates.

    python3 design_taste.py update [--human NAME]      fold every round of this project into the profile
    python3 design_taste.py show [--human NAME]        the values per gene, most to least liked, and past directions
    python3 design_taste.py forget PROJECT [--human NAME]
    python3 design_taste.py team                       fold this project's rounds into .uak/design/taste.json (shared in the repo)
    python3 design_taste.py merge A B                  fold profile B into profile A (the same person under two names)

The profile lives in ~/.uak/taste/<human>.json (UAK_TASTE_HOME overrides the folder). Per round (keyed
"<project>:R<k>") it keeps, for each gene value, how often it was shown, picked first, picked, and the human's notes;
a re-fold replaces that round's entry, so folding twice changes nothing and `forget` drops a project cleanly. The
totals are summed on read. weights() gives each value (picked + 1) / (shown + 2), Laplace-smoothed. Only rounds with a
picks.json count (a round nobody judged teaches nothing). Past directions (the final genome of each project) are kept
only so a new project can avoid copying them (UAK-063); no hex value or page is ever stored (hex in notes is dropped).
Under MIN_PICKS picks the profile says `confidence: low` and rounds keep exploring.
A team shares one profile through the repo: .uak/design/taste.json, same schema, committed with the rest of .uak/design.
effective(root, human) picks the profile a first round draws from: team, else personal, else the kit's prior (UAK-075 passes
it in), each only when it has confidence ok. One person has one profile: names that differ in case or accents map to the
same file, and aliases (.uak/design/aliases, then <taste home>/aliases; "alias = name" or "name: alias1, alias2") map the rest.
Why (2026-11-12): the same human ended with "joahan" (the pick page) and "JoahanMorales" (the CLI), and a profile that
never left one machine.
Why (v6.2, the human): once a genome wins, every project must not come out the same; the kit learns what the human
likes, not what one page looked like. Python 3.8+ standard library only."""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design_breed import _read, converged, first_pick  # noqa: E402
from design_round import GENES, ground_of, project_root  # noqa: E402

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


def norm(name):
    """A name's identity: lower case, no accents, letters and digits only ("José Pérez" is "joseperez")."""
    d = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in d if c.isalnum() and not unicodedata.combining(c)).lower()


def _alias_files():
    out = [taste_home() / "aliases"]
    try:
        out.append(project_root() / ".uak" / "design" / "aliases")  # the project's wins: read last
    except Exception:  # noqa: BLE001
        pass
    return out


def aliases():
    """{norm(alias): canonical name} from the alias files. Lines: `alias = name`, or `name: alias1, alias2`; # comments."""
    out = {}
    for f in _alias_files():
        try:
            lines = f.read_text(encoding="utf-8").replace("\r", "").split("\n")
        except OSError:
            continue
        for line in lines:
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                a, c = (x.strip() for x in line.split("=", 1))
                pairs = [(a, c)]
            elif ":" in line:
                c, rest = (x.strip() for x in line.split(":", 1))
                pairs = [(a.strip(), c) for a in rest.split(",")]
            else:
                continue
            for a, c in pairs:
                if a and c:
                    out[norm(a)] = c
    return out


def _stems():
    home = taste_home()
    try:
        return sorted(p.stem for p in home.glob("*.json") if ".metrics" not in p.name)
    except OSError:
        return []


def profile_names():
    """Names of the profiles that exist on this machine (the pick page suggests them)."""
    return _stems()


def canonical(name):
    """The profile name a typed name maps to: an alias, else an existing profile that differs only in case or accents,
    else the name as typed."""
    name = (name or "").strip() or "human"
    amap = aliases()
    for _ in range(5):
        hit = amap.get(norm(name))
        if not hit or hit == name:
            break
        name = hit
    n = norm(name)
    for stem in _stems():
        if norm(stem) == n:
            return stem
    return name


def profile_path(human):
    safe = re.sub(r"[^\w.-]+", "-", canonical(human), flags=re.UNICODE).strip("-.") or "human"  # accents stay: José is not Jos
    return taste_home() / (safe + ".json")


def team_path(root):
    return Path(root) / ".uak" / "design" / "taste.json"


def _load_path(path, human):
    doc = _read(path)
    if not isinstance(doc, dict):
        doc = {}
    doc.setdefault("human", human)
    doc.setdefault("rounds", {})
    doc.setdefault("directions", {})
    return doc


def load(human):
    return _load_path(profile_path(human), human)


def load_team(root):
    return _load_path(team_path(root), "team")


def _save_to(p, doc):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(str(tmp), "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    os.replace(str(tmp), str(p))


def save(human, doc):
    _save_to(profile_path(human), doc)


def effective(root, human, prior=None):
    """(doc, source) a first round draws from: the team profile, else the personal one, else the prior; each only when its
    confidence is ok. When none is, the one with the most picks (still low: rounds keep exploring), source "none" if empty."""
    team, mine = load_team(root), load(human)
    for src, doc in (("team", team), ("personal", mine), ("prior", prior)):
        if isinstance(doc, dict) and doc and confidence(doc) == "ok":
            return doc, src
    best = max((team, mine), key=pick_count)
    return best, ("none" if not pick_count(best) else "team" if best is team else "personal")


def merge(a, b):
    """Fold profile b into profile a (one person, two names): rounds by key (more picks wins), directions by project (later
    date wins). b's file is kept as <b>.json.merged-into-<a>.bak and an alias b = a is written, so b maps to a from now on."""
    pa, pb = profile_path(a), profile_path(b)
    if pa == pb:
        return None
    if not pb.is_file():
        raise ValueError("no profile named %s (looked in %s)" % (b, pb))
    da, db = load(a), load(b)
    for k, r in db["rounds"].items():
        if k not in da["rounds"] or r.get("picks", 0) > da["rounds"][k].get("picks", 0):
            da["rounds"][k] = r
    for k, d in db["directions"].items():
        if k not in da["directions"] or d.get("date", "") >= da["directions"][k].get("date", ""):
            da["directions"][k] = d
    _save_to(pa, da)
    mb, ma = pb.with_name(pb.stem + ".metrics.json"), pa.with_name(pa.stem + ".metrics.json")
    if mb.is_file():
        merged = dict(_read(mb) or {}, **(_read(ma) or {}))
        _save_to(ma, merged)
        os.replace(str(mb), str(mb) + ".merged-into-" + pa.stem + ".bak")
    os.replace(str(pb), str(pb) + ".merged-into-" + pa.stem + ".bak")
    with open(str(taste_home() / "aliases"), "a", encoding="utf-8", newline="\n") as f:
        f.write("%s = %s\n" % (pb.stem, pa.stem))
    return da


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
        # ground (light/dark, UAK-072) is a trait like a gene: the genome's own, else what its color implies (older rounds)
        traits = dict(g["genes"])
        ground = g.get("ground") or ground_of(g["genes"])
        if ground:
            traits["ground"] = ground
        for gene in list(GENES) + ["ground"]:
            val = traits.get(gene)
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
            d = {"round": rnd, "variant": vid, "genes": g["genes"]}
            try:  # the winning pair, so a new project's round 1 never reuses its faces (UAK-071)
                import design_fonts
                fonts = design_fonts.winning_fonts(base, rnd, vid)
                if fonts:
                    d["fonts"] = fonts
            except Exception:  # noqa: BLE001  fonts are a bonus; the direction stands without them
                pass
            return d
    return None


def update(root, human, project=None, now=None, team=False):
    """Fold every judged round of root into human's profile (team=True: the repo's .uak/design/taste.json). Returns it."""
    root = Path(root)
    project = project or root.name
    base = root / ".uak" / "design" / "rounds"
    doc = load_team(root) if team else load(human)
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
        same = old.get("genes") == d["genes"] and old.get("round") == d["round"] and old.get("variant") == d["variant"] and old.get("fonts") == d.get("fonts")
        d["date"] = old["date"] if same else (now or time.strftime("%Y-%m-%d", time.gmtime()))
        d["project"] = project
        doc["directions"][project] = d
    else:
        doc["directions"].pop(project, None)
    if team:
        _save_to(team_path(root), doc)
    else:
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


def show(human, doc=None):
    doc = doc if doc is not None else load(human)
    tot = totals(doc)
    w = weights(doc)
    lines = ["TASTE %s: %d picks in %d rounds, confidence: %s%s" % (
        human, pick_count(doc), len(doc["rounds"]), confidence(doc), " (still learning: rounds keep exploring)" if confidence(doc) == "low" else "")]
    for gene in list(GENES) + ["ground"]:
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
    if args[:1] == ["team"]:
        root = project_root()
        doc = update(root, human, team=True)
        print("TASTE team updated: %s (commit it with the rest of .uak/design)" % team_path(root))
        print(show("team", doc))
        return 0
    if args[:1] == ["merge"] and len(args) == 3:
        try:
            doc = merge(args[1], args[2])
        except ValueError as exc:
            print("TASTE merge: %s" % exc, file=sys.stderr)
            return 1
        if doc is None:
            print("TASTE merge: %s and %s are already the same profile" % (args[1], args[2]))
            return 0
        print("TASTE merged %s into %s: %d picks in %d rounds (%s kept as a .bak; %s now maps to %s)" % (
            args[2], args[1], pick_count(doc), len(doc["rounds"]), args[2], args[2], args[1]))
        return 0
    if args[:1] == ["forget"] and len(args) == 2:
        n, had = forget(human, args[1])
        print("TASTE forgot %s: %d rounds%s" % (args[1], n, " and its direction" if had else ""))
        return 0
    print("Usage: design_taste.py update|show|team|forget PROJECT|merge A B [--human NAME]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
