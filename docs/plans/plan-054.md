## UAK-054 · The merge gate runs the full suite in parallel shards on the local machine

- **Type:** feature
- **Priority:** P1
- **Estimate:** 2 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/smoke, kit/.uak/docs/PROTOCOL.md, kit/.uak/tests/test_smoke_parallel.py
- **Acceptance:**
  - `bash .uak/bin/smoke --package-only --jobs N` (and `Smoke-Jobs: N` in PROJECT.md, read by the gate's smoke) runs the suite's test files in N balanced shards at once, the same split CI uses (`UAK_SMOKE_TESTS` per shard, balanced by the timings test_ci_shards already knows), and fails if any shard fails, printing each failing shard's tail; default 1 (today's behaviour)
  - every shard gets its own TMPDIR and HOME-like scratch so tests cannot collide; the result is identical to a serial run on the kit's suite (same PASS/FAIL set)
  - `--jobs auto` uses the CPU count minus one, at most 4
  - why (v6.1.0 and v6.1.1): every `uak merge` on the maintainer's machine ran the whole suite serially, over 10 minutes per task; `Merge-Smoke: affected` cannot help the kit itself because almost every task touches `.uak/bin/`
- **Tests:** jobs_split_runs_every_file_once, a_failing_shard_fails_the_run, default_is_serial
- **Verify:** `python3 kit/.uak/tests/test_smoke_parallel.py`
- **Next step:** the test-file loop of the package mode in kit/.uak/bin/smoke
