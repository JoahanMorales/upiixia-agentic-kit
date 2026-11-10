#!/usr/bin/env python3
"""UAK-034: `uak status ID` and `status --task ID` of a task published with `uak plan` (Plan-Channel: claims) that has
no claim or record yet died "ID is not in TASKS.md": the read path loaded main's .uak/TASKS.md, while the transaction
builds the canonical backlog (main's + claims backlog/TASKS.md + AMEND.md). Seen 12 times in two hackathons right
after `uak plan`. Real Git, a local bare remote."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_coordination import config, hack


def task(tid, verify):
    return ("## %s — planned later\n\n- **Priority:** P1\n- **Paths:** src/planned/%s.txt\n- **Depends on:** None\n"
            "- **Acceptance:** the planned criterion shows\n- **Verify:** %s\n\n" % (tid, tid.lower(), verify))


def plan(f, body, *extra):
    path = f.worktrees[0] / ("plan-%d.md" % time.monotonic_ns())
    path.write_text(body, encoding="utf-8")
    return hack(f, 0, "plan", path, *extra, UAK_HUMAN="joahan", allowed=None)


def planned_fixture(r, name):
    f = r.fixture(name, paths={"HACK-001": "src/one/"}, count=2)
    config(f, Plan_Channel="claims")
    out = plan(f, "# Wave\n\n" + task("HACK-005", "echo first"))
    expect(out.returncode == 0 and "OK plan" in out.stdout, "plan must publish: " + out.stdout + out.stderr)
    return f


def status_shows_a_task_planned_on_claims(r):
    f = planned_fixture(r, "sp-planned")
    for args in (["status", "HACK-005"], ["status", "--task", "HACK-005"]):
        out = f.hack(1, *args, allowed=None)
        text = out.stdout + out.stderr
        expect(out.returncode == 0 and "not in TASKS.md" not in text, "%s: rc %d %s" % (args, out.returncode, text[-500:]))
        expect("HACK-005 | AVAILABLE | P1" in text and "src/planned/hack-005.txt" in text and "echo first" in text
               and "the planned criterion shows" in text, "%s must show Paths, Verify and criteria: %s" % (args, text[-600:]))
    return "AVAILABLE with Paths, Verify, criteria"


def amended_task_shows_its_new_verify(r):
    f = planned_fixture(r, "sp-amended")
    out = plan(f, "# Wave\n\n" + task("HACK-005", "echo second"), "--amend")
    expect(out.returncode == 0, "amend must publish: " + out.stdout + out.stderr)
    out = f.hack(1, "status", "--task", "HACK-005", allowed=None)
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "echo second" in text and "echo first" not in text, "the amended Verify shows: " + text[-600:])
    return "amended Verify"


HARNESS = r'''# $1 the engine's .uak/bin, $2 a claims clone with refs/uak/config, $3 a TASKS.md that is only main's stale copy, $4 ID.
# The read path of a command that opened no transaction: TX and BACKLOG as fresh_state leaves them, no coord_init.
UAK_BIN=$1
for l in lib/core.sh uak-coordination lib/config.sh lib/backlog.sh; do . "$UAK_BIN/$l" || exit 9; done
TX=$2 BACKLOG=$3 ID=$4 TXROOT=$(mktemp -d) OWNERS=$TXROOT/none
if (load_task) > "$TXROOT/out" 2>&1; then
  load_task; printf 'LOADED %s | %s | %s\n' "$PRIORITY" "$PATHS" "$VERIFY"
else printf 'REFUSED: %s\n' "$(cat "$TXROOT/out")"; fi
'''


def load_task_reads_the_canonical_backlog_without_a_transaction(r):
    f = planned_fixture(r, "sp-harness")
    clone = f.base / "read-clone"
    r.g(f.base, "clone", "-q", "-b", "claims", f.remote, clone)
    r.g(clone, "fetch", "-q", "origin", "+refs/heads/main:refs/uak/config")
    stale = f.base / "stale-TASKS.md"
    stale.write_text(r.g(f.remote, "show", "main:.uak/TASKS.md").stdout, encoding="utf-8")
    h = f.base / "harness.sh"
    h.write_text(HARNESS, encoding="utf-8", newline="\n")
    bindir = (r.package / ".uak" / "bin").as_posix()
    for tid, want in (("HACK-005", "LOADED P1 | src/planned/hack-005.txt | echo first"), ("HACK-001", "LOADED P0")):
        out = r.run([r.bash, h.as_posix(), bindir, clone.as_posix(), stale.as_posix(), tid], cwd=f.base, allowed=None)
        expect(want in out.stdout, "%s: load_task wants %r, got %s" % (tid, want, (out.stdout + out.stderr)[-400:]))
    out = r.run([r.bash, h.as_posix(), bindir, clone.as_posix(), stale.as_posix(), "HACK-099"], cwd=f.base, allowed=None)
    expect("REFUSED" in out.stdout and "HACK-099 is not in TASKS.md" in out.stdout, "an unknown ID still refuses: " + out.stdout)
    return "planned and main tasks load, unknown refuses"


TESTS = [status_shows_a_task_planned_on_claims, amended_task_shows_its_new_verify,
         load_task_reads_the_canonical_backlog_without_a_transaction]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-status-planned-") as tmp:
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
    print("STATUS_PLANNED_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
