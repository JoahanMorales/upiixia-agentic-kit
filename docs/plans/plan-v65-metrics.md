## UAK-070 · Every design round measures its tokens and its time, and the next estimate uses them

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2.5 h
- **Depends on:** UAK-069, UAK-064
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/bin/lib/design_metrics.py, kit/.uak/tests/test_design_metrics.py
- **Acceptance:**
  - each variant records `metrics.json` in its folder: started (TASK.md written), first page (first index.html write), done (last capture), wall seconds, look-and-fix passes (captures taken), and tokens with their source: the agent's reported usage when the builder writes it (`uak design done R<k> v<i> --tokens N` — one line in TASK.md tells the agent to run it with its usage), else the kit's own token records for that session (`uak tokens`), else `null` with the reason (never 0, never estimated)
  - `uak design report R<k>` prints one row per variant (tokens, minutes, passes, page errors) and the round's totals: tokens, wall time in parallel (longest variant), and tokens per picked variant; `--all` lists every round of the project with cumulative totals
  - the cost line before a round uses the measured median tokens per variant of this human's past rounds (by stage family: still/SVG/canvas vs three.js; from the taste profile store) and says where the number comes from; the 60k default only when there is no history, labeled "no history"
  - the cost line also estimates wall time (median minutes per variant at the given parallelism) and warns when a round won't fit before the event's next deadline in `uak clock` (sprint)
  - `uak design pick` shows each variant's tokens and minutes under its captures, and the round's totals in the header
  - the machine's load is recorded with each variant (1-min load average at start and end), so wall time inflated by an overloaded machine is visible
  - Why (AXIA R1–R3, 2026-11-11): in a hackathon, tokens and minutes decide whether a round fits. Measured by hand from the harness: R1 ≈ 454k tokens (partial, a usage limit cut it), R2 415k tokens in about 2.5 min wall (60–75k per variant), R3 812k tokens and 54 min wall (119–156k per variant: three.js spectacle, an overloaded Jetson). The kit's fixed 60k-per-variant estimate was off by 2× on R3.
- **Tests:** variant_metrics_written, tokens_null_with_reason_when_unknown, report_totals_and_parallel_wall, estimate_uses_measured_median_by_stage, deadline_warning_in_sprint, pick_page_shows_tokens_and_minutes
- **Verify:** `python3 kit/.uak/tests/test_design_metrics.py`
- **Next step:** a new kit/.uak/bin/lib/design_metrics.py (read/write metrics.json, medians), then the cost line in design_round.py
