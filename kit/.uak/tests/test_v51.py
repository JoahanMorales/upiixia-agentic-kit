#!/usr/bin/env python3
"""uak v5.1: the MLB hackathon, second autopsy (Oct 16-22 2026, the v5 week). One test per failure seen there:
review offers that waited on closed sessions, messages to identities that never came back, a human's own name
picked as reviewer, .uak-env granting human authority, approvals lost after "merge on GitHub, then pull", follow-ups
refused by their parent's OWNERS rows, merge candidates without node_modules, and the small CLI and CI errors.
Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import hack
from test_v43 import push_main
import test_review_merge as rm


def reviews(f):
    return [l for l in f.show("inbox/log.md").splitlines() if "| review |" in l]


def register(f, *names):
    rm.actor(f, "human-registrar", "register-reviewer", *names, human=True)


def review_offers_move_on(r):
    """v5 week: 67 review requests went to one named agent; that agent gave the verdict for 14. Median 55 min,
    p90 11 h to a verdict, and 22 messages asked around for a reviewer."""
    f = rm.fixture(r, "v51-offer", count=4)
    register(f, "agent-2", "agent-3", "agent-4")
    for i in (1, 2, 3):
        hack(f, i, "msg", "all", "--kind", "info", "online %d" % i, now=1000005)
    t0 = 1000010
    rm.ready(f, 0, "HACK-001")
    first = reviews(f)[-1]
    x = re.search(r"\| agent:(agent-\d) \|", first).group(1)
    hack(f, 0, "status", now=t0 + 600)
    expect(len(reviews(f)) == 1, "an offer younger than 15 min stays put")
    hack(f, 0, "status", now=t0 + 901)
    second = reviews(f)[-1]
    y = re.search(r"\| agent:(agent-\d) \|", second)
    expect(len(reviews(f)) == 2 and y and y.group(1) not in (x, "agent-1") and "| scheduler |" in second
           and "reassigned: " + x + " has not been seen since the offer" in second,
           "a lapsed offer goes to another agent, from the scheduler, saying why: " + second)
    y = y.group(1)
    start = f.hack(int(y[-1]) - 1, "review", "HACK-001", "--start", now=t0 + 905)
    expect(start.returncode == 0, start.stdout + start.stderr)
    hack(f, 0, "status", now=t0 + 1900)
    expect(len(reviews(f)) == 2, "nothing moves while someone reviews the SHA")
    hack(f, 0, "status", now=t0 + 2200)
    third = reviews(f)[-1]
    z = re.search(r"\| agent:(agent-\d) \|", third)
    expect(len(reviews(f)) == 3 and z and z.group(1) not in (x, y, "agent-1"), "a lapsed lock moves on too: " + third)
    hack(f, 0, "status", now=t0 + 3200)
    last = reviews(f)[-1]
    expect(len(reviews(f)) == 4 and "| all |" in last and "nobody started it" in last, "after 3 offers, all: " + last)
    hack(f, 0, "status", now=t0 + 4200)
    expect(len(reviews(f)) == 4, "an offer to all is final")
    return {"offers": 4}


def humans_and_stale_identities_get_no_review(r):
    """A human's bare name (an identity through `uak plan`) was picked as reviewer next to its -1..-7; identities whose
    sessions closed hours ago kept getting reviews by rotation."""
    f = rm.fixture(r, "v51-human", count=3)
    hack(f, 2, "msg", "all", "--kind", "info", "agent-3 was here", now=1000005)        # stale by the time of done
    hack(f, 1, "msg", "all", "--kind", "info", "agent-2 online", now=1011000)
    rm.actor(f, "agent", "msg", "all", "--kind", "info", "the human, as an identity", now=1011001)
    f.claim(0, "HACK-001", now=1011002)
    rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1011010)
    last = reviews(f)[-1]
    expect("agent:agent-2" in last, "the online agent is picked, not the human 'agent' nor the stale agent-3: " + last)
    return {"picked": "agent-2"}


def offline_recipients_and_orphans(r):
    """26 requests and review offers went to identities that never came back; one human ran 8 identities and the
    live one never saw what reached the closed ones."""
    f = rm.fixture(r, "v51-orphans", count=3)
    hack(f, 2, "claim", "HACK-003", "--branch", f.branches[2], "--worktree", f.worktrees[2].as_posix(),
         "--next", "seguir", now=1000000, UAK_LEASE_SECONDS="20000")
    sent = hack(f, 0, "msg", "agent-3", "need the parser shape", "--kind", "request", now=1004000)
    expect("agent-3 was last seen 66 min ago: also sent to its task HACK-003" in sent.stdout, sent.stdout + sent.stderr)
    line = [l for l in f.show("inbox/log.md").splitlines() if "need the parser shape" in l][0]
    expect("agent:agent-3,task:HACK-003" in line, "an offline owner's task gets the message too: " + line)
    ghost = hack(f, 0, "msg", "agnet-9", "typo", now=1004001)
    expect("never been seen on claims (a typo?)" in ghost.stdout, ghost.stdout)
    nxt = hack(f, 1, "next", now=1004010)
    expect("For your offline identities" in nxt.stdout and "for agent-3" in nxt.stdout and "need the parser shape" in nxt.stdout,
           "next shows what waits for an offline identity of the same human: " + nxt.stdout)
    refused = rm.actor(f, "judge", "handover", "HACK-003", "--to", "judge", now=1004020, allowed=None)
    expect(refused.returncode == 3, "another human's identity cannot take a live task: " + refused.stdout + refused.stderr)
    taken = hack(f, 1, "handover", "HACK-003", "--to", "agent-2", now=1004030, allowed=None)
    expect(taken.returncode == 0 and "Owner: agent-2" in f.show("claims/HACK-003.md"),
           "the same human's live identity takes over after 1 h offline: " + taken.stdout + taken.stderr)
    return {"rerouted": True, "orphans": True, "handover": True}


def worktree_env_is_not_a_human(r):
    """.uak-env carried UAK_HUMAN into every agent's shell, so any agent in a task worktree passed the human gates."""
    f = rm.fixture(r, "v51-env", count=1)
    (f.worktrees[0] / ".uak-env").write_text("UAK_AGENT=agent-1\nUAK_HUMAN=boss\nUAK_TASK=HACK-001\n", encoding="utf-8")
    denied = f.hack(0, "allow", "HACK-001", "--reason", "demo fix", allowed=None)
    expect(denied.returncode == 3 and "human decision" in denied.stderr, "no authority from .uak-env: " + denied.stdout + denied.stderr)
    ok = f.r.run([f.r.bash, ".uak/bin/uak", "allow", "HACK-001", "--reason", "demo fix"], cwd=f.worktrees[0],
                 env={"UAK_AGENT": "agent-1", "UAK_HUMAN": "boss", "UAK_NOW": "1000001"})
    expect(ok.returncode == 0, "an explicit UAK_HUMAN still works: " + ok.stdout + ok.stderr)
    f.claim(0, "HACK-001", now=1000002)
    expect("Human: boss" in f.show("meta/agents/agent-1.md"), "the agent's human is recorded for presence")
    return {"authority": "explicit only"}


def approval_survives_forge_merge_and_pull(r):
    """The PR was merged on GitHub, then the branch fast-forwarded to main and pushed: integrate refused the
    approval as stale (8 refusals, 2 black box notes)."""
    f = rm.fixture(r, "v51-ff", count=2)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f); rm.approve(f, "HACK-001", tip)
    push_main(f, {"docs/other.md": "main moved on\n"}, "unrelated work on main")
    forge = f.base / "forge"
    r.g(f.base, "clone", "-q", f.remote, forge)
    r.g(forge, "config", "user.name", "Forge"); r.g(forge, "config", "user.email", "forge@example.invalid")
    r.g(forge, "merge", "--no-ff", "-m", "Merge pull request #1", "origin/" + f.branches[0])
    r.g(forge, "push", "-q", "origin", "HEAD:main")
    w = f.worktrees[0]
    r.g(w, "fetch", "-q", "origin")
    r.g(w, "merge", "--ff-only", "origin/main")
    r.g(w, "push", "-q", "origin", f.branches[0])
    out = f.hack(1, "integrate", "HACK-001", now=1000040, allowed=None)
    expect(out.returncode == 0 and "INTEGRATED" in f.show("tasks/HACK-001.md"),
           "the approval carries through the PR's own merge commit: " + out.stdout + out.stderr)
    return {"integrated": True}


def followup_owns_the_parent_paths(r):
    """Every `uak followup` of a task that owned paths in OWNERS.md was refused (4 black box notes)."""
    f = rm.fixture(r, "v51-followup", count=2)
    project = (f.seed / ".uak/PROJECT.md").read_text(encoding="utf-8") + "Plan-Channel: claims\n"
    push_main(f, {".uak/PROJECT.md": project,
                  ".uak/OWNERS.md": "# Owners\n\n| Pattern | Owner task |\n|---|---|\n| `src/value-1.txt` | HACK-001 |\n"},
              "HACK-001 owns its file")
    for w in f.worktrees:
        r.g(w, "merge", "-q", "--no-edit", "origin/main")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f); rm.approve(f, "HACK-001", tip)
    merged = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    expect(merged.returncode == 0, merged.stdout + merged.stderr)
    fu = f.hack(0, "followup", "HACK-001", "--title", "polish the copy", now=1000031)
    new_id = re.search(r"OK followup (\S+)", fu.stdout).group(1)
    r.g(f.worktrees[1], "fetch", "-q", "origin")
    r.g(f.worktrees[1], "merge", "-q", "--no-edit", "origin/main")
    c = f.claim(1, new_id, now=1000032, allowed=None)
    expect(c.returncode == 0, "a follow-up works on its parent's owned paths: " + c.stdout + c.stderr)
    return {"followup": new_id}


def merge_gate_links_node_modules(r):
    """3 merges went to the human queue with "vitest: command not found": the candidate clone had no node_modules."""
    f = rm.fixture(r, "v51-node", count=2)
    push_main(f, {"web/package.json": '{"name": "w", "version": "1.0.0"}\n',
                  "web/package-lock.json": '{"name": "w", "lockfileVersion": 3}\n',
                  ".uak/bin/smoke-project": "#!/usr/bin/env bash\nset -eu\ntest -f web/node_modules/fakepkg/index.js\n"},
              "web app with a lockfile")
    for w in f.worktrees:
        r.g(w, "merge", "-q", "--no-edit", "origin/main")
    nm = f.worktrees[0] / "web/node_modules/fakepkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f); rm.approve(f, "HACK-001", tip)
    out = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout, "the gate sees the worktree's node_modules: " + out.stdout + out.stderr)
    expect((nm / "index.js").exists(), "cleaning the candidate never deletes the real node_modules")
    tree = r.g(f.remote, "ls-tree", "-r", "--name-only", "main").stdout
    expect("node_modules" not in tree, "the link is never committed")
    return {"linked": True}


def small_fixes(r):
    """impact with no importers was an error, guessed command names failed, a PR link named another repository,
    the guard read "-DATA" in a clone URL as branch -D, an old worktree kit went unnoticed, and the product CI failed on uak-mcp."""
    f = rm.fixture(r, "v51-small", count=2)
    none = f.hack(0, "msg", "impact:HACK-002", "--kind", "contract", "shape changed", allowed=None)
    expect(none.returncode == 0 and "no contract needed" in none.stdout, none.stdout + none.stderr)
    for args in (["tasks"], ["task", "HACK-001"], ["status", "--verbose"], ["next", "--all"]):
        res = f.hack(0, *args, allowed=None)
        expect(res.returncode == 0, " ".join(args) + ": " + res.stdout + res.stderr)
    w = f.worktrees[0]
    r.g(w, "config", "url." + f.remote.as_posix() + ".insteadOf", "git@github.com:team/app.git")
    r.g(w, "remote", "set-url", "origin", "git@github.com:team/app.git")
    gh = {"GIT_CONFIG_COUNT": "3", "GIT_CONFIG_KEY_2": "url." + f.remote.as_posix() + ".insteadOf",
          "GIT_CONFIG_VALUE_2": "git@github.com:team/app.git"}   # the temp repos of uak see the same rewrite
    hack(f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", w.as_posix(), "--next", "x", **gh)
    rm.publish(f, 0, "HACK-001")
    wrong = hack(f, 0, "done", "HACK-001", "--pr", "https://github.com/someone/other-repo/compare/main...x",
                 "--evidence", "ok", now=1000010, allowed=None, **gh)
    expect(wrong.returncode == 2 and "github.com/team/app" in wrong.stderr and "wt pr" in wrong.stderr, wrong.stderr)
    right = hack(f, 0, "done", "HACK-001", "--pr", "https://github.com/Team/App/compare/main...task/agent-1",
                 "--evidence", "ok", now=1000011, allowed=None, **gh)
    expect(right.returncode == 0, "the right repository passes (any case): " + right.stdout + right.stderr)
    for cmd, blocked in (("git clone --branch main git@github.com:x/app-DATA.git", False),
                         ("git branch -D feat/x", True), ("git -C ../r branch -D x", True), ("git branch -d x", False)):
        res = r.run([r.bash, ".uak/bin/guard", "check", cmd], cwd=f.worktrees[1], allowed=None)
        expect((res.returncode != 0) == blocked, cmd + ": " + res.stdout + res.stderr)
    push_main(f, {".uak/VERSION": "9.9.9\n"}, "kit upgrade")
    skew = f.hack(1, "next", now=1000020)
    expect("KIT: this worktree runs uak" in skew.stdout and "has 9.9.9" in skew.stdout, skew.stdout)
    step = (r.package / ".github/workflows/uak.yml").read_text(encoding="utf-8").split("- name: Kit syntax", 1)[1]
    script = step.split("run: |", 1)[1].split("- name:", 1)[0]
    script = "\n".join(l[10:] for l in script.splitlines() if l.strip())
    ci = r.run([r.bash, "-c", "set -e\n" + script], cwd=f.seed, allowed=None)
    expect(ci.returncode == 0, "the product CI syntax step passes on the kit itself: " + ci.stdout + ci.stderr)
    return {"small": True}


def identities_are_reused(r):
    """One human ran 8 identities: each new agent took the next number while closed ones kept their inbox."""
    f = rm.fixture(r, "v51-ids", count=2)
    main = f.clones[0]
    env = {"UAK_AGENT": "", "UAK_HUMAN": "", "UAK_NOW": "1000000"}
    one = r.run([r.bash, ".uak/bin/wt", "new", "HACK-002"], cwd=main, env=env, allowed=None)
    expect(one.returncode == 0 and "new identity fixtureagent-1" in one.stderr, one.stdout + one.stderr)
    wt2 = Path(re.search(r"Worktree: (\S+)", one.stdout).group(1)) if "Worktree: " in one.stdout else \
        main.parent / (main.name + "-wt") / "hack-002"
    rel = r.run([r.bash, ".uak/bin/uak", "release", "HACK-002"], cwd=wt2, env={"UAK_NOW": "1000001"}, allowed=None)
    expect(rel.returncode == 0, rel.stdout + rel.stderr)
    two = r.run([r.bash, ".uak/bin/wt", "new", "HACK-001"], cwd=main, env={**env, "UAK_NOW": "1000002"}, allowed=None)
    expect(two.returncode == 0 and "reusing fixtureagent-1" in two.stderr, "a free identity of this machine is reused: " + two.stdout + two.stderr)
    expect("Owner: fixtureagent-1" in f.show("claims/HACK-001.md"), "the claim is under the reused name")
    return {"reused": "fixtureagent-1"}


TESTS = [review_offers_move_on, humans_and_stale_identities_get_no_review, offline_recipients_and_orphans,
         worktree_env_is_not_a_human, approval_survives_forge_merge_and_pull, followup_owns_the_parent_paths,
         merge_gate_links_node_modules, small_fixes, identities_are_reused]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v51-") as tmp:
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
    print("V51_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
