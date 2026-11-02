# The one reader of "Key: value" lines in .uak/PROJECT.md (and any file written the same way). Bash 3.2, builtins
# only: no process, so guard and hook, which run on every tool call of every agent, use it too (Windows pays 20-50 ms
# per process). Bold, list bullets, backticks, CRLF and trailing spaces are tolerated: "- **Freeze-Epoch:** `0`" is 0.
# Why (v5.11, architecture review): 13 copies of this reader in 10 scripts disagreed on spaces, backticks and which
# file they read; kit_lint now refuses a new copy.
#   uak_cfg_var FILE KEY [DEFAULT]   the first value of KEY into CFG (DEFAULT when absent or empty); FILE - is stdin
#   uak_cfg FILE KEY [DEFAULT]       the same, printed
uak_cfg_scan() { # KEY: reads stdin
  local line v
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line#"${line%%[!-* ]*}"}
    case "$line" in "$1:"*) ;; *) continue;; esac
    v=${line#"$1:"}; v=${v#"${v%%[!* ]*}"}
    v=${v//$'\r'/}; v=${v//\`/}
    CFG=${v%"${v##*[! ]}"}
    return 0
  done
}
uak_cfg_var() {
  CFG=
  if [ "$1" = - ]; then uak_cfg_scan "$2"
  elif [ -f "$1" ]; then uak_cfg_scan "$2" < "$1"; fi
  [ -n "$CFG" ] || CFG=${3:-}
}
uak_cfg() { uak_cfg_var "$@"; printf '%s\n' "$CFG"; }
