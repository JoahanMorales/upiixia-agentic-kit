# GitHub feedback for tasks; Bash 3.2+. Needs the gh CLI (UAK_GH overrides it, for tests).
# `uak pr-sync [ID]`: failed checks and new human review comments on a task's PR become one message to the task
# (task:ID: whoever holds it reads it, and the hooks inject it). Already-sent items are kept in claims meta/pr/ID.md.
# The owner's post-tool hook runs it every 5 min in the background; the opt-in uak-tick Action runs it for all.
# Why (MLB hackathon): 52 of 59 integrations were merged on GitHub, where CI results and human comments lived;
# agents learned of them only when a human relayed them. Composio's Agent Orchestrator routes CI failures and
# review comments back to the session that opened the PR.
PR_EVENTS=
pr_sync_targets() { # "ID<TAB>branch" for the task given, or every CLAIMED/REVIEW task with a branch
  local c id
  for c in "$TX"/claims/*.md; do
    [ -f "$c" ] || continue
    id=$(field "$c" ID); [ -z "$ID" ] || [ "$id" = "$ID" ] || continue
    case "$(field "$c" State)" in CLAIMED|REVIEW|BLOCKED) ;; *) continue;; esac
    [ -n "$(field "$c" Branch)" ] && printf '%s\t%s\n' "$id" "$(field "$c" Branch)"
  done
}
pr_sync_run() {
  local gh=${UAK_GH:-gh} id branch
  command -v "$gh" >/dev/null 2>&1 || { say "PR_SYNC: gh is not installed; nothing to read."; return 0; }
  ATTEMPT=read; fresh_state; coord_init
  PR_EVENTS="$TXROOT/pr-events"; : > "$PR_EVENTS"
  pr_sync_targets > "$TXROOT/pr-targets"
  while IFS="$(printf '\t')" read -r id branch; do
    # One line per item: kind TAB key TAB text. gh's built-in --jq; no jq needed.
    (cd "$ROOT" && "$gh" pr view "$branch" --json number,statusCheckRollup,comments,reviews --jq '
      .number as $n
      | ((.statusCheckRollup // [])[] | select(((.conclusion // .state) // "") | test("FAILURE|ERROR|TIMED_OUT|ACTION_REQUIRED"))
          | "check\t\(.name // .context)|\(.detailsUrl // .targetUrl // "")\t#\($n) CI failed: \(.name // .context) \(.detailsUrl // .targetUrl // "")"),
        ((.comments // [])[] | select((.author.login // "") | test("\\[bot\\]$") | not)
          | "comment\t\(.id)\t#\($n) @\(.author.login): \(.body | gsub("[\r\n\t|]+"; " ") | .[0:220])"),
        ((.reviews // [])[] | select(((.author.login // "") | test("\\[bot\\]$") | not) and ((.body // "") != "" or .state == "CHANGES_REQUESTED"))
          | "review\t\(.id)\t#\($n) review \(.state) by @\(.author.login): \(.body // "" | gsub("[\r\n\t|]+"; " ") | .[0:220])")' 2>/dev/null) |
      while IFS= read -r line; do [ -n "$line" ] && printf '%s\t%s\n' "$id" "$line"; done >> "$PR_EVENTS"
  done < "$TXROOT/pr-targets"
  [ -s "$PR_EVENTS" ] || { say "PR_SYNC: no failed checks or new comments on $( [ -n "$ID" ] && printf '%s' "$ID" || printf 'the live tasks')."; return 0; }
  cp "$PR_EVENTS" "$TXROOT/pr-events.keep"
  QUIET=yes; transaction
  say "PR_SYNC: ${PR_SENT:-nothing new} (each failed check and comment is told once)"
}
pr_sync_mutate() {
  local id kind key text seen msgs n
  PR_SENT=
  mkdir -p "$TX/meta/pr"
  for id in $(cut -f1 "$TXROOT/pr-events.keep" | sort -u); do
    seen="$TX/meta/pr/$id.md"; [ -f "$seen" ] || printf '%s\n' "# Sent to $id (uak pr-sync)" > "$seen"
    msgs= n=0
    while IFS="$(printf '\t')" read -r tid kind key text; do
      [ "$tid" = "$id" ] || continue
      ! grep -qxF -- "$kind $key" "$seen" || continue
      printf '%s\n' "$kind $key" >> "$seen"
      case "$kind" in
        check) local run; run=$(printf '%s' "$key" | sed -n 's@.*/actions/runs/\([0-9]*\).*@\1@p')
               if [ -n "$run" ]; then text="$text · read it: gh run view $run --log-failed"; else text="$text · read it: gh pr checks"; fi;;
      esac
      n=$((n + 1)); [ "$n" -le 4 ] || continue
      msgs="${msgs}${msgs:+ · }$text"
    done < "$TXROOT/pr-events.keep"
    [ "$n" -gt 0 ] || continue
    [ "$n" -le 4 ] || msgs="$msgs · (+$((n - 4)) more: gh pr view --comments)"
    msg_append_as github "task:$id" request "$id" "GitHub: $msgs"
    PR_SENT="${PR_SENT}${PR_SENT:+, }$id ($n)"
  done
}
