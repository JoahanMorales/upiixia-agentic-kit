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
# The same, from a given sender (the scheduler re-offers reviews in someone else's tick).
msg_append_as() { local AGENT=$1; shift; msg_append "$@"; }
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
# Presence: the last time each identity did anything visible on claims (an event, an inbox read, a message).
# Online = within Presence-Seconds (default 30 min); recent = within 3 h. Prints "S NAME EPOCH" per identity and
# "H NAME" for names that are humans (a meta/agents Human field, or a bare name like "ana" next to "ana-1").
# Why (MLB hackathon, v5 week): 67 review requests went to one named reviewer; that reviewer gave the verdict for
# 14. "Active" meant any message in 3 h, so closed sessions and even a human's own name got picked.
msg_presence() { local v; v=$(coord_config Presence-Seconds 1800 2>/dev/null); case "$v" in ''|*[!0-9]*) v=1800;; esac; printf '%s' "$v"; }
msg_seen_all() {
  local f
  set --   # file arguments, safe with spaces in the temp path (Windows profiles)
  for f in "$TX"/meta/agents/*.md "$TX"/inbox/read/*.md "$TX/$MSG_LOG"; do [ -f "$f" ] && set -- "$@" "$f"; done
  [ "$#" -gt 0 ] || return 0
  awk -F' [|] ' '
    FNR == 1 { name = FILENAME; sub(/.*\//, "", name); sub(/\.md$/, "", name); log_ = (FILENAME ~ /inbox\/log\.md$/) }
    log_ { if ($0 ~ /^- [0-9]/ && $3 != "" && $2 + 0 > seen[$3]) seen[$3] = $2 + 0; next }
    /^Role: human/ { human[name] = 1 }
    /^Updated: / { v = substr($0, 10) + 0; if (v > seen[name]) seen[name] = v }
    /^Human: / { h = substr($0, 8); if (h != "" && h != name) human[h] = 1 }
    /^Last: / { last[name] = substr($0, 7) + 0 }
    /^Session-Ended: / { ended[name] = substr($0, 16) + 0 }
    END {
      for (n in ended) if (ended[n] >= seen[n]) print "A", n
      for (n in seen) { p = n; if (sub(/-[A-Za-z0-9]+$/, "", p) && p !~ /-[A-Za-z0-9]+$/ && (p in seen)) human[p] = 1 }
      for (n in seen) print "S", n, seen[n]
      for (n in human) print "H", n
      for (n in last) print "L", n, last[n]
    }' "$@" 2>/dev/null
}
# Last time NAME was seen (0 if never).
msg_seen() { msg_seen_all | awk -v n="$1" '$1 == "S" && $2 == n { print $3; f = 1 } END { if (!f) print 0 }'; }
# NAME closed its session with `uak away` and did nothing since.
msg_away() { msg_seen_all | awk -v n="$1" '$1 == "A" && $2 == n { f = 1 } END { exit !f }'; }
# Suggested reviewer: an online agent first (seen within Presence-Seconds), else a recent one (3 h); never the owner,
# a retired identity, a human, or a name in MSG_PICK_EXCLUDE (already offered this SHA). Within a tier: whoever
# rejected the previous SHA (they know the diff), then another human's agent, then idle agents (no CLAIMED/BLOCKED
# task), then the fewest verdicts.
# Why: Hack-Nation (2 agents gave 51 of 70 verdicts), Reap (busy agents answered "I can't review now"), MLB
# (15 rotations went to identities without a session; the author's own human got its review twice; every
# re-review needed an extra message to the rejecter).
MSG_PICK_REJECTER= MSG_PICK_EXCLUDE=
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
  local c busy=' ' retired
  MSG_PICK_REJECTER=
  [ -f "$TX/$MSG_LOG" ] || return 0
  retired=" $(msg_retired) "
  for c in "$TX"/claims/*.md; do
    [ -f "$c" ] || continue
    case "$(field "$c" State)" in CLAIMED|BLOCKED) busy="$busy$(field "$c" Owner) ";; esac
  done
  MSG_PICK_REJECTER=$(msg_last_rejecter "$1" "${2:-none}")
  msg_seen_all > "$TXROOT/seen"
  awk -F' [|] ' -v owner="$1" -v now="$NOW" -v busy="$busy" -v retired="$retired" -v rej="$MSG_PICK_REJECTER" \
      -v excl=" $MSG_PICK_EXCLUDE " -v online="$(msg_presence)" -v sf="$TXROOT/seen" '
    function human(n) { if (n ~ /-[A-Za-z0-9]+$/) sub(/-[A-Za-z0-9]+$/, "", n); return n }
    BEGIN { while ((getline l < sf) > 0) { split(l, fl, " "); if (fl[1] == "H") ishuman[fl[2]] = 1; else if (fl[1] == "S") seen[fl[2]] = fl[3] + 0; else if (fl[1] == "A") away[fl[2]] = 1 } }
    /^- [0-9]/ { if ($5 == "approve" || $5 == "reject") load[$3]++ }
    function better(a, b) {
      if (tier[a] != tier[b]) return tier[a] > tier[b]
      if ((a == rej) != (b == rej)) return a == rej
      oa = human(a) != human(owner); ob = human(b) != human(owner)
      if (oa != ob) return oa
      ia = index(busy, " " a " ") == 0; ib = index(busy, " " b " ") == 0
      if (ia != ib) return ia
      return load[a]+0 < load[b]+0 || (load[a]+0 == load[b]+0 && a < b)
    }
    END {
      for (n in seen) {
        # Never "github" (the sender of pr-sync messages) nor a human (Role: human). Why (Chilangatón): 14 of 48 review
        # offers went to "github" (idle, no verdicts, so always the best pick) and 3 to the UAK_HUMAN name of a human;
        # each waited 15 min for the re-offer.
        if (n == owner || n == "scheduler" || n == "github" || n == "" || (n in ishuman) || (n in away) || index(retired, " " n " ") || index(excl, " " n " ")) continue
        age = now - seen[n]; if (age > 10800) continue
        tier[n] = (age <= online) ? 2 : 1
      }
      best = ""; for (a in tier) if (best == "" || better(a, best)) best = a; print best }' "$TX/$MSG_LOG"
}
# A review offer to one agent lapses after Review-Offer-Seconds (default 15 min) without `review --start` or a
# verdict on that SHA: the next status/next of any agent re-offers it to another agent, and after two lapses to
# all. The message says why, so nothing waits on a closed session. Run from the tick (status/next).
# Why (MLB hackathon, v5 week): median 55 min and p90 11 h from the review request to the verdict; 22 messages
# were humans or agents asking around "who can review X?".
msg_reoffer_reviews() {
  local c id tip owner last offer lt lto who n offered pr lk lu age note seen_t reviewer
  offer=$(coord_config Review-Offer-Seconds 900 2>/dev/null); case "$offer" in ''|*[!0-9]*) offer=900;; esac
  [ "$offer" -gt 0 ] && [ -f "$TX/$MSG_LOG" ] || return 0
  for c in "$TX"/claims/*.md; do
    [ -f "$c" ] && [ "$(field "$c" State)" = REVIEW ] || continue
    id=$(field "$c" ID); owner=$(field "$c" Owner); tip=$(field "$TX/tasks/$id.md" Task-Tip); pr=$(field "$c" PR)
    [ -n "$tip" ] || continue
    [ "$(field "$TX/reviews/$id.md" SHA)" != "$tip" ] || continue          # a verdict on this SHA exists
    lk="$TX/reviews/$id.reviewing"
    if [ -f "$lk" ] && [ "$(field "$lk" SHA)" = "$tip" ]; then
      lu=$(field "$lk" Until | tr -cd '0-9'); [ "$NOW" -ge "${lu:-0}" ] || continue   # someone is on it
    fi
    # The offers for this SHA: "N|epoch|to" of every review message on this task that names the SHA.
    awk -F' [|] ' -v id="$id" -v tip="$tip" '/^- [0-9]/ && $5 == "review" && $6 == id && index($7, tip) { print substr($1, 3) "|" $2 "|" $4 }' \
      "$TX/$MSG_LOG" > "$TXROOT/offers"
    last=$(tail -n 1 "$TXROOT/offers"); [ -n "$last" ] || continue
    lt=${last#*|}; lt=${lt%%|*}; lto=${last##*|}
    case "$lto" in agent:*) ;; *) continue;; esac                     # already offered to all
    age=$((NOW - lt)); [ "$age" -ge "$offer" ] || continue
    who=${lto#agent:}; who=${who%%,*}
    offered=$(cut -d'|' -f3 "$TXROOT/offers" | sed -n 's/^agent://p' | tr ',' ' ' | tr '\n' ' ')
    n=$(wc -l < "$TXROOT/offers" | tr -d ' ')
    seen_t=$(msg_seen "$who")
    if msg_away "$who"; then note="$who closed its session"
    elif [ "$seen_t" -le "$lt" ]; then note="$who has not been seen since the offer $((age / 60)) min ago"
    else note="$who did not start it in $((age / 60)) min"; fi
    MSG_PICK_EXCLUDE=$offered
    if [ "$n" -ge 3 ]; then reviewer=; else reviewer=$(msg_pick_reviewer "$owner" "$id"); fi
    MSG_PICK_EXCLUDE=
    if [ -n "$reviewer" ]; then
      msg_append_as scheduler "agent:$reviewer" review "$id" "$id ready for review (reassigned: $note): $pr (SHA $tip). /uak-review $id. Not free? Leave it: it moves to another agent in $((offer / 60)) min."
    else
      msg_append_as scheduler all review "$id" "$id ready for review (offered to ${offered% }; nobody started it): $pr (SHA $tip). First free agent: /uak-review $id"
    fi
  done
  return 0
}
# Unread messages that need an answer, addressed to another identity of the same human that went offline.
# `next` shows them so the human's live identity can answer or take over. Why (MLB hackathon): one human ran 8
# identities; reviews and requests kept reaching the ones whose sessions had closed, and nobody saw them.
msg_orphans() {
  [ -n "$AGENT" ] && [ -f "$TX/$MSG_LOG" ] || return 0
  msg_seen_all > "$TXROOT/seen"
  awk -F' [|] ' -v me="$AGENT" -v now="$NOW" -v online="$(msg_presence)" -v sf="$TXROOT/seen" '
    function human(n) { if (n ~ /-[A-Za-z0-9]+$/) sub(/-[A-Za-z0-9]+$/, "", n); return n }
    BEGIN { while ((getline l < sf) > 0) { split(l, fl, " "); if (fl[1] == "S") seen[fl[2]] = fl[3] + 0; else if (fl[1] == "L") last[fl[2]] = fl[3] + 0; else if (fl[1] == "A") away[fl[2]] = 1 } }
    /^- [0-9]/ {
      n = substr($1, 3) + 0
      if (now - $2 > 86400 || $5 !~ /^(review|request|reject|contract|approve)$/) next
      k = split($4, t, ",")
      for (i = 1; i <= k; i++) {
        if (t[i] !~ /^agent:/) continue
        x = substr(t[i], 7)
        if (x == me || human(x) != human(me) || (now - seen[x] <= online && !(x in away)) || n <= last[x] + 0) continue
        if (seen[x] > $2 && !(x in away)) continue      # it was seen after the message: it had its chance
        line[++c] = sprintf("  #%d · for %s (offline %d min) · %s %s · %s", n, x, (now - seen[x]) / 60, $5, $6, substr($7, 1, 110))
      }
    }
    END {
      if (!c) exit
      print "For your offline identities (" c "; nobody else will see them):"
      for (i = (c > 4 ? c - 3 : 1); i <= c; i++) print line[i]
      print "  Answer the sender (uak msg NAME --kind reply) or take the task over: uak handover ID --to " me " (allowed after 1 h"
      print "  offline). An identity you will not use again: UAK_HUMAN=NAME uak retire NAME (its reviews go to others)."
    }' "$TX/$MSG_LOG"
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
      local imp
      imp=$(bash "$UAK_BIN/map" impact --tasks --backlog "$BACKLOG" "${MSG_TO#impact:}" 2>&1) ||
        die "impact:${MSG_TO#impact:}: $(printf '%s' "$imp" | sed 's/^map: //' | head -n 1)"
      printf '%s\n' "$imp" | grep -E '^[A-Z][A-Z0-9]*-[0-9]+$' | grep -vx "${MSG_TO#impact:}" | sed 's/^/task:/'
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
      printf 'agent:%s\n' "$name"
      # Offline recipient: the message also goes to its live tasks (whoever takes them over reads it), and the sender
      # is told. Why (MLB hackathon): 26 requests and review offers went to identities that never came back.
      local seen c held=
      seen=$(msg_seen "$name")
      if [ $((NOW - seen)) -gt "$(msg_presence)" ] || msg_away "$name"; then
        for c in "$TX"/claims/*.md; do
          [ -f "$c" ] && [ "$(field "$c" Owner)" = "$name" ] || continue
          printf 'task:%s\n' "$(field "$c" ID)"; held="$held $(field "$c" ID)"
        done
        if [ "$seen" -eq 0 ]; then
          # The names that exist, same human first, so a typo or a gone identity (joahan-5) is fixed at once.
          local known; known=$(msg_seen_all | awk -v n="$name" -v now="$NOW" 'function h(x) { sub(/-[A-Za-z0-9]+$/, "", x); return x }
            $1 == "H" { hu[$2] = 1 } $1 == "S" { s[$2] = $3 }
            END { for (x in s) if (!(x in hu) && x != "scheduler" && x != "github") print (h(x) == h(n) ? 0 : 1), now - s[x], x }' | sort -k1,1n -k2,2n | head -n 6 | awk '{printf "%s%s", (NR > 1 ? ", " : ""), $3}')
          printf '%s\n' "$name has never been seen on claims (a typo?).${known:+ Known: $known.} It waits in its inbox until $name runs." >> "$TXROOT/msg-note"
        elif [ -n "$held" ]; then printf '%s\n' "$name $(msg_away "$name" && printf 'closed its session' || printf 'was last seen %s min ago' $(( (NOW - seen) / 60 ))): also sent to its task$held, so whoever takes it over reads it." >> "$TXROOT/msg-note"
        else printf '%s\n' "$name $(msg_away "$name" && printf 'closed its session' || printf 'was last seen %s min ago' $(( (NOW - seen) / 60 ))) and holds no task: it waits in its inbox. To reach someone working now: uak msg all, a task ID, or human." >> "$TXROOT/msg-note"; fi
      fi;;
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
  rm -f "$TXROOT/msg-note"
  targets=$(msg_resolve_targets) || exit $?
  # impact:ID with no importers is an answer, not an error: nobody to tell. Why (MLB hackathon): 3 exit-2 errors
  # for contracts on files no other task imports, and the agent then wondered whether the message went out.
  if [ -z "$targets" ]; then
    case "$MSG_TO" in impact:*) say "OK msg | no live task imports the files of ${MSG_TO#impact:}: no contract needed, nothing sent"; exit 0;; esac
  fi
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
