# TASKS · stateless backlog

State lives on the `claims` branch (`uak status`); this file holds only tasks. IDs are `PREFIX-NNN` (`HACK-001`, `T-001`, `API-120`).
Priority is `P0/P1/P2`. Type is `setup/contract/spike/feature/bug/integration/demo/docs`. Check the graph with `uak graph`.

Format rules (the CLI parses them):
- `Depends on:` real IDs separated by commas, or `None`. It blocks the claim until they are INTEGRATED. Text in parentheses is ignored.
- `Uses contract:` soft dependency. It never blocks; it routes contract notices. Work against the mock.
- `Paths:` relative paths separated by commas; directories end in `/`. Reserve everything you will touch.
- `Verify:` one exact command that exits 0 when the task is done.
- `Estimate:` minutes or hours, used for the critical path.
- `Tests:` the behaviors as test names, separated by commas: the spec. `uak red ID` sees them fail first; `done` checks each exists. A task with nothing to test first: `Test-First: no (why)`.

## HACK-001 · <one visible result>

- **Type:** feature
- **Priority:** P0
- **Estimate:** 45 min
- **Rubric / Spec:** C1 · `docs/specs/001-x/spec.md`
- **Depends on:** None
- **Uses contract:** HACK-002
- **Related:** HACK-003
- **Paths:** app/routers/example.py, app/services/example.py, app/tests/test_example.py, web/src/features/example/
- **Freeze-Allowed:** no
- **Acceptance:**
  - <given an input, an exact observable result>
  - <an error or edge case you can check>
  - `bash .uak/bin/smoke` exits 0
- **Tests:** returns_the_example_for_a_known_id, answers_404_for_an_unknown_id
- **Verify:** `uv run pytest -q app/tests/test_example.py`
- **Next step:** <exact first action: file, function or command>
