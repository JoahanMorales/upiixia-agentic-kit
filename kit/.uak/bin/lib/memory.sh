# Team memory anchored to paths; Bash 3.2+.
# claims:memory/LESSONS.md is append-only: "- N | epoch | agent | task | paths | text". A lesson is a gotcha or a
# "how things are done here" fact tied to the paths where it bites. The harness retrieves it by itself: `uak next`
# (which every session starts with) prints the lessons whose paths overlap the task, newest first.
# Why (MLB hackathon): the same traps came back task after task — a label that shifts with altitude was rejected in
# 3 tasks, "every number must come from the CSV" in 4 rejects, `df['count']` vs DataFrame.count lived only in a
# contract message from day 1. Messages scroll away; lessons stay where the code is. Research on long-running
# agents points the same way: situational knowledge retrieved by the harness, not chosen by the agent.
MEM_LOG=memory/LESSONS.md
MEM_TEXT= MEM_PATHS= MEM_FORGET= MEM_DONE= MEM_SEARCH= MEM_SIMILAR=no
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
# The words of a task for retrieval: its title, acceptance and Paths in the backlog.
mem_task_text() {
  awk -v id="$1" '/^## / { on = ($2 == id); if (on) { sub(/^## [^ ]+[ ·—-]*/, ""); print }; next } /^# / { on = 0 } on' "$BACKLOG" 2>/dev/null
}
# Lexical retrieval (BM25) over what the team already learned: lessons, reject notes, contract messages,
# decisions and the live summaries of INTEGRATED tasks on claims, ranked by the words of $1. Prints at most $2 lines; $3 is a space list of lessons to skip
# ("#4 #9", already shown by path). A hit needs 2 or more shared words. No model, no network, no index to build.
# Why (MLB hackathon): the same rejects came back on tasks with other paths ("numbers must come from the CSV" in 4
# rejects, a label that shifts with altitude in 3); lessons matched by path alone missed them, and 10 recalls for
# 130 claims show agents do not search the past themselves.
mem_similar() {
  local f
  set -- "$1" "${2:-3}" "${3:-}"
  # One line: BSD awk (macOS) rejects a -v value with a newline ("newline in string") and prints nothing.
  local q max=$2 skip=" $3 "
  q=$(printf '%s' "$1" | tr '\n\r\t' '   ')
  shift 3
  # Finished work too: the live summary of each INTEGRATED task (how something like this was solved). Three awk
  # passes, not a field read per task (81 tasks at MLB took 1 s that way).
  : > "$TXROOT/done-summaries"
  if ls "$TX"/tasks/*.md >/dev/null 2>&1; then
    awk 'function out() { if (st == "INTEGRATED" && wl != "") print id "\t" up "\t" ow "\t" wl }
      FNR == 1 { if (NR > 1) out(); id = st = wl = ow = up = "" }
      /^ID: / { id = substr($0, 5) } /^State: / { st = substr($0, 8) } /^Worklog: / { wl = substr($0, 10) }
      /^Owner: / { ow = substr($0, 8) } /^Updated: / { up = substr($0, 10) }
      END { out() }' "$TX"/tasks/*.md > "$TXROOT/done-meta"
    awk '/^## [A-Z][A-Z0-9]*-[0-9]/ { id = $2; t = $0; sub(/^## [^ ]+[ ·—-]*/, "", t); print id "\t" t }' "$BACKLOG" 2>/dev/null > "$TXROOT/done-titles"
    set --
    while IFS="$(printf '\t')" read -r _ _ _ wl; do [ -f "$TX/$wl" ] && set -- "$@" "$TX/$wl"; done < "$TXROOT/done-meta"
    [ "$#" -eq 0 ] || awk -v meta="$TXROOT/done-meta" -v titles="$TXROOT/done-titles" -v tx="$TX/" '
      BEGIN { FS = "\t"; while ((getline l < titles) > 0) { split(l, a, "\t"); T[a[1]] = a[2] }
        while ((getline l < meta) > 0) { split(l, a, "\t"); W[tx a[4]] = l } FS = " " }
      FNR == 1 { if (cur != "") flush(); cur = FILENAME; on = 0; txt = "" }
      /^## Live summary$/ { on = 1; next } /^## History$/ { on = 0 }
      on && /^- (Done|Decision|Why|Failing): / { x = $0; sub(/^- /, "", x); txt = txt x " · " }
      function flush(   a) { split(W[cur], a, "\t"); gsub(/[\t|]/, " ", txt); print a[1] "\t" a[2] "\t" a[3] "\t" T[a[1]] " · " txt }
      END { if (cur != "") flush() }' "$@" > "$TXROOT/done-summaries"
    set -- "$q" "$max" "${skip# }"; shift 3
  fi
  for f in "$TX/$MEM_LOG" "$TX/inbox/log.md" "$TX/DECISIONS.md" "$TXROOT/done-summaries"; do [ -s "$f" ] && set -- "$@" "$f"; done
  [ "$#" -gt 0 ] && [ -n "$q" ] || return 0
  awk -F' [|] ' -v q="$q" -v max="$max" -v now="$NOW" -v skip="$skip" '
    function toks(s, arr,   n, i, t, a, c) { s = tolower(s); gsub(/[^a-z0-9_\200-\377]+/, " ", s); n = split(s, a, " "); c = 0
      for (i = 1; i <= n; i++) { t = a[i]; if (length(t) < 3 || (t in stop) || (length(t) >= 7 && t ~ /^[0-9a-f]+$/) || t ~ /^[0-9]+$/) continue; arr[++c] = t }
      return c }
    function add(kind, t, who, task, text,   n, i, a, w, sw2) { D++; K[D] = kind; TM[D] = t + 0; WHO[D] = who; TK[D] = task; TXT[D] = text
      n = toks(text, a); L[D] = n; tot += n; split("", sw2)
      for (i = 1; i <= n; i++) { w = a[i]; tf[D, w]++; if (!(w in sw2)) { sw2[w] = 1; df[w]++ } } }
    BEGIN { n = split("the and for with that this from into are was were not but you your have has had its our out all any can will one two per via use used uses using when what where which who how why than then them they also each more most such only over under after before able los las del que con por para una uno sus como mas sin sobre entre este esta estos estas cada pero tambien ser son fue debe hay todo todos task tasks file files done next fix test tests add new must should hack sha approved rejected review reviewed agent paths path verify acceptance priority depends type estimate area rubric ninguna none", sw, " ")
      for (i = 1; i <= n; i++) stop[sw[i]] = 1
      nq = toks(q, Q); for (i = 1; i <= nq; i++) qs[Q[i]] = 1 }
    FILENAME ~ /LESSONS/ { if ($0 !~ /^- [0-9]/) next
      if ($6 ~ /^forget #/) { g = $6; sub(/^forget #/, "", g); gone["#" g] = 1; next }
      add("lesson #" substr($1, 3), $2, $3, $4, $6); next }
    FILENAME ~ /inbox\/log\.md$/ { if ($0 !~ /^- [0-9]/) next
      if ($5 == "reject" || $5 == "contract") add($5, $2, $3, $6, $7); next }
    FILENAME ~ /done-summaries$/ { split($0, a, "\t"); add("integrated", a[2], a[3], a[1], a[4]); next }
    FILENAME ~ /DECISIONS/ { if ($0 !~ /^- [0-9]/ || $2 ~ /^deadline/ || $0 ~ /REQUIRES_RECOVERY|tasks added|follow-up of/) next
      t = $1; sub(/^- /, "", t); add("decision", t, $3, "-", $4 (NF > 4 ? " · " $5 : "")) }
    END { if (!D || !nq) exit; avg = tot / D
      for (d = 1; d <= D; d++) { k = K[d]; sub(/^lesson /, "", k); if ((k in gone) || index(skip, " " k " ")) continue
        sc = 0; m = ""; hits = 0
        for (w in qs) if ((d, w) in tf) { idf = log(1 + (D - df[w] + 0.5) / (df[w] + 0.5)); f = tf[d, w]
          sc += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * L[d] / avg)); hits++; m = m (m == "" ? "" : ",") w }
        if (hits >= 2) { S[d] = sc; M[d] = m } }
      for (r = 1; r <= max; r++) { best = 0
        for (d in S) if (!(d in used) && (best == 0 || S[d] > S[best])) best = d
        if (!best) break; used[best] = 1
        age = now - TM[best]; ag = (age >= 86400) ? int(age / 86400) "d" : (age >= 3600 ? int(age / 3600) "h" : int(age / 60) "m")
        txt = TXT[best]; if (length(txt) > 170) txt = substr(txt, 1, 167) "..."
        printf "  %s%s · %s ago%s: %s  [%s]\n", K[best], (TK[best] != "-" && TK[best] != "" ? " on " TK[best] : ""), ag, (WHO[best] != "" ? " · " WHO[best] : ""), txt, M[best] } }' "$@"
}
# For `next` and `claim`: the lessons of a task's paths, then what the team learned on similar work; silent when none.
mem_for_task() {
  local paths out shown sim
  paths=$(mem_paths_of "$1")
  if [ -n "$paths" ]; then
    out=$(mem_select "$paths" 3)
    [ -z "$out" ] || { say "Lessons for these paths (uak recall $1 for all):"; say "$out"; }
  fi
  shown=$(printf '%s\n' "$out" | sed -n 's/^  \(#[0-9][0-9]*\) .*/\1/p' | tr '\n' ' ')
  sim=$(mem_similar "$(mem_task_text "$1")" 3 "$shown")
  [ -z "$sim" ] || { say "Learned on similar work (by words; uak recall $1 --similar):"; say "$sim"; }
}
recall_run() {
  ATTEMPT=read; fresh_state; coord_init
  [ -n "$ID" ] || [ -z "${UAK_TASK:-}" ] || ID=$UAK_TASK
  if [ -n "$MEM_SEARCH" ] || [ "$MEM_SIMILAR" = yes ]; then
    local q=$MEM_SEARCH; [ -n "$q" ] || q=$(mem_task_text "$ID")
    [ -n "$q" ] || die "recall --similar needs a task (ID or UAK_TASK) or --search \"words\"."
    local hits; hits=$(mem_similar "$q" "${MEM_MAX:-8}")
    if [ -z "$hits" ]; then say "RECALL: nothing the team learned shares 2+ words with: $(printf '%s' "$q" | head -n 1 | cut -c 1-80)"; return 0; fi
    say "RECALL by words (lessons, rejects, contracts, decisions; best first):"; say "$hits"; return 0
  fi
  local want=${MEM_PATHS:-}
  if [ -z "$want" ] && [ -n "$ID" ]; then want=$(mem_paths_of "$ID"); [ -n "$want" ] || die "$ID has no Paths in TASKS.md."; fi
  if [ -z "$want" ] && [ -n "${UAK_TASK:-}" ]; then ID=$UAK_TASK; want=$(mem_paths_of "$ID"); fi
  want=${want:-*}
  local out; out=$(mem_select "$want" "${MEM_MAX:-20}")
  if [ -z "$out" ]; then say "RECALL ${ID:-$want}: no lessons yet. Record one: uak learn \"what bites · where · what to do\""; return 0; fi
  say "RECALL ${ID:-$want} (newest first):"; say "$out"
}
