# The command ledger (UAK-116): one line per `uak` command in <git-common-dir>/uak-ledger.pending, tab separated:
#   epoch  command  task  exit  code  milliseconds  agent  harness      ("-" = unknown)
# `bb flush` publishes it to claims as metrics/<day>-<machine>.tsv with the black box lines. Builtins only: no process
# starts on the way. Bash 5 has EPOCHREALTIME (milliseconds); bash 3.2 has $SECONDS (whole seconds) and no epoch builtin:
# there the epoch is NOW (the engine's clock, set by commands that read it) or "-", and `bb flush` stamps "-" with the flush
# time. UAK_LEDGER_CLOCK=seconds forces the 3.2 path (tests). UAK_BLACKBOX=off writes nothing.
# Why (audit of v6.5.0, §4): calls were names only; "how often does `claim` fail, how long does `status` take" had no answer.
LG_ON=0 LG_CODE=
lg_clock() { LG_US= LG_EP=; if [ "${BASH_VERSINFO[0]}" -ge 5 ] && [ "${UAK_LEDGER_CLOCK:-}" != seconds ]; then LG_US=${EPOCHREALTIME/[.,]/} LG_EP=${EPOCHREALTIME%[.,]*}; fi; }
ledger_start() { # DIR: the git common dir (the same place as the calls file); called where the call is counted
  LG_DIR=$1 LG_ON=1 LG_CODE=
  lg_clock; LG_T0=${LG_US:-$SECONDS}
}
# EXIT status of the command → one line. A script of its own (lib/commands.tsv run=exec) is run by uak as a child and
# waited for (UAK-136), so it ends the same way: exit code and milliseconds. "-" stays only for lines older than that.
ledger_end() { # EXIT_CODE ["TASK" when the command has not set ID]
  [ "$LG_ON" = 1 ] || return 0
  LG_ON=0
  local rc=$1 t=${2:-${ID:-}} ms=- ep=- ag=${AGENT:-${UAK_AGENT:-}} hn=${UAK_HARNESS:-} t1
  case "$rc" in ''|*[!0-9]*) rc=-;; esac
  lg_clock; ep=${LG_EP:--}
  # Bash 3.2 has no epoch builtin: the engine's own clock (NOW, read by the claims transaction) is the only free source.
  case "$ep:${NOW:-}" in -:''|-:*[!0-9]*) ;; -:*) ep=$NOW;; esac
  if [ "$rc" = - ]; then :
  elif [ -n "$LG_US" ]; then ms=$(( (LG_US - LG_T0) / 1000 ))
  else ms=$(( (SECONDS - LG_T0) * 1000 )); fi
  case "$t" in [A-Z]*-[0-9][0-9]*[0-9]) case "$t" in *[!A-Za-z0-9-]*) t=-;; esac;; *) t=-;; esac
  case "$ag" in ''|*[!A-Za-z0-9_.-]*) ag=-;; esac
  if [ -z "$hn" ]; then
    if [ -n "${CLAUDECODE:-}" ]; then hn=claude-code
    elif [ -n "${CODEX_SANDBOX:-}${CODEX_THREAD_ID:-}${CODEX_HOME:-}" ]; then hn=codex
    elif [ -n "${CURSOR_TRACE_ID:-}${CURSOR_AGENT:-}${CURSOR_VERSION:-}" ]; then hn=cursor
    elif [ -n "${GEMINI_CLI:-}" ]; then hn=gemini-cli
    else hn=other; fi
  fi
  case "$hn" in *[!A-Za-z0-9._-]*) hn=other;; esac
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$ep" "${UAK_CALLER:+$UAK_CALLER-}${CMD:-?}" "$t" "$rc" "${LG_CODE:--}" "$ms" "$ag" "$hn" \
    >> "$LG_DIR/uak-ledger.pending" 2>/dev/null || :
}
# An exec'd script of the engine (lib/commands.tsv run=exec) keeps the dispatcher's process, so the line is closed by the script
# itself (UAK-136; no waiting parent, signals reach the script): `uak` calls ledger_handoff just before the exec, the script calls
# ledger_owed once at its top, and an EXIT trap writes the line with the real exit code and milliseconds. The script's own EXIT
# traps are chained through a `trap` function (they all read `trap 'CMD' EXIT`). Not covered, so written at launch with exit and
# ms "-": wrappers that exec Python themselves (autopsy, design, design-gallery) and `pace set` (re-execs itself). dash, timeline
# and metrics close the line from Python (lib/ledger_py.py). A signal death writes no line: bash defers a trap while a foreground
# command runs (measured: TERM waited 4 s for a sleep), so a trap would make the script outlive the signal.
ledger_handoff() { # ["TASK"]: the dispatcher, just before `exec bash script`
  unset UAK_LG_OWED
  [ "$LG_ON" = 1 ] || return 0
  case "$CMD:${1:-}" in autopsy:*|design:*|design-gallery:*|pace:set) ledger_end - "${1:-}"; return 0;; esac
  LG_ON=0
  export UAK_LG_OWED=$LG_DIR UAK_LG_CMD=$CMD UAK_LG_TASK=${1:-} UAK_LG_AGENT=${AGENT:-${UAK_AGENT:-}}
  [ "${#LG_T0}" -lt 15 ] || export UAK_LG_T0=$LG_T0
}
ledger_owed() { # an exec'd engine script, once, at its top (before it sets traps of its own)
  [ -n "${UAK_LG_OWED:-}" ] || return 0
  LG_ON=1 LG_DIR=$UAK_LG_OWED LG_CODE= LG_X_CMD=${UAK_LG_CMD:-?} LG_X_TASK=${UAK_LG_TASK:-} LG_X_AG=${UAK_LG_AGENT:-}
  lg_clock
  LG_X_T0=${UAK_LG_T0:-}   # (bash 3.2 with set -u: ${#unset} is an error, so the length is taken from a set variable)
  if [ "${#LG_X_T0}" -ge 15 ] && [ -n "$LG_US" ]; then LG_T0=$LG_X_T0; else LG_T0=${LG_US:-$SECONDS}; fi
  unset UAK_LG_OWED UAK_LG_CMD UAK_LG_TASK UAK_LG_AGENT UAK_LG_T0   # a nested uak never closes this line twice
  trap() { # chains the script's own EXIT trap with the ledger line
    if [ "$#" -eq 2 ] && { [ "$2" = EXIT ] || [ "$2" = 0 ]; }; then
      case "$1" in
        -|'') builtin trap 'lg_rc=$?; ledger_exit "$lg_rc"' EXIT;;
        *) builtin trap "lg_rc=\$?; $1
ledger_exit \"\$lg_rc\"" EXIT;;
      esac
    else builtin trap "$@"; fi
  }
  builtin trap 'lg_rc=$?; ledger_exit "$lg_rc"' EXIT
}
ledger_exit() { CMD=$LG_X_CMD AGENT=$LG_X_AG; ledger_end "$1" "$LG_X_TASK"; }
# Is the oldest pending ledger line more than 10 min old? Bash 5: the first line's epoch against the clock, builtins only
# (a find per command would cost a process on every call); bash 3.2 or a first line without epoch asks find (the file's age).
ledger_due() { # DIR
  local f=$1/uak-ledger.pending e=
  [ -s "$f" ] || return 1
  lg_clock
  if [ -z "$LG_EP" ]; then [ -n "$(find "$f" -mmin +10 2>/dev/null)" ]; return; fi
  IFS=$'\t' read -r e _ < "$f" || :
  case "$e" in ''|*[!0-9]*) [ -n "$(find "$f" -mmin +10 2>/dev/null)" ]; return;; esac
  [ $((LG_EP - e)) -gt 600 ]
}
