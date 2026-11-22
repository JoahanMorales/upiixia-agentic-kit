#!/usr/bin/env python3
"""UAK-132: `uak integrate` records in Merge-Commit the commit that brought THIS task's tip onto the base, never the base's
tip at that moment. Why (review of UAK-117, 2026-11-21): on UAK-030 and UAK-013 the field named another task's merge, so
`uak metrics` stopped trusting it and classified 104 tasks from the base's history. When no such commit is found the
field says `unknown` and the reason goes in the event; `uak metrics` counts the records it had to classify by history.
Real Git, a local bare remote."""
import argparse
import concurrent.futures
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_integrate_outside import commit_file, integrate, record, seed, seed_pull, squash_into_main
import test_metrics

REVIEWER = 2  # index of the third clone: agent-3 reviews


def fx3(r, name):
    return r.fixture(name, count=3)


def in_review(r, f, idx, task, rel, text):
    f.claim(idx, task, now=1000000 + idx)
    w = f.worktrees[idx]
    (w / ".uak-env").write_bytes(("UAK_TASK=%s\nUAK_AGENT=agent-%d\n" % (task, idx + 1)).encode())
    commit_file(r, w, rel, text, task + ": the work")
    r.g(w, "push", "-q", "origin", f.branches[idx])
    f.hack(idx, "done", task, "--pr", "https://example.invalid/pull/%d" % (idx + 1), "--evidence", "x", "--no-red", "fixture", now=1000010 + idx)
    return r.g(w, "rev-parse", "HEAD").stdout.strip()


def approve_by_third(r, f, task, tip):
    f.hack(0, "register-reviewer", "agent-3", human=True, now=1000011)
    rv = r.run([r.bash, ".uak/bin/uak", "review", task, "--sha", tip, "--verdict", "approve"], cwd=f.clones[REVIEWER],
               env={"UAK_AGENT": "agent-3", "UAK_NOW": "1000020", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}, allowed=None)
    expect(rv.returncode == 0, "approval: " + rv.stdout + rv.stderr)


def merge_into_main(r, f, branch, msg):
    seed_pull(r, f)
    seed(r, f, "fetch", "-q", "origin")
    seed(r, f, "merge", "-q", "--no-ff", "-m", msg, "origin/" + branch)
    seed(r, f, "push", "-q", "origin", "main")
    return r.g(f.seed, "rev-parse", "HEAD").stdout.strip()


def unrelated_on_main(r, f, name="docs/later.txt"):
    commit_file(r, f.seed, name, "another change\n", "docs: later")
    seed(r, f, "push", "-q", "origin", "main")
    return r.g(f.seed, "rev-parse", "HEAD").stdout.strip()


def field_of(rec, name):
    for line in rec.splitlines():
        if line.startswith(name + ": "):
            return line.split(": ", 1)[1].strip()
    return None


def integrate_records_its_own_merge(r):
    f = fx3(r, "mcf-own")
    tip = in_review(r, f, 0, "HACK-001", "src/one.txt", "the work\n")
    approve_by_third(r, f, "HACK-001", tip)
    merged = merge_into_main(r, f, f.branches[0], "Merge PR")
    head = unrelated_on_main(r, f)
    expect(head != merged, "fixture: main moved on after the merge")
    out = integrate(f)
    expect(out.returncode == 0, "integrate: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    rec = record(f, "HACK-001")
    expect(field_of(rec, "Merge-Commit") == merged, "Merge-Commit is the merge of this task (%s), not main's tip (%s): %s" % (merged[:7], head[:7], rec))
    return "own merge commit"


def two_tasks_merged_together_get_their_own(r):
    f = fx3(r, "mcf-two")
    t1 = in_review(r, f, 0, "HACK-001", "src/one.txt", "one\n")
    t2 = in_review(r, f, 1, "HACK-002", "src/two.txt", "two\n")
    approve_by_third(r, f, "HACK-001", t1)
    approve_by_third(r, f, "HACK-002", t2)
    m1 = merge_into_main(r, f, f.branches[0], "Merge pull request #1 from o/feat/hack-001")
    m2 = merge_into_main(r, f, f.branches[1], "Merge pull request #2 from o/feat/hack-002")
    expect(m1 != m2, "fixture: two merges")
    for idx, task, want in ((0, "HACK-001", m1), (1, "HACK-002", m2)):
        out = integrate(f, task, agent=idx)
        expect(out.returncode == 0, "integrate %s: rc %d %s" % (task, out.returncode, (out.stdout + out.stderr)[-500:]))
        got = field_of(record(f, task), "Merge-Commit")
        expect(got == want, "%s: Merge-Commit %s, want its own %s (main's tip is %s)" % (task, got, want, m2))
    return "each task names its own merge"


def squash_is_found_by_tree(r):
    f = fx3(r, "mcf-squash")
    tip = in_review(r, f, 0, "HACK-001", "src/one.txt", "squashed\n")
    approve_by_third(r, f, "HACK-001", tip)
    squash_into_main(r, f, f.branches[0], msg="a squash with a subject that names nothing")
    squashed = r.g(f.seed, "rev-parse", "HEAD").stdout.strip()
    head = unrelated_on_main(r, f)
    out = integrate(f)
    expect(out.returncode == 0, "integrate: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    got = field_of(record(f, "HACK-001"), "Merge-Commit")
    expect(got == squashed, "Merge-Commit is the squash commit %s, not main's tip %s: %s" % (squashed[:7], head[:7], got))
    return "squash found by tree"


def unknown_when_not_found(r):
    f = fx3(r, "mcf-unknown")
    tip = in_review(r, f, 0, "HACK-001", "src/one.txt", "squashed\n")
    approve_by_third(r, f, "HACK-001", tip)
    squash_into_main(r, f, f.branches[0], msg="a squash with a subject that names nothing")
    seed(r, f, "reset", "-q", "--soft", "HEAD~1")  # the squash also carries another change: its tree is not the tip's
    commit_file(r, f.seed, "docs/rode-along.txt", "rode along\n", "a squash with a subject that names nothing")
    seed(r, f, "push", "-q", "-f", "origin", "main")
    unrelated_on_main(r, f)
    out = integrate(f)
    expect(out.returncode == 0, "integrate: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    rec = record(f, "HACK-001")
    expect(field_of(rec, "Merge-Commit") == "unknown", "no commit is found: the field says unknown, not a SHA: " + rec)
    log = f.show(f.worklog("HACK-001"))
    expect("Merge-Commit unknown" in log, "the reason is in the event: " + log[-800:])
    return "unknown, with the reason in the event"


def long_history(r, f, count, touch):
    """`count` first-parent commits on main in one git fast-import (a process per commit would make the fixture as slow as
    the code under test). touch=False: empty commits, the tree never changes; touch=True: each one adds its own file."""
    seed_pull(r, f)
    lines = []
    for i in range(count):
        msg = "hist %d" % i
        lines += ["commit refs/heads/main", "committer t <t@t> %d +0000" % (1000000 + i), "data %d" % len(msg), msg]
        if i == 0:
            lines += ["from refs/heads/main^0"]
        if touch:
            lines += ["M 100644 inline hist/f%d.txt" % i, "data 1", "x"]
        lines += [""]
    data = "\n".join(lines) + "\n"
    done = subprocess.run([r.git, "fast-import", "--quiet", "--date-format=raw"], cwd=str(f.seed), input=data.encode(), capture_output=True)
    expect(done.returncode == 0, "fast-import: " + done.stderr.decode(errors="replace"))
    seed(r, f, "reset", "-q", "--hard", "main")
    seed(r, f, "push", "-q", "origin", "main")


def counting_env(r):
    """A `git` shim first on PATH that logs one line per process and runs the real one."""
    d = Path(tempfile.mkdtemp(prefix="mcf-shim-", dir=str(r.scratch)))  # one per call: the cases run in threads
    log = d.parent / (d.name + ".log")
    out = r.run([r.bash, "-c", 'real=$(type -P git); printf "#!/usr/bin/env bash\\necho x >> \\"%s\\"\\nexec \\"%s\\" \\"\\$@\\"\\n" "$2" "$real" > "$1/git"; '
                 'chmod +x "$1/git"; if command -v cygpath >/dev/null 2>&1; then cygpath -u "$1"; else printf "%s" "$1"; fi',
                 "_", d.as_posix(), log.as_posix()], cwd=r.scratch)
    return out.stdout.strip(), log


def integrate_counting(r, f, task="HACK-001"):
    shim, log = counting_env(r)
    log.write_text("")
    env = {"UAK_AGENT": "agent-2", "UAK_HUMAN": "", "UAK_NOW": "1000100", "UAK_REMOTE": "origin",
           "PATH": shim + ":" + os.environ["PATH"]}
    out = r.run([r.bash, ".uak/bin/uak", "integrate", task], cwd=f.worktrees[1], env=env, allowed=None)
    expect(out.returncode == 0, "integrate: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    return len(log.read_text().split()), field_of(record(f, task), "Merge-Commit")


def stale_tip_scenario(r, name, history, touch, subject, rode_along):
    f = fx3(r, name)
    tip = in_review(r, f, 0, "HACK-001", "src/one.txt", "squashed\n")
    approve_by_third(r, f, "HACK-001", tip)
    long_history(r, f, history, touch)
    squash_into_main(r, f, f.branches[0], msg=subject)
    if rode_along:  # the squash also carries another change: its tree is not the tip's, the subject must name the task
        seed(r, f, "reset", "-q", "--soft", "HEAD~1")
        commit_file(r, f.seed, "docs/rode-along.txt", "rode along\n", subject)
        seed(r, f, "push", "-q", "-f", "origin", "main")
    squashed = r.g(f.seed, "rev-parse", "HEAD").stdout.strip()
    unrelated_on_main(r, f)
    calls, got = integrate_counting(r, f)
    return squashed, calls, got


def lookup_cost_does_not_grow_with_history(r):
    sq_s, short, got_s = stale_tip_scenario(r, "mcf-hist-short", 10, False, "a squash with a subject that names nothing", False)
    sq_l, long, got_l = stale_tip_scenario(r, "mcf-hist-long", 300, False, "a squash with a subject that names nothing", False)
    expect(got_s == sq_s and got_l == sq_l, "the squash is found by tree: %s %s, want %s %s" % (got_s, got_l, sq_s, sq_l))
    expect(long - short < 10, "a stale tip: 300 commits cost %d git processes, 10 commits %d (one process per commit?)" % (long, short))
    return "git processes %d (10 commits) vs %d (300 commits)" % (short, long)


def forge_subject_found_in_long_history(r):
    sq, calls, got = stale_tip_scenario(r, "mcf-hist-forge", 300, True, "HACK-001: the work (#1)", True)
    expect(got == sq, "the squash that names the task (#1) is found in a long history: %s, want %s" % (got, sq))
    sq2, calls2, got2 = stale_tip_scenario(r, "mcf-hist-forge2", 300, True, "a squash that names nothing", True)
    expect(got2 == "unknown", "nothing names the task and the trees differ: unknown, got %s" % got2)
    return "named squash found, unnamed one unknown (%d, %d git processes)" % (calls, calls2)


def metrics_counts_untrusted_records(r):
    c = test_metrics.claims(r["tmp"])
    for tid, pr, extra in (("UAK-010", "pull/3", ""), ("UAK-011", "pull/7", ""), ("UAK-012", "pull/9", ""), ("UAK-013", "pull/4", "")):
        test_metrics.task(c, tid, hist=[(test_metrics.T0, "CLAIMED", "a-1", "claim"), (test_metrics.T0 + 60, "INTEGRATED", "a-3", "integrate; recorded by a-3")],
                          extra="PR: https://github.com/o/r/%s\n" % pr)
    repo = c.parent
    sh = {}

    def g(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"] + list(a), cwd=str(repo),
                              capture_output=True, text=True, check=True).stdout.strip()
    g("init", "-q")
    for key, subject in (("root", "root"), ("e10", "Merge UAK-010 reviewed by kit-r1 (human-authorized merge: engine file)"),
                         ("f11", "Merge pull request #7 from o/feat/uak-011"), ("s12", "UAK-012: a squash (#9)"),
                         ("x13", "harness: regenerate")):
        g("commit", "-q", "--allow-empty", "-m", subject)
        sh[key] = g("rev-parse", "HEAD")
    # UAK-010: a correct field. UAK-011: names UAK-010's merge (wrong). UAK-012: absent. UAK-013: unknown.
    for tid, val in (("UAK-010", sh["e10"]), ("UAK-011", sh["e10"]), ("UAK-013", "unknown")):
        p = c / "tasks" / (tid + ".md")
        p.write_text(p.read_text() + "Merge-Commit: %s\n" % val)
    out = test_metrics.run(r, c)
    m = json.loads(test_metrics.run(r, c, "--json"))["merge_paths"]
    expect(m.get("classified_by_history") == {"n": 5, "of": 6}, "UAK-002 and UAK-005 (no field), UAK-011 (wrong), UAK-012 (none) and UAK-013 (unknown) were classified by history: %s" % m)
    expect(m["gate_built_human_landed"]["n"] == 1 and m["forge"]["n"] == 2, "UAK-010 by its field; UAK-011 and UAK-012 by history: %s" % m)
    expect("5 of 6 recorded tasks had a wrong, missing or unknown Merge-Commit and were classified by the base's history" in out, out)
    return "wrong, missing and unknown fields are counted"


TESTS = [integrate_records_its_own_merge, two_tasks_merged_together_get_their_own, squash_is_found_by_tree, unknown_when_not_found,
         lookup_cost_does_not_grow_with_history, forge_subject_found_in_long_history]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak merge-commit-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                return test.__name__, True, "%s, %.2fs" % (test(runner), time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]

        def metrics_one(test):
            sub = tempfile.mkdtemp(dir=tmp)
            env = {"bash": resolve_binary("bash"), "pkg": args.package.resolve() / ".uak", "tmp": sub}
            try:
                return test.__name__, True, test(env)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        selected = [t for t in TESTS if not args.case or t.__name__ in args.case]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, selected))
        if not args.case or "metrics_counts_untrusted_records" in args.case:
            results.append(metrics_one(metrics_counts_untrusted_records))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("MERGE_COMMIT_FIELD_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
