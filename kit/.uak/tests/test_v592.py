#!/usr/bin/env python3
"""uak v5.9.2: the hooks on the hot path start almost no processes. On Git Bash (Windows) a process costs 20-50 ms,
and Claude Code runs guard bash before every command and hook tick + hook output after it: 35 + 83 + 22 processes,
about 3.5 s per command on a teammate's laptop (Nov 2026). A 300-line heredoc took guard 35 s, past the 5 s hook
timeout, which lets the command run. Processes are counted as distinct PIDs in an xtrace (PS4 prints $BASHPID,
children inherit SHELLOPTS) with a traced shim in front of each program. Real Git, local bare remote."""
import argparse
import concurrent.futures
import json
import re
import shutil
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

PROGRAMS = ("git sed awk grep tr head tail cat date find touch mv rm mkdir cut sort wc dirname basename cksum od "
            "uname cygpath ls nohup sleep base64 timeout tee xargs uniq stat readlink")


def shims(r):
    d = r.scratch / "v592-shims"
    if not d.exists():
        d.mkdir()
        r.run([r.bash, "-c", 'for p in ' + PROGRAMS + '; do real=$(type -P "$p") || continue; '
               'printf "#!/usr/bin/env bash\\n: shim\\nexec \\"%s\\" \\"\\$@\\"\\n" "$real" > "$1/$p"; chmod +x "$1/$p"; done',
               "_", d.as_posix()], cwd=r.scratch)
    return d


def call(r, cwd, args, payload, env=None):
    """One hook call with the payload on stdin."""
    stdin = r.scratch / ("v592-in-%d" % time.monotonic_ns())
    stdin.write_text(payload, encoding="utf-8")
    return r.run([r.bash, "-c", 'exec < "$1"; shift; exec "$@"', "_", stdin.as_posix(), r.bash] + args,
                 cwd=cwd, env=env or {}, allowed=None)


def bash_major(r):
    out = r.run(["bash", "-c", "echo ${BASH_VERSINFO[0]}"], cwd=r.scratch, allowed=None).stdout.strip()
    return int(out) if out.isdigit() else 0


def processes(r, cwd, args, payload, env=None):
    """Distinct processes of one hook call (the hook's own bash included). Bash 3.2 (macOS) has no $BASHPID to tell
    them apart: there the call runs and counts as 0, and the counts are checked on Linux and Windows."""
    if bash_major(r) < 4:
        return 0, call(r, cwd, args, payload, env)
    trace = r.scratch / ("v592-trace-%d" % time.monotonic_ns())
    stdin = r.scratch / ("v592-in-%d" % time.monotonic_ns())
    stdin.write_text(payload, encoding="utf-8")
    script = ('exec 9>>"$1" < "$3"; PATH="$2:$PATH"; export PATH; shift 3; '
              "exec env BASH_XTRACEFD=9 'PS4=+$BASHPID ' SHELLOPTS=xtrace \"$@\"")
    # The hook runs as `bash` from PATH: Git for Windows' bin\bash.exe is a launcher that starts a new native process,
    # and fd 9 does not reach it.
    out = r.run([r.bash, "-c", script, "_", trace.as_posix(), shims(r).as_posix(), stdin.as_posix(), "bash"] + args,
                cwd=cwd, env=env or {}, allowed=None)
    pids = set(re.findall(r"(?m)^\++([0-9]+) ", trace.read_text(encoding="utf-8", errors="replace")))
    expect(pids, "the trace counted nothing: " + out.stderr[-300:])
    return len(pids), out


def bash_payload(cmd):
    return json.dumps({"session_id": "v592", "tool_name": "Bash", "tool_input": {"command": cmd}})


def guard_runs_on_builtins(r):
    """guard bash: 35 processes for `ls`, 81 for a git commit; guard prompt: 27 for any message."""
    f = r.fixture("v592-guard", count=1)
    w = f.worktrees[0]
    n, out = processes(r, w, [".uak/bin/guard", "bash", "claude"], bash_payload("ls -la src"))
    expect(out.returncode == 0 and n <= 2, "guard bash ls: %d processes" % n)
    n, out = processes(r, w, [".uak/bin/guard", "bash", "claude"], bash_payload('git add a.txt && git commit -m "fix: the parser keeps the last line"'))
    expect(out.returncode == 0 and n <= 6, "guard bash git commit: %d processes" % n)
    n, out = processes(r, w, [".uak/bin/guard", "bash", "claude"], bash_payload("cd x && git push --force"))
    expect(out.returncode == 2 and "forced push" in out.stderr, "still blocked: " + out.stderr)
    n, out = processes(r, w, [".uak/bin/guard", "prompt"], json.dumps({"session_id": "v592", "prompt": "please fix the parser so it keeps the last line"}))
    expect(out.returncode == 0 and n <= 2, "guard prompt: %d processes" % n)
    return {"guard": "builtins"}


def a_long_heredoc_is_read_in_time(r):
    """A 300-line heredoc: json_field added one character at a time (35 s on Windows); the hook timeout is 5 s."""
    f = r.fixture("v592-heredoc", count=1)
    body = "\n".join('    value_%d = compute("x", %d)  # a "quoted" comment \\ and more' % (i, i) for i in range(300))
    started = time.monotonic()
    out = call(r, f.worktrees[0], [".uak/bin/guard", "bash", "claude"], bash_payload("cat > src/big.py <<'PY'\n" + body + "\nPY"))
    took = time.monotonic() - started
    if out.returncode == 0 and took >= 5:
        # A slow runner, once (5.2 s on Windows CI for a commit that did not touch guard): measured again, and only a
        # second time over the limit is the bug this guards against (UAK-021).
        started = time.monotonic()
        out = call(r, f.worktrees[0], [".uak/bin/guard", "bash", "claude"], bash_payload("cat > src/big.py <<'PY'\n" + body + "\nPY"))
        took = time.monotonic() - started
    expect(out.returncode == 0 and took < 5, "a 300-line heredoc: rc %d in %.1f s" % (out.returncode, took))
    out = call(r, f.worktrees[0], [".uak/bin/guard", "bash", "claude"], bash_payload("cat > src/big.py <<'PY'\n" + body + "\nPY\ngit push -f"))
    expect(out.returncode == 2, "a push -f after the heredoc is still blocked")
    return {"seconds": round(took, 1)}


def tick_and_output_run_on_builtins(r):
    """hook tick (after every tool call): 83 processes on its common path; hook output: 22 for a small output."""
    f = r.fixture("v592-tick", count=1)
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    tick = json.dumps({"session_id": "v592", "tool_name": "Bash", "tool_input": {"command": "ls -la src"},
                       "tool_response": {"stdout": "a.txt", "stderr": "", "interrupted": False}})
    env = {"UAK_POLL_SECONDS": "100000"}
    call(r, w, [".uak/bin/hook", "tick"], tick, env)  # beat, drift, pace: now fresh
    n, out = processes(r, w, [".uak/bin/hook", "tick"], tick, env)
    expect(out.returncode == 0 and n <= 4, "hook tick: %d processes" % n)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    expect((gd / "uak-live").read_text(encoding="utf-8").startswith("v592 "), "the session is still recorded")
    n, out = processes(r, w, [".uak/bin/hook", "output"], tick)
    expect(out.returncode == 0 and out.stdout == "" and n <= 4, "hook output: %d processes" % n)
    return {"tick": n}


def tick_stays_fast_on_a_long_payload(r):
    """The builtin readers copied the rest of the payload at each escape: an 800-line heredoc took tick 10 s on Linux
    and 40 KB of output 1.3 s (0.2 s for the sed and awk they replaced). Both under 64 KB, where awk took over."""
    f = r.fixture("v592-long", count=1)
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    env = {"UAK_POLL_SECONDS": "100000"}
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    heredoc = "cat > src/big.py <<'PY'\n" + "\n".join('row %d "x" \\ y' % i for i in range(800)) + "\nPY"
    payloads = {"heredoc": {"session_id": "v592-a", "tool_name": "Bash", "tool_input": {"command": heredoc},
                            "tool_response": {"stdout": "", "stderr": ""}},
                "output": {"session_id": "v592-b", "tool_name": "Bash", "tool_input": {"command": "pytest -q"},
                           "tool_response": {"stdout": 'x "y" \\\n' * 4000, "stderr": ""}}}
    call(r, w, [".uak/bin/hook", "tick"], json.dumps(payloads["output"]), env)  # beat, drift, pace: now fresh
    took = {}
    for name, p in payloads.items():
        text = json.dumps(p)
        expect(len(text) < 65536, "under 64 KB: %d" % len(text))
        started = time.monotonic()
        out = call(r, w, [".uak/bin/hook", "tick"], text, env)
        took[name] = round(time.monotonic() - started, 2)
        expect(out.returncode == 0 and took[name] < 3, "tick on the %s (%d KB): rc %d in %.1f s" % (name, len(text) // 1024, out.returncode, took[name]))
        expect((gd / "uak-live").read_text(encoding="utf-8").startswith(p["session_id"] + " "), "the session id of the " + name)
    # A key past the first 4 KB is read by sed, as before.
    late = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {"stdout": "x" * 9000},
                       "session_id": "v592-late"})
    call(r, w, [".uak/bin/hook", "tick"], late, env)
    expect((gd / "uak-live").read_text(encoding="utf-8").startswith("v592-late "), "a session id after the output")
    return took


TESTS = [guard_runs_on_builtins, a_long_heredoc_is_read_in_time, tick_and_output_run_on_builtins,
         tick_stays_fast_on_a_long_payload]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    # Not TemporaryDirectory: on Windows the beat and the drift fetch that tick starts in the background can still hold
    # the worktree when the run ends, and the cleanup error hid the results.
    tmp = tempfile.mkdtemp(prefix="uak-v592-")
    try:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        shims(runner)
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("V592_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
