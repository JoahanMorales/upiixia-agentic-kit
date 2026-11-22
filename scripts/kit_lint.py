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


# Seconds each test file took on the CI runners, the median of its group in the job logs of five runs on main
# (45001302339 and four before it, 2026-11-22; UAK-144). Two tables because the platforms disagree by file: test_design_pick
# takes 285 s on macOS and 7 to 21 s on Windows, test_flaky_guard 495 s and 1496 s. CI_SECONDS is the macOS time and
# balances the Linux and macOS shards; CI_WINDOWS_SECONDS is the Windows time (mcp_tools is tests/test_mcp_tools.py).
# The lint refuses a test file with no entry in both (timing_problems): UAK-141's table had none for test_flaky_guard, it
# counted the default 60 s and ran 25 min on Windows and 8 min on macOS. To measure again, take each file's group time
# (from its ::group:: line to its ::endgroup:: line) in `gh run view RUN --log --job JOB` of recent runs on main.
CI_SECONDS = {
    "test_flaky_guard": 496, "test_design_pick": 286, "test_merge_engine_policy": 163, "test_review_merge": 91,
    "test_design_taste_cli": 72, "test_v51": 67, "test_claims_perf": 65, "test_v54": 65, "test_merge_commit_field":
    63, "test_v5": 62, "test_v57": 60, "test_integrate_unreviewed": 59, "test_smoke_affected": 55,
    "test_design_shoot_full": 45, "test_hack": 45, "test_design_shoot_qa": 44, "test_command_ledger": 42,
    "test_review_substates": 41, "test_coordination": 40, "test_design_color": 40, "test_v42": 40, "test_v43": 39,
    "test_design_taste_team": 37, "test_read_cache": 37, "test_v55": 34, "test_pre_push": 32, "test_design_perf":
    31, "test_merge_renewer_orphan": 30, "test_tokens_coverage": 27, "test_v3": 26, "test_v571": 26, "test_v41": 25,
    "test_direct_main": 23, "test_design_density": 22, "test_integrate_outside": 22, "test_demo": 21,
    "test_merge_affected": 21, "test_integrate_on_main": 19, "test_bb_flush_no_hooks": 18, "test_v53": 18,
    "mcp_tools": 17, "test_install_light": 17, "test_one_live_renew": 16, "test_v57_tools": 15,
    "test_wt_refused_identity": 15, "test_claims_read": 14, "test_external_skills": 14, "test_skills_windows_clone":
    14, "test_tokens_elsewhere": 14, "test_tokens_window": 14, "test_v510": 14, "test_v52": 14,
    "test_design_breed_notes": 13, "test_manual_notes": 13, "test_review_unseen_approval": 13, "test_v511": 13,
    "test_hook_claims": 12, "test_reviewer_next": 12, "test_v21_security": 12, "test_task_participants": 11,
    "test_v59": 11, "test_critic_stale_ui_only": 10, "test_doctor_skills_compare": 10, "test_plan_amend_overlap":
    10, "test_cursor_skills_keep": 9, "test_design_shoot_timeout": 9, "test_gitleaks_exception": 9,
    "test_next_prefilter": 9, "test_smoke_parallel": 9, "test_claims_cache": 8, "test_plan_check": 8,
    "test_ui_shot_names": 8, "test_v58": 8, "test_cli_spelling_hints": 7, "test_plan_owners": 7,
    "test_review_identity": 7, "test_status_planned": 7, "test_wt_resume_claim": 7, "test_design_aspect": 6,
    "test_lint_paths_hint": 6, "test_v57_install": 6, "test_v591": 6, "test_ci_shards": 5, "test_design_breed": 5,
    "test_design_breed_rules": 5, "test_design_creativity": 5, "test_harness_commands": 5, "test_temp_and_timeouts":
    5, "test_autopsy": 4, "test_design_metrics": 4, "test_git_identity_msg": 4, "test_guard_substitution": 4,
    "test_v592": 4, "test_design_breed_twins": 3, "test_design_lint_scale": 3, "test_gate_scope": 3, "test_metrics":
    3, "test_design_creativity_inherit": 2, "test_design_fonts": 2, "test_design_ground": 2, "test_design_prior": 2,
    "test_design_round": 2, "test_design_round_taste": 2, "test_design_taste": 2, "test_freeze_claim": 2,
    "test_snapshot": 2, "test_task_timeline": 2, "test_banner_version": 1, "test_ci_web_deps": 1,
    "test_design_brief_real": 1, "test_design_lint_html": 1, "test_design_lock_round": 1, "test_design_stage": 1,
    "test_gallery_lint": 1, "test_harvest_discovery": 1, "test_landing_skills": 1, "test_mcp_runs_commands": 1,
    "test_policy": 1, "test_q_string": 1, "test_smoke_env": 1
}
CI_WINDOWS_SECONDS = {
    "test_flaky_guard": 1496, "test_merge_engine_policy": 606, "test_review_merge": 405,
    "test_integrate_unreviewed": 403, "test_claims_perf": 375, "test_v51": 338, "test_v57": 299, "test_pre_push":
    226, "test_hack": 209, "test_v42": 205, "test_v5": 204, "test_review_substates": 202, "test_smoke_affected":
    194, "test_coordination": 192, "test_read_cache": 191, "test_v55": 185, "test_v43": 184, "test_v54": 183,
    "test_v3": 160, "test_command_ledger": 157, "test_integrate_outside": 147, "test_integrate_on_main": 144,
    "test_v41": 134, "test_direct_main": 127, "test_v53": 127, "test_skills_windows_clone": 123,
    "test_merge_affected": 117, "test_external_skills": 109, "test_v571": 108, "test_v510": 103, "mcp_tools": 100,
    "test_manual_notes": 100, "test_merge_commit_field": 100, "test_install_light": 96, "test_one_live_renew": 93,
    "test_v52": 90, "test_wt_refused_identity": 86, "test_demo": 84, "test_claims_read": 82, "test_tokens_window":
    82, "test_v21_security": 82, "test_v511": 81, "test_tokens_coverage": 73, "test_merge_renewer_orphan": 71,
    "test_plan_check": 70, "test_tokens_elsewhere": 69, "test_plan_amend_overlap": 66, "test_next_prefilter": 62,
    "test_task_participants": 62, "test_v57_tools": 61, "test_cursor_skills_keep": 60,
    "test_review_unseen_approval": 60, "test_v59": 60, "test_hook_claims": 59, "test_wt_resume_claim": 57,
    "test_claims_cache": 56, "test_critic_stale_ui_only": 52, "test_doctor_skills_compare": 52, "test_plan_owners":
    51, "test_status_planned": 48, "test_bb_flush_no_hooks": 47, "test_reviewer_next": 47, "test_v58": 46,
    "test_ui_shot_names": 45, "test_lint_paths_hint": 44, "test_v591": 44, "test_gitleaks_exception": 42,
    "test_v57_install": 40, "test_cli_spelling_hints": 39, "test_review_identity": 37, "test_design_perf": 31,
    "test_harness_commands": 31, "test_git_identity_msg": 30, "test_v592": 29, "test_smoke_parallel": 24,
    "test_design_density": 22, "test_guard_substitution": 21, "test_temp_and_timeouts": 20, "test_ci_shards": 19,
    "test_design_breed_notes": 16, "test_design_lint_scale": 13, "test_snapshot": 13, "test_design_shoot_full": 12,
    "test_design_shoot_qa": 11, "test_gate_scope": 10, "test_design_creativity": 9, "test_design_breed": 8,
    "test_design_breed_rules": 8, "test_design_color": 8, "test_design_shoot_timeout": 8, "test_freeze_claim": 8,
    "test_design_metrics": 7, "test_design_pick": 7, "test_autopsy": 6, "test_design_aspect": 6,
    "test_design_breed_twins": 4, "test_design_creativity_inherit": 4, "test_design_ground": 4,
    "test_design_lint_html": 4, "test_design_round": 4, "test_metrics": 4, "test_design_fonts": 3,
    "test_design_taste_cli": 3, "test_banner_version": 2, "test_ci_web_deps": 2, "test_design_round_taste": 2,
    "test_design_taste_team": 2, "test_q_string": 2, "test_smoke_env": 2, "test_task_timeline": 2,
    "test_design_brief_real": 1, "test_design_lock_round": 1, "test_design_prior": 1, "test_design_stage": 1,
    "test_design_taste": 1, "test_gallery_lint": 1, "test_harvest_discovery": 1, "test_landing_skills": 1,
    "test_mcp_runs_commands": 1, "test_policy": 1
}


def ci_seconds(test):
    return CI_SECONDS.get(test, 60)


def ci_windows_seconds(test):
    return CI_WINDOWS_SECONDS.get(test, ci_seconds(test) * 5)


def timing_problems(tests):
    """One finding per test file (or mcp_tools) missing from CI_SECONDS or CI_WINDOWS_SECONDS: the default hid a 25 minute file."""
    return ["scripts/kit_lint.py · no-timing · %s has no entry in %s: measure it (see the comment above CI_SECONDS)" % (t, "CI_SECONDS" if t not in CI_SECONDS else "CI_WINDOWS_SECONDS")
            for t in tests if t not in CI_SECONDS or t not in CI_WINDOWS_SECONDS]


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
# and no split can put it under 25. The longest shard must stay at or under WINDOWS_MARGIN of the bound (25.5 min against
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
    if "python3 scripts/kit_lint.py --ci-shards" not in ci or "fromJSON(needs.discover.outputs.shards)" not in ci \
            or "SHARD_TESTS: ${{ matrix.shard.tests }}" not in ci or "UAK_SMOKE_TESTS=$t" not in ci:
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


def check_structure(findings):
    # The command registry routes, documents and exposes every command (scripts/gen_registry.py).
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_registry
    findings.extend("registry · " + x for x in gen_registry.problems())
    check_test_discovery(findings)
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
