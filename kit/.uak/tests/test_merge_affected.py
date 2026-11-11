#!/usr/bin/env python3
"""UAK-052: `Merge-Smoke: affected` in PROJECT.md. `uak merge` then runs the project's smoke with only the test files that
name a changed file or were changed themselves (UAK_SMOKE_TESTS, which the kit's smoke already honours), instead of the whole
suite; a change to the engine's shared files (lib/core.sh, lib/tx.sh, uak-coordination) still runs everything; the default is
`full`; the task record says which (`Smoke: affected 1 of 52 test files`). Why (v6.1.0 session): each `uak merge` ran the whole
suite on the maintainer's machine, over 10 minutes per task, and CI runs every test on every push anyway.
Real Git, a local bare remote; the fixture's project smoke writes what the gate handed it."""
import argparse
import re
import tempfile
import time
from pathlib import Path

import test_review_merge as rm
from test_hack import Runner, expect, resolve_binary


def affected_fixture(r, name, mode=None, core=False):
    f = rm.fixture(r, "ma-" + name, count=1)
    log = f.base / "gate-env.log"
    seed = f.seed
    if mode:
        p = seed / ".uak/PROJECT.md"
        p.write_text(p.read_text(encoding="utf-8") + "Merge-Smoke: %s\n" % mode, encoding="utf-8")
    (seed / ".uak/bin/smoke-project").write_text(
        "#!/usr/bin/env bash\nset -eu\nprintf 'SET=%%s\\n' \"${UAK_SMOKE_TESTS-UNSET}\" >> '%s'\n" % log.as_posix(), encoding="utf-8")
    (seed / ".uak/tests/test_names_it.py").write_text("# exercises src/value-1.txt\n", encoding="utf-8")
    (seed / ".uak/tests/test_unrelated.py").write_text("# exercises nothing that changes\n", encoding="utf-8")
    if core:
        tasks = (seed / ".uak/TASKS.md").read_text(encoding="utf-8")
        tasks = tasks.replace("- **Paths:** src/value-1.txt", "- **Paths:** src/value-1.txt, .uak/bin/lib/core.sh", 1)
        (seed / ".uak/TASKS.md").write_text(tasks, encoding="utf-8")
    r.g(seed, "add", "-A")
    r.g(seed, "commit", "-q", "-m", "fixture: affected-mode project")
    r.g(seed, "push", "-q", "origin", "main")
    f.main_head = r.g(f.remote, "rev-parse", "main").stdout.strip()
    for clone, worktree in zip(f.clones, f.worktrees):
        r.g(clone, "fetch", "-q", "origin", "main")
        r.g(worktree, "reset", "-q", "--hard", "origin/main")
    return f, log


def merge_task(r, f, extra=None, human=False):
    f.claim(0, "HACK-001")
    tip = rm.publish(f, 0, "HACK-001")
    if extra:
        path = f.worktrees[0] / extra
        path.write_text(path.read_text(encoding="utf-8") + "# touched by the task\n", encoding="utf-8")
        r.g(f.worktrees[0], "add", extra)
        r.g(f.worktrees[0], "commit", "-q", "-m", "HACK-001: engine file")
        r.g(f.worktrees[0], "push", "-q", "origin", f.branches[0])
        tip = r.g(f.worktrees[0], "rev-parse", "HEAD").stdout.strip()
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "x", "--no-red", "fixture", now=1000010)
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    # An engine file is a shared resource: only a human's merge may carry it through the gate.
    out = rm.actor(f, "boss", "merge", "HACK-001", now=1000030, human=True, allowed=None) if human else f.hack(0, "merge", "HACK-001", now=1000030, allowed=None)
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout, "the merge goes through: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-600:]))
    return out


def affected_mode_runs_only_matching_tests(r):
    f, log = affected_fixture(r, "only", mode="affected")
    merge_task(r, f)
    seen = log.read_text(encoding="utf-8")
    names = seen.split("SET=", 1)[1].split()
    expect("test_names_it" in names and "test_unrelated" not in names and "test_hack" not in names, "only tests naming value-1.txt: " + seen)
    rec = f.show("tasks/HACK-001.md")
    m = re.search(r"Smoke: affected (\d+) of (\d+) test files", rec)
    expect(m and int(m.group(1)) == len(names) and len(names) < int(m.group(2)) - 3, "the record says which: " + rec)
    return "affected %d of %s" % (len(names), m.group(2))


HARNESS = r'''# $1 the engine's .uak/bin, $2 a candidate repo with the merge staged. The scope function alone: an engine file is a
# shared resource, so no agent merge carries one through the gate; a human's merge reaches this code.
UAK_BIN=$1
. "$UAK_BIN/lib/review-merge.sh" || exit 9
coord_source_field() { printf '%s\n' affected; }
RM_BUILD=$2 TXROOT=$(mktemp -d)
rm_smoke_scope
printf 'NOTE=%s TESTS=%s NONE=%s\n' "$RM_SMOKE_NOTE" "${RM_SMOKE_TESTS:-UNSET}" "${RM_SMOKE_NONE-}"
'''


def engine_core_change_runs_everything(r):
    base = Path(tempfile.mkdtemp(prefix="ma-core-", dir=str(r.scratch)))
    repo = base / "candidate"
    repo.mkdir()
    r.g(repo, "init", "-q")
    r.g(repo, "config", "user.name", "t"); r.g(repo, "config", "user.email", "t@example.test")
    for rel, text in ((".uak/bin/lib/core.sh", "# core\n"), (".uak/bin/lib/tx.sh", "# tx\n"), (".uak/bin/uak-coordination", "# coord\n"),
                      (".uak/bin/lib/plan.sh", "# plan\n"), ("docs/guide.md", "# guide\n"), ("docs/other.md", "# other\n"), (".uak/bin/lib/claim.sh", "# claim\n"), (".uak/tests/test_names_it.py", "# docs/guide.md\n"),
                      (".uak/tests/test_other.py", "# nothing\n")):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    r.g(repo, "add", "-A"); r.g(repo, "commit", "-q", "-m", "base")
    h = base / "harness.sh"
    h.write_text(HARNESS, encoding="utf-8", newline="\n")
    bindir = (r.package / ".uak" / "bin").as_posix()

    def scope(changed):
        r.g(repo, "reset", "-q", "--hard")
        for rel in changed:
            (repo / rel).write_text((repo / rel).read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
            r.g(repo, "add", rel)
        return r.run([r.bash, h.as_posix(), bindir, repo.as_posix()], cwd=base, allowed=None).stdout
    for core in (".uak/bin/lib/core.sh", ".uak/bin/lib/tx.sh", ".uak/bin/uak-coordination", ".uak/bin/lib/claim.sh"):
        out = scope([core, "docs/guide.md"])
        expect("NOTE=full (engine changed) TESTS=UNSET" in out, "%s runs everything: %s" % (core, out))
    out = scope(["docs/guide.md"])
    expect("NOTE=affected 1 of 2 test files TESTS=test_names_it" in out, "a non-engine file is affected-mode: " + out)
    out = scope(["docs/other.md"])
    expect("NOTE=affected 0 of 2 test files TESTS=UNSET NONE=" in out and "smoke-none-token" in out, "nothing affected: the internal sentinel, no test list: " + out)
    return "full on engine, affected otherwise"


def default_is_full(r):
    f, log = affected_fixture(r, "default")
    merge_task(r, f)
    expect("SET=UNSET" in log.read_text(encoding="utf-8"), "no key means the whole suite: " + log.read_text(encoding="utf-8"))
    expect("Smoke: full" in f.show("tasks/HACK-001.md"), "the record says full: " + f.show("tasks/HACK-001.md"))
    return "full by default"


def a_stale_none_signal_in_the_users_env_runs_the_tests(r):
    """kit-r1: UAK_SMOKE_GATE_NONE=affected-none left in a user's env made a full gate and a plain smoke run 0 tests."""
    f, log = affected_fixture(r, "stale")
    stale = {"UAK_SMOKE_GATE_NONE": "affected-none"}
    f.claim(0, "HACK-001")
    tip = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "x", "--no-red", "fixture", now=1000010)
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    out = r.run([r.bash, ".uak/bin/uak", "merge", "HACK-001"], cwd=f.clones[0], env={
        "UAK_AGENT": "agent-1", "UAK_HUMAN": "", "UAK_NOW": "1000030", "UAK_REVIEW_MODE": "claims", **stale}, allowed=None)
    expect(out.returncode == 0, "full gate merges: " + (out.stdout + out.stderr)[-400:])
    expect("SET=UNSET" in log.read_text(encoding="utf-8"), "the project smoke saw no none-signal: " + log.read_text(encoding="utf-8"))
    # A plain smoke in a tiny package with one test file: the stale export must not skip it.
    import shutil
    pkg = Path(tempfile.mkdtemp(prefix="ma-plain-", dir=str(r.scratch)))
    shutil.copytree(r.package / ".uak" / "bin", pkg / ".uak" / "bin")
    (pkg / ".uak" / "tests").mkdir()
    (pkg / ".uak" / "tests" / "test_one.py").write_text("print('ONE_RAN')\n", encoding="utf-8")
    # CI runs this file inside a shard: its UAK_SMOKE_TESTS would leak into these nested smokes (lesson #4).
    plain = r.run(["env", "-u", "UAK_SMOKE_TESTS", r.bash, ".uak/bin/smoke", "--package-only"], cwd=pkg, env=stale, allowed=None)
    expect("ONE_RAN" in plain.stdout and "Shard: 0" not in plain.stdout, "a plain smoke ignores a stale none-signal: " + (plain.stdout + plain.stderr)[-400:])
    token = pkg / "token"
    token.write_text("affected-none\n", encoding="utf-8")
    gate = r.run(["env", "-u", "UAK_SMOKE_TESTS", r.bash, ".uak/bin/smoke", "--package-only"], cwd=pkg, env={"UAK_SMOKE_GATE_NONE": token.as_posix()}, allowed=None)
    expect("Shard: 0 of 1" in gate.stdout and "ONE_RAN" not in gate.stdout, "the gate's token file skips the tests: " + (gate.stdout + gate.stderr)[-400:])
    return "stale env ignored"


TESTS = [a_stale_none_signal_in_the_users_env_runs_the_tests, affected_mode_runs_only_matching_tests, engine_core_change_runs_everything, default_is_full]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-merge-affected-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
            started = time.monotonic()
            try:
                note = test(runner)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started), flush=True)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]), flush=True)
    print("MERGE_AFFECTED_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
