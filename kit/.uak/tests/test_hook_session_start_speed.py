#!/usr/bin/env python3
"""UAK-013: the session-start hook answers within 3 seconds. Claude Code's /doctor on Dylan's Mac (22 sessions over
18 days, 2026-11-11) measured the kit's SessionStart hook at about 9.5 s typical on startup, 12.6 s on resume and up
to 28 s: it waited for the network (`uak next --full`, the inbox read, `uak digest`) before every session could start.
A slow remote is simulated with remote.origin.uploadpack ('sleep N; git-upload-pack'), so no real network is used."""
import argparse
import json
import os
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
    # No process works in the checkout any more (Windows refuses to rename a folder in use; the UAK-009 probe).
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


# UAK-068: on GitHub's Windows runners the 3 s budget failed at 3.1-3.2 s (a Git Bash process costs 20-50 ms), while
# the same SHAs passed elsewhere. The work session-start makes the agent wait for is counted instead of timed: shims
# on PATH log every external process while UAK_FG_LOG is set; each background launch in the hook clears it.
COUNTED = ("git", "bash", "awk", "sed", "grep", "head", "tail", "sort", "uniq", "cat", "tr", "cut", "date", "mkdir",
           "mktemp", "rm", "mv", "sleep", "find", "touch", "wc", "basename", "dirname", "cksum", "ls")
# At main a5f38f1 (with only the UAK_FG_LOG clears added) the hook launched these counted processes on this fixture
# before returning, measured on Bash 3.2 (macOS), the most: Bash 4+ reads the payload and the clock with builtins.
# UAK-068 asks for at most half of each.
STARTUP_BEFORE = 41
RESUME_BEFORE = 42


def real_bash(r):
    """The Bash that runs scripts. On Windows r.bash is Git's bin/bash.exe, a launcher that puts its own folders first
    on PATH, so a shim that called it would hide the other shims from the hook (UAK-068, Windows verification)."""
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
    # No machine usage logs (UAK-012): the count is the same on every machine.
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
    30 min apart. Before UAK-068 session start printed it every time; now it may come from the first tick instead."""
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


TESTS = [session_start_returns_within_budget, session_start_output_is_unchanged,
         session_start_marks_only_the_inbox_snapshot_it_prints, session_start_coalesces_aged_live_refreshes,
         session_start_recovers_a_dead_refresh_owner, session_start_orphan_output_cannot_change_replacement_cache,
         session_start_orphan_inbox_output_cannot_change_cache, session_start_revokes_a_dead_owners_pending_move,
         session_start_finishes_an_interrupted_reap, session_start_failed_reap_is_closed_and_retryable,
         session_start_corrupt_owner_records_cannot_delete_paths, session_start_internal_owner_refs_bypass_user_hooks,
         session_start_concurrent_claims_launch_one_refresh, session_start_abandoned_handoff_cannot_run_or_release,
         session_start_inbox_failure_preserves_cache_and_status, session_start_launches_half_the_processes_on_startup,
         session_start_launches_half_the_processes_on_resume, session_start_keeps_reporting_the_pace_level]


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
