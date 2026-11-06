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
