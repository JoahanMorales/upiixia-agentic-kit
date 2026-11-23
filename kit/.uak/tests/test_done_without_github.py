#!/usr/bin/env python3
"""UAK-180: a project without GitHub can finish a task. QA round C (2026-11-14, C-2): on a local bare remote
`wt pr` said "Not a GitHub remote" and `uak done --pr file://...` said "needs --pr HTTPS URL (... wt pr)", a dead
loop; one tester invented an https URL to get out. With Review-Mode: claims or a non-GitHub remote, `--pr none`
(or the task's branch) is accepted and recorded, and both messages name it. A GitHub remote in PR review mode
still needs a real PR URL. Real Git, a local bare remote."""
import argparse
import concurrent.futures
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary



def github_url(f):
    return "https://github.com/fixture-org/%s.git" % f.base.name


def env_for(r, f, index, github=False):
    """UAK_* for agent N; on a GitHub-looking origin, every Git process maps that URL to the local bare remote."""
    env = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": "1000010", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    if github:
        n = int(r.env.get("GIT_CONFIG_COUNT", "0"))
        env.update({"GIT_CONFIG_COUNT": str(n + 1), "GIT_CONFIG_KEY_%d" % n: "url.%s.insteadOf" % f.remote.as_posix(),
                    "GIT_CONFIG_VALUE_%d" % n: github_url(f)})
    return env


def uak(r, f, index, *args, github=False, allowed=(0,)):
    return r.run([r.bash, ".uak/bin/uak", *map(str, args)], cwd=f.worktrees[index], env=env_for(r, f, index, github), allowed=allowed)


def ready(r, f, index, task, github=False):
    uak(r, f, index, "claim", task, "--branch", f.branches[index], "--worktree", f.worktrees[index].as_posix(),
        "--next", "Ship it", github=github)
    w = f.worktrees[index]
    (w / ".uak-env").write_bytes(("UAK_TASK=%s\nUAK_AGENT=agent-%d\n" % (task, index + 1)).encode())
    (w / "src").mkdir(exist_ok=True)
    (w / "src" / ("%s.txt" % task)).write_text("a change\n", encoding="utf-8")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", task + ": a change")
    r.run([r.git, "push", "-q", "origin", f.branches[index]], cwd=w, env=env_for(r, f, index, github))


def as_github(r, f, index):
    """The clone's origin reads as a GitHub URL (env_for maps it back to the local bare remote)."""
    r.g(f.clones[index], "remote", "set-url", "origin", github_url(f))


def done(r, f, index, task, pr, github=False):
    return uak(r, f, index, "done", task, "--pr", pr, "--evidence", "fixture exit 0", "--no-red", "fixture",
               github=github, allowed=None)


def record_field(f, task, key):
    m = re.search(r"^%s:\s*(.*)$" % re.escape(key), f.show("tasks/%s.md" % task), re.M)
    return m.group(1).strip() if m else ""


def done_accepts_no_pr_without_github(r):
    f = r.fixture("dn-accept", count=3)
    # A local bare remote, Review-Mode: claims (the fixture's PROJECT.md): --pr none.
    ready(r, f, 0, "HACK-001")
    out = done(r, f, 0, "HACK-001", "none")
    expect(out.returncode == 0, "--pr none is accepted on a local remote: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(record_field(f, "HACK-001", "State") == "REVIEW", "HACK-001 is in REVIEW")
    expect(record_field(f, "HACK-001", "PR") == "none", "PR none is recorded: %r" % record_field(f, "HACK-001", "PR"))
    expect("reviews none" not in f.show("tasks/HACK-001.md"), "the review hint names the branch, not 'none'")
    # The task's branch instead of a PR URL.
    ready(r, f, 1, "HACK-002")
    out = done(r, f, 1, "HACK-002", f.branches[1])
    expect(out.returncode == 0, "--pr BRANCH is accepted: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(record_field(f, "HACK-002", "PR") == f.branches[1], "the branch is recorded: %r" % record_field(f, "HACK-002", "PR"))
    # A GitHub remote with Review-Mode: claims needs no PR either.
    as_github(r, f, 2)
    ready(r, f, 2, "HACK-003", github=True)
    out = done(r, f, 2, "HACK-003", "none", github=True)
    expect(out.returncode == 0, "Review-Mode: claims on GitHub accepts --pr none: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    expect(record_field(f, "HACK-003", "PR") == "none", "PR none recorded on HACK-003")
    return "none, branch, claims on GitHub"


def wt_pr_names_the_fallback(r):
    f = r.fixture("dn-wtpr", count=1)
    ready(r, f, 0, "HACK-001")
    w = f.worktrees[0]
    env = {"UAK_AGENT": "agent-1", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    out = r.run([r.bash, ".uak/bin/wt", "pr"], cwd=w, env=env, allowed=None)
    text = out.stdout + out.stderr
    expect("Not a GitHub remote" in text, "wt pr still says it is not GitHub: " + text[-500:])
    expect("--pr none" in text and "uak done HACK-001" in text, "wt pr names the no-PR fallback with the task: " + text[-500:])
    # The done error for a URL it cannot use names the same fallback, not only wt pr.
    bad = done(r, f, 0, "HACK-001", "file://%s#%s" % (f.remote.as_posix(), f.branches[0]))
    btext = bad.stdout + bad.stderr
    expect(bad.returncode != 0 and "HTTPS" in btext, "a file:// URL is still refused: " + btext[-500:])
    expect("--pr none" in btext, "the done error names --pr none: " + btext[-500:])
    expect(record_field(f, "HACK-001", "State") == "CLAIMED", "still CLAIMED after the refusal")
    return "both messages"


def github_still_needs_a_pr(r):
    f = r.fixture("dn-github", count=2)
    # PROJECT.md on main says Review-Mode: auto: GitHub reviews the PR.
    project = f.seed / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8").replace("Review-Mode: claims", "Review-Mode: auto"), encoding="utf-8")
    r.g(f.seed, "commit", "-q", "-am", "Review-Mode: auto")
    r.g(f.seed, "push", "-q", "origin", "main")
    as_github(r, f, 0)
    ready(r, f, 0, "HACK-001", github=True)
    for pr in ("none", f.branches[0]):
        out = done(r, f, 0, "HACK-001", pr, github=True)
        text = out.stdout + out.stderr
        expect(out.returncode != 0, "--pr %s is refused on GitHub with Review-Mode auto: %s" % (pr, text[-500:]))
        expect("wt pr" in text and "Review-Mode: claims" in text, "the refusal says how to get a PR or switch mode: " + text[-500:])
        expect(record_field(f, "HACK-001", "State") == "CLAIMED", "still CLAIMED after --pr %s" % pr)
    # Another branch name is never a stand-in, even where no PR is needed.
    ready(r, f, 1, "HACK-002")
    out = done(r, f, 1, "HACK-002", "some-other-branch")
    expect(out.returncode != 0 and "--pr none" in out.stdout + out.stderr, "a branch that is not the task's is refused: " + (out.stdout + out.stderr)[-500:])
    return "PR still required"


def merge_fixture(r, name, project_lines="", mode="claims", path="src/HACK-001.txt"):
    """A fixture whose base PROJECT.md says Review-Mode: MODE (plus extra lines) and whose product gate is the file
    the task adds; one task (HACK-001) and one more agent."""
    f = r.fixture(name, paths={"HACK-001": path}, count=2)
    (f.seed / ".uak/PROJECT.md").write_text(
        "# Fixture\nAutonomy: yes\nAuto-Merge: yes\nBacklog-Approved: yes\nBacklog-Proposed-Epoch: 1000000\n"
        "Freeze-Epoch: 9999999\nReview-Mode: %s\nEvents-Per-Session: 100000\nCheckpoint-Percent: 60\n"
        "Merge-Lease-Seconds: 1800\nMerge-Wait-Seconds: 600\n%s" % (mode, project_lines), encoding="utf-8")
    tasks = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8").replace(".uak/bin/smoke --package-only", "grep -q change %s" % path)
    (f.seed / ".uak/TASKS.md").write_text(tasks, encoding="utf-8")
    (f.seed / ".uak/bin/smoke").write_text(
        "#!/usr/bin/env bash\nset -eu\ncd \"$(dirname \"$0\")/../..\"\nbash -n .uak/bin/uak\n"
        "[ -f .uak/bin/smoke-project ] || { echo PRODUCT_UNVERIFIED; exit 2; }\nbash .uak/bin/smoke-project\necho FIXTURE_PRODUCT_PASS\n",
        encoding="utf-8")
    (f.seed / ".uak/bin/smoke-project").write_text("#!/usr/bin/env bash\nset -eu\n[ ! -f .red-product-gate ]\n", encoding="utf-8")
    r.g(f.seed, "add", "-A")
    r.g(f.seed, "commit", "-q", "-m", "Configure the fixture")
    r.g(f.seed, "push", "-q", "origin", "main")
    f.main_head = r.g(f.remote, "rev-parse", "main").stdout.strip()
    for clone, worktree in zip(f.clones, f.worktrees):
        r.g(clone, "fetch", "-q", "origin", "main")
        r.g(worktree, "reset", "-q", "--hard", "origin/main")
        # The agent's identity file is never part of the task's diff here.
        with open(str(clone / ".git" / "info" / "exclude"), "a", encoding="utf-8", newline="\n") as handle:
            handle.write(".uak-env\n")
    return f


def as_human(r, f, *args, github=False):
    env = env_for(r, f, 0, github)
    env.update({"UAK_AGENT": "human-registrar", "UAK_HUMAN": "human-registrar"})
    return r.run([r.bash, ".uak/bin/uak", *map(str, args)], cwd=f.clones[0], env=env)


def as_agent(r, f, name, *args, github=False, allowed=(0,)):
    env = env_for(r, f, 0, github)
    env.update({"UAK_AGENT": name, "UAK_NOW": "1000021"})
    return r.run([r.bash, ".uak/bin/uak", *map(str, args)], cwd=f.clones[0], env=env, allowed=allowed)


def moved(r, f):
    return r.g(f.remote, "rev-parse", "main").stdout.strip() != f.main_head


def tip_of(r, f):
    return r.g(f.worktrees[0], "rev-parse", "HEAD").stdout.strip()


def pr_none_still_needs_an_approval(r):
    notes = []
    for mode in ("claims", "gh", "auto"):
        f = merge_fixture(r, "dn-appr-" + mode, mode=mode)
        ready(r, f, 0, "HACK-001")
        out = done(r, f, 0, "HACK-001", "none")
        expect(out.returncode == 0, "%s: --pr none is accepted on a local remote: %s" % (mode, (out.stdout + out.stderr)[-500:]))
        tip = tip_of(r, f)
        as_human(r, f, "register-reviewer", "judge")
        # No approval at all.
        out = uak(r, f, 0, "merge", "HACK-001", allowed=None)
        expect(not moved(r, f), "%s: --pr none merged with no approval: %s" % (mode, (out.stdout + out.stderr)[-500:]))
        # The owner approving its own task, and another identity approving a tip that is no longer the tip.
        as_agent(r, f, "agent-1", "review", "HACK-001", "--sha", tip, "--verdict", "approve", allowed=None)
        out = uak(r, f, 0, "merge", "HACK-001", allowed=None)
        expect(not moved(r, f), "%s: --pr none merged on the owner's own approval" % mode)
        if mode == "gh":
            # gh reads an approval of a GitHub PR: a task with none never gets one.
            as_agent(r, f, "judge", "review", "HACK-001", "--sha", tip, "--verdict", "approve", allowed=None)
            out = uak(r, f, 0, "merge", "HACK-001", allowed=None)
            expect(not moved(r, f), "gh: --pr none merged: %s" % (out.stdout + out.stderr)[-500:])
            notes.append("gh refuses")
            continue
        as_agent(r, f, "judge", "review", "HACK-001", "--sha", tip, "--verdict", "approve")
        (f.worktrees[0] / "src" / "HACK-001.txt").write_text("a change, then another\n", encoding="utf-8")
        r.g(f.worktrees[0], "commit", "-q", "-am", "HACK-001: a later change")
        r.run([r.git, "push", "-q", "origin", f.branches[0]], cwd=f.worktrees[0], env=env_for(r, f, 0))
        out = uak(r, f, 0, "merge", "HACK-001", allowed=None)
        expect(not moved(r, f), "%s: an approval of an older tip let a newer one merge: %s" % (mode, (out.stdout + out.stderr)[-500:]))
        as_agent(r, f, "judge", "review", "HACK-001", "--sha", tip_of(r, f), "--verdict", "approve")
        out = uak(r, f, 0, "merge", "HACK-001", allowed=None)
        expect(out.returncode == 0 and moved(r, f), "%s: the exact tip approved by another identity merges: %s" % (mode, (out.stdout + out.stderr)[-700:]))
        notes.append(mode + " merges once approved")
    return ", ".join(notes)


def pr_none_goes_to_the_human_under_merge_engine_ci(r):
    engine = ".uak/bin/lib/metrics.py"  # the one kind of file Merge-Engine: ci releases to the gate, on the checks of a PR
    f = merge_fixture(r, "dn-ci", project_lines="Mode: sprint\nMerge-Engine: ci\nMerge-Engine-Checks: build (*\n", path=engine)
    as_github(r, f, 0)
    uak(r, f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(), "--next", "Ship it", github=True)
    w = f.worktrees[0]
    (w / ".uak-env").write_bytes(b"UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n")
    (w / engine).write_text((w / engine).read_text(encoding="utf-8") + "\n# change\n", encoding="utf-8")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", "HACK-001: a change")
    r.run([r.git, "push", "-q", "origin", f.branches[0]], cwd=w, env=env_for(r, f, 0, True))
    out = done(r, f, 0, "HACK-001", "none", github=True)
    expect(out.returncode == 0, "claims on GitHub accepts --pr none: %s" % (out.stdout + out.stderr)[-500:])
    as_human(r, f, "register-reviewer", "judge", github=True)
    as_agent(r, f, "judge", "review", "HACK-001", "--sha", tip_of(r, f), "--verdict", "approve", github=True)
    out = uak(r, f, 0, "merge", "HACK-001", github=True, allowed=None)
    text = out.stdout + out.stderr
    expect(not moved(r, f), "Merge-Engine ci merged an engine file of a task with no PR: " + text[-500:])
    expect("MERGE_HUMAN" in text, "a task with no PR goes to the human: " + text[-500:])
    expect("Merge-Engine ci reads the checks of a github.com PR: this task has none" in text,
           "the reason says the required checks need a PR and the task has none: " + text[-500:])
    return "human, reason names the pull request"


def env_review_mode_does_not_override_the_base(r):
    f = merge_fixture(r, "dn-env", mode="gh")
    as_github(r, f, 0)
    ready(r, f, 0, "HACK-001", github=True)
    for value in ("claims", "auto"):
        env = env_for(r, f, 0, True)
        env["UAK_REVIEW_MODE"] = value
        out = r.run([r.bash, ".uak/bin/uak", "done", "HACK-001", "--pr", "none", "--evidence", "fixture exit 0", "--no-red", "fixture"],
                    cwd=f.worktrees[0], env=env, allowed=None)
        text = out.stdout + out.stderr
        expect(out.returncode != 0 and "Review-Mode is gh" in text,
               "UAK_REVIEW_MODE=%s let --pr none through on a base that says gh: %s" % (value, text[-500:]))
        expect(record_field(f, "HACK-001", "State") == "CLAIMED", "still CLAIMED with UAK_REVIEW_MODE=%s" % value)
    return "the base wins"


def merge_with_env_mode(r, f, value):
    """Merge HACK-001 with UAK_REVIEW_MODE=value in the environment of uak merge."""
    env = env_for(r, f, 0)
    env["UAK_REVIEW_MODE"] = value
    return r.run([r.bash, ".uak/bin/uak", "merge", "HACK-001"], cwd=f.worktrees[0], env=env, allowed=None)


def env_review_mode_does_not_change_the_merge(r):
    """UAK-186: the base says gh, the task has no real PR and an approval on claims: the variable in the shell of whoever
    runs uak merge must not turn that into a claims merge."""
    f = merge_fixture(r, "dn-envm", mode="gh")
    ready(r, f, 0, "HACK-001")
    expect(done(r, f, 0, "HACK-001", "none").returncode == 0, "--pr none accepted on a local remote")
    as_human(r, f, "register-reviewer", "judge")
    as_agent(r, f, "judge", "review", "HACK-001", "--sha", tip_of(r, f), "--verdict", "approve")
    for value in ("claims", "auto", "CLAIMS", " claims"):
        out = merge_with_env_mode(r, f, value)
        expect(not moved(r, f), "UAK_REVIEW_MODE=%s merged a task on a gh base: %s" % (value, (out.stdout + out.stderr)[-500:]))
    return "gh base, 4 variable values, nothing merged"


def merge_reads_the_base_mode(r):
    """UAK-186: the base says claims: a claims approval merges, and a variable that says gh does not stop it."""
    f = merge_fixture(r, "dn-basem", mode="claims")
    ready(r, f, 0, "HACK-001")
    expect(done(r, f, 0, "HACK-001", "none").returncode == 0, "--pr none accepted")
    as_human(r, f, "register-reviewer", "judge")
    as_agent(r, f, "judge", "review", "HACK-001", "--sha", tip_of(r, f), "--verdict", "approve")
    out = merge_with_env_mode(r, f, "gh")
    expect(out.returncode == 0 and moved(r, f), "the base's claims decides, not the variable: %s" % (out.stdout + out.stderr)[-700:])
    return "claims base merges with UAK_REVIEW_MODE=gh"


TESTS = [done_accepts_no_pr_without_github, wt_pr_names_the_fallback, github_still_needs_a_pr]
TESTS += [pr_none_still_needs_an_approval, pr_none_goes_to_the_human_under_merge_engine_ci, env_review_mode_does_not_override_the_base]
TESTS += [env_review_mode_does_not_change_the_merge, merge_reads_the_base_mode]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-done-nogh-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        selected = [t for t in TESTS if not args.case or t.__name__ in args.case]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, selected))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("DONE_WITHOUT_GITHUB_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
