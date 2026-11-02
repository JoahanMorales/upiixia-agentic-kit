# `uak --json CMD …`: the same command run as a child, its result as one JSON object on stdout. The text output stays
# the contract for agents; this is for programs (dashboards, CI, other tools) that should not parse prose.
# Why (v5.11, architecture review): the MCP server, the hooks and the dashboard each parsed uak's lines on their own.
#   {"v":1, "cmd":…, "id":…, "ok":true|false, "exit":N, "result":"OK|CONFLICT|ERROR|GIT_ERROR|RED_OK|APPROVED|…",
#    "code":"…", "message":…, "state":…, "next":…, "stdout":[…], "stderr":[…], "tasks":[…] (status only)}
# code: the short stable code of a refusal (CLI.md, Result codes), else the result in lower case.
json_run() {
  local d rc
  d=$(mktemp -d "${TMPDIR:-/tmp}/uak-json.XXXXXX") || { printf '{"v":1,"ok":false,"exit":1,"result":"GIT_ERROR","code":"temp-dir"}\n'; return 1; }
  : > "$d/meta"; : > "$d/data"
  UAK_JSON= UAK_JSON_META="$d/meta" UAK_JSON_DATA="$d/data" bash "$UAK_BIN/uak" "$@" > "$d/out" 2> "$d/err" < /dev/null
  rc=$?
  { printf 'cmd\t%s\n' "${1:-help}"; printf 'exit\t%s\n' "$rc"; } >> "$d/meta"
  awk -v meta="$d/meta" -v data="$d/data" -v out="$d/out" -v err="$d/err" '
    # Character by character: a backslash in a gsub replacement means different things in mawk, gawk and BSD awk.
    function esc(s,   o, i, c, n) {
      gsub(/\r/, "", s)
      if (s !~ /[\\"\001-\037]/) return s
      o = ""; n = length(s)
      for (i = 1; i <= n; i++) {
        c = substr(s, i, 1)
        if (c == "\\") o = o "\\\\"; else if (c == "\"") o = o "\\\""; else if (c == "\t") o = o "\\t"
        else if (c ~ /[\001-\037]/) o = o sprintf("\\u%04x", ord[c]); else o = o c
      }
      return o }
    function arr(file,   l, s, sep) { s = "["; sep = ""; while ((getline l < file) > 0) { s = s sep "\"" esc(l) "\""; sep = "," }; close(file); return s "]" }
    function str(v) { return (v == "" ? "null" : "\"" esc(v) "\"") }
    BEGIN {
      for (i = 1; i < 32; i++) ord[sprintf("%c", i)] = i
      while ((getline l < meta) > 0) { k = l; sub(/\t.*/, "", k); v = substr(l, length(k) + 2); m[k] = v }
      rc = m["exit"] + 0
      # The result: a refusal on stderr, else the last result line on stdout (wait prints WAITING, then APPROVED).
      tok = "^(OK|CONFLICT|ERROR|GIT_ERROR|RED_OK|RED_WRONG|RED_PASSED|APPROVED|REJECTED|INTEGRATED|WAIT_TIMEOUT|MERGE_WAIT|MERGE_BUSY|MERGED|SKIP|LINT_OK|LINT_FAILED|PACE|START)([ :]|$)"
      while ((getline l < err) > 0) if (res == "" && l ~ /^(CONFLICT|ERROR|GIT_ERROR):/) { res = l; ecls = l }
      close(err)
      while ((getline l < out) > 0) { if (l ~ tok && ecls == "") res = l; if (l ~ /^Next: /) nx = substr(l, 7) }
      close(out)
      r = res; sub(/[ :].*/, "", r)
      if (r == "") r = (rc == 0 ? "OK" : "ERROR")
      code = (rc != 0 && m["code"] != "") ? m["code"] : tolower(r)
      gsub(/_/, "-", code)
      msg = res; sub(/^[A-Z_]+:? */, "", msg)
      printf "{\"v\":1,\"cmd\":%s,\"id\":%s,\"ok\":%s,\"exit\":%d,\"result\":%s,\"code\":%s,\"message\":%s,\"state\":%s,\"next\":%s,\"stdout\":%s,\"stderr\":%s",
        str(m["cmd"]), str(m["id"]), (rc == 0 ? "true" : "false"), rc, str(r), str(code), str(msg), str(m["state"]), str(nx), arr(out), arr(err)
      n = 0; t = "["
      while ((getline l < data) > 0) {
        split(l, f, "\t"); if (f[1] != "task") continue
        t = t (n++ ? "," : "") sprintf("{\"id\":%s,\"state\":%s,\"owner\":%s,\"lease_until\":%d,\"expired\":%s}", str(f[2]), str(f[3]), str(f[4] == "-" ? "" : f[4]), f[5] + 0, (f[6] == "yes" ? "true" : "false"))
      }
      if (n || m["data"] == "tasks") printf ",\"tasks\":%s]", t
      printf "}\n"
    }'
  rm -rf "$d"
  return "$rc"
}
