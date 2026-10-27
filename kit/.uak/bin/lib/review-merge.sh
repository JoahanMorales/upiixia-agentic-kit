#!/usr/bin/env bash
# Bash 3.2 library: per-SHA review and an atomic merge queue.
# Why: a declared name never proves an independent approval.
RM_REASON= APPROVED_BY= RM_TIP= RM_ELIGIBLE_VIA= RM_PROOF=
RM_COUNTER=0 RM_HELD=no RM_FINISHED=no RM_TOKEN= RM_BUILD= RM_CANDIDATE= RM_BASE_TIP= RM_REVIEWED_TIP=
RM_ACTION= RM_QUEUE_REASON= RM_TREE= RM_REVIEW_MODE= RM_GH_MERGED= RM_GH_MERGE= RM_ADOPTED=no RM_MAIN= RM_GATE_PATH=

rm_config() {
  if typeset -f coord_config >/dev/null 2>&1; then coord_config "$1" "$2";
  elif [ -f "$TX/meta/config.md" ]; then
    v=$(field "$TX/meta/config.md" "$1"); printf '%s\n' "${v:-$2}"
  else printf '%s\n' "$2"; fi
}
registered_reviewer() {
  case "$1" in ''|*[!A-Za-z0-9_.-]*) return 1;; esac
  [ ! -f "$TX/meta/retired/$1.md" ] && [ -f "$TX/roles/reviewers/$1.md" ] &&
    [ "$(field "$TX/roles/reviewers/$1.md" Reviewer)" = "$1" ] &&
    [ -n "$(field "$TX/roles/reviewers/$1.md" Registered-By)" ]
}
review_identity_eligible() {
  local who=${1:-$AGENT} c until state
  RM_ELIGIBLE_VIA=
  if registered_reviewer "$who"; then RM_ELIGIBLE_VIA="role:$who"; return 0; fi
  for c in "$TX"/claims/*.md; do
    [ -f "$c" ] || continue
    [ "$(field "$c" Owner)" = "$who" ] || continue
    until=$(field "$c" Lease-Until); state=$(field "$c" State)
    case "$until" in ''|*[!0-9]*) continue;; esac
    case "$state" in CLAIMED|BLOCKED|REVIEW) ;; *) continue;; esac
    if [ "$NOW" -lt "$until" ]; then RM_ELIGIBLE_VIA="claim:$(field "$c" ID):$until"; return 0; fi
  done
  # An agent whose last task was integrated recently is still a real, working agent.
  # Why (UpiixSol): reviewers lost eligibility the moment their own task merged, and only a human could
  # re-register them, so reviews stalled overnight. Window: 24 h or Review-Lease-Seconds if longer.
  local window updated r
  window=${REVIEW_LEASE:-86400}; case "$window" in ''|*[!0-9]*) window=86400;; esac; [ "$window" -ge 86400 ] || window=86400
  for r in "$TX"/tasks/*.md; do
    [ -f "$r" ] || continue
    [ "$(field "$r" Owner)" = "$who" ] || continue
    [ "$(field "$r" State)" = INTEGRATED ] || continue
    updated=$(field "$r" Updated); case "$updated" in ''|*[!0-9]*) continue;; esac
    if [ $((NOW - updated)) -le "$window" ]; then RM_ELIGIBLE_VIA="recent:$(field "$r" ID):$updated"; return 0; fi
  done
  return 1
}
register_reviewer_mutate() {
  local who
  [ -n "$HUMAN" ] || conflict "register-reviewer needs UAK_HUMAN (a human registers agents)."
  mkdir -p "$TX/roles/reviewers"
  for who in ${REGISTER_REVIEWER:-$ID}; do
    case "$who" in ''|*[!A-Za-z0-9_.-]*) die "Invalid reviewer identity.";; esac
    # Why (Reap): 5 refusals came from agents registering themselves from their own worktree (.uak-env).
    [ "$who" != "$AGENT" ] && [ "$who" != "$HUMAN" ] ||
      conflict "The registrar cannot grant a role to themselves (you are $AGENT). The human runs it from the main checkout: cd \"\$(git rev-parse --git-common-dir)/..\" && UAK_HUMAN=$HUMAN UAK_AGENT= bash .uak/bin/uak register-reviewer NAME..."
    RECORD="$TX/roles/reviewers/$who.md"
    [ ! -f "$RECORD" ] || [ "$(field "$RECORD" Reviewer)" != "$who" ] || continue
    printf '%s\n' "Reviewer: $who" 'State: REGISTERED' "Registered-By: $HUMAN" "Registered: $NOW" > "$RECORD"
  done
}
resolve_task_tip() {
  local branch worktree
  branch=$(field "$RECORD" Branch); worktree=$(field "$RECORD" Worktree)
  git check-ref-format "refs/heads/$branch" >/dev/null 2>&1 || { RM_REASON='Invalid task branch'; return 1; }
  if git -C "$TX" ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
    git -C "$TX" fetch -q origin "refs/heads/$branch:refs/uak/task" || { RM_REASON='Could not read the remote task branch'; return 1; }
    RM_TIP=$(git -C "$TX" rev-parse refs/uak/task) || return 1
    # A newer local HEAD also invalidates the review; push first to remove ambiguity.
    if [ -d "$worktree" ] && [ "$(git -C "$worktree" symbolic-ref --short HEAD 2>/dev/null)" = "$branch" ]; then
      [ "$(git -C "$worktree" rev-parse HEAD 2>/dev/null)" = "$RM_TIP" ] || {
        RM_REASON='Local and remote HEAD differ; push the branch before review/merge'; return 1;
      }
    fi
  elif [ -d "$worktree" ] && [ "$(git -C "$worktree" symbolic-ref --short HEAD 2>/dev/null)" = "$branch" ]; then
    RM_TIP=$(git -C "$worktree" rev-parse HEAD) || return 1
    git -C "$TX" fetch -q "$worktree" "$RM_TIP" || { RM_REASON='Could not read the task HEAD'; return 1; }
  else
    RM_TIP=$(field "$RECORD" Task-Tip)
    [ -n "$RM_TIP" ] || { RM_REASON='Missing verifiable HEAD or Task-Tip'; return 1; }
    git -C "$TX" cat-file -e "$RM_TIP^{commit}" 2>/dev/null ||
      git -C "$TX" fetch -q origin "$RM_TIP" || { RM_REASON='Task-Tip not available'; return 1; }
  fi
}
# The approval of SHA $1 still holds for $2 when everything after $1 is a clean merge of the base: each
# commit is a 2-parent merge whose other parent is already in the base, and its tree is exactly what git
# computes for that merge (no hand edits, no conflict resolution). Any git (older than 2.38: a stricter 3-way index merge).
# Why (MLB hackathon): "Update branch" or a merge of main after the approval made the SHA stale; agents asked
# for re-reviews of pure merges by message (#42, #66) and integrate refused a merged PR (HACK-031).
# Tree of a clean automatic merge of $1 and $2, or failure. git 2.38+: merge-tree --write-tree. Older git
# (Ubuntu 22.04 ships 2.34): a 3-way read-tree in a temporary index, which resolves file-level merges only;
# anything it cannot resolve fails, so the approval is not carried (a re-review, never a false approval).
rm_clean_merge_tree() {
  local base idx="$TXROOT/carry-index.$$"
  if git -C "$TX" merge-tree -h 2>&1 | grep -q -- --write-tree; then
    git -C "$TX" merge-tree --write-tree "$1" "$2" 2>/dev/null | head -n 1; return "${PIPESTATUS[0]}"
  fi
  base=$(git -C "$TX" merge-base "$1" "$2" 2>/dev/null) || return 1
  [ "$(git -C "$TX" merge-base --all "$1" "$2" | wc -l | tr -d ' ')" -eq 1 ] || return 1
  rm -f "$idx"
  GIT_INDEX_FILE=$idx git -C "$TX" read-tree -i -m --aggressive "$base" "$1" "$2" 2>/dev/null || { rm -f "$idx"; return 1; }
  GIT_INDEX_FILE=$idx git -C "$TX" write-tree 2>/dev/null; local rc=$?; rm -f "$idx"; return "$rc"
}
rm_main_merges_only() {
  local c=$2 p1 p2 t i=0
  [ "$1" != "$2" ] || return 0
  git -C "$TX" merge-base --is-ancestor "$1" "$2" 2>/dev/null || return 1
  git -C "$TX" rev-parse -q --verify refs/uak/base >/dev/null 2>&1 ||
    git -C "$TX" fetch -q origin "refs/heads/$BASE:refs/uak/base" 2>/dev/null || return 1
  while [ "$c" != "$1" ]; do
    i=$((i + 1)); [ "$i" -le 30 ] || return 1
    p1=$(git -C "$TX" rev-parse -q --verify "$c^1" 2>/dev/null) || return 1
    p2=$(git -C "$TX" rev-parse -q --verify "$c^2" 2>/dev/null) || return 1
    ! git -C "$TX" rev-parse -q --verify "$c^3" >/dev/null 2>&1 || return 1
    # The branch side is the parent that contains the approved SHA (a merge made from main has the parents
    # swapped; so does the PR's own merge commit once the branch is fast-forwarded to main after a forge merge).
    # Why (MLB hackathon): 8 integrate refusals and 2 black box notes after "merge on GitHub, then pull main".
    if ! git -C "$TX" merge-base --is-ancestor "$1" "$p1" 2>/dev/null; then t=$p1; p1=$p2; p2=$t; fi
    git -C "$TX" merge-base --is-ancestor "$1" "$p1" 2>/dev/null || return 1
    git -C "$TX" merge-base --is-ancestor "$p2" refs/uak/base || return 1
    t=$(rm_clean_merge_tree "$p1" "$p2") || return 1
    [ -n "$t" ] && [ "$t" = "$(git -C "$TX" rev-parse "$c^{tree}")" ] || return 1
    c=$p1
  done
}
review_mutate() {
  RECORD=$(task_file)
  [ -f "$RECORD" ] || conflict "$ID has no claimed task."
  # --stop: give the review back (could not finish). Why (MLB): a reviewer that could not read the diff had to
  # say "my lock expires in 20 min" by message.
  if [ "$REVIEW_STOP" = yes ]; then
    [ -f "$TX/reviews/$ID.reviewing" ] && [ "$(field "$TX/reviews/$ID.reviewing" Reviewer)" = "$AGENT" ] ||
      { say "OK review --stop $ID | you hold no review lock on it"; return 0; }
    rm -f "$TX/reviews/$ID.reviewing"; return 0
  fi
  [ "$AGENT" != "$(field "$RECORD" Owner)" ] || conflict "The owner cannot approve their own task."
  review_identity_eligible "$AGENT" || conflict "The reviewer needs an active own claim or a registered role."
  resolve_task_tip || conflict "$RM_REASON"
  # --start: "I am reviewing this SHA" for a short lease, so a second agent does not review it in parallel.
  # Why (Reap buildathon): 2-3 agents reviewed the same SHA at the same time; each review is a full diff,
  # a fresh Verify and a smoke run, so the duplicates cost the most tokens of the whole event.
  if [ "$REVIEW_START" = yes ]; then
    [ -n "$REVIEW_SHA" ] || REVIEW_SHA=$RM_TIP
    [ "$REVIEW_SHA" = "$RM_TIP" ] || conflict "The task's current HEAD is ${RM_TIP%"${RM_TIP#???????}"}; review that SHA."
    if [ -f "$TX/reviews/$ID.md" ] && [ "$(field "$TX/reviews/$ID.md" SHA)" = "$RM_TIP" ] &&
       [ "$(field "$TX/reviews/$ID.md" Verdict)" = approve ]; then
      say "SKIP review $ID | already approved by $(field "$TX/reviews/$ID.md" Reviewer) on this SHA; it needs a merge, not a reviewer."
      return 0
    fi
    local lock="$TX/reviews/$ID.reviewing" until who
    if [ -f "$lock" ]; then
      who=$(field "$lock" Reviewer); until=$(field "$lock" Until)
      case "$until" in ''|*[!0-9]*) until=0;; esac
      if [ "$who" != "$AGENT" ] && [ "$(field "$lock" SHA)" = "$RM_TIP" ] && [ "$NOW" -lt "$until" ]; then
        conflict "$who is already reviewing $ID at this SHA ($(((until - NOW + 59) / 60)) min left). Pick another task or review."
      fi
    fi
    mkdir -p "$TX/reviews"
    printf '%s\n' "Reviewer: $AGENT" "SHA: $RM_TIP" "Started: $NOW" "Until: $((NOW + ${UAK_REVIEW_LOCK_SECONDS:-1200}))" > "$lock"
    REVIEW_STARTED=yes
    return 0
  fi
  # A short SHA of the current HEAD is the HEAD.
  case "$RM_TIP" in "$REVIEW_SHA"*) [ "${#REVIEW_SHA}" -lt 7 ] || REVIEW_SHA=$RM_TIP;; esac
  local carried=
  if [ "$REVIEW_SHA" != "$RM_TIP" ]; then
    local full; full=$(git -C "$TX" rev-parse -q --verify "$REVIEW_SHA^{commit}" 2>/dev/null) || full=
    if [ -n "$full" ] && rm_main_merges_only "$full" "$RM_TIP"; then
      carried=$full
    elif [ -n "$full" ] && git -C "$TX" merge-base --is-ancestor "$full" "$RM_TIP" 2>/dev/null; then
      conflict "HEAD moved: ${RM_TIP%"${RM_TIP#???????}"} has $(git -C "$TX" rev-list --count "$full..$RM_TIP") commit(s) after your ${full%"${full#???????}"} ($(git -C "$TX" diff --name-only "$full" "$RM_TIP" | wc -l | tr -d ' ') files). Review the new commits: git diff ${full%"${full#???????}"} ${RM_TIP%"${RM_TIP#???????}"}, then --sha $RM_TIP."
    else
      conflict "The review must match the task's current HEAD (${RM_TIP%"${RM_TIP#???????}"}); --sha $REVIEW_SHA is not in its history."
    fi
  fi
  case "$REVIEW_VERDICT" in approve|reject) ;; *) die "--verdict must be approve or reject.";; esac
  rm -f "$TX/reviews/$ID.reviewing"
  # An approval of a SHA that already has one is duplicate work (Reap: HACK-005 got 7 approvals, 3 on one SHA).
  if [ -f "$TX/reviews/$ID.md" ] && [ "$(field "$TX/reviews/$ID.md" SHA)" = "$RM_TIP" ] &&
     [ "$(field "$TX/reviews/$ID.md" Verdict)" = approve ] && [ "$REVIEW_VERDICT" = approve ]; then
    say "OK review $ID | already approved by $(field "$TX/reviews/$ID.md" Reviewer) on this SHA; nothing recorded. Next: the owner runs uak merge $ID"
    return 0
  fi
  mkdir -p "$TX/reviews"
  printf '%s\n' "ID: $ID" "SHA: $RM_TIP" "Reviewer: $AGENT" "Owner: $(field "$RECORD" Owner)" \
    "Verdict: $REVIEW_VERDICT" "Reviewed: $NOW" "Eligible-Via: $RM_ELIGIBLE_VIA" 'Command: uak review' > "$TX/reviews/$ID.md"
  [ -z "$carried" ] || printf '%s\n' "Carried-From: $carried (later commits are clean merges of $BASE)" >> "$TX/reviews/$ID.md"
  put "$RECORD" Task-Tip "$RM_TIP"
  WL=$(field "$RECORD" Worklog); STATE=$(field "$RECORD" State)
  event "review; $REVIEW_VERDICT; SHA $RM_TIP; reviewer $AGENT"
  # --note goes in the same message: one message per verdict, not a verdict plus a separate detail message.
  local note=; [ -z "$REVIEW_NOTE" ] || note=" · $REVIEW_NOTE"
  if [ "$REVIEW_VERDICT" = approve ]; then
    msg_append "task:$ID" approve "$ID" "Approved SHA ${RM_TIP%"${RM_TIP#???????}"} by $AGENT$note. Next: bash .uak/bin/uak merge $ID (the owner; after $(( $(rm_config Merge-Adopt-Seconds 1200) / 60 )) min any agent can)"
  else
    msg_append "task:$ID" reject "$ID" "Rejected SHA ${RM_TIP%"${RM_TIP#???????}"} by $AGENT$note. Fix, push, and rerun /uak-ship"
    # --learn: the reason becomes a lesson on the task's paths, so the next task there does not repeat it.
    if [ "$REVIEW_LEARN" = yes ] && [ -n "$REVIEW_NOTE" ]; then MEM_TEXT=$REVIEW_NOTE; MEM_PATHS=; learn_mutate
    else REVIEW_HINT="If this mistake can happen in other tasks too, keep it for them: bash .uak/bin/uak learn \"what bites · where · what to do\" --task $ID"; fi
  fi
}
approval_check() {
  local tip=$1 pr=${2:-} mode review who author meta gh_tip gh_author gh_base gh_branch gh_repo gh_state gh_merged gh_merge remote_repo
  APPROVED_BY= RM_REASON=
  RM_GH_MERGED= RM_GH_MERGE=
  mode=${UAK_REVIEW_MODE:-$(rm_config Review-Mode auto)}
  if [ "$mode" = auto ]; then
    case "$pr" in https://github.com/*/pull/*)
      if command -v gh >/dev/null 2>&1; then mode=gh; else mode=claims; fi;;
      *) mode=claims;;
    esac
  fi
  RM_REVIEW_MODE=$mode
  case "$mode" in
    claims)
      review="$TX/reviews/$ID.md"; author=$(field "$RECORD" Owner)
      [ -f "$review" ] || { RM_REASON='Missing verifiable approval on claims'; return 1; }
      who=$(field "$review" Reviewer)
      case "$who" in ''|*[!A-Za-z0-9_.-]*) RM_REASON='Invalid approval identity'; return 1;; esac
      [ "$(field "$review" Verdict)" = approve ] &&
        { [ "$(field "$review" SHA)" = "$tip" ] || rm_main_merges_only "$(field "$review" SHA)" "$tip"; } &&
        [ "$(field "$review" Owner)" = "$author" ] && [ "$who" != "$author" ] &&
        [ "$(field "$review" Command)" = 'uak review' ] && [ -n "$(field "$review" Eligible-Via)" ] || {
        RM_REASON='Approval missing, rejected, self-made or stale for the current SHA'; return 1;
      }
      APPROVED_BY=$who;;
    gh)
      command -v gh >/dev/null 2>&1 || { RM_REASON='Review-Mode gh needs the gh CLI'; return 1; }
      printf '%s\n' "$pr" | grep -Eq '^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*$' || {
        RM_REASON='gh mode needs an exact github.com PR URL'; return 1;
      }
      gh_repo=$(printf '%s\n' "$pr" | sed 's@^https://github.com/@@;s@/pull/.*@@')
      remote_repo=$(printf '%s\n' "$REMOTE_URL" | sed 's@^git\@github.com:@@;s@^https://github.com/@@;s@\.git$@@')
      [ "$(printf '%s' "$remote_repo" | tr '[:upper:]' '[:lower:]')" = "$(printf '%s' "$gh_repo" | tr '[:upper:]' '[:lower:]')" ] || {
        RM_REASON='The PR does not belong to the configured remote'; return 1;
      }
      RM_GH_ENDPOINT="repos/$gh_repo/pulls/${pr##*/}"
      meta=$(gh api "$RM_GH_ENDPOINT" --template '{{.head.sha}}|{{.user.login}}|{{.base.ref}}|{{.head.ref}}|{{.head.repo.full_name}}|{{.state}}|{{.merged}}|{{.merge_commit_sha}}' 2>/dev/null) || {
        RM_REASON='GitHub API could not verify the PR'; return 1;
      }
      IFS='|' read -r gh_tip gh_author gh_base gh_branch gh_repo gh_state gh_merged gh_merge <<< "$meta"
      RM_GH_MERGED=$gh_merged; RM_GH_MERGE=$gh_merge
      [ "$gh_tip" = "$tip" ] && [ "$gh_base" = "$BASE" ] && [ "$gh_branch" = "$(field "$RECORD" Branch)" ] || {
        RM_REASON='PR SHA/branch/base does not match the task'; return 1;
      }
      gh api "$RM_GH_ENDPOINT/reviews" --paginate --template '{{range .}}{{.user.login}}|{{.state}}|{{.commit_id}}{{"\n"}}{{end}}' > "$TXROOT/gh-reviews" 2>/dev/null || {
        RM_REASON='GitHub API could not verify the reviews'; return 1;
      }
      APPROVED_BY=$(awk -F'|' -v tip="$tip" -v author="$gh_author" '
        $2=="APPROVED" || $2=="CHANGES_REQUESTED" || $2=="DISMISSED" {k=tolower($1); state[k]=$2; sha[k]=$3; name[k]=$1}
        END {
          for(k in state) if(k!=tolower(author) && state[k]=="CHANGES_REQUESTED" && sha[k]==tip) exit;
          for(k in state) if(k!=tolower(author) && state[k]=="APPROVED" && sha[k]==tip) {print name[k]; exit}
        }' "$TXROOT/gh-reviews")
      # GitHub never lets a PR's author approve it: with one human on the repo this waits forever. Say the way out.
      # Why (a solo marathon project, Oct 2026): "it asks for the approval of another GitHub account and I am alone".
      [ -n "$APPROVED_BY" ] || { RM_REASON="GitHub shows no current independent approval on this SHA (GitHub never lets the PR's author, $gh_author, approve it; alone on the repo? set Review-Mode: claims in .uak/PROJECT.md on $BASE: another agent identity reviews with uak review, you still merge)"; return 1; };;
    *) RM_REASON='Invalid Review-Mode'; return 1;;
  esac
  return 0
}
integrated_check() {
  local tip=$1 merged=$2 task_base parent expected actual path entry mode type blob changed=no
  RM_PROOF= RM_REASON=
  task_base=$(field "$RECORD" Task-Base)
  if [ "$RM_REVIEW_MODE" = gh ]; then
    [ "$RM_GH_MERGED" = true ] && [ "$RM_GH_MERGE" = "$merged" ] || {
      RM_REASON='GitHub does not show this COMMIT as a merged PR result'; return 1;
    }
  fi
  [ -n "$task_base" ] && [ "$tip" != "$task_base" ] || { RM_REASON='TIP equals base; nothing implemented'; return 1; }
  git -C "$TX" diff --quiet "$task_base" "$tip" && { RM_REASON='The task has no diff against its base'; return 1; }
  git -C "$TX" merge-base --is-ancestor "$merged" refs/uak/base || { RM_REASON='COMMIT not integrated in the remote base'; return 1; }
  if git -C "$TX" merge-base --is-ancestor "$tip" "$merged"; then RM_PROOF=ancestry; return 0; fi
  parent=$(git -C "$TX" rev-parse "$merged^" 2>/dev/null) || { RM_REASON='No parent to rebuild squash/rebase'; return 1; }
  git -C "$TX" diff --no-renames --name-only -z "$task_base" "$tip" > "$TXROOT/proof-task-paths" || return 1
  git -C "$TX" diff --no-renames --name-only -z "$parent" "$merged" > "$TXROOT/proof-result-paths" || return 1
  # Full overlay of reviewed content on the real parent. Two passes
  # handle deletions, modes and file/directory swaps correctly.
  GIT_INDEX_FILE="$TXROOT/proof-index-$ATTEMPT" git -C "$TX" read-tree "$parent" || return 1
  while IFS= read -r -d '' path; do
    GIT_INDEX_FILE="$TXROOT/proof-index-$ATTEMPT" git -C "$TX" update-index --force-remove -- "$path" || return 1
    while IFS= read -r -d '' entry; do [ "$entry" != "$path" ] || changed=yes; done < "$TXROOT/proof-result-paths"
  done < "$TXROOT/proof-task-paths"
  [ "$changed" = yes ] || { RM_REASON='The resulting commit changes no task file'; return 1; }
  while IFS= read -r -d '' path; do
    git -C "$TX" ls-tree -z "$tip" -- "$path" > "$TXROOT/proof-entry"
    while IFS=$'\t' read -r -d '' entry ignored_path; do
      IFS=' ' read -r mode type blob <<< "$entry"
      [ "$type" != tree ] || continue
      GIT_INDEX_FILE="$TXROOT/proof-index-$ATTEMPT" git -C "$TX" update-index --add --cacheinfo "$mode" "$blob" "$path" || return 1
    done < "$TXROOT/proof-entry"
  done < "$TXROOT/proof-task-paths"
  expected=$(GIT_INDEX_FILE="$TXROOT/proof-index-$ATTEMPT" git -C "$TX" write-tree) || return 1
  actual=$(git -C "$TX" rev-parse "$merged^{tree}") || return 1
  [ "$expected" = "$actual" ] || { RM_REASON='The resulting tree hash does not match the reviewed content'; return 1; }
  # A merge that dropped changes already in the parent does not credit this task.
  git -C "$TX" diff --quiet "$parent" "$merged" && { RM_REASON='The integration result contains no changes'; return 1; }
  RM_PROOF="tree:$actual"
}
merge_tick_lock() {
  local lock="$TX/queue/merge-lock.md" until token task
  [ -f "$lock" ] || return 0
  until=$(field "$lock" Lease-Until); token=$(field "$lock" Token); task=$(field "$lock" Task)
  case "$until" in ''|*[!0-9]*) return 0;; esac
  [ "$NOW" -ge "$until" ] || return 0
  if typeset -f coord_receipt >/dev/null 2>&1; then
    coord_receipt queue-lock "$token" "$until" HUMAN 'Lock lease expired; revalidate before merging' || true
  fi
  if [ -f "$TX/queue/$task.md" ]; then
    put "$TX/queue/$task.md" State HUMAN; put "$TX/queue/$task.md" Reason 'Lock lease expired; revalidate before merging'
  fi
  rm -f "$lock"
}
rm_lock_owned() {
  [ -f "$TX/queue/merge-lock.md" ] && [ "$(field "$TX/queue/merge-lock.md" Token)" = "$RM_TOKEN" ]
}
rm_authority_check() {
  local freeze
  [ "$(rm_config Autonomy no)" = yes ] || { RM_REASON='Autonomy revoked or not explicitly authorized'; return 1; }
  [ "$(rm_config Auto-Merge no)" = yes ] || { RM_REASON='Auto-merge not explicitly authorized'; return 1; }
  freeze=$(rm_config Freeze-Epoch 0)
  if [ "$freeze" -gt 0 ] && [ "$NOW" -ge "$freeze" ]; then
    typeset -f coord_freeze_allowed >/dev/null 2>&1 && coord_freeze_allowed || {
      RM_REASON="FREEZE: $ID is not allowed after the freeze (human: uak allow $ID --reason TEXT)"; return 1;
    }
  fi
  return 0
}
rm_coord_mutate() {
  local lock="$TX/queue/merge-lock.md" until current_base
  RECORD=$(task_file); CLAIM=$(claim_file); mkdir -p "$TX/queue"
  case "$RM_ACTION" in
    enqueue|lock|finalize)
      # Merged by another agent while this one waited for the queue: done, not a human problem.
      # Why (Chilangatón): the owner's merge waited on "Queue busy" while an adopter merged PB-024; it then went
      # to the human queue as "Task without claim" and wrote "Humano: …" on the INTEGRATED record.
      [ "$(field "$RECORD" State)" != INTEGRATED ] || return 5
      [ -f "$RECORD" ] && [ -f "$CLAIM" ] || { RM_REASON='Task without claim; cannot merge'; return 3; }
      [ "$(field "$RECORD" State)" = REVIEW ] || { RM_REASON='Run done first to enter REVIEW'; return 3; }
      # An approved task waits for nobody: after Merge-Adopt-Seconds (20 min) any eligible agent may merge it.
      # The lease does not matter in REVIEW: the approval of the exact SHA is what is verified.
      # Why (MLB hackathon): approved tasks waited 7-13 h for their owner's `uak merge` (HACK-016 blocked 4
      # tasks for 10 h) and two agents sent the human "stop and merge" messages.
      if [ "$(field "$RECORD" Owner)" != "$AGENT" ]; then
        local rv="$TX/reviews/$ID.md" adopt reviewed
        adopt=$(rm_config Merge-Adopt-Seconds 1200); case "$adopt" in ''|*[!0-9]*) adopt=1200;; esac
        reviewed=$(field "$rv" Reviewed); case "$reviewed" in ''|*[!0-9]*) reviewed=$NOW;; esac
        [ "$(field "$rv" Verdict)" = approve ] || { RM_REASON="Only the owner ($(field "$RECORD" Owner)) merges a task without an approval"; return 3; }
        [ $((NOW - reviewed)) -ge "$adopt" ] || {
          RM_REASON="The owner $(field "$RECORD" Owner) has $(( (adopt - NOW + reviewed + 59) / 60 )) min left to merge its approved task; after that any agent can"; return 3; }
        review_identity_eligible "$AGENT" || { RM_REASON='Merging another agent'"'"'s task needs an active claim or a registered role'; return 3; }
        RM_ADOPTED=yes
      fi;;
  esac
  case "$RM_ACTION" in
    enqueue)
      printf '%s\n' "ID: $ID" 'State: WAITING' "Owner: $AGENT" "Queued: $NOW" 'Reason: Waiting for queue' > "$TX/queue/$ID.md";;
    lock)
      merge_tick_lock
      if [ -f "$lock" ] && ! rm_lock_owned; then RM_REASON='Queue busy'; return 4; fi
      printf '%s\n' "Owner: $AGENT" "Task: $ID" "Token: $RM_TOKEN" "Lease-Until: $((NOW + RM_LOCK_LEASE))" "Updated: $NOW" > "$lock"
      put "$TX/queue/$ID.md" State MERGING;;
    human)
      # Merged meanwhile (another agent's merge, or `integrate` after a forge merge): release the lock, nothing else.
      if [ "$(field "$RECORD" State)" = INTEGRATED ]; then rm_lock_owned && rm -f "$lock"; return 0; fi
      printf '%s\n' "ID: $ID" 'State: HUMAN' "Owner: $AGENT" "Updated: $NOW" "Reason: $(one_line "$RM_QUEUE_REASON")" > "$TX/queue/$ID.md"
      if [ -f "$RECORD" ]; then
        put "$RECORD" Next "Humano: $(one_line "$RM_QUEUE_REASON")"
        [ ! -f "$CLAIM" ] || put "$CLAIM" Next "Humano: $(one_line "$RM_QUEUE_REASON")"
        WL=$(field "$RECORD" Worklog); STATE=$(field "$RECORD" State)
        [ ! -f "$TX/$WL" ] || { update_summary_field Next "Humano: $RM_QUEUE_REASON"; event "merge rechazado; $RM_QUEUE_REASON"; }
      fi
      msg_append human human "$ID" "Merge of $ID in human queue: $RM_QUEUE_REASON"
      rm_lock_owned && rm -f "$lock";;
    unlock)
      if rm_lock_owned; then rm -f "$lock"; else return 6; fi;;
    finalize)
      rm_authority_check || return 3
      rm_lock_owned || { RM_REASON='Lock perdido; candidato cancelado'; return 3; }
      until=$(field "$lock" Lease-Until)
      [ "$NOW" -lt "$until" ] || { RM_REASON='Lock expired; candidate cancelled'; return 3; }
      git -C "$TX" fetch -q origin "refs/heads/$BASE:refs/uak/base" || { RM_REASON='Could not revalidate the base'; return 3; }
      current_base=$(git -C "$TX" rev-parse refs/uak/base)
      [ "$current_base" = "$RM_BASE_TIP" ] || { RM_REASON='Base moved; revalidate the candidate'; return 3; }
      resolve_task_tip || return 3
      [ "$RM_TIP" = "$RM_REVIEWED_TIP" ] || { RM_REASON='Task SHA changed during validation'; return 3; }
      approval_check "$RM_TIP" "$(field "$RECORD" PR)" || return 3
      git -C "$TX" fetch -q "$RM_BUILD" "$RM_CANDIDATE:refs/uak/candidate" || { RM_REASON='Candidate not available'; return 3; }
      STATE=INTEGRATED; WL=$(field "$RECORD" Worklog)
      put "$RECORD" State INTEGRATED; put "$RECORD" Merge-Commit "$RM_CANDIDATE"; put "$RECORD" Reviewer "$APPROVED_BY"
      put "$RECORD" Task-Tip "$RM_REVIEWED_TIP"; put "$RECORD" Integration-Proof ancestry
      [ "${RM_ADOPTED:-no}" != yes ] || put "$RECORD" Merged-By "$AGENT"
      put "$RECORD" Lease-Until 0; put "$RECORD" Updated "$NOW"; put "$RECORD" Next "Integrated in $BASE: $RM_CANDIDATE"
      update_summary_field Next "Integrated in $BASE: $RM_CANDIDATE"; event "merge; smoke and Verify PASS; commit $RM_CANDIDATE; reviewer $APPROVED_BY"
      rm -f "$CLAIM" "$lock"; put "$TX/queue/$ID.md" State INTEGRATED; put "$TX/queue/$ID.md" Commit "$RM_CANDIDATE"
      msg_notify_related "$ID" integrated "$ID integrated in $BASE ($RM_CANDIDATE). If you depend on it: git fetch origin && git merge origin/$BASE";;
  esac
  return 0
}
rm_coord_update() {
  local rc attempts=0
  RM_ACTION=$1
  while [ "$attempts" -lt 80 ]; do
    attempts=$((attempts + 1)); RM_COUNTER=$((RM_COUNTER + 1)); ATTEMPT="merge-$RM_COUNTER"
    fresh_state
    if typeset -f coord_init >/dev/null 2>&1; then coord_init; fi
    rm_coord_mutate; rc=$?
    [ "$rc" -ne 6 ] || return 0
    [ "$rc" -eq 0 ] || return "$rc"
    snapshot
    git -C "$TX" add -A || { RM_REASON='Could not prepare the queue transaction'; return 3; }
    git -C "$TX" diff --cached --quiet && return 0
    git -C "$TX" commit -q -m "uak: merge $ID $RM_ACTION ($AGENT)" || { RM_REASON='Queue commit failed'; return 3; }
    if [ "$RM_ACTION" = finalize ]; then
      git -C "$TX" push --atomic --porcelain origin HEAD:refs/heads/claims refs/uak/candidate:refs/heads/"$BASE" > "$TXROOT/merge-push" 2>&1 && return 0
    else
      git -C "$TX" push --porcelain origin HEAD:refs/heads/claims > "$TXROOT/merge-push" 2>&1 && return 0
    fi
    if ! grep -Eqi 'fetch first|non-fast-forward|cannot lock ref|already exists|failed to update ref|incorrect old value provided' "$TXROOT/merge-push"; then
      RM_REASON='Queue/base push rejected; check remote, atomic push and permissions'; return 3
    fi
  done
  RM_REASON='Contention exceeded retries; try again'; return 3
}
rm_exit_cleanup() {
  local rc=$1
  trap - EXIT INT TERM
  if [ "$RM_HELD" = yes ]; then
    if [ "$RM_FINISHED" != yes ]; then
      RM_QUEUE_REASON=${RM_QUEUE_REASON:-'Process interrupted; needs revalidation'}
      # A remote error exit is contained and does not prevent temp cleanup.
      (rm_coord_update human) >/dev/null 2>&1 || {
        RM_COUNTER=$((RM_COUNTER + 1000))
        (rm_coord_update unlock) >/dev/null 2>&1 || true
      }
    else (rm_coord_update unlock) >/dev/null 2>&1 || true; fi
  fi
  cleanup
  exit "$rc"
}
# " (Paths of HACK-029)" when another task reserves that file; empty otherwise.
rm_path_owner() {
  local t
  printf '%s\n' "$1" > "$TXROOT/owner-path"
  for t in "$TX"/tasks/*.md; do
    [ -f "$t" ] && [ "$(field "$t" ID)" != "$ID" ] || continue
    normalize_paths "$(field "$t" Paths)" > "$TXROOT/owner-paths" 2>/dev/null || continue
    if overlaps "$TXROOT/owner-path" "$TXROOT/owner-paths"; then printf ' (Paths of %s)' "$(field "$t" ID)"; return 0; fi
  done
}
rm_gate_scope() {
  local path allowed reserve
  normalize_paths "$(field "$RECORD" Paths)" > "$TXROOT/merge-allowed" || { RM_REASON='Invalid claim Paths'; return 1; }
  # Scope = what this merge changes in the CURRENT base (the staged candidate vs RM_BASE_TIP), not Task-Base..tip.
  # Why (Reap buildathon, 6 of 13 merged tasks): a branch that merged origin/main inherited other tasks' files
  # (.env.example, workflows, PROJECT.md) and every one of them was sent to the human queue as "outside Paths".
  git -C "$RM_BUILD" diff --cached --no-renames --name-only -z "$RM_BASE_TIP" > "$TXROOT/merge-files" || return 1
  # Additive-Paths (PROJECT.md, e.g. `e2e/, tests/`): NEW files there need no reservation; edits still do.
  # Why (UpiixSol): 4 of 11 decisions were "this task adds a new test file outside its Paths", 15 min each.
  : > "$TXROOT/merge-additive"
  additive=-; [ ! -f "$TXROOT/coord-source" ] || additive=$(coord_source_field Additive-Paths -)
  if [ -n "$additive" ] && [ "$additive" != - ]; then
    normalize_paths "$additive" > "$TXROOT/merge-additive" 2>/dev/null || : > "$TXROOT/merge-additive"
  fi
  git -C "$RM_BUILD" diff --cached --no-renames --diff-filter=A --name-only "$RM_BASE_TIP" > "$TXROOT/merge-added" || return 1
  while IFS= read -r -d '' path; do
    case "$path" in *$'\n'*|*$'\r'*) RM_REASON='Path with newline not supported'; return 1;; esac
    # Shared resources first, so the reason says what it really is (MLB: the smoke provenance file, written by
    # init-smoke, was reported as "outside Paths").
    case "/$(printf '%s' "$path" | tr '[:upper:]' '[:lower:]')/" in
      */contracts/*|*/types/*|*/shared-types/*|*/migrations/*|*/db/migration/*|*/gradle.lockfile/*|*/.github/workflows/*|*/.gitlab-ci.yml/*|*/azure-pipelines.yml/*|*/package-lock.json/*|*/pnpm-lock.yaml/*|*/*.lock/*|*/*.lockb/*|*/go.sum/*|*/.uak/bin/smoke/*|*/.uak/bin/smoke-project/*|*/.uak/bin/.smoke-project.provenance/*|*/.uak/bin/secret-scan/*|*/.uak/bin/uak/*|*/.uak/bin/lib/*|*/.uak/bin/uak-coordination/*|*/.githooks/*|*/hackathon.md/*|*/.uak/project.md/*)
        RM_REASON="Shared resource/CI needs a human: $path"; return 1;;
    esac
    normalize_paths "$path" > "$TXROOT/merge-path" || { RM_REASON='Invalid diff path'; return 1; }
    allowed=no
    while IFS= read -r reserve; do
      printf '%s\n' "$reserve" > "$TXROOT/merge-reserve"
      overlaps "$TXROOT/merge-path" "$TXROOT/merge-reserve" && allowed=yes
    done < "$TXROOT/merge-allowed"
    added=no; ! grep -qxF -- "$path" "$TXROOT/merge-added" 2>/dev/null || added=yes
    if [ "$allowed" = no ] && [ "$added" = yes ] && [ -s "$TXROOT/merge-additive" ] &&
       overlaps "$TXROOT/merge-path" "$TXROOT/merge-additive"; then allowed=yes; fi
    # A new EMPTY file (package marker such as __init__.py, .gitkeep) changes no behavior of other tasks.
    # Why (MLB hackathon): an empty app/__init__.py and analysis/__init__.py sent two merges to the human.
    if [ "$allowed" = no ] && [ "$added" = yes ] && [ "$(git -C "$RM_BUILD" cat-file -s ":$path" 2>/dev/null)" = 0 ]; then allowed=yes; fi
    if [ "$allowed" = no ]; then
      if printf '%s' "$path" | grep -Eq '(^|/)(__pycache__|node_modules|\.pytest_cache|\.next|dist|build|target|\.gradle)/|\.pyc$|\.class$|(^|/)\.DS_Store$'; then
        RM_REASON="Generated file committed: $path. Remove it from the branch (git rm -r --cached $path), add the pattern to .gitignore, push, and ask for review again"
      elif [ "$added" = yes ]; then
        RM_REASON="New file outside Paths: $path. Move it into the task's Paths, or a human adds its dir to Additive-Paths in PROJECT.md (new files there need no reservation)"
      else
        RM_REASON="Edits a file outside Paths: $path$(rm_path_owner "$path"). Revert that file on the branch (git checkout origin/$BASE -- $path), or the human merges the PR"
      fi
      return 1
    fi
  done < "$TXROOT/merge-files"
}
# The candidate is a fresh clone: no .venv, no node_modules, no git-ignored data. The gate puts the worktree's
# (or the main checkout's) virtualenv first on PATH and exports UAK_MAIN_CHECKOUT for project scripts.
# Why (MLB hackathon): 6 of 17 human-queue entries were "Smoke red" because the clone had no Python env;
# agents worked around it with PATH=<main>/.venv/Scripts:$PATH by hand.
rm_gate_env() {
  local v
  RM_MAIN=$(cd "$ROOT" && cd "$(git rev-parse --git-common-dir)/.." 2>/dev/null && pwd -P) || RM_MAIN=$ROOT
  RM_GATE_PATH=$PATH
  for v in "$ROOT/.venv" "$RM_MAIN/.venv" "$ROOT/venv" "$RM_MAIN/venv"; do
    if [ -d "$v/Scripts" ]; then RM_GATE_PATH="$v/Scripts:$PATH"; break; fi
    if [ -d "$v/bin" ]; then RM_GATE_PATH="$v/bin:$PATH"; break; fi
  done
  [ -z "${RM_BUILD:-}" ] || rm_gate_node
}
# Node packages for the candidate: each package.json (up to 2 levels deep) gets the worktree's or the main
# checkout's node_modules when its lockfile is identical (a link, or a junction on Windows); a changed lockfile
# gets `npm ci`. Why (MLB hackathon): 3 merges went to the human queue with "vitest: command not found" though
# Verify had passed in the worktree.
rm_link_dir() { # $1 existing dir, $2 link path
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) command -v cygpath >/dev/null 2>&1 &&
      cmd //c mklink /J "$(cygpath -w "$2")" "$(cygpath -w "$1")" >/dev/null 2>&1;;
    *) ln -s "$1" "$2" 2>/dev/null;;
  esac
}
rm_gate_node() {
  local pj d lock src done_
  git -C "$RM_BUILD" ls-files -- 'package.json' '*/package.json' '*/*/package.json' 2>/dev/null | grep -v node_modules > "$TXROOT/gate-node" || return 0
  while IFS= read -r pj; do
    d=$(dirname "$pj"); [ "$d" != . ] || d=
    [ ! -e "$RM_BUILD/${d:+$d/}node_modules" ] || continue
    lock=
    for f in package-lock.json pnpm-lock.yaml yarn.lock bun.lockb npm-shrinkwrap.json; do [ -f "$RM_BUILD/${d:+$d/}$f" ] && { lock=$f; break; }; done
    [ -n "$lock" ] || continue
    done_=no
    for src in "$ROOT/${d:+$d/}" "$RM_MAIN/${d:+$d/}"; do
      [ -d "${src}node_modules" ] && cmp -s "${src}$lock" "$RM_BUILD/${d:+$d/}$lock" || continue
      if rm_link_dir "${src}node_modules" "$RM_BUILD/${d:+$d/}node_modules"; then
        printf '%s\n' "$RM_BUILD/${d:+$d/}node_modules" >> "$TXROOT/gate-links"; done_=yes; break
      fi
    done
    if [ "$done_" = no ] && [ "$lock" = package-lock.json ] && command -v npm >/dev/null 2>&1; then
      (cd "$RM_BUILD/${d:-.}" && npm ci --no-audit --no-fund --loglevel=error) >> "$TXROOT/gate-node.log" 2>&1 || true
    fi
  done < "$TXROOT/gate-node"
  return 0
}
# Keeps a failed gate log (the temp dir is deleted) and returns ": last error line (log: PATH)".
# Why (MLB, Codex): "merge smoke failed without exposing the diagnostic log".
rm_gate_log() {
  local src="$TXROOT/gate-$1.log" dir dst line
  dir="$(git -C "$ROOT" rev-parse --absolute-git-dir 2>/dev/null)/uak-out"; mkdir -p "$dir" 2>/dev/null || return 0
  dst="$dir/gate-$ID-$1-$NOW.log"; cp "$src" "$dst" 2>/dev/null || return 0
  line=$(grep -Ev '^[[:space:]]*$' "$dst" | grep -Ei 'error|fail|not found|no module|exit' | tail -n 1 | cut -c 1-140)
  [ -n "$line" ] || line=$(grep -Ev '^[[:space:]]*$' "$dst" | tail -n 1 | cut -c 1-140)
  printf ': %s (log: %s)' "$(one_line "$line" | tr '|' '/')" "$dst"
}
rm_prepare_candidate() {
  local branch task_base verify
  RECORD=$(task_file); CLAIM=$(claim_file)
  rm_authority_check || return 1
  resolve_task_tip || return 1; RM_REVIEWED_TIP=$RM_TIP
  approval_check "$RM_REVIEWED_TIP" "$(field "$RECORD" PR)" || return 1
  task_base=$(field "$RECORD" Task-Base); branch=$(field "$RECORD" Branch)
  git -C "$TX" cat-file -e "$task_base^{commit}" 2>/dev/null || { RM_REASON='Task-Base not available'; return 1; }
  git -C "$TX" merge-base --is-ancestor "$task_base" "$RM_REVIEWED_TIP" || { RM_REASON='Task-Base is not in the current history'; return 1; }
  git -C "$TX" diff --quiet "$task_base" "$RM_REVIEWED_TIP" && { RM_REASON='The task has no implementation'; return 1; }
  RM_BUILD="$TXROOT/candidate"
  git clone -q --no-checkout "$REMOTE_URL" "$RM_BUILD" || { RM_REASON='Could not clone the current base'; return 1; }
  git -C "$RM_BUILD" config user.name "$USER_NAME"; git -C "$RM_BUILD" config user.email "$USER_EMAIL"
  git -C "$RM_BUILD" fetch -q origin "refs/heads/$BASE:refs/uak/base" || { RM_REASON='Remote base not available'; return 1; }
  RM_BASE_TIP=$(git -C "$RM_BUILD" rev-parse refs/uak/base)
  git -C "$RM_BUILD" fetch -q "$TX" "$RM_REVIEWED_TIP:refs/uak/task" || { RM_REASON='Task TIP not available'; return 1; }
  git -C "$RM_BUILD" checkout -q --detach "$RM_BASE_TIP" || return 1
  # Validates the merge with the current base without rewriting the approved SHA.
  git -C "$RM_BUILD" merge --no-ff --no-commit "$RM_REVIEWED_TIP" > "$TXROOT/candidate-merge.log" 2>&1 || {
    RM_REASON='Conflict with current base; a human must resolve and request a new review'; return 1;
  }
  RM_TREE=$(git -C "$RM_BUILD" write-tree) || { RM_REASON='Could not capture the candidate tree'; return 1; }
  rm_gate_scope || return 1
  [ -f "$RM_BUILD/.uak/bin/secret-scan" ] || { RM_REASON='Missing built-in secret scanner'; return 1; }
  (cd "$RM_BUILD" && bash .uak/bin/secret-scan --tracked --decisions "$TX/DECISIONS.md") > "$TXROOT/gate-secrets.log" 2>&1 || {
    RM_REASON='Secret gate red'; return 1;
  }
  rm_gate_env
  (cd "$RM_BUILD" && PATH="$RM_GATE_PATH" UAK_MAIN_CHECKOUT="$RM_MAIN" bash .uak/bin/smoke) > "$TXROOT/gate-smoke.log" 2>&1 ||
    { RM_REASON="Smoke red or product unverified$(rm_gate_log smoke)"; return 1; }
  verify=$(field "$RECORD" Verify); verify=$(printf '%s\n' "$verify" | sed 's/^`//;s/`$//')
  [ -n "$verify" ] || { RM_REASON='Missing runnable Verify'; return 1; }
  (cd "$RM_BUILD" && PATH="$RM_GATE_PATH" UAK_MAIN_CHECKOUT="$RM_MAIN" bash -c "$verify") > "$TXROOT/gate-verify.log" 2>&1 ||
    { RM_REASON="Verify / acceptance red$(rm_gate_log verify)"; return 1; }
  git -C "$RM_BUILD" diff --quiet && [ "$(git -C "$RM_BUILD" write-tree)" = "$RM_TREE" ] || {
    RM_REASON='Smoke/Verify modified tracked files of the candidate; needs a new review'; return 1;
  }
  git -C "$RM_BUILD" diff --quiet && git -C "$RM_BUILD" diff --cached --quiet && {
    RM_REASON='Candidate adds no changes'; return 1;
  }
  git -C "$RM_BUILD" commit -q -m "Merge $ID reviewed by $APPROVED_BY" || { RM_REASON='Could not create the merge commit'; return 1; }
  RM_CANDIDATE=$(git -C "$RM_BUILD" rev-parse HEAD)
}
# Why (Reap): 9 merges went to the human queue; the fast path (merge on the forge + integrate) was not said.
rm_human_hint() {
  local pr; pr=$(field "$(task_file)" PR)
  say "HUMAN: review the reason; if the PR is fine, merge ${pr:-it} on the forge, then any agent runs: bash .uak/bin/uak integrate $ID"
}
rm_already_integrated() {
  local rec; rec=$(task_file)
  say "OK merge $ID | already INTEGRATED by $(field "$rec" Merged-By | grep . || field "$rec" Owner) | $(field "$rec" Merge-Commit | cut -c 1-12) | nothing to do"
}
merge_run() {
  local waited=0 rc wait_started
  # No approval on the current SHA yet is a "wait", not a human-queue entry.
  # Why (Reap buildathon): HACK-008 and HACK-010 ran merge before any review; both landed in the human queue
  # ("Missing verifiable approval") and a human had to read them.
  ATTEMPT=precheck; fresh_state; RECORD=$(task_file)
  [ "$(field "$RECORD" State)" != INTEGRATED ] || { rm_already_integrated; return 0; }
  if [ -f "$RECORD" ] && [ "$(field "$RECORD" State)" = REVIEW ] && resolve_task_tip &&
     ! approval_check "$RM_TIP" "$(field "$RECORD" PR)"; then
    case "$RM_REASON" in 'Missing verifiable approval on claims'|'Approval missing, rejected, self-made or stale for the current SHA'|'GitHub shows no current independent approval on this SHA')
      local rv="$TX/reviews/$ID.md" last=
      [ ! -f "$rv" ] || last=" Last review: $(field "$rv" Verdict) by $(field "$rv" Reviewer) on ${RM_TIP:+$(field "$rv" SHA | cut -c 1-7)}."
      say "MERGE_WAIT $ID | $RM_REASON (current SHA $(printf '%s' "$RM_TIP" | cut -c 1-7)).$last Wait for an approve message on this SHA (or fix a reject and push); nothing was queued."
      return 3;;
    esac
  fi
  RM_TOKEN="$(basename "$TXROOT")-$AGENT-$ID"; RM_HELD=no; RM_FINISHED=no
  rm_coord_update enqueue; rc=$?
  [ "$rc" -ne 5 ] || { rm_already_integrated; return 0; }
  [ "$rc" -eq 0 ] || { say "MERGE_HUMAN $ID | $RM_REASON"; return 3; }
  RM_LOCK_LEASE=$(rm_config Merge-Lease-Seconds 1800); RM_WAIT=$(rm_config Merge-Wait-Seconds 180)
  case "$RM_LOCK_LEASE:$RM_WAIT" in *[!0-9:]*|0:*|*:0) die 'Merge lease/wait must be positive seconds.';; esac
  wait_started=$(date +%s)
  while :; do
    clock_now
    rm_coord_update lock; rc=$?
    if [ "$rc" -eq 0 ]; then RM_HELD=yes; break; fi
    [ "$rc" -ne 5 ] || { rm_already_integrated; return 0; }
    waited=$(($(date +%s) - wait_started))
    # A busy queue is a wait, not a human problem (MLB: "Queue busy" landed in the human queue).
    if [ "$rc" -eq 4 ] && [ "$waited" -ge "$RM_WAIT" ]; then
      say "MERGE_BUSY $ID | $(field "$TX/queue/merge-lock.md" Task) is merging; nothing was lost. Run uak merge $ID again in a few minutes."
      return 3
    fi
    [ "$rc" -eq 4 ] || {
      RM_QUEUE_REASON=${RM_REASON:-'Queue wait exhausted'}; rm_coord_update human || true
      say "MERGE_HUMAN $ID | $RM_QUEUE_REASON"; rm_human_hint; return 3;
    }
    sleep 1
  done
  trap 'rm_exit_cleanup $?' EXIT
  trap 'exit 130' INT; trap 'exit 143' TERM
  if ! rm_prepare_candidate; then
    RM_QUEUE_REASON=${RM_REASON:-'Candidate validation failed'}
    if rm_coord_update human; then RM_HELD=no; fi
    [ "$(field "$(task_file)" State)" != INTEGRATED ] || { rm_already_integrated; return 0; }
    say "MERGE_HUMAN $ID | $RM_QUEUE_REASON"; rm_human_hint; return 3
  fi
  clock_now
  rm_coord_update finalize; rc=$?
  if [ "$rc" -ne 0 ]; then
    RM_QUEUE_REASON=${RM_REASON:-'Atomic publish failed'}
    if rm_coord_update human; then RM_HELD=no; fi
    [ "$rc" -ne 5 ] || { rm_already_integrated; return 0; }
    say "MERGE_HUMAN $ID | $RM_QUEUE_REASON"; rm_human_hint; return 3
  fi
  RM_FINISHED=yes; RM_HELD=no
  say "OK merge $ID | INTEGRATED | $RM_CANDIDATE | review $APPROVED_BY | atomic claims+$BASE"
}
