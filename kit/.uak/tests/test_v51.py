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
from test_coordination import config, hack
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


AMEND_BASE = """# Wave 2

## HACK-005 — Published on claims

- **Priority:** P0
- **Paths:** src/five.txt
- **Depends on:** Ninguna
- **Verify:** .uak/bin/smoke --package-only
"""


def plan_amends_before_review(r):
    """A fix had to touch fixtures the plan missed; `uak plan` refused to republish the task (1 black box note)."""
    f = rm.fixture(r, "v51-amend", count=3)
    config(f, Plan_Channel="claims")
    plan = f.worktrees[0] / "wave2.md"
    plan.write_text(AMEND_BASE, encoding="utf-8")
    hack(f, 0, "plan", plan, UAK_HUMAN="boss")
    again = hack(f, 0, "plan", plan, UAK_HUMAN="boss", allowed=None)
    expect(again.returncode == 3 and "--amend" in again.stderr, "a republish points to --amend: " + again.stderr)
    f.claim(1, "HACK-005")
    plan.write_text(AMEND_BASE.replace("src/five.txt", "src/five.txt, tests/five_fixture.txt"), encoding="utf-8")
    ok = hack(f, 0, "plan", plan, "--amend", UAK_HUMAN="boss", now=1000005)
    expect(ok.returncode == 0 and "OK plan --amend HACK-005" in ok.stdout, ok.stdout + ok.stderr)
    expect("tests/five_fixture.txt" in f.show("tasks/HACK-005.md") and "tests/five_fixture.txt" in f.show("claims/HACK-005.md"),
           "a claimed task's record takes the new Paths (the merge gate reads them)")
    expect("HACK-005 amended by boss" in f.show("inbox/log.md") and "plan --amend" in f.show("DECISIONS.md"), "owner told, decision kept")
    six = AMEND_BASE.replace("HACK-005", "HACK-006").replace("src/five.txt", "src/six.txt")
    plan.write_text(six, encoding="utf-8")
    hack(f, 0, "plan", plan, UAK_HUMAN="boss", now=1000006)
    plan.write_text(six.replace("src/six.txt", "src/six.txt, tests/six_fixture.txt"), encoding="utf-8")
    hack(f, 0, "plan", plan, "--amend", UAK_HUMAN="boss", now=1000006)
    f.claim(2, "HACK-006", now=1000006)
    expect("tests/six_fixture.txt" in f.show("claims/HACK-006.md"), "an AVAILABLE task is claimed with its amended Paths")
    f.claim(0, "HACK-001", now=1000007)
    plan.write_text(AMEND_BASE.replace("src/five.txt", "src/five.txt, src/value-1.txt"), encoding="utf-8")
    clash = hack(f, 0, "plan", plan, "--amend", UAK_HUMAN="boss", now=1000008, allowed=None)
    expect(clash.returncode == 3 and "overlap HACK-001" in clash.stderr, "new Paths cannot take a live claim's files: " + clash.stderr)
    nohuman = hack(f, 0, "plan", plan, "--amend", now=1000009, allowed=None)
    expect(nohuman.returncode == 2 and "UAK_HUMAN" in nohuman.stderr, "amend is a human decision")
    tip = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1000010)
    review_text = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8")
    sec = review_text[review_text.index("## HACK-001"):review_text.index("## HACK-002")]
    plan.write_text("# Fix\n\n" + sec.replace("src/value-1.txt", "src/value-1.txt, docs/one.md"), encoding="utf-8")
    late = hack(f, 0, "plan", plan, "--amend", UAK_HUMAN="boss", now=1000011, allowed=None)
    expect(late.returncode == 3 and "in REVIEW" in late.stderr, "a task in review keeps the criteria it was reviewed on: " + late.stderr)
    return {"amended": True, "tip": tip[:7]}


CODE = {
    "lib/__init__.py": "",
    "lib/config.py": "def data_path(name):\n    return name\n\nclass Settings:\n    pass\n",
    "lib/io.py": "from lib.config import data_path\nfrom . import config\n\ndef load():\n    return data_path('x')\n",
    "app/page.py": "from lib import io\nimport lib.config as c\n\ndef render():\n    return io.load()\n",
    "web/src/lib/api.ts": "export async function api(path: string) { return path }\n",
    "web/src/features/a/index.tsx": "import { api } from '../../lib/api'\nexport default function A() { return api('x') }\n",
}


def map_in_the_loop(r):
    """9 agent calls of the map for 67 tasks: the claim pointed at `uak map show`, and the graph waited to be asked.
    impact:ID failed for tasks published with `uak plan`; hook calls inflated the agents' own status/inbox counts."""
    f = r.fixture("v51-lens", count=2, paths={"HACK-001": "lib/", "HACK-002": "app/"})
    config(f, Plan_Channel="claims")
    push_main(f, CODE, "code")
    for w in f.worktrees:
        r.g(w, "merge", "-q", "--ff-only", "origin/main")
    c = f.claim(0, "HACK-001")
    expect("TASK MAP HACK-001" in c.stdout and "lib/config.py" in c.stdout and "imported by" in c.stdout
           and "in the Paths of HACK-002" in c.stdout, "the claim prints the task's slice of the map: " + c.stdout)
    w = f.worktrees[1]
    r.run([r.bash, ".uak/bin/map", "build"], cwd=w)
    def send(payload):
        p = subprocess.run([r.bash, ".uak/bin/hook", "tick"], cwd=w, input=json.dumps(payload), text=True,
                           capture_output=True, env={**r.env, "UAK_AGENT": ""}, timeout=60)
        return p.stdout
    read = send({"session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": str(w / "lib/config.py")}})
    expect("uak map: lib/config.py" in read and "imported by 2 file(s)" in read, "a read gets who imports the file: " + read)
    again = send({"session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": str(w / "lib/config.py")}})
    expect("uak map: lib/config.py" not in again, "once per file per session")
    grep = send({"session_id": "s1", "tool_name": "Grep", "tool_input": {"pattern": "def data_path"}})
    expect("data_path is defined at lib/config.py:1" in grep and "called from 1 place(s)" in grep, "a symbol search gets its definition and callers: " + grep)
    shell = send({"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "rg -n 'load' app"}})
    expect("load is defined at lib/io.py" in shell, "grep/rg in a shell too: " + shell)
    cur = subprocess.run([r.bash, ".uak/bin/hook", "tick", "cursor"], cwd=w, text=True, capture_output=True, timeout=60,
                         input=json.dumps({"conversation_id": "c1", "tool_name": "Read", "tool_input": {"path": "app/page.py"}}),
                         env={**r.env, "UAK_AGENT": ""}).stdout
    expect(cur.startswith('{"additional_context":"') and "uak map: app/page.py" in cur, "Cursor postToolUse gets the same line: " + cur)
    calls = (f.clones[1] / ".git/uak-blackbox.calls")
    plan = f.worktrees[0] / "wave2.md"
    plan.write_text("# Wave 2\n\n## HACK-003 — api\n\n- **Priority:** P1\n- **Paths:** web/src/lib/\n- **Depends on:** Ninguna\n"
                    "- **Verify:** true\n\n## HACK-004 — feature\n\n- **Priority:** P1\n- **Paths:** web/src/features/\n"
                    "- **Depends on:** Ninguna\n- **Verify:** true\n", encoding="utf-8")
    hack(f, 0, "plan", plan, UAK_HUMAN="boss")
    sent = hack(f, 0, "msg", "impact:HACK-003", "--kind", "contract", "api() takes options now", now=1000005, allowed=None)
    expect(sent.returncode == 0 and "task:HACK-004" in sent.stdout, "impact:ID works for tasks published on claims: " + sent.stdout + sent.stderr)
    subprocess.run([r.bash, ".uak/bin/hook", "session-start"], cwd=w, input="{}", text=True, capture_output=True,
                   env={**r.env, "UAK_AGENT": ""}, timeout=120)
    counted = calls.read_text(encoding="utf-8") if calls.exists() else ""
    expect("lens" in counted and "hook-" in counted, "pushes and hook calls are counted apart: " + counted[-300:])
    return {"brief": True, "lens": True}


def sessions_leave_a_trace(r):
    """74 checkpoints for 130 claims and 43 lease recoveries; sessions closed without a handoff, and their
    identities kept getting reviews for hours."""
    f = rm.fixture(r, "v51-away", count=3)
    register(f, "agent-2", "agent-3")
    for i in (1, 2):
        hack(f, i, "msg", "all", "--kind", "info", "online %d" % i, now=1000005)
    f.claim(0, "HACK-001", now=1000006)
    tip = rm.publish(f, 0, "HACK-001")
    hack(f, 0, "heartbeat", "HACK-001", now=1000007)
    rec = f.show("tasks/HACK-001.md")
    expect("Progress: 1 commit(s) since the claim · last: " + tip[:7] in rec and "Implement HACK-001" in rec,
           "every heartbeat writes where the task stands: " + rec)
    st = hack(f, 1, "status", "--task", "HACK-001", now=1000008)
    expect("Progress: 1 commit(s)" in st.stdout, "status shows it to the next owner: " + st.stdout)
    clear = subprocess.run([r.bash, ".uak/bin/hook", "session-end"], cwd=f.worktrees[1], input='{"reason":"clear"}', text=True,
                           capture_output=True, env={**r.env, "UAK_AGENT": "agent-2", "UAK_NOW": "1000009"}, timeout=60)
    expect("meta/agents/agent-2.md" not in f.files("meta/"), "/clear is not the end of a session: " + clear.stderr)
    subprocess.run([r.bash, ".uak/bin/hook", "session-end"], cwd=f.worktrees[1], input='{"reason":"prompt_input_exit"}', text=True,
                   capture_output=True, env={**r.env, "UAK_AGENT": "agent-2", "UAK_NOW": "1000009"}, timeout=60)
    expect("Session-Ended: 1000009" in f.show("meta/agents/agent-2.md"), "SessionEnd runs uak away")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1000010)
    last = reviews(f)[-1]
    expect("agent:agent-3" in last, "an identity that closed its session gets no review offer: " + last)
    sent = hack(f, 0, "msg", "agent-2", "the fixture moved", now=1000011)
    expect("agent-2 closed its session" in sent.stdout, "the sender is told at once: " + sent.stdout)
    return {"progress": True, "away": True}


def past_work_comes_back(r):
    """The same rejects came back on tasks with other paths ("numbers must come from the CSV" in 4 rejects); lessons
    matched by path missed them, and 10 recalls for 130 claims show agents do not search the past themselves."""
    f = rm.fixture(r, "v51-recall", count=3)
    config(f, Plan_Channel="claims", Auto_Merge="yes")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, verdict="reject", now=1000020)
    last = [l for l in f.show("inbox/log.md").splitlines() if "| reject |" in l]
    expect(last, "a reject on file")
    hack(f, 1, "learn", "paper figures must be copied from reports/label_shift.csv, never typed by hand", "--path", "docs/", now=1000022)
    plan = f.worktrees[0] / "wave2.md"
    plan.write_text("# Wave 2\n\n## HACK-009 — Paper figures for the label shift section\n\n- **Priority:** P0\n"
                    "- **Paths:** paper/\n- **Depends on:** Ninguna\n- **Acceptance:** figures match label_shift.csv\n"
                    "- **Verify:** true\n", encoding="utf-8")
    hack(f, 0, "plan", plan, UAK_HUMAN="boss", now=1000023)
    c = f.claim(2, "HACK-009", now=1000024)
    expect("Learned on similar work" in c.stdout and "paper figures must be copied" in c.stdout and "[" in c.stdout,
           "the claim brings back what the team learned on similar work, with the shared words: " + c.stdout)
    s = hack(f, 2, "recall", "--search", "label shift figures paper", now=1000025)
    expect("RECALL by words" in s.stdout and "lesson #1" in s.stdout, s.stdout)
    f.claim(1, "HACK-002", now=1000030)
    hack(f, 1, "checkpoint", "HACK-002", "--done", "parsed the quokka telemetry with streaming windows",
         "--decision", "quokka telemetry in streaming windows of 5 s", "--why", "memory bound", "--fails", "-", "--commands", "true", "--next", "ship", now=1000031)
    tip2 = rm.publish(f, 1, "HACK-002")
    f.hack(1, "done", "HACK-002", "--pr", "https://example.test/pull/2", "--evidence", "ok", now=1000032)
    rm.approve(f, "HACK-002", tip2, now=1000033)
    merged = f.hack(1, "merge", "HACK-002", now=1000034, allowed=None)
    expect(merged.returncode == 0, merged.stdout + merged.stderr)
    done_work = hack(f, 2, "recall", "--search", "quokka telemetry streaming", now=1000035)
    expect("integrated on HACK-002" in done_work.stdout and "streaming windows" in done_work.stdout,
           "finished work is searchable by how it was solved: " + done_work.stdout)
    none = hack(f, 2, "recall", "--search", "kubernetes helm chart", now=1000026)
    expect("nothing the team learned" in none.stdout, "no match, no noise: " + none.stdout)
    return {"similar": True}


def upstream_drift_is_told(r):
    """Conflicting changes surfaced only in the merge gate; STORM (arXiv 2605.20563) caught them at write time."""
    f = r.fixture("v51-drift", count=2, paths={"HACK-001": "lib/", "HACK-002": "app/"})
    config(f)
    push_main(f, CODE, "code")
    for w in f.worktrees:
        r.g(w, "merge", "-q", "--ff-only", "origin/main")
    w = f.worktrees[1]
    (w / ".uak-env").write_text("UAK_AGENT=agent-2\nUAK_TASK=HACK-002\n", encoding="utf-8")
    f.claim(1, "HACK-002")
    (w / "app/page.py").write_text(CODE["app/page.py"] + "\ndef title():\n    return 'x'\n", encoding="utf-8")
    r.g(w, "commit", "-qam", "title()")
    quiet = r.run([r.bash, ".uak/bin/map", "drift"], cwd=w, allowed=None)
    expect(quiet.returncode == 1, "nothing upstream, nothing said: " + quiet.stdout)
    push_main(f, {"lib/config.py": CODE["lib/config.py"].replace("return name", "return 'data/' + name")}, "HACK-001: data_path prefixes data/")
    r.g(w, "fetch", "-q", "origin")
    d = r.run([r.bash, ".uak/bin/map", "drift"], cwd=w)
    expect("UPSTREAM: lib/config.py changed on main" in d.stdout and "your app/page.py imports it" in d.stdout
           and "HACK-001: data_path prefixes data/" in d.stdout and "git merge origin/main" in d.stdout, d.stdout)
    payload = json.dumps({"session_id": "d1", "tool_name": "Bash", "tool_input": {"command": "true"}})
    tick = lambda: subprocess.run([r.bash, ".uak/bin/hook", "tick"], cwd=w, input=payload, text=True, capture_output=True,
                                  env={**r.env, "UAK_AGENT": "agent-2"}, timeout=60).stdout
    tick()
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    for _ in range(40):
        if (gd / "uak-drift.txt").exists(): break
        time.sleep(0.5)
    first = tick()
    expect("UPSTREAM: lib/config.py" in first, "the hook says it during the work: " + first)
    expect("UPSTREAM" not in tick(), "once per change set")
    r.g(w, "push", "-q", "origin", f.branches[1])
    ship = f.hack(1, "done", "HACK-002", "--pr", "https://example.test/pull/2", "--evidence", "ok", now=1000010)
    expect("UPSTREAM: lib/config.py" in ship.stdout, "and again when shipping: " + ship.stdout)
    return {"drift": True}


def stalled_tasks_are_seen(r):
    """43 lease recoveries at MLB; the orchestra rule: reassign an agent stuck on one error instead of letting it spin."""
    f = rm.fixture(r, "v51-stall", count=2)
    f.claim(0, "HACK-001", now=1000000)
    hack(f, 0, "heartbeat", "HACK-001", now=1000010)
    rec = f.show("tasks/HACK-001.md")
    expect("Progress-Changed: 1000010" in rec, "the first heartbeat sets when the work last moved: " + rec)
    hack(f, 0, "heartbeat", "HACK-001", now=1003000, UAK_LEASE_SECONDS="20000")
    expect("Progress-Changed: 1000010" in f.show("tasks/HACK-001.md"), "no new commit, no move")
    own = hack(f, 0, "next", now=1006000)
    expect("STALLED: no work moved on HACK-001 in 99 min" in own.stdout and "--state BLOCKED" in own.stdout, own.stdout)
    other = hack(f, 1, "next", now=1006000)
    expect("Stalled: HACK-001 of agent-1" in other.stdout or "HACK-002 | AVAILABLE" in other.stdout, other.stdout)
    digest = rm.actor(f, "boss", "digest", now=1006000, human=True)
    expect("HACK-001 | STALLED | agent-1 | no work moved in 99 min" in digest.stdout, "the human digest lists it: " + digest.stdout)
    rm.publish(f, 0, "HACK-001")
    hack(f, 0, "heartbeat", "HACK-001", now=1006100, UAK_LEASE_SECONDS="20000")
    own2 = hack(f, 0, "next", now=1006200)
    expect("STALLED" not in own2.stdout, "a commit moves it again: " + own2.stdout)
    return {"stalled": True}


def github_feedback_reaches_the_task(r):
    """52 of 59 integrations at MLB were merged on GitHub, where CI results and human comments lived; agents heard of
    them only when a human relayed them."""
    f = rm.fixture(r, "v51-gh", count=1)
    tip = rm.ready(f, 0, "HACK-001")
    events = f.base / "gh-events.txt"
    events.write_text("check\tunit|https://github.com/o/r/actions/runs/123/job/9\t#7 CI failed: unit https://github.com/o/r/actions/runs/123/job/9\n"
                      "comment\tIC_1\t#7 @alice: please rename price_with_tax to price\n", encoding="utf-8")
    fake = f.base / "gh"
    fake.write_text("#!/usr/bin/env bash\n[ \"$1 $2\" = \"pr view\" ] || exit 1\ncat '%s'\n" % events, encoding="utf-8")
    os.chmod(fake, 0o755)
    sync = lambda now: hack(f, 0, "pr-sync", "HACK-001", now=now, UAK_GH=str(fake))
    out = sync(1000030)
    line = [l for l in f.show("inbox/log.md").splitlines() if "| github |" in l]
    expect("PR_SYNC: HACK-001 (2)" in out.stdout and line and "task:HACK-001" in line[-1] and "gh run view 123 --log-failed" in line[-1]
           and "@alice: please rename" in line[-1], "one message to the task with the failed check and the comment: " + out.stdout + str(line))
    again = sync(1000031)
    expect("nothing new" in again.stdout, "each item is told once: " + again.stdout)
    events.write_text(events.read_text(encoding="utf-8") + "review\tPRR_2\t#7 review CHANGES_REQUESTED by @bob: missing test\n", encoding="utf-8")
    third = sync(1000032)
    last = [l for l in f.show("inbox/log.md").splitlines() if "| github |" in l][-1]
    expect("HACK-001 (1)" in third.stdout and "@bob: missing test" in last and "@alice" not in last, "only the new one: " + last)
    inbox = hack(f, 0, "inbox", now=1000033)
    expect("missing test" in inbox.stdout, "the owner reads it in its inbox: " + inbox.stdout)
    return {"tip": tip[:7]}


def commands_come_up_when_they_apply(r):
    """`loop` 0 calls, `log --state BLOCKED` 4, `secret-exception` 0, `up` 0, `graph --assign` 3 at MLB: nothing brought
    them up at the moment they apply."""
    f = rm.fixture(r, "v51-moments", count=2)
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_AGENT=agent-1\nUAK_TASK=HACK-001\n", encoding="utf-8")
    failing = [r.bash, ".uak/bin/q", "bash", "-c", "echo \"AssertionError: expected 3 got 4 (took 0.$RANDOM s)\"; exit 1"]
    one = r.run(failing, cwd=w, allowed=None)
    expect(one.returncode == 1 and "LOOP:" not in one.stdout, "one failure is just a failure")
    two = r.run(failing, cwd=w, allowed=None)
    expect("LOOP: this check failed the same way 2 times" in two.stdout and "uak log HACK-001 --state BLOCKED" in two.stdout,
           "the same failure twice says LOOP where tests run (timings ignored): " + two.stdout)
    r.run([r.bash, ".uak/bin/q", "true"], cwd=w)
    three = r.run(failing, cwd=w, allowed=None)
    expect("LOOP:" not in three.stdout, "a pass resets it")
    (w / "leak.txt").write_text("AKIA" + "ABCDEFGHIJKLMNOP\n", encoding="utf-8")
    r.g(w, "add", "leak.txt")
    scan = r.run([r.bash, ".uak/bin/secret-scan", "--staged"], cwd=w, allowed=None)
    expect(scan.returncode != 0 and "uak secret-exception ID --path FILE" in scan.stderr, "the way out of a false positive: " + scan.stderr)
    r.g(w, "reset", "-q", "leak.txt")
    start = subprocess.run([r.bash, ".uak/bin/hook", "session-start"], cwd=w, input='{"source":"compact"}', text=True,
                           capture_output=True, env={**r.env, "UAK_AGENT": "agent-1"}, timeout=120).stdout
    expect("context was just compacted" in start and "uak checkpoint HACK-001" in start, "after a compaction: checkpoint now: " + start[:400])
    digest = rm.actor(f, "boss", "digest", now=1000000, human=True)
    expect("Capacity:" not in digest.stdout or "tasks wait" in digest.stdout or "1 task waits" in digest.stdout, digest.stdout)
    return {"moments": True}


def a_smaller_root(r):
    """About 12 kit entries at the project root felt invasive; only AGENTS.md and the dirs each tool reads must stay."""
    pkg = r.package.parent
    t = r.scratch / "v51-root"; t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.run([r.bash, str(pkg / "install.sh"), "--mode", "sprint", "--harness", "claude", "--no-mcp", str(t)], cwd=t)
    root = sorted(p.name for p in t.iterdir() if p.name != ".git")
    expect(root == [".claude", ".github", ".gitignore", ".uak", "AGENTS.md"], "claude only, no MCP: " + str(root))
    expect((t / ".claude/CLAUDE.md").read_text(encoding="utf-8").splitlines()[2] == "@../AGENTS.md", "CLAUDE.md imports ../AGENTS.md")
    expect(r.g(t, "config", "core.hooksPath").stdout.strip() == ".uak/githooks", "the scanner hook lives in .uak")
    old = r.scratch / "v51-root-old"; old.mkdir()
    r.g(old, "init", "-q", "-b", "main")
    r.run([r.bash, str(pkg / "install.sh"), "--mode", "sprint", "--harness", "claude,codex", str(old)], cwd=old)
    expect(not (old / ".cursor").exists() and not (old / ".gemini").exists() and (old / ".agents/skills").exists(), "only the chosen harnesses")
    import shutil
    shutil.copy2(pkg / "kit/CLAUDE.md", old / "CLAUDE.md"); (old / ".claude/CLAUDE.md").unlink()
    (old / ".githooks").mkdir(); shutil.copy2(pkg / "kit/.githooks/pre-commit", old / ".githooks/pre-commit")
    up = r.run([r.bash, str(pkg / "install.sh"), "--mode", "sprint", "--harness", "claude,codex", "--update", str(old)], cwd=old)
    expect(not (old / "CLAUDE.md").exists() and (old / ".claude/CLAUDE.md").exists() and not (old / ".githooks").exists()
           and "moved" in up.stdout, "an older layout migrates on --update: " + up.stdout[-500:])
    return {"root": root}


JAVA = {
    "src/main/java/com/acme/app/common/Money.java": "package com.acme.app.common;\n\npublic record Money(long cents) {\n    public static Money of(long cents) { return new Money(cents); }\n}\n",
    "src/main/java/com/acme/app/orders/OrderService.java": "package com.acme.app.orders;\n\nimport com.acme.app.common.Money;\n\npublic class OrderService {\n    public Money price(int items) {\n        return Money.of(items * 100L);\n    }\n}\n",
    "src/test/java/com/acme/app/orders/OrderServiceTest.java": "package com.acme.app.orders;\n\nclass OrderServiceTest {\n    void price() { new OrderService().price(2); }\n}\n",
}


def spring_boot_preset(r):
    """A Spring Boot template, and a code map that knows Java imports (definitions only before)."""
    pkg = r.package.parent
    t = r.scratch / "v51-sb"; t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    out = r.run([r.bash, str(pkg / "install.sh"), "--mode", "marathon", "--stack", "spring-boot", "--harness", "claude", str(t)], cwd=t)
    expect((t / ".claude/skills/stack-spring-boot/SKILL.md").exists() and (t / ".uak/stacks/spring-boot/STACK.md").exists()
           and "target/" in (t / ".gitignore").read_text(encoding="utf-8"), out.stdout[-400:])
    f = r.fixture("v51-java", count=2, paths={"HACK-001": "src/main/java/com/acme/app/common/",
                                             "HACK-002": "src/main/java/com/acme/app/orders/, src/test/java/com/acme/app/orders/"})
    config(f)
    push_main(f, JAVA, "java code")
    for w in f.worktrees:
        r.g(w, "merge", "-q", "--ff-only", "origin/main")
    w = f.worktrees[0]
    edges = r.run([r.bash, ".uak/bin/map", "deps", "src/main/java/com/acme/app/orders/OrderService.java"], cwd=w).stdout
    expect("src/main/java/com/acme/app/common/Money.java" in edges, "a Java import is an edge: " + edges)
    callers = r.run([r.bash, ".uak/bin/map", "callers", "price"], cwd=w).stdout
    expect("OrderServiceTest.java" in callers and "OrderService.java" in callers, "same-package calls across main and test: " + callers)
    c = f.claim(0, "HACK-001")
    expect("TASK MAP HACK-001" in c.stdout and "in the Paths of HACK-002" in c.stdout, "brief on a Java task: " + c.stdout)
    f.claim(1, "HACK-002")
    sent = hack(f, 0, "msg", "impact:HACK-001", "--kind", "contract", "Money.of takes a currency now", now=1000005)
    expect("task:HACK-002" in sent.stdout, "impact reaches the Java importer: " + sent.stdout)
    return {"java": True}


def dashboard_shows_everything(r):
    """To know where the project stood, humans asked the agents (99 digests, 22 "who can review?" messages)."""
    f = rm.fixture(r, "v51-dash", count=2)
    tip = rm.ready(f, 0, "HACK-001")
    hack(f, 1, "msg", "agent-1", "the parser returns a list now", "--kind", "contract", now=1000012)
    out = f.base / "dash"
    res = r.run([r.bash, ".uak/bin/uak", "dash", "--out", str(out)], cwd=f.worktrees[1], env={"UAK_NOW": "1000020"})
    expect("DASH " in res.stdout and "% integrated" in res.stdout, res.stdout + res.stderr)
    html = (out / "index.html").read_text(encoding="utf-8")
    expect("<script src=\"data.js\"></script>" in html and "http" not in html.split("<style>")[0], "a self-contained page")
    expect(not re.search(r"<(script|link)[^>]+(https?:)?//", html), "no external script or stylesheet")
    expect(":root[data-theme=\"dark\"]" in html and "prefers-color-scheme: dark" in html, "light, dark and an explicit theme choice")
    data = json.loads((out / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    states = data["progress"]["states"]
    expect(states.get("REVIEW") == 1 and data["progress"]["total"] == 2, "progress from claims: " + str(data["progress"]))
    names = {a["name"]: a for a in data["agents"]}
    expect("agent-1" in names and "agent-2" in names and names["agent-1"]["tasks"][0]["id"] == "HACK-001", str(names)[:300])
    expect(any(m["kind"] == "contract" and "parser" in m["text"] for m in data["messages"]), "the conversation is there")
    expect(any(o["task"] == "HACK-001" for o in data["offers"]), "the review waiting is listed: " + str(data["offers"]))
    return {"tip": tip[:7]}


TESTS = [review_offers_move_on, humans_and_stale_identities_get_no_review, offline_recipients_and_orphans,
         worktree_env_is_not_a_human, approval_survives_forge_merge_and_pull, followup_owns_the_parent_paths,
         merge_gate_links_node_modules, small_fixes, identities_are_reused, plan_amends_before_review, map_in_the_loop, sessions_leave_a_trace, past_work_comes_back, upstream_drift_is_told, stalled_tasks_are_seen, github_feedback_reaches_the_task, commands_come_up_when_they_apply, a_smaller_root, spring_boot_preset, dashboard_shows_everything]


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
