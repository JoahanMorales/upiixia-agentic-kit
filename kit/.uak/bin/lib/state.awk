# The claims state in one pass: every "Key: value" line of the records on claims, as shell assignments.
#   eval "$(awk -v backlog=FILE -f state.awk TX/tasks/*.md TX/claims/*.md TX/reviews/*.md TX/queue/*.md ...)"
# Only task IDs (ABC-123) load: one dash, so a name never collides (HACK-001-Lease + Until is not HACK-001 + Lease-Until).
# A record TX/<kind>/<ID>.md (kind: tasks, claims, reviews, queue; reviews/<ID>.reviewing is kind "reviewing")
# gives UAK_S_<kind>_<ID>_<Key>='value' (dashes become underscores) for the first line of each key, the same line
# `field` reads; UAK_S_<kind> lists the IDs in argument order. The backlog file (-v backlog) gives UAK_S_backlog:
# the IDs of its "## ID" headings, repeats included. UAK_S_VARS names every variable, for the next load to unset.
# Why (UAK-003): `status` and `next` read each field in its own subshell, `$(field FILE Key)`: about 100 of the
# 210 processes of a `next`, at 20-50 ms each on Git Bash. Values are single-quoted: nothing in a record runs.
# A CRLF record (written on Windows) reads like LF. Portable awk: gawk, mawk, BSD awk.
function q(s,   out, i) {
  out = ""
  while ((i = index(s, "'")) > 0) { out = out substr(s, 1, i - 1) "'\\''"; s = substr(s, i + 1) }
  return "'" out s "'"
}
function var(s) { gsub(/-/, "_", s); return s }
function add(name, value) { if (!(name in val)) { order[++n] = name }; val[name] = value }
FNR == 1 {
  kind = ""; id = ""; split("", seen)
  if (backlog != "" && FILENAME == backlog) { kind = "backlog" }
  else {
    m = split(FILENAME, p, "/"); b = p[m]; d = (m > 1 ? p[m - 1] : "")
    if (b ~ /\.reviewing$/ && d == "reviews") { kind = "reviewing"; sub(/\.reviewing$/, "", b) }
    else if (b ~ /\.md$/ && (d == "tasks" || d == "claims" || d == "reviews" || d == "queue")) { kind = d; sub(/\.md$/, "", b) }
    if (kind != "" && b ~ /^[A-Z][A-Z0-9]*-[0-9]+$/) { id = b; ids[kind] = ids[kind] (ids[kind] == "" ? "" : " ") id }
    else kind = ""
  }
}
kind == "backlog" {
  if ($0 ~ /^## [A-Z][A-Z0-9]*-[0-9]/) ids["backlog"] = ids["backlog"] (ids["backlog"] == "" ? "" : " ") $2
  next
}
kind != "" {
  l = $0; sub(/\r$/, "", l)
  if (match(l, /^[A-Za-z][A-Za-z0-9-]*: /)) {
    k = substr(l, 1, RLENGTH - 2)
    if (!(k in seen)) { seen[k] = 1; add(var("UAK_S_" kind "_" id "_" k), substr(l, RLENGTH + 1)) }
  }
}
END {
  split("tasks claims reviews queue reviewing backlog", kinds, " ")
  for (i = 1; i <= 6; i++) add("UAK_S_" kinds[i], ids[kinds[i]])
  names = ""
  for (i = 1; i <= n; i++) { print order[i] "=" q(val[order[i]]); names = names (i > 1 ? " " : "") order[i] }
  print "UAK_S_VARS=" q(names)
}
