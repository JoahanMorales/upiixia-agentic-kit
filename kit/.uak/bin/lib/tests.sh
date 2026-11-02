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
