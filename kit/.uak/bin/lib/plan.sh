# plan: publish tasks on claims without a PR, or amend published ones before their review.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

# `plan FILE --amend`: new Paths, Verify or criteria for tasks already published, before their review.
# The amended section replaces the old one wherever the backlog is read (claims backlog/AMEND.md, last one wins);
# a claimed task's record and claim take the new Paths and Verify, so the merge gate checks the new scope.
# Why (MLB hackathon, v5 week): a fix had to touch fixtures and tests the plan missed, `uak plan` refused to
# republish the task, and the only way out was a new task or edits outside Paths.
plan_amend_mutate() {
  # A plan written on Windows is CRLF: "## PB-030\r" was an invalid ID and a list-form Verify kept a \r that broke
  # the gate's bash -c (portability audit, Oct 2026). Read an LF copy.
  [ "$PLAN_FILE" = "$TXROOT/plan-lf.md" ] || { tr -d '\r' < "$PLAN_FILE" > "$TXROOT/plan-lf.md" && coord_fold_backlog "$TXROOT/plan-lf.md" && PLAN_FILE="$TXROOT/plan-lf.md"; }
  local id st c e old_p new_p old_v new_v changes=
  for id in $plan_ids; do
    valid_id "$id" || die "Invalid ID in plan: $id"
    [ "$(awk -v id="$id" '/^## / && $2==id {n++} END {print n+0}' "$BACKLOG")" -eq 1 ] || conflict "$id is not in the backlog: publish it with uak plan FILE (no --amend)."
    [ "$(awk -v id="$id" '/^## / && $2==id {n++} END {print n+0}' "$PLAN_FILE")" -eq 1 ] || die "$id appears more than once in $PLAN_FILE."
    for key in Priority "Paths" "Depends on" "Verify"; do
      [ -n "$(ID=$id BACKLOG=$PLAN_FILE task_field "$key")" ] || die "$id needs $key."
    done
    ! e=$(verify_parse_error "$(ID=$id BACKLOG=$PLAN_FILE task_field Verify)") ||
      die "$id's Verify does not parse ($e): check its quotes. The merge gate runs it with bash -c."
    st=$(field "$TX/tasks/$id.md" State); st=${st:-AVAILABLE}
    case "$st" in
      AVAILABLE|CLAIMED|BLOCKED) ;;
      # A REVIEW task whose current SHA was rejected may be amended: it goes back to CLAIMED and its owner runs done
      # again. Why (Hacktoberfest): "a reviewer rejects it first" never made amend possible (a reject kept REVIEW),
      # so the human merged on GitHub over the reject instead.
      REVIEW) [ "$(field "$TX/reviews/$id.md" Verdict)" = reject ] && [ -n "$(field "$TX/tasks/$id.md" Task-Tip)" ] &&
                [ "$(field "$TX/reviews/$id.md" SHA)" = "$(field "$TX/tasks/$id.md" Task-Tip)" ] ||
                conflict "$id is in REVIEW: its review covers the old criteria. Once a reviewer rejects its current SHA, amend moves it back to CLAIMED; more work after INTEGRATED is uak followup $id."
              put "$TX/tasks/$id.md" State CLAIMED; [ ! -f "$TX/claims/$id.md" ] || put "$TX/claims/$id.md" State CLAIMED;;
      *) conflict "$id is $st: more work on it is uak followup $id --title TEXT.";;
    esac
    new_p=$(ID=$id BACKLOG=$PLAN_FILE task_field Paths); new_v=$(ID=$id BACKLOG=$PLAN_FILE task_field Verify)
    old_p=$(ID=$id task_field Paths); old_v=$(ID=$id task_field Verify)
    # New Paths must not take files of other live claims or of OWNERS rows (same checks as a claim). Only the Paths
    # the amend adds are checked against the claims: an amend that keeps them (Depends, criteria) passes a claim under
    # them. Why (UAK-019): UAK-006's new Depends waited for UAK-008, claimed under the same Paths, to integrate.
    ( ID=$id; normalize_paths "$new_p" > "$TXROOT/paths-request" || die "Invalid Paths for $id."
      check_owners
      normalize_paths "$old_p" > "$TXROOT/paths-old" 2>/dev/null || : > "$TXROOT/paths-old"
      grep -vxF -f "$TXROOT/paths-old" "$TXROOT/paths-request" > "$TXROOT/paths-added" || :
      [ ! -s "$TXROOT/paths-old" ] || [ -s "$TXROOT/paths-added" ] || exit 0
      [ -s "$TXROOT/paths-old" ] || cp "$TXROOT/paths-request" "$TXROOT/paths-added"
      for c in "$TX"/claims/*.md; do
        [ -f "$c" ] && [ "$(field "$c" ID)" != "$id" ] || continue
        normalize_paths "$(field "$c" Paths)" > "$TXROOT/other-paths" || continue
        ! overlaps "$TXROOT/paths-added" "$TXROOT/other-paths" || conflict "The new Paths of $id overlap $(field "$c" ID) (claimed by $(field "$c" Owner)): split the work or ask them."
      done ) || exit $?
    if [ -f "$TX/tasks/$id.md" ] && [ "$st" != AVAILABLE ]; then
      put "$TX/tasks/$id.md" Paths "$(one_line "$new_p")"; put "$TX/tasks/$id.md" Verify "$(one_line "$new_v")"
      [ ! -f "$TX/claims/$id.md" ] || { put "$TX/claims/$id.md" Paths "$(one_line "$new_p")"; put "$TX/claims/$id.md" Verify "$(one_line "$new_v")"; }
    fi
    changes="$changes $id"
    [ "$old_p" = "$new_p" ] || changes="$changes Paths: $old_p → $new_p;"
    [ "$old_v" = "$new_v" ] || changes="$changes Verify changed;"
    msg_append "task:$id" info "$id" "$id amended by $HUMAN: Paths $(one_line "$new_p") · Verify $(one_line "$new_v"). uak status --task $id; the merge gate checks the new Paths."
  done
  [ -f "$TX/backlog/AMEND.md" ] || printf '%s\n' '# Amended tasks (uak plan --amend)' '' \
    'Append-only; the last section of an ID replaces its section in the backlog. Why: Paths can grow before review.' '' > "$TX/backlog/AMEND.md"
  awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {on=1} /^# / {on=0} on {print}' "$PLAN_FILE" >> "$TX/backlog/AMEND.md"
  if grep -Eq '^\|.*\|[[:space:]]*[A-Z][A-Z0-9]*-[0-9]+[[:space:]]*\|' "$PLAN_FILE"; then
    [ -f "$TX/backlog/OWNERS.md" ] || printf '%s\n' '# Owners published on claims' '' '| Pattern | Owner task |' '|---|---|' > "$TX/backlog/OWNERS.md"
    grep -E '^\|.*\|[[:space:]]*[A-Z][A-Z0-9]*-[0-9]+[[:space:]]*\|' "$PLAN_FILE" >> "$TX/backlog/OWNERS.md"
  fi
  ID=
  [ -f "$TX/DECISIONS.md" ] || printf "# DECISIONS\n\nCoordination decisions on the claims branch.\n" > "$TX/DECISIONS.md"
  printf '%s\n' "- $NOW | plan --amend | $HUMAN/$AGENT | amended:$(one_line "$changes" | tr '|' '/') | Why: scope or criteria fixed before review" >> "$TX/DECISIONS.md"
}
plan_mutate() {
  # A plan written on Windows is CRLF: "## PB-030\r" was an invalid ID and a list-form Verify kept a \r that broke
  # the gate's bash -c (portability audit, Oct 2026). Read an LF copy.
  [ "$PLAN_FILE" = "$TXROOT/plan-lf.md" ] || { tr -d '\r' < "$PLAN_FILE" > "$TXROOT/plan-lf.md" && coord_fold_backlog "$TXROOT/plan-lf.md" && PLAN_FILE="$TXROOT/plan-lf.md"; }
  [ "$(coord_source_field Plan-Channel main)" = claims ] ||
    conflict "Plan-Channel is not claims in .uak/PROJECT.md: publish the backlog by PR to $BASE."
  plan_ids=$(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$PLAN_FILE")
  [ -n "$plan_ids" ] || die "The file has no task sections: each starts with a line \"## PB-030 · Title\" (the ID as in TASKS.md, uppercase), then - **Priority:**, - **Paths:**, - **Verify:**."
  if [ "$PLAN_AMEND" = yes ]; then plan_amend_mutate; return; fi
  local e
  for ID in $plan_ids; do
    valid_id "$ID" || die "Invalid ID in plan: $ID"
    [ "$(awk -v id="$ID" '/^## / && $2==id {n++} END {print n+0}' "$BACKLOG" "$PLAN_FILE")" -eq 1 ] ||
      conflict "$ID already exists in the backlog or is duplicated. To change its Paths, Verify or criteria before review: uak plan FILE --amend."
    for key in Priority "Paths" "Depends on" "Verify"; do
      [ -n "$(BACKLOG=$PLAN_FILE task_field "$key")" ] || die "$ID needs $key."
    done
    ! e=$(verify_parse_error "$(BACKLOG=$PLAN_FILE task_field Verify)") ||
      die "$ID's Verify does not parse ($e): check its quotes. The merge gate runs it with bash -c."
  done
  # A task the claim would refuse for good (its Paths under another task's OWNERS row): said now, not at claim time.
  { cat "$BACKLOG"; printf '\n'; cat "$PLAN_FILE"; } > "$TXROOT/plan-backlog"
  { cat "$OWNERS" 2>/dev/null; grep -E '^\|.*\|[[:space:]]*[A-Z][A-Z0-9]*-[0-9]+[[:space:]]*\|' "$PLAN_FILE"; } > "$TXROOT/plan-owners"
  DONE_HINT=$(BACKLOG="$TXROOT/plan-backlog" OWNERS="$TXROOT/plan-owners" owner_conflicts $plan_ids | while IFS='|' read -r id pat owner; do
    printf 'PLAN WARNING: %s can never be claimed: its Paths fall under %s, owned by %s. Drop the path (uak plan FILE --amend), give the OWNERS row to %s, or make %s depend on %s.\n' "$id" "$pat" "$owner" "$id" "$owner" "$id"
  done)
  mkdir -p "$TX/backlog"
  [ -f "$TX/backlog/TASKS.md" ] || printf '%s\n' '# Backlog published on claims (uak plan)' '' \
    'Append-only; added to .uak/TASKS.md from main. Why: adding tasks never waits for a PR.' > "$TX/backlog/TASKS.md"
  awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {on=1} /^# / {on=0} on {print}' "$PLAN_FILE" >> "$TX/backlog/TASKS.md"
  if grep -Eq '^\|.*\|[[:space:]]*[A-Z][A-Z0-9]*-[0-9]+[[:space:]]*\|' "$PLAN_FILE"; then
    [ -f "$TX/backlog/OWNERS.md" ] || printf '%s\n' '# Owners published on claims' '' '| Pattern | Owner task |' '|---|---|' > "$TX/backlog/OWNERS.md"
    grep -E '^\|.*\|[[:space:]]*[A-Z][A-Z0-9]*-[0-9]+[[:space:]]*\|' "$PLAN_FILE" >> "$TX/backlog/OWNERS.md"
  fi
  ID=
  [ -f "$TX/DECISIONS.md" ] || printf "# DECISIONS\n\nCoordination decisions on the claims branch.\n" > "$TX/DECISIONS.md"
  printf '%s\n' "- $NOW | plan | $HUMAN/$AGENT | tasks added: $(printf '%s ' $plan_ids)| Why: backlog without PR (Plan-Channel: claims)" >> "$TX/DECISIONS.md"
  msg_append all info - "Backlog: new tasks $(printf '%s ' $plan_ids)published by $HUMAN. uak next shows them."
}
