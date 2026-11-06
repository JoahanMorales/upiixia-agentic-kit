# The claims transaction: a fresh shallow clone of the claims branch, one mutation, a secret check, a commit, a push;
# a rejected push retries on the new tip. Record and worklog helpers every mutation uses.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

init_temp() {
  TMP_BASE=$(cd "${TMPDIR:-/tmp}" && pwd -P) || gitfail "Cannot open TMPDIR."
  TXROOT=$(mktemp -d "$TMP_BASE/hack.XXXXXX") || gitfail "Cannot create temp dir."
}
remote_setup() {
  REMOTE_URL=$(git -C "$ROOT" config --get "remote.$REMOTE.url") ||
    UAK_CODE=no-remote gitfail "Missing remote $REMOTE in $ROOT$(r=$(git -C "$ROOT" remote 2>/dev/null | tr '\n' ' '); [ -z "$r" ] || printf ' (its remotes: %s)' "${r% }"). Run uak from the team checkout or one of its worktrees (a copy or a fresh clone without origin has no claims), or set UAK_REMOTE. Offline claims are not allowed."
  # A relative remote is relative to the main checkout, not to this worktree.
  case "$REMOTE_URL" in /*|[A-Za-z]:*|*://*|*@*:*) ;; *)
    main_dir=$(cd "$ROOT" && cd "$(git rev-parse --git-common-dir)/.." 2>/dev/null && pwd -P) || main_dir=$ROOT
    REMOTE_URL="$main_dir/$REMOTE_URL";; esac
  USER_NAME=$(git -C "$ROOT" config user.name 2>/dev/null || true)
  USER_EMAIL=$(git -C "$ROOT" config user.email 2>/dev/null || true)
  [ -n "$USER_NAME" ] || USER_NAME=${AGENT:-uak}
  [ -n "$USER_EMAIL" ] || USER_EMAIL=uak@localhost
}
fresh_state() {
  TX="$TXROOT/try-$ATTEMPT"
  mkdir "$TX" || gitfail "Cannot create transaction."
  # Windows (antivirus, OneDrive, indexers) can lock a just-created directory for a moment: 3 tries, and the
  # real cause in the message. Why (MLB hackathon): 6 "git init failed." from Cursor on Windows, cause unknown.
  init_try=0
  until git -C "$TX" init -q 2> "$TXROOT/init-error"; do
    init_try=$((init_try + 1))
    # A sandbox that forbids git in the system temp dir (Codex on macOS: "Operation not permitted" in /var/folders)
    # gets a temp dir inside the repo's own .git. Why (MLB hackathon): 12 tick/next/status/inbox calls failed this way.
    if [ "$init_try" -ge 2 ] && [ -z "${UAK_TMP_FALLBACK:-}" ] && grep -Eqi 'not permitted|permission denied|read-only' "$TXROOT/init-error"; then
      UAK_TMP_FALLBACK="$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null)/uak-tmp"
      if mkdir -p "$UAK_TMP_FALLBACK" 2>/dev/null && fb_root=$(mktemp -d "$UAK_TMP_FALLBACK/hack.XXXXXX" 2>/dev/null); then
        case "$TXROOT" in "$TMP_BASE"/hack.??????) rm -rf "$TXROOT";; esac
        TMP_BASE=$(cd "$UAK_TMP_FALLBACK" && pwd -P); TXROOT=$(cd "$fb_root" && pwd -P); TX="$TXROOT/try-$ATTEMPT"
        mkdir "$TX" || gitfail "Cannot create transaction."; init_try=0; continue
      fi
    fi
    [ "$init_try" -lt 3 ] || gitfail "git init failed in $TX: $(head -n 1 "$TXROOT/init-error"). Check TMPDIR (now ${TMPDIR:-/tmp}) is writable, or set TMPDIR to another folder."
    sleep "$init_try"; rm -rf "$TX"; mkdir "$TX" || gitfail "Cannot create transaction."
  done
  git -C "$TX" config user.name "$USER_NAME"
  git -C "$TX" config user.email "$USER_EMAIL"
  # Claims files are data read line by line: never CRLF. Git for Windows defaults to core.autocrlf=true, and every
  # field then ended in \r ("Presence-Seconds must be an integer" on the second command).
  git -C "$TX" config core.autocrlf false; git -C "$TX" config core.eol lf
  git -C "$TX" remote add origin "$REMOTE_URL" 2> "$TXROOT/remote-error" || gitfail "Invalid remote $REMOTE ($REMOTE_URL): $(head -n 1 "$TXROOT/remote-error")"
  # One fetch brings claims and the base's config (PROJECT.md, TASKS.md) together: one network round trip instead
  # of three (ls-remote, fetch claims, fetch config). done/integrate/merge prove ancestry on the base, so they
  # fetch it whole later (coord_init). Wi-Fi at events drops for seconds: 3 tries (Reap: 8 "Remote unreachable").
  local refs="+refs/heads/claims:refs/uak/claims"
  case "$CMD" in done|integrate|merge) ;; *) refs="$refs +refs/heads/$BASE:refs/uak/config";; esac
  net_try=0 HAS_REMOTE=yes
  until git -C "$TX" fetch -q --depth 2 origin $refs 2> "$TXROOT/git-error"; do
    if grep -qi "couldn't find remote ref refs/heads/claims" "$TXROOT/git-error"; then
      HAS_REMOTE=no
      case "$CMD" in done|integrate|merge) break;; esac
      git -C "$TX" fetch -q --depth 2 origin "+refs/heads/$BASE:refs/uak/config" 2> "$TXROOT/git-error" && break
    fi
    net_try=$((net_try + 1)); [ "$net_try" -lt 3 ] || UAK_CODE=remote-unreachable gitfail "Remote unreachable (3 tries). $(head -n 1 "$TXROOT/git-error")"
    sleep $((net_try * 2))
  done
  if [ "$HAS_REMOTE" = yes ]; then
    # HEAD^ (depth 2) is enough for the append-only lint; the full claims history (600+ commits at Reap) is not.
    git -C "$TX" checkout -q -b claims refs/uak/claims || gitfail "checkout claims failed."
  else
    git -C "$TX" checkout -q --orphan claims || gitfail "Cannot initialize claims."
  fi
  mkdir -p "$TX/tasks" "$TX/claims" "$TX/worklog"
}
is_reserved() { case "$1" in CLAIMED|BLOCKED|REVIEW) return 0;; *) return 1;; esac; }
task_file() { printf '%s/tasks/%s.md\n' "$TX" "$ID"; }
claim_file() { printf '%s/claims/%s.md\n' "$TX" "$ID"; }
require_owner() {
  RECORD=$(task_file); CLAIM=$(claim_file)
  [ -f "$CLAIM" ] && [ -f "$RECORD" ] || UAK_CODE=no-claim conflict "$ID has no active claim; do not modify someone else's work."
  [ "$(field "$CLAIM" Owner)" = "$AGENT" ] || UAK_CODE=not-owner conflict "$ID belongs to $(field "$CLAIM" Owner)."
  WL=$(field "$RECORD" Worklog)
  valid_worklog "$WL" || die "Invalid worklog path."
  [ -f "$TX/$WL" ] || die "Missing worklog $WL."
}
valid_worklog() { printf '%s\n' "$1" | grep -Eq '^worklog/WL-[A-Za-z0-9_.-]+\.md$'; }
put() {
  file=$1 key=$2 value=$(one_line "$3")
  UAK_AWK_VALUE="$value" awk -v key="$key" '
    BEGIN {value=ENVIRON["UAK_AWK_VALUE"]}
    index($0,key ": ")==1 {$0=key ": " value; seen=1} {print}
    END {if(!seen) print key ": " value}' "$file" > "$TXROOT/edit"
  mv "$TXROOT/edit" "$file"
}
summary_text() {
  valid_worklog "$WL" || die "Invalid worklog path."
  awk '/^## Live summary$/ {on=1;next} /^## History$/ {on=0} on && NF {print}' "$TX/$WL"
}
read_token() { { cat "$(claim_file)"; summary_text; } | cksum | awk '{print $1 "-" $2}'; }
set_summary() {
  {
    printf '# %s · %s\n\n## Live summary\n' "$WL" "$ID"
    printf '%s\n' "- Done: $(one_line "$DONE_TEXT")" "- Decision: $(one_line "$DECISION_TEXT")" \
      "- Why: $(one_line "$WHY_TEXT")" "- Failing: $(one_line "$FAILS_TEXT")" \
      "- Commands: $(one_line "$COMMANDS_TEXT")" "- Next: $(one_line "$NEXT_TEXT")"
    printf '\n## History\n'
    [ ! -f "$TX/$WL" ] || awk 'on {print} /^## History$/ {on=1}' "$TX/$WL"
  } > "$TXROOT/summary"
  mv "$TXROOT/summary" "$TX/$WL"
}
event() { printf '%s\n' "- $NOW | $STATE | $AGENT | $(one_line "$1")" >> "$TX/$WL"; coord_event; }
update_summary_field() {
  label=$1 text=$(one_line "$2")
  UAK_AWK_TEXT="$text" awk -v label="$label" '
    BEGIN {text=ENVIRON["UAK_AWK_TEXT"]}
    /^## Live summary$/ {on=1} /^## History$/ {on=0}
    on && index($0,"- " label ": ")==1 {$0="- " label ": " text}
    {print}' "$TX/$WL" > "$TXROOT/summary"
  mv "$TXROOT/summary" "$TX/$WL"
}
refresh_lease() {
  UNTIL=$((NOW + LEASE))
  [ "$(field "$RECORD" State)" != REVIEW ] || UNTIL=$((NOW + ${REVIEW_LEASE:-$LEASE}))
  put "$RECORD" Lease-Until "$UNTIL"; put "$RECORD" Updated "$NOW"
  put "$CLAIM" Lease-Until "$UNTIL"; put "$CLAIM" Updated "$NOW"
}
# STATE.md after every mutation. One awk pass reads the records (lib/state.awk's rule: the first "KEY: " line, one
# trailing \r dropped); the shell only formats. Why (UAK-016): `$(field ...)` per record and per state was about 90 of
# heartbeat's 152 processes and grew with every task ever claimed. The output is byte-identical to that version
# (tests/test_snapshot.py runs both); values are printed as text, never evaluated.
snapshot() {
  [ -f "$TX/DECISIONS.md" ] || {
    printf '# DECISIONS\n\nCoordination decisions on the claims branch.\nWhy: a reversible option after 15 min keeps work moving.\n' > "$TX/DECISIONS.md"
  }
  local coord_v phase freeze state ids n_ids snap_f snap_l snap_k snap_nt=0 snap_nc=0 snap_hb=0 snap_x lu
  local -a snap_files snap_st snap_bl snap_c
  snap_files=(); snap_st=(); snap_bl=(); snap_c=()
  for snap_f in "$TX"/tasks/*.md; do [ -f "$snap_f" ] || continue; snap_files[${#snap_files[@]}]=$snap_f; snap_nt=$((snap_nt + 1)); done
  for snap_f in "$TX"/claims/*.md; do [ -f "$snap_f" ] || continue; snap_files[${#snap_files[@]}]=$snap_f; snap_nc=$((snap_nc + 1)); done
  if [ -f "$BACKLOG" ]; then snap_files[${#snap_files[@]}]=$BACKLOG; snap_hb=1; fi
  # /dev/null last: with no record and no backlog awk would read stdin.
  awk -v nt="$snap_nt" -v nc="$snap_nc" -v hb="$snap_hb" '
    BEGIN { split("ID State Owner Lease-Until", K, " "); split("AVAILABLE CLAIMED BLOCKED REVIEW INTEGRATED CANCELLED", ST, " ")
            for (i = 1; i <= nt + nc + hb; i++) pos[ARGV[i]] = i }
    { i = pos[FILENAME] }
    i > nt + nc { if (hb && i == nt + nc + 1 && /^## [A-Z][A-Z0-9]*-[0-9]/) bl[++nb] = $2; next }
    { line = $0; sub(/\r$/, "", line)
      for (k = 1; k <= 4; k++) if (!((i, K[k]) in v) && index(line, K[k] ": ") == 1) v[i, K[k]] = substr(line, length(K[k]) + 3) }
    END { for (s = 1; s <= 6; s++) { ids = ""
            for (j = 1; j <= nt; j++) if (((j, "State") in v) && v[j, "State"] == ST[s] && ((j, "ID") in v)) ids = ids v[j, "ID"] " "
            print "S" ids }
          for (b = 1; b <= nb; b++) print "B" bl[b]
          for (j = nt + 1; j <= nt + nc; j++) for (k = 1; k <= 4; k++) print "C" (((j, K[k]) in v) ? v[j, K[k]] : "") }
  ' ${snap_files[@]+"${snap_files[@]}"} /dev/null > "$TXROOT/snapshot-records" || return 1
  while IFS= read -r snap_l || [ -n "$snap_l" ]; do
    case $snap_l in
      S*) snap_st[${#snap_st[@]}]=${snap_l#S};;
      B*) snap_bl[${#snap_bl[@]}]=${snap_l#B};;
      C*) snap_c[${#snap_c[@]}]=${snap_l#C};;
    esac
  done < "$TXROOT/snapshot-records"
  {
    phase='execution'
    coord_cfg Freeze-Epoch 0; freeze=$coord_v
    if [ "$freeze" -gt 0 ] && [ "$NOW" -ge "$freeze" ]; then phase='feature freeze; authorized fixes, rehearsal and submission only'; fi
    printf '# STATE\n\nPhase: %s\nUpdated: %s\n' "$phase" "$NOW"
    snap_k=0
    for state in AVAILABLE CLAIMED BLOCKED REVIEW INTEGRATED CANCELLED; do
      ids=${snap_st[$snap_k]}; snap_k=$((snap_k + 1))
      # AVAILABLE: the backlog's IDs with no record, then the records released back to AVAILABLE.
      if [ "$state" = AVAILABLE ] && [ "$snap_hb" = 1 ]; then
        snap_x=
        for snap_f in ${snap_bl[@]+"${snap_bl[@]}"}; do [ -f "$TX/tasks/$snap_f.md" ] || snap_x="$snap_x$snap_f "; done
        ids=$snap_x$ids
      fi
      # Why (UpiixSol): a silent cut at 120 chars made INTEGRATED look stuck at UPS-015 with 26 done.
      if [ "${#ids}" -gt 120 ]; then
        n_ids=$(printf '%s' "$ids" | wc -w | tr -d ' ')
        ids="($n_ids; last 12) ... $(printf '%s' "$ids" | awk '{for(i=(NF>12?NF-11:1);i<=NF;i++) printf "%s ", $i}')"
      fi
      printf '%s: %s\n' "$state" "${ids:--}"
    done
    printf '\nClaims (first 24; status --task ID shows detail):\n'
    snap_k=0
    while [ "$snap_k" -lt "${#snap_c[@]}" ] && [ "$snap_k" -lt 96 ]; do
      # An expired lease says so (Hacktoberfest: STATE.md showed a stale Lease-Until as if the claim were live).
      lu=${snap_c[$((snap_k + 3))]}; case "$lu" in ''|*[!0-9]*) lu=0;; esac
      snap_x=
      [ "${snap_c[$((snap_k + 1))]}" = REVIEW ] || [ "$lu" -eq 0 ] || [ "$NOW" -lt "$lu" ] || snap_x=' (EXPIRED: release --expired --read-summary TOKEN)'
      printf '%s | %s | %s | until %s%s\n' "${snap_c[$snap_k]}" "${snap_c[$((snap_k + 1))]}" "${snap_c[$((snap_k + 2))]}" "$lu" "$snap_x"
      snap_k=$((snap_k + 4))
    done
    printf '\nBlockers: BLOCKED tasks; use status --task ID --summary.\nCurrent decisions (last 5):\n'
    grep '^-' "$TX/DECISIONS.md" | tail -n 5 | cut -c 1-180
    printf '\nGlobal next step: available P0; else review PRs, tests, demo, rehearsal.\nWhy: bounded snapshot to resume without rereading history.\n'
  } > "$TX/STATE.md"
}
# Identities that differ only in case collide on macOS and Windows disks (meta/agents/Ana-1.md opens ana-1.md), and
# git add then commits one over the other. The name already on claims wins. Why (portability audit, Oct 2026).
identity_case_check() {
  local other
  # A human's name is matched case-blind already (v5.5: the Mac folded Victor.md into victor.md).
  [ -n "$AGENT" ] && [ "$AGENT" != "$HUMAN" ] || return 0
  other=$(git -C "$TX" ls-tree --name-only HEAD meta/agents/ 2>/dev/null | sed 's#^meta/agents/##; s#\.md$##' |
    awk -v me="$AGENT" 'tolower($0) == tolower(me) && $0 != me { print; exit }')
  [ -z "$other" ] || conflict "Identity $AGENT differs from $other only in case; on macOS and Windows they are one file. Use $other (UAK_AGENT=$other)."
}
mutate() {
  coord_init
  identity_case_check
  coord_mark_human
  RECORD=$(task_file); CLAIM=$(claim_file)
  # The command's mutation, named in lib/commands.tsv (in claim.sh, done.sh, plan.sh, messages.sh…). MUTATE_NOOP: an
  # idempotent call that already printed its OK (heartbeat of a closed task, integrate of an INTEGRATED one).
  reg_find "$CMD" && [ "$REG_MUTATE" != - ] || die "internal: $CMD has no mutation in lib/commands.tsv."
  MUTATE_NOOP=no; "$REG_MUTATE"; [ "$MUTATE_NOOP" = no ] || return 0
  # An idempotent read changes no STATE and creates no empty commit.
  if [ -n "$(git -C "$TX" status --porcelain)" ]; then snapshot; fi
}
transaction() {
  ATTEMPT=0
  while :; do
    ATTEMPT=$((ATTEMPT + 1)); HANDOVER_ENV_WT=
    # A retry runs on a fresh clock too. Why (Hacktoberfest, slow Wi-Fi): a lock committed after 36 min of retries
    # carried the first attempt's time, already expired, and a second reviewer took the same SHA.
    [ "$ATTEMPT" -eq 1 ] || clock_now
    fresh_state; mutate
    git -C "$TX" add -A || gitfail "git add failed."
    # Nothing that looks like a key reaches claims: every clone of the repository reads it (public repo = public).
    # Why (audit, Oct 2026): a key pasted into uak msg, a checkpoint or a review note was committed to claims.
    secret_kind=$(git -C "$TX" diff --cached -U0 --no-color 2>/dev/null | sed -n 's/^+//p' | grep -v '^++ ' | secret_like) &&
      UAK_CODE=secret-refused conflict "Refused: this would write something that looks like a secret ($secret_kind) to the claims branch, which every clone of the repository can read. Keep it in .env and name the variable instead (rotate it if it was real)."
    if git -C "$TX" diff --cached --quiet; then
      [ "$CMD" != allow ] || say "OK allow (already allowed) | nothing to record"
      [ "$CMD" != learn ] || say "OK learn $MEM_DONE | nothing to record"
      return 0
    fi
    git -C "$TX" commit -q -m "uak: $CMD $ID ($AGENT)" || gitfail "git commit failed."
    if git -C "$TX" push --porcelain origin HEAD:refs/heads/claims > "$TXROOT/push" 2>&1; then
      [ -z "$HANDOVER_ENV_WT" ] || handover_env_apply
      if [ "${QUIET:-no}" != yes ]; then
        if [ "$SESSION_ONLY" = yes ]; then say "OK checkpoint --session | budget reset | attempt $ATTEMPT"
        elif [ "$CMD" = tick ]; then say "OK tick | deadlines reconciled | attempt $ATTEMPT"
        elif [ "$CMD" = plan ] && [ "$PLAN_AMEND" = yes ]; then say "OK plan --amend$(printf ' %s' $plan_ids) | new Paths/Verify/criteria on claims; their owners got one message | attempt $ATTEMPT"
        elif [ "$CMD" = plan ]; then say "OK plan | tasks published on claims | attempt $ATTEMPT"
        elif [ "$CMD" = allow ] && [ "$ALLOW_TESTS" = yes ]; then say "OK allow --tests${ALLOW_DONE:- (already allowed)} | done accepts changes to its existing tests | attempt $ATTEMPT"
        elif [ "$CMD" = allow ]; then say "OK allow${ALLOW_DONE:- (already allowed)} | claim and merge allowed after the freeze | attempt $ATTEMPT"
        elif [ "$CMD" = register-reviewer ]; then say "OK register-reviewer $REGISTER_REVIEWER | attempt $ATTEMPT"
        elif [ "$CMD" = handover ]; then say "OK handover $ID → $DONE_TO | lease renewed; $DONE_TO continues from the live summary"
        elif [ "$CMD" = learn ]; then say "OK learn $MEM_DONE | uak next shows it to whoever works there"
        elif [ "$CMD" = away ]; then say "OK away $AGENT | out of the reviewer rotation; messages to you reach your tasks; ${AWAY_TASKS:-0} claim(s) keep their leases. Any uak command brings you back."
        elif [ "$CMD" = retire ]; then say "OK retire$RETIRE_NAMES | out of the reviewer rotation; a new claim brings an identity back"
        elif [ "$CMD" = followup ]; then say "OK followup $NEW_ID (after $ID, same Paths) | take it: bash .uak/bin/wt new $NEW_ID --agent ${AGENT}"
        elif [ "$REVIEW_DECLINE" = yes ]; then say "OK review --decline $ID | offered to another agent now"
        elif [ "$REVIEW_STARTED" = yes ]; then say "OK review --start $ID | yours for $(( ${UAK_REVIEW_LOCK_SECONDS:-1200} / 60 )) min; finish with --verdict"
        else say "OK $CMD $ID | $(field "$RECORD" State) | attempt $ATTEMPT"
          # The next step in the output itself: it reaches every harness, Cursor included (no post-tool hook there).
          case "$CMD" in
            done) [ "$(field "$RECORD" State)" != REVIEW ] ||
                    say "Next: bash .uak/bin/uak wait $ID --for approve (one call; returns on approve or reject). Meanwhile: uak next for other work; do not poll status.";;
            # The task's slice of the code map, not a pointer to it (MLB, v5 week: 9 map calls in 67 tasks).
            claim) brief=$(bash "$UAK_BIN/map" brief "$ID" --paths "$PATHS" --backlog "$BACKLOG" 2>/dev/null | head -n 10)
                   [ -z "$brief" ] || say "$brief"
                   say "Query, do not open whole files: uak map find NAME · callers NAME · users FILE · recall $ID (lessons)."
                   mem_for_task "$ID"
                   ui_brief; test_brief;;
          esac
        fi
      fi
      if [ "$CMD" = handoff ]; then print_task; fi
      [ -z "$REVIEW_HINT" ] || say "$REVIEW_HINT"
      [ -z "$DONE_HINT" ] || say "$DONE_HINT"
      return 0
    fi
    if grep -Eqi 'pre-receive hook declined|hook declined|protected branch|permission denied|authentication failed|remote rejected.*(policy|prohibited)' "$TXROOT/push" ||
       ! grep -Eqi 'fetch first|non-fast-forward|cannot lock ref|already exists|failed to update ref|incorrect old value provided' "$TXROOT/push"; then
      # Why (Chilangatón): a laptop with an https remote and no stored credentials failed its first claim 3 times
      # ("could not read Username ... terminal prompts disabled"), and the agent gave up on wt new.
      push_hint=
      grep -Eqi 'could not read Username|terminal prompts disabled|Authentication failed|Permission denied \(publickey\)|Invalid username or (password|token)' "$TXROOT/push" &&
        push_hint=" This machine has no Git credentials for $REMOTE: gh auth login && gh auth setup-git (https remote) or an SSH key, then retry; bash .uak/bin/uak start checks push before the first claim."
      UAK_CODE=push-failed gitfail "push failed; the claim was not confirmed. $(tail -n 2 "$TXROOT/push")$push_hint"
    fi
    # Why: another valid push means redo from the new remote and revalidate, not give up.
    [ "${QUIET:-no}" = yes ] || say "RETRY $CMD $ID | remote contention; refetch and revalidate" >&2
    previous_tip=$(git -C "$TX" rev-parse HEAD^ 2>/dev/null || true)
    remote_tip=$(git -C "$TX" ls-remote origin refs/heads/claims 2>/dev/null | awk '{print $1; exit}')
    [ -z "$remote_tip" ] || [ "$remote_tip" != "$previous_tip" ] || gitfail "push rejected without remote progress; check permissions/protection."
    [ "$ATTEMPT" -lt "${UAK_MAX_ATTEMPTS:-30}" ] || UAK_CODE=contention gitfail "claims contention: $ATTEMPT attempts. Wait a minute and retry."
    # Jittered exponential backoff (0.25 s .. 4 s). Why (Reap): 12 agents retried in lockstep; an approval
    # needed 14 attempts and a checkpoint 8, because everybody refetched and pushed at the same instant.
    backoff_cap=$((250 * (1 << (ATTEMPT > 4 ? 4 : ATTEMPT - 1)))); backoff=$((RANDOM % backoff_cap + 50))
    sleep "$((backoff / 1000)).$(printf '%03d' $((backoff % 1000)))" 2>/dev/null || sleep 1
    # The next loop starts from a fresh clone of the new remote: IDs, leases and overlaps are revalidated.
  done
}
# tick: the deadline reconcile as its own call (a scheduler, the uak-tick Action).
tick_run() { AGENT=${AGENT:-scheduler}; transaction; }
