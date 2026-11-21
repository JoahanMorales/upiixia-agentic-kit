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
# EXIT status of the command → one line. An exec'd script (lib/commands.tsv run=exec) replaces this shell and cannot report
# its end: uak records it at launch with exit and milliseconds "-" (a parent process kept alive to wait would cost a process).
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
