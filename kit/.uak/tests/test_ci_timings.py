#!/usr/bin/env python3
"""UAK-187: the seconds of a test file live in one small file per test, kit/.uak/tests/timings/NAME.txt (`ci N`,
`windows N`, optional `# why` lines), read by scripts/kit_lint.py at import. Why: thirteen published tasks listed
scripts/kit_lint.py only to add two numbers to CI_SECONDS and CI_WINDOWS_SECONDS, and the protocol refuses two live claims
that share a path, so they ran one at a time (2026-11-23, plan "visual setup"). A task that adds a test now adds its own
timing file and does not touch scripts/kit_lint.py. These cases call the lint's reader, the selector and a real install."""
import argparse
import importlib.util
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_install_light import files, install
from test_skills_windows_clone import repo

REPO = Path(__file__).resolve().parents[3]
TIMINGS = REPO / "kit" / ".uak" / "tests" / "timings"

# The two tables as they were before this task (scripts/kit_lint.py of main at 2026-11-23, 152 test files). Frozen on purpose:
# moving the numbers into files must not move a single shard.
FROZEN_CI = {
    "mcp_tools": 17, "test_autopsy": 4, "test_banner_version": 1, "test_bb_flush_no_hooks": 16, "test_ci_shards": 19,
    "test_ci_tiers": 8, "test_ci_web_deps": 1, "test_claims_cache": 9, "test_claims_perf": 84,
    "test_claims_read": 19, "test_cli_spelling_hints": 7, "test_command_ledger": 46, "test_coordination": 35,
    "test_critic_stale_ui_only": 11, "test_cursor_skills_keep": 12, "test_dashboard_journey": 18,
    "test_dashboard_profiles": 25, "test_dashboard_truth": 14, "test_demo": 25, "test_deploy_python_stdlib": 2,
    "test_design_aspect": 7, "test_design_breed": 8, "test_design_breed_notes": 16, "test_design_breed_rules": 6,
    "test_design_breed_twins": 3, "test_design_brief_real": 1, "test_design_color": 43, "test_design_creativity": 6,
    "test_design_creativity_inherit": 3, "test_design_density": 22, "test_design_fonts": 3, "test_design_ground": 3,
    "test_design_lint_html": 1, "test_design_lint_scale": 2, "test_design_lock_round": 1, "test_design_metrics": 39,
    "test_design_perf": 67, "test_design_pick": 439, "test_design_prior": 2, "test_design_round": 3,
    "test_design_round_taste": 2, "test_design_shoot_full": 10, "test_design_shoot_qa": 45,
    "test_design_shoot_timeout": 9, "test_design_stage": 1, "test_design_taste": 2, "test_design_taste_cli": 72,
    "test_design_taste_team": 37, "test_direct_main": 25, "test_doctor_skills_compare": 11,
    "test_done_without_github": 20, "test_engine_messages_qa14": 22, "test_external_skills": 15,
    "test_flaky_guard": 101, "test_flaky_guard_race": 441, "test_freeze_claim": 3, "test_gallery_lint": 1,
    "test_gate_scope": 3, "test_git_identity_msg": 6, "test_gitleaks_exception": 12, "test_guard_substitution": 5,
    "test_hack": 61, "test_harness_commands": 6, "test_harvest_discovery": 1, "test_hook_claims": 12,
    "test_hook_session_start_speed": 72, "test_hooks_health": 34, "test_install_claude_only": 22,
    "test_install_light": 18, "test_integrate_on_main": 28, "test_integrate_outside": 22,
    "test_integrate_unreviewed": 72, "test_landing_skills": 1, "test_lint_paths_hint": 8, "test_manual_notes": 16,
    "test_mcp_runs_commands": 1, "test_merge_affected": 24, "test_merge_commit_field": 91,
    "test_merge_engine_policy": 186, "test_merge_renewer_orphan": 30, "test_metrics": 3, "test_next_prefilter": 10,
    "test_next_reviewer": 13, "test_one_live_renew": 15, "test_plan_amend_overlap": 14, "test_plan_check": 11,
    "test_plan_owners": 8, "test_plan_scale": 7, "test_policy": 1, "test_pre_push": 39, "test_q_string": 1,
    "test_read_cache": 35, "test_review_identity": 6, "test_review_merge": 93, "test_review_substates": 90,
    "test_review_unseen_approval": 16, "test_reviewer_next": 13, "test_setup_branches": 20, "test_setup_feedback": 2,
    "test_setup_first_run": 19, "test_setup_forms": 7, "test_setup_guide": 27, "test_setup_language": 5,
    "test_setup_planning": 59, "test_setup_prepare": 96, "test_setup_processes": 130, "test_setup_resume": 25,
    "test_setup_roles": 30, "test_setup_team": 68, "test_setup_trust": 80, "test_setup_tutorial": 4,
    "test_setup_wizard": 25, "test_skills_windows_clone": 21, "test_smoke_affected": 58, "test_smoke_env": 2,
    "test_smoke_onboarding": 62, "test_smoke_parallel": 7, "test_snapshot": 2, "test_start_version_gate": 26,
    "test_status_planned": 10, "test_task_participants": 9, "test_task_timeline": 2, "test_temp_and_timeouts": 4,
    "test_tokens_coverage": 29, "test_tokens_elsewhere": 13, "test_tokens_window": 28, "test_tutorial_video": 5,
    "test_ui_shot_names": 10, "test_unified_workspace": 3, "test_v21_security": 18, "test_v3": 28, "test_v41": 29,
    "test_v42": 45, "test_v43": 37, "test_v5": 58, "test_v51": 73, "test_v510": 16, "test_v511": 13, "test_v52": 15,
    "test_v53": 23, "test_v54": 66, "test_v55": 36, "test_v57": 46, "test_v571": 22, "test_v57_install": 6,
    "test_v57_tools": 13, "test_v58": 9, "test_v59": 12, "test_v591": 5, "test_v592": 5,
    "test_wt_refused_identity": 14, "test_wt_resume_claim": 8
}
FROZEN_WINDOWS = {
    "mcp_tools": 104, "test_autopsy": 6, "test_banner_version": 2, "test_bb_flush_no_hooks": 49,
    "test_ci_shards": 33, "test_ci_tiers": 25, "test_ci_web_deps": 1, "test_claims_cache": 62,
    "test_claims_perf": 385, "test_claims_read": 102, "test_cli_spelling_hints": 46, "test_command_ledger": 154,
    "test_coordination": 196, "test_critic_stale_ui_only": 64, "test_cursor_skills_keep": 64,
    "test_dashboard_journey": 34, "test_dashboard_profiles": 22, "test_dashboard_truth": 32, "test_demo": 108,
    "test_deploy_python_stdlib": 3, "test_design_aspect": 7, "test_design_breed": 9, "test_design_breed_notes": 17,
    "test_design_breed_rules": 10, "test_design_breed_twins": 4, "test_design_brief_real": 1, "test_design_color": 8,
    "test_design_creativity": 9, "test_design_creativity_inherit": 4, "test_design_density": 23,
    "test_design_fonts": 3, "test_design_ground": 2, "test_design_lint_html": 5, "test_design_lint_scale": 12,
    "test_design_lock_round": 1, "test_design_metrics": 7, "test_design_perf": 33, "test_design_pick": 22,
    "test_design_prior": 2, "test_design_round": 4, "test_design_round_taste": 2, "test_design_shoot_full": 13,
    "test_design_shoot_qa": 12, "test_design_shoot_timeout": 8, "test_design_stage": 1, "test_design_taste": 1,
    "test_design_taste_cli": 4, "test_design_taste_team": 3, "test_direct_main": 143,
    "test_doctor_skills_compare": 67, "test_done_without_github": 68, "test_engine_messages_qa14": 92,
    "test_external_skills": 108, "test_flaky_guard": 208, "test_flaky_guard_race": 1278, "test_freeze_claim": 9,
    "test_gallery_lint": 1, "test_gate_scope": 12, "test_git_identity_msg": 25, "test_gitleaks_exception": 49,
    "test_guard_substitution": 27, "test_hack": 254, "test_harness_commands": 34, "test_harvest_discovery": 1,
    "test_hook_claims": 63, "test_hook_session_start_speed": 316, "test_hooks_health": 194,
    "test_install_claude_only": 88, "test_install_light": 116, "test_integrate_on_main": 146,
    "test_integrate_outside": 147, "test_integrate_unreviewed": 420, "test_landing_skills": 1,
    "test_lint_paths_hint": 41, "test_manual_notes": 104, "test_mcp_runs_commands": 1, "test_merge_affected": 129,
    "test_merge_commit_field": 455, "test_merge_engine_policy": 905, "test_merge_renewer_orphan": 66,
    "test_metrics": 5, "test_next_prefilter": 59, "test_next_reviewer": 42, "test_one_live_renew": 99,
    "test_plan_amend_overlap": 63, "test_plan_check": 56, "test_plan_owners": 53, "test_plan_scale": 22,
    "test_policy": 1, "test_pre_push": 230, "test_q_string": 3, "test_read_cache": 192, "test_review_identity": 32,
    "test_review_merge": 380, "test_review_substates": 330, "test_review_unseen_approval": 72,
    "test_reviewer_next": 48, "test_setup_branches": 57, "test_setup_feedback": 4, "test_setup_first_run": 59,
    "test_setup_forms": 11, "test_setup_guide": 74, "test_setup_language": 10, "test_setup_planning": 141,
    "test_setup_prepare": 283, "test_setup_processes": 140, "test_setup_resume": 60, "test_setup_roles": 97,
    "test_setup_team": 207, "test_setup_trust": 330, "test_setup_tutorial": 2, "test_setup_wizard": 55,
    "test_skills_windows_clone": 116, "test_smoke_affected": 244, "test_smoke_env": 2, "test_smoke_onboarding": 155,
    "test_smoke_parallel": 27, "test_snapshot": 12, "test_start_version_gate": 143, "test_status_planned": 51,
    "test_task_participants": 57, "test_task_timeline": 2, "test_temp_and_timeouts": 21, "test_tokens_coverage": 83,
    "test_tokens_elsewhere": 71, "test_tokens_window": 186, "test_tutorial_video": 13, "test_ui_shot_names": 45,
    "test_unified_workspace": 2, "test_v21_security": 100, "test_v3": 182, "test_v41": 149, "test_v42": 213,
    "test_v43": 216, "test_v5": 210, "test_v51": 374, "test_v510": 82, "test_v511": 84, "test_v52": 79,
    "test_v53": 127, "test_v54": 196, "test_v55": 198, "test_v57": 300, "test_v571": 104, "test_v57_install": 36,
    "test_v57_tools": 76, "test_v58": 60, "test_v59": 70, "test_v591": 44, "test_v592": 31,
    "test_wt_refused_identity": 86, "test_wt_resume_claim": 55
}
NEW_SINCE_FREEZE = {"test_ci_timings"}  # this file's own entry; a later task's test is not in the frozen tables either


_cache = {}


def load(name, path):
    if name not in _cache:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _cache[name] = mod
    return _cache[name]


def lint_module():
    return load("kit_lint_for_timings", REPO / "scripts" / "kit_lint.py")


def select_module():
    return load("ci_select_for_timings", REPO / "scripts" / "ci_select.py")


def source_repository(r):
    return (REPO / "scripts" / "kit_lint.py").is_file()


def write(folder, name, text):
    (folder / name).write_text(text, encoding="utf-8", newline="\n")


def tables_equal_before_and_after(r):
    lint = lint_module()
    for label, frozen, real in (("CI_SECONDS", FROZEN_CI, lint.CI_SECONDS), ("CI_WINDOWS_SECONDS", FROZEN_WINDOWS, lint.CI_WINDOWS_SECONDS)):
        expect(len(frozen) == 152, "the frozen copy has the 152 entries of main: %d" % len(frozen))
        for t in sorted(frozen):
            expect(real.get(t) == frozen[t], "%s[%s] was %d, is %s" % (label, t, frozen[t], real.get(t)))
        extra = set(real) - set(frozen)
        expect(extra <= NEW_SINCE_FREEZE or all((REPO / "kit/.uak/tests" / (t + ".py")).is_file() or t == "mcp_tools" for t in extra),
               "%s has entries that are not test files: %s" % (label, sorted(extra)))
        expect(NEW_SINCE_FREEZE <= set(real), "%s has this test's own entry" % label)
    for t in sorted(FROZEN_CI):
        expect(lint.ci_seconds(t) == FROZEN_CI[t] and lint.ci_windows_seconds(t) == FROZEN_WINDOWS[t], "ci_seconds / ci_windows_seconds of %s" % t)
    expect(lint.ci_seconds("test_never_measured") == 60 and lint.ci_windows_seconds("test_never_measured") == 300, "an unmeasured file keeps its defaults")
    files_ = sorted(p.stem for p in TIMINGS.glob("*.txt"))
    expect(files_ == sorted(lint.CI_SECONDS) == sorted(lint.CI_WINDOWS_SECONDS), "one file per entry, both tables from the same folder")
    return "%d entries, both tables" % len(FROZEN_CI)


def test_without_timing_file_is_named(r):
    lint = lint_module()
    real = lint.ci_tests()
    expect(lint.timing_problems(real) == [], "the real folder has no gap: %s" % lint.timing_problems(real))
    got = lint.timing_problems(real + ["test_added_later"])
    expect(len(got) == 1 and "kit/.uak/tests/timings/test_added_later.txt" in got[0], "the finding names the file to create: %s" % got)
    expect("CI_SECONDS" in got[0] and "CI_WINDOWS_SECONDS" in got[0], "and both tables: %s" % got)
    expect(any("no-timing" in x for x in got), "with its rule id: %s" % got)
    src = (REPO / "scripts" / "kit_lint.py").read_text(encoding="utf-8")
    expect("timing_file_problems(" in src.split("def check_test_discovery", 1)[1].split("def check_structure", 1)[0],
           "check_test_discovery runs the reader's findings too")
    return "named"


def timing_file_without_test_is_refused(r):
    lint = lint_module()
    with tempfile.TemporaryDirectory(prefix="uak-timings-") as tmp:
        d = Path(tmp)
        write(d, "test_gate_scope.txt", "ci 3\nwindows 12\n")
        write(d, "test_removed_long_ago.txt", "ci 5\nwindows 9\n")
        ci, win, problems = lint.read_timings(d)
        expect(problems == [], "both files read: %s" % problems)
        got = lint.timing_problems(["test_gate_scope"], seconds=ci, windows=win)
        expect(len(got) == 2 and all("test_removed_long_ago" in x and "stale" in x for x in got), "the file of a missing test is refused in both tables: %s" % got)
        expect(all("timings/test_removed_long_ago.txt" in x for x in got), "and the finding names the file to remove: %s" % got)
        write(d, "mcp_tools.txt", "ci 17\nwindows 104\n")
        ci, win, problems = lint.read_timings(d)
        expect(len(lint.timing_problems(["test_gate_scope", "mcp_tools"], seconds=ci, windows=win)) == 2, "mcp_tools is not a stale name")
    return "stale file named"


def unreadable_timing_line_is_refused(r):
    lint = lint_module()
    bad = [("not a word", "ci fast\nwindows 5\n", "ci fast"),
           ("zero", "ci 0\nwindows 5\n", "ci 0"),
           ("over an hour", "ci 5\nwindows 3601\n", "windows 3601"),
           ("not whole", "ci 1.5\nwindows 5\n", "ci 1.5"),
           ("negative", "ci 5\nwindows -3\n", "windows -3"),
           ("unknown key", "ci 5\nwindows 5\nmacos 7\n", "macos 7"),
           ("two ci lines", "ci 5\nci 6\nwindows 5\n", "ci 6"),
           ("two windows lines", "ci 5\nwindows 5\nwindows 6\n", "windows 6"),
           ("no number", "ci\nwindows 5\n", "ci")]
    with tempfile.TemporaryDirectory(prefix="uak-timings-") as tmp:
        d = Path(tmp)
        write(d, "test_ok.txt", "# why: measured on 12 runs\n\nci 3600\nwindows 1\n# another note\n")
        write(d, "test_crlf.txt", "ci 4\r\nwindows 8\r\n")
        ci, win, problems = lint.read_timings(d)
        expect(problems == [] and ci == {"test_ok": 3600, "test_crlf": 4} and win == {"test_ok": 1, "test_crlf": 8},
               "comments, blank lines, bounds 1 and 3600 and CRLF are read: %s %s %s" % (problems, ci, win))
        for why, text, needle in bad:
            sub = d / why.replace(" ", "_")
            sub.mkdir()
            write(sub, "test_x.txt", text)
            ci, win, problems = lint.read_timings(sub)
            expect(len(problems) == 1 and "test_x.txt" in problems[0] and needle in problems[0] and "bad-timing" in problems[0],
                   "%s: one finding that names the file and the line: %s" % (why, problems))
        sub = d / "other"
        sub.mkdir()
        write(sub, "notes.md", "ci 5\n")
        expect(len(lint.read_timings(sub)[2]) == 1, "a file that is not NAME.txt is refused")
    expect(lint.TIMING_FILE_PROBLEMS == [], "the real folder reads clean: %s" % lint.TIMING_FILE_PROBLEMS)
    return "%d bad shapes" % len(bad)


def shards_are_unchanged(r):
    lint = lint_module()

    def old(frozen, now):
        return lambda t: frozen[t] if t in frozen else now(t)
    mac, win = old(FROZEN_CI, lint.ci_seconds), old(FROZEN_WINDOWS, lint.ci_windows_seconds)
    tests = lint.ci_tests()
    for n in (3, 4, 5, 6, 8):
        got = lint.ci_shards(n)
        expect(got == lint._split([t for t in tests if t != "mcp_tools"], n, mac), "the %d macOS and Linux shards are the lists the frozen seconds make" % n)
        expect(sum(len(s["tests"].split()) for s in got) == len(tests) - 1, "every file is in one of the %d shards" % n)
        expect(lint.ci_windows_shards(n) == lint._split(tests, n, win), "the %d Windows shards are the lists the frozen seconds make" % n)
    k = lint.windows_shard_count()
    expect(lint.ci_windows_shards(k) == lint._split(tests, k, win), "and at the count CI uses (%d)" % k)
    return "5 sizes and %d Windows shards" % k


def timings_are_not_installed(r):
    d = repo(r, "timings")
    install(r, d, "--mode", "sprint")
    fs = [p.relative_to(d).as_posix() for p in files(d)]
    expect(not any("timings" in x for x in fs), "no timing file in a light install: %s" % [x for x in fs if "timings" in x][:3])
    expect(not (d / ".uak/tests").exists(), "and no tests folder")
    w = repo(r, "timings-with-tests")
    install(r, w, "--mode", "sprint", "--with-tests")
    ws = [p.relative_to(w).as_posix() for p in files(w)]
    expect(any(x.startswith(".uak/tests/test_") for x in ws), "--with-tests still brings the tests")
    expect(not any("/timings/" in x for x in ws), "but not their timings: only the kit's CI reads them")
    return "%d files, none a timing" % len(fs)


def timing_only_change_is_first_tier(r):
    sel = select_module()
    changed = [("M", "kit/.uak/tests/timings/test_v59.txt")]
    tier, why = sel.decide("pull_request", [], "", changed)
    expect(tier == "first", "a pull request that changes a timing file runs the first tier: %s %s" % (tier, why))
    got = sel.select(changed)
    expect(got["withheld"] == [], "nothing is withheld to main (a file under tests/ that is not a test used to ask for everything): %s" % got["withheld"])
    expect("test_v59" in got["macos"] and "test_v59" in got["windows"], "the test whose timing changed runs on both systems: %s" % sorted(got["macos"]))
    expect("timing" in " ".join(got["windows"]["test_v59"]), "and says why: %s" % got["windows"]["test_v59"])
    added = sel.select([("A", "kit/.uak/tests/timings/test_hack.txt")])
    expect("test_hack" in added["windows"] and added["withheld"] == [], "a new timing file runs its test too")
    gone = sel.select([("D", "kit/.uak/tests/timings/test_v59.txt")])
    expect(set(gone["windows"]) <= set(sel.lint.PORTABILITY_SET) | {"test_v59"}, "and nothing odd: %s" % sorted(gone["windows"]))
    m = sel.matrices(tier, got)
    expect(sel.job_count(m) <= 9, "at most nine jobs: %d" % sel.job_count(m))
    return "first tier, test_v59 selected"


TESTS = [tables_equal_before_and_after, test_without_timing_file_is_named, timing_file_without_test_is_refused,
         unreadable_timing_line_is_refused, shards_are_unchanged, timings_are_not_installed, timing_only_change_is_first_tier]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    if not source_repository(None):
        print("CI_TIMINGS_RESULT PASS passed=0 failed=0 (no kit source repository here: the timings are read by its scripts/kit_lint.py)")
        return 0
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-ci-timings-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ not in args.case:
                continue
            started = time.monotonic()
            try:
                note = test(runner)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started))
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("CI_TIMINGS_RESULT %s passed=%d failed=%d" % ("PASS" if not fails else "FAIL", len(TESTS) - fails, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
