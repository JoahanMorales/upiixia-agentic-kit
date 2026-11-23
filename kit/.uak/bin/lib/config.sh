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
# Shared resources of the human, one list for the merge gate (rm_gate_scope) and for `uak done`: each is a "*/name/*"
# pattern matched against "/lower-case/path/". Moved here from the gate's awk (UAK-148) so `Generated:` can never release
# one of them in one place and not in the other.
UAK_SHARED_RES='/contracts/ /types/ /shared-types/ /migrations/ /db/migration/ /gradle.lockfile/ /.github/workflows/ /.gitlab-ci.yml/ /azure-pipelines.yml/ /package-lock.json/ /pnpm-lock.yaml/ .lock/ .lockb/ /go.sum/ /.uak/bin/smoke/ /.uak/bin/smoke-project/ /.uak/bin/.smoke-project.provenance/ /.uak/bin/secret-scan/ /.uak/bin/uak/ /.uak/bin/lib/ /.uak/bin/uak-coordination/ /.githooks/ /hackathon.md/ /.uak/project.md/'
# Generated files (UAK-148). `Generated: PATH = COMMAND` lines of the PROJECT.md given on stdin, one "PATH<TAB>COMMAND"
# per valid line. The first `=` splits (the command may hold more); PATH is one file, never a directory or a glob
# (no trailing slash, no * ? [ ] { } or backslash, no `..`, not absolute); an empty PATH or COMMAND drops the line.
# Wrapping backticks are removed from each side. Callers read the BASE tip's PROJECT.md, never the branch under review.
# Why (v6.8, 21 tasks): every task's PR changed known-files.txt and was sent to the human for it.
uak_generated_list() {
  local line v p c
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line#"${line%%[!-* ]*}"}
    case "$line" in 'Generated:'*) ;; *) continue;; esac
    v=${line#Generated:}; v=${v//$'\r'/}
    case "$v" in *=*) ;; *) continue;; esac
    p=${v%%=*}; c=${v#*=}
    p=${p#"${p%%[!* ]*}"}; p=${p%"${p##*[! ]}"}; c=${c#"${c%%[! ]*}"}; c=${c%"${c##*[! ]}"}
    case "$p" in '`'*'`') p=${p#\`}; p=${p%\`};; esac
    case "$c" in '`'*'`') c=${c#\`}; c=${c%\`};; esac
    while :; do case "$p" in ./*) p=${p#./};; *) break;; esac; done
    [ -n "$p" ] && [ -n "$c" ] || continue
    case "$p" in /*|*/|*'*'*|*'?'*|*'['*|*']'*|*'{'*|*'}'*|*'\'*|*$'\t'*|..|../*|*/..|*/../*|*//*|[A-Za-z]:*) continue;; esac
    printf '%s\t%s\n' "$p" "$c"
  done
}
