#!/usr/bin/env python3
"""uak dash: one local page with the whole team state, read-only from the claims branch.

    bash .uak/bin/uak dash [--watch SECONDS] [--open] [--out DIR] [--claims DIR]

Writes <git common dir>/uak-dash/index.html (once) and data.js (every refresh). The page reloads data.js by
itself, so it works from file:// with no server, no CDN and no framework. --watch keeps refreshing (default 20 s).
--claims DIR reads an extracted claims checkout instead of fetching (autopsies, tests).
Why (the human's view, MLB hackathon): to know where the project stood, the humans asked the agents; 22 messages
asked around for reviewers and 99 digests were printed. One page shows progress, agents, conversations, reviews,
the human queue and the black box without asking anyone.
Python 3.8+ standard library only. Data stays on this machine.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import io
import tempfile
import time
import webbrowser
from pathlib import Path

PRESENCE = 1800
STALL = 5400


def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip() or "git " + " ".join(args))
    return r.stdout


def fields(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z][A-Za-z0-9-]*): (.*)$", line)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip()
    return out


def num(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def rows(text, n=None):
    """'- a | b | c' lines → lists of fields."""
    out = []
    for line in text.splitlines():
        if line.startswith("- "):
            parts = line[2:].split(" | ")
            if n:
                parts = parts[: n - 1] + [" | ".join(parts[n - 1:])] if len(parts) > n else parts
            out.append([p.strip() for p in parts])
    return out


def snapshot(root, claims_dir=None):
    """A directory with the claims files, and the backlog text (main's TASKS.md + claims backlog + amendments)."""
    if claims_dir:
        return Path(claims_dir), read(Path(root) / ".uak/TASKS.md")
    remote = os.environ.get("UAK_REMOTE", "origin")
    base = os.environ.get("UAK_BASE", "main")
    git("fetch", "-q", remote, f"+refs/heads/claims:refs/uak/dash-claims", f"+refs/heads/{base}:refs/uak/dash-base", cwd=root)
    tmp = Path(tempfile.mkdtemp(prefix="uak-dash-"))
    data = git("archive", "refs/uak/dash-claims", cwd=root)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        for m in t.getmembers():
            if m.name.startswith("/") or ".." in Path(m.name).parts:
                continue
            t.extract(m, tmp)
    backlog = git("show", "refs/uak/dash-base:.uak/TASKS.md", cwd=root, check=False).decode("utf-8", "replace")
    return tmp, backlog


def backlog_tasks(text):
    tasks, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^## ([A-Z][A-Z0-9]*-\d+)\s*[·—-]*\s*(.*)$", line)
        if m:
            cur = m.group(1)
            tasks[cur] = {"id": cur, "title": m.group(2).strip(), "priority": "", "paths": "", "depends": ""}
            continue
        if line.startswith("# "):
            cur = None
        if cur:
            s = re.sub(r"\*\*", "", line).strip().lstrip("-").strip()
            for key, name in (("Priority", "priority"), ("Paths", "paths"), ("Depends on", "depends")):
                if s.startswith(key + ":"):
                    tasks[cur][name] = s.split(":", 1)[1].strip()
    return tasks


def human_of(name, humans):
    m = re.match(r"^(.*)-[A-Za-z0-9]+$", name)
    base = m.group(1) if m and not re.search(r"-[A-Za-z0-9]+$", m.group(1)) else name
    return humans.get(name) or base


def build(c, backlog_text, repo):
    now = int(time.time()) if not os.environ.get("UAK_NOW") else int(os.environ["UAK_NOW"])
    cfg = fields(read(c / "meta/config.md"))
    plan = backlog_tasks(backlog_text + "\n" + read(c / "backlog/TASKS.md"))
    amended = backlog_tasks(read(c / "backlog/AMEND.md"))
    for k, v in amended.items():
        plan.setdefault(k, v).update({x: y for x, y in v.items() if y})

    # Tasks: the backlog, with the state and records from claims.
    tasks = {}
    for k, v in plan.items():
        tasks[k] = dict(v, state="AVAILABLE", owner="", pr="", progress="", progress_changed=0, updated=0, stalled=0)
    for f in sorted((c / "tasks").glob("*.md")):
        r = fields(read(f))
        tid = r.get("ID", f.stem)
        t = tasks.setdefault(tid, {"id": tid, "title": "", "priority": r.get("Priority", ""), "paths": r.get("Paths", ""), "depends": ""})
        t.update(state=r.get("State", "AVAILABLE"), owner=r.get("Owner", ""), pr=r.get("PR", ""), progress=r.get("Progress", ""),
                 progress_changed=num(r.get("Progress-Changed")), updated=num(r.get("Updated")), lease=num(r.get("Lease-Until")),
                 next=r.get("Next", ""), away=num(r.get("Away")))
        if not t.get("paths"):
            t["paths"] = r.get("Paths", "")
        stall = num(cfg.get("Stall-Seconds"), STALL)
        if t["state"] == "CLAIMED" and t["progress_changed"] and now - t["progress_changed"] >= stall:
            t["stalled"] = (now - t["progress_changed"]) // 60

    # Messages.
    msgs = []
    for p in rows(read(c / "inbox/log.md"), 7):
        if len(p) < 7:
            continue
        msgs.append({"n": num(p[0]), "t": num(p[1]), "from": p[2], "to": [x for x in p[3].split(",") if x], "kind": p[4],
                     "task": "" if p[5] == "-" else p[5], "text": p[6]})

    # Agents: every identity seen anywhere, with presence.
    humans, seen, ended, sessions, events, checkpoints, started = {}, {}, {}, {}, {}, {}, {}
    for f in (c / "meta/agents").glob("*.md"):
        r = fields(read(f))
        n = f.stem
        seen[n] = max(seen.get(n, 0), num(r.get("Updated")))
        if r.get("Human") and r["Human"] != n:
            humans[n] = r["Human"]
        ended[n] = num(r.get("Session-Ended"))
        sessions[n], events[n], checkpoints[n], started[n] = num(r.get("Sessions")), num(r.get("Events")), num(r.get("Checkpoints")), num(r.get("Started"))
    for f in (c / "inbox/read").glob("*.md"):
        seen[f.stem] = max(seen.get(f.stem, 0), num(fields(read(f)).get("Updated")))
    sent = {}
    for m in msgs:
        seen[m["from"]] = max(seen.get(m["from"], 0), m["t"])
        sent[m["from"]] = sent.get(m["from"], 0) + 1
    retired = {f.stem for f in (c / "meta/retired").glob("*.md")}
    bare = {n for n in seen if not re.search(r"-[A-Za-z0-9]+$", n)}
    human_names = {n for n in bare if any(x.startswith(n + "-") for x in seen)} | set(humans.values())
    verdicts = {}
    for m in msgs:
        if m["kind"] in ("approve", "reject"):
            verdicts[m["from"]] = verdicts.get(m["from"], 0) + 1
    agents = []
    for n in sorted(seen):
        if n in ("scheduler", "github", ""):
            continue
        last = seen[n]
        if n in retired:
            status = "retired"
        elif ended.get(n, 0) >= last and ended.get(n, 0):
            status = "away"
        elif now - last <= PRESENCE:
            status = "online"
        elif now - last <= 3 * 3600:
            status = "recent"
        else:
            status = "offline"
        cur = [t for t in tasks.values() if t.get("owner") == n and t["state"] in ("CLAIMED", "BLOCKED", "REVIEW")]
        agents.append({"name": n, "human": human_of(n, humans), "is_human": n in human_names, "last_seen": last, "status": status,
                       "tasks": [{"id": t["id"], "state": t["state"]} for t in cur], "sessions": sessions.get(n, 0),
                       "events": events.get(n, 0), "checkpoints": checkpoints.get(n, 0), "messages": sent.get(n, 0),
                       "verdicts": verdicts.get(n, 0), "started": started.get(n, 0)})

    # Reviews, locks, queue.
    reviews = []
    for f in (c / "reviews").glob("*.md"):
        r = fields(read(f))
        reviews.append({"task": r.get("ID", f.stem), "verdict": r.get("Verdict", ""), "reviewer": r.get("Reviewer", ""),
                        "sha": r.get("SHA", "")[:7], "at": num(r.get("Reviewed"))})
    locks = []
    for f in (c / "reviews").glob("*.reviewing"):
        r = fields(read(f))
        if num(r.get("Until")) > now:
            locks.append({"task": f.stem, "reviewer": r.get("Reviewer", ""), "until": num(r.get("Until"))})
    queue = []
    for f in (c / "queue").glob("*.md"):
        r = fields(read(f))
        if r.get("State") not in ("INTEGRATED", "") or r.get("Reason"):
            if r.get("State") != "INTEGRATED":
                queue.append({"task": r.get("Task", f.stem), "state": r.get("State", ""), "reason": r.get("Reason", ""), "at": num(r.get("Updated"))})
    # Open review offers: the last review message per REVIEW task with no verdict on its tip.
    offers = []
    tips = {f.stem: fields(read(f)).get("Task-Tip", "") for f in (c / "tasks").glob("*.md")}
    vsha = {r["task"]: r["sha"] for r in reviews}
    for t in tasks.values():
        if t["state"] != "REVIEW":
            continue
        tip = tips.get(t["id"], "")
        if tip and vsha.get(t["id"], "") == tip[:7]:
            continue
        last = [m for m in msgs if m["kind"] == "review" and m["task"] == t["id"]]
        if last:
            offers.append({"task": t["id"], "to": last[-1]["to"], "since": last[-1]["t"], "owner": t["owner"]})

    # Black box.
    bb = []
    usage = {}
    for f in sorted((c / "blackbox").glob("*.md")):
        for p in rows(read(f)):
            if len(p) < 8:
                continue
            row = {"time": p[0], "kit": p[1], "harness": p[2], "source": p[4], "kind": p[5], "command": p[6], "what": p[7],
                   "fix": (p[8] if len(p) > 8 else "").replace("fix: ", "")}
            if row["kind"] == "usage":
                for kv in row["what"].split():
                    k, _, v = kv.partition(":")
                    if v.isdigit():
                        u = usage.setdefault(row["harness"], {})
                        u[k] = u.get(k, 0) + int(v)
                continue
            bb.append(row)
    bb.sort(key=lambda r: r["time"])

    decisions = [{"t": num(p[0]), "kind": p[1] if len(p) > 1 else "", "who": p[2] if len(p) > 2 else "", "text": " | ".join(p[3:])}
                 for p in rows(read(c / "DECISIONS.md")) if p and p[0].isdigit()]
    lessons, gone = [], set()
    for p in rows(read(c / "memory/LESSONS.md"), 6):
        if len(p) >= 6:
            if p[5].startswith("forget #"):
                gone.add(p[5][8:])
            else:
                lessons.append({"n": p[0], "t": num(p[1]), "agent": p[2], "task": p[3], "paths": p[4], "text": p[5]})
    lessons = [x for x in lessons if x["n"] not in gone]

    tokens = {"total": 0, "by_task": {}, "by_harness": {}, "by_scope": {}}
    for f in (c / "tokens").glob("*.md"):
        for p in rows(read(f)):
            if len(p) >= 9 and p[5].isdigit():
                t = sum(num(x) for x in p[5:9])
                tokens["total"] += t
                for key, val in (("by_task", p[0]), ("by_harness", p[1]), ("by_scope", p[3])):
                    tokens[key][val] = tokens[key].get(val, 0) + t

    states = {}
    for t in tasks.values():
        states[t["state"]] = states.get(t["state"], 0) + 1
    live = [t for t in tasks.values() if t["state"] != "CANCELLED"]
    weight = {"INTEGRATED": 1.0, "REVIEW": 0.8, "CLAIMED": 0.4, "BLOCKED": 0.3}
    progress = {"done": round(100 * states.get("INTEGRATED", 0) / max(1, len(live))),
                "weighted": round(100 * sum(weight.get(t["state"], 0) for t in live) / max(1, len(live))),
                "total": len(live), "states": states}
    freeze = num(cfg.get("Freeze-Epoch"))
    return {"repo": repo, "generated": now, "mode": cfg.get("Mode", ""), "freeze": freeze, "progress": progress,
            "tasks": sorted(tasks.values(), key=lambda t: t["id"]), "agents": agents, "messages": msgs[-600:],
            "reviews": reviews, "locks": locks, "queue": queue, "offers": offers, "blackbox": bb[-400:], "usage": usage,
            "decisions": decisions[-60:], "lessons": lessons[-60:], "tokens": tokens}


def main():
    ap = argparse.ArgumentParser(prog="uak dash")
    ap.add_argument("--watch", nargs="?", const=20, type=int, default=0)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--claims")
    a = ap.parse_args()
    root = git("rev-parse", "--show-toplevel").decode().strip()
    common = Path(root) / git("rev-parse", "--git-common-dir", cwd=root).decode().strip()
    out = Path(a.out) if a.out else common.resolve() / "uak-dash"
    out.mkdir(parents=True, exist_ok=True)
    tpl = Path(__file__).with_name("dash.html")
    shutil.copyfile(tpl, out / "index.html")
    repo = Path(root).name
    refresh = a.watch or 20
    opened = False
    while True:
        tmp = None
        try:
            c, backlog = snapshot(root, a.claims)
            tmp = None if a.claims else c
            data = build(Path(c), backlog, repo)
            data["refresh"] = refresh
            body = "window.UAK_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
            (out / "data.js.tmp").write_text(body, encoding="utf-8")
            os.replace(out / "data.js.tmp", out / "data.js")
            print(f"DASH {out / 'index.html'} · {data['progress']['done']}% integrated · {len(data['agents'])} agents · "
                  f"{len(data['messages'])} messages · refresh {refresh} s", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"DASH_ERROR: {exc}", file=sys.stderr, flush=True)
            if not a.watch:
                return 1
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
        if a.open and not opened:
            webbrowser.open((out / "index.html").resolve().as_uri())
            opened = True
        if not a.watch:
            return 0
        time.sleep(a.watch)


if __name__ == "__main__":
    sys.exit(main())
