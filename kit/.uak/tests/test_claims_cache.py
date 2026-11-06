#!/usr/bin/env python3
"""UAK-004: a cache of the parsed claims state (lib/cache.sh), keyed by the exact claims tip and base tip. A read whose
tips are unchanged reuses the state without a clone, coord_init or state_load; leases, the freeze and every "min ago"
are still computed from the clock, because the cache holds record data only. A mutation, a different tip, a corrupt
or partial cache file never serve a stale state, and nothing in the cache runs: it is read with builtins, never eval'd.
A harness sources the engine's libraries and calls cache_put / cache_get on a read clone of claims, as `uak status`
and `uak next` build it (fresh_state: claims checked out, the base fetched to refs/uak/config). Real Git."""
import argparse
import concurrent.futures
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

HARNESS = r'''# $1 the engine's .uak/bin, $2 the mode, $3 ROOT (a checkout of the clone: the cache lives in its git common dir).
#   put TX TXROOT              coord_init and state_load on the read clone TX, then cache_put of the state and files
#   get TXROOT CLAIMS BASE     cache_get into TXROOT (no clone: TX names a directory that does not exist)
#   bare TXROOT CLAIMS BASE    cache_get of the state alone with an empty PATH: a hit starts no process
#   drop                       cache_drop
# Prints PUT / NOPUT why / HIT / MISS why, then the state: S name=value, L claim lease, A task min ago, F freeze.
set -u  # as .uak/bin/uak runs, with its Git for Windows setting: refs/uak/config:.uak/PROJECT.md is a git object
# name, not a path list (without it coord_init read an empty PROJECT.md there and the freeze was 0).
MSYS2_ARG_CONV_EXCL="refs/;origin/;${UAK_REMOTE:-origin}/;HEAD;FETCH_HEAD;:"; export MSYS2_ARG_CONV_EXCL
UAK_BIN=$1 MODE=$2 ROOT=$3; shift 3
for l in lib/core.sh uak-coordination lib/config.sh lib/backlog.sh lib/status.sh lib/cache.sh; do . "$UAK_BIN/$l" || exit 9; done
LEASE=1800 BASE=main CMD=status ID= AGENT=agent-1 REG_MUTATE=${H_MUTATE:--}
clock_now
dump() {
  local v id e
  for v in $UAK_S_VARS; do printf 'S %s=%s\n' "$v" "${!v}"; done
  for id in $UAK_S_claims; do
    sv claims "$id" Lease-Until; e=active; [ "$NOW" -lt "$SV" ] || e=EXPIRED; printf 'L %s %s\n' "$id" "$e"
  done
  for id in $UAK_S_tasks; do
    sv tasks "$id" Updated; case "$SV" in ''|*[!0-9]*) ;; *) printf 'A %s %s min ago\n' "$id" $(((NOW - SV) / 60));; esac
  done
  freeze_warning | while IFS= read -r v; do printf 'F %s\n' "$v"; done
}
case "$MODE" in
  put) TX=$1 TXROOT=$2; coord_init > /dev/null
       state_load
       if cache_put "$TXROOT/canonical-TASKS.md" "$TXROOT/coord-auth"; then echo PUT; else echo "NOPUT ${CACHE_WHY:-}"; fi
       dump;;
  get) TXROOT=$1 TX=$1/not-a-clone; mkdir -p "$TXROOT"
       if cache_get "$2" "$3" "$TXROOT"; then echo HIT; dump; else echo "MISS ${CACHE_WHY:-}"; fi;;
  bare) TXROOT=$1 TX=$1/not-a-clone; saved=$PATH; PATH=/no-programs-here  # one entry, no drive colon
       cache_get "$2" "$3"; rc=$?; PATH=$saved
       if [ "$rc" -eq 0 ]; then echo HIT; dump; else echo "MISS ${CACHE_WHY:-}"; fi;;
  drop) cache_drop; echo DROPPED;;
esac
'''

T0 = 1000000          # the fixture's claims are taken at this epoch
FREEZE = 1003000      # Freeze-Epoch on PROJECT.md


def harness(r):
    h = r.scratch / "claims-cache-harness.sh"
    if not h.exists():
        h.write_text(HARNESS, encoding="utf-8", newline="\n")
    return h


def call(r, f, mode, args, now=T0 + 60, mutate=None):
    env = {"UAK_NOW": str(now), "UAK_AGENT": "agent-1", "UAK_REMOTE": "origin"}
    if mutate:
        env["H_MUTATE"] = mutate
    out = r.run([r.bash, harness(r).as_posix(), (r.package / ".uak/bin").as_posix(), mode, f.worktrees[0].as_posix()]
                + [str(a) for a in args], cwd=f.base, env=env, allowed=None)
    expect(out.returncode == 0, "harness %s failed (%d): %s" % (mode, out.returncode, (out.stdout + out.stderr)[-1500:]))
    lines = out.stdout.splitlines()
    expect(lines, "harness %s printed nothing: %s" % (mode, out.stderr[-800:]))
    return lines[0], lines[1:], out


def state(lines):
    return sorted(l for l in lines if l.startswith("S "))


def fixture(r, name, claims=1):
    """A remote with a freeze on PROJECT.md and `claims` tasks claimed at T0 (agent-1 HACK-001, agent-2 HACK-002)."""
    f = r.fixture(name, paths={"HACK-%03d" % i: "src/t%d/" % i for i in range(1, 4)}, count=2)
    project = f.seed / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8") + "Freeze-Epoch: %d\n" % FREEZE, encoding="utf-8")
    r.g(f.seed, "commit", "-qam", "freeze")
    r.g(f.seed, "push", "-q", "origin", "main")
    for i in range(claims):
        f.claim(i, "HACK-%03d" % (i + 1), now=T0)
    return f


def read_clone(r, f, name):
    """The clone a read builds (fresh_state): claims checked out, the base at refs/uak/config. Returns (TX, TXROOT)."""
    root = f.base / name
    tx = root / "try-1"
    root.mkdir()
    r.g(root, "clone", "-q", "-b", "claims", f.remote, tx)
    r.g(tx, "fetch", "-q", "origin", "+refs/heads/main:refs/uak/config")
    return tx, root


def tips(r, f):
    out = r.g(f.base, "ls-remote", f.remote, "refs/heads/claims", "refs/heads/main").stdout.split()
    refs = dict(zip(out[1::2], out[0::2]))
    return refs["refs/heads/claims"], refs["refs/heads/main"]


def entry(f, claims, base):
    """The cache entry: in the clone's common git dir (agent-1/.git), shared by its worktrees."""
    return f.clones[0] / ".git" / "uak-cache" / ("%s-%s" % (claims, base))


def put(r, f, name, now=T0 + 60):
    tx, root = read_clone(r, f, name)
    head, rest, _ = call(r, f, "put", [tx, root], now=now)
    expect(head == "PUT", "cache_put on a clean read clone: expected: PUT, got: %r" % head)
    return tx, root, rest


def reuses_the_state_when_the_tip_is_unchanged(r):
    f = fixture(r, "reuse", claims=2)
    tx, root, fresh = put(r, f, "read-1")
    claims, base = tips(r, f)
    e = entry(f, claims, base)
    expect((e / "state").is_file(), "the cache entry: expected: %s, got: %s" % (e, sorted(p.name for p in e.parent.glob("*"))
                                                                            if e.parent.exists() else "no uak-cache dir"))
    expect(not (f.clones[0] / ".git/worktrees/worktree-1/uak-cache").exists(), "the cache is per clone, not per worktree")
    # Another read of the same tips, without a clone: the same state, and the attached files are back.
    out = f.base / "read-2"
    head, rest, _ = call(r, f, "get", [out, claims, base])
    expect(head == "HIT", "same tips: expected: HIT, got: %r" % head)
    expect(state(rest) == state(fresh), "the reused state differs from the parsed one:\n%s\nvs\n%s" % (state(rest), state(fresh)))
    expect(any(l.startswith("S UAK_S_claims_HACK_002_Owner=agent-2") for l in rest), "the reused state has HACK-002's owner")
    for name in ("canonical-TASKS.md", "coord-auth"):
        got = (out / name).read_bytes() if (out / name).exists() else None
        expect(got == (root / name).read_bytes(), "%s restored from the cache: expected the put's bytes, got: %r" % (name, got))
    # The state alone, from builtins: with an empty PATH any git, awk or cat would fail the read.
    head, bare, _ = call(r, f, "bare", [f.base / "read-3", claims, base])
    expect(head == "HIT", "a hit starts no process: expected: HIT with an empty PATH, got: %r" % head)
    expect(state(bare) == state(fresh), "the state read with an empty PATH differs")
    return "%d variables reused for tip %s, no process on a hit" % (len(state(fresh)), claims[:7])


def recomputes_leases_from_the_clock(r):
    f = fixture(r, "clock")
    _, _, fresh = put(r, f, "read-1", now=T0 + 60)
    claims, base = tips(r, f)
    state_bytes = (entry(f, claims, base) / "state").read_bytes()
    until = int([l for l in fresh if l.startswith("S UAK_S_claims_HACK_001_Lease_Until=")][0].split("=", 1)[1])
    seen, why = {}, {}
    for label, now in (("before", until - 60), ("after", until + 60)):
        head, rest, out = call(r, f, "get", [f.base / ("read-" + label), claims, base], now=now)
        expect(head == "HIT", "%s the lease: expected: HIT, got: %r" % (label, head))
        seen[label] = rest
        auth = f.base / ("read-" + label) / "coord-auth"
        why[label] = "coord-auth %r, stderr %r" % (auth.read_bytes() if auth.exists() else None, out.stderr[-600:])
    want = {"before": "L HACK-001 active", "after": "L HACK-001 EXPIRED"}
    for label, line in want.items():
        expect(line in seen[label], "the lease %s Lease-Until, from the same cache: expected: %r, got: %r" % (label, line, seen[label]))
    ago = {k: [l for l in v if l.startswith("A HACK-001 ")] for k, v in seen.items()}
    expect(ago["before"] == ["A HACK-001 %d min ago" % ((until - 60 - T0) // 60)] and ago["after"] == ["A HACK-001 %d min ago" % ((until + 60 - T0) // 60)],
           "min ago from the clock: got %r" % ago)
    freeze = {k: [l for l in v if l.startswith("F ")] for k, v in seen.items()}
    for label, now in (("before", until - 60), ("after", until + 60)):
        mins = (FREEZE - now + 59) // 60
        expect(len(freeze[label]) == 1 and freeze[label][0].startswith("F FREEZE in %d min" % mins),
               "the freeze %s: expected: FREEZE in %d min, got: %r (%s)" % (label, mins, freeze[label], why[label]))
    # Nothing in the cache comes from the clock: a put at another time writes the same bytes.
    r.run([r.bash, harness(r).as_posix(), (r.package / ".uak/bin").as_posix(), "drop", f.worktrees[0].as_posix()], cwd=f.base)
    put(r, f, "read-2", now=T0 + 999)
    again = (entry(f, claims, base) / "state").read_bytes()
    expect(again == state_bytes, "the cache must hold no clock value: two puts at different times differ")
    return "lease active then EXPIRED, freeze %s then %s, from one cache" % (freeze["before"][0][2:20], freeze["after"][0][2:20])


def never_serves_a_stale_tip(r):
    f = fixture(r, "stale")
    tx, root, _ = put(r, f, "read-1")
    t1, base = tips(r, f)
    # A mutation reads nothing from the cache, even on its own tip.
    head, _, _ = call(r, f, "get", [f.base / "m", t1, base], mutate="claim_mutate")
    expect(head == "MISS mutation", "a mutation (REG_MUTATE claim_mutate): expected: MISS mutation, got: %r" % head)
    # The tip moves: the old entry is never served for it.
    f.claim(1, "HACK-002", now=T0 + 30)
    t2, _ = tips(r, f)
    expect(t2 != t1, "the claim moved the claims tip")
    head, _, _ = call(r, f, "get", [f.base / "t2", t2, base])
    expect(head == "MISS no-entry", "a different tip: expected: MISS no-entry, got: %r" % head)
    head, _, _ = call(r, f, "get", [f.base / "t1b", t1, "0" * 40])
    expect(head == "MISS no-entry", "a different base: expected: MISS no-entry, got: %r" % head)
    # A dirty clone (a record written, not committed) is never cached under its HEAD.
    (tx / "claims/HACK-003.md").write_text("ID: HACK-003\nState: CLAIMED\nOwner: ghost\n", encoding="utf-8")
    head, _, _ = call(r, f, "put", [tx, root])
    expect(head == "NOPUT dirty", "cache_put of an uncommitted record: expected: NOPUT dirty, got: %r" % head)
    (tx / "claims/HACK-003.md").unlink()
    # Corrupt or partial entries are misses.
    e = entry(f, t1, base)
    good = (e / "state").read_text(encoding="utf-8")
    lines = good.splitlines(True)
    for label, text, why in (("partial (no end line)", "".join(lines[:-1]), "corrupt"), ("cut mid-file", good[: len(good) // 2], "corrupt"),
                             ("another format", good.replace("uak-state-cache 1 ", "uak-state-cache 0 ", 1), "other-key"),
                             ("a wrong count", "".join(lines[:-1]) + "end 1\n", "corrupt"), ("empty", "", "corrupt")):
        (e / "state").write_text(text, encoding="utf-8", newline="\n")
        head, _, _ = call(r, f, "get", [f.base / "c", t1, base])
        expect(head == "MISS " + why, "a %s cache file: expected: MISS %s, got: %r" % (label, why, head))
    # An entry renamed to the new tip still names the old one inside: a miss, never the old state.
    (e / "state").write_text(good, encoding="utf-8", newline="\n")
    moved = entry(f, t2, base)
    e.rename(moved)
    head, _, _ = call(r, f, "get", [f.base / "r", t2, base])
    expect(head == "MISS other-key", "an entry whose header names another tip: expected: MISS other-key, got: %r" % head)
    moved.rename(e)
    # Invalidation: after cache_drop, the same tip is a miss.
    call(r, f, "drop", [])
    head, _, _ = call(r, f, "get", [f.base / "d", t1, base])
    expect(head == "MISS no-entry", "after cache_drop: expected: MISS no-entry, got: %r" % head)
    # The new tip, cached from its own clone, serves the new state.
    put(r, f, "read-2")
    head, rest, _ = call(r, f, "get", [f.base / "n", t2, base])
    expect(head == "HIT" and "S UAK_S_claims_HACK_002_Owner=agent-2" in rest, "the new tip: expected: HIT with HACK-002, got: %r" % ([head] + rest[:5]))
    return "mutation, new tip, other base, dirty clone, 5 corrupt files, a renamed entry and a drop: all misses"


def a_hostile_record_in_the_cache_runs_nothing(r):
    """Claims records are data written by other agents, and the cache file sits in .git: a value comes back verbatim, a
    name that is not UAK_S_<word> makes the whole entry a miss, and nothing in either is run."""
    f = fixture(r, "hostile")
    marker = f.base / "ran"
    evil = f.base / "raw"
    r.g(f.base, "clone", "-q", "-b", "claims", f.remote, evil)
    r.g(evil, "config", "user.name", "raw")
    r.g(evil, "config", "user.email", "raw@example.invalid")
    payload = "PATH[$(touch %s)] `touch %s` ${X:0:$(touch %s)} 'q' \"d\"" % ((marker.as_posix(),) * 3)
    (evil / "claims/HACK-009.md").write_text("ID: HACK-009\nOwner: nobody\nState: INTEGRATED\nWorklog: %s\n" % payload, encoding="utf-8")
    r.g(evil, "add", "-A")
    r.g(evil, "commit", "-qm", "raw record")
    r.g(evil, "push", "-q", "origin", "claims")
    put(r, f, "read-1")
    claims, base = tips(r, f)
    head, rest, _ = call(r, f, "get", [f.base / "g", claims, base])
    expect(head == "HIT", "expected: HIT, got: %r" % head)
    expect("S UAK_S_claims_HACK_009_Worklog=" + payload in rest, "the value must come back verbatim: %r" % [l for l in rest if "HACK_009" in l])
    expect(not marker.exists(), "a value in the cache ran a command")
    e = entry(f, claims, base) / "state"
    good = e.read_text(encoding="utf-8")
    lines = good.splitlines(True)
    n = int(lines[-1].split()[1])
    for bad in ("v UAK_S_x[$(touch %s)]=1." % marker.as_posix(), "v PATH=/nowhere.", "v UAK_S_a b=1.",
                "v UAK_S_tasks=HACK-001 *.", "v UAK_S_VARS=PATH.", "v UAK_S_x=$(touch %s)" % marker.as_posix()):
        e.write_text("".join(lines[:-1]) + bad + "\nend %d\n" % (n + 1), encoding="utf-8", newline="\n")
        head, rest, out = call(r, f, "get", [f.base / "h", claims, base])
        expect(head == "MISS corrupt", "a cache line %r: expected: MISS corrupt, got: %r" % (bad, head))
        expect(not marker.exists(), "a cache line %r ran a command" % bad)
    return "a hostile value round-trips verbatim; 6 hostile cache lines are misses; nothing ran"


TESTS = [reuses_the_state_when_the_tip_is_unchanged, recomputes_leases_from_the_clock, never_serves_a_stale_tip,
         a_hostile_record_in_the_cache_runs_nothing]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-claims-cache-") as tmp:
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
    print("CLAIMS_CACHE_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
