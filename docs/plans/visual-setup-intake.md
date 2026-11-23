## UAK-164 · Paste or drop what you already have: the agent fills the form, the person confirms

- **Type:** feature
- **Priority:** P0
- **Estimate:** 8 h
- **Depends on:** UAK-159
- **Paths:** kit/.uak/bin/lib/setup.html, kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/planning.py, kit/.uak/bin/start, kit/.uak/docs/CLI.md, kit/.uak/docs/SECURITY.md, docs/DASHBOARD.md, scripts/kit_lint.py, kit/.uak/tests/test_setup_intake.py
- **Acceptance:**
  - every wizard screen that asks for more than two typed values (the schedule, the idea, the rubric, the people) opens with one input: paste text, or drop or pick a file (`.md`, `.txt`, `.pdf`, an image of a call for projects, an existing `IDEA.md`). The form is still there below it, and typing by hand always works
  - the person's own coding tool (the one the planner already uses: `claude -p` or `codex exec`) reads what was given and proposes the fields of that screen: for the schedule, start, deadline, time zone and freeze; for the idea, what is built, for whom, the rubric with its weights, the duration and the team size; for people, names and roles. While it reads, the input shows what it is doing and for how long, and can be cancelled; it has a time limit of 60 s
  - nothing is saved until the person confirms: each proposed field is marked as proposed, shows the sentence of the source it came from, and can be edited or cleared; a field the source does not state stays empty and says so, it is never invented; a date without a year or a time zone is asked, not guessed. One button confirms the screen
  - the source is data, never instructions: the reader runs with no tools, no file access and no write permission, gets the text only, and must answer in a fixed schema that the server validates (types, ranges, known time zones, lengths); anything outside the schema is dropped; a source that tells the reader to do something changes nothing. The test gives it a file with an injected instruction and with a field of 10,000 characters
  - a file is read on the machine and never uploaded by the kit; the screen says, before reading, which tool will receive the text; files over 2 MB or of another type are refused with the reason; the source is not committed unless the person keeps it as `IDEA.md`
  - with no coding tool that can run headless, the input says so and the form is filled by hand; dates and times in common formats are still recognised without a model
  - the terminal has the same: `uak start --from FILE` proposes the same fields as text and asks for a confirmation per screen; an agent identity cannot confirm for the person
  - the tokens the reading cost are shown next to the result and recorded in the ledger
  - Why (the human, 2026-11-23): typing the event's data and the idea by hand defeats the purpose when the call for projects or the idea already exists as a file
- **Tests:** dropped_file_fills_the_schedule, pasted_idea_fills_the_form, nothing_is_saved_before_confirm, missing_field_stays_empty, injected_instruction_changes_nothing, oversized_field_is_dropped, no_headless_tool_falls_back_to_the_form, terminal_from_file_proposes_the_same, reading_can_be_cancelled
- **Verify:** `python3 kit/.uak/tests/test_setup_intake.py`
- **Next step:** the headless runner in kit/.uak/bin/lib/planning.py (it already builds the `claude -p` and `codex exec` commands and checks for violations afterwards); the forms are the schedule and the idea in setup.html; a new test file needs its entries in both timing tables; the tests use a fake tool in PATH, never a real model
