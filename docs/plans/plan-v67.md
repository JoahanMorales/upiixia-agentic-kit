## UAK-116 · A ledger of every command: name, outcome and milliseconds

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak, kit/.uak/bin/bb, kit/.uak/tests/test_command_ledger.py
- **Acceptance:**
  - every `uak` command appends one line when it ends to `<git-common-dir>/uak-ledger.pending`: epoch, command (with the `UAK_CALLER` prefix the calls file already uses), task ID when it has one, exit code, UAK_CODE when set, milliseconds, agent, harness. No extra process on the way (shell builtins; the clock from the cache the engine already has, or `$SECONDS`/`EPOCHREALTIME` where bash has them, falling back to whole seconds on bash 3.2)
  - `bb flush` publishes the pending ledger to claims as `metrics/<day>-<machine>.tsv` in the same transaction as the black box lines, then empties it; a flush that fails keeps the lines; the file per day and machine is capped (oldest lines summarized as counts per command and outcome) so claims does not grow without bound
  - UAK_BLACKBOX=off writes nothing; the existing `uak-blackbox.calls` file and its readers keep working
  - the output, exit code and process counts of every command stay as they are (test_claims_perf, test_v592)
  - Why (audit of v6.5.0, docs/audit-2026-11.md §4): calls were names only, per machine, with no durations and no outcomes; "how often does `claim` fail and how long does `status` take" could not be answered
- **Tests:** a_command_appends_one_ledger_line, a_failed_command_records_its_code, flush_publishes_and_empties, blackbox_off_writes_nothing, output_and_exit_code_unchanged
- **Verify:** `python3 kit/.uak/tests/test_command_ledger.py`
- **Next step:** the calls counter at kit/.uak/bin/uak:~103 and the flush in kit/.uak/bin/bb

## UAK-117 · `uak metrics`: every speed number next to an instability number

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-116
- **Paths:** kit/.uak/bin/metrics, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_metrics.py
- **Acceptance:**
  - `uak metrics [--since DAYS] [--task ID] [--json]` reads claims only (ledger files, tasks, reviews, queue, events, black box) and prints, in this order: tasks integrated per day next to tasks reopened, followed up or recorded `Unreviewed`; median hours from claim to INTEGRATED next to the share of tasks rejected at least once and the review rounds per task; per command: calls, error rate, median and p95 milliseconds; human interventions by reason (the queue reasons, `allow`, human integrates); work outside the kit (commits on the base branch without a task, integrates outside the gate, `manual` notes when UAK-121 lands: the section says "not recorded yet" until then)
  - every count is printed with its denominator ("7 of 89"), never a bare percentage for fewer than 20 events
  - `--task ID` prints one task: time in each state, rounds of review with each verdict and reviewer, who integrated it, its commands and errors
  - `--json` prints the same numbers as one object with stable keys (documented in CLI.md); commands.tsv gets the row and `gen_registry --check` passes
  - Why (audit §4; the human, 2026-11-20: "que todo sea medible y cuantificable para poder mejorar el kit"): `stats` counts events but pairs no speed with its cost, and has no per-command error rate or duration
- **Tests:** throughput_is_printed_with_instability, per_command_error_rate_and_p95, small_samples_print_counts, task_view_lists_review_rounds, json_has_stable_keys
- **Verify:** `python3 kit/.uak/tests/test_metrics.py`
- **Next step:** kit/.uak/bin/stats (the reader of claims to copy) and the commands.tsv row

## UAK-118 · Every task records who touched it and which model and harness each one ran

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/uak-coordination, kit/.uak/bin/hook, kit/.uak/bin/lib/tx.sh, kit/.uak/tests/test_task_participants.py
- **Acceptance:**
  - the session record a task already gets (`meta/task-sessions/<ID>/agent-<name>/session-*.md`) also holds `Harness:` and `Model:`, and so does the event line of every mutation (claim, done, review, merge, integrate, handover). The model comes from `UAK_MODEL` when set, else from what the harness hook saw at session start (Claude Code's payload, Codex's), else `unknown`; a subagent's model is its own, not its parent's
  - a task record lists its participants by role: author(s), reviewers with their verdicts, who merged or integrated, humans who stepped in
  - `uak status --task ID` prints the participants line; STATE.md keeps its format (test_snapshot stays byte-identical)
  - Why (the human, 2026-11-21: "debemos guardar qué agentes y modelos participaron en una tarea"): the session record had Agent, Session and Started only, and nothing said which model reviewed or wrote a task
- **Tests:** session_record_has_harness_and_model, events_carry_the_model, participants_by_role, unknown_when_nothing_tells, snapshot_unchanged
- **Verify:** `python3 kit/.uak/tests/test_task_participants.py`
- **Next step:** the session files written at kit/.uak/bin/uak-coordination:~381-394 and the harness detection at kit/.uak/bin/hook:~424

## UAK-119 · REVIEW says what it is waiting for, and for how long

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** UAK-118
- **Paths:** kit/.uak/bin/lib/status.sh, kit/.uak/bin/lib/dash.py, kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_review_substates.py
- **Acceptance:**
  - a task in REVIEW has one derived sub-state, computed from claims (no new stored state): `waiting for a reviewer`, `in review by NAME`, `changes requested (round N)` after a reject with no newer tip, `re-review (round N)` after the author pushed again, `approved, waiting for CI` when pr-sync knows the checks, `approved, waiting for a human merge` with the queue reason, `approved, waiting for the owner to merge`
  - `uak status`, `uak status --task ID` and `uak board` print the sub-state and the time spent in it; the dashboard's REVIEW column groups its cards by sub-state, each card with a badge (rounds, rejects) and the time in the sub-state, and a card that sat more than the review lease is marked
  - the text of the sub-state is the same everywhere (one function); STATE.md keeps its format
  - Why (the human, 2026-11-21: "a veces está en In review por horas y visualmente no sabes si hubo un rejected, está en CI o lo que sea"; v6.6: UAK-111 and UAK-114 each went through a reject and several rounds and the board showed REVIEW)
- **Tests:** substate_after_a_reject, substate_after_a_new_tip, approved_waiting_for_a_human_names_the_reason, time_in_substate, dashboard_data_groups_by_substate
- **Verify:** `python3 kit/.uak/tests/test_review_substates.py`
- **Next step:** the REVIEW rows in kit/.uak/bin/lib/status.sh and `build()` in kit/.uak/bin/lib/dash.py:~133

## UAK-120 · A task's whole story: `uak timeline ID`, and a click on its card

- **Type:** feature
- **Priority:** P1
- **Estimate:** 4 h
- **Depends on:** UAK-117, UAK-119
- **Paths:** kit/.uak/bin/timeline, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/bin/lib/dash.py, kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_task_timeline.py
- **Acceptance:**
  - `uak timeline ID [--json]` prints every move of a task in order, from claims and its history: planned and amended (by whom), claimed, each checkpoint, red recorded, done (PR, evidence), each review (reviewer, model, verdict, the reason of a reject, the SHA), each new tip after a reject with the files it changed, CI results when pr-sync has them, the merge or the human queue with its reason, integrate (and `Unreviewed`), handovers, expired leases and takeovers; each line with its time, the gap since the previous one, the agent, its model and harness
  - the totals at the end: hours in each state and sub-state, review rounds, agents and models that took part, commands and errors (from the ledger), tokens when published
  - the dashboard: clicking a card opens the task's story as a vertical timeline with the same lines, colored by kind of move, rejects and human steps standing out, with the sub-state durations as a bar on top; it works from file:// like the rest of the page (data embedded, no server), and Escape or a click outside closes it
  - a task with no history yet says so; a task from before the model was recorded shows `unknown`, not a guess
  - Why (the human, 2026-11-21: "presionar sobre una tarea debe mostrar todo el mapa de agentes y movimientos de la tarea súper bien explicado para realmente poder auditar")
- **Tests:** timeline_orders_every_move, a_reject_shows_reason_and_the_next_tip, totals_match_the_lines, json_has_stable_keys, dashboard_embeds_the_timeline
- **Verify:** `python3 kit/.uak/tests/test_task_timeline.py`
- **Next step:** the worklog and event readers in kit/.uak/bin/lib/dash.py (`snapshot`, `build`) and the card markup in kit/.uak/bin/lib/dash.html

## UAK-121 · "I had to do this by hand": manual steps are recorded and counted

- **Type:** feature
- **Priority:** P2
- **Estimate:** 2 h
- **Depends on:** UAK-116, UAK-118
- **Paths:** kit/.uak/bin/bb, kit/.uak/bin/hook, kit/.uak/tests/test_manual_notes.py
- **Acceptance:**
  - `uak bb note manual "what I did by hand" --fix "what the kit should do"` records a note of kind `manual` (next to friction, bug, idea, need), with the task and the command that was missing when given
  - the output hook recognizes the manual moves the black boxes show most: `git worktree add` in a kit repo, a commit on the base branch from the main checkout (the pre-commit log already has them), `gh pr merge` run by a human after MERGE_HUMAN, a `git push` of claims refused by the guard. Each becomes one `manual` line (auto), at most one per kind per session
  - AGENTS.md is not touched: the rule that asks for the note is one line in the text `uak bb` prints after a refused or failed command that has a known manual workaround
  - Why (the human, 2026-11-20: "en qué se tuvo que hacer algo que no estaba en el kit"; harvest 2026-11: "had to git worktree add by hand"): work outside the kit was visible only as "Direct to main: 130 of 222" with no reason
- **Tests:** manual_note_is_recorded_with_task, worktree_add_by_hand_is_noticed_once, human_merge_after_merge_human_is_counted
- **Verify:** `python3 kit/.uak/tests/test_manual_notes.py`
- **Next step:** the note kinds in kit/.uak/bin/bb and the output hook in kit/.uak/bin/hook:~657

## UAK-122 · Tokens per task and per step, also when the session started somewhere else

- **Type:** bug
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/tokens, kit/.uak/tests/test_tokens_elsewhere.py
- **Acceptance:**
  - a transcript whose session started outside the repo counts for the project when its tool calls ran in the main checkout or in a worktree under `<repo>-wt/` (the cwd of the calls, not only the cwd of the session); its subagent transcripts are attributed to the task whose worktree they worked in
  - tokens are split per step of a task: author work, review, merge gate and lead/coordination, from the worktree and the commands the transcript ran (`uak review`, `uak merge`); `uak tokens --by step` prints it and `--publish` includes it
  - `Token-Budget: N` in PROJECT.md (per task): `uak next` and `uak status --task` warn when a task's published tokens cross it; no budget, no warning
  - the transcripts' content is never copied: only counts, model names and task IDs leave the machine (as today)
  - Why (audit §1, 2026-11-20): `uak tokens` answered "no transcripts of this project found" in the kit's own repo, because every session that drives it starts in the home directory; so the cost per task of the kit's own development was unknown
- **Tests:** a_session_started_elsewhere_counts, subagent_tokens_go_to_their_task, tokens_by_step, budget_warns_once_crossed, no_content_leaves_the_machine
- **Verify:** `python3 kit/.uak/tests/test_tokens_elsewhere.py`
- **Next step:** the "a transcript belongs to this project" rule at the top of kit/.uak/bin/tokens

## UAK-123 · `uak autopsy`: the report of an event, written from claims

- **Type:** feature
- **Priority:** P2
- **Estimate:** 3 h
- **Depends on:** UAK-120
- **Paths:** kit/.uak/bin/autopsy, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_autopsy.py
- **Acceptance:**
  - `uak autopsy [--since DATE] [--until DATE] [--out FILE] [--claims DIR]` writes one markdown file in the shape of docs/blackbox/*.md: the facts table (kit version, mode, harnesses and models, machines, tasks by final state, commits on the base outside tasks, black box lines, tokens), the `uak metrics` numbers, the ten most repeated errors with their counts, every agent note verbatim marked as untrusted data, the slowest and the most-reviewed tasks with their timelines in short form, and a last section "Findings" left with one line per repeated issue for a human or an agent to complete
  - it reads claims only (or `--claims DIR`, an extracted checkout, for another repo's event) and runs nothing from it
  - names of people and repos stay as they are in claims for the team's own report; `--anonymous` replaces agent and human names with roles and drops repo names (for a public autopsy)
  - Why (the human, 2026-11-20: "cuando hagamos la autopsia sea más fácil identificar qué pasó"): each autopsy in docs/blackbox/ was assembled by hand from five commands
- **Tests:** autopsy_has_the_facts_table, top_errors_are_counted, notes_are_marked_untrusted, anonymous_hides_names, reads_an_extracted_claims_dir
- **Verify:** `python3 kit/.uak/tests/test_autopsy.py`
- **Next step:** kit/.uak/bin/stats and scripts/blackbox_harvest.py (what they already count)

## UAK-124 · A pre-push hook that reads the real ref, and the guard reads Mode like the engine

- **Type:** bug
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.githooks/pre-push, kit/.uak/bin/guard, install.sh, kit/.uak/tests/test_pre_push.py
- **Acceptance:**
  - `kit/.githooks/pre-push` reads the refs git is about to push (its stdin) and refuses a push by an agent to the base branch or to the claims branch from outside the engine, with the same reasons as the guard; the engine's own pushes (merge gate, transactions) pass (they set a marker the hook checks), and a human passes with the documented override (`UAK_DIRECT_MAIN=1`, as pre-commit)
  - the installer puts it next to pre-commit under the same rules (another hook manager keeps its hooks; the kit says how to add the check)
  - `guard` reads `Mode` trimmed and case-insensitively, like UAK-114's reader
  - Why (v6.6 review of UAK-111): the guard reads text, so a ref built by an arbitrary command, or a script written to a file and then run, is not seen; git itself knows the real ref at push time. And `Mode: Marathon` was not marathon for the guard
- **Tests:** push_to_base_is_refused_for_an_agent, push_to_claims_is_refused, engine_pushes_pass, human_override_passes, guard_reads_mode_case_insensitively
- **Verify:** `python3 kit/.uak/tests/test_pre_push.py`
- **Next step:** kit/.githooks/pre-commit (the pattern to copy) and where install.sh places it (~line 285)
