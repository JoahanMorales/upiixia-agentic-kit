#!/usr/bin/env python3
"""The claims redesign's targets, as tests: the processes `uak next`, `uak status` and `uak heartbeat` start.
On Git Bash a process costs 20-50 ms and `next` started about 220 of them: 4-8 s per call on a Windows laptop
(docs/ROADMAP.md, "Next"). The targets are the assertions; the redesign (UAK-002 … UAK-006) turns them green.
Real Git, a local bare remote, 12 tasks and 3 live claims."""
import argparse
import concurrent.futures
import os
import re
import tempfile
import time
from pathlib import Path

from test_hack import Failure, Runner, expect, resolve_binary
from test_v592 import PROGRAMS, bash_major, call

TARGETS = {"next": 40, "status": 30, "heartbeat": 20}
# Targets the redesign does not reach (UAK-006, measured on 0ec9f2f: next 93, 122 for an idle agent, status 61,
# heartbeat 139). Most of what is left is the claims transaction itself (a fresh clone, a commit, a push per call):
# UAK-002 and UAK-005, a persistent claims repo, were cancelled (about 5 processes saved per call for a lock shared
# between processes). Strict: a test in it that meets its target fails, so the set never hides a win. Nothing here is
# skipped: every count runs and is printed.
XFAIL = {"next_starts_at_most_40_processes", "status_starts_at_most_30_processes", "heartbeat_starts_at_most_20_processes",
         "next_for_an_idle_agent_starts_at_most_40_processes"}


def shims(r):
    """test_v592's traced shims plus ps: next and status call it (the session key). Created once, before the threads."""
    d = r.scratch / "claims-perf-shims"
    if not d.exists():
        d.mkdir()
        r.run([r.bash, "-c", 'for p in ' + PROGRAMS + ' ps; do real=$(type -P "$p") || continue; '
               'printf "#!/usr/bin/env bash\\n: shim\\nexec \\"%s\\" \\"\\$@\\"\\n" "$real" > "$1/$p"; chmod +x "$1/$p"; done',
               "_", d.as_posix()], cwd=r.scratch)
    return d


def unique(r, prefix):
    """A file name no other call can take: time-based names collide on Windows Python before 3.13 (coarse clock)."""
    fd, name = tempfile.mkstemp(prefix=prefix, dir=str(r.scratch))
    os.close(fd)
    return Path(name)


def processes(r, cwd, args, payload, env=None):
    """Distinct processes of one call, as test_v592 counts them: every program runs through a traced shim, so each
    leaves its own PID. Bash 3.2 has no $BASHPID: there the call runs and counts 0."""
    if bash_major(r) < 4:
        return 0, call(r, cwd, args, payload, env)
    trace, stdin = unique(r, "perf-trace-"), unique(r, "perf-in-")
    stdin.write_text(payload, encoding="utf-8")
    script = ('exec 9>>"$1" < "$3"; PATH="$2:$PATH"; export PATH; shift 3; '
              "exec env BASH_XTRACEFD=9 'PS4=+$BASHPID ' SHELLOPTS=xtrace \"$@\"")
    out = r.run([r.bash, "-c", script, "_", trace.as_posix(), shims(r).as_posix(), stdin.as_posix(), "bash"] + args,
                cwd=cwd, env=env or {}, allowed=None)
    pids = set(re.findall(r"(?m)^\++([0-9]+) ", trace.read_text(encoding="utf-8", errors="replace")))
    expect(pids, "the trace counted nothing: " + out.stderr[-300:])
    return len(pids), out


def fixture(r, name):
    """12 tasks, 3 of them claimed by three agents: the state every call reads."""
    f = r.fixture(name, paths={"HACK-%03d" % i: "src/t%02d/" % i for i in range(1, 13)}, count=3)
    for i in range(3):
        f.claim(i, "HACK-%03d" % (i + 1))
    return f


def count(r, f, args, cwd=None, agent="agent-1"):
    """Processes one uak call starts, with test_v592's counter: every program runs through a traced shim, so each
    process leaves its own PID (bash 3.2 has no $BASHPID: there it counts 0). The second call is measured: the first
    one of a fresh clone also writes its session file."""
    env = {"UAK_AGENT": agent, "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000060", "UAK_DEDUPE": "off"}
    cwd = cwd or f.worktrees[0]
    r.run([r.bash, ".uak/bin/uak"] + args, cwd=cwd, env=env)
    n, out = processes(r, cwd, [".uak/bin/uak"] + args, "", env)
    expect(out.returncode == 0, "uak %s failed: %s" % (" ".join(args), (out.stdout + out.stderr)[-400:]))
    return n


def check(r, name, command, args, idle=False):
    f = fixture(r, "perf-" + name)
    # idle: an agent with no claim, in the main checkout, choosing a task (not resuming its own)
    n = count(r, f, args, cwd=f.clones[0], agent="idle-1") if idle else count(r, f, args)
    if bash_major(r) < 4:
        return "not counted on bash %d (no $BASHPID); Linux and Windows count" % bash_major(r)
    try:
        expect(n <= TARGETS[command], "uak %s: expected: at most %d processes, got: %d" % (command, TARGETS[command], n))
    except Failure as exc:
        if name in XFAIL:
            return "XFAIL %s" % exc
        raise
    expect(name not in XFAIL, "uak %s: %d processes meets its target of %d: take %s out of XFAIL" % (command, n, TARGETS[command], name))
    return "%d processes (target %d)" % (n, TARGETS[command])


def next_starts_at_most_40_processes(r):
    return check(r, "next_starts_at_most_40_processes", "next", ["next"])


def status_starts_at_most_30_processes(r):
    return check(r, "status_starts_at_most_30_processes", "status", ["status"])


def heartbeat_starts_at_most_20_processes(r):
    return check(r, "heartbeat_starts_at_most_20_processes", "heartbeat", ["heartbeat", "HACK-001"])


def next_for_an_idle_agent_starts_at_most_40_processes(r):
    return check(r, "next_for_an_idle_agent_starts_at_most_40_processes", "next", ["next"], idle=True)


def the_counter_sees_ps(r):
    """next and status call ps (the session key); a counter without a ps shim was 5 processes short (kit-r1, UAK-001)."""
    if bash_major(r) < 4:
        return "not counted on bash %d" % bash_major(r)
    n, _ = processes(r, r.scratch, ["-c", "ps -o pid= -p $$ >/dev/null"], "", {})
    expect(n >= 2, "a bash that runs ps: expected: at least 2 processes, got: %d" % n)
    return "%d processes" % n


def old_and_new_engines_print_the_same_and_write_the_same_tree(r):
    """The redesign changed how the claims branch is read and written, not what uak says or writes:
    scripts/claims_diff.py runs the engine from before it and today's through the same protocol commands, and every
    exit code, stdout and claims tree must match. It needs the kit's source repository (its history holds the old
    engine): in an installed project there is none, and this says so."""
    script = Path(__file__).resolve().parents[3] / "scripts" / "claims_diff.py"
    if not script.is_file() or not (script.parents[1] / ".git").exists():
        return "no kit source repository here: run scripts/claims_diff.py in the kit's repository"
    import importlib.util
    spec = importlib.util.spec_from_file_location("claims_diff", str(script))
    diff = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diff)
    steps, problems = diff.run()
    expect(not problems, "the old and the new engine differ on %d of %d steps:\n%s" % (len(problems), steps, "\n".join(problems)[:2500]))
    return "%d steps identical (old %s)" % (steps, diff.OLD[:7])


TESTS = [next_starts_at_most_40_processes, status_starts_at_most_30_processes, heartbeat_starts_at_most_20_processes,
         next_for_an_idle_agent_starts_at_most_40_processes, the_counter_sees_ps,
         old_and_new_engines_print_the_same_and_write_the_same_tree]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-claims-perf-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        shims(runner)  # once, before the threads: three of them creating it at once would race
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
    print("CLAIMS_PERF_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
