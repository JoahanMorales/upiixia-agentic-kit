#!/usr/bin/env python3
"""uak v5.7: what the v5.6.0 audit left open. Claims trust (authority keys, the gate's Verify and Paths, ghost
approvals, the owner's own human, secrets), messages (task threads, reviewer eligibility, humans by name, wait,
inbox caps), claims (handover after the push, stale owners, braces and [slug] paths, Depends on lists, damaged
leases, amend after a reject, integrated owners), human decisions, criteria in status, review --decline and the
merge lock. Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm
from test_v55 import write_claims

PROJECT = ("# Fixture humana\nAutonomy: yes\nAuto-Merge: yes\nBacklog-Approved: yes\n"
           "Backlog-Proposed-Epoch: 1000000\nFreeze-Epoch: 9999999\nReview-Mode: claims\n"
           "Events-Per-Session: 100000\nCheckpoint-Percent: 60\n"
           "Merge-Lease-Seconds: 1800\nMerge-Wait-Seconds: 600\n")


def set_project(f, text):
    """Rewrite .uak/PROJECT.md on main, as a human's PR would."""
    (f.seed / ".uak/PROJECT.md").write_text(text, encoding="utf-8")
    f.r.g(f.seed, "add", ".uak/PROJECT.md")
    f.r.g(f.seed, "commit", "-q", "-m", "PROJECT.md")
    f.r.g(f.seed, "push", "-q", "origin", "main")
    for clone, worktree in zip(f.clones, f.worktrees):
        f.r.g(clone, "fetch", "-q", "origin", "main")
        f.r.g(worktree, "merge", "-q", "--ff-only", "origin/main", allowed=None)


def run_as(f, index, *args, agent=None, human="", now=1000020, allowed=(0,), env=None):
    e = {"UAK_AGENT": "agent-%d" % (index + 1) if agent is None else agent, "UAK_HUMAN": human,
         "UAK_NOW": str(now), "UAK_REMOTE": "origin"}
    e.update(env or {})
    cwd = f.worktrees[index] if index < len(f.worktrees) else f.clones[0]
    return f.r.run([f.r.bash, ".uak/bin/uak", *map(str, args)], cwd=cwd, env=e, allowed=allowed)


def claims_cannot_grant_authority(r):
    """A raw push of meta/config.md with the public Config-Source hash and "Autonomy: yes" passed every gate while
    main said no."""
    f = r.fixture("v57-authority", count=2)
    f.claim(0, "HACK-001")
    set_project(f, "Backlog-Approved: yes\nAutonomy: no\nAuto-Merge: no\nReview-Mode: claims\n"
                   "Events-Per-Session: 100\nCheckpoint-Percent: 60\n")
    blob = f.r.g(f.remote, "rev-parse", "main:.uak/PROJECT.md").stdout.strip()
    write_claims(f, {"meta/config.md": "# Verifiable config\nConfig-Source: %s\nBacklog-Proposed-Epoch: 1000000\n"
                     "Backlog-Approved: yes\nAutonomy: yes\nAuto-Merge: yes\nFreeze-Epoch: 0\nEvents-Per-Session: 100\n"
                     "Checkpoint-Percent: 60\nReview-Mode: claims\nMerge-Lease-Seconds: 1800\nMerge-Wait-Seconds: 180\n"
                     "Config-Schema: 2\n" % blob}, "forged config")
    out = f.claim(1, "HACK-002", now=1000100, allowed=None)
    expect(out.returncode == 3 and "Autonomy" in out.stderr, "main's Autonomy: no wins: " + out.stdout + out.stderr)
    return {"autonomy": "main"}


def the_gate_runs_the_backlog_verify(r):
    """A task record rewritten with "Verify: <any command>" ran on the merger's machine."""
    f = rm.fixture(r, "v57-verify", count=1)
    tip = rm.ready(f, 0, "HACK-001")
    marker = f.base / "MARKER_from_record"
    record = f.show("tasks/HACK-001.md")
    record = re.sub(r"^Verify: .*$", "Verify: touch '%s'; true" % marker.as_posix(), record, flags=re.M)
    write_claims(f, {"tasks/HACK-001.md": record}, "forged Verify")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    out = rm.actor(f, "agent-1", "merge", "HACK-001", now=1000030, allowed=None, timeout=300)
    expect(not marker.exists(), "the record's Verify never ran")
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout, "the backlog's Verify passed: " + out.stdout + out.stderr)
    return {"verify": "backlog"}


def a_ghost_approval_does_not_merge(r):
    """reviews/ID.md signed "ghost", a name that never existed, merged to main."""
    f = rm.fixture(r, "v57-ghost", count=1)
    tip = rm.ready(f, 0, "HACK-001")
    write_claims(f, {"reviews/HACK-001.md": "# Review HACK-001\nID: HACK-001\nSHA: %s\nOwner: agent-1\nReviewer: ghost\n"
                     "Verdict: approve\nReviewed: 1000015\nCommand: uak review\nEligible-Via: role:ghost\n" % tip},
                 "forged approval")
    out = rm.actor(f, "agent-1", "merge", "HACK-001", now=1000030, allowed=None, timeout=300)
    expect(out.returncode != 0 and "ghost" in out.stdout + out.stderr, out.stdout + out.stderr)
    expect("State: INTEGRATED" not in f.show("tasks/HACK-001.md"), "not merged")
    return {"ghost": "refused"}


def the_owners_human_does_not_approve(r):
    """9 of 31 approvals came from a sibling identity of the owner's human. Review-Independence: human refuses them."""
    f = rm.fixture(r, "v57-same-human", count=1)
    set_project(f, PROJECT + "Review-Independence: human\n")
    tip = rm.ready(f, 0, "HACK-001")
    rm.actor(f, "human-registrar", "register-reviewer", "agent-7", human=True)
    rm.approve(f, "HACK-001", tip, name="agent-7")
    out = rm.actor(f, "agent-1", "merge", "HACK-001", now=1000030, allowed=None, timeout=300)
    expect(out.returncode != 0 and "same human" in out.stdout + out.stderr, out.stdout + out.stderr)
    return {"independence": "human"}


def claims_refuse_a_secret(r):
    """A key pasted into uak msg was committed to claims, which every clone reads."""
    f = r.fixture("v57-secret", count=1)
    f.claim(0, "HACK-001")
    key = "sk-" + "proj-" + "ab12CD34ef56GH78ij90KL12"
    out = f.hack(0, "msg", "all", "--kind", "info", "the key is " + key, now=1000010, allowed=None)
    expect(out.returncode == 3 and "looks like a secret" in out.stderr, out.stdout + out.stderr)
    expect(key not in f.show("inbox/log.md") if "inbox/log.md" in f.files("inbox") else True, "nothing on claims")
    ok = f.hack(0, "msg", "all", "--kind", "info", "task-assignment-notification-service ready at abc1234", now=1000011)
    expect(ok.returncode == 0, "a feature name is not a key: " + ok.stderr)
    return {"secret": "refused"}


def a_task_thread_reaches_its_next_owner(r):
    """A request "sent to its task, so whoever takes it over reads it" never reached the next owner."""
    f = r.fixture("v57-thread", count=3)
    f.claim(0, "HACK-001")
    f.hack(2, "msg", "HACK-001", "--kind", "request", "please change src/one.txt line 3", now=1000010)
    f.hack(2, "msg", "agent-2", "--kind", "info", "agent-2: the fixture runs at src/two.txt", now=1000015)
    acked = f.hack(1, "inbox", "--ack", now=1000020)
    expect("INBOX_ACK up to #2" in acked.stdout, "agent-2's pointer is past the request: " + acked.stdout)
    run_as(f, 0, "handover", "HACK-001", "--to", "agent-2", agent="", human="boss", now=1000030)
    box = f.hack(1, "inbox", now=1000040)
    expect("please change src/one.txt line 3" in box.stdout, box.stdout)
    f.hack(1, "inbox", "--ack", now=1000050)
    again = f.hack(1, "inbox", now=1000060)
    expect("please change" not in again.stdout, "acked once: " + again.stdout)
    return {"thread": "delivered"}


def reviews_go_to_who_can_review(r):
    """Offers went to identities with no claim, whose --start was refused; each cost a 15-min re-offer window."""
    f = rm.fixture(r, "v57-eligible", count=3)
    f.claim(1, "HACK-002")
    f.hack(1, "msg", "all", "--kind", "info", "agent-2 on HACK-002 at src/value-2.txt", now=1000004)
    f.hack(2, "msg", "all", "--kind", "info", "agent-3 here, no task yet (src/)", now=1000005)
    rm.ready(f, 0, "HACK-001")
    offer = [l for l in f.show("inbox/log.md").splitlines() if "| review | HACK-001 |" in l][-1]
    expect("| agent:agent-2 |" in offer, "the idle identity with no claim is skipped: " + offer)
    return {"reviewer": "agent-2"}


def a_human_named_reads_it_in_the_digest(r):
    """"uak msg victor" went to agent:victor, which victor's digest never shows."""
    f = r.fixture("v57-human-name", count=1)
    f.claim(0, "HACK-001")
    run_as(f, 0, "msg", "all", "--kind", "info", "hello from the human", agent="", human="victor", now=1000005)
    f.hack(0, "msg", "victor", "--kind", "request", "need approval to buy the domain", now=1000010)
    line = [l for l in f.show("inbox/log.md").splitlines() if "buy the domain" in l][-1]
    expect("| human | request |" in line, line)
    return {"to": "human"}


def wait_returns_only_on_new_messages(r):
    """15 unread messages already shown made every wait return in a second, and the agent polled."""
    f = r.fixture("v57-wait", count=2)
    f.claim(0, "HACK-001")
    f.hack(1, "msg", "agent-1", "--kind", "request", "an old request", now=1000010)
    out = f.r.run([f.r.bash, ".uak/bin/uak", "wait", "--for", "message", "--timeout", "3"], cwd=f.worktrees[0],
                  env={"UAK_AGENT": "agent-1", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}, allowed=None)
    expect(out.returncode == 4 and "WAIT_TIMEOUT" in out.stdout and "from before this wait" in out.stdout,
           out.stdout + out.stderr)
    return {"wait": "new only"}


def inbox_acks_only_what_it_showed(r):
    """The output cap hid the middle of a long inbox, and --ack acked messages nobody had seen."""
    f = r.fixture("v57-inbox-cap", count=2)
    f.claim(0, "HACK-001")
    for i in range(18):
        f.hack(1, "msg", "agent-1", "--kind", "info", "note number %d at src/x.txt" % i, now=1000010 + i)
    first = f.hack(0, "inbox", "--ack", now=1000100)
    expect("the first 15 here" in first.stdout and "+3 more" in first.stdout, first.stdout)
    rest = f.hack(0, "inbox", now=1000110)
    expect("note number 15" in rest.stdout and "note number 17" in rest.stdout and "note number 3 " not in rest.stdout,
           rest.stdout)
    return {"cap": 15}


def handover_rewrites_the_worktree_after_the_push(r):
    """A refused push left .uak-env naming the new owner while claims still said the old one."""
    f = r.fixture("v57-handover-env", count=2)
    f.claim(0, "HACK-001")
    env = f.worktrees[0] / ".uak-env"
    env.write_text("UAK_AGENT=agent-1\nUAK_TASK=HACK-001\n", encoding="utf-8")
    hook = f.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho refused by policy >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    bad = f.hack(0, "handover", "HACK-001", "--to", "agent-2", now=1000010, allowed=None)
    expect(bad.returncode != 0, bad.stdout + bad.stderr)
    expect("UAK_AGENT=agent-1" in env.read_text(encoding="utf-8"), "unchanged after a refused push")
    hook.unlink()
    f.hack(0, "handover", "HACK-001", "--to", "agent-2", now=1000020)
    expect("UAK_AGENT=agent-2" in env.read_text(encoding="utf-8"), "rewritten after the push")
    return {"env": "after push"}


def a_released_owner_is_told_to_stop(r):
    """After another agent released the expired lease, the old owner's heartbeat said OK and its checkpoint rewrote
    the summary the next owner inherits."""
    f = r.fixture("v57-stale-owner", count=2)
    f.claim(0, "HACK-001")
    late = 1000000 + 200000
    status = f.hack(1, "status", "--task", "HACK-001", "--summary", now=late)
    token = re.search(r"Read-token: (\S+)", status.stdout).group(1)
    f.hack(1, "release", "HACK-001", "--expired", "--read-summary", token, now=late + 1)
    hb = f.hack(0, "heartbeat", "HACK-001", now=late + 10, allowed=None)
    expect(hb.returncode == 3 and "agent-2 released it" in hb.stderr, hb.stdout + hb.stderr)
    cp = f.hack(0, "checkpoint", "HACK-001", "--done", "x", "--decision", "-", "--why", "-", "--fails", "-",
                "--commands", "-", "--next", "y", now=late + 11, allowed=None)
    expect(cp.returncode == 3, "no checkpoint on a task taken from it: " + cp.stdout + cp.stderr)
    return {"stale": "conflict"}


def braces_and_route_segments_reserve_what_they_name(r):
    """src/{api,web}/** let two claims share src/api; app/[slug] made app/about collide."""
    f = r.fixture("v57-paths", count=4, paths={"HACK-001": "src/{api,web}/**", "HACK-002": "src/api/handler.ts",
                                              "HACK-003": "app/[slug]/page.tsx", "HACK-004": "app/about/page.tsx"})
    f.claim(0, "HACK-001")
    two = f.claim(1, "HACK-002", allowed=None)
    expect(two.returncode == 3 and "overlap" in (two.stdout + two.stderr).lower(), two.stdout + two.stderr)
    f.claim(2, "HACK-003")
    f.claim(3, "HACK-004")
    return {"braces": "expanded"}


def depends_on_as_a_list_counts(r):
    """A Depends on written as a list, or as hack-001, was ignored and the task was claimed first."""
    f = r.fixture("v57-depends", count=2, dependencies={"HACK-002": "\n  - hack-001"})
    out = f.claim(1, "HACK-002", allowed=None)
    expect(out.returncode == 3 and "HACK-001" in out.stderr, out.stdout + out.stderr)
    return {"depends": "list"}


def a_damaged_lease_does_not_stop_the_team(r):
    """One non-numeric Lease-Until in any claim made every command of every agent die."""
    f = r.fixture("v57-damaged", count=2)
    f.claim(0, "HACK-001")
    write_claims(f, {"claims/HACK-003.md": "# HACK-003\nID: HACK-003\nState: CLAIMED\nOwner: x-1\nLease-Until: soon\n"},
                 "a damaged claim")
    f.claim(1, "HACK-002", now=1000010)
    return {"lease": "tolerated"}


def a_rejected_task_can_be_amended(r):
    """"A reviewer rejects it first" never made amend possible (a reject kept REVIEW): the human merged on GitHub
    over the reject instead."""
    f = rm.fixture(r, "v57-amend", count=1)
    set_project(f, PROJECT + "Plan-Channel: claims\n")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, verdict="reject")
    plan = f.base / "amend.md"
    plan.write_text("## HACK-001 · fixture\n- **Priority:** P0\n- **Paths:** src/value-1.txt, src/extra.txt\n"
                    "- **Depends on:** none\n- **Verify:** test \"$(cat src/value-1.txt)\" = ready-HACK-001\n", encoding="utf-8")
    out = rm.actor(f, "boss", "plan", str(plan), "--amend", human=True, now=1000040, allowed=None)
    expect(out.returncode == 0, out.stdout + out.stderr)
    expect("State: CLAIMED" in f.show("tasks/HACK-001.md"), "back to its owner")
    return {"amend": "after reject"}


def an_integrated_owner_row_is_advice(r):
    """A bug in lib/sse.ts, owned by an integrated task, stayed on main while 5 views copied a workaround."""
    f = r.fixture("v57-owners", count=2, paths={"HACK-001": "src/shared/a.txt", "HACK-002": "src/shared/b.txt",
                                                "HACK-003": "src/other.txt"}, owners={"src/shared/": "HACK-001"})
    f.claim(0, "HACK-003")
    blocked = f.claim(1, "HACK-002", allowed=None)
    expect(blocked.returncode == 3, "the owner row still locks while HACK-001 is to do")
    write_claims(f, {"tasks/HACK-001.md": "# HACK-001\nID: HACK-001\nState: INTEGRATED\nOwner: agent-1\nUpdated: 1000001\n"},
                 "HACK-001 integrated")
    ok = f.claim(1, "HACK-002", now=1000010, allowed=None)
    expect(ok.returncode == 0 and "already INTEGRATED" in ok.stdout, ok.stdout + ok.stderr)
    return {"owners": "advice"}


def status_shows_criteria_and_a_human_decides(r):
    """Reviewers judged "from the summary" (nothing printed the criteria), and a human's uak decision was refused
    ("has no active claim")."""
    f = r.fixture("v57-criteria", count=1)
    out = f.hack(0, "status", "--task", "HACK-001")
    expect("Criteria:" in out.stdout and "salida comprobable" in out.stdout and "Paths: src/one.txt" in out.stdout,
           out.stdout)
    d = run_as(f, 0, "decision", "HACK-001", "--option", "use the mock", "--why", "no key yet", "--reversible", "yes",
               "--authorized", "yes", "--class", "routine", agent="", human="boss", now=1000005, allowed=None)
    expect(d.returncode == 0, d.stdout + d.stderr)
    expect(any(p.startswith("meta/decisions/HACK-001-") for p in f.files("meta/decisions")), "recorded")
    bad = f.hack(0, "checkpoint", "--summary", "x", allowed=None)
    expect("Usage: checkpoint" in bad.stderr, "a flag in the ID's place says the usage: " + bad.stderr)
    return {"criteria": True}


def a_declined_review_moves_at_once(r):
    """A reviewer declined by message as the review skill said, and the re-offer came 8.5 min later."""
    f = rm.fixture(r, "v57-decline", count=3)
    f.claim(1, "HACK-002")
    f.claim(2, "HACK-003")
    f.hack(1, "msg", "all", "--kind", "info", "agent-2 on HACK-002 at src/value-2.txt", now=1000004)
    f.hack(2, "msg", "all", "--kind", "info", "agent-3 on HACK-003 at src/value-3.txt", now=1000005)
    rm.ready(f, 0, "HACK-001")
    first = [l for l in f.show("inbox/log.md").splitlines() if "| review | HACK-001 |" in l][-1]
    who = re.search(r"\| agent:(agent-\d)", first).group(1)
    other = "agent-3" if who == "agent-2" else "agent-2"
    out = f.hack(int(who[-1]) - 1, "review", "HACK-001", "--decline", now=1000030)
    expect("offered to another agent" in out.stdout, out.stdout + out.stderr)
    last = [l for l in f.show("inbox/log.md").splitlines() if "| review | HACK-001 |" in l][-1]
    expect("| agent:%s |" % other in last and "declined" in last, last)
    return {"declined": who}


def a_merger_takes_back_its_own_lock(r):
    """An agent held the merge lock for the full 30 min and its own retries could not reclaim it."""
    f = rm.fixture(r, "v57-relock", count=1)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    write_claims(f, {"queue/merge-lock.md": "Owner: agent-1\nTask: HACK-001\nToken: hack.OLD123-agent-1-HACK-001\n"
                     "Lease-Until: 1009999\nUpdated: 1000022\n"}, "an interrupted merge left its lock")
    out = rm.actor(f, "agent-1", "merge", "HACK-001", now=1000030, allowed=None, timeout=300)
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout, out.stdout + out.stderr)
    return {"lock": "reclaimed"}


TESTS = [claims_cannot_grant_authority, the_gate_runs_the_backlog_verify, a_ghost_approval_does_not_merge,
         the_owners_human_does_not_approve, claims_refuse_a_secret, a_task_thread_reaches_its_next_owner,
         reviews_go_to_who_can_review, a_human_named_reads_it_in_the_digest, wait_returns_only_on_new_messages,
         inbox_acks_only_what_it_showed, handover_rewrites_the_worktree_after_the_push, a_released_owner_is_told_to_stop,
         braces_and_route_segments_reserve_what_they_name, depends_on_as_a_list_counts,
         a_damaged_lease_does_not_stop_the_team, a_rejected_task_can_be_amended, an_integrated_owner_row_is_advice,
         status_shows_criteria_and_a_human_decides, a_declined_review_moves_at_once, a_merger_takes_back_its_own_lock]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v57-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("V57_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
