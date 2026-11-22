# A cache of the parsed claims state, keyed by the exact claims tip and base tip (UAK-004). Bash 3.2+, POSIX tools.
# Sourced after lib/core.sh (git_dir_var, state_load, sv). Why: `next` started 93 processes and `status` 61, most of
# them the temp clone, its fetch and coord_init; when the remote tips did not move since the last read, the state they
# rebuild is the same. A hit is builtins only (one cp when files are asked back); a miss costs nothing more.
#
#   cache_get CLAIMS BASE [DIR]  the entry for these tips (full SHAs: `git ls-remote origin refs/heads/claims
#                                refs/heads/BASE`, one call) into the UAK_S_* state, as state_load leaves it, and the
#                                files put with it into DIR. Fails (CACHE_WHY says why) and leaves the state untouched
#                                on any doubt: off, a mutation, no entry, another tip or format, a corrupt or partial
#                                file. A hit sets UAK_S_TX=$TX, so sv reads the cache and never reloads: set TX first.
#   cache_put [FILE...]          after state_load on the read clone $TX (coord_init first, so BACKLOG is its own):
#                                stores that state and FILEs (TXROOT's canonical-TASKS.md, coord-auth, ...) under the
#                                tips the clone holds itself (HEAD, refs/uak/config), never under a tip it was told.
#                                Refuses a clone whose tasks/claims/reviews/queue/backlog differ from its HEAD.
#   cache_drop                   removes every entry: call it on any mutation (a push moves the tip anyway).
#
# What is cached: record data only (Lease-Until, Updated, Freeze-Epoch are epochs written in records or PROJECT.md).
# Nothing derived from the clock is stored: leases, the freeze and every "min ago" are computed from NOW by the reader.
# Reads only: a command whose registry row has a mutation (REG_MUTATE other than -) never reads the cache, and
# neither does the tick transaction status/next run first (transaction sets it). UAK_CACHE=off turns it off.
#
# Where: <git common dir>/uak-cache/<claims>-<base>/ (state, files/), one per clone, shared by its worktrees; a put
# leaves only its own entry. Written in a temp dir beside it, then one mv: a reader sees a whole entry or none.
# The state file: a header line (format, kit version, both tips), "v NAME=VALUE." lines, "f NAME." lines, "end N".
# It is read with builtins, never eval'd or sourced: a NAME other than UAK_S_<letters, digits, _> or a list of IDs
# with a glob character makes the whole entry a miss, and a value is assigned as data (printf -v). Why (kit-r1,
# UAK-003): an ID with a colon from a claims record ran code through ${…:offset}; the cache keeps that guarantee.
CACHE_FORMAT=1

# cache_sha VALUE: a full hex object name (SHA-1 or SHA-256), lower case as git prints it.
cache_sha() {
  case "$1" in *[!0-9a-f]*) return 1;; esac
  [ "${#1}" -eq 40 ] || [ "${#1}" -eq 64 ]
}
# cache_dir: CACHE_DIR, <git common dir of $ROOT>/uak-cache. Builtins: .git and commondir read directly.
cache_dir() {
  local line=
  CACHE_DIR=
  [ -n "${ROOT:-}" ] || return 1
  git_dir_var "$ROOT"
  [ -n "$GD" ] || return 1
  if [ -f "$GD/commondir" ]; then
    IFS= read -r line < "$GD/commondir" || :
    line=${line%$'\r'}
    case "$line" in
      '') ;;
      /*|[A-Za-z]:[\\/]*) GD=$line;;
      *) GD=$GD/$line;;
    esac
  fi
  CACHE_DIR=$GD/uak-cache
}
# cache_header CLAIMS BASE: CACHE_HEADER, the first line of an entry. The kit version is in it: a new state.awk
# (another kit) never reads an older kit's entry.
cache_header() {
  local v=
  IFS= read -r v 2>/dev/null < "$UAK_BIN/../VERSION" || :
  v=${v%$'\r'}
  case "$v" in ''|*[!0-9A-Za-z.+-]*) v=unknown;; esac
  CACHE_HEADER="uak-state-cache $CACHE_FORMAT kit $v claims $1 base $2"
}
# cache_name NAME: a variable this cache may set (UAK_S_ and a word), never UAK_S_VARS or UAK_S_TX (rebuilt here).
cache_name() {
  case "$1" in UAK_S_VARS|UAK_S_TX|UAK_S_) return 1;; UAK_S_*) ;; *) return 1;; esac
  case "$1" in *[!A-Za-z0-9_]*) return 1;; esac
}
# cache_list_ok NAME VALUE: the ID lists are word-split and globbed by their readers (for id in $UAK_S_tasks).
cache_list_ok() {
  case "$1" in UAK_S_tasks|UAK_S_claims|UAK_S_reviews|UAK_S_queue|UAK_S_reviewing|UAK_S_backlog) ;; *) return 0;; esac
  case "$2" in *[*?[\\]*|*$'\t'*|*$'\r'*) return 1;; esac
}
cache_get() {
  local claims=${1:-} base=${2:-} dest=${3:-} entry line n=0 nv=0 count= i name f files= vars=
  local -a names values
  CACHE_WHY=
  [ "${UAK_CACHE:-on}" != off ] || { CACHE_WHY=off; return 1; }
  [ "${REG_MUTATE:-}" = - ] || { CACHE_WHY=mutation; return 1; }
  cache_sha "$claims" && cache_sha "$base" || { CACHE_WHY=bad-tip; return 1; }
  cache_dir || { CACHE_WHY=no-git-dir; return 1; }
  entry=$CACHE_DIR/$claims-$base
  [ -f "$entry/state" ] || { CACHE_WHY=no-entry; return 1; }
  cache_header "$claims" "$base"
  CACHE_WHY=corrupt
  {
    IFS= read -r line || return 1
    [ "${line%$'\r'}" = "$CACHE_HEADER" ] || { CACHE_WHY=other-key; return 1; }
    while IFS= read -r line; do
      line=${line%$'\r'}
      [ -z "$count" ] || return 1   # nothing after the end line
      case "$line" in
        'v '*.)
          line=${line#v }; line=${line%.}
          case "$line" in *=*) ;; *) return 1;; esac
          name=${line%%=*}
          cache_name "$name" && cache_list_ok "$name" "${line#*=}" || return 1
          names[nv]=$name; values[nv]=${line#*=}; nv=$((nv + 1)); n=$((n + 1));;
        'f '*.)
          f=${line#f }; f=${f%.}
          case "$f" in ''|.*|*[!A-Za-z0-9._-]*) return 1;; esac
          files="$files $f"; n=$((n + 1));;
        'end '*)
          count=${line#end }
          case "$count" in ''|*[!0-9]*) return 1;; esac;;
        *) return 1;;
      esac
    done
  } < "$entry/state" || return 1
  [ -n "$count" ] && [ "$count" -eq "$n" ] 2>/dev/null || return 1
  # The files first: a missing one (an entry pruned by another put meanwhile) is a miss with the state untouched.
  if [ -n "$dest" ] && [ -n "$files" ]; then
    set --
    for f in $files; do set -- "$@" "$entry/files/$f"; done
    [ -d "$dest" ] && cp -- "$@" "$dest/" 2>/dev/null || { CACHE_WHY=files; return 1; }
  fi
  [ -z "${UAK_S_VARS:-}" ] || unset $UAK_S_VARS
  UAK_S_tasks= UAK_S_claims= UAK_S_reviews= UAK_S_queue= UAK_S_reviewing= UAK_S_backlog=
  i=0
  while [ "$i" -lt "$nv" ]; do
    printf -v "${names[i]}" '%s' "${values[i]}"
    vars="$vars${vars:+ }${names[i]}"
    i=$((i + 1))
  done
  UAK_S_VARS=$vars UAK_S_TX=${TX:-} CACHE_WHY=
  return 0
}
cache_put() {
  local tip= base= dirty= line name val f n=0 tmp entry out e
  CACHE_WHY=
  [ "${UAK_CACHE:-on}" != off ] || { CACHE_WHY=off; return 1; }
  [ -n "${TX:-}" ] && [ "${UAK_S_TX:-}" = "$TX" ] || { CACHE_WHY=not-loaded; return 1; }
  cache_dir || { CACHE_WHY=no-git-dir; return 1; }
  # The tips the clone holds, and whether the records it was parsed from are its HEAD's: one git call for both.
  out=$(git -C "$TX" status --porcelain=v2 --branch --untracked-files=all -- tasks claims reviews queue backlog 2>/dev/null) ||
    { CACHE_WHY=git; return 1; }
  while IFS= read -r line; do
    line=${line%$'\r'}
    case "$line" in "# branch.oid "*) tip=${line#"# branch.oid "};; '#'*|'') ;; *) dirty=yes;; esac
  done <<EOF
$out
EOF
  [ -z "$dirty" ] || { CACHE_WHY=dirty; return 1; }
  base=$(git -C "$TX" rev-parse -q --verify 'refs/uak/config^{commit}' 2>/dev/null) || base=
  cache_sha "$tip" && cache_sha "$base" || { CACHE_WHY=no-tip; return 1; }
  for name in $UAK_S_VARS; do
    cache_name "$name" || { CACHE_WHY=bad-name; return 1; }
    val=${!name}
    case "$val" in *$'\n'*) CACHE_WHY=newline; return 1;; esac
    cache_list_ok "$name" "$val" || { CACHE_WHY=bad-list; return 1; }
  done
  for f in "$@"; do
    [ -f "$f" ] || { CACHE_WHY=no-file; return 1; }
    case "${f##*/}" in ''|.*|*[!A-Za-z0-9._-]*) CACHE_WHY=bad-file-name; return 1;; esac
  done
  [ -d "$CACHE_DIR" ] || mkdir -p "$CACHE_DIR" 2>/dev/null || { CACHE_WHY=mkdir; return 1; }
  entry=$CACHE_DIR/$tip-$base
  tmp=$CACHE_DIR/.tmp-$$-${RANDOM:-0}
  mkdir "$tmp" 2>/dev/null || { CACHE_WHY=mkdir; return 1; }
  if [ "$#" -gt 0 ]; then
    mkdir "$tmp/files" && cp -- "$@" "$tmp/files/" 2>/dev/null || { rm -rf "$tmp"; CACHE_WHY=copy; return 1; }
  fi
  cache_header "$tip" "$base"
  if ! {
    printf '%s\n' "$CACHE_HEADER"
    for name in $UAK_S_VARS; do printf 'v %s=%s.\n' "$name" "${!name}"; n=$((n + 1)); done
    for f in "$@"; do printf 'f %s.\n' "${f##*/}"; n=$((n + 1)); done
    printf 'end %s\n' "$n"
  } > "$tmp/state"; then
    rm -rf "$tmp"; CACHE_WHY=state; return 1
  fi
  # Same tips, same content: an entry another worktree just wrote stays.
  if [ -d "$entry" ]; then rm -rf "$tmp"
  else mv "$tmp" "$entry" 2>/dev/null || { rm -rf "$tmp"; [ -d "$entry" ] || { CACHE_WHY=mv; return 1; }; }
  fi
  # One entry per clone: older tips are never read again (a reader of one gets a miss, never a part of it).
  set --
  for e in "$CACHE_DIR"/* "$CACHE_DIR"/.tmp-*; do
    [ -e "$e" ] && [ "$e" != "$entry" ] && [ "$e" != "$tmp" ] && set -- "$@" "$e"
  done
  [ "$#" -eq 0 ] || rm -rf -- "$@" 2>/dev/null || :
  return 0
}
cache_drop() {
  cache_dir || return 0
  [ ! -d "$CACHE_DIR" ] || rm -rf -- "$CACHE_DIR" 2>/dev/null || :
}
# ---- The read cache (UAK-130): the claims clone a read just fetched, reused while it is young. ----
# status and next fetched claims on every call (3.7 s and 2.3 s measured; agents poll 2.7 times per `done`). A read
# whose last fetch is younger than `Read-Cache: N` seconds (PROJECT.md, default 20, 0 = off) copies the clone kept
# here instead of fetching, and says how old it is. Only reads ask (status_run); every write fetches as always, and a
# successful write refreshes the clone with what it pushed (rc_put in transaction), so an agent reads its own writes.
# Out of reach: other clones' writes, for up to N seconds (that is the trade; `status --fresh` forces a fetch).
#
#   rc_get   TX does not exist yet: on a hit it is made, a copy of the cached clone; RC_AGE is its age in s.
#   rc_put TX  keeps TX (clean, at the tip it just pushed or fetched; coord_init already ran: TXROOT/coord-source
#              holds PROJECT.md) with the time NOW and N. N=0 drops instead.
#   rc_drop  forgets it.
# Where: <git common dir>/uak-read-cache/: entries e-<NOW>-<pid>-<n>/ {stamp, tx/} and `current`, a file naming the
# live entry. An entry is built under a temp name, moved into place, then `current` is replaced by one rename: a reader
# sees a whole entry or none. The entry before the live one is kept for readers still copying it; older ones go.
# A simulated clock (UAK_NOW) turns it off unless UAK_READ_CACHE=on.
# The stamp names the remote URL and the base: another remote or base is a miss. NOW is the engine's clock (UAK_NOW).
RC_FORMAT=1
# A simulated clock (UAK_NOW) does not move between calls, so a window of seconds means nothing there: the suites of
# the kit, which read twice at one instant and compare, keep fetching unless a test asks (UAK_READ_CACHE=on).
rc_clock_ok() { [ -z "${UAK_NOW:-}" ] || [ "${UAK_READ_CACHE:-}" = on ]; }
rc_dir() { cache_dir || return 1; RC_DIR=${CACHE_DIR%/*}/uak-read-cache; }
# rc_basetip: RC_BASETIP, the base's tip as this checkout last saw it (a push or fetch of the base moves it). The base
# holds PROJECT.md and TASKS.md, which a read takes from the remote; the user's own push of them is read back at once.
rc_basetip() { RC_BASETIP=$(git -C "$ROOT" rev-parse -q --verify "refs/remotes/${REMOTE:-origin}/${BASE:-main}" 2>/dev/null) || RC_BASETIP=none; }
# rc_stamp ENTRY: RC_AT RC_TTL RC_URL RC_BASE RC_BT, or fails.
rc_stamp() {
  local l1 l2 l3 l4
  RC_AT= RC_TTL=
  { IFS= read -r l1 && IFS= read -r l2 && IFS= read -r l3 && IFS= read -r l4; } < "$1/stamp" 2>/dev/null || return 1
  case "$l1" in "uak-read-cache $RC_FORMAT at "*" ttl "*) ;; *) return 1;; esac
  l1=${l1#"uak-read-cache $RC_FORMAT at "}; RC_AT=${l1%% *}; RC_TTL=${l1##* }
  case "$RC_AT$RC_TTL" in ''|*[!0-9]*) return 1;; esac
  RC_URL=${l2#remote }; RC_BASE=${l3#base }; RC_BT=${l4#basetip }
  [ "$l2" != "$RC_URL" ] && [ "$l3" != "$RC_BASE" ] && [ "$l4" != "$RC_BT" ]
}
rc_get() {
  local cur name
  RC_AGE=
  [ "${UAK_CACHE:-on}" != off ] && [ "${READ_FRESH:-no}" != yes ] && [ "${REG_MUTATE:-}" = - ] || return 1
  rc_clock_ok || return 1
  case "${CMD:-}" in status|next) ;; *) return 1;; esac
  rc_dir || return 1
  IFS= read -r name < "$RC_DIR/current" 2>/dev/null || return 1
  case "$name" in e-*[!A-Za-z0-9._-]*|e-) return 1;; e-*) ;; *) return 1;; esac
  cur=$RC_DIR/$name
  rc_stamp "$cur" || return 1
  [ "$RC_URL" = "${REMOTE_URL:-}" ] && [ "$RC_BASE" = "${BASE:-}" ] || return 1
  rc_basetip; [ "$RC_BT" = "$RC_BASETIP" ] || return 1
  [ "$RC_TTL" -gt 0 ] && [ "$NOW" -ge "$RC_AT" ] && [ $((NOW - RC_AT)) -lt "$RC_TTL" ] || return 1
  mkdir "$TX" 2>/dev/null && cp -R "$cur/tx/." "$TX/" 2>/dev/null || { rm -rf "$TX"; return 1; }
  # The entry still existed when the copy ended: a copy of an entry pruned meanwhile is never used.
  [ -d "$cur/tx" ] || { rm -rf "$TX"; return 1; }
  RC_AGE=$((NOW - RC_AT))
}
rc_put() {
  local tx=$1 ttl entry tmp prev= name e
  [ "${UAK_CACHE:-on}" != off ] || return 1
  rc_clock_ok || return 1
  [ -d "$tx/.git" ] && [ -f "$TXROOT/coord-source" ] || return 1
  uak_cfg_var "$TXROOT/coord-source" Read-Cache 20; ttl=$CFG
  case "$ttl" in ''|*[!0-9]*) ttl=20;; esac
  [ "$ttl" -gt 0 ] || { rc_drop; return 0; }
  # Only a clone whose records are its HEAD's (UAK-006's lesson: never a state older than the tip it is kept under).
  [ -z "$(git -C "$tx" status --porcelain --untracked-files=no 2>/dev/null)" ] || return 1
  rc_dir || return 1
  mkdir -p "$RC_DIR" 2>/dev/null || return 1
  # A read that began before a write must not replace what the write refreshed.
  if IFS= read -r name < "$RC_DIR/current" 2>/dev/null && rc_stamp "$RC_DIR/$name"; then
    prev=$name
    [ "$NOW" -ge "$RC_AT" ] || return 1
  fi
  entry=e-$NOW-$$-${RANDOM:-0}
  tmp=$RC_DIR/.tmp-$$-${RANDOM:-0}
  mkdir "$tmp" 2>/dev/null && mkdir "$tmp/tx" && cp -R "$tx/." "$tmp/tx/" 2>/dev/null || { rm -rf "$tmp"; return 1; }
  rc_basetip
  printf 'uak-read-cache %s at %s ttl %s\nremote %s\nbase %s\nbasetip %s\n' "$RC_FORMAT" "$NOW" "$ttl" "${REMOTE_URL:-}" "${BASE:-}" "$RC_BASETIP" > "$tmp/stamp" || { rm -rf "$tmp"; return 1; }
  mv "$tmp" "$RC_DIR/$entry" 2>/dev/null || { rm -rf "$tmp"; return 1; }
  printf '%s\n' "$entry" > "$RC_DIR/.current-$$" && mv "$RC_DIR/.current-$$" "$RC_DIR/current" || { rm -rf "$RC_DIR/$entry" "$RC_DIR/.current-$$"; return 1; }
  set --
  for e in "$RC_DIR"/e-*; do
    [ -d "$e" ] && [ "${e##*/}" != "$entry" ] && [ "${e##*/}" != "$prev" ] && set -- "$@" "$e"
  done
  [ "$#" -eq 0 ] || rm -rf -- "$@" 2>/dev/null || :
  return 0
}
rc_drop() {
  rc_dir || return 0
  [ ! -d "$RC_DIR" ] || rm -rf -- "$RC_DIR" 2>/dev/null || :
}
