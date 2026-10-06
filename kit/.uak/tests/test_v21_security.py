#!/usr/bin/env python3
"""Real processes; only synthetic strings generated in temp dirs."""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def scan(f, index=0, mode="--staged", env=None):
    return f.r.run([f.r.bash, ".uak/bin/secret-scan", mode], cwd=f.worktrees[index],
                   env=env, allowed=None)


def put(f, relative, text, index=0, stage=True):
    path = f.worktrees[index] / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if stage:
        f.r.g(f.worktrees[index], "add", "--", relative)
    return path


def synthetic_formats(r):
    f = r.fixture("security-formats", count=1)
    normal = scan(f)
    expect(normal.returncode == 0, "Normal staged content must pass")
    fixtures = [
        ("SEC_CLOUD_ACCESS", "A" + "KIA" + "Z" * 16),
        ("SEC_CLOUD_ACCESS", "AI" + "za" + "Z" * 35),
        ("SEC_CLOUD_SECRET", "AWS_SECRET_ACCESS_KEY=" + "Z" * 40),
        ("SEC_GITHUB", "gh" + "p_" + "Z" * 36),
        ("SEC_GITHUB", "github_" + "pat_" + "Z" * 44),
        ("SEC_ANTHROPIC", "sk-" + "ant-" + "Z" * 35),
        ("SEC_OPENAI", "sk-" + "proj-" + "Z" * 35),
        ("SEC_OPENAI", "s" + "k-" + "Z" * 40),
        ("SEC_PRIVATE_KEY", "-----BEGIN " + "PRIVATE KEY-----"),
    ]
    codes = []
    for rule, value in fixtures:
        put(f, "src/one.txt", "synthetic=" + value + "\n")
        result = scan(f)
        output = result.stdout + result.stderr
        expect(result.returncode == 1 and rule in output, "Synthetic format must be blocked: " + rule)
        expect(value not in output, "Scanner diagnostics must redact the synthetic value")
        codes.append(result.returncode)
    put(f, "src/one.txt", "normal text, empty variable and an example without credentials\n")
    expect(scan(f).returncode == 0, "Normal text must pass after replacing synthetic fixtures")
    return {"synthetic_formats": len(fixtures), "blocked_codes": codes,
            "values_in_output": False, "normal_text_code": 0}


def env_and_index_boundaries(r):
    f = r.fixture("security-index", count=1)
    put(f, ".env.example", "VARIABLE=\n")
    expect(scan(f).returncode == 0, "Empty .env.example is allowed")
    put(f, ".env", "VARIABLE=\n", stage=False)
    r.g(f.worktrees[0], "add", "-f", "--", ".env")
    env_result = scan(f)
    expect(env_result.returncode == 1 and "SEC_ENV" in env_result.stderr, "Tracked .env is blocked even empty")
    r.g(f.worktrees[0], "rm", "--cached", "--", ".env")
    synthetic = "gh" + "p_" + "Z" * 36
    put(f, "src/one.txt", "safe staged text\n")
    put(f, "src/one.txt", synthetic + "\n", stage=False)
    expect(scan(f).returncode == 0, "Unstaged secret must not affect staged-only scan")
    r.g(f.worktrees[0], "add", "src/one.txt")
    put(f, "src/one.txt", "working tree clean, index retains synthetic\n", stage=False)
    staged = scan(f)
    expect(staged.returncode == 1, "Staged secret remains blocked after working-tree edit")
    expect(synthetic not in staged.stdout + staged.stderr, "Index scan output must omit the value")
    lint = f.hack(0, "lint", "--secrets", allowed=None)
    expect(lint.returncode != 0 and "SEC_GITHUB" in lint.stdout + lint.stderr,
           "Public uak lint --secrets must invoke the own scanner")
    expect(synthetic not in lint.stdout + lint.stderr, "Public lint output must omit the value")
    return {"tracked_env_code": env_result.returncode, "unstaged_only_code": 0,
            "staged_blob_code": staged.returncode, "public_lint_code": lint.returncode}


def hook_blocks_real_commit(r):
    f = r.fixture("security-hook", count=1)
    hooks = f.worktrees[0] / ".githooks"
    hooks.mkdir(exist_ok=True)
    hook = hooks / "pre-commit"
    shutil.copy2(r.package / ".githooks/pre-commit", hook)
    hook.chmod(0o755)
    r.g(f.worktrees[0], "config", "core.hooksPath", hooks.as_posix())
    synthetic = "sk-" + "proj-" + "Z" * 35
    put(f, "src/one.txt", synthetic + "\n")
    before = r.g(f.worktrees[0], "rev-parse", "HEAD").stdout.strip()
    commit = r.g(f.worktrees[0], "commit", "-m", "Synthetic secret must be blocked", allowed=None)
    after = r.g(f.worktrees[0], "rev-parse", "HEAD").stdout.strip()
    expect(commit.returncode != 0 and before == after, "Real Git hook must block commit without moving HEAD")
    expect("SEC_OPENAI" in commit.stderr + commit.stdout, "Hook must identify the rule")
    expect(synthetic not in commit.stderr + commit.stdout, "Hook diagnostics must omit the value")
    put(f, "src/one.txt", "normal text\n")
    r.g(f.worktrees[0], "commit", "-m", "Safe change accepted")
    return {"blocked_commit_code": commit.returncode, "head_unchanged_on_block": True,
            "safe_commit_code": 0}


def exceptions_bind_actual_index(r):
    f = r.fixture("security-exceptions", count=2)
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")
    synthetic = "sk-" + "proj-" + "Z" * 35
    put(f, "src/one.txt", synthetic + "\n")
    args = ("secret-exception", "HACK-001", "--path", "src/one.txt", "--rule", "SEC_OPENAI",
            "--reason", "Reviewed public synthetic fixture")
    denied = f.hack(0, *args, now=1000010, allowed=None)
    expect(denied.returncode != 0, "Owner must not approve its own exception")
    f.hack(1, *args, now=1000010)
    decision = f.show("DECISIONS.md")
    expect("Secret-Exception: HACK-001|src/one.txt|SEC_OPENAI|" in decision and
           "|agent-2|approved|" in decision, "DECISIONS must bind path, rule, blob and reviewer")
    accepted = scan(f)
    expect(accepted.returncode == 0 and "SECRET_EXCEPTION" in accepted.stdout,
           "Actual command's approved blob must be allowed")
    put(f, "src/one.txt", synthetic + "\nchanged byte\n")
    changed = scan(f)
    expect(changed.returncode == 1, "Changing content invalidates the exception")
    put(f, "src/other.txt", synthetic + "\n")
    moved = scan(f)
    expect(moved.returncode == 1, "Other path cannot reuse the exception")
    expect(synthetic not in decision + accepted.stdout + changed.stderr + moved.stderr,
           "Exception evidence must omit values")
    return {"self_approval_code": denied.returncode, "approved_blob_code": accepted.returncode,
            "changed_blob_code": changed.returncode, "other_path_code": moved.returncode}


def optional_external_is_used_and_redacted(r):
    f = r.fixture("security-external", count=1)
    tools = f.base / "tool-stubs"
    tools.mkdir()
    marker = f.base / "external-called.txt"
    stub = tools / "gitleaks"
    stub.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$EXTERNAL_MARKER"\n'
                    'printf "%s\\n" "sensitive external output withheld"\nexit 7\n', encoding="utf-8")
    stub.chmod(0o755)
    # PATH conversion on Windows is handled by Bash; use a POSIX drive path there.
    prefix = tools.as_posix()
    if os.name == "nt" and len(prefix) > 1 and prefix[1] == ":":
        prefix = "/" + prefix[0].lower() + prefix[2:]
    command = 'PATH="$STUB_PATH:$PATH"; export PATH; bash .uak/bin/secret-scan --staged'
    result = r.run([r.bash, "-c", command], cwd=f.worktrees[0],
                   env={"STUB_PATH": prefix, "EXTERNAL_MARKER": marker.as_posix()}, allowed=None)
    expect(result.returncode == 1 and marker.exists(), "Installed additional scanner must run and block on failure")
    expect("--staged" in marker.read_text(encoding="utf-8"), "External hook scan must receive staged mode")
    expect("sensitive external output withheld" not in result.stdout + result.stderr,
           "External output must be captured")
    return {"scanner_code": result.returncode, "external_called": True, "external_output_captured": True}


def product_default_unverified(r):
    f = r.fixture("product-default", count=1)
    # A project that runs smoke may bring its own adapter. This case
    # isolates the missing-adapter boundary in its temp clone.
    scripts_root = (f.worktrees[0] / "scripts").resolve()
    for name in ("smoke-project", ".smoke-project.provenance"):
        path = f.worktrees[0] / "scripts" / name
        expect(path.resolve().parent == scripts_root, "Default-product fixture path must stay inside its scripts directory")
        if path.exists():
            path.unlink()
    result = r.run([r.bash, ".uak/bin/lib/smoke-init.sh", "gate"], cwd=f.worktrees[0], allowed=None)
    expect(result.returncode == 2 and "PRODUCT_UNVERIFIED" in result.stderr, "Missing product adapter must stay unverified")
    manual = put(f, ".uak/bin/smoke-project", "#!/usr/bin/env bash\nexit 0\n", stage=False)
    original = manual.read_bytes()
    protected = f.hack(0, "init-smoke", "--command", "exit 0", allowed=None)
    expect(protected.returncode != 0 and manual.read_bytes() == original, "Init must preserve an existing manual adapter")
    uncompiled = r.run([r.bash, ".uak/bin/lib/smoke-init.sh", "gate"], cwd=f.worktrees[0], allowed=None)
    expect(uncompiled.returncode == 2, "A manual file alone must not mark product verified")
    return {"missing_adapter_code": result.returncode, "manual_protected_code": protected.returncode,
            "manual_unverified_code": uncompiled.returncode}


def product_actual_command_propagates(r):
    f = r.fixture("product-adapter", count=1)
    command = 'printf "run\\n" >> smoke-runs.txt; exit "${DEMO_STATUS:-0}"'
    f.hack(0, "init-smoke", "--command", command, now=1000010)
    marker = f.worktrees[0] / "smoke-runs.txt"
    expect(marker.read_text(encoding="utf-8").splitlines() == ["run"], "Init must actually execute the supplied command")
    gate = [r.bash, ".uak/bin/lib/smoke-init.sh", "gate"]
    passed = r.run(gate, cwd=f.worktrees[0], env={"DEMO_STATUS": "0"}, allowed=None)
    failed = r.run(gate, cwd=f.worktrees[0], env={"DEMO_STATUS": "7"}, allowed=None)
    expect(passed.returncode == 0 and "PRODUCT_PASS" in passed.stdout, "Product callback pass must propagate")
    expect(failed.returncode == 7 and "PRODUCT_FAIL" in failed.stderr, "Product callback exit 7 must propagate")
    expect(marker.read_text(encoding="utf-8").splitlines() == ["run", "run", "run"],
           "Both gate outcomes must execute the actual supplied command")
    adapter = f.worktrees[0] / ".uak/bin/smoke-project"
    adapter.write_text(adapter.read_text(encoding="utf-8") + "# modified\n", encoding="utf-8")
    modified = r.run(gate, cwd=f.worktrees[0], allowed=None)
    expect(modified.returncode == 2 and "PRODUCT_UNVERIFIED" in modified.stderr,
           "Adapter edit must invalidate provenance")
    return {"init_actual_runs": 1, "gate_actual_runs": 2, "pass_code": passed.returncode,
            "fail_code": failed.returncode, "changed_adapter_code": modified.returncode,
            "scope": "Synthetic supplied shell command; no real product verification"}


def product_initial_failure_stays_unverified(r):
    f = r.fixture("product-init-failure", count=1)
    result = f.hack(0, "init-smoke", "--command", 'printf "attempt\\n" >> smoke-runs.txt; exit 7', allowed=None)
    expect(result.returncode == 7, "Init must propagate the supplied failing command")
    expect((f.worktrees[0] / "smoke-runs.txt").is_file(), "Failing command must really execute")
    gate = r.run([r.bash, ".uak/bin/lib/smoke-init.sh", "gate"], cwd=f.worktrees[0], allowed=None)
    expect(gate.returncode == 2 and "PRODUCT_UNVERIFIED" in gate.stderr, "Initially failing adapter must stay unverified")
    f.hack(0, "init-smoke", "--command", 'printf "retry\\n" >> smoke-runs.txt; exit 0')
    recovered = r.run([r.bash, ".uak/bin/lib/smoke-init.sh", "gate"], cwd=f.worktrees[0], allowed=None)
    expect(recovered.returncode == 0, "Generated adapter must be safely reinitializable after failure")
    expect((f.worktrees[0] / "smoke-runs.txt").read_text(encoding="utf-8").splitlines() ==
           ["attempt", "retry", "retry"], "Recovery must execute both supplied initialization and gate commands")
    return {"init_code": result.returncode, "actual_command_executed": True,
            "gate_code": gate.returncode, "reinitialized_gate_code": recovered.returncode}


CASES = [synthetic_formats, env_and_index_boundaries, hook_blocks_real_commit,
         exceptions_bind_actual_index, optional_external_is_used_and_redacted,
         product_default_unverified, product_actual_command_propagates,
         product_initial_failure_stays_unverified]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--bash")
    p.add_argument("--git")
    p.add_argument("--report", type=Path, default=os.environ.get("UAK_SECURITY_REPORT"))
    p.add_argument("--work-dir", type=Path, default=os.environ.get("UAK_SECURITY_WORK_DIR"))
    p.add_argument("--case", action="append")
    a = p.parse_args()
    temporary = None
    if a.work_dir:
        scratch = a.work_dir.resolve()
        scratch.mkdir(parents=True, exist_ok=False)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="hack-v21-security-")
        scratch = Path(temporary.name)
    package = a.package.resolve()
    expect(package != scratch and package not in scratch.parents, "Scratch must be outside package")
    r = Runner(package, scratch, resolve_binary("bash", a.bash), resolve_binary("git", a.git))
    report = {"schema": 1, "scope": "Real Git and shell commands; synthetic secrets only",
              "tests": [], "not_verified": ["Real provider credentials or specialized scanning accuracy",
                                             "Real product build, demo or end-to-end flow"]}
    hash_names = [".uak/bin/uak", ".uak/bin/secret-scan", ".githooks/pre-commit",
                  ".uak/bin/lib/security.sh", ".uak/bin/lib/smoke-init.sh", ".uak/tests/test_v21_security.py"]
    report["package_sha256"] = {name: hashlib.sha256((package / name).read_bytes()).hexdigest()
                                for name in hash_names}
    selected = [test for test in CASES if not a.case or test.__name__ in a.case]
    for test in selected:
        item = {"name": test.__name__}
        started = time.monotonic()
        try:
            item["evidence"] = test(r)
            item["status"] = "PASS"
        except Exception as error:
            item["status"] = "FAIL"
            item["error"] = str(error)
        item["seconds"] = round(time.monotonic() - started, 3)
        report["tests"].append(item)
        print("%s %s (%ss)" % (item["status"], item["name"], item["seconds"]), flush=True)
        if item["status"] == "FAIL": print(item.get("error", ""), flush=True)
    report["passed"] = sum(item["status"] == "PASS" for item in report["tests"])
    report["failed"] = len(report["tests"]) - report["passed"]
    report["status"] = "FAIL" if report["failed"] else "PASS"
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("SECURITY_RESULT %s passed=%s failed=%s" % (report["status"], report["passed"], report["failed"]))
    if temporary:
        temporary.cleanup()
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
