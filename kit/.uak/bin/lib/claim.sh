# A task's life before done: claim, heartbeat, release, log, checkpoint, handoff, handover, away, retire, followup.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

check_dependencies() {
  deps=$(printf '%s\n' "$DEPENDS" | awk '{
    s=$0; gsub(/\([^)]*\)/, "", s); while(match(s,/[A-Z][A-Z0-9]*-[0-9][0-9][0-9]+/)) {
      print substr(s,RSTART,RLENGTH); s=substr(s,RSTART+RLENGTH)
    }}')
  for dep in $deps; do
    dep_state=$(field "$TX/tasks/$dep.md" State)
    [ "$dep_state" = INTEGRATED ] && continue
    # A cancelled dependency never integrates: waiting on it is forever (audit, Oct 2026).
    [ "$dep_state" != CANCELLED ] || UAK_CODE=dependency-cancelled conflict "$ID depends on $dep, which is CANCELLED: it never integrates. A human drops it from Depends on: UAK_HUMAN=NAME bash .uak/bin/uak plan --amend FILE (or cancels $ID too)."
    [ "$dep_state" != REVIEW ] || UAK_CODE=dependency-in-review conflict "$ID depends on $dep (REVIEW). If its PR is already merged, any agent can run: uak integrate $dep. Otherwise do not retry the claim: take other work, or wait once: uak wait $dep --for integrated"
    UAK_CODE=dependency-pending conflict "$ID depends on $dep; claim it after INTEGRATED (do not retry: uak wait $dep --for integrated, once)."
  done
}
check_collisions() {
  [ ! -f "$(claim_file)" ] || UAK_CODE=already-claimed conflict "$ID already has claims/$ID.md; read its summary."
  if [ -f "$(task_file)" ]; then
    old_state=$(field "$(task_file)" State)
    case "$old_state" in INTEGRATED|CANCELLED) UAK_CODE=task-closed conflict "$ID is already $old_state.";; esac
  fi
  check_owners; check_dependencies
  for other in "$TX"/claims/*.md; do
    [ -f "$other" ] || continue
    # One identity = one live task. Why (Reap buildathon): two sessions shared agent-2 on two tasks and
    # overwrote each other's claims; REVIEW tasks do not count (waiting is not working).
    if [ "${UAK_MULTI_CLAIM:-}" != 1 ] && [ "$(field "$other" Owner)" = "$AGENT" ]; then
      case "$(field "$other" State)" in CLAIMED|BLOCKED)
        other_until=$(field "$other" Lease-Until)
        case "$other_until" in ''|*[!0-9]*) other_until=0;; esac
        [ "$NOW" -ge "$other_until" ] ||
          UAK_CODE=one-live-task conflict "$AGENT already holds $(field "$other" ID) ($(field "$other" State)). One identity = one live task: finish or release it, or let another agent take it: bash .uak/bin/wt new $ID (picks a free identity of this machine).";;
      esac
    fi
    if [ "$(field "$other" Branch)" = "$BRANCH" ] || [ "$(field "$other" Worktree)" = "$WORKTREE" ]; then
      UAK_CODE=branch-taken conflict "Branch/worktree already claimed by $(field "$other" ID); use one per task."
    fi
    normalize_paths "$(field "$other" Paths)" > "$TXROOT/other-paths" || die "Claim with invalid Paths."
    if overlaps "$TXROOT/paths-request" "$TXROOT/other-paths"; then
      # Why (MLB hackathon): HACK-033 and HACK-022 were refused for 9 h by an expired claim of a retired identity.
      other_until=$(field "$other" Lease-Until); case "$other_until" in ''|*[!0-9]*) other_until=0;; esac
      if [ "$other_until" -gt 0 ] && [ "$NOW" -ge "$other_until" ] && [ "$(field "$other" State)" != REVIEW ]; then
        UAK_CODE=overlap-expired conflict "$ID overlaps $(field "$other" ID) ($(field "$other" Owner)), whose lease expired $(( (NOW - other_until) / 60 )) min ago. Take that one over: uak status --task $(field "$other" ID) --summary, then uak release $(field "$other" ID) --expired --read-summary TOKEN."
      fi
      # Why (Hacktoberfest): one agent retried "overlaps HACK-028" and "depends on HACK-028" 14 times in 40 min.
      UAK_CODE=overlap conflict "$ID overlaps $(field "$other" ID) ($(field "$other" Owner)); pick another task, or wait once: uak wait $(field "$other" ID) --for integrated (retrying the claim changes nothing)."
    fi
  done
}
# Progress facts from the task's worktree, written by every heartbeat (the hooks send them): commits since the claim,
# the last one, uncommitted files. The next owner sees them even when nobody checkpointed. Why (MLB hackathon): 74
# checkpoints for 130 claims, 43 lease recoveries, and a summary that said what the task was, not where it stood.
task_progress() {
  local wt base n last dirty
  wt=$(field "$RECORD" Worktree); [ -d "$wt" ] && same_repo_worktree "$wt" || wt=$ROOT
  [ "$(git -C "$wt" symbolic-ref --short HEAD 2>/dev/null)" = "$(field "$RECORD" Branch)" ] || return 0
  base=$(field "$RECORD" Task-Base)
  n=$(git -C "$wt" rev-list --count "${base:-HEAD}..HEAD" 2>/dev/null || echo 0)
  last=$(git -C "$wt" log -1 --format='%h %s (%cr)' 2>/dev/null | cut -c 1-120 | tr '|' '/')
  dirty=$(git -C "$wt" status --porcelain 2>/dev/null | grep -vc '^??' || true)
  put "$RECORD" Progress "$n commit(s) since the claim · last: ${last:--} · $dirty uncommitted tracked file(s) · at $NOW"
  # When the work last moved (a new HEAD, or a different set of uncommitted files): stall detection reads it.
  local head; head="$(git -C "$wt" rev-parse --short HEAD 2>/dev/null)/$(git -C "$wt" status --porcelain 2>/dev/null | cksum | awk '{print $1}')"
  if [ "$(field "$RECORD" Progress-Head)" != "$head" ]; then put "$RECORD" Progress-Head "$head"; put "$RECORD" Progress-Changed "$NOW"; fi
}
# Stalled: a CLAIMED task whose work has not moved for Stall-Seconds (default 90 min) while its lease is live.
# Prints "minutes" or nothing. Why (MLB hackathon): 43 lease recoveries; Addy Osmani's orchestra notes: kill and
# reassign an agent stuck three iterations on one error instead of letting it spin.
task_stalled() { # $1 record file
  local ch lim; [ "$(field "$1" State)" = CLAIMED ] || return 0
  ch=$(field "$1" Progress-Changed); case "$ch" in ''|*[!0-9]*) return 0;; esac
  lim=$(coord_config Stall-Seconds 5400 2>/dev/null); case "$lim" in ''|*[!0-9]*) lim=5400;; esac
  [ $((NOW - ch)) -ge "$lim" ] || return 0
  printf '%s' $(( (NOW - ch) / 60 ))
}
# A path from claims (Worktree:) is used only when it is a checkout of this same repository on this machine.
same_repo_worktree() {
  local a b
  a=$(cd "$1" 2>/dev/null && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P) || return 1
  b=$(cd "$ROOT" && cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P) || return 1
  [ -n "$a" ] && [ "$a" = "$b" ]
}
released_from_me() {
  local by
  [ ! -f "$CLAIM" ] && [ -f "$RECORD" ] && [ "$(field "$RECORD" Owner)" = "$AGENT" ] || return 0
  by=$(field "$RECORD" Released-By)
  [ -z "$by" ] || [ "$by" = "$AGENT" ] ||
    UAK_CODE=released-by-other conflict "$ID has no active claim: $by released it after your lease expired (your summary is kept for its next owner). Stop editing it; run uak next."
}
# `uak away`: this identity closed its session. It leaves the reviewer rotation and messages to it reach its tasks
# at once (not after 30 min of silence); its claims keep their leases. The next uak command brings it back.
# SessionEnd hooks run it. Why (MLB hackathon): sessions closed without a handoff (5 handoffs, 14 releases for 130
# claims), and their identities kept getting reviews for hours.
away_mutate() {
  local c n=0
  mkdir -p "$TX/meta/agents"
  [ -f "$TX/meta/agents/$AGENT.md" ] || printf '%s\n' "# $AGENT" "Agent: $AGENT" "Started: $NOW" > "$TX/meta/agents/$AGENT.md"
  for c in "$TX"/claims/*.md; do
    [ -f "$c" ] && [ "$(field "$c" Owner)" = "$AGENT" ] || continue
    ID=$(field "$c" ID); RECORD=$(task_file)
    case "$(field "$c" State)" in CLAIMED|BLOCKED) task_progress; put "$RECORD" Away "$NOW"; n=$((n + 1));; esac
  done
  ID=
  put "$TX/meta/agents/$AGENT.md" Session-Ended "$NOW"
  AWAY_TASKS=$n
}
# Explicit transfer of a live task: same claim, branch, worktree and summary; only the owner changes.
# Allowed to the owner, to a human (UAK_HUMAN) and to anyone once the lease has expired.
# Why (MLB hackathon): the tasks of three abandoned identities were redistributed by messages ("you take 033, I
# take 020"), then each one needed release --expired with a read token and a new claim.
handover_mutate() {
  local owner until c wt
  [ -f "$CLAIM" ] && [ -f "$RECORD" ] || conflict "$ID has no claim to hand over."
  owner=$(field "$CLAIM" Owner); until=$(field "$CLAIM" Lease-Until); case "$until" in ''|*[!0-9]*) until=0;; esac
  [ "$DONE_TO" != "$owner" ] || conflict "$ID already belongs to $DONE_TO."
  # Also another identity of the same human once the owner has been offline for 1 h (or closed its session, uak away): a human's closed session must
  # not strand its task in review (MLB: verdicts and requests reached closed identities while the same human ran a live one).
  local seen_o; seen_o=$(msg_seen "$owner")
  [ "$owner" = "$AGENT" ] || [ -n "$HUMAN" ] || [ "$NOW" -ge "$until" ] ||
    { [ "${owner%-*}" = "${AGENT%-*}" ] && { [ $((NOW - seen_o)) -ge 3600 ] || msg_away "$owner"; }; } ||
    UAK_CODE=lease-active conflict "$ID belongs to $owner with a live lease: only $owner, a human (UAK_HUMAN) or another identity of the same human after 1 h offline can hand it over."
  # An expired lease is taken over the way release --expired takes it: after reading its summary (the token proves
  # it). Why (audit, Oct 2026): handover --to SELF took any expired claim with no token and no summary read.
  if [ "$owner" != "$AGENT" ] && [ -z "$HUMAN" ] && [ "$NOW" -ge "$until" ] &&
     ! { [ "${owner%-*}" = "${AGENT%-*}" ] && { [ $((NOW - seen_o)) -ge 3600 ] || msg_away "$owner"; }; }; then
    WL=$(field "$RECORD" Worklog)
    [ -n "$TOKEN" ] && [ "$TOKEN" = "$(read_token)" ] ||
      UAK_CODE=read-token conflict "$ID's lease expired: read it first (uak status --task $ID --summary), then handover $ID --to $DONE_TO --read-summary TOKEN."
  fi
  [ ! -f "$TX/meta/retired/$DONE_TO.md" ] || conflict "$DONE_TO is retired; a claim by $DONE_TO brings it back, a handover does not."
  if [ "${UAK_MULTI_CLAIM:-}" != 1 ]; then
    for c in "$TX"/claims/*.md; do
      [ -f "$c" ] && [ "$c" != "$CLAIM" ] && [ "$(field "$c" Owner)" = "$DONE_TO" ] || continue
      case "$(field "$c" State)" in CLAIMED|BLOCKED) conflict "$DONE_TO already holds $(field "$c" ID): one identity = one live task.";; esac
    done
  fi
  put "$RECORD" Owner "$DONE_TO"; put "$CLAIM" Owner "$DONE_TO"; put "$CLAIM" Thread-Read 0
  WL=$(field "$RECORD" Worklog); STATE=$(field "$RECORD" State)
  local saved=$AGENT; refresh_lease
  event "handover; $owner → $DONE_TO by ${HUMAN:-$saved}"
  # The worktree's .uak-env wins over the shell, so it must name the new owner when the worktree is here.
  wt=$(field "$RECORD" Worktree)
  # Claude Code's env (.claude/settings.local.json) too: the hooks read UAK_AGENT from it. Why: after a handover the
  # new owner's session started as the old identity ("agent=cy-1") and every uak call printed the mismatch.
  # Rewritten only once the push is confirmed (handover_env_apply, from transaction). Why (audit, Oct 2026): a
  # refused push left .uak-env naming the new owner while claims still said the old one, and the real owner's
  # heartbeats then failed with "belongs to".
  HANDOVER_ENV_WT=$wt
  msg_append "agent:$DONE_TO" request "$ID" "$ID is yours now (from $owner): branch $(field "$RECORD" Branch), worktree $wt. Read uak status --task $ID --summary and continue its Next. Another machine: git fetch origin && git worktree add <dir> $(field "$RECORD" Branch), then write UAK_AGENT=$DONE_TO and UAK_TASK=$ID in <dir>/.uak-env."
}
handover_env_apply() {
  local f wt=$HANDOVER_ENV_WT
  [ -n "$wt" ] && [ -d "$wt" ] || return 0
  # Only a worktree of this repository: the path comes from claims.
  same_repo_worktree "$wt" || return 0
  for f in "$wt/.uak-env" "$wt/.claude/settings.local.json"; do
    [ -f "$f" ] || continue
    sed -e "s/^UAK_AGENT=.*/UAK_AGENT=$DONE_TO/" -e "s/^UAK_SESSION=.*/UAK_SESSION=$DONE_TO-$NOW/" \
        -e "s/\"UAK_AGENT\": \"[^\"]*\"/\"UAK_AGENT\": \"$DONE_TO\"/" -e "s/\"UAK_SESSION\": \"[^\"]*\"/\"UAK_SESSION\": \"$DONE_TO-$NOW\"/" \
        "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  done
}
# An identity whose human closed its terminal keeps receiving reviews by rotation until it is retired.
# Why (MLB hackathon): three identities of one human had no session left, got 15 rotation reviews, and a human had to tell
# every agent by message that they "no longer exist".
retire_mutate() {
  local who c
  mkdir -p "$TX/meta/retired"
  for who in $RETIRE_NAMES; do
    [ "$who" = "$AGENT" ] || [ -n "$HUMAN" ] || conflict "Retiring $who needs its human: UAK_HUMAN=NAME uak retire $who (or $who retires itself)."
    for c in "$TX"/claims/*.md; do
      [ -f "$c" ] && [ "$(field "$c" Owner)" = "$who" ] || continue
      case "$(field "$c" State)" in CLAIMED|BLOCKED)
        conflict "$who still holds $(field "$c" ID): release or hand it off first (uak release ID, or release --expired).";; esac
    done
    printf '%s\n' "Agent: $who" "Retired-By: ${HUMAN:-$AGENT}" "Retired: $NOW" > "$TX/meta/retired/$who.md"
  done
  ID=
}
# A follow-up of an INTEGRATED task (fix, polish, a reviewer's non-blocking notes) is a new task on the same
# Paths, so it gets a claim, a review and a merge. Why (MLB hackathon): 3 follow-up PRs of integrated tasks
# went around the kit; `uak review` refused them ("already INTEGRATED") and one was approved only by message.
followup_mutate() {
  local parent=$ID prefix n paths verify freeze
  RECORD=$(task_file)
  local st; st=$(field "$RECORD" State); st=${st:-AVAILABLE}
  [ "$st" = INTEGRATED ] || conflict "$parent is $st, not INTEGRATED: keep working on it, or push to its branch and run done again."
  [ "$(coord_source_field Plan-Channel main)" = claims ] ||
    conflict "Plan-Channel is not claims in .uak/PROJECT.md: add the follow-up task to TASKS.md by PR."
  paths=$(field "$RECORD" Paths); verify=$(field "$RECORD" Verify)
  prefix=${parent%-*}
  n=$(awk -v p="$prefix" '/^## / {split($2, a, "-"); if (a[1] == p && a[2] ~ /^[0-9]+$/ && a[2] + 0 > m) m = a[2] + 0} END {print m + 0}' "$BACKLOG")
  for f in "$TX"/tasks/"$prefix"-*.md; do [ -f "$f" ] || continue; f=${f##*-}; f=${f%.md}; case "$f" in *[!0-9]*) continue;; esac
    [ "$((10#$f))" -le "$n" ] || n=$((10#$f)); done
  NEW_ID=$(printf '%s-%03d' "$prefix" $((n + 1)))
  mkdir -p "$TX/backlog"
  [ -f "$TX/backlog/TASKS.md" ] || printf '%s\n' '# Backlog published on claims (uak plan)' '' \
    'Append-only; added to .uak/TASKS.md from main. Why: adding tasks never waits for a PR.' > "$TX/backlog/TASKS.md"
  printf '%s\n' '' "## $NEW_ID · $(one_line "$FOLLOWUP_TITLE") (follow-up of $parent)" '' '- **Type:** follow-up' '- **Priority:** P1' \
    "- **Depends on:** $parent" "- **Follow-up of:** $parent" "- **Paths:** $paths" '- **Freeze-Allowed:** no' \
    '- **Acceptance:**' "  - $(one_line "$FOLLOWUP_TITLE")" "- **Verify:** $verify" >> "$TX/backlog/TASKS.md"
  [ -f "$TX/DECISIONS.md" ] || printf "# DECISIONS\n" > "$TX/DECISIONS.md"
  printf '%s\n' "- $NOW | $NEW_ID | follow-up of $parent by $AGENT: $(one_line "$FOLLOWUP_TITLE") | Why: same Paths, no scope change" >> "$TX/DECISIONS.md"
}
# claim: the record, the claim and the worklog of a new owner (an existing worklog is continued).
claim_mutate() {
  coord_tick_mutate; load_task
  [ -n "$REQUEST_NEXT" ] || NEXT_TEXT=$DEFAULT_NEXT
  coord_claim_gate
  check_collisions; STATE=CLAIMED; UNTIL=$((NOW + LEASE))
  WL="worklog/WL-$NOW-$AGENT-$ID-$(basename "$TXROOT").md"
  task_base=$CLAIM_BASE
  if [ -f "$RECORD" ]; then
    prior_wl=$(field "$RECORD" Worklog)
    if [ -f "$TX/$prior_wl" ]; then
      WL=$prior_wl
      task_base=$(field "$RECORD" Task-Base)
      [ -n "$REQUEST_NEXT" ] || NEXT_TEXT=$(field "$RECORD" Next)
    fi
  fi
  {
    printf '# %s\n' "$ID"
    printf '%s\n' "ID: $ID" "State: $STATE" "Owner: $AGENT" "Branch: $BRANCH" "Worktree: $WORKTREE" \
      "Worklog: $WL" "Priority: $PRIORITY" "Paths: $(one_line "$PATHS")" \
      "Depends: $(one_line "$DEPENDS")" "Verify: $(one_line "$VERIFY")" \
      "Lease-Until: $UNTIL" "Updated: $NOW" "Task-Base: $task_base" "Next: $(one_line "$NEXT_TEXT")" "PR: -" "Evidence: -"
  } > "$RECORD"
  cp "$RECORD" "$CLAIM"; put "$CLAIM" Thread-Read 0; rm -f "$TX/meta/retired/$AGENT.md"
  DONE_TEXT="Claim created; implementation pending"
  DECISION_TEXT="Own branch and worktree"
  WHY_TEXT="Parallel work without touching the main checkout"
  FAILS_TEXT="No validation run yet"; COMMANDS_TEXT=$VERIFY
  if [ -f "$TX/$WL" ]; then update_summary_field Next "$NEXT_TEXT"; else set_summary; fi
  event "claim; next: $NEXT_TEXT"
}
# heartbeat: renew the lease and record the worktree's progress. A no-op (MUTATE_NOOP) on the owner's own task that
# already left CLAIMED/REVIEW.
heartbeat_mutate() {
  coord_tick_mutate
  # Your own task that already left CLAIMED/REVIEW: nothing to renew, not an error.
  # Why (MLB hackathon): Cursor agents heartbeated integrated tasks and logged "no active claim" conflicts.
  # Unless another agent released it after the lease expired: the old owner must stop. Why (audit, Oct 2026): its
  # heartbeat said OK and its checkpoint rewrote the summary the next owner inherits.
  released_from_me
  if [ ! -f "$CLAIM" ] && [ -f "$RECORD" ] && [ "$(field "$RECORD" Owner)" = "$AGENT" ]; then
    say "OK heartbeat $ID | $(field "$RECORD" State): nothing to renew. Next: uak next"; MUTATE_NOOP=yes; return 0
  fi
  require_owner; STATE=$(field "$RECORD" State)
  refresh_lease; event "heartbeat; lease until $UNTIL"
  task_progress
}
# release: back to AVAILABLE (or CANCELLED); someone else's claim only once its lease expired and its summary was read.
release_mutate() {
  [ -f "$CLAIM" ] && [ -f "$RECORD" ] || conflict "$ID has no claim."
  WL=$(field "$RECORD" Worklog); STATE=$(field "$RECORD" State)
  valid_worklog "$WL" || die "Invalid worklog path."
  [ -f "$TX/$WL" ] || die "Missing live summary."
  if [ "$(field "$CLAIM" Owner)" != "$AGENT" ]; then
    [ "$EXPIRED" = yes ] || UAK_CODE=not-owner conflict "Only the owner can release an unexpired claim."
    until=$(field "$CLAIM" Lease-Until)
    case "$until" in ''|*[!0-9]*) die "Invalid lease.";; esac
    [ "$NOW" -ge "$until" ] || UAK_CODE=lease-active conflict "Lease of $ID still active."
    [ -n "$TOKEN" ] && [ "$TOKEN" = "$(read_token)" ] ||
      UAK_CODE=read-token conflict "Read status --task $ID --summary and pass its current Read-token."
  fi
  STATE=AVAILABLE
  if [ -n "$CANCEL_REASON" ]; then
    [ "$(field "$CLAIM" Owner)" = "$AGENT" ] || conflict "Only the owner can cancel."
    STATE=CANCELLED
    put "$RECORD" Next "Cancelled: $CANCEL_REASON"
    update_summary_field Next "Cancelled: $CANCEL_REASON"
  fi
  put "$RECORD" State "$STATE"; put "$RECORD" Updated "$NOW"; put "$RECORD" Lease-Until 0
  [ "$(field "$CLAIM" Owner)" = "$AGENT" ] || put "$RECORD" Released-By "$AGENT"
  rm "$CLAIM"; event "release; claim released by $AGENT; reason: ${CANCEL_REASON:--}; summary kept"
}
# log: one event line; --state moves CLAIMED <-> BLOCKED.
log_mutate() {
  require_owner; STATE=$(field "$RECORD" State)
  if [ -n "$NEW_STATE" ]; then
    case "$STATE" in CLAIMED|BLOCKED) ;; *) conflict "log cannot move $ID out of $STATE.";; esac
    STATE=$NEW_STATE; put "$RECORD" State "$STATE"; put "$CLAIM" State "$STATE"
  fi
  [ "$STATE" != BLOCKED ] || update_summary_field Failing "$LOG_TEXT"
  refresh_lease; event "$LOG_TEXT"
}
# checkpoint: the six-field live summary (or --session: the budget only).
checkpoint_mutate() {
  if [ "$SESSION_ONLY" = yes ]; then coord_checkpoint_session
  else
    if [ -f "$CLAIM" ]; then require_owner
    else
      released_from_me
      [ -f "$RECORD" ] && [ "$(field "$RECORD" Owner)" = "$AGENT" ] || conflict "Checkpoint needs your own task record or --session."
      WL=$(field "$RECORD" Worklog); valid_worklog "$WL" && [ -f "$TX/$WL" ] || die "Missing valid worklog."
    fi
    STATE=$(field "$RECORD" State); set_summary
    put "$RECORD" Next "$NEXT_TEXT"
    if [ -f "$CLAIM" ]; then put "$CLAIM" Next "$NEXT_TEXT"; refresh_lease
    else put "$RECORD" Updated "$NOW"; fi
    if [ "$DECISION_TEXT" != "-" ] && [ -n "$DECISION_TEXT" ]; then
      [ -f "$TX/DECISIONS.md" ] || printf '# DECISIONS\n' > "$TX/DECISIONS.md"
      printf '%s\n' "- $NOW | $ID | $(one_line "$DECISION_TEXT") | Why: $(one_line "$WHY_TEXT")" >> "$TX/DECISIONS.md"
    fi
    event "checkpoint; next: $NEXT_TEXT"
  fi
}
# handoff: an event and the summary printed for the next session.
handoff_mutate() {
  if [ -f "$CLAIM" ]; then require_owner; refresh_lease
  else
    [ -f "$RECORD" ] && [ "$(field "$RECORD" Owner)" = "$AGENT" ] || conflict "Only the owner can close a handoff."
    WL=$(field "$RECORD" Worklog)
  fi
  STATE=$(field "$RECORD" State); event "handoff; next: $(field "$RECORD" Next)"
}
# Before the transaction: the worktree is a real, separate worktree of this repository, on the branch claimed.
claim_args_check() {
  [ -n "$BRANCH" ] && [ -n "$WORKTREE" ] || die "claim needs --branch and --worktree."
  git check-ref-format --branch "$BRANCH" > /dev/null 2>&1 || die "Invalid branch."
  WORKTREE=$(cd "$WORKTREE" 2>/dev/null && pwd -P) || die "Worktree does not exist."
  primary=$(git -C "$ROOT" worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)
  primary=$(cd "$primary" && pwd -P) || die "Invalid main checkout."
  [ "$WORKTREE" != "$primary" ] || die "Use a worktree separate from the main checkout."
  registered_root=$(git -C "$WORKTREE" rev-parse --show-toplevel 2>/dev/null) || die "Invalid worktree."
  registered_root=$(cd "$registered_root" && pwd -P) || die "Invalid worktree."
  [ "$WORKTREE" = "$registered_root" ] || die "Use the exact root of a registered worktree."
  actual=$(git -C "$WORKTREE" symbolic-ref --short HEAD 2>/dev/null) || die "Worktree detached or invalid."
  [ "$actual" = "$BRANCH" ] || die "Worktree is not on $BRANCH."
  CLAIM_BASE=$(git -C "$WORKTREE" rev-parse HEAD) || die "Missing initial commit in worktree."
  # Why (UpiixSol UPS-030): a claim taken after the code was written stored the finished tip as its base,
  # so done/merge saw "nothing implemented". The fork point with the remote base is the real start.
  fork=$(git -C "$WORKTREE" merge-base HEAD "refs/remotes/$REMOTE/$BASE" 2>/dev/null) && [ -n "$fork" ] && CLAIM_BASE=$fork
  common_main=$(git -C "$ROOT" rev-parse --git-common-dir)
  common_work=$(git -C "$WORKTREE" rev-parse --git-common-dir)
  common_main=$(cd "$ROOT" && cd "$common_main" && pwd -P) || die "Invalid Git common dir."
  common_work=$(cd "$WORKTREE" && cd "$common_work" && pwd -P) || die "Invalid Git common dir."
  [ "$common_main" = "$common_work" ] || die "Worktree belongs to another repository."
  REQUEST_NEXT=$NEXT_TEXT
}
