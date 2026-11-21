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


def shim(r):
    """A git in front of PATH that logs every `fetch`: the number of lines is the number of fetches."""
    d = r.scratch / "read-cache-shim"
    if not d.exists():
        d.mkdir()
        real = r.run([r.bash, "-c", "type -P git"], cwd=r.scratch).stdout.strip()
        script = ('#!/usr/bin/env bash\nfor a in "$@"; do [ "$a" = fetch ] && { echo fetch >> "$UAK_FETCH_LOG"; break; }; done\n'
                  'exec "%s" "$@"\n' % real)
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


def uak(r, f, index, args, now, allowed=(0,)):
    env = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_HUMAN": "",
           "UAK_DEDUPE": "off", "UAK_FETCH_LOG": f.log.as_posix(),
           "PATH": shim(r).as_posix() + os.pathsep + os.environ["PATH"]}
    started = time.monotonic()
    out = r.run([r.bash, ".uak/bin/uak"] + args, cwd=f.worktrees[index], env=env, allowed=allowed)
    return out, time.monotonic() - started


def age_line(out):
    last = out.stdout.rstrip("\n").splitlines()[-1] if out.stdout.strip() else ""
    m = re.fullmatch(r"claims as of (\d+) s ago", last)
    return int(m.group(1)) if m else None


def second_read_reuses_the_fetch(r):
    f = fixture(r, "rc-reuse")
    f.claim(0, "HACK-001", now=T0)
    first, t1 = uak(r, f, 0, ["status"], T0 + 1)
    n1 = fetches(f)
    expect(n1 >= 1, "the first read fetches claims: expected: at least 1 fetch, got: %d" % n1)
    expect(age_line(first) is None, "a read that fetched says nothing about age: got last line %r" % first.stdout.splitlines()[-1:])
    second, t2 = uak(r, f, 0, ["status"], T0 + 6)
    expect(fetches(f) == n1, "two reads within the window cost one fetch: expected: %d fetches, got: %d" % (n1, fetches(f)))
    expect(age_line(second) == 5, "the second read says how old: expected: 'claims as of 5 s ago', got last line %r" % second.stdout.splitlines()[-1:])
    body = lambda o: "\n".join(o.stdout.splitlines()[:-1])
    expect(body(second) == first.stdout.rstrip("\n"), "the cached read prints what the fetched one printed:\n%s\nvs\n%s" % (body(second), first.stdout))
    expect(t2 < t1 / 2, "the second status takes under half the first: expected: < %.2f s, got: %.2f s" % (t1 / 2, t2))
    nxt, _ = uak(r, f, 1, ["next"], T0 + 7)
    expect(fetches(f) == n1, "`next` reuses the fetch `status` left: expected: %d fetches, got: %d" % (n1, fetches(f)))
    expect(age_line(nxt) == 6, "next says how old: expected: 6, got: %r" % nxt.stdout.splitlines()[-1:])
    return "first %.2fs with %d fetches, second %.2fs with 0" % (t1, n1, t2)


def a_write_refreshes_the_cache(r):
    f = fixture(r, "rc-write")
    uak(r, f, 0, ["status"], T0 + 1)
    out, _ = uak(r, f, 1, ["status"], T0 + 2)
    expect("HACK-002 | CLAIMED" not in out.stdout, "nothing claimed yet")
    before = fetches(f)
    f.claim(1, "HACK-002", now=T0 + 3)
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


TESTS = [second_read_reuses_the_fetch, a_write_refreshes_the_cache, fresh_fetches_now, zero_turns_it_off, read_says_how_old,
         wait_is_never_cached]


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
