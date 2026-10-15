# Async agent messaging on the claims branch; Bash 3.2+.
# Why: related tasks must notify each other without a human relay,
# and Git is the only channel shared by Claude Code, Cursor and Codex across machines.
# inbox/log.md is append-only: "- N | epoch | from | to | kind | task | text".
# Targets: agent:NAME, task:ID (reaches whoever holds it, now or later), all, human.
# One message to several targets is ONE line with a comma list (task:A,task:B).
# Why (Reap buildathon): 63 of 365 lines were the same contract copied once per related task.
MSG_LOG=inbox/log.md
MSG_TO= MSG_KIND=info MSG_TASK= MSG_TEXT= MSG_SENT= MSG_ACK=no MSG_MODE=unread MSG_ACK_UPTO=0
msg_valid_kind() {
  case "$1" in info|request|contract|blocker|reply|review|approve|reject|integrated|human) return 0;; *) return 1;; esac
}
# IDs related to $1 both ways: Depends on, Uses contract, Related, Contracts.
msg_related() {
  [ -f "$BACKLOG" ] || return 0
  awk -v id="$1" '
    function ids(s,   out) { out=""; while (match(s, /[A-Z][A-Z0-9]*-[0-9][0-9][0-9]+/)) { out=out " " substr(s, RSTART, RLENGTH); s=substr(s, RSTART+RLENGTH) } return out }
    /^## / { cur=($2 ~ /^[A-Z][A-Z0-9]*-[0-9]+$/) ? $2 : ""; next }
    cur != "" {
      s=$0; gsub(/\*\*/, "", s); sub(/^[[:space:]]*-[[:space:]]*/, "", s)
      if (s ~ /^(Depends on|Uses contract|Related|Contracts)[[:space:]]*:/) {
        n=split(ids(s), a, " ")
        for (i=1; i<=n; i++) { if (cur==id) rel[a[i]]=1; else if (a[i]==id) rel[cur]=1 }
      }
    }
    END { for (k in rel) if (k != id) print k }' "$BACKLOG" | sort -u
}
msg_append() {
  # $1 to, $2 kind, $3 task, $4 text
  local n
  mkdir -p "$TX/inbox"
  [ -f "$TX/$MSG_LOG" ] || printf '%s\n' '# Agent messages' '' \
    'Append-only; use bash .uak/bin/uak msg / inbox. Format: - N | epoch | from | to | kind | task | text' '' > "$TX/$MSG_LOG"
  n=$(grep -c '^- [0-9]' "$TX/$MSG_LOG" || true); n=$((n + 1))
  printf -- '- %s | %s | %s | %s | %s | %s | %s\n' "$n" "$NOW" "${AGENT:-scheduler}" "$1" "$2" "${3:--}" \
    "$(one_line "$4" | tr '|' '/')" >> "$TX/$MSG_LOG"
  MSG_SENT="${MSG_SENT}${MSG_SENT:+, }#$n→$1"
}
msg_notify_related() {
  # $1 source task, $2 kind, $3 text.
  # integrated: one message per owner of currently claimed related tasks; free tasks start from main.
  # Why: at Hack-Nation 2026, 194 of 717 messages were duplicate per-task integrated notices.
  local r owner owners='' tasks
  if [ "$2" != integrated ]; then
    tasks=$(msg_related "$1" | sed 's/^/task:/' | tr '\n' ',' | sed 's/,$//')
    [ -z "$tasks" ] || msg_append "$tasks" "$2" "$1" "$3"
    return 0
  fi
  for r in $(msg_related "$1"); do
    [ -f "$TX/claims/$r.md" ] || continue
    [ "$(field "$TX/claims/$r.md" Owner)" != "$AGENT" ] || continue
    owner=$(field "$TX/claims/$r.md" Owner)
    case " $owners " in *" $owner "*) ;; *) owners="$owners $owner";; esac
  done
  # One line for every owner: "affects: HACK-003 ana-1, HACK-004 ana-2" (MLB: 3 lines per integration).
  [ -n "$owners" ] || return 0
  tasks=$(for r in $(msg_related "$1"); do
    [ -f "$TX/claims/$r.md" ] || continue; owner=$(field "$TX/claims/$r.md" Owner)
    [ "$owner" != "$AGENT" ] && printf '%s %s, ' "$r" "$owner"
  done)
  msg_append "$(printf 'agent:%s,' $owners | sed 's/,$//')" integrated "$1" "$3 (affects: ${tasks%, })"
}
# Suggested reviewer: an active agent (a message or an event in the last 3 h), never the owner nor a retired
# identity. Order: whoever rejected the previous SHA (they know the diff), then another human's agent, then
# idle agents (no CLAIMED/BLOCKED task), then the fewest verdicts.
# Why: Hack-Nation (2 agents gave 51 of 70 verdicts), Reap (busy agents answered "I can't review now"), MLB
# (15 rotations went to identities without a session; the author's own human got its review twice; every
# re-review needed an extra message to the rejecter).
MSG_PICK_REJECTER=
# Who rejected the current review of task $2 (not owner $1, not retired); empty otherwise.
msg_last_rejecter() {
  local rv="$TX/reviews/$2.md" who
  [ -f "$rv" ] && [ "$(field "$rv" Verdict)" = reject ] || return 0
  who=$(field "$rv" Reviewer)
  [ -n "$who" ] && [ "$who" != "$1" ] && [ ! -f "$TX/meta/retired/$who.md" ] && printf '%s' "$who"
  return 0
}
msg_retired() { local f; for f in "$TX"/meta/retired/*.md; do [ -f "$f" ] && basename "$f" .md; done | tr '\n' ' '; }
msg_pick_reviewer() {
  local c f busy=' ' seen=' ' rv="$TX/reviews/${2:-none}.md" retired
  MSG_PICK_REJECTER=
  [ -f "$TX/$MSG_LOG" ] || return 0
  retired=" $(msg_retired) "
  for c in "$TX"/claims/*.md; do
    [ -f "$c" ] || continue
    case "$(field "$c" State)" in CLAIMED|BLOCKED) busy="$busy$(field "$c" Owner) ";; esac
  done
  for f in "$TX"/meta/agents/*.md; do
    [ -f "$f" ] || continue
    u=$(field "$f" Updated); case "$u" in ''|*[!0-9]*) continue;; esac
    [ $((NOW - u)) -gt 10800 ] || seen="$seen$(basename "$f" .md) "
  done
  MSG_PICK_REJECTER=$(msg_last_rejecter "$1" "${2:-none}")
  awk -F' [|] ' -v owner="$1" -v now="$NOW" -v busy="$busy" -v seen="$seen" -v retired="$retired" -v rej="$MSG_PICK_REJECTER" '
    function human(n) { if (n ~ /-[A-Za-z0-9]+$/) sub(/-[A-Za-z0-9]+$/, "", n); return n }
    /^- [0-9]/ {
      from=$3
      if (from == owner || from == "scheduler" || from == "" || index(retired, " " from " ")) next
      if (now - $2 <= 10800) active[from]=1
      if ($5 == "approve" || $5 == "reject") load[from]++
    }
    function better(a, b) {
      if ((a == rej) != (b == rej)) return a == rej
      oa = human(a) != human(owner); ob = human(b) != human(owner)
      if (oa != ob) return oa
      ia = index(busy, " " a " ") == 0; ib = index(busy, " " b " ") == 0
      if (ia != ib) return ia
      return load[a]+0 < load[b]+0 || (load[a]+0 == load[b]+0 && a < b)
    }
    END {
      n = split(seen, s, " "); for (i = 1; i <= n; i++) if (s[i] != owner && !index(retired, " " s[i] " ")) active[s[i]] = 1
      best=""; for (a in active) if (best == "" || better(a, best)) best=a; print best }' "$TX/$MSG_LOG"
}
msg_owned() {
  local c
  for c in "$TX"/claims/*.md; do
    [ -f "$c" ] || continue
    [ "$(field "$c" Owner)" != "$AGENT" ] || field "$c" ID
  done | tr '\n' ' '
}
msg_last_read() {
  local v
  v=$(field "$TX/inbox/read/$AGENT.md" Last)
  case "$v" in ''|*[!0-9]*) v=0;; esac
  printf '%s' "$v"
}
msg_select() {
  # $1: unread | all | task:ID | human
  [ -f "$TX/$MSG_LOG" ] || return 0
  # A newer contract from the same sender about the same task supersedes the older one: the inbox shows only
  # the current one, the task thread marks the old one. Why (Reap buildathon): two contracts for the same
  # endpoint (#127, #129) arrived minutes apart and a consumer had to ask which shape was final.
  # A new identity (no read pointer yet) starts with the last 6 h, plus anything addressed to it by name.
  # Why (MLB hackathon): 5 identities joined mid-event and each got up to 22 unread "all" messages, 60 h old.
  local since=0; [ -f "$TX/inbox/read/$AGENT.md" ] || since=$((NOW - ${UAK_INBOX_FRESH_SECONDS:-21600}))
  awk -F' [|] ' -v me="$AGENT" -v owned=" $(msg_owned) " -v last="$(msg_last_read)" -v mode="$1" -v now="$NOW" -v since="$since" '
    FNR == NR { if ($0 ~ /^- [0-9]/ && $5 == "contract" && $6 != "-") latest[$3 "|" $6] = substr($1, 3) + 0; next }
    /^- [0-9]/ {
      n=substr($1, 3) + 0; from=$3; to=$4; sup=""
      if ($5 == "contract" && $6 != "-" && latest[from "|" $6] > n) {
        if (mode !~ /^task:/) next
        sup=" · superseded by #" latest[from "|" $6]
      }
      nt=split(to, t, ",")
      if (mode ~ /^task:/) { hit=0; for (i=1; i<=nt; i++) if (t[i] == mode) hit=1; if (!hit) next }
      else if (mode == "human") { hit=0; for (i=1; i<=nt; i++) if (t[i] == "human") hit=1; if (!hit) next }
      else {
        mine=0
        for (i=1; i<=nt; i++) mine = mine || (t[i] == "agent:" me) || (t[i] == "all" && from != me) || (t[i] ~ /^task:/ && index(owned, " " substr(t[i], 6) " "))
        if (!mine || (mode == "unread" && n <= last)) next
        if (mode == "unread" && $2 < since && to != "agent:" me) next
      }
      age=int((now - $2) / 60)
      printf "#%d · %dm ago · %s → %s · %s · %s%s\n  %s\n", n, age, from, to, $5, $6, sup, $7
    }' "$TX/$MSG_LOG" "$TX/$MSG_LOG"
}
msg_resolve_targets() {
  # Expands MSG_TO into canonical targets, one per line. "A,B" is a list; impact:ID asks the code map which tasks
  # import the files of ID (uak map impact). Why: related:ID only knows the Depends/Uses edges people wrote; at MLB
  # 27 tasks imported HACK-001's files and a contract change reached them by hand-picked messages.
  case "$MSG_TO" in
    *,*)
      local one all=$MSG_TO
      for one in $(printf '%s' "$all" | tr ',' ' '); do MSG_TO=$one; msg_resolve_targets; done
      MSG_TO=$all; return 0;;
    impact:*)
      valid_id "${MSG_TO#impact:}" || die "Invalid target: $MSG_TO"
      bash "$UAK_BIN/map" impact --tasks "${MSG_TO#impact:}" 2>/dev/null | grep -E '^[A-Z][A-Z0-9]*-[0-9]+$' | sed 's/^/task:/'
      return 0;;
    all|human) printf '%s\n' "$MSG_TO";;
    related:*)
      valid_id "${MSG_TO#related:}" || die "Invalid target: $MSG_TO"
      msg_related "${MSG_TO#related:}" | sed 's/^/task:/';;
    task:*) valid_id "${MSG_TO#task:}" || die "Invalid ID: $MSG_TO"; printf '%s\n' "$MSG_TO";;
    # A task ID only if it is one; "Ana-1" is an agent (Reap: 4 messages to Ana-N refused as "Invalid ID").
    *) if valid_id "$MSG_TO"; then printf 'task:%s\n' "$MSG_TO"; return 0; fi
      local name=${MSG_TO#agent:}
      case "$name" in ''|*[!A-Za-z0-9_.-]*) die "Invalid target: use NAME, ID, related:ID, all or human.";; esac
      [ "$name" != "$AGENT" ] || die "Do not message yourself."
      [ ! -f "$TX/meta/retired/$name.md" ] || die "$name is retired (no session). Message its task (ID), its human (human) or all."
      printf 'agent:%s\n' "$name";;
  esac
}
msg_mutate() {
  local targets words
  # An acknowledgment is `uak inbox --ack`, not a message every reader must load (Reap: 11 "Recibido" replies).
  words=$(printf '%s\n' "$MSG_TEXT" | wc -w | tr -d ' ')
  # Refused: a reply that starts like an ack, is short, and carries no SHA, number or path.
  if [ "$MSG_KIND" = reply ] && [ "$words" -le 12 ] && ! printf '%s\n' "$MSG_TEXT" | grep -q '[0-9/]' &&
     printf '%s\n' "$MSG_TEXT" | tr '[:upper:]' '[:lower:]' | grep -Eq '^[[:space:]]*(recibido|recibida|received|ok|okay|entendido|understood|gracias|thanks|thank you|ack|noted|copy|confirmado|confirmed|de acuerdo)([[:space:][:punct:]]|$)'; then
    die "An acknowledgment is not a message: run uak inbox --ack. Reply only with new information (SHA, file, decision)."
  fi
  [ "${#MSG_TEXT}" -le 1200 ] || die "Message over 1200 characters: keep 3 lines; put detail in the PR or a file and send its path."
  targets=$(msg_resolve_targets) || exit $?
  [ -n "$targets" ] || die "$MSG_TO has no related tasks (related:ID reads Depends on / Uses contract / Related in TASKS.md; impact:ID reads the code map)."
  targets=$(printf '%s\n' "$targets" | awk '!seen[$0]++')
  MSG_SENT=
  msg_append "$(printf '%s\n' "$targets" | tr '\n' ',' | sed 's/,$//')" "$MSG_KIND" "$MSG_TASK" "$MSG_TEXT"
}
msg_ack_mutate() {
  local current
  current=$(msg_last_read)
  [ "$MSG_ACK_UPTO" -gt "$current" ] || return 0
  mkdir -p "$TX/inbox/read"
  printf 'Agent: %s\nLast: %s\nUpdated: %s\n' "$AGENT" "$MSG_ACK_UPTO" "$NOW" > "$TX/inbox/read/$AGENT.md"
}
msg_inbox_run() {
  local out count
  ATTEMPT=read; fresh_state   # "read" does not clash with the --ack transaction try-N
  case "$MSG_MODE" in
    task:*) out=$(msg_select "$MSG_MODE"); say "INBOX ${MSG_MODE#task:} (full thread)"; say "${out:-  no messages}"; return 0;;
    human) out=$(msg_select human); say "INBOX humans"; say "${out:-  no messages}"; return 0;;
  esac
  out=$(msg_select "$MSG_MODE")
  count=$(printf '%s\n' "$out" | grep -c '^#' || true)
  if [ "$MSG_MODE" = peek ]; then
    out=$(msg_select unread); count=$(printf '%s\n' "$out" | grep -c '^#' || true)
    [ "$count" -gt 0 ] || return 0
  fi
  if [ "$count" -eq 0 ]; then say "INBOX $AGENT: no new messages"; return 0; fi
  # Unread but already shown to this session: one line, not the same messages again (Reap: 295 inbox calls).
  if [ "$MSG_MODE" = unread ] && [ "$MSG_ACK" = no ] && [ "${FULL:-no}" != yes ] && [ "${UAK_DEDUPE:-on}" != off ]; then
    local gp gd ids
    gp=$(session_key); gd=$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null) || gd=
    ids=$(printf '%s\n' "$out" | sed -n 's/^#\([0-9][0-9]*\) .*/\1/p' | tr '\n' ' ')
    case "$gp" in ''|*[!0-9]*) gp=;; esac
    if [ -n "$gp" ] && [ -n "$gd" ]; then
      if [ "$(cat "$gd/uak-seen.inbox" 2>/dev/null)" = "$gp $ids" ]; then
        say "INBOX $AGENT: $count unread already shown this session (#${ids%% *}..). Handle them, then uak inbox --ack. --full reprints."
        return 0
      fi
      printf '%s %s\n' "$gp" "$ids" > "$gd/uak-seen.inbox" 2>/dev/null || true
    fi
  fi
  say "INBOX $AGENT: $count message(s)$([ "$MSG_MODE" = all ] || printf ' unread')"
  say "$out"
  if [ "$MSG_MODE" = peek ] || [ "$MSG_ACK" = no ]; then
    say "Handle request/reject/contract/approve first; reply with uak msg NAME --kind reply TEXT; then uak inbox --ack."
    return 0
  fi
  MSG_ACK_UPTO=$(printf '%s\n' "$out" | sed -n 's/^#\([0-9][0-9]*\) .*/\1/p' | sort -n | tail -n 1)
  QUIET=yes; transaction; QUIET=no
  say "INBOX_ACK up to #$MSG_ACK_UPTO"
}
