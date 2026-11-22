# Test integrity and test-first evidence: what `uak done` checks and `uak red` records. Bash 3.2, POSIX awk.
# Why (v5.10, test-first): agents optimize toward green. Stuck on red, an agent edits the assertion, adds a skip or
# deletes the test; a test written after the code passes by construction; a test that only checks "the mock was
# called" passes whatever the code does. A rule in prose is a suggestion, so each of these is a check here.
# The patterns reach awk through ENVIRON: -v would turn their backslashes into escape sequences.

# Test files (the same set `uak loop` protects).
TF_PROTECT='(^|/)(tests?|__tests__|spec|specs|e2e)/|(^|/)test_[^/]*$|_test\.[a-z]+$|\.(test|spec)\.[a-z]+$'
# A test definition: pytest, jest/vitest/mocha, go, JUnit, Rust.
TF_DEF='^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+test|^[[:space:]]*(it|test|describe|context)(\.each[^(]*)?[[:space:]]*\(|^[[:space:]]*func[[:space:]]+Test|@(Test|ParameterizedTest)([^A-Za-z]|$)|#\[(tokio::)?test\]|^[[:space:]]*fn[[:space:]]+test_'
TF_ASSERT='assert|expect[[:space:]]*\(|\.should|t\.(Error|Errorf|Fatal|Fatalf|Fail)|require\.|XCTAssert|refute'
# Turning a test off without deleting it.
TF_SKIP='@pytest\.mark\.(skip|xfail)|pytest\.(skip|xfail|importorskip)[[:space:]]*\(|unittest\.skip|@skip|(^|[^A-Za-z0-9_])(it|test|describe|context)\.(skip|only|todo|fixme)[[:space:]]*\(|(^|[^A-Za-z0-9_.])x(it|test|describe)[[:space:]]*\(|t\.Skip|@Disabled|@Ignore|#\[ignore\]'
# Taking tests out of the run from the runner's config.
TF_DESELECT='--deselect|--ignore[= ]|testPathIgnorePatterns|modulePathIgnorePatterns|testIgnore|norecursedirs|collect_ignore|exclude[[:space:]]*[:=].*(test|spec)'
TF_CONFIG='(^|/)(pytest\.ini|pyproject\.toml|setup\.cfg|tox\.ini|conftest\.py|package\.json|(jest|vitest|playwright|vite)\.config\.[a-z]+)$'
TF_MOCKCALL='assert_called|assert_any_call|assert_has_calls|toHaveBeenCalled|toBeCalled|verify[[:space:]]*\(|\.called[[:space:]]*(==|is)'
# A red that says nothing about behavior: the file, the module or the tests are missing, or the code does not parse.
TF_WRONG_RED='ModuleNotFoundError|ImportError|Cannot find module|Module not found|No such file or directory|command not found|SyntaxError|IndentationError|collected 0 items|no tests ran|No tests found|No test files found|ERROR: file or directory not found|is not recognized as|Failed to resolve import|undefined: |cannot find package|error\[E04(25|32|33)\]|NameError|ReferenceError: [A-Za-z_]+ is not defined'
# A red on an assertion: the behavior is wrong, which is what a new test must show.
# Not a bare "expected": Python's SyntaxError says "expected ':'".
TF_RIGHT_RED='AssertionError|assert .*(==|!=| in | is )|Expected:|expected:|Expected value|Received:|to equal|--- FAIL:|AssertionFailedError|assertion failed|FAILED [^ ]+::|XCTAssert'

# Findings of a branch against its base, one per line: "FAIL text" or "WARN text".
#   tf_findings WORKTREE RANGE TMPDIR      (RANGE: origin/main...TIP)
tf_findings() {
  local wt=$1 range=$2 tmp=$3 st f
  git -C "$wt" -c core.quotePath=false diff --no-renames --name-status "$range" 2>/dev/null > "$tmp/tf-ns" || return 0
  while IFS="$(printf '\t')" read -r st f; do
    [ -n "$f" ] || continue
    if printf '%s\n' "$f" | grep -Eq "$TF_PROTECT"; then
      case "$st" in
        D) printf 'FAIL %s: an existing test file was deleted\n' "$f"; continue;;
        A|M) ;;
        *) continue;;
      esac
      git -C "$wt" -c core.quotePath=false diff --no-renames -U0 "$range" -- "$f" 2>/dev/null |
        TF_F=$f TF_NEW=$st TF_DEF=$TF_DEF TF_ASSERT=$TF_ASSERT TF_SKIP=$TF_SKIP TF_MOCKCALL=$TF_MOCKCALL awk '
          function trim(t) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", t); return substr(t, 1, 90) }
          BEGIN { def = ENVIRON["TF_DEF"]; as = ENVIRON["TF_ASSERT"]; sk = ENVIRON["TF_SKIP"]; mc = ENVIRON["TF_MOCKCALL"] }
          /^(\+\+\+|---) / { next }
          /^-/ { s = substr($0, 2); n = s; gsub(/[[:space:]]+/, "", n); if (s ~ def || s ~ as) { nr++; rem[nr] = n; txt[nr] = s }; next }
          /^\+/ { s = substr($0, 2); n = s; gsub(/[[:space:]]+/, "", n); add[n] = 1
                  if (s ~ sk && skip == "") skip = s
                  if (s ~ as) { na++; if (s ~ mc) nm++ }
                  next }
          END {
            f = ENVIRON["TF_F"]
            # A line moved or re-indented is the same line; one edited or gone is an existing check changed.
            for (i = 1; i <= nr; i++) if (!(rem[i] in add)) { lost++; if (first == "") first = txt[i] }
            if (lost) printf "FAIL %s: %d existing test or assertion line(s) changed or removed (%s)\n", f, lost, trim(first)
            if (skip != "") printf "FAIL %s: a skip, only or todo was added (%s)\n", f, trim(skip)
            if (nm >= 2 && nm == na) printf "WARN %s: its new assertions only check that mocks were called; a Fake with state fails for the right reason (skill test-first)\n", f
          }'
    elif printf '%s\n' "$f" | grep -Eq "$TF_CONFIG"; then
      git -C "$wt" -c core.quotePath=false diff --no-renames -U0 "$range" -- "$f" 2>/dev/null |
        TF_F=$f TF_DESELECT=$TF_DESELECT awk 'BEGIN { d = ENVIRON["TF_DESELECT"] }
          /^\+\+\+ / { next }
          /^\+/ && substr($0, 2) ~ d { s = substr($0, 2); gsub(/^[[:space:]]+/, "", s); printf "FAIL %s: tests taken out of the run (%s)\n", ENVIRON["TF_F"], substr(s, 1, 90); exit }'
    fi
  done < "$tmp/tf-ns"
}

# The names a task's `Tests:` line lists that no added line of a test file contains. Names compare as words:
# "places order when stock is enough" matches places_order_when_stock_is_enough and placesOrderWhenStockIsEnough.
#   tf_missing_names WORKTREE RANGE "name, name; name"
tf_missing_names() {
  local wt=$1 range=$2 names=$3 files
  files=$(git -C "$wt" -c core.quotePath=false diff --no-renames --diff-filter=AM --name-only "$range" 2>/dev/null | grep -E "$TF_PROTECT")
  [ -n "$files" ] || { printf '%s\n' "$names" | tr ',;' '\n\n' | sed 's/^[[:space:]`]*//; s/[[:space:]`]*$//' | grep -v '^$'; return 0; }
  printf '%s\n' "$files" | while IFS= read -r f; do git -C "$wt" -c core.quotePath=false diff --no-renames -U0 "$range" -- "$f" 2>/dev/null; done |
    TF_NAMES=$names awk '
      function norm(t) { t = tolower(t); gsub(/[^a-z0-9]+/, "", t); return t }
      BEGIN { n = split(ENVIRON["TF_NAMES"], raw, /[,;]/)
              for (i = 1; i <= n; i++) { s = raw[i]; gsub(/^[[:space:]`]+|[[:space:]`]+$/, "", s); if (s != "") { k++; name[k] = s; key[k] = norm(s) } } }
      /^\+/ && !/^\+\+\+ / { body = body norm(substr($0, 2)) "\n" }
      END { for (i = 1; i <= k; i++) if (key[i] != "" && index(body, key[i]) == 0) print name[i] }'
}

# Why a red output is or is not a red: prints "right LINE", "wrong LINE" or "unknown".
tf_red_kind() {
  local log=$1 line
  # pytest prints "FAILED t.py::test_x - NameError: …": a FAILED line that names a missing name is still wrong.
  # The error line first (AssertionError: …); the `assert x == y` source line Python 3.11+ echoes only after it.
  line=$(grep -E -- "$TF_RIGHT_RED" "$log" 2>/dev/null | grep -Ev -- "$TF_WRONG_RED" | grep -Ev -m 1 '^[[:space:]]*assert ')
  [ -n "$line" ] || line=$(grep -E -- "$TF_RIGHT_RED" "$log" 2>/dev/null | grep -Ev -m 1 -- "$TF_WRONG_RED")
  if [ -n "$line" ]; then printf 'right %s\n' "$line"; return 0; fi
  line=$(grep -E -m 1 -- "$TF_WRONG_RED" "$log" 2>/dev/null)
  if [ -n "$line" ]; then printf 'wrong %s\n' "$line"; return 0; fi
  printf 'unknown\n'
}

# Which test files `smoke --affected` runs for a diff (UAK-129). The same idea as the gate's `Merge-Smoke: affected`
# (a test file that was changed or names a changed file, by `grep -F`), with a conservative rule on top: only a person or an
# agent calling smoke by hand uses it. The merge gate never passes --affected and no variable turns it on: the gate's run on
# the merged result stays the whole suite. Why (audit section 1): the suite took 8-10 min and ran three times per task.
#   tf_affected_select ROOT CHANGED TESTS
#     ROOT: the kit root (holds .uak/tests); CHANGED: a file of root-relative paths, one per line (../x is outside ROOT);
#     TESTS: a file of test file names (test_x.py), one per line.
# The floor of 3 test files does not count test_smoke_affected.py: it only lists engine file names (UAK-129 review).
# Prints TAB-separated lines: `ALL<TAB>why` (run everything, and nothing else), or `test_x.py<TAB>why` per chosen file, or
# `-<TAB>why` for a changed file no test names (a note). A shared engine file, a test helper (test_hack.py, a module another
# test imports, anything else under .uak/tests), install.sh, a file it cannot classify, or an engine file no test names and
# the small map below does not know: everything.
tf_affected_select() {
  local root=$1 changed=$2 tests=$3 tab f t base mod hits sel='' mapped cmds
  tab=$(printf '\t')
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    base=${f##*/}; hits=''
    case "$f" in
      .uak/tests/test_*.py)
        t=$base; mod=${t%.py}
        grep -qx -- "$t" "$tests" || continue   # a deleted test file has nothing to run
        if [ "$mod" = test_hack ] || (cd "$root/.uak/tests" && grep -lE -- "^[[:space:]]*(import|from)[[:space:]]+$mod([[:space:]]|[.]|,|\$)" $(grep -vx -- "$t" "$tests") 2>/dev/null | grep -q .); then
          printf 'ALL%s%s is a test helper (another test imports it)\n' "$tab" "$f"; return 0
        fi
        sel="$sel$t${tab}changed test file
"; continue;;
      .uak/tests/*) printf 'ALL%s%s is under .uak/tests and is not a test file (a helper or data)\n' "$tab" "$f"; return 0;;
      .uak/bin/lib/core.sh|.uak/bin/lib/tx.sh|.uak/bin/lib/cache.sh|.uak/bin/uak|.uak/bin/uak-coordination|install.sh|../install.sh)
        printf 'ALL%s%s is shared by every command\n' "$tab" "$f"; return 0;;
      .uak/bin/lib/*)
        # A library is tested through the commands that use it, not through its own file name (review of UAK-129: lib/claim.sh
        # selected 1 of 115 test files and test_coordination, which runs `claim`, was missed). The commands come from the
        # engine itself: the rows of commands.tsv that name the file, and the scripts in .uak/bin that mention it (one hop
        # through a python module for lib/*.py). A shell or awk library no row names is shared plumbing: everything.
        cmds=$(tf_lib_commands "$root" "$base")
        case "$base" in
          *.py|*.html) [ -n "$cmds" ] || { printf 'ALL%s%s is a library no command is known to use\n' "$tab" "$f"; return 0; };;
          *) if ! awk -F'\t' -v f="$base" '$1 !~ /^#/ && $4 == f { n++ } END { exit n ? 0 : 1 }' "$root/.uak/bin/lib/commands.tsv" 2>/dev/null; then
               printf 'ALL%s%s is shared plumbing: no command of commands.tsv is implemented in it\n' "$tab" "$f"; return 0; fi;;
        esac
        mapped=''
        case "$base" in
          review-merge.sh) mapped='test_review_merge.py test_merge_affected.py';;
          smoke-init.sh) mapped='test_smoke_env.py';;
        esac
        for t in $mapped; do grep -qx -- "$t" "$tests" && hits="$hits $t"; done
        hits="$hits $(tf_command_tests "$root" "$tests" $cmds) $(cd "$root/.uak/tests" && grep -lF -e "$base" $(cat "$tests") 2>/dev/null | tr '\n' ' ')"
        hits=$(printf '%s\n' $hits | LC_ALL=C sort -u)
        if [ "$(printf '%s\n' $hits | grep -v '^test_smoke_affected.py$' | grep -c .)" -lt 3 ]; then
          printf 'ALL%s%s: fewer than 3 test files run its commands (%s), too few to trust\n' "$tab" "$f" "$(printf '%s' "$cmds" | tr '\n' ' ' | sed 's/ $//')"; return 0; fi
        sel="$sel$(printf '%s\n' $hits | sed "s/\$/${tab}runs its commands ($(printf '%s' "$cmds" | tr '\n' ' ' | sed 's/ $//'))/")
"; continue;;
      .uak/bin/*)
        hits=$(cd "$root/.uak/tests" && { grep -lF -e "bin/$base" $(cat "$tests") 2>/dev/null; [ "${#base}" -lt 5 ] || grep -lF -e "$base" $(cat "$tests") 2>/dev/null; } | LC_ALL=C sort -u)
        if [ "$(printf '%s\n' $hits | grep -v '^test_smoke_affected.py$' | grep -c .)" -lt 3 ]; then   # too few: widen with the tests that run it as a command
          hits=$(printf '%s\n%s\n' "$hits" "$(tf_command_tests "$root" "$tests" "$base")" | grep . | LC_ALL=C sort -u)
        fi
        if [ "$(printf '%s\n' $hits | grep -v '^test_smoke_affected.py$' | grep -c .)" -lt 3 ]; then printf 'ALL%s%s is an engine file fewer than 3 test files name or run\n' "$tab" "$f"; return 0; fi;;
      .uak/docs/*|.uak/modes/*|.uak/templates/*|.uak/skills/*|.uak/stacks/*|.uak/settings/*|.claude/*|.codex/*|.cursor/*|.gemini/*|.github/*|.githooks/*|docs/*|scripts/*|*.md|\
../docs/*|../scripts/*|../skills/*|../.claude-plugin/*|../.github/*|../llms.txt|../*.md)
        hits=$(cd "$root/.uak/tests" && grep -lF -e "$base" $(cat "$tests") 2>/dev/null | LC_ALL=C sort -u)
        if [ -z "$hits" ]; then sel="$sel-${tab}$f: no test file names it
"; continue; fi;;
      *) printf 'ALL%s%s: the kit cannot classify it\n' "$tab" "$f"; return 0;;
    esac
    for t in $hits; do sel="$sel$t${tab}names $f
"; done
  done < "$changed"
  printf '%s' "$sel" | LC_ALL=C sort -t "$tab" -u -k1,1
}

# The commands a library file takes part in: the rows of commands.tsv whose file column is it, and the scripts of .uak/bin
# (not the dispatcher uak, nor uak-coordination, which source every library) that mention it, one hop through the python
# modules of lib/ that mention it (design_color.py is reached through design_round.py). One command name per line.
#   tf_lib_commands ROOT FILE
tf_lib_commands() {
  local root=$1 file=$2 seen=" $2 " add m g round names stem
  for round in 1 2; do
    add=''
    for m in $seen; do
      case "$m" in *.py|*.html) ;; *) continue;; esac
      stem=${m%.*}; [ "${#stem}" -ge 6 ] || stem=$m   # a python module is imported by its stem
      for g in $(cd "$root/.uak/bin/lib" && grep -lF -e "$m" -e "$stem" *.py 2>/dev/null); do
        [ "$g" != "$m" ] || continue
        case "$seen" in *" $g "*) ;; *) add="$add $g";; esac
      done
    done
    seen="$seen$add "
  done
  names=$(for m in $seen; do
    awk -F'\t' -v f="$m" '$1 !~ /^#/ && $4 == f { print $1 }' "$root/.uak/bin/lib/commands.tsv" 2>/dev/null
    for g in $(cd "$root/.uak/bin" && grep -slF -e "$m" * 2>/dev/null); do
      [ -f "$root/.uak/bin/$g" ] || continue
      if [ "$g" != uak ] && [ "$g" != uak-coordination ] && [ "$g" != smoke ]; then printf '%s\n' "$g"; fi
    done
  done | LC_ALL=C sort -u)
  printf '%s\n' "$names" | grep .
  return 0
}

# The test files that run a command: its name as a quoted argument (`"claim"`, 'claim'), after `uak ` or as `bin/NAME`.
# A short or common name matches many tests: wider is the safe side.
#   tf_command_tests ROOT TESTS NAME...      prints test file names, one per line
tf_command_tests() {
  local root=$1 tests=$2 n; shift 2
  for n in "$@"; do
    (cd "$root/.uak/tests" && grep -lF -e "\"$n\"" -e "'$n'" -e "uak $n" -e "bin/$n" $(cat "$tests") 2>/dev/null)
  done | LC_ALL=C sort -u
}
