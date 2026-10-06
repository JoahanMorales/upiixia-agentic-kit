# Async agent messaging on the claims branch; Bash 3.2+.
# Why: related tasks must notify each other without a human relay,
# and Git is the only channel shared by Claude Code, Cursor and Codex across machines.
# inbox/log.md es append-only: "- N | epoch | from | to | kind | task | text".
# Targets: agent:NAME, task:ID (reaches whoever holds it, now or later), all, human.
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
    for r in $(msg_related "$1"); do msg_append "task:$r" "$2" "$1" "$3"; done
    return 0
  fi
  for r in $(msg_related "$1"); do
    [ -f "$TX/claims/$r.md" ] || continue
    owner=$(field "$TX/claims/$r.md" Owner)
    case " $owners " in *" $owner "*) ;; *) owners="$owners $owner";; esac
  done
  for owner in $owners; do
    tasks=$(for r in $(msg_related "$1"); do
      [ -f "$TX/claims/$r.md" ] && [ "$(field "$TX/claims/$r.md" Owner)" = "$owner" ] && printf '%s ' "$r"
    done)
    msg_append "agent:$owner" integrated "$1" "$3 (affects: ${tasks% })"
  done
}
# Suggested reviewer: active agent (messages in the last 3 h), not the owner, with the fewest reviews.
# Why: at Hack-Nation 2 agents gave 51 of 70 review verdicts.
msg_pick_reviewer() {
  [ -f "$TX/$MSG_LOG" ] || return 0
  awk -F' [|] ' -v owner="$1" -v now="$NOW" '
    /^- [0-9]/ {
      from=$3
      if (from == owner || from == "scheduler" || from == "" ) next
      if (now - $2 <= 10800) active[from]=1
      if ($5 == "approve" || $5 == "reject") load[from]++
    }
    END { best=""; for (a in active) if (best == "" || load[a]+0 < load[best]+0 || (load[a]+0 == load[best]+0 && a < best)) best=a; print best }' "$TX/$MSG_LOG"
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
  awk -F' [|] ' -v me="$AGENT" -v owned=" $(msg_owned) " -v last="$(msg_last_read)" -v mode="$1" -v now="$NOW" '
    /^- [0-9]/ {
      n=substr($1, 3) + 0; from=$3; to=$4
      if (mode ~ /^task:/) { if (to != mode) next }
      else if (mode == "human") { if (to != "human") next }
      else {
        mine=(to == "agent:" me) || (to == "all" && from != me) || (to ~ /^task:/ && index(owned, " " substr(to, 6) " "))
        if (!mine || (mode == "unread" && n <= last)) next
      }
      age=int((now - $2) / 60)
      printf "#%d · %dm ago · %s → %s · %s · %s\n  %s\n", n, age, from, to, $5, $6, $7
    }' "$TX/$MSG_LOG"
}
msg_resolve_targets() {
  # Expands MSG_TO into canonical targets, one per line.
  case "$MSG_TO" in
    all|human) printf '%s\n' "$MSG_TO";;
    related:*)
      valid_id "${MSG_TO#related:}" || die "Invalid target: $MSG_TO"
      msg_related "${MSG_TO#related:}" | sed 's/^/task:/';;
    [A-Z]*-[0-9]*) valid_id "$MSG_TO" || die "Invalid ID: $MSG_TO"; printf 'task:%s\n' "$MSG_TO";;
    task:*) valid_id "${MSG_TO#task:}" || die "Invalid ID: $MSG_TO"; printf '%s\n' "$MSG_TO";;
    agent:*|*)
      local name=${MSG_TO#agent:}
      case "$name" in ''|*[!A-Za-z0-9_.-]*) die "Invalid target: use NAME, ID, related:ID, all or human.";; esac
      [ "$name" != "$AGENT" ] || die "Do not message yourself."
      printf 'agent:%s\n' "$name";;
  esac
}
msg_mutate() {
  local targets t
  targets=$(msg_resolve_targets) || exit $?
  [ -n "$targets" ] || die "$MSG_TO has no related tasks in TASKS.md (Depends on / Uses contract / Related)."
  MSG_SENT=
  for t in $targets; do msg_append "$t" "$MSG_KIND" "$MSG_TASK" "$MSG_TEXT"; done
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
