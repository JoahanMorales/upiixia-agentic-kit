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
from test_gate_scope import HARNESS  # noqa: E402  (rm_gate_scope on a candidate repository, no merge)

PR = "https://github.com/org/repo/pull/1"
GH_URL = "https://github.com/org/repo.git"
ENGINE_FILE = ".uak/bin/lib/metrics.py"  # a .py of lib/ that nothing the gate loads names: the one kind of file `ci` releases
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


def fixture(r, name, path, project="", content="ready-HACK-001\n", mode="sprint", seed_edit=None):
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
    if seed_edit:
        seed_edit(f.seed)
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
        if f.content.startswith("SYMLINK:"):  # the path is a symlink to a sibling
            if target.exists() or target.is_symlink():
                target.unlink()
            os.symlink(f.content[8:], str(target))
        elif target.exists() and each.startswith(".uak/bin/"):  # a real engine file: append a comment, never overwrite the engine in use
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


def attempt(r, name, path=ENGINE_FILE, project="", content="ready-HACK-001\n", mode="sprint", seed_edit=None):
    forge(r, name)
    f = fixture(r, name, path, project, content, mode, seed_edit)
    tip = ship(f, r)
    out = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    return f, tip, out


BASE_LIB = {".uak/bin/uak": "x\n", ".uak/bin/uak-coordination": "x\n", ".uak/bin/guard": "x\n", ".uak/bin/smoke": "x\n",
            ".uak/bin/lib/hints.sh": "x\n", ".uak/bin/lib/tests.sh": "x\n", ".uak/bin/lib/github.sh": "x\n",
            ".uak/bin/lib/commands.tsv": "x\n", ".uak/bin/lib/review-merge.sh": "x\n", ".uak/bin/lib/status.sh": "x\n",
            ".uak/bin/lib/metrics.py": "x\n", ".uak/bin/lib/gallery_pick.py": "x\n", ".uak/bin/lib/dash.py": "x\n",
            "README.md": "x\n"}


def scope_verdict(r, name, changes, links=None, base_extra=None, project="Merge-Engine: ci\n"):
    """rm_gate_scope's verdict for a candidate whose base has Merge-Engine: ci and the engine's file names (the same
    function `uak merge` runs, without the merge: a refusal there is decided before any smoke or check). `changes`
    are files written and staged, `links` symlinks (mode 120000) staged. The task's Paths name every one of them."""
    d = r.scratch / ("scope-" + name)
    repo, tx, tmp = d / "repo", d / "tx", d / "tmp"
    for q in (repo, tx / "tasks", tmp):
        q.mkdir(parents=True)
    paths = list(changes) + list(links or {})
    (tx / "tasks/HACK-001.md").write_text("ID: HACK-001\nState: REVIEW\nPaths: %s\n" % ", ".join(paths), encoding="utf-8")
    (d / "TASKS.md").write_text("# Tasks\n\n## HACK-001 · The task\n- **Paths:** %s\n" % ", ".join(paths), encoding="utf-8")
    r.g(repo, "init", "-q")
    base_files = dict(BASE_LIB)
    base_files[".uak/PROJECT.md"] = "Mode: sprint\n" + project
    base_files.update(base_extra or {})
    for rel, text in base_files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    r.g(repo, "add", "-A")
    r.g(repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.test", "commit", "-q", "-m", "base")
    base = r.g(repo, "rev-parse", "HEAD").stdout.strip()
    for rel, text in changes.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(old + text, encoding="utf-8", newline="\n")
    r.g(repo, "add", "-A")
    for i, (rel, to) in enumerate((links or {}).items()):
        blob = d / ("blob-%d" % i)
        blob.write_text(to, encoding="utf-8", newline="\n")
        sha = r.g(repo, "hash-object", "-w", blob.as_posix()).stdout.strip()
        r.g(repo, "update-index", "--add", "--cacheinfo", "120000,%s,%s" % (sha, rel))
    script = r.scratch / "policy-scope-harness.sh"
    if not script.exists():
        script.write_text(HARNESS, encoding="utf-8", newline="\n")
    bindir = r.package / ".uak" / "bin"
    out = r.run([r.bash, script.as_posix(), bindir.as_posix(), repo.as_posix(), base, tx.as_posix(), (d / "TASKS.md").as_posix(), tmp.as_posix()],
                cwd=d, allowed=None)
    text = out.stdout.strip()
    expect(out.returncode == 0 and text.startswith("SCOPE "), "the harness ran rm_gate_scope: " + (out.stdout + out.stderr)[-600:])
    return text


def expect_human(r, name, changes, **kw):
    text = scope_verdict(r, name, changes, **kw)
    # Without letter case: a case-insensitive checkout stores .GitHub/Actions/y as the case that directory already has.
    expect(text.lower().startswith("scope refused: shared resource/ci needs a human"),
           "%s: expected a human, got: %s" % (list(changes) + list(kw.get("links") or {}), text))
    return text


def human_is_the_default(r):
    for label, project in (("absent", ""), ("a typo is human", "Merge-Engine: yes\n")):
        checks(r, GREEN)
        f, _, out = attempt(r, "human-" + label.split()[0], project=project)
        expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout, "%s: %s" % (label, out.stdout + out.stderr))
        expect("Shared resource/CI needs a human: %s" % ENGINE_FILE in out.stdout, "%s: reason: %s" % (label, out.stdout))
        expect(not merged(r, f), "%s: base must not move" % label)
        expect("Merge-Policy" not in f.show("queue/HACK-001.md") + f.show("tasks/HACK-001.md"), "no policy recorded")
    return "engine file goes to a human with the policy absent or misspelled"


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
    for label, text in (("one running", GREEN + "e2e|in_progress|\n"), ("none found yet", "")):
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
                                ("a commit status failed", GREEN, "failure|1\n")):
        checks(r, text, status)
        f, _, out = attempt(r, "red-" + re.sub(r"\W+", "", label), project=CI)
        expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout, "%s: %s" % (label, out.stdout + out.stderr))
        expect(not merged(r, f), "%s: base must not move" % label)
        if label == "a later run red":
            expect("e2e" in out.stdout, "the red check is named: " + out.stdout)
    return "a red run, a red shard and a failed status refuse"


def lock_files_still_need_a_human(r):
    for name, path in (("lock", "package-lock.json"), ("migration", "db/migration/V9__x.sql"),
                       ("both", ".uak/bin/lib/migrations/x.txt"), ("project", ".uak/PROJECT.md"),
                       ("provenance", ".uak/bin/.smoke-project.provenance")):
        expect_human(r, "lock-" + name, {path: "ready-HACK-001\n"})
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


def doctor_explains_the_approvals_key(r):
    """doctor explains Merge-Engine-Approvals: 2 (the libs it adds, the limit of two identities), warns when fewer than two
    registered reviewers exist, when the value is not 2, and when it is set without `Merge-Engine: ci`."""
    checks(r, GREEN)
    forge(r, "doctor2")
    f = fixture(r, "doctor2", ENGINE_FILE, TWO_KEY)
    clone = f.clones[0]
    r.g(clone, "pull", "-q", "origin", "main")
    project = clone / ".uak/PROJECT.md"
    base = project.read_text(encoding="utf-8")

    def doctor(text):
        project.write_text(text, encoding="utf-8")
        out = r.run([r.bash, ".uak/bin/doctor"], cwd=clone, env={"UAK_AGENT": "agent-1"}, allowed=None)
        return out.stdout + out.stderr
    r.env.pop("MOCK_REQUIRED", None)
    text = doctor(base)
    expect(re.search(r"OK .*Merge-Engine-Approvals: 2 also releases these loaded libs.*status\.sh.*cannot be told apart", text), "explained: " + text[-1800:])
    expect(re.search(r"WARN .*Merge-Engine-Approvals: 2 needs two registered reviewers", text), "no reviewers: a warning: " + text[-1800:])
    text = doctor(base.replace("Merge-Engine-Approvals: 2", "Merge-Engine-Approvals: 3"))
    expect(re.search(r"WARN .*Merge-Engine-Approvals: 3 is ignored", text), "3 is ignored: " + text[-1800:])
    text = doctor(base.replace("Merge-Engine: ci\n", "Merge-Engine: human\n"))
    expect(re.search(r"WARN .*Merge-Engine-Approvals: 2 does nothing without Merge-Engine: ci", text), "without ci: " + text[-1800:])
    return "explained; warns without reviewers, with a value other than 2, and without ci"


def status_and_lone_checks_prove_nothing(r):
    for label, text, status, want in (
            ("a bare success status", "", "success|1\n", "MERGE_WAIT"),
            ("a lone x check", "x|completed|success\n", STATUS_NONE, "MERGE_HUMAN"),
            ("unnamed plus whitespace", " |completed|success\nx|completed|success\n", STATUS_NONE, "MERGE_HUMAN")):
        checks(r, text, status)
        f, _, out = attempt(r, "weak-" + re.sub(r"\W+", "", label), project=CI)
        expect(want in out.stdout and not merged(r, f), "%s: expected %s, never green: %s" % (label, want, out.stdout + out.stderr))
    return "none of them is green"


def shards_match_by_prefix(r):
    """The green run's list is `build (*, lint`: both build shards are counted by the prefix (no fixture of its own)."""
    f, _, out = green_run(r)
    record = f.show("tasks/HACK-001.md")
    expect("INTEGRATED" in out.stdout and "build (linux)" in record and "build (macos)" in record and "lint" in record,
           "both build shards and lint counted: " + record)
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
    for name, path in (("workflow", ".github/workflows/ci.yml"), ("smoke", ".uak/bin/smoke"), ("smokeproject", ".uak/bin/smoke-project"),
                       ("secretscan", ".uak/bin/secret-scan"), ("githook", ".githooks/pre-commit"), ("guard", ".uak/bin/guard"),
                       ("hookfixture", ".githooks/fixtures/x.txt"), ("libfixture", ".uak/bin/lib/fixtures/x.txt")):
        expect_human(r, "judge-" + name, {path: "ready-HACK-001\n"})
    return "the things that judge or guard a merge are never released; lib/fixtures is not exempt"


def the_gate_itself_and_github_stay_human(r):
    """Under ci only a file the gate does not load is released. bin/uak sources its libs into one process and the last
    definition wins, so each loaded file (hints.sh, tests.sh, github.sh, commands.tsv, bin/uak, uak-coordination, the
    gate's own files), all of .github/ (any letter case), and a new lib/x.sh go to a human, alone or mixed with a
    released file; a .py the gate names is loaded too; a symlink is never released. A released .py alone is not
    refused as a shared resource, and lands end to end with the required checks green."""
    for name, path in (("action", ".github/actions/x/action.yml"), ("codeowners", ".github/CODEOWNERS"),
                       ("casefold", ".GitHub/Actions/y/action.yml"), ("hints", ".uak/bin/lib/hints.sh"),
                       ("tests", ".uak/bin/lib/tests.sh"), ("github", ".uak/bin/lib/github.sh"),
                       ("tsv", ".uak/bin/lib/commands.tsv"), ("uak", ".uak/bin/uak"), ("coord", ".uak/bin/uak-coordination"),
                       ("reviewmerge", ".uak/bin/lib/review-merge.sh"), ("status", ".uak/bin/lib/status.sh"),
                       ("newsh", ".uak/bin/lib/x.sh"), ("newpy", ".uak/bin/lib/new_helper.py"), ("sub", ".uak/bin/lib/sub/metrics.py")):
        expect_human(r, "gate-" + name, {path: "# ready-HACK-001\n"})
    text = scope_verdict(r, "gate-mixed", {".uak/bin/lib/metrics.py": "# ready-HACK-001\n", ".uak/bin/lib/hints.sh": "# ready-HACK-001\n"})
    expect(text.lower().startswith("scope refused: shared resource/ci needs a human: .uak/bin/lib/hints.sh"), "a released file mixed with a loaded one: " + text)
    text = scope_verdict(r, "gate-free", {".uak/bin/lib/metrics.py": "# ready-HACK-001\n"})
    expect("Shared resource" not in text, "a released .py is not a shared resource (it goes on to the approval and the checks): " + text)
    # the base's hints.sh names gallery_pick.py: a helper the gate may call, so it is loaded
    expect_human(r, "gate-pycalled", {".uak/bin/lib/gallery_pick.py": "# ready-HACK-001\n"},
                 base_extra={".uak/bin/lib/hints.sh": 'x\n# python3 "$UAK_BIN/lib/gallery_pick.py"\n'})
    # a symlink under lib/ (a released name linked to a loaded file) is the human's: the mode 120000
    expect_human(r, "gate-symlink", {}, links={".uak/bin/lib/metrics.py": "review-merge.sh"})
    # an unnamed .py lands end to end with the required checks green
    checks(r, GREEN)
    f, _, out = attempt(r, "gate-pyfree", path=".uak/bin/lib/gallery_pick.py", project=CI)
    expect("INTEGRATED" in out.stdout and merged(r, f), "an unnamed .py lands with the checks green: " + out.stdout + out.stderr)
    return "loaded files, .github/, a new lib/x.sh, a named .py and a symlink are a human's; an unnamed .py lands"


def released_set_matches_the_source_chain(r):
    """The computed set (rm_released_lib, on a git ref) holds no .sh/.awk/.tsv, nothing bin/uak's real source chain loads,
    and no .py or .html that a loaded file names; and it is exactly the .py and .html nobody names. A lib sourced
    tomorrow is seen: every .sh counts as loaded whether or not a chain of `. lib/X` lines is understood."""
    repo = Path(__file__).resolve().parents[2].parent
    kit = Path(__file__).resolve().parents[2]
    ref = "HEAD"
    out = r.run([r.bash, "-c", '. "%s/.uak/bin/lib/review-merge.sh"; rm_released_lib "%s" HEAD' % (kit.as_posix(), repo.as_posix())], allowed=None)
    got = sorted(x for x in out.stdout.split() if x)
    expect(out.returncode == 0 and got, "the computed set is empty or failed: " + out.stdout + out.stderr)
    lib = kit / ".uak/bin/lib"
    loaded_text = "".join(f.read_text(encoding="utf-8", errors="replace") for f in [kit / ".uak/bin/uak", kit / ".uak/bin/uak-coordination"]
                          + sorted(lib.glob("*.sh")) + sorted(lib.glob("*.awk")) + sorted(lib.glob("*.tsv")))
    # bin/uak's real source chain: `. "$UAK_BIN/lib/X"` lines and the `for uak_lib in ...; do` list, followed through the libs
    def sourced(text):
        found = re.findall(r'(?:^|[\s;&])(?:\.|source) "\$UAK_BIN/([A-Za-z0-9_./-]+)"', text)
        loop = re.search(r"for uak_lib in(.*?); do", text, re.S)
        if loop:
            found += loop.group(1).replace("\\\n", " ").split()
        return found
    chain, todo = set(), ["uak", "uak-coordination"]
    while todo:
        cur = todo.pop()
        text = (kit / ".uak/bin" / cur).read_text(encoding="utf-8")
        for m in sourced(text):
            if m not in chain and (kit / ".uak/bin" / m).is_file():
                chain.add(m)
                todo.append(m)
    expect(len(chain) >= 15, "the source chain was not read: %s" % sorted(chain))
    names = {Path(m).name.lower() for m in chain}
    expect(not names & set(got), "a file bin/uak sources is in the released set: %s" % sorted(names & set(got)))
    expect(all(x.endswith((".py", ".html")) for x in got), "only .py and .html can be released: %s" % got)
    want = sorted(f.name.lower() for f in list(lib.glob("*.py")) + list(lib.glob("*.html")) if f.name not in loaded_text)
    expect(got == want, "released %s, expected the .py/.html nobody names: %s" % (got, want))
    for must_be_human in ("dash.py", "ledger_py.py"):  # named by status.sh and ledger.sh
        expect(must_be_human not in got, "%s is named by a loaded file" % must_be_human)
    return "released: " + ", ".join(got)


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


# UAK-149: Merge-Engine-Approvals: 2. The gate's scope pass and the approval count, without the merge (rm_ci_checks stubbed
# green: the end-to-end cases below use the real checks), then two real `uak merge` runs.
TWO_KEY = CI + "Merge-Engine-Approvals: 2\n"
TIP = "a" * 40
HARNESS_TWO = r"""# $1 the engine's .uak/bin, $2 the candidate (changes staged over $3), $3 the base SHA, $4 the claims tree, $5 TASKS.md,
# $6 the merge temp dir, $7 the tip. The claims tree holds the task, its review, the second approvals and the registered reviewers.
UAK_BIN=$1
for l in lib/core.sh uak-coordination lib/config.sh lib/backlog.sh lib/review-merge.sh; do . "$UAK_BIN/$l" || exit 9; done
RM_BUILD=$2 RM_BASE_TIP=$3 TX=$4 BACKLOG=$5 TXROOT=$6 ID=HACK-001 BASE=main RECORD=$4/tasks/HACK-001.md
RM_REVIEW_MODE=claims RM_REVIEWED_TIP=$7 APPROVED_BY=$(field "$TX/reviews/HACK-001.md" Reviewer)
rm_ci_checks() { return 0; }
if rm_gate_scope; then printf 'SCOPE OK\n'; else printf 'SCOPE REFUSED: %s\n' "$RM_REASON"; fi
"""
LIB = Path(__file__).resolve().parents[1] / "bin" / "lib"


def lib_files():
    return sorted(f.name for f in LIB.iterdir() if f.is_file() and f.suffix in (".sh", ".awk", ".tsv"))


def lib_lists(r):
    """RM_LIB_HUMAN and RM_LIB_TWO as the engine defines them (one place)."""
    out = r.run([r.bash, "-c", '. "%s/review-merge.sh"; printf "%%s\\n" "$RM_LIB_HUMAN"; printf "%%s\\n" "$RM_LIB_TWO"' % LIB.as_posix()], allowed=None)
    human, two = (x.split() for x in out.stdout.strip().splitlines())
    return human, two


def two_verdict(r, name, changes, project=TWO_KEY, first="judge", extra=(), registered=("judge", "judge-2"), reviewed_sha=TIP,
                links=None, base_extra=None, first_sha=TIP, owner="agent-1", index=None):
    """rm_gate_scope's verdict (and the approval count) for a candidate. `first` approved reviews/HACK-001.md at first_sha,
    `extra` are the lines of reviews/HACK-001.approvals as (sha, who), `registered` the identities with a role."""
    d = r.scratch / ("two-" + name)
    tx = d / "tx"
    for q in ("tasks", "reviews", "roles/reviewers", "meta/agents"):
        (tx / q).mkdir(parents=True)
    (tx / "tasks/HACK-001.md").write_text("ID: HACK-001\nState: REVIEW\nOwner: %s\nPaths: .\n" % owner, encoding="utf-8")
    (tx / "reviews/HACK-001.md").write_text(
        "ID: HACK-001\nSHA: %s\nReviewer: %s\nOwner: %s\nVerdict: approve\nReviewed: 1\nEligible-Via: role:%s\nCommand: uak review\n"
        % (first_sha, first, owner, first), encoding="utf-8")
    if extra:
        (tx / "reviews/HACK-001.approvals").write_text("".join("%s|%s|2|role:%s\n" % (sha, who, who) for sha, who in extra), encoding="utf-8")
    for who in set(registered) | {first, owner} | {w for _, w in extra}:
        (tx / "meta/agents" / (who + ".md")).write_text("Agent: %s\n" % who, encoding="utf-8")
    for who in registered:
        (tx / "roles/reviewers" / (who + ".md")).write_text("Reviewer: %s\nState: REGISTERED\nRegistered-By: human\nRegistered: 1\n" % who, encoding="utf-8")
    # scope_verdict builds the repository and runs HARNESS; reuse its repository builder with this harness and tx
    script = r.scratch / "policy-two-harness.sh"
    if not script.exists():
        script.write_text(HARNESS_TWO, encoding="utf-8", newline="\n")
    return scope_with(r, "two-" + name, changes, links, dict(dict.fromkeys(lib_files(), "x\n"), **(base_extra or {})), project, script, tx, reviewed_sha, index)


def scope_with(r, name, changes, links, base_extra, project, script, tx, tip, index=None):
    d = r.scratch / ("scopetwo-" + name)
    repo, tmp = d / "repo", d / "tmp"
    for q in (repo, tmp):
        q.mkdir(parents=True)
    (d / "TASKS.md").write_text("# Tasks\n\n## HACK-001 · The task\n- **Paths:** .\n", encoding="utf-8")
    r.g(repo, "init", "-q")
    files = dict(BASE_LIB)
    files.update({".uak/bin/lib/" + k: v for k, v in (base_extra or {}).items() if "/" not in k})
    files.update({k: v for k, v in (base_extra or {}).items() if "/" in k})
    files[".uak/PROJECT.md"] = "Mode: sprint\n" + project
    for rel, text in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    r.g(repo, "add", "-A")
    r.g(repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.test", "commit", "-q", "-m", "base")
    base = r.g(repo, "rev-parse", "HEAD").stdout.strip()
    for rel, text in changes.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(old + text, encoding="utf-8", newline="\n")
    r.g(repo, "add", "-A")
    for i, (rel, to) in enumerate((links or {}).items()):
        blob = d / ("blob-%d" % i)
        blob.write_text(to, encoding="utf-8", newline="\n")
        sha = r.g(repo, "hash-object", "-w", blob.as_posix()).stdout.strip()
        r.g(repo, "update-index", "--add", "--cacheinfo", "120000,%s,%s" % (sha, rel))
    for i, (rel, text) in enumerate((index or {}).items()):  # staged without the working tree: a case-insensitive disk would merge the names
        blob = d / ("iblob-%d" % i)
        blob.write_text(text, encoding="utf-8", newline="\n")
        sha = r.g(repo, "hash-object", "-w", blob.as_posix()).stdout.strip()
        r.g(repo, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (sha, rel))
    bindir = r.package / ".uak" / "bin"
    out = r.run([r.bash, script.as_posix(), bindir.as_posix(), repo.as_posix(), base, tx.as_posix(), (d / "TASKS.md").as_posix(), tmp.as_posix(), tip],
                cwd=d, allowed=None)
    text = out.stdout.strip()
    expect(out.returncode == 0 and text.startswith("SCOPE "), "the harness ran: " + (out.stdout + out.stderr)[-600:])
    return text


LIBPATH = ".uak/bin/lib/"
HUMAN_REASON = "SCOPE REFUSED: Shared resource/CI needs a human: "


def one_approval_releases_only_todays_set(r):
    """One approval, or the key absent, 1, 3, two, 02 or without `ci`: the verdicts of a loaded lib and of an unnamed .py are
    exactly today's (the same fixture is run with each key); with 2 and a single approval the lib is refused by the count."""
    change = {LIBPATH + "status.sh": "# ready-HACK-001\n"}
    want = HUMAN_REASON + LIBPATH + "status.sh"
    for label, project in (("absent", "Merge-Engine: ci\n"), ("one", CI + "Merge-Engine-Approvals: 1\n"), ("three", CI + "Merge-Engine-Approvals: 3\n"),
                           ("word", CI + "Merge-Engine-Approvals: two\n"), ("zero2", CI + "Merge-Engine-Approvals: 02\n"),
                           ("noci", "Merge-Engine-Approvals: 2\n"), ("human", "Merge-Engine: human\nMerge-Engine-Approvals: 2\n")):
        got = two_verdict(r, "one-" + label, change, project=project, extra=[(TIP, "judge-2")])
        expect(got == want, "%s: expected today's verdict %r, got %r" % (label, want, got))
        py = two_verdict(r, "onepy-" + label, {LIBPATH + "metrics.py": "# ready-HACK-001\n"}, project=project, extra=[(TIP, "judge-2")])
        expect(py == ("SCOPE OK" if label not in ("noci", "human") else HUMAN_REASON + LIBPATH + "metrics.py"), "%s: an unnamed .py: %r" % (label, py))
    got = two_verdict(r, "one-count", change, extra=())
    expect(got.startswith("SCOPE REFUSED: Merge-Engine-Approvals: 2: a change to a loaded lib needs 2 approvals of the exact tip") and "has 1 (judge)" in got,
           "key 2 and one approval: " + got)
    got = two_verdict(r, "one-py", {LIBPATH + "metrics.py": "# ready-HACK-001\n"}, extra=())
    expect(got == "SCOPE OK", "an unnamed .py still lands with one approval under key 2: " + got)
    return "absent/1/3/two/02/no ci/human: today's verdicts; key 2 with one approval: refused by the count"


def two_approvals_release_a_loaded_lib(r):
    """Key 2 and two registered reviewers on the exact tip: every lib of RM_LIB_TWO is released (scope pass), and one real
    `uak merge` lands through the gate with the second approval recorded by a second `uak review`."""
    human, two = lib_lists(r)
    for name in two:
        got = two_verdict(r, "rel-" + name, {LIBPATH + name: "# ready-HACK-001\n"}, extra=[(TIP, "judge-2")])
        expect(got == "SCOPE OK", "%s with two approvals: %s" % (name, got))
    # end to end: a second `uak review` of the same SHA by another registered reviewer is recorded, not skipped
    forge(r, "two-lands")
    f = fixture(r, "two-lands", LIBPATH + "hints.sh", TWO_KEY)
    tip = ship(f, r)
    actor(f, "human-registrar", "register-reviewer", "judge-2", human=True)
    expect("SKIP" not in actor(f, "judge-2", "review", "HACK-001", "--start").stdout, "the second reviewer is not told to skip")
    second = approve(f, "HACK-001", tip, name="judge-2")
    expect("second approval recorded" in second.stdout, "second review: " + second.stdout)
    expect("%s|judge-2|" % tip in f.show("reviews/HACK-001.approvals") and "Reviewer: judge\n" in f.show("reviews/HACK-001.md"), "both approvals kept")
    out = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout and merged(r, f), "two approvals land a loaded lib: " + out.stdout + out.stderr)
    expect("Merge-Policy: ci" in f.show("tasks/HACK-001.md"), "policy recorded")
    return "%d libs released in the scope pass; hints.sh landed end to end with two approvals" % len(two)


def gate_files_are_never_released(r):
    """With key 2 and two approvals: each lib of RM_LIB_HUMAN, bin/uak, uak-coordination, .github/, the hooks, guard, smoke,
    smoke-project, secret-scan, lock files, migrations, PROJECT.md and a symlink stay the human's, alone or mixed with a
    released lib; a lib in neither list, a new lib, a letter-case variant, a deleted one and one that redefines a function
    of the gate or adds eval / unset -f / alias / source go to the human; every real lib file is in exactly one list."""
    human, two = lib_lists(r)
    names = lib_files()
    expect(not set(human) & set(two), "a lib is in both lists: %s" % sorted(set(human) & set(two)))
    expect(sorted(set(human) | set(two)) == names, "every .sh/.awk/.tsv of lib/ is classified: unclassified %s, unknown %s" %
           (sorted(set(names) - set(human) - set(two)), sorted((set(human) | set(two)) - set(names))))
    for must in ("review-merge.sh", "tx.sh", "security.sh", "config.sh"):  # the four UAK-131 kept
        expect(must in human, must + " is one of the four the human kept")
    def refused(label, got, path):
        expect(got.lower() == (HUMAN_REASON + path).lower(), "%s: expected the human for %s, got %s" % (label, path, got))
    for name in human:
        refused(name, two_verdict(r, "never-" + name, {LIBPATH + name: "# ready-HACK-001\n"}, extra=[(TIP, "judge-2")]), LIBPATH + name)
    for path in (".uak/bin/uak", ".uak/bin/uak-coordination", ".github/workflows/ci.yml", ".github/actions/x/action.yml", ".githooks/pre-commit",
                 ".uak/bin/guard", ".uak/bin/smoke", ".uak/bin/smoke-project", ".uak/bin/secret-scan", "package-lock.json",
                 "db/migrations/001.sql", ".uak/PROJECT.md", ".uak/bin/lib/fixtures/x.txt", ".uak/bin/lib/sub/status.sh"):
        refused(path, two_verdict(r, "never-" + path.replace("/", "-"), {path: "# ready-HACK-001\n"}, extra=[(TIP, "judge-2")]), path)
    refused("symlink", two_verdict(r, "never-link", {}, links={LIBPATH + "status.sh": "review-merge.sh"}, extra=[(TIP, "judge-2")]), LIBPATH + "status.sh")
    refused("mixed", two_verdict(r, "never-mixed", {LIBPATH + "status.sh": "# a\n", LIBPATH + "review-merge.sh": "# b\n"}, extra=[(TIP, "judge-2")]), LIBPATH + "review-merge.sh")
    refused("new lib", two_verdict(r, "never-new", {LIBPATH + "newlib.sh": "# a\n"}, extra=[(TIP, "judge-2")]), LIBPATH + "newlib.sh")
    # not a plain edit of a base file: case variant, deleted
    got = two_verdict(r, "never-case", {}, index={LIBPATH + "Status.SH": "# a\n"}, extra=[(TIP, "judge-2")])
    expect(got.startswith("SCOPE REFUSED: Merge-Engine-Approvals: 2 releases an edit of an existing regular lib file only") or got.lower() == (HUMAN_REASON + LIBPATH + "Status.SH").lower(),
           "case variant: " + got)
    shape = {"redefines": "approval_check() { return 0; }\n", "defines git": "git() { :; }\n", "eval": "eval \"$x\"\n", "unset": "unset -f field\n",
             "alias": "alias git=true\n", "source": ". ./evil.sh\n", "source2": "source ./evil.sh\n"}
    for label, text in shape.items():
        got = two_verdict(r, "never-shape-" + label.replace(" ", ""), {LIBPATH + "status.sh": text}, extra=[(TIP, "judge-2")],
                          base_extra={"review-merge.sh": "approval_check() { :; }\n"})
        expect(got.startswith("SCOPE REFUSED: Merge-Engine-Approvals: 2:") and "a human lands that" in got, "%s: %s" % (label, got))
    ok = two_verdict(r, "never-shape-ok", {LIBPATH + "status.sh": "status_extra() { printf 'x\\n'; }\n# eval is only a word here\n"}, extra=[(TIP, "judge-2")])
    expect(ok == "SCOPE OK", "a new helper function and a comment are fine: " + ok)
    return "%d human libs, %d two-approval libs; gate files, workflows, hooks, symlinks, new, case variants and redefinitions stay with the human" % (len(human), len(two))


def same_identity_twice_counts_once(r):
    """The same identity listed twice, the author, an unregistered name, a retired one, and the first approver again count
    for nothing: the count stays at one and the gate refuses with it."""
    change = {LIBPATH + "status.sh": "# ready-HACK-001\n"}
    for label, kw in (("twice", dict(extra=[(TIP, "judge"), (TIP, "judge"), (TIP, "judge-2"), (TIP, "judge-2")], registered=("judge",))),
                      ("author", dict(extra=[(TIP, "agent-1")], registered=("judge", "agent-1"))),
                      ("unregistered", dict(extra=[(TIP, "ghost")], registered=("judge",))),
                      ("badname", dict(extra=[(TIP, "bad name")], registered=("judge",)))):
        got = two_verdict(r, "same-" + label, change, **kw)
        expect(got.startswith("SCOPE REFUSED: Merge-Engine-Approvals: 2: ") and "has 1 (judge)" in got, "%s: %s" % (label, got))
    # an unregistered FIRST approver (eligible through a claim) does not count either
    got = two_verdict(r, "same-first-unregistered", change, first="claimer", extra=[(TIP, "judge-2")], registered=("judge-2",))
    expect("has 1 (judge-2)" in got, "an unregistered first approver: " + got)
    ok = two_verdict(r, "same-two", change, extra=[(TIP, "judge"), (TIP, "judge-2")])
    expect(ok == "SCOPE OK", "two distinct registered reviewers, one listed twice: " + ok)
    return "twice, the author, an unregistered name and the first approver again: one approval"


def approval_of_an_older_sha_does_not_count(r):
    """A second approval, or the first, on another SHA than the exact tip does not count (an approval followed by a new tip)."""
    change = {LIBPATH + "status.sh": "# ready-HACK-001\n"}
    old = "b" * 40
    got = two_verdict(r, "old-second", change, extra=[(old, "judge-2")])
    expect(got.startswith("SCOPE REFUSED: Merge-Engine-Approvals: 2: ") and "has 1 (judge)" in got, "second on an older SHA: " + got)
    got = two_verdict(r, "old-first", change, extra=[(TIP, "judge-2")], first_sha=old)
    expect("has 1 (judge-2)" in got, "first on an older SHA: " + got)
    got = two_verdict(r, "old-tip", change, extra=[(TIP, "judge-2")], reviewed_sha="c" * 40)
    expect("has 0 (none)" in got, "both approvals then a new tip: " + got)
    return "second, first and both approvals of another SHA count for nothing"


def status_says_how_many_approvals(r):
    """The gate's refusal says how many approvals of the tip exist, who, and how many the policy needs, and a real `uak merge`
    with one approval under key 2 goes to the human with that reason and lands nothing; a reject voids the second approval.
    (`uak status --task` reads lib/status.sh, outside this task's Paths: its approvals line is a follow-up.)"""
    forge(r, "two-one")
    f = fixture(r, "two-one", LIBPATH + "hints.sh", TWO_KEY)
    tip = ship(f, r)
    out = f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    expect(out.returncode == 3 and "MERGE_HUMAN" in out.stdout and "needs 2 approvals" in out.stdout and "has 1 (judge)" in out.stdout and not merged(r, f),
           "one approval under key 2: " + out.stdout + out.stderr)
    actor(f, "human-registrar", "register-reviewer", "judge-2", human=True)
    approve(f, "HACK-001", tip, name="judge-2")
    expect("judge-2" in f.show("reviews/HACK-001.approvals"), "second approval stored")
    actor(f, "human-registrar", "register-reviewer", "judge-3", human=True)
    rejected = approve(f, "HACK-001", tip, name="judge-3", verdict="reject", allowed=None)
    expect("reviews/HACK-001.approvals" not in f.files("reviews") and "Verdict: reject" in f.show("reviews/HACK-001.md"),
           "a reject voids the second approvals: " + rejected.stdout + rejected.stderr)
    return "refusal names the count (1 of 2) and the approver; a reject deletes the second approvals"


TESTS = [human_is_the_default, ci_merges_when_every_check_is_green, a_running_check_waits, a_red_check_refuses,
         lock_files_still_need_a_human, record_names_the_policy, a_task_cannot_turn_the_policy_on,
         gh_unavailable_is_not_green, doctor_fails_without_required_checks, marathon_needs_human_independence,
         metrics_counts_ci_merges_apart, status_and_lone_checks_prove_nothing, shards_match_by_prefix,
         a_missing_required_check_waits_then_refuses, workflow_or_smoke_goes_to_the_human, forge_required_checks_win,
         no_required_list_goes_to_the_human, the_gate_itself_and_github_stay_human, released_set_matches_the_source_chain,
         two_approvals_release_a_loaded_lib, one_approval_releases_only_todays_set, gate_files_are_never_released,
         same_identity_twice_counts_once, approval_of_an_older_sha_does_not_count, status_says_how_many_approvals,
         doctor_explains_the_approvals_key]


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
