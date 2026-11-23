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
  # 1280.png / 390.png, or exactly one <screen>-1280.png / <screen>-390.png. Why (DevDay hackathon, 2026-11-08): the critic
  # approved landing-1280.png and voz-1280.png and done refused twice for the exact name; two candidates stay ambiguous.
  for f in 1280 390; do
    [ ! -s "$d/$f.png" ] || continue
    cand=; ncand=0
    for c in "$d"/*-"$f".png; do [ -s "$c" ] || continue; cand="$cand ${c##*/}"; ncand=$((ncand + 1)); done
    [ "$ncand" -eq 1 ] && continue
    if [ "$ncand" -gt 1 ]; then
      UAK_CODE=ui-shots-missing conflict "$ID has several $f shots in .uak-shots/$ID/:$cand and no $f.png. Which is the main screen? Save it as $f.png (copy it) and run done again."
    fi
    missing="$missing $f.png"
  done
  [ -s "$d/critic.txt" ] || missing="$missing critic.txt"
  [ -z "$missing" ] || UAK_CODE=ui-shots-missing conflict "$ID writes UI ($ui): it ships with what was seen. Missing in .uak-shots/$ID/:$missing. Capture the screens it changed at 1280x720 and 390x844 there (skill webapp-testing), then run the design-critic subagent on them: it writes critic.txt. design-critic not in your Agent tool list? Give any subagent the prompt file .claude/agents/design-critic.md, writing the same critic.txt (VERDICT: SHIP|FIX <sha7> on line 1). No visible change? done $ID ... --no-ui \"why\"."
  grep -q '^VERDICT: SHIP' "$d/critic.txt" ||
    UAK_CODE=critic-fix conflict "The design critic said FIX for $ID ($(grep -m 1 '^VERDICT' "$d/critic.txt" 2>/dev/null)). Fix its P1s (.uak-shots/$ID/critic.txt), capture again and rerun it."
  grep -q "$short" "$d/critic.txt" || critic_covers_tip "$1" "$2" "$d/critic.txt" ||
    UAK_CODE=critic-stale conflict "critic.txt in .uak-shots/$ID/ is about another commit; this one is $short. Capture again and rerun design-critic on it. design-critic not in your Agent tool list? Give any subagent the prompt file .claude/agents/design-critic.md, writing the same critic.txt (VERDICT: SHIP|FIX <sha7> on line 1)."
}
# A critique of commit A holds at commit B when A..B touches no UI path (the paths that make done ask for shots).
# Why (private sprint, v6.4.0): "critic.txt is about another commit" x3 in one night after docs and test commits.
# $1 tip, $2 worktree, $3 critic.txt; uses $TXROOT/ui-paths from ui_gate.
critic_covers_tip() {
  local tok full files
  for tok in $(sed -n 's/^VERDICT: [A-Z]* *\([0-9a-f][0-9a-f]*\).*/\1/p' "$3" | head -n 1); do
    [ "${#tok}" -ge 7 ] || continue
    full=$(git -C "$2" rev-parse -q --verify "$tok^{commit}" 2>/dev/null) || continue
    git -C "$2" merge-base --is-ancestor "$full" "$1" 2>/dev/null || continue
    files=$(git -C "$2" diff --name-only "$full" "$1" 2>/dev/null) || continue
    [ -n "$files" ] || return 0
    normalize_paths "$files" > "$TXROOT/ui-changed" 2>/dev/null || continue
    overlaps "$TXROOT/ui-changed" "$TXROOT/ui-paths" || return 0
  done
  return 1
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
# the task is already INTEGRATED. Work that reached main outside the gate (squash, a PR merged after more commits, base
# merges in the branch, equivalent content, a task never claimed) is recorded with Integrated-Outside: yes when its own
# diff is on main (integrated_outside_check); the normal proof is tried first and `uak merge` is untouched.
# Why (deus-ex-machina, 2026-11-09): 11 integrate refusals and 6 of 23 integrated while the product had shipped.
integrate_normal() { # TIP: the approval and the proof of the reviewed content; INT_WHY says what failed
  INT_WHY=
  if ! approval_check "$1" "$PR_URL"; then
    [ -n "$HUMAN" ] && [ "$AGENT" = "$HUMAN" ] || {
      INT_WHY="$RM_REASON. Approve the merged SHA first: uak review $ID --sha ${1:-SHA} --verdict approve. A human merged it? That human records it: UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate $ID"; return 1; }
    APPROVED_BY="human:$HUMAN"
    # A human merge over a reject that still covers this code is a decision: it says why, it is logged, and the
    # rejecter hears it. Why (Hacktoberfest): a task rejected for files outside its Paths was merged on GitHub a
    # minute later and recorded as human-approved; the reject stayed on record and nobody was told.
    if rm_standing_reject; then
      [ -n "$WHY_TEXT" ] || conflict "$RM_REJECTER rejected this code of $ID. A human who merged it anyway records why: UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate $ID --reason \"why the reject does not apply\""
      [ -f "$TX/DECISIONS.md" ] || printf "# DECISIONS\n" > "$TX/DECISIONS.md"
      printf '%s\n' "- $NOW | $ID | merged by $HUMAN over the reject of $RM_REJECTER | Why: $(one_line "$WHY_TEXT")" >> "$TX/DECISIONS.md"
      msg_append "agent:$RM_REJECTER,task:$ID" info "$ID" "$ID was merged by $HUMAN over your reject at ${1%"${1#???????}"}: $(one_line "$WHY_TEXT")"
    fi
  fi
  if [ -n "$MERGE_COMMIT" ]; then
    merged=$(git -C "$TX" rev-parse --verify "$MERGE_COMMIT^{commit}" 2>/dev/null) || conflict "COMMIT not in the remote history of $BASE."
  elif [ "$RM_REVIEW_MODE" = gh ] && [ -n "$RM_GH_MERGE" ]; then merged=$RM_GH_MERGE
  else merged=$(git -C "$TX" rev-parse refs/uak/base); fi
  integrated_check "$1" "$merged" || { INT_WHY="$RM_REASON (squash merge: pass --integrated COMMIT)"; return 1; }
}
# The commit on the base that brought this task's tip in, for the Merge-Commit field. Sets MERGE_REC (a full SHA, or
# "unknown") and MERGE_WHY. Ancestry: the earliest first-parent commit of the base that contains the tip (found by
# bisection: containment only grows along the chain); it is the task's when it is the tip itself or a merge with the tip as
# a parent, else the first commit from there on whose subject names the task (its ID or its PR number): another task's
# merge that carried this tip along does not count. Not an ancestor (squash, rebase): the first commit since the fork whose
# tree is the tip's, else the first single-parent commit whose subject names the task. Never the base's tip by default.
# Why (review of UAK-117, 2026-11-21): UAK-030 and UAK-013 recorded another task's merge, so metrics stopped trusting it.
# Does the subject on stdin name this task (its ID, as a whole word) or its PR number (#N)?
MERGE_NAMES_AWK='
  function names(l, id, pr,   t, i, k, a, b, s) {
    t = tolower(l); i = tolower(id); k = index(t, i); s = 0
    while (k > 0) { a = substr(t, k + length(i), 1); b = k > 1 ? substr(t, k - 1, 1) : " "
      if (a !~ /[0-9a-z-]/ && b !~ /[0-9a-z-]/) s = 1
      t = substr(t, k + 1); k = index(t, i) }
    if (pr != "" && (l ~ ("#" pr "[^0-9]") || l ~ ("#" pr "$"))) s = 1
    return s }'
merge_names_task() { # ID PR_NUMBER
  awk -v id="$1" -v pr="$2" "$MERGE_NAMES_AWK"'
    { if (names($0, id, pr)) f = 1 }
    END { exit !f }'
}
find_merge_commit() { # TIP
  local tip=$1 base=refs/uak/base chain lo hi mid n c p pr ttree sub
  MERGE_REC=unknown MERGE_WHY=
  pr=$(printf '%s' "$PR_URL" | sed -n 's#.*/pull/\([0-9][0-9]*\).*#\1#p')
  git -C "$TX" cat-file -e "$tip^{commit}" 2>/dev/null || { MERGE_WHY="the task tip is not in the repository"; return 0; }
  if git -C "$TX" merge-base --is-ancestor "$tip" "$base"; then
    chain=$TXROOT/merge-chain
    git -C "$TX" log --first-parent --format='%H %s' "$base" > "$chain" 2>/dev/null
    n=$(wc -l < "$chain" | tr -d ' ')
    # Line 1 is the base's tip, line n the oldest. The largest line whose commit still contains the tip is the earliest one.
    lo=1 hi=$n
    git -C "$TX" merge-base --is-ancestor "$tip" "$(sed -n 1p "$chain" | cut -d' ' -f1)" || { MERGE_WHY="the tip is not in the first-parent history of $BASE"; return 0; }
    while [ "$lo" -lt "$hi" ]; do
      mid=$(( (lo + hi + 1) / 2 ))
      if git -C "$TX" merge-base --is-ancestor "$tip" "$(sed -n "${mid}p" "$chain" | cut -d' ' -f1)"; then lo=$mid; else hi=$((mid - 1)); fi
    done
    c=$(sed -n "${lo}p" "$chain" | cut -d' ' -f1)
    if [ "$c" = "$tip" ]; then MERGE_REC=$c; return 0; fi
    for p in $(git -C "$TX" rev-list --parents -n 1 "$c" | cut -d' ' -f3-); do
      [ "$p" != "$tip" ] || { MERGE_REC=$c; return 0; }
    done
    while [ "$lo" -ge 1 ]; do
      if sed -n "${lo}p" "$chain" | cut -d' ' -f2- | merge_names_task "$ID" "$pr"; then MERGE_REC=$(sed -n "${lo}p" "$chain" | cut -d' ' -f1); return 0; fi
      lo=$((lo - 1))
    done
    MERGE_WHY="no merge of $ID on $BASE: the first commit with this tip is another task's merge and none names $ID"; return 0
  fi
  # Not an ancestor: a squash or a rebase. One git log from the base back to the fork point (--not tip), oldest first; awk
  # compares the trees and the subjects in that one pass (a process per commit made 2000 commits cost 1995 calls, 45 s).
  # The first single-parent commit with the tip's own tree, else the first non-root commit (a merge too) that names the task.
  # No cap: the walk is bounded by BASE --not TIP, and a window of the newest commits would pick the wrong "first" one.
  local res bytree byname seen
  ttree=$(git -C "$TX" rev-parse "$tip^{tree}" 2>/dev/null)
  res=$(git -C "$TX" log --first-parent --reverse --format='%H %T %P%x09%s' "$base" --not "$tip" 2>/dev/null | awk -v tt="$ttree" -v id="$ID" -v pr="$pr" "$MERGE_NAMES_AWK"'
    { n = split(substr($0, 1, index($0, "\t") - 1), a, " "); if (n < 3) next
      if (t == "" && n == 3 && a[2] == tt) t = a[1]
      if (m == "" && names(substr($0, index($0, "\t") + 1), id, pr)) m = a[1] }
    END { print t "," m "," NR }')
  IFS=, read -r bytree byname seen <<EOF_MERGE
$res
EOF_MERGE
  if [ -n "$bytree" ]; then MERGE_REC=$bytree; return 0; fi
  if [ -n "$byname" ]; then MERGE_REC=$byname; return 0; fi
  MERGE_WHY="the tip is not in the history of $BASE (squash or rebase) and no commit has its tree or names $ID"
  return 0
}
# A task nobody claimed (or whose claim never reached REVIEW) gets its record here, from the backlog and the branch
# feat/<id> by the kit's own naming; the claim, if any, is released below with the rest.
integrate_new_record() {
  local pri paths
  load_task; pri=$PRIORITY; paths=$PATHS
  WL="worklog/WL-$NOW-$AGENT-$ID-$(basename "$TXROOT").md"
  BRANCH=feat/$(printf '%s' "$ID" | tr '[:upper:]' '[:lower:]')
  {
    printf '# %s\n' "$ID"
    printf '%s\n' "ID: $ID" "State: AVAILABLE" "Owner: $AGENT" "Branch: $BRANCH" "Worktree: -" "Worklog: $WL" "Priority: $pri" \
      "Paths: $(one_line "$paths")" "Depends: $(one_line "$DEPENDS")" "Verify: $(one_line "$VERIFY")" "Lease-Until: 0" "Updated: $NOW" \
      "Next: recorded outside the gate" "PR: -" "Evidence: -"
  } > "$RECORD"
  DONE_TEXT="Recorded by integrate; the work reached $BASE outside the gate"; DECISION_TEXT="Integrated-Outside"
  WHY_TEXT="The task's own diff is on $BASE"; FAILS_TEXT="-"; COMMANDS_TEXT="-"; NEXT_TEXT="Integrated"
  set_summary
}
# Commits after the approved SHA that are ALREADY on the base: unreviewed code in main. Named (say + the event), never refused:
# it is there already. Sets INT_UNREVIEWED.
integrate_name_unreviewed() { # APPROVED_SHA TIP
  local sha=$1 tip=$2 n=0 line sub
  INT_UNREVIEWED=
  git -C "$TX" merge-base --is-ancestor "$sha" "$tip" 2>/dev/null || return 0
  while IFS=' ' read -r line sub; do
    git -C "$TX" merge-base --is-ancestor "$line" refs/uak/base || continue
    n=$((n + 1)); INT_UNREVIEWED="$INT_UNREVIEWED${INT_UNREVIEWED:+; }$line $sub"
  done < <(git -C "$TX" log --no-merges --format='%h %s' "$sha..$tip")
  if [ "$n" -gt 0 ]; then
    INT_UNREVIEWED="$n commit$([ "$n" -eq 1 ] || printf 's') after the approved SHA $([ "$n" -eq 1 ] && printf 'is' || printf 'are') on $BASE without a review: $INT_UNREVIEWED"
    say "NOTE integrate $ID: $INT_UNREVIEWED"
  fi
}
# The approved SHA is already on the base and the branch has commits after it (a reviewer's nit, a review note): the
# approval covers the SHA, so that is what is recorded, and the later commits are named. Only a valid approval of THAT
# SHA counts (the full approval_check, claims mode), the SHA must be on the task branch and be task work. UAK-092.
# Why (UpiixSol, Nov 2026): "UPS-031 is in main (PR #50) but stays AVAILABLE: integrate blocked by an unmerged review commit".
integrate_approved_ancestor() { # TIP; sets INT_SHA, RM_PROOF, APPROVED_BY; fails (and records nothing) otherwise
  local tip=$1 sha tb n=0 line
  sha=$(field "$TX/reviews/$ID.md" SHA); INT_SHA=
  case "$sha" in ''|*[!0-9a-f]*) return 1;; esac
  [ "$sha" != "$tip" ] && git -C "$TX" cat-file -e "$sha^{commit}" 2>/dev/null || return 1
  git -C "$TX" merge-base --is-ancestor "$sha" "$tip" && git -C "$TX" merge-base --is-ancestor "$sha" refs/uak/base || return 1
  tb=$(field "$RECORD" Task-Base); case "$tb" in ''|-|*[!0-9a-f]*) return 1;; esac
  [ "$sha" != "$tb" ] && ! git -C "$TX" diff --quiet "$tb" "$sha" || return 1
  approval_check "$sha" "$PR_URL" && [ "$RM_REVIEW_MODE" = claims ] || return 1
  INT_SHA=$sha; RM_PROOF="approved-ancestor:$sha"
  while IFS= read -r line; do n=$((n + 1)); [ "$n" -gt 1 ] || INT_FIRST=$line; done < <(git -C "$TX" log --format='%h %s' "$tip" --not "$sha" refs/uak/base)
  [ "$n" -eq 0 ] || say "NOTE integrate $ID: $n commit$([ "$n" -eq 1 ] || printf 's') after the approved SHA $([ "$n" -eq 1 ] && printf 'is' || printf 'are') not on $BASE: $INT_FIRST$([ "$n" -eq 1 ] || printf ' (+%s more)' $((n - 1)))"
  integrate_name_unreviewed "$sha" "$tip"
  return 0
}
# A human, not an agent that set UAK_HUMAN to its own name: the human acts under their own identity (UAK_AGENT empty,
# so AGENT is HUMAN) and that name is no identity that ever worked on claims as an agent (coord_mark_human gives a
# human `Role: human`). Why (review of UAK-114): UAK_AGENT=agent-1 UAK_HUMAN=agent-1 passed the plain check.
integrate_human_only() {
  [ -n "$HUMAN" ] && [ "$AGENT" = "$HUMAN" ] || return 1
  case "$HUMAN" in *[!A-Za-z0-9_.-]*) return 1;; esac
  [ ! -f "$TX/meta/agents/$HUMAN.md" ] || [ "$(coord_read "$TX/meta/agents/$HUMAN.md" Role)" = human ] || return 1
  [ -z "${UAK_AGENT:-}" ]
}
integrate_mutate() {
  local st= outside=no approval=none owner unreviewed=no rsha mrec
  # Why (UpiixSol): a human merged on GitHub while the owner agent was offline; the task sat in REVIEW and
  # blocked its dependents for hours. The proof is verifiable, so any identity may record it.
  [ ! -f "$RECORD" ] || st=$(field "$RECORD" State)
  if [ "$st" = INTEGRATED ]; then
    say "OK integrate $ID | already INTEGRATED ($(field "$RECORD" Merge-Commit | cut -c 1-7)); nothing to do"; MUTATE_NOOP=yes; return 0
  fi
  case "$st" in
    REVIEW) ;;
    CLAIMED|BLOCKED)
      owner=$(field "$RECORD" Owner)
      [ "$owner" = "$AGENT" ] || { [ -n "$HUMAN" ] && [ "$AGENT" = "$HUMAN" ]; } ||
        conflict "$ID is $st, held by $owner: only its owner or a human records work that reached $BASE outside the gate.";;
    ''|AVAILABLE)
      awk -v id="$ID" '/^## / && $2==id {f=1} END {exit !f}' "$BACKLOG" || conflict "$ID is not a task (uak status lists them)."
      integrate_new_record;;
    # A task cancelled before its PR was merged on the forge: its merge is on main, its dependents wait for a state that
    # never comes. A human records it, with the reason (UAK-092); an agent never does.
    CANCELLED)
      [ -n "$HUMAN" ] && [ "$AGENT" = "$HUMAN" ] || conflict "$ID is CANCELLED, not REVIEW; a human records its merge on $BASE: UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate $ID --reason TEXT"
      [ -n "$WHY_TEXT" ] || conflict "$ID is CANCELLED: say why it is recorded anyway: UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate $ID --reason TEXT"
      [ -f "$TX/DECISIONS.md" ] || printf "# DECISIONS\n" > "$TX/DECISIONS.md"
      printf '%s\n' "- $NOW | $ID | cancelled task recorded INTEGRATED by $HUMAN | Why: $(one_line "$WHY_TEXT")" >> "$TX/DECISIONS.md";;
    *) conflict "$ID is $st, not REVIEW; integrate records the merged work of a task under review, claimed or not yet claimed.";;
  esac
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
  if [ "$st" = REVIEW ] && integrate_normal "$tip"; then :
  elif [ "$st" = REVIEW ] && ! integrated_outside_check "$tip" && integrate_approved_ancestor "$tip"; then
    tip=$INT_SHA; merged=$(git -C "$TX" rev-parse refs/uak/base)
    # Later commits of the branch that are already ON the base are code in main nobody reviewed (UAK-092 names them).
    [ -z "${INT_UNREVIEWED:-}" ] || unreviewed=yes
  else
    integrated_outside_check "$tip" || conflict "${INT_WHY:+$INT_WHY. }${INT_WHY:+Not on $BASE either: }$RM_REASON"
    outside=yes
    if [ -f "$TX/reviews/$ID.md" ] && [ "$(field "$TX/reviews/$ID.md" Verdict)" = approve ]; then
      approval="$(field "$TX/reviews/$ID.md" Reviewer)@$(field "$TX/reviews/$ID.md" SHA | cut -c 1-7)"
      integrate_name_unreviewed "$(field "$TX/reviews/$ID.md" SHA)" "$tip"
    fi
    # Valid = the full approval check of the approved SHA (another seen identity, claims mode). Without one the code is on
    # the base unreviewed: sprint records it and says so; marathon needs a human and a reason (UAK-114, audit #7).
    # What landed is what was approved only when the approved SHA is the branch tip (no commit after it) and the content
    # checked on the base is the tip's: a review of an older SHA covers none of the later commits.
    unreviewed=yes
    rsha=$(field "$TX/reviews/$ID.md" SHA 2>/dev/null)
    if [ "$approval" != none ] && [ -n "$rsha" ] && [ "$rsha" = "$tip" ] && approval_check "$rsha" "$PR_URL" && [ "$RM_REVIEW_MODE" = claims ]; then unreviewed=no; fi
    # Unreviewed work under review is a human's to record, as before (v5.x); an approval of any earlier SHA, or a task
    # whose owner records its own claim, or one nobody claimed, needs no human.
    [ "$st" != REVIEW ] || [ "$approval" != none ] || { [ -n "$HUMAN" ] && [ "$AGENT" = "$HUMAN" ]; } || conflict "${INT_WHY:-No approval on claims}"
    # Why (v6.1.0 review of UAK-033): one file whose content equals main by coincidence, with nobody's approval, would
    # be credited as integrated. Two or more matching files, or any approval, are proof enough for an agent.
    [ "$RM_PROOF" != outside:content:1 ] || [ "$approval" != none ] || { [ -n "$HUMAN" ] && [ "$AGENT" = "$HUMAN" ]; } ||
      conflict "only one file matched $BASE and nobody approved it: a human records it (UAK_HUMAN=NAME uak integrate $ID)"
    if [ -n "$MERGE_COMMIT" ]; then
      merged=$(git -C "$TX" rev-parse --verify "$MERGE_COMMIT^{commit}" 2>/dev/null) || conflict "COMMIT not in the remote history of $BASE."
    else merged=$(git -C "$TX" rev-parse refs/uak/base); fi
    APPROVED_BY=
  fi
  if [ "$unreviewed" = yes ]; then
    # The mode is read with the one config reader from PROJECT.md on the remote base (a branch cannot switch it):
    # spaces, CR and bold are trimmed there; the case is folded here.
    uak_cfg_var - Mode sprint < <(git -C "$TX" show "refs/uak/base:.uak/PROJECT.md" 2>/dev/null)
    case "$CFG" in [Mm][Aa][Rr][Aa][Tt][Hh][Oo][Nn])
      integrate_human_only || conflict "marathon mode: the work of $ID is on $BASE with no valid review of its tip; a human records it: UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate $ID --reason TEXT"
      [ -n "$WHY_TEXT" ] || conflict "marathon mode: say why $ID is recorded without a review: UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate $ID --reason TEXT"
      [ -f "$TX/DECISIONS.md" ] || printf "# DECISIONS\n" > "$TX/DECISIONS.md"
      printf '%s\n' "- $NOW | $ID | recorded INTEGRATED without a review by $HUMAN | Why: $(one_line "$WHY_TEXT")" >> "$TX/DECISIONS.md";;
    esac
    say "NOTE integrate $ID: the code reached $BASE without a review (recorded Unreviewed: yes)"
  fi
  STATE=INTEGRATED
  # Merge-Commit: the forge's own answer or the COMMIT given, else the commit that brought this tip in; `unknown` when
  # none is found (never the base's tip by default, UAK-132).
  if [ -n "$MERGE_COMMIT" ] || { [ "$RM_REVIEW_MODE" = gh ] && [ -n "$RM_GH_MERGE" ]; }; then mrec=$merged; MERGE_WHY=
  else find_merge_commit "$tip"; mrec=$MERGE_REC; fi
  put "$RECORD" Integration-Proof "$RM_PROOF"; put "$RECORD" Merge-Commit "$mrec"
  if [ "$outside" = yes ]; then put "$RECORD" Integrated-Outside yes; put "$RECORD" Approval "$approval"; put "$RECORD" Recorded-By "$AGENT"
    [ "$unreviewed" != yes ] || put "$RECORD" Unreviewed yes
  else put "$RECORD" Reviewer "$APPROVED_BY"; [ "$unreviewed" != yes ] || put "$RECORD" Unreviewed yes; fi
  put "$RECORD" Task-Tip "$tip"; put "$RECORD" State INTEGRATED
  put "$RECORD" Next "Integrated in $BASE: $mrec; claim next P0"
  put "$RECORD" Lease-Until 0; put "$RECORD" Updated "$NOW"
  update_summary_field Next "Integrated in $BASE: $mrec (recorded by $AGENT)"
  rm -f "$CLAIM"
  event "integrate; recorded by $AGENT; PR $PR_URL; merged $mrec; proof $RM_PROOF$([ -z "$MERGE_WHY" ] || printf '; Merge-Commit unknown: %s' "$MERGE_WHY")$([ "$outside" != yes ] || printf '; outside the gate, approval %s' "$approval")$([ "$unreviewed" != yes ] || printf '; unreviewed')$([ -z "${INT_UNREVIEWED:-}" ] || printf '; %s' "$INT_UNREVIEWED")"
  msg_notify_related "$ID" integrated "$ID integrated in $BASE ($mrec), recorded by $AGENT. If you depend on it: git fetch origin && git merge --no-edit origin/$BASE"
}
# done --pr BRANCH (harvest 2026-11 x2): a branch name is not a URL; the PR's URL comes from wt pr. Same first words as
# done_args_check. `--pr none` and the branch this worktree is on (the task's own) go on to done_args_check and
# done_no_pr_check, which allow them only where no GitHub PR is reviewed; any other value is refused here, and the
# message names that way out.
done_pr_shape_check() {
  case "$PR_URL" in https://*/*|none|NONE|None) return 0;; esac
  [ "$PR_URL" != "$(git branch --show-current 2>/dev/null || true)" ] || return 0
  die "done needs --pr HTTPS URL$([ -n "$EVIDENCE" ] || printf ' and --evidence'). '$PR_URL' is a branch name, not a URL: push, then get the URL with bash .uak/bin/wt pr (with no GitHub PR, as on a non-GitHub remote or with Review-Mode: claims: --pr none). Usage: bash .uak/bin/uak done ${ID:-ID} --pr URL --evidence \"<Verify command> exit 0; <criteria checked>\""
}
# done: REVIEW with the PR and evidence after the gates (UI shots, test-first), and one reviewer asked; or, with
# --integrated, INTEGRATED after a human merge with a verified approval.
# --pr none or the task's branch: only where no GitHub PR is reviewed (a non-GitHub remote, or Review-Mode: claims).
done_no_pr_check() {
  local mode remote
  [ "$PR_URL" = none ] || [ "$PR_URL" = "$task_branch" ] ||
    die "--pr $PR_URL is neither a PR URL nor this task's branch ($task_branch). With no GitHub PR: --pr none"
  remote=$(git -C "$ROOT" config --get "remote.$REMOTE.url" 2>/dev/null || true)
  case "$remote" in *github.com*) ;; *) return 0;; esac
  # The mode of the base PROJECT.md, never the environment (as at merge): nothing in the shell of whoever runs done can turn a
  # GitHub repository that reviews PRs into one that takes a branch with no PR (UAK-155).
  mode=$(rm_config Review-Mode auto)
  [ "$mode" = claims ] || die "--pr $PR_URL: this repository is on GitHub and Review-Mode is $mode, so the PR is what gets reviewed. Open it (bash .uak/bin/wt pr) and pass its URL, or, to review on claims (another agent identity runs uak review), set Review-Mode: claims in .uak/PROJECT.md on $BASE."
}
done_mutate() {
  require_owner; STATE=REVIEW
  task_branch=$(field "$RECORD" Branch)
  DONE_REF=$PR_URL
  if [ "$DONE_NO_PR" = yes ]; then done_no_pr_check; DONE_REF="branch $task_branch (no PR)"; fi
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
    find_merge_commit "$tip"; [ "$MERGE_REC" = unknown ] || merged=$MERGE_REC
    put "$RECORD" Merge-Commit "$merged"; put "$RECORD" Reviewer "$REVIEWER"
  fi
  [ "$STATE" != REVIEW ] || ui_gate "$tip" "$task_worktree"
  [ "$STATE" != REVIEW ] || test_gate "$tip" "$task_worktree"
  put "$RECORD" Task-Tip "$tip"
  put "$RECORD" State "$STATE"; put "$CLAIM" State "$STATE"
  put "$RECORD" PR "$PR_URL"; put "$CLAIM" PR "$PR_URL"; put "$RECORD" Evidence "$EVIDENCE"
  put "$RECORD" Next "Another agent reviews $DONE_REF; run .uak/bin/smoke"
  put "$CLAIM" Next "Another agent reviews $DONE_REF; run .uak/bin/smoke"
  update_summary_field Done "$EVIDENCE"
  update_summary_field Next "Another agent reviews $DONE_REF; run .uak/bin/smoke"
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
    # Generated: files (UAK-148) of the BASE's PROJECT.md (never the branch's): not out of scope unless a shared resource of
    # the human. The gate checks their content against the command, so there is nothing to revert. One normalized path a line.
    local gp1 gx lp1 gm0 gm1
    git -C "$task_worktree" show "origin/$BASE:.uak/PROJECT.md" 2>/dev/null | uak_generated_list > "$TXROOT/done-gen" 2>/dev/null || : > "$TXROOT/done-gen"
    cut -f1 "$TXROOT/done-gen" | sort | uniq -u > "$TXROOT/done-genpaths"
    git -C "$task_worktree" -c core.quotePath=false diff --no-renames --name-only "origin/$BASE...$tip" 2>/dev/null | head -n 200 > "$TXROOT/done-files"
    git -C "$task_worktree" -c core.quotePath=false diff --no-renames --diff-filter=A --name-only "origin/$BASE...$tip" 2>/dev/null > "$TXROOT/done-added"
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      normalize_paths "$f" > "$TXROOT/done-one" 2>/dev/null || continue
      ! overlaps "$TXROOT/done-one" "$TXROOT/done-paths" || continue
      # The exact path, listed once, a plain file kept with its mode (as the gate releases it).
      if [ -s "$TXROOT/done-genpaths" ] && grep -qxF -- "$f" "$TXROOT/done-genpaths"; then
        lp1="/$(cat "$TXROOT/done-one")/"; gx=yes
        for gp1 in $UAK_SHARED_RES /.github/ /.uak/bin/guard/; do case "$lp1" in (*"$gp1"*) gx=no;; esac; done
        gm1=$(git -C "$task_worktree" ls-tree "$tip" -- "$f" 2>/dev/null | cut -d' ' -f1)
        gm0=$(git -C "$task_worktree" ls-tree "origin/$BASE" -- "$f" 2>/dev/null | cut -d' ' -f1)
        [ "$gm1" = 100644 ] && { [ -z "$gm0" ] || [ "$gm0" = 100644 ]; } || gx=no
        [ "$gx" = no ] || continue
      fi
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
      msg_append "agent:$reviewer" review "$ID" "$ID ready for review ($why_r): $DONE_REF (SHA $tip)$note_r. /uak-review $ID; if you can't, reply and any free agent takes it (uak next shows it)."
    else
      msg_append all review "$ID" "$ID ready for review: $DONE_REF (SHA $tip)$note_r. First free agent: /uak-review $ID"
    fi
  fi
}
# Before the transaction: the PR URL names this repository, and the lines the task adds pass design-lint.
done_args_check() {
  # Both flags in one error, with the whole command. Why (Hacktoberfest): `done` failed 3 times in a row, first
  # on --pr, then on --evidence; neither wt pr nor the hint named them.
  done_usage="Usage: bash .uak/bin/uak done ${ID:-ID} --pr URL --evidence \"<Verify command> exit 0; <criteria checked>\" (the PR URL: bash .uak/bin/wt pr; no GitHub PR, as on a non-GitHub remote or with Review-Mode: claims: --pr none)"
  # --pr none (or the task's branch): no PR to link; done_no_pr_check decides inside the transaction, where Review-Mode
  # is read from PROJECT.md on the remote base. Why (QA round C, Nov 2026): on a local bare remote `wt pr` said "Not a
  # GitHub remote" and done said "needs --pr HTTPS URL (… wt pr)", a dead loop; a tester invented an https URL.
  DONE_NO_PR=
  case "$PR_URL" in https://*/*) ;;
    none|NONE|None) PR_URL=none; DONE_NO_PR=yes;;
    *://*|-*|'') ;;
    *) ! git check-ref-format --branch "$PR_URL" >/dev/null 2>&1 || DONE_NO_PR=yes;;
  esac
  case "$PR_URL:$DONE_NO_PR" in https://*/*:|*:yes) [ -n "$EVIDENCE" ] || die "done needs --evidence. $done_usage";;
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
