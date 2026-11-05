#!/usr/bin/env python3
"""UAK-003: `status` and `next` read the claims state in one awk pass (lib/state.awk) instead of a subshell per field.
Before this task `next` started about 210 processes and `status` about 190 (UAK-001's counter); half of them were
subshells, one per `$(field …)` or `$(coord_config …)`, and a `ps` walk of up to 8 levels for the session key.
The output does not change: GOLDEN is what the engine printed before the rewrite, on the same fixture.
Real Git, a local bare remote."""
import argparse
import concurrent.futures
import json
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_v592 import bash_major, processes, shims

# Measured before this task with UAK-001's counter on test_claims_perf's fixture (12 tasks, 3 live claims).
BEFORE = {"next": 208, "status": 190, "idle next": 258}
NOW = "1000060"
BIN = Path(__file__).resolve().parents[1] / "bin"


def env(agent):
    return {"UAK_AGENT": agent, "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": NOW, "UAK_DEDUPE": "off"}


def perf_fixture(r, name):
    f = r.fixture(name, paths={"HACK-%03d" % i: "src/t%02d/" % i for i in range(1, 13)}, count=3)
    for i in range(3):
        f.claim(i, "HACK-%03d" % (i + 1))
    return f


def count(r, cwd, args, agent, dedupe="off"):
    """Processes of the second call (the first one of a fresh clone also writes its session file)."""
    e = env(agent)
    e["UAK_DEDUPE"] = dedupe
    r.run([r.bash, ".uak/bin/uak"] + args, cwd=cwd, env=e)
    n, out = processes(r, cwd, [".uak/bin/uak"] + args, "", e)
    expect(out.returncode == 0, "uak %s failed: %s" % (" ".join(args), (out.stdout + out.stderr)[-400:]))
    return n


def body(path, name):
    """The source of one shell function: from `name() {` to the first line that is only `}`."""
    text = (BIN / path).read_text(encoding="utf-8")
    m = re.search(r"(?ms)^%s\(\) \{.*?^\}" % re.escape(name), text)
    expect(m is not None, "%s: function %s not found" % (path, name))
    return m.group(0)


def no_field_subshells(path, names):
    for name in names:
        hits = [l.strip() for l in body(path, name).splitlines()
                if re.search(r"\$\((field|coord_read|coord_config|task_file|claim_file) ", l) or "$(task_file)" in l or "$(claim_file)" in l]
        expect(not hits, "%s %s still reads a field in a subshell: %s" % (path, name, hits[:3]))


def half(r, label, n):
    if bash_major(r) < 4:
        return "not counted on bash %d (no $BASHPID)" % bash_major(r)
    expect(n <= BEFORE[label] // 2, "uak %s: expected: at most %d processes (half of %d), got: %d" % (label, BEFORE[label] // 2, BEFORE[label], n))
    return "%s %d (before %d)" % (label, n, BEFORE[label])


def status_reads_the_state_in_one_pass(r):
    no_field_subshells("lib/status.sh", ["print_status", "print_task", "status_run", "seen_print", "session_key"])
    f = perf_fixture(r, "read-status")
    n = count(r, f.worktrees[0], ["status"], "agent-1")
    note = half(r, "status", n)
    # The session key is one ps pass, not a walk of a ps per level: deduplication on costs a few processes at most.
    if bash_major(r) >= 4:
        on = count(r, f.worktrees[0], ["status", "--full"], "agent-1", dedupe="on")
        expect(on - n <= 4, "the session key: expected: at most 4 processes more with deduplication on, got: %d (%d vs %d)" % (on - n, on, n))
        note += ", dedupe on %d" % on
    return note


def next_reads_the_state_in_one_pass(r):
    no_field_subshells("uak-coordination", ["coord_next", "coord_why", "coord_review_candidate", "coord_tick_mutate", "coord_threshold"])
    f = perf_fixture(r, "read-next")
    notes = [half(r, "next", count(r, f.worktrees[0], ["next"], "agent-1")),
             half(r, "idle next", count(r, f.clones[0], ["next"], "idle-1"))]
    return ", ".join(notes)


def state(r, files):
    """lib/state.awk on some records: the shell assignments it prints, run through bash, as a dict."""
    out = r.run([r.bash, "-c", 'eval "$(awk -f "$1" "${@:2}")" && set | grep "^UAK_S_" | LC_ALL=C sort', "_",
                 (BIN / "lib/state.awk").as_posix()] + [p.as_posix() for p in files], cwd=r.scratch)
    return dict(l.split("=", 1) for l in out.stdout.splitlines() if "=" in l)


def a_record_with_crlf_reads_like_lf(r):
    """A record written on Windows (CRLF) reads exactly like one written on Linux: no \\r in any value."""
    record = ("# Claim\nID: HACK-001\nState: CLAIMED\nOwner: ana-1\nLease-Until: 1000300\n"
              "Next: it's \"quoted\" $(not run) `nor this`\nPaths: src/a b/, src/c/\n")
    sets = []
    for name, text in (("lf", record), ("crlf", record.replace("\n", "\r\n"))):
        d = r.scratch / ("state-" + name) / "claims"
        d.mkdir(parents=True)
        (d / "HACK-001.md").write_bytes(text.encode("utf-8"))
        sets.append(state(r, [d / "HACK-001.md"]))
    lf, crlf = sets
    expect(lf.get("UAK_S_claims_HACK_001_State") == "CLAIMED", "state.awk: expected State CLAIMED, got: %r" % lf.get("UAK_S_claims_HACK_001_State"))
    expect(crlf == lf, "a CRLF record must read like LF: %r vs %r" % (crlf, lf))
    out = r.run([r.bash, "-c", 'eval "$(awk -f "$1" "$2")" && printf "%s|%s|%s" "$UAK_S_claims_HACK_001_Next" "$UAK_S_claims_HACK_001_Paths" "$UAK_S_claims"',
                 "_", (BIN / "lib/state.awk").as_posix(), (r.scratch / "state-crlf/claims/HACK-001.md").as_posix()], cwd=r.scratch)
    expect(out.stdout == "it's \"quoted\" $(not run) `nor this`|src/a b/, src/c/|HACK-001",
           "values must come back verbatim, never run: got %r" % out.stdout)
    return "LF and CRLF give the same %d variables" % len(lf)


def a_raw_record_on_claims_runs_nothing(r):
    """A record pushed raw to claims (no uak) is data: an ID with a colon must not reach `${…:offset}` arithmetic,
    where a field with PATH[$(cmd)] ran cmd in another agent's `uak next` (kit-r1, UAK-003 at dfe7949)."""
    f = r.fixture("read-inject", paths={"HACK-001": "src/a/", "HACK-002": "src/b/"}, count=2)
    f.claim(0, "HACK-001")
    marker = r.scratch / "read-inject-ran"
    evil = f.base / "raw"
    r.g(f.base, "clone", "-q", "-b", "claims", f.remote, evil)
    r.g(evil, "config", "user.name", "raw")
    r.g(evil, "config", "user.email", "raw@example.invalid")
    (evil / "claims/AAA-001.md").write_text("# Claim\nID: HACK-001-Worklog:UAK-S-claims-EVIL-Next\nOwner: agent-2\nState: CLAIMED\nLease-Until: 9999999\n", encoding="utf-8")
    (evil / "claims/EVIL-Next.md").write_text("# Claim\nID: EVIL-Next\nOwner: nobody\nState: INTEGRATED\nWorklog: PATH[$(touch %s)]\n" % marker.as_posix(), encoding="utf-8")
    r.g(evil, "add", "-A")
    r.g(evil, "commit", "-qm", "raw records")
    r.g(evil, "push", "-q", "origin", "claims")
    for args, index in ((["next"], 1), (["status"], 1), (["next"], 0)):
        out = r.run([r.bash, ".uak/bin/uak"] + args, cwd=f.worktrees[index], env=env("agent-%d" % (index + 1)), allowed=None)
        expect(not marker.exists(), "uak %s ran a command written in a claims record: %s" % (" ".join(args), (out.stdout + out.stderr)[-600:]))
        expect(out.returncode == 0, "uak %s must still answer: %s" % (" ".join(args), (out.stdout + out.stderr)[-600:]))
    return "next and status ran nothing from the records"


def a_raw_record_naming_a_task_id_runs_nothing(r):
    """The same attack aimed at a record that does load (HACK-009, a valid task ID): only sv's own checks stop it.
    With dfe7949's sv this ran the command; the EVIL-Next variant above is already stopped by state.awk (kit-r1)."""
    f = r.fixture("read-inject-id", paths={"HACK-001": "src/a/", "HACK-002": "src/b/"}, count=2)
    f.claim(0, "HACK-001")
    marker = r.scratch / "read-inject-id-ran"
    evil = f.base / "raw"
    r.g(f.base, "clone", "-q", "-b", "claims", f.remote, evil)
    r.g(evil, "config", "user.name", "raw")
    r.g(evil, "config", "user.email", "raw@example.invalid")
    (evil / "claims/AAA-001.md").write_text("# Claim\nID: HACK-001-Worklog:UAK-S-claims-HACK-009\nOwner: agent-2\nState: CLAIMED\nLease-Until: 9999999\n", encoding="utf-8")
    (evil / "claims/HACK-009.md").write_text("# Claim\nID: HACK-009\nOwner: nobody\nState: INTEGRATED\nWorklog: PATH[$(touch %s)]\n" % marker.as_posix(), encoding="utf-8")
    r.g(evil, "add", "-A")
    r.g(evil, "commit", "-qm", "raw records")
    r.g(evil, "push", "-q", "origin", "claims")
    for args, index in ((["next"], 1), (["status"], 1)):
        out = r.run([r.bash, ".uak/bin/uak"] + args, cwd=f.worktrees[index], env=env("agent-%d" % (index + 1)), allowed=None)
        expect(not marker.exists(), "uak %s ran a command written in a claims record: %s" % (" ".join(args), (out.stdout + out.stderr)[-600:]))
        expect(out.returncode == 0, "uak %s must still answer: %s" % (" ".join(args), (out.stdout + out.stderr)[-600:]))
    return "next and status ran nothing from HACK-009's record"


def record_names_do_not_collide(r):
    """claims/HACK-001-Lease.md with Until: must not read as HACK-001's Lease-Until: only task IDs (ABC-123) load."""
    d = r.scratch / "state-collide" / "claims"
    d.mkdir(parents=True)
    (d / "HACK-001.md").write_text("ID: HACK-001\nLease-Until: 5\n", encoding="utf-8")
    (d / "HACK-001-Lease.md").write_text("ID: HACK-001-Lease\nUntil: 9\n", encoding="utf-8")
    got = state(r, [d / "HACK-001-Lease.md", d / "HACK-001.md"])
    expect(got.get("UAK_S_claims_HACK_001_Lease_Until") == "5", "HACK-001's Lease-Until: expected '5', got: %r" % got.get("UAK_S_claims_HACK_001_Lease_Until"))
    expect(got.get("UAK_S_claims") == "HACK-001", "only task IDs are listed: got %r" % got.get("UAK_S_claims"))
    return "HACK-001-Lease.md left out"


def golden_outputs(r):
    """status, status --task, next (own task, BLOCKED task, idle, nothing eligible) and digest on one fixture."""
    f = r.fixture("read-golden", paths={"HACK-%03d" % i: "src/t%02d/" % i for i in range(1, 7)}, count=4,
                  dependencies={"HACK-005": "HACK-001"}, owners={"src/t06/": "HACK-002"})
    for i in range(3):
        f.claim(i, "HACK-%03d" % (i + 1))
    f.hack(2, "log", "HACK-003", "--state", "BLOCKED", "the fixture API returns 500")
    base = f.base.as_posix()
    # The path as the engine records it (pwd -P): /private/var/… on macOS, /c/Users/… under Git Bash (kit-r1, UAK-014).
    real = r.run([r.bash, "-c", 'cd "$1" && pwd -P', "_", f.base.as_posix()]).stdout.strip() or base
    outs = {}

    def run(key, index, args, agent=None, cwd=None):
        out = r.run([r.bash, ".uak/bin/uak"] + args, cwd=cwd or f.worktrees[index], env=env(agent or "agent-%d" % (index + 1)), allowed=None)
        text = (out.stdout + ("\n[stderr]\n" + out.stderr if out.stderr.strip() else "")).replace(real, "<base>").replace(base, "<base>")
        # What differs between runs or machines, not between engines: the version, a worklog's random suffix, the
        # read token, and PREFLIGHT (whether this machine's gh is logged in).
        text = re.sub(r"uak v[0-9][^ ]*", "uak vX", text)
        text = re.sub(r"(WL-[^ ]*)\.[A-Za-z0-9]{6}\.md", r"\1.XXXXXX.md", text)
        text = re.sub(r"(?m)^Read-token: .*$", "Read-token: <token>", text)
        text = re.sub(r"(?m)^PREFLIGHT: .*\n", "", text)
        outs[key] = "exit %d\n%s" % (out.returncode, text)

    run("status", 0, ["status"])
    run("status --task HACK-001", 0, ["status", "--task", "HACK-001"])
    run("status --task HACK-004", 0, ["status", "--task", "HACK-004"])
    run("status --task HACK-003 --summary", 0, ["status", "--task", "HACK-003", "--summary"])
    run("next own", 0, ["next"])
    run("next blocked", 2, ["next"])
    run("next idle", 3, ["next"])
    run("digest", 0, ["digest"])
    f.claim(3, "HACK-004")
    run("next nothing eligible", 0, ["next"], agent="idle-1", cwd=f.clones[0])
    run("status after", 0, ["status"])
    return outs


# Printed by the engine before UAK-003 (test_claims_read.py --print-golden at 74a9f51+UAK-011, c949f90).
GOLDEN = {
    "status": "exit 0\nuak vX | remote claims | epoch 1000060 | lease 1800s\nAVAILABLE=3 CLAIMED=2 BLOCKED=1 REVIEW=0 INTEGRATED=0 CANCELLED=0 \nClaims (max 12; use --task ID):\nHACK-001 | CLAIMED | agent-1 | active | until 1001800\nHACK-002 | CLAIMED | agent-2 | active | until 1001800\nHACK-003 | BLOCKED | agent-3 | active | until 1001800\nSmoke: syntax + secrets + product (.uak/bin/smoke-project); --package-only/--full add the kit suite.\nNext: run uak next.\nEvents: 1/60 alert (total 1); checkpoint required in 59 events\nClock: simulated; remote comparison not checked.\n",
    "status --task HACK-001": "exit 0\nHACK-001 | CLAIMED | agent-1\nBranch: task/agent-1\nWorktree: <base>/worktree-1\nPR: -\nPaths: src/t01/\nVerify: .uak/bin/smoke --package-only\nCriteria:\n- **Type:** vertical\n- **Area:** tests, demo\n- **Rubric:** funcionalidad\n- **Acceptance:** salida comprobable\nNext: Ejecutar siguiente paso exacto\nWorklog: worklog/WL-1000000-agent-1-HACK-001-hack.XXXXXX.md (claims branch)\nEvents: 1/60 alert (total 1); checkpoint required in 59 events\nClock: simulated; remote comparison not checked.\n",
    "status --task HACK-004": "exit 0\nHACK-004 | AVAILABLE | P0\nNext: Write its tests, see them fail (uak red HACK-004), then implement until this passes: .uak/bin/smoke --package-only\nPaths: src/t04/\nVerify: .uak/bin/smoke --package-only\nCriteria:\n- **Type:** vertical\n- **Area:** tests, demo\n- **Rubric:** funcionalidad\n- **Acceptance:** salida comprobable\nEvents: 1/60 alert (total 1); checkpoint required in 59 events\nClock: simulated; remote comparison not checked.\n",
    "status --task HACK-003 --summary": "exit 0\nHACK-003 | BLOCKED | agent-3\nBranch: task/agent-3\nWorktree: <base>/worktree-3\nPR: -\nPaths: src/t03/\nVerify: .uak/bin/smoke --package-only\nCriteria:\n- **Type:** vertical\n- **Area:** tests, demo\n- **Rubric:** funcionalidad\n- **Acceptance:** salida comprobable\nNext: Ejecutar siguiente paso exacto\nWorklog: worklog/WL-1000000-agent-3-HACK-003-hack.XXXXXX.md (claims branch)\nLive summary:\n- Done: Claim created; implementation pending\n- Decision: Own branch and worktree\n- Why: Parallel work without touching the main checkout\n- Failing: the fixture API returns 500\n- Commands: .uak/bin/smoke --package-only\n- Next: Ejecutar siguiente paso exacto\nRead-token: <token>\nEvents: 1/60 alert (total 1); checkpoint required in 59 events\nClock: simulated; remote comparison not checked.\n",
    "next own": "exit 0\nHACK-001 | CLAIMED | agent-1\nBranch: task/agent-1\nWorktree: <base>/worktree-1\nNext: Ejecutar siguiente paso exacto\nLive summary:\n- Done: Claim created; implementation pending\n- Decision: Own branch and worktree\n- Why: Parallel work without touching the main checkout\n- Failing: No validation run yet\n- Commands: .uak/bin/smoke --package-only\n- Next: Ejecutar siguiente paso exacto\nEvents: 1/60 alert (total 1); checkpoint required in 59 events\nClock: simulated; remote comparison not checked.\n",
    "next blocked": "exit 0\nHACK-003 | BLOCKED | agent-3\nBranch: task/agent-3\nWorktree: <base>/worktree-3\nNext: Ejecutar siguiente paso exacto\nLive summary:\n- Done: Claim created; implementation pending\n- Decision: Own branch and worktree\n- Why: Parallel work without touching the main checkout\n- Failing: the fixture API returns 500\n- Commands: .uak/bin/smoke --package-only\n- Next: Ejecutar siguiente paso exacto\nEvents: 2/60 alert (total 2); checkpoint required in 58 events\nClock: simulated; remote comparison not checked.\n",
    "next idle": "exit 0\nHACK-004 | AVAILABLE | P0\nNext: Write its tests, see them fail (uak red HACK-004), then implement until this passes: .uak/bin/smoke --package-only\nVerify: .uak/bin/smoke --package-only\nPaths: src/t04/\nBefore editing: bash .uak/bin/wt new HACK-004 --agent agent-4 (branch + worktree + claim).\nEvents: 0/60 alert (total 0); checkpoint required in 60 events\nClock: simulated; remote comparison not checked.\n",
    "digest": "exit 0\nHuman digest | epoch 1000060 | remote claims\nHACK-003 | BLOCKED | agent-3 | PR -\n  Ejecutar siguiente paso exacto\nCapacity: 3 tasks wait and no idle agent is online. More hands: bash .uak/bin/uak up N --tool claude (one worktree and agent each), or uak graph --assign for who takes what next.\nRule: no answer in 15 min → recorded reversible decision, take another task.\nEverything on one page (progress, agents, conversation, reviews, black box): bash .uak/bin/uak dash --watch --open\n",
    "next nothing eligible": "exit 0\nNo eligible candidate (priority, dependencies, claims or authorization).\nWhy not HACK-006: src/t06/ belongs to HACK-002; split the work or request its contract. If the plan gave HACK-006 that path on purpose: drop it (uak plan FILE --amend), give the OWNERS row to HACK-006, or make HACK-002 depend on HACK-006.\nWaiting on dependencies: 1 task(s); HACK-005 waits on HACK-001 (CLAIMED).\nIdle: improve tests → polish demo → rehearse. Do not poll uak next in a loop; wait for a message or a new task.\nEvents: 0/60 alert (total 0); checkpoint required in 60 events\nClock: simulated; remote comparison not checked.\n",
    "status after": "exit 0\nuak vX | remote claims | epoch 1000060 | lease 1800s\nAVAILABLE=2 CLAIMED=3 BLOCKED=1 REVIEW=0 INTEGRATED=0 CANCELLED=0 \nClaims (max 12; use --task ID):\nHACK-001 | CLAIMED | agent-1 | active | until 1001800\nHACK-002 | CLAIMED | agent-2 | active | until 1001800\nHACK-003 | BLOCKED | agent-3 | active | until 1001800\nHACK-004 | CLAIMED | agent-4 | active | until 1001800\nSmoke: syntax + secrets + product (.uak/bin/smoke-project); --package-only/--full add the kit suite.\nNext: run uak next.\nEvents: 1/60 alert (total 1); checkpoint required in 59 events\nClock: simulated; remote comparison not checked.\n"
}


def next_and_status_print_the_same_as_before(r):
    outs = golden_outputs(r)
    for key, want in GOLDEN.items():
        got = outs.get(key)
        if got != want:
            import difflib
            diff = "\n".join(difflib.unified_diff(want.splitlines(), (got or "").splitlines(), "before", "now", lineterm=""))
            expect(False, "uak %s prints something else than before:\n%s" % (key, diff[:1800]))
    expect(set(outs) == set(GOLDEN), "cases: expected %s, got %s" % (sorted(GOLDEN), sorted(outs)))
    return "%d outputs identical" % len(outs)


def a_crlf_checkout_prints_no_carriage_return(r):
    """Git for Windows checks files out with CRLF (core.autocrlf=true). The one-pass read took VERSION and the smoke
    scope with a builtin read, which keeps the \\r: status printed "uak v5.11.0\\r" (CI on e5957e5, Windows:
    test_v52 audit_small_fixes, test_v55 claims_read_on_a_crlf_machine)."""
    f = r.fixture("read-crlf-checkout", paths={"HACK-001": "src/a/"}, count=1)
    f.claim(0, "HACK-001")
    wt = f.worktrees[0]
    version = (wt / ".uak/VERSION").read_text(encoding="utf-8").strip()
    (wt / ".uak/VERSION").write_bytes((version + "\r\n").encode())
    smoke = (wt / ".uak/bin/smoke").read_bytes().split(b"\n", 1)
    (wt / ".uak/bin/smoke").write_bytes(smoke[0] + b"\n# UAK_SMOKE_SCOPE: crlf scope\r\n" + smoke[1])
    for args in (["status"], ["next"], ["status", "--task", "HACK-001"]):
        out = r.run([r.bash, ".uak/bin/uak"] + args, cwd=wt, env=env("agent-1"), allowed=None)
        expect(out.returncode == 0 and "\r" not in out.stdout,
               "uak %s printed a carriage return from the CRLF checkout: %r" % (" ".join(args), out.stdout[:400]))
        if args == ["status"]:
            expect("uak v%s |" % version in out.stdout and "Smoke: crlf scope\n" in out.stdout, out.stdout[:400])
    return {"version": version}


TESTS = [status_reads_the_state_in_one_pass, next_reads_the_state_in_one_pass, a_record_with_crlf_reads_like_lf,
         next_and_status_print_the_same_as_before, a_raw_record_on_claims_runs_nothing, record_names_do_not_collide,
         a_raw_record_naming_a_task_id_runs_nothing, a_crlf_checkout_prints_no_carriage_return]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--print-golden", action="store_true", help="print today's outputs as GOLDEN (to refresh it on purpose)")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-claims-read-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        if args.print_golden:
            print("GOLDEN = " + json.dumps(golden_outputs(runner), indent=4, ensure_ascii=False))
            return 0
        shims(runner)  # once, before the threads
        tests = [t for t in TESTS if not args.case or t.__name__ in args.case]

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("CLAIMS_READ_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
