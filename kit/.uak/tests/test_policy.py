#!/usr/bin/env python3
"""Executable policy scenarios; no simulated result is called a live human test."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from test_hack import resolve_binary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--bash")
    parser.add_argument("--report", type=Path, default=os.environ.get("UAK_POLICY_REPORT"))
    args = parser.parse_args()
    bash = resolve_binary("bash", args.bash)
    cases = [
        ("backlog_before_timebox", ["backlog", "599", "no", "P0", "yes"], 3, "WAIT_OTHER_TASK"),
        ("backlog_p0_at_timebox", ["backlog", "600", "no", "P0", "yes"], 0, "ALLOW_P0"),
        ("backlog_p1_does_not_bypass", ["backlog", "600", "no", "P1", "yes"], 3, "WAIT_OTHER_TASK"),
        ("backlog_timeout_does_not_grant_autonomy", ["backlog", "600", "no", "P0", "no"], 3, "HUMAN_QUEUE_CONTINUE"),
        ("backlog_approved", ["backlog", "0", "yes", "P1", "yes"], 0, "ALLOW"),
        ("decision_before_timebox", ["decision", "899", "no", "yes", "yes"], 3, "BLOCKED_OTHER_TASK"),
        ("decision_reversible_at_timebox", ["decision", "900", "no", "yes", "yes"], 0, "REVERSIBLE_AND_LOG"),
        ("decision_irreversible_needs_human", ["decision", "900", "no", "no", "yes"], 3, "BLOCKED_OTHER_TASK"),
        ("decision_timeout_does_not_grant_autonomy", ["decision", "900", "no", "yes", "no"], 3, "BLOCKED_OTHER_TASK"),
        ("idle_reviews_first", ["idle", "yes", "yes", "yes"], 0, "REVIEW_PR"),
        ("idle_tests_second", ["idle", "no", "yes", "yes"], 0, "IMPROVE_TESTS"),
        ("idle_demo_third", ["idle", "no", "no", "yes"], 0, "POLISH_DEMO"),
        ("idle_rehearse_last", ["idle", "no", "no", "no"], 0, "REHEARSE"),
        ("before_feature_freeze", ["freeze", "999", "1000"], 0, "FEATURES_ALLOWED"),
        ("at_feature_freeze", ["freeze", "1000", "1000"], 3, "DEMO_FIXES_ONLY"),
        ("invalid_flag", ["idle", "maybe", "yes", "no"], 2, "yes or no"),
    ]
    positive = ["merge", "yes", "yes", "yes", "author-a", "reviewer-b", "yes", "no", "yes", "yes"]
    cases.append(("merge_all_gates", positive, 0, "AUTO_MERGE_ELIGIBLE"))
    for name, index, value in [
        ("merge_unauthorized", 1, "no"), ("merge_smoke_red", 2, "no"),
        ("merge_criteria_pending", 3, "no"), ("merge_self_review", 5, "author-a"),
        ("merge_outside_scope", 6, "no"), ("merge_protected_files", 7, "yes"),
        ("merge_stale_revision", 8, "no"), ("merge_queue_busy", 9, "no"),
    ]:
        values = positive.copy()
        values[index] = value
        cases.append((name, values, 3, "HUMAN_QUEUE_CONTINUE"))
    report = {"schema": 1, "scope": "Executed .uak/bin/policy scenarios; no live human wait or GitHub merge",
              "tests": [], "not_verified": ["Human availability in a live hackathon",
                                             "GitHub validation of smoke/review/SHA evidence",
                                             "Actual PR merger or remote merge queue"]}
    for name, command, code, output in cases:
        process = subprocess.run([bash, ".uak/bin/policy", *command], cwd=args.package.resolve(),
                                 text=True, encoding="utf-8", errors="replace", capture_output=True)
        text = process.stdout + process.stderr
        status = "PASS" if process.returncode == code and output in text else "FAIL"
        report["tests"].append({"name": name, "status": status, "command": command,
                                "expected_code": code, "actual_code": process.returncode,
                                "output": text.strip()})
        print(status + " " + name)
    report["passed"] = sum(x["status"] == "PASS" for x in report["tests"])
    report["failed"] = len(cases) - report["passed"]
    report["status"] = "FAIL" if report["failed"] else "PASS"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("POLICY_RESULT %s passed=%d failed=%d" % (report["status"], report["passed"], report["failed"]))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
