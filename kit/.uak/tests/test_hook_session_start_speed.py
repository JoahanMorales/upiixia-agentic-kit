#!/usr/bin/env python3
"""UAK-174: the session-start hook answers within 3 seconds. Claude Code's /doctor on Dylan's Mac (22 sessions over
18 days, 2026-11-11) measured the kit's SessionStart hook at about 9.5 s typical on startup, 12.6 s on resume and up
to 28 s: it waited for the network (`uak next --full`, the inbox read, `uak digest`) before every session could start.
A slow remote is simulated with remote.origin.uploadpack ('sleep N; git-upload-pack'), so no real network is used."""
import argparse
import json
import os
import re
import shutil
import time
from collections import Counter
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

BUDGET = 3.0
SLOW = 3


def start(r, cwd, agent=None, source="startup", **extra):
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": agent or ""}
    env.update(extra)
    payload = '{"session_id":"s-%s","source":"%s"}' % (source, source)
    began = time.monotonic()
    out = r.run([r.bash, "-c", "printf '%s' \"$1\" | bash .uak/bin/hook session-start", "_", payload],
                cwd=cwd, env=env, allowed=None)
    return time.monotonic() - began, out.stdout


def slow_remote(r, f, seconds=SLOW):
    for clone in set(f.clones):
        r.g(clone, "config", "remote.origin.uploadpack", "sleep %d; git-upload-pack" % seconds)


def fast_remote(r, f):
    for clone in set(f.clones):
        r.g(clone, "config", "--unset", "remote.origin.uploadpack", allowed=(0, 5))


def settle(r, cwd, seconds=40):
    """Wait, bounded, until no background refresh started by the hook is still running in this checkout."""
    gd = Path(r.g(cwd, "rev-parse", "--absolute-git-dir").stdout.strip())
    deadline = time.monotonic() + seconds
    while list(gd.glob("uak-start.*.running")):
        if time.monotonic() >= deadline:
            raise AssertionError("a background refresh never finished within %d s" % seconds)
        time.sleep(0.25)
    # No process works in the checkout any more (Windows refuses to rename a folder in use; the UAK-170 probe).
    probe = Path(str(cwd) + ".released")
    while True:
        try:
            os.rename(str(cwd), str(probe))
            os.rename(str(probe), str(cwd))
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise AssertionError("background processes still work in %s after %d s" % (cwd, seconds))
            time.sleep(0.25)


def session_start_returns_within_budget(r):
    f = r.fixture("ss-budget", count=1)
    f.claim(0, "HACK-001")
    slow_remote(r, f)
    w, main = f.worktrees[0], f.clones[0]
    for cwd, agent, what in ((w, "agent-1", "an agent's worktree"), (main, None, "the main checkout")):
        took, out = start(r, cwd, agent)
        expect(took < BUDGET, "session-start in %s took %.1f s with a slow remote (budget %.0f s): %s"
               % (what, took, BUDGET, out[-300:]))
        settle(r, cwd)
    took, _ = start(r, w, "agent-1", source="resume")
    expect(took < BUDGET, "resume took %.1f s (budget %.0f s)" % (took, BUDGET))
    settle(r, w)
    return "startup and resume under %.0f s with a %d s remote" % (BUDGET, SLOW)


def session_start_output_is_unchanged(r):
    f = r.fixture("ss-output", count=1)
    f.claim(0, "HACK-001")
    w = f.worktrees[0]
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1"}
    expected = r.run([r.bash, ".uak/bin/uak", "next", "--full"], cwd=w, env=env, allowed=None).stdout.splitlines()[:3]
    expect(expected, "uak next prints something for the fixture")
    # A first start shows the fresh lines when they arrive within the wait, or says where they are (slower machines,
    # Git Bash on Windows); the second start shows them either way, from the kept copy.
    _, out = start(r, w, "agent-1")
    settle(r, w)
    expect("UAK: agent=agent-1" in out, "the identity line is shown: " + out[:300])
    expect(all(line in out for line in expected) or "uak next" in out,
           "a first start shows the `uak next` lines or how to get them: " + out[:600])
    _, out = start(r, w, "agent-1")
    settle(r, w)
    for line in expected:
        expect(line in out, "a later start shows the `uak next` lines (%r) at once: %s" % (line, out[:600]))
    slow_remote(r, f)
    # A refresh that outlasts the wait (forced here with a 0.1 s wait) still shows the last lines, with a note.
    took, out = start(r, w, "agent-1", UAK_START_WAIT="1")
    expect(took < BUDGET, "a slow remote does not hold the session (%.1f s)" % took)
    for line in expected:
        expect(line in out, "a slow remote still shows the last `uak next` lines (%r): %s" % (line, out[:600]))
    expect("refreshing" in out, "the agent is told the list is being refreshed: " + out[:600])
    settle(r, w)
    fast_remote(r, f)
    return "identity, next and the refresh note"


def session_start_marks_only_the_inbox_snapshot_it_prints(r):
    """A refresh after the first inbox print must leave its unseen request for the next tick."""
    from test_hook_claims import hook

    f = r.fixture("ss-inbox-snapshot", count=2)
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")
    w = f.worktrees[0]
    (w / ".uak-env").write_bytes(b"UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    f.hack(1, "msg", "HACK-001", "first snapshot request", "--kind", "request", now=int(time.time()))
    first = f.hack(0, "inbox", "--peek", now=int(time.time())).stdout
    (gd / "uak-inbox.txt").write_bytes(first.encode("utf-8"))
    f.hack(1, "msg", "HACK-001", "second request must reach the next tick", "--kind", "request", now=int(time.time()))
    # The real inbox read waits until head has printed the old copy. Head then waits for that refresh to finish,
    # forcing the replacement between printing and recording shown-n without relying on runner speed.
    release = r.scratch / "ss-inbox-printed"
    b = w / ".uak/bin"
    (b / "uak").rename(b / "uak-real")
    (b / "uak").write_bytes(b'''#!/usr/bin/env bash
if [ "$1" = next ]; then printf 'Next: fixture task\\n'; exit 0; fi
if [ "$1" = inbox ]; then
  n=0
  while [ ! -e "$UAK_RACE_RELEASE" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
fi
exec bash "$(dirname "$0")/uak-real" "$@"
''')
    shim = r.scratch / "ss-inbox-shim"
    shim.mkdir()
    head = shim / "head"
    head.write_bytes(b'''#!/usr/bin/env bash
printed=$("$UAK_RACE_HEAD" "$@")
printf '%s\\n' "$printed"
case "$printed" in *'first snapshot request'*)
  if mkdir "$UAK_RACE_RELEASE" 2>/dev/null; then
    n=0
    while ! grep -q '^#2 ' "$UAK_RACE_INBOX" && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
  fi;;
esac
''')
    r.run([r.bash, "-c", 'chmod +x "$1"', "_", head.as_posix()], cwd=w)
    real_head = r.run([r.bash, "-c", "type -P head"], cwd=w).stdout.strip()
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1", "UAK_RACE_HEAD": real_head,
           "UAK_RACE_RELEASE": release.as_posix(), "UAK_RACE_INBOX": (gd / "uak-inbox.txt").as_posix(),
           "UAK_START_WAIT": "1"}
    # Build PATH in Bash from its physical POSIX directory: a native Windows drive/semicolon PATH must not hide the
    # extensionless shim. Prove selection before a background job waits on that shim's release barrier.
    prefix = 'shim_dir=$(CDPATH= cd -- "$1" && pwd -P) || exit 1; PATH="$shim_dir:$PATH"; export PATH; '
    setup = r.run([r.bash, "-c", prefix + 'printf "%s\\n" "$shim_dir/head"; command -v head; '
                   '[ -d "$(dirname "$UAK_RACE_RELEASE")" ]', "_", shim.as_posix()], cwd=w, env=env)
    paths = setup.stdout.splitlines()
    expect(len(paths) == 2 and paths[0] == paths[1], "the inbox race must select its head shim: %r" % paths)
    out = hook(r, w, ["-c", prefix + 'exec bash .uak/bin/hook session-start', "_", shim.as_posix()],
               json.dumps({"session_id": "s-resume", "source": "resume"}), env).stdout
    released = release.is_dir()
    if not released:
        release.mkdir()  # unblock cleanup before reporting a failed fault-injection precondition
    settle(r, w)
    expect(released, "the head shim must release the inbox refresh after printing: " + out[-500:])
    shown = (gd / "uak-inbox.shown-n").read_text(encoding="utf-8").strip()
    expect("#2 " in (gd / "uak-inbox.txt").read_text(encoding="utf-8"), "the real refresh loaded request #2")
    # Keep tick's unrelated network/pace jobs fresh so only the inbox delivery is exercised and Windows can clean up.
    for name in ("uak-inbox.poll", "uak-pace.seen", "uak-heartbeat", "uak-heartbeat.reviews"):
        (gd / name).write_bytes(b"%d\n" % int(time.time()))
    tick = hook(r, w, [".uak/bin/hook", "tick"], json.dumps({"session_id": "s-resume", "tool_name": "Bash",
                "tool_input": {"command": "true"}, "tool_response": {"stdout": "", "stderr": ""}}), env)
    observed = ("#1 " in out, "#2 " in out, shown, "#2 " in tick.stdout)
    expect(observed == (True, False, "1", True),
           "assertion failed: printed #1/#2, shown-n, next tick #2: %r" % (observed,))
    return "unseen refreshed request delivered on the next tick"


def refresh_fixture(r, name, body):
    """Run the actual refresh helpers in a real worktree, with barriers and waitable Bash child processes."""
    f = r.fixture("ss-owner-" + name, count=1)
    w = f.worktrees[0]
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    case_dir = r.scratch / ("ss-owner-control-" + name)
    case_dir.mkdir()
    (case_dir / "backend.sh").write_bytes(b'''#!/usr/bin/env bash
mode=$1 case_dir=$2 kind=$3
printf '%s\\n' "$mode" >> "$case_dir/backend-calls"
if [ "$mode" = OLD ]; then
  : > "$case_dir/old-ready"
  n=0
  while [ ! -f "$case_dir/release-old" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
fi
printf '%s: %s snapshot\\n' "$kind" "$mode"
[ "$mode" != OLD ] || : > "$case_dir/old-done"
''')
    source = (r.package / ".uak/bin/hook").read_text(encoding="utf-8")
    first = source.index("fresh() {")
    fresh = source[first:source.index("\n}\n", first) + 3]
    rd = next(line for line in source.splitlines() if line.startswith("rd() {"))
    first = source.index("# The inbox as tick keeps it:")
    helpers = source[first:source.index("# A small file's first line", first)]
    script = case_dir / "refresh.sh"
    script.write_bytes(('''set -u
gd=$1 case_dir=$2
NOW=$(date +%s)
NL='\n'
CR=$(printf '\\r')
''' + fresh + "\n" + rd + "\n" + helpers + '''
wait_file() {
  local n=0
  while [ ! -f "$1" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
  [ -f "$1" ] || { printf 'assertion failed: barrier missing: %s\\n' "$1" >&2; exit 1; }
}
age_refresh() {
  for marker in "$gd"/uak-start.next*.running; do
    [ -f "$marker" ] || continue
    { printf '%s\\n' "$((NOW - 121))"; sed '1d' "$marker"; } > "$case_dir/aged"
    cat "$case_dir/aged" > "$marker"
  done
}
trap 'for release in old new move claim backend handoff recovery; do : > "$case_dir/release-$release"; done; wait' EXIT
''' + body).encode("utf-8"))
    out = r.run([r.bash, script.as_posix(), gd.as_posix(), case_dir.as_posix()], cwd=w, allowed=None, timeout=180)
    expect(out.returncode == 0, "refresh harness: " + out.stdout[-1000:] + out.stderr[-1000:])
    # A killed owner's backend can outlive that owner briefly; Windows cannot remove its working directory yet.
    deadline = time.monotonic() + 40
    probe = Path(str(w) + ".released")
    while True:
        try:
            os.rename(str(w), str(probe))
            os.rename(str(probe), str(w))
            break
        except PermissionError:
            if time.monotonic() >= deadline:
                raise AssertionError("a refresh backend still holds its worktree after cleanup")
            time.sleep(0.25)
    return gd, case_dir


def session_start_coalesces_aged_live_refreshes(r):
    for order in ("new-first", "old-first"):
        gd, control = refresh_fixture(r, "live-" + order, '''
old_read() {
  printf 'OLD\\n' >> "$case_dir/calls"; : > "$case_dir/old-ready"
  wait_file "$case_dir/release-old"
  printf 'Next: OLD task\\n'
}
new_read() {
  printf 'NEW\\n' >> "$case_dir/calls"; : > "$case_dir/new-ready"
  wait_file "$case_dir/release-new"
  printf 'Next: NEW task\\n'
}
printf 'Next: KEPT task\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next old_read
old_pid=$!
wait_file "$case_dir/old-ready"
age_refresh
start_bg next start_capture next new_read
new_pid=$!
''' + ('''
: > "$case_dir/release-new"
[ "$new_pid" = "$old_pid" ] || wait "$new_pid"
: > "$case_dir/release-old"
wait "$old_pid"
''' if order == "new-first" else '''
: > "$case_dir/release-old"
wait "$old_pid"
: > "$case_dir/release-new"
[ "$new_pid" = "$old_pid" ] || wait "$new_pid"
'''))
        calls = (control / "calls").read_text(encoding="utf-8").splitlines()
        expect(calls == ["OLD"], "assertion failed: %s started a second live refresh: %r" % (order, calls))
        expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: OLD task\n",
               "the sole live owner publishes its result")
        expect(not list(gd.glob("uak-start.next*.running")), "the completed sole owner leaves no running marker")
    return "aged live owners coalesce in both attempted completion orders"


def session_start_recovers_a_dead_refresh_owner(r):
    gd, control = refresh_fixture(r, "dead", '''
old_read() { : > "$case_dir/old-ready"; wait_file "$case_dir/release-old"; printf 'Next: OLD task\\n'; }
new_read() { printf 'NEW\\n' >> "$case_dir/calls"; printf 'Next: NEW task\\n'; }
printf 'Next: KEPT task\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next old_read
old_pid=$!
wait_file "$case_dir/old-ready"
kill -KILL "$old_pid"
wait "$old_pid" 2>/dev/null || true
# Do not age the marker: proven death must be recoverable immediately.
start_bg next start_capture next new_read
wait
''')
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW task\n",
           "assertion failed: a dead owner with a fresh marker prevented recovery")
    expect((control / "calls").read_text(encoding="utf-8").splitlines() == ["NEW"], "one replacement runs")
    expect(not list(gd.glob("uak-start.next*.running")), "dead and replacement markers are cleaned up")
    return "dead owner recovered without waiting for marker age"


def session_start_orphan_output_cannot_change_replacement_cache(r):
    gd, control = refresh_fixture(r, "orphan-output", '''
new_read() { printf 'Next: NEW snapshot\\n'; }
if [ "${3:-}" = recover ]; then
  trap - EXIT
  start_bg next start_capture next new_read
  wait
  exit 0
fi
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next bash "$case_dir/backend.sh" OLD "$case_dir" Next
old_pid=$!
wait_file "$case_dir/old-ready"
kill -KILL "$old_pid"
wait "$old_pid" 2>/dev/null || true
age_refresh
# Windows may defer recovery while an orphan holds an output handle; it must fail closed in that case.
bash "$0" "$gd" "$case_dir" recover
: > "$case_dir/release-old"
wait_file "$case_dir/old-done"
cat "$gd/uak-start.next.txt" > "$case_dir/after-orphan"
# Once the orphan closes, either recovery path must finish normally.
start_bg next start_capture next new_read
wait
''')
    after = (control / "after-orphan").read_text(encoding="utf-8")
    expect(after in ("Next: KEPT snapshot\n", "Next: NEW snapshot\n"),
           "assertion failed: orphan output changed the committed cache: %r" % after)
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n",
           "recovery succeeds after the orphan closes its output")
    expect(not list(gd.glob("uak-start.next*.running")), "no crashed generation marker remains")
    return "orphan output cannot write into the replacement's cache inode"


def session_start_orphan_inbox_output_cannot_change_cache(r):
    gd, control = refresh_fixture(r, "orphan-inbox", '''
export UAK_BACKEND_DIR="$case_dir"
mv .uak/bin/uak .uak/bin/uak-real
cat > .uak/bin/uak <<'INBOX'
#!/usr/bin/env bash
if [ "$1" = inbox ]; then
  if mkdir "$UAK_BACKEND_DIR/selected" 2>/dev/null; then
    exec bash "$UAK_BACKEND_DIR/backend.sh" OLD "$UAK_BACKEND_DIR" Inbox
  fi
  printf 'Inbox: NEW snapshot\\n'; exit 0
fi
exec bash "$(dirname "$0")/uak-real" "$@"
INBOX
printf 'Inbox: KEPT snapshot\\n' > "$gd/uak-inbox.txt"
inbox_kept &
old_pid=$!
wait_file "$case_dir/old-ready"
kill -KILL "$old_pid"
wait "$old_pid" 2>/dev/null || true
inbox_kept
cat "$gd/uak-inbox.txt" > "$case_dir/before-orphan"
: > "$case_dir/release-old"
wait_file "$case_dir/old-done"
''')
    before = (control / "before-orphan").read_text(encoding="utf-8")
    after = (gd / "uak-inbox.txt").read_text(encoding="utf-8")
    expect(before == after == "Inbox: NEW snapshot\n",
           "assertion failed: orphan inbox output changed a committed cache: %r -> %r" % (before, after))
    return "inbox readers use private publication sources"


def session_start_revokes_a_dead_owners_pending_move(r):
    gd, control = refresh_fixture(r, "pending-move", '''
export UAK_MOVE_CASE="$case_dir" UAK_MOVE_CACHE="$gd/uak-start.next.txt"
UAK_REAL_MV=$(type -P mv); export UAK_REAL_MV
cat > "$case_dir/move.sh" <<'MOVE'
#!/usr/bin/env bash
src= dst=
for arg in "$@"; do src=$dst; dst=$arg; done
if [ "$dst" = "$UAK_MOVE_CACHE" ] && grep -q '^Next: OLD' "$src"; then
  : > "$UAK_MOVE_CASE/move-ready"
  n=0
  while [ ! -f "$UAK_MOVE_CASE/release-move" ] && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
  "$UAK_REAL_MV" "$@"; status=$?
  : > "$UAK_MOVE_CASE/move-done"
  exit "$status"
fi
exec "$UAK_REAL_MV" "$@"
MOVE
mv() { bash "$case_dir/move.sh" "$@"; }
old_read() { printf 'Next: OLD snapshot\\n'; }
new_read() { printf 'Next: NEW snapshot\\n'; }
new_publish() {
  start_capture next new_read
  : > "$case_dir/new-ready"
  wait_file "$case_dir/release-new"
}
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next old_read
old_pid=$!
wait_file "$case_dir/move-ready"
kill -KILL "$old_pid"
wait "$old_pid" 2>/dev/null || true
age_refresh
start_bg next new_publish
new_pid=$!
wait_file "$case_dir/new-ready"
cat "$gd/uak-start.next.txt" > "$case_dir/before-move"
find "$gd" -name 'uak-start.next*.running' | sort > "$case_dir/markers-before"
: > "$case_dir/release-move"
wait_file "$case_dir/move-done"
cat "$gd/uak-start.next.txt" > "$case_dir/after-move"
find "$gd" -name 'uak-start.next*.running' | sort > "$case_dir/markers-after"
: > "$case_dir/release-new"
wait "$new_pid"
''')
    before = (control / "before-move").read_text(encoding="utf-8")
    after = (control / "after-move").read_text(encoding="utf-8")
    expect(before == after == "Next: NEW snapshot\n",
           "assertion failed: a dead owner's delayed rename overwrote NEW: %r -> %r" % (before, after))
    marks = (control / "markers-before").read_text(encoding="utf-8")
    expect(marks and marks == (control / "markers-after").read_text(encoding="utf-8"),
           "the dead generation cannot remove the current generation's marker")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n", "NEW stays committed")
    return "dead generation's rename source is revoked before replacement"


def session_start_finishes_an_interrupted_reap(r):
    gd, control = refresh_fixture(r, "interrupted-reap", '''
old_gen=$(mktemp -d "$gd/uak-start.next.XXXXXX")
printf '%s\\n' "$old_gen" > "$case_dir/old-generation"
printf 'private OLD output\\n' > "$old_gen/output"
printf '%s\\n' "$NOW" > "$old_gen.running"
(exit 0) &
dead_pid=$!
wait "$dead_pid"
owner=$(printf 'REAP %s %s\\n' "$dead_pid" "${old_gen##*/}" | git hash-object -w --stdin)
git update-ref --no-deref refs/worktree/uak-start/next "$owner"
new_read() {
  local expected_old=
  IFS= read -r expected_old < "$case_dir/old-generation"
  [ ! -e "$expected_old" ] || : > "$case_dir/started-before-revocation"
  printf 'Next: NEW snapshot\\n'
}
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
start_bg next start_capture next new_read
wait
''')
    old = Path((control / "old-generation").read_text(encoding="utf-8").strip())
    expect(not old.exists() and not old.is_symlink(), "interrupted REAP revokes the old generation")
    expect(not (control / "started-before-revocation").exists(), "replacement starts only after revocation")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n",
           "an interrupted REAP cannot strand refresh ownership")
    expect(not list(gd.glob("uak-start.next*.running")), "REAP and replacement markers are cleaned")
    return "dead reaper adopted without losing old-generation cleanup"


def session_start_failed_reap_is_closed_and_retryable(r):
    gd, control = refresh_fixture(r, "failed-reap", '''
rm() {
  local expected_old= arg candidate=
  [ ! -f "$case_dir/old-generation" ] || IFS= read -r expected_old < "$case_dir/old-generation"
  if [ -f "$case_dir/fail-cleanup" ]; then
    expected_old=$(CDPATH= cd -- "$expected_old" && pwd -P) || return 1
    for arg in "$@"; do
      candidate=${arg%/}
      [ ! -d "$candidate" ] || candidate=$(CDPATH= cd -- "$candidate" && pwd -P) || return 1
      if [ "$candidate" = "$expected_old" ]; then : > "$case_dir/cleanup-blocked"; return 1; fi
    done
  fi
  command rm "$@"
}
new_read() { printf 'NEW\\n' >> "$case_dir/calls"; printf 'Next: NEW snapshot\\n'; }
if [ "${3:-}" = failed-attempt ]; then
  trap - EXIT
  start_bg next start_capture next new_read
  wait
  exit 0
fi
old_gen=$(mktemp -d "$gd/uak-start.next.XXXXXX")
printf '%s\\n' "$old_gen" > "$case_dir/old-generation"
printf 'private OLD output\\n' > "$old_gen/output"
printf '%s\\n' "$NOW" > "$old_gen.running"
(exit 0) &
dead_pid=$!
wait "$dead_pid"
owner=$(printf 'REAP %s %s\\n' "$dead_pid" "${old_gen##*/}" | git hash-object -w --stdin)
git update-ref --no-deref refs/worktree/uak-start/next "$owner"
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
: > "$case_dir/fail-cleanup"
bash "$0" "$gd" "$case_dir" failed-attempt
cat "$gd/uak-start.next.txt" > "$case_dir/after-failure"
[ ! -f "$case_dir/calls" ] || cp "$case_dir/calls" "$case_dir/early-calls"
command rm "$case_dir/fail-cleanup"
start_bg next start_capture next new_read
wait
''')
    expect((control / "cleanup-blocked").exists(), "the cleanup fault actually ran")
    expect((control / "after-failure").read_text(encoding="utf-8") == "Next: KEPT snapshot\n"
           and not (control / "early-calls").exists(), "failed revocation cannot start or publish a replacement")
    expect((control / "calls").read_text(encoding="utf-8").splitlines() == ["NEW"], "one retry runs after cleanup works")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n", "REAP recovery finishes")
    expect(not list(gd.glob("uak-start.next*.running")), "recovered cleanup leaves no old markers")
    return "cleanup failure stays closed and a later caller finishes REAP"


def session_start_corrupt_owner_records_cannot_delete_paths(r):
    gd, control = refresh_fixture(r, "corrupt-owner", '''
mkdir -p "$gd/../../victim"
printf 'KEEP\\n' > "$gd/../../victim/sentinel"
printf '%s\\n' "$gd/../../victim/sentinel" > "$case_dir/victim-path"
printf 'Next: KEPT snapshot\\n' > "$gd/uak-start.next.txt"
new_read() { printf 'BAD\\n' >> "$case_dir/calls"; printf 'Next: BAD snapshot\\n'; }
(exit 0) &
dead_pid=$!
wait "$dead_pid"
for record in 'REAP 0 uak-start.next.ABC123' 'REAP nope uak-start.next.ABC123' \
              'UNKNOWN 999999 uak-start.next.ABC123' 'REAP 999999 ../../victim' \
              'REAP 999999 uak-start.next.ABC123/../../victim' 'RUNNING 999999 uak-start.next.ABC123 extra' \
              'REAP 999999 uak-start.next.ABC123
RUNNING 1 uak-start.next.DEF456'; do
  record=${record//999999/$dead_pid}
  owner=$(printf '%s\\n' "$record" | git hash-object -w --stdin)
  git update-ref --no-deref refs/worktree/uak-start/next "$owner"
  start_bg next start_capture next new_read
  wait
  after=$(git rev-parse --verify refs/worktree/uak-start/next 2>/dev/null || true)
  [ "$after" = "$owner" ] || : > "$case_dir/corrupt-ref-mutated"
done
''')
    victim = Path((control / "victim-path").read_text(encoding="utf-8").strip())
    expect(victim.read_text(encoding="utf-8") == "KEEP\n", "corrupt paths cannot escape gitdir")
    expect(not (control / "calls").exists(), "invalid ownership records must fail closed without a backend")
    expect(not (control / "corrupt-ref-mutated").exists(), "invalid records cannot claim or clear ownership")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: KEPT snapshot\n", "corruption keeps last cache")
    return "invalid schema, PID and traversal tokens fail closed"


def session_start_internal_owner_refs_bypass_user_hooks(r):
    gd, control = refresh_fixture(r, "reference-hook", '''
mkdir "$case_dir/user-hooks"
cat > "$case_dir/user-hooks/reference-transaction" <<'HOOK'
#!/usr/bin/env bash
: > "$UAK_REFERENCE_HOOK_MARKER"
exit 1
HOOK
chmod +x "$case_dir/user-hooks/reference-transaction"
export UAK_REFERENCE_HOOK_MARKER="$case_dir/reference-hook-ran"
git config core.hooksPath "$case_dir/user-hooks"
new_read() { printf 'Next: NEW snapshot\\n'; }
start_bg next start_capture next new_read
wait
''')
    expect(not (control / "reference-hook-ran").exists(), "private ownership CAS must not invoke project hooks")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n", "internal ref claim succeeds")
    return "reference-transaction hook is excluded from internal ownership updates"


def session_start_concurrent_claims_launch_one_refresh(r):
    gd, control = refresh_fixture(r, "claim-race", '''
real_git=$(type -P git)
git() {
  local arg last= is_update= is_owner=
  for arg in "$@"; do
    last=$arg
    [ "$arg" != update-ref ] || is_update=1
    [ "$arg" != refs/worktree/uak-start/next ] || is_owner=1
  done
  if [ -n "$is_update" ] && [ -n "$is_owner" ] && [ -z "$last" ]; then
    if mkdir "$case_dir/first-claim" 2>/dev/null; then : > "$case_dir/claim-one-ready"
    else : > "$case_dir/claim-two-ready"; fi
    wait_file "$case_dir/release-claim"
  fi
  command "$real_git" "$@"
}
backend() {
  printf '%s\\n' "$1" >> "$case_dir/calls"
  : > "$case_dir/backend-ready"
  wait_file "$case_dir/release-backend"
  printf 'Next: %s snapshot\\n' "$1"
}
if [ "${3:-}" != '' ]; then
  trap - EXIT
  start_bg next start_capture next backend "$3"
  wait
  exit 0
fi
bash "$0" "$gd" "$case_dir" FIRST &
first=$!
wait_file "$case_dir/claim-one-ready"
bash "$0" "$gd" "$case_dir" SECOND &
second=$!
wait_file "$case_dir/claim-two-ready"
: > "$case_dir/release-claim"
wait_file "$case_dir/backend-ready"
: > "$case_dir/release-backend"
wait "$first"
wait "$second"
''')
    calls = (control / "calls").read_text(encoding="utf-8").splitlines()
    expect(len(calls) == 1 and calls[0] in ("FIRST", "SECOND"), "exactly one concurrent CAS claimant may run")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: %s snapshot\n" % calls[0],
           "the winning claimant publishes its output")
    expect(not list(gd.glob("uak-start.next*.running")), "losing claimant cannot strand a marker")
    return "real concurrent absent-ref claims are atomic"


def session_start_abandoned_handoff_cannot_run_or_release(r):
    gd, control = refresh_fixture(r, "handoff-race", '''
real_git=$(type -P git)
git() {
  local arg previous= last= is_update= is_owner= is_delete= record= state= pid= token=
  for arg in "$@"; do
    previous=$last; last=$arg
    [ "$arg" != update-ref ] || is_update=1
    [ "$arg" != refs/worktree/uak-start/next ] || is_owner=1
    [ "$arg" != -d ] || is_delete=1
  done
  if [ -n "$is_update" ] && [ -n "$is_owner" ] && [ -z "$is_delete" ] && [ -n "$last" ]; then
    record=$(command "$real_git" cat-file blob "$previous" 2>/dev/null) || record=
    IFS=' ' read -r state pid token <<< "$record"
    if [ "$state" = RUNNING ] && mkdir "$case_dir/first-handoff" 2>/dev/null; then
      printf '%s\\n' "$pid" > "$case_dir/old-worker-pid"
      : > "$case_dir/handoff-ready"
      wait_file "$case_dir/release-handoff"
    fi
  fi
  command "$real_git" "$@"
}
old_read() { printf 'OLD\\n' >> "$case_dir/calls"; printf 'Next: OLD snapshot\\n'; }
new_read() { printf 'NEW\\n' >> "$case_dir/calls"; printf 'Next: NEW snapshot\\n'; }
new_publish() { start_capture next new_read; : > "$case_dir/new-ready"; wait_file "$case_dir/release-new"; }
if [ "${3:-}" = old-parent ]; then
  trap - EXIT
  printf '%s\\n' "$$" > "$case_dir/old-parent-pid"
  start_bg next start_capture next old_read
  wait
  exit 0
fi
bash "$0" "$gd" "$case_dir" old-parent &
parent_job=$!
wait_file "$case_dir/handoff-ready"
IFS= read -r parent_pid < "$case_dir/old-parent-pid"
IFS= read -r old_worker < "$case_dir/old-worker-pid"
kill -KILL "$parent_pid"
wait "$parent_job" 2>/dev/null || true
start_bg next new_publish
new_pid=$!
wait_file "$case_dir/new-ready"
find "$gd" -name 'uak-start.next*.running' | sort > "$case_dir/markers-before"
: > "$case_dir/release-handoff"
n=0
while kill -0 "$old_worker" 2>/dev/null && [ "$n" -lt 400 ]; do sleep 0.1; n=$((n + 1)); done
kill -0 "$old_worker" 2>/dev/null && { printf 'assertion failed: abandoned worker did not exit\\n' >&2; exit 1; }
find "$gd" -name 'uak-start.next*.running' | sort > "$case_dir/markers-after"
: > "$case_dir/release-new"
wait "$new_pid"
''')
    expect((control / "calls").read_text(encoding="utf-8").splitlines() == ["NEW"],
           "an abandoned STARTING handoff must not run its backend")
    marks = (control / "markers-before").read_text(encoding="utf-8")
    expect(marks and marks == (control / "markers-after").read_text(encoding="utf-8"),
           "abandoned handoff cannot release a replacement's marker")
    expect((gd / "uak-start.next.txt").read_text(encoding="utf-8") == "Next: NEW snapshot\n", "NEW stays committed")
    return "dead parent handoff loses CAS without touching replacement"


def session_start_inbox_failure_preserves_cache_and_status(r):
    gd, control = refresh_fixture(r, "inbox-failure", '''
mv .uak/bin/uak .uak/bin/uak-real
cat > .uak/bin/uak <<'INBOX'
#!/usr/bin/env bash
exit 7
INBOX
printf 'Inbox: KEPT snapshot\\n' > "$gd/uak-inbox.txt"
if inbox_kept; then status=0; else status=$?; fi
printf '%s\\n' "$status" > "$case_dir/status"
''')
    expect((control / "status").read_text(encoding="utf-8").strip() == "7",
           "assertion failed: private inbox cleanup masked the failed read's status")
    expect((gd / "uak-inbox.txt").read_text(encoding="utf-8") == "Inbox: KEPT snapshot\n", "failed read keeps cache")
    expect(not list(gd.glob("uak-inbox.??????")), "failed private inbox output is removed")
    return "inbox read failure survives cleanup without replacing cached output"


# UAK-177: on GitHub's Windows runners the 3 s budget failed at 3.1-3.2 s (a Git Bash process costs 20-50 ms), while
# the same SHAs passed elsewhere. The work session-start makes the agent wait for is counted instead of timed: shims
# on PATH log every external process while UAK_FG_LOG is set; each background launch in the hook clears it.
COUNTED = ("git", "bash", "awk", "sed", "grep", "head", "tail", "sort", "uniq", "cat", "tr", "cut", "date", "mkdir",
           "mktemp", "rm", "mv", "sleep", "find", "touch", "wc", "basename", "dirname", "cksum", "ls")
# At main a5f38f1 (with only the UAK_FG_LOG clears added) the hook launched these counted processes on this fixture
# before returning, measured on Bash 3.2 (macOS), the most: Bash 4+ reads the payload and the clock with builtins.
# UAK-177 asks for at most half of each.
STARTUP_BEFORE = 41
RESUME_BEFORE = 42


def real_bash(r):
    """The Bash that runs scripts. On Windows r.bash is Git's bin/bash.exe, a launcher that puts its own folders first
    on PATH, so a shim that called it would hide the other shims from the hook (UAK-177, Windows verification)."""
    if os.name != "nt":
        return r.bash
    return r.run([r.bash, "-c", 'cygpath -m "$(type -P bash)"']).stdout.strip() or r.bash


def shims(r, where):
    where.mkdir(parents=True, exist_ok=True)
    bash = real_bash(r)
    for name in COUNTED:
        real = bash if name == "bash" else r.git if name == "git" else shutil.which(name, path=r.env.get("PATH"))
        if not real:
            continue
        shim = where / name
        shim.write_text('#!/bin/sh\n[ -z "$UAK_FG_LOG" ] || echo %s >> "$UAK_FG_LOG"\nexec "%s" "$@"\n'
                        % (name, Path(real).as_posix()), encoding="utf-8")
        shim.chmod(0o755)
    return where


def counted_start(r, f, w, source, tag):
    """Processes session-start launches before it returns, by name; the remote answers only after the hook returned,
    so the bounded wait always runs to its end and the count does not depend on the runner's speed."""
    gate = Path(r.scratch) / ("gate-" + tag)
    if gate.exists():
        gate.unlink()
    for clone in set(f.clones):
        r.g(clone, "config", "remote.origin.uploadpack",
            "while [ ! -f '%s' ]; do sleep 0.1; done; git-upload-pack" % gate.as_posix())
    log = Path(r.scratch) / ("count-%s.log" % tag)
    log.write_text("", encoding="utf-8")
    shim_dir = shims(r, Path(r.scratch) / "count-shims")
    # No machine usage logs (UAK-173): the count is the same on every machine.
    env = {"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1", "UAK_FG_LOG": log.as_posix(),
           "CODEX_HOME": str(Path(r.scratch) / "no-codex")}
    payload = '{"session_id":"s-%s","source":"%s"}' % (source, source)
    # PATH is built inside Bash from the shims' physical POSIX folder, as the inbox race test does: Git Bash's
    # launcher and a native Windows PATH would otherwise put /ucrt64/bin and /usr/bin first.
    prefix = 'shim_dir=$(CDPATH= cd -- "$1" && pwd -P) || exit 1; PATH="$shim_dir:$PATH"; export PATH; '
    try:
        r.run([r.bash, "-c", prefix + "printf '%s' \"$2\" | bash .uak/bin/hook session-start", "_",
               shim_dir.as_posix(), payload], cwd=w, env=env, allowed=None)
        before = [n for n in log.read_text(encoding="utf-8").split() if n]
        # Review of cdbb934 (P2): on Git Bash the shims logged nothing and the limits passed with 0. The hook always
        # runs git (rev-parse), so an empty count means the count is broken, never that the hook is fast.
        expect("git" in before, "the count saw the hook's own git call (shims on PATH and UAK_FG_LOG work here): %r"
               % before[:10])
    finally:
        # Opened whatever happened: a closed gate leaves upload-pack loops behind and Windows cannot clean up.
        gate.write_text("open\n", encoding="utf-8")
    settle(r, w)
    after = [n for n in log.read_text(encoding="utf-8").split() if n]
    expect(after == before, "no background work is counted (a launcher left UAK_FG_LOG set): %s"
           % Counter(after[len(before):]).most_common(6))
    return before


def counted_fixture(r, name):
    f = r.fixture(name, count=1)
    f.claim(0, "HACK-001")
    return f, f.worktrees[0]


def session_start_launches_half_the_processes_on_startup(r):
    f, w = counted_fixture(r, "ss-count-start")
    calls = counted_start(r, f, w, "startup", "startup")
    limit = (STARTUP_BEFORE or 0) // 2
    expect(STARTUP_BEFORE and len(calls) <= limit, "startup launched %d processes before returning (at most %s, half of %s): %s"
           % (len(calls), limit, STARTUP_BEFORE, Counter(calls).most_common(8)))
    return "%d processes (limit %d)" % (len(calls), limit)


def session_start_launches_half_the_processes_on_resume(r):
    f, w = counted_fixture(r, "ss-count-resume")
    counted_start(r, f, w, "startup", "first")
    calls = counted_start(r, f, w, "resume", "resume")
    limit = (RESUME_BEFORE or 0) // 2
    expect(RESUME_BEFORE and len(calls) <= limit, "resume launched %d processes before returning (at most %s, half of %s): %s"
           % (len(calls), limit, RESUME_BEFORE, Counter(calls).most_common(8)))
    return "%d processes (limit %d)" % (len(calls), limit)


def session_start_keeps_reporting_the_pace_level(r):
    """Review of cdbb934 (P2): a level that stays critical must still reach the agent when sessions are more than
    30 min apart. Before UAK-177 session start printed it every time; now it may come from the first tick instead."""
    f = r.fixture("ss-pace-level", count=1)
    f.claim(0, "HACK-001")
    w = f.worktrees[0]
    (w / ".uak/bin/pace").write_text('#!/usr/bin/env bash\ncase "${1:-}" in --caps) echo "critical 1 0";; '
                                     '*) echo "PACE critical: stop spending (test)";; esac\n', encoding="utf-8")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    (gd / "uak-pace.level").write_text("critical", encoding="utf-8")
    (gd / "uak-pace.start").write_text("%d\nPACE critical: an old reading\n" % (int(time.time()) - 7200), encoding="utf-8")
    took, out = start(r, w, "agent-1", UAK_START_WAIT="1")
    settle(r, w)
    seen = "PACE critical" in out
    for _ in range(2):
        if seen:
            break
        for name in ("uak-pace.seen", "uak-inbox.poll"):
            if (gd / name).exists():
                (gd / name).unlink()
        tick = r.run([r.bash, "-c", "printf '%s' '{\"session_id\":\"s-pace\"}' | bash .uak/bin/hook tick"], cwd=w,
                     env={"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1"}, allowed=None)
        seen = "PACE critical" in tick.stdout
        settle(r, w)
    expect(seen, "a critical pace level reaches the agent at session start or its first tick: start printed %r"
           % out[-400:])
    return "critical level reported"


def alive(r, cwd, pid):
    """Whether this PID still runs, asked of Bash so that a Git Bash PID on Windows means the same thing."""
    return r.run([r.bash, "-c", 'kill -0 "$1" 2>/dev/null', "_", str(pid)], cwd=cwd, allowed=None).returncode == 0


def stub_engine(r, w, **bodies):
    """Replace engine scripts of the worktree by small stubs: NAME -> Bash body."""
    b = w / ".uak/bin"
    for name, body in bodies.items():
        (b / name).write_bytes(("#!/usr/bin/env bash\n" + body + "\n").encode("utf-8"))


HUNG_UAK = """case "$1" in next)
  sleep 300 &
  printf '%s\\n' "$$" > "$UAK_HUNG_DIR/uak.pid"
  printf '%s\\n' "$!" > "$UAK_HUNG_DIR/child.pid"
  wait;;
esac"""


def hung_worker_is_killed(r):
    """UAK-157: a `git` that hangs in the refresh must not outlive the session start's worker. The stub `uak next`
    starts a child that sleeps for 300 s, as a git waiting on a dead remote does."""
    f, w = counted_fixture(r, "ss-hung")
    control = Path(r.scratch) / "ss-hung-control"
    control.mkdir()
    stub_engine(r, w, uak=HUNG_UAK)
    pids = []
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1", UAK_START_LIMIT="2", UAK_HUNG_DIR=control.as_posix())
        deadline = time.monotonic() + 20
        while not (control / "child.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        pids = [int((control / n).read_text().strip()) for n in ("uak.pid", "child.pid") if (control / n).exists()]
        expect(len(pids) == 2, "the stub refresh started: %r" % pids)
        # The limit is 2 s here (60 s by default); the kill needs a moment more.
        deadline = time.monotonic() + 15
        while any(alive(r, w, p) for p in pids) and time.monotonic() < deadline:
            time.sleep(0.5)
        left = [p for p in pids if alive(r, w, p)]
        expect(not left, "after the time limit the hung refresh and its child still run (PIDs %r)" % left)
        settle(r, w)
        gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
        expect(not list(gd.glob("uak-start.*.running")), "the killed worker leaves no running marker")
    finally:
        for p in pids:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(p)], cwd=w, allowed=None)
        for p in pids:
            expect(not alive(r, w, p), "test cleanup: PID %d is gone" % p)
    return "a refresh that hangs is killed with its child after the limit"


def pace_and_map_run_once_under_ten_starts(r):
    """UAK-157: `pace` and `map build` are single-flight like `next`: ten starts in a row run each at most once."""
    f, w = counted_fixture(r, "ss-once")
    control = Path(r.scratch) / "ss-once-control"
    control.mkdir()
    stub_engine(r, w, uak='case "$1" in next) echo "Next: stub";; esac',
                pace='echo x >> "$UAK_ONCE_DIR/pace.calls"; sleep 1; echo "PACE normal: stub"',
                map='[ "$1" != build ] || { echo x >> "$UAK_ONCE_DIR/map.calls"; sleep 1; }')
    began = time.monotonic()
    for _ in range(10):
        start(r, w, "agent-1", UAK_START_WAIT="1", UAK_ONCE_DIR=control.as_posix())
    elapsed = time.monotonic() - began
    settle(r, w)
    calls = {n: len((control / (n + ".calls")).read_text().split()) if (control / (n + ".calls")).exists() else 0
             for n in ("pace", "map")}
    expect(calls["pace"] == 1 and calls["map"] == 1,
           "ten starts in %.0f s ran pace %d and map build %d times (once each)" % (elapsed, calls["pace"], calls["map"]))
    return "ten starts in %.0f s: one pace and one map build" % elapsed


def cached_start_does_not_wait(r):
    """UAK-157: with a cached copy the hook answers without waiting for the refresh and says how old the copy is;
    without one it waits for the refresh (bounded) and shows it."""
    f, w = counted_fixture(r, "ss-cached")
    control = Path(r.scratch) / "ss-cached-control"
    control.mkdir()
    stub_engine(r, w, uak='case "$1" in next) d=$(cat "$UAK_DELAY_FILE"); sleep "$d"; echo "Next: stub $d";; esac')
    delay = control / "delay"
    extra = {"UAK_DELAY_FILE": delay.as_posix()}
    delay.write_text("1\n")
    # No copy yet: the hook waits (up to 3 s here) for the 1 s refresh and shows it.
    _, out = start(r, w, "agent-1", UAK_START_WAIT="30", **extra)
    expect("Next: stub 1" in out, "without a cached copy the hook waits for the refresh and shows it: " + out[:400])
    settle(r, w)
    # A copy exists: a 6 s refresh does not hold the hook, which shows the copy and its age.
    delay.write_text("6\n")
    time.sleep(1.2)
    took, out = start(r, w, "agent-1", UAK_START_WAIT="80", **extra)
    expect(took < 5, "with a cached copy the hook waited for the refresh (%.1f s)" % took)
    expect("Next: stub 1" in out, "the cached copy is shown: " + out[:400])
    expect(re.search(r"\b\d+ s ago", out), "the hook says how old the copy is: " + out[:600])
    settle(r, w)
    return "no copy: waits; copy: %.1f s with its age" % took


def hook_functions(r, w, *names):
    """The text of these hook functions, as the hook defines them, so a small Bash harness can run them without a
    whole session start. A name the hook does not define yet is left out (the test then fails on what it checks)."""
    text = (w / ".uak/bin/hook").read_text(encoding="utf-8")
    found = []
    for name in names:
        m = re.search(r"^%s\(\) \{.*?^\}$|^%s\(\) \{.*\}$" % (name, name), text, re.S | re.M)
        if m:
            found.append(m.group(0))
    return "\n".join(found)


ONCE_FUNCS = ("epoch_age", "start_pid_ok", "start_children", "start_tree", "start_kill_tree", "start_limited",
              "start_once_live", "start_once_recent", "start_once_mine", "start_once")


def once_harness(r, w, name, body):
    """A Bash script with start_once and what it needs from the hook, NOW as the hook has it, then BODY."""
    script = Path(r.scratch) / name
    script.write_text("NOW=$(date +%s)\n" + hook_functions(r, w, *ONCE_FUNCS) + "\n" + body + "\n", encoding="utf-8")
    return script


def live_process(r, w):
    """A process that stays alive for the test; its PID as Bash sees it. Stopped by PID in `stop_live`."""
    import subprocess
    proc = subprocess.Popen([r.bash, "-c", "echo $$; exec sleep 120"], stdout=subprocess.PIPE, text=True)
    pid = int(proc.stdout.readline().strip())
    return proc, pid


def stop_live(r, w, proc, pid):
    r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(pid)], cwd=w, allowed=None)
    proc.wait(timeout=20)
    proc.stdout.close()
    expect(not alive(r, w, pid), "test cleanup: PID %d is gone" % pid)


def settle_once(r, w, seconds=40):
    """Also wait for the single-flight jobs (pace, map build), which settle() does not see."""
    settle(r, w, seconds)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    deadline = time.monotonic() + seconds
    while list(gd.glob("uak-once.*.running")):
        expect(time.monotonic() < deadline, "a pace or map build job never finished within %d s" % seconds)
        time.sleep(0.25)
    settle(r, w, seconds)


def bash_counts(control, *names):
    return {n: len((control / (n + ".calls")).read_text().split()) if (control / (n + ".calls")).exists() else 0
            for n in names}


def counting_stubs(r, w, control):
    stub_engine(r, w, uak='case "$1" in next) echo "Next: stub";; esac',
                pace='echo x >> "$UAK_ONCE_DIR/pace.calls"; echo "PACE normal: stub"',
                map='[ "$1" != build ] || echo x >> "$UAK_ONCE_DIR/map.calls"')


def corrupt_time_file_does_not_end_the_hook(r):
    """UAK-185: a time file that holds `08`, letters, nothing or twenty digits made the hook stop at an arithmetic
    error: the output ended at the identity line. Now the value is stale, and the start prints what it always does."""
    f, w = counted_fixture(r, "ss-corrupt")
    control = Path(r.scratch) / "ss-corrupt-control"
    control.mkdir()
    counting_stubs(r, w, control)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    extra = {"UAK_START_WAIT": "1", "UAK_ONCE_DIR": control.as_posix()}
    _, reference = start(r, w, "agent-1", **dict(extra, UAK_START_WAIT="60"))
    settle_once(r, w)
    tail = [l for l in reference.splitlines() if l.strip()][-1]
    expect("Next: stub" in reference and tail, "the reference start prints the list: " + reference[-300:])
    seen = bash_counts(control, "pace", "map")
    for value in ("08", "abc", "", "9" * 20):
        for name in ("uak-start.next.at", "uak-once.pace.at", "uak-once.map.at"):
            (gd / name).write_text(value + "\n", encoding="utf-8")
        (gd / "uak-pace.start").write_text(value + "\nPACE critical: kept from a corrupt time\n", encoding="utf-8")
        _, out = start(r, w, "agent-1", **extra)
        settle_once(r, w)
        expect("UAK: agent=agent-1" in out and "Next: stub" in out and tail in out,
               "with %r in the time files the start still prints everything (its last line %r): %s"
               % (value, tail, out[-400:]))
        now = bash_counts(control, "pace", "map")
        expect(now["pace"] == seen["pace"] + 1 and now["map"] == seen["map"] + 1,
               "with %r in the time files pace and map build still run: before %r, after %r" % (value, seen, now))
        seen = now
    return "08, letters, nothing and twenty digits: the whole output, pace and map build run"


def future_time_file_is_stale(r):
    """UAK-185: a time an hour ahead blocked pace and map build for that hour, and a negative age was printed."""
    f, w = counted_fixture(r, "ss-future")
    control = Path(r.scratch) / "ss-future-control"
    control.mkdir()
    counting_stubs(r, w, control)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    extra = {"UAK_START_WAIT": "1", "UAK_ONCE_DIR": control.as_posix()}
    start(r, w, "agent-1", **dict(extra, UAK_START_WAIT="60"))
    settle_once(r, w)
    before = bash_counts(control, "pace", "map")
    ahead = str(int(time.time()) + 3600)
    proc, pid = live_process(r, w)
    try:
        for name in ("uak-start.next.at", "uak-once.pace.at", "uak-once.map.at"):
            (gd / name).write_text(ahead + "\n", encoding="utf-8")
        for name in ("pace", "map"):  # a live owner whose start lies in the future is not a live owner
            (gd / ("uak-once.%s.running" % name)).write_text("%d %s\n" % (pid, ahead), encoding="utf-8")
        (gd / "uak-pace.start").write_text(ahead + "\nPACE critical: kept from the future\n", encoding="utf-8")
        _, out = start(r, w, "agent-1", **extra)
        settle_once(r, w)
    finally:
        stop_live(r, w, proc, pid)
    after = bash_counts(control, "pace", "map")
    expect(after["pace"] == before["pace"] + 1 and after["map"] == before["map"] + 1,
           "a time an hour ahead does not block pace or map build: before %r, after %r" % (before, after))
    expect("PACE critical: kept from the future" not in out, "a pace reading stamped in the future is not shown")
    expect("Next: stub" in out, "the list is shown: " + out[-300:])
    expect(not re.search(r"-\d+ s ago", out), "an age is never negative: " + out[-400:])
    return "a time an hour ahead is stale: pace and map build run, no negative age"


def stale_lock_reclaim_runs_once(r):
    """UAK-185: reclaiming a stale lock deleted the lock another start had just taken (pace ran twice in 1 of 3
    rounds of 8 simultaneous starts). Ten rounds of eight starts, all released together on a stale lock."""
    import subprocess
    f, w = counted_fixture(r, "ss-race")
    base = Path(r.scratch) / "ss-race-control"
    base.mkdir()
    script = once_harness(r, w, "race.sh", r"""gd=$1
while [ ! -f "$gd/go" ]; do :; done
for n in pace map; do start_once "$n" 60 bash -c 'echo x >> "$1/$2.calls"; sleep 1' _ "$gd" "$n"; done""")
    stale = int(time.time()) - 1000
    totals = []
    for rnd in range(10):
        gd = base / ("round%d" % rnd)
        gd.mkdir()
        for name in ("pace", "map"):
            (gd / ("uak-once.%s.running" % name)).write_text("999999 %d\n" % stale, encoding="utf-8")
        procs = [subprocess.Popen([r.bash, script.as_posix(), gd.as_posix()], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(8)]
        (gd / "go").write_text("go\n")
        for p in procs:
            p.wait(timeout=60)
        deadline = time.monotonic() + 30
        while list(gd.glob("uak-once.*.running")) and time.monotonic() < deadline:
            time.sleep(0.2)
        counts = bash_counts(gd, "pace", "map")
        totals.append(counts)
        expect(counts == {"pace": 1, "map": 1},
               "round %d: eight simultaneous starts on a stale lock ran pace %d and map build %d times (once each); "
               "rounds so far %r" % (rnd + 1, counts["pace"], counts["map"], totals))
        expect(not list(gd.glob("uak-once.*.running")) and not list(gd.glob("uak-once.*.reclaim")),
               "round %d leaves no lock behind" % (rnd + 1))
    return "ten rounds of eight starts: each job ran once in every round"


def once_lock_with_a_bad_time_is_stale(r):
    f, w = counted_fixture(r, "ss-lock-time")
    gd = Path(r.scratch) / "ss-lock-time-gd"
    gd.mkdir()
    script = once_harness(r, w, "lock.sh", r"""gd=$1
start_once pace 0 bash -c 'echo x >> "$1/pace.calls"' _ "$gd"
sleep 1""")
    proc, pid = live_process(r, w)
    try:
        for value in ("08", "abc", "9" * 20, str(int(time.time()) + 3600)):
            before = bash_counts(gd, "pace")["pace"]
            (gd / "uak-once.pace.running").write_text("%d %s\n" % (pid, value), encoding="utf-8")
            r.run([r.bash, script.as_posix(), gd.as_posix()], cwd=w, allowed=None)
            deadline = time.monotonic() + 15
            while bash_counts(gd, "pace")["pace"] == before and time.monotonic() < deadline:
                time.sleep(0.2)
            expect(bash_counts(gd, "pace")["pace"] == before + 1,
                   "a live owner whose lock says %r is stale and pace runs" % value)
            deadline = time.monotonic() + 15
            while (gd / "uak-once.pace.running").exists() and time.monotonic() < deadline:
                time.sleep(0.2)
    finally:
        stop_live(r, w, proc, pid)
    return "08, letters, twenty digits and a time ahead in a lock: stale"


HANG = 'echo "$0 $*" >> "$UAK_HUNG_DIR/jobs"; sleep 300 & echo "$$ $!" >> "$UAK_HUNG_DIR/pids"; wait'


def every_background_job_has_a_limit(r):
    """UAK-185: tokens --publish, bb flush, the lens `map build`, pr-sync and heartbeat were plain nohup jobs. Each
    is stubbed to hang with a child that sleeps for 300 s; with a 2 s limit none of them may be left."""
    import subprocess
    f, w = counted_fixture(r, "ss-limits")
    control = Path(r.scratch) / "ss-limits-control"
    control.mkdir()
    gh = Path(r.scratch) / "ss-limits-gh"
    gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gh.chmod(0o755)
    stub_engine(r, w, uak='case "$1" in next) echo "Next: stub";; pr-sync|heartbeat) %s;; esac' % HANG,
                tokens=HANG, bb='case "$1" in flush) %s;; esac' % HANG,
                map='case "$1" in build) %s;; esac' % HANG, pace='echo "PACE normal: stub"')
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    common = (gd / "commondir")
    cdir = (gd / common.read_text().strip()).resolve() if common.exists() else gd
    (cdir / "uak-blackbox.pending").write_text('{"x":1}\n', encoding="utf-8")
    (w / "README.md").write_text("x\n", encoding="utf-8")
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    env = {"UAK_START_WAIT": "1", "UAK_START_LIMIT": "2", "UAK_HUNG_DIR": control.as_posix(), "UAK_GH": gh.as_posix()}
    pids = []
    try:
        start(r, w, "agent-1", **env)
        lens_tick(r, w, "s-limits", env)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            jobs = (control / "jobs").read_text() if (control / "jobs").exists() else ""
            if all(k in jobs for k in ("tokens", "flush", "build", "pr-sync", "heartbeat")):
                break
            time.sleep(0.3)
        jobs = (control / "jobs").read_text() if (control / "jobs").exists() else ""
        for key in ("tokens", "flush", "build", "pr-sync", "heartbeat"):
            expect(key in jobs, "the hook started the %s job: %s" % (key, jobs))
        pids = [int(x) for line in (control / "pids").read_text().splitlines() for x in line.split()]
        deadline = time.monotonic() + 25
        while any(alive(r, w, p) for p in pids) and time.monotonic() < deadline:
            time.sleep(0.5)
        left = [p for p in pids if alive(r, w, p)]
        expect(not left, "after the 2 s limit these background jobs (and children) still run: PIDs %r of %r; jobs:\n%s"
               % (left, pids, jobs))
        settle_once(r, w)
    finally:
        for p in pids:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(p)], cwd=w, allowed=None)
        for p in pids:
            expect(not alive(r, w, p), "test cleanup: PID %d is gone" % p)
    return "tokens, bb flush, lens map build, pr-sync and heartbeat killed with their children at the limit"


def cached_copy_always_says_its_age(r):
    """UAK-185: the age of a cached copy was said only while a refresh ran. Now whenever the copy is shown, and a
    copy without a (usable) time file says "age unknown"."""
    f, w = counted_fixture(r, "ss-age")
    gd = Path(r.scratch) / "ss-age-gd"
    gd.mkdir()
    (gd / "uak-start.next.txt").write_text("Next: copy\n", encoding="utf-8")
    script = Path(r.scratch) / "show.sh"
    script.write_text("NOW=$(date +%s)\n" + hook_functions(r, w, "epoch_age", "start_once_live", "start_busy", "start_show")
                      + '\ngd=$1\nstart_show next 18 next\n', encoding="utf-8")
    now = int(time.time())
    for value, want in ((str(now - 42), r"\b4[2-9] s ago"), (None, "age unknown"), ("", "age unknown"),
                        ("abc", "age unknown"), (str(now + 3600), "age unknown"), ("9" * 20, "age unknown"),
                        ("08", "age unknown"), ("0", "age unknown")):
        at = gd / "uak-start.next.at"
        if at.exists():
            at.unlink()
        if value is not None:
            at.write_text(value + "\n", encoding="utf-8")
        out = r.run([r.bash, script.as_posix(), gd.as_posix()], cwd=w, allowed=None)
        expect("Next: copy" in out.stdout and re.search(want, out.stdout) and not re.search(r"-\d+ s", out.stdout),
               "with the time file %r, a shown copy (no refresh running) says its age (%s): %r %r"
               % (value, want, out.stdout, out.stderr[:200]))
    # And in the real hook: a copy with no time file next to it, shown while the refresh (3 s) runs.
    control = Path(r.scratch) / "ss-age-control"
    control.mkdir()
    stub_engine(r, w, uak='case "$1" in next) sleep 3; echo "Next: stub";; esac')
    real = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    (real / "uak-start.next.txt").write_text("Next: old copy\n", encoding="utf-8")
    _, out = start(r, w, "agent-1", UAK_START_WAIT="1")
    settle_once(r, w)
    expect("Next: old copy" in out and "age unknown" in out, "a copy without a time file says so: " + out[-500:])
    return "age said with and without a refresh; a copy without a time file says age unknown"


def empty_guard_is_recovered(r):
    """UAK-185 review: a reclaimer killed between creating its guard and writing it left an empty guard that nothing
    judged stale: pace and map build never ran again. An empty guard is judged by the file's own age."""
    f, w = counted_fixture(r, "ss-empty-guard")
    gd = Path(r.scratch) / "ss-empty-guard-gd"
    gd.mkdir()
    script = once_harness(r, w, "emptyguard.sh", r"""gd=$1
start_once pace 0 bash -c 'echo x >> "$1/pace.calls"; sleep 1' _ "$gd"
""")
    (gd / "uak-once.pace.running").write_text("999999 %d 60\n" % (int(time.time()) - 1000), encoding="utf-8")
    guard = gd / "uak-once.pace.reclaim"
    guard.write_text("", encoding="utf-8")
    old = time.time() - 600
    os.utime(str(guard), (old, old))
    for _ in range(3):
        r.run([r.bash, script.as_posix(), gd.as_posix()], cwd=w, allowed=None)
        time.sleep(0.3)
    deadline = time.monotonic() + 15
    while (gd / "uak-once.pace.running").exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    expect(bash_counts(gd, "pace")["pace"] == 1, "an old empty guard on a stale lock: pace ran %d times in 3 starts (once)"
           % bash_counts(gd, "pace")["pace"])
    expect(not guard.exists(), "the old empty guard is removed")
    return "an empty guard older than a minute no longer blocks the job"


def limited_jobs_poll_coarsely(r):
    """UAK-185 review: a detached job polled once a second for its whole limit, a process each on Git Bash."""
    f, w = counted_fixture(r, "ss-poll")
    gd = Path(r.scratch) / "ss-poll-gd"
    gd.mkdir()
    script = Path(r.scratch) / "poll.sh"
    script.write_text(hook_functions(r, w, "start_pid_ok", "start_children", "start_tree", "start_kill_tree",
                                     "start_limit_value", "start_limited") + r"""
gd=$1
sleep() { echo "$1" >> "$gd/sleeps"; SECONDS=$((SECONDS + ${1%%.*})); command sleep 0.01; }
UAK_START_LIMIT=300 start_limited bash -c 'echo $$ > "$1/pid"; exec sleep 600' _ "$gd"
echo "status=$?" > "$gd/status"
""", encoding="utf-8")
    pid = None
    try:
        r.run([r.bash, script.as_posix(), gd.as_posix()], cwd=w, allowed=None)
        pid = int((gd / "pid").read_text().strip())
        sleeps = len((gd / "sleeps").read_text().split())
        expect((gd / "status").read_text().strip() == "status=1", "a job that passes the limit makes start_limited fail")
        expect(20 <= sleeps <= 90, "a 300 s limit costs %d sleeps (at most 90, was about 300)" % sleeps)
        expect(not alive(r, w, pid), "the killed job is gone")
    finally:
        if pid:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(pid)], cwd=w, allowed=None)
    return "a 300 s limit: %d sleeps" % sleeps


def first_pending_dir(r, w):
    return Path(r.run([r.bash, "-c", "git rev-parse --path-format=absolute --git-common-dir"], cwd=w).stdout.strip())


def killed_bb_flush_is_recovered_and_published_once(r):
    """UAK-185 review: a flush killed mid-push left uak-blackbox.pending.PID and a clone, and the lines were never
    retried. The next start puts them back and publishes them once; the clone goes with the kill."""
    f, w = counted_fixture(r, "ss-bb-kill")
    common = first_pending_dir(r, w)
    gate = Path(r.scratch) / "ss-bb-gate"
    gate.write_text("closed\n")
    hook = Path(f.remote) / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nwhile [ -f '%s' ]; do sleep 0.2; done\nexit 0\n" % gate.as_posix(), encoding="utf-8")
    hook.chmod(0o755)
    lines = "".join("2026-11-10T10:0%dZ | agent | kit | error | uak claim | kill-test-%d | - | - | - | v6.4\n" % (i, i)
                    for i in (1, 2))
    pending = common / "uak-blackbox.pending"
    pending.write_text(lines, encoding="utf-8")
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1", UAK_START_LIMIT="3")
        deadline = time.monotonic() + 40
        left = []
        while time.monotonic() < deadline:
            left = [p for p in common.glob("uak-blackbox.pending.*") if p.name.rsplit(".", 1)[1].isdigit()]
            if left and not alive(r, w, int(left[0].name.rsplit(".", 1)[1])) and not list(common.glob("uak-bb-tmp.*")):
                break
            time.sleep(0.3)
        expect(left, "a flush killed mid-push leaves its snapshot (the test needs it): %r" % list(common.glob("uak-*")))
        expect(not list(common.glob("uak-bb-tmp.*")), "the killed flush's clone directory is removed: %r"
               % list(common.glob("uak-bb-tmp.*")))
    finally:
        gate.unlink()
    settle_once(r, w)
    start(r, w, "agent-1", UAK_START_WAIT="1")
    deadline = time.monotonic() + 40
    found = ""
    while time.monotonic() < deadline:
        names = [n for n in r.g(f.remote, "ls-tree", "-r", "--name-only", "claims").stdout.split() if n.startswith("blackbox/")]
        found = "".join(r.g(f.remote, "show", "claims:" + n).stdout for n in names)
        if ("kill-test-1" in found and "kill-test-2" in found and not list(common.glob("uak-blackbox.pending.*"))
                and not list(common.glob("uak-bb-tmp.*"))):
            break
        time.sleep(0.5)
    settle_once(r, w)
    expect(found.count("kill-test-1") == 1 and found.count("kill-test-2") == 1,
           "the next start publishes the recovered lines once: %r" % found[-600:])
    expect(not list(common.glob("uak-blackbox.pending.*")), "no snapshot is left: %r" % list(common.glob("uak-*")))
    return "killed mid-push, recovered by the next start, published once"


def other_users_pending_file_is_left(r):
    """UAK-185 review: `kill -0` fails with EPERM for a process of another user, and bb_leftover read that as a dead
    owner and took the file under a live flush. PID 1 is alive and not ours: its pending file stays; a dead PID's goes."""
    f, w = counted_fixture(r, "ss-bb-eperm")
    probe = r.run([r.bash, "-c", 'kill -0 1 2>&1; echo "rc=$?"'], cwd=w, allowed=None).stdout
    if "rc=0" in probe:
        return "kill -0 1 succeeds here (same user): nothing to prove, skipped"
    if "ermission" not in probe and "not permitted" not in probe.lower():
        return "kill -0 1 does not report a permission error here (%r): skipped" % probe.strip()[:80]
    dead = r.run([r.bash, "-c", "sleep 0 & echo $!; wait"], cwd=w).stdout.split()[0]
    common = Path(r.scratch) / "ss-eperm-common"
    common.mkdir()
    foreign = common / "uak-blackbox.pending.1"
    foreign.write_text("line-of-a-live-flush\n", encoding="utf-8")
    harness = Path(r.scratch) / "ss-eperm.sh"
    harness.write_text('COMMON="$1"\n' + hook_functions(r, w, "start_pid_ok", "bb_leftover") +
                       '\nbb_leftover any; echo "any=$?"\n', encoding="utf-8")
    out = r.run([r.bash, harness.as_posix(), common.as_posix()], cwd=w, allowed=None)
    expect("any=1" in out.stdout, "a pending file of PID 1 (alive, another user) is not a dead owner's: %r %r" % (out.stdout, out.stderr))
    expect(foreign.exists() and foreign.read_text(encoding="utf-8") == "line-of-a-live-flush\n", "its file is left as it was")
    (common / ("uak-blackbox.pending." + dead)).write_text("line-of-a-dead-flush\n", encoding="utf-8")
    out = r.run([r.bash, harness.as_posix(), common.as_posix()], cwd=w, allowed=None)
    expect("any=0" in out.stdout, "a dead owner's file is still found: %r %r" % (out.stdout, out.stderr))
    return "PID 1's pending file is left; a dead PID's is taken"


LENS_STUB = 'case "$1" in build) %s;; esac'


def lens_tick(r, w, sid, env):
    tick = '{"session_id":"%s","tool_name":"Read","tool_input":{"file_path":"%s"}}' % (sid, (w / "README.md").as_posix())
    # The payload goes through the environment: Windows drops the double quotes of a command-line argument.
    out = r.run([r.bash, "-c", "printf '%s' \"$TICK_PAYLOAD\" | bash .uak/bin/hook tick"], cwd=w,
                 env=dict({"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1", "TICK_PAYLOAD": tick}, **env),
                 allowed=None)
    time.sleep(2)   # the tick's own background jobs (drift fetch, heartbeat, pr-sync) are short; the directory is removed next
    return out


def killed_map_build_is_not_a_built_map(r):
    """UAK-185 review: a lens `map build` killed mid-way left a partial symbols.tsv that counted as built."""
    f, w = counted_fixture(r, "ss-map-kill")
    control = Path(r.scratch) / "ss-map-kill-control"
    control.mkdir()
    (w / "README.md").write_text("x\n", encoding="utf-8")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    shutil.rmtree(str(gd / "uak-map"), ignore_errors=True)
    stub_engine(r, w, map=LENS_STUB % ('mkdir -p "$(git rev-parse --absolute-git-dir)/uak-map"; '
                                       'echo partial > "$(git rev-parse --absolute-git-dir)/uak-map/symbols.tsv"; ' + HANG))
    pids = []
    env = {"UAK_START_LIMIT": "2", "UAK_HUNG_DIR": control.as_posix()}
    try:
        t = lens_tick(r, w, "s-map-a", env)
        deadline = time.monotonic() + 15
        while not (control / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        expect((control / "pids").exists(), "the lens started a map build; tick said %r %r; git dir holds %r"
               % (t.stdout[-300:], t.stderr[-300:], sorted(p.name for p in gd.glob("uak-*"))[:40]))
        pids = [int(x) for line in (control / "pids").read_text().splitlines() for x in line.split()]
        deadline = time.monotonic() + 25
        while (any(alive(r, w, p) for p in pids) or (gd / "uak-map/symbols.tsv").exists()) and time.monotonic() < deadline:
            time.sleep(0.5)
        expect(not any(alive(r, w, p) for p in pids), "the killed map build is gone")
        expect(not (gd / "uak-map/symbols.tsv").exists() and not (gd / "uak-map/stamp").exists(),
               "a killed build leaves no partial index: %r" % list((gd / "uak-map").glob("*")))
        # A partial symbols.tsv without a stamp is not a built map: the lens starts a build.
        (gd / "uak-map").mkdir(exist_ok=True)
        (gd / "uak-map/symbols.tsv").write_text("x\tfunction\tREADME.md\t1\n", encoding="utf-8")
        stub_engine(r, w, map=LENS_STUB % 'echo "$0 $*" >> "$UAK_HUNG_DIR/jobs"')
        lens_tick(r, w, "s-map-b", env)
        deadline = time.monotonic() + 15
        while not (control / "jobs").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        expect((control / "jobs").exists() and "build" in (control / "jobs").read_text(),
               "an index without a stamp starts a build")
    finally:
        for p in pids:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(p)], cwd=w, allowed=None)
    settle_once(r, w)
    return "no partial index after a kill; an unstamped index is rebuilt"


def killed_tokens_publish_is_retried(r):
    """UAK-185 review: tokens --publish stamped before it ran, so a kill meant no retry for 30 minutes."""
    f, w = counted_fixture(r, "ss-tokens-kill")
    control = Path(r.scratch) / "ss-tokens-kill-control"
    control.mkdir()
    common = first_pending_dir(r, w)
    stub_engine(r, w, tokens=HANG)
    pids = []
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1", UAK_START_LIMIT="2", UAK_HUNG_DIR=control.as_posix())
        deadline = time.monotonic() + 15
        while not (control / "pids").exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        pids = [int(x) for line in (control / "pids").read_text().splitlines() for x in line.split()]
        deadline = time.monotonic() + 25
        while (any(alive(r, w, p) for p in pids) or (common / "uak-tokens.published").exists()) and time.monotonic() < deadline:
            time.sleep(0.5)
        expect(not any(alive(r, w, p) for p in pids), "the killed tokens job is gone")
        expect(not (common / "uak-tokens.published").exists(), "a killed publish is not stamped as published")
    finally:
        for p in pids:
            r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", str(p)], cwd=w, allowed=None)
    settle_once(r, w)
    return "a killed tokens --publish is retried at the next start"


def counter_files_are_validated(r):
    """UAK-185 review: `08` in a counter aborted the tick, and `a[$(cmd)]` in one ran cmd (arithmetic expansion)."""
    f, w = counted_fixture(r, "ss-counters")
    (w / "README.md").write_text("x\n", encoding="utf-8")
    (w / ".uak-env").write_text("UAK_TASK=HACK-001\nUAK_AGENT=agent-1\n", encoding="utf-8")
    stub_engine(r, w, uak="exit 0", map="exit 0")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    project = w / ".uak/PROJECT.md"
    base = project.read_text(encoding="utf-8") if project.exists() else ""
    evil = "a[$(touch PWNED)]"
    try:
        for value in ("08", evil):
            coach = gd / "uak-coach-s-count"
            coach.mkdir(exist_ok=True)
            for name in ("calls", "explore", "fired.explore"):
                (coach / name).write_text(value + "\n", encoding="utf-8")
            (gd / "uak-inbox.poll").write_text(value + "\n", encoding="utf-8")
            project.write_text(base + "\nLease-Seconds: %s\n" % value, encoding="utf-8")
            out = lens_tick(r, w, "s-count", {})
            settle_once(r, w)
            expect(out.returncode == 0, "a counter holding %r does not abort the tick: %r" % (value, out.stderr[-300:]))
            expect(not (w / "PWNED").exists() and not (gd / "PWNED").exists(), "%r ran a command" % value)
            want = "9" if value == "08" else "1"   # 08 is eight, anything that is not digits starts again from 0
            expect((coach / "calls").read_text().strip() == want, "the call counter after %r is %r, not %s; tick said %r %r; "
                   "git dir %s holds %r" % (value, (coach / "calls").read_text(), want, out.stdout[-300:], out.stderr[-300:],
                                           gd, sorted(p.name for p in gd.glob("uak-*"))[:40]))
            poll = (gd / "uak-inbox.poll").read_text().strip()
            expect(poll.isdigit() and int(poll) > 10**9, "the tick went on to poll and stamped %r (held %r)" % (poll, value))
    finally:
        if base:
            project.write_text(base, encoding="utf-8")
    return "08 and a[$(cmd)] in counters, the poll stamp and Lease-Seconds: no abort, no command"


TESTS = [session_start_returns_within_budget, session_start_output_is_unchanged,
         session_start_marks_only_the_inbox_snapshot_it_prints, session_start_coalesces_aged_live_refreshes,
         session_start_recovers_a_dead_refresh_owner, session_start_orphan_output_cannot_change_replacement_cache,
         session_start_orphan_inbox_output_cannot_change_cache, session_start_revokes_a_dead_owners_pending_move,
         session_start_finishes_an_interrupted_reap, session_start_failed_reap_is_closed_and_retryable,
         session_start_corrupt_owner_records_cannot_delete_paths, session_start_internal_owner_refs_bypass_user_hooks,
         session_start_concurrent_claims_launch_one_refresh, session_start_abandoned_handoff_cannot_run_or_release,
         session_start_inbox_failure_preserves_cache_and_status, session_start_launches_half_the_processes_on_startup,
         session_start_launches_half_the_processes_on_resume, session_start_keeps_reporting_the_pace_level,
         hung_worker_is_killed, pace_and_map_run_once_under_ten_starts, cached_start_does_not_wait]
TESTS += [corrupt_time_file_does_not_end_the_hook, future_time_file_is_stale, stale_lock_reclaim_runs_once,
          once_lock_with_a_bad_time_is_stale, every_background_job_has_a_limit, cached_copy_always_says_its_age,
          empty_guard_is_recovered, limited_jobs_poll_coarsely, killed_bb_flush_is_recovered_and_published_once,
          killed_map_build_is_not_a_built_map, killed_tokens_publish_is_retried, counter_files_are_validated]
TESTS += [other_users_pending_file_is_left]


def clone_listing(common):
    """What is left of the clone directories: every path under them, with its size."""
    out = []
    for d in common.glob("uak-bb-tmp.*"):
        for root, dirs, files in os.walk(str(d)):
            for n in dirs + files:
                p = os.path.join(root, n)
                try:
                    out.append("%s (%d)" % (os.path.relpath(p, str(common)), os.path.getsize(p)))
                except OSError as exc:
                    out.append("%s (%s)" % (os.path.relpath(p, str(common)), exc))
    return out[:12]


def process_listing():
    """Windows only: the git, bash and sleep processes that run with their parent and command line, to see what still
    holds a directory."""
    if os.name != "nt":
        return "no process listing here"
    import subprocess
    cmd = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'git|bash|sh|sleep' } | ForEach-Object "
           "{ '{0}<{1} {2} {3}' -f $_.ProcessId, $_.ParentProcessId, $_.Name, $_.CommandLine }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return "process listing failed: %s" % exc
    return " | ".join(l.strip()[:160] for l in out.splitlines() if l.strip())[:2500]


def kill_round(r, f, w, common, gate, n):
    """One scenario: a flush held at the remote's gate passes its 3 s limit and is killed. Returns (seconds from the
    owner's death to the clone's removal or None, diagnostics) and leaves the checkout recovered for the next round."""
    lines = "".join("2026-11-10T10:0%dZ | agent | kit | error | uak claim | kill-loop-%d-%d | - | - | - | v6.4\n" % (i, n, i)
                    for i in (1, 2))
    (common / "uak-blackbox.pending").write_text(lines, encoding="utf-8")
    gate.write_text("closed\n")
    start(r, w, "agent-1", UAK_START_WAIT="1", UAK_START_LIMIT="3")
    deadline = time.monotonic() + 40
    dead_at = gone_at = None
    while time.monotonic() < deadline:
        left = [p for p in common.glob("uak-blackbox.pending.*") if p.name.rsplit(".", 1)[1].isdigit()]
        if left and dead_at is None and not alive(r, w, int(left[0].name.rsplit(".", 1)[1])):
            dead_at = time.monotonic()
        if dead_at is not None and not list(common.glob("uak-bb-tmp.*")):
            gone_at = time.monotonic()
            break
        time.sleep(0.1)
        if dead_at is not None and time.monotonic() - dead_at > 15:
            break
    diag = ""
    if dead_at is not None and gone_at is None:
        diag = "left: %s; owner: %s; processes: %s" % (clone_listing(common), [
            (d.name, (d / "owner").read_text().strip() if (d / "owner").exists() else None) for d in common.glob("uak-bb-tmp.*")],
            process_listing())
        for d in list(common.glob("uak-bb-tmp.*")):
            try:
                shutil.rmtree(str(d))
                diag += "; rmtree after the wait worked"
            except OSError as exc:
                diag += "; rmtree after the wait: %s" % exc
    gate.unlink()
    settle_once(r, w)
    start(r, w, "agent-1", UAK_START_WAIT="1")
    again = time.monotonic() + 40
    while time.monotonic() < again and (list(common.glob("uak-blackbox.pending.*")) or list(common.glob("uak-bb-tmp.*"))):
        time.sleep(0.3)
    settle_once(r, w)
    if dead_at is None:
        return None, "the flush never passed its limit and died (left: %r)" % list(common.glob("uak-*"))
    return (None if gone_at is None else gone_at - dead_at), diag


def killed_flush_leaves_no_clone_on_windows(r):
    """UAK-190: on main at 967f794 (run 45326081765, windows (10)) the clone directory of a killed flush was still there
    when killed_bb_flush_is_recovered_and_published_once looked (once; it passed on the re-run and in earlier runs).
    Measured on Windows, 20 rounds of this scenario in one job: before the fix (run 45338123292, job 138255069367)
    0 of 20 left a clone and the directory was gone 0.5-0.6 s after the owner's death; after the fix (run 45342514688,
    job 138269556072) 0 of 20, same 0.5-0.6 s. So the race is rare (under 1 in 40 here) and was not reproduced; the
    cause is read from the code: Windows refuses to remove a directory a dying process still uses (a native git's
    cwd or an open file), and bb_unclone tried once, leaving the directory for the next flush, which removed only a
    clone older than 600 s. The fix retries the removal for up to 10 s and lets the next flush remove a clone whose
    owner is gone (leftover_clone_is_removed_by_the_next_flush). The loop costs about 9 s a round on Windows, so the
    default is 1; UAK_KILL_ROUNDS=20 repeats it as in the measurement."""
    rounds = int(os.environ.get("UAK_KILL_ROUNDS", "1"))
    times, bad = [], []
    for n in range(rounds):
        # A fresh checkout each round: the first session start of a checkout also starts the refresh, the pace and
        # the map build, the load under which the failure was seen (run 45326081765 and 45357519599).
        f, w, common, gate = held_push_fixture(r, "ss-bb-kill-loop-%d" % n)
        try:
            took, diag = kill_round(r, f, w, common, gate, n)
        finally:
            if gate.exists():
                gate.unlink()
        if took is None:
            bad.append("round %d: %s" % (n, diag))
        else:
            times.append(took)
    summary = "%d rounds, clone removed after %s s (max %.1f)" % (
        rounds, ",".join("%.1f" % t for t in times), max(times) if times else -1)
    print("MEASURED killed_flush_leaves_no_clone: %s; failures %d: %s" % (summary, len(bad), bad), flush=True)
    expect(not bad, "a killed flush left its clone directory in %d of %d rounds: %s" % (len(bad), rounds, bad[:3]))
    return summary


def plant_clone(common, owner, age=0, name=None):
    """A clone directory as bb_flush_job makes it: uak-bb-tmp.TIME.HOOKPID, with the PID of the process that lives as
    long as the flush in its file `owner` (UAK-190 review: the PID in the name is the hook's, gone in seconds)."""
    d = common / (name or "uak-bb-tmp.%d.%d" % (int(time.time()) - age, 4242))
    (d / "uak-bb.AAAAAA" / ".git").mkdir(parents=True)
    (d / "uak-bb.AAAAAA" / ".git" / "HEAD").write_text("ref: refs/heads/x\n")
    if owner is not None:
        (d / "owner").write_text("%s\n" % owner)
    return d


def leftover_clone_is_removed_by_the_next_flush(r):
    """UAK-190: a clone directory whose flush died stays when its removal failed (Windows refuses while a file is in
    use). The next flush removes it at once when the owner recorded in it is gone, however young it is; a live
    owner's clone stays, and so does a young one that records no owner yet."""
    f, w = counted_fixture(r, "ss-bb-leftover")
    common = first_pending_dir(r, w)
    dead = r.run([r.bash, "-c", "sleep 0 & echo $!; wait"], cwd=w).stdout.split()[0]
    mine = r.run([r.bash, "-c", "sleep 100 & echo $!; disown"], cwd=w).stdout.split()[0]
    gone = plant_clone(common, dead)
    kept = plant_clone(common, mine, name="uak-bb-tmp.%d.4243" % int(time.time()))
    fresh = plant_clone(common, None, name="uak-bb-tmp.%d.4244" % int(time.time()))
    (common / "uak-blackbox.pending").write_text(
        "2026-11-10T10:01Z | agent | kit | error | uak claim | leftover-1 | - | - | - | v6.4\n", encoding="utf-8")
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1")
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and gone.exists():
            time.sleep(0.3)
        settle_once(r, w)
        expect(not gone.exists(), "a young clone whose owner is gone is removed by the next flush: %r"
               % list(common.glob("uak-bb-tmp.*")))
        expect(kept.exists(), "a clone whose owner is alive stays")
        expect(fresh.exists(), "a young clone that records no owner yet stays")
    finally:
        r.run([r.bash, "-c", 'kill -KILL "$1" 2>/dev/null; true', "_", mine], cwd=w, allowed=None)
    return "a dead owner's clone is removed, a live one's stays"


def held_push_fixture(r, name):
    f, w = counted_fixture(r, name)
    common = first_pending_dir(r, w)
    gate = Path(r.scratch) / (name + "-gate")
    gate.write_text("closed\n")
    hook = Path(f.remote) / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nwhile [ -f '%s' ]; do sleep 0.2; done\nexit 0\n" % gate.as_posix(), encoding="utf-8")
    hook.chmod(0o755)
    return f, w, common, gate


def published(r, f):
    names = [n for n in r.g(f.remote, "ls-tree", "-r", "--name-only", "claims").stdout.split() if n.startswith("blackbox/")]
    return "".join(r.g(f.remote, "show", "claims:" + n).stdout for n in names)


def pending_line(tag):
    return "2026-11-10T10:01Z | agent | kit | error | uak claim | %s | - | - | - | v6.4\n" % tag


def recover_and_count(r, f, w, common, tags):
    """The gate is open: let every flush end, start once more to recover what a kill left, and count the lines."""
    settle_once(r, w)
    deadline = time.monotonic() + 60
    found = ""
    while time.monotonic() < deadline:
        start(r, w, "agent-1", UAK_START_WAIT="1")
        settle_once(r, w)
        found = published(r, f)
        if all(t in found for t in tags) and not list(common.glob("uak-blackbox.pending*")):
            break
        time.sleep(1)
    return found


def second_start_leaves_a_live_flushs_clone(r):
    """UAK-190 review of 34480754: the clone carried the PID of the session-start hook, gone in seconds while the flush
    lives up to 300 s, so a second start took the clone of a flush that was still pushing for a dead owner's."""
    f, w, common, gate = held_push_fixture(r, "ss-bb-second")
    (common / "uak-blackbox.pending").write_text(pending_line("second-1"), encoding="utf-8")
    try:
        start(r, w, "agent-1", UAK_START_WAIT="1")
        deadline = time.monotonic() + 40
        first = []
        while time.monotonic() < deadline and not (first and list(common.glob("uak-blackbox.pending.*"))):
            first = list(common.glob("uak-bb-tmp.*"))
            time.sleep(0.3)
        expect(first, "the held flush has its clone: %r" % list(common.glob("uak-*")))
        (common / "uak-blackbox.pending").write_text(pending_line("second-2"), encoding="utf-8")
        start(r, w, "agent-1", UAK_START_WAIT="1")
        time.sleep(4)
        expect(all(p.exists() for p in first), "a second start leaves the clone of a flush that still lives: %r"
               % list(common.glob("uak-bb-tmp.*")))
    finally:
        gate.unlink()
    found = recover_and_count(r, f, w, common, ("second-1", "second-2"))
    expect(found.count("second-1") == 1 and found.count("second-2") == 1, "each line is published once: %r" % found[-500:])
    expect(not list(common.glob("uak-bb-tmp.*")), "no clone is left: %r" % list(common.glob("uak-bb-tmp.*")))
    return "a second start during a held push removes nothing; both lines published once"


def eight_starts_with_a_held_push_publish_once(r):
    """UAK-190 review: eight simultaneous starts while a push is held. Every line is published exactly once, no clone
    goes while its flush lives, none is left at the end. Off by default (UAK_STORM_ROUNDS sets the rounds; the review's
    ten rounds ran on Linux, 10 of 10; a CI run with UAK_STORM_ROUNDS set is the Windows evidence)."""
    from concurrent.futures import ThreadPoolExecutor
    rounds = int(os.environ.get("UAK_STORM_ROUNDS", "0"))
    if rounds < 1:
        return "skipped: it costs 38 s a round on Windows, 14 s on Linux; UAK_STORM_ROUNDS=10 runs the review's ten rounds"
    f, w, common, gate = held_push_fixture(r, "ss-bb-storm")
    try:
        for n in range(rounds):
            tags = ["storm-%d-%d" % (n, i) for i in (1, 2, 3)]
            gate.write_text("closed\n")
            (common / "uak-blackbox.pending").write_text("".join(pending_line(t) for t in tags[:2]), encoding="utf-8")
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: start(r, w, "agent-1", UAK_START_WAIT="1"), range(8)))
                # A line written while the first flush is held: the second wave's flush must not take the first's clone.
                time.sleep(2)
                (common / "uak-blackbox.pending").write_text(pending_line(tags[2]), encoding="utf-8")
                list(pool.map(lambda _: start(r, w, "agent-1", UAK_START_WAIT="1"), range(8)))
            # A flush that finds nothing pending ends at once and takes its own clone; a clone that went while its
            # owner (the PID in its file) still runs was taken from a live flush.
            seen = {}
            end = time.monotonic() + 6
            while time.monotonic() < end:
                for d in common.glob("uak-bb-tmp.*"):
                    if not seen.get(d):
                        try:
                            seen[d] = (d / "owner").read_text().strip()
                        except OSError:
                            seen[d] = ""
                time.sleep(0.3)
            lost = [str(d) for d, o in seen.items() if o and not d.exists() and alive(r, w, int(o))]
            expect(not lost, "round %d: a clone went while its flush still ran: %r" % (n, lost))
            # The flushes held at the remote each own a snapshot (uak-blackbox.pending.BBPID) and each needs its clone.
            held = [x for x in common.glob("uak-blackbox.pending.*") if x.name.rsplit(".", 1)[1].isdigit()
                    and alive(r, w, int(x.name.rsplit(".", 1)[1]))]
            clones = list(common.glob("uak-bb-tmp.*"))
            expect(len(clones) >= len(held) and held, "round %d: %d flushes are held and %d clones remain" % (n, len(held), len(clones)))
            gate.unlink()
            found = recover_and_count(r, f, w, common, tags)
            for t in tags:
                expect(found.count(t) == 1, "round %d: %s is published %d times (once)" % (n, t, found.count(t)))
            expect(not list(common.glob("uak-bb-tmp.*")), "round %d: a clone is left: %r" % (n, list(common.glob("uak-bb-tmp.*"))))
    finally:
        if gate.exists():
            gate.unlink()
    return "%d rounds of eight starts: every line once, no clone lost or left" % rounds


def sweep_harness(r, w, common, body):
    script = Path(r.scratch) / "sweep.sh"
    script.write_text('COMMON="$1"; NOW=$(date +%s)\n' + hook_functions(r, w, "epoch_age", "start_pid_ok", "bb_sweep", "bb_unclone")
                      + "\n" + body + "\n", encoding="utf-8")
    return [r.bash, script.as_posix(), common.as_posix()]


def unremovable_clone_is_retried_then_left_to_the_next_flush(r):
    """UAK-190, Windows imitated on POSIX (an imitation: a directory of mode 000 holding a file cannot be emptied, as
    a directory in use cannot on Windows): the removal is retried and succeeds once the directory can be removed;
    past 10 s it stops, leaves no process, and the next flush removes it; the hook's foreground is not delayed."""
    if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        return "mode 000 does not stop this user here: skipped"
    import threading
    f, w = counted_fixture(r, "ss-bb-unremovable")
    common = first_pending_dir(r, w)
    dead = r.run([r.bash, "-c", "sleep 0 & echo $!; wait"], cwd=w).stdout.split()[0]
    clone = plant_clone(common, dead)
    lock = clone / "uak-bb.AAAAAA" / "locked"
    lock.mkdir()
    (lock / "f").write_text("x")
    lock.chmod(0)
    cmd = sweep_harness(r, w, common, 'bb_unclone; echo "left=$(ls "$COMMON" | grep -c uak-bb-tmp)"')
    try:
        timer = threading.Timer(3, lambda: lock.chmod(0o755))
        timer.start()
        began = time.monotonic()
        out = r.run(cmd, cwd=w, allowed=None)
        took = time.monotonic() - began
        timer.join()
        first_took = took
        expect("left=0" in out.stdout and not clone.exists(), "the retry removes it once it can be removed: %r %r" % (out.stdout, out.stderr))
        expect(3 <= took < 9, "after about 3 s, not at once and not at the end of the retries: %.1f s" % took)
        clone = plant_clone(common, dead)
        lock = clone / "uak-bb.AAAAAA" / "locked"
        lock.mkdir()
        (lock / "f").write_text("x")
        lock.chmod(0)
        began = time.monotonic()
        out = r.run(cmd, cwd=w, allowed=None)
        took = time.monotonic() - began
        expect("left=1" in out.stdout and clone.exists(), "a directory that stays unremovable is left: %r" % out.stdout)
        expect(took < 16, "the retry is bounded: %.1f s" % took)
        (common / "uak-blackbox.pending").write_text(pending_line("unremovable-1"), encoding="utf-8")
        spent, _ = start(r, w, "agent-1", UAK_START_WAIT="1")
        expect(spent < BUDGET, "the session start is not delayed by it: %.1f s" % spent)
        settle_once(r, w)
        expect(clone.exists(), "the flush that could not remove it left it")
        lock.chmod(0o755)
        (common / "uak-blackbox.pending").write_text(pending_line("unremovable-2"), encoding="utf-8")
        start(r, w, "agent-1", UAK_START_WAIT="1")
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and clone.exists():
            time.sleep(0.3)
        expect(not clone.exists(), "the next flush removes it once it can be")
    finally:
        for d in common.glob("uak-bb-tmp.*"):
            for p in d.rglob("locked"):
                p.chmod(0o755)
    settle_once(r, w)
    return "retried until removable (%.1f s), bounded at %.1f s when not, removed by the next flush" % (first_took, took)


def clone_removal_stays_inside_the_clone_directories(r):
    """UAK-190: the sweep touches only directories named uak-bb-tmp.TIME.PID in the git directory: a link named like
    one is removed without its target, a plain file, a name with garbage, an owner that is not a PID and PID 1 are
    left alone."""
    f, w = counted_fixture(r, "ss-bb-safe")
    common = first_pending_dir(r, w)
    outside = Path(r.scratch) / "ss-bb-outside"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    now = int(time.time())
    link = common / ("uak-bb-tmp.%d.5001" % now)
    try:
        os.symlink(str(outside), str(link))
        linked = True
    except (OSError, NotImplementedError):
        linked = False
    plain = common / ("uak-bb-tmp.%d.5002" % now)
    plain.write_text("a file")
    dead = r.run([r.bash, "-c", "sleep 0 & echo $!; wait"], cwd=w).stdout.split()[0]
    garbage = plant_clone(common, dead, name="uak-bb-tmp.garbage.abc;rm")
    badowner = plant_clone(common, "../../x", name="uak-bb-tmp.%d.5003" % now)
    pid1 = plant_clone(common, "1", name="uak-bb-tmp.%d.5004" % now)
    out = r.run(sweep_harness(r, w, common, "bb_sweep; echo swept"), cwd=w, allowed=None)
    expect("swept" in out.stdout, "the sweep runs: %r %r" % (out.stdout, out.stderr))
    expect((outside / "keep").read_text() == "keep", "the target of a link is intact")
    if linked:
        expect(not os.path.lexists(str(link)), "a link named like a clone is removed")
    expect(plain.is_file(), "a plain file stays")
    expect(garbage.is_dir() and badowner.is_dir(), "a name with garbage and an owner that is no PID stay")
    if os.name != "nt":   # Git Bash has no PID 1
        expect(pid1.is_dir(), "PID 1 is an owner that lives: its clone stays")
    return "link removed, target intact; file, garbage, bad owner and PID 1 left alone"


TESTS += [killed_flush_leaves_no_clone_on_windows, leftover_clone_is_removed_by_the_next_flush,
          second_start_leaves_a_live_flushs_clone, eight_starts_with_a_held_push_publish_once,
          unremovable_clone_is_retried_then_left_to_the_next_flush, clone_removal_stays_inside_the_clone_directories]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    import tempfile
    with tempfile.TemporaryDirectory(prefix="uak-ss-speed-") as tmp:
        r = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        failed = 0
        for test in TESTS:
            if args.case and test.__name__ not in args.case:
                continue
            began = time.monotonic()
            try:
                note = test(r)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - began))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:1500]))
    print("SESSION_START_SPEED_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
