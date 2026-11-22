## UAK-129 · The reviewer runs Verify and the tests the diff touches; the whole suite runs once, at the merge gate

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/smoke, kit/.uak/bin/lib/tests.sh, kit/.claude/agents/uak-reviewer.md, kit/.uak/modes/sprint.md, kit/.uak/modes/marathon.md, kit/.uak/tests/test_smoke_affected.py
- **Acceptance:**
  - `smoke --affected [BASE]` runs the lint, the secret scan, the task's Verify and only the test files the diff against BASE touches or names (a test file changed; a test file whose name or imports match a changed engine file; every file when the diff touches `lib/core.sh`, `lib/tx.sh` or the test helpers). It prints which files it chose and why, and how many it left for the gate
  - `smoke --affected` is documented in its own usage line and in both mode files (docs/CLI.md is held by UAK-131 and gets its line in a follow-up)
  - the reviewer's instructions and both mode files say: Verify plus `smoke --affected`, and the note of an approval says which was run; the author does the same before `done`
  - the merge gate keeps running the whole suite on the merged result; nothing an agent sets (an environment variable, a flag) makes the gate run fewer tests
  - on the kit's own repository the three runs per task become one whole run and two partial ones; the test measures a partial run on a one-file diff under a quarter of the files
  - Why (audit §1): the suite took 8–10 min and ran three times per task (author, reviewer, gate), the largest cost in time; 152 review rounds in 105 tasks each paid a whole run
- **Tests:** affected_runs_changed_test_files, engine_change_selects_its_tests, core_change_runs_everything, gate_ignores_the_shortcut, prints_what_it_left
- **Verify:** `python3 kit/.uak/tests/test_smoke_affected.py`
- **Next step:** the `UAK_SMOKE_TESTS` selection at kit/.uak/bin/smoke:41-56 and step 26 of kit/.claude/agents/uak-reviewer.md
