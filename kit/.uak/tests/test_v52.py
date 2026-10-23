#!/usr/bin/env python3
"""uak v5.2.1: a full audit of the kit after v5.2 (Oct 23 2026). One test per defect found by installing, updating and
driving the kit by hand: an update that dropped a team's pre-commit and a husky hooksPath and left 16 unedited files as
.uak-new, a handover whose worktree still named the old owner for the hooks, timing keys read from claims but never
written there, a dashboard that failed before the first claim, a wait that overslept its timeout, a BM25 filter that
mawk ignored, and an MCP server that dropped running calls when stdin closed.
Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack
from test_v43 import push_main
import test_review_merge as rm


def older_version(repo, rel):
    """The newest committed version of repo/rel that differs from the working tree (None without history)."""
    current = (repo / rel).read_bytes()
    log = subprocess.run(["git", "rev-list", "HEAD", "--", rel], cwd=repo, capture_output=True, text=True)
    for commit in log.stdout.split():
        old = subprocess.run(["git", "show", commit + ":" + rel], cwd=repo, capture_output=True)
        if old.returncode == 0 and old.stdout and old.stdout != current:
            return old.stdout
    return None


def update_keeps_what_the_team_wrote(r):
    """An update from v5.0 removed a pre-commit the team had extended, replaced a husky core.hooksPath, and wrote 16
    .uak-new files for kit files nobody had edited (settings.json among them: the new hooks never arrived)."""
    pkg = r.package.parent
    install = lambda t, *a: r.run([r.bash, str(pkg / "install.sh"), "--mode", "sprint", "--harness", "claude", *a, str(t)], cwd=t)
    t = r.scratch / "v52-update"; t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    install(t)
    old = older_version(pkg, "kit/.uak/settings/settings.sprint.json")
    if old is not None:
        (t / ".claude/settings.json").write_bytes(old)
    with open(t / "AGENTS.md", "a", encoding="utf-8") as fh:
        fh.write("\n- Team rule: run make check before every push.\n")
    (t / ".githooks").mkdir()
    hook = (pkg / "kit/.githooks/pre-commit").read_text(encoding="utf-8") + "npm run lint\n"
    (t / ".githooks/pre-commit").write_text(hook, encoding="utf-8")
    up = install(t, "--update")
    kit_settings = (pkg / "kit/.uak/settings/settings.sprint.json").read_bytes()
    if old is not None:
        expect((t / ".claude/settings.json").read_bytes() == kit_settings and not (t / ".claude/settings.json.uak-new").exists()
               and "settings.json updated (an earlier kit version, unedited)" in up.stdout,
               "an unedited earlier kit file is updated in place: " + up.stdout[-800:])
    expect("Team rule" in (t / "AGENTS.md").read_text(encoding="utf-8") and (t / "AGENTS.md.uak-new").exists(),
           "an edited file stays, with the kit's text beside it")
    expect((t / ".githooks/pre-commit").read_text(encoding="utf-8") == hook and r.g(t, "config", "core.hooksPath").stdout.strip() == ".githooks",
           "a pre-commit the team extended survives --update: " + up.stdout[-500:])
    h = r.scratch / "v52-husky"; h.mkdir()
    r.g(h, "init", "-q", "-b", "main")
    r.g(h, "config", "core.hooksPath", ".husky/_")
    out = install(h)
    expect(r.g(h, "config", "core.hooksPath").stdout.strip() == ".husky/_" and "another hook manager" in out.stdout,
           "another hook manager keeps its hooksPath: " + out.stdout[-400:])
    doc = r.run([r.bash, ".uak/bin/doctor"], cwd=h, allowed=None)
    expect("bash .uak/githooks/pre-commit" in doc.stdout and "core.hooksPath is not" not in doc.stdout, doc.stdout[-600:])
    d = r.scratch / "v52-dangling"; d.mkdir()
    r.g(d, "init", "-q", "-b", "main")
    (d / ".agents").mkdir()
    (d / ".agents/skills").symlink_to("../nowhere")
    r.run([r.bash, str(pkg / "install.sh"), "--mode", "marathon", "--harness", "claude,codex", str(d)], cwd=d)
    return {"history": old is not None}


def handover_moves_the_worktree_identity(r):
    """After a handover the worktree's Claude Code env still named the old owner: the new owner's session started as
    "agent=<old>" and every uak call printed the mismatch."""
    f = rm.fixture(r, "v52-handover", count=2)
    f.claim(0, "HACK-001", now=1000000)
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_AGENT=agent-1\nUAK_AGENT_HUMAN=ana\nUAK_SESSION=agent-1-1\nUAK_TASK=HACK-001\n", encoding="utf-8")
    (w / ".claude").mkdir(exist_ok=True)
    (w / ".claude/settings.local.json").write_text(json.dumps({"env": {"UAK_AGENT": "agent-1", "UAK_SESSION": "agent-1-1",
                                                                        "UAK_TASK": "HACK-001"}}, indent=2) + "\n", encoding="utf-8")
    rm.actor(f, "boss", "handover", "HACK-001", "--to", "agent-2", now=1000100, human=True)
    env = json.loads((w / ".claude/settings.local.json").read_text(encoding="utf-8"))["env"]
    expect(env["UAK_AGENT"] == "agent-2" and env["UAK_SESSION"].startswith("agent-2-") and env["UAK_TASK"] == "HACK-001",
           "Claude Code's env names the new owner: " + str(env))
    expect("UAK_AGENT=agent-2" in (w / ".uak-env").read_text(encoding="utf-8"), "so does .uak-env")
    start = subprocess.run([r.bash, ".uak/bin/hook", "session-start"], cwd=w, input='{"session_id":"s9"}', text=True,
                           capture_output=True, env={**r.env, "UAK_AGENT": "agent-1"}, timeout=120).stdout
    expect("agent=agent-2" in start, "the hook takes the worktree's identity over an inherited export: " + start[:300])
    return {"owner": "agent-2"}


def timing_keys_come_from_project(r):
    """Presence-Seconds, Stall-Seconds, Review-Offer-Seconds and Merge-Adopt-Seconds were read from claims
    meta/config.md but never written there: setting them in PROJECT.md, as CLI.md says, did nothing."""
    f = rm.fixture(r, "v52-timing", count=2)
    project = (f.seed / ".uak/PROJECT.md").read_text(encoding="utf-8")
    push_main(f, {".uak/PROJECT.md": project + "Stall-Seconds: 600\nPresence-Seconds: 120\nReview-Offer-Seconds: 300\n"
                  "Merge-Adopt-Seconds: 60\n"}, "timing keys")
    f.claim(0, "HACK-001", now=1000000)
    cfg = f.show("meta/config.md")
    expect(all(k in cfg for k in ("Stall-Seconds: 600", "Presence-Seconds: 120", "Review-Offer-Seconds: 300",
                                  "Merge-Adopt-Seconds: 60", "Config-Schema: 2")), "claims config carries them: " + cfg)
    hack(f, 0, "heartbeat", "HACK-001", now=1000010)
    own = hack(f, 0, "next", now=1000700)
    expect("STALLED: no work moved on HACK-001 in 11 min" in own.stdout, "Stall-Seconds from PROJECT.md applies: " + own.stdout)
    return {"stall": 600}


def dash_before_the_first_claim(r):
    """`uak dash` right after /uak-plan failed: DASH_ERROR couldn't find remote ref refs/heads/claims."""
    f = rm.fixture(r, "v52-dash", count=2)
    if r.g(f.worktrees[0], "ls-remote", "--heads", "origin", "claims").stdout.strip():
        return {"skipped": "fixture already has claims"}
    out = f.base / "dash"
    res = r.run([r.bash, ".uak/bin/uak", "dash", "--out", str(out)], cwd=f.worktrees[0], env={"UAK_NOW": "1000000"}, allowed=None)
    expect(res.returncode == 0 and "DASH " in res.stdout, res.stdout + res.stderr)
    data = json.loads((out / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    expect(data["progress"]["total"] == 2 and data["progress"]["states"].get("AVAILABLE") == 2, "the backlog, all AVAILABLE: " + str(data["progress"]))
    return {"tasks": 2}


def audit_small_fixes(r):
    """The version printed by status (v3.0 since v3), a wait that slept its 15 s interval past a 3 s timeout, lint
    errors before the backlog exists, a SHA filter mawk ignored ({7,}), a typo'd recipient with no hint, and an MCP
    server that dropped calls still running when stdin closed."""
    f = rm.fixture(r, "v52-small", count=2)
    version = (r.package / ".uak/VERSION").read_text(encoding="utf-8").strip()
    st = hack(f, 0, "status")
    expect(st.stdout.startswith("uak v" + version + " |"), "status names the installed version: " + st.stdout[:80])
    started = time.monotonic()
    waited = hack(f, 1, "wait", "--for", "message", "--timeout", "2", allowed=(4,))
    expect(time.monotonic() - started < 10 and "WAIT_TIMEOUT" in waited.stdout, "a 2 s wait returns near 2 s, not after the 15 s interval")
    hack(f, 1, "msg", "all", "--kind", "info", "agent-2 is here", now=1000005)
    typo = hack(f, 0, "msg", "agnet-2", "the parser shape changed", now=1000006)
    expect("a typo?" in typo.stdout and "Known: agent-2" in typo.stdout, "a typo'd name lists the known ones: " + typo.stdout)
    hack(f, 1, "learn", "abcdef12 parser crashes on empty input lines", "--path", "src/", now=1000007)
    rec = hack(f, 0, "recall", "--search", "abcdef12 parser", now=1000008)
    expect("shares 2+ words" in rec.stdout, "a SHA-like token is no shared word (mawk ignored {7,}): " + rec.stdout)
    pkg = r.package.parent
    t = r.scratch / "v52-lint"; t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.run([r.bash, str(pkg / "install.sh"), "--mode", "marathon", "--harness", "claude", str(t)], cwd=t)
    lint = r.run([r.bash, ".uak/bin/uak", "lint"], cwd=t, allowed=None)
    expect("cannot open" not in lint.stderr and "owner not in TASKS" not in lint.stderr, "lint before /uak-plan: " + lint.stderr[-400:])
    calls = "\n".join(json.dumps(m) for m in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "uak_status", "arguments": {}}})) + "\n"
    py = shutil.which("python3") or shutil.which("python")
    mcp = subprocess.run([py, ".uak/bin/uak-mcp"], cwd=f.worktrees[0], input=calls, text=True, capture_output=True,
                         env={**r.env, "UAK_AGENT": "agent-1"}, timeout=120)
    expect('"id":2' in mcp.stdout.replace(" ", ""), "the call running when stdin closed is answered: " + mcp.stdout[-300:] + mcp.stderr[-300:])
    return {"version": version}


def root_task_writes_where_its_dependent_owns(r):
    """A team's black box (Oct 2026): the root task had a mock file in a mocks package OWNERS.md gave to a second task,
    which depends on the root. The root's claim was refused for good (CONFLICT, exit 3), `uak next` offered no
    candidate, and the whole project stalled at its first task."""
    f = r.fixture("v52-owner-dep", {"HACK-001": "pkg/mocks/Mocks.swift, pkg/core/", "HACK-002": "pkg/mocks/",
                                    "HACK-003": "pkg/mocks/Extra.swift"},
                  count=3, owners={"pkg/mocks/": "HACK-002"}, dependencies={"HACK-002": "HACK-001"})
    nxt = f.hack(0, "next", allowed=None)
    expect("HACK-001" in nxt.stdout, "next offers the root task: " + nxt.stdout[-400:])
    root = f.claim(0, "HACK-001", allowed=None)
    expect(root.returncode == 0, "the owner waits on HACK-001, so HACK-001 may write there first: " + root.stdout + root.stderr)
    other = f.claim(2, "HACK-003", now=1000001, allowed=None)
    expect(other.returncode == 3 and "make HACK-002 depend on HACK-003" in other.stderr,
           "a task the owner does not wait on is still refused, with the way out: " + other.stderr)
    lint = f.hack(1, "lint", allowed=None)
    expect("HACK-003 can never be claimed" in lint.stderr and "HACK-001 can never" not in lint.stderr, "lint names it: " + lint.stderr[-600:])
    config(f, Plan_Channel="claims")
    plan = f.worktrees[1] / "wave2.md"
    plan.write_text("# Wave 2\n\n## HACK-004 — mock fixtures\n\n- **Priority:** P1\n- **Paths:** pkg/mocks/Fixtures.swift\n"
                    "- **Depends on:** Ninguna\n- **Verify:** true\n", encoding="utf-8")
    pub = hack(f, 1, "plan", plan, UAK_HUMAN="boss")
    expect("PLAN WARNING: HACK-004 can never be claimed" in pub.stdout, "plan says it at once: " + pub.stdout)
    return {"root": "claimed"}


def solo_marathon_has_a_way(r):
    """A solo marathon project (Oct 2026): "two hours and I still cannot start; it asks for the approval of another
    GitHub account and I am alone on the repo". GitHub never lets a PR's author approve it, so Review-Mode gh waited
    forever and nothing said why."""
    import os
    pkg = r.package.parent
    t = r.scratch / "v52-solo"; t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.run([r.bash, str(pkg / "install.sh"), "--mode", "marathon", "--solo", "--harness", "claude", str(t)], cwd=t)
    expect("Review-Mode: claims" in (t / ".uak/PROJECT.md").read_text(encoding="utf-8"), "--solo reviews on claims")
    remote = r.scratch / "v52-solo-remote.git"
    r.g(r.scratch, "init", "-q", "--bare", remote)
    r.g(t, "remote", "add", "origin", "https://github.com/solo/app.git")
    r.g(t, "config", "url." + remote.as_posix() + ".insteadOf", "https://github.com/solo/app.git")
    (t / ".uak/PROJECT.md").write_text((t / ".uak/PROJECT.md").read_text(encoding="utf-8").replace("Review-Mode: claims", "Review-Mode: gh"), encoding="utf-8")
    bin_dir = r.scratch / "v52-solo-bin"; bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/usr/bin/env bash\ncase \"$1 $2\" in\n  'auth status') echo 'Token scopes: repo';;\n"
                                "  'api repos/solo/app/collaborators?per_page=2') echo 1;;\n  'api repos/solo/app') echo true,true,true;;\n"
                                "  'api '*'/reviews') printf 'solo|COMMENTED|%s\\n' \"$TIP\";;\n"
                                "  'api '*) printf '%s|solo|main|feat/x|solo/app|open|false|' \"$TIP\";;\nesac\nexit 0\n", encoding="utf-8")
    os.chmod(bin_dir / "gh", 0o755)
    env = {"PATH": bin_dir.as_posix() + os.pathsep + r.env.get("PATH", "")}
    doc = r.run([r.bash, ".uak/bin/doctor"], cwd=t, env=env, allowed=None)
    expect("only collaborator of solo/app" in doc.stdout and "Review-Mode: claims" in doc.stdout, "doctor says it at minute 0: " + doc.stdout[-700:])
    sha = "a" * 40
    rec = r.scratch / "v52-solo-rec"; (rec / "tasks").mkdir(parents=True)
    (rec / "tasks/HACK-001.md").write_text("Owner: agent-1\nBranch: feat/x\n", encoding="utf-8")
    harness = r.scratch / "v52-solo-gate.sh"
    harness.write_text("#!/usr/bin/env bash\nset -u\nfield() { sed -n \"s/^$2: //p\" \"$1\" | head -n 1; }\n"
                       "source \"$PACKAGE/.uak/bin/lib/review-merge.sh\"\nTX=$FIXTURE; TXROOT=$FIXTURE; RECORD=$FIXTURE/tasks/HACK-001.md\n"
                       "ID=HACK-001; BASE=main; REMOTE_URL=https://github.com/solo/app.git\n"
                       "approval_check \"$TIP\" https://github.com/solo/app/pull/3; echo \"$RM_REASON\"\n", encoding="utf-8")
    gate = r.run([r.bash, harness.as_posix()], env={**env, "PACKAGE": r.package.as_posix(), "FIXTURE": rec.as_posix(), "TIP": sha,
                                                   "UAK_REVIEW_MODE": "gh"}, allowed=None)
    expect("never lets the PR's author, solo, approve it" in gate.stdout and "Review-Mode: claims" in gate.stdout, "the gate says the way out: " + gate.stdout)
    return {"solo": True}


TESTS = [update_keeps_what_the_team_wrote, handover_moves_the_worktree_identity, timing_keys_come_from_project,
         dash_before_the_first_claim, audit_small_fixes, root_task_writes_where_its_dependent_owns,
         solo_marathon_has_a_way]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v52-") as tmp:
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
    print("V52_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
