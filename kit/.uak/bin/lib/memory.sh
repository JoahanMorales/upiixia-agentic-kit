# Team memory anchored to paths; Bash 3.2+.
# claims:memory/LESSONS.md is append-only: "- N | epoch | agent | task | paths | text". A lesson is a gotcha or a
# "how things are done here" fact tied to the paths where it bites. The harness retrieves it by itself: `uak next`
# (which every session starts with) prints the lessons whose paths overlap the task, newest first.
# Why (MLB hackathon): the same traps came back task after task — a label that shifts with altitude was rejected in
# 3 tasks, "every number must come from the CSV" in 4 rejects, `df['count']` vs DataFrame.count lived only in a
# contract message from day 1. Messages scroll away; lessons stay where the code is. Research on long-running
# agents points the same way: situational knowledge retrieved by the harness, not chosen by the agent.
MEM_LOG=memory/LESSONS.md
MEM_TEXT= MEM_PATHS= MEM_FORGET= MEM_DONE=
mem_paths_of() { # $1 task ID → its Paths from the backlog, comma separated
  local saved=$ID; ID=$1; task_field Paths 2>/dev/null | tr -d '` '; ID=$saved
}
learn_mutate() {
  mkdir -p "$TX/memory"
  [ -f "$TX/$MEM_LOG" ] || printf '%s\n' '# Lessons (uak learn)' '' \
    'Append-only. Format: - N | epoch | agent | task | paths | text. `uak recall` and `uak next` show the ones for your paths.' '' > "$TX/$MEM_LOG"
  local n; n=$(grep -c '^- [0-9]' "$TX/$MEM_LOG" || true); n=$((n + 1))
  if [ -n "$MEM_FORGET" ]; then
    grep -q "^- $MEM_FORGET | " "$TX/$MEM_LOG" || die "No lesson #$MEM_FORGET."
    printf -- '- %s | %s | %s | - | - | forget #%s\n' "$n" "$NOW" "$AGENT" "$MEM_FORGET" >> "$TX/$MEM_LOG"
    MEM_DONE="forgot #$MEM_FORGET"; return 0
  fi
  local text; text=$(one_line "$MEM_TEXT" | tr '|' '/')
  [ "${#text}" -le 300 ] || die "A lesson is one fact of 300 characters or fewer: what bites, where, and what to do instead."
  [ "${#text}" -ge 12 ] || die "A lesson needs the fact itself (what bites and what to do)."
  if awk -F' [|] ' -v t="$text" '$6 == t {found = 1} END {exit !found}' "$TX/$MEM_LOG"; then MEM_DONE="already known"; return 0; fi
  local task=${ID:-${UAK_TASK:-}} paths=$MEM_PATHS
  [ -n "$paths" ] || { [ -z "$task" ] || paths=$(mem_paths_of "$task"); }
  paths=$(printf '%s' "${paths:-*}" | tr -d ' ' | tr '|' '/')
  printf -- '- %s | %s | %s | %s | %s | %s\n' "$n" "$NOW" "$AGENT" "${task:--}" "$paths" "$text" >> "$TX/$MEM_LOG"
  MEM_DONE="#$n on ${paths}"
}
# Lessons whose paths overlap $1 (comma-separated paths; "*" = all). Newest first, at most $2 (default 5).
mem_select() {
  [ -f "$TX/$MEM_LOG" ] || return 0
  awk -F' [|] ' -v want="$1" -v max="${2:-5}" -v now="$NOW" '
    function ov(a, b,   x, y) { x = a; y = b; sub(/\*.*$/, "", x); sub(/\*.*$/, "", y)
      if (x == "" || y == "") return 1
      return index(x, y) == 1 || index(y, x) == 1 }
    /^- [0-9]/ { n = substr($1, 3) + 0; if ($6 ~ /^forget #[0-9]+$/) { f = $6; sub(/^forget #/, "", f); gone[f + 0] = 1; next }
      line[n] = $0; P[n] = $5; T[n] = $6; W[n] = $3; K[n] = $4; E[n] = $2; if (n > top) top = n }
    END { nw = split(want, w, ","); shown = 0
      for (i = top; i >= 1 && shown < max; i--) { if (!(i in line) || (i in gone)) continue
        np = split(P[i], p, ","); hit = 0
        for (a = 1; a <= np && !hit; a++) for (b = 1; b <= nw && !hit; b++) if (ov(p[a], w[b])) hit = 1
        if (!hit) continue
        age = now - E[i]; ag = (age >= 86400) ? int(age / 86400) "d" : (age >= 3600 ? int(age / 3600) "h" : int(age / 60) "m")
        printf "  #%d · %s ago · %s%s: %s\n", i, ag, W[i], (K[i] != "-" ? " · " K[i] : ""), T[i]; shown++ } }' "$TX/$MEM_LOG"
}
# For `next`: the lessons of a task's paths, with a header; silent when there are none.
mem_for_task() {
  local paths out; paths=$(mem_paths_of "$1"); [ -n "$paths" ] || return 0
  out=$(mem_select "$paths" 3); [ -n "$out" ] || return 0
  say "Lessons for these paths (uak recall $1 for all):"; say "$out"
}
recall_run() {
  ATTEMPT=read; fresh_state; coord_init
  local want=${MEM_PATHS:-}
  if [ -z "$want" ] && [ -n "$ID" ]; then want=$(mem_paths_of "$ID"); [ -n "$want" ] || die "$ID has no Paths in TASKS.md."; fi
  if [ -z "$want" ] && [ -n "${UAK_TASK:-}" ]; then ID=$UAK_TASK; want=$(mem_paths_of "$ID"); fi
  want=${want:-*}
  local out; out=$(mem_select "$want" "${MEM_MAX:-20}")
  if [ -z "$out" ]; then say "RECALL ${ID:-$want}: no lessons yet. Record one: uak learn \"what bites · where · what to do\""; return 0; fi
  say "RECALL ${ID:-$want} (newest first):"; say "$out"
}
