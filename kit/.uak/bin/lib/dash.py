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
import urllib.parse
import webbrowser
from pathlib import Path

PRESENCE = 1800
STALL = 5400
BASE_PROJECT = "base-project.md"  # snapshot() leaves the base branch's PROJECT.md here, inside the claims directory


GIT_TIMEOUT = 30  # seconds: an unreachable remote must end in a message, not a hang (audit of v6.5.0, #9)


RUNNER = None  # UAK-156: the wizard sets this to its own runner, so every git of the page is a child it records and ends


def run_git(*args, cwd=None, input=None):
    """subprocess.run of git with the timeout; a timeout becomes a RuntimeError of one line."""
    if RUNNER:
        try:
            return RUNNER(["git", *args], cwd=cwd, timeout=GIT_TIMEOUT, binary=True, input=input)
        except subprocess.TimeoutExpired:
            raise RuntimeError("git %s timed out after %d s: is the remote reachable?" % (args[0] if args else "", GIT_TIMEOUT)) from None
    # No prompt for credentials, and a git hook's own GIT_DIR must not redirect the call (the page may start from a hook).
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(key, None)
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=env, timeout=GIT_TIMEOUT, input=input)
    except subprocess.TimeoutExpired:
        raise RuntimeError("git %s timed out after %d s: is the remote reachable?" % (args[0] if args else "", GIT_TIMEOUT)) from None


def git(*args, cwd=None, check=True):
    r = run_git(*args, cwd=cwd)
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
        return Path(p).read_text(encoding="utf-8", errors="replace").replace("\r", "")
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
    git("fetch", "-q", remote, f"+refs/heads/{base}:refs/uak/dash-base", cwd=root)
    tmp = Path(tempfile.mkdtemp(prefix="uak-dash-"))
    # Before the first claim there is no claims branch: the page shows the backlog, all AVAILABLE.
    # Why: `uak dash` right after /uak-plan failed with "couldn't find remote ref refs/heads/claims".
    has_claims = run_git("ls-remote", "--exit-code", "--heads", remote, "claims", cwd=root).returncode == 0
    if has_claims:
        git("fetch", "-q", remote, "+refs/heads/claims:refs/uak/dash-claims", cwd=root)
        data = git("archive", "refs/uak/dash-claims", cwd=root)
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            for m in t.getmembers():
                # Plain files and directories only: a symlink on claims could point the page at any local file.
                if m.name.startswith("/") or ".." in Path(m.name).parts or not (m.isfile() or m.isdir()):
                    continue
                # filter="data" where tarfile has it (3.12+, backports): no DeprecationWarning on stderr, and the
                # extraction refuses what the check above already skips. Why (QA round C, 2026-11-14, C-11).
                if hasattr(tarfile, "data_filter"):
                    t.extract(m, tmp, filter="data")
                else:
                    t.extract(m, tmp)
    # TASKS.md and PROJECT.md of the base branch in one git process (UAK-147: the leases are read from the base's PROJECT.md, as status and board do).
    names = ["refs/uak/dash-base:.uak/TASKS.md", "refs/uak/dash-base:.uak/PROJECT.md"]
    blob = run_git("cat-file", "--batch", cwd=root, input="\n".join(names).encode() + b"\n").stdout
    texts, pos = [], 0
    for _ in names:
        end = blob.find(b"\n", pos)
        head = blob[pos:end].split() if end >= 0 else []
        if len(head) == 3 and head[1] == b"blob" and head[2].isdigit():
            size = int(head[2])
            texts.append(blob[end + 1:end + 1 + size].decode("utf-8", "replace"))
            pos = end + 2 + size
        else:
            texts.append("")
            pos = end + 1 if end >= 0 else len(blob)
    (tmp / BASE_PROJECT).write_text(texts[1], encoding="utf-8")
    return tmp, texts[0]


# Live-URL in PROJECT.md: where the team's app is deployed. Claims' meta/config.md carries only the engine's keys,
# so the dashboard reads it from the base branch's PROJECT.md (the copy the team agreed on) or the local one.
LIVE_URL_KEY = re.compile(r"(?m)^[-* ]*\**Live-URL\**:\**[ \t]*`?([^`\r\n]*?)`?[ \t]*$")


def live_url(value):
    """An absolute https:// link with a host and no credentials, or None: never a guessed or scriptable URL."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value.startswith("https://") or len(value) > 2048:
        return None
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return None
    # The key is optional and hand-edited: a malformed value (an unclosed IPv6 bracket, a bad port) is absent, never
    # an error that stops setup or the dashboard from reading the project.
    try:
        parts = urllib.parse.urlsplit(value)
        if parts.scheme != "https" or not parts.hostname or "@" in parts.netloc:
            return None
        parts.port  # raises ValueError on a non-numeric or out-of-range port
    except ValueError:
        return None
    return value


def project_live_url(text):
    match = LIVE_URL_KEY.search(text or "")
    return live_url(match.group(1)) if match else None


def base_live_url(root):
    text = git("show", "refs/uak/dash-base:.uak/PROJECT.md", cwd=root, check=False).decode("utf-8", "replace")
    return project_live_url(text)


# Mode (sprint or marathon) is a PROJECT.md key; claims' meta/config.md has it only when the engine wrote one.
# Why (QA round C, 2026-11-14, C-12): the page reported mode "" for a sprint project. \r: a CRLF PROJECT.md (Windows).
MODE_KEY = re.compile(r"(?m)^[-* ]*\**Mode\**:\**[ \t]*`?([A-Za-z]+)`?[ \t\r]*$")


def project_mode(text):
    match = MODE_KEY.search(text or "")
    return match.group(1).lower() if match else ""


def base_mode(root):
    return project_mode(git("show", "refs/uak/dash-base:.uak/PROJECT.md", cwd=root, check=False).decode("utf-8", "replace"))


NAME_KEY = re.compile(r"^\s*(?:-\s*)?\**(?:Project|Project-Name|Name)\**\s*:\s*(.+?)\s*$", re.M | re.I)


def project_name(root):
    """The PROJECT's name, never a linked worktree's folder: what `.uak/PROJECT.md` declares (`Project: NAME`), else the
    repository name of the base remote, else the main checkout's folder (the parent of the common git dir)."""
    text = read(Path(root) / ".uak/PROJECT.md") if (Path(root) / ".uak/PROJECT.md").is_file() else ""
    m = NAME_KEY.search(text or "")
    if m and m.group(1).strip():
        return m.group(1).strip().strip("`\"'")[:60]
    remote = os.environ.get("UAK_REMOTE", "origin")
    url = git("config", "--get", "remote.%s.url" % remote, cwd=root, check=False).decode("utf-8", "replace").strip()
    tail = re.split(r"[/:\\]", url.rstrip("/\\"))[-1] if url else ""
    tail = tail[:-4] if tail.endswith(".git") else tail
    if tail:
        return tail
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=root, check=False).decode().strip()
    if common:
        c = Path(common)
        name = (c.parent if c.name == ".git" else c).name
        return name[:-4] if name.endswith(".git") else name
    return Path(root).name


def page_version(template):
    """A short hash of the page's file: the page compares it with the one in data.js and reloads itself when a newer page was written."""
    import hashlib
    return hashlib.sha1(Path(template).read_bytes()).hexdigest()[:12]


def base_commits(root):
    """Commits reachable from the base branch the page was read against (`git rev-list --count refs/uak/dash-base`); None when
    that ref is not there, so the share card leaves the figure out instead of showing a made-up zero."""
    out = git("rev-list", "--count", "refs/uak/dash-base", cwd=root, check=False).strip()
    return int(out) if out.isdigit() else None


def workspace_data(root, keep=None):
    """The same dashboard model, including a clearly labelled offline/local-plan state. `keep` (a dict, UAK-156): the
    claims copy and what was read beside it stay on disk and are put in it, for a caller that builds the model again
    from them (it removes the folder); without it the copy is removed here."""
    remote = os.environ.get("UAK_REMOTE", "origin")
    configured = git("config", "--get", "remote.%s.url" % remote, cwd=root, check=False).strip()
    extracted = None
    warning = "No remote is connected. Showing the local plan."
    if configured:
        try:
            extracted, backlog = snapshot(root)
            data = build(extracted, backlog, project_name(root))
            data.update(source="remote", connection="ok", warning="", refresh=20, live_url=base_live_url(root))
            commits = base_commits(root)
            if commits is not None:
                data["commits"] = commits
            data["mode"] = data.get("mode") or base_mode(root)
            if keep is not None:
                keep.update(dir=str(extracted), backlog=backlog, live_url=data["live_url"], base_mode=data["mode"])
                extracted = None
            return data
        except (OSError, RuntimeError, subprocess.SubprocessError):
            # A remote that exists but cannot be read is a different problem from no remote at all.
            warning = "Coordination could not refresh. Showing the local plan."
        finally:
            if extracted:
                shutil.rmtree(extracted, ignore_errors=True)
    with tempfile.TemporaryDirectory(prefix="uak-local-dashboard-") as folder:
        data = build(Path(folder), read(Path(root) / ".uak/TASKS.md"), project_name(root))
    data.update(source="local", connection="unreachable" if configured else "none", warning=warning, refresh=20,
                live_url=project_live_url(read(Path(root) / ".uak/PROJECT.md")))
    return data


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


def ci_failed(c, tid, since):
    """Failed checks pr-sync told about the task since the tip was recorded (messages from `github` to task:ID,
    "#N CI failed: NAME URL"); same rule as review_ci_failed in lib/status.sh. pr-sync stores no SHA and no passes: the
    message time against the tip's time ties a failure to this tip. Returns "NAME" or "NAME +N", and when it was told."""
    names, first_at = [], 0
    for line in read(c / "inbox/log.md").splitlines():
        if not line.startswith("- "):
            continue
        p = line[2:].split(" | ", 6)
        if len(p) < 7 or p[2] != "github" or p[5] != tid or not p[1].isdigit() or int(p[1]) < since:
            continue
        for seg in p[6].split("CI failed: ")[1:]:
            name = seg.split(" https://")[0].split(" · ")[0]
            if name not in names:
                names.append(name)
                first_at = first_at or int(p[1])
    if not names:
        return "", 0
    return names[0] + (" +%d" % (len(names) - 1) if len(names) > 1 else ""), first_at


def review_substate(c, tid, rec, now, lease):
    """What a task in REVIEW waits for: the same words and rules as review_substate in lib/status.sh (the test compares
    them on one fixture). Derived from claims: Task-Tip, reviews/ID.md, reviews/ID.reviewing, queue/ID.md, messages
    (a failed check pr-sync told) and the worklog's `done` and `review` events. Returns kind, text, since, rounds, rejects, late."""
    tip = rec.get("Task-Tip", "")
    last_done = num(rec.get("Updated"))
    rounds = rejects = 0
    wl = c / rec.get("Worklog", "") if rec.get("Worklog") else None
    if wl and wl.is_file():
        for line in read(wl).splitlines():
            m = re.match(r"^- (\d+) \| [^|]*\| [^|]*\| ?(.*)$", line.rstrip("\r"))
            if not m:
                continue
            text = m.group(2)
            if text.startswith("done;"):
                last_done = int(m.group(1))
            elif text.startswith("review; reject;"):
                rounds += 1
                rejects += 1
            elif text.startswith("review; "):
                rounds += 1
    rv = fields(read(c / "reviews" / (tid + ".md")))
    lk = fields(read(c / "reviews" / (tid + ".reviewing")))
    rsha, verdict = rv.get("SHA", ""), rv.get("Verdict", "")
    rtime = num(rv.get("Reviewed")) or last_done
    if rsha and rsha == tip and verdict == "approve":
        q = fields(read(c / "queue" / (tid + ".md")))
        ci, ci_at = ci_failed(c, tid, last_done)
        if q.get("State") == "HUMAN":
            kind, text, since = "human", "approved, waiting for a human merge" + (": " + q["Reason"] if q.get("Reason") else ""), num(q.get("Updated")) or rtime
        elif ci:
            kind, text, since = "cifail", "approved, CI failed: " + ci, ci_at
        else:
            kind, text, since = "owner", "approved, waiting for the owner to merge", rtime
    elif rsha and rsha == tip:
        kind, text, since = "changes", "changes requested (round %d)" % rounds, rtime
    elif lk.get("Reviewer") and lk.get("SHA", "") == tip and now < num(lk.get("Until")):
        kind, text, since = "review", "in review by " + lk["Reviewer"], num(lk.get("Started")) or last_done
    elif rsha:
        kind, text, since = "rereview", "re-review (round %d)" % (rounds + 1), last_done
    else:
        kind, text, since = "waiting", "waiting for a reviewer", last_done
    return {"kind": kind, "text": text, "since": since, "rounds": rounds, "rejects": rejects,
            "late": bool(lease and since and now - since > lease)}


def harnesses(c, tid):
    """Who ran the task, on which harness and model (UAK-118 task-session records)."""
    out = []
    for d in sorted((c / "meta/task-sessions" / tid).glob("agent-*")):
        h = m = ""
        for f in sorted(d.glob("session-*.md")):
            r = fields(read(f))
            h, m = r.get("Harness", h), r.get("Model", m)
        if h or m:
            out.append({"agent": d.name[len("agent-"):], "harness": h or "unknown", "model": m or "unknown"})
    return out


def review_lease(project):
    """The review lease as status.sh review_lease_of: UAK_LEASE_SECONDS, else Lease-Seconds, else 1800; Review-Lease-Seconds, else 4 x the lease."""
    lease = 0
    for v in (os.environ.get("UAK_LEASE_SECONDS"), project.get("Lease-Seconds")):
        n = num(v) if str(v or "").strip().isdigit() else 0
        lease = lease or n
        if lease:
            break
    lease = lease or 1800
    v = str(project.get("Review-Lease-Seconds") or "").strip()
    return int(v) if v.isdigit() and int(v) > 0 else 4 * lease


def build(c, backlog_text, repo, root=None):
    now = int(time.time()) if not os.environ.get("UAK_NOW") else int(os.environ["UAK_NOW"])
    cfg = fields(read(c / "meta/config.md"))
    # The base branch's PROJECT.md (--claims: the checkout's, no fetch): where Lease-Seconds and Review-Lease-Seconds live.
    project = fields(read(c / BASE_PROJECT) if (c / BASE_PROJECT).exists() else read(Path(root) / ".uak/PROJECT.md") if root else "")
    presence = num(cfg.get("Presence-Seconds"), PRESENCE)
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
                 next=r.get("Next", ""), away=num(r.get("Away")), outside=r.get("Integrated-Outside") == "yes",
                 participants=r.get("Participants", ""), harnesses=harnesses(c, tid))
        if t["state"] == "REVIEW":
            lease_s = review_lease(project)
            t["sub"] = review_substate(c, tid, r, now, lease_s)
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
        elif now - last <= presence:
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

    tokens = {"total": 0, "by_task": {}, "by_harness": {}, "by_scope": {}, "by_model": {}, "by_kind": {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}}
    for f in (c / "tokens").glob("*.md"):
        for p in rows(read(f)):
            if len(p) >= 9 and p[5].isdigit():
                t = sum(num(x) for x in p[5:9])
                tokens["total"] += t
                for key, val in (("by_task", p[0]), ("by_harness", p[1]), ("by_scope", p[3]), ("by_model", p[2])):
                    tokens[key][val] = tokens[key].get(val, 0) + t
                for key, val in zip(("input", "cache_write", "cache_read", "output"), p[5:9]):
                    tokens["by_kind"][key] += num(val)

    states = {}
    for t in tasks.values():
        states[t["state"]] = states.get(t["state"], 0) + 1
    live = [t for t in tasks.values() if t["state"] != "CANCELLED"]
    weight = {"INTEGRATED": 1.0, "REVIEW": 0.8, "CLAIMED": 0.4, "BLOCKED": 0.3}
    progress = {"done": round(100 * states.get("INTEGRATED", 0) / max(1, len(live))),
                "weighted": round(100 * sum(weight.get(t["state"], 0) for t in live) / max(1, len(live))),
                "total": len(live), "states": states,
                "outside": sum(1 for t in live if t["state"] == "INTEGRATED" and t.get("outside"))}
    freeze = num(cfg.get("Freeze-Epoch"))
    # The stories: every task that is not closed, plus the last TL_EMBED_INTEGRATED closed ones (by last move), compact.
    # Why bounded: a busy repo has 100+ tasks and data.js is re-read every refresh; older stories stay in `uak timeline ID`.
    ctx = tl_ctx(c, msgs, None)
    recs = {}
    for f in (c / "tasks").glob("*.md"):
        r = fields(read(f))
        recs[r.get("ID", f.stem)] = r
    closed = sorted((t for t in tasks.values() if t["state"] in ("INTEGRATED", "CANCELLED") and t["id"] in recs),
                    key=lambda t: -(t.get("updated") or 0))
    keep = [t["id"] for t in tasks.values() if t["state"] not in ("INTEGRATED", "CANCELLED")] + [t["id"] for t in closed[:TL_EMBED_INTEGRATED]]
    cache, timelines = {}, {}
    for tid in keep:
        timelines[tid] = compact_timeline(timeline(ctx, tid, recs.get(tid, {"State": tasks[tid]["state"], "Owner": tasks[tid].get("owner", "")}), now, root, cache))
    return {"repo": repo, "generated": now, "mode": cfg.get("Mode", ""), "freeze": freeze, "progress": progress,
            "tasks": sorted(tasks.values(), key=lambda t: t["id"]), "agents": agents, "messages": msgs[-600:],
            "reviews": reviews, "locks": locks, "queue": queue, "offers": offers, "blackbox": bb[-400:], "usage": usage,
            "decisions": decisions[-60:], "lessons": lessons[-60:], "tokens": tokens,
            "timelines": timelines, "timeline_bound": {"embedded": len(timelines), "tasks": len(tasks), "closed_kept": TL_EMBED_INTEGRATED}}


# ---- A task's whole story (UAK-120): `uak timeline ID` and the dashboard's card dialog share these functions. ----
TL_EMBED_INTEGRATED = 15   # the page embeds the stories of every open task plus the last N closed ones (bounded data.js)


def tl_history(text):
    """The worklog's `## History` lines: '- epoch | STATE | actor | text [| Harness: h] [| Model: m]'. Harness and
    model are 'unknown' for events written before UAK-118: never a guess."""
    out, started = [], False
    for line in text.replace("\r", "").split("\n"):
        if line.startswith("## History"):
            started = True
            continue
        if not started:
            continue
        m = re.match(r"^- (\d+) \| ([A-Z]+) \| ([^|]*?) \| (.*)$", line)
        if not m:
            continue
        body, harness, model = m.group(4), "unknown", "unknown"
        mm = re.search(r" \| Model: (\S.*)$", body)
        if mm:
            model, body = mm.group(1).strip(), body[:mm.start()]
        mh = re.search(r" \| Harness: (\S.*)$", body)
        if mh:
            harness, body = mh.group(1).strip(), body[:mh.start()]
        out.append({"epoch": int(m.group(1)), "state": m.group(2), "actor": m.group(3).strip(), "text": body.strip(),
                    "harness": harness, "model": model})
    return out


def tl_ctx(c, msgs, decisions=None):
    """Everything a story needs that is not per task, read once: worklog histories by task, messages, DECISIONS rows,
    the ledger by task, tokens by task, the backlog's amendments."""
    c = Path(c)
    wl = {}
    for f in sorted((c / "worklog").glob("*.md")):
        text = read(f)
        m = re.search(r"[·]\s*([A-Z][A-Z0-9]*-\d+)\s*$", text.replace("\r", "").split("\n", 1)[0])
        if m:
            wl.setdefault(m.group(1), []).extend(tl_history(text))
    ledger = {}
    for f in sorted((c / "metrics").glob("*.tsv")):
        for line in read(f).replace("\r", "").split("\n"):
            p = line.split("\t")
            if len(p) >= 8 and not p[0].startswith("#") and p[2] not in ("", "-"):
                ledger.setdefault(p[2], []).append({"epoch": num(p[0]), "cmd": p[1], "rc": p[3], "code": p[4], "agent": p[6]})
    decs = []
    for p in rows(read(c / "DECISIONS.md")):
        if p and p[0].isdigit() and len(p) >= 4:
            decs.append({"t": int(p[0]), "kind": p[1], "who": p[2], "text": " | ".join(p[3:])})
    tokens = {}
    for f in (c / "tokens").glob("*.md"):
        for p in rows(read(f)):
            if len(p) >= 9 and p[5].isdigit():
                tokens[p[0]] = tokens.get(p[0], 0) + sum(num(x) for x in p[5:9])
    return {"c": c, "wl": wl, "msgs": msgs, "decs": decs, "ledger": ledger, "tokens": tokens}


def tl_files(root, old, new, cache):
    """Files changed between two tips, when both commits are in the repository at hand; else None."""
    key = (old, new)
    if key in cache:
        return cache[key]
    out = None
    if root and old and new:
        try:
            if all(run_git("cat-file", "-e", x + "^{commit}", cwd=root).returncode == 0 for x in (old, new)):
                r = run_git("diff", "--name-only", old, new, cwd=root)
                if r.returncode == 0:
                    out = [x for x in r.stdout.decode("utf-8", "replace").splitlines() if x]
        except RuntimeError:
            out = None
    cache[key] = out
    return out


def tl_reviews_history(root, tid):
    """The review file is one per task, overwritten: earlier verdicts live in the claims branch history. Returns
    (list of {verdict, sha, reviewer, at}, note); the note says when the history is not at hand."""
    if not root:
        return [], "unavailable: claims read from a directory, not from the claims branch"
    ref = "refs/uak/dash-claims"
    if run_git("rev-parse", "-q", "--verify", ref, cwd=root).returncode != 0:
        return [], "unavailable: the claims branch is not fetched here"
    r = run_git("log", "--format=%H", "-n", "40", ref, "--", "reviews/%s.md" % tid, cwd=root)
    out = []
    for h in r.stdout.decode("utf-8", "replace").split():
        f = fields(run_git("show", "%s:reviews/%s.md" % (h, tid), cwd=root).stdout.decode("utf-8", "replace"))
        if f.get("Verdict"):
            out.append({"verdict": f["Verdict"], "sha": f.get("SHA", ""), "reviewer": f.get("Reviewer", ""), "at": num(f.get("Reviewed"))})
    return out, "git log of reviews/%s.md on the claims branch: %d version%s" % (tid, len(out), "" if len(out) == 1 else "s")


def timeline(ctx, tid, rec, now, root=None, cache=None, history_root=None):
    """The story of one task: lines in order, each with its gap, agent, model and harness; totals from the same lines."""
    cache = {} if cache is None else cache
    c, hist = ctx["c"], sorted(ctx["wl"].get(tid, []), key=lambda e: e["epoch"])
    sess = {h["agent"]: h for h in harnesses(c, tid)}
    lines, seq = [], [0]

    def add(epoch, kind, agent, text, detail="", model="unknown", harness="unknown", sha=""):
        sx = sess.get(agent, {})
        if model == "unknown":
            model = sx.get("model", "unknown")
        if harness == "unknown":
            harness = sx.get("harness", "unknown")
        seq[0] += 1
        lines.append({"epoch": epoch, "kind": kind, "agent": agent or "-", "model": model, "harness": harness, "text": text,
                      "detail": detail, "sha": sha, "_s": seq[0]})

    # Planned and amended, by whom (DECISIONS).
    for d in ctx["decs"]:
        words = re.findall(r"[A-Z][A-Z0-9]*-\d+", d["text"])
        if d["kind"] == "plan" and tid in words and "added" in d["text"][:20]:
            add(d["t"], "plan", d["who"], "planned" + (" with %d other task%s" % (len(words) - 1, "" if len(words) == 2 else "s") if len(words) > 1 else ""))
        elif d["kind"] == "plan --amend" and tid in words:
            add(d["t"], "amend", d["who"], "plan amended", d["text"].split("amended:", 1)[-1].strip()[:600])
        elif d["kind"] == tid:
            add(d["t"], "decision", "-", "decision recorded", (d["who"] + (" | " + d["text"] if d["text"] else ""))[:600])
        elif d["kind"] == "allow" and tid in words:
            add(d["t"], "human", d["who"], "allowed by a human", d["text"][:600])
    msgs = [m for m in ctx["msgs"] if m["task"] == tid or ("task:" + tid) in m["to"]]
    used = set()
    verdict_seen, last_reviewed_sha, rejected_before, prev_actor_claim, last_state, lease_end = [], "", 0, None, "", 0
    rounds = rejects = 0
    red_seen, handed_to = set(), ""
    for e in hist:
        t, st, who = e["text"], e["state"], e["actor"]
        kw = dict(model=e["model"], harness=e["harness"])
        if lease_end and e["epoch"] > lease_end and not t.startswith("heartbeat"):
            add(lease_end, "expired", prev_actor_claim or "-", "lease expired: no heartbeat before the next move", "")
        if not t.startswith("heartbeat"):
            lease_end = 0
        if t.startswith("claim"):
            if prev_actor_claim and who != prev_actor_claim and last_state not in ("AVAILABLE", "CANCELLED", "INTEGRATED", "") and handed_to != who:
                add(e["epoch"], "takeover", who, "took the task over from %s" % prev_actor_claim, **kw)
            add(e["epoch"], "claim", who, "claimed" if not t.startswith("claim resumed") else "claim resumed in a new worktree",
                t.split("next:", 1)[1].strip() if "next:" in t else "", **kw)
            prev_actor_claim, handed_to = who, ""
        elif t.startswith("checkpoint"):
            add(e["epoch"], "checkpoint", who, "checkpoint", t.split("next:", 1)[1].strip() if "next:" in t else "", **kw)
        elif t.startswith("heartbeat"):
            mm = re.search(r"lease until (\d+)", t)
            lease_end = int(mm.group(1)) if mm else 0
            add(e["epoch"], "lease", who, "heartbeat, lease renewed" + (" until %s" % utc(lease_end) if lease_end else ""), **kw)
        elif t.startswith("done;"):
            ev = t.split("evidence: ", 1)[1] if "evidence: " in t else ""
            pr = re.search(r"PR (\S+?)(?:;|$)", t)
            ev = re.sub(r"; reviewer: .*$", "", ev)
            main_ev = ev.split(" · red at ")[0]
            for sha, why in re.findall(r"red at ([0-9a-f]{4,40}): (.*?)(?= · red at |$)", ev):
                if sha in red_seen:
                    continue   # the engine copies every earlier red into each resubmit's evidence: one red per SHA, when first seen
                red_seen.add(sha)
                add(e["epoch"], "red", who, "red recorded at %s" % sha[:7], why.strip(), **kw)
            tip = ""
            for m in msgs:
                if m["kind"] == "review" and m["from"] == who and abs(m["t"] - e["epoch"]) <= 120 and id(m) not in used:
                    mt = re.search(r"SHA ([0-9a-f]{40})", m["text"])
                    if mt:
                        tip = mt.group(1)
                        used.add(id(m))
                        break
            add(e["epoch"], "done", who, "done, PR %s" % (pr.group(1) if pr else "-") + (" · tip %s" % tip[:7] if tip else ""),
                main_ev, sha=tip, **kw)
            if verdict_seen:
                prior = verdict_seen[-1]
                files = tl_files(root, last_reviewed_sha, tip, cache)
                if not tip:
                    fx = "the tip's SHA was not recorded"
                elif files is None:
                    fx = "files changed: not available here (the base repo lacks one of the commits)"
                else:
                    fx = "files changed (%d): %s" % (len(files), ", ".join(files[:12]) + (" …" if len(files) > 12 else ""))
                add(e["epoch"], "tip", who, "new tip %s after %s by %s" % (tip[:7] or "?", "a reject" if prior[0] == "reject" else "an approval", prior[1]),
                    fx, sha=tip, **kw)
        elif t.startswith("review;"):
            mm = re.match(r"review; (approve|reject)(?:; SHA ([0-9a-f]+))?(?:; reviewer (\S+))?", t)
            if not mm:
                add(e["epoch"], "note", who, t[:200], **kw)
                continue
            verdict, sha, rv = mm.group(1), mm.group(2) or "", mm.group(3) or who
            reason = ""
            for m in msgs:
                if m["kind"] == verdict and m["from"] == who and abs(m["t"] - e["epoch"]) <= 120 and (not sha or sha[:7] in m["text"]):
                    reason = re.sub(r"^(Rejected|Approved) SHA \S+ by \S+\s*(?:[·.]\s*)?", "", m["text"]).strip() if verdict == "reject" else ""
                    break
            if verdict == "reject" and not reason:
                reason = "reason not recorded"
            rounds += 1
            rejects += verdict == "reject"
            verdict_seen.append((verdict, rv))
            last_reviewed_sha = sha
            add(e["epoch"], verdict, rv, ("rejected" if verdict == "reject" else "approved") + (" %s" % sha[:7] if sha else "") + (" (round %d)" % rounds),
                reason, sha=sha, **kw)
        elif t.startswith("merge rechazado"):
            add(e["epoch"], "human", who, "merge refused: a human has to merge", t.split(";", 1)[1].strip() if ";" in t else "", **kw)
        elif t.startswith("merge;"):
            add(e["epoch"], "merge", who, "merged by the gate", t.split(";", 1)[1].strip(), **kw)
        elif t.startswith("integrate"):
            unrev = "unreviewed" in t
            add(e["epoch"], "integrate", who, "integrated" + (" · Unreviewed" if unrev else "") + (" · outside the gate" if "outside the gate" in t else ""),
                t.split(";", 1)[1].strip(), **kw)
        elif t.startswith("handover") or t.startswith("handoff"):
            mh = re.search(r"\u2192 (\S+)", t)
            handed_to = mh.group(1) if mh else ""
            add(e["epoch"], "handover", who, t.split(";")[0] + (": " + t.split(";", 1)[1].strip() if ";" in t else ""), **kw)
        elif t.startswith("release"):
            add(e["epoch"], "release", who, "claim released" if st != "CANCELLED" else "cancelled", t.split(";", 1)[1].strip() if ";" in t else "", **kw)
        else:
            add(e["epoch"], "note", who, t[:200], **kw)
        last_state = st
    # CI results pr-sync told, and the human queue.
    refused = [(l["epoch"], l["detail"]) for l in lines if l["kind"] == "human"]
    for m in msgs:
        if m["from"] == "github" and "CI failed: " in m["text"]:
            names = []
            for seg in m["text"].split("CI failed: ")[1:]:
                n = seg.split(" https://")[0].split(" · ")[0]
                if n not in names:
                    names.append(n)
            add(m["t"], "ci", "github", "CI failed: " + ", ".join(names), "told by pr-sync")
        elif m["kind"] == "human" and not any(abs(m["t"] - ep) <= 900 for ep, _ in refused):
            add(m["t"], "human", m["from"], "in the human queue", re.sub(r"^Merge of \S+ in human queue:\s*", "", m["text"]))
    q = fields(read(c / "queue" / (tid + ".md")))
    if q.get("State") == "HUMAN" and q.get("Reason") and not any(l["kind"] == "human" and q["Reason"][:40] in l["detail"] for l in lines):
        add(num(q.get("Updated")), "human", q.get("Owner", "-"), "in the human queue", q["Reason"])
    lease = num(rec.get("Lease-Until"))
    state = rec.get("State", "")
    if state == "CLAIMED" and lease and lease < now:
        add(lease, "expired", rec.get("Owner", "-"), "lease expired and nobody has renewed it")
    lines.sort(key=lambda l: (l["epoch"], l["_s"]))
    prev = None
    for l in lines:
        l["gap"] = 0 if prev is None else max(0, l["epoch"] - prev)
        prev = l["epoch"]
        del l["_s"]
    # Totals. A gap belongs to the state the previous relabeling move put the task in; REVIEW splits like `status` does.
    open_ = state not in ("INTEGRATED", "CANCELLED") and bool(lines)
    points, r_n = [], 0
    for l in lines:
        k = l["kind"]
        if k == "plan" and not any(x["kind"] == "claim" and x["epoch"] < l["epoch"] for x in lines):
            points.append((l["epoch"], ("AVAILABLE", "waiting to be claimed")))
        elif k == "claim":
            points.append((l["epoch"], ("CLAIMED", "")))
        elif k == "done":
            points.append((l["epoch"], ("REVIEW", "waiting for a reviewer" if not r_n else "re-review (round %d)" % (r_n + 1))))
        elif k in ("approve", "reject"):
            r_n += 1
            points.append((l["epoch"], ("REVIEW", "changes requested (round %d)" % r_n if k == "reject" else "approved, waiting for the merge")))
        elif k == "human":
            points.append((l["epoch"], ("REVIEW", "approved, waiting for a human merge")))
        elif k == "ci" and points and (points[-1][1] or ("", ""))[1].startswith("approved"):
            points.append((l["epoch"], ("REVIEW", "approved, CI failed: " + l["text"][11:])))
        elif k == "release":
            points.append((l["epoch"], ("AVAILABLE", "released, waiting to be claimed") if l["text"] == "claim released" else None))
        elif k in ("integrate", "merge"):
            points.append((l["epoch"], None))
    points.append((now if open_ else (lines[-1]["epoch"] if lines else 0), None))
    spans = []
    for (at, lab), (nxt, _) in zip(points, points[1:]):
        if lab is not None and nxt > at:
            spans.append((lab, nxt - at))
    by_state, sums = [], {}
    for lab, secs in spans:
        key = lab
        sums[key] = sums.get(key, 0) + secs
    for key in sums:
        by_state.append({"state": key[0], "sub": key[1], "seconds": sums[key]})
    agents = {}
    for l in lines:
        if l["agent"] in ("-", "github"):
            continue
        a = agents.setdefault(l["agent"], {"agent": l["agent"], "model": "unknown", "harness": "unknown", "moves": 0, "kinds": []})
        a["moves"] += 1
        if l["model"] != "unknown":
            a["model"] = l["model"]
        if l["harness"] != "unknown":
            a["harness"] = l["harness"]
        if l["kind"] not in a["kinds"]:
            a["kinds"].append(l["kind"])
    cmds, errs = {}, []
    for r in ctx["ledger"].get(tid, []):
        cm = cmds.setdefault(r["cmd"], {"command": r["cmd"], "calls": 0, "errors": 0})
        cm["calls"] += 1
        if r["rc"].isdigit() and r["rc"] != "0":
            cm["errors"] += 1
            errs.append({"epoch": r["epoch"], "command": r["cmd"], "exit": int(r["rc"]), "code": r["code"], "agent": r["agent"]})
    hist_note, rev_hist = "not read here: `uak timeline %s` reads it" % tid, []
    if history_root is not None:
        rev_hist, hist_note = tl_reviews_history(history_root or None, tid)
        have = {(l["kind"], l["sha"][:7]) for l in lines if l["kind"] in ("approve", "reject")}
        for rv in rev_hist:
            k = "reject" if rv["verdict"] == "reject" else "approve"
            if (k, rv["sha"][:7]) not in have and rv["at"]:
                lines.append({"epoch": rv["at"], "kind": k, "agent": rv["reviewer"] or "-", "model": "unknown", "harness": "unknown",
                              "text": ("rejected" if k == "reject" else "approved") + " %s (from the reviews file history)" % rv["sha"][:7],
                              "detail": "", "sha": rv["sha"], "gap": 0})
                have.add((k, rv["sha"][:7]))
        lines.sort(key=lambda l: l["epoch"])
        for i, l in enumerate(lines):
            l["gap"] = 0 if i == 0 else max(0, l["epoch"] - lines[i - 1]["epoch"])
    return {"task": tid, "title": rec.get("Title", ""), "state": state or "AVAILABLE", "owner": rec.get("Owner", ""), "now": now,
            "empty": not lines, "open": open_, "lines": lines,
            "totals": {"states": by_state, "seconds": sum(s["seconds"] for s in by_state), "review_rounds": rounds, "rejects": rejects,
                       "agents": sorted(agents.values(), key=lambda a: (-a["moves"], a["agent"])),
                       "models": sorted({a["model"] for a in agents.values() if a["model"] != "unknown"}),
                       "commands": sorted(cmds.values(), key=lambda x: (-x["calls"], x["command"])), "errors": errs,
                       "tokens": ctx["tokens"].get(tid)},
            "sources": {"reviews_history": hist_note}}


def utc(epoch):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(epoch)) if epoch else "-"


def span_words(s):
    if s < 90:
        return "%ds" % s
    if s < 5400:
        return "%dm" % ((s + 30) // 60)
    if s < 172800:
        return "%dh%02dm" % (s // 3600, (s % 3600) // 60)
    return "%dd%02dh" % (s // 86400, (s % 86400) // 3600)


def render_timeline(tl):
    o = ["UAK TIMELINE · %s%s · %s%s" % (tl["task"], " · " + tl["title"] if tl["title"] else "", tl["state"],
                                          " · owner " + tl["owner"] if tl["owner"] else "")]
    if tl["empty"]:
        o.append("no history yet: %s has no plan line, claim or move on the claims branch." % tl["task"])
        return "\n".join(o)
    o.append("  %-19s  %7s  %-10s %-22s %s" % ("time (UTC)", "gap", "move", "agent (model, harness)", ""))
    for l in tl["lines"]:
        who = "%s (%s, %s)" % (l["agent"], l["model"], l["harness"]) if l["agent"] != "-" else "-"
        o.append("  %-19s  %7s  %-10s %s  %s" % (utc(l["epoch"]), "+" + span_words(l["gap"]) if l["gap"] else "", l["kind"], who, l["text"]))
        if l["detail"]:
            o.append("  %s%s" % (" " * 42, l["detail"]))
    t = tl["totals"]
    o.append("totals:")
    cur = None
    for s in t["states"]:
        o.append("  %-10s %-34s %s" % (s["state"] if s["state"] != cur else "", s["sub"], span_words(s["seconds"])))
        cur = s["state"]
    o.append("  in all %s%s" % (span_words(t["seconds"]), " (the open state counts up to now)" if tl["open"] else ""))
    o.append("review rounds: %d (%d rejected)" % (t["review_rounds"], t["rejects"]))
    o.append("agents: " + (" · ".join("%s %s/%s %d moves" % (a["agent"], a["model"], a["harness"], a["moves"]) for a in t["agents"]) or "none"))
    o.append("models: " + (", ".join(t["models"]) or "unknown"))
    o.append("commands: " + (" · ".join("%s %d%s" % (x["command"], x["calls"], " (%d failed)" % x["errors"] if x["errors"] else "")
                                       for x in t["commands"]) or "none in the ledger"))
    for e in t["errors"]:
        o.append("  error: %s exit %d%s by %s" % (e["command"], e["exit"], "" if e["code"] == "-" else " " + e["code"], e["agent"]))
    o.append("tokens: " + ("{:,}".format(t["tokens"]) if t["tokens"] is not None else "not published"))
    o.append("reviews history: " + tl["sources"]["reviews_history"])
    return "\n".join(o)


def compact_timeline(tl, cut=700):
    """The dashboard's copy: arrays, not objects, text bounded."""
    t = tl["totals"]
    def line(l):
        pr = re.search(r"PR (https://\S+?/pull/(\d+))", l["text"]) if l["kind"] == "done" else None
        text = l["text"].replace(pr.group(1), "#" + pr.group(2)) if pr else l["text"]   # the URL goes in a title, not in the flow
        return [l["epoch"], l["kind"], l["agent"], l["model"], l["harness"], text[:300], l["detail"][:cut], l["sha"][:7], pr.group(1) if pr else ""]
    return {"state": tl["state"], "open": tl["open"], "now": tl["now"],
            "lines": [line(l) for l in tl["lines"]],
            "states": [[s["state"], s["sub"], s["seconds"]] for s in t["states"]],
            "agents": [[a["agent"], a["model"], a["harness"], a["moves"], a["kinds"]] for a in t["agents"]],
            "rounds": t["review_rounds"], "rejects": t["rejects"], "tokens": t["tokens"],
            "commands": [[x["command"], x["calls"], x["errors"]] for x in t["commands"][:8]], "errors": len(t["errors"]),
            "history": tl["sources"]["reviews_history"]}


LOOK_TAG = '<html lang="en" data-pal="clasico">'
FONT_FILES = ("Inter.woff2", "JetBrainsMono.woff2", "OFL.txt")


def look_default(out):
    """The palette a page starts with, before the viewer chooses one (the choice stays in their browser).
    Lavanda in a checkout that never had a dashboard; Clasico, the colours of v6.8, where its output directory already
    exists, so nobody's panel changes colour by itself. The answer is kept in the directory (`palette`) once given."""
    out = Path(out)
    mark = out / "palette"
    try:
        saved = mark.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[a-z]+", saved):
            return saved
    except OSError:
        pass
    return "clasico" if out.exists() else "lavanda"


def page_html(template, pal):
    """dash.html as served: the default palette written into the <html> tag."""
    html = Path(template).read_text(encoding="utf-8").replace('content="dev"', 'content="%s"' % page_version(template), 1)
    return html.replace(LOOK_TAG, LOOK_TAG.replace("clasico", pal), 1) if re.fullmatch(r"[a-z]+", pal) else html


def main():
    ap = argparse.ArgumentParser(prog="uak dash")
    ap.add_argument("--watch", nargs="?", const=20, type=int, default=0)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--claims")
    ap.add_argument("--fresh", action="store_true", help="accepted; the dashboard and timeline always fetch")
    ap.add_argument("--timeline", metavar="ID")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.timeline:
        return timeline_main(a)
    root = git("rev-parse", "--show-toplevel").decode().strip()
    common = Path(root) / git("rev-parse", "--git-common-dir", cwd=root).decode().strip()
    out = Path(a.out) if a.out else common.resolve() / "uak-dash"
    pal = look_default(out)
    out.mkdir(parents=True, exist_ok=True)
    if not (out / "palette").exists():
        (out / "palette").write_text(pal + "\n", encoding="utf-8")
    tpl = Path(__file__).with_name("dash.html")
    (out / "index.html").write_text(page_html(tpl, pal), encoding="utf-8")
    shutil.copyfile(tpl.with_name("workspace.js"), out / "workspace.js")
    fonts = tpl.with_name("fonts")
    if fonts.is_dir():
        (out / "fonts").mkdir(exist_ok=True)
        for name in FONT_FILES:
            if (fonts / name).is_file():
                shutil.copyfile(fonts / name, out / "fonts" / name)
    repo = project_name(root)
    refresh = a.watch or 20
    opened = False
    while True:
        tmp = None
        try:
            c, backlog = snapshot(root, a.claims)
            tmp = None if a.claims else c
            data = build(Path(c), backlog, repo, root)
            data["refresh"] = refresh
            data["page"] = page_version(tpl)
            if (out / "index.html").read_text(encoding="utf-8") != page_html(tpl, pal):
                (out / "index.html").write_text(page_html(tpl, pal), encoding="utf-8")
            data["live_url"] = (project_live_url(read(Path(root) / ".uak/PROJECT.md")) if a.claims
                                else base_live_url(root))
            commits = None if a.claims else base_commits(root)
            if commits is not None:
                data["commits"] = commits
            data["mode"] = data.get("mode") or (project_mode(read(Path(root) / ".uak/PROJECT.md")) if a.claims
                                                else base_mode(root))
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


def timeline_main(a):
    """`uak timeline ID [--json] [--claims DIR]`: one task's story, read-only from the claims branch."""
    tid = a.timeline
    if not re.match(r"^[A-Z][A-Z0-9]*-\d+$", tid):
        print("timeline: %s is not a task ID" % tid, file=sys.stderr)
        return 2
    top = run_git("rev-parse", "--show-toplevel")
    root = top.stdout.decode("utf-8", "replace").strip() if top.returncode == 0 else None
    if not root and not a.claims:
        print("timeline: not a Git repository", file=sys.stderr)
        return 2
    tmp = None
    try:
        if not a.claims and run_git("ls-remote", "--exit-code", "--heads", os.environ.get("UAK_REMOTE", "origin"), "claims", cwd=root).returncode != 0:
            print("timeline: no remote claims branch yet", file=sys.stderr)
            return 2
        c, backlog = snapshot(root or ".", a.claims)
        tmp = None if a.claims else c
        c = Path(c)
        now = int(os.environ.get("UAK_NOW") or time.time())
        msgs = [{"n": num(p[0]), "t": num(p[1]), "from": p[2], "to": [x for x in p[3].split(",") if x], "kind": p[4],
                 "task": "" if p[5] == "-" else p[5], "text": p[6]} for p in rows(read(c / "inbox/log.md"), 7) if len(p) >= 7]
        rec = fields(read(c / "tasks" / (tid + ".md")))
        plan = backlog_tasks(backlog + "\n" + read(c / "backlog/TASKS.md")).get(tid, {})
        rec = dict(rec, Title=plan.get("title", ""))
        ctx = tl_ctx(c, msgs)
        if not rec.get("ID") and not plan and tid not in ctx["wl"] and not any(tid in d["text"] for d in ctx["decs"]):
            print("timeline: %s is not on the claims branch" % tid, file=sys.stderr)
            return 1
        tl = timeline(ctx, tid, rec, now, root, {}, history_root=(False if a.claims else root))
        print(json.dumps(tl, ensure_ascii=False, indent=1) if a.json else render_timeline(tl))
        return 0
    except RuntimeError as exc:
        print("timeline: %s" % exc, file=sys.stderr)
        return 1
    finally:
        if tmp:
            shutil.rmtree(str(tmp), ignore_errors=True)


def run():
    try:
        return main()
    except RuntimeError as exc:  # a git failure or timeout before the loop: one line, not a traceback
        print(f"DASH_ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    import ledger_py  # UAK-136: closes this command's ledger line
    sys.exit(ledger_py.run(run))
