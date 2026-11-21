#!/usr/bin/env python3
"""UAK-114: `integrate` of a task whose content is on main with no valid approval. Sprint: an agent records it as before
(the board must tell the truth during an event), the record keeps Integrated-Outside: yes and adds Unreviewed: yes, and
the output says the code reached main without a review. Marathon: a human records it (UAK_HUMAN=NAME ... --reason TEXT,
the reason goes to DECISIONS.md); an agent gets a refusal with the line the human runs. A valid approval of that SHA by
another seen identity lets an agent integrate in both modes with no Unreviewed field. stats counts the unreviewed.
Why (audit of v6.5.0, #7). Real Git, a local bare remote; the fixtures of test_integrate_outside."""
import argparse
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_integrate_outside import (approve, claimed_with_pushed_work, commit_file, fx, integrate, record, seed,
                                    seed_pull, squash_into_main, task_in_review)


def landed(r, name):
    """HACK-001 claimed by agent-1 with two files pushed; the same two files land on main by another commit."""
    f = fx(r, name)
    claimed_with_pushed_work(r, f, "bytes\n", second="second\n")
    seed_pull(r, f)
    commit_file(r, f.seed, "src/one.txt", "bytes\n", "landed by another commit")
    commit_file(r, f.seed, "src/two.txt", "second\n", "landed too")
    seed(r, f, "push", "-q", "origin", "main")
    return f


def marathon(r, f):
    """Mode: marathon on main (the guard reads PROJECT.md on the remote base)."""
    seed_pull(r, f)
    p = f.seed / ".uak" / "PROJECT.md"
    p.write_text("Mode: marathon\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    r.g(f.seed, "add", ".uak/PROJECT.md")
    r.g(f.seed, "commit", "-q", "-m", "Mode: marathon")
    seed(r, f, "push", "-q", "origin", "main")


def human(r, f, *extra):
    return r.run([r.bash, ".uak/bin/uak", "integrate", "HACK-001", *extra], cwd=f.clones[0], env={
        "UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_NOW": "1000100", "UAK_REMOTE": "origin"}, allowed=None)


def sprint_agent_integrates_and_record_says_unreviewed(r):
    f = landed(r, "iu-sprint")
    out = integrate(f, agent=0)
    text = out.stdout + out.stderr
    expect(out.returncode == 0, "sprint: an agent records it: rc %d %s" % (out.returncode, text[-500:]))
    expect("without a review" in text, "the output says it: " + text)
    rec = record(f, "HACK-001")
    expect("State: INTEGRATED" in rec and "Integrated-Outside: yes" in rec and "Unreviewed: yes" in rec, "record: " + rec)
    return "Unreviewed: yes"


def marathon_agent_is_refused(r):
    f = landed(r, "iu-marathon-agent")
    marathon(r, f)
    out = integrate(f, agent=0)
    text = out.stdout + out.stderr
    expect(out.returncode != 0, "marathon: an agent is refused: " + text)
    expect("UAK_HUMAN=NAME" in text and "uak integrate HACK-001" in text and "--reason" in text, "it names the human line: " + text)
    expect("State: INTEGRATED" not in record(f, "HACK-001"), "not recorded: " + record(f, "HACK-001"))
    return "refused"


def marathon_human_records_it_with_a_reason(r):
    f = landed(r, "iu-marathon-human")
    marathon(r, f)
    out = human(r, f)
    expect(out.returncode != 0 and "--reason" in out.stdout + out.stderr, "a human needs a reason: " + out.stdout + out.stderr)
    out = human(r, f, "--reason", "merged on GitHub during the event")
    expect(out.returncode == 0, "the human records it: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    rec = record(f, "HACK-001")
    expect("State: INTEGRATED" in rec and "Integrated-Outside: yes" in rec and "Unreviewed: yes" in rec, "record: " + rec)
    expect("merged on GitHub during the event" in f.show("DECISIONS.md"), "the reason is in DECISIONS.md: " + f.show("DECISIONS.md"))
    return "reason recorded"


def approved_sha_integrates_in_both_modes(r):
    for mode in ("sprint", "marathon"):
        f = fx(r, "iu-approved-" + mode)
        tip = task_in_review(r, f)
        approve(r, f, "HACK-001", tip)
        squash_into_main(r, f, f.branches[0])
        if mode == "marathon":
            marathon(r, f)
        out = integrate(f)
        expect(out.returncode == 0, "%s: approved work is recorded by an agent: rc %d %s" % (mode, out.returncode, (out.stdout + out.stderr)[-500:]))
        rec = record(f, "HACK-001")
        expect("State: INTEGRATED" in rec and "Unreviewed" not in rec, "%s: no Unreviewed field: %s" % (mode, rec))
        expect("without a review" not in out.stdout + out.stderr, "%s: nothing says it was unreviewed" % mode)
    return "both modes"


def stats_counts_unreviewed(r):
    f = landed(r, "iu-stats")
    expect(integrate(f, agent=0).returncode == 0, "integrate")
    out = f.hack(0, "stats", allowed=None)
    expect("outside the gate: 1" in out.stdout and "unreviewed: 1" in out.stdout, "stats: " + out.stdout + out.stderr)
    return "stats line"


TESTS = [sprint_agent_integrates_and_record_says_unreviewed, marathon_agent_is_refused,
         marathon_human_records_it_with_a_reason, approved_sha_integrates_in_both_modes, stats_counts_unreviewed]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="uak-integrate-unreviewed-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ != args.case:
                continue
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("INTEGRATE_UNREVIEWED_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
