#!/usr/bin/env python3
"""UAK-113: the merge lock's background renewer exits when its merge process is gone. The EXIT trap does not run on
SIGKILL (a harness timeout, the OOM killer), and the orphaned renewer kept renewing merge-lock.md, so the queue stayed
locked (audit of v6.5.0, docs/audit-2026-11.md #6). Real Git, a local bare remote, a real kill of the merge."""
import argparse
import subprocess
import tempfile
import time
import os
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_review_merge import fixture, actor, publish


def slow_fixture(r, name, gate_seconds, lease):
    """A fixture whose product gate sleeps GATE_SECONDS and whose merge lock lease is LEASE seconds (the renewer
    renews every max(5, LEASE / 3) seconds)."""
    f = fixture(r, name, count=1)
    project = f.seed / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8").replace("Merge-Lease-Seconds: 1800", "Merge-Lease-Seconds: %d" % lease).replace("Freeze-Epoch: 9999999", "Freeze-Epoch: 99999999999"), encoding="utf-8")
    (f.seed / ".uak/bin/smoke-project").write_text(
        "#!/usr/bin/env bash\nset -eu\n[ ! -f .red-product-gate ]\nsleep %d\n" % gate_seconds, encoding="utf-8")
    r.g(f.seed, "add", ".uak/PROJECT.md", ".uak/bin/smoke-project")
    r.g(f.seed, "commit", "-m", "Slow product gate and a short merge lease")
    r.g(f.seed, "push", "origin", "main")
    for clone, worktree in zip(f.clones, f.worktrees):
        r.g(clone, "fetch", "origin", "main")
        r.g(worktree, "reset", "--hard", "origin/main")
    return f


def approved(r, f, task="HACK-001"):
    """The task approved by `judge`, with real timestamps (the merge runs on the real clock, the renewer needs it)."""
    now = int(time.time())
    f.claim(0, task, now=now)
    tip = publish(f, 0, task)
    f.hack(0, "done", task, "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance", now=now + 1)
    actor(f, "human-registrar", "register-reviewer", "judge", now=now + 2, human=True)
    actor(f, "judge", "review", task, "--sha", tip, "--verdict", "approve", now=now + 3)
    return tip


def lock_field(f, key):
    for path in f.files("queue"):
        if path.endswith("merge-lock.md"):
            for line in f.show(path).splitlines():
                if line.startswith(key + ":"):
                    return line.split(":", 1)[1].strip()
    return ""


def start_merge(r, f, task="HACK-001"):
    env = r.env.copy()
    env.update({"UAK_AGENT": "agent-1", "UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_REVIEW_MODE": "claims"})
    env.pop("UAK_NOW", None)
    out, err = tempfile.TemporaryFile(), tempfile.TemporaryFile()
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    # The merge writes its own pid first and then execs into uak, so that pid is the process the renewer watches
    # ($$ of the uak script). On Windows Python's Popen pid is Git for Windows' bin\bash.exe launcher, a different
    # process from the MSYS bash that runs the merge: killing the launcher leaves the merge (and its renewer) alive.
    pidfile = f.base / "merge.pid"
    script = 'echo $$ > "$1"; shift; exec bash .uak/bin/uak "$@"'
    proc = subprocess.Popen([r.bash, "-c", script, "_", pidfile.as_posix(), "merge", task], cwd=f.worktrees[0], env=env,
                            stdout=out, stderr=err, **kw)
    proc.pidfile = pidfile
    return proc, out, err


def real_pid(proc):
    got = wait_for(lambda: proc.pidfile.read_text(encoding="utf-8").strip() if proc.pidfile.exists() else "", 30)
    expect(got, "the merge wrote its pid")
    return got


def kill_from_bash(r, f, pid):
    """SIGKILL the merge through bash, which knows MSYS pids (Python's pids differ on Windows)."""
    return r.run([r.bash, "-c", 'kill -9 "$1"', "_", pid], cwd=f.worktrees[0], allowed=None)


def ps_text(r, f):
    out = r.run([r.bash, "-c", "ps 2>&1 || ps -ef 2>&1"], cwd=f.worktrees[0], allowed=None)
    return (out.stdout + out.stderr)[-1500:]


def wait_for(check, seconds, step=0.5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(step)
    return None


def renewer_exits_after_parent_is_killed(r):
    f = slow_fixture(r, "orphan-kill", gate_seconds=40, lease=15)
    approved(r, f)
    proc, out, err = start_merge(r, f)
    try:
        first = wait_for(lambda: lock_field(f, "Updated"), 60)
        expect(first, "the merge took the lock")
        renewed = wait_for(lambda: lock_field(f, "Updated") not in ("", first) and lock_field(f, "Updated"), 40)
        expect(renewed, "a running merge renews its lock (Updated stayed %s)" % first)
        pid = real_pid(proc)
        killed = kill_from_bash(r, f, pid)  # SIGKILL: no trap runs
        proc.wait(timeout=20)
        time.sleep(2)  # a renewal already in flight may still land
        settled = lock_field(f, "Updated")
        time.sleep(13)  # more than two renewal intervals (5 s each) while the lock lease (15 s) is still valid
        after = lock_field(f, "Updated")
        expect(after == settled, "the orphaned renewer kept renewing: Updated %s -> %s; watched/killed merge pid %s (kill rc %s %s); ps:\n%s"
               % (settled, after, pid, killed.returncode, (killed.stdout + killed.stderr).strip(), ps_text(r, f)))
    finally:
        if proc.poll() is None:
            proc.kill()
        out.close(); err.close()
    return "exited"


def normal_merge_releases_the_lock(r):
    f = slow_fixture(r, "orphan-normal", gate_seconds=8, lease=15)
    approved(r, f)
    proc, out, err = start_merge(r, f)
    try:
        code = proc.wait(timeout=180)
        out.seek(0)
        text = out.read().decode("utf-8", "replace")
    finally:
        out.close(); err.close()
    expect(code == 0 and "INTEGRATED" in text, "the merge finishes: rc %s %s" % (code, text[-500:]))
    expect(not [p for p in f.files("queue") if p.endswith("merge-lock.md")], "the lock is released")
    return "released"


TESTS = [renewer_exits_after_parent_is_killed, normal_merge_releases_the_lock]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-renewer-orphan-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("MERGE_RENEWER_ORPHAN_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
