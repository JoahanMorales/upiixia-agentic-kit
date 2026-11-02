# lint: budgets, the claims invariants, and the backlog checks that would make a task unclaimable or its Verify red.
# Sourced by .uak/bin/uak (docs/ARCHITECTURE.md: where to change what). Bash 3.2+, POSIX tools.

# DESIGN.md filled from its template, and every UI task names its recipe and hero. Why (Hacktoberfest): the lock had a
# 15 px body and no screen table, and ten screens copied the one locked screen.
lint_design() {
  local d ui id tp
  for d in "$ROOT/web/DESIGN.md" "$ROOT/DESIGN.md"; do
    [ -f "$d" ] || continue
    if grep -q '`<[^`]*>`' "$d"; then
      say "LINT: ${d#"$ROOT"/} still has template fields: $(grep -n '`<[^`]*>`' "$d" | head -n 3 | cut -d: -f1 | tr '\n' ' ')(line numbers). The design lock fills every one." >&2
      LINT_ERRORS=$((LINT_ERRORS + 1))
    fi
    grep -q '^## Screens' "$d" || say "LINT WARNING: ${d#"$ROOT"/} has no '## Screens' table (screen → recipe → hero): .uak/templates/DESIGN.template.md" >&2
  done
  [ -s "$BACKLOG" ] || return 0
  if [ -f "$TXROOT/coord-source" ]; then ui=$(coord_source_field UI-Paths -)
  else ui=$(uak_cfg "$ROOT/.uak/PROJECT.md" UI-Paths); fi
  [ -n "$ui" ] && [ "$ui" != - ] || return 0
  normalize_paths "$ui" > "$TXROOT/lint-ui" 2>/dev/null || return 0
  for id in $(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG"); do
    tp=$(ID=$id task_field Paths)
    case "$tp" in *DESIGN.md*|*design-lock*) continue;; esac
    normalize_paths "$tp" > "$TXROOT/lint-tp" 2>/dev/null || continue
    overlaps "$TXROOT/lint-tp" "$TXROOT/lint-ui" || continue
    awk -v id="$id" '/^## / { on = ($2 == id) } on && /Recipe:/ { f = 1 } END { exit !f }' "$BACKLOG" ||
      say "LINT WARNING: $id writes UI but names no recipe: add to its Acceptance \"Recipe: <map + panel | dashboard | detail | flow | list> · Hero: <element>\" (web/DESIGN.md, ## Screens)." >&2
  done
}
# A Verify bash cannot parse is red at the gate whatever the code does; prints bash's error. Why (HackADA): an
# unbalanced quote in a published Verify sent an approved PR to the human queue as "unexpected end of file".
verify_parse_error() {
  local v err
  v=$(printf '%s\n' "$1" | sed 's/^`//;s/`$//')
  err=$(bash -n -c "$v" 2>&1) && return 1
  printf '%s\n' "$err" | head -n 1 | sed 's/^bash: -c: //'
}
# `! rg …` passes on a machine without rg (command not found is a failure, and ! turns it into success). Why
# (HackADA): a negated rg in Verify passed for any code where rg was missing; Git Bash on Windows ships none.
verify_negates_rg() { printf '%s\n' "$1" | grep -Eq '(^|[;&|(`'"'"'"[:space:]])![[:space:]]+rg([[:space:]]|$)'; }
lint_verify_syntax() {
  [ -s "$BACKLOG" ] || return 0
  local id v e
  for id in $(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG"); do
    v=$(ID=$id task_field Verify); [ -n "$v" ] || continue
    if e=$(verify_parse_error "$v"); then
      say "LINT: $id's Verify does not parse ($e): check its quotes; the merge gate runs it with bash -c (uak plan FILE --amend)." >&2
      LINT_ERRORS=$((LINT_ERRORS + 1))
    fi
    ! verify_negates_rg "$v" ||
      say "LINT WARNING: $id's Verify negates rg: where rg is missing (Git Bash on Windows), \`! rg …\` passes for any code. Use \`! grep -rniE …\`." >&2
  done
}
# A feature or bug task lists its behaviors as test names: the shortest spec an agent can be given, and done checks
# each exists. Why (v5.10, test-first): "validate stock and do not charge if it fails" is ambiguous; a test name that
# says what goes in, what comes out and what must not happen is not.
lint_tests_named() {
  [ -s "$BACKLOG" ] || return 0
  local id t policy
  policy=$(uak_cfg "$ROOT/.uak/PROJECT.md" Test-First)
  [ "$policy" = yes ] || return 0
  for id in $(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG"); do
    t=$(ID=$id task_field Type | tr -d '`'); case "$t" in feature*|bug*) ;; *) continue;; esac
    case "$(ID=$id task_field Test-First)" in no*|No*) continue;; esac
    [ -n "$(ID=$id task_field Tests)" ] ||
      say "LINT WARNING: $id ($t) lists no Tests: name its behaviors (places_order_when_stock_is_enough, does_not_charge_when_payment_fails); done checks each exists. Nothing to test first? Test-First: no (why)." >&2
  done
}
lint_verify_scaffold() {
  [ -s "$BACKLOG" ] || return 0
  local id v dir need f t tp dep
  for id in $(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG"); do
    v=$(ID=$id task_field Verify | tr -d '`'); dir=
    case "$v" in "cd "*" && "*) dir=${v#cd }; dir=${dir%% &&*}; dir=${dir%/}/; v=${v#*&& };; esac
    case "$v" in "uv run"*|pytest*|"python -m pytest"*|"python3 -m pytest"*|"poetry run"*) need=pyproject.toml;;
      npm\ *|pnpm\ *|yarn\ *|npx\ *|bun\ *) need=package.json;; "go test"*|"go run"*|"go build"*) need=go.mod;;
      mvn*|./mvnw*) need=pom.xml;; cargo\ *) need=Cargo.toml;; *) continue;; esac
    f="$dir$need"
    git -C "$ROOT" cat-file -e "refs/remotes/$REMOTE/$BASE:$f" 2>/dev/null || [ -f "$ROOT/$f" ] && continue
    dep=" $(ID=$id task_field 'Depends on' | tr ',()' '   ') "
    for t in $(awk '/^## [A-Z][A-Z0-9]*-[0-9]/ {print $2}' "$BACKLOG"); do
      [ "$t" != "$id" ] || continue
      tp=$(ID=$t task_field Paths | tr -d '`' | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s#^\./##')
      printf '%s\n' "$tp" | grep -qxF -- "$f" || continue
      case "$dep" in *" $t "*) ;; *) say "LINT WARNING: $id's Verify needs $f, which $t creates; add Depends on: $t (or its Verify runs on someone's local merge of $t)." >&2;; esac
      break
    done
  done
}
budget() {
  [ -f "$1" ] || { say "LINT: missing $1" >&2; LINT_ERRORS=$((LINT_ERRORS + 1)); return; }
  lines=$(awk 'END {print NR+0}' "$1"); words=$(awk '{n+=NF} END {print n+0}' "$1")
  say "BUDGET $(basename "$1"): $lines lines / $words words (max $2 / $3)"
  if [ "$lines" -gt "$2" ] || [ "$words" -gt "$3" ]; then LINT_ERRORS=$((LINT_ERRORS + 1)); fi
}
lint_all() {
  LINT_ERRORS=0; budget "$ROOT/AGENTS.md" 100 1300
  state_file="$TX/STATE.md"; [ -f "$state_file" ] || state_file="$ROOT/STATE.md"
  [ ! -f "$state_file" ] || budget "$state_file" 60 700
  pr_template="$ROOT/.github/pull_request_template.md"
  if [ ! -f "$pr_template" ] || [ "$(awk 'END {print NR+0}' "$pr_template")" -ne 5 ]; then
    say "LINT: PR template must have 5 lines" >&2; LINT_ERRORS=$((LINT_ERRORS + 1))
  fi
  for w in "$TX"/worklog/*.md; do
    [ -f "$w" ] || continue
    summary_lines=$(awk '/^## Live summary$/ {on=1;next} /^## History$/ {on=0} on {n++} END {print n+0}' "$w")
    if [ "$summary_lines" -gt 15 ] || [ "$(grep -c '^## Live summary$' "$w")" -ne 1 ] ||
       [ "$(grep -c '^## History$' "$w")" -ne 1 ]; then
      say "LINT: invalid live summary: $(basename "$w")" >&2; LINT_ERRORS=$((LINT_ERRORS + 1))
    fi
    if ! awk '/^## History$/ {on=1;next} on && NF && $0 !~ /^- [0-9]+ \| (AVAILABLE|CLAIMED|BLOCKED|REVIEW|INTEGRATED|CANCELLED) \| / {bad=1} END {exit bad}' "$w"; then
      say "LINT: history must have one line per event: $(basename "$w")" >&2; LINT_ERRORS=$((LINT_ERRORS + 1))
    fi
    rel="worklog/$(basename "$w")"
    if git -C "$TX" show "HEAD^:$rel" > "$TXROOT/previous" 2>/dev/null; then
      awk '/^## History$/ {on=1;next} on {print}' "$TXROOT/previous" > "$TXROOT/history-old"
      awk '/^## History$/ {on=1;next} on {print}' "$w" > "$TXROOT/history-new"
      n=$(awk 'END {print NR+0}' "$TXROOT/history-old")
      head -n "$n" "$TXROOT/history-new" > "$TXROOT/history-prefix"
      if ! cmp -s "$TXROOT/history-old" "$TXROOT/history-prefix"; then
        say "LINT: history modified, must be append-only: $rel" >&2; LINT_ERRORS=$((LINT_ERRORS + 1))
      fi
    fi
  done
  for f in "$TX"/tasks/*.md; do
    [ -f "$f" ] || continue
    state=$(field "$f" State); id=$(field "$f" ID)
    case "$state" in AVAILABLE|CLAIMED|BLOCKED|REVIEW|INTEGRATED|CANCELLED) ;; *)
      say "LINT: invalid state in $id" >&2; LINT_ERRORS=$((LINT_ERRORS + 1));; esac
    reserved=no; is_reserved "$state" && reserved=yes
    if { [ "$reserved" = yes ] && [ ! -f "$TX/claims/$id.md" ]; } ||
       { [ "$reserved" = no ] && [ -f "$TX/claims/$id.md" ]; }; then
      say "LINT: state and claim inconsistent in $id" >&2; LINT_ERRORS=$((LINT_ERRORS + 1))
    fi
    wl=$(field "$f" Worklog)
    if ! valid_worklog "$wl" || [ ! -f "$TX/$wl" ]; then
      say "LINT: missing valid worklog $id" >&2; LINT_ERRORS=$((LINT_ERRORS + 1))
    fi
  done
  for f in "$TX"/claims/*.md; do
    [ -f "$f" ] || continue
    id=$(field "$f" ID)
    [ -f "$TX/tasks/$id.md" ] || { say "LINT: orphan claim $id" >&2; LINT_ERRORS=$((LINT_ERRORS + 1)); }
    if [ -f "$TX/tasks/$id.md" ]; then
      for key in State Owner Branch Worktree Lease-Until Worklog; do
        if [ "$(field "$f" "$key")" != "$(field "$TX/tasks/$id.md" "$key")" ]; then
          say "LINT: claim and task differ in $id/$key" >&2; LINT_ERRORS=$((LINT_ERRORS + 1))
        fi
      done
    fi
  done
  owner_rows > "$TXROOT/owners"
  # No backlog yet (before /uak-plan): the template's owner rows name tasks the plan will create.
  [ -s "$BACKLOG" ] || : > "$TXROOT/owners"
  # One line per missing owner, with its rows. Why (Oct 2026): the template's rows name HACK-001; a plan with another
  # prefix got 12 identical "owner not in TASKS" lines and no hint of the fix.
  awk -F'|' 'NF >= 2 && $2 != "" { n[$2]++; if (n[$2] <= 3) ex[$2] = ex[$2] (ex[$2] == "" ? "" : ", ") $1 }
             END { for (o in n) print o "|" n[o] "|" ex[o] (n[o] > 3 ? ", ..." : "") }' "$TXROOT/owners" | sort > "$TXROOT/owners-by"
  while IFS='|' read -r owner count examples; do
    if ! awk -v id="$owner" '/^## / && $2==id {found=1} END {exit !found}' "$BACKLOG"; then
      say "LINT: owner not in TASKS: $owner owns $count row(s) of OWNERS.md ($examples). Point them to the task that sets those files up, or delete the rows for files this project does not have." >&2
      LINT_ERRORS=$((LINT_ERRORS + 1))
    fi
  done < "$TXROOT/owners-by"
  while IFS='|' read -r id pat owner; do
    [ -n "$id" ] || continue
    say "LINT: $id can never be claimed: its Paths fall under '$pat', owned by $owner in OWNERS.md. Drop the path from $id (uak plan FILE --amend), give the row to $id, or make $owner depend on $id." >&2
    LINT_ERRORS=$((LINT_ERRORS + 1))
  done <<EOF_OC
$( [ ! -s "$BACKLOG" ] || owner_conflicts )
EOF_OC
  # A Verify that needs a project file (pyproject.toml, package.json…) another task creates: that task belongs in
  # Depends on. Why (Hacktoberfest): 12 backend tasks said "Depends on: None" while their `uv run pytest` needed the
  # scaffold's pyproject; agents verified on local merges of it, stacked branches and clashed with its ruff config.
  lint_verify_scaffold
  lint_verify_syntax
  lint_tests_named
  lint_design
  # sprint without a freeze = features until the last minute (Hack-Nation: 8 PRs, incl. a product rename, in the last 6 h).
  if [ -f "$ROOT/.uak/PROJECT.md" ] && case "$(uak_cfg "$ROOT/.uak/PROJECT.md" Mode)" in sprint*) true;; *) false;; esac &&
     case "$(uak_cfg "$ROOT/.uak/PROJECT.md" Freeze-Epoch)" in [1-9]*) false;; *) true;; esac; then
    say "LINT: Mode sprint without Freeze-Epoch in .uak/PROJECT.md" >&2; LINT_ERRORS=$((LINT_ERRORS + 1))
  fi
  # Execution graph: cycles and unknown dependencies make tasks unclaimable forever.
  if [ -s "$BACKLOG" ] && [ -f "$UAK_BIN/graph" ]; then
    bash "$UAK_BIN/graph" --file "$BACKLOG" > "$TXROOT/graph" 2>&1 ||
      { grep -E '^(CYCLE|MISSING|DUPLICATE)' "$TXROOT/graph" | sed 's/^/LINT: /' >&2; LINT_ERRORS=$((LINT_ERRORS + 1)); }
  fi
  if [ "$LINT_SECRETS" = yes ]; then secrets_lint || LINT_ERRORS=$((LINT_ERRORS + 1)); fi
  [ "$LINT_ERRORS" -eq 0 ] || { say "LINT_FAILED $LINT_ERRORS"; return 1; }
  say "LINT_OK"
}
lint_run() { ATTEMPT=1; fresh_state; lint_all; }
# No remote (before the first push, a fresh clone, CI): the local files only.
lint_local() { TX="$TXROOT/local"; mkdir -p "$TX/worklog" "$TX/tasks" "$TX/claims"; lint_all; }
