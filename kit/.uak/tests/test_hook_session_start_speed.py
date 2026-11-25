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


def settle_once(r, w, seconds=40):
    """Also wait for the single-flight jobs (pace, map build), which settle() does not see."""
    settle(r, w, seconds)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    deadline = time.monotonic() + seconds
    while list(gd.glob("uak-once.*.running")):
        expect(time.monotonic() < deadline, "a pace or map build job never finished within %d s" % seconds)
        time.sleep(0.25)
    settle(r, w, seconds)


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


LENS_STUB = 'case "$1" in build) %s;; esac'


def lens_tick(r, w, sid, env):
    tick = '{"session_id":"%s","tool_name":"Read","tool_input":{"file_path":"%s"}}' % (sid, (w / "README.md").as_posix())
    # The payload goes through the environment: Windows drops the double quotes of a command-line argument.
    out = r.run([r.bash, "-c", "printf '%s' \"$TICK_PAYLOAD\" | bash .uak/bin/hook tick"], cwd=w,
                 env=dict({"UAK_REMOTE": "origin", "UAK_HUMAN": "", "UAK_AGENT": "agent-1", "TICK_PAYLOAD": tick}, **env),
                 allowed=None)
    # UAK-197: no fixed 2 s here any more. It waited for the tick's own background jobs (drift fetch, heartbeat, pr-sync)
    # before the directory was removed; the case that calls this ends with settle_once, a bounded wait until no process
    # works in the checkout, and polls for what it checks.
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
         session_start_marks_only_the_inbox_snapshot_it_prints, session_start_orphan_output_cannot_change_replacement_cache,
         session_start_orphan_inbox_output_cannot_change_cache, session_start_revokes_a_dead_owners_pending_move,
         session_start_finishes_an_interrupted_reap, session_start_failed_reap_is_closed_and_retryable,
         session_start_corrupt_owner_records_cannot_delete_paths, session_start_internal_owner_refs_bypass_user_hooks,
         session_start_inbox_failure_preserves_cache_and_status, session_start_launches_half_the_processes_on_startup,
         session_start_launches_half_the_processes_on_resume, session_start_keeps_reporting_the_pace_level]
TESTS += [every_background_job_has_a_limit, cached_copy_always_says_its_age, limited_jobs_poll_coarsely,
          killed_map_build_is_not_a_built_map, killed_tokens_publish_is_retried, counter_files_are_validated]
# UAK-197: the cases about locks, simultaneous starts and the black box flush's clones run in
# test_hook_session_start_locks.py (moved unchanged), so that neither file takes more than 300 s on Windows.


# UAK-197: windows (3) of run 45645537660 (job 139315504846) ended with exit code 3840 and no FAIL line while this file
# (then one file with test_hook_session_start_locks.py) ran: 3840 = 15 << 8, which MSYS reports for a Bash ended by
# SIGTERM, so the step's own Bash most likely got a TERM. The only TERM these files cause is start_kill_tree in the hook
# (kit/.uak/bin/hook, `kill -TERM` per PID of a job's tree, listed with pgrep or `ps -e` on Git Bash) and the cleanup
# `kill -KILL` of PIDs the cases recorded. Reading the code found no line that can name the step's Bash: no `kill 0`,
# no negative PID, no empty variable in a kill line (every kill quotes one PID read from `$!`, a pid file or a ps column
# filtered to digits). Not found: whether a PID the tree listing returns on Git Bash can be one this test did not start
# (PID reuse, or a parent PID MSYS reports for processes started by a native Windows program). So every Bash these files
# start sources KILL_GUARD (BASH_ENV): a signal to one of the test's own ancestors (the CI step's Bash among them), to
# PID 0 or to a process group is refused and written down with the script and function that sent it, the file fails
# naming it, and every other signal is written down and sent. A mitigation and a detector, not a fix of a found cause.
KILL_GUARD = r"""# BASH_ENV of test_hook_session_start_speed/_locks (UAK-197): every signal goes through here; see KILL_GUARD there.
kill_guard_started() { # PID [MSYS STIME]: KG_STARTED = the epoch the process started; fails when it cannot be told
  local et= d=0 a= b= c= now=
  KG_STARTED=
  if [ -n "${UAK_KILL_GUARD_WINPIDS:-}" ]; then
    # Git Bash's ps gives STIME: HH:MM:SS for a process of today, a date for an older one (started before the test).
    case "${2:-}" in
      [0-9][0-9]:[0-9][0-9]:[0-9][0-9]) KG_STARTED=$(date -d "$2" +%s 2>/dev/null) || return 1;;
      '') return 1;;
      *) KG_STARTED=0;;
    esac
    return 0
  fi
  et=$(ps -o etime= -p "$1" 2>/dev/null) || return 1
  et=${et// /}
  [ -n "$et" ] || return 1
  case "$et" in *-*) d=${et%%-*}; et=${et#*-};; esac
  IFS=: read -r a b c <<KGEOF
$et
KGEOF
  if [ -z "$c" ]; then c=$b; b=$a; a=0; fi
  now=$(date +%s)
  KG_STARTED=$((now - ((10#$d * 24 + 10#$a) * 60 + 10#$b) * 60 - 10#$c))
}
kill() {
  local first=${1:-} opt= targets= refused= t= rc=0 line= seen=
  case "$first" in -0|-s0|-l|-L) builtin kill "$@"; return;; esac
  if [ "$first" = -s ] && [ "${2:-}" = 0 ]; then builtin kill "$@"; return; fi
  case "$first" in -s|-n) opt="$1 ${2:-}"; shift; shift;; -[A-Za-z0-9]*) opt=$1; shift;; esac
  if [ "${1:-}" = "--" ]; then shift; fi
  local all="$*"
  for t in $all; do
    case "$t" in
      0|-*) refused="$refused $t";;
      *[!0-9]*|'') targets="$targets $t";;
      *) case " ${UAK_KILL_GUARD_PIDS:-} " in *" $t "*) refused="$refused $t"; continue;; esac
         # Git Bash: the Windows process an MSYS PID stands for (`ps -p`: [flag] PID PPID PGID WINPID ...). A signal whose
         # target is one of the test's ancestors under another MSYS PID (a stale or reused entry) is refused too; the ps
         # line of every target is written down.
         if [ -n "${UAK_KILL_GUARD_WINPIDS:-}" ]; then
           line=$(ps -p "$t" 2>/dev/null); line=${line##*$'\n'}
           set -- $line
           case "${1:-}" in [0-9]*) ;; *) [ "$#" -eq 0 ] || shift;; esac
           seen="$seen [$t: ${line:-no such process}]"
           case " $UAK_KILL_GUARD_WINPIDS " in *" ${4:-x} "*) refused="$refused $t(winpid ${4})"; continue;; esac
         fi
         # Only a process started after this test file began may get a signal: a PID that names an older process (an
         # ancestor, the human's session, a PID reused by something else) is refused.
         if [ -n "${UAK_KILL_GUARD_SINCE:-}" ] && kill_guard_started "$t" "${7:-}" && [ "$KG_STARTED" -lt $((UAK_KILL_GUARD_SINCE - 2)) ]; then
           refused="$refused $t(started $((UAK_KILL_GUARD_SINCE - KG_STARTED)) s before the test)"; continue
         fi
         targets="$targets $t";;
    esac
  done
  if [ -n "$refused" ]; then
    printf 'REFUSED kill %s%s from %s %s (pid %s)%s\n' "${opt:--TERM}" "$refused" "${0##*/}" "${FUNCNAME[1]:-main}" "$$" "$seen" >> "${UAK_KILL_GUARD_LOG:-/dev/null}"
    rc=1
  fi
  if [ -z "$targets" ]; then return "$rc"; fi
  printf 'SENT kill %s%s from %s %s%s\n' "${opt:--TERM}" "$targets" "${0##*/}" "${FUNCNAME[1]:-main}" "$seen" >> "${UAK_KILL_GUARD_LOG:-/dev/null}"
  if [ -n "${UAK_KILL_GUARD_DRY:-}" ]; then return "$rc"; fi   # the guard's own test: written down, never sent
  builtin kill $opt $targets || return
  return "$rc"
}
"""


def ancestors():
    """PIDs of this process and its ancestors, as a Bash `kill` would name them: on Git Bash both the Windows PIDs of the
    chain (Toolhelp snapshot) and the MSYS PIDs whose WINPID is one of them (`ps -e`)."""
    import subprocess
    chain, pid = [], os.getpid()
    if os.name != "nt":
        while pid > 1 and pid not in chain and len(chain) < 64:
            chain.append(pid)
            out = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
            pid = int(out) if out.isdigit() else 0
        return chain
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_char * 260)]
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    parent, e = {}, Entry()
    e.dwSize = ctypes.sizeof(Entry)
    ok = k32.Process32First(snap, ctypes.byref(e))
    while ok:
        parent[e.th32ProcessID] = e.th32ParentProcessID
        ok = k32.Process32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    while pid and pid not in chain and len(chain) < 64:
        chain.append(pid)
        pid = parent.get(pid, 0)
    ancestors.winpids = list(chain)
    msys = []
    bash = resolve_binary("bash")
    listing = subprocess.run([bash, "-c", "ps -e"], capture_output=True, text=True).stdout
    for line in listing.splitlines():
        cols = line.split()
        if cols and not cols[0].isdigit():
            cols = cols[1:]
        if len(cols) >= 4 and cols[0].isdigit() and cols[3].isdigit() and int(cols[3]) in chain:
            msys.append(int(cols[0]))
    return chain + msys


def kill_guard(r):
    """Install KILL_GUARD for every Bash this test starts (the Runner's env and os.environ, for Popen); returns the log."""
    guard, log = Path(r.scratch) / "kill-guard.sh", Path(r.scratch) / "kill-guard.log"
    guard.write_text(KILL_GUARD, encoding="utf-8")
    log.write_text("", encoding="utf-8")
    env = {"BASH_ENV": guard.as_posix(), "UAK_KILL_GUARD_LOG": log.as_posix(),
           "UAK_KILL_GUARD_PIDS": " ".join(str(p) for p in sorted(set(ancestors()))),
           "UAK_KILL_GUARD_SINCE": str(int(time.time()))}
    if os.name == "nt":
        env["UAK_KILL_GUARD_WINPIDS"] = " ".join(str(p) for p in getattr(ancestors, "winpids", []))
    print("KILL_GUARD protects %s (Windows PIDs of the chain: %s)" % (env["UAK_KILL_GUARD_PIDS"], env.get("UAK_KILL_GUARD_WINPIDS", "-")),
          flush=True)
    os.environ.update(env)
    r.env.update(env)
    return log


def stream_kill_log(log, stop):
    """Print each line the guard writes as it comes (flushed): a run whose step dies still shows the last signals."""
    import threading

    def follow():
        done = 0
        while True:
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            lines = text.splitlines()
            if len(lines) < done:      # the guard's own case puts the log back as it was
                done = len(lines)
            for line in lines[done:]:
                print("KILL_GUARD " + line[:600], flush=True)
            done = len(lines)
            if stop.wait(0.2):
                return
    t = threading.Thread(target=follow, daemon=True)
    t.start()
    return t


def kill_guard_report(log):
    """(line to print, refused lines): what the Bashes of this file signalled."""
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    refused = [l for l in lines if l.startswith("REFUSED")]
    sent = [l for l in lines if l.startswith("SENT")]
    by = Counter(" ".join(l.split()[2:3] + l.split()[-2:]) for l in sent)
    return ("KILL_GUARD sent=%d refused=%d protected=%s; signals sent: %s" % (
        len(sent), len(refused), os.environ.get("UAK_KILL_GUARD_PIDS", ""), dict(by.most_common(8)))), refused


def kill_guard_refuses_an_ancestor(r):
    """UAK-197: the guard every Bash of these files sources refuses a signal to a protected process (an ancestor of the
    test in a real run), to PID 0 and to a process group, writes it down, and still sends every other signal. Forced with
    processes this case starts: its own `victim` stands for a protected ancestor, and the refused kills run with
    UAK_KILL_GUARD_DRY set, so a broken guard would only write SENT, never signal anything."""
    import subprocess
    log = Path(os.environ.get("UAK_KILL_GUARD_LOG", ""))
    expect(os.environ.get("BASH_ENV") and log.is_file(), "the guard is installed for this file's Bashes")
    before = log.read_text(encoding="utf-8", errors="replace")
    procs = [subprocess.Popen([r.bash, "-c", "echo $$; exec sleep 60"], stdout=subprocess.PIPE, text=True) for _ in range(2)]
    victim, other = (p.stdout.readline().strip() for p in procs)
    try:
        dry = r.run([r.bash, "-c", 'kill -TERM "$1"; echo "a=$?"; kill -TERM 0; echo "b=$?"; kill -TERM -- -"$1"; echo "c=$?"', "_",
                     victim], env={"UAK_KILL_GUARD_PIDS": victim, "UAK_KILL_GUARD_DRY": "1"}, allowed=None)
        # Git Bash's view, forced with a ps that answers as MSYS does: the target's WINPID is a protected Windows PID.
        msys = r.run([r.bash, "-c", 'ps() { printf "      PID    PPID    PGID     WINPID   TTY         UID    STIME COMMAND\\n'
                      'I    %s       1    %s       4242  cons0     197108 10:00:00 /usr/bin/sleep\\n" "$2" "$2"; }; '
                      'kill -TERM "$1"; echo "f=$?"', "_", other],
                     env={"UAK_KILL_GUARD_PIDS": "", "UAK_KILL_GUARD_WINPIDS": "4242", "UAK_KILL_GUARD_DRY": "1"}, allowed=None)
        # A process older than the test file (forced: the file "began" 100 s from now) is refused, whatever its PID.
        older = r.run([r.bash, "-c", 'kill -TERM "$1"; echo "g=$?"', "_", other],
                      env={"UAK_KILL_GUARD_PIDS": "", "UAK_KILL_GUARD_SINCE": str(int(time.time()) + 100), "UAK_KILL_GUARD_DRY": "1"},
                      allowed=None)
        real = r.run([r.bash, "-c", 'kill -0 "$1"; echo "d=$?"; kill -KILL "$2"; echo "e=$?"', "_", victim, other],
                     env={"UAK_KILL_GUARD_PIDS": victim}, allowed=None)
        procs[1].wait(timeout=20)
        victim_alive = procs[0].poll() is None
    finally:
        for p in procs:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=20)
            p.stdout.close()
    new = log.read_text(encoding="utf-8", errors="replace")[len(before):].splitlines()
    log.write_text(before, encoding="utf-8")   # the forced refusals are this case's, not the file's
    expect(all(x in dry.stdout for x in ("a=1", "b=1", "c=1")), "refused kills fail: %r" % dry.stdout)
    expect("d=0" in real.stdout and "e=0" in real.stdout, "kill -0 and a kill of another process work: %r" % real.stdout)
    refused = [l for l in new if l.startswith("REFUSED")]
    expect(len(refused) >= 4 and " %s " % victim in refused[0] + " " and " 0 " in refused[1] + " " and "-" + victim in refused[2],
           "the refusals are written down, with the target: %r" % new)
    expect("f=1" in msys.stdout and "%s(winpid 4242)" % other in refused[3] and "/usr/bin/sleep" in refused[3],
           "a target whose Windows PID is protected is refused, its ps line written down: %r %r" % (msys.stdout, refused[3:]))
    expect("g=1" in older.stdout and len(refused) == 5 and "%s(started" % other in refused[4] and "before the test)" in refused[4],
           "a process older than the test is refused: %r %r" % (older.stdout, refused[4:]))
    expect(not [l for l in new if l.startswith("SENT") and victim in l], "nothing was sent to the protected process: %r" % new)
    expect(any(l.startswith("SENT kill -KILL %s" % other) for l in new), "the allowed kill is written down: %r" % new)
    expect(victim_alive and procs[1].returncode is not None, "the protected process lives, the other got its signal")
    return "a protected PID, PID 0, a group, a protected Windows PID and an older process refused; another process killed"


def run_cases(tests, label, prefix):
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    import tempfile
    with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
        r = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        log = kill_guard(r)
        import threading
        stop = threading.Event()
        follower = stream_kill_log(log, stop)
        # UAK_SS_REPEAT=CASE:N[,CASE:N] runs those cases N times in a row, each round in a scratch folder of its own
        # (UAK-197: the 20 runs in a row a fix is judged by, opt-in; off by default).
        repeat = dict(x.partition(":")[::2] for x in os.environ.get("UAK_SS_REPEAT", "").split(",") if ":" in x)
        failed = 0
        for test in tests:
            if args.case and test.__name__ not in args.case:
                continue
            rounds = int(repeat[test.__name__]) if repeat.get(test.__name__, "").isdigit() else 1
            for k in range(rounds):
                here = r if k == 0 else Runner(r.package, Path(tmp) / ("round-%d" % (k + 1)), r.bash, r.git)
                shown = test.__name__ + (" round %d of %d" % (k + 1, rounds) if rounds > 1 else "")
                began = time.monotonic()
                try:
                    note = test(here)
                    print("PASS %s (%s, %.2fs)" % (shown, note, time.monotonic() - began), flush=True)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    print("FAIL %s (%s)" % (shown, str(exc)[:1500]), flush=True)
        stop.set()
        follower.join(5)
        line, refused = kill_guard_report(log)
        print(line)
        if refused:
            failed += 1
            print("FAIL kill_guard (a Bash of this file signalled an ancestor of the test, PID 0 or a group: %s)" % refused[:5])
    print("%s_RESULT %s failed=%d" % (label, "PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


TESTS += [kill_guard_refuses_an_ancestor]


def main():
    return run_cases(TESTS, "SESSION_START_SPEED", "uak-ss-speed-")


if __name__ == "__main__":
    raise SystemExit(main())
