#!/usr/bin/env python3
"""UAK-197: the cases of test_hook_session_start_speed.py about locks and simultaneous starts move here (stub)."""
import hashlib
import inspect
import sys
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


# moved_cases_are_the_same_cases (UAK-197): each function moved here, as its source text was in
# test_hook_session_start_speed.py on main at 0e50f9d0 (sha256 of inspect.getsource, first 16 hex digits). Text, not an
# AST dump: identical text is an identical AST on every Python. A case changed by this task as its fix is listed in FIXED
# with the exact text the fix added: without that text the source is the original.
ORIGINAL = {
    "session_start_coalesces_aged_live_refreshes": "85a78f02cda948b3",
    "session_start_recovers_a_dead_refresh_owner": "ef2467b8377e6368",
    "session_start_concurrent_claims_launch_one_refresh": "c70d5e3cf25c4e99",
    "session_start_abandoned_handoff_cannot_run_or_release": "e1d7ddca202d2b19",
    "hung_worker_is_killed": "ab0c36f5e7456e73",
    "pace_and_map_run_once_under_ten_starts": "25863d832d74a6f1",
    "cached_start_does_not_wait": "cff980abbe294bca",
    "once_harness": "5e932a3526f49c26",
    "live_process": "ed14048d5dec2b9d",
    "stop_live": "4002b8234f61361a",
    "bash_counts": "08ccc4dd80886a49",
    "counting_stubs": "783d98fc26f7e9bf",
    "corrupt_time_file_does_not_end_the_hook": "1b2cde66069fc878",
    "future_time_file_is_stale": "13a8abc7ff365605",
    "stale_lock_reclaim_runs_once": "bf7cbf92322f36e2",
    "once_lock_with_a_bad_time_is_stale": "6007ef21bb2fc3c0",
    "empty_guard_is_recovered": "0854febc9e16fcf8",
    "killed_bb_flush_is_recovered_and_published_once": "e6d3bdd3b460a05f",
    "other_users_pending_file_is_left": "2ceef526b6e72279",
    "clone_listing": "eaa3ac368bde0c05",
    "process_listing": "d88ba59fc51cd888",
    "kill_round": "d92b994ac2640dad",
    "killed_flush_leaves_no_clone_on_windows": "ea34eabe38a68490",
    "plant_clone": "2736936721b6d4cf",
    "leftover_clone_is_removed_by_the_next_flush": "822914d665c2c430",
    "held_push_fixture": "ab4204128d0a14a4",
    "published": "4a4a09e9bab4bad6",
    "pending_line": "cd6c1e2ada9844b9",
    "recover_and_count": "ba99ddff5646e665",
    "second_start_leaves_a_live_flushs_clone": "de7134dbbf5a4412",
    "eight_starts_with_a_held_push_publish_once": "6257982f20d14e02",
    "sweep_harness": "1ddd9883fc11e1b8",
    "unremovable_clone_is_retried_then_left_to_the_next_flush": "4417ad537fd680fb",
    "clone_removal_stays_inside_the_clone_directories": "76afc3bf936fe22b",
}
CONSTANTS = "3f63e571ebd279e2"   # repr((HUNG_UAK, ONCE_FUNCS))
FIXED = {}
# The 40 cases of test_hook_session_start_speed.py on main at 0e50f9d0: after the split each runs in exactly one file.
BEFORE = ["session_start_returns_within_budget", "session_start_output_is_unchanged", "session_start_marks_only_the_inbox_snapshot_it_prints",
          "session_start_coalesces_aged_live_refreshes", "session_start_recovers_a_dead_refresh_owner",
          "session_start_orphan_output_cannot_change_replacement_cache", "session_start_orphan_inbox_output_cannot_change_cache",
          "session_start_revokes_a_dead_owners_pending_move", "session_start_finishes_an_interrupted_reap",
          "session_start_failed_reap_is_closed_and_retryable", "session_start_corrupt_owner_records_cannot_delete_paths",
          "session_start_internal_owner_refs_bypass_user_hooks", "session_start_concurrent_claims_launch_one_refresh",
          "session_start_abandoned_handoff_cannot_run_or_release", "session_start_inbox_failure_preserves_cache_and_status",
          "session_start_launches_half_the_processes_on_startup", "session_start_launches_half_the_processes_on_resume",
          "session_start_keeps_reporting_the_pace_level", "hung_worker_is_killed", "pace_and_map_run_once_under_ten_starts",
          "cached_start_does_not_wait", "corrupt_time_file_does_not_end_the_hook", "future_time_file_is_stale",
          "stale_lock_reclaim_runs_once", "once_lock_with_a_bad_time_is_stale", "every_background_job_has_a_limit",
          "cached_copy_always_says_its_age", "empty_guard_is_recovered", "limited_jobs_poll_coarsely",
          "killed_bb_flush_is_recovered_and_published_once", "killed_map_build_is_not_a_built_map",
          "killed_tokens_publish_is_retried", "counter_files_are_validated", "other_users_pending_file_is_left",
          "killed_flush_leaves_no_clone_on_windows", "leftover_clone_is_removed_by_the_next_flush",
          "second_start_leaves_a_live_flushs_clone", "eight_starts_with_a_held_push_publish_once",
          "unremovable_clone_is_retried_then_left_to_the_next_flush", "clone_removal_stays_inside_the_clone_directories"]


def source_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def moved_cases_are_the_same_cases(r):
    import test_hook_session_start_speed as speed
    here = globals()
    changed, missing = [], []
    for name, digest in ORIGINAL.items():
        fn = here.get(name)
        if fn is None:
            missing.append(name)
            continue
        text = inspect.getsource(fn)
        for added in FIXED.get(name, ()):
            expect(added in text, "%s: the fix's text is in it: %r" % (name, added[:60]))
            text = text.replace(added, "", 1)
        if source_digest(text) != digest:
            changed.append(name)
        expect(not hasattr(speed, name), "%s is defined in one file only (it moved)" % name)
    expect(not missing, "moved here: %s" % missing)
    expect(not changed, "moved, not rewritten: the source of %s differs from main's" % changed)
    expect(source_digest(repr((here.get("HUNG_UAK"), here.get("ONCE_FUNCS")))) == CONSTANTS, "HUNG_UAK and ONCE_FUNCS moved unchanged")
    mine = [t.__name__ for t in TESTS if t.__name__ != "moved_cases_are_the_same_cases"]
    theirs = [t.__name__ for t in speed.TESTS]
    expect(not set(mine) & set(theirs), "no case runs in both files: %s" % sorted(set(mine) & set(theirs)))
    expect(sorted(mine + theirs) == sorted(BEFORE), "every case of the file before the split runs once: missing %s, new %s"
           % (sorted(set(BEFORE) - set(mine + theirs)), sorted(set(mine + theirs) - set(BEFORE))))
    # The check sees a change: one character more in a moved case is not the original.
    probe = inspect.getsource(here["pending_line"])
    expect(source_digest(probe + " ") != ORIGINAL["pending_line"] and source_digest(probe) == ORIGINAL["pending_line"], "the digest sees one character")
    return "%d functions moved unchanged%s; %d cases here, %d in the speed file" % (
        len(ORIGINAL) - len(FIXED), (", %s changed only by its fix" % ", ".join(FIXED)) if FIXED else "", len(mine), len(theirs))


TESTS = [moved_cases_are_the_same_cases]


def main():
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-ss-locks-") as tmp:
        r = Runner(Path(__file__).resolve().parents[2], Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            try:
                print("PASS %s (%s)" % (test.__name__, test(r)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:1500]))
    print("SESSION_START_LOCKS_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
