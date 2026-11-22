## UAK-127 · An install without the kit's own tests, with skills on demand

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3 h
- **Depends on:** None
- **Paths:** install.sh, kit/.uak/bin/doctor, kit/.uak/bin/smoke, kit/.uak/bin/uak-coordination, kit/.uak/bin/skill, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/settings/known-files.txt, scripts/kit_hashes.py, kit/.uak/tests/test_install_light.py
- **Acceptance:**
  - `install.sh` no longer copies `kit/.uak/tests/` into a project (112 files, 1.5 MB): a project's `smoke` runs its own checks and the product smoke, and says in one line that the kit's protocol suite runs in the kit's repository. `--with-tests` installs them as today; `--update` removes the kit's test files it recognizes by hash (`known-files.txt`) and keeps any file a team edited or added
  - the skill library (`.uak/skills/`, 114 files) is not copied whole: the install places only the skills the mode, stack and `--skills` ask for, as today under `.claude/skills` and `.agents/skills`, and `uak skill add NAME` copies one more from the kit's checkout or, with no checkout, from the pinned release (git only, hash-checked like the external skills)
  - a default marathon install for Claude Code (`--harness claude`, external skills on, as a user gets it) is under 260 files (was 534, 9.3 MB); the test counts it with the external skills fetched from a local fixture, prints the count and the bytes, and fails over the bound. Decided by the human on 2026-11-21: the first bound was 200, and the 63 files over it are the pinned external landing skill, which an existing test requires the install to fetch; placing it on demand is a task of its own
  - `doctor` does not ask for the test directory, and every command that reads `.uak/tests` or `.uak/skills` works when they are absent
  - Why (audit of v6.5.0, docs/audit-2026-11.md §1): an install put 535 files and 9.3 MB in a project, of which 108 were the kit's own tests and 114 the skill library; heavy in files, not in context
- **Tests:** install_has_no_kit_tests, with_tests_installs_them, update_removes_only_known_test_files, skill_add_copies_one, marathon_install_under_260_files
- **Verify:** `python3 kit/.uak/tests/test_install_light.py`
- **Next step:** the copy loop at install.sh:107 (`for part in bin docs modes templates tests settings stacks skills`) and the skill placement at install.sh:162-173
