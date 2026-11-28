# Spelling hints (UAK-091): what a wrong command or argument should have been. Sourced by uak; only the text of an error
# gains words, the first words, exit codes and UAK_CODE stay as they were (messages are an API). Bash 3.2.
unknown_hint() {
  case "$CMD" in
    owners) printf ' Owners are in the file .uak/OWNERS.md (uak lint checks them).'; return;;
    agents) printf ' Who holds what: bash .uak/bin/uak status (claims and identities); the team on one page: bash .uak/bin/uak dash.'; return;;
    kit-hashes|kit_hashes) printf ' That is a script of the kit repository: python3 scripts/kit_hashes.py.'; return;;
  esac
  awk -F'\t' -v c="$CMD" '
    function lev(a, b,   i, j, la, lb, d, x, y, z) {
      la = length(a); lb = length(b)
      for (i = 0; i <= la; i++) d[i, 0] = i
      for (j = 0; j <= lb; j++) d[0, j] = j
      for (i = 1; i <= la; i++) for (j = 1; j <= lb; j++) {
        x = d[i-1, j] + 1; y = d[i, j-1] + 1; z = d[i-1, j-1] + (substr(a, i, 1) != substr(b, j, 1))
        if (y < x) x = y; if (z < x) x = z; d[i, j] = x }
      return d[la, lb] }
    /^#/ || $1 == "" { next }
    { n = lev(c, $1); if (length($1) >= 3 && length(c) >= 3 && (index(c, $1) == 1 || index($1, c) == 1)) n = 1
      if (n < best || best == "") { best = n; name = $1 } }
    END { if (name != "" && best <= 2) printf " Did you mean: %s", name }' "$UAK_BIN/lib/commands.tsv" 2>/dev/null
}
unexpected_arg() { # a word where a flag or nothing goes: the base message, then the spelling that works
  local hint= v=
  case "$CMD:$opt" in
    review:--approve|review:--reject) v=${opt#--}; [ "$v" != reject ] || v="reject --cause CAUSE"; hint=" The verdict is a flag value: bash .uak/bin/uak review ${ID:-ID} --sha SHA --verdict $v";;
    review:*|status:*)
      case "$opt" in *[!0-9a-f]*|'') ;; *) if [ "${#opt}" -ge 7 ] && [ "${#opt}" -le 40 ]; then
        if [ "$CMD" = review ]; then hint=" A SHA needs its flag: bash .uak/bin/uak review ${ID:-ID} --sha $opt --verdict approve|reject"
        else hint=" status takes no SHA; a verdict names its SHA with a flag: bash .uak/bin/uak review ${ID:-ID} --sha $opt --verdict approve|reject"; fi; fi;; esac;;
    merge:*) hint=" merge takes only the task ID (bash .uak/bin/uak merge ${ID:-ID}); a reviewer name goes to done: --reviewer $opt";;
  esac
  die "Unexpected argument: $opt (quote multi-word values: --flag \"two words\").$hint"
}
# UAK-203: a generated file among the conflicts of a task the gate sent to the human anyway: the three commands that
# resolve it on the branch (merge the base, run the base's COMMAND, commit). $1: lines "PATH<TAB>COMMAND".
generated_conflict_hint() {
  local line
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    say "HUMAN: ${line%%$'\t'*} is generated and conflicts with $BASE: git fetch origin && git merge --no-edit origin/$BASE; ${line#*$'\t'}; git add ${line%%$'\t'*} && git commit --no-edit"
  done <<EOF2
$1
EOF2
}
