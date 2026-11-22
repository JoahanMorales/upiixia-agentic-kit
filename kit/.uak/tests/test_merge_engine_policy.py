#!/usr/bin/env python3
"""UAK-131: `Merge-Engine: ci` in .uak/PROJECT.md (on the base branch). Real Git and real `uak merge`; the forge is a
`gh` stub in PATH, the way test_review_merge's gh_contract does it, and the remote is a local bare repo that git
reaches through `url.<path>.insteadOf` (GIT_CONFIG_*), so the engine sees a github.com remote and PR.

  human_is_the_default                  no Merge-Engine, or `human`: an engine file still goes to a human, as before
  ci_merges_when_every_check_is_green   `ci`: the same task lands through the gate when every check run of the tip passed
  a_running_check_waits                 a check still running, or none found yet: MERGE_WAIT, nothing queued, never green
  a_red_check_refuses                   a red check among green ones (the second run, not the first) goes to the human
  lock_files_still_need_a_human         lock files, migrations, PROJECT.md and a path that is also engine and lock: human (the engine
                                        subset is `.uak/bin/uak`, `.uak/bin/uak-coordination`, `.uak/bin/lib/`)
  record_names_the_policy               the task record says `Merge-Policy: ci` and the checks counted
  a_task_cannot_turn_the_policy_on      the value is read from the base: a diff that sets it changes nothing and goes to the human
  gh_unavailable_is_not_green           the forge cannot be read: the human, with the reason
  doctor_fails_without_required_checks  `ci` set and no list of required checks (forge or PROJECT.md): a FAIL, names printed
  status_and_lone_checks_prove_nothing  a bare success status, a lone `x` check, an unnamed check: refused or waiting
  shards_match_by_prefix                `suite (*` style patterns match shard runs; one red shard refuses
  a_missing_required_check_waits_then_refuses  no run matches: wait while a workflow run is going, refuse once complete
  workflow_or_smoke_goes_to_the_human   workflows, smoke, githooks, guard and their fixtures dirs are never released by ci
  forge_required_checks_win             the forge's required checks replace the PROJECT.md list
  no_required_list_goes_to_the_human    `ci` with neither source: the human, and the reason says how to configure it

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
[ "$1" = auth ] || [ "$1" = pr ] && exit 0
case "$2" in
  */check-runs) cat "$MOCK_CHECKS";;
  */commits/*/status) cat "$MOCK_STATUS";;
  repos/org/repo) echo true,false,false;;
  */protection/required_status_checks) [ -n "${MOCK_REQUIRED:-}" ] && cat "$MOCK_REQUIRED" || exit 1;;
  */actions/runs*) [ -z "${MOCK_RUNS:-}" ] || cat "$MOCK_RUNS";;
  *) exit 1;;
esac
"""
CI = "Merge-Engine: ci\nMerge-Engine-Checks: build (*, lint\n"
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
    r.env["MOCK_RUNS"] = (scratch / "runs.txt").as_posix()
    (scratch / "runs.txt").write_text("", encoding="utf-8")
    checks(r, GREEN)
    return r


def checks(r, text, status=STATUS_NONE):
    Path(r.env["MOCK_CHECKS"]).write_text(text, encoding="utf-8")
    Path(r.env["MOCK_STATUS"]).write_text(status, encoding="utf-8")


def fixture(r, name, path, project="", content="ready-HACK-001\n", mode="sprint"):
    plist = path if isinstance(path, list) else [path]  # several paths: the first is the one the gate reports
    path = plist[0]
    f = r.fixture("pol-" + name, paths={"HACK-001": ", ".join(plist)}, count=1, owners={p: "HACK-001" for p in plist})
    (f.seed / ".uak/PROJECT.md").write_text(
        "# Fixture\nMode: " + mode + "\nAutonomy: yes\nAuto-Merge: yes\nBacklog-Approved: yes\nBacklog-Proposed-Epoch: 1000000\n"
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
    f.path, f.paths_all, f.content = path, plist, content
    return f


def ship(f, r):
    """claim, write the file, `done` with a github.com PR, a registered reviewer approves the exact tip."""
    f.claim(0, "HACK-001")
    for each in f.paths_all:
        target = f.worktrees[0] / each
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and each.startswith(".uak/bin/"):  # a real engine file: append a comment, never overwrite the engine in use
            target.write_text(target.read_text(encoding="utf-8") + "\n# ready-HACK-001\n", encoding="utf-8")
        else:
            target.write_text(f.content, encoding="utf-8")
        r.g(f.worktrees[0], "add", each)
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


def attempt(r, name, path=ENGINE_FILE, project="", content="ready-HACK-001\n", mode="sprint"):
    forge(r, name)
    f = fixture(r, name, path, project, content, mode)
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
        _cache["green"] = attempt(r, "green", project=CI)
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
    expect(m and all(n in m.group(1) for n in ("build (linux)", "build (macos)", "lint")) and m.group(1).startswith("3: "),
           "the checks counted are named: %r" % (m and m.group(1)))
    expect("docs" not in m.group(1), "a skipped check is not counted as a success: " + m.group(1))
    expect(re.search(r"^Merge-Policy: ci$", record, re.M) and "Merge-Checks" in record, "record")
    return "Merge-Policy: ci · " + m.group(1)


def a_running_check_waits(r):
    for label, text in (("one running", GREEN + "e2e|in_progress|\n"), ("one queued", GREEN + "e2e|queued|\n"),
                        ("none found yet", "")):
        checks(r, text)
        f, _, out = attempt(r, "wait-" + label.split()[1] if " " in label else "wait-none", project=CI)
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
                                ("one shard red", GREEN + "build (windows)|completed|failure\n", STATUS_NONE),
                                ("cancelled", GREEN + "e2e|completed|cancelled\n", STATUS_NONE),
                                ("only skipped", "docs|completed|skipped\nlint|completed|neutral\n", STATUS_NONE),
                                ("a commit status failed", GREEN, "failure|1\n")):
        checks(r, text, status)
        f, _, out = attempt(r, "red-" + re.sub(r"\W+", "", label), project=CI)
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
        f, _, out = attempt(r, "lock-" + name, path=path, project=CI,
                            content="ready-HACK-001\n" if name != "project" else "ready-HACK-001\nMode: sprint\n")
        expect(out.returncode == 3 and "Shared resource/CI needs a human: %s" % path in out.stdout, "%s: %s" % (path, out.stdout + out.stderr))
        expect(not merged(r, f), "%s: base must not move" % path)
    return "lock, migration, engine+migration, PROJECT.md and the smoke provenance file go to the human with ci on"


def marathon_needs_human_independence(r):
    checks(r, GREEN)
    f, _, out = attempt(r, "marathon", project=CI, mode="marathon")
    expect(out.returncode == 3 and "Review-Independence: human" in out.stdout and not merged(r, f), out.stdout + out.stderr)
    f, _, out = attempt(r, "marathon-human", project=CI + "Review-Independence: human\n", mode="marathon")
    expect("INTEGRATED" in out.stdout and merged(r, f), "with Review-Independence: human it lands: " + out.stdout + out.stderr)
    return "marathon: refused with agent independence, lands with human"


def metrics_counts_ci_merges_apart(r):
    f, _, _ = green_run(r)
    out = r.run([r.bash, ".uak/bin/uak", "metrics", "--json"], cwd=f.clones[0], env={"UAK_AGENT": "agent-1", "UAK_NOW": "1000100"}, allowed=None)
    m = re.search(r'"gate_pushed_ci":\s*\{[^}]*"n":\s*(\d+)', out.stdout)
    expect(m and m.group(1) == "1", "uak metrics counts the Merge-Engine ci merge apart: " + out.stdout[-800:] + out.stderr[-400:])
    return "gate_pushed_ci = 1"


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
        f, _, out = attempt(r, "ghdown", project=CI)
    finally:
        del r.env["MOCK_GH_DOWN"]
    expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout and "checks" in out.stdout, out.stdout + out.stderr)
    expect(not merged(r, f), "never green without the forge")
    return "gh down: the human, with the reason"


def doctor_fails_without_required_checks(r):
    checks(r, GREEN)
    forge(r, "doctor")
    f = fixture(r, "doctor", ENGINE_FILE, "Merge-Engine: ci\n")  # no Merge-Engine-Checks
    clone = f.clones[0]
    r.g(clone, "pull", "-q", "origin", "main")
    required = Path(r.env["MOCK_CHECKS"]).with_name("required.txt")

    def doctor():
        out = r.run([r.bash, ".uak/bin/doctor"], cwd=clone, env={"UAK_AGENT": "agent-1"}, allowed=None)
        return out.stdout + out.stderr

    r.env.pop("MOCK_REQUIRED", None)
    text = doctor()
    expect(re.search(r"FAIL .*Merge-Engine: ci is set and no list of required checks exists.*Merge-Engine-Checks", text), "neither source: a FAIL that says how to set it: " + text[-1500:])
    required.write_text("build (linux)\nlint\n", encoding="utf-8")
    r.env["MOCK_REQUIRED"] = required.as_posix()
    text = doctor()
    expect(re.search(r"OK .*Merge-Engine: ci will require every one of: build \(linux\),lint", text) and not re.search(r"FAIL .*Merge-Engine", text),
           "the forge's list: named, no FAIL: " + text[-1500:])
    r.env.pop("MOCK_REQUIRED", None)
    (clone / ".uak/PROJECT.md").write_text((clone / ".uak/PROJECT.md").read_text(encoding="utf-8") + "Merge-Engine-Checks: suite (*, windows (*\n", encoding="utf-8")
    text = doctor()
    expect(re.search(r"OK .*Merge-Engine: ci will require every one of: suite \(\*,windows \(\*", text), "PROJECT.md's list: named: " + text[-1500:])
    r.env["MOCK_GH_DOWN"] = "1"
    try:
        text = doctor()
    finally:
        del r.env["MOCK_GH_DOWN"]
    expect(re.search(r"OK .*Merge-Engine: ci will require", text), "the forge unreadable: the PROJECT.md list still counts: " + text[-1500:])
    return "FAIL with no list; the names printed with a forge list or a PROJECT.md list"


def status_and_lone_checks_prove_nothing(r):
    for label, text, status, want in (
            ("a bare success status", "", "success|1\n", "MERGE_WAIT"),
            ("a lone x check", "x|completed|success\n", STATUS_NONE, "MERGE_HUMAN"),
            ("an unnamed check", "|completed|success\n", STATUS_NONE, "MERGE_HUMAN"),
            ("a status and a lone check", "x|completed|success\n", "success|1\n", "MERGE_HUMAN"),
            ("unnamed plus whitespace", " |completed|success\nx|completed|success\n", STATUS_NONE, "MERGE_HUMAN")):
        checks(r, text, status)
        f, _, out = attempt(r, "weak-" + re.sub(r"\W+", "", label), project=CI)
        expect(want in out.stdout and not merged(r, f), "%s: expected %s, never green: %s" % (label, want, out.stdout + out.stderr))
    return "none of them is green"


def shards_match_by_prefix(r):
    checks(r, GREEN)
    f, _, out = attempt(r, "shards", project="Merge-Engine: ci\nMerge-Engine-Checks: build (*, lint\n")
    expect("INTEGRATED" in out.stdout and merged(r, f), "both build shards and lint counted: " + out.stdout + out.stderr)
    record = f.show("tasks/HACK-001.md")
    expect("build (linux)" in record and "build (macos)" in record and "lint" in record, "the shards are named in the record: " + record)
    return "prefix patterns match shard runs"


def a_missing_required_check_waits_then_refuses(r):
    project = "Merge-Engine: ci\nMerge-Engine-Checks: build (*, lint, windows (*\n"
    Path(r.env["MOCK_RUNS"]).write_text("in_progress\n", encoding="utf-8")
    checks(r, GREEN)
    f, _, out = attempt(r, "missing-wait", project=project)
    expect("MERGE_WAIT" in out.stdout and "MERGE_HUMAN" not in out.stdout and not merged(r, f), "a workflow run is still going: " + out.stdout + out.stderr)
    expect("State: HUMAN" not in f.show("queue/HACK-001.md"), "nothing queued for a human")
    Path(r.env["MOCK_RUNS"]).write_text("completed\n", encoding="utf-8")
    out = f.hack(0, "merge", "HACK-001", now=1000040, allowed=None)
    expect("MERGE_HUMAN" in out.stdout and "windows (*" in out.stdout and not merged(r, f), "everything is complete: refused: " + out.stdout)
    Path(r.env["MOCK_RUNS"]).write_text("", encoding="utf-8")
    return "wait while a workflow run is going, then the human"


def workflow_or_smoke_goes_to_the_human(r):
    checks(r, GREEN)
    for name, path in (("workflow", ".github/workflows/ci.yml"), ("smoke", ".uak/bin/smoke"), ("smokeproject", ".uak/bin/smoke-project"),
                       ("secretscan", ".uak/bin/secret-scan"), ("githook", ".githooks/pre-commit"), ("guard", ".uak/bin/guard"),
                       ("hookfixture", ".githooks/fixtures/x.txt")):
        f, _, out = attempt(r, "judge-" + name, path=path, project=CI)
        expect(out.returncode == 3 and "Shared resource/CI needs a human: %s" % path in out.stdout and not merged(r, f), "%s: %s" % (path, out.stdout + out.stderr))
    # An engine path under a fixtures directory is not test data: it needs the same green checks (a red one refuses).
    checks(r, GREEN + "e2e|completed|failure\n")
    f, _, out = attempt(r, "judge-libfixture", path=".uak/bin/lib/fixtures/x.txt", project=CI)
    expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout and "e2e" in out.stdout and not merged(r, f), "lib/fixtures is engine: " + out.stdout + out.stderr)
    f, _, out = attempt(r, "judge-libfixture-human", path=".uak/bin/lib/fixtures/x.txt")
    expect("Shared resource/CI needs a human: .uak/bin/lib/fixtures/x.txt" in out.stdout, "and shared under human: " + out.stdout)
    return "the things that judge or guard a merge are never released; lib/fixtures is not exempt"


def the_gate_itself_and_github_stay_human(r):
    """Under ci, all of .github/ (any letter case) and the four files that ARE the merge gate go to a human, alone or
    next to another lib file; another lib file alone still lands with the required checks green."""
    checks(r, GREEN)
    for name, path in (("action", ".github/actions/x/action.yml"), ("codeowners", ".github/CODEOWNERS"),
                       ("casefold", ".GitHub/Actions/y/action.yml"), ("reviewmerge", ".uak/bin/lib/review-merge.sh"),
                       ("tx", ".uak/bin/lib/tx.sh"), ("security", ".uak/bin/lib/security.sh"), ("config", ".uak/bin/lib/config.sh"),
                       ("mixed", ".uak/bin/lib/config.sh,.uak/bin/lib/status.sh")):
        paths = path.split(",")
        f, _, out = attempt(r, "gate-" + name, path=paths, project=CI)
        want = paths[0]
        expect(out.returncode == 3 and "Shared resource/CI needs a human: %s" % want in out.stdout and not merged(r, f), "%s: %s" % (path, out.stdout + out.stderr))
    f, _, out = attempt(r, "gate-other-lib", path=".uak/bin/lib/status.sh", project=CI)
    expect("INTEGRATED" in out.stdout and merged(r, f), "another lib file lands with the checks green: " + out.stdout + out.stderr)
    return ".github/ and the four gate files are a human's; lib/status.sh lands"


def forge_required_checks_win(r):
    required = Path(r.env["MOCK_CHECKS"]).with_name("required-win.txt")
    checks(r, GREEN)
    required.write_text("deploy\n", encoding="utf-8")  # the forge requires a check that never ran; PROJECT.md lists ones that did
    r.env["MOCK_REQUIRED"] = required.as_posix()
    try:
        f, _, out = attempt(r, "forge-wins-refuses", project=CI)
        expect("MERGE_HUMAN" in out.stdout and "deploy" in out.stdout and not merged(r, f), "the forge's list replaces PROJECT.md's: " + out.stdout + out.stderr)
        required.write_text("build (linux)\nlint\n", encoding="utf-8")
        f, _, out = attempt(r, "forge-wins-lands", project="Merge-Engine: ci\nMerge-Engine-Checks: deploy\n")
        expect("INTEGRATED" in out.stdout and merged(r, f), "the forge's list lands what PROJECT.md's would refuse: " + out.stdout + out.stderr)
        expect(re.search(r"^Merge-Checks: 2: build \(linux\); lint$", f.show("tasks/HACK-001.md"), re.M), "the record names exactly the required runs counted")
    finally:
        del r.env["MOCK_REQUIRED"]
    return "forge list first; PROJECT.md's only when the forge gives none"


def no_required_list_goes_to_the_human(r):
    checks(r, GREEN)
    f, _, out = attempt(r, "nolist", project="Merge-Engine: ci\n")
    expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout and "Merge-Engine-Checks" in out.stdout and "required status checks" in out.stdout and not merged(r, f),
           out.stdout + out.stderr)
    return "no list: the human, with the way to configure it"


TESTS = [human_is_the_default, ci_merges_when_every_check_is_green, a_running_check_waits, a_red_check_refuses,
         lock_files_still_need_a_human, record_names_the_policy, a_task_cannot_turn_the_policy_on,
         gh_unavailable_is_not_green, doctor_fails_without_required_checks, marathon_needs_human_independence,
         metrics_counts_ci_merges_apart, status_and_lone_checks_prove_nothing, shards_match_by_prefix,
         a_missing_required_check_waits_then_refuses, workflow_or_smoke_goes_to_the_human, forge_required_checks_win,
         no_required_list_goes_to_the_human, the_gate_itself_and_github_stay_human]


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
