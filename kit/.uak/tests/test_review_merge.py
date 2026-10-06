#!/usr/bin/env python3
"""Real Git and separate processes; gh API only via a simulated contract."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

from test_hack import Runner, Failure, expect, resolve_binary


def fixture(r, name, count=2, verify_fail=False):
    paths = {"HACK-%03d" % (i + 1): "src/value-%d.txt" % (i + 1) for i in range(count)}
    f = r.fixture("v21-" + name, paths=paths, count=count)
    (f.seed / ".uak/PROJECT.md").write_text(
        "# Fixture humana\nAutonomy: yes\nAuto-Merge: yes\nBacklog-Approved: yes\n"
        "Backlog-Proposed-Epoch: 1000000\nFreeze-Epoch: 9999999\nReview-Mode: claims\n"
        "Events-Per-Session: 100000\nCheckpoint-Percent: 60\n"
        "Merge-Lease-Seconds: 1800\nMerge-Wait-Seconds: 600\n", encoding="utf-8")
    tasks = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8")
    for task, path in paths.items():
        command = "test \"$(cat %s)\" = ready-%s" % (path, task)
        if verify_fail and task == "HACK-001":
            command = "test \"$(cat %s)\" = impossible-result" % path
        start = tasks.index("## " + task)
        end = tasks.find("\n## ", start + 1)
        end = len(tasks) if end < 0 else end
        section = tasks[start:end].replace(".uak/bin/smoke --package-only", command)
        tasks = tasks[:start] + section + tasks[end:]
    (f.seed / ".uak/TASKS.md").write_text(tasks, encoding="utf-8")
    # A runnable fixture product keeps smoke from calling tests that would
    # invoke merge and smoke recursively. The real CLI has no bypass.
    (f.seed / ".uak/bin/smoke").write_text(
        "#!/usr/bin/env bash\nset -eu\n"
        "cd \"$(dirname \"$0\")/../..\"\n"
        "bash -n .uak/bin/uak\n"
        "[ -f .uak/bin/smoke-project ] || { echo PRODUCT_UNVERIFIED; exit 2; }\n"
        "bash .uak/bin/smoke-project\necho FIXTURE_PRODUCT_PASS\n", encoding="utf-8")
    (f.seed / ".uak/bin/smoke-project").write_text(
        "#!/usr/bin/env bash\nset -eu\n[ ! -f .red-product-gate ]\n", encoding="utf-8")
    r.g(f.seed, "add", ".uak/TASKS.md", ".uak/PROJECT.md", ".uak/bin/smoke", ".uak/bin/smoke-project")
    r.g(f.seed, "commit", "-m", "Configure explicit permissions and fixture product gates")
    r.g(f.seed, "push", "origin", "main")
    f.main_head = r.g(f.remote, "rev-parse", "main").stdout.strip()
    for clone, worktree in zip(f.clones, f.worktrees):
        r.g(clone, "fetch", "origin", "main")
        r.g(worktree, "reset", "--hard", "origin/main")
    f.paths = paths
    return f


def actor(f, name, *args, now=1000020, human=False, allowed=(0,), timeout=180):
    return f.r.run([f.r.bash, ".uak/bin/uak", *args], cwd=f.clones[0], env={
        "UAK_AGENT": name, "UAK_HUMAN": name if human else "",
        "UAK_NOW": str(now), "UAK_REVIEW_MODE": "claims"}, allowed=allowed, timeout=timeout)


def publish(f, index, task, suffix=""):
    path = f.paths[task]
    target = f.worktrees[index] / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ready-" + task + suffix + "\n", encoding="utf-8")
    f.r.g(f.worktrees[index], "add", path)
    f.r.g(f.worktrees[index], "commit", "-m", "Implement " + task + suffix)
    f.r.g(f.worktrees[index], "push", "origin", f.branches[index])
    return f.r.g(f.worktrees[index], "rev-parse", "HEAD").stdout.strip()


def ready(f, index, task):
    f.claim(index, task)
    tip = publish(f, index, task)
    f.hack(index, "done", task, "--pr", "https://example.test/pull/" + str(index + 1),
           "--evidence", "Fixture product acceptance", now=1000010)
    return tip


def judge(f):
    actor(f, "human-registrar", "register-reviewer", "judge", human=True)


def approve(f, task, tip, name="judge", now=1000021, verdict="approve", allowed=(0,)):
    return actor(f, name, "review", task, "--sha", tip, "--verdict", verdict, now=now, allowed=allowed)


def review_gates(r):
    f = fixture(r, "review-gates")
    tip = ready(f, 0, "HACK-001")
    invented = f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1",
                      "--evidence", "Invented declaration", "--integrated", f.main_head,
                      "--reviewer", "ghost", now=1000011, allowed=None)
    expect(invented.returncode == 3, "An invented CLI reviewer must not prove approval")
    self_review = approve(f, "HACK-001", tip, name="agent-1", allowed=None)
    unregistered = approve(f, "HACK-001", tip, name="ghost", allowed=None)
    expect(self_review.returncode == 3, "Owner self review must fail")
    expect(unregistered.returncode == 3, "Identity without active claim/registered role must fail")
    f.claim(1, "HACK-002", now=1000012)
    approve(f, "HACK-001", tip, name="agent-2")
    expect("Eligible-Via: claim:HACK-002:" in f.show("reviews/HACK-001.md"), "Active claim must justify reviewer identity")
    judge(f)
    obsolete_input = approve(f, "HACK-001", "0" * 40, allowed=None)
    expect(obsolete_input.returncode == 3, "Review command must reject an obsolete SHA")
    approve(f, "HACK-001", tip)
    stale = publish(f, 0, "HACK-001", suffix="-changed")
    fail = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    expect(fail.returncode == 3 and "stale" in fail.stdout, "Changed SHA must invalidate existing approval")
    expect("queue/merge-lock.md" not in f.files("."), "Stale review failure must release lock")
    # The new approval is valid; the acceptance gate still checks the
    # original value and detects this change. Restore the product with another SHA.
    approve(f, "HACK-001", stale, now=1000031)
    original = publish(f, 0, "HACK-001")
    approve(f, "HACK-001", original, now=1000032)
    merged = f.hack(0, "merge", "HACK-001", now=1000033)
    expect("INTEGRATED" in merged.stdout, "Valid registered role approval must allow merge")
    expect("Reviewer: judge" in f.show("tasks/HACK-001.md"), "Actual recorded reviewer must be retained")
    return {"invented": invented.returncode, "self_review": self_review.returncode,
            "unregistered": unregistered.returncode, "stale": fail.returncode,
            "obsolete_review_input": obsolete_input.returncode,
            "active_claim_and_registered_role": "PASS", "valid_merge": "PASS"}


def concurrent_merges(r):
    f = fixture(r, "four-merges", count=4)
    tips = [ready(f, i, "HACK-%03d" % (i + 1)) for i in range(4)]
    judge(f)
    for i, tip in enumerate(tips):
        approve(f, "HACK-%03d" % (i + 1), tip)
    barrier = threading.Barrier(4)
    def one(i):
        barrier.wait(timeout=20)
        result = f.r.run([r.bash, ".uak/bin/uak", "merge", "HACK-%03d" % (i + 1)],
                         cwd=f.worktrees[i], env={"UAK_AGENT": "agent-%d" % (i + 1),
                         "UAK_NOW": "1000030", "UAK_REVIEW_MODE": "claims"}, allowed=None, timeout=720)
        return {"agent": i + 1, "code": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, range(4)))
    expect(all(x["code"] == 0 for x in results), "Four real merge processes must finish: " + json.dumps(results))
    base = r.g(f.remote, "rev-parse", "main").stdout.strip()
    commits = []
    for i, tip in enumerate(tips):
        task = "HACK-%03d" % (i + 1)
        record = f.show("tasks/" + task + ".md")
        expect("State: INTEGRATED" in record, "All task records must be integrated")
        commit = re.search(r"^Merge-Commit: (\w+)$", record, re.M).group(1)
        commits.append(commit)
        r.g(f.remote, "merge-base", "--is-ancestor", tip, commit)
        r.g(f.remote, "merge-base", "--is-ancestor", commit, base)
        expect(r.g(f.remote, "show", "main:" + f.paths[task]).stdout.strip() == "ready-" + task, "Merged base must retain every task")
    expect(len(set(commits)) == 4 and not f.files("claims/"), "Four distinct serial merge commits, no remaining claims")
    expect("queue/merge-lock.md" not in f.files("."), "All queue locks must be released")
    return {"processes": results, "serial_merge_commits": commits, "consistent_tasks": 4, "lock_remaining": False}


def gate_and_lease(r):
    f = fixture(r, "gate-red", count=1, verify_fail=True)
    tip = ready(f, 0, "HACK-001"); judge(f); approve(f, "HACK-001", tip)
    result = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    expect(result.returncode == 3 and "acceptance red" in result.stdout, "Executable acceptance gate must reject")
    expect(r.g(f.remote, "rev-parse", "main").stdout.strip() == f.main_head, "A red gate must never push base")
    expect("State: HUMAN" in f.show("queue/HACK-001.md") and "queue/merge-lock.md" not in f.files("."), "Red gate must queue human and release lock")
    config_path = f.seed / ".uak/PROJECT.md"
    config_path.write_text(config_path.read_text(encoding="utf-8").replace("Autonomy: yes", "Autonomy: no"), encoding="utf-8")
    r.g(f.seed, "add", ".uak/PROJECT.md"); r.g(f.seed, "commit", "-m", "Human revokes autonomy"); r.g(f.seed, "push", "origin", "main")
    expected = r.g(f.remote, "rev-parse", "main").stdout.strip()
    revoked = f.hack(0, "merge", "HACK-001", now=1000031, allowed=None)
    expect(revoked.returncode == 3 and "Autonomy" in revoked.stdout, "Current human autonomy revocation must block merge")
    expect(r.g(f.remote, "rev-parse", "main").stdout.strip() == expected and "queue/merge-lock.md" not in f.files("."), "Permission rejection must not merge and must release lock")
    config_path.write_text(config_path.read_text(encoding="utf-8").replace("Autonomy: no", "Autonomy: yes").replace("Freeze-Epoch: 9999999", "Freeze-Epoch: 1000032"), encoding="utf-8")
    r.g(f.seed, "add", ".uak/PROJECT.md"); r.g(f.seed, "commit", "-m", "Human schedules freeze"); r.g(f.seed, "push", "origin", "main")
    expected = r.g(f.remote, "rev-parse", "main").stdout.strip()
    frozen = f.hack(0, "merge", "HACK-001", now=1000032, allowed=None)
    expect(frozen.returncode == 3 and "FREEZE" in frozen.stdout, "Existing REVIEW task also must obey freeze")
    expect(r.g(f.remote, "rev-parse", "main").stdout.strip() == expected and "queue/merge-lock.md" not in f.files("."), "Freeze gate must not merge and must release lock")
    g = fixture(r, "expired-lock", count=1)
    tip = ready(g, 0, "HACK-001"); judge(g); approve(g, "HACK-001", tip)
    queue = g.base / "queue-editor"
    r.g(g.base, "clone", "--branch", "claims", g.remote, queue)
    r.g(queue, "config", "user.name", "QueueFixture"); r.g(queue, "config", "user.email", "queue@example.test")
    (queue / "queue").mkdir(exist_ok=True)
    (queue / "queue/merge-lock.md").write_text("Owner: abandoned\nTask: HACK-001\nToken: abandoned-token\nLease-Until: 1000029\nUpdated: 999999\n", encoding="utf-8")
    r.g(queue, "add", "."); r.g(queue, "commit", "-m", "Seed expired lease"); r.g(queue, "push", "origin", "claims")
    success = g.hack(0, "merge", "HACK-001", now=1000030)
    expect("INTEGRATED" in success.stdout and "queue/merge-lock.md" not in g.files("."), "Expired lock must be recovered safely")
    return {"red_gate": result.returncode, "red_base_unchanged": True, "red_lock_released": True,
            "autonomy_revoked": revoked.returncode, "freeze_existing_review": frozen.returncode,
            "expired_lock_recovered": True}


def squash_registration(r):
    f = fixture(r, "squash", count=1)
    tip = ready(f, 0, "HACK-001"); judge(f); approve(f, "HACK-001", tip)
    r.g(f.seed, "fetch", "origin", f.branches[0])
    r.g(f.seed, "merge", "--squash", "FETCH_HEAD")
    r.g(f.seed, "commit", "-m", "Fixture external squash")
    r.g(f.seed, "push", "origin", "main")
    merged = r.g(f.seed, "rev-parse", "HEAD").stdout.strip()
    expect(r.g(f.remote, "merge-base", "--is-ancestor", tip, merged, allowed=None).returncode == 1, "Squash fixture must genuinely replace task SHA")
    phantom = f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1",
                     "--evidence", "Incorrect reviewer declaration", "--integrated", merged,
                     "--reviewer", "ghost", now=1000029, allowed=None)
    expect(phantom.returncode == 3, "CLI reviewer must match actual approval even when valid approval exists")
    result = f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1",
                    "--evidence", "External squash proof", "--integrated", merged,
                    "--reviewer", "judge", now=1000030)
    expect("INTEGRATED" in result.stdout and "State: INTEGRATED" in f.show("tasks/HACK-001.md"), "Tree proof must register squash")
    expect("Integration-Proof: tree:" in f.show("tasks/HACK-001.md"), "Squash must record its verified tree hash")
    g = fixture(r, "rebase-two-commits", count=1)
    g.claim(0, "HACK-001")
    publish(g, 0, "HACK-001", suffix="-first-step")
    original = publish(g, 0, "HACK-001")
    g.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Two reviewed commits", now=1000010)
    judge(g); approve(g, "HACK-001", original)
    unrelated = g.seed / "src/unrelated.txt"; unrelated.parent.mkdir(exist_ok=True); unrelated.write_text("other task\n", encoding="utf-8")
    r.g(g.seed, "add", "src/unrelated.txt"); r.g(g.seed, "commit", "-m", "Advance base with disjoint work"); r.g(g.seed, "push", "origin", "main")
    replay = g.base / "replay"
    r.g(g.base, "clone", g.remote, replay)
    r.g(replay, "config", "user.name", "RebaseFixture"); r.g(replay, "config", "user.email", "rebase@example.test")
    r.g(replay, "checkout", "-b", "replayed", "origin/" + g.branches[0]); r.g(replay, "rebase", "origin/main")
    rebased = r.g(replay, "rev-parse", "HEAD").stdout.strip(); partial = r.g(replay, "rev-parse", "HEAD^").stdout.strip()
    r.g(replay, "push", "origin", "HEAD:refs/heads/main")
    expect(r.g(g.remote, "merge-base", "--is-ancestor", original, rebased, allowed=None).returncode == 1, "Rebase must really replace original SHAs")
    wrong = g.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Wrong partial rebase commit",
                   "--integrated", partial, "--reviewer", "judge", now=1000029, allowed=None)
    expect(wrong.returncode == 3 and "tree hash" in wrong.stderr, "Partial rewritten history must not prove complete task content")
    correct = g.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Actual complete two-commit rebase",
                     "--integrated", rebased, "--reviewer", "judge", now=1000030)
    expect("INTEGRATED" in correct.stdout and "Integration-Proof: tree:" in g.show("tasks/HACK-001.md"), "Two-commit rebase must register using complete verified tree")
    return {"tip": tip, "squash_commit": merged, "tip_not_ancestor": True,
            "phantom_with_existing_approval": phantom.returncode, "tree_proof_registration": "PASS",
            "rebase_original_tip": original, "rebase_result": rebased, "partial_rebase_rejected": wrong.returncode,
            "rebase_two_commits_disjoint_base": "PASS"}


def gh_contract(r):
    scratch = r.scratch / "gh-api-mock"
    scratch.mkdir(); (scratch / "tasks").mkdir(); (scratch / "bin").mkdir()
    sha = "a" * 40
    (scratch / "tasks/HACK-001.md").write_text("Owner: agent-1\nBranch: task/agent-1\n", encoding="utf-8")
    fake = scratch / "bin/gh"
    fake.write_text("#!/usr/bin/env bash\ncase \"$2\" in */reviews) cat \"$MOCK_REVIEWS\";; *) printf '%s' \"$MOCK_PR\";; esac\n", encoding="utf-8")
    os.chmod(fake, 0o755)
    harness = scratch / "harness.sh"
    harness.write_text("#!/usr/bin/env bash\nset -u\n"
        "field() { sed -n \"s/^$2: //p\" \"$1\" | head -n 1; }\n"
        "source \"$PACKAGE/.uak/bin/lib/review-merge.sh\"\n"
        "TX=$FIXTURE; TXROOT=$FIXTURE; RECORD=$FIXTURE/tasks/HACK-001.md\n"
        "ID=HACK-001; BASE=main; REMOTE_URL=git@github.com:org/repo.git\n"
        "approval_check \"$TIP\" https://github.com/org/repo/pull/7\n"
        "rc=$?\n"
        "if [ \"$rc\" = 0 ] && [ -n \"${CHECK_GH_RESULT:-}\" ]; then integrated_check \"$TIP\" \"$CHECK_GH_RESULT\"; rc=$?; fi\n"
        "echo \"$rc|$APPROVED_BY|$RM_REASON\"; exit \"$rc\"\n", encoding="utf-8")
    cases = {
        "current_independent": ("other|APPROVED|" + sha + "\n", 0),
        "self": ("author|APPROVED|" + sha + "\n", 1),
        "stale": ("other|APPROVED|" + "b" * 40 + "\n", 1),
        "dismissed": ("other|APPROVED|" + sha + "\nother|DISMISSED|" + sha + "\n", 1),
        "changes_requested": ("other|APPROVED|" + sha + "\nthird|CHANGES_REQUESTED|" + sha + "\n", 1),
    }
    actual = {}
    for name, (reviews, code) in cases.items():
        data = scratch / "reviews.txt"; data.write_text(reviews, encoding="utf-8")
        result = r.run([r.bash, harness.as_posix()], env={"PATH": (scratch / "bin").as_posix() + os.pathsep + r.env.get("PATH", ""),
            "PACKAGE": r.package.as_posix(), "FIXTURE": scratch.as_posix(), "TIP": sha,
            "UAK_REVIEW_MODE": "gh", "MOCK_REVIEWS": data.as_posix(),
            "MOCK_PR": sha + "|author|main|task/agent-1|org/repo|open|false|"}, allowed=None)
        expect(result.returncode == code, "gh mock contract mismatch " + name + ": " + result.stdout + result.stderr)
        actual[name] = result.returncode
    data.write_text("other|APPROVED|" + sha + "\n", encoding="utf-8")
    for name, pr_meta in (("pr_not_merged", sha + "|author|main|task/agent-1|org/repo|open|false|"),
                          ("wrong_merge_commit", sha + "|author|main|task/agent-1|org/repo|closed|true|" + "b" * 40)):
        result = r.run([r.bash, harness.as_posix()], env={"PATH": (scratch / "bin").as_posix() + os.pathsep + r.env.get("PATH", ""),
            "PACKAGE": r.package.as_posix(), "FIXTURE": scratch.as_posix(), "TIP": sha,
            "UAK_REVIEW_MODE": "gh", "MOCK_REVIEWS": data.as_posix(), "MOCK_PR": pr_meta,
            "CHECK_GH_RESULT": "c" * 40}, allowed=None)
        expect(result.returncode == 1 and "COMMIT" in result.stdout, "gh result identity contract mismatch " + name)
        actual[name] = result.returncode
    return {"scope": "API contract mocked; no authenticated GitHub request", "cases": actual}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--work-dir", type=Path, default=os.environ.get("UAK_MERGE_WORK_DIR"))
    parser.add_argument("--report", type=Path, default=os.environ.get("UAK_MERGE_REPORT"))
    args = parser.parse_args()
    scratch = args.work_dir or Path(tempfile.mkdtemp(prefix="hack-review-merge-"))
    scratch.mkdir(parents=True, exist_ok=True)
    runner = Runner(args.package.resolve(), scratch.resolve(), resolve_binary("bash"), resolve_binary("git"))
    production = (".uak/bin/uak", ".uak/bin/uak-coordination", ".uak/bin/lib/review-merge.sh",
                  ".uak/bin/secret-scan", ".uak/tests/test_review_merge.py", ".uak/tests/test_hack.py")
    hashes = {name: hashlib.sha256((runner.package / name).read_bytes()).hexdigest() for name in production}
    result = {"scope": "Local real Git, four merge processes, gh API mocked", "source_sha256": hashes,
              "results": [], "failures": 0}
    for test in (review_gates, concurrent_merges, gate_and_lease, squash_registration, gh_contract):
        started = time.monotonic()
        try:
            evidence = test(runner)
            entry = {"name": test.__name__, "status": "PASS", "evidence": evidence}
            print("PASS " + test.__name__, flush=True)
        except Exception as error:
            entry = {"name": test.__name__, "status": "FAIL", "error": str(error)}
            result["failures"] += 1
            print("FAIL " + test.__name__ + ": " + str(error), flush=True)
        entry["seconds"] = round(time.monotonic() - started, 3)
        result["results"].append(entry)
    result["checks"] = len(result["results"])
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("REVIEW_MERGE: %d/%d PASS" % (result["checks"] - result["failures"], result["checks"]))
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
