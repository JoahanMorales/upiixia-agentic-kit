# Which Node engines a project does not satisfy. Used by doctor:
#   awk -v node=20.16.0 -f engines.awk web/package.json web/package-lock.json
# prints "NAME<TAB>RANGE" for the package itself and each direct dependency whose engines.node excludes this Node.
# Why (Windows audit of HackADA, Oct 2026): Node 20.16 under Vite 8's "^20.19.0 || >=22.12.0"; npm only warned
# (EBADENGINE), skipped the native @rolldown/binding-win32-x64-msvc, and the build failed with "Cannot find module".
# POSIX awk (BSD awk on macOS, mawk on Linux): no gensub, no match() arrays. JSON as npm writes it: one key per line.
function vn(a1, a2, a3) { return (a1 + 0) * 1000000 + (a2 + 0) * 1000 + (a3 + 0) }
function sat1(c, v,   op, ver, a, n, i, given, lo, hi, bump) {
  if (c == "" || c ~ /^[*xX]$/) return 1
  op = c; sub(/[0-9].*$/, "", op); ver = substr(c, length(op) + 1); sub(/^v/, "", op)
  n = split(ver, a, "."); given = 0
  for (i = 1; i <= 3 && i <= n; i++) { if (a[i] !~ /^[0-9]+$/) break; given = i }
  if (given == 0) return 1
  lo = vn(a[1], given >= 2 ? a[2] : 0, given >= 3 ? a[3] : 0)
  # the first version past the given precision: 20 -> 21.0.0, 20.19 -> 20.20.0, 20.19.0 -> 20.19.1
  bump = given == 1 ? vn(a[1] + 1, 0, 0) : given == 2 ? vn(a[1], a[2] + 1, 0) : lo + 1
  if (op == "^") {
    hi = a[1] > 0 || given == 1 ? vn(a[1] + 1, 0, 0) : vn(0, a[2] + 1, 0)
    return v >= lo && v < hi
  }
  if (op == "~") { hi = given >= 2 ? vn(a[1], a[2] + 1, 0) : vn(a[1] + 1, 0, 0); return v >= lo && v < hi }
  if (op == ">=") return v >= lo
  if (op == ">") return v >= bump
  if (op == "<=") return v < bump
  if (op == "<") return v < lo
  return v >= lo && v < bump
}
function sat(r, v,   alts, na, i, s, cs, nc, j, ok) {
  na = split(r, alts, /\|\|/)
  for (i = 1; i <= na; i++) {
    s = alts[i]; gsub(/^ +| +$/, "", s)
    if (s ~ / - /) { sub(/ - /, " <=", s); s = ">=" s }
    while (match(s, /[<>=^~] +/)) s = substr(s, 1, RSTART) substr(s, RSTART + RLENGTH)
    nc = split(s, cs, / +/); ok = 1
    for (j = 1; j <= nc; j++) if (!sat1(cs[j], v)) { ok = 0; break }
    if (ok) return 1
  }
  return 0
}
function q(line, k,   p) { split(line, p, "\""); return p[k] }
BEGIN { split(node, nv, "."); v = vn(nv[1], nv[2], nv[3]) }
FNR == 1 { f++; block = "" }
f == 1 {
  if ($0 ~ /^  "(dependencies|devDependencies)": *\{/) { block = "deps"; next }
  if ($0 ~ /^  "engines": *\{/) { block = "engines"; if ($0 ~ /"node"/) { split($0, e, "\"node\""); own = q(e[2], 2) }; next }
  if ($0 ~ /^  [}\]]/) { block = ""; next }
  if (block == "deps" && $0 ~ /^    "/) deps[q($0, 2)] = 1
  if (block == "engines" && $0 ~ /^    "node"/) own = q($0, 4)
  next
}
f == 2 {
  if ($0 ~ /^    "node_modules\/[^"]*": *\{/) { cur = q($0, 2); sub(/^node_modules\//, "", cur); if (cur ~ /\/node_modules\//) cur = ""; next }
  if (cur != "" && $0 ~ /^      "engines": *\{/) {
    if ($0 ~ /"node"/) { split($0, e, "\"node\""); eng[cur] = q(e[2], 2) } else block = "engines"
    next
  }
  if (block == "engines") { if ($0 ~ /"node"/) eng[cur] = q($0, 4); if ($0 ~ /\}/) block = ""; next }
  if ($0 ~ /^    \}/) cur = ""
}
END {
  if (own != "" && !sat(own, v)) print "the project\t" own
  for (d in deps) if ((d in eng) && eng[d] != "" && !sat(eng[d], v)) print d "\t" eng[d]
}
