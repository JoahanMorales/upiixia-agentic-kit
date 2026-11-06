#!/usr/bin/env python3
"""UAK-002: one persistent claims repo per machine (<git-common-dir>/uak-claims/) instead of a `git init` per call.
One fetch refreshes it, its config is set once, a mkdir lock serializes the processes of one machine, a stale lock
is taken over, and a corrupt or locked repo falls back to a temporary clone (and says so once).
Real Git, a local bare remote, one clone with several worktrees (they share the git common dir)."""
import argparse
import concurrent.futures
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

LOCK = "uak-claims.lock"
FALLBACK = re.compile(r"temporary clone", re.I)


def env_for(index, **extra):
    env = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": "1000000", "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    env.update(extra)
    return env


def with_shim(r, shim, command):
    """The shim goes first on PATH inside bash, as test_v592 does: a PATH built in Python (Windows form) never put it
    before Git Bash's own git (the Windows CI job saw no fetch through it)."""
    if shim is None:
        return command
    # The inner call is `bash` from PATH, as in test_v592: Git for Windows' bin\bash.exe is a launcher that puts
    # /mingw64/bin first on PATH again, before the shim (the Windows job still saw no fetch through it).
    return [r.bash, "-c", 'PATH="$1:$PATH"; export PATH; shift; exec "$@"', "_", shim.as_posix(), "bash"] + command[1:]


def uak(r, f, index, args, allowed=(0,), bash_flags=(), shim=None, **extra):
    return r.run(with_shim(r, shim, [r.bash, *bash_flags, ".uak/bin/uak", *args]), cwd=f.worktrees[index],
                 env=env_for(index, **extra), allowed=allowed)


def claim_args(f, index, task):
    return ["claim", task, "--branch", f.branches[index], "--worktree", f.worktrees[index].as_posix(),
            "--next", "Siguiente paso exacto"]


def common(f):
    return f.clones[0] / ".git"


def slow_git(r, name):
    """A git shim: the claims fetch of a labeled call logs LABEL-begin, then (label A) waits, logs LABEL-end and runs
    the real fetch; label C waits 30 s and fails without touching any repo (it is killed while it waits)."""
    d = r.scratch / ("slow-git-" + name)
    d.mkdir()
    r.run([r.bash, "-c", 'real=$(type -P git) && cat > "$1/git" <<EOF\n'
           '#!/usr/bin/env bash\n'
           'case " \\$* " in *" fetch "*"refs/heads/claims:"*)\n'
           '  printf "%s-begin\\\\n" "\\$UAK_TEST_LABEL" >> "\\$UAK_TEST_ORDER"\n'
           '  case "\\$UAK_TEST_LABEL" in A) sleep 3;; C) sleep 30; exit 1;; esac\n'
           '  printf "%s-end\\\\n" "\\$UAK_TEST_LABEL" >> "\\$UAK_TEST_ORDER";;\n'
           'esac\n'
           'exec "$real" "\\$@"\n'
           'EOF\n'
           'chmod +x "$1/git"', "_", d.as_posix()], cwd=r.scratch)
    return d


def wait_for(path, text, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and text in path.read_text(encoding="utf-8").split():
            return
        time.sleep(0.1)
    raise AssertionError("%s never logged %s: %r" % (path.name, text, path.read_text(encoding="utf-8") if path.exists() else ""))


def reuses_the_claims_repo_between_calls(r):
    f = r.fixture("repo-reuse", count=3, shared_repo=True)
    f.claim(0, "HACK-001")   # the first claim starts the claims branch (a temporary clone: there is nothing to fetch)
    uak(r, f, 0, ["status"])
    repo = common(f) / "uak-claims"
    expect((repo / ".git" / "HEAD").is_file(), "expected: the claims repo in %s after a call, got: %s" % (
        repo, sorted(p.name for p in common(f).iterdir())))
    (repo / ".git" / "uak-test-sentinel").write_text("kept\n", encoding="utf-8")
    # What a call that died mid-way leaves behind: a stray ref and an untracked claim file. Neither may survive.
    r.g(repo, "update-ref", "refs/uak/base", "HEAD")
    (repo / "claims").mkdir(exist_ok=True)
    (repo / "claims" / "HACK-004.md").write_text("# garbage from a crashed call\nState: CLAIMED\n", encoding="utf-8")
    out = uak(r, f, 1, claim_args(f, 1, "HACK-002"), bash_flags=("-x",))
    trace = out.stderr
    expect("uak-claims" in trace, "expected: the second call works in the claims repo, got no uak-claims in its trace")
    inits = re.findall(r"(?m)^\++ ?\S*git(?:\.exe)? .*\binit\b.*$", trace)
    expect(not inits, "expected: no git init on the second call, got: %s" % inits[:3])
    # A write has a value (remote_setup's `config user.name` read of the checkout has none).
    configs = re.findall(r"(?m)^\++ ?\S*git(?:\.exe)? .*\b(?:config user\.name \S|remote add\b).*$", trace)
    expect(not configs, "expected: the config set once, got on the second call: %s" % configs[:3])
    expect((repo / ".git" / "uak-test-sentinel").is_file(), "expected: the same repo reused, got a new one (sentinel gone)")
    files = f.files("claims/")
    expect("claims/HACK-002.md" in files, "expected: claims/HACK-002.md on the remote, got: %s" % files)
    expect("claims/HACK-004.md" not in files, "expected: no stray file from a crashed call on the remote, got: %s" % files)
    stray = r.g(repo, "for-each-ref", "--format=%(refname)", "refs/uak/base").stdout.strip()
    expect(not stray, "expected: refs from an earlier call gone after the fetch, got: %s" % stray)
    expect(not (common(f) / LOCK).exists(), "expected: the lock released when the call ends, got: %s still there" % LOCK)
    # A third call by another agent reads the state the second one wrote.
    status = uak(r, f, 2, ["status"]).stdout
    expect(re.search(r"HACK-002 .*CLAIMED", status) is not None, "expected: HACK-002 CLAIMED in status, got:\n" + status[-800:])
    return "second call: no init, no config, same repo"


def serializes_two_processes_on_one_machine(r):
    f = r.fixture("repo-lock", count=4, shared_repo=True)
    f.claim(0, "HACK-001")
    order = r.scratch / "repo-lock-order.log"
    shim = slow_git(r, "lock")
    results = {}

    def slow():
        results["A"] = uak(r, f, 0, ["heartbeat", "HACK-001"], allowed=None, shim=shim,
                           UAK_TEST_LABEL="A", UAK_TEST_ORDER=order.as_posix())
    a = threading.Thread(target=slow)
    a.start()
    wait_for(order, "A-begin")
    b = uak(r, f, 1, claim_args(f, 1, "HACK-002"), allowed=None, shim=shim, UAK_TEST_LABEL="B", UAK_TEST_ORDER=order.as_posix())
    a.join(120)
    logged = order.read_text(encoding="utf-8").split()
    expect(results["A"].returncode == 0, "expected: the first call succeeds, got: %s" % (results["A"].stdout + results["A"].stderr)[-600:])
    expect(b.returncode == 0, "expected: the second call succeeds, got: %s" % (b.stdout + b.stderr)[-600:])
    expect(logged.index("B-begin") > logged.index("A-end"),
           "expected: the second call fetches after the first one ends (one lock per machine), got: %s" % logged)
    expect(not FALLBACK.search(b.stdout + b.stderr), "expected: the waiting call keeps the claims repo, got: %s" % (b.stdout + b.stderr)[-400:])
    # Two more at the same instant: both claims land.
    barrier = threading.Barrier(2)

    def one(index, task):
        barrier.wait(timeout=20)
        return uak(r, f, index, claim_args(f, index, task), allowed=None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        raced = list(pool.map(one, [2, 3], ["HACK-003", "HACK-004"]))
    for out in raced:
        expect(out.returncode == 0, "expected: concurrent claims succeed, got: %s" % (out.stdout + out.stderr)[-600:])
    files = f.files("claims/")
    expect(all("claims/HACK-%03d.md" % i in files for i in range(1, 5)), "expected: 4 claims on the remote, got: %s" % files)
    # A holder that dies with the lock (kill -9, a closed terminal): the next call takes it over at once.
    env = r.env.copy()
    env.update(env_for(0, UAK_TEST_LABEL="C", UAK_TEST_ORDER=order.as_posix()))
    holder = subprocess.Popen(with_shim(r, shim, [r.bash, ".uak/bin/uak", "heartbeat", "HACK-001"]), cwd=str(f.worktrees[0]), env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=(os.name != "nt"))
    try:
        wait_for(order, "C-begin")
    finally:
        holder.kill()
        holder.wait(30)
    expect((common(f) / LOCK).exists(), "expected: the killed holder leaves its lock behind, got no %s" % LOCK)
    started = time.monotonic()
    d = uak(r, f, 1, ["heartbeat", "HACK-002"], allowed=None)
    took = time.monotonic() - started
    expect(d.returncode == 0, "expected: the call after a dead holder succeeds, got: %s" % (d.stdout + d.stderr)[-600:])
    expect(not FALLBACK.search(d.stdout + d.stderr), "expected: a dead holder's lock taken over, not a temporary clone, got: %s" % (d.stdout + d.stderr)[-400:])
    expect(took < 15, "expected: a dead holder's lock taken over at once, got: %.1f s" % took)
    expect(not (common(f) / LOCK).exists(), "expected: the lock released when the call ends, got: %s still there" % LOCK)
    return "second call waited for the first; dead holder taken over in %.1f s" % took


def falls_back_to_a_temp_clone_when_the_repo_is_corrupt(r):
    f = r.fixture("repo-corrupt", count=2, shared_repo=True)
    f.claim(0, "HACK-001")
    repo = common(f) / "uak-claims"
    expect((repo / ".git" / "HEAD").is_file(), "expected: the claims repo after a call, got none in %s" % common(f))
    head_before = r.g(f.clones[0], "symbolic-ref", "HEAD").stdout.strip()
    (repo / ".git" / "HEAD").write_text("garbage\n", encoding="utf-8")
    out = uak(r, f, 1, claim_args(f, 1, "HACK-002"), allowed=None)
    text = out.stdout + out.stderr
    expect(out.returncode == 0, "expected: a corrupt claims repo still lets the call succeed, got: %s" % text[-600:])
    expect(len(FALLBACK.findall(text)) == 1, "expected: one note about the temporary clone, got:\n%s" % text[-800:])
    expect("claims/HACK-002.md" in f.files("claims/"), "expected: the claim on the remote, got: %s" % f.files("claims/"))
    # The fallback never reaches the checkout's own repository (git walks up from a broken .git into the common dir).
    expect(r.g(f.clones[0], "symbolic-ref", "HEAD").stdout.strip() == head_before, "expected: the clone's HEAD untouched")
    leaked = r.g(f.clones[0], "rev-parse", "-q", "--verify", "refs/heads/claims", allowed=None).stdout.strip()
    expect(not leaked, "expected: no claims branch in the clone's own repository, got: %s" % leaked)
    again = uak(r, f, 1, ["heartbeat", "HACK-002"])
    expect(not FALLBACK.search(again.stdout + again.stderr), "expected: the note once, then a rebuilt repo, got: %s" % (again.stdout + again.stderr)[-400:])
    expect(r.g(repo, "symbolic-ref", "HEAD", allowed=None).returncode == 0, "expected: the claims repo rebuilt")
    # Locked (antivirus, OneDrive, a git killed mid-write): the same fallback, once.
    (repo / ".git" / "index.lock").write_text("", encoding="utf-8")
    locked = uak(r, f, 0, ["heartbeat", "HACK-001"], allowed=None)
    text = locked.stdout + locked.stderr
    expect(locked.returncode == 0, "expected: a locked claims repo still lets the call succeed, got: %s" % text[-600:])
    expect(len(FALLBACK.findall(text)) == 1, "expected: one note about the temporary clone, got:\n%s" % text[-800:])
    after = uak(r, f, 0, ["heartbeat", "HACK-001"])
    expect(not FALLBACK.search(after.stdout + after.stderr), "expected: the note once, got: %s" % (after.stdout + after.stderr)[-400:])
    expect(not (common(f) / LOCK).exists(), "expected: the lock released when the call ends, got: %s still there" % LOCK)
    return "corrupt and locked: temporary clone, said once, repo rebuilt"


def a_dead_holder_is_taken_over_by_one_process(r):
    """kit-r1 (UAK-002): a takeover by rename left a moment with no lock, and a third waiter ran beside the new holder
    in the same repo (a false "no active claim", an empty owner, git walking up into the checkout). Six calls at once
    on a lock whose holder is dead, several rounds: every call lands, and no lock directory is left behind."""
    n = 6
    f = r.fixture("repo-reap", paths={"HACK-%03d" % (i + 1): "src/f%d.txt" % i for i in range(n)}, count=n, shared_repo=True)
    for i in range(n):
        f.claim(i, "HACK-%03d" % (i + 1))
    lock = common(f) / LOCK
    for rnd in range(4):
        dead = r.run([r.bash, "-c", "echo $$"]).stdout.strip()   # a PID that no longer runs, as bash sees PIDs
        lock.mkdir(exist_ok=True)
        (lock / "owner").write_text(dead + "\n", encoding="utf-8")
        barrier = threading.Barrier(n)

        def one(i):
            barrier.wait(timeout=30)
            return uak(r, f, i, ["log", "HACK-%03d" % (i + 1), "marker-r%d-a%d" % (rnd, i)], allowed=None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(one, range(n)))
        for i, out in enumerate(results):
            expect(out.returncode == 0, "round %d, call %d: expected: it succeeds, got: %s" % (rnd, i, (out.stdout + out.stderr)[-500:]))
            log = f.show(f.worklog("HACK-%03d" % (i + 1)))
            expect("marker-r%d-a%d" % (rnd, i) in log, "round %d, call %d: expected: its line in the worklog, got it lost" % (rnd, i))
        left = sorted(p.name for p in common(f).iterdir() if p.name.startswith(LOCK))
        expect(not left, "round %d: expected: no lock directory left, got: %s" % (rnd, left))
    return "4 rounds of 6 calls on a dead holder's lock"


TESTS = [reuses_the_claims_repo_between_calls, serializes_two_processes_on_one_machine,
         falls_back_to_a_temp_clone_when_the_repo_is_corrupt, a_dead_holder_is_taken_over_by_one_process]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-claims-repo-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("CLAIMS_REPO_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
