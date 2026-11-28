#!/usr/bin/env python3
"""uak metrics: every speed number next to its instability number, from the claims branch (read-only).

    bash .uak/bin/uak metrics [--since DAYS] [--task ID] [--trend] [--json] [--claims DIR]

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
MANUAL_FROM = (6, 7, 0)   # the first kit version whose black box records manual notes (UAK-121)
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
    m = re.match(r"review; (approve|reject)(?:; SHA ([0-9a-f]+))?(?:; reviewer ([^\s;]+))?(?:; cause (\S+))?", ev["text"])
    if ev["state"] == "REVIEW" and m:
        return {"epoch": ev["epoch"], "verdict": m.group(1), "sha": (m.group(2) or "")[:7],
                "reviewer": m.group(3) or ev["actor"], "model": ev["model"], "cause": m.group(4) or ""}
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
    bb_versions = []   # (day, (major, minor, patch)) of every black box line: which kit versions wrote the box (UAK-136)
    bb = c / "blackbox"
    for f in sorted(bb.glob("*.md")) if bb.is_dir() else []:
        for line in lines_of(f):
            p = line[2:].split(" | ") if line.startswith("- ") else []
            vm = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", p[1].strip()) if len(p) >= 2 else None
            if vm:
                bb_versions.append((f.name[:10], tuple(int(x) for x in vm.groups())))
            if len(p) >= 6 and p[5].strip() == "manual":
                manual.append({"day": f.name[:10], "text": p[7].strip() if len(p) > 7 else ""})
    lessons = {}   # memory/LESSONS.md: "- N | epoch | agent | task | paths | text"; "forget #N" lines remove one
    for line in lines_of(c / "memory" / "LESSONS.md"):
        p = line[2:].split(" | ") if re.match(r"^- \d", line) else []
        if len(p) < 6:
            continue
        fm = re.match(r"^forget #(\d+)$", p[5].strip())
        if fm:
            lessons.pop(int(fm.group(1)), None)
        elif p[0].strip().isdigit() and p[1].strip().isdigit():
            lessons[int(p[0])] = {"id": int(p[0]), "epoch": int(p[1]), "task": p[3].strip(), "paths": p[4].strip(), "text": p[5]}
    return {"lessons": lessons, "tasks": tasks, "ledger": ledger, "sums": sums, "queue": queue, "allows": allows, "followups": followups,
            "manual": manual, "humans": humans, "bb_versions": bb_versions}


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


def subject_kind(tid, pr, sub):
    """What one base subject says about task `tid` (PR number `pr` or None): engine / forge when it is this task's merge,
    other when it is some other task's or PR's merge, none when it names neither."""
    if sub.startswith("Merge %s reviewed by " % tid):
        return "engine"
    if pr and (sub.startswith("Merge pull request #%s " % pr) or sub.endswith("(#%s)" % pr)):
        return "forge"
    if re.match(r"^Merge [A-Z][A-Z0-9]*-\d+ reviewed by ", sub) or sub.startswith("Merge pull request #") \
            or re.search(r"\(#\d+\)$", sub):
        return "other"
    return "none"


def merge_kind(t, subjects):
    """(kind, by_history): how the task's code reached the base. The Merge-Commit field is used when it names a commit of
    the base that is not another task's merge or another PR's (UAK-132 writes the task's own merge, or `unknown`); a field
    that is missing, `unknown`, not on the base or another task's merge is the one that is not trusted: then the kind is
    read from the base's history by subjects (engine = the gate's "Merge UAK-N reviewed by", forge = the task's PR number
    in a "Merge pull request #N" or squash "(#N)" subject, other = none found), and by_history is True.
    Why (review of UAK-117): on UAK-030 and UAK-013 the field named another task's merge."""
    tid = t["id"]
    pr_m = re.search(r"/pull/(\d+)", t["f"].get("PR", ""))
    pr = pr_m.group(1) if pr_m else None
    field = t["f"].get("Merge-Commit", "").strip()
    sub = subjects.get(field) if re.match(r"^[0-9a-f]{40}$", field) else None
    if sub is not None:
        k = subject_kind(tid, pr, sub)
        if k != "other":
            return (k if k in ("engine", "forge") else "other"), False
    forge = False
    for sub in subjects.values():
        k = subject_kind(tid, pr, sub)
        if k == "engine":
            return "engine", True
        forge = forge or k == "forge"
    return ("forge" if forge else "other"), True


def direct_commits(root, ref, cutoff=None):
    """(direct, all) first-parent commits on the base (those committed at or after `cutoff` when given): a merge, the root,
    or a squash-merged task PR is not direct. None only when the base is not visible (UAK-136: a window with no commit is 0 of 0)."""
    if not ref:
        return None
    out = dash.run_git("log", "--first-parent", "--format=%ct|%P|%s", ref, cwd=root)
    if out.returncode != 0:
        return None
    total = direct = 0
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        when, _, rest = line.partition("|")
        parents, _, subject = rest.partition("|")
        if cutoff is not None and (not when.isdigit() or int(when) < cutoff):
            continue
        total += 1
        if len(parents.split()) == 1 and not re.match(r"^[A-Z][A-Z0-9]*-\d{3,}", subject) \
                and not re.search(r"\(#\d+\)$", subject):
            direct += 1
    return (direct, total)


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
    paths = {"gate_pushed": 0, "gate_pushed_ci": 0, "gate_built_human_landed": 0, "forge": 0, "recorded_unclassified": 0}
    rec = []
    by_hist = 0
    for t in done.values():
        ev = integrated_event(t)
        if ev["text"].startswith("merge"):
            paths["gate_pushed"] += 1
            if t["f"].get("Merge-Policy") == "ci":  # an engine change the gate landed under Merge-Engine: ci (UAK-131)
                paths["gate_pushed_ci"] += 1
            continue
        if not ev["text"].startswith("integrate"):
            continue
        rec.append(t)
        if subjects is not None:
            kind, hist_used = merge_kind(t, subjects)
            by_hist += 1 if hist_used else 0
        else:
            kind = "unknown"
        paths[{"engine": "gate_built_human_landed", "forge": "forge"}.get(kind, "recorded_unclassified")] += 1
    rec_human = sum(1 for t in rec if integrated_event(t)["actor"] in data["humans"])
    rec_unrev = sum(1 for t in rec if t["f"].get("Unreviewed") == "yes")
    # 5. Work outside the kit.
    outside = sum(1 for t in done.values() if t["f"].get("Integrated-Outside") == "yes")
    direct = direct_commits(git_root, base_ref(git_root, claims_given), cutoff)
    classified = subjects is not None
    manual = [m for m in data["manual"] if cutoff is None or m["day"] >= day_of(cutoff)]
    # `bb note manual` came with 6.7.0 (UAK-121): a box line of that version or later in the window means 0 is a real count.
    records_manual = any(v >= MANUAL_FROM and (cutoff is None or d >= day_of(cutoff)) for d, v in data["bb_versions"])
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
                        "gate_pushed_ci": count(paths["gate_pushed_ci"], len(done)),
                        "gate_built_human_landed": count(paths["gate_built_human_landed"], len(done)),
                        "forge": count(paths["forge"], len(done)),
                        "recorded_unclassified": count(paths["recorded_unclassified"], len(done)),
                        "recorded_with_integrate": count(len(rec), len(done)),
                        "classified_by_history": count(by_hist, len(rec)) if classified else None,
                        "recorded_with_agent_identity": count(len(rec) - rec_human, len(rec)),
                        "recorded_by_human": count(rec_human, len(rec)),
                        "recorded_unreviewed": count(rec_unrev, len(rec))},
        "outside": {"direct_to_main": count(*direct) if direct else None,
                    "integrated_outside_field": count(outside, len(done)),
                    "manual_notes": {"recorded": bool(manual) or records_manual, "count": len(manual)}},
    }


TREND_MIN = 5          # a window with fewer tasks than this gives counts, never a percentage or a median (UAK-201)
NO_CAUSE = "no cause recorded"
TREND_WEEKS = 8


def week_start(epoch):
    """Monday 00:00 UTC of the week of `epoch`, in integers (1970-01-01 was a Thursday): no locale, no date library."""
    d = int(epoch) // 86400
    return (d - (d + 3) % 7) * 86400


def share(n, d):
    """'3 of 8 (38%)', or '3 of 3 (fewer than 5 tasks: no percentage)'."""
    return "%d of %d" % (n, d) + (" (%d%%)" % round(100.0 * n / d) if d >= TREND_MIN else " (fewer than %d tasks: no percentage)" % TREND_MIN if d else "")


def lessons_shown(ev):
    m = re.search(r"; lessons shown ((?:#\d+,?)+)$", ev["text"]) if ev["state"] == "CLAIMED" else None
    return [int(x) for x in re.findall(r"#(\d+)", m.group(1))] if m else []


def path_overlap(a, b):
    """The engine's rule (memory.sh mem_select): paths overlap when one is a prefix of the other up to a glob; '*' or '' = all."""
    for x in a.replace(" ", "").split(","):
        for y in b.replace(" ", "").split(","):
            x1, y1 = x.split("*")[0], y.split("*")[0]
            if x1 == "" or y1 == "" or x1.startswith(y1) or y1.startswith(x1):
                return True
    return False


def window(data, lo, hi, label):
    done = [t for t in data["tasks"].values() if integrated_event(t) and lo <= integrated_event(t)["epoch"] < hi]
    verdicts = {t["id"]: [v for v in (verdict_of(e) for e in t["hist"]) if v] for t in done}
    reviewed = [t for t in done if verdicts[t["id"]]]
    rejected = sum(1 for t in reviewed if any(v["verdict"] == "reject" for v in verdicts[t["id"]]))
    rounds = sum(len(verdicts[t["id"]]) for t in reviewed)
    hours = []
    for t in done:
        c1, i1 = first_claim(t), integrated_event(t)
        if c1 and i1["epoch"] >= c1["epoch"]:
            hours.append((i1["epoch"] - c1["epoch"]) / 3600.0)
    human = sum(1 for t in done if not integrated_event(t)["text"].startswith("merge"))
    causes, shown, claims = {}, {}, 0
    for t in data["tasks"].values():
        for e in t["hist"]:
            v = verdict_of(e)
            if v and v["verdict"] == "reject" and lo <= e["epoch"] < hi:
                k = v["cause"] or NO_CAUSE
                causes[k] = causes.get(k, 0) + 1
            ls = lessons_shown(e)
            if ls and lo <= e["epoch"] < hi:
                claims += 1
                for n in ls:
                    shown[n] = shown.get(n, 0) + 1
    few = len(done) < TREND_MIN
    return {"label": label, "from": day_of(lo), "to": day_of(hi - 1), "tasks": len(done), "few": few,
            "rejected": count(rejected, len(reviewed)),
            "review_rounds": {"rounds": rounds, "tasks": len(reviewed), "per_task": round(rounds / float(len(reviewed)), 2) if reviewed and not few else None},
            "claim_to_integrated_hours": {"n": len(hours), "median": None if few else median(hours)},
            "needed_a_human": count(human, len(done)),
            "reject_causes": dict(sorted(causes.items(), key=lambda kv: (-kv[1], kv[0]))),
            "lessons_shown": {"claims": claims, "by_lesson": {"#%d" % k: v for k, v in sorted(shown.items(), key=lambda kv: (-kv[1], kv[0]))}}}


def lesson_effect(data):
    """Per lesson: tasks that saw it (the claim's record names it) and how many were later rejected with the lesson's cause,
    next to tasks claimed before it existed on overlapping paths. The lesson's cause is the one its own task was rejected for."""
    tasks = data["tasks"].values()
    rej = {t["id"]: [v for v in (verdict_of(e) for e in t["hist"]) if v and v["verdict"] == "reject"] for t in tasks}
    saw = {}
    for t in tasks:
        for e in t["hist"]:
            for n in lessons_shown(e):
                saw.setdefault(n, set()).add(t["id"])
    out = []
    for n, ls in sorted(data["lessons"].items()):
        causes = [v["cause"] for v in rej.get(ls["task"], []) if v["cause"]]
        cause = causes[-1] if causes else None
        seen = sorted(i for i in saw.get(n, ()) if i != ls["task"])
        before = sorted(t["id"] for t in tasks if t["id"] != ls["task"] and first_claim(t) and first_claim(t)["epoch"] < ls["epoch"]
                        and path_overlap(ls["paths"], t["f"].get("Paths", "")))
        hit = lambda ids: sum(1 for i in ids if any(v["cause"] == cause for v in rej.get(i, [])))
        e = {"lesson": n, "task": ls["task"], "cause": cause, "saw": count(hit(seen), len(seen)) if cause else {"n": None, "of": len(seen)},
             "before": count(hit(before), len(before)) if cause else {"n": None, "of": len(before)}}
        e["verdict"] = ("its task has no recorded reject cause: cannot be judged" if not cause else
                        "too few to tell" if len(seen) < TREND_MIN or len(before) < TREND_MIN else "counted")
        out.append(e)
    return out


def trend(data, now):
    this = week_start(now)
    first = min([integrated_event(t)["epoch"] for t in data["tasks"].values() if integrated_event(t)] or [now])
    start = max(week_start(first), this - (TREND_WEEKS - 1) * 7 * 86400)
    weeks = [window(data, w, w + 7 * 86400, "week of %s" % day_of(w)) for w in range(start, this + 1, 7 * 86400)]
    last7 = window(data, now - 7 * 86400, now + 1, "last 7 days")
    prev7 = window(data, now - 14 * 86400, now - 7 * 86400, "the 7 days before")
    return {"min_tasks": TREND_MIN, "weeks": weeks, "last_7_days": last7, "before_that": prev7, "lessons": lesson_effect(data)}


def render_trend(t):
    o = ["UAK TREND · weeks start on Monday (UTC) · a window with fewer than %d tasks says so and gives counts, no percentage or median" % t["min_tasks"]]

    def block(w):
        o.append("%s (%s .. %s): %d task(s) integrated%s" % (w["label"], w["from"], w["to"], w["tasks"],
                 " · fewer than %d tasks" % t["min_tasks"] if w["few"] else ""))
        if not w["tasks"] and not w["reject_causes"] and not w["lessons_shown"]["claims"]:
            return
        r = w["rejected"]
        o.append("  rejected at least once: %s reviewed tasks" % share(r["n"], r["of"]))
        rr = w["review_rounds"]
        o.append("  review rounds per task: %s (%d rounds, %d reviewed tasks)" % (
            "%.2f" % rr["per_task"] if rr["per_task"] is not None else "n/a: fewer than %d tasks" % t["min_tasks"], rr["rounds"], rr["tasks"]))
        h = w["claim_to_integrated_hours"]
        o.append("  claim to INTEGRATED: median %s (%d tasks)" % ("%.1f h" % h["median"] if h["median"] is not None else "n/a: fewer than %d tasks" % t["min_tasks"], h["n"]))
        nh = w["needed_a_human"]
        o.append("  needed a human at merge (integrated after the gate did not merge): %s tasks" % share(nh["n"], nh["of"]))
        nrej = sum(w["reject_causes"].values())
        o.append("  reject causes (%d reject%s): %s" % (nrej, "" if nrej == 1 else "s", " · ".join("%s %d" % kv for kv in w["reject_causes"].items()) or "none"))
        ls = w["lessons_shown"]
        o.append("  lessons shown at claim (%d claim%s): %s" % (ls["claims"], "" if ls["claims"] == 1 else "s",
                 " · ".join("%s x%d" % kv for kv in ls["by_lesson"].items()) or "none"))

    for w in t["weeks"]:
        block(w)
    o.append("last 7 days against the 7 before:")
    block(t["last_7_days"])
    block(t["before_that"])
    o.append("what each lesson changed (tasks that saw it vs tasks before it on its paths, rejected with its cause; needs %d tasks per side):" % t["min_tasks"])
    for e in t["lessons"][-20:]:
        if e["verdict"] == "counted":
            o.append("  lesson #%d (cause %s, from %s): saw it %s · before it %s" % (e["lesson"], e["cause"], e["task"],
                     "%d of %d tasks rejected with it" % (e["saw"]["n"], e["saw"]["of"]), "%d of %d" % (e["before"]["n"], e["before"]["of"])))
        elif e["verdict"] == "too few to tell":
            o.append("  lesson #%d (cause %s, from %s): too few to tell (%d tasks saw it, %d before it)" % (e["lesson"], e["cause"], e["task"], e["saw"]["of"], e["before"]["of"]))
        else:
            o.append("  lesson #%d (from %s): %s (%d tasks saw it)" % (e["lesson"], e["task"], e["verdict"], e["saw"]["of"]))
    if not t["lessons"]:
        o.append("  no lessons recorded")
    return "\n".join(o)


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
        # Lines written before every command was timed carry no exit code: counted apart, not as successes (UAK-136).
        unk = c["calls"] - e["of"]
        o.append("  %-18s %5d call(s) · errors %s%s · median %s · p95 %s" % (
            c["command"], c["calls"], ratio(e["n"], e["of"]), " (outcome not recorded: %d)" % unk if unk > 0 else "",
            fmt_ms(c["median_ms"]), fmt_ms(c["p95_ms"])))
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
    o.append("    of them, engine changes released by Merge-Engine: ci (Merge-Policy: ci), apart from the rest: %s" % n_of("gate_pushed_ci"))
    if mp["basis"] == "base history":
        o.append("  built by the gate, landed by a human after the queue asked (engine merge commit, then integrate): %s" % n_of("gate_built_human_landed"))
        o.append("  merged on the forge (PR merge commit or squash), then recorded with integrate: %s" % n_of("forge"))
        o.append("  recorded with integrate, merge commit not found or of another kind: %s" % n_of("recorded_unclassified"))
    else:
        o.append("  recorded with integrate (forge merge, or gate merge a human landed; not told apart): %s" % n_of("recorded_with_integrate"))
    if mp["classified_by_history"]:
        bh = mp["classified_by_history"]
        o.append("  %d of %d recorded tasks had a wrong, missing or unknown Merge-Commit and were classified by the base's history" % (bh["n"], bh["of"]))
    rr = mp["recorded_with_integrate"]
    o.append("  of the %d recorded with integrate: with an agent identity %s · by a human (Role: human) %s · Unreviewed: yes %s"
             % (rr["n"], n_of("recorded_with_agent_identity"), n_of("recorded_by_human"), n_of("recorded_unreviewed")))
    o.append("  (names like joahanmorales-11 are agent identities a person may drive: `Role: human` only marks a person's own name)")
    ou = m["outside"]
    o.append("work outside the kit:")
    dm = ou["direct_to_main"]
    o.append("  commits on the base with no task: %s first-parent commits" % ratio(dm["n"], dm["of"]) if dm
             else "  commits on the base with no task: n/a (no base branch visible here)")
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
    ap.add_argument("--trend", action="store_true", help="per week and last 7 days against the 7 before, reject causes, lessons")
    ap.add_argument("--claims", metavar="DIR")
    ap.add_argument("--fresh", action="store_true", help="accepted; metrics always fetches")
    a = ap.parse_args(argv)
    if a.since is not None and a.since < 1:
        print("metrics: --since needs a number of days of 1 or more", file=sys.stderr)
        return 2
    if a.trend and (a.task or a.since is not None):
        print("metrics: --trend takes no --task or --since (it has its own windows)", file=sys.stderr)
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
        if a.trend:
            tr = trend(data, now)
            print(json.dumps(tr, ensure_ascii=False, indent=1) if a.json else render_trend(tr))
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
    import ledger_py  # UAK-136: closes this command's ledger line
    sys.exit(ledger_py.run(main))
