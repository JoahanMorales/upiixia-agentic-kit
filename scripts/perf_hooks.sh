#!/usr/bin/env bash
# Time and process count of the kit's hot paths (the hooks that run on every tool call), in a worktree with a claimed
# task. Why: on Git Bash every process costs 20-50 ms, so the count, not the work, is what an agent waits for.
#   bash scripts/perf_hooks.sh WORKTREE [RUNS]
# Processes: every bash fork and every program the run starts, counted as distinct PIDs in an xtrace (PS4 prints
# $BASHPID, children inherit SHELLOPTS) with a traced shim in front of each program. Time: RUNS untraced runs.
set -u
wt=${1:?usage: perf_hooks.sh WORKTREE [RUNS]} runs=${2:-5}
cd "$wt" || exit 1
lab=$(mktemp -d "${TMPDIR:-/tmp}/uak-perf.XXXXXX") || exit 1
realenv=$(type -P env)   # the measured run starts through env (SHELLOPTS is read-only in bash), not its shim
trap 'rm -rf "$lab"' EXIT
mkdir "$lab/shims"
for p in git sed awk grep tr head tail cat date find touch mv rm mkdir cut sort wc dirname basename cksum od mktemp \
         uname cygpath ls nohup env sleep base64 python python3 timeout tee xargs uniq comm paste expr seq stat \
         readlink realpath id hostname ps cp chmod ln sha1sum sha256sum md5sum shasum gh curl; do
  real=$(type -P "$p" 2>/dev/null) || continue
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" %s >> "$UAK_PERF_PROGS"\nexec "%s" "$@"\n' "$p" "$real" > "$lab/shims/$p"
  chmod +x "$lab/shims/$p"
done
payload() { # $1 name → hook JSON on stdin
  case "$1" in
    bash-simple) printf '{"session_id":"perf1","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls -la src"}}';;
    bash-commit) printf '{"session_id":"perf1","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git add src/one.txt && git commit -m \\"fix: the parser keeps the last line\\""}}';;
    tick|output) printf '{"session_id":"perf1","hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"ls -la src"},"tool_response":{"stdout":"one.txt","stderr":"","interrupted":false}}';;
    wrap) printf '{"session_id":"perf1","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"pytest -q"}}';;
    prompt) printf '{"session_id":"perf1","hook_event_name":"UserPromptSubmit","prompt":"please fix the parser so it keeps the last line"}';;
    stop) printf '{"session_id":"perf1","hook_event_name":"Stop","stop_hook_active":false}';;
    start) printf '{"session_id":"perf1","hook_event_name":"SessionStart","source":"startup"}';;
    *) printf '{}';;
  esac
}
run_row() { # $1 label, $2 payload, rest: command
  local label=$1 pl=$2 s e ms procs progs top; shift 2
  payload "$pl" | "$@" > /dev/null 2>&1   # warm: state files, caches
  s=$(date +%s%N)
  for _ in $(seq "$runs"); do payload "$pl" | "$@" > /dev/null 2>&1; done
  e=$(date +%s%N)
  ms=$(( (e - s) / 1000000 / runs ))
  : > "$lab/trace"; : > "$lab/progs"
  payload "$pl" > "$lab/in"
  ( exec 9>> "$lab/trace"
    PATH="$lab/shims:$PATH" UAK_PERF_PROGS="$lab/progs" BASH_XTRACEFD=9 PS4='+$BASHPID ' \
      "$realenv" SHELLOPTS=xtrace "$@" < "$lab/in" > /dev/null 2>&1 )
  procs=$(sed -n 's/^+*\([0-9][0-9]*\) .*/\1/p' "$lab/trace" | sort -u | wc -l | tr -d ' ')
  progs=$(wc -l < "$lab/progs" | tr -d ' ')
  top=$(sort "$lab/progs" | uniq -c | sort -rn | head -n 5 | awk '{printf "%s%s %s", (NR > 1 ? ", " : ""), $2, $1}')
  printf '| %s | %s | %s | %s ms | %s |\n' "$label" "$procs" "$progs" "$ms" "$top"
}
printf '| command | processes | programs | time per call | top programs |\n|---|---|---|---|---|\n'
# UAK_PERF_ONLY="tick stop": only the rows of those payload names.
row() { [ -z "${UAK_PERF_ONLY:-}" ] || case " $UAK_PERF_ONLY " in *" $2 "*) ;; *) return 0;; esac; run_row "$@"; }
row "guard bash (ls)" bash-simple bash .uak/bin/guard bash claude
row "guard bash (git commit)" bash-commit bash .uak/bin/guard bash claude
row "hook tick" tick bash .uak/bin/hook tick
row "hook output" output bash .uak/bin/hook output
row "hook wrap codex" wrap bash .uak/bin/hook wrap codex
row "guard prompt" prompt bash .uak/bin/guard prompt
row "hook stop" stop bash .uak/bin/hook stop
row "hook session-start" start bash .uak/bin/hook session-start
row "uak next" next bash .uak/bin/uak next
row "uak status" status bash .uak/bin/uak status
