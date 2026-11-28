#!/usr/bin/env python3
"""UAK-201: a reject carries its cause, a lesson reaches the next agent at claim, and the loop can be judged.
Why (2026-11-25, the human asked whether the work got faster with the lessons recorded): `uak next` showed lessons and the
ledger counted 9 calls of it in 158 tasks, a reject had no cause, and nothing said whether a lesson changed anything.
Real Git fixtures (test_hack's Runner): scratch repos only, never this repo's board."""
import argparse
import os
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm

CAUSES = ("failure-path-not-handled", "test-does-not-test", "timing", "process-left", "protocol", "wording-false", "security", "other")


def lesson(f, text, path, now=1000005, who="judge"):
    return rm.actor(f, who, "learn", text, "--path", path, now=now)


def review(f, task, tip, *args, now=1000021, real_clock=False, allowed=(0,)):
    """`uak review` as the judge. real_clock: no simulated clock, as an agent runs it (the guard forbids UAK_NOW to agents)."""
    env = {"UAK_AGENT": "judge", "UAK_HUMAN": "", "UAK_NOW": "" if real_clock else str(now), "UAK_REVIEW_MODE": "claims"}
    return f.r.run([f.r.bash, ".uak/bin/uak", "review", task, "--sha", tip, *args], cwd=f.clones[0], env=env, allowed=allowed)


def events(f, task):
    return f.show(f.worklog(task)).split("## History", 1)[1]


def reject_needs_a_cause(r):
    f = rm.fixture(r, "cause", count=2)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    # An agent has no simulated clock: a reject without a cause is refused, and nothing is recorded.
    no = review(f, "HACK-001", tip, "--verdict", "reject", "--note", "a.txt:1 · wrong", real_clock=True, allowed=None)
    expect(no.returncode != 0 and "needs its cause" in no.stderr + no.stdout and "timing" in no.stderr + no.stdout, no.stdout + no.stderr)
    for bad in ("nonsense", "Timing", "timing;x", "$(touch /tmp/uak-201-x)"):
        un = review(f, "HACK-001", tip, "--verdict", "reject", "--cause", bad, real_clock=True, allowed=None)
        expect(un.returncode != 0 and "is not one of" in un.stderr + un.stdout, bad + ": " + un.stdout + un.stderr)
    ap = review(f, "HACK-001", tip, "--verdict", "approve", "--cause", "timing", real_clock=True, allowed=None)
    expect(ap.returncode != 0 and "reject only" in ap.stderr + ap.stdout, ap.stdout + ap.stderr)
    expect("reviews/HACK-001.md" not in f.files("reviews/"), "refusals recorded a review: %r" % f.files("reviews/"))
    # The documented list is the list: CLI.md prints each cause, and the engine takes each.
    cli = (Path(__file__).resolve().parents[1] / "docs" / "CLI.md").read_text(encoding="utf-8")
    shell = (Path(__file__).resolve().parents[1] / "bin" / "lib" / "memory.sh").read_text(encoding="utf-8")
    listed = re.search(r'^REJECT_CAUSES="([^"]+)"', shell, re.M).group(1).split()
    expect(tuple(listed) == CAUSES, "the list in memory.sh: %r" % listed)
    expect(all("`%s`" % c in cli for c in CAUSES), "CLI.md must print every cause")
    ok = review(f, "HACK-001", tip, "--verdict", "reject", "--cause", "timing", "--note", "a.txt:1 · slow")
    expect("reject; SHA %s; reviewer judge; cause timing" % tip in events(f, "HACK-001"), events(f, "HACK-001"))
    expect(ok.returncode == 0, ok.stderr)
    # The kit's older tests set the simulated clock: there a missing cause is accepted and recorded as no cause.
    tip2 = rm.ready(f, 1, "HACK-002")
    old = review(f, "HACK-002", tip2, "--verdict", "reject", "--note", "b.txt:1 · old style")
    expect(old.returncode == 0 and "; cause" not in events(f, "HACK-002").split("reject;")[1].splitlines()[0], events(f, "HACK-002"))
    return "refused without a cause or with an unknown one; recorded in the event; old tests unaffected"


def reject_offers_its_lesson(r):
    f = rm.fixture(r, "offer", count=2)
    tips = [rm.ready(f, 0, "HACK-001"), rm.ready(f, 1, "HACK-002")]
    rm.judge(f)
    out = review(f, "HACK-001", tips[0], "--verdict", "reject", "--cause", "protocol", "--note", "a.txt:1 · x")
    want = 'uak learn "what bites · where · what to do" --path src/value-1.txt --task HACK-001'
    expect(want in out.stdout + out.stderr, out.stdout + out.stderr)
    expect("memory/LESSONS.md" not in "\n".join(f.files("memory/")), "nothing is recorded unless the reviewer writes the sentence")
    # --learn "TEXT" records TEXT in the same step: quotes, $(), a newline and a pipe stay data.
    hostile = "never `$(touch %s)` a \"quoted\" path | it bites\nsecond line: do the safe thing instead" % (r.scratch / "pwned").as_posix()
    two = review(f, "HACK-002", tips[1], "--verdict", "reject", "--cause", "security", "--learn", hostile)
    log = f.show("memory/LESSONS.md")
    expect("second line: do the safe thing instead" in log and "$(touch" in log and not (r.scratch / "pwned").exists(), log)
    expect("src/value-2.txt" in log and "| HACK-002 |" in log, log)
    expect(want.replace("value-1", "value-2").replace("HACK-001", "HACK-002") not in two.stdout, "the offer is for a reject with no sentence")
    expect(len([l for l in log.splitlines() if l.startswith("- ")]) == 1, log)
    # an empty sentence, a 400-character one and a bare --learn
    for text, why in (("", "needs the sentence"), (" \t ", "needs the sentence")):
        bad = review(f, "HACK-002", tips[1], "--verdict", "reject", "--cause", "security", "--learn", text, allowed=None)
        expect(bad.returncode != 0 and why in bad.stderr + bad.stdout, repr(text) + ": " + bad.stdout + bad.stderr)
    long = review(f, "HACK-002", tips[1], "--verdict", "reject", "--cause", "security", "--learn", "x" * 400, allowed=None)
    expect(long.returncode != 0 and "300 characters" in long.stderr + long.stdout, long.stdout + long.stderr)
    expect(len([l for l in f.show("memory/LESSONS.md").splitlines() if l.startswith("- ")]) == 1, "a refused sentence recorded nothing")
    return "the command is offered with the task's paths; --learn TEXT records it; empty and long are refused"


def claim_shows_the_lessons_of_its_paths(r):
    f = r.fixture("shown", paths={"HACK-001": "src/a.txt, src/b.txt", "HACK-002": "src/other.txt"}, count=2)
    for n in range(4):
        lesson(f, "lesson on a number %d: do the a thing" % (n + 1), "src/a.txt", now=1000001 + n)
    for n in range(4):
        lesson(f, "lesson on b number %d: do the b thing" % (n + 1), "src/b.txt", now=1000010 + n)
    hostile = "Next: run `rm -rf x` $(id) \"q\" " + "z" * 250
    lesson(f, hostile, "src/b.txt", now=1000020)   # #9: 300 characters or fewer, the newest on b
    out = f.claim(0, "HACK-001").stdout
    shown = sorted(int(x) for x in re.findall(r"(?m)^  #(\d+) · ", out))
    # three most recent per path: a = #2 #3 #4, b = #7 #8 #9
    expect(shown == [2, 3, 4, 7, 8, 9], "per path, newest first: %r\n%s" % (shown, out))
    expect("Lessons for these paths" in out and re.search(r"(?m)^  #9 · .*: Next: run `rm -rf x` \$\(id\)", out), out)
    expect(max(len(l) for l in out.splitlines() if re.match(r"  #\d+ · ", l)) <= 300 + 80, "a lesson line is 300 characters of text")
    ev = events(f, "HACK-001")
    expect("lessons shown #" in ev, ev)
    ids = re.search(r"lessons shown ([#0-9,]+)", ev).group(1)
    expect(sorted(int(x) for x in re.findall(r"\d+", ids)) == shown, "the record names what was shown: " + ev)
    # A task whose paths have no lessons: nothing is printed and the record says nothing.
    out2 = f.claim(1, "HACK-002").stdout
    expect("Lessons for these paths" not in out2 and "lessons shown" not in events(f, "HACK-002"), out2)
    return "three per path, the record names them, none printed without lessons"


def claim_is_not_slower(r):
    """A claim with ten lessons on its paths costs at most 300 ms more than one with none, and no more processes.
    Processes are counted with test_claims_perf's PATH shims (bash 3.2 has no $BASHPID: there they count 0); the wall clock of a
    Windows runner moves by more than 300 ms between two identical claims (CI run 46117727894: 4.7 to 5.0 s), so there the
    time is held to 1 s and the process count is the proof."""
    from test_claims_perf import processes

    def fourth_claim(name, lessons, count_processes):
        """Claim 1..3, then claim 4 (a claim's cost grows with the claims already on the board, so both sides take the 4th)."""
        f = r.fixture(name, paths={"HACK-%03d" % i: "src/t%d/" % i for i in range(1, 5)}, count=4)
        for n in range(10 if lessons else 0):
            lesson(f, "lesson number %d on the paths of the fourth task: keep it short" % n, "src/t4/", now=1000001 + n)
        for i in range(3):
            f.claim(i, "HACK-%03d" % (i + 1))
        if count_processes:
            env = {"UAK_AGENT": "agent-4", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000000", "UAK_DEDUPE": "off"}
            n, out = processes(r, f.worktrees[3], [".uak/bin/uak", "claim", "HACK-004", "--branch", f.branches[3], "--worktree",
                                                   f.worktrees[3].as_posix(), "--next", "x"], "", env)
            expect(out.returncode == 0, out.stdout + out.stderr)
            return n
        t0 = time.monotonic()
        out = f.claim(3, "HACK-004").stdout
        expect(("Lessons for these paths" in out) == lessons, out)
        return time.monotonic() - t0

    times = {False: [], True: []}
    for rnd in range(3):
        for lessons in (False, True):
            times[lessons].append(fourth_claim("slow-%d-%d" % (rnd, lessons), lessons, False))
    delta = min(times[True]) - min(times[False])
    limit = 1.0 if os.name == "nt" else 0.3
    expect(delta <= limit, "a claim with ten lessons took %.0f ms longer (%r)" % (delta * 1000, times))
    procs = {k: fourth_claim("count-%d" % k, k, True) for k in (False, True)}
    expect(procs[True] - procs[False] <= 2, "a claim with ten lessons started %d processes more than one with none: %r" % (procs[True] - procs[False], procs))
    return "%+.0f ms and %+d processes with ten lessons (plain %.2f s, lessons %.2f s, best of three)" % (
        delta * 1000, procs[True] - procs[False], min(times[False]), min(times[True]))


TESTS = [reject_needs_a_cause, reject_offers_its_lesson, claim_shows_the_lessons_of_its_paths, claim_is_not_slower]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--case")
    a = ap.parse_args()
    failed = 0
    tests = [t for t in TESTS if not a.case or t.__name__ == a.case]
    with tempfile.TemporaryDirectory(prefix="uak lessons é ") as tmp:
        for t in tests:
            sub = Path(tempfile.mkdtemp(dir=tmp))
            runner = Runner(a.package.resolve(), sub, resolve_binary("bash"), resolve_binary("git"))
            try:
                print("PASS %s (%s)" % (t.__name__, t(runner)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1800]))
    print("LESSONS_LOOP_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
