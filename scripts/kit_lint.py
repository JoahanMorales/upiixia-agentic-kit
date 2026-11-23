#!/usr/bin/env python3
"""kit_lint: the kit's own rules as checks, not prose. Run in CI and before every push:

    python3 scripts/kit_lint.py            # exit 1 on any finding
    python3 scripts/kit_lint.py --list     # the rules and the incident behind each

Why: the portability rules lived in AGENTS.md and CONTRIBUTING.md, and every one of them was broken at least once
(an awk interval mawk ignores, a BSD sed without \\|, `awk -W version` hanging on macOS, a `${s//[class]/}` that took
47 s on bash 3.2). A rule in prose is a suggestion; this file makes each one fail the build. A deliberate exception
carries `kit-lint: ok (why)` on the same line or the line above.
Structure checks keep the pieces in step: every command documented, every test file registered and run in CI, every
installed skill vendored and recorded.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "kit/.uak/bin"

# (id, regex on a code line, message with the incident). Code lines only: comments are skipped.
PORTABILITY = [
    ("bash4-assoc", r"\bdeclare\s+-A\b|\blocal\s+-A\b", "associative arrays need bash 4; macOS ships 3.2"),
    ("bash4-mapfile", r"\b(mapfile|readarray)\b", "mapfile/readarray need bash 4; macOS ships 3.2"),
    ("bash4-case", r"\$\{[A-Za-z_][A-Za-z0-9_]*(,,|\^\^)\}", "${x,,} / ${x^^} need bash 4: use tr"),
    ("bash4-redirect", r"&>>|\|&", "&>> and |& need bash 4"),
    ("bash4-nameref", r"\blocal\s+-n\b|\bdeclare\s+-n\b", "namerefs need bash 4.3"),
    ("bash4-coproc", r"\bcoproc\b", "coproc needs bash 4"),
    ("bash5-epoch", r"\$\{?EPOCH(SECONDS|REALTIME)", "EPOCHSECONDS needs bash 5: guard it with BASH_VERSINFO (hook does)"),
    ("bash42-printf-time", r"printf\s+(-v\s+\S+\s+)?'%\(", "printf %()T needs bash 4.2: guard it with BASH_VERSINFO"),
    ("gnu-readlink", r"\breadlink\s+-[a-z]*f", "readlink -f is GNU: use cd \"$d\" && pwd -P"),
    ("gnu-date", r"\bdate\s+(-d|--date)\b", "date -d is GNU: BSD date takes -r or -j"),
    ("gnu-grep-P", r"\bgrep\s+(-[A-Za-z]*P|--perl)", "grep -P is GNU (and absent on macOS): use grep -E"),
    ("gnu-sed-alt", r"\bsed\s+(-n\s+)?(\"|')[^\"']*\\\|", "BSD sed has no \\| in a basic regex: use sed -E with |"),
    ("gnu-sed-i", r"\bsed\s+-i\s+(\"|'|-e)", "sed -i differs between GNU and BSD: write to a temp file and mv"),
    ("gnu-stat", r"\bstat\s+(-c|--format)\b", "stat -c is GNU: BSD stat takes -f"),
    ("gnu-find-printf", r"\bfind\b.*\s-printf\b", "find -printf is GNU"),
    ("gnu-xargs-r", r"\bxargs\s+(-[A-Za-z]*r|--no-run-if-empty)", "xargs -r is GNU"),
    ("gnu-sort-V", r"\bsort\s+(-[A-Za-z]*V|--version-sort)", "sort -V is GNU and missing on old macOS: compare numerically (start's vnum)"),
    ("gnu-head-neg", r"\bhead\s+-n\s+-[0-9]", "head -n -N is GNU"),
    ("awk-gensub", r"\bgensub\s*\(", "gensub is gawk only"),
    ("awk-version-probe", r"awk\s+-W\s+version", "BSD awk -W version waits on stdin and hung doctor on macOS (v5.4.3): run it with < /dev/null"),
    ("echo-e", r"\becho\s+-e\b", "echo -e prints -e under sh and differs across shells: use printf"),
    # One reader of PROJECT.md keys (v5.11): 13 copies disagreed on spaces, backticks and which file they read.
    ("config-reader-copy", r"sed\s+-n\s+[\"']s/\^\[-\* \]\*|\$\{line%%\[!-\* \]\*\}", "a copy of the PROJECT.md key reader: use uak_cfg FILE KEY [DEFAULT] from lib/config.sh"),
    # bash 3.2 makes ${s//pattern/…} cost matches × length (437 s at 18 KB): a class pattern on an unbounded string.
    ("bash32-class-subst", r"\$\{[A-Za-z_][A-Za-z0-9_]*//(\[|\$P_)", "a class pattern in ${s//…} is quadratic on bash 3.2 (47 s on a heredoc, v5.10): bound the length (guard's SHORT) or use tr; mark kit-lint: ok when the string is short by construction"),
]
AWK_INTERVAL = re.compile(r"awk[^|]*'[^']*/[^/']*\{[0-9]+(,[0-9]*)?\}[^/']*/")


def code_lines(path):
    """(number, line, the two lines before) of the lines that are code, with the exception marker honored."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for n, line in enumerate(lines, 1):
        before = "\n".join(lines[max(0, n - 3):n - 1])
        ok = "kit-lint: ok" in line or "kit-lint: ok" in (lines[n - 2] if n > 1 else "")
        if line.lstrip().startswith("#") or ok:
            continue
        yield n, line, before


def unquoted(line):
    return re.sub(r"'[^']*'", "''", line)


def bash_scripts():
    for p in sorted(BIN.iterdir()) + sorted((BIN / "lib").glob("*.sh")) + [ROOT / "install.sh"]:
        if p.is_file() and p.suffix not in (".py", ".html", ".awk", ".pyc") and p.name != "uak-mcp":
            head = p.read_bytes()[:200]
            if b"bash" in head or p.suffix == ".sh":
                yield p


def check_portability(findings):
    for p in bash_scripts():
        rel = p.relative_to(ROOT)
        for n, line, before in code_lines(p):
            for rid, rx, msg in PORTABILITY:
                text = unquoted(line) if rid.startswith("bash4") else line
                if not re.search(rx, text):
                    continue
                # A GNU form with its BSD fallback on the same line (`date -d … || date -j …`) is the portable idiom.
                if rid.startswith("gnu-") and "||" in line:
                    continue
                if rid in ("bash5-epoch", "bash42-printf-time") and "BASH_VERSINFO" in line + before:
                    continue
                if rid == "awk-version-probe" and re.search(r"<\s*/dev/null", line):
                    continue
                if rid == "bash32-class-subst" and "SHORT" in line:
                    continue
                if rid == "config-reader-copy" and p.name == "config.sh":
                    continue
                findings.append("%s:%d · %s · %s" % (rel, n, rid, msg))
            if AWK_INTERVAL.search(line):
                findings.append("%s:%d · awk-interval · mawk ignores {n} intervals in awk regexes: use grep -E" % (rel, n))
        if p.read_bytes().find(b"\r\n") >= 0:
            findings.append("%s · crlf · a CRLF script fails under bash on Linux and WSL" % rel)
        r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
        if r.returncode != 0:
            findings.append("%s · syntax · bash -n: %s" % (rel, r.stderr.strip()[:200]))


def ci_tests():
    """The Windows matrix: one job per kit/.uak/tests/test_*.py (C order), plus the MCP tools of tests/."""
    return sorted(t.stem for t in (ROOT / "kit/.uak/tests").glob("test_*.py")) + ["mcp_tools"]


# Seconds each test file took on the CI runners, the median of its group in the job logs of the 12 latest runs on main and
# pull requests (2026-11-22, newest 45037067147; the 6 latest for files that grew: test_review_substates, test_read_cache,
# test_tokens_window, test_hooks_health, test_flaky_guard; UAK-144). Two tables because the platforms disagree by file: test_design_pick
# takes 439 s on macOS and 22 s on Windows, test_flaky_guard 508 s and 1500 s. CI_SECONDS is the macOS time and
# balances the Linux and macOS shards; CI_WINDOWS_SECONDS is the Windows time (mcp_tools is tests/test_mcp_tools.py).
# The lint refuses a test file with no entry in both (timing_problems): UAK-141's table had none for test_flaky_guard, it
# counted the default 60 s and ran 25 min on Windows and 8 min on macOS. To measure again, take each file's group time
# (from its ::group:: line to its ::endgroup:: line) in `gh run view RUN --log --job JOB` of recent runs on main.
CI_SECONDS = {
    "test_flaky_guard_race": 441, "test_design_pick": 439, "test_merge_engine_policy": 186, "test_flaky_guard": 101,
    "test_setup_prepare": 96, "test_review_merge": 93, "test_merge_commit_field": 91, "test_review_substates": 90,
    "test_claims_perf": 84, "test_v51": 73, "test_design_taste_cli": 72, "test_hook_session_start_speed": 72,
    "test_integrate_unreviewed": 72, "test_setup_team": 68, "test_design_perf": 67, "test_v54": 66,
    "test_smoke_onboarding": 62, "test_hack": 61, "test_setup_planning": 59, "test_smoke_affected": 58, "test_v5": 58,
    "test_command_ledger": 46, "test_v57": 46, "test_design_shoot_qa": 45, "test_v42": 45, "test_design_color": 43,
    "test_design_metrics": 39, "test_pre_push": 39, "test_design_taste_team": 37, "test_v43": 37, "test_v55": 36,
    "test_coordination": 35, "test_read_cache": 35, "test_hooks_health": 34, "test_merge_renewer_orphan": 30,
    "test_setup_roles": 30, "test_tokens_coverage": 29, "test_v41": 29, "test_integrate_on_main": 28,
    "test_tokens_window": 28, "test_v3": 28, "test_setup_guide": 27, "test_start_version_gate": 26,
    "test_dashboard_profiles": 25, "test_demo": 25, "test_direct_main": 25, "test_setup_resume": 25,
    "test_setup_wizard": 25, "test_merge_affected": 24, "test_v53": 23, "test_design_density": 22,
    "test_engine_messages_qa14": 22, "test_install_claude_only": 22, "test_integrate_outside": 22, "test_v571": 22,
    "test_skills_windows_clone": 21, "test_done_without_github": 20, "test_setup_branches": 20, "test_claims_read": 19,
    "test_setup_first_run": 19, "test_dashboard_journey": 18, "test_install_light": 18, "test_v21_security": 18,
    "mcp_tools": 17, "test_bb_flush_no_hooks": 16, "test_design_breed_notes": 16, "test_manual_notes": 16,
    "test_review_unseen_approval": 16, "test_v510": 16, "test_external_skills": 15, "test_one_live_renew": 15,
    "test_v52": 15, "test_dashboard_truth": 14, "test_plan_amend_overlap": 14, "test_wt_refused_identity": 14,
    "test_next_reviewer": 13, "test_reviewer_next": 13, "test_tokens_elsewhere": 13, "test_v511": 13,
    "test_v57_tools": 13, "test_cursor_skills_keep": 12, "test_gitleaks_exception": 12, "test_hook_claims": 12,
    "test_v59": 12, "test_critic_stale_ui_only": 11, "test_doctor_skills_compare": 11, "test_plan_check": 11,
    "test_design_shoot_full": 10, "test_next_prefilter": 10, "test_status_planned": 10, "test_ui_shot_names": 10,
    "test_claims_cache": 9, "test_design_shoot_timeout": 9, "test_setup_trust": 80, "test_task_participants": 9,
    "test_v58": 9, "test_design_breed": 8, "test_lint_paths_hint": 8, "test_plan_owners": 8, "test_wt_resume_claim": 8,
    "test_cli_spelling_hints": 7, "test_design_aspect": 7, "test_plan_scale": 7, "test_setup_forms": 7,
    "test_smoke_parallel": 7, "test_design_breed_rules": 6, "test_design_creativity": 6, "test_git_identity_msg": 6,
    "test_harness_commands": 6, "test_review_identity": 6, "test_v57_install": 6, "test_ci_shards": 19, "test_ci_tiers": 8,
    "test_guard_substitution": 5, "test_setup_language": 5, "test_tutorial_video": 5, "test_v591": 5, "test_v592": 5,
    "test_autopsy": 4, "test_setup_tutorial": 4, "test_temp_and_timeouts": 4, "test_design_breed_twins": 3,
    "test_design_creativity_inherit": 3, "test_design_fonts": 3, "test_design_ground": 3, "test_design_round": 3,
    "test_freeze_claim": 3, "test_gate_scope": 3, "test_metrics": 3, "test_unified_workspace": 3,
    "test_deploy_python_stdlib": 2, "test_design_lint_scale": 2, "test_design_prior": 2, "test_design_round_taste": 2,
    "test_design_taste": 2, "test_setup_feedback": 2, "test_smoke_env": 2, "test_snapshot": 2, "test_task_timeline": 2,
    "test_banner_version": 1, "test_ci_web_deps": 1, "test_design_brief_real": 1, "test_design_lint_html": 1,
    "test_design_lock_round": 1, "test_design_stage": 1, "test_gallery_lint": 1, "test_harvest_discovery": 1,
    "test_landing_skills": 1, "test_mcp_runs_commands": 1, "test_policy": 1, "test_q_string": 1
}
CI_WINDOWS_SECONDS = {
    "test_flaky_guard_race": 1278, "test_merge_engine_policy": 905, "test_merge_commit_field": 455,
    "test_integrate_unreviewed": 420, "test_claims_perf": 385, "test_review_merge": 380, "test_v51": 374,
    "test_review_substates": 330, "test_hook_session_start_speed": 316, "test_v57": 300, "test_setup_prepare": 283,
    "test_hack": 254, "test_smoke_affected": 244, "test_pre_push": 230, "test_v43": 216, "test_v42": 213,
    "test_v5": 210, "test_flaky_guard": 208, "test_setup_team": 207, "test_v55": 198, "test_coordination": 196,
    "test_v54": 196, "test_hooks_health": 194, "test_read_cache": 192, "test_tokens_window": 186, "test_v3": 182,
    "test_smoke_onboarding": 155, "test_command_ledger": 154, "test_v41": 149, "test_integrate_outside": 147,
    "test_integrate_on_main": 146, "test_direct_main": 143, "test_start_version_gate": 143, "test_setup_planning": 141,
    "test_merge_affected": 129, "test_v53": 127, "test_install_light": 116, "test_skills_windows_clone": 116,
    "test_demo": 108, "test_external_skills": 108, "mcp_tools": 104, "test_manual_notes": 104, "test_v571": 104,
    "test_claims_read": 102, "test_v21_security": 100, "test_one_live_renew": 99, "test_setup_roles": 97,
    "test_engine_messages_qa14": 92, "test_install_claude_only": 88, "test_wt_refused_identity": 86, "test_v511": 84,
    "test_tokens_coverage": 83, "test_v510": 82, "test_v52": 79, "test_v57_tools": 76, "test_setup_guide": 74,
    "test_review_unseen_approval": 72, "test_tokens_elsewhere": 71, "test_v59": 70, "test_done_without_github": 68,
    "test_doctor_skills_compare": 67, "test_merge_renewer_orphan": 66, "test_critic_stale_ui_only": 64,
    "test_cursor_skills_keep": 64, "test_hook_claims": 63, "test_plan_amend_overlap": 63, "test_claims_cache": 62,
    "test_setup_resume": 60, "test_v58": 60, "test_next_prefilter": 59, "test_setup_first_run": 59,
    "test_setup_branches": 57, "test_task_participants": 57, "test_plan_check": 56, "test_setup_wizard": 55,
    "test_wt_resume_claim": 55, "test_plan_owners": 53, "test_status_planned": 51, "test_bb_flush_no_hooks": 49,
    "test_gitleaks_exception": 49, "test_reviewer_next": 48, "test_cli_spelling_hints": 46, "test_ui_shot_names": 45,
    "test_v591": 44, "test_next_reviewer": 42, "test_lint_paths_hint": 41, "test_v57_install": 36,
    "test_dashboard_journey": 34, "test_harness_commands": 34, "test_design_perf": 33, "test_dashboard_truth": 32,
    "test_review_identity": 32, "test_v592": 31, "test_guard_substitution": 27, "test_smoke_parallel": 27,
    "test_git_identity_msg": 25, "test_design_density": 23, "test_dashboard_profiles": 22, "test_design_pick": 22,
    "test_plan_scale": 22, "test_setup_trust": 240, "test_temp_and_timeouts": 21, "test_ci_shards": 33, "test_ci_tiers": 25,
    "test_design_breed_notes": 17, "test_design_shoot_full": 13, "test_tutorial_video": 13,
    "test_design_lint_scale": 12, "test_design_shoot_qa": 12, "test_gate_scope": 12, "test_snapshot": 12,
    "test_setup_forms": 11, "test_design_breed_rules": 10, "test_setup_language": 10, "test_design_breed": 9,
    "test_design_creativity": 9, "test_freeze_claim": 9, "test_design_color": 8, "test_design_shoot_timeout": 8,
    "test_design_aspect": 7, "test_design_metrics": 7, "test_autopsy": 6, "test_design_lint_html": 5, "test_metrics": 5,
    "test_design_breed_twins": 4, "test_design_creativity_inherit": 4, "test_design_round": 4,
    "test_design_taste_cli": 4, "test_setup_feedback": 4, "test_deploy_python_stdlib": 3, "test_design_fonts": 3,
    "test_design_taste_team": 3, "test_q_string": 3, "test_banner_version": 2, "test_design_ground": 2,
    "test_design_prior": 2, "test_design_round_taste": 2, "test_setup_tutorial": 2, "test_smoke_env": 2,
    "test_task_timeline": 2, "test_unified_workspace": 2, "test_ci_web_deps": 1, "test_design_brief_real": 1,
    "test_design_lock_round": 1, "test_design_stage": 1, "test_design_taste": 1, "test_gallery_lint": 1,
    "test_harvest_discovery": 1, "test_landing_skills": 1, "test_mcp_runs_commands": 1, "test_policy": 1
}


def ci_seconds(test):
    return CI_SECONDS.get(test, 60)


def ci_windows_seconds(test):
    return CI_WINDOWS_SECONDS.get(test, ci_seconds(test) * 5)


# A test file over half of WINDOWS_BOUND_S cannot share a shard with anything else and one slow measurement turns it red:
# the lint says to split it (UAK-150). These files are over and are not split yet: each entry says why and what follows.
# Not a way to raise the limit: a new file over half is refused, and an entry whose file is not over half any more is
# reported (so the list shrinks as files are split).
HALF_BOUND_EXCEPTIONS = {
    "test_merge_engine_policy": "905 s on Windows, 5 s over the limit: not split yet (a task of its own, outside UAK-150's paths); until then it takes a shard with little else",
    "test_flaky_guard_race": "870 to 1363 s on Windows: twenty_runs_under_load, 60 runs under CPU hogs in one case. UAK-151 tried one case per kind with background jobs of the other kinds: lease alone took 862, 1175 and 1336 s, and the two files together 1700 to 1900 s against 1090 to 1580 s before, so no two-file split gets under 900 s; it needs a third file or fewer lease runs, a decision for a human",
}


# The fixed portability set of the first tier (UAK-168): a pull request runs these on macOS and Windows whatever it changes,
# because the failures that only those systems show come from a few things and these files are the cheapest that cover each.
# At most PORTABILITY_MAX files, each under PORTABILITY_WINDOWS_MAX_S on Windows, each with its reason; the lint refuses a
# file that is missing, too slow or without a reason (portability_problems).
PORTABILITY_MAX = 6
PORTABILITY_WINDOWS_MAX_S = 120
PORTABILITY_SET = {
    "test_temp_and_timeouts": "paths with a space and an accent in the temp directory, as on C:\\Users\\José Pérez",
    "test_skills_windows_clone": "symlinks: Git for Windows checks them out as text files (core.symlinks=false)",
    "test_gate_scope": "Bash 3.2 (no $BASHPID, no bash 4 features) and case folding with accents in paths",
    "test_snapshot": "CRLF: task and claim records checked out with Windows line endings",
    "test_v571": "case-insensitive names: accented capitals in Paths on macOS and Windows file systems",
    "test_merge_renewer_orphan": "process groups: a killed merge must not leave its background renewer running",
}


def portability_problems(tests, table=None, windows=None):
    """Findings about the portability set: a file that does not exist, over PORTABILITY_WINDOWS_MAX_S on Windows, with no
    reason, or more than PORTABILITY_MAX files."""
    table = PORTABILITY_SET if table is None else table
    windows = CI_WINDOWS_SECONDS if windows is None else windows
    out = []
    if len(table) > PORTABILITY_MAX:
        out.append("scripts/kit_lint.py · portability-set · %d files, at most %d" % (len(table), PORTABILITY_MAX))
    for t in sorted(table):
        if t not in tests:
            out.append("scripts/kit_lint.py · portability-missing · %s is in PORTABILITY_SET but is not a test file" % t)
        elif windows.get(t, 0) >= PORTABILITY_WINDOWS_MAX_S:
            out.append("scripts/kit_lint.py · portability-slow · %s takes %d s on Windows, not under %d: choose a cheaper file" % (t, windows.get(t, 0), PORTABILITY_WINDOWS_MAX_S))
        if not str(table[t]).strip():
            out.append("scripts/kit_lint.py · portability-reason · %s is in PORTABILITY_SET with no reason" % t)
    return out


def path_filter_problems(text):
    """No trigger of the workflow is filtered by path: a required check of a workflow that did not run stays Pending and
    blocks the merge (GitHub's documentation on skipped required checks). The workflow runs and decides inside."""
    head = "\n".join(re.sub(r"(^|\s)#.*$", "", l) for l in text.split("\njobs:")[0].splitlines())
    if re.search(r"(?m)^\s*paths(-ignore)?:|[{,]\s*paths(-ignore)?:", head):
        return [".github/workflows/test.yml · path-filter · a trigger has paths: or paths-ignore: a skipped workflow leaves its required check Pending; select inside the workflow (scripts/ci_select.py)"]
    return []


def workflow_tier_problems(text, select_src):
    """The two-tier shape: one final job `ci` that always runs and needs every job that runs tests, the label and the manual input."""
    out = []
    jobs = re.findall(r"(?m)^  ([a-z][a-z-]*):\n", text.split("\njobs:", 1)[1]) if "\njobs:" in text else []
    m = re.search(r"(?s)\n  ci:\n(.*?)(?=\n  [a-z][a-z-]*:\n|\Z)", text)
    if not m or not re.search(r"(?m)^    if: always\(\)\s*$", m.group(1)):
        out.append(".github/workflows/test.yml · no-final-job · the workflow needs one job `ci` with `if: always()`: it is the one check to require")
    else:
        need = re.search(r"(?m)^    needs: \[([^\]]*)\]", m.group(1))
        listed = {x.strip() for x in need.group(1).split(",")} if need else set()
        missing = sorted(set(jobs) - {"ci", "red-main"} - listed)
        if missing:
            out.append(".github/workflows/test.yml · final-job-needs · `ci` does not wait for %s" % ", ".join(missing))
    if "ci_select.py" not in text:
        out.append(".github/workflows/test.yml · no-selector · the discover job must decide the tier with scripts/ci_select.py")
    if "UAK_SMOKE_TESTS" not in select_src:
        out.append("scripts/ci_select.py · no-test-shards · the runner must pass each file to smoke in UAK_SMOKE_TESTS")
    return out


def timing_problems(tests, seconds=None, windows=None, exceptions=None):
    """Findings about the timing tables (the defaults hid a 25 minute file): a test file (or mcp_tools) missing from
    CI_SECONDS or CI_WINDOWS_SECONDS (the message names each table it is missing from); a file over half of
    WINDOWS_BOUND_S on Windows that is not in HALF_BOUND_EXCEPTIONS (split it); an exception that is not over half
    any more; and a stale entry, in either table, of a test file that no longer exists."""
    seconds = CI_SECONDS if seconds is None else seconds
    windows = CI_WINDOWS_SECONDS if windows is None else windows
    exceptions = HALF_BOUND_EXCEPTIONS if exceptions is None else exceptions
    half = WINDOWS_BOUND_S // 2
    out = []
    for t in tests:
        missing = [name for name, table in (("CI_SECONDS", seconds), ("CI_WINDOWS_SECONDS", windows)) if t not in table]
        if missing:
            out.append("scripts/kit_lint.py · no-timing · %s has no entry in %s: measure it (see the comment above CI_SECONDS)" % (t, " or ".join(missing)))
        elif windows[t] > half and t not in exceptions:
            out.append("scripts/kit_lint.py · over-half-the-bound · %s takes %d s on Windows, over half of WINDOWS_BOUND_S (%d s): split it" % (t, windows[t], half))
    for t in sorted(exceptions):
        if t in windows and windows[t] <= half:
            out.append("scripts/kit_lint.py · stale-exception · %s is in HALF_BOUND_EXCEPTIONS but takes %d s, not over %d: remove it" % (t, windows[t], half))
    for name, table in (("CI_SECONDS", seconds), ("CI_WINDOWS_SECONDS", windows)):
        for t in sorted(table):
            if t != "mcp_tools" and not (ROOT / "kit/.uak/tests" / (t + ".py")).is_file():
                out.append("scripts/kit_lint.py · stale-timing · %s has an entry in %s but no test file: remove it" % (t, name))
    return out


def ci_shards(n):
    """The suite's test files in n shards for the CI matrix, [{"n": 1, "tests": "test_a test_b"}, …]: longest first,
    each to the shard with the least seconds so far (ties to the lower shard), so every file is in exactly one."""
    return _split([t for t in ci_tests() if t != "mcp_tools"], n)


def _split(tests, n, seconds=None):
    seconds = seconds or ci_seconds
    load, picked = [0] * n, [[] for _ in range(n)]
    for t in sorted(tests, key=lambda x: (-seconds(x), x)):
        i = min(range(n), key=lambda k: (load[k], k))
        load[i] += seconds(t)
        picked[i].append(t)
    return [{"n": i + 1, "tests": " ".join(sorted(picked[i]))} for i in range(n)]


# A Windows shard's time is WINDOWS_SETUP_S (checkout and setup, about 15 s) plus the Windows seconds of its files
# (CI_WINDOWS_SECONDS, measured per file). The bound is 30 minutes, not UAK-128's 25: test_flaky_guard alone took 1496 s,
# and no split can put it under 25 (UAK-150 split it in two files). The longest shard must stay at or under WINDOWS_MARGIN of the bound (25.5 min against
# the job's 45 minute timeout, which is not raised), so noise does not turn the job red.
WINDOWS_SETUP_S = 15
WINDOWS_BOUND_S = 30 * 60
WINDOWS_MARGIN = 0.85
WINDOWS_MAX_SHARDS = 15   # 24 jobs a commit on main: discover (1) + 4 shards x 2 OS (8) + these



def push_trigger_problems(text):
    """A push trigger must name branches or tags: `on: [push, pull_request]` and a bare `push:` both run everything twice
    for a branch with a PR (audit v6.7 §1, UAK-141). Only the top-level `on:` key is read, comments are dropped, and a
    filter is a `branches:` or `tags:` key of the push trigger, not a word that appears in a value."""
    why = "runs everything twice for a branch with a PR: pull_request, and push on main and tags only"
    lines = [re.sub(r"(^|\s)#.*$", "", l).rstrip() for l in text.split("\njobs:")[0].splitlines()]
    for i, line in enumerate(lines):
        m = re.match(r"""^(?:on|"on"|'on'):[ \t]*(.*)$""", line)
        if not m:
            continue
        rest = m.group(1).strip()
        block = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and not nxt[0].isspace():
                break
            block.append(nxt)
        if rest.startswith("["):
            items = [x.strip(" '\"") for x in rest.strip("[]").split(",")]
            return ["`on: [push, ...]` " + why] if "push" in items else []
        if rest == "push":
            return ["`on: push` " + why]
        if rest.startswith("{"):
            block = [rest]
        for j, l in enumerate(block):
            pm = re.match(r"""^(\s*)(?:push|"push"|'push'):[ \t]*(.*)$""", l) if not rest.startswith("{") else \
                re.match(r"""^()\{.*?\bpush:[ \t]*(.*)$""", l)
            if not pm:
                continue
            sub = [pm.group(2)]
            for nxt in block[j + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= len(pm.group(1)):
                    break
                sub.append(nxt)
            if not re.search(r"(?m)(^|[{,])\s*(branches|tags)\s*:", "\n".join(sub)):
                return ["`push:` names no branches or tags: it " + why]
        return []
    return []


def ci_windows_shards(n):
    """Every test file plus mcp_tools in n Windows shards, balanced like ci_shards."""
    return _split(ci_tests(), n, ci_windows_seconds)


def windows_seconds(shard):
    return WINDOWS_SETUP_S + sum(ci_windows_seconds(t) for t in shard["tests"].split())


def windows_shard_count():
    """The smallest shard count whose longest shard stays under WINDOWS_MARGIN of WINDOWS_BOUND_S (capped at WINDOWS_MAX_SHARDS)."""
    total = len(ci_tests())
    for n in range(1, min(total, WINDOWS_MAX_SHARDS) + 1):
        if max(windows_seconds(s) for s in ci_windows_shards(n)) <= WINDOWS_BOUND_S * WINDOWS_MARGIN:
            return n
    return min(total, WINDOWS_MAX_SHARDS)


def check_test_discovery(findings):
    """smoke and CI find the test files themselves: no hand-kept list to forget (a list made every task that added a
    test edit the workflow, and the merge gate sends every workflow change to a human)."""
    smoke = (BIN / "smoke").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    if "ls -1 .uak/tests" not in smoke or "^test_[A-Za-z0-9_]+[.]py$" not in smoke:
        findings.append("kit/.uak/bin/smoke · no-test-discovery · --package-only must run every .uak/tests/test_*.py it finds")
    listed = sorted(set(re.findall(r"\.uak/tests/(test_\w+)\.py", smoke)))
    if listed:
        findings.append("kit/.uak/bin/smoke · hand-kept-tests · names %s: let the discovery run them" % ", ".join(listed))
    if "python3 scripts/kit_lint.py --ci-windows" not in ci or "fromJSON(needs.discover.outputs.wshards)" not in ci:
        findings.append(".github/workflows/test.yml · no-test-discovery · the Windows shards must come from the discover job (kit_lint.py --ci-windows)")
    findings.extend(".github/workflows/test.yml · double-run · " + x for x in push_trigger_problems(ci))
    findings.extend(timing_problems(ci_tests()))
    # The macOS and Linux suites run in shards (UAK-018): their lists come from --ci-shards, and smoke must run only them.
    select_src = (ROOT / "scripts/ci_select.py").read_text(encoding="utf-8") if (ROOT / "scripts/ci_select.py").is_file() else ""
    findings.extend(portability_problems(ci_tests()))
    findings.extend(path_filter_problems(ci))
    findings.extend(workflow_tier_problems(ci, select_src))
    if "python3 scripts/kit_lint.py --ci-shards" not in ci or "fromJSON(needs.discover.outputs.shards)" not in ci \
            or "SHARD_TESTS: ${{ matrix.shard.tests }}" not in ci or "UAK_SMOKE_TESTS" not in select_src:
        findings.append(".github/workflows/test.yml · no-test-shards · the suite's shards must come from the discover job (kit_lint.py --ci-shards) into UAK_SMOKE_TESTS")
    if "UAK_SMOKE_TESTS" not in smoke:
        findings.append("kit/.uak/bin/smoke · no-test-shards · smoke must run only the files UAK_SMOKE_TESTS names when it is set")
    named = sorted(set(re.findall(r"\btest_v?\w+\b", ci)) & set(ci_tests()))
    if named:
        findings.append(".github/workflows/test.yml · hand-kept-tests · names %s: the discover job lists them" % ", ".join(named))
    for t in ci_tests()[:-1]:
        if not re.fullmatch(r"test_[A-Za-z0-9_]+", t):
            findings.append("kit/.uak/tests/%s.py · test-name · smoke discovers only [A-Za-z0-9_] names" % t)
        # Why (v6.2, UAK-057): smoke runs every file as `test_x.py --package <candidate>/kit`; an argparse test without
        # that option dies with "unrecognized arguments" and the merge gate goes red for every later task.
        src = (ROOT / "kit/.uak/tests" / (t + ".py")).read_text(encoding="utf-8")
        if "parse_args(" in src and '"--package"' not in src:
            findings.append("kit/.uak/tests/%s.py · no-package-arg · smoke passes --package; add parser.add_argument(\"--package\", ...)" % t)


def check_workflow_dispatch(findings):
    # The suite must be runnable on demand (workflow_dispatch) as well as on pull requests and main.
    p = ROOT / ".github/workflows/test.yml"
    if p.is_file() and not re.search(r"^  workflow_dispatch:", p.read_text(encoding="utf-8"), re.M):
        findings.append(".github/workflows/test.yml · workflow-dispatch · `on:` must list workflow_dispatch so the suite runs on demand")


def check_structure(findings):
    # The command registry routes, documents and exposes every command (scripts/gen_registry.py).
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_registry
    findings.extend("registry · " + x for x in gen_registry.problems())
    check_test_discovery(findings)
    check_workflow_dispatch(findings)
    install = (ROOT / "install.sh").read_text(encoding="utf-8")
    sources = (ROOT / "kit/.uak/skills/SOURCES.md").read_text(encoding="utf-8")
    named = set(re.findall(r"skills=\"([^\"]+)\"", install))
    for group in named:
        for s in group.split():
            if s.startswith("$"):
                continue
            if not (ROOT / "kit/.uak/skills" / s / "SKILL.md").is_file():
                findings.append("install.sh · missing-skill · installs %s, which kit/.uak/skills does not have" % s)
            if "| " + s + " |" not in sources:
                findings.append("kit/.uak/skills/SOURCES.md · unrecorded-skill · %s has no provenance row" % s)
    for p in sorted(BIN.iterdir()):
        if p.is_file() and p.suffix not in (".py", ".html", ".awk", ".pyc") and not (p.stat().st_mode & 0o111):
            findings.append("%s · not-executable · chmod +x" % p.relative_to(ROOT))
    agents = (ROOT / "kit/AGENTS.md").read_text(encoding="utf-8")
    words, lines = len(agents.split()), len(agents.splitlines())
    if lines > 100 or words > 1300:
        findings.append("kit/AGENTS.md · budget · %d lines / %d words (max 100 / 1300): move detail to .uak/docs" % (lines, words))


def check_garden(findings):
    """The kit gardens itself: a fresh install of each mode, then `uak garden`; a doc that names a command, script,
    doc or skill that does not exist fails the build."""
    for mode in ("sprint", "marathon"):
        d = Path(tempfile.mkdtemp(prefix="kit-lint-"))
        try:
            subprocess.run(["git", "init", "-q", "-b", "main", str(d)], check=True, capture_output=True)
            subprocess.run(["bash", str(ROOT / "install.sh"), "--mode", mode, "--stack", "fastapi-react", str(d)], check=True, capture_output=True)
            out = subprocess.run(["bash", ".uak/bin/uak", "garden"], cwd=d, capture_output=True, text=True, errors="replace").stdout
            drift = out.split("DRIFT", 1)[1].split("\n\n", 1)[0].splitlines()[1:] if "DRIFT" in out else ["no DRIFT section"]
            for line in drift:
                if line.strip() and line.strip() != "none":
                    findings.append("garden (%s install) · drift · %s" % (mode, line.strip()))
        finally:
            shutil.rmtree(d, ignore_errors=True)


def check_banner(findings):
    """docs/media/banner.png says the kit's major.minor in its eyebrow; make_media.py writes it to banner.version.
    A release that moved VERSION without regenerating the banner fails here (v6.4.0 shipped a banner that said v6.1)."""
    stamp, version = ROOT / "docs/media/banner.version", ROOT / "kit/.uak/VERSION"
    if not version.is_file() or not (ROOT / "docs/media/banner.png").is_file():
        return
    want = ".".join(version.read_text(encoding="utf-8").strip().split(".")[:2])
    have = stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else "missing"
    if have != want:
        findings.append("docs/media/banner.version · stale banner · %s but kit/.uak/VERSION is %s: regenerate it with "
                        "`uv run --with playwright --with pillow python scripts/make_media.py` and commit docs/media/banner.png "
                        "and banner.version" % (have, want))


def check_dogfood(findings):
    """The kit's own backlog (.uak/ at the root: this repo is developed with the kit) passes `uak lint` offline:
    budgets, owners, the graph, every Verify parses, every feature names its Tests."""
    if not (ROOT / ".uak/TASKS.md").is_file():
        return
    r = subprocess.run(["bash", ".uak/bin/uak", "lint"], cwd=ROOT, capture_output=True, text=True, errors="replace",
                       env=dict(__import__("os").environ, UAK_REMOTE="kit-lint-offline", UAK_AGENT="kit-lint", UAK_HUMAN=""))
    if r.returncode != 0 or "LINT_OK" not in r.stdout:
        for line in (r.stdout + r.stderr).splitlines():
            if line.startswith("LINT") and not line.startswith("LINT_"):
                findings.append(".uak/TASKS.md · dogfood · " + line)
        if not any(f.startswith(".uak/TASKS.md") for f in findings):
            findings.append(".uak/TASKS.md · dogfood · uak lint failed: " + (r.stdout + r.stderr).strip()[-200:])
    for line in r.stderr.splitlines():
        if line.startswith("LINT WARNING"):
            findings.append(".uak/TASKS.md · dogfood · " + line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--ci-tests", action="store_true", help="print the Windows matrix for $GITHUB_OUTPUT")
    ap.add_argument("--ci-windows", action="store_true", help="print the Windows shards for $GITHUB_OUTPUT")
    ap.add_argument("--ci-shards", type=int, metavar="N", help="print the suite's N shards for $GITHUB_OUTPUT")
    a = ap.parse_args()
    if a.ci_tests:
        print("tests=" + json.dumps(ci_tests()))
        return 0
    if a.ci_windows:
        print("wshards=" + json.dumps(ci_windows_shards(windows_shard_count())))
        return 0
    if a.ci_shards:
        print("shards=" + json.dumps(ci_shards(a.ci_shards)))
        return 0
    if a.list:
        for rid, _, msg in PORTABILITY:
            print("%-22s %s" % (rid, msg))
        print("%-22s %s" % ("awk-interval", "mawk ignores {n} intervals in awk regexes"))
        print("%-22s %s" % ("structure", "commands documented, smoke and CI discover the tests, skills vendored and recorded, scripts executable, AGENTS.md budget"))
        return 0
    findings = []
    check_portability(findings)
    check_structure(findings)
    check_garden(findings)
    check_banner(findings)
    check_dogfood(findings)
    for f in findings:
        print("KIT_LINT " + f)
    print("KIT_LINT_%s %d finding(s)" % ("FAIL" if findings else "PASS", len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
