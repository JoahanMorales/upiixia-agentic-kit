# Adapter compiled from the user's explicit command, or from the detected web app; Bash 3.2+.
# Why (QA round C, UAK-093): the hand-made smoke ran only unit tests that forced a fake store, so two green merges
# integrated an app that crashed on boot (ImportError). A web app's smoke boots it and requests one route.

# The boot check for the web app `uak deploy` detects (read-only: deploy without --write writes nothing), or nothing.
smoke_detect() {
  local out stack run path entry
  out=$(cd "$ROOT" && bash .uak/bin/deploy 2>/dev/null | tr -d '\r') || return 1
  stack=$(printf '%s\n' "$out" | sed -n 's/^DEPLOY \([a-z][a-z-]*\) · target .*/\1/p' | head -n 1)
  path=$(printf '%s\n' "$out" | sed -n 's/^DEPLOY .* · health \(\/[^ ]*\)$/\1/p' | head -n 1)
  case "$stack" in
    python-stdlib) run=$(printf '%s\n' "$out" | sed -n 's/^DEPLOY start: \(.*\) (from .*)$/\1/p' | head -n 1)
      entry=$(printf '%s\n' "$out" | sed -n 's/^DEPLOY start: .* (from \(.*\))$/\1/p' | head -n 1)
      # No health route: the route the Render Blueprint checks, else the first quoted "/api/..." the server names.
      [ -n "$path" ] || path=$(sed -n 's/^ *healthCheckPath: *\(\/[^ ]*\).*/\1/p' "$ROOT/render.yaml" 2>/dev/null | tr -d '\r' | head -n 1)
      [ -n "$path" ] || [ -z "$entry" ] ||
        path=$(grep -oE "[\"'](/api/[A-Za-z0-9_./-]*)[\"']" "$ROOT/$entry" 2>/dev/null | head -n 1 | tr -d "\"'");;
    fastapi|fastapi-react) run='uv run uvicorn app.main:app --host 127.0.0.1 --port $PORT';;
    django) run='uv run python manage.py runserver 127.0.0.1:$PORT --noreload';;
    nextjs) run='npm run dev -- --port $PORT';;
    vite) run='npm run dev -- --port $PORT --strictPort';;
    *) return 1;;
  esac
  [ -n "$run" ] || return 1
  case "$path" in /*) ;; *) path=/;; esac
  printf "bash .uak/bin/lib/smoke-init.sh boot --path %s -- '%s'\n" "$path" "$run"
}
# The init-smoke line `uak start` shows: the exact one for a detected web app, else a template to fill in.
smoke_suggest() {
  local cmd
  if cmd=$(smoke_detect) && [ -n "$cmd" ]; then
    printf 'bash .uak/bin/uak init-smoke --command "%s"\n' "$(printf '%s' "$cmd" | sed 's/\$/\\$/g')"
  else
    printf '%s\n' "bash .uak/bin/uak init-smoke --command \"bash .uak/bin/lib/smoke-init.sh boot --path /ROUTE -- 'COMMAND THAT STARTS THE APP ON \\\$PORT'\""
  fi
}
init_smoke() {
  local adapter provenance hash command_hash result
  if [ -z "${SMOKE_COMMAND:-}" ]; then
    SMOKE_COMMAND=$(smoke_detect) || SMOKE_COMMAND=
    [ -n "$SMOKE_COMMAND" ] || die "init-smoke found no web app to boot (uak deploy names the stacks it knows); pass the real product check: $(smoke_suggest)"
    printf 'SMOKE_DETECTED: %s\n' "$SMOKE_COMMAND"
  fi
  adapter="$ROOT/.uak/bin/smoke-project"
  provenance="$ROOT/.uak/bin/.smoke-project.provenance"
  if [ -e "$adapter" ] && ! grep -Fqx '# UAK_PRODUCT_ADAPTER: generated-v2.1' "$adapter"; then
    die "a manual .uak/bin/smoke-project already exists; review it and remove it to regenerate."
  fi
  printf '%s\n' '#!/usr/bin/env bash' '# UAK_PRODUCT_ADAPTER: generated-v2.1' 'set -u' 'set -o pipefail' > "$adapter" || return 2
  printf '%s\n' 'root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)' 'cd "$root" || exit 2' >> "$adapter"
  printf 'exec bash -c %q\n' "$SMOKE_COMMAND" >> "$adapter"
  chmod +x "$adapter" || return 2
  hash=$(git -C "$ROOT" hash-object "$adapter") || return 2
  command_hash=$(printf '%s' "$SMOKE_COMMAND" | git -C "$ROOT" hash-object --stdin) || return 2
  printf 'Adapter-Blob: %s\nCommand-Blob: %s\nGenerated-By: %s\nCreated-At: %s\nProduct-Result: UNVERIFIED\n' "$hash" "$command_hash" "${AGENT:-user-command}" "${NOW:-$(date +%s)}" > "$provenance"
  bash "$adapter"
  result=$?
  if [ "$result" -ne 0 ]; then
    printf 'PRODUCT_UNVERIFIED: supplied command exited %s.\n' "$result" >&2
    return "$result"
  fi
  printf 'Adapter-Blob: %s\nCommand-Blob: %s\nGenerated-By: %s\nCreated-At: %s\nProduct-Result: PASS\n' "$hash" "$command_hash" "${AGENT:-user-command}" "${NOW:-$(date +%s)}" > "$provenance"
  printf '%s\n' 'SMOKE_ADAPTER_CREATED: supplied command exited 0; the gate will run it again.'
}
product_gate() {
  local adapter provenance expected actual result
  adapter="$ROOT/.uak/bin/smoke-project"
  provenance="$ROOT/.uak/bin/.smoke-project.provenance"
  if [ ! -f "$adapter" ]; then
    printf '%s\n' 'PRODUCT_UNVERIFIED: missing .uak/bin/smoke-project; exit 2.' >&2; return 2
  fi
  if ! grep -Fqx '# UAK_PRODUCT_ADAPTER: generated-v2.1' "$adapter" || [ ! -f "$provenance" ]; then
    printf '%s\n' 'PRODUCT_UNVERIFIED: adapter without init-smoke provenance; exit 2.' >&2; return 2
  fi
  expected=$(sed -n 's/^Adapter-Blob: //p' "$provenance" | head -n 1)
  actual=$(git -C "$ROOT" hash-object "$adapter" 2>/dev/null) || return 2
  if [ -z "$expected" ] || [ "$expected" != "$actual" ] || ! grep -Fqx 'Product-Result: PASS' "$provenance"; then
    printf '%s\n' 'PRODUCT_UNVERIFIED: adapter modified or initial command unvalidated; exit 2.' >&2; return 2
  fi
  bash "$adapter"
  result=$?
  if [ "$result" -ne 0 ]; then printf 'PRODUCT_FAIL: adapter exit=%s\n' "$result" >&2; return "$result"; fi
  printf '%s\n' 'PRODUCT_PASS: current adapter exited 0.'
}
# boot [--path ROUTE] [--timeout SECONDS] -- COMMAND: start the app on $PORT (UAK_PORT when the merge gate gives one,
# else a free one), request ROUTE until it answers below 500 or the timeout, then stop the whole process tree.
# Exit 0 = it answered; 1 = it exited, answered 5xx or never answered. The app's output is shown on failure.
smoke_windows() { case "$(uname -s 2>/dev/null)" in MINGW*|MSYS*|CYGWIN*) return 0;; esac; return 1; }
smoke_probe() { # print the HTTP status of URL, 000 when nothing answers
  if command -v curl >/dev/null 2>&1; then
    curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null || :
  else
    "$SMOKE_PY" -c 'import sys, urllib.request, urllib.error
try: print(urllib.request.urlopen(sys.argv[1], timeout=3).status)
except urllib.error.HTTPError as e: print(e.code)
except Exception: print("000")' "$1" 2>/dev/null || printf '000'
  fi
}
smoke_stop() { # the process tree of $1: taskkill /T on Git Bash, the process group (set -m) elsewhere
  local pid=$1 win
  kill -0 "$pid" 2>/dev/null || return 0
  if smoke_windows; then
    win=$(cat "/proc/$pid/winpid" 2>/dev/null)
    MSYS_NO_PATHCONV=1 taskkill /F /T /PID "${win:-$pid}" >/dev/null 2>&1 || kill "$pid" 2>/dev/null
  else
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    sleep 1
    kill -KILL -- "-$pid" 2>/dev/null || :
  fi
  { wait "$pid"; } 2>/dev/null || :
}
smoke_boot() {
  local path=/ timeout=30 port code pid log i end rc=1 cmd
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --path) path=${2:-/}; shift 2 2>/dev/null || shift;;
      --timeout) timeout=${2:-30}; shift 2 2>/dev/null || shift;;
      --) shift; break;;
      *) break;;
    esac
  done
  case "$timeout" in ''|*[!0-9]*) timeout=30;; esac
  case "$path" in /*) ;; *) path=/$path;; esac
  [ "$#" -gt 0 ] || { printf '%s\n' 'Usage: smoke-init.sh boot [--path ROUTE] [--timeout SECONDS] -- COMMAND' >&2; return 2; }
  cmd=$*
  SMOKE_PY=python3; "$SMOKE_PY" -c 'import sys' >/dev/null 2>&1 || SMOKE_PY=python
  # A python3 that does not run (Windows has only `python`, or the Store stub): the command's python3 is python.
  [ "$SMOKE_PY" = python3 ] || cmd="python3() { python \"\$@\"; }; $cmd"
  port=${UAK_PORT:-}
  case "$port" in ''|*[!0-9]*)
    port=
    for i in 1 2 3 4 5 6 7 8; do
      port=$(( 20000 + ($$ * 7 + i * 1009 + RANDOM) % 20000 ))
      [ "$(smoke_probe "http://127.0.0.1:$port/")" = 000 ] && break
    done;;
  esac
  log=$(mktemp "${TMPDIR:-/tmp}/uak-boot.XXXXXX") || return 2
  set -m   # its own process group, so the stop reaches npm's node or a shell's child too
  PORT=$port bash -c "$cmd" > "$log" 2>&1 < /dev/null &
  pid=$!
  set +m
  end=$(( SECONDS + timeout )) code=000
  while [ "$SECONDS" -lt "$end" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      printf 'BOOT_FAIL: the app exited before answering %s (port %s). Its output:\n' "$path" "$port" >&2
      tail -n 30 "$log" >&2; rm -f "$log"; { wait "$pid"; } 2>/dev/null; return 1
    fi
    code=$(smoke_probe "http://127.0.0.1:$port$path")
    case "$code" in [1-4][0-9][0-9]) rc=0; break;; [5][0-9][0-9]) break;; esac
    sleep 1
  done
  smoke_stop "$pid" 2>/dev/null   # also the shell's "Terminated" job notice
  if [ "$rc" -eq 0 ]; then printf 'BOOT_PASS: %s answered %s on port %s.\n' "$path" "$code" "$port"
  elif [ "$code" = 000 ]; then printf 'BOOT_FAIL: no answer from %s on port %s within %ss. Its output:\n' "$path" "$port" "$timeout" >&2; tail -n 30 "$log" >&2
  else printf 'BOOT_FAIL: %s answered %s. Its output:\n' "$path" "$code" >&2; tail -n 30 "$log" >&2; fi
  rm -f "$log"
  return "$rc"
}
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd) || exit 2
  case "${1:-}" in
    gate) product_gate; exit "$?";;
    boot) shift; smoke_boot "$@"; exit "$?";;
    suggest) smoke_suggest; exit 0;;
    detect) smoke_detect; exit "$?";;
    *) printf '%s\n' 'Internal usage: smoke-init.sh gate|boot|suggest|detect' >&2; exit 2;;
  esac
fi
