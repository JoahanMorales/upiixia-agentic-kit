# The backlog (TASKS.md as main and claims publish it) and the path rules: fields, Paths as reserved prefixes, OWNERS.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

# Reads one section; accepts - **Field:** value, **Field**: value and Field: value.
task_field() {
  awk -v id="$ID" -v key="$1" '
    /^## / { on=($2==id) }
    on {
      s=$0; gsub(/\*\*/, "", s); sub(/^[[:space:]]*-[[:space:]]*/, "", s);
      sub(/^[[:space:]]*/, "", s);
      if (index(s,key ":")==1) {
        sub(/^[^:]*:[[:space:]]*/, "", s); print s; exit
      }
    }' "$BACKLOG"
}
load_task() {
  [ -f "$BACKLOG" ] || die "Missing .uak/TASKS.md."
  awk -v id="$ID" '/^## / && $2==id {found=1} END {exit !found}' "$BACKLOG" ||
    UAK_CODE=not-in-backlog die "$ID is not in TASKS.md."
  PRIORITY=$(task_field Priority)
  case "$PRIORITY" in P0|P1|P2) ;; *) die "$ID needs Priority P0/P1/P2.";; esac
  PATHS=$(task_field "Paths")
  [ -n "$PATHS" ] || die "$ID needs Paths."
  DEPENDS=$(task_field "Depends on")
  VERIFY=$(task_field "Verify")
  [ -n "$VERIFY" ] || die "$ID needs Verify."
  DEFAULT_NEXT=$(task_field "Next step")
  # Test first in the default step too (v5.10): "Implement X and run" told agents to write the code first.
  [ -n "$DEFAULT_NEXT" ] || DEFAULT_NEXT="Write its tests, see them fail (uak red $ID), then implement until this passes: $VERIFY"
  normalize_paths "$PATHS" > "$TXROOT/paths-request" || die "Invalid paths in $ID."
}
# The task's acceptance criteria as the backlog has them (amended, plan tasks included): every line of its section
# that is not one of the keys above. Why (Hacktoberfest): reviewers of 11 tasks published with uak plan judged
# "from the summary", since main's TASKS.md did not have them and nothing printed them.
task_criteria() {
  local c
  c=$(awk -v id="$ID" '/^## / { on = ($2 == id); next } /^# / { on = 0 } on && NF {
      s = $0; gsub(/\*\*/, "", s); sub(/^[[:space:]]*[-*][[:space:]]*/, "", s)
      if (s ~ /^(Priority|Paths|Depends on|Verify|Next step|Estimate|Uses contract|Related|Contracts|Freeze-Allowed|Follow-up of)[[:space:]]*:/) next
      print }' "$BACKLOG" 2>/dev/null | head -n 30)
  [ -z "$c" ] || { say "Criteria:"; say "$c"; }
}
# Globs reserve their whole prefix; a root glob reserves the repo.
# Why: reversible over-reservation avoids conflicts a glob would hide.
# Paths as a list of reserved prefixes. Braces expand ("src/{api,web}/**" is src/api and src/web, not "src/{api"
# and "web}"), a trailing note in parentheses is dropped ("`src/a.ts` (new)"), and a whole segment in brackets is a
# name, not a glob (Next.js app/[slug]/page.tsx reserves that file, not all of app/). Why (audit, Oct 2026): the
# brace case let two claims share src/api, and [slug] made app/about collide with app/[slug].
normalize_paths() {
  # Accented capitals fold too (awk's tolower leaves UTF-8 bytes alone): Botón and BOTÓN are one file on macOS and
  # Windows. Byte-sequence replacements, the same under GNU and BSD sed.
  printf '%s\n' "$1" | sed 's/Á/á/g;s/É/é/g;s/Í/í/g;s/Ó/ó/g;s/Ú/ú/g;s/Ü/ü/g;s/Ñ/ñ/g;s/À/à/g;s/È/è/g;s/Ì/ì/g;s/Ò/ò/g;s/Ù/ù/g;s/Â/â/g;s/Ê/ê/g;s/Î/î/g;s/Ô/ô/g;s/Û/û/g;s/Ç/ç/g;s/Ã/ã/g;s/Õ/õ/g' | awk '
    BEGIN {bad=0}
    function emit(p,   n, seg, i, out, g) {
      gsub(sprintf("%c",96),"",p);
      sub(/^[[:space:]]*/,"",p); sub(/[[:space:]]*$/,"",p);
      sub(/[[:space:]]+\([^)]*\)$/,"",p);
      gsub(/\\/,"/",p); while(p ~ /^\.\//) sub(/^\.\//,"",p);
      gsub(/\/+/,"/",p);
      while(p ~ /\/\.\//) gsub(/\/\.\//,"/",p);
      sub(/\/\.$/,"",p); sub(/\/$/,"",p); p=tolower(p);
      if(p=="" || p ~ /^\// || p ~ /^[A-Za-z]:/ || p ~ /(^|\/)\.\.(\/|$)/) {bad=1; return}
      n=split(p,seg,"/"); out=""; g=0
      for(i=1;i<=n;i++) {
        if(seg[i] ~ /^\[.*\]$/) { out=out (out==""?"":"/") seg[i]; continue }
        if(seg[i] ~ /[*?[]/) { g=1; break }
        out=out (out==""?"":"/") seg[i]
      }
      if(out=="") out=".";
      print out;
    }
    function expand(p,   o, c, pre, body, post, n, alt, i) {
      o=index(p,"{"); if(!o) { emit(p); return }
      c=index(substr(p,o),"}"); if(!c) { emit(p); return }
      pre=substr(p,1,o-1); body=substr(p,o+1,c-2); post=substr(p,o+c)
      n=split(body,alt,"\001"); for(i=1;i<=n;i++) expand(pre alt[i] post)
    }
    {
      line=$0; out=""; depth=0
      for(i=1;i<=length(line);i++) { ch=substr(line,i,1)
        if(ch=="{") depth++; else if(ch=="}" && depth>0) depth--
        if(ch=="," && depth>0) ch="\001"
        out=out ch }
      n=split(out,a,",");
      for(i=1;i<=n;i++) expand(a[i]);
    }
    END {exit bad}' | sort -u
}
overlaps() {
  awk 'NR==FNR {a[++n]=$0;next}
    {for(i=1;i<=n;i++) if(a[i]=="." || $0=="." || a[i]==$0 ||
      index(a[i],$0 "/")==1 || index($0,a[i] "/")==1) exit 1}' "$1" "$2"
  [ "$?" -eq 1 ]
}
owner_rows() {
  [ -f "$OWNERS" ] || return 0
  awk -F'|' '{
    for(i=1;i<NF;i++) {
      p=$i; q=$(i+1); gsub(sprintf("%c",96),"",p); gsub(sprintf("%c",96),"",q);
      sub(/^[[:space:]]*/,"",p);sub(/[[:space:]]*$/,"",p);
      sub(/^[[:space:]]*/,"",q);sub(/[[:space:]]*$/,"",q);
      if(q ~ /^[A-Z][A-Z0-9]*-[0-9][0-9][0-9]+$/) print p "|" q
    }}' "$OWNERS"
}
# The task itself, or a task it follows up (the "Follow-up of" chain): a follow-up works on its parent's owned paths.
# Why (MLB hackathon): 4 black box notes; every `uak followup` of a task that owned paths in OWNERS.md was refused.
owner_is_self() {
  local id=$ID i=0
  while [ -n "$id" ] && [ "$i" -lt 6 ]; do
    [ "$1" != "$id" ] || return 0
    id=$(ID=$id task_field "Follow-up of" | grep -Eo '^[A-Z][A-Z0-9]*-[0-9]+' | head -n 1); i=$((i + 1))
  done
  return 1
}
# The owner task waits on this one (its Depends on reach $ID, directly or through others): it cannot start before
# this one is INTEGRATED, so there are never two writers and this task may write there first.
# Why (a team's black box, Oct 2026): the root task created a mock file in a mocks package OWNERS.md gave to a second
# task, which depends on the root: the root could never be claimed and `uak next` offered nothing at all.
owner_waits_on_me() {
  local queue=$1 seen=' ' cur d i=0
  while [ -n "$queue" ] && [ "$i" -lt 60 ]; do
    cur=${queue%% *}; queue=${queue#"$cur"}; queue=${queue# }; i=$((i + 1))
    case "$seen" in *" $cur "*) continue;; esac
    seen="$seen$cur "
    for d in $(ID=$cur task_field "Depends on" | awk '{ s = $0; gsub(/\([^)]*\)/, "", s)
        while (match(s, /[A-Z][A-Z0-9]*-[0-9][0-9][0-9]+/)) { print substr(s, RSTART, RLENGTH); s = substr(s, RSTART + RLENGTH) } }'); do
      [ "$d" != "$ID" ] || return 0
      queue="$queue $d"
    done
    queue=${queue# }
  done
  return 1
}
# Tasks whose Paths fall under an OWNERS row of a task that neither is them nor waits on them: claim refuses those
# for good. Prints "ID|pattern|owner". `plan` warns with it, `lint` fails on it.
owner_conflicts() { # [ID...] (default: every task of the backlog)
  local id ids=$*
  [ -n "$ids" ] || ids=$(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG" 2>/dev/null)
  owner_rows > "$TXROOT/oc-owners"
  [ -s "$TXROOT/oc-owners" ] || return 0
  for id in $ids; do
    ( ID=$id
      normalize_paths "$(task_field Paths)" > "$TXROOT/oc-paths" 2>/dev/null || exit 0
      while IFS='|' read -r pat owner; do
        [ -n "$pat" ] && [ "$owner" != "$id" ] || continue
        normalize_paths "$pat" > "$TXROOT/oc-owner" 2>/dev/null || continue
        overlaps "$TXROOT/oc-paths" "$TXROOT/oc-owner" || continue
        owner_is_self "$owner" || owner_waits_on_me "$owner" && continue
        # An owner already INTEGRATED: its row is advice and claim allows the path (check_owners), so no warning.
        # Why (UAK-019): plan said "can never be claimed" for UAK-018, which claimed fine.
        [ "$(field "$TX/tasks/$owner.md" State)" = INTEGRATED ] || printf '%s|%s|%s\n' "$id" "$pat" "$owner"
      done < "$TXROOT/oc-owners" )
  done
}
check_owners() {
  owner_rows > "$TXROOT/owners"
  while IFS='|' read -r pat owner; do
    [ -n "$pat" ] || continue
    normalize_paths "$pat" > "$TXROOT/owner-paths" || die "Invalid OWNERS pattern: $pat"
    if overlaps "$TXROOT/paths-request" "$TXROOT/owner-paths" && ! owner_is_self "$owner" && ! owner_waits_on_me "$owner"; then
      # An owner task already INTEGRATED no longer works there: its row is advice, not a lock. Why (Hacktoberfest): a
      # bug in lib/sse.ts, owned by an integrated task, stayed on main while 5 views copied a workaround around it.
      if [ "$(field "$TX/tasks/$owner.md" State)" = INTEGRATED ]; then
        DONE_HINT="NOTE: $pat belongs to $owner, already INTEGRATED: you may edit it; tell its users first: uak msg impact:$ID --kind contract \"what changed · what to do\""
        continue
      fi
      UAK_CODE=owned-path conflict "$pat belongs to $owner; split the work or request its contract. If the plan gave $ID that path on purpose: drop it (uak plan FILE --amend), give the OWNERS row to $ID, or make $owner depend on $ID."
    fi
  done < "$TXROOT/owners"
  while IFS= read -r path; do
    case "/$path/" in
      */package-lock.json/*|*/npm-shrinkwrap.json/*|*/pnpm-lock.yaml/*|*/*.lock/*|*/*.lockb/*|*/go.sum/*|*/gradle.lockfile/*|*/lockfiles/*|*/migrations/*|*/db/migration/*|*/contracts/*|*/types/*|*/shared-types/*|*/.github/workflows/*|*/.gitlab-ci.yml/*|*/azure-pipelines.yml/*)
        assigned=no
        printf '%s\n' "$path" > "$TXROOT/one-path"
        while IFS='|' read -r pat owner; do
          normalize_paths "$pat" > "$TXROOT/owner-paths" || die "Invalid OWNERS."
          if overlaps "$TXROOT/one-path" "$TXROOT/owner-paths" && { owner_is_self "$owner" || owner_waits_on_me "$owner" ||
             [ "$(field "$TX/tasks/$owner.md" State)" = INTEGRATED ]; }; then assigned=yes; fi
        done < "$TXROOT/owners"
        [ "$assigned" = yes ] || UAK_CODE=shared-unowned conflict "Shared resource without an owner in OWNERS.md: $path"
        ;;
    esac
  done < "$TXROOT/paths-request"
}
