# Sourced by .uak/bin/uak; needs no Python or jq.
secrets_lint() {
  local mode=${1:---tracked}
  bash "$ROOT/.uak/bin/secret-scan" "$mode" --decisions "$TX/DECISIONS.md"
}
secret_exception_action() {
  local claim until owner wt branch actual hash line
  case "$SECRET_RULE" in SEC_ENV|SEC_PRIVATE_KEY|SEC_CLOUD_ACCESS|SEC_CLOUD_SECRET|SEC_GITHUB|SEC_ANTHROPIC|SEC_OPENAI) ;; *) die "Unknown secret rule.";; esac
  case "$SECRET_PATH" in ''|/*|[A-Za-z]:*|../*|*/../*|*/..|*'|'*|*'\'*|*$'\n'*|*$'\r'*) die "Invalid exception path.";; esac
  [ -n "$SECRET_REASON" ] || die "secret-exception needs --reason."
  claim="$TX/claims/$ID.md"
  [ -f "$claim" ] || conflict "$ID has no claim to review the index blob."
  until=$(field "$claim" Lease-Until)
  case "$until" in ''|*[!0-9]*) conflict "Invalid task lease.";; esac
  [ "$until" -gt "$NOW" ] && is_reserved "$(field "$claim" State)" || conflict "Task claim expired or inactive."
  owner=$(field "$claim" Owner)
  [ "$owner" != "$AGENT" ] || conflict "An exception needs a reviewer other than the owner."
  review_identity_eligible "$AGENT" || conflict "Reviewer has no active claim nor registered role."
  normalize_paths "$SECRET_PATH" > "$TXROOT/secret-path" || die "Invalid exception path."
  normalize_paths "$(field "$claim" Paths)" > "$TXROOT/secret-scope" || die "Invalid claim scope."
  overlaps "$TXROOT/secret-scope" "$TXROOT/secret-path" || conflict "The path is outside the scope of $ID."
  wt=$(field "$claim" Worktree); branch=$(field "$claim" Branch)
  actual=$(git -C "$wt" symbolic-ref --short HEAD 2>/dev/null) || conflict "Owner worktree not accessible."
  [ "$actual" = "$branch" ] || conflict "Owner worktree changed branch."
  git -C "$wt" show ":$SECRET_PATH" > "$TXROOT/secret-blob" 2>/dev/null || conflict "The path is not in the index of $ID."
  hash=$(git -C "$wt" hash-object "$TXROOT/secret-blob") || gitfail "Cannot identify the blob."
  line="Secret-Exception: $ID|$SECRET_PATH|$SECRET_RULE|$hash|$AGENT|approved|$NOW"
  [ -f "$TX/DECISIONS.md" ] || printf '%s\n' '# Verified decisions' > "$TX/DECISIONS.md"
  if ! grep -Fqx "$line" "$TX/DECISIONS.md"; then
    printf '\n%s\n%s\n' "$line" "Why: $(one_line "$SECRET_REASON")" >> "$TX/DECISIONS.md"
  fi
  say "SECRET_EXCEPTION_APPROVED $ID $SECRET_PATH $SECRET_RULE reviewer=$AGENT blob=$hash"
}
