#!/usr/bin/env python3
"""UAK-094: engine messages and caches that misled agents (QA round C, 2026-11-14, C-7, C-11..C-16).

- a contract message cited a SHA that only existed on an unmerged feature branch: the consumer could not find it;
- `next`'s "= unchanged" cache was keyed by session, not identity: beto-r saw "Nothing new" after ana-r's call;
- `uak stats` listed normal merge-queue waits ("Waiting for queue") as human-queue reasons;
- `uak board` showed "PR#001" for https://forge.invalid/cafeteria/pull/feat/caf-001;
- `uak dash` printed a tarfile DeprecationWarning and reported mode "" (Mode lives in PROJECT.md, not claims).
Real Git, a local bare remote."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_reviewer_next import to_review


def env(agent, **extra):
    e = {"UAK_AGENT": agent, "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000020"}
    e.update(extra)
    return e


def contract_message_names_the_branch(r):
    f = r.fixture("qa14-contract", count=2)
    f.claim(0, "HACK-001")
    w = f.worktrees[0]
    (w / "src").mkdir(exist_ok=True)
    (w / "src" / "one.txt").write_text("the contract\n", encoding="utf-8")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", "HACK-001: contract")
    r.g(w, "push", "-q", "origin", f.branches[0])
    sha = r.g(w, "rev-parse", "--short=7", "HEAD").stdout.strip()
    out = f.hack(0, "msg", "HACK-002", "--kind", "contract", "--task", "HACK-001",
                 "src/one.txt at %s · build against it" % sha, now=1000010)
    log = f.show("inbox/log.md")
    line = [l for l in log.splitlines() if "| contract |" in l]
    expect(line, "the contract is in the log: " + log[-600:])
    want = "git show origin/%s:src/one.txt" % f.branches[0]
    expect(want in line[-1], "the contract names the branch the SHA is on (%s): %s | %s" % (want, line[-1], out.stdout[-400:]))
    # A SHA already on main needs no pointer.
    base = r.g(w, "rev-parse", "--short=7", "origin/main").stdout.strip()
    f.hack(0, "msg", "HACK-002", "--kind", "contract", "--task", "HACK-001", "src/one.txt at %s · the base" % base, now=1000011)
    last = [l for l in f.show("inbox/log.md").splitlines() if "| contract |" in l][-1]
    expect("git show" not in last, "a SHA on main is left as written: " + last)
    return "branch named"


def next_cache_is_per_identity(r):
    f = r.fixture("qa14-next", count=3)
    f.hack(0, "register-reviewer", "agent-2", "agent-3", human=True, now=1000005)
    to_review(r, f)  # both reviewers are offered the same review: the same text
    c = f.clones[2]
    run = lambda agent: r.run([r.bash, ".uak/bin/uak", "next"], cwd=c, env=env(agent, UAK_DEDUPE="on")).stdout
    first = run("agent-3")
    expect("= unchanged" not in first, "the first call prints: " + first[:400])
    other = run("agent-2")
    expect("= unchanged" not in other, "another identity in the same session is not told 'Nothing new': " + other[:400])
    again = run("agent-2")
    expect("= unchanged" in again, "the same identity again is deduplicated: " + again[:400])
    return "per identity"


def stats_counts_only_escalations(r):
    d = r.scratch / "qa14-stats"
    (d / "queue").mkdir(parents=True)
    (d / "queue" / "HACK-001.md").write_text("ID: HACK-001\nState: WAITING\nOwner: a\nQueued: 1\nReason: Waiting for queue\n", encoding="utf-8")
    (d / "queue" / "HACK-002.md").write_text("ID: HACK-002\nState: WAITING\nOwner: b\nQueued: 2\nReason: Waiting for queue\n", encoding="utf-8")
    (d / "queue" / "HACK-003.md").write_text("ID: HACK-003\nState: HUMAN\nOwner: c\nUpdated: 3\nReason: Lock lease expired; revalidate before merging\n", encoding="utf-8")
    out = r.run([r.bash, str(r.package / ".uak/bin/stats"), "--dir", str(d)], cwd=d).stdout
    line = [l for l in out.splitlines() if l.startswith("human-queue reasons:")]
    expect(line, "the human-queue line is printed: " + out[-500:])
    expect("Waiting for queue" not in line[0], "a queue wait is not a human-queue reason: " + line[0])
    expect("Lock lease expired" in line[0], "an escalation is: " + line[0])
    (d / "queue" / "HACK-003.md").unlink()
    out = r.run([r.bash, str(r.package / ".uak/bin/stats"), "--dir", str(d)], cwd=d).stdout
    expect("Waiting for queue" not in out, "only waits: no reason listed: " + out[-500:])
    return "escalations only"


def board_pr_label_without_number(r):
    f = r.fixture("qa14-board", count=2)
    for index, task, pr in ((0, "HACK-001", "https://forge.invalid/team/pull/feat/hack-001"),
                            (1, "HACK-002", "https://example.invalid/team/pull/12")):
        f.claim(index, task)
        w = f.worktrees[index]
        (w / "src").mkdir(exist_ok=True)
        (w / "src" / (task + ".txt")).write_text("a change\n", encoding="utf-8")
        r.g(w, "add", "-A")
        r.g(w, "commit", "-q", "-m", task + ": a change")
        r.g(w, "push", "-q", "origin", f.branches[index])
        f.hack(index, "done", task, "--pr", pr, "--evidence", "a change", "--no-red", "fixture", now=1000010)
    out = r.run([r.bash, ".uak/bin/board"], cwd=f.clones[0], env=env("agent-1")).stdout
    one = [l for l in out.splitlines() if " HACK-001 " in l]
    two = [l for l in out.splitlines() if " HACK-002 " in l]
    expect(one and two, "both tasks are on the board: " + out)
    expect("PR#001" not in one[0] and "hack-001" in one[0], "a URL without a PR number shows its tail: " + one[0])
    expect("PR#12" in two[0], "a numbered PR keeps PR#N: " + two[0])
    return "url tail"


def dash_reports_the_mode(r):
    f = r.fixture("qa14-dash", count=1)
    c = f.clones[0]
    project = c / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8") + "Mode: sprint\n", encoding="utf-8")
    r.g(c, "add", ".uak/PROJECT.md")
    r.g(c, "commit", "-q", "-m", "mode")
    r.g(c, "push", "-q", "origin", "main")
    f.claim(0, "HACK-001")
    out_dir = f.base / "dash-out"
    res = r.run([r.bash, ".uak/bin/uak", "dash", "--out", str(out_dir)], cwd=c, env=env("agent-1", PYTHONWARNINGS="default"))
    expect("DeprecationWarning" not in res.stderr, "no tarfile DeprecationWarning: " + res.stderr[-600:])
    data = (out_dir / "data.js").read_text(encoding="utf-8")
    expect('"mode":"sprint"' in data, "the mode comes from PROJECT.md on main when claims has none: " + data[:300])
    return "mode sprint"


TESTS = [contract_message_names_the_branch, next_cache_is_per_identity, stats_counts_only_escalations,
         board_pr_label_without_number, dash_reports_the_mode]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-qa14-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        results = []
        for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
            started = time.monotonic()
            try:
                note = test(runner)
                results.append((test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)))
            except Exception as exc:  # noqa: BLE001
                results.append((test.__name__, False, str(exc)[:2500]))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("ENGINE_MESSAGES_QA14_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
