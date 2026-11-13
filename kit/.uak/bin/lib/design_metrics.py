#!/usr/bin/env python3
"""Every design variant measures what it cost: tokens and minutes, so the next round's estimate is a measurement.

    python3 design_metrics.py done R<k> v<i> --tokens N     the builder reports its usage (run from the project root)
    python3 design_metrics.py report R<k> [--all]           one row per variant and the round's totals

Per variant, v<i>/metrics.json: started (TASK.md written), first_page (index.html created), done (last capture),
wall_seconds, passes (captures taken), load_start / load_end (1-minute load average, so a slow round on a busy machine
shows), and tokens {value, source, reason}. Tokens are only ever what the builder reported (`design done --tokens N`);
otherwise value is null with the reason. Never 0, never estimated: `uak tokens` reads session transcripts, which cannot
tell one variant's subagent from another's, so it is not guessed from there. Round-level metrics.json written by hand
from a harness (R<k>/metrics.json with variants {v1: {tokens, seconds}}) are read as a fallback.
History for the cost line: the measured tokens and minutes of this human's rounds (this project's, plus the store
<taste home>/<human>.metrics.json that every record and report refreshes), median by stage family (light: still, SVG,
canvas, video; three.js).
Why (AXIA R1-R3, Nov 11 2026): in a hackathon tokens and minutes decide whether a round fits; the fixed 60k per variant
was off by 2x on R3 (812k tokens, 54 min). UAK_METRICS_NOW (epoch seconds) fixes the clock for tests.
Python 3.8+ standard library only."""
import json
import math
import os
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_TOKENS = 60000
NO_TOKENS = "not reported: the builder runs `bash .uak/bin/uak design done %s %s --tokens N` with its usage; `uak tokens` cannot tell one variant's subagent from another's"


def now():
    try:
        return int(os.environ["UAK_METRICS_NOW"])
    except (KeyError, ValueError):
        return int(time.time())


def load_avg():
    try:
        return round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        return None  # Windows has no load average


def family(stage):
    return "three.js" if str(stage or "").lower().startswith("three.js") else "light"


def _read(p):
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _write(p, doc):
    p = Path(p)
    tmp = p.with_name(p.name + ".tmp")
    with open(str(tmp), "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(str(tmp), str(p))


def _family_of(vdir):
    g = _read(Path(vdir) / "genome.json") or {}
    # Rounds built by hand before the gene existed kept `stage` beside the genes (AXIA R3, colonIA R1).
    return family((g.get("genes") or {}).get("stage") or g.get("stage"))


def _born(p):
    st = os.stat(str(p))
    return int(getattr(st, "st_birthtime", st.st_mtime))  # creation time where the OS keeps it, else the last write


def load(vdir):
    """The variant's metrics, created on first use for rounds that did not start through `design round` (bred rounds)."""
    vdir = Path(vdir)
    doc = _read(vdir / "metrics.json")
    if doc is not None:
        return doc
    task = vdir / "TASK.md"
    started = _born(task) if task.is_file() else now()
    rnd = vdir.parent.name
    doc = {"variant": vdir.name, "family": _family_of(vdir), "started": started, "first_page": None, "done": None, "wall_seconds": None,
           "passes": 0, "load_start": None, "load_end": None, "tokens": {"value": None, "source": None, "reason": NO_TOKENS % (rnd, vdir.name)}}
    return doc


def start(vdir):
    """Called when TASK.md is written."""
    vdir = Path(vdir)
    doc = load(vdir)
    doc["started"], doc["load_start"] = now(), load_avg()
    _write(vdir / "metrics.json", doc)
    return doc


def record_capture(vdir):
    """Called after a successful capture: one more look-and-fix pass; done moves to now."""
    vdir = Path(vdir)
    doc = load(vdir)
    t = now()
    page = vdir / "index.html"
    if doc.get("first_page") is None and page.is_file():
        doc["first_page"] = max(doc["started"], min(_born(page), t))
    doc["passes"] = int(doc.get("passes") or 0) + 1
    doc["done"], doc["load_end"] = t, load_avg()
    doc["wall_seconds"] = max(0, t - doc["started"])
    _write(vdir / "metrics.json", doc)
    sync_store(vdir.parent.parent.parent.parent.parent)
    return doc


def record_tokens(vdir, n):
    vdir = Path(vdir)
    doc = load(vdir)
    doc["tokens"] = {"value": int(n), "source": "reported by the builder (design done --tokens)", "reason": None}
    if doc.get("done") is None:
        doc["done"] = now()
        doc["wall_seconds"] = max(0, doc["done"] - doc["started"])
        doc["load_end"] = load_avg()
    _write(vdir / "metrics.json", doc)
    sync_store(vdir.parent.parent.parent.parent.parent)
    return doc


def variant_view(rnd, name):
    """{tokens, source, reason, seconds, passes, family, errors} for one variant, from its metrics.json or, failing that,
    the round-level metrics.json a harness wrote by hand."""
    rnd = Path(rnd)
    vdir = rnd / name
    doc = _read(vdir / "metrics.json")
    qa = _read(vdir / "qa.json") or {}
    errors = sum(int(q.get("errors") or 0) for q in qa.values() if isinstance(q, dict)) if qa else None
    if doc:
        t = doc.get("tokens") or {}
        return {"tokens": t.get("value"), "source": t.get("source"), "reason": t.get("reason"), "seconds": doc.get("wall_seconds"),
                "passes": doc.get("passes") or 0, "family": doc.get("family") or _family_of(vdir), "errors": errors}
    hand = ((_read(rnd / "metrics.json") or {}).get("variants") or {}).get(name)
    if isinstance(hand, dict):
        return {"tokens": hand.get("tokens"), "source": "round metrics.json (harness)", "reason": None if hand.get("tokens") else "not in the round's metrics.json",
                "seconds": hand.get("seconds"), "passes": None, "family": _family_of(vdir), "errors": errors}
    return None


def variants_of(rnd):
    return sorted((p.name for p in Path(rnd).iterdir() if p.is_dir() and re.match(r"^v\d+$", p.name)), key=lambda s: int(s[1:])) if Path(rnd).is_dir() else []


def round_summary(rnd):
    """{rows, tokens (sum of the reported), reported, n, wall (longest variant), picked, per_picked}."""
    rnd = Path(rnd)
    rows = []
    for name in variants_of(rnd):
        view = variant_view(rnd, name)
        if view:
            rows.append(dict(view, name=name))
    known = [r["tokens"] for r in rows if r["tokens"]]
    secs = [r["seconds"] for r in rows if r["seconds"] is not None]
    picks = _read(rnd / "picks.json") or {}
    picked = [i for i in picks.get("picked", []) if isinstance(i, str)]
    total = sum(known)
    return {"rows": rows, "tokens": total if known else None, "reported": len(known), "n": len(variants_of(rnd)),
            "wall": max(secs) if secs else None, "picked": len(picked), "per_picked": int(total / len(picked)) if known and picked else None}


# ---- history (this human's measured rounds) ----

def store_path(human):
    import design_taste
    p = design_taste.profile_path(human)
    return p.with_name(p.stem + ".metrics.json")


def _human():
    import design_taste
    return design_taste.default_human()


def sync_store(root, human=None):
    """Refresh this project's entries in the human's metrics store; a store that cannot be written never fails a record."""
    try:
        human = human or _human()
        root = Path(root)
        base = root / ".uak" / "design" / "rounds"
        p = store_path(human)
        doc = _read(p) or {}
        entries = {k: v for k, v in doc.items() if not k.startswith(root.name + ":")}
        for e in project_entries(root):
            entries["%s:%s:%s" % (root.name, e["round"], e["variant"])] = e
        p.parent.mkdir(parents=True, exist_ok=True)
        _write(p, entries)
    except Exception:  # noqa: BLE001
        pass


def project_entries(root):
    base = Path(root) / ".uak" / "design" / "rounds"
    out = []
    for r in sorted((p for p in base.glob("R*") if re.match(r"^R\d+$", p.name)), key=lambda p: int(p.name[1:])) if base.is_dir() else []:
        for name in variants_of(r):
            v = variant_view(r, name)
            if v and (v["tokens"] or v["seconds"]):
                out.append({"round": r.name, "variant": name, "family": v["family"], "tokens": v["tokens"], "seconds": v["seconds"]})
    return out


def history(root, human):
    """All measured entries: this project's now, plus the human's store (other projects), de-duplicated by key."""
    seen = {}
    store = _read(store_path(human)) or {}
    for k, e in store.items():
        if isinstance(e, dict):
            seen[k] = e
    for e in project_entries(root):
        seen["%s:%s:%s" % (Path(root).name, e["round"], e["variant"])] = e
    return list(seen.values())


def medians(entries):
    """{family: {"tokens": median or None, "minutes": median or None, "n": count}} plus the number of rounds."""
    out = {}
    for fam in ("light", "three.js"):
        es = [e for e in entries if e.get("family") == fam]
        toks = [e["tokens"] for e in es if e.get("tokens")]
        mins = [e["seconds"] / 60.0 for e in es if e.get("seconds")]
        out[fam] = {"tokens": int(statistics.median(toks)) if toks else None, "minutes": round(statistics.median(mins), 1) if mins else None, "n": len(es)}
    return out


def fmt_tokens(t):
    return "%dk" % int(round(t / 1000.0)) if t >= 1000 else str(t)


def estimate(root, human, stages, default_tokens, parallel=None, now_epoch=None):
    """The cost line's numbers for a round whose variants have these stage values. Returns a dict:
    tokens, source (words), wall_minutes (or None), warning (or None)."""
    entries = history(root, human)
    med = medians(entries)
    fams = [family(s) for s in stages]
    counts = {f: fams.count(f) for f in ("light", "three.js") if fams.count(f)}
    usable = [e for e in entries if e.get("tokens")]
    if not usable:
        return {"tokens": default_tokens * len(stages), "source": None, "parts": [], "wall_minutes": None, "n": len(stages), "default": default_tokens}
    overall = int(statistics.median([e["tokens"] for e in usable]))
    parts, total = [], 0
    for f, c in counts.items():
        m = med[f]["tokens"] or overall
        parts.append("%d %s x %s%s" % (c, f, fmt_tokens(m), "" if med[f]["tokens"] else " (all families' median)"))
        total += c * m
    mins = [med[f]["minutes"] for f in counts if med[f]["minutes"]]
    p = max(1, min(parallel or len(stages), len(stages)))
    waves = int(math.ceil(len(stages) / float(p)))
    wall = waves * max(mins) if mins else None
    return {"tokens": total, "parts": parts, "wall_minutes": wall, "n": len(stages), "waves": waves, "parallel": p, "entries": len(usable)}


def deadline_warning(root, wall_minutes, now_epoch=None):
    """In sprint mode, a warning when the round (wall_minutes) ends after the Freeze-Epoch of PROJECT.md (uak clock --write)."""
    if wall_minutes is None:
        return None
    from design_round import cfg
    if cfg(Path(root), "Mode", "").lower() != "sprint":
        return None
    try:
        freeze = int(cfg(Path(root), "Freeze-Epoch", "0"))
    except ValueError:
        return None
    if freeze <= 0:
        return None
    t = now_epoch or now()
    left = (freeze - t) / 60.0
    at = time.strftime("%H:%M", time.localtime(freeze))
    if left <= 0:
        return "WARNING: the freeze (%s, uak clock) has passed; a round of ~%d min would land after it" % (at, math.ceil(wall_minutes))
    if wall_minutes > left:
        return "WARNING: ~%d min of wall time will not fit before the freeze at %s (%d min left, uak clock); fewer variants, or more in parallel" % (
            math.ceil(wall_minutes), at, int(left))
    return None


# ---- commands ----

def fmt_row(r):
    tok = fmt_tokens(r["tokens"]) if r["tokens"] else "n/a"
    mins = "%.1f" % (r["seconds"] / 60.0) if r["seconds"] is not None else "n/a"
    return "%-4s %-8s %-9s %-7s %-6s %s" % (r["name"], r["family"], tok, mins, r["passes"] if r["passes"] is not None else "n/a",
                                          r["errors"] if r["errors"] is not None else "n/a")


def report_round(rnd):
    s = round_summary(rnd)
    lines = ["%s: %d variants" % (Path(rnd).name, s["n"]), "%-4s %-8s %-9s %-7s %-6s %s" % ("", "stage", "tokens", "minutes", "passes", "page errors")]
    lines += [fmt_row(r) for r in s["rows"]]
    if s["tokens"] is None:
        lines.append("totals: tokens n/a (no variant reported; builders run `uak design done %s v<i> --tokens N`)" % Path(rnd).name)
    else:
        part = "" if s["reported"] == s["n"] else " (only %d of %d variants reported)" % (s["reported"], s["n"])
        lines.append("totals: %s tokens%s" % (fmt_tokens(s["tokens"]), part))
    lines.append("wall in parallel (longest variant): %s" % ("%.1f min" % (s["wall"] / 60.0) if s["wall"] is not None else "n/a"))
    lines.append("tokens per picked variant: %s" % ("%s (%d picked)" % (fmt_tokens(s["per_picked"]), s["picked"]) if s["per_picked"] else "n/a (%s)" % ("nothing picked yet" if not s["picked"] else "no tokens reported")))
    return lines


def cmd_report(argv, root):
    base = Path(root) / ".uak" / "design" / "rounds"
    allr = "--all" in argv
    names = [a for a in argv if re.match(r"^R\d+$", a)]
    if not allr and not names:
        print("Usage: design report R<k> [--all]", file=sys.stderr)
        return 2
    rounds = sorted((p for p in base.glob("R*") if re.match(r"^R\d+$", p.name)), key=lambda p: int(p.name[1:])) if base.is_dir() else []
    if not allr:
        rounds = [p for p in rounds if p.name in names]
        if not rounds:
            print("design report: no round %s in %s" % (names[0], base), file=sys.stderr)
            return 1
    toks, wall, reported, n = 0, 0, 0, 0
    for r in rounds:
        for line in report_round(r):
            print(line)
        s = round_summary(r)
        toks, reported, n = toks + (s["tokens"] or 0), reported + s["reported"], n + s["n"]
        wall += s["wall"] or 0
        print("")
    if allr:
        print("ALL %d rounds: %s tokens (%d of %d variants reported), wall %.1f min added up round by round" % (len(rounds), fmt_tokens(toks) if reported else "n/a", reported, n, wall / 60.0))
    sync_store(root)
    return 0


def cmd_done(argv, root):
    args = list(argv)
    try:
        i = args.index("--tokens")
        raw = args[i + 1]
        del args[i:i + 2]
        n = int(raw.replace(",", "").replace("_", ""))
        if n <= 0:
            raise ValueError(raw)
    except (ValueError, IndexError):
        print("Usage: design done R<k> v<i> --tokens N   (N is the usage you really spent, a positive number; unknown? do not run it)", file=sys.stderr)
        return 2
    if len(args) != 2 or not re.match(r"^R\d+$", args[0]) or not re.match(r"^v\d+$", args[1]):
        print("Usage: design done R<k> v<i> --tokens N", file=sys.stderr)
        return 2
    vdir = Path(root) / ".uak" / "design" / "rounds" / args[0] / args[1]
    if not vdir.is_dir():
        print("design done: no variant %s/%s in %s" % (args[0], args[1], vdir.parent), file=sys.stderr)
        return 1
    doc = record_tokens(vdir, n)
    print("DESIGN_DONE %s/%s: %s tokens recorded, %s min since TASK.md" % (args[0], args[1], fmt_tokens(n), "%.1f" % (doc["wall_seconds"] / 60.0)))
    return 0


def main(argv):
    from design_round import project_root
    root = project_root()
    if argv[:1] == ["done"]:
        return cmd_done(argv[1:], root)
    if argv[:1] == ["report"]:
        return cmd_report(argv[1:], root)
    print("Usage: design done R<k> v<i> --tokens N | design report R<k> [--all]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
