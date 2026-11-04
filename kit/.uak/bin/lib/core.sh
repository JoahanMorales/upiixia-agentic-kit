# Core of every uak command: output and exit codes, IDs, identity, the clock, the temp dir's cleanup.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

say() { printf '%s\n' "$*"; }
# Black box (.uak/docs/BLACKBOX.md): every error is also recorded locally; flushed later in one push.
# UAK_PROBE: next tests every candidate in a subshell; those expected refusals are not errors.
# Why (Reap buildathon): 153 of 290 black box lines were one FREEZE refusal per candidate of `uak next`.
bb_auto() {
  [ -z "${UAK_PROBE:-}" ] || return 0
  bash "$UAK_BIN/bb" auto "$1" "$CMD" "$2" >/dev/null 2>&1 || true
  loop_hint "$2"
}
# The same error 3 times in 10 min on this machine = a retry loop that burns tokens. Say so once per repeat.
loop_hint() {
  [ -n "${bb_common:-}" ] && [ -d "$bb_common" ] || return 0
  local f="$bb_common/uak-errors.recent" t key n
  t=$(date +%s); key=$(printf '%s %s' "$CMD" "$1" | cksum | awk '{print $1}')
  printf '%s %s\n' "$t" "$key" >> "$f" 2>/dev/null || return 0
  n=$(awk -v now="$t" -v k="$key" '$1 >= now - 600 && $2 == k {n++} END {print n+0}' "$f")
  tail -n 200 "$f" > "$f.tmp" 2>/dev/null && mv "$f.tmp" "$f" 2>/dev/null
  [ "$n" -lt 3 ] || say "LOOP: the same error $n times in 10 min. Stop retrying: read the message above, do other work, or ask the human." >&2
}
# The three ways a command fails, each with its exit code. A stable short code for `uak --json` comes from UAK_CODE
# set on the call (UAK_CODE=lease-active conflict "…"; the list is in CLI.md, Result codes); the text stays as it is.
die() { result_code error; say "ERROR: $*" >&2; bb_auto 2 "ERROR: $*"; exit 2; }
conflict() { result_code conflict; say "CONFLICT: $*" >&2; bb_auto 3 "CONFLICT: $*"; exit 3; }
gitfail() { result_code git-error; say "GIT_ERROR: $*" >&2; bb_auto 1 "GIT_ERROR: $*"; exit 1; }
result_code() { [ -z "${UAK_JSON_META:-}" ] || [ -n "${UAK_PROBE:-}" ] || printf 'code\t%s\n' "${UAK_CODE:-$1}" >> "$UAK_JSON_META" 2>/dev/null || true; }
valid_id() { printf '%s\n' "$1" | grep -Eq '^[A-Z][A-Z0-9]*-[0-9][0-9][0-9]+$'; }
# hack-021 means HACK-021. Why (MLB hackathon): 4 "Invalid ID." errors from Cursor with no hint of the value.
norm_id() { case "$1" in *[a-z]*-[0-9]*) printf '%s' "$1" | tr '[:lower:]' '[:upper:]';; *) printf '%s' "$1";; esac; }
bad_id() {
  # A flag where the ID goes ("checkpoint --summary", "status --task --summary" with an empty $UAK_TASK): say the usage.
  case "$1" in -*) UAK_CODE=invalid-id die "Invalid ID '$1': $CMD takes the task ID first. Usage: $(usage | grep -E "^$CMD( |\$)" | head -n 1)";; esac
  UAK_CODE=invalid-id die "Invalid ID '$1': use the task ID as in TASKS.md, e.g. HACK-012 (uak status lists them)."
}
# Why (Chilangatón): `done` failed with a bare "Invalid option." and the agent guessed again.
bad_opt() { UAK_CODE=invalid-option die "Invalid option $opt for $CMD. Usage: $(usage | grep -E "^$CMD( |\$)" | head -n 1)"; }
# Prints the kind of the first secret-looking token on stdin; fails when there is none. Shared by every claims
# write. A token must carry a digit and be long: "task-assignment-service" is not an sk- key.
secret_like() {
  local inp t
  inp=$(cat)
  case "$inp" in *'-----BEGIN '*'PRIVATE KEY'*) printf 'a private key'; return 0;; esac
  t=$(printf '%s\n' "$inp" | grep -Eo '(^|[^A-Za-z0-9])(sk-[A-Za-z0-9_-]{20,}|[sr]k_(live|test)_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|xox[abprs]-[0-9][A-Za-z0-9-]{10,}|npm_[A-Za-z0-9]{36}|hf_[A-Za-z0-9]{30,}|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp)://[^ :/@]+:[^ @/]+@)' | grep -E '[0-9]|://' | head -n 1)
  [ -n "$t" ] || return 1
  case "$t" in *sk-*|*sk_*|*rk_*) printf 'an API key';; *gh?_*|*github_pat_*) printf 'a GitHub token';; *AKIA*) printf 'an AWS key';;
    *AIza*) printf 'a Google key';; *xox*) printf 'a Slack token';; *eyJ*) printf 'a JWT';; *://*) printf 'a database URL with a password';; *) printf 'a token';; esac
}
one_line() { local text=$1; text=${text//$'\r'/ }; text=${text//$'\n'/ }; printf '%s' "$text"; }
field() {
  local line prefix="$2: "
  [ -f "$1" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case "$line" in "$prefix"*) printf '%s\n' "${line#"$prefix"}"; return 0;; esac
  done < "$1"
}
# The read path without a subshell per field (UAK-003). `$(field F K)` is a fork: `next` paid about 100 of them.
#   fv FILE KEY       the first "KEY: value" of FILE into FV (empty when absent), like field, no process
#   state_load        every record on claims (tasks, claims, reviews, queue) and the backlog's IDs, one awk pass
#   sv KIND ID KEY    a field of that load into SV, no process (state_load first when TX changed)
#   git_dir_var DIR   the absolute git dir of a checkout into GD: .git read directly, git only when that fails
fv() {
  local line prefix="$2: "
  FV=
  [ -f "$1" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    case "$line" in "$prefix"*) FV=${line#"$prefix"}; return 0;; esac
  done < "$1"
}
state_load() {
  local k f
  [ -z "${UAK_S_VARS:-}" ] || unset $UAK_S_VARS
  set --
  for k in tasks claims reviews queue; do
    for f in "$TX/$k"/*.md; do [ ! -f "$f" ] || set -- "$@" "$f"; done
  done
  for f in "$TX"/reviews/*.reviewing; do [ ! -f "$f" ] || set -- "$@" "$f"; done
  [ ! -f "${BACKLOG:-}" ] || set -- "$@" "$BACKLOG"
  UAK_S_tasks= UAK_S_claims= UAK_S_reviews= UAK_S_queue= UAK_S_reviewing= UAK_S_backlog= UAK_S_VARS=
  [ "$#" -eq 0 ] || eval "$(awk -v backlog="${BACKLOG:-}" -f "$UAK_BIN/lib/state.awk" "$@")"
  UAK_S_TX=$TX
}
sv() {
  SV=
  # Each part checked on its own: the name is UAK_S_<kind>_<ID>_<Key> and nothing else. An ID from a record with a
  # colon reached ${…:offset}, whose arithmetic ran PATH[$(cmd)] (kit-r1, UAK-003). IDs are task IDs (ABC-123).
  case "$1" in tasks|claims|reviews|queue|reviewing) ;; *) return 0;; esac
  case "$2" in [A-Z]*-[0-9]*) ;; *) return 0;; esac
  case "$2" in *[!A-Z0-9-]*|*-*-*|*-*[!0-9]*) return 0;; esac
  case "$3" in [A-Za-z]*) ;; *) return 0;; esac
  case "$3" in *[!A-Za-z0-9-]*) return 0;; esac
  [ "${UAK_S_TX:-}" = "$TX" ] || state_load
  eval "SV=\${UAK_S_$1_${2//-/_}_${3//-/_}-}"
}
git_dir_var() {
  local line=
  GD=
  if [ -d "$1/.git" ]; then GD=$1/.git
  elif [ -f "$1/.git" ]; then
    IFS= read -r line < "$1/.git" || :
    line=${line%$'\r'}
    case "$line" in "gitdir: "?*) GD=${line#gitdir: };; esac
    case "$GD" in ''|/*|[A-Za-z]:[\\/]*) ;; *) GD=$1/$GD;; esac
  fi
  [ -n "$GD" ] && [ -d "$GD" ] || GD=$(git -C "$1" rev-parse --absolute-git-dir 2>/dev/null) || GD=
}
clock_now() {
  NOW=${UAK_NOW:-$(date +%s)}
  case "$NOW" in ''|*[!0-9]*) die "UAK_NOW must be epoch seconds.";; esac
  case "$LEASE" in ''|*[!0-9]*|0) die "UAK_LEASE_SECONDS must be positive.";; esac
}
identity() {
  [ -n "$AGENT" ] || AGENT=$(git config --get uak.agent 2>/dev/null || true)
  [ -n "$AGENT" ] || AGENT=$HUMAN
  # Why (MLB hackathon): 16 "No identity" errors, mostly reviews and inbox from the main checkout, where several
  # agents share one git config: a per-command prefix is the only identity that cannot leak to another agent.
  [ -n "$AGENT" ] || UAK_CODE=no-identity die "No identity. Prefix the command with your agent name: UAK_AGENT=NAME bash .uak/bin/uak $CMD ... (inside a task worktree, .uak-env sets it). A human: UAK_HUMAN=NAME."
  case "$AGENT" in *[!A-Za-z0-9_.-]*) die "Identity: use letters, digits, dot, dash or underscore.";; esac
}
cleanup() {
  # --json: what the envelope needs from this run, written before the temp dir goes.
  if [ -n "${UAK_JSON_META:-}" ]; then
    { printf 'id\t%s\n' "${ID:-}"
      [ -z "${ID:-}" ] || [ -z "${TX:-}" ] || [ ! -f "$TX/tasks/$ID.md" ] || printf 'state\t%s\n' "$(field "$TX/tasks/$ID.md" State)"
    } >> "$UAK_JSON_META" 2>/dev/null
  fi
  # Why: only the temp dir created by this invocation is removed.
  if [ -n "$TXROOT" ] && [ -n "${TMP_BASE:-}" ]; then
    case "$TXROOT" in "$TMP_BASE"/hack.??????)
      # Links into real node_modules go first, so the recursive delete can never follow one into its target.
      if [ -f "$TXROOT/gate-links" ]; then
        while IFS= read -r l; do
          case "$(uname -s 2>/dev/null)" in
            MINGW*|MSYS*|CYGWIN*) MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' cmd /c rmdir "$(cygpath -w "$l")" >/dev/null 2>&1 || rm -f "$l";;
            *) rm -f "$l";;
          esac
        done < "$TXROOT/gate-links"
      fi
      rm -rf "$TXROOT";;
    esac
  fi
}
# The command registry (lib/commands.tsv), read with builtins: every uak call reads it. Tab is IFS whitespace, so no
# field is ever empty (- stands for none); a CR from a CRLF checkout is dropped from the last field.
reg_find() { # NAME → REG_RUN REG_MUTATE REG_FILE REG_MCP (its first row); fails for an unknown command
  local n r m f p u
  REG_RUN= REG_MUTATE= REG_FILE= REG_MCP=
  while IFS=$'\t' read -r n r m f p u; do
    [ "$n" = "$1" ] || continue
    REG_RUN=$r REG_MUTATE=$m REG_FILE=$f REG_MCP=$p
    return 0
  done < "$UAK_BIN/lib/commands.tsv"
  return 1
}
reg_usage() {
  local n r m f p u
  while IFS=$'\t' read -r n r m f p u; do
    case "$n" in ''|'#'*) continue;; esac
    printf '%s\n' "${u%$'\r'}"
  done < "$UAK_BIN/lib/commands.tsv"
}
