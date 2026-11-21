#!/usr/bin/env python3
"""UAK-131: `Merge-Engine: ci` in .uak/PROJECT.md (on the base branch). Real Git and real `uak merge`; the forge is a
`gh` stub in PATH, the way test_review_merge's gh_contract does it, and the remote is a local bare repo that git
reaches through `url.<path>.insteadOf` (GIT_CONFIG_*), so the engine sees a github.com remote and PR.

  human_is_the_default                  no Merge-Engine, or `human`: an engine file still goes to a human, as before
  ci_merges_when_every_check_is_green   `ci`: the same task lands through the gate when every check run of the tip passed
  a_running_check_waits                 a check still running, or none found yet: MERGE_WAIT, nothing queued, never green
  a_red_check_refuses                   a red check among green ones (the second run, not the first) goes to the human
  lock_files_still_need_a_human         lock files, migrations, PROJECT.md and a path that is also engine and lock: human
  record_names_the_policy               the task record says `Merge-Policy: ci` and the checks counted
  a_task_cannot_turn_the_policy_on      the value is read from the base: a diff that sets it changes nothing and goes to the human
  gh_unavailable_is_not_green           the forge cannot be read: the human, with the reason
  doctor_warns_without_required_checks  `ci` set and no required checks on the base (or not knowable): a warning

Why (`uak metrics`, 2026-11-21): the gate sent 39 of 39 queued tasks to a human, 38 of them as "Shared resource/CI needs
a human"; 46 of 104 integrated tasks were built by the gate and then landed by a person who added no check of their own.
Standard library only. Run: python3 kit/.uak/tests/test_merge_engine_policy.py [--case NAME]."""
import argparse
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hack import Failure, Runner, expect, resolve_binary  # noqa: E402
from test_review_merge import actor, approve, judge  # noqa: E402

PR = "https://github.com/org/repo/pull/1"
GH_URL = "https://github.com/org/repo.git"
ENGINE_FILE = ".uak/bin/lib/engine-note.txt"
GH_STUB = """#!/usr/bin/env bash
# gh api repos/org/repo/commits/SHA/check-runs | .../status | .../branches/main/protection/required_status_checks
[ -z "${MOCK_GH_DOWN:-}" ] || exit 1
[ "$1" = auth ] && exit 0
case "$2" in
  */check-runs) cat "$MOCK_CHECKS";;
  */commits/*/status) cat "$MOCK_STATUS";;
  */protection/required_status_checks) [ -n "${MOCK_REQUIRED:-}" ] && cat "$MOCK_REQUIRED" || exit 1;;
  *) exit 1;;
esac
"""
GREEN = "build (linux)|completed|success\nbuild (macos)|completed|success\nlint|completed|success\ndocs|completed|skipped\n"
STATUS_NONE = "pending|0\n"
_cache = {}


def runner(scratch):
    r = Runner(Path(__file__).resolve().parents[2], scratch, resolve_binary("bash"), resolve_binary("git"))
    stub = scratch / "stub"
    stub.mkdir()
    (stub / "gh").write_text(GH_STUB, encoding="utf-8", newline="\n")
    os.chmod(str(stub / "gh"), os.stat(str(stub / "gh")).st_mode | stat.S_IXUSR)
    r.env["PATH"] = stub.as_posix() + os.pathsep + r.env["PATH"]
    r.env["MOCK_CHECKS"] = (scratch / "checks.txt").as_posix()
    r.env["MOCK_STATUS"] = (scratch / "status.txt").as_posix()
    checks(r, GREEN)
    return r


def checks(r, text, status=STATUS_NONE):
    Path(r.env["MOCK_CHECKS"]).write_text(text, encoding="utf-8")
    Path(r.env["MOCK_STATUS"]).write_text(status, encoding="utf-8")


def fixture(r, name, path, project="", content="ready-HACK-001\n"):
    f = r.fixture("pol-" + name, paths={"HACK-001": path}, count=1)
    (f.seed / ".uak/PROJECT.md").write_text(
        "# Fixture\nMode: sprint\nAutonomy: yes\nAuto-Merge: yes\nBacklog-Approved: yes\nBacklog-Proposed-Epoch: 1000000\n"
        "Freeze-Epoch: 9999999\nReview-Mode: claims\nEvents-Per-Session: 100000\nCheckpoint-Percent: 60\n"
        "Merge-Lease-Seconds: 1800\nMerge-Wait-Seconds: 600\n" + project, encoding="utf-8")
    tasks = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8")
    tasks = tasks.replace(".uak/bin/smoke --package-only", "grep -q ready-HACK-001 '%s'" % path)
    (f.seed / ".uak/TASKS.md").write_text(tasks, encoding="utf-8")
    # A runnable fixture product keeps the gate's smoke from calling tests that would run merge recursively.
    (f.seed / ".uak/bin/smoke").write_text(
        "#!/usr/bin/env bash\nset -eu\ncd \"$(dirname \"$0\")/../..\"\nbash -n .uak/bin/uak\n"
        "[ -f .uak/bin/smoke-project ] || { echo PRODUCT_UNVERIFIED; exit 2; }\nbash .uak/bin/smoke-project\necho FIXTURE_PRODUCT_PASS\n",
        encoding="utf-8")
    (f.seed / ".uak/bin/smoke-project").write_text("#!/usr/bin/env bash\nset -eu\n[ ! -f .red-product-gate ]\n", encoding="utf-8")
    r.g(f.seed, "add", "-A")
    r.g(f.seed, "commit", "-m", "Configure the policy fixture")
    r.g(f.seed, "push", "origin", "main")
    f.main_head = r.g(f.remote, "rev-parse", "main").stdout.strip()
    for clone, worktree in zip(f.clones, f.worktrees):
        r.g(clone, "fetch", "origin", "main")
        r.g(worktree, "reset", "--hard", "origin/main")
        r.g(clone, "config", "remote.origin.url", GH_URL)  # what the engine reads; git reaches the bare repo by insteadOf
    f.path, f.content = path, content
    return f


def ship(f, r):
    """claim, write the file, `done` with a github.com PR, a registered reviewer approves the exact tip."""
    f.claim(0, "HACK-001")
    target = f.worktrees[0] / f.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f.content, encoding="utf-8")
    r.g(f.worktrees[0], "add", f.path)
    r.g(f.worktrees[0], "commit", "-m", "Implement HACK-001")
    r.g(f.worktrees[0], "push", "origin", f.branches[0])
    tip = r.g(f.worktrees[0], "rev-parse", "HEAD").stdout.strip()
    f.hack(0, "done", "HACK-001", "--pr", PR, "--evidence", "Fixture acceptance", now=1000010)
    judge(f)
    approve(f, "HACK-001", tip)
    return tip


def merged(r, f):
    return r.g(f.remote, "rev-parse", "main").stdout.strip() != f.main_head


def forge(r, name):
    """The engine reads a github.com remote; git reaches the local bare repo through url.<path>.insteadOf."""
    remote = r.scratch / ("pol-" + name) / "remote.git"
    r.env["GIT_CONFIG_COUNT"] = "3"
    r.env["GIT_CONFIG_KEY_2"] = "url.%s.insteadOf" % remote.as_posix()
    r.env["GIT_CONFIG_VALUE_2"] = GH_URL


def attempt(r, name, path=ENGINE_FILE, project="", content="ready-HACK-001\n"):
    forge(r, name)
    f = fixture(r, name, path, project, content)
    tip = ship(f, r)
    out = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    return f, tip, out


def human_is_the_default(r):
    for label, project in (("absent", ""), ("explicit human", "Merge-Engine: human\n"), ("a typo is human", "Merge-Engine: yes\n")):
        checks(r, GREEN)
        f, _, out = attempt(r, "human-" + label.split()[0], project=project)
        expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout, "%s: %s" % (label, out.stdout + out.stderr))
        expect("Shared resource/CI needs a human: %s" % ENGINE_FILE in out.stdout, "%s: reason: %s" % (label, out.stdout))
        expect(not merged(r, f), "%s: base must not move" % label)
        expect("Merge-Policy" not in f.show("queue/HACK-001.md") + f.show("tasks/HACK-001.md"), "no policy recorded")
    return "engine file goes to a human with absent, human and an unknown value"


def green_run(r):
    if "green" not in _cache:
        checks(r, GREEN)
        _cache["green"] = attempt(r, "green", project="Merge-Engine: ci\n")
    return _cache["green"]


def ci_merges_when_every_check_is_green(r):
    f, _, out = green_run(r)
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout, "merge through the gate: " + out.stdout + out.stderr)
    expect(merged(r, f), "base moved")
    expect("State: INTEGRATED" in f.show("tasks/HACK-001.md"), "integrated on claims")
    return "an engine file lands with 3 green checks and 1 skipped"


def record_names_the_policy(r):
    f, _, _ = green_run(r)
    record = f.show("tasks/HACK-001.md")
    expect("Merge-Policy: ci" in record, "Merge-Policy: ci in the record: " + record)
    m = re.search(r"^Merge-Checks: (.*)$", record, re.M)
    expect(m and all(n in m.group(1) for n in ("build (linux)", "build (macos)", "lint")) and "3 " in m.group(1),
           "the checks counted are named: %r" % (m and m.group(1)))
    expect("docs" not in m.group(1), "a skipped check is not counted as a success: " + m.group(1))
    return "Merge-Policy: ci · " + m.group(1)


def a_running_check_waits(r):
    for label, text in (("one running", GREEN + "e2e|in_progress|\n"), ("one queued", GREEN + "e2e|queued|\n"),
                        ("none found yet", "")):
        checks(r, text)
        f, _, out = attempt(r, "wait-" + label.split()[1] if " " in label else "wait-none", project="Merge-Engine: ci\n")
        expect(out.returncode == 3 and "MERGE_WAIT" in out.stdout and "MERGE_HUMAN" not in out.stdout, "%s: %s" % (label, out.stdout + out.stderr))
        expect(not merged(r, f), "%s: never green" % label)
        expect("State: HUMAN" not in f.show("queue/HACK-001.md") and "queue/merge-lock.md" not in f.files("."),
               "%s: nothing queued for a human, lock released" % label)
    # and once it finished green the same task lands
    checks(r, GREEN + "e2e|completed|success\n")
    out = f.hack(0, "merge", "HACK-001", now=1000040, allowed=None)
    expect("INTEGRATED" in out.stdout and merged(r, f), "after the check finishes: " + out.stdout)
    return "running, queued and absent checks wait; the retry lands"


def a_red_check_refuses(r):
    for label, text, status in (("a later run red", GREEN + "e2e|completed|failure\n", STATUS_NONE),
                                ("cancelled", GREEN + "e2e|completed|cancelled\n", STATUS_NONE),
                                ("only skipped", "docs|completed|skipped\nlint|completed|neutral\n", STATUS_NONE),
                                ("a commit status failed", GREEN, "failure|1\n")):
        checks(r, text, status)
        f, _, out = attempt(r, "red-" + label.split()[-1], project="Merge-Engine: ci\n")
        expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout, "%s: %s" % (label, out.stdout + out.stderr))
        expect(not merged(r, f), "%s: base must not move" % label)
        if label == "a later run red":
            expect("e2e" in out.stdout, "the red check is named: " + out.stdout)
    return "failure, cancelled, only-skipped and a failed status all refuse"


def lock_files_still_need_a_human(r):
    checks(r, GREEN)
    for name, path in (("lock", "package-lock.json"), ("migration", "db/migration/V9__x.sql"),
                       ("both", ".uak/bin/lib/migrations/x.txt"), ("project", ".uak/PROJECT.md"),
                       ("provenance", ".uak/bin/.smoke-project.provenance")):
        f, _, out = attempt(r, "lock-" + name, path=path, project="Merge-Engine: ci\n",
                            content="ready-HACK-001\n" if name != "project" else "ready-HACK-001\nMode: sprint\n")
        expect(out.returncode == 3 and "Shared resource/CI needs a human: %s" % path in out.stdout, "%s: %s" % (path, out.stdout + out.stderr))
        expect(not merged(r, f), "%s: base must not move" % path)
    return "lock, migration, engine+migration, PROJECT.md and the smoke provenance file go to the human with ci on"


def a_task_cannot_turn_the_policy_on(r):
    checks(r, GREEN)
    f, _, out = attempt(r, "selfon", path=".uak/PROJECT.md", content="ready-HACK-001\nMerge-Engine: ci\n")
    expect(out.returncode == 3 and "Shared resource/CI needs a human: .uak/PROJECT.md" in out.stdout, out.stdout + out.stderr)
    expect(not merged(r, f), "base must not move")
    return "PROJECT.md in the diff is the human's, and the base still says human"


def gh_unavailable_is_not_green(r):
    checks(r, GREEN)
    r.env["MOCK_GH_DOWN"] = "1"
    try:
        f, _, out = attempt(r, "ghdown", project="Merge-Engine: ci\n")
    finally:
        del r.env["MOCK_GH_DOWN"]
    expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout and "checks" in out.stdout, out.stdout + out.stderr)
    expect(not merged(r, f), "never green without the forge")
    return "gh down: the human, with the reason"


def doctor_warns_without_required_checks(r):
    checks(r, GREEN)
    forge(r, "doctor")
    f = fixture(r, "doctor", ENGINE_FILE, "Merge-Engine: ci\n")
    clone = f.clones[0]
    r.g(clone, "pull", "-q", "origin", "main")
    required = Path(r.env["MOCK_CHECKS"]).with_name("required.json")
    cases = (("none", None, "has no required status checks"),
             ("some", "1\n", None))
    for label, body, want in cases:
        if body is None:
            r.env.pop("MOCK_REQUIRED", None)
        else:
            required.write_text(body, encoding="utf-8")
            r.env["MOCK_REQUIRED"] = required.as_posix()
        out = r.run([r.bash, ".uak/bin/doctor"], cwd=clone, env={"UAK_AGENT": "agent-1"}, allowed=None)
        text = out.stdout + out.stderr
        if want:
            expect(re.search(r"WARN .*Merge-Engine: ci.*" + want, text), "%s: expected the warning: %s" % (label, text[-1500:]))
        else:
            expect("Merge-Engine: ci" not in text or "OK" in text, "%s: no warning with a required check: %s" % (label, text[-1500:]))
            expect(not re.search(r"WARN .*Merge-Engine", text), "%s: no warning: %s" % (label, text[-1500:]))
    r.env["MOCK_GH_DOWN"] = "1"
    out = r.run([r.bash, ".uak/bin/doctor"], cwd=clone, env={"UAK_AGENT": "agent-1"}, allowed=None)
    del r.env["MOCK_GH_DOWN"]
    expect(re.search(r"WARN .*Merge-Engine: ci.*cannot tell", out.stdout + out.stderr), "gh down says it cannot tell: " + (out.stdout + out.stderr)[-1500:])
    return "warns with no required checks and when it cannot tell; silent with one"


TESTS = [human_is_the_default, ci_merges_when_every_check_is_green, a_running_check_waits, a_red_check_refuses,
         lock_files_still_need_a_human, record_names_the_policy, a_task_cannot_turn_the_policy_on,
         gh_unavailable_is_not_green, doctor_warns_without_required_checks]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--package")  # smoke passes it to every test; this one reads its own tree
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-engine-policy-") as tmp:
        r = runner(Path(tmp))
        for t in [t for t in TESTS if not args.case or t.__name__ == args.case]:
            try:
                print("PASS %s (%s)" % (t.__name__, t(r)), flush=True)
            except Failure as exc:
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:2500]), flush=True)
    print("MERGE_ENGINE_POLICY_RESULT %s" % ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
