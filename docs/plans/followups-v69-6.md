## UAK-195 · CI has a browser: the cases that need one run there, and a case that did not run says so

- **Type:** fix
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-191
- **Paths:** .github/workflows/test.yml, scripts/ci_select.py, kit/.uak/tests/test_ci_browser.py, kit/.uak/tests/timings/test_ci_browser.txt, kit/.uak/docs/WHY.md, AGENTS.md
- **Acceptance:**
  - the Linux suite jobs of the kit's CI install Chromium for Playwright (pinned version, cached between runs) before the tests, on pull requests and on main; the install's seconds are measured and written in WHY.md, and a pull request does not wait more than 60 s longer for it once the cache is warm. Why: on 2026-11-24 and 25 the reviews of UAK-159, UAK-162, UAK-192 and UAK-194 found defects that only a browser shows (a click refused in the first second after load, a tab that stopped drawing on partial data, a dialog that opened nothing); every case that needs Playwright passed in CI without running, so a green CI said nothing about them and each defect cost a review round
  - a test case that needs a browser and finds none does not print PASS: it prints `SKIP name (no browser)`, the file's result line counts skips, and on a job that declares it has a browser (an environment variable set by the workflow) a skip for lack of browser fails the file. On macOS and Windows, and on a developer's machine without Playwright, a skip stays a skip
  - the summary of a CI run says how many cases ran in a browser and how many were skipped, per system
  - the kit's rule is written once in AGENTS.md: behaviour of a page is tested in pure functions under node and in Chromium; a case that only reads the page's source does not count as testing a behaviour
  - nothing is downloaded at install time of the kit, and an installed project gains no file and no dependency: the browser is the kit's CI's, not the product's
- **Tests:** browser_cases_run_on_the_linux_job, skip_without_browser_is_not_a_pass, skip_fails_where_a_browser_is_declared, summary_counts_browser_cases, install_gains_no_file
- **Verify:** `python3 kit/.uak/tests/test_ci_browser.py && python3 kit/.uak/tests/test_ci_tiers.py && python3 scripts/kit_lint.py`
- **Next step:** how the existing cases find Playwright (search `playwright` in kit/.uak/tests: `test_setup_guide.py`, `test_setup_resume.py`, `test_dashboard_truth.py`, `test_setup_run_here.py`) and what they print when it is missing; the `suite` job in `.github/workflows/test.yml`; the workflow is the human's file, so the merge goes to the human. The helper that prints SKIP lives in each test file today: changing those files is not in this task's Paths, so this task adds the shared rule and the check of the result lines, and lists the files to convert for the tasks that own them
