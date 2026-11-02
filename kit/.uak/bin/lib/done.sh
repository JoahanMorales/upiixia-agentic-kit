# done and integrate: the gates at the moment of shipping (UI shots, test-first) and the records they write.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

# At claim: a task in UI-Paths is told what to open before the first line of UI. Why (frontend audit, Oct 2026):
# product-ui reached agents only when its description happened to match, and DESIGN.md was read by a few.
ui_brief() {
  local ui r
  ui=$(coord_source_field UI-Paths -); [ -n "$ui" ] && [ "$ui" != - ] || return 0
  normalize_paths "$ui" > "$TXROOT/ui-paths" 2>/dev/null && normalize_paths "$PATHS" > "$TXROOT/ui-task" 2>/dev/null || return 0
  overlaps "$TXROOT/ui-task" "$TXROOT/ui-paths" || return 0
  r=$(awk -v id="$ID" '/^## / { on = ($2 == id) } on && /Recipe:/ { s = $0; sub(/.*Recipe:[* ]*/, "", s); print s; exit }' "$BACKLOG" 2>/dev/null)
  say "UI TASK: before the first line, read web/DESIGN.md (your row of ## Screens${r:+: $r}), open the locked screen with that recipe in web/public/design-lock/screens/ (Read the PNG), and load the skill product-ui. Build only from web/src/lib/ui."
  say "Before done: capture 1280 and 390 into .uak-shots/$ID/ and run the design-critic subagent; done checks its SHIP verdict."
}
# At claim: the task's tests and the red, before the first line of code. Why (v5.10, harness review): the agent heard
# of the test-first gate only when done refused it, one round trip late; a rule reaches agents at the moment it applies.
test_brief() { # [next]: only where the gate is on (next keeps its 15-line budget)
  local policy names t
  case "$(rm_task_value Test-First)" in no*|No*|off*) return 0;; esac
  policy=$(coord_source_field Test-First warn); t=$(rm_task_value Type)
  case "$t" in bug*|Bug*|fix*) [ "$policy" = no ] || policy=yes;; esac
  [ "$policy" != no ] || return 0
  [ "${1:-}" != next ] || [ "$policy" = yes ] || return 0
  names=$(rm_task_value Tests); case "$names" in -|none|None) names=;; esac
  say "TEST FIRST: ${names:+write the tests $names (their names are the spec), }the stub (signature, wrong value), then bash .uak/bin/uak red $ID: it must fail on its assertion; then implement until Verify is green. Never change an existing test to pass: done refuses it (skill test-first)."
}
# A task that writes where screens live (UI-Paths in PROJECT.md) ships with what someone saw: screenshots at 1280 and
# 390 wide and the design critic's verdict on this commit, in <worktree>/.uak-shots/ID/ (git-ignored). Why
# (Hacktoberfest): approvals said "UI not walked in browser" and "no 390x844 screenshot", the critic ran on a few PRs,
# and ten screens shipped as copies of one template.
ui_gate() {
  local ui d f missing= short
  ui=$(coord_source_field UI-Paths -); [ -n "$ui" ] && [ "$ui" != - ] || return 0
  normalize_paths "$ui" > "$TXROOT/ui-paths" 2>/dev/null || return 0
  normalize_paths "$(rm_task_value Paths)" > "$TXROOT/ui-task" 2>/dev/null || return 0
  overlaps "$TXROOT/ui-task" "$TXROOT/ui-paths" || return 0
  if [ -n "$NO_UI_TEXT" ]; then EVIDENCE="$EVIDENCE · no visible change: $NO_UI_TEXT"; return 0; fi
  d="$2/.uak-shots/$ID"; short=$(printf '%s' "$1" | cut -c 1-7)
  for f in 1280.png 390.png critic.txt; do [ -s "$d/$f" ] || missing="$missing $f"; done
  [ -z "$missing" ] || UAK_CODE=ui-shots-missing conflict "$ID writes UI ($ui): it ships with what was seen. Missing in .uak-shots/$ID/:$missing. Capture the screens it changed at 1280x720 and 390x844 there (skill webapp-testing), then run the design-critic subagent on them: it writes critic.txt. No visible change? done $ID ... --no-ui \"why\"."
  grep -q '^VERDICT: SHIP' "$d/critic.txt" ||
    UAK_CODE=critic-fix conflict "The design critic said FIX for $ID ($(grep -m 1 '^VERDICT' "$d/critic.txt" 2>/dev/null)). Fix its P1s (.uak-shots/$ID/critic.txt), capture again and rerun it."
  grep -q "$short" "$d/critic.txt" ||
    UAK_CODE=critic-stale conflict "critic.txt in .uak-shots/$ID/ is about another commit; this one is $short. Capture again and rerun design-critic on it."
}
# Tests only grow, a task's named tests exist, and its test failed before its code. Why (v5.10, test-first): agents
# optimize toward green; stuck on red they edit the assertion, add a skip or delete the test, and a test written after
# the code passes by construction. Each rule is a check here, not a line of prose (lib/tests.sh).
test_gate() { # $1 tip, $2 worktree
  local range findings policy f names missing red sha reason ttype
  [ -d "$2" ] || return 0
  range="origin/$BASE...$1"
  tf_findings "$2" "$range" "$TXROOT" > "$TXROOT/tf-findings" 2>/dev/null
  if grep -q '^FAIL' "$TXROOT/tf-findings"; then
    if [ -f "$TX/backlog/TEST-CHANGES.md" ] && grep -q "^- $ID |" "$TX/backlog/TEST-CHANGES.md"; then
      EVIDENCE="$EVIDENCE · existing tests changed with a human's approval ($(grep -m 1 "^- $ID |" "$TX/backlog/TEST-CHANGES.md" | cut -d '|' -f 3 | tr -d ' '))"
    else
      findings=$(grep '^FAIL' "$TXROOT/tf-findings" | head -n 4 | sed 's/^FAIL /  /')
      UAK_CODE=tests-weakened conflict "Tests only grow on $ID: an existing test is a spec, not a suggestion.
$findings
Restore them and fix the code. If a test is wrong, do not change it: uak msg human \"$ID · file:test · why it is wrong\"; a human allows it with UAK_HUMAN=NAME bash .uak/bin/uak allow $ID --tests --reason TEXT."
    fi
  fi
  grep '^WARN' "$TXROOT/tf-findings" | head -n 3 | sed 's/^WARN /WARN: /' >&2
  names=$(rm_task_value Tests)
  case "$names" in ''|-|none|None) ;; *)
    missing=$(tf_missing_names "$2" "$range" "$names" | head -n 5 | tr '\n' ',' | sed 's/,$//; s/,/, /g')
    [ -z "$missing" ] || UAK_CODE=tests-missing conflict "$ID names tests the branch does not add: $missing. They are the task's spec: write each one (its name in the test), see it fail (uak red $ID), then implement.";;
  esac
  policy=$(coord_source_field Test-First warn)
  ttype=$(rm_task_value Type)
  case "$ttype" in bug*|Bug*|fix*) [ "$policy" = no ] || policy=yes;; esac
  case "$(rm_task_value Test-First)" in no*|No*|off*) policy=no;; esac
  [ "$policy" != no ] || return 0
  if [ -n "$NO_RED_TEXT" ]; then EVIDENCE="$EVIDENCE · no red: $NO_RED_TEXT"; return 0; fi
  red="$(git -C "$2" rev-parse --absolute-git-dir 2>/dev/null)/uak-red/$ID.txt"
  sha=$(sed -n 's/^SHA: //p' "$red" 2>/dev/null | head -n 1)
  if [ -n "$sha" ] && git -C "$2" merge-base --is-ancestor "$sha" "$1" 2>/dev/null; then
    reason=$(sed -n 's/^Reason: //p' "$red" | head -n 1 | cut -c 1-120)
    EVIDENCE="$EVIDENCE · red at $(printf '%s' "$sha" | cut -c 1-7): $reason"
    return 0
  fi
  f="No red recorded for $ID$([ -z "$sha" ] || printf ' on this branch'): with the test written and the code not yet, run bash .uak/bin/uak red $ID (it must fail on its assertion). Nothing a test can show first (docs, config, styling)? done $ID ... --no-red \"why\"."
  case "$ttype" in bug*|Bug*|fix*) f="$f A bug starts with the test that reproduces it.";; esac
  case "$policy" in yes|required) UAK_CODE=red-missing conflict "$f";; *) say "WARN: $f" >&2;; esac
}
# integrate: any identity records a merged PR of a task in REVIEW (the proof is verifiable). A no-op (MUTATE_NOOP) when
# the task is already INTEGRATED.
integrate_mutate() {
  # Why (UpiixSol): a human merged on GitHub while the owner agent was offline; the task sat in REVIEW and
  # blocked its dependents for hours. The proof is verifiable, so any identity may record it.
  if [ -f "$RECORD" ] && [ "$(field "$RECORD" State)" = INTEGRATED ]; then
    say "OK integrate $ID | already INTEGRATED ($(field "$RECORD" Merge-Commit | cut -c 1-7)); nothing to do"; MUTATE_NOOP=yes; return 0
  fi
  [ -f "$RECORD" ] && [ "$(field "$RECORD" State)" = REVIEW ] ||
    conflict "$ID is $(st=$(field "$RECORD" State); printf '%s' "${st:-AVAILABLE}"), not REVIEW; integrate records the merged PR of a task under review (INTEGRATED needs nothing)."
  WL=$(field "$RECORD" Worklog); valid_worklog "$WL" || die "Invalid worklog path."
  [ -f "$TX/$WL" ] || die "Missing worklog $WL."
  PR_URL=$(field "$RECORD" PR)
  git check-ref-format "refs/heads/$BASE" >/dev/null 2>&1 || die "Invalid UAK_BASE."
  git -C "$TX" fetch -q origin "refs/heads/$BASE:refs/uak/base" || gitfail "Could not verify remote base branch $BASE."
  resolve_task_tip || conflict "$RM_REASON"
  tip=$RM_TIP
  # A human who merged it on the forge is the approval: from the shell, under UAK_HUMAN, it is recorded as theirs.
  # Why (Chilangatón): PB-027 was merged on GitHub with no approval on claims; integrate refused, and the task stayed
  # in REVIEW after the event.
  if ! approval_check "$tip" "$PR_URL"; then
    [ -n "$HUMAN" ] && [ "$AGENT" = "$HUMAN" ] ||
      conflict "$RM_REASON. Approve the merged SHA first: uak review $ID --sha ${tip:-SHA} --verdict approve. A human merged it? That human records it: UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate $ID"
    APPROVED_BY="human:$HUMAN"
    # A human merge over a reject that still covers this code is a decision: it says why, it is logged, and the
    # rejecter hears it. Why (Hacktoberfest): a task rejected for files outside its Paths was merged on GitHub a
    # minute later and recorded as human-approved; the reject stayed on record and nobody was told.
    if rm_standing_reject; then
      [ -n "$WHY_TEXT" ] || conflict "$RM_REJECTER rejected this code of $ID. A human who merged it anyway records why: UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate $ID --reason \"why the reject does not apply\""
      [ -f "$TX/DECISIONS.md" ] || printf "# DECISIONS\n" > "$TX/DECISIONS.md"
      printf '%s\n' "- $NOW | $ID | merged by $HUMAN over the reject of $RM_REJECTER | Why: $(one_line "$WHY_TEXT")" >> "$TX/DECISIONS.md"
      msg_append "agent:$RM_REJECTER,task:$ID" info "$ID" "$ID was merged by $HUMAN over your reject at ${tip%"${tip#???????}"}: $(one_line "$WHY_TEXT")"
    fi
  fi
  if [ -n "$MERGE_COMMIT" ]; then
    merged=$(git -C "$TX" rev-parse --verify "$MERGE_COMMIT^{commit}" 2>/dev/null) || conflict "COMMIT not in the remote history of $BASE."
  elif [ "$RM_REVIEW_MODE" = gh ] && [ -n "$RM_GH_MERGE" ]; then merged=$RM_GH_MERGE
  else merged=$(git -C "$TX" rev-parse refs/uak/base); fi
  integrated_check "$tip" "$merged" || conflict "$RM_REASON (squash merge: pass --integrated COMMIT)"
  STATE=INTEGRATED
  put "$RECORD" Integration-Proof "$RM_PROOF"; put "$RECORD" Merge-Commit "$merged"
  put "$RECORD" Reviewer "$APPROVED_BY"; put "$RECORD" Task-Tip "$tip"; put "$RECORD" State INTEGRATED
  put "$RECORD" Next "Integrated in $BASE: $merged; claim next P0"
  put "$RECORD" Lease-Until 0; put "$RECORD" Updated "$NOW"
  update_summary_field Next "Integrated in $BASE: $merged (recorded by $AGENT)"
  rm -f "$CLAIM"
  event "integrate; recorded by $AGENT; PR $PR_URL; merged $merged; proof $RM_PROOF"
  msg_notify_related "$ID" integrated "$ID integrated in $BASE ($merged), recorded by $AGENT. If you depend on it: git fetch origin && git merge --no-edit origin/$BASE"
}
# done: REVIEW with the PR and evidence after the gates (UI shots, test-first), and one reviewer asked; or, with
# --integrated, INTEGRATED after a human merge with a verified approval.
done_mutate() {
  require_owner; STATE=REVIEW
  task_branch=$(field "$RECORD" Branch)
  task_worktree=$(field "$RECORD" Worktree)
  # The path comes from claims: only a checkout of this repository counts. Why (audit, Oct 2026): a record
  # pointing at another checkout made done run that checkout's map.
  [ ! -d "$task_worktree" ] || same_repo_worktree "$task_worktree" || task_worktree="$TXROOT/not-a-worktree"
  tip=$(field "$RECORD" Task-Tip)
  # Handed over from another machine: the recorded Worktree is theirs. This checkout on the task's branch is the
  # new one. Why (Chilangatón): after a Windows → macOS handover, PB-027's done died with "Missing worktree";
  # the way out was release and re-claim, which put a decision and two heartbeat conflicts on claims.
  # Never the main checkout: a task lives in a worktree of its own (claim refuses the main checkout too).
  if [ ! -d "$task_worktree" ] && [ "$(git -C "$ROOT" symbolic-ref --short HEAD 2>/dev/null)" = "$task_branch" ] &&
     [ "$ROOT" != "$(cd "$(git -C "$ROOT" worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)" 2>/dev/null && pwd -P)" ]; then
    task_worktree=$ROOT; put "$RECORD" Worktree "$ROOT"; put "$CLAIM" Worktree "$ROOT"
  fi
  if [ -z "$MERGE_COMMIT" ]; then
    tip=$(git -C "$task_worktree" rev-parse HEAD 2>/dev/null) ||
      die "Missing worktree to record Task-Tip: $task_worktree is not on this machine. Run done from a checkout of $task_branch."
  else
    git check-ref-format "refs/heads/$BASE" >/dev/null 2>&1 || die "Invalid UAK_BASE."
    git -C "$TX" fetch -q origin "refs/heads/$BASE:refs/uak/base" ||
      gitfail "Could not verify remote base branch $BASE."
    resolve_task_tip || conflict "$RM_REASON"
    tip=$RM_TIP
    [ -n "$tip" ] || conflict "Missing Task-Tip; record done (REVIEW) or push the branch first."
    task_base=$(field "$RECORD" Task-Base)
    [ -n "$task_base" ] && [ "$tip" != "$task_base" ] ||
      conflict "TIP equals the claim base; nothing implemented."
    merged=$(git -C "$TX" rev-parse --verify "$MERGE_COMMIT^{commit}" 2>/dev/null) ||
      conflict "COMMIT not in the remote history of $BASE."
    approval_check "$tip" "$PR_URL" || conflict "$RM_REASON"
    [ -z "$REVIEWER" ] || [ "$REVIEWER" = "$APPROVED_BY" ] || conflict "--reviewer does not match the verified approval."
    integrated_check "$tip" "$merged" || conflict "$RM_REASON"
    REVIEWER=$APPROVED_BY
    put "$RECORD" Integration-Proof "$RM_PROOF"
    STATE=INTEGRATED
    put "$RECORD" Merge-Commit "$merged"; put "$RECORD" Reviewer "$REVIEWER"
  fi
  [ "$STATE" != REVIEW ] || ui_gate "$tip" "$task_worktree"
  [ "$STATE" != REVIEW ] || test_gate "$tip" "$task_worktree"
  put "$RECORD" Task-Tip "$tip"
  put "$RECORD" State "$STATE"; put "$CLAIM" State "$STATE"
  put "$RECORD" PR "$PR_URL"; put "$CLAIM" PR "$PR_URL"; put "$RECORD" Evidence "$EVIDENCE"
  put "$RECORD" Next "Another agent reviews $PR_URL; run .uak/bin/smoke"
  put "$CLAIM" Next "Another agent reviews $PR_URL; run .uak/bin/smoke"
  update_summary_field Done "$EVIDENCE"
  update_summary_field Next "Another agent reviews $PR_URL; run .uak/bin/smoke"
  # Contract check at the moment of shipping: does this diff touch files that other live tasks import, with no
  # contract message from you on this task? Why (adoption eval): with the rule in context (AGENTS.md §5.1) a
  # Sonnet agent changed a function another claimed task imported, pushed and shipped without telling it.
  if [ "$STATE" = REVIEW ] && [ -d "$task_worktree" ]; then
    # Files outside Paths, said now rather than after a review round. Why (Hacktoberfest): two tasks with web
    # files outside their Paths each cost a review round and two red gate runs.
    # What the branch changes against the base it last merged (three dots), as the gate sees it, with the gate's
    # exemptions for new files (Additive-Paths, empty files).
    local outside= f add=-
    normalize_paths "$(rm_task_value Paths)" > "$TXROOT/done-paths" 2>/dev/null || : > "$TXROOT/done-paths"
    : > "$TXROOT/done-additive"; [ ! -f "$TXROOT/coord-source" ] || add=$(coord_source_field Additive-Paths -)
    [ "$add" = - ] || normalize_paths "$add" > "$TXROOT/done-additive" 2>/dev/null || : > "$TXROOT/done-additive"
    git -C "$task_worktree" -c core.quotePath=false diff --no-renames --name-only "origin/$BASE...$tip" 2>/dev/null | head -n 200 > "$TXROOT/done-files"
    git -C "$task_worktree" -c core.quotePath=false diff --no-renames --diff-filter=A --name-only "origin/$BASE...$tip" 2>/dev/null > "$TXROOT/done-added"
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      normalize_paths "$f" > "$TXROOT/done-one" 2>/dev/null || continue
      ! overlaps "$TXROOT/done-one" "$TXROOT/done-paths" || continue
      if grep -qxF -- "$f" "$TXROOT/done-added"; then
        { [ -s "$TXROOT/done-additive" ] && overlaps "$TXROOT/done-one" "$TXROOT/done-additive"; } && continue
        [ "$(git -C "$task_worktree" cat-file -s "$tip:$f" 2>/dev/null)" != 0 ] || continue
      fi
      outside="$outside $f"
    done < "$TXROOT/done-files"
    [ -z "$outside" ] || DONE_HINT="SCOPE? Files outside the Paths of $ID:$(printf '%s\n' $outside | head -n 8 | tr '\n' ' ')· the merge gate sends them to the human: revert them (git checkout origin/$BASE -- FILE), or a human amends the Paths (uak plan FILE --amend)."
  fi
  if [ "$STATE" = REVIEW ] && [ -d "$task_worktree" ] && [ -f "$UAK_BIN/map" ]; then
    local cfiles ctasks
    cfiles=$(git -C "$task_worktree" diff --name-only "$(field "$RECORD" Task-Base)" "$tip" 2>/dev/null | head -n 30)
    ctasks=$( [ -z "$cfiles" ] || (cd "$task_worktree" && bash "$UAK_BIN/map" impact --tasks --backlog "$BACKLOG" $cfiles 2>/dev/null) | grep -v "^$ID\$" |
      while IFS= read -r t; do [ -f "$TX/claims/$t.md" ] && printf '%s ' "$t"; done)
    if [ -n "$ctasks" ] && ! awk -F' [|] ' -v me="$AGENT" -v id="$ID" '$3 == me && $5 == "contract" && ($6 == id || index($4, "impact:" id)) {f = 1} END {exit !f}' "$TX/$MSG_LOG" 2>/dev/null; then
      DONE_HINT="${DONE_HINT}${DONE_HINT:+
}CONTRACT? Your diff changes files that live tasks import (${ctasks% }) and you sent them no contract. If the shape changed: bash .uak/bin/uak msg impact:$ID --kind contract --task $ID \"what changed · what to do\""
    fi
  fi
  # Upstream drift at the moment of shipping: the base changed what this branch edits or imports since it last
  # synced (the merge gate would find it later, after a review). Why: STORM, arXiv 2605.20563.
  if [ "$STATE" = REVIEW ] && [ -d "$task_worktree" ] && [ -f "$UAK_BIN/map" ]; then
    local drift
    drift=$(cd "$task_worktree" && git fetch -q origin "$BASE" 2>/dev/null && bash "$UAK_BIN/map" drift --ref "origin/$BASE" 2>/dev/null | head -n 4)
    [ -z "$drift" ] || DONE_HINT="${DONE_HINT}${DONE_HINT:+
}$drift"
  fi
  if [ "$STATE" = INTEGRATED ]; then
    put "$RECORD" Next "Integrated in $BASE: $merged; claim next P0"
    put "$RECORD" Lease-Until 0; put "$RECORD" Updated "$NOW"
    update_summary_field Next "Integrated in $BASE: $merged; claim next P0"
    rm "$CLAIM"
  else refresh_lease; fi
  event "done; PR $PR_URL; evidence: $EVIDENCE; reviewer: ${REVIEWER:--}"
  if [ "$STATE" = INTEGRATED ]; then
    msg_notify_related "$ID" integrated "$ID integrated in $BASE ($merged). If you depend on it: git fetch origin && git merge --no-edit origin/$BASE"
  else
    # One review message: --to picks the reviewer, --note says what changed. Why (MLB hackathon): a re-review
    # was 3 messages (rotation + "re-review X" to the task + "ready" to the rejecter) 9 times.
    local why_r="your turn by rotation" note_r=; [ -z "$REVIEW_NOTE" ] || note_r=" · $REVIEW_NOTE"
    if [ -n "$DONE_TO" ]; then
      [ "$DONE_TO" != "$AGENT" ] || UAK_CODE=own-review conflict "--to: the reviewer is never the author."
      # Someone who can review: not retired, not a human, seen on claims. Why (audit, Oct 2026): --to took any
      # name, and the offer waited 15 min for the re-offer.
      [ ! -f "$TX/meta/retired/$DONE_TO.md" ] || conflict "--to: $DONE_TO is retired. Leave out --to (rotation), or name an active agent."
      if msg_seen_all | awk -v n="$DONE_TO" '$1 == "H" && tolower($2) == tolower(n) { f = 1 } END { exit !f }'; then
        conflict "--to: $DONE_TO is a human; reviews go to agents. Leave out --to, or name an agent."
      fi
      [ "$(msg_seen "$DONE_TO")" -gt 0 ] || registered_reviewer "$DONE_TO" || conflict "--to: $DONE_TO has never been seen on claims (a typo?). Leave out --to for the rotation."
      reviewer=$DONE_TO; why_r="asked by $AGENT"
    else
      reviewer=$(msg_pick_reviewer "$AGENT" "$ID")
      [ -z "$reviewer" ] || [ "$reviewer" != "$(msg_last_rejecter "$AGENT" "$ID")" ] || why_r="you rejected the previous SHA"
    fi
    if [ -n "$reviewer" ]; then
      msg_append "agent:$reviewer" review "$ID" "$ID ready for review ($why_r): $PR_URL (SHA $tip)$note_r. /uak-review $ID; if you can't, reply and any free agent takes it (uak next shows it)."
    else
      msg_append all review "$ID" "$ID ready for review: $PR_URL (SHA $tip)$note_r. First free agent: /uak-review $ID"
    fi
  fi
}
# Before the transaction: the PR URL names this repository, and the lines the task adds pass design-lint.
done_args_check() {
  # Both flags in one error, with the whole command. Why (Hacktoberfest): `done` failed 3 times in a row, first
  # on --pr, then on --evidence; neither wt pr nor the hint named them.
  done_usage="Usage: bash .uak/bin/uak done ${ID:-ID} --pr URL --evidence \"<Verify command> exit 0; <criteria checked>\" (the PR URL: bash .uak/bin/wt pr)"
  case "$PR_URL" in https://*/*) [ -n "$EVIDENCE" ] || die "done needs --evidence. $done_usage";;
    *) die "done needs --pr HTTPS URL$([ -n "$EVIDENCE" ] || printf ' and --evidence'). $done_usage";; esac
  # A GitHub PR URL must name this repository. Why (MLB hackathon): two tasks shipped with a PR link to another of
  # the human's repositories; reviewers opened the wrong compare page.
  pr_remote=$(git -C "$ROOT" config --get "remote.$REMOTE.url" 2>/dev/null || true)
  case "$pr_remote:$PR_URL" in
    *github.com*:https://github.com/*)
      pr_repo=$(printf '%s' "$pr_remote" | sed 's@^git\@github.com:@@;s@^https://github.com/@@;s@^ssh://git\@github.com/@@;s@\.git$@@' | tr 'A-Z' 'a-z')
      pr_url_repo=$(printf '%s' "${PR_URL#https://github.com/}" | cut -d/ -f1-2 | tr 'A-Z' 'a-z')
      [ "$pr_repo" = "$pr_url_repo" ] || die "--pr names github.com/$pr_url_repo, but this repository is github.com/$pr_repo. The right link: bash .uak/bin/wt pr";;
  esac
  if [ -n "$REVIEWER" ]; then
    case "$REVIEWER" in *[!A-Za-z0-9_.-]*) die "Reviewer must be a valid identity.";; esac
  fi
  # Screens use the design system: the lines this task adds pass design-lint before anyone reviews them.
  # Why (Chilangatón): 10 views shipped their own colors and components, and the first UI was redone 3 hours in.
  if [ -z "$MERGE_COMMIT" ] && [ -f "$UAK_BIN/design-lint" ]; then
    dl_out=$(cd "$ROOT" && bash "$UAK_BIN/design-lint" --changed "$BASE" 2>&1); dl_rc=$?
    if [ "$dl_rc" -eq 1 ]; then
      printf '%s\n' "$dl_out" | head -n 12 >&2
      die "done: the lines this task adds break the design system (above). Use the tokens and the UI kit (skill product-ui), or mark a deliberate line with \"design-lint: ok\" and the reason."
    fi
  fi
}
