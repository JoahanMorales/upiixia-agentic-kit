# wait: one call that returns when something happens on claims, instead of polling.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

# One call that blocks until something happens on claims, instead of an agent polling status/inbox.
# A cheap `git ls-remote` every WAIT_EVERY s (0.4 s with SSH reuse); claims are read only when their tip moves.
# Why (MLB hackathon): 225 `status` and 172 `inbox` calls, most of them an agent checking whether its review,
# a dependency or a reply had arrived; every call re-sends its output into the agent's context.
#   approve     your REVIEW task (or ID): exit 0 on approve or INTEGRATED, 3 on reject
#   integrated  ID becomes INTEGRATED (a dependency): exit 0
#   message     a new unread message for you: printed, exit 0
# Timeout (default 540 s, under a 10-min tool limit): WAIT_TIMEOUT, exit 4. Rerun to keep waiting.
wait_run() {
  local deadline last= tip n=0 rv st c left
  deadline=$(( $(date +%s) + WAIT_TIMEOUT ))
  if [ "$WAIT_FOR" = approve ] && [ -z "$ID" ]; then
    ATTEMPT=wait-0; fresh_state
    for c in "$TX"/claims/*.md; do
      [ -f "$c" ] && [ "$(field "$c" Owner)" = "$AGENT" ] && [ "$(field "$c" State)" = REVIEW ] && { ID=$(field "$c" ID); break; }
    done
    [ -n "$ID" ] || die "wait --for approve: you have no task in REVIEW; name one: uak wait ID --for approve"
  fi
  [ "$WAIT_FOR" = message ] || [ -n "$ID" ] || die "wait --for $WAIT_FOR needs an ID."
  say "WAITING ${ID:+$ID }for $WAIT_FOR (up to $WAIT_TIMEOUT s; checks every $WAIT_EVERY s)"
  local wait_base=
  # Unread messages from before the wait are answered now, not by waiting.
  if [ "$WAIT_FOR" = message ]; then
    ATTEMPT=wait-0; fresh_state
    wait_base=$(awk '/^- [0-9]/ { n = $2 + 0; if (n > m) m = n } END { print m + 0 }' "$TX/$MSG_LOG" 2>/dev/null || echo 0)
    c=$(msg_select unread | grep -c '^#' || true)
    [ "${c:-0}" -eq 0 ] || say "($c unread from before this wait: uak inbox shows them; the wait returns only for new ones.)"
  fi
  while :; do
    tip=$(git -C "$ROOT" ls-remote "$REMOTE" refs/heads/claims 2>/dev/null | awk '{print $1; exit}')
    if [ -n "$tip" ] && [ "$tip" != "$last" ]; then
      last=$tip; n=$((n + 1)); ATTEMPT="wait-$n"; [ -n "${UAK_NOW:-}" ] || NOW=$(date +%s)
      fresh_state
      case "$WAIT_FOR" in
        approve)
          st=$(field "$TX/tasks/$ID.md" State); rv="$TX/reviews/$ID.md"
          if [ "$st" = INTEGRATED ]; then say "INTEGRATED $ID ($(field "$TX/tasks/$ID.md" Merge-Commit | cut -c 1-7))"; return 0; fi
          if [ -f "$rv" ] && [ "$(field "$rv" SHA)" = "$(field "$TX/tasks/$ID.md" Task-Tip)" ]; then
            case "$(field "$rv" Verdict)" in
              approve) say "APPROVED $ID by $(field "$rv" Reviewer) on $(field "$rv" SHA | cut -c 1-7). Next: bash .uak/bin/uak merge $ID"; return 0;;
              reject) say "REJECTED $ID by $(field "$rv" Reviewer) on $(field "$rv" SHA | cut -c 1-7). Read it: bash .uak/bin/uak inbox --task $ID"; return 3;;
            esac
          fi;;
        integrated)
          st=$(field "$TX/tasks/$ID.md" State)
          if [ "$st" = INTEGRATED ]; then say "INTEGRATED $ID ($(field "$TX/tasks/$ID.md" Merge-Commit | cut -c 1-7)). git fetch origin && git merge --no-edit origin/$BASE"; return 0; fi;;
        message)
          # Only what arrives after the wait started. Why (audit, Oct 2026): 15 unread messages already shown made
          # every wait return in a second, and the agent polled.
          [ -n "$wait_base" ] || wait_base=$(awk '/^- [0-9]/ { n = $2 + 0; if (n > m) m = n } END { print m + 0 }' "$TX/$MSG_LOG" 2>/dev/null || echo 0)
          c=$(msg_select unread | awk -v b="${wait_base:-0}" '/^#[0-9]/ { n = substr($1, 2) + 0; keep = n > b } keep')
          if [ -n "$c" ]; then say "NEW for $AGENT:"; say "$c"; say "Handle them, then uak inbox --ack."; return 0; fi;;
      esac
    fi
    left=$((deadline - $(date +%s)))
    [ "$left" -gt 0 ] || { say "WAIT_TIMEOUT ${ID:+$ID }$WAIT_FOR after $WAIT_TIMEOUT s: nothing yet. Do other work, or run the same wait again."; return 4; }
    # Never past the deadline: --timeout 3 used to sleep the whole 15 s check interval.
    [ "$left" -ge "$WAIT_EVERY" ] || { sleep "$left"; continue; }
    sleep "$WAIT_EVERY"
  done
}
