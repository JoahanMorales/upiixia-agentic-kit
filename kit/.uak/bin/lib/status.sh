# Reads: status, digest, a task's detail, and the de-duplication of repeated reads in one session.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

print_task() {
  RECORD=$(task_file)
  if [ -f "$RECORD" ]; then
    WL=$(field "$RECORD" Worklog)
    say "$ID | $(field "$RECORD" State) | $(field "$RECORD" Owner)"
    say "Branch: $(field "$RECORD" Branch)"
    say "Worktree: $(field "$RECORD" Worktree)"
    # What a reviewer needs, tasks published with uak plan included (they are not in main's TASKS.md). Why (audit,
    # Oct 2026): uak-reviewer is told to read PR, SHA, Verify and Paths here, and none of them was printed.
    [ -z "$(field "$RECORD" PR)" ] || say "PR: $(field "$RECORD" PR)"
    [ -z "$(field "$RECORD" Task-Tip)" ] || say "Task-Tip: $(field "$RECORD" Task-Tip)"
    if [ -f "$BACKLOG" ] && awk -v id="$ID" '/^## / && $2==id {f=1} END {exit !f}' "$BACKLOG"; then
      say "Paths: $(task_field Paths)"; say "Verify: $(task_field Verify)"
      task_criteria
    fi
    say "Next: $(field "$RECORD" Next)"
    [ -z "$(field "$RECORD" Progress)" ] || say "Progress: $(field "$RECORD" Progress)"
    [ -z "$(field "$RECORD" Away)" ] || [ "$(field "$RECORD" Away)" -lt "$(field "$RECORD" Updated)" ] 2>/dev/null ||
      say "Away: its session closed $(( (NOW - $(field "$RECORD" Away)) / 60 )) min ago (uak away); the lease still runs"
    say "Worklog: $WL (claims branch)"
    if [ "$SHOW_SUMMARY" = yes ] || [ "$CMD" = handoff ]; then
      say "Live summary:"; summary_text
      [ ! -f "$(claim_file)" ] || say "Read-token: $(read_token)"
    fi
    [ "$CMD" != handoff ] || coord_handoff
  elif [ -f "$(claim_file)" ]; then
    # A claim without its task record yet (a claim in flight): never AVAILABLE. Why (Hacktoberfest): status said
    # AVAILABLE, wt new then failed with CONFLICT on the other agent's claim.
    say "$ID | $(field "$(claim_file)" State) | $(field "$(claim_file)" Owner)"; say "Next: pick another task (uak next)"
  else
    load_task; say "$ID | AVAILABLE | $PRIORITY"; say "Next: $DEFAULT_NEXT"; say "Paths: $PATHS"; say "Verify: $VERIFY"
    task_criteria
  fi
}
print_status() {
  [ -z "$ID" ] || { print_task; coord_status_budget; say "$CLOCK_NOTE"; return; }
  [ -z "${UAK_JSON_DATA:-}" ] || status_data
  say "uak v$(cat "$UAK_BIN/../VERSION" 2>/dev/null || printf '?') | remote claims | epoch $NOW | lease ${LEASE}s"
  for state in AVAILABLE CLAIMED BLOCKED REVIEW INTEGRATED CANCELLED; do
    count=0
    for f in "$TX"/tasks/*.md; do
      [ -f "$f" ] || continue
      [ "$(field "$f" State)" != "$state" ] || count=$((count + 1))
    done
    if [ "$state" = AVAILABLE ] && [ -f "$BACKLOG" ]; then
      extra=$(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG" | while IFS= read -r id; do
        [ -f "$TX/tasks/$id.md" ] || say "$id"
      done | awk 'END {print NR+0}')
      count=$((count + extra))
    fi
    printf '%s=%s ' "$state" "$count"
  done
  printf '\n'; say "Claims (max 12; use --task ID):"
  for f in "$TX"/claims/*.md; do
    [ -f "$f" ] || continue
    until=$(field "$f" Lease-Until); expiry=active
    [ "$NOW" -lt "$until" ] || expiry=EXPIRED
    say "$(field "$f" ID) | $(field "$f" State) | $(field "$f" Owner) | $expiry | until $until"
  done | head -n 12
  scope=$(sed -n 's/^# UAK_SMOKE_SCOPE: //p' "$ROOT/.uak/bin/smoke" 2>/dev/null | head -n 1)
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
  # The bill, from what every machine published (uak tokens --publish; the Stop hook does it every 30 min).
  if ls "$TX"/tokens/*.md >/dev/null 2>&1; then
    sed -n 's/^- //p' "$TX"/tokens/*.md | awk -F' [|] ' '{t = $6 + $7 + $8 + $9; T += t; R += $8; k[$1] += t}
      function M(n) { return n >= 1e6 ? sprintf("%.1fM", n / 1e6) : sprintf("%.0fk", n / 1e3) }
      END { if (!T) exit; b = ""; for (x in k) if (x != "main" && (b == "" || k[x] > k[b])) b = x
            printf "Tokens: %s, cache hit %d%%%s · detail: uak tokens --team\n", M(T), 100 * R / T, (b != "" ? sprintf(", top task %s %s", b, M(k[b])) : "") }'
  fi
  say "Rule: no answer in 15 min → recorded reversible decision, take another task."
  say "Everything on one page (progress, agents, conversation, reviews, black box): bash .uak/bin/uak dash --watch --open"
}
# `uak --json status`: one row per task (records on claims, then backlog tasks nobody claimed yet) for lib/json.sh.
status_data() {
  local f id st lu exp
  printf 'data\ttasks\n' >> "$UAK_JSON_META"
  { for f in "$TX"/tasks/*.md; do
      [ -f "$f" ] || continue
      id=$(field "$f" ID); st=$(field "$f" State); lu=$(field "$f" Lease-Until); case "$lu" in ''|*[!0-9]*) lu=0;; esac
      exp=no; is_reserved "$st" && [ "$st" != REVIEW ] && [ "$lu" -gt 0 ] && [ "$NOW" -ge "$lu" ] && exp=yes
      printf 'task\t%s\t%s\t%s\t%s\t%s\n' "$id" "$st" "$(field "$f" Owner)" "$lu" "$exp"
    done
    [ ! -f "$BACKLOG" ] || awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG" | while IFS= read -r id; do
      [ -f "$TX/tasks/$id.md" ] || printf 'task\t%s\tAVAILABLE\t-\t0\tno\n' "$id"
    done; } >> "$UAK_JSON_DATA"
}
# Repeated reads: the same `status`/`next`/`digest` output in the same agent session prints one line.
# The session is the harness process (grandparent of uak); a new session or --full prints everything.
# Why (Reap buildathon): agents ran status 258 times and inbox 295 times; most outputs were identical and
# every copy stayed in context for the rest of the session ("reading the same thing over and over").
# Session key: the nearest ancestor that is the agent harness (claude, codex, cursor, gemini, aider, node),
# else the grandparent. Every tool call is a new shell, but the harness process lives as long as the session.
session_key() {
  local pid=$PPID i=0 line ppid comm
  while [ "$i" -lt 8 ]; do
    case "$pid" in ''|*[!0-9]*|0|1) break;; esac
    line=$(ps -o ppid= -o comm= -p "$pid" 2>/dev/null) || break
    ppid=$(printf '%s\n' "$line" | awk '{print $1}'); comm=$(printf '%s\n' "$line" | awk '{print $2}' | tr '[:upper:]' '[:lower:]')
    case "$comm" in *claude*|*codex*|*cursor*|*gemini*|*aider*|node*|*/node) printf '%s' "$pid"; return 0;; esac
    pid=$ppid; i=$((i + 1))
  done
  # Git Bash has no `ps -o` and the harness is a native Windows process: use the session id that the
  # session-start hook wrote (Why, MLB hackathon: 4 Windows laptops never got "= unchanged").
  line=$(ps -o ppid= -p "$PPID" 2>/dev/null | tr -d ' ')
  case "$line" in ''|*[!0-9]*)
    line=$(awk '{print $1; exit}' "$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null)/uak-live" 2>/dev/null)
    [ -z "$line" ] || line=$(printf '%s' "$line" | cksum | awk '{print $1}');;
  esac
  printf '%s' "$line"
}
seen_print() {
  local out key=$1 gd gp sum prev
  out=$(cat)
  gp=$(session_key)
  gd=$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null) || gd=
  case "$gp" in ''|*[!0-9]*) gp=;; esac
  if [ "$FULL" = yes ] || [ -z "$gp" ] || [ -z "$gd" ] || [ "${UAK_DEDUPE:-on}" = off ]; then
    printf '%s\n' "$out"; [ -z "$gd" ] || rm -f "$gd/uak-seen.$key" 2>/dev/null; return 0
  fi
  sum=$(printf '%s\n' "$out" | sed 's/epoch [0-9][0-9]*//' | grep -Ev '^(Clock|Remote clock|CLOCK_SKEW)' | cksum | awk '{print $1}')
  prev=$(cat "$gd/uak-seen.$key" 2>/dev/null) || prev=
  set -- $prev
  if [ "${1:-}" = "$gp" ] && [ "${3:-}" = "$sum" ] && [ "$((NOW - ${2:-0}))" -lt 1800 ]; then
    say "= unchanged since $(((NOW - $2) / 60)) min ago (uak $key). Nothing new. Waiting for something? bash .uak/bin/uak wait ID --for approve|integrated|message (one call). --full reprints."
    return 0
  fi
  printf '%s\n' "$out"
  printf '%s %s %s\n' "$gp" "$NOW" "$sum" > "$gd/uak-seen.$key" 2>/dev/null || true
}
# Once per 12 h per checkout: say early when PRs cannot be opened by the agent.
# Why (Reap buildathon): a new checkout reached claims and reviews before finding out gh was missing.
preflight_note() {
  local gd; gd=$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null) || return 0
  [ ! -f "$gd/uak-preflight" ] || [ -z "$(find "$gd/uak-preflight" -mmin -720 2>/dev/null)" ] || return 0
  touch "$gd/uak-preflight" 2>/dev/null
  if ! command -v gh >/dev/null 2>&1; then
    say "PREFLIGHT: gh is not installed; the agent cannot open PRs. bash .uak/bin/wt pr prints the URL for the human."
  elif ! gh auth status >/dev/null 2>&1; then
    say "PREFLIGHT: gh is not logged in (gh auth login); until then bash .uak/bin/wt pr prints the PR URL for the human."
  fi
}
# 30 min before the freeze, every next/digest says it once. Why (Reap buildathon): 6 PRs were still open at
# the extended deadline; nobody had been told that unfinished work would not get in.
freeze_warning() {
  local f; f=$(coord_config Freeze-Epoch 0 2>/dev/null); case "$f" in ''|*[!0-9]*) return 0;; esac
  [ "$f" -gt 0 ] && [ "$NOW" -lt "$f" ] && [ $((f - NOW)) -le 1800 ] || return 0
  say "FREEZE in $(((f - NOW + 59) / 60)) min: finish the criterion and run uak done, or release; after the freeze a task needs a human uak allow."
}
# status and next: the deadline reconcile (a tick transaction) first, then the read on its fresh clone.
# The reconcile is housekeeping: if it fails, status/next still answer from a plain read. Why (MLB hackathon): a failed
# tick made `uak status` and `uak next` exit with GIT_ERROR on Cursor/Windows.
status_run() {
  local saved_cmd=$CMD saved_id=$ID
  CMD=tick; ID=; QUIET=yes
  if ( transaction; printf '%s\n' "$TX" > "$TXROOT/tick-tx" ) 2> "$TXROOT/tick-error"; then
    TX=$(cat "$TXROOT/tick-tx")
  else
    # No remote at all: an explicit read-only mode (the fetch already proved it, no extra ls-remote).
    if grep -q 'Remote unreachable' "$TXROOT/tick-error"; then CMD=$saved_cmd; coord_degraded_status; exit 0; fi
    CMD=$saved_cmd; ATTEMPT=read; fresh_state
    say "NOTE: deadline reconcile skipped ($(grep -m 1 -E 'ERROR|CONFLICT' "$TXROOT/tick-error" | cut -c 1-160)); showing the remote state." >&2
  fi
  CMD=$saved_cmd; ID=$saved_id; QUIET=no; COORD_INITIALIZED_TX=; coord_init
  coord_clock
  case "$CMD" in status) print_status | seen_print "status${ID:+-$ID}";; next) coord_next | seen_print next; preflight_note;; esac
}
digest_run() { ATTEMPT=1; fresh_state; print_digest | seen_print digest; }
