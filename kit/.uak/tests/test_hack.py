#!/usr/bin/env python3
"""Integration checks against real Git processes and disposable local remotes.

Only Python's standard library is used. A local bare remote exercises Git's
compare-and-swap branch updates; it does not verify GitHub APIs or protection.
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


class Failure(Exception):
    pass


def expect(condition, message):
    if not condition:
        raise Failure(message)


def resolve_binary(name, explicit=None):
    if explicit:
        return str(Path(explicit).resolve())
    if os.name == "nt":
        roots = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git"]
        for root in roots:
            options = [root / "bin" / (name + ".exe"), root / "cmd" / (name + ".exe")]
            for option in options:
                if option.is_file():
                    return str(option)
    found = shutil.which(name)
    if not found:
        raise Failure("Required executable is unavailable: " + name)
    return found


class Runner:
    def __init__(self, package, scratch, bash, git):
        self.package, self.scratch = package, scratch
        self.bash, self.git = bash, git
        self.env = os.environ.copy()
        self.env.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
        # A user signing default must not make disposable fixture commits interactive.
        self.env["GIT_CONFIG_COUNT"] = "2"
        self.env["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
        self.env["GIT_CONFIG_VALUE_0"] = "false"
        self.env["GIT_CONFIG_KEY_1"] = "core.autocrlf"
        self.env["GIT_CONFIG_VALUE_1"] = "false"

    def run(self, command, cwd=None, env=None, allowed=(0,), timeout=240):
        effective = self.env.copy()
        if env:
            effective.update(env)
        result = subprocess.run(command, cwd=cwd, env=effective, text=True,
                                encoding="utf-8", errors="replace", capture_output=True,
                                timeout=timeout)
        if allowed is not None and result.returncode not in allowed:
            raise Failure("Command failed (%s): %s\n%s\n%s" % (
                result.returncode, " ".join(map(str, command)), result.stdout[-8000:],
                result.stderr[-8000:]))
        return result

    def g(self, cwd, *args, allowed=(0,)):
        return self.run([self.git, *map(str, args)], cwd=cwd, allowed=allowed)

    def fixture(self, name, paths=None, count=4, owners=None, shared_repo=False, dependencies=None):
        return Fixture(self, name, paths or {
            "HACK-001": "src/one.txt", "HACK-002": "src/two.txt",
            "HACK-003": "src/three.txt", "HACK-004": "src/four.txt"}, count, owners, shared_repo, dependencies)


class Fixture:
    def __init__(self, runner, name, paths, count, owners=None, shared_repo=False, dependencies=None):
        self.r = runner
        self.base = runner.scratch / name
        self.base.mkdir(parents=True)
        self.remote = self.base / "remote.git"
        self.seed = self.base / "seed"
        self.seed.mkdir()
        runner.g(self.base, "init", "--bare", self.remote)
        runner.g(self.seed, "init")
        runner.g(self.seed, "symbolic-ref", "HEAD", "refs/heads/main")
        for src in runner.package.iterdir():
            if src.name.startswith(".") and src.name not in (".gitignore", ".gitattributes", ".github", ".githooks", ".uak"):
                continue
            if src.name in ("test-results.json", "TEST-RESULTS.md"):
                continue
            dest = self.seed / src.name
            if src.is_dir():
                shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(src, dest)
        tasks = ["# TASKS — static backlog", "", "States live on claims.", ""]
        for task, path in paths.items():
            tasks += ["## " + task + " — Fixture verificable", "",
                      "- **Type:** vertical", "- **Priority:** P0",
                      "- **Area:** tests, demo", "- **Estimate:** 10 min",
                      "- **Rubric:** funcionalidad",
                      "- **Paths:** " + path,
                      "- **Depends on:** " + (dependencies or {}).get(task, "ninguna"),
                      "- **Acceptance:** salida comprobable",
                      "- **Verify:** .uak/bin/smoke --package-only", ""]
        (self.seed / ".uak/TASKS.md").write_text("\n".join(tasks), encoding="utf-8")
        (self.seed / ".uak/PROJECT.md").write_text("Backlog-Approved: yes\nAutonomy: yes\nAuto-Merge: yes\nReview-Mode: claims\nEvents-Per-Session: 100\nCheckpoint-Percent: 60\n", encoding="utf-8")
        owner_text = "# Owners\n\n| Pattern | Owner task |\n|---|---|\n"
        for pattern, task in (owners or {}).items():
            owner_text += "| `" + pattern + "` | " + task + " |\n"
        (self.seed / ".uak/OWNERS.md").write_text(owner_text, encoding="utf-8")
        runner.g(self.seed, "config", "user.name", "Fixture")
        runner.g(self.seed, "config", "user.email", "fixture@example.invalid")
        runner.g(self.seed, "add", ".")
        runner.g(self.seed, "commit", "-m", "Fixture main")
        runner.g(self.seed, "remote", "add", "origin", self.remote)
        runner.g(self.seed, "push", "-u", "origin", "main")
        runner.g(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.main_head = runner.g(self.remote, "rev-parse", "main").stdout.strip()
        self.clones, self.worktrees, self.branches = [], [], []
        for index in range(count):
            clone = self.base / ("agent-%d" % (1 if shared_repo else index + 1))
            if not shared_repo or index == 0:
                runner.g(self.base, "clone", self.remote, clone)
                runner.g(clone, "config", "user.name", "FixtureAgent")
                runner.g(clone, "config", "user.email", "agent@example.invalid")
            branch = "task/agent-%d" % (index + 1)
            worktree = self.base / ("worktree-%d" % (index + 1))
            runner.g(clone, "worktree", "add", "-b", branch, worktree, "main")
            self.clones.append(clone)
            self.worktrees.append(worktree)
            self.branches.append(branch)

    def hack(self, index, *args, now=1000000, allowed=(0,), human=False):
        env = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": str(now),
               "UAK_REMOTE": "origin", "UAK_HUMAN": "human-fixture" if human else ""}
        return self.r.run([self.r.bash, ".uak/bin/uak", *map(str, args)],
                          cwd=self.worktrees[index], env=env, allowed=allowed)

    def claim(self, index, task, now=1000000, allowed=(0,), next_step="Ejecutar siguiente paso exacto"):
        return self.hack(index, "claim", task, "--branch", self.branches[index],
                         "--worktree", self.worktrees[index].as_posix(), "--next", next_step,
                         now=now, allowed=allowed)

    def race(self, tasks):
        barrier = threading.Barrier(len(tasks))
        def one(index):
            barrier.wait(timeout=20)
            result = self.claim(index, tasks[index], allowed=None)
            return {"agent": "agent-%d" % (index + 1), "task": tasks[index],
                    "code": result.returncode, "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip()}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            return list(pool.map(one, range(len(tasks))))

    def show(self, path):
        return self.r.g(self.remote, "show", "claims:" + path).stdout

    def files(self, prefix=""):
        return self.r.g(self.remote, "ls-tree", "-r", "--name-only", "claims", "--", prefix).stdout.splitlines()

    def worklog(self, task):
        match = re.search(r"^Worklog:\s*(.+)$", self.show("tasks/" + task + ".md"), re.M)
        expect(match is not None, "Task must reference a shared worklog")
        return match.group(1).strip()


def history(text):
    expect("## History" in text, "Shared worklog must expose Historial")
    return text.split("## History", 1)[1].splitlines()[1:]


def summary_lines(text):
    expect("## Live summary" in text, "Shared worklog must expose Live summary")
    return text.split("## Live summary", 1)[1].split("## History", 1)[0].strip("\n").splitlines()


def same_task_race(r):
    f = r.fixture("same-task")
    results = f.race(["HACK-001"] * 4)
    winners = [x for x in results if x["code"] == 0]
    expect(len(winners) == 1, "Exactly one of four claim processes must win: " + json.dumps(results))
    expect(all(x["code"] == 3 for x in results if x["code"] != 0),
           "Each loser must report an actual claim conflict: " + json.dumps(results))
    claim = f.show("claims/HACK-001.md")
    expect("Owner: " + winners[0]["agent"] in claim, "Remote winner must match successful process")
    expect(len(f.files("claims/")) == 1, "Only one active claim may exist")
    return {"processes": results, "winners": 1, "conflict_exits": 3}


def disjoint_race_and_visibility(r):
    f = r.fixture("disjoint")
    results = f.race(["HACK-001", "HACK-002", "HACK-003", "HACK-004"])
    expect(all(x["code"] == 0 for x in results),
           "Unrelated push contention must be retried until all four succeed: " + json.dumps(results))
    expect(len(f.files("claims/")) == 4, "All four claims must survive push/rebase contention")
    expect(len(f.files("worklog/")) == 4, "All four logs must be shared without feature merges")
    expect(r.g(f.remote, "rev-parse", "main").stdout.strip() == f.main_head,
           "Visibility must not require merging into main")
    status = f.hack(3, "status").stdout
    expect(all(task in status for task in ("HACK-001", "HACK-002", "HACK-003", "HACK-004")),
           "Fresh status must see claims made from other clones")
    return {"processes": results, "claims": 4, "shared_logs": 4,
            "main_unchanged": True, "status_lines": len(status.splitlines())}


def shared_repository_disjoint_race(r):
    f = r.fixture("shared-git-directory", shared_repo=True)
    results = f.race(["HACK-001", "HACK-002", "HACK-003", "HACK-004"])
    expect(all(x["code"] == 0 for x in results),
           "Four worktrees sharing .git must all progress despite local fetch/ref contention: " + json.dumps(results))
    expect(len(f.files("claims/")) == 4, "Shared-repository race cannot lose an independent claim")
    return {"processes": results, "registered_worktrees": 4, "common_git_directories": 1, "claims": 4}


def overlap_race(r):
    f = r.fixture("overlap", {"HACK-001": "src/./shared/**", "HACK-002": "src/shared/widget.txt"}, count=2)
    results = f.race(["HACK-001", "HACK-002"])
    expect(sum(x["code"] == 0 for x in results) == 1, "One overlapping claim must win: " + json.dumps(results))
    expect(sum(x["code"] == 3 for x in results) == 1, "Other overlapping claim must report conflict")
    expect(len(f.files("claims/")) == 1, "Overlap must be rechecked after remote contention")
    return {"processes": results, "winners": 1, "conflict_exits": 1}


def wrong_owner_and_expired_lease(r):
    f = r.fixture("lease", count=2)
    f.claim(0, "HACK-001", now=1000000)
    f.hack(0, "heartbeat", "HACK-001", now=1000001)
    expect("Lease-Until: 1001801" in f.show("claims/HACK-001.md"), "Heartbeat must renew default 30-minute lease")
    wrong_owner = f.hack(1, "heartbeat", "HACK-001", now=1000001, allowed=None)
    expect(wrong_owner.returncode == 3, "Another owner cannot refresh a lease")
    old_view = f.hack(1, "status", "--task", "HACK-001", "--summary", now=1000002).stdout
    old_token = re.search(r"^Read-token:\s*(\S+)\s*$", old_view, re.M)
    expect(old_token is not None, "Read token must be available before ownership changes")
    f.hack(0, "heartbeat", "HACK-001", now=1000003)
    premature = f.hack(1, "release", "HACK-001", "--expired", "--read-summary", "invalid",
                       now=1000004, allowed=None)
    expect(premature.returncode != 0, "An unexpired lease cannot be stolen")
    stale = f.hack(1, "release", "HACK-001", "--expired", "--read-summary", old_token.group(1),
                   now=1001804, allowed=None)
    expect(stale.returncode == 3, "A token read before another heartbeat must not release the updated claim")
    without_reading = f.hack(1, "release", "HACK-001", "--expired", now=1001804, allowed=None)
    expect(without_reading.returncode != 0, "Expired takeover must require reading the live summary")
    view = f.hack(1, "status", "--task", "HACK-001", "--summary", now=1001804).stdout
    token = re.search(r"^Read-token:\s*(\S+)\s*$", view, re.M)
    expect(token is not None, "Summary must provide a read token")
    invalid = f.hack(1, "release", "HACK-001", "--expired", "--read-summary", "invalid",
                     now=1001804, allowed=None)
    expect(invalid.returncode != 0, "Wrong summary token cannot release another agent's lease")
    old_log = f.worklog("HACK-001")
    f.hack(1, "release", "HACK-001", "--expired", "--read-summary", token.group(1), now=1001804)
    f.claim(1, "HACK-001", now=1001805)
    expect("Owner: agent-2" in f.show("claims/HACK-001.md"), "Expired task must be reclaimable")
    expect(old_log in f.files("worklog/"), "A takeover must preserve previous session history")
    return {"wrong_owner_code": wrong_owner.returncode,
            "unexpired_release_code": premature.returncode,
            "missing_read_code": without_reading.returncode,
            "wrong_token_code": invalid.returncode, "stale_token_code": stale.returncode,
            "takeover": "agent-2", "old_log_preserved": True}


def log_checkpoint_handoff(r):
    f = r.fixture("continuity", count=1)
    exact = "Ejecutar .uak/bin/smoke --package-only y revisar resultado"
    exact_command = r"printf '%s\n' 'x|y' | sed 's/x/z/'"
    f.claim(0, "HACK-001", next_step="Construir fixture")
    path = f.worklog("HACK-001")
    before = f.show(path)
    f.hack(0, "log", "HACK-001", "Progress event\nbefore checkpoint", now=1000030)
    after_log = f.show(path)
    log_events = [line for line in history(after_log) if line.strip()]
    initial_events = [line for line in history(before) if line.strip()]
    expect(len(log_events) == len(initial_events) + 1, "A multiline log input must produce one single-line event")
    f.hack(0, "checkpoint", "HACK-001", "--done", "Criterio fixture cumplido",
           "--decision", "Usar mock local", "--why", "Evitar bloqueo externo",
           "--fails", "ninguno", "--commands", exact_command, "--next", exact,
           now=1000060)
    after = f.show(path)
    previous_history = history(before)
    expect(history(after)[:len(previous_history)] == previous_history,
           "Checkpoint may overwrite live summary but must preserve old history byte-for-byte")
    expect(len(history(after)) > len(previous_history), "Checkpoint must append an event")
    expect(len(summary_lines(after)) <= 15, "Live summary must stay within 15 lines")
    expect(exact in after, "Checkpoint must retain exact next command")
    expect("- Commands: " + exact_command in after, "Checkpoint must preserve literal pipeline and backslash escapes")
    handoff = f.hack(0, "handoff", "HACK-001", now=1000061).stdout
    expect(exact in handoff and "HACK-001" in handoff and f.branches[0] in handoff,
           "Handoff must carry task, branch and exact next step")
    expect("Evitar bloqueo externo" in handoff, "Handoff must preserve decision rationale")
    expect("- Commands: " + exact_command in handoff, "Handoff must preserve exact pipeline command")
    return {"old_history_lines": len(previous_history), "new_history_lines": len(history(after)),
            "summary_lines": len(summary_lines(after)), "handoff_lines": len(handoff.splitlines()),
            "next_step": exact, "exact_command": exact_command,
            "outside_scope": "Independent cold-start agent check is run by root"}


def review_does_not_block(r):
    f = r.fixture("review-queue", count=2)
    f.claim(0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.invalid/pull/1",
           "--evidence", "Local fixture criterion met; package smoke passed", now=1000010)
    expect("State: REVIEW" in f.show("tasks/HACK-001.md"), "Done queues review rather than integrating")
    f.claim(1, "HACK-002", now=1000011)
    digest = f.hack(1, "digest", now=1000012).stdout
    expect("HACK-001" in digest and "REVIEW" in digest, "One digest must expose review queue")
    expect("State: CLAIMED" in f.show("tasks/HACK-002.md"), "Review queue cannot block independent work")
    return {"queued_state": "REVIEW", "independent_state": "CLAIMED", "digest": digest.strip()}


def blocked_does_not_block(r):
    f = r.fixture("blocked-queue", count=2)
    f.claim(0, "HACK-001")
    f.hack(0, "log", "HACK-001", "--state", "BLOCKED", "External decision pending; continue HACK-002", now=1000010)
    expect("State: BLOCKED" in f.show("tasks/HACK-001.md"), "Block must be visible in shared state")
    f.claim(1, "HACK-002", now=1000011)
    digest = f.hack(1, "digest", now=1000012).stdout
    expect("HACK-001" in digest and "BLOCKED" in digest, "Digest must aggregate blocked work")
    f.hack(1, "release", "HACK-002", now=1000013)
    expect("State: AVAILABLE" in f.show("tasks/HACK-002.md"), "Owner release must make work available")
    return {"blocked_state": "BLOCKED", "independent_claim_passed": True,
            "owner_release_state": "AVAILABLE", "digest": digest.strip()}


def shared_files_have_one_owner(r):
    f = r.fixture("owners", {"HACK-001": "package-lock.json", "HACK-002": "package-lock.json"},
                  count=2, owners={"package-lock.json": "HACK-001"})
    non_owner = f.claim(1, "HACK-002", allowed=None)
    expect(non_owner.returncode == 3, "Nonowner cannot claim lockfile even without an active overlapping claim")
    f.claim(0, "HACK-001")
    expect("Owner: agent-1" in f.show("claims/HACK-001.md"), "Designated task can claim its protected shared file")
    return {"nonowner_code": non_owner.returncode, "designated_task": "HACK-001"}


def invalid_worktree_and_branch(r):
    f = r.fixture("worktree-validation", count=1)
    unregistered = f.base / "unregistered"
    unregistered.mkdir()
    wrong_path = f.hack(0, "claim", "HACK-001", "--branch", f.branches[0],
                        "--worktree", unregistered.as_posix(), "--next", "Rechazar ruta",
                        allowed=None)
    expect(wrong_path.returncode == 2, "Unregistered worktree must be rejected before claiming")
    wrong_branch = f.hack(0, "claim", "HACK-001", "--branch", "task/nonexistent",
                          "--worktree", f.worktrees[0].as_posix(), "--next", "Rechazar rama",
                          allowed=None)
    expect(wrong_branch.returncode == 2, "Worktree/branch mismatch must be rejected")
    subdir = f.worktrees[0] / "subdir"
    subdir.mkdir()
    wrong_subdir = f.hack(0, "claim", "HACK-001", "--branch", f.branches[0],
                          "--worktree", subdir.as_posix(), "--next", "Rechazar subdirectorio",
                          allowed=None)
    expect(wrong_subdir.returncode == 2, "A subdirectory must not count as a registered worktree root")
    return {"unregistered_worktree_code": wrong_path.returncode, "wrong_branch_code": wrong_branch.returncode,
            "worktree_subdir_code": wrong_subdir.returncode}


def unavailable_remote_never_claims(r):
    f = r.fixture("unavailable-remote", count=1)
    r.g(f.clones[0], "remote", "set-url", "origin", f.base / "does-not-exist.git")
    result = f.claim(0, "HACK-001", allowed=None)
    expect(result.returncode == 1, "An unavailable remote must report Git failure, not success or task collision")
    missing = r.g(f.remote, "show-ref", "--verify", "refs/heads/claims", allowed=(1, 128))
    expect(missing.returncode != 0, "Remote failure cannot create a published claim")
    return {"unavailable_remote_code": result.returncode, "published_claim": False}


def one_worktree_per_task(r):
    f = r.fixture("unique-worktree", count=1)
    f.claim(0, "HACK-001")
    reused = f.claim(0, "HACK-002", allowed=None)
    expect(reused.returncode == 3, "Even disjoint tasks must not share an actively reserved branch/worktree")
    expect(len(f.files("claims/")) == 1, "Reusing an active branch/worktree must not publish a second reservation")
    return {"same_branch_worktree_code": reused.returncode, "active_claims": 1}


def unimplemented_task_cannot_integrate(r):
    f = r.fixture("empty-implementation", count=1)
    # A second base commit catches implementations that compare against root commit
    # instead of the base captured when this specific task was claimed.
    (f.seed / "baseline.txt").write_text("Second baseline commit\n", encoding="utf-8")
    r.g(f.seed, "add", "baseline.txt")
    r.g(f.seed, "commit", "-m", "Advance baseline before claiming")
    r.g(f.seed, "push", "origin", "main")
    baseline = r.g(f.remote, "rev-parse", "main").stdout.strip()
    r.g(f.worktrees[0], "fetch", "origin", "main")
    r.g(f.worktrees[0], "merge", "--ff-only", "FETCH_HEAD")
    f.claim(0, "HACK-001")
    r.g(f.worktrees[0], "push", "origin", f.branches[0])
    pr = "https://example.invalid/pull/1"
    no_commit = f.hack(0, "done", "HACK-001", "--pr", pr, "--evidence", "No implementation",
                       "--integrated", baseline, "--reviewer", "reviewer-other", now=1000010, allowed=None)
    expect(no_commit.returncode == 3, "An unchanged task tip cannot be certified as integrated")
    r.g(f.worktrees[0], "commit", "--allow-empty", "-m", "Empty fixture commit")
    r.g(f.worktrees[0], "push", "origin", f.branches[0])
    r.g(f.seed, "fetch", "origin", f.branches[0])
    r.g(f.seed, "merge", "--ff-only", "FETCH_HEAD")
    r.g(f.seed, "push", "origin", "main")
    empty_tip = r.g(f.remote, "rev-parse", "main").stdout.strip()
    empty_commit = f.hack(0, "done", "HACK-001", "--pr", pr, "--evidence", "Empty commit only",
                          "--integrated", empty_tip, "--reviewer", "reviewer-other", now=1000011, allowed=None)
    expect(empty_commit.returncode == 3, "A merged empty commit cannot be certified as implementation")
    expect("State: CLAIMED" in f.show("tasks/HACK-001.md"), "Rejected integration must preserve active task")
    return {"baseline_commits": 2, "no_implementation_code": no_commit.returncode,
            "merged_empty_commit_code": empty_commit.returncode, "state": "CLAIMED"}


def integrated_dependency_and_cancellation(r):
    f = r.fixture("terminal-states", count=3, dependencies={"HACK-002": "HACK-001"})
    dependency = f.claim(1, "HACK-002", allowed=None)
    expect(dependency.returncode == 3, "A dependent task cannot claim before its predecessor is integrated")
    f.claim(0, "HACK-001")
    (f.worktrees[0] / "src").mkdir(exist_ok=True)
    (f.worktrees[0] / "src" / "one.txt").write_text("Real task branch change\n", encoding="utf-8")
    r.g(f.worktrees[0], "add", "src/one.txt")
    r.g(f.worktrees[0], "commit", "-m", "Complete fixture vertical increment")
    r.g(f.worktrees[0], "push", "origin", f.branches[0])
    pr = "https://example.invalid/pull/1"
    f.hack(0, "done", "HACK-001", "--pr", pr, "--evidence", "Committed fixture increment", now=1000010)
    invalid = f.hack(0, "done", "HACK-001", "--pr", pr, "--evidence", "Invalid old base",
                     "--integrated", f.main_head, "--reviewer", "agent-2", now=1000011, allowed=None)
    expect(invalid.returncode != 0, "Old main cannot falsely prove task integration")
    r.g(f.seed, "fetch", "origin", f.branches[0])
    r.g(f.seed, "merge", "--no-ff", "FETCH_HEAD", "-m", "Real local fixture integration")
    r.g(f.seed, "push", "origin", "main")
    merged = r.g(f.remote, "rev-parse", "main").stdout.strip()
    self_review = f.hack(0, "done", "HACK-001", "--pr", pr, "--evidence", "Local Git merge",
                         "--integrated", merged, "--reviewer", "agent-1", now=1000012, allowed=None)
    expect(self_review.returncode != 0, "Author cannot certify independent integration review")
    # v2.1 prepares a real review; keeps all original assertions.
    f.hack(0, "register-reviewer", "agent-2", human=True, now=1000012)
    tip = r.g(f.remote, "rev-parse", f.branches[0]).stdout.strip()
    f.hack(1, "review", "HACK-001", "--sha", tip, "--verdict", "approve", now=1000012)
    f.hack(0, "done", "HACK-001", "--pr", pr, "--evidence", "Local Git merge with actual task change",
           "--integrated", merged, "--reviewer", "agent-2", now=1000013)
    expect("State: INTEGRATED" in f.show("tasks/HACK-001.md"), "Verified merge must persist terminal INTEGRATED")
    expect("claims/HACK-001.md" not in f.files("claims/"), "Integration must release active file reservation")
    f.claim(1, "HACK-002", now=1000014)
    f.claim(2, "HACK-003", now=1000015)
    f.hack(2, "release", "HACK-003", "--cancel", "Below the cut line", now=1000016)
    expect("State: CANCELLED" in f.show("tasks/HACK-003.md"), "Cancellation must persist terminal state")
    cannot_reclaim = f.claim(2, "HACK-003", now=1000017, allowed=None)
    expect(cannot_reclaim.returncode == 3, "Cancelled work cannot silently restart")
    return {"dependency_before_code": dependency.returncode, "false_integration_code": invalid.returncode,
            "self_review_code": self_review.returncode, "integrated_commit": merged,
            "dependency_after_state": "CLAIMED", "cancelled_state": "CANCELLED",
            "cancelled_reclaim_code": cannot_reclaim.returncode,
            "scope": "Real Git branch merge locally; no GitHub PR or live reviewer"}


def lint_budgets(r):
    f = r.fixture("budgets", count=1)
    f.claim(0, "HACK-001")
    f.hack(0, "lint")
    agents = (f.worktrees[0] / "AGENTS.md").read_text(encoding="utf-8")
    state = f.show("STATE.md")
    expect(len(agents.splitlines()) <= 150, "AGENTS exceeds 150 lines")
    expect(len(state.splitlines()) <= 60, "STATE exceeds 60 lines")
    (f.worktrees[0] / "AGENTS.md").write_text(agents + "\n" + "Exceso\n" * 151, encoding="utf-8")
    oversized = f.hack(0, "lint", allowed=None)
    expect(oversized.returncode != 0, "Lint must fail on oversized AGENTS")
    (f.worktrees[0] / "AGENTS.md").write_text(agents, encoding="utf-8")
    r.g(f.clones[0], "fetch", "origin", "claims")
    state_edit = f.base / "state-edit"
    r.g(f.clones[0], "worktree", "add", "--detach", state_edit, "FETCH_HEAD")
    (state_edit / "STATE.md").write_text(state + "Exceso\n" * 61, encoding="utf-8")
    r.g(state_edit, "add", "STATE.md")
    r.g(state_edit, "commit", "-m", "Intentional invalid state fixture")
    r.g(state_edit, "push", "origin", "HEAD:claims")
    oversized_state = f.hack(0, "lint", allowed=None)
    expect(oversized_state.returncode != 0, "Lint must fail on oversized shared STATE")
    return {"agents_lines": len(agents.splitlines()), "agents_words": len(agents.split()),
            "state_lines": len(state.splitlines()), "state_words": len(state.split()),
            "oversized_agents_code": oversized.returncode, "oversized_state_code": oversized_state.returncode}


CASES = [same_task_race, disjoint_race_and_visibility, shared_repository_disjoint_race, overlap_race,
         wrong_owner_and_expired_lease, log_checkpoint_handoff, review_does_not_block,
         blocked_does_not_block, shared_files_have_one_owner, invalid_worktree_and_branch,
         unavailable_remote_never_claims, one_worktree_per_task, unimplemented_task_cannot_integrate,
         integrated_dependency_and_cancellation, lint_budgets]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--bash")
    parser.add_argument("--git")
    parser.add_argument("--report", type=Path, default=os.environ.get("UAK_TEST_REPORT"))
    parser.add_argument("--work-dir", type=Path, default=os.environ.get("UAK_TEST_WORK_DIR"),
                        help="Keep disposable fixtures under this new directory")
    parser.add_argument("--case", action="append", help="Run named test functions only")
    parser.add_argument("--jobs", type=int, default=2, help="Independent disposable scenarios in parallel")
    args = parser.parse_args()
    package = args.package.resolve()
    selected = [test for test in CASES if not args.case or test.__name__ in args.case]
    if not selected:
        parser.error("No cases selected")
    bash, git = resolve_binary("bash", args.bash), resolve_binary("git", args.git)
    temporary = None
    if args.work_dir:
        scratch = args.work_dir.resolve()
        if package == scratch or package in scratch.parents:
            parser.error("--work-dir must be outside the package, to avoid copying a directory into itself")
        scratch.mkdir(parents=True, exist_ok=False)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="hack-v2-tests-")
        scratch = Path(temporary.name)
    package_snapshot = scratch / "package-snapshot"
    shutil.copytree(package, package_snapshot, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "*.pyc", "integration-results.json", "policy-results.json"))
    runner = Runner(package_snapshot, scratch, bash, git)
    report = {"schema": 1, "scope": "real Git local bare remote; no live GitHub or product tests",
              "runtime": {"bash": runner.run([bash, "--version"]).stdout.splitlines()[0],
                          "git": runner.run([git, "--version"]).stdout.strip(),
                          "python": sys.version.split()[0]}, "jobs": max(1,args.jobs), "tests": [],
              "package_sha256": {name: hashlib.sha256((package_snapshot / name).read_bytes()).hexdigest()
                                 for name in ("AGENTS.md", ".uak/bin/uak", ".uak/bin/policy", ".uak/bin/smoke",
                                              ".uak/tests/test_hack.py", ".uak/tests/test_policy.py", ".uak/bin/uak-coordination",
                                              ".uak/bin/lib/review-merge.sh", ".uak/bin/lib/security.sh", ".uak/bin/lib/smoke-init.sh",
                                              ".uak/bin/secret-scan", ".githooks/pre-commit", ".uak/tests/test_coordination.py",
                                              ".uak/tests/test_review_merge.py", ".uak/tests/test_v21_security.py")},
              "not_verified": ["GitHub API, branch protection, CI and live PR merges",
                               "Product behavior without .uak/bin/smoke-project",
                               "Bash 3.2 runtime; syntax portability is reviewed separately",
                               "Live humans and a full 24-hour hackathon"]}
    started = time.monotonic()
    try:
        def run_case(test):
            item = {"name": test.__name__}
            begin = time.monotonic()
            try:
                item["evidence"] = test(runner)
                item["status"] = "PASS"
            except Exception as error:
                item["status"] = "FAIL"
                item["error"] = str(error)
            item["seconds"] = round(time.monotonic() - begin, 3)
            print("%s %s (%ss)" % (item["status"], test.__name__, item["seconds"]), flush=True)
            if item["status"] == "FAIL": print(item["error"], flush=True)
            return item
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            report["tests"] = list(pool.map(run_case, selected))
        report["passed"] = sum(t["status"] == "PASS" for t in report["tests"])
        report["failed"] = sum(t["status"] == "FAIL" for t in report["tests"])
        report["seconds"] = round(time.monotonic() - started, 3)
        report["status"] = "PASS" if report["failed"] == 0 else "FAIL"
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("RESULT %s passed=%d failed=%d" % (report["status"], report["passed"], report["failed"]))
        return 1 if report["failed"] else 0
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    sys.exit(main())
