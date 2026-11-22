#!/usr/bin/env python3
"""UAK-119: a task in REVIEW says what it waits for and for how long. One derived sub-state, computed from claims (no new
stored state): waiting for a reviewer, in review by NAME, changes requested (round N), re-review (round N), approved
waiting for CI, approved waiting for a human merge (with the queue reason), approved waiting for the owner to merge.
`uak status`, `uak status --task ID` print it with the time spent in it; the dashboard data carries the same words
(lib/dash.py) and groups REVIEW cards by it. STATE.md keeps its format. Real Git, local bare remotes.
Why (the human, 2026-11-21): "a veces esta en In review por horas y visualmente no sabes si hubo un rejected, esta en CI
o lo que sea"."""
import argparse
import concurrent.futures
import json
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config
from test_reviewer_next import to_review, three, reviewer_env

T0 = 1000010


def tip(r, f):
    return r.g(f.worktrees[0], "rev-parse", "HEAD").stdout.strip()


def review(r, f, verdict, now, extra=()):
    return r.run([r.bash, ".uak/bin/uak", "review", "HACK-001", "--sha", tip(r, f), "--verdict", verdict, *extra],
                 cwd=f.clones[2], env=reviewer_env(UAK_NOW=str(now)))


def task_line(r, f, now):
    out = r.run([r.bash, ".uak/bin/uak", "status", "--task", "HACK-001", "--full"], cwd=f.worktrees[0],
                env={"UAK_AGENT": "agent-1", "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_DEDUPE": "off"}).stdout
    got = [l for l in out.splitlines() if l.startswith("Review: ")]
    expect(len(got) == 1, "one Review: line in status --task: " + out)
    # The Python twin (lib/dash.py) says the same words, the same time and the same late mark, word for word.
    sub = [x for x in dash_data(r, f, now)["tasks"] if x["id"] == "HACK-001"][0].get("sub") or {}
    ago = now - sub.get("since", now)
    expect(got[0].startswith("Review: " + sub.get("text", "?") + " · "), "bash and python words differ: %s | %s" % (got[0], sub))
    expect(("OVER the review lease" in got[0]) == bool(sub.get("late")), "late mark differs: %s | %s" % (got[0], sub))
    expect(got[0].count(" reject") == (1 if sub.get("rejects") else 0) or sub.get("rejects", 0) > 1, "rejects differ: %s | %s" % (got[0], sub))
    expect(" · %s" % age_words(ago) in got[0], "time differs: %s | %s s" % (got[0], ago))
    return got[0], out


def age_words(s):
    if s < 90:
        return "%d s" % s
    if s < 5400:
        return "%d min" % ((s + 30) // 60)
    if s < 172800:
        return "%d h %02d min" % (s // 3600, (s % 3600) // 60)
    return "%d d %02d h" % (s // 86400, (s % 86400) // 3600)


def setup(r, name, **cfg):
    f = three(r, name, "agent-3")
    config(f, **cfg)
    to_review(r, f, now=T0)
    return f


def push_again(r, f, now):
    w = f.worktrees[0]
    (w / "src" / "again.txt").write_text("a fix\n", encoding="utf-8")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", "HACK-001: a fix")
    r.g(w, "push", "-q", "origin", f.branches[0])
    f.hack(0, "done", "HACK-001", "--pr", "https://example.invalid/pull/1", "--evidence", "a fix", "--no-red", "fixture", now=now)


def waits_for_a_reviewer(r):
    f = setup(r, "rs-wait")
    line, _ = task_line(r, f, T0 + 120)
    expect(line.startswith("Review: waiting for a reviewer · 2 min"), line)
    return line


def substate_after_a_reject(r):
    f = setup(r, "rs-reject")
    res = review(r, f, "reject", T0 + 600, ["--note", "wrong rounding"])
    expect(res.returncode == 0, "review: " + res.stdout + res.stderr)
    line, out = task_line(r, f, T0 + 600 + 300)
    expect(line.startswith("Review: changes requested (round 1) · 5 min · 1 reject"), line)
    return line


def substate_after_a_new_tip(r):
    f = setup(r, "rs-newtip")
    review(r, f, "reject", T0 + 600)
    push_again(r, f, T0 + 900)
    line, _ = task_line(r, f, T0 + 900 + 60)
    expect(line.startswith("Review: re-review (round 2) · 60 s · 1 reject"), line)
    review(r, f, "reject", T0 + 1200)
    line, _ = task_line(r, f, T0 + 1200)
    expect(line.startswith("Review: changes requested (round 2) · 0 s · 2 rejects"), line)
    return line


def in_review_by_name(r):
    f = setup(r, "rs-lock")
    res = review(r, f, "approve", T0 + 100, ["--start"])
    expect(res.returncode == 0, "start: " + res.stdout + res.stderr)
    line, _ = task_line(r, f, T0 + 160)
    expect(line.startswith("Review: in review by agent-3 · 60 s"), line)
    return line


def approved_waiting_for_the_owner(r):
    f = setup(r, "rs-owner")
    review(r, f, "approve", T0 + 300)
    line, _ = task_line(r, f, T0 + 300 + 7200)
    expect(line.startswith("Review: approved, waiting for the owner to merge · 2 h 00 min"), line)
    return line


def approved_waiting_for_a_human_names_the_reason(r):
    f = setup(r, "rs-human")
    config(f, Autonomy="no")
    review(r, f, "approve", T0 + 300)
    res = f.hack(0, "merge", "HACK-001", now=T0 + 400, allowed=None)
    expect("MERGE_HUMAN" in res.stdout, "merge goes to the human queue: " + res.stdout + res.stderr)
    line, _ = task_line(r, f, T0 + 460)
    expect(line.startswith("Review: approved, waiting for a human merge: Autonomy revoked or not explicitly authorized · 60 s"), line)
    return line


def claims_edit(r, f, name, change):
    """Write to the claims branch the way pr-sync does (a message from github), with plain Git."""
    work = Path(f.base) / ("claims-edit-" + name)
    r.g(f.base, "clone", "-q", "--branch", "claims", str(f.remote), str(work))
    change(work)
    r.g(work, "add", "-A")
    r.g(work, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "pr-sync fixture")
    r.g(work, "push", "-q", "origin", "claims")


def github_says(f, r, at, text, name="m"):
    def change(work):
        log = work / "inbox" / "log.md"
        body = log.read_text(encoding="utf-8") if log.exists() else ""
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(body + "- 900 | %d | github | task:HACK-001 | request | HACK-001 | %s\n" % (at, text), encoding="utf-8")
    claims_edit(r, f, name, change)


def approved_ci_failed_names_the_check(r):
    f = setup(r, "rs-ci")
    review(r, f, "approve", T0 + 300)
    github_says(f, r, T0 + 400, "GitHub: #1 CI failed: lint https://example.invalid/runs/1 · read it: gh run view 1 --log-failed · #1 CI failed: unit (linux) https://example.invalid/runs/2", "a")
    line, _ = task_line(r, f, T0 + 400 + 600)
    expect(line.startswith("Review: approved, CI failed: lint +1 · 10 min"), line)
    expect("waiting for CI" not in line, "there is no waiting-for-CI state: pr-sync knows failures only")
    return line


def a_failure_of_an_older_tip_does_not_count(r):
    f = setup(r, "rs-ci-old")
    review(r, f, "approve", T0 + 300)
    github_says(f, r, T0 + 400, "GitHub: #1 CI failed: lint https://example.invalid/runs/1", "a")
    push_again(r, f, T0 + 900)
    review(r, f, "approve", T0 + 1000)
    line, _ = task_line(r, f, T0 + 1100)
    expect(line.startswith("Review: approved, waiting for the owner to merge · 100 s") or line.startswith("Review: approved, waiting for the owner to merge · 2 min"), line)
    github_says(f, r, T0 + 1050, "GitHub: #1 CI failed: lint https://example.invalid/runs/3", "b")
    line, _ = task_line(r, f, T0 + 1100)
    expect(line.startswith("Review: approved, CI failed: lint · 50 s"), line)
    return line


def time_in_substate_and_the_lease_mark(r):
    f = setup(r, "rs-time")
    # lease is Review-Lease-Seconds (default 4 x lease): far past it the line says so.
    line, _ = task_line(r, f, T0 + 30 * 3600)
    expect(re.search(r"Review: waiting for a reviewer · 30 h 00 min · OVER the review lease", line), line)
    out = r.run([r.bash, ".uak/bin/uak", "status", "--full"], cwd=f.worktrees[0],
                env={"UAK_AGENT": "agent-1", "UAK_NOW": str(T0 + 30 * 3600), "UAK_REMOTE": "origin", "UAK_DEDUPE": "off"}).stdout
    expect("HACK-001 | waiting for a reviewer · 30 h 00 min" in out, "the status list: " + out)
    return "status and status --task agree"


def status_keeps_its_shape(r):
    f = setup(r, "rs-shape")
    out = r.run([r.bash, ".uak/bin/uak", "status", "--full"], cwd=f.worktrees[0],
                env={"UAK_AGENT": "agent-1", "UAK_NOW": str(T0 + 60), "UAK_REMOTE": "origin", "UAK_DEDUPE": "off"}).stdout
    lines = out.splitlines()
    i = lines.index("Claims (max 12; use --task ID):")
    expect(re.match(r"^HACK-001 \| REVIEW \| agent-1 \| active \| until \d+$", lines[i + 1]), "claims rows unchanged: " + lines[i + 1])
    expect(lines[i + 2].startswith("Review (") and lines[i + 3].startswith("HACK-001 | waiting"), "review section after the claims: " + out)
    expect(any(l.startswith("Smoke:") for l in lines[i + 4:]), "Smoke line still there")
    # STATE.md keeps its format: no sub-state in it.
    expect("waiting for a reviewer" not in f.show("STATE.md"), "STATE.md untouched")
    return "claims rows and STATE.md unchanged"


def dash_data(r, f, now):
    out = f.base / "dash"
    res = r.run([r.bash, ".uak/bin/uak", "dash", "--out", str(out)], cwd=f.worktrees[0],
                env={"UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_AGENT": "agent-1"}, allowed=None)
    expect(res.returncode == 0, "dash: " + res.stdout + res.stderr)
    body = (out / "data.js").read_text(encoding="utf-8")
    return json.loads(body[len("window.UAK_DATA = "):].rstrip().rstrip(";"))


def dashboard_data_groups_by_substate(r):
    f = setup(r, "rs-dash")
    review(r, f, "reject", T0 + 600)
    push_again(r, f, T0 + 900)
    now = T0 + 900 + 4 * 3600 * 4 + 5
    data = dash_data(r, f, now)
    t = [x for x in data["tasks"] if x["id"] == "HACK-001"][0]
    sub = t.get("sub") or {}
    expect(sub.get("kind") == "rereview" and sub.get("text") == "re-review (round 2)", "sub: %s" % sub)
    expect(sub.get("rejects") == 1 and sub.get("rounds") == 1 and sub.get("since") == T0 + 900, "badge numbers: %s" % sub)
    expect(sub.get("late") is True, "late after the review lease: %s" % sub)
    # the words are the ones `uak status --task` prints
    line, _ = task_line(r, f, now)
    expect(line.startswith("Review: " + sub["text"] + " · "), "same words in status and dash: %s | %s" % (line, sub))
    expect("author agent-1" in t.get("participants", ""), "participants carried: %s" % t.get("participants"))
    html = (Path(__file__).resolve().parents[1] / "bin/lib/dash.html").read_text(encoding="utf-8")
    expect("reviewGroups" in html and "sub.late" in html, "the page groups REVIEW by sub-state")
    expect('"waiting" || t.sub.kind === "rereview"' in html and "waiting for CI" not in html, "the tile counts tasks waiting for a reviewer")
    return sub["text"]


def surfaces(r, f, now, cache=False):
    """`uak status --task`, `uak board` and `uak --json status` on the same claims at the same clock."""
    env = {"UAK_AGENT": "agent-1", "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_DEDUPE": "off"}
    if cache:
        env["UAK_READ_CACHE"] = "on"
    line, _ = task_line(r, f, now)
    board = r.run([r.bash, ".uak/bin/board"], cwd=f.worktrees[0], env=env).stdout
    rows = [l for l in board.splitlines() if " HACK-001 " in l]
    expect(len(rows) == 1, "one board row for HACK-001: " + board)
    res = r.run([r.bash, ".uak/bin/uak", "--json", "status", "--full"], cwd=f.worktrees[0], env=env)
    doc = json.loads(res.stdout)
    task = [t for t in doc["tasks"] if t["id"] == "HACK-001"][0]
    return line[len("Review: "):], rows[0], task, doc


def board_prints_the_substate(r):
    f = setup(r, "rs-board")
    now = T0 + 30 * 3600
    words, row, _, _ = surfaces(r, f, now)
    expect(row.startswith("REVIEW") and row.endswith("[" + words + "]"), "board row ends with the status words: %s | %s" % (row, words))
    expect("waiting for a reviewer · 30 h 00 min · OVER the review lease" in row, row)
    review(r, f, "reject", T0 + 600)
    push_again(r, f, T0 + 900)
    words, row, _, _ = surfaces(r, f, T0 + 900 + 60)
    expect(row.endswith("[re-review (round 2) · 60 s · 1 reject]"), "after a reject and a new tip: " + row)
    md = r.run([r.bash, ".uak/bin/board", "--md"], cwd=f.worktrees[0], env={"UAK_NOW": str(T0 + 960), "UAK_REMOTE": "origin"}).stdout
    expect(any("| HACK-001 |" in l and "[re-review (round 2)" in l for l in md.splitlines()), "the table too: " + md)
    return row


def json_status_has_the_substate(r):
    f = setup(r, "rs-json")
    _, _, task, doc = surfaces(r, f, T0 + 90)
    expect(task["review_substate"] == "waiting for a reviewer" and task["review_round"] == 0, "keys: %s" % task)
    expect(isinstance(task["review_substate_since"], int) and task["review_substate_since"] > 0, "since is an epoch: %s" % task)
    # every existing key keeps its name and type; a task not in REVIEW carries none of the new ones
    old = {"id": str, "state": str, "owner": str, "lease_until": int, "expired": bool}
    for k, typ in old.items():
        expect(type(task[k]) is typ, "%s keeps its type: %r" % (k, task[k]))
    others = [t for t in doc["tasks"] if t["state"] != "REVIEW"]
    expect(others and all("review_substate" not in t for t in others), "only REVIEW tasks carry it")
    for k in ("v", "cmd", "id", "ok", "exit", "result", "code", "message", "state", "next", "stdout", "stderr", "tasks"):
        expect(k in doc, "envelope key %s" % k)
    return "keys added"


def three_surfaces_agree(r):
    f = setup(r, "rs-three")
    review(r, f, "reject", T0 + 600)
    push_again(r, f, T0 + 900)
    now = T0 + 900 + 4 * 3600 * 4 + 5
    for n, cache in enumerate((False, True, True)):   # the last read is served from the cache
        words, row, task, doc = surfaces(r, f, now, cache)
        expect(n < 2 or "claims_age" in doc, "the third read came from the cache: %s" % sorted(doc))
        sub = [x for x in dash_data(r, f, now)["tasks"] if x["id"] == "HACK-001"][0]["sub"]
        expect(task["review_substate"] == sub["text"] == "re-review (round 2)", "json and dashboard words: %s | %s" % (task, sub))
        expect(task["review_substate_since"] == sub["since"] == T0 + 900, "same start: %s | %s" % (task, sub))
        expect(task["review_round"] == sub["rounds"] == 1, "same round: %s | %s" % (task, sub))
        expect(words.startswith(task["review_substate"] + " · " + age_words(now - task["review_substate_since"])), "status words and time: " + words)
        expect(row.endswith("[" + words + "]"), "board says what status says: %s | %s" % (row, words))
    return words


def marks(r, f, now, **extra):
    """The OVER mark as `status --task`, `board`, `--json status` (its stdout) and the dashboard data show it, UAK-145."""
    env = {"UAK_AGENT": "agent-1", "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_DEDUPE": "off", **extra}
    run = lambda *a: r.run([r.bash, *a], cwd=f.worktrees[0], env=env, allowed=None)
    task = run(".uak/bin/uak", "status", "--task", "HACK-001", "--full")
    board = run(".uak/bin/board")
    js = run(".uak/bin/uak", "--json", "status", "--full")
    dash = r.run([r.bash, ".uak/bin/uak", "dash", "--out", str(f.base / "dash-marks")], cwd=f.worktrees[0], env=env, allowed=None)
    expect(task.returncode == 0 and board.returncode == 0 and js.returncode == 0 and dash.returncode == 0,
           "all four surfaces run: %s %s %s %s" % (task.stderr, board.stderr, js.stderr, dash.stderr))
    body = (f.base / "dash-marks" / "data.js").read_text(encoding="utf-8")
    sub = [x for x in json.loads(body[len("window.UAK_DATA = "):].rstrip().rstrip(";"))["tasks"] if x["id"] == "HACK-001"][0]["sub"]
    rows = [l for l in board.stdout.splitlines() if " HACK-001 " in l]
    expect(len(rows) == 1, "one board row: " + board.stdout)
    out = json.loads(js.stdout)["stdout"]
    jl = [l for l in (out.splitlines() if isinstance(out, str) else out) if l.startswith("HACK-001 | ") and " · " in l]
    expect(len(jl) == 1, "one json status line: " + js.stdout)
    return {"status": "OVER the review lease" in task.stdout, "board": "OVER the review lease" in rows[0],
            "json": "OVER the review lease" in jl[0], "dash": bool(sub.get("late"))}


def board_and_status_agree_on_the_lease_env(r):
    f = setup(r, "rs-env")
    now = T0 + 3 * 3600
    # (the dashboard data has its own default lease and no env var: lib/dash.py is not part of UAK-145, so it is left out here)
    got = marks(r, f, now)
    expect(got["status"] and got["board"] and got["json"], "3 h is over the default review lease (2 h): %s" % got)
    got = marks(r, f, now, UAK_LEASE_SECONDS="3600")   # review lease 4 x 3600 = 4 h
    expect(not (got["status"] or got["board"] or got["json"]), "UAK_LEASE_SECONDS=3600: not over on status, board, json: %s" % got)
    for bad in ("0", "abc", "-5"):
        env = {"UAK_AGENT": "agent-1", "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_DEDUPE": "off", "UAK_LEASE_SECONDS": bad}
        res = r.run([r.bash, ".uak/bin/board"], cwd=f.worktrees[0], env=env, allowed=None)
        expect(res.returncode == 0 and "HACK-001" in res.stdout and "waiting for a reviewer" in res.stdout, "board survives UAK_LEASE_SECONDS=%s: %s" % (bad, res.stdout + res.stderr))
    return str(got)


def board_reads_the_lease_of_the_config_ref_not_the_checkout(r):
    f = setup(r, "rs-ref")
    config(f, Review_Lease_Seconds="20000")   # main (the config ref) moves on; the worktree's PROJECT.md does not
    expect("Review-Lease-Seconds" not in (f.worktrees[0] / ".uak/PROJECT.md").read_text(encoding="utf-8"), "the checkout lags the config ref")
    got = marks(r, f, T0 + 3 * 3600)    # 10800 s: over the checkout's default 7200, under the ref's 20000
    expect(set(got.values()) == {False}, "the ref's Review-Lease-Seconds decides on every surface: %s" % got)
    got = marks(r, f, T0 + 6 * 3600)    # 21600 s: over 20000
    expect(set(got.values()) == {True}, "and over it when it is: %s" % got)
    return str(got)


def dash_late_agrees_with_the_over_mark(r):
    """UAK-147: the dashboard's late flag is the OVER mark of status, board and json, by the same lease rule."""
    f = setup(r, "rs-dash-lease")
    got = marks(r, f, T0 + 9000)   # between 7200 s (2 h) and 10800 s (3 h) in a default setup
    expect(set(got.values()) == {True}, "9000 s in REVIEW is over the default review lease on every surface: %s" % got)
    got = marks(r, f, T0 + 12000, UAK_LEASE_SECONDS="3600")   # review lease 14400 s
    expect(set(got.values()) == {False}, "UAK_LEASE_SECONDS=3600: 12000 s is not over on any surface: %s" % got)
    got = marks(r, f, T0 + 15000, UAK_LEASE_SECONDS="3600")
    expect(set(got.values()) == {True}, "and 15000 s is: %s" % got)
    return str(got)


def dash_late_agrees_under_marathon_and_explicit_leases(r):
    f = setup(r, "rs-dash-marathon", Mode="marathon")
    got = marks(r, f, T0 + 9000)   # Mode: marathon changes no lease default: 1800 s, review 7200 s
    expect(set(got.values()) == {True}, "marathon: 9000 s is over the review lease on every surface: %s" % got)
    config(f, Mode="marathon", Lease_Seconds="3600", Review_Lease_Seconds="20000")
    got = marks(r, f, T0 + 15000)
    expect(set(got.values()) == {False}, "Review-Lease-Seconds wins on every surface: %s" % got)
    config(f, Mode="marathon", Lease_Seconds="3600")
    got = marks(r, f, T0 + 15000)
    expect(set(got.values()) == {True}, "Lease-Seconds 3600: review lease 14400 s, 15000 s is over: %s" % got)
    return str(got)


def a_tab_in_free_text_keeps_the_record(r):
    f = setup(r, "rs-tab-q")
    config(f, Autonomy="no")
    review(r, f, "approve", T0 + 300)
    res = f.hack(0, "merge", "HACK-001", now=T0 + 400, allowed=None)
    expect("MERGE_HUMAN" in res.stdout, "merge goes to the human queue: " + res.stdout + res.stderr)

    def tabbed(work):
        q = work / "queue" / "HACK-001.md"
        q.write_text(re.sub(r"(?m)^Reason: .*$", "Reason: wait\tfor\tthe \\ \"human\" \u00e9", q.read_text(encoding="utf-8")), encoding="utf-8")
    claims_edit(r, f, "tab-q", tabbed)
    now = T0 + 460
    env = {"UAK_AGENT": "agent-1", "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_DEDUPE": "off"}
    js = r.run([r.bash, ".uak/bin/uak", "--json", "status", "--full"], cwd=f.worktrees[0], env=env)
    task = [t for t in json.loads(js.stdout)["tasks"] if t["id"] == "HACK-001"][0]
    expect(task["review_substate_since"] == T0 + 400 and task["review_round"] == 1, "since and round survive a tab in the reason: %s" % task)
    expect(task["review_substate"].startswith("approved, waiting for a human merge: wait") and "\t" not in task["review_substate"], "words: %r" % task["review_substate"])
    board = r.run([r.bash, ".uak/bin/board"], cwd=f.worktrees[0], env=env).stdout
    rows = [l for l in board.splitlines() if " HACK-001 " in l]
    expect(len(rows) == 1 and "\t" not in rows[0] and "wait for the" in rows[0] and rows[0].endswith("60 s]"), "board row: %r" % rows)
    return task["review_substate"]


def a_tab_in_a_reviewer_name_keeps_the_record(r):
    f = setup(r, "rs-tab-r")
    res = review(r, f, "approve", T0 + 100, ["--start"])
    expect(res.returncode == 0, "start: " + res.stdout + res.stderr)

    def tabbed(work):
        q = work / "reviews" / "HACK-001.reviewing"
        q.write_text(re.sub(r"(?m)^Reviewer: .*$", "Reviewer: agent\t3 \"q\" \u00e9", q.read_text(encoding="utf-8")), encoding="utf-8")
    claims_edit(r, f, "tab-r", tabbed)
    env = {"UAK_AGENT": "agent-1", "UAK_NOW": str(T0 + 160), "UAK_REMOTE": "origin", "UAK_DEDUPE": "off"}
    js = r.run([r.bash, ".uak/bin/uak", "--json", "status", "--full"], cwd=f.worktrees[0], env=env)
    task = [t for t in json.loads(js.stdout)["tasks"] if t["id"] == "HACK-001"][0]
    expect(task["review_substate_since"] == T0 + 100, "since survives a tab in the name: %s" % task)
    board = r.run([r.bash, ".uak/bin/board"], cwd=f.worktrees[0], env=env).stdout
    rows = [l for l in board.splitlines() if " HACK-001 " in l]
    expect(len(rows) == 1 and "\t" not in rows[0] and "in review by agent 3" in rows[0] and rows[0].endswith("60 s]"), "board row: %r" % rows)
    return task["review_substate"]


TESTS = [waits_for_a_reviewer, substate_after_a_reject, substate_after_a_new_tip, in_review_by_name,
         approved_waiting_for_the_owner, approved_waiting_for_a_human_names_the_reason, approved_ci_failed_names_the_check, a_failure_of_an_older_tip_does_not_count,
         time_in_substate_and_the_lease_mark, status_keeps_its_shape, dashboard_data_groups_by_substate,
         board_prints_the_substate, json_status_has_the_substate, three_surfaces_agree,
         board_and_status_agree_on_the_lease_env, board_reads_the_lease_of_the_config_ref_not_the_checkout,
         dash_late_agrees_with_the_over_mark, dash_late_agrees_under_marathon_and_explicit_leases,
         a_tab_in_free_text_keeps_the_record, a_tab_in_a_reviewer_name_keeps_the_record]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-substates-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        selected = [t for t in TESTS if not args.case or t.__name__ in args.case]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, selected))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("REVIEW_SUBSTATES_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
