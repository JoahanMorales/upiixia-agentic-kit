#!/usr/bin/env python3
"""UAK-016: `snapshot` (lib/tx.sh) writes STATE.md after every mutation (heartbeat, claim, msg, done...).
It read each record with `$(field ...)`: two subshells per task record and per state (six states), four or five per
claim, a pipeline per state. On UAK-001's fixture it was about 90 of `uak heartbeat`'s 152 processes, and it grew
with every task ever claimed. Now one awk pass reads the records; the shell only formats.
BEFORE is the function as it was (main at b767eee), run side by side with today's on the same records: STATE.md must
be byte-identical. Real Git, a local bare remote for the heartbeat count."""
import argparse
import concurrent.futures
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_v592 import bash_major, processes

BIN = Path(__file__).resolve().parents[1] / "bin"
NOW = 1000060
# `uak heartbeat` on UAK-001's fixture (12 tasks, 3 claims), measured with this counter on main at b767eee (the
# engine before this task). The plan's "152" came from an earlier profile that counted differently.
HEARTBEAT_BEFORE = 210

BEFORE = r'''snapshot_before() {
  [ -f "$TX/DECISIONS.md" ] || {
    printf '# DECISIONS\n\nCoordination decisions on the claims branch.\nWhy: a reversible option after 15 min keeps work moving.\n' > "$TX/DECISIONS.md"
  }
  {
    phase='execution'
    freeze=$(coord_config Freeze-Epoch 0)
    if [ "$freeze" -gt 0 ] && [ "$NOW" -ge "$freeze" ]; then phase='feature freeze; authorized fixes, rehearsal and submission only'; fi
    printf '# STATE\n\nPhase: %s\nUpdated: %s\n' "$phase" "$NOW"
    for state in AVAILABLE CLAIMED BLOCKED REVIEW INTEGRATED CANCELLED; do
      ids=$(for record in "$TX"/tasks/*.md; do
        [ -f "$record" ] || continue
        [ "$(field "$record" State)" != "$state" ] || field "$record" ID
      done | tr '\n' ' ')
      if [ "$state" = AVAILABLE ] && [ -f "$BACKLOG" ]; then
        ids=$(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG" | while IFS= read -r id; do
          [ -f "$TX/tasks/$id.md" ] || printf '%s ' "$id"
        done; printf '%s' "$ids")
      fi
      n_ids=$(printf '%s' "$ids" | wc -w | tr -d ' ')
      [ "${#ids}" -le 120 ] || ids="($n_ids; last 12) ... $(printf '%s' "$ids" | awk '{for(i=(NF>12?NF-11:1);i<=NF;i++) printf "%s ", $i}')"
      printf '%s: %s\n' "$state" "${ids:--}"
    done
    printf '\nClaims (first 24; status --task ID shows detail):\n'
    for c in "$TX"/claims/*.md; do
      [ -f "$c" ] || continue
      lu=$(field "$c" Lease-Until); case "$lu" in ''|*[!0-9]*) lu=0;; esac
      printf '%s | %s | %s | until %s%s\n' "$(field "$c" ID)" "$(field "$c" State)" "$(field "$c" Owner)" "$lu" \
        "$( [ "$(field "$c" State)" = REVIEW ] || [ "$lu" -eq 0 ] || [ "$NOW" -lt "$lu" ] || printf ' (EXPIRED: release --expired --read-summary TOKEN)')"
    done | head -n 24
    printf '\nBlockers: BLOCKED tasks; use status --task ID --summary.\nCurrent decisions (last 5):\n'
    grep '^-' "$TX/DECISIONS.md" | tail -n 5 | cut -c 1-180
    printf '\nGlobal next step: available P0; else review PRs, tests, demo, rehearsal.\nWhy: bounded snapshot to resume without rereading history.\n'
  } > "$TX/STATE.md"
}
'''

STATES = ["AVAILABLE", "CLAIMED", "BLOCKED", "REVIEW", "INTEGRATED", "CANCELLED"]


def body(path, name):
    """The source of one shell function: from `name() {` to the first line that is only `}`."""
    text = (BIN / path).read_text(encoding="utf-8")
    m = re.search(r"(?ms)^%s\(\) \{.*?^\}" % re.escape(name), text)
    expect(m is not None, "%s: function %s not found" % (path, name))
    return m.group(0)


def harness(r):
    """The engine's own field, snapshot today, snapshot before, and coord_config reading Freeze-Epoch from FREEZE."""
    h = r.scratch / "snapshot-harness.sh"
    if not h.exists():
        h.write_text("set -u\n" + body("lib/core.sh", "field") + "\n"
                     + 'coord_cfg() { coord_v=${FREEZE:-}; [ -n "$coord_v" ] || coord_v=${2:-}; }\n'
                     + 'coord_config() { coord_cfg "$@"; printf \'%s\\n\' "$coord_v"; }\n'
                     + body("lib/tx.sh", "snapshot") + "\n" + BEFORE
                     + '"$@"\n', encoding="utf-8")
    return h


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)


def task(tx, name, tid, state, crlf=False, extra=""):
    text = "# Task\nID: %s\nState: %s\nOwner: ana-1\n%s" % (tid, state, extra)
    write(tx / "tasks" / (name + ".md"), text.replace("\n", "\r\n") if crlf else text)


def claim(tx, name, tid, state, owner, lease, crlf=False):
    text = "# Claim\nID: %s\nState: %s\nOwner: %s\nLease-Until: %s\nPaths: src/x/\n" % (tid, state, owner, lease)
    write(tx / "claims" / (name + ".md"), text.replace("\n", "\r\n") if crlf else text)


def backlog(tx, ids, crlf=False):
    text = "# TASKS\n\n" + "".join("## %s · a task\n\n- **Priority:** P0\n\n" % i for i in ids)
    write(tx / "backlog.md", text.replace("\n", "\r\n") if crlf else text)


def protocol_fixtures(base):
    """name -> (TX dir, environment). Each one exercises a branch of snapshot."""
    fx = {}

    def new(name, **env):
        tx = base / name / "tx"
        (tx / "tasks").mkdir(parents=True)
        (tx / "claims").mkdir()
        fx[name] = (tx, env)
        return tx

    new("empty")  # no records, no backlog, no DECISIONS.md yet
    tx = new("every-state")
    for i, st in enumerate(STATES * 3):
        task(tx, "HACK-%03d" % (i + 1), "HACK-%03d" % (i + 1), st)
    backlog(tx, ["HACK-%03d" % i for i in range(1, 25)])  # 19..24 have no record: AVAILABLE from the backlog
    write(tx / "DECISIONS.md", "# DECISIONS\n\n" + "".join("- %d | decision %d %s\n" % (1000000 + i, i, "x" * (i * 30)) for i in range(9)))
    tx = new("long-lists")  # the 120-char cut with "(N; last 12)"
    for i in range(1, 41):
        task(tx, "LONGPREFIX-%03d" % i, "LONGPREFIX-%03d" % i, "INTEGRATED")
    for i in range(41, 46):
        task(tx, "LONGPREFIX-%03d" % i, "LONGPREFIX-%03d" % i, "AVAILABLE")  # released: AVAILABLE with a record
    backlog(tx, ["LONGPREFIX-%03d" % i for i in range(1, 80)])
    tx = new("claims", FREEZE="999")  # freeze passed
    for i in range(30):  # more than 24; leases live, expired, REVIEW, zero, empty, not a number
        lease = [str(NOW + 100), str(NOW - 100), "0", "", "12ab", str(NOW)][i % 6]
        st = "REVIEW" if i % 7 == 0 else "CLAIMED"
        claim(tx, "HACK-%03d" % (i + 1), "HACK-%03d" % (i + 1), st, "agent-%d" % (i % 4), lease)
        task(tx, "HACK-%03d" % (i + 1), "HACK-%03d" % (i + 1), st)
    tx = new("freeze-ahead", FREEZE=str(NOW + 1))
    task(tx, "HACK-001", "HACK-001", "BLOCKED")
    tx = new("odd-records")
    task(tx, "HACK-001", "HACK-001", "CLAIMED", crlf=True)
    claim(tx, "HACK-001", "HACK-001", "CLAIMED", "ana-1", NOW - 5, crlf=True)
    task(tx, "HACK-002", "HACK 002 with spaces", "REVIEW")
    task(tx, "HACK-003", "", "CLAIMED")  # an empty ID
    write(tx / "tasks" / "HACK-004.md", "# Task\nOwner: no state at all\n")
    write(tx / "tasks" / "HACK-005.md", "")  # empty record
    write(tx / "claims" / "HACK-005.md", "")
    write(tx / "tasks" / "HACK-006.md", "# Task\nState: CLAIMED\nState: REVIEW\nID: HACK-006\nID: second\n")  # first wins
    write(tx / "tasks" / "HACK-007.md", "# Task\nID: HACK-007\nState: INTEGRATED")  # no final newline
    task(tx, "HACK-008", "ÜNÏ-008 ñandú", "INTEGRATED")  # multibyte
    (tx / "tasks" / "HACK-009.md").mkdir()  # a directory is not a record
    task(tx, "HACK-010", "HACK-010", "CLAIMED", extra="State-Note: not the State\n IDx: no\n")
    backlog(tx, ["HACK-001", "HACK-011", "HACK-012"], crlf=True)
    write(tx / "DECISIONS.md", "# DECISIONS\r\n\r\n- 1 | crlf decision\r\n- 2 | ñandú " + "é" * 200 + "\n")
    return fx


def run(r, h, fn, tx, env):
    e = {"TX": tx.as_posix(), "NOW": str(NOW), "BACKLOG": (tx / "backlog.md").as_posix(),
         "TXROOT": tx.parent.as_posix(), "FREEZE": env.get("FREEZE", "")}
    out = r.run([r.bash, h.as_posix(), fn], cwd=tx.parent, env=e, allowed=None)
    expect(out.returncode == 0, "%s on %s failed: %s" % (fn, tx.parent.name, (out.stdout + out.stderr)[-600:]))
    return (tx / "STATE.md").read_bytes(), out.stderr


def state_md_is_identical_to_before(r):
    h = harness(r)
    fx = protocol_fixtures(r.scratch / "snapshot-same")
    for name, (tx, env) in fx.items():
        decisions = tx / "DECISIONS.md"
        had = decisions.exists()
        before, err_before = run(r, h, "snapshot_before", tx, env)
        if not had:
            decisions.unlink()
        now, err_now = run(r, h, "snapshot", tx, env)
        if before != now:
            import difflib
            diff = "\n".join(difflib.unified_diff(before.decode("utf-8", "replace").splitlines(),
                                                  now.decode("utf-8", "replace").splitlines(), "before", "now", lineterm=""))
            expect(False, "%s: STATE.md differs from before:\n%s" % (name, diff[:1800]))
        expect(err_now == err_before, "%s: stderr differs: %r vs %r" % (name, err_before[-300:], err_now[-300:]))
    return "%d fixtures byte-identical" % len(fx)


def snapshot_processes(r, h, tx, env):
    trace = tx.parent / "trace"
    e = {"TX": tx.as_posix(), "NOW": str(NOW), "BACKLOG": (tx / "backlog.md").as_posix(),
         "TXROOT": tx.parent.as_posix(), "FREEZE": env.get("FREEZE", "")}
    out = r.run([r.bash, "-c", 'exec 9>>"$1"; shift; exec env BASH_XTRACEFD=9 "PS4=+\\$BASHPID " SHELLOPTS=xtrace bash "$@"',
                 "_", trace.as_posix(), h.as_posix(), "snapshot"], cwd=tx.parent, env=e, allowed=None)
    expect(out.returncode == 0, "snapshot failed: " + (out.stdout + out.stderr)[-400:])
    return len(set(re.findall(r"(?m)^\++([0-9]+) ", trace.read_text(encoding="utf-8", errors="replace"))))


def heartbeat_does_not_grow_with_tasks(r):
    if bash_major(r) < 4:
        return "not counted on bash %d (no $BASHPID)" % bash_major(r)
    h = harness(r)
    counts = {}
    for n in (12, 48):
        tx = r.scratch / ("snapshot-grow-%d" % n) / "tx"
        (tx / "claims").mkdir(parents=True)
        for i in range(n):
            task(tx, "HACK-%03d" % (i + 1), "HACK-%03d" % (i + 1), STATES[i % 6])
        for i in range(3):
            claim(tx, "HACK-%03d" % (i + 1), "HACK-%03d" % (i + 1), "CLAIMED", "agent-1", NOW + 100)
        backlog(tx, ["HACK-%03d" % i for i in range(1, n + 5)])
        write(tx / "DECISIONS.md", "# DECISIONS\n\n- 1 | one\n")
        counts[n] = snapshot_processes(r, h, tx, {})
    expect(counts[48] == counts[12], "snapshot: expected the same processes for 12 and 48 task records, got: %s" % counts)
    expect(counts[12] <= 8, "snapshot: expected at most 8 processes on 12 records, got: %d" % counts[12])
    # The whole heartbeat on UAK-001's fixture: about 90 fewer than before.
    f = r.fixture("snapshot-heartbeat", paths={"HACK-%03d" % i: "src/t%02d/" % i for i in range(1, 13)}, count=3)
    for i in range(3):
        f.claim(i, "HACK-%03d" % (i + 1))
    env = {"UAK_AGENT": "agent-1", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": str(NOW), "UAK_DEDUPE": "off"}
    r.run([r.bash, ".uak/bin/uak", "heartbeat", "HACK-001"], cwd=f.worktrees[0], env=env)
    hb, out = processes(r, f.worktrees[0], [".uak/bin/uak", "heartbeat", "HACK-001"], "", env)
    expect(out.returncode == 0, "heartbeat failed: " + (out.stdout + out.stderr)[-400:])
    expect(hb <= HEARTBEAT_BEFORE - 65, "uak heartbeat: expected at most %d processes (before %d), got: %d"
           % (HEARTBEAT_BEFORE - 65, HEARTBEAT_BEFORE, hb))
    return "snapshot %s, heartbeat %d (before %d)" % (counts, hb, HEARTBEAT_BEFORE)


def a_hostile_record_runs_nothing(r):
    h = harness(r)
    tx = r.scratch / "snapshot-hostile" / "tx"
    marker = r.scratch / "snapshot-hostile" / "ran"
    m = marker.as_posix()
    bad = ["$(touch %s)" % m, "`touch %s`" % m, "x; touch %s" % m, "a[$(touch %s)]" % m, "' \" $((1/0)) ${HOME} %%s \\n"]
    for i, text in enumerate(bad):
        task(tx, "HACK-%03d" % (i + 1), text, STATES[i % 6])
        claim(tx, "HACK-%03d" % (i + 1), text, text, text, text)
    write(tx / "claims" / "HACK-099.md", "ID: x\nState: CLAIMED\nOwner: o\nLease-Until: 1+$(touch %s)\n" % m)
    backlog(tx, ["HACK-1$(touch %s)" % m, "HACK-2`touch %s`" % m])
    state, err = run(r, h, "snapshot", tx, {})
    expect(not marker.exists(), "a record ran a command: " + err[-300:])
    text = state.decode("utf-8")
    for t in bad[:4]:
        expect(t in text, "the record must be written as text: %r not in STATE.md:\n%s" % (t, text[:1200]))
    expect("HACK-1$(touch" in text, "the backlog ID must be written as text:\n" + text[:1200])
    return "%d hostile values written as text" % len(bad)


TESTS = [state_md_is_identical_to_before, heartbeat_does_not_grow_with_tasks, a_hostile_record_runs_nothing]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-snapshot-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        harness(runner)  # once, before the threads
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
    print("SNAPSHOT_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
