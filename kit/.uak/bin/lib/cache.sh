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
# here instead of fetching, and says how old it is (first line). Only status and next ask (status_run); every write
# fetches as always, and a successful write refreshes the clone with what it pushed (rc_put in transaction), so an
# agent reads its own writes. Out of reach: other clones' writes, for up to N seconds (that is the trade; `--fresh`
# forces a fetch). inbox, board, timeline and metrics never read it (docs/CLI.md, Read cache).
#
#   rc_get          TX does not exist yet: on a hit it is made, a copy of the cached clone; RC_AGE is its age in s.
#                   Any entry that is not a whole, clean clone is a miss.
#   rc_gen          RC_GEN, this clone's write generation: take it BEFORE the fetch a read may put.
#   rc_put TX read GEN0    keeps a read's clone; refused when a write of this clone began since GEN0 (that read may hold
#                          a state older than what the write pushed).
#   rc_put TX write        keeps a writer's clone (ordered by claims tip like any put); counts one more write.
#   rc_drop         forgets every entry and counts a write.
# Order is the generation, not a clock: every writer bumps `gen` (under the lock) when it starts (rc_drop) and again when
# it puts its own state; a reader's put compares `gen` with the value it saw before its fetch, under the same lock as
# the rename of the entry, so check and replace are one step against a concurrent put (kit-r2, review of d68b644).
# Where: <git common dir>/uak-read-cache/: entries e-<NOW>-<pid>-<n>/ {stamp, tx/}, `current` (names the live entry),
# `gen`, and `lock/` (mkdir lock; one older than a minute is stale). An entry is built under a temp name, moved into
# place and `current` replaced by one rename: a reader sees a whole entry or none. The entry before the live one is
# kept for readers still copying it; older ones go. The stamp names the remote URL, the base and the base tip this
# checkout last saw. NOW is the engine's clock (UAK_NOW); a simulated clock turns the cache off unless UAK_READ_CACHE=on.
RC_FORMAT=2
# A simulated clock (UAK_NOW) does not move between calls, so a window of seconds means nothing there: the suites of
# the kit, which read twice at one instant and compare, keep fetching unless a test asks (UAK_READ_CACHE=on).
rc_clock_ok() { [ -z "${UAK_NOW:-}" ] || [ "${UAK_READ_CACHE:-}" = on ]; }
rc_dir() { cache_dir || return 1; RC_DIR=${CACHE_DIR%/*}/uak-read-cache; }
# rc_line FILE: RC_L1, the first line of FILE, silently (the redirect error goes first: bash prints it otherwise).
rc_line() { RC_L1=; [ -f "$1" ] || return 1; IFS= read -r RC_L1 2>/dev/null < "$1" || [ -n "$RC_L1" ]; }
rc_gen() {
  RC_GEN=0
  rc_dir || return 0
  rc_line "$RC_DIR/gen" || return 0
  case "$RC_L1" in ''|*[!0-9]*) ;; *) RC_GEN=$RC_L1;; esac
}
# The lock is a directory holding its owner's pid. A holder that is not alive (kill -0) is cleared at once; a lock
# older than a minute goes too (another host, a recycled pid). A lock whose pid file is not written yet is a live one.
rc_lock() {
  local i=0 pid dead
  while ! mkdir "$RC_DIR/lock" 2>/dev/null; do
    pid=
    [ ! -f "$RC_DIR/lock/pid" ] || IFS= read -r pid 2>/dev/null < "$RC_DIR/lock/pid" || :
    pid=${pid%$'\r'}
    case "$pid" in
      ''|*[!0-9]*) ;;
      *) if ! kill -0 "$pid" 2>/dev/null; then
           # One waiter wins the rename; if it moved a lock that is not the dead one's (someone took it meanwhile),
           # it puts it back.
           dead=$RC_DIR/.dead-$$-${RANDOM:-0}
           if mv "$RC_DIR/lock" "$dead" 2>/dev/null; then
             IFS= read -r i 2>/dev/null < "$dead/pid" || i=; i=${i%$'\r'}
             if [ "$i" = "$pid" ]; then rm -rf "$dead"; else mv "$dead" "$RC_DIR/lock" 2>/dev/null || rm -rf "$dead"; fi
           else
             # A directory that cannot be renamed (Windows, an open handle) is removed where it stands when it still
             # names the same dead pid.
             IFS= read -r i 2>/dev/null < "$RC_DIR/lock/pid" || i=; i=${i%$'\r'}
             [ "$i" != "$pid" ] || rm -rf "$RC_DIR/lock" 2>/dev/null
           fi
           i=0; continue
         fi;;
    esac
    i=$((i + 1))
    if [ "$i" -ge 100 ]; then
      [ -z "$(find "$RC_DIR/lock" -maxdepth 0 -mmin +1 2>/dev/null)" ] || rm -rf "$RC_DIR/lock" 2>/dev/null
      return 1
    fi
    sleep 0.05 2>/dev/null || sleep 1
  done
  printf '%s\n' "$$" > "$RC_DIR/lock/pid" 2>/dev/null || :
}
rc_unlock() { rm -rf "$RC_DIR/lock" 2>/dev/null || :; }
# rc_bump: one more write of this clone (under the lock).
rc_bump() { rc_gen; printf '%s\n' $((RC_GEN + 1)) > "$RC_DIR/.gen-$$" 2>/dev/null && mv "$RC_DIR/.gen-$$" "$RC_DIR/gen" 2>/dev/null || :; }
# rc_basetip: RC_BASETIP, the base's tip as this checkout last saw it (a push or fetch of the base moves it). The base
# holds PROJECT.md and TASKS.md, which a read takes from the remote; the user's own push of them is read back at once.
rc_basetip() { RC_BASETIP=$(git -C "$ROOT" rev-parse -q --verify "refs/remotes/${REMOTE:-origin}/${BASE:-main}" 2>/dev/null) || RC_BASETIP=none; }
# rc_stamp ENTRY: RC_AT RC_TTL RC_URL RC_BASE RC_BT RC_TIP, or fails.
rc_stamp() {
  local l1 l2 l3 l4 l5
  RC_AT= RC_TTL= RC_TIP=
  [ -f "$1/stamp" ] || return 1
  { IFS= read -r l1 && IFS= read -r l2 && IFS= read -r l3 && IFS= read -r l4 && IFS= read -r l5; } 2>/dev/null < "$1/stamp" || return 1
  case "$l1" in "uak-read-cache $RC_FORMAT at "*" ttl "*) ;; *) return 1;; esac
  l1=${l1#"uak-read-cache $RC_FORMAT at "}; RC_AT=${l1%% *}; RC_TTL=${l1##* }
  case "$RC_AT$RC_TTL" in ''|*[!0-9]*) return 1;; esac
  RC_URL=${l2#remote }; RC_BASE=${l3#base }; RC_BT=${l4#basetip }; RC_TIP=${l5#tip }
  [ "$l2" != "$RC_URL" ] && [ "$l3" != "$RC_BASE" ] && [ "$l4" != "$RC_BT" ] && [ "$l5" != "$RC_TIP" ]
}
rc_get() {
  local cur name
  RC_AGE=
  [ "${UAK_CACHE:-on}" != off ] && [ "${READ_FRESH:-no}" != yes ] && [ "${REG_MUTATE:-}" = - ] || return 1
  rc_clock_ok || return 1
  case "${CMD:-}" in status|next) ;; *) return 1;; esac
  rc_dir || return 1
  rc_line "$RC_DIR/current" || return 1
  name=$RC_L1
  case "$name" in e-*[!A-Za-z0-9._-]*|e-) return 1;; e-*) ;; *) return 1;; esac
  cur=$RC_DIR/$name
  rc_stamp "$cur" || return 1
  [ "$RC_URL" = "${REMOTE_URL:-}" ] && [ "$RC_BASE" = "${BASE:-}" ] || return 1
  rc_basetip; [ "$RC_BT" = "$RC_BASETIP" ] || return 1
  [ "$RC_TTL" -gt 0 ] && [ "$NOW" -ge "$RC_AT" ] && [ $((NOW - RC_AT)) -lt "$RC_TTL" ] || return 1
  [ -d "$cur/tx/.git" ] && mkdir "$TX" 2>/dev/null && cp -R "$cur/tx/." "$TX/" 2>/dev/null || { rm -rf "$TX"; return 1; }
  # A whole, clean clone at a commit, or a miss: an entry that is empty, cut short or pruned meanwhile is never used.
  if [ ! -d "$TX/.git" ] || ! git -C "$TX" rev-parse -q --verify HEAD >/dev/null 2>&1 ||
     [ -n "$(git -C "$TX" status --porcelain --untracked-files=no 2>/dev/null)" ]; then rm -rf "$TX"; return 1; fi
  mkdir -p "$TX/tasks" "$TX/claims" "$TX/worklog"
  RC_AGE=$((NOW - RC_AT))
}
# rc_put TX MODE [GEN0]: see the header.
rc_put() {
  local tx=$1 mode=${2:-read} gen0=${3:-} ttl entry tmp prev= e tip cmp
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
  case "$mode" in write) ;; *) case "$gen0" in ''|*[!0-9]*) return 1;; esac;; esac
  rc_gen; [ "$mode" = write ] || [ "$RC_GEN" = "$gen0" ] || return 1   # cheap early exit; checked again under the lock
  entry=e-$NOW-$$-${RANDOM:-0}
  tmp=$RC_DIR/.tmp-$$-${RANDOM:-0}
  rc_basetip
  tip=$(git -C "$tx" rev-parse -q --verify HEAD 2>/dev/null) && cache_sha "$tip" || return 1
  mkdir "$tmp" 2>/dev/null && mkdir "$tmp/tx" && cp -R "$tx/." "$tmp/tx/" 2>/dev/null || { rm -rf "$tmp"; return 1; }
  printf 'uak-read-cache %s at %s ttl %s\nremote %s\nbase %s\nbasetip %s\ntip %s\n' "$RC_FORMAT" "$NOW" "$ttl" "${REMOTE_URL:-}" "${BASE:-}" "$RC_BASETIP" "$tip" > "$tmp/stamp" || { rm -rf "$tmp"; return 1; }
  rc_lock || { rm -rf "$tmp"; return 1; }
  rc_gen
  if [ "$mode" != write ] && [ "$RC_GEN" != "$gen0" ]; then rm -rf "$tmp"; rc_unlock; return 1; fi
  [ "$mode" != write ] || rc_bump
  ! rc_line "$RC_DIR/current" || prev=$RC_L1
  # Order by the claims tip, writes included: an entry is replaced only by the same tip or a descendant of it. An older
  # put (a writer that was held up, a slower reader) keeps what is there; tips that cannot be compared (unrelated, or
  # further apart than the shallow clones reach) drop the cache, so the next read fetches.
  if [ -n "$prev" ] && rc_stamp "$RC_DIR/$prev" && [ "$RC_TIP" != "$tip" ]; then
    cmp=unknown
    if git -C "$tx" merge-base --is-ancestor "$RC_TIP" "$tip" 2>/dev/null; then cmp=newer
    elif git -C "$RC_DIR/$prev/tx" merge-base --is-ancestor "$tip" "$RC_TIP" 2>/dev/null; then cmp=older; fi
    case "$cmp" in
      newer) ;;
      older) rm -rf "$tmp"; rc_unlock; return 1;;
      *) rm -rf -- "$tmp" "$RC_DIR"/e-* "$RC_DIR/current" 2>/dev/null; rc_bump; rc_unlock; return 1;;
    esac
  fi
  if mv "$tmp" "$RC_DIR/$entry" 2>/dev/null && printf '%s\n' "$entry" > "$RC_DIR/.current-$$" && mv "$RC_DIR/.current-$$" "$RC_DIR/current" 2>/dev/null; then
    set --
    for e in "$RC_DIR"/e-*; do
      [ -d "$e" ] && [ "${e##*/}" != "$entry" ] && [ "${e##*/}" != "$prev" ] && set -- "$@" "$e"
    done
    [ "$#" -eq 0 ] || rm -rf -- "$@" 2>/dev/null || :
    rc_unlock; return 0
  fi
  rm -rf "$tmp" "$RC_DIR/$entry" "$RC_DIR/.current-$$"; rc_unlock; return 1
}
rc_drop() {
  rc_dir || return 0
  mkdir -p "$RC_DIR" 2>/dev/null || return 0
  rc_lock || :
  rc_bump
  rm -rf -- "$RC_DIR"/e-* "$RC_DIR/current" 2>/dev/null || :
  rc_unlock
}
