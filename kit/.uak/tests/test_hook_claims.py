#!/usr/bin/env python3
"""UAK-007: the hooks that run on every turn read the claims state through what tick already keeps.
`hook stop` ran a full `uak inbox --peek` (a fresh clone of claims: 19 git calls, 3-5 s on Git Bash) at the end of every
turn, and `session-start` once more, although `tick` keeps the inbox (uak-inbox.txt) with the claims tip it was read
at (uak-claims.tip) and only reads it again when that tip moves. Now stop and session-start do the same: one
`git ls-remote` of claims, and the full read only when the tip moved or the copy is over 5 minutes old.
`tick` checked the plan pace (`pace --caps`) in the foreground every 5 minutes, about 40 processes the agent waited
for; it now runs in the background like the poll, and its note comes on a later tick.
Real Git, a local bare remote; the engine is wrapped so the test sees each full read."""
import argparse
import concurrent.futures
import json
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

STOP = json.dumps({"session_id": "hook-claims", "hook_event_name": "Stop", "stop_hook_active": False})


def hook(r, w, args, payload, env=None):
    stdin = r.scratch / ("hook-in-%d" % time.monotonic_ns())
    stdin.write_text(payload, encoding="utf-8")
    return r.run([r.bash, "-c", 'exec < "$1"; shift; exec "$@"', "_", stdin.as_posix(), r.bash] + args,
                 cwd=w, env=env or {}, allowed=None)


def wrap_engine(r, w, marker):
    """Each run of the worktree's .uak/bin/uak adds its arguments to marker, then runs the real engine."""
    b = w / ".uak" / "bin"
    (b / "uak").rename(b / "uak-real")
    (b / "uak").write_text('#!/usr/bin/env bash\nprintf \'%%s\\n\' "$*" >> "%s"\nexec bash "$(dirname "$0")/uak-real" "$@"\n'
                           % marker.as_posix(), encoding="utf-8")


def peeks(marker):
    return [l for l in (marker.read_text(encoding="utf-8").splitlines() if marker.exists() else []) if l.startswith("inbox --peek")]


def stop_reads_the_inbox_from_the_cache(r):
    f = r.fixture("hook-stop", count=2)
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    marker = r.scratch / "hook-stop-engine.log"
    wrap_engine(r, w, marker)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    # stop also publishes this machine's token spend to claims every 30 min, in the background: a commit that moves
    # the tip (and rightly costs a read). Published just now, so only the messages below move it.
    common = Path(r.g(w, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    (common / "uak-tokens.published").write_text("%d\n" % int(time.time()), encoding="utf-8")
    f.hack(1, "msg", "HACK-001", "src/one.txt · one line · the spec", "--kind", "request", now=int(time.time()))
    # Cold: nothing kept yet, so the full read; the message blocks the stop.
    out = hook(r, w, [".uak/bin/hook", "stop"], STOP)
    expect(out.returncode == 0 and '"decision":"block"' in out.stdout and "#1 " in out.stdout,
           "the first stop must read the inbox and block on #1: rc %d %r" % (out.returncode, out.stdout[-400:]))
    expect(len(peeks(marker)) == 1, "the first stop reads the inbox once: %s" % peeks(marker))
    # Warm: the claims tip has not moved and the copy is fresh: no full read (the same batch does not block twice).
    for _ in range(2):
        out = hook(r, w, [".uak/bin/hook", "stop"], STOP)
        expect(out.returncode == 0 and out.stdout == "", "a stop on the same batch: rc %d %r" % (out.returncode, out.stdout[-300:]))
    expect(len(peeks(marker)) == 1, "stops with the claims tip unchanged must not read the inbox again: %s" % peeks(marker))
    # The tip moves (a new message): the next stop reads it and blocks on #2.
    f.hack(1, "msg", "HACK-001", "src/one.txt · and a second · the spec", "--kind", "request", now=int(time.time()))
    out = hook(r, w, [".uak/bin/hook", "stop"], STOP)
    expect('"decision":"block"' in out.stdout and "#2 " in out.stdout, "a new message must block the stop: %r" % out.stdout[-400:])
    expect(len(peeks(marker)) == 2, "a moved claims tip means one more read: %s" % peeks(marker))
    # A copy over 5 minutes old is read again even when the tip is the same.
    old = time.time() - 600
    for name in ("uak-inbox.txt", "uak-claims.tip"):
        if (gd / name).exists():
            os.utime(str(gd / name), (old, old))
    hook(r, w, [".uak/bin/hook", "stop"], STOP)
    expect(len(peeks(marker)) == 3, "a stale copy is read again: %s" % peeks(marker))
    # session-start reads through the same copy. Its own `uak next` may commit a tick to claims first (the tip moves:
    # one read); a second session start with nothing new on claims reads nothing.
    start = json.dumps({"session_id": "hook-claims-2", "hook_event_name": "SessionStart"})
    hook(r, w, [".uak/bin/hook", "session-start"], start)
    before = len(peeks(marker))
    tip = r.g(f.remote, "rev-parse", "claims").stdout.strip()
    out = hook(r, w, [".uak/bin/hook", "session-start"], start)
    expect(r.g(f.remote, "rev-parse", "claims").stdout.strip() == tip, "the second session start committed to claims")
    expect(len(peeks(marker)) == before, "session-start with a fresh copy must not read the inbox again: %s" % peeks(marker))
    expect("#2 " in out.stdout, "session-start still shows the inbox from the kept copy: %r" % out.stdout[-500:])
    return "%d full reads for 6 stops and a session start" % len(peeks(marker))


def tick_runs_pace_in_the_background(r):
    f = r.fixture("hook-pace", count=1)
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    tick = json.dumps({"session_id": "hook-pace", "tool_name": "Bash", "tool_input": {"command": "ls"},
                       "tool_response": {"stdout": "", "stderr": "", "interrupted": False}})
    env = {"UAK_POLL_SECONDS": "100000"}
    # The warm-up tick does its beat and drift; its pace check is marked done so no real pace runs in the background
    # while the fake one below is put in place (on Windows a slow one ran the fake and set the level first).
    # write_bytes: Windows' write_text writes CRLF, and a seen file reading "1794…\r" is no epoch to the hook, which
    # then goes by its mtime (just written: fresh), so the check never ran (Windows CI on e570732 and 5095ed5).
    (gd / "uak-pace.seen").write_bytes(b"%d\n" % int(time.time()))
    hook(r, w, [".uak/bin/hook", "tick"], tick, env)
    # A pace that takes 8 s and moves from steady to surge; the last check is made 10 minutes old.
    log = r.scratch / "hook-pace-calls.log"
    (w / ".uak" / "bin" / "pace").write_bytes((
        '#!/usr/bin/env bash\nprintf \'%%s\\n\' "${1:-note}" >> "%s"\n'
        'if [ "${1:-}" = --caps ]; then sleep 8; echo "surge 4 2"; else echo "PACE-NOTE surge: spend more"; fi\n'
        % log.as_posix()).encode("utf-8"))
    (gd / "uak-pace.level").write_bytes(b"steady")
    (gd / "uak-pace.seen").write_bytes(b"%d\n" % (int(time.time()) - 600))
    started = time.monotonic()
    out = hook(r, w, [".uak/bin/hook", "tick"], tick, env)
    took = time.monotonic() - started
    expect(out.returncode == 0 and took < 6, "tick must not wait for pace --caps: rc %d in %.1f s" % (out.returncode, took))
    expect("PACE-NOTE" not in out.stdout, "the note comes from the background check, on a later tick: %r" % out.stdout)
    deadline = time.monotonic() + 40
    note = ""
    while time.monotonic() < deadline and "PACE-NOTE" not in note:
        time.sleep(2)
        note = hook(r, w, [".uak/bin/hook", "tick"], tick, env).stdout
    state = {n: ((gd / n).read_text(encoding="utf-8", errors="replace")[:80] if (gd / n).exists() else None)
             for n in ("uak-pace.level", "uak-pace.note", "uak-pace.seen", "uak-inbox.txt")}
    calls = log.read_text(encoding="utf-8").split() if log.exists() else []
    expect("PACE-NOTE" in note, "a later tick must carry the pace note: %r; pace calls %s; state %s" % (note[-300:], calls, state))
    again = hook(r, w, [".uak/bin/hook", "tick"], tick, env).stdout
    expect("PACE-NOTE" not in again, "the note is said once: %r" % again[-300:])
    return "tick %.1f s with an 8 s pace" % took


def fresh_reads_a_crlf_epoch(r):
    """A state file whose epoch ends in \r (written with CRLF) is that epoch, not "no epoch, go by mtime": a seen file
    from 10 minutes ago, just written with CRLF, read as fresh and the pace check never ran (UAK-021)."""
    f = r.fixture("hook-crlf", count=1)
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    tick = json.dumps({"session_id": "hook-crlf", "tool_name": "Bash", "tool_input": {"command": "ls"},
                       "tool_response": {"stdout": "", "stderr": "", "interrupted": False}})
    env = {"UAK_POLL_SECONDS": "100000"}
    (gd / "uak-pace.seen").write_bytes(b"%d\n" % int(time.time()))
    hook(r, w, [".uak/bin/hook", "tick"], tick, env)
    log = r.scratch / "hook-crlf-calls.log"
    (w / ".uak" / "bin" / "pace").write_bytes(('#!/usr/bin/env bash\nprintf \'%%s\\n\' "${1:-note}" >> "%s"\necho "steady 4 2"\n'
                                               % log.as_posix()).encode("utf-8"))
    (gd / "uak-pace.seen").write_bytes(b"%d\r\n" % (int(time.time()) - 600))
    hook(r, w, [".uak/bin/hook", "tick"], tick, env)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not log.exists():
        time.sleep(1)
    expect(log.exists() and "--caps" in log.read_text(encoding="utf-8"),
           "a seen file of 10 minutes ago, written with CRLF, must let the pace check run")
    return "pace checked"


TESTS = [stop_reads_the_inbox_from_the_cache, tick_runs_pace_in_the_background, fresh_reads_a_crlf_epoch]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-hook-claims-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("HOOK_CLAIMS_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
