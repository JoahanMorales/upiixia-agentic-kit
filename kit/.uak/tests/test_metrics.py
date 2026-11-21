#!/usr/bin/env python3
"""UAK-117: `uak metrics` prints every speed number next to its instability number, from claims only.
Why (audit of v6.5.0, docs/audit-2026-11.md section 4): `stats` counts events but pairs no speed with its cost and has no
per-command error rate or duration. A synthetic claims checkout (--claims DIR, in a folder with a space and an accent)."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from test_hack import expect, resolve_binary

T0 = 1800000000
DAY = 86400


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def task(c, tid, state="INTEGRATED", hist=(), extra=""):
    put(c / "tasks" / (tid + ".md"), "# %s\nID: %s\nState: %s\nOwner: a-1\nUpdated: %d\n%s" % (tid, tid, state, T0, extra))
    lines = "\n".join("- %d | %s | %s | %s | Harness: claude-code | Model: m1" % h for h in hist)
    put(c / "worklog" / ("WL-1-a-1-%s-hack.x.md" % tid), "# worklog/WL-1-a-1-%s-hack.x.md · %s\n\n## History\n%s\n" % (tid, tid, lines))


def claims(tmp, n_ledger=30):
    c = Path(tmp) / "claims é dir"
    # UAK-001: rejected once, approved, merged by the gate. UAK-002: straight through, integrated by hand, later reopened.
    task(c, "UAK-001", hist=[(T0, "CLAIMED", "a-1", "claim"), (T0 + 3600, "REVIEW", "a-1", "done; PR x"),
                             (T0 + 4200, "REVIEW", "r-1", "review; reject; SHA abcdef0123; reviewer r-1"),
                             (T0 + 5400, "REVIEW", "a-1", "done; PR x"),
                             (T0 + 6000, "REVIEW", "r-1", "review; approve; SHA 1234567abc; reviewer r-1"),
                             (T0 + 7200, "INTEGRATED", "a-2", "merge; smoke PASS")])
    task(c, "UAK-002", hist=[(T0, "CLAIMED", "a-1", "claim"), (T0 + 7200, "REVIEW", "a-1", "done"),
                             (T0 + 7300, "REVIEW", "r-1", "review; approve; SHA 7654321abc; reviewer r-1"),
                             (T0 + 9000, "INTEGRATED", "h-1", "integrate; recorded by h-1"),
                             (T0 + 9500, "CLAIMED", "a-1", "claim")], extra="Unreviewed: yes\n")
    task(c, "UAK-005", hist=[(T0, "CLAIMED", "a-1", "claim"), (T0 + 100, "REVIEW", "a-1", "done"),
                             (T0 + 200, "REVIEW", "r-1", "review; approve; SHA aaaaaaa111; reviewer r-1"),
                             (T0 + 300, "REVIEW", "a-1", "done"),
                             (T0 + 400, "REVIEW", "r-1", "review; approve; SHA bbbbbbb222; reviewer r-1"),
                             (T0 + 500, "INTEGRATED", "Ana", "integrate; recorded by Ana")])
    put(c / "meta" / "agents" / "Ana.md", "# Ana\nAgent: Ana\nRole: human\n")
    task(c, "UAK-003", state="CLAIMED", hist=[(T0 + DAY, "CLAIMED", "a-1", "claim")])
    put(c / "backlog" / "TASKS.md", "## UAK-004 · fix (follow-up of UAK-001)\n\n- **Type:** follow-up\n- **Follow-up of:** UAK-001\n")
    put(c / "queue" / "UAK-001.md", "# q\nTask: UAK-001\nReason: Shared resource/CI needs a human: kit/x\nUpdated: %d\n" % T0)
    put(c / "queue" / "UAK-002.md", "# q\nTask: UAK-002\nReason: Waiting for queue\nUpdated: %d\n" % T0)
    put(c / "DECISIONS.md", "# d\n- %d | allow | Ana | freeze exception: UAK-001 | Why: x\n" % T0)
    rows = ["# ledger: epoch, command, task, exit, code, ms, agent, harness"]
    rows.append("#sum\tclaim\tfail\t5")
    for i in range(n_ledger):  # status: 30 calls, 3 fail, ms 10..300
        rows.append("%d\tstatus\t-\t%s\t-\t%d\ta-1\tclaude-code" % (T0 + i, "2" if i % 10 == 0 else "0", 10 * (i + 1)))
    rows.append("%d\tdone\tUAK-001\t1\tred-missing\t500\ta-1\tclaude-code" % (T0 + 50))
    rows.append("%d\tdone\tUAK-001\t0\t-\t700\ta-1\tclaude-code" % (T0 + 60))
    rows.append("%d\tbb\t-\t-\t-\t-\ta-1\tclaude-code" % (T0 + 70))  # ended in an exec: outcome unknown
    put(c / "metrics" / "2027-01-15-1.tsv", "\r\n".join(rows) + "\r\n")  # CRLF on purpose
    return c


def run(r, c, *args, extra=None):
    env = dict(os.environ, UAK_METRICS_NOW=str(T0 + 3 * DAY))
    for k in ("UAK_REMOTE", "UAK_BASE"):
        env.pop(k, None)
    p = subprocess.run([r["bash"], str(r["pkg"] / "bin" / "metrics"), "--claims", str(c)] + list(args), cwd=str(c.parent), env=env,
                       capture_output=True, text=True, timeout=120)
    expect(p.returncode == 0, "rc %d: %s" % (p.returncode, p.stdout + p.stderr))
    return p.stdout


def throughput_is_printed_with_instability(r):
    out = run(r, claims(r["tmp"]))
    expect("integrated 3 · reopened 1 · followed up 1 · Unreviewed 1" in out, out)
    expect("reopened 1 of 3 · followed up 1 of 3 · Unreviewed 1 of 3" in out, out)
    expect("claim to INTEGRATED: median 2.0 h (3 tasks)" in out, out)  # 7200 s, 9000 s and 500 s -> median 2 h
    expect("rejected at least once: 1 of 3 reviewed tasks" in out and "new tip after an approval (rework without a reject): 1 of 3 reviewed" in out and "review rounds per task: 1.67 (5 rounds in 3 tasks, 1 of 5 rounds rejected;" in out, out)
    order = [out.index(k) for k in ("tasks integrated per day", "speed and its cost", "per command", "human interventions", "work outside the kit")]
    expect(order == sorted(order), "sections out of order")
    expect("sent to a human: 1 of 2 queued tasks (Shared resource/CI needs a human 1)" in out and "1 freeze exceptions" in out, out)
    expect("no human (event `merge`): 1 of 3" in out and "base history is not available here" in out and "not told apart): 2 of 3" in out and "with an agent identity 1 of 2 · by a human (Role: human) 1 of 2 · Unreviewed: yes 1 of 2" in out and "manual notes: not recorded yet" in out, out)
    return "throughput next to reopened, followed up, Unreviewed"


def per_command_error_rate_and_p95(r):
    out = run(r, claims(r["tmp"]))
    line = [x for x in out.splitlines() if x.strip().startswith("status ") and "call(s)" in x][0]
    expect("30 call(s)" in line and "errors 3 of 30 (10%)" in line and "median 155 ms" in line and "p95 290 ms" in line, line)
    claim = [x for x in out.splitlines() if x.strip().startswith("claim ") and "call(s)" in x][0]
    expect("5 call(s)" in claim and "errors 5 of 5" in claim and "(" not in claim.split("errors")[1].split("·")[0], claim)
    bb = [x for x in out.splitlines() if x.strip().startswith("bb ") and "call(s)" in x][0]
    expect("errors 0 of 0" in bb, bb)  # an exec'd command: outcome unknown, not counted as a success
    return "error rate, median, p95 per command"


def small_samples_print_counts(r):
    out = run(r, claims(r["tmp"], n_ledger=5))
    line = [x for x in out.splitlines() if x.strip().startswith("status ") and "call(s)" in x][0]
    expect("errors 1 of 5" in line and "%" not in line and "p95 -" in line, line)
    expect("%" not in out.split("work outside")[0].split("human interventions")[0].split("tasks integrated per day")[1], "percentage under 20 events")
    return "counts, no percentage under 20"


def merge_paths_classified_by_base_history(r):
    c = claims(r["tmp"])
    # More tasks: engine merge commit + integrate, forge PR merge, forge squash, none found. PR numbers come from the PR field.
    for tid, pr in (("UAK-010", "pull/3"), ("UAK-011", "pull/7"), ("UAK-012", "pull/9"), ("UAK-013", "pull/new/feat/uak-013")):
        task(c, tid, hist=[(T0, "CLAIMED", "a-1", "claim"), (T0 + 60, "INTEGRATED", "a-3", "integrate; recorded by a-3")],
             extra="PR: https://github.com/o/r/%s\n" % pr)
    # A task whose own Merge-Commit field names another task's merge must not take that one's class.
    put(c / "tasks" / "UAK-013.md", (c / "tasks" / "UAK-013.md").read_text() + "Merge-Commit: deadbeef\n")
    repo = c.parent
    g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"] + list(a), cwd=str(repo),
                                  capture_output=True, text=True, check=True)
    g("init", "-q")
    for subject in ("root", "Merge UAK-010 reviewed by kit-r1 (human-authorized merge: engine file)", "Merge pull request #7 from o/feat/uak-011",
                    "UAK-012: a squash (#9)", "harness: regenerate (UAK-013 changed its source)"):
        g("commit", "-q", "--allow-empty", "-m", subject)
    out = run(r, c)
    for want in ("by the gate, no human (event `merge`): 1 of 7", "engine merge commit, then integrate): 1 of 7",
                 "then recorded with integrate: 2 of 7", "merge commit not found or of another kind: 3 of 7",
                 "classified by the base's own history"):
        expect(want in out, want + "\n" + out)
    m = json.loads(run(r, c, "--json"))["merge_paths"]
    expect(m["basis"] == "base history" and m["gate_built_human_landed"] == {"n": 1, "of": 7} and m["forge"] == {"n": 2, "of": 7}
           and m["gate_pushed"] == {"n": 1, "of": 7} and m["recorded_unclassified"] == {"n": 3, "of": 7}, m)
    return "gate / engine merge landed by a human / forge, from the base history"


def task_view_lists_review_rounds(r):
    c = claims(r["tmp"])
    out = run(r, c, "--task", "UAK-001")
    expect("review rounds: 2" in out and "1. reject by r-1 on abcdef0" in out and "2. approve by r-1 on 1234567" in out, out)
    expect("integrated: by a-2 (gate merge)" in out, out)
    expect("done 2 (1 failed)" in out and "error: done exit 1 red-missing" in out, out)
    expect("REJECTED (rework)" in out and "APPROVED (waiting for the merge)" in out and "REVIEW (waiting for a reviewer)" in out, out)
    expect("integrated: by h-1 (integrate), recorded Unreviewed" in run(r, c, "--task", "UAK-002"), "uak-002")
    return "one task: states, rounds, who integrated, errors"


def json_has_stable_keys(r):
    c = claims(r["tmp"])
    m = json.loads(run(r, c, "--json"))
    expect(list(m) == ["since_days", "tasks", "throughput", "flow", "commands", "human", "merge_paths", "outside"], list(m))
    expect(sorted(m["throughput"]) == ["days", "followed_up", "integrated", "reopened", "unreviewed"], m["throughput"])
    expect(sorted(m["flow"]) == ["claim_to_integrated_hours", "new_tip_after_approval", "rejected_tasks", "review_rounds"], m["flow"])
    expect(m["throughput"]["reopened"] == {"n": 1, "of": 3} and m["flow"]["rejected_tasks"] == {"n": 1, "of": 3}, m["flow"])
    st = [x for x in m["commands"] if x["command"] == "status"][0]
    expect(st["errors"] == {"n": 3, "of": 30} and st["p95_ms"] == 290 and sorted(st) == ["calls", "command", "errors", "median_ms", "p95_ms", "timed"], st)
    expect(m["outside"]["manual_notes"] == {"recorded": False, "count": 0}, m["outside"])
    t = json.loads(run(r, c, "--task", "UAK-001", "--json"))
    expect(sorted(t) == ["commands", "errors", "integrated", "owner", "rounds", "state", "states", "task"], sorted(t))
    w = json.loads(run(r, c, "--since", "2", "--json"))  # window: only the task last moved within 2 days
    expect(w["tasks"]["n"] == 1 and w["since_days"] == 2, w["tasks"])
    return "documented keys"


def old_lines_are_counted_apart(r):
    """UAK-136: lines with no exit code (written before every command was timed) are counted as 'outcome not recorded'."""
    c = claims(r["tmp"])
    out = run(r, c)
    bb = [x for x in out.splitlines() if x.strip().startswith("bb ") and "call(s)" in x][0]
    expect("outcome not recorded: 1" in bb, bb)
    st = [x for x in out.splitlines() if x.strip().startswith("status ") and "call(s)" in x][0]
    expect("outcome not recorded" not in st, st)
    # A command that ran with an exit code and ms never prints "errors 0 of 0" nor "median -".
    rows = open(str(c / "metrics" / "2027-01-15-1.tsv"), encoding="utf-8", newline="").read()
    rows += "%d\tmetrics\t-\t0\t-\t42\ta-1\tclaude-code\r\n" % (T0 + 80)
    put(c / "metrics" / "2027-01-15-1.tsv", rows)
    out = run(r, c)
    mt = [x for x in out.splitlines() if x.strip().startswith("metrics ") and "call(s)" in x][0]
    expect("errors 0 of 1" in mt and "median 42 ms" in mt and "outcome not recorded" not in mt, mt)
    return "old lines apart"


def git(cwd, *args, **env):
    e = dict(os.environ, **env)
    p = subprocess.run(["git"] + list(args), cwd=str(cwd), env=e, capture_output=True, text=True)
    expect(p.returncode == 0, "git %s: %s" % (args, p.stderr))


def direct_commits_inside_a_window(r):
    """UAK-136: 'commits on the base with no task' is computed inside a --since window (first-parent commits of it)."""
    c = claims(r["tmp"])
    repo = Path(r["tmp"]) / "repo é"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    for i, (when, msg) in enumerate([(T0 - 20 * DAY, "root"), (T0 - 10 * DAY, "old direct"), (T0 + 2 * DAY + 100, "direct in the window"),
                                     (T0 + 2 * DAY + 200, "UAK-001 · a task commit")]):
        (repo / "f").write_text(str(i))
        git(repo, "add", "f")
        d = "@%d +0000" % when
        git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg, GIT_AUTHOR_DATE=d, GIT_COMMITTER_DATE=d)
    env = dict(os.environ, UAK_METRICS_NOW=str(T0 + 3 * DAY))
    for k in ("UAK_REMOTE", "UAK_BASE"):
        env.pop(k, None)
    def go(*a):
        p = subprocess.run([r["bash"], str(r["pkg"] / "bin" / "metrics"), "--claims", str(c)] + list(a), cwd=str(repo), env=env,
                           capture_output=True, text=True, timeout=120)
        expect(p.returncode == 0, p.stdout + p.stderr)
        return p.stdout
    whole = go()
    expect("commits on the base with no task: 2 of 4 first-parent commits" in whole, whole)
    win = go("--since", "1")
    expect("commits on the base with no task: 1 of 2 first-parent commits" in win, win)
    expect("n/a" not in win.split("work outside the kit")[1].split("recorded as")[0], win)
    return "window counts first-parent commits"


def manual_notes_print_zero(r):
    """UAK-136: 'manual notes' prints a count, 0 included, once a black box of the window comes from a version that records them."""
    c = claims(r["tmp"])
    put(c / "blackbox" / "2027-01-15.md", "# Black box\n\n- 2027-01-15T10:00Z | v6.6.0 | claude-code | solo | auto | bug | status | old kit | fix: -\n")
    out = run(r, c)
    expect("manual notes: not recorded yet" in out, out)   # only a version that does not record them
    put(c / "blackbox" / "2027-01-16.md", "# Black box\n\n- 2027-01-16T10:00Z | v6.7.0 | claude-code | solo | auto | bug | status | new kit | fix: -\n")
    out = run(r, c)
    expect("manual notes: 0" in out, out)
    m = json.loads(run(r, c, "--json"))
    expect(m["outside"]["manual_notes"] == {"recorded": True, "count": 0}, m["outside"])
    return "zero is printed"


TESTS = [merge_paths_classified_by_base_history, throughput_is_printed_with_instability, per_command_error_rate_and_p95, small_samples_print_counts, task_view_lists_review_rounds,
         json_has_stable_keys, old_lines_are_counted_apart, direct_commits_inside_a_window, manual_notes_print_zero]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--case")
    a = ap.parse_args()
    failed = 0
    tests = [t for t in TESTS if not a.case or t.__name__ == a.case]
    with tempfile.TemporaryDirectory(prefix="uak metrics é ") as tmp:
        for t in tests:
            sub = tempfile.mkdtemp(dir=tmp)
            env = {"bash": resolve_binary("bash"), "pkg": a.package.resolve() / ".uak", "tmp": sub}
            try:
                print("PASS %s (%s)" % (t.__name__, t(env)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("METRICS_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
