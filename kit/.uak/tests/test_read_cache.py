#!/usr/bin/env python3
"""UAK-130: `status` and `next` reuse the last fetch of claims while it is younger than `Read-Cache: N` seconds of
PROJECT.md (default 20; 0 turns it off). The audit measured `status` at 3.7 s and `next` at 2.3 s, each a fetch of
claims, and agents poll about 2.7 times per `done`. The tests count the real `git fetch` calls through a shim in PATH.
A cached read says so in its last line; every write fetches as before and refreshes the cache with what it pushed;
`--fresh` fetches now; `wait` is never served from the cache. Real Git, a local bare remote, the engine's injected
clock (UAK_NOW) to move time."""
import argparse
import concurrent.futures
import json
import os
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

T0 = 1000000
# The shim directory goes first in PATH as an MSYS path: on Windows `C:/dir:$PATH` is split at the drive colon and the
# shim is never found (windows (7), tip 560e2ed: 0 fetches counted).
LAUNCH = ('d=$(cygpath -u "$1" 2>/dev/null) || d=$1; PATH="$d:$PATH"; export PATH; shift; exec bash .uak/bin/uak "$@"')


def shim(r):
    """A git in front of PATH that logs every `fetch`: the number of lines is the number of fetches."""
    d = r.scratch / "read-cache-shim"
    if not d.exists():
        d.mkdir()
        real = r.run([r.bash, "-c", "type -P git"], cwd=r.scratch).stdout.strip()
        # After the real fetch: logged, 0.3 s for the network round trip a local bare remote does not have, and held
        # until $UAK_FETCH_GATE/go exists when that variable is set (a reader stopped between its fetch and its put).
        script = ('#!/usr/bin/env bash\n"%s" "$@"; rc=$?\n'
                  'for a in "$@"; do if [ "$a" = fetch ]; then echo fetch >> "$UAK_FETCH_LOG"; sleep 0.3\n'
                  '  if [ -n "${UAK_FETCH_GATE:-}" ]; then : > "$UAK_FETCH_GATE/at-fetch"; for i in $(seq 1 150); do [ -e "$UAK_FETCH_GATE/go" ] && break; sleep 0.2; done; fi\n'
                  '  break; fi\n'
                  '  if [ "$a" = push ] && [ -n "${UAK_PUSH_GATE:-}" ]; then : > "$UAK_PUSH_GATE/at-push"; for i in $(seq 1 150); do [ -e "$UAK_PUSH_GATE/go" ] && break; sleep 0.2; done; break; fi\n'
                  'done\nexit $rc\n' % real)
        (d / "git").write_text(script, encoding="utf-8", newline="\n")
        (d / "git").chmod(0o755)
    return d


def fixture(r, name, project=""):
    """Three tasks, one checkout shared by three agents (one cache), PROJECT.md plus `project` lines."""
    f = r.fixture(name, paths={"HACK-%03d" % i: "src/t%d/" % i for i in range(1, 4)}, count=3, shared_repo=True)
    if project:
        p = f.seed / ".uak/PROJECT.md"
        p.write_text(p.read_text(encoding="utf-8") + project, encoding="utf-8")
        r.g(f.seed, "commit", "-qam", "project")
        r.g(f.seed, "push", "-q", "origin", "main")
    f.log = r.scratch / (name + "-fetches")
    f.log.write_text("", encoding="utf-8")
    return f


def fetches(f):
    return len(f.log.read_text(encoding="utf-8").split())


def uak(r, f, index, args, now, allowed=(0,), extra=None):
    env = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_HUMAN": "",
           "UAK_DEDUPE": "off", "UAK_READ_CACHE": "on", "UAK_FETCH_LOG": f.log.as_posix(), **(extra or {})}
    started = time.monotonic()
    out = r.run([r.bash, "-c", LAUNCH, "_", shim(r).as_posix()] + args, cwd=f.worktrees[index], env=env, allowed=allowed)
    return out, time.monotonic() - started


def age_line(out):
    """The age is the LAST line: bin/up parses the first line of next, so nothing goes before it."""
    last = out.stdout.rstrip("\n").splitlines()[-1] if out.stdout.strip() else ""
    m = re.fullmatch(r"claims as of (\d+) s ago", last)
    return int(m.group(1)) if m else None


def second_read_reuses_the_fetch(r):
    f = fixture(r, "rc-reuse")
    f.claim(0, "HACK-001", now=T0)
    first, t1 = uak(r, f, 0, ["status"], T0 + 100)  # the claim's own refresh is long out of the window
    n1 = fetches(f)
    expect(n1 >= 1, "the first read fetches claims: expected: at least 1 fetch, got: %d" % n1)
    expect(age_line(first) is None, "a read that fetched says nothing about age: got last line %r" % first.stdout.splitlines()[-1:])
    second, t2 = uak(r, f, 0, ["status"], T0 + 105)
    for extra in (106, 107):  # the best of three cached reads: one slow scheduling of a loaded runner is not the cache
        again, t = uak(r, f, 0, ["status"], T0 + extra)
        t2 = min(t2, t)
    expect(fetches(f) == n1, "two reads within the window cost one fetch: expected: %d fetches, got: %d" % (n1, fetches(f)))
    expect(age_line(second) == 5, "the second read says how old: expected: 'claims as of 5 s ago', got last line %r" % second.stdout.splitlines()[-1:])
    body = lambda o, cut: "\n".join(o.stdout.splitlines()[1:cut or None])  # the header line carries the clock's epoch
    expect(body(second, -1) == body(first, None), "the cached read prints what the fetched one printed:\n%s\nvs\n%s" % (body(second, -1), body(first, None)))
    # Seconds are measured where the machine is quiet; a shared CI runner is judged by the fetch counts above.
    expect(os.environ.get("CI") or t2 < t1 / 2, "the second status takes under half the first: expected: < %.2f s, got: %.2f s" % (t1 / 2, t2))
    nxt, _ = uak(r, f, 1, ["next"], T0 + 106)
    expect(fetches(f) == n1, "`next` reuses the fetch `status` left: expected: %d fetches, got: %d" % (n1, fetches(f)))
    expect(age_line(nxt) == 6, "next says how old: expected: 6, got: %r" % nxt.stdout.splitlines()[-1:])
    return "first %.2fs with %d fetches, second %.2fs with 0" % (t1, n1, t2)


def a_write_refreshes_the_cache(r):
    f = fixture(r, "rc-write")
    uak(r, f, 0, ["status"], T0 + 1)
    out, _ = uak(r, f, 1, ["status"], T0 + 2)
    expect("HACK-002 | CLAIMED" not in out.stdout, "nothing claimed yet")
    before = fetches(f)
    uak(r, f, 1, ["claim", "HACK-002", "--branch", f.branches[1], "--worktree", f.worktrees[1].as_posix(), "--next", "step"], T0 + 3)
    expect(fetches(f) > before, "a claim fetches as today: expected: more than %d fetches, got: %d" % (before, fetches(f)))
    after = fetches(f)
    seen, _ = uak(r, f, 0, ["status"], T0 + 4)
    expect(re.search(r"HACK-002 \| CLAIMED \| agent-2", seen.stdout), "status right after the write shows the claim:\n" + seen.stdout)
    expect(fetches(f) == after, "that read was served from what the write pushed: expected: %d fetches, got: %d" % (after, fetches(f)))
    expect(age_line(seen) is not None, "and says so in its last line: %r" % seen.stdout.splitlines()[-1:])
    # The write's own refresh is the claims tip: a release is read back at once, too.
    uak(r, f, 1, ["release", "HACK-002"], T0 + 5)
    gone, _ = uak(r, f, 0, ["status"], T0 + 6)
    expect("HACK-002 | CLAIMED" not in gone.stdout, "a release is read back right after it:\n" + gone.stdout)
    return "claim and release are read back within the window"


def fresh_fetches_now(r):
    f = fixture(r, "rc-fresh")
    f.claim(0, "HACK-001", now=T0)
    uak(r, f, 0, ["status"], T0 + 1)
    n = fetches(f)
    out, _ = uak(r, f, 0, ["status", "--fresh"], T0 + 3)
    expect(fetches(f) > n, "--fresh fetches now: expected: more than %d fetches, got: %d" % (n, fetches(f)))
    expect(age_line(out) is None, "a fresh read has no age line: %r" % out.stdout.splitlines()[-1:])
    n = fetches(f)
    out, _ = uak(r, f, 0, ["status"], T0 + 4)
    expect(fetches(f) == n and age_line(out) == 1, "the fresh read refreshed the cache: expected: age 1 and %d fetches, got: %r and %d" % (n, age_line(out), fetches(f)))
    # A change made behind this clone's back is seen by --fresh and not by the cached read.
    other = r.run([r.bash, ".uak/bin/uak", "claim", "HACK-003", "--branch", f.branches[2], "--worktree", f.worktrees[2].as_posix(),
                   "--next", "step"], cwd=f.worktrees[2], env={"UAK_AGENT": "agent-3", "UAK_NOW": str(T0 + 5), "UAK_REMOTE": "origin", "UAK_HUMAN": ""})
    expect(other.returncode == 0, "agent-3 claims")
    fresh, _ = uak(r, f, 0, ["status", "--fresh"], T0 + 6)
    expect("HACK-003 | CLAIMED | agent-3" in fresh.stdout, "--fresh shows the claim:\n" + fresh.stdout)
    return "--fresh fetches and refreshes"


def zero_turns_it_off(r):
    f = fixture(r, "rc-off", project="Read-Cache: 0\n")
    f.claim(0, "HACK-001", now=T0)
    a, _ = uak(r, f, 0, ["status"], T0 + 1)
    n = fetches(f)
    b, _ = uak(r, f, 0, ["status"], T0 + 2)
    expect(fetches(f) > n, "Read-Cache: 0 fetches every read: expected: more than %d fetches, got: %d" % (n, fetches(f)))
    expect(age_line(a) is None and age_line(b) is None, "no age line when it is off: %r" % b.stdout.splitlines()[-1:])
    return "two reads, two fetches"


def read_says_how_old(r):
    f = fixture(r, "rc-age", project="Read-Cache: 8\n")
    f.claim(0, "HACK-001", now=T0)
    uak(r, f, 0, ["status"], T0 + 10)
    n = fetches(f)
    out, _ = uak(r, f, 0, ["status"], T0 + 12)
    expect(age_line(out) == 2, "exactly: 'claims as of 2 s ago', got: %r" % out.stdout.splitlines()[-1:])
    out, _ = uak(r, f, 0, ["status"], T0 + 17)
    expect(age_line(out) == 7 and fetches(f) == n, "7 s of 8 is inside the window: got %r with %d fetches" % (age_line(out), fetches(f)))
    out, _ = uak(r, f, 0, ["status"], T0 + 18)
    expect(age_line(out) is None and fetches(f) > n, "8 s is the end of the window: a fetch and no age line, got %r and %d fetches" % (age_line(out), fetches(f)))
    # A clock that went backwards never serves the cache.
    n = fetches(f)
    out, _ = uak(r, f, 0, ["status"], T0 + 5)
    expect(age_line(out) is None and fetches(f) > n, "a cache from the future is a miss")
    # --json keeps its keys and adds the age; no text line in stdout.
    uak(r, f, 0, ["status"], T0 + 30)
    out, _ = uak(r, f, 0, ["status"], T0 + 33)
    plain = json.loads(uak(r, f, 0, ["--json", "status"], T0 + 34)[0].stdout)
    expect(plain.get("claims_age") == 4, "--json carries claims_age: expected: 4, got: %r" % plain.get("claims_age"))
    expect(not any(l.startswith("claims as of") for l in plain["stdout"]), "no text line inside the JSON stdout: %r" % plain["stdout"][-1:])
    for key in ("v", "cmd", "ok", "exit", "result", "stdout", "stderr", "tasks"):
        expect(key in plain, "--json keeps its key %r" % key)
    fresh = json.loads(uak(r, f, 0, ["--json", "status", "--fresh"], T0 + 35)[0].stdout)
    expect("claims_age" not in fresh, "a fetched read has no claims_age: %r" % fresh.get("claims_age"))
    return "age line, window edge, backwards clock, --json"


def wait_is_never_cached(r):
    """`wait` polls for a change: a cache would hide it. Its fetch count grows on every call."""
    f = fixture(r, "rc-wait")
    f.claim(0, "HACK-001", now=T0)
    uak(r, f, 0, ["status"], T0 + 1)
    n = fetches(f)
    uak(r, f, 0, ["wait", "HACK-001", "--for", "message", "--timeout", "1"], T0 + 2, allowed=(0, 1, 2, 3, 4))
    expect(fetches(f) > n, "wait fetches though a cache is fresh: expected: more than %d fetches, got: %d" % (n, fetches(f)))
    return "wait fetched"


def a_held_reader_never_overwrites_a_write(r):
    """kit-r2 (review of d68b644): a status that fetched before a claim pushed must not replace the entry the claimer's
    own write refreshed, even when it started in the same second or later. The reader is held after its fetch."""
    import threading
    f = fixture(r, "rc-held")
    gate = f.base / "gate"
    gate.mkdir()
    uak(r, f, 0, ["status"], T0 + 50)
    res = {}
    t = threading.Thread(target=lambda: res.update(r=uak(r, f, 0, ["status"], T0 + 100, extra={"UAK_FETCH_GATE": gate.as_posix()})[0]))
    t.start()
    for _ in range(100):
        if (gate / "at-fetch").exists():
            break
        time.sleep(0.2)
    expect((gate / "at-fetch").exists(), "the reader reached its fetch")
    uak(r, f, 1, ["claim", "HACK-002", "--branch", f.branches[1], "--worktree", f.worktrees[1].as_posix(), "--next", "step"], T0 + 100)
    (gate / "go").write_text("", encoding="utf-8")
    t.join()
    expect("HACK-002 | CLAIMED" not in res["r"].stdout, "the held reader fetched before the claim")
    for now in (T0 + 100, T0 + 101):
        out, _ = uak(r, f, 1, ["status"], now)
        expect(re.search(r"HACK-002 \| CLAIMED \| agent-2", out.stdout), "the claimer reads its own write at %d, got:\n%s" % (now - T0, out.stdout))
    nxt, _ = uak(r, f, 1, ["next"], T0 + 102)
    expect("HACK-002" in nxt.stdout, "next of the claimer names its live task:\n" + nxt.stdout)
    return "a reader held across a claim lost its put"


def two_writers_the_older_put_last(r):
    """kit-r2 (round 2): writer A is held after its push; writer B fetches A's tip, pushes and puts; A then puts. A's put
    holds the older tip: it must not replace B's entry. Every agent then reads both claims."""
    import threading
    f = fixture(r, "rc-writers")
    gate = f.base / "pgate"
    gate.mkdir()
    uak(r, f, 0, ["status"], T0 + 90)
    res = {}
    claim = lambda i, task, now, extra=None: uak(r, f, i, ["claim", task, "--branch", f.branches[i], "--worktree", f.worktrees[i].as_posix(), "--next", "step"], now, extra=extra)[0]
    t = threading.Thread(target=lambda: res.update(a=claim(1, "HACK-002", T0 + 100, {"UAK_PUSH_GATE": gate.as_posix()})))
    t.start()
    for _ in range(100):
        if (gate / "at-push").exists():
            break
        time.sleep(0.2)
    expect((gate / "at-push").exists(), "writer A reached its push")
    claim(2, "HACK-003", T0 + 101)
    (gate / "go").write_text("", encoding="utf-8")
    t.join()
    expect(res["a"].returncode == 0, "writer A's claim succeeded")
    for i in range(3):
        out, _ = uak(r, f, i, ["status"], T0 + 102)
        expect(re.search(r"HACK-002 \| CLAIMED \| agent-2", out.stdout) and re.search(r"HACK-003 \| CLAIMED \| agent-3", out.stdout),
               "agent-%d sees both claims after the older put:\n%s" % (i + 1, out.stdout))
    return "the older writer's put lost; both claims are read back"


def a_dead_lock_does_not_stall_a_put(r):
    """A lock left by a process that died is cleared at once (kill -0 on the pid it holds), not after 5 s of waiting."""
    f = fixture(r, "rc-deadlock")
    uak(r, f, 0, ["status", "--fresh"], T0 + 10)
    d = f.clones[0] / ".git" / "uak-read-cache"
    # A pid of the shell's own namespace (on Windows Git Bash `kill -0` speaks MSYS pids, not the native ones Python's
    # Popen reports): the pid of a bash that ran and exited.
    dead = r.run([r.bash, "-c", "echo $$"], cwd=r.scratch).stdout.strip()
    expect(dead.isdigit(), "a dead pid: %r" % dead)
    (d / "lock").mkdir()
    (d / "lock" / "pid").write_text(dead + "\n", encoding="utf-8", newline="\n")
    started = time.monotonic()
    uak(r, f, 0, ["status", "--fresh"], T0 + 12)
    took = time.monotonic() - started
    expect(not (d / "lock").exists(), "the dead holder's lock was cleared")
    out, _ = uak(r, f, 0, ["status"], T0 + 13)
    expect(age_line(out) == 1, "the put went through: expected: age 1, got: %r" % age_line(out))
    # The cleared lock and the put above are the proof on a shared runner, where one call alone takes 5 s on Windows.
    expect(os.environ.get("CI") or took < 4, "a dead lock must not cost a 5 s wait: took %.1f s" % took)
    return "cleared at once (%.1f s)" % took

# UAK-142: the lock functions run straight from bash shells, stopped between steps by gates (files), not by timing.
LOCK_HEAD = ('d=$(cygpath -u "$1" 2>/dev/null) || d=$1; G=$(cygpath -u "$2" 2>/dev/null) || G=$2; RC_DIR=$(cygpath -u "$3" 2>/dev/null) || RC_DIR=$3\n'
             'UAK_BIN=$d/.uak/bin; . "$d/.uak/bin/lib/cache.sh"\n'
             'w() { n=0; while [ ! -e "$G/$1" ] && [ "$n" -lt 150 ]; do sleep 0.1; n=$((n + 1)); done; }\n')
# A cleaner stopped right after it judged the lock stale (its kill -0 said dead), and again after any rename it makes.
PAUSED_CLEANER = LOCK_HEAD + (
    'kill() { builtin kill "$@"; local rc=$?; if [ ! -e "$G/at-kill" ]; then : > "$G/at-kill"; w go1; fi; return $rc; }\n'
    'mv() { command mv "$@"; local rc=$?; : > "$G/at-mv"; w go2; return $rc; }\n'
    'rc_lock; echo "lock=$?" > "$G/a-result"; rc_held && echo held >> "$G/a-result"; w go3; rc_unlock\n')
HOLDER = LOCK_HEAD + 'rc_lock; : > "$G/$4-held"; w "$4-go"; if rc_held; then echo held > "$G/$4-end"; else echo lost > "$G/$4-end"; fi; rc_unlock\n'


def lock_fixture(r, name):
    base = r.scratch / name
    d = base / "rc"
    (d).mkdir(parents=True)
    (base / "g").mkdir()
    dead = r.run([r.bash, "-c", "echo $$"], cwd=r.scratch).stdout.strip()
    expect(dead.isdigit(), "a dead pid: %r" % dead)
    return base / "g", d, dead


def lock_proc(r, script, g, d, *extra):
    import subprocess
    return subprocess.Popen([r.bash, "-c", script, "x", str(r.package), str(g), str(d), *extra], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def wait_for(path, secs=15):
    end = time.monotonic() + secs
    while time.monotonic() < end and not path.exists():
        time.sleep(0.05)
    return path.exists()


def a_cleaner_that_judged_stale_never_removes_a_retaken_lock(r):
    """Cleaner A sees a dead holder's lock and stops. Holder C clears it and takes the lock. When A goes on it must leave
    C's lock where it is, every instant (today A renames it away, and a third writer can mkdir into the gap)."""
    g, d, dead = lock_fixture(r, "lock-reap")
    (d / "lock").mkdir()
    (d / "lock" / "pid").write_text(dead + "\n", encoding="utf-8", newline="\n")
    procs = []
    try:
        a = lock_proc(r, PAUSED_CLEANER, g, d); procs.append(a)
        expect(wait_for(g / "at-kill"), "cleaner A judged the lock stale")
        c = lock_proc(r, HOLDER, g, d, "c"); procs.append(c)
        expect(wait_for(g / "c-held"), "holder C took the lock")
        (g / "go1").write_text("", encoding="utf-8")
        gone = []
        for _ in range(12):  # A runs on: the lock must exist all along, and A must not have renamed anything
            gone.append(not (d / "lock" / "pid").exists() or (g / "at-mv").exists())
            time.sleep(0.05)
        expect(not any(gone), "C's lock was moved away by the cleaner that judged the OLD holder stale (%d of 12 looks)" % sum(gone))
        (g / "go2").write_text("", encoding="utf-8")
        (g / "c-go").write_text("", encoding="utf-8")
        expect(wait_for(g / "c-end"), "holder C finished")
        expect((g / "c-end").read_text(encoding="utf-8").strip() == "held", "C still held the lock when it unlocked")
        expect(wait_for(g / "a-result"), "A got the lock once C was done")
        expect((g / "a-result").read_text(encoding="utf-8").split()[0] == "lock=0", "A's rc_lock succeeded: %r" % (g / "a-result").read_text(encoding="utf-8"))
        (g / "go3").write_text("", encoding="utf-8")
        a.communicate(timeout=30)
        expect(not (d / "lock").exists() and not (d / "lock.reap").exists(), "no lock and no lock.reap left behind")
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
    return "C's lock never moved"


def a_holder_cleared_as_slow_neither_unlocks_nor_publishes(r):
    """A holds the lock, is cleared as stale (another host, a minute gone) and B takes it. A's unlock must not remove
    B's lock, and rc_held says A lost it (rc_put publishes nothing then)."""
    g, d, _ = lock_fixture(r, "lock-slow")
    procs = []
    try:
        a = lock_proc(r, HOLDER, g, d, "a"); procs.append(a)
        expect(wait_for(g / "a-held"), "A took the lock")
        import shutil
        shutil.rmtree(d / "lock")  # what a cleaner does to a lock older than a minute
        b = lock_proc(r, HOLDER, g, d, "b"); procs.append(b)
        expect(wait_for(g / "b-held"), "B took the lock A lost")
        (g / "a-go").write_text("", encoding="utf-8")
        expect(wait_for(g / "a-end"), "A finished")
        a.communicate(timeout=30)
        expect((g / "a-end").read_text(encoding="utf-8").strip() == "lost", "A knows it lost the lock: %r" % (g / "a-end").read_text(encoding="utf-8"))
        expect((d / "lock" / "pid").exists(), "A's unlock removed B's lock")
        (g / "b-go").write_text("", encoding="utf-8")
        expect(wait_for(g / "b-end") and (g / "b-end").read_text(encoding="utf-8").strip() == "held", "B still held the lock")
        b.communicate(timeout=30)
        expect(not (d / "lock").exists(), "B's unlock removed its own lock")
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
    return "A neither held nor unlocked B's lock"


def a_fresh_lock_reap_next_to_a_dead_holder_waits_and_gives_up(r):
    """A cleaner died holding a young lock.reap: waiters sleep between looks and give up (rc_lock returns 1, the caller
    fetches) instead of spinning until the lock.reap is a minute old. UAK_RC_SPINS shortens the 100 looks of 50 ms."""
    import subprocess
    g, d, dead = lock_fixture(r, "lock-fresh-reap")
    (d / "lock").mkdir()
    (d / "lock" / "pid").write_text(dead + ".5\n", encoding="utf-8", newline="\n")
    (d / "lock.reap").mkdir()
    script = LOCK_HEAD + 'rc_lock; echo "lock=$?"\n'
    env = dict(r.env, UAK_RC_SPINS="6")
    started = time.monotonic()
    out = subprocess.run([r.bash, "-c", script, "x", str(r.package), str(g), str(d)], capture_output=True, text=True, env=env, timeout=30)
    took = time.monotonic() - started
    expect("lock=1" in out.stdout, "rc_lock gave up: %r %r" % (out.stdout, out.stderr))
    expect(took >= 0.25, "it slept between looks instead of spinning: %.2f s" % took)
    expect((d / "lock.reap").exists(), "a young lock.reap was left alone")
    return "gave up in %.1f s" % took


def a_stuck_lock_reap_does_not_stall_the_lock(r):
    """A `lock.reap` left by a cleaner that died (older than a minute) is removed, and the dead holder's lock goes."""
    g, d, dead = lock_fixture(r, "lock-stuck")
    (d / "lock").mkdir()
    (d / "lock" / "pid").write_text(dead + ".1\r\n", encoding="utf-8", newline="")  # a CRLF pid file
    (d / "lock.reap").mkdir()
    old = time.time() - 300
    os.utime(d / "lock.reap", (old, old))
    a = lock_proc(r, HOLDER, g, d, "a")
    try:
        expect(wait_for(g / "a-held", 20), "the lock was taken past a stuck lock.reap")
        (g / "a-go").write_text("", encoding="utf-8")
        a.communicate(timeout=30)
    finally:
        if a.poll() is None:
            a.kill()
    expect(not (d / "lock.reap").exists() and not (d / "lock").exists(), "nothing left behind")
    return "stuck lock.reap cleared"


def no_noise_on_stderr(r):
    """The first read in a clone and every read after a write that dropped the cache print nothing on stderr."""
    f = fixture(r, "rc-quiet")
    a, _ = uak(r, f, 0, ["status"], T0 + 1)
    expect(a.stderr == "", "the first read: expected: empty stderr, got: %r" % a.stderr)
    b, _ = uak(r, f, 0, ["status"], T0 + 2)
    expect(b.stderr == "" and age_line(b) == 1, "a cached read: stderr %r" % b.stderr)
    uak(r, f, 0, ["done", "HACK-001"], T0 + 3, allowed=None)  # a writer that leaves no entry
    c, _ = uak(r, f, 1, ["status"], T0 + 4)
    expect(c.stderr == "", "a read after a drop: expected: empty stderr, got: %r" % c.stderr)
    return "stderr empty"


def a_corrupt_entry_is_a_miss(r):
    """An entry whose clone is empty, without .git, or cut short is a miss: status fetches and exits 0."""
    import shutil
    import stat

    def rmtree(path):  # Git's object files are read-only: Windows refuses to delete them until they are writable
        def onerror(func, p, _exc):
            os.chmod(p, stat.S_IWRITE)
            func(p)
        shutil.rmtree(path, onerror=onerror)
    f = fixture(r, "rc-corrupt")
    for damage in ("empty", "no-git", "no-head"):
        uak(r, f, 0, ["status", "--fresh"], T0 + 10)
        d = f.clones[0] / ".git" / "uak-read-cache"
        cur = (d / "current").read_text(encoding="utf-8").strip()
        tx = d / cur / "tx"
        expect(tx.is_dir(), "an entry exists to damage")
        if damage == "empty":
            rmtree(tx)
            tx.mkdir()
        elif damage == "no-git":
            rmtree(tx / ".git")
        else:
            (tx / ".git" / "HEAD").write_text("ref: refs/heads/nowhere\n", encoding="utf-8")
        n = fetches(f)
        out, _ = uak(r, f, 0, ["status"], T0 + 11)
        expect(fetches(f) > n and age_line(out) is None, "a %s entry is a miss: expected: a fetch, got: %d fetches, age %r" % (damage, fetches(f), age_line(out)))
        expect("AVAILABLE=" in out.stdout, "status printed the state: " + out.stdout[:200])
    return "empty, no .git, no HEAD: three misses"


def fresh_is_accepted_everywhere(r):
    """--fresh on the commands that do not read the cache is a no-op (they always fetch): it is not an invalid option."""
    f = fixture(r, "rc-fresh-all")
    f.claim(0, "HACK-001", now=T0)
    for args in (["inbox", "--fresh"], ["board", "--fresh"], ["metrics", "--fresh"], ["timeline", "HACK-001", "--fresh"]):
        out, _ = uak(r, f, 0, args, T0 + 5, allowed=None)
        expect("nvalid option" not in out.stderr and "nexpected" not in out.stderr and out.returncode in (0, 1),
               "uak %s must accept --fresh: exit %d, %s" % (" ".join(args), out.returncode, out.stderr[-200:]))
    return "inbox, board, metrics, timeline accept --fresh"


def a_simulated_clock_does_not_read_the_cache(r):
    """UAK_NOW does not move between calls: the cache needs a real clock, or UAK_READ_CACHE=on from a test."""
    f = fixture(r, "rc-sim")
    f.claim(0, "HACK-001", now=T0)
    env = {"UAK_AGENT": "agent-1", "UAK_NOW": str(T0 + 1), "UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_DEDUPE": "off",
           "UAK_FETCH_LOG": f.log.as_posix()}
    outs = [r.run([r.bash, "-c", LAUNCH, "_", shim(r).as_posix(), "status"], cwd=f.worktrees[0], env=env) for _ in range(2)]
    expect(fetches(f) >= 2, "two reads at a simulated instant fetch twice: got %d" % fetches(f))
    expect(all(age_line(o) is None for o in outs), "no age line under a simulated clock")
    return "two fetches"


def a_push_of_the_base_from_this_checkout_is_read_back(r):
    """PROJECT.md and TASKS.md come from the base: the user's own push of them (the first-run flow: push, then next)
    moves origin/main here, and the cached read is not served over it."""
    f = fixture(r, "rc-base")
    uak(r, f, 0, ["status"], T0 + 100)
    n = fetches(f)
    clone = f.clones[0]
    (clone / "NOTE.md").write_text("x\n", encoding="utf-8")
    r.g(clone, "add", "NOTE.md")
    r.g(clone, "commit", "-qm", "note")
    r.g(clone, "push", "-q", "origin", "HEAD:main")
    out, _ = uak(r, f, 0, ["status"], T0 + 101)
    expect(fetches(f) > n and age_line(out) is None, "a push of the base is a miss: expected: more than %d fetches, got: %d" % (n, fetches(f)))
    return "miss after a push of main"


TESTS = [second_read_reuses_the_fetch, a_write_refreshes_the_cache, fresh_fetches_now, zero_turns_it_off, read_says_how_old,
         wait_is_never_cached, a_held_reader_never_overwrites_a_write, two_writers_the_older_put_last, a_dead_lock_does_not_stall_a_put, a_cleaner_that_judged_stale_never_removes_a_retaken_lock, a_holder_cleared_as_slow_neither_unlocks_nor_publishes, a_stuck_lock_reap_does_not_stall_the_lock, a_fresh_lock_reap_next_to_a_dead_holder_waits_and_gives_up, no_noise_on_stderr, a_corrupt_entry_is_a_miss, fresh_is_accepted_everywhere, a_push_of_the_base_from_this_checkout_is_read_back, a_simulated_clock_does_not_read_the_cache]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-read-cache-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        shim(runner)  # once, before the threads
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
    print("READ_CACHE_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
