#!/usr/bin/env bash
# Times `uak next`, `uak status` and `uak heartbeat` on this machine, on the same state the suite counts
# (kit/.uak/tests/test_claims_perf.py): 12 tasks, 3 live claims, a local bare remote. Run it on Windows (Git Bash),
# where a process costs 20-50 ms, before and after a change to the claims transaction.
#
#   bash scripts/perf_claims.sh [RUNS]      (default 5; prints the median and the slowest of each command)
#
# Nothing leaves this machine: the remote is a folder in a temp dir, removed at the end. Bash 3.2+.
set -eu
runs=${1:-5}
case "$runs" in ''|*[!0-9]*|0) printf 'Usage: perf_claims.sh [RUNS]\n' >&2; exit 2;; esac
kit=$(CDPATH= cd -- "$(dirname -- "$0")/../kit" && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/uak-perf.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
g() { git -c user.name=perf -c user.email=perf@example.invalid "$@"; }
mkdir "$tmp/seed"
cp -R "$kit/.uak" "$tmp/seed/.uak"
{ printf '# TASKS\n\n'
  i=1; while [ "$i" -le 12 ]; do
    printf '## HACK-%03d · task %d\n\n- **Priority:** P0\n- **Paths:** src/t%02d/\n- **Depends on:** None\n- **Verify:** true\n\n' "$i" "$i" "$i"
    i=$((i + 1)); done; } > "$tmp/seed/.uak/TASKS.md"
printf 'Backlog-Approved: yes\nAutonomy: yes\nReview-Mode: claims\n' > "$tmp/seed/.uak/PROJECT.md"
printf '# Owners\n' > "$tmp/seed/.uak/OWNERS.md"
( cd "$tmp/seed" && g init -q -b main && g add -A && g commit -q -m seed && g clone -q --bare . "$tmp/remote.git" )
i=1; while [ "$i" -le 3 ]; do
  g clone -q "$tmp/remote.git" "$tmp/agent-$i"
  g -C "$tmp/agent-$i" worktree add -q -b "task-$i" "$tmp/wt-$i" main
  ( cd "$tmp/wt-$i" && UAK_AGENT="agent-$i" bash .uak/bin/uak claim "HACK-00$i" --branch "task-$i" --worktree "$(pwd -P)" >/dev/null )
  i=$((i + 1)); done
cd "$tmp/wt-1"
export UAK_AGENT=agent-1 UAK_DEDUPE=off
TIMEFORMAT=%R
printf 'uak %s · %s runs each · %s\n' "$(cat .uak/VERSION)" "$runs" "$(uname -s)"
for c in next status "heartbeat HACK-001"; do
  : > "$tmp/times"
  bash .uak/bin/uak $c >/dev/null 2>&1 || true   # the first call of a clone writes its session file
  n=0; while [ "$n" -lt "$runs" ]; do
    { time bash .uak/bin/uak $c >/dev/null 2>&1; } 2>> "$tmp/times"
    n=$((n + 1)); done
  sort -n "$tmp/times" | awk -v c="${c%% *}" '{ t[NR] = $1 } END { printf "%-10s median %.2f s · slowest %.2f s\n", c, t[int((NR + 1) / 2)], t[NR] }'
done
