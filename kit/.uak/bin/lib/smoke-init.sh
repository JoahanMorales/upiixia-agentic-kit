# Adapter compiled from the user's explicit command; Bash 3.2+.
init_smoke() {
  local adapter provenance hash command_hash result
  [ -n "${SMOKE_COMMAND:-}" ] || die "init-smoke needs --command with the real product check."
  mkdir -p "$ROOT/scripts" || return 2
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
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd) || exit 2
  case "${1:-}" in gate) product_gate; exit "$?";; *) printf '%s\n' 'Internal usage: smoke-init.sh gate' >&2; exit 2;; esac
fi
