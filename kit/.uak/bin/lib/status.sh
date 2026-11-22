# Reads: status, digest, a task's detail, and the de-duplication of repeated reads in one session.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

# Failed checks pr-sync told about task $1 since $2 (the epoch the tip was recorded with `done`): RS_CI is the first
# name, plus " +N" for N more, RS_CI_AT when the first one was told. pr-sync stores only failures, per check name and
# without a SHA, as a message from `github` to task:ID ("#N CI failed: NAME URL"); the time of that message against the
# time of the tip is what ties a failure to this tip: a failure told before the tip was pushed again does not count.
# A later green run leaves no trace (pr-sync does not record passes), so a failure stays until the next `done`.
review_ci_failed() {
  local l r t from to kind task text seg name names= n=0
  RS_CI= RS_CI_AT=0 RS_CI_N=0
  [ -f "$TX/$MSG_LOG" ] || return 0
  while IFS= read -r l || [ -n "$l" ]; do
    case "$l" in "- "[0-9]*" | "[0-9]*" | github | "*"CI failed: "*) ;; *) continue;; esac
    r=${l#* | }; t=${r%% | *}; r=${r#* | }; from=${r%% | *}; r=${r#* | }; to=${r%% | *}; r=${r#* | }
    kind=${r%% | *}; r=${r#* | }; task=${r%% | *}; text=${r#* | }
    [ "$task" = "$1" ] && [ "$t" -ge "$2" ] 2>/dev/null || continue
    while :; do
      case "$text" in *"CI failed: "*) ;; *) break;; esac
      text=${text#*CI failed: }; name=${text%% https://*}; name=${name%% · *}
      case "|$names|" in *"|$name|"*) continue;; esac
      names="$names|$name"; n=$((n + 1))
      [ "$n" -gt 1 ] || { RS_CI=$name; RS_CI_AT=$t; }
    done
  done < "$TX/$MSG_LOG"
  RS_CI_N=$n
  [ "$n" -le 1 ] || RS_CI="$RS_CI +$((n - 1))"
}
# One derived sub-state per task in REVIEW, from what claims already hold (no new stored state): the task's Task-Tip, the
# last verdict (reviews/ID.md), a live reviewer lock (reviews/ID.reviewing), the human merge queue (queue/ID.md), the
# failed checks pr-sync told (messages from github) and the worklog (every `done` and `review` event). Sets RS_TEXT (the words every
# surface prints: lib/dash.py computes the same ones, test_review_substates compares them), RS_SINCE (epoch it began),
# RS_ROUNDS (review verdicts so far), RS_REJECTS, RS_LATE (yes: it sat longer than the review lease).
# Builtins only: status runs this per REVIEW task and its process count is tested.
# Why (the human, 2026-11-21): "a veces esta en In review por horas y visualmente no sabes si hubo un rejected, esta en
# CI o lo que sea"; v6.6: UAK-111 and UAK-114 went through a reject and several rounds under one REVIEW label.
review_substate() {
  local id=$1 tip rsha verdict rtime wl line t rest last_done=0 lock_who lock_sha lock_until lock_start qs reason qtime lease
  RS_TEXT= RS_SINCE=0 RS_ROUNDS=0 RS_REJECTS=0 RS_LATE=no
  fv "$TX/tasks/$id.md" Task-Tip; tip=$FV
  fv "$TX/tasks/$id.md" Worklog; wl=$FV
  fv "$TX/tasks/$id.md" Updated; last_done=$FV
  case "$last_done" in ''|*[!0-9]*) last_done=0;; esac
  if [ -n "$wl" ] && [ -f "$TX/$wl" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in "- "[0-9]*" | "*) ;; *) continue;; esac
      t=${line#- }; t=${t%% *}; rest=${line#*|}; rest=${rest#*|}; rest=${rest#*|}; rest=${rest# }
      case "$rest" in
        "done;"*) last_done=$t;;
        "review; reject;"*) RS_ROUNDS=$((RS_ROUNDS + 1)); RS_REJECTS=$((RS_REJECTS + 1));;
        "review; "*) RS_ROUNDS=$((RS_ROUNDS + 1));;
      esac
    done < "$TX/$wl"
  fi
  fv "$TX/reviews/$id.md" SHA; rsha=$FV
  fv "$TX/reviews/$id.md" Verdict; verdict=$FV
  fv "$TX/reviews/$id.md" Reviewed; rtime=$FV; case "$rtime" in ''|*[!0-9]*) rtime=$last_done;; esac
  fv "$TX/reviews/$id.reviewing" Reviewer; lock_who=$FV
  fv "$TX/reviews/$id.reviewing" SHA; lock_sha=$FV
  fv "$TX/reviews/$id.reviewing" Until; lock_until=$FV; case "$lock_until" in ''|*[!0-9]*) lock_until=0;; esac
  fv "$TX/reviews/$id.reviewing" Started; lock_start=$FV; case "$lock_start" in ''|*[!0-9]*) lock_start=$last_done;; esac
  if [ -n "$rsha" ] && [ "$rsha" = "$tip" ] && [ "$verdict" = approve ]; then
    fv "$TX/queue/$id.md" State; qs=$FV
    fv "$TX/queue/$id.md" Reason; reason=$FV
    fv "$TX/queue/$id.md" Updated; qtime=$FV; case "$qtime" in ''|*[!0-9]*) qtime=$rtime;; esac
    review_ci_failed "$id" "$last_done"
    if [ "$qs" = HUMAN ]; then RS_TEXT="approved, waiting for a human merge${reason:+: $reason}"; RS_SINCE=$qtime
    elif [ -n "$RS_CI" ]; then RS_TEXT="approved, CI failed: $RS_CI"; RS_SINCE=$RS_CI_AT
    else RS_TEXT="approved, waiting for the owner to merge"; RS_SINCE=$rtime; fi
  elif [ -n "$rsha" ] && [ "$rsha" = "$tip" ]; then
    RS_TEXT="changes requested (round $RS_ROUNDS)"; RS_SINCE=$rtime
  elif [ -n "$lock_who" ] && [ "$lock_sha" = "$tip" ] && [ "$NOW" -lt "$lock_until" ]; then
    RS_TEXT="in review by $lock_who"; RS_SINCE=$lock_start
  elif [ -n "$rsha" ]; then
    RS_TEXT="re-review (round $((RS_ROUNDS + 1)))"; RS_SINCE=$last_done
  else
    RS_TEXT="waiting for a reviewer"; RS_SINCE=$last_done
  fi
  lease=${REVIEW_LEASE:-0}; case "$lease" in ''|*[!0-9]*) lease=0;; esac
  if [ "$lease" -gt 0 ] && [ "$RS_SINCE" -gt 0 ] && [ $((NOW - RS_SINCE)) -gt "$lease" ]; then RS_LATE=yes; fi
  return 0
}
# Seconds as the board writes them: 45 s, 12 min, 3 h 05 min, 2 d 04 h.
review_age() {
  local s=$1; [ "$s" -ge 0 ] 2>/dev/null || s=0
  if [ "$s" -lt 90 ]; then RS_AGE="$s s"
  elif [ "$s" -lt 5400 ]; then RS_AGE="$(((s + 30) / 60)) min"
  elif [ "$s" -lt 172800 ]; then RS_AGE="$((s / 3600)) h $(printf %02d $(((s % 3600) / 60))) min"
  else RS_AGE="$((s / 86400)) d $(printf %02d $(((s % 86400) / 3600))) h"; fi
}
# "text · 12 min · 2 rejects · OVER the review lease": the line `status` and `status --task` print.
review_line() {
  review_substate "$1"; review_age $((NOW - RS_SINCE))
  RS_LINE="$RS_TEXT · $RS_AGE"
  [ "$RS_REJECTS" -eq 0 ] || RS_LINE="$RS_LINE · $RS_REJECTS reject$([ "$RS_REJECTS" -eq 1 ] || printf s)"
  [ "$RS_LATE" != yes ] || RS_LINE="$RS_LINE · OVER the review lease"
}
# What `uak board` prints after each REVIEW task (UAK-134): "ID<TAB>the line status prints" from a claims checkout $1 at epoch $2,
# the lease from PROJECT.md of the repository $3. Sourced by bin/board with lib/core.sh and lib/config.sh; no clone, no fetch.
board_substates() {
  local f id lease
  TX=$1; NOW=$2; MSG_LOG=inbox/log.md
  uak_cfg_var "$3/.uak/PROJECT.md" Lease-Seconds 1800; lease=$CFG
  case "$lease" in ''|*[!0-9]*) lease=1800;; esac
  uak_cfg_var "$3/.uak/PROJECT.md" Review-Lease-Seconds $((lease * 4)); REVIEW_LEASE=$CFG
  for f in "$TX"/tasks/*.md; do
    [ -f "$f" ] || continue
    fv "$f" State; [ "$FV" = REVIEW ] || continue
    fv "$f" ID; id=$FV; review_line "$id"
    printf '%s\t%s\n' "$id" "$RS_LINE"
  done
}
# Who ran the task, on which harness and model, from the task-session records (UAK-118): "agent-1 codex/model-a; ...".
review_harnesses() {
  local d f who h m seen=
  RS_HARNESS=
  for d in "$TX/meta/task-sessions/$1"/agent-*; do
    [ -d "$d" ] || continue
    who=${d##*/agent-}; h= m=
    for f in "$d"/session-*.md; do [ -f "$f" ] || continue; fv "$f" Harness; h=$FV; fv "$f" Model; m=$FV; done
    [ -n "$h$m" ] || continue
    RS_HARNESS="$RS_HARNESS${RS_HARNESS:+; }$who ${h:-unknown}/${m:-unknown}"
  done
}
print_task() {
  # Direct reads (fv), no state cache: handoff prints this inside its own transaction, after writing.
  local away updated
  RECORD="$TX/tasks/$ID.md"
  if [ -f "$RECORD" ]; then
    fv "$RECORD" Worklog; WL=$FV
    fv "$RECORD" State; local st=$FV; fv "$RECORD" Owner; say "$ID | $st | $FV"
    fv "$RECORD" Branch; say "Branch: $FV"
    fv "$RECORD" Worktree; say "Worktree: $FV"
    # What a reviewer needs, tasks published with uak plan included (they are not in main's TASKS.md). Why (audit,
    # Oct 2026): uak-reviewer is told to read PR, SHA, Verify and Paths here, and none of them was printed.
    fv "$RECORD" PR; [ -z "$FV" ] || say "PR: $FV"
    fv "$RECORD" Task-Tip; [ -z "$FV" ] || say "Task-Tip: $FV"
    if [ -f "$BACKLOG" ] && awk -v id="$ID" '/^## / && $2==id {f=1} END {exit !f}' "$BACKLOG"; then
      say "Paths: $(task_field Paths)"; say "Verify: $(task_field Verify)"
      task_criteria
    fi
    if [ "$st" = REVIEW ]; then review_line "$ID"; say "Review: $RS_LINE"; fi
    # Who took part and on what (UAK-118): where a reviewer or the human reads it, not on every live task (agents and
    # tests read the output of a CLAIMED task as it was).
    case "$st" in REVIEW|INTEGRATED)
      fv "$RECORD" Participants; [ -z "$FV" ] || say "Participants: $FV"
      review_harnesses "$ID"; [ -z "$RS_HARNESS" ] || say "Harness: $RS_HARNESS";;
    esac
    fv "$RECORD" Next; say "Next: $FV"
    fv "$RECORD" Progress; [ -z "$FV" ] || say "Progress: $FV"
    fv "$RECORD" Away; away=$FV; fv "$RECORD" Updated; updated=$FV
    [ -z "$away" ] || [ "$away" -lt "$updated" ] 2>/dev/null ||
      say "Away: its session closed $(( (NOW - away) / 60 )) min ago (uak away); the lease still runs"
    say "Worklog: $WL (claims branch)"
    if [ "$SHOW_SUMMARY" = yes ] || [ "$CMD" = handoff ]; then
      say "Live summary:"; summary_text
      [ ! -f "$TX/claims/$ID.md" ] || say "Read-token: $(read_token)"
    fi
    [ "$CMD" != handoff ] || coord_handoff
  elif [ -f "$TX/claims/$ID.md" ]; then
    # A claim without its task record yet (a claim in flight): never AVAILABLE. Why (Hacktoberfest): status said
    # AVAILABLE, wt new then failed with CONFLICT on the other agent's claim.
    fv "$TX/claims/$ID.md" State; local cst=$FV; fv "$TX/claims/$ID.md" Owner
    say "$ID | $cst | $FV"; say "Next: pick another task (uak next)"
  else
    load_task; say "$ID | AVAILABLE | $PRIORITY"; say "Next: $DEFAULT_NEXT"; say "Paths: $PATHS"; say "Verify: $VERIFY"
    task_criteria
  fi
}
print_status() {
  [ -z "$ID" ] || { print_task; coord_status_budget; say "$CLOCK_NOTE"; return; }
  # One awk pass loads every record (lib/state.awk); the loops below read variables, no process per field.
  local state count id n=0 version= until expiry scope= line
  state_load
  [ -z "${UAK_JSON_DATA:-}" ] || status_data
  # A CRLF checkout (Git for Windows) keeps the \r on a builtin read (UAK-014: "uak v5.11.0\r").
  IFS= read -r version 2>/dev/null < "$UAK_BIN/../VERSION" || version=${version:-?}; version=${version%$'\r'}
  say "uak v$version | remote claims | epoch $NOW | lease ${LEASE}s"
  for state in AVAILABLE CLAIMED BLOCKED REVIEW INTEGRATED CANCELLED; do
    count=0
    for id in $UAK_S_tasks; do sv tasks "$id" State; [ "$SV" != "$state" ] || count=$((count + 1)); done
    if [ "$state" = AVAILABLE ] && [ -f "$BACKLOG" ]; then
      for id in $UAK_S_backlog; do [ -f "$TX/tasks/$id.md" ] || count=$((count + 1)); done
    fi
    printf '%s=%s ' "$state" "$count"
  done
  printf '\n'; say "Claims (max 12; use --task ID):"
  for id in $UAK_S_claims; do
    [ "$n" -lt 12 ] || break
    n=$((n + 1))
    sv claims "$id" Lease-Until; until=$SV; expiry=active
    [ "$NOW" -lt "$until" ] || expiry=EXPIRED
    sv claims "$id" ID; line="$SV | "; sv claims "$id" State; line="$line$SV | "; sv claims "$id" Owner
    say "$line$SV | $expiry | until $until"
  done
  n=0
  for id in $UAK_S_tasks; do
    sv tasks "$id" State; [ "$SV" = REVIEW ] || continue
    [ "$n" -gt 0 ] || say "Review (what each REVIEW task waits for; --task ID has the detail):"
    [ "$n" -lt 12 ] || break
    n=$((n + 1)); review_line "$id"; say "$id | $RS_LINE"
  done
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in "# UAK_SMOKE_SCOPE: "*) scope=${line#"# UAK_SMOKE_SCOPE: "}; scope=${scope%$'\r'}; break;; esac
  done 2>/dev/null < "$ROOT/.uak/bin/smoke"
  say "Smoke: ${scope:-scope not declared; check .uak/bin/smoke}"
  say "Next: run uak next."
  coord_status_budget; say "$CLOCK_NOTE"
}
print_digest() {
  say "Human digest | epoch $NOW | remote claims"; found=no
  for f in "$TX"/tasks/*.md; do
    [ -f "$f" ] || continue
    state=$(field "$f" State)
    case "$state" in REVIEW|BLOCKED)
      found=yes
      say "$(field "$f" ID) | $state | $(field "$f" Owner) | PR $(field "$f" PR)"
      say "  $(field "$f" Next)"
      ;;
    esac
  done
  [ "$found" = yes ] || say "No pending reviews or blockers."
  for f in "$TX"/tasks/*.md; do
    [ -f "$f" ] || continue
    m=$(task_stalled "$f"); [ -n "$m" ] || continue
    say "$(field "$f" ID) | STALLED | $(field "$f" Owner) | no work moved in $m min · $(field "$f" Progress | awk -F' · ' '{print $1 " · " $2}')"
  done
  [ ! -f "$TX/DECISIONS.md" ] || grep '^-' "$TX/DECISIONS.md" | tail -n 5
  freeze_warning
  human_msgs=$(msg_select human | tail -n 10)
  [ -z "$human_msgs" ] || { say "Agent messages for humans (last 5):"; say "$human_msgs"; }
  # Capacity: tasks waiting vs agents online and idle. The commands for it are human ones (`up`, `graph --assign`),
  # so the human's digest is where they come up. Why (MLB hackathon): `up` 0 calls, `graph --assign` 3.
  local avail idle online
  avail=$(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG" 2>/dev/null | while read -r t; do
    st=$(field "$TX/tasks/$t.md" State); [ -z "$st" ] || [ "$st" = AVAILABLE ] && echo "$t"; done | wc -l | tr -d ' ')
  msg_seen_all > "$TXROOT/seen"
  online=$(awk -v now="$NOW" -v p="$(msg_presence)" '$1 == "A" {a[$2] = 1} $1 == "H" {h[$2] = 1} $1 == "S" && now - $3 <= p {s[$2] = 1}
    END {for (n in s) if (!(n in a) && !(n in h) && n != "scheduler" && n != "github") print n}' "$TXROOT/seen")
  local busy=' ' c n wait_word; idle=0
  for c in "$TX"/claims/*.md; do [ -f "$c" ] || continue; case "$(field "$c" State)" in CLAIMED|BLOCKED) busy="$busy$(field "$c" Owner) ";; esac; done
  for n in $online; do case "$busy" in *" $n "*) ;; *) idle=$((idle + 1));; esac; done
  if [ "${avail:-0}" -ge 3 ] && [ "$idle" -eq 0 ]; then
    say "Capacity: $avail tasks wait and no idle agent is online. More hands: bash .uak/bin/uak up N --tool claude (one worktree and agent each), or uak graph --assign for who takes what next."
  elif [ "${avail:-0}" -gt 0 ] && [ "$idle" -gt 0 ]; then
    [ "$avail" -eq 1 ] && wait_word="1 task waits" || wait_word="$avail tasks wait"
    say "Capacity: $wait_word, $idle idle agent(s) online: uak graph --assign suggests who takes which."
  fi
  # The bill, from what every machine published (uak tokens --publish; the Stop, session-start and Codex hooks do it
  # every 30 min), with how many machines that is and what share nobody's task owns.
  # Why (deus-ex-machina, DevDay): tokens from 1 of 3 Macs, 100 % and 78 % in "main"; the line gave no hint of either.
  if ls "$TX"/tokens/*.md >/dev/null 2>&1; then
    local th=' ' npub=0 nall h f
    for f in "$TX"/tokens/*.md; do [ -f "$f" ] || continue; h=${f##*/}; th="$th${h%.md} "; npub=$((npub + 1)); done
    nall=$npub
    for f in "$TX"/blackbox/*.md; do
      [ -f "$f" ] || continue; h=${f##*-}; h=${h%.md}
      case "$th" in *" $h "*) ;; *) th="$th$h "; nall=$((nall + 1));; esac
    done
    sed -n 's/^- //p' "$TX"/tokens/*.md | awk -F' [|] ' -v npub="$npub" -v nall="$nall" '{t = $6 + $7 + $8 + $9; T += t; R += $8; k[$1] += t}
      function M(n) { return n >= 1e6 ? sprintf("%.1fM", n / 1e6) : sprintf("%.0fk", n / 1e3) }
      END { if (!T) exit; b = ""; for (x in k) if (x != "main" && (b == "" || k[x] > k[b])) b = x
            printf "Tokens: %s, cache hit %d%%%s", M(T), 100 * R / T, (b != "" ? sprintf(", top task %s %s", b, M(k[b])) : "")
            if (nall > npub) printf ", from %d of %d machines", npub, nall
            if (k["main"] > 0) { p = int(100 * k["main"] / T + 0.5); printf " · main (coordination and work outside tasks) %d%%", p
              if (p > 50) printf " WARNING: above 50%%, per-task cost is not measurable (start tasks with wt new)" }
            printf " · detail: uak tokens --team\n" }'
  fi
  say "Rule: no answer in 15 min → recorded reversible decision, take another task."
  say "Everything on one page (progress, agents, conversation, reviews, black box): bash .uak/bin/uak dash --watch --open"
}
# `uak --json status`: one row per task (records on claims, then backlog tasks nobody claimed yet) for lib/json.sh.
status_data() {
  local id rid st lu exp
  printf 'data\ttasks\n' >> "$UAK_JSON_META"
  { for id in $UAK_S_tasks; do
      sv tasks "$id" ID; rid=$SV; sv tasks "$id" State; st=$SV
      sv tasks "$id" Lease-Until; lu=$SV; case "$lu" in ''|*[!0-9]*) lu=0;; esac
      exp=no; is_reserved "$st" && [ "$st" != REVIEW ] && [ "$lu" -gt 0 ] && [ "$NOW" -ge "$lu" ] && exp=yes
      sv tasks "$id" Owner
      # A task in REVIEW also carries its sub-state (UAK-134): the same words and epoch as `status`, the verdict count as the round.
      if [ "$st" = REVIEW ]; then review_substate "$id"; printf 'task\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$rid" "$st" "$SV" "$lu" "$exp" "$RS_TEXT" "$RS_SINCE" "$RS_ROUNDS"
      else printf 'task\t%s\t%s\t%s\t%s\t%s\n' "$rid" "$st" "$SV" "$lu" "$exp"; fi
    done
    for id in $UAK_S_backlog; do
      [ -f "$TX/tasks/$id.md" ] || printf 'task\t%s\tAVAILABLE\t-\t0\tno\n' "$id"
    done; } >> "$UAK_JSON_DATA"
}
# Repeated reads: the same `status`/`next`/`digest` output in the same agent session prints one line.
# The session is the harness process (grandparent of uak); a new session or --full prints everything.
# Why (Reap buildathon): agents ran status 258 times and inbox 295 times; most outputs were identical and
# every copy stayed in context for the rest of the session ("reading the same thing over and over").
# Session key: the nearest ancestor that is the agent harness (claude, codex, cursor, gemini, aider, node),
# else the grandparent. Every tool call is a new shell, but the harness process lives as long as the session.
session_key() { session_key_var; printf '%s' "$SESSION_KEY"; }
# One ps for the whole process table, walked in awk, once per call (UAK-003): a ps, two awks and a tr per level were
# up to 40 processes. Same answer: the nearest harness ancestor, else the grandparent, else (Git Bash: no ps -o)
# the session id the session-start hook wrote to <git dir>/uak-live.
session_key_var() {
  [ -z "${SESSION_KEY_DONE:-}" ] || return 0
  SESSION_KEY_DONE=1
  SESSION_KEY=$(ps -A -o pid= -o ppid= -o comm= 2>/dev/null | awk -v start="$PPID" '
    # Only "PID PPID COMM" rows: a ps that ignored -o (a header, other columns) is no table; uak-live keys it then.
    $1 !~ /^[0-9]+$/ || $2 !~ /^[0-9]+$/ { bad = 1 }
    { pp[$1] = $2; cm[$1] = tolower($3) }
    END { if (bad) exit
      p = start
      for (i = 0; i < 8; i++) {
        if (p !~ /^[0-9]+$/ || p == 0 || p == 1 || !(p in pp)) break
        if (cm[p] ~ /claude|codex|cursor|gemini|aider/ || cm[p] ~ /^node/ || cm[p] ~ /\/node$/) { printf "%s", p; exit }
        p = pp[p] }
      if ((start in pp) && pp[start] ~ /^[0-9]+$/) printf "%s", pp[start] }')
  case "$SESSION_KEY" in ''|*[!0-9]*)
    SESSION_KEY=
    git_dir_var "$ROOT"
    if [ -n "$GD" ] && [ -f "$GD/uak-live" ]; then
      local first=
      IFS=' 	' read -r first _ < "$GD/uak-live" || :
      [ -z "$first" ] || SESSION_KEY=$(printf '%s' "$first" | cksum | awk '{print $1}')
    fi;;
  esac
}
# The output with what changes on every call taken out (epoch, clock lines), into SEEN_TEXT: builtins only.
seen_normal() {
  local line pre rest
  SEEN_TEXT=
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in Clock*|'Remote clock'*|CLOCK_SKEW*) continue;; esac
    # The time a task has spent in its REVIEW sub-state grows with every call: it is not "something new" (UAK-119).
    case "$line" in "Review: "*|[A-Z]*-[0-9]*" | "*" · "[0-9]*)
      pre=${line%% · [0-9]*}
      if [ "$pre" != "$line" ]; then
        rest=${line#"$pre · "}
        case "$rest" in *" · "*) rest=" · ${rest#* · }";; *) rest=;; esac
        line=$pre$rest
      fi;;
    esac
    case "$line" in *"epoch "[0-9]*)
      pre=${line%%epoch [0-9]*}; rest=${line#"$pre"epoch }
      while :; do case "$rest" in [0-9]*) rest=${rest#?};; *) break;; esac; done
      line=$pre$rest;;
    esac
    SEEN_TEXT="$SEEN_TEXT$line
"
  done <<EOF_SEEN
$1
EOF_SEEN
}
# seen_print KEY TEXT: TEXT, or "= unchanged" when this session already saw the same TEXT in the last 30 min.
# <git dir>/uak-seen.KEY holds "SESSION EPOCH" and the normalized text it saw (read back with builtins, no cksum).
seen_print() {
  local key=$1 out=$2 gp prev line t=0
  git_dir_var "$ROOT"
  if [ "$FULL" = yes ] || [ "${UAK_DEDUPE:-on}" = off ] || [ -z "$GD" ]; then
    printf '%s\n' "$out"; [ -z "$GD" ] || [ ! -e "$GD/uak-seen.$key" ] || rm -f "$GD/uak-seen.$key" 2>/dev/null; return 0
  fi
  session_key_var; gp=$SESSION_KEY
  case "$gp" in ''|*[!0-9]*) printf '%s\n' "$out"; [ ! -e "$GD/uak-seen.$key" ] || rm -f "$GD/uak-seen.$key" 2>/dev/null; return 0;; esac
  seen_normal "$out"
  prev=
  if [ -f "$GD/uak-seen.$key" ]; then
    { IFS= read -r line || :; while IFS= read -r t || [ -n "$t" ]; do prev="$prev$t
"; done; } < "$GD/uak-seen.$key"
    set -- $line
  else set --; fi
  if [ "${1:-}" = "$gp" ] && [ "$prev" = "$SEEN_TEXT" ] && [ "$((NOW - ${2:-0}))" -lt 1800 ]; then
    say "= unchanged since $(((NOW - $2) / 60)) min ago (uak $key). Nothing new. Waiting for something? bash .uak/bin/uak wait ID --for approve|integrated|message (one call). --full reprints."
    return 0
  fi
  printf '%s\n' "$out"
  printf '%s %s\n%s' "$gp" "$NOW" "$SEEN_TEXT" > "$GD/uak-seen.$key" 2>/dev/null || true
}
# Once per 12 h per checkout: say early when PRs cannot be opened by the agent. The file holds the real epoch it ran,
# read with builtins (bash 4.2+ printf %()T); bash 3.2 keeps the find -mmin check.
# Why (Reap buildathon): a new checkout reached claims and reviews before finding out gh was missing.
preflight_note() {
  local at= real=
  git_dir_var "$ROOT"; [ -n "$GD" ] || return 0
  printf -v real '%(%s)T' -1 2>/dev/null || real=
  case "$real" in
    ''|*[!0-9]*) [ ! -f "$GD/uak-preflight" ] || [ -z "$(find "$GD/uak-preflight" -mmin -720 2>/dev/null)" ] || return 0
      touch "$GD/uak-preflight" 2>/dev/null;;
    *) [ ! -f "$GD/uak-preflight" ] || { IFS= read -r at < "$GD/uak-preflight" || :; }
      case "$at" in ''|*[!0-9]*) ;; *) [ $((real - at)) -ge 43200 ] || [ "$at" -gt "$real" ] || return 0;; esac
      printf '%s\n' "$real" > "$GD/uak-preflight" 2>/dev/null;;
  esac
  if ! command -v gh >/dev/null 2>&1; then
    say "PREFLIGHT: gh is not installed; the agent cannot open PRs. bash .uak/bin/wt pr prints the URL for the human."
  elif ! gh auth status >/dev/null 2>&1; then
    say "PREFLIGHT: gh is not logged in (gh auth login); until then bash .uak/bin/wt pr prints the PR URL for the human."
  fi
}
# 30 min before the freeze, every next/digest says it once. Why (Reap buildathon): 6 PRs were still open at
# the extended deadline; nobody had been told that unfinished work would not get in.
freeze_warning() {
  local f; coord_cfg Freeze-Epoch 0 2>/dev/null; f=$coord_v; case "$f" in ''|*[!0-9]*) return 0;; esac
  [ "$f" -gt 0 ] && [ "$NOW" -lt "$f" ] && [ $((f - NOW)) -le 1800 ] || return 0
  say "FREEZE in $(((f - NOW + 59) / 60)) min: finish the criterion and run uak done, or release; after the freeze a task needs a human uak allow."
}
# status and next: the deadline reconcile (a tick transaction) first, then the read on its fresh clone.
# The reconcile is housekeeping: if it fails, status/next still answer from a plain read. Why (MLB hackathon): a failed
# tick made `uak status` and `uak next` exit with GIT_ERROR on Cursor/Windows.
status_run() {
  local saved_cmd=$CMD saved_id=$ID out rc=0 line rc_gen0
  RC_AGE=
  # A read younger than Read-Cache seconds is served from the clone the last read or write kept (lib/cache.sh,
  # rc_get): no fetch and no tick (the deadline reconcile ran with that fetch; leases and "min ago" are computed from
  # NOW by the readers). --fresh and UAK_CACHE=off always fetch.
  ATTEMPT=read; TX="$TXROOT/try-read"
  rc_gen; rc_gen0=$RC_GEN   # before any fetch: a write that begins after this keeps a stale read out of the cache
  if rc_get; then
    COORD_INITIALIZED_TX=
  else
  CMD=tick; ID=; QUIET=yes
  # The tick's subshell also hands back what its coord_init read (lease, backlog, owners): the read below runs on the
  # same clone, so a second coord_init (6 git calls and 4 awks) read the same files again.
  if ( transaction; printf '%s\n' "$TX" "${COORD_INITIALIZED_TX:-}" "${LEASE:-}" "${REVIEW_LEASE:-}" "${BACKLOG:-}" "${OWNERS:-}" > "$TXROOT/tick-tx" ) 2> "$TXROOT/tick-error"; then
    { IFS= read -r TX; IFS= read -r line; IFS= read -r LEASE; IFS= read -r REVIEW_LEASE; IFS= read -r BACKLOG; IFS= read -r OWNERS; } < "$TXROOT/tick-tx"
    COORD_INITIALIZED_TX=; [ "$line" != "$TX" ] || [ ! -f "$BACKLOG" ] || COORD_INITIALIZED_TX=$TX
    # Keep what was just fetched (or pushed by the tick) for the next read.
    rc_put "$TX" read "$rc_gen0" || :
  else
    # No remote at all: an explicit read-only mode (the fetch already proved it, no extra ls-remote).
    if grep -q 'Remote unreachable' "$TXROOT/tick-error"; then CMD=$saved_cmd; coord_degraded_status; exit 0; fi
    CMD=$saved_cmd; ATTEMPT=read; fresh_state; COORD_INITIALIZED_TX=
    say "NOTE: deadline reconcile skipped ($(grep -m 1 -E 'ERROR|CONFLICT' "$TXROOT/tick-error" | cut -c 1-160)); showing the remote state." >&2
  fi
  fi
  CMD=$saved_cmd; ID=$saved_id; QUIET=no; coord_init
  coord_clock
  # The output is taken whole, then deduplicated in this shell: a pipe into seen_print was two more subshells.
  case "$CMD" in
    status) out=$(print_status) || rc=$?; seen_print "status${ID:+-$ID}" "$out"; budget_note; rc_age_line; return "$rc";;
    next) out=$(coord_next) || rc=$?; seen_print next "$out"; budget_note; preflight_note; rc_age_line;;
  esac
}
# The TOKENS_BUDGET line of `tokens --budget-check` (UAK-133) for the task asked (status --task ID) or the agent's live task
# (the one `next` shows), when Token-Budget is set in PROJECT.md. This machine's transcripts only, no fetch; tokens keeps the
# total 5 min and refreshes it in the background: a call prints the last finished scan and never waits for one. Nothing without a budget (no process started) or without --json's text.
# Why (v6.7.0, left open): the warning existed only as a command nobody calls.
budget_note() {
  local id=${ID:-} owner state who=${AGENT:-} line
  [ -z "${UAK_JSON_META:-}" ] || return 0
  uak_cfg_var "$ROOT/.uak/PROJECT.md" Token-Budget; [ -n "$CFG" ] || return 0
  case "$CFG" in -*|*[!0-9.,_kKmMbB' ']*) return 0;; esac   # not a positive number: nothing to warn (UAK-143)
  if [ -z "$id" ]; then
    [ -n "$who" ] || who=$(git config --get uak.agent 2>/dev/null) || :
    [ -n "$who" ] || return 0
    [ "${UAK_S_TX:-}" = "$TX" ] || state_load
    for state in CLAIMED BLOCKED REVIEW; do
      for owner in ${UAK_S_claims:-}; do
        sv claims "$owner" Owner; [ "$SV" = "$who" ] || continue
        sv claims "$owner" State; [ "$SV" = "$state" ] || continue
        id=$owner; break
      done
      [ -z "$id" ] || break
    done
  fi
  [ -n "$id" ] || return 0
  line=$(bash "$UAK_BIN/tokens" --budget-check "$id" --local 2>/dev/null) || return 0
  [ -z "$line" ] || say "$line"
}
# The last line of a read served from the cache (the first line of next and status is parsed: bin/up reads it). --json gets it as the claims_age key (json.sh), never as text.
rc_age_line() {
  [ -n "${RC_AGE:-}" ] || return 0
  if [ -n "${UAK_JSON_META:-}" ]; then printf 'claims_age\t%s\n' "$RC_AGE" >> "$UAK_JSON_META" 2>/dev/null || :
  else say "claims as of $RC_AGE s ago"; fi
}
digest_run() { local out rc=0; ATTEMPT=1; fresh_state; out=$(print_digest) || rc=$?; seen_print digest "$out"; return "$rc"; }
