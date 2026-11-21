#!/usr/bin/env python3
"""uak metrics: every speed number next to its instability number, from the claims branch (read-only).

    bash .uak/bin/uak metrics [--since DAYS] [--task ID] [--json] [--claims DIR]

Reads claims only: the ledger files metrics/<day>-<machine>.tsv (UAK-116), tasks, worklog histories, queue, DECISIONS,
the backlog, the black box. One fetch (dash.snapshot, the reader `uak dash` uses), then passes over local files.
--claims DIR reads an extracted claims checkout instead of fetching (tests, autopsies).
Why (audit of v6.5.0, section 4; the human, 2026-11-20: "que todo sea medible y cuantificable para poder mejorar el kit"):
`stats` counts events but pairs no speed with its cost and has no per-command error rate or duration.
Python 3.8+ standard library only. Every count is "N of M"; a percentage appears only when M >= 20.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dash  # noqa: E402  (the shared claims reader: git helpers, fields, rows, snapshot)

MIN_PCT = 20          # fewer events than this: counts only, never a bare percentage
TASK_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")


def day_of(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d")


def ratio(n, d):
    """'7 of 89', plus ' (8%)' only when the denominator reaches MIN_PCT."""
    s = "%d of %d" % (n, d)
    if d >= MIN_PCT:
        s += " (%d%%)" % round(100.0 * n / d)
    return s


def count(n, d):
    return {"n": n, "of": d}


def median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0


def p95(xs):
    xs = sorted(xs)
    if len(xs) < MIN_PCT:
        return None   # a 95th percentile of fewer than 20 samples is the maximum in disguise
    return xs[min(len(xs) - 1, int(0.95 * len(xs) + 0.999999) - 1)]


def lines_of(path):
    return dash.read(path).replace("\r", "").split("\n")


def history(wl_text):
    """'- epoch | STATE | actor | text | Harness: h | Model: m' → dicts, in time order."""
    out = []
    started = False
    for line in wl_text.replace("\r", "").split("\n"):
        if line.startswith("## History"):
            started = True
            continue
        if not started or not line.startswith("- "):
            continue
        p = line[2:].split(" | ")
        if len(p) < 4 or not p[0].strip().isdigit():
            continue
        text = p[3]
        harness = model = "unknown"
        for extra in p[4:]:
            if extra.startswith("Harness: "):
                harness = extra[9:].strip()
            elif extra.startswith("Model: "):
                model = extra[7:].strip()
        out.append({"epoch": int(p[0]), "state": p[1].strip(), "actor": p[2].strip(), "text": text.strip(),
                    "harness": harness, "model": model})
    out.sort(key=lambda e: e["epoch"])
    return out


def verdict_of(ev):
    m = re.match(r"review; (approve|reject)(?:; SHA ([0-9a-f]+))?(?:; reviewer (\S+))?", ev["text"])
    if ev["state"] == "REVIEW" and m:
        return {"epoch": ev["epoch"], "verdict": m.group(1), "sha": (m.group(2) or "")[:7],
                "reviewer": m.group(3) or ev["actor"], "model": ev["model"]}
    return None


def load(claims):
    """Everything the report needs, as plain structures. Nothing here touches the network."""
    c = Path(claims)
    tasks = {}
    for f in sorted((c / "tasks").glob("*.md")):
        fl = dash.fields(dash.read(f).replace("\r", ""))
        tid = fl.get("ID") or f.stem
        if not TASK_RE.match(tid):
            continue
        tasks[tid] = {"id": tid, "f": fl, "hist": []}
    wl_dir = c / "worklog"
    if wl_dir.is_dir():
        for f in sorted(wl_dir.glob("*.md")):
            text = dash.read(f)
            first = text.replace("\r", "").split("\n", 1)[0]
            m = re.search(r"[·]\s*([A-Z][A-Z0-9]*-\d+)\s*$", first)
            tid = m.group(1) if m else None
            if tid in tasks:
                tasks[tid]["hist"] += history(text)
    for t in tasks.values():
        t["hist"].sort(key=lambda e: e["epoch"])
    # The ledger: rows, and the "#sum" rows that stand for lines older than the per-file cap (counted, undated, no ms).
    ledger, sums = [], []
    for f in sorted((c / "metrics").glob("*.tsv")) if (c / "metrics").is_dir() else []:
        for line in lines_of(f):
            p = line.split("\t")
            if p[0] == "#sum" and len(p) >= 4:
                sums.append((p[1], p[2], dash.num(p[3])))
            elif len(p) >= 8 and not p[0].startswith("#"):
                ledger.append({"epoch": dash.num(p[0], None) if p[0].isdigit() else None, "cmd": p[1], "task": p[2],
                               "rc": p[3], "code": p[4], "ms": int(p[5]) if p[5].isdigit() else None,
                               "agent": p[6], "harness": p[7]})
    humans = set()   # identities with `Role: human` in meta/agents: a human recording under their own name
    for f in sorted((c / "meta" / "agents").glob("*.md")) if (c / "meta" / "agents").is_dir() else []:
        if dash.fields(dash.read(f).replace("\r", "")).get("Role") == "human":
            humans.add(f.stem)
    queue = []
    for f in sorted((c / "queue").glob("*.md")) if (c / "queue").is_dir() else []:
        fl = dash.fields(dash.read(f).replace("\r", ""))
        if fl.get("Reason"):
            queue.append({"task": fl.get("Task") or fl.get("ID") or f.stem, "reason": fl["Reason"],
                          "updated": dash.num(fl.get("Updated"))})
    allows = []
    for line in lines_of(c / "DECISIONS.md"):
        p = line[2:].split(" | ") if line.startswith("- ") else []
        if len(p) >= 4 and p[1] == "allow":
            allows.append({"epoch": dash.num(p[0]), "kind": "tests" if p[3].startswith("test change") else "freeze"})
    followups = {}
    cur = None
    for line in lines_of(c / "backlog" / "TASKS.md"):
        m = re.match(r"^## ([A-Z][A-Z0-9]*-\d+)", line)
        if m:
            cur = m.group(1)
        m = re.match(r"^- \*\*Follow-up of:\*\*\s*([A-Z][A-Z0-9]*-\d+)", line)
        if m and cur:
            followups[cur] = m.group(1)
    manual = []   # black box lines of kind "manual" (UAK-121): "- time | kit | harness | mode | source | kind | ..."
    bb = c / "blackbox"
    for f in sorted(bb.glob("*.md")) if bb.is_dir() else []:
        for line in lines_of(f):
            p = line[2:].split(" | ") if line.startswith("- ") else []
            if len(p) >= 6 and p[5].strip() == "manual":
                manual.append({"day": f.name[:10], "text": p[7].strip() if len(p) > 7 else ""})
    return {"tasks": tasks, "ledger": ledger, "sums": sums, "queue": queue, "allows": allows, "followups": followups,
            "manual": manual, "humans": humans}


def integrated_event(t):
    ev = [e for e in t["hist"] if e["state"] == "INTEGRATED"]
    return ev[-1] if ev else None


def first_claim(t):
    ev = [e for e in t["hist"] if e["state"] == "CLAIMED"]
    return ev[0] if ev else None


def base_ref(root, claims_given):
    """The base branch ref to count direct commits on: the one dash.snapshot just fetched, else origin/main, else main."""
    if not root:
        return None
    base = os.environ.get("UAK_BASE", "main")
    remote = os.environ.get("UAK_REMOTE", "origin")
    cands = [] if claims_given else ["refs/uak/dash-base"]
    cands += ["refs/remotes/%s/%s" % (remote, base), "refs/heads/%s" % base]
    for ref in cands:
        if dash.run_git("rev-parse", "-q", "--verify", ref, cwd=root).returncode == 0:
            return ref
    return None


def base_subjects(root, ref):
    """{commit sha: subject} of the base's history, one git call; None when the base is not visible."""
    if not ref:
        return None
    out = dash.run_git("log", "--format=%H|%s", ref, cwd=root)
    if out.returncode != 0:
        return None
    return dict(l.split("|", 1) for l in out.stdout.decode("utf-8", "replace").splitlines() if "|" in l)


def merge_kind(t, subjects):
    """How the task's code reached the base, from the base's subjects: engine = the gate's own merge commit of THIS task
    ("Merge UAK-N reviewed by ..."); forge = the task's PR number in a "Merge pull request #N" or squash "(#N)" subject;
    other = none found. (The Merge-Commit field is not trusted: for some tasks it names another task's merge.)"""
    tid = t["id"]
    pr = re.search(r"/pull/(\d+)", t["f"].get("PR", ""))
    forge = False
    for sub in subjects.values():
        if sub.startswith("Merge %s reviewed by " % tid):
            return "engine"
        if pr and (sub.startswith("Merge pull request #%s " % pr.group(1)) or sub.endswith("(#%s)" % pr.group(1))):
            forge = True
    return "forge" if forge else "other"


def direct_commits(root, ref):
    """(direct, all) first-parent commits on the base: a merge, the root, or a squash-merged task PR is not direct."""
    if not ref:
        return None
    out = dash.run_git("log", "--first-parent", "--format=%P|%s", ref, cwd=root)
    if out.returncode != 0:
        return None
    total = direct = 0
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        parents, _, subject = line.partition("|")
        total += 1
        if len(parents.split()) == 1 and not re.match(r"^[A-Z][A-Z0-9]*-\d{3,}", subject) \
                and not re.search(r"\(#\d+\)$", subject):
            direct += 1
    return (direct, total) if total else None


def build(data, since_days, now, git_root, claims_given):
    cutoff = now - since_days * 86400 if since_days else None
    inwin = (lambda e: True) if cutoff is None else (lambda e: e is not None and e >= cutoff)
    tasks = data["tasks"]
    # The tasks in the window: any task whose last move is inside it.
    win = {tid: t for tid, t in tasks.items()
           if inwin(t["hist"][-1]["epoch"] if t["hist"] else dash.num(t["f"].get("Updated")))}
    done = {tid: t for tid, t in win.items() if integrated_event(t)}
    # 1. Throughput next to instability, per day of integration.
    days = {}
    for tid, t in done.items():
        d = days.setdefault(day_of(integrated_event(t)["epoch"]),
                            {"day": None, "integrated": 0, "reopened": 0, "followed_up": 0, "unreviewed": 0})
        d["integrated"] += 1
        ie = integrated_event(t)
        if any(e["state"] == "CLAIMED" and e["epoch"] > ie["epoch"] for e in t["hist"]):
            d["reopened"] += 1
        d["followed_up"] += sum(1 for child, parent in data["followups"].items() if parent == tid)
        if t["f"].get("Unreviewed") == "yes":
            d["unreviewed"] += 1
    day_rows = []
    for k in sorted(days):
        days[k]["day"] = k
        day_rows.append(days[k])
    tot = {k: sum(d[k] for d in day_rows) for k in ("integrated", "reopened", "followed_up", "unreviewed")}
    # 2. Claim to INTEGRATED, rejected share, review rounds.
    hours = []
    for t in done.values():
        c1, i1 = first_claim(t), integrated_event(t)
        if c1 and i1 and i1["epoch"] >= c1["epoch"]:
            hours.append((i1["epoch"] - c1["epoch"]) / 3600.0)
    rounds = {tid: [v for v in (verdict_of(e) for e in t["hist"]) if v] for tid, t in win.items()}
    reviewed = {tid: r for tid, r in rounds.items() if r}
    # Rework with no reject: after an approve the owner pushed a new tip and recorded `done` again (a lead sent it back).
    reworked = 0
    for tid in reviewed:
        seen = False
        for e in win[tid]["hist"]:
            v = verdict_of(e)
            if v and v["verdict"] == "approve":
                seen = True
            elif seen and e["state"] == "REVIEW" and e["text"].startswith("done"):
                reworked += 1
                break
    rejected = sum(1 for r in reviewed.values() if any(v["verdict"] == "reject" for v in r))
    n_rounds = sum(len(r) for r in reviewed.values())
    dist = {}
    for r in reviewed.values():
        k = str(len(r)) if len(r) < 3 else "3+"
        dist[k] = dist.get(k, 0) + 1
    # 3. Per command, from the ledger (+ the "#sum" counts when the window is the whole history).
    per = {}
    for r in data["ledger"]:
        if cutoff is not None and not inwin(r["epoch"]):
            continue
        c = per.setdefault(r["cmd"], {"calls": 0, "known": 0, "errors": 0, "ms": []})
        c["calls"] += 1
        if r["rc"].isdigit():
            c["known"] += 1
            c["errors"] += r["rc"] != "0"
        if r["ms"] is not None:
            c["ms"].append(r["ms"])
    if cutoff is None:
        for cmd, outcome, n in data["sums"]:
            c = per.setdefault(cmd, {"calls": 0, "known": 0, "errors": 0, "ms": []})
            c["calls"] += n
            c["known"] += n
            c["errors"] += n if outcome == "fail" else 0
    cmds = [{"command": k, "calls": v["calls"], "errors": count(v["errors"], v["known"]), "timed": len(v["ms"]),
             "median_ms": median(v["ms"]), "p95_ms": p95(v["ms"])} for k, v in per.items()]
    cmds.sort(key=lambda x: (-x["calls"], x["command"]))
    # 4. Human interventions.
    reasons = {}
    queue_in = [q for q in data["queue"] if inwin(q["updated"])]
    for q in queue_in:
        if True:
            reasons[q["reason"].split(": ")[0]] = reasons.get(q["reason"].split(": ")[0], 0) + 1
    gate_wait = reasons.pop("Waiting for queue", 0)
    allows = [a for a in data["allows"] if inwin(a["epoch"])]
    # How each task reached INTEGRATED. With the base's history: the task's Merge-Commit on the base, by its subject (the
    # gate's "Merge UAK-N reviewed by", a forge "Merge pull request #N" or squash "(#N)", or neither / not found). Without
    # it (--claims runs, no base): the text of the INTEGRATED event, `merge` (the gate) vs `integrate` (recorded after).
    subjects = base_subjects(git_root, base_ref(git_root, claims_given))
    paths = {"gate_pushed": 0, "gate_built_human_landed": 0, "forge": 0, "recorded_unclassified": 0}
    rec = []
    for t in done.values():
        ev = integrated_event(t)
        if ev["text"].startswith("merge"):
            paths["gate_pushed"] += 1
            continue
        if not ev["text"].startswith("integrate"):
            continue
        rec.append(t)
        kind = merge_kind(t, subjects) if subjects is not None else "unknown"
        paths[{"engine": "gate_built_human_landed", "forge": "forge"}.get(kind, "recorded_unclassified")] += 1
    rec_human = sum(1 for t in rec if integrated_event(t)["actor"] in data["humans"])
    rec_unrev = sum(1 for t in rec if t["f"].get("Unreviewed") == "yes")
    # 5. Work outside the kit.
    outside = sum(1 for t in done.values() if t["f"].get("Integrated-Outside") == "yes")
    direct = direct_commits(git_root, base_ref(git_root, claims_given)) if cutoff is None else None
    classified = subjects is not None
    manual = [m for m in data["manual"] if cutoff is None or m["day"] >= day_of(cutoff)]
    return {
        "since_days": since_days or None,
        "tasks": count(len(win), len(tasks)),
        "throughput": {"days": day_rows, "integrated": count(tot["integrated"], len(win)),
                       "reopened": count(tot["reopened"], tot["integrated"]),
                       "followed_up": count(tot["followed_up"], tot["integrated"]),
                       "unreviewed": count(tot["unreviewed"], tot["integrated"])},
        "flow": {"claim_to_integrated_hours": {"n": len(hours), "median": median(hours), "p95": p95(hours)},
                 "rejected_tasks": count(rejected, len(reviewed)),
                 "new_tip_after_approval": count(reworked, len(reviewed)),
                 "review_rounds": {"rounds": n_rounds, "rejects": sum(1 for r in reviewed.values() for v in r if v["verdict"] == "reject"), "tasks": len(reviewed),
                                   "per_task": round(n_rounds / float(len(reviewed)), 2) if reviewed else None,
                                   "distribution": dist}},
        "commands": cmds,
        "human": {"queue_reasons": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
                  "queue_total": sum(reasons.values()), "waiting_for_gate": gate_wait,
                  "allow": {"freeze": sum(1 for a in allows if a["kind"] == "freeze"),
                            "tests": sum(1 for a in allows if a["kind"] == "tests")},
                  "queue_tasks": count(sum(reasons.values()), len(queue_in))},
        "merge_paths": {"basis": "base history" if classified else "event text",
                        "gate_pushed": count(paths["gate_pushed"], len(done)),
                        "gate_built_human_landed": count(paths["gate_built_human_landed"], len(done)),
                        "forge": count(paths["forge"], len(done)),
                        "recorded_unclassified": count(paths["recorded_unclassified"], len(done)),
                        "recorded_with_integrate": count(len(rec), len(done)),
                        "recorded_with_agent_identity": count(len(rec) - rec_human, len(rec)),
                        "recorded_by_human": count(rec_human, len(rec)),
                        "recorded_unreviewed": count(rec_unrev, len(rec))},
        "outside": {"direct_to_main": count(*direct) if direct else None,
                    "integrated_outside_field": count(outside, len(done)),
                    "manual_notes": {"recorded": bool(manual), "count": len(manual)}},
    }


def hhmm(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return "%ds" % seconds
    if seconds < 3600:
        return "%dm" % (seconds // 60)
    return "%.1fh" % (seconds / 3600.0)


def fmt_ms(v):
    return "-" if v is None else ("%d ms" % v if v < 10000 else "%.1f s" % (v / 1000.0))


def render(m):
    o = []
    w = " (last %d days)" % m["since_days"] if m["since_days"] else ""
    o.append("UAK METRICS%s · %d of %d tasks in the window" % (w, m["tasks"]["n"], m["tasks"]["of"]))
    t = m["throughput"]
    o.append("tasks integrated per day, next to what came back (reopened, followed up, Unreviewed):")
    for d in t["days"]:
        o.append("  %s  integrated %d · reopened %d · followed up %d · Unreviewed %d"
                 % (d["day"], d["integrated"], d["reopened"], d["followed_up"], d["unreviewed"]))
    if not t["days"]:
        o.append("  no integrated task yet")
    o.append("  total: %d integrated · reopened %s · followed up %s · Unreviewed %s"
             % (t["integrated"]["n"], ratio(t["reopened"]["n"], t["reopened"]["of"]),
                ratio(t["followed_up"]["n"], t["followed_up"]["of"]), ratio(t["unreviewed"]["n"], t["unreviewed"]["of"])))
    f = m["flow"]
    h = f["claim_to_integrated_hours"]
    o.append("speed and its cost:")
    o.append("  claim to INTEGRATED: median %s (%d tasks)" % ("%.1f h" % h["median"] if h["median"] is not None else "n/a", h["n"]))
    r = f["rejected_tasks"]
    o.append("  rejected at least once: %s reviewed tasks" % ratio(r["n"], r["of"]))
    nt = f["new_tip_after_approval"]
    o.append("  tasks with a new tip after an approval (rework without a reject): %s reviewed tasks" % ratio(nt["n"], nt["of"]))
    rr = f["review_rounds"]
    if rr["tasks"]:
        o.append("  review rounds per task: %.2f (%d rounds in %d tasks, %s; %s)" % (
            rr["per_task"], rr["rounds"], rr["tasks"], ratio(rr["rejects"], rr["rounds"]) + " rounds rejected",
            " · ".join("%s round%s %d" % (k, "" if k == "1" else "s", v) for k, v in sorted(rr["distribution"].items()))))
    else:
        o.append("  review rounds per task: no review yet")
    o.append("per command (calls · errors of known outcomes · median · p95; p95 needs %d timed calls):" % MIN_PCT)
    for c in m["commands"]:
        e = c["errors"]
        o.append("  %-18s %5d call(s) · errors %s · median %s · p95 %s" % (
            c["command"], c["calls"], ratio(e["n"], e["of"]), fmt_ms(c["median_ms"]), fmt_ms(c["p95_ms"])))
    if not m["commands"]:
        o.append("  no ledger lines yet (UAK-116 publishes them with `bb flush`)")
    hu = m["human"]
    o.append("human interventions:")
    qs = " · ".join("%s %d" % (k, v) for k, v in hu["queue_reasons"].items())
    qt = hu["queue_tasks"]
    o.append("  tasks the merge gate sent to a human: %s queued tasks%s" % (ratio(hu["queue_total"], qt["of"]), " (%s)" % qs if qs else ""))
    o.append("  tasks held in the queue only waiting their turn (no human): %d" % hu["waiting_for_gate"])
    o.append("  allow: %d freeze exceptions · %d test changes (human decisions)" % (hu["allow"]["freeze"], hu["allow"]["tests"]))
    mp = m["merge_paths"]
    n_of = lambda k: ratio(mp[k]["n"], mp[k]["of"])
    o.append("how tasks reached INTEGRATED (classified by %s):" % ("the base's own history" if mp["basis"] == "base history"
             else "the INTEGRATED event only: the base history is not available here"))
    o.append("  merged and pushed by the gate, no human (event `merge`): %s integrated tasks" % n_of("gate_pushed"))
    if mp["basis"] == "base history":
        o.append("  built by the gate, landed by a human after the queue asked (engine merge commit, then integrate): %s" % n_of("gate_built_human_landed"))
        o.append("  merged on the forge (PR merge commit or squash), then recorded with integrate: %s" % n_of("forge"))
        o.append("  recorded with integrate, merge commit not found or of another kind: %s" % n_of("recorded_unclassified"))
    else:
        o.append("  recorded with integrate (forge merge, or gate merge a human landed; not told apart): %s" % n_of("recorded_with_integrate"))
    rr = mp["recorded_with_integrate"]
    o.append("  of the %d recorded with integrate: with an agent identity %s · by a human (Role: human) %s · Unreviewed: yes %s"
             % (rr["n"], n_of("recorded_with_agent_identity"), n_of("recorded_by_human"), n_of("recorded_unreviewed")))
    o.append("  (names like joahanmorales-11 are agent identities a person may drive: `Role: human` only marks a person's own name)")
    ou = m["outside"]
    o.append("work outside the kit:")
    dm = ou["direct_to_main"]
    o.append("  commits on the base with no task: %s first-parent commits" % ratio(dm["n"], dm["of"]) if dm
             else "  commits on the base with no task: n/a (no base branch visible here, or a --since window)")
    ig = ou["integrated_outside_field"]
    o.append("  recorded as Integrated-Outside (work that reached the base with no task of its own): %s integrated tasks"
             % ratio(ig["n"], ig["of"]))
    mn = ou["manual_notes"]
    o.append("  manual notes: %d" % mn["count"] if mn["recorded"] else "  manual notes: not recorded yet")
    return "\n".join(o)


def task_view(data, tid, now):
    t = data["tasks"].get(tid)
    if not t:
        return None
    hist = t["hist"]
    # Time in each state: a gap belongs to the state the previous move put the task in. REVIEW splits into who has the
    # ball: the reviewer (after done), the owner (after a reject) and the merge (after an approve).
    spans, prev, label = {}, None, None
    for e in hist:
        if prev is not None:
            spans[label] = spans.get(label, 0) + max(0, e["epoch"] - prev)
        v = verdict_of(e)
        if e["state"] == "INTEGRATED":
            label, prev = None, None
            continue
        label = {"approve": "APPROVED (waiting for the merge)", "reject": "REJECTED (rework)"}[v["verdict"]] if v else \
            ("REVIEW (waiting for a reviewer)" if e["state"] == "REVIEW" else e["state"])
        prev = e["epoch"]
    if prev is not None and t["f"].get("State") not in ("INTEGRATED", "CANCELLED"):
        spans[label] = spans.get(label, 0) + max(0, now - prev)
    rounds = [v for v in (verdict_of(e) for e in hist) if v]
    ie = integrated_event(t)
    integ = None
    if ie:
        how = "gate merge" if ie["text"].startswith("merge") else ("integrate" if ie["text"].startswith("integrate") else ie["text"][:30])
        integ = {"by": ie["actor"], "how": how, "epoch": ie["epoch"], "unreviewed": t["f"].get("Unreviewed") == "yes",
                 "outside_gate": t["f"].get("Integrated-Outside") == "yes"}
    cmds, errs = {}, []
    for r in data["ledger"]:
        if r["task"] != tid:
            continue
        c = cmds.setdefault(r["cmd"], {"command": r["cmd"], "calls": 0, "errors": 0})
        c["calls"] += 1
        if r["rc"].isdigit() and r["rc"] != "0":
            c["errors"] += 1
            errs.append({"epoch": r["epoch"], "command": r["cmd"], "exit": int(r["rc"]), "code": r["code"], "agent": r["agent"]})
    return {"task": tid, "state": t["f"].get("State", "?"), "owner": t["f"].get("Owner", "?"),
            "states": [{"state": k, "seconds": v} for k, v in spans.items()],
            "rounds": rounds, "integrated": integ,
            "commands": sorted(cmds.values(), key=lambda c: (-c["calls"], c["command"])), "errors": errs}


def render_task(v):
    o = ["UAK METRICS · %s · %s · owner %s" % (v["task"], v["state"], v["owner"]), "time in each state:"]
    o += ["  %-34s %s" % (s["state"], hhmm(s["seconds"])) for s in v["states"]] or ["  no history yet"]
    o.append("review rounds: %d" % len(v["rounds"]))
    for i, r in enumerate(v["rounds"], 1):
        o.append("  %d. %s by %s%s%s" % (i, r["verdict"], r["reviewer"], " on " + r["sha"] if r["sha"] else "",
                                         " (%s)" % r["model"] if r["model"] != "unknown" else ""))
    g = v["integrated"]
    o.append("integrated: by %s (%s)%s%s" % (g["by"], g["how"], ", recorded Unreviewed" if g["unreviewed"] else "",
                                            ", outside the gate" if g["outside_gate"] else "") if g else "integrated: not yet")
    o.append("commands: " + (" · ".join("%s %d%s" % (c["command"], c["calls"], " (%d failed)" % c["errors"] if c["errors"] else "")
                                       for c in v["commands"]) or "none in the ledger"))
    for e in v["errors"]:
        o.append("  error: %s exit %d%s by %s" % (e["command"], e["exit"], "" if e["code"] == "-" else " " + e["code"], e["agent"]))
    return "\n".join(o)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="uak metrics")
    ap.add_argument("--since", type=int, metavar="DAYS")
    ap.add_argument("--task", metavar="ID")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--claims", metavar="DIR")
    a = ap.parse_args(argv)
    if a.since is not None and a.since < 1:
        print("metrics: --since needs a number of days of 1 or more", file=sys.stderr)
        return 2
    if a.task and not TASK_RE.match(a.task):
        print("metrics: %s is not a task ID" % a.task, file=sys.stderr)
        return 2
    now = int(os.environ.get("UAK_METRICS_NOW") or time.time())
    top = dash.run_git("rev-parse", "--show-toplevel")
    root = top.stdout.decode("utf-8", "replace").strip() if top.returncode == 0 else None
    if not root and not a.claims:
        print("metrics: not a Git repository", file=sys.stderr)
        return 2
    tmp = None
    try:
        if not a.claims and dash.run_git("ls-remote", "--exit-code", "--heads", os.environ.get("UAK_REMOTE", "origin"),
                                         "claims", cwd=root).returncode != 0:
            print("metrics: no remote claims branch yet", file=sys.stderr)
            return 2
        claims, _ = dash.snapshot(root or ".", a.claims)
        tmp = None if a.claims else claims
        data = load(claims)
        if a.task:
            v = task_view(data, a.task, now)
            if v is None:
                print("metrics: %s is not on the claims branch" % a.task, file=sys.stderr)
                return 1
            print(json.dumps(v, ensure_ascii=False, indent=1) if a.json else render_task(v))
            return 0
        m = build(data, a.since, now, root, bool(a.claims))
        print(json.dumps(m, ensure_ascii=False, indent=1) if a.json else render(m))
        return 0
    except RuntimeError as exc:
        print("metrics: %s" % exc, file=sys.stderr)
        return 1
    finally:
        if tmp:
            shutil.rmtree(str(tmp), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
