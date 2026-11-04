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
    if "python3 scripts/kit_lint.py --ci-tests" not in ci or "fromJSON(needs.discover.outputs.tests)" not in ci:
        findings.append(".github/workflows/test.yml · no-test-discovery · the Windows matrix must come from the discover job (kit_lint.py --ci-tests)")
    named = sorted(set(re.findall(r"\btest_v?\w+\b", ci)) & set(ci_tests()))
    if named:
        findings.append(".github/workflows/test.yml · hand-kept-tests · names %s: the discover job lists them" % ", ".join(named))
    for t in ci_tests()[:-1]:
        if not re.fullmatch(r"test_[A-Za-z0-9_]+", t):
            findings.append("kit/.uak/tests/%s.py · test-name · smoke discovers only [A-Za-z0-9_] names" % t)


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
    a = ap.parse_args()
    if a.ci_tests:
        print("tests=" + json.dumps(ci_tests()))
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
    check_dogfood(findings)
    for f in findings:
        print("KIT_LINT " + f)
    print("KIT_LINT_%s %d finding(s)" % ("FAIL" if findings else "PASS", len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
