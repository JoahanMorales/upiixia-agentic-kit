## UAK-193 · An install never copies Python's bytecode, so the merge gate's smoke stops counting it

- **Type:** fix
- **Priority:** P0
- **Estimate:** 2 h
- **Depends on:** UAK-190
- **Paths:** install.sh, kit/.uak/tests/test_install_light.py, kit/.uak/tests/timings/test_install_light.txt
- **Acceptance:**
  - an install made from a kit folder that holds `__pycache__` directories or `.pyc` files (in `bin`, `bin/lib`, `docs`, `modes`, `templates`, `settings`, `stacks` or a skill) writes none of them into the project, in every mode and for an update as for a first install. Why: on 2026-11-24 the gate's smoke for UAK-190 failed `marathon_install_under_260_files` twice with 270 and 271 files against a bound of 270, while the same case alone on main counts 256; `install.sh` copies `.uak/bin` and the other parts with `cp -R` and removes `__pycache__` only under `tests`, so the bytecode that the other test files of the smoke write into `kit/.uak/bin/lib` while they run is installed and counted. With two `.pyc` files planted the case counted 258
  - the count of `marathon_install_under_260_files` is the same alone and while the whole smoke runs in four shards: a case plants bytecode in the kit's folders before installing and the count does not move
  - an install does not delete or change anything in the kit's own folder (the source): bytecode is left out of the copy, not removed from where it was
  - a project's own `__pycache__` outside `.uak/` and the kit's folders is never touched by an install or an update
- **Tests:** install_copies_no_bytecode, update_copies_no_bytecode, count_is_the_same_with_bytecode_in_the_kit, source_folder_is_left_as_it_was
- **Verify:** `python3 kit/.uak/tests/test_install_light.py`
- **Next step:** the loop `for part in bin docs modes templates settings stacks` in install.sh (line 153) and the skill copies below it; `files()` in the test
