## UAK-082 · test_tokens_coverage no longer fails on Windows when its temp worktree is still locked at cleanup

- **Type:** bug
- **Priority:** P2
- **Estimate:** 30 min
- **Depends on:** —
- **Paths:** kit/.uak/tests/test_tokens_coverage.py
- **Acceptance:**
  - the test's temporary directory is removed with retries (a short backoff for WinError 32 / 5) and a cleanup that still fails is reported as a warning, never as a test failure; every case's own pass/fail is unchanged
  - if a process of the test itself (git, a hook) still holds `tk-hooks/worktree-1`, it is waited for or closed before cleanup, and the Why names it
  - Why (CI 2026-11-14, runs 43561825313 and 43563146571 of v6.3.0): both failed only on Windows with `PermissionError: [WinError 32] … uak-tokens-coverage-*\tk-hooks\worktree-1` raised by `TemporaryDirectory` cleanup after every case passed; a rerun went green each time, so the release needed manual reruns
- **Tests:** cleanup_survives_locked_worktree
- **Verify:** `python3 kit/.uak/tests/test_tokens_coverage.py`
- **Next step:** the `tempfile.TemporaryDirectory(prefix="uak-tokens-coverage-")` block in main() of kit/.uak/tests/test_tokens_coverage.py (line ~151)
