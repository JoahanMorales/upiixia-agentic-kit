#!/usr/bin/env python3
"""UAK-197: the known intermittent cases of the suite, in one place. On 2026-11-24 and 25 almost every task lost one or two
CI rounds of 30 to 60 minutes to a failure it did not cause, and each author told the next which failures to ignore in
their own words. KNOWN_INTERMITTENT below is the one list: each case with the system and the run that showed it and the
task or issue that owns it ("unowned" until a human gives it one). The kit's documents and the briefs of agents cite this
list; scripts/kit_lint.py reads it (the files named here are its KNOWN_INTERMITTENT, which keeps them out of the
portability set). A case fixed by a task leaves the list in that task's pull request."""
import argparse
import ast
import importlib.util
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TESTS_DIR = Path(__file__).resolve().parent

# file: the test file without .py; case: a function of that file, or "(what)" when the failure is not one case;
# system: linux, macos or windows; run: the workflow run that showed it (job when known); seen: what failed;
# owner: the task (UAK-NNN), issue (issue #N) or pull request (PR #N) that owns it, or "unowned".
KNOWN_INTERMITTENT = [
    {"file": "test_task_participants", "case": "(temporary folder cleanup)", "system": "windows", "run": "45275593318",
     "job": "138046494771", "seen": "the file's temporary folder could not be removed: WinError 32 on tp-unknown/remote.git, "
     "a process still used it; passed on the second run", "owner": "unowned"},
    {"file": "test_bb_flush_no_hooks", "case": "old_pending_is_flushed_by_a_plain_command", "system": "windows",
     "run": "45209873743", "job": "137815575556", "seen": "the lines did not reach claims:blackbox/; passed on the second run",
     "owner": "unowned"},
    {"file": "test_hook_session_start_locks", "case": "killed_bb_flush_is_recovered_and_published_once", "system": "windows",
     "run": "45633439357", "seen": "the clone directory of the killed flush was not removed (also run 45357519599, "
     "windows (5), with the retry of UAK-190 in place); cause not found", "owner": "issue #83"},
    {"file": "test_hook_session_start_speed", "case": "(the job's step ended with exit code 3840)", "system": "windows",
     "run": "45645537660", "job": "139315504846", "seen": "no FAIL line; 3840 = 15 << 8, the step's Bash ended by SIGTERM "
     "while this file ran (then one file with test_hook_session_start_locks). Cause not found: UAK-197 removed the TERMs its "
     "harness sent to jobs just started and made every Bash of both files refuse and name a signal to an ancestor of the test",
     "owner": "unowned"},
    {"file": "test_dashboard_truth", "case": "share_dialog_shows_a_real_image", "system": "linux", "run": "45645537660",
     "job": "139315504755", "seen": "the dialog showed its text but no image", "owner": "UAK-165 (PR #95)"},
    # "TimeoutError: timed out": the 10 s client of test_setup_wizard.request ran out on a Windows runner (see
    # test_dashboard_journey.py, REQUEST_BOUND_S: patient_requests() is the fix this task used for its own two files).
    {"file": "test_setup_language", "case": "git_failures_are_plain", "system": "windows", "run": "45350167384",
     "job": "138294385161", "seen": "TimeoutError: timed out; passed on the second run", "owner": "UAK-160"},
    {"file": "test_dashboard_truth", "case": "blocked_tasks_are_not_available", "system": "windows", "run": "45464597204",
     "job": "138696092141", "seen": "TimeoutError: timed out (also run 45181138947); passed on the second run", "owner": "UAK-165"},
    {"file": "test_dashboard_truth", "case": "frozen_is_frozen", "system": "windows", "run": "45181138947", "job": "137715036159",
     "seen": "TimeoutError: timed out; passed on the second run", "owner": "UAK-165"},
    {"file": "test_dashboard_profiles", "case": "live_url_link_is_shown_when_set", "system": "windows", "run": "45537069022",
     "job": "138946214964", "seen": "TimeoutError: timed out (also runs 45239383773 and 45557730844); passed on the second run",
     "owner": "unowned"},
    {"file": "test_setup_wizard", "case": "duplicate_install_is_rejected", "system": "windows", "run": "45406802135",
     "job": "139032256634", "seen": "TimeoutError: timed out; passed on the second run", "owner": "unowned"},
    {"file": "test_setup_wizard", "case": "invalid_requests_cannot_mutate", "system": "macos", "run": "45314029684",
     "job": "138176447808", "seen": "ConnectionResetError: [Errno 54] Connection reset by peer; passed on the second run",
     "owner": "unowned"},
    {"file": "test_setup_forms", "case": "field_errors_sit_next_to_the_field", "system": "windows", "run": "45453936428",
     "job": "138658263752", "seen": "TimeoutError: timed out (also runs 45492326908 and 45551275069); passed on the second run",
     "owner": "unowned"},
    {"file": "test_v57_tools", "case": "subagent_cap_holds_under_parallel_launches", "system": "macos", "run": "45456950612",
     "job": "138669071615", "seen": "5 launches allowed with 4 active under a cap of 4; passed on the second run", "owner": "unowned"},
]

# Cases this task fixed (each with its cause in the test's own comment): they must not stay on the list.
FIXED_BY_UAK_197 = [
    ("test_deploy_python_stdlib", "deploy_recognises_stdlib_python"),
    ("test_setup_branches", "install_refuses_a_non_base_branch"),
    ("test_hook_claims", "fresh_reads_a_crlf_epoch"),
    ("test_hook_session_start_locks", "stale_lock_reclaim_runs_once"),
    ("test_dashboard_journey", "new_project_visual_setup_journey"),
]

OWNER = re.compile(r"^(UAK-[0-9]+( \(PR #[0-9]+\))?|issue #[0-9]+|PR #[0-9]+|unowned)$")
SYSTEMS = ("linux", "macos", "windows")


class Failure(Exception):
    pass


def expect(condition, message):
    if not condition:
        raise Failure("expected: " + message)


def by_file():
    """{file: evidence} for scripts/kit_lint.py: one line per file, every case of it with its system and run."""
    out = {}
    for e in KNOWN_INTERMITTENT:
        line = "%s on %s, run %s: %s (%s)" % (e["case"], e["system"], e["run"], e["seen"], e["owner"])
        out[e["file"]] = (out[e["file"]] + "; " + line) if e["file"] in out else line
    return out


def problems(entries, tests_dir=TESTS_DIR, tasks_text=None):
    """What is wrong with a list of entries: a missing field, a file that is not a test file, a case its file does not
    define, a system, run or owner of the wrong shape, an owner task the backlog does not know, a case named twice."""
    out, seen = [], set()
    for i, e in enumerate(entries):
        where = "entry %d (%s %s)" % (i + 1, e.get("file"), e.get("case"))
        missing = [k for k in ("file", "case", "system", "run", "seen", "owner") if not str(e.get(k, "")).strip()]
        if missing:
            out.append("%s: no %s" % (where, ", ".join(missing)))
            continue
        path = Path(tests_dir) / (e["file"] + ".py")
        if not path.is_file():
            out.append("%s: %s.py is not a test file" % (where, e["file"]))
        elif not e["case"].startswith("("):
            names = {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)}
            if e["case"] not in names:
                out.append("%s: %s.py defines no case %s" % (where, e["file"], e["case"]))
        if e["system"] not in SYSTEMS:
            out.append("%s: system %r is not one of %s" % (where, e["system"], ", ".join(SYSTEMS)))
        if not re.fullmatch(r"[0-9]{8,}", str(e["run"])) or ("job" in e and not re.fullmatch(r"[0-9]{8,}", str(e["job"]))):
            out.append("%s: a run (and a job) is the number of a workflow run: %r" % (where, e["run"]))
        if not OWNER.match(e["owner"]):
            out.append("%s: the owner %r is not UAK-NNN, issue #N, PR #N or unowned" % (where, e["owner"]))
        elif tasks_text is not None and e["owner"].startswith("UAK-"):
            task = e["owner"].split()[0]
            if not re.search(r"(?m)^#+ .*\b%s\b" % re.escape(task), tasks_text):
                out.append("%s: the owner %s is not a task of .uak/TASKS.md" % (where, task))
        if (e["file"], e["case"]) in seen:
            out.append("%s: named twice" % where)
        seen.add((e["file"], e["case"]))
    return out


def lint_module():
    p = REPO / "scripts" / "kit_lint.py"
    if not p.is_file():
        return None
    spec = importlib.util.spec_from_file_location("kit_lint_for_flaky", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def known_intermittent_list_names_its_runs():
    # The kit's live backlog is on its claims branch, not in a file of the checkout: the owner's shape is checked here,
    # and a backlog text when one is given (the case below).
    got = problems(KNOWN_INTERMITTENT)
    expect(KNOWN_INTERMITTENT and got == [], "every known intermittent case names its file, case, system, run and owner: %s" % got)
    named = {(e["file"], e["case"]) for e in KNOWN_INTERMITTENT}
    left = [x for x in FIXED_BY_UAK_197 if x in named]
    expect(not left, "a case this task fixed leaves the list: %s" % left)
    # The checks see what they claim to: each broken shape is refused.
    good = dict(KNOWN_INTERMITTENT[1])
    for key, bad in (("run", ""), ("run", "last week"), ("owner", "someone"), ("system", "solaris"), ("case", "no_such_case"),
                     ("file", "test_not_a_file"), ("job", "x")):
        expect(problems([dict(good, **{key: bad})]) != [], "an entry with %s=%r is refused" % (key, bad))
    expect(problems([good, dict(good)]) != [], "a case named twice is refused")
    expect(problems([dict(good, owner="UAK-99999")], tasks_text="## UAK-001 · a task\n") != [], "an owner that is no task is refused")
    expect(problems([good]) == [], "a good entry passes: %s" % problems([good]))
    lint = lint_module()
    if lint is None:
        return "%d cases (no kit source repository here: the lint is not read)" % len(KNOWN_INTERMITTENT)
    files = by_file()
    expect(dict(lint.KNOWN_INTERMITTENT) == files, "scripts/kit_lint.py reads this list (one place): %s" % sorted(lint.KNOWN_INTERMITTENT))
    expect(all(e["run"] in files[e["file"]] for e in KNOWN_INTERMITTENT), "the lint's evidence names each run")
    return "%d cases in %d files, each with its run and owner" % (len(KNOWN_INTERMITTENT), len(files))


TESTS = [known_intermittent_list_names_its_runs]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        started = time.monotonic()
        try:
            note = test()
            print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("CI_FLAKY_RESULT %s passed=%d failed=%d" % ("PASS" if not fails else "FAIL", len(TESTS) - fails, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
