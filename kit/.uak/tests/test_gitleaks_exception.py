#!/usr/bin/env python3
"""UAK-037: a gitleaks finding (SECRET_EXTERNAL) gets its own way out. Why (deus-ex-machina): smoke flagged fixture
history through gitleaks and suggested `uak secret-exception --path --rule`, which refuses rules that are not the kit's.
Now the finding names its fingerprint and `uak secret-exception ID --fingerprint FP --reason TEXT` clears that one
finding through a .gitleaksignore entry. gitleaks is faked on PATH (the test needs no install) and holds no key: the
fake only reports fingerprints."""
import argparse
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

FP_A = "src/one.txt:generic-api-key:1"
FP_B = "src/two.txt:generic-api-key:4"

# A gitleaks that finds FP_A and FP_B unless its .gitleaksignore (--gitleaks-ignore-path DIR, or the source's own) lists them.
FAKE = r'''#!/usr/bin/env bash
report= ign=
while [ $# -gt 0 ]; do
  case "$1" in --report-path) report=$2; shift;; --gitleaks-ignore-path) ign=$2; shift;; esac
  shift
done
list=
[ -z "$ign" ] || [ ! -f "$ign/.gitleaksignore" ] || list=$(cat "$ign/.gitleaksignore")
n=0; out=
for fp in "FP_A" "FP_B"; do
  case "
$list
" in *"
$fp
"*) continue;; esac
  out="$out{\"Fingerprint\": \"$fp\"},"; n=$((n + 1))
done
[ -z "$report" ] || printf '[%s]\n' "${out%,}" > "$report"
[ "$n" -eq 0 ] || exit 1
exit 0
'''.replace("FP_A", FP_A).replace("FP_B", FP_B)


def fake_path(f):
    tools = f.base / "fake-gitleaks"
    tools.mkdir(exist_ok=True)
    stub = tools / "gitleaks"
    stub.write_text(FAKE, encoding="utf-8")
    stub.chmod(0o755)
    prefix = tools.as_posix()
    if os.name == "nt" and len(prefix) > 1 and prefix[1] == ":":
        prefix = "/" + prefix[0].lower() + prefix[2:]
    return prefix


def scan(f, *args):
    command = 'PATH="$STUB_PATH:$PATH"; export PATH; bash .uak/bin/secret-scan --staged "$@"'
    return f.r.run([f.r.bash, "-c", command, "x", *args], cwd=f.worktrees[0], env={"STUB_PATH": fake_path(f)}, allowed=None)


def stage(f, rel, text):
    p = f.worktrees[0] / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    f.r.g(f.worktrees[0], "add", "--", rel)


def gitleaks_finding_names_its_fingerprint(r):
    f = r.fixture("gl-fingerprint", count=1)
    f.claim(0, "HACK-001")
    stage(f, "src/one.txt", "plain text\n")
    out = scan(f)
    err = out.stdout + out.stderr
    expect(out.returncode == 1, "the finding blocks: rc %d %s" % (out.returncode, err[-400:]))
    expect("fingerprint=" + FP_A in err and "fingerprint=" + FP_B in err, "each finding prints its fingerprint: " + err[-600:])
    expect("--fingerprint FP" in err and "secret-exception" in err, "the way out names --fingerprint: " + err[-600:])
    # The kit's own rules keep --path --rule.
    stage(f, "src/key.txt", "sk-" + "proj-" + "Z" * 30 + "\n")
    both = scan(f)
    expect("--path FILE --rule RULE" in both.stderr and "--fingerprint FP" in both.stderr, "both ways out when both kinds fire: " + both.stderr[-700:])
    return "fingerprints named"


def fingerprint_exception_clears_only_that_finding(r):
    f = r.fixture("gl-clear", count=2)
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")
    stage(f, "src/one.txt", "plain text\n")
    args = ("secret-exception", "HACK-001", "--fingerprint", FP_A, "--reason", "Fixture history, reviewed")
    denied = f.hack(0, *args, now=1000010, allowed=None)
    expect(denied.returncode != 0, "the owner cannot approve its own exception")
    wrong = f.hack(1, "secret-exception", "HACK-001", "--fingerprint", "docs/outside.txt:generic-api-key:1", "--reason", "x", now=1000010, allowed=None)
    expect(wrong.returncode != 0, "a path outside the task's scope is refused")
    mixed = f.hack(1, "secret-exception", "HACK-001", "--fingerprint", FP_A, "--path", "src/one.txt", "--reason", "x", now=1000010, allowed=None)
    expect(mixed.returncode != 0, "--fingerprint takes no --path/--rule")
    f.hack(1, *args, now=1000011)
    expect("Gitleaks-Exception: HACK-001|" + FP_A + "|agent-2|approved|" in f.show("DECISIONS.md"), "DECISIONS binds the fingerprint and the reviewer")
    one = scan(f)
    err = one.stdout + one.stderr
    expect(one.returncode == 1 and "fingerprint=" + FP_B in err and "fingerprint=" + FP_A not in err,
           "only the other finding remains: rc %d %s" % (one.returncode, err[-500:]))
    f.hack(1, "secret-exception", "HACK-001", "--fingerprint", FP_B, "--reason", "Fixture history, reviewed", now=1000012, allowed=None)
    # FP_B lives in src/two.txt: outside HACK-001's scope in this fixture, so it stays a finding.
    still = scan(f)
    expect(still.returncode == 1, "an exception outside the task's scope does not clear: " + (still.stdout + still.stderr)[-300:])
    ign = f.worktrees[0] / ".gitleaksignore"
    # CRLF and no final newline, as a Windows editor leaves it (UAK-044: CI on Windows failed here, Linux did not).
    ign.write_bytes(("# fixtures\r\n" + FP_B).encode("utf-8"))
    own = scan(f)
    expect(own.returncode == 0, "the project's own .gitleaksignore still works with the exception: " + (own.stdout + own.stderr)[-400:])
    return "one finding cleared"


TESTS = [gitleaks_finding_names_its_fingerprint, fingerprint_exception_clears_only_that_finding]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-gitleaks-exc-") as tmp:
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
    print("GITLEAKS_EXCEPTION_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
