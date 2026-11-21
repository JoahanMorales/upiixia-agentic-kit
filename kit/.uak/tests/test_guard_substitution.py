#!/usr/bin/env python3
"""UAK-111: the guard is a text filter; each rule must at least see what runs (audit of v6.5.0, #3 #4 #5).
(a) a double-quoted span with `$(` or a backtick is code, not prose; (b) `gh -R o/r pr merge` is a merge;
(c) a push to the claims branch is blocked; (d) a push or merge whose ref is dynamic asks the human.
Plain commands stay on builtins and stay allowed. Real git repo in a temp dir; guard runs from the package."""
import argparse
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_v592 import bash_payload, processes

BLOCK, ASK, ALLOW = 2, 3, 0


def repo(r, name):
    d = r.scratch / name
    d.mkdir(parents=True)
    r.g(d, "init", "-q")
    return d


def check(r, d, cmd):
    return r.run([r.bash, str(r.package / ".uak" / "bin" / "guard"), "check", cmd], cwd=d, allowed=None)


def expect_all(r, name, cases):
    d = repo(r, name)
    for cmd, want in cases:
        out = check(r, d, cmd)
        expect(out.returncode == want, "%r: expected rc %d, got %d (%s)" % (cmd, want, out.returncode, out.stderr.strip()[-200:]))


def substitution_in_double_quotes_is_checked(r):
    expect_all(r, "gs-subst", [
        ('git commit -m "fix: $(git push --force origin x) now"', BLOCK),
        ('echo "see `git push --force` here"', BLOCK),
        ('echo "run $(sudo ls) please"', BLOCK),
        ('echo "$(date) is a harmless substitution"', ALLOW),
        ('git commit -m "fix the parser keeps"', ALLOW),
        ("git commit -m 'fix: $(git push --force) in single quotes'", ALLOW),
    ])
    return "seen"


def gh_merge_with_flags_is_blocked(r):
    expect_all(r, "gs-gh", [
        ("gh -R o/r pr merge 3", BLOCK),
        ("gh pr --repo o/r merge 3", BLOCK),
        ("gh --repo=o/r pr merge --squash", BLOCK),
        ("gh pr merge 3", BLOCK),
        ("gh pr view 3", ALLOW),
        ("gh pr create --title merge --body x", ALLOW),
        ("gh -R o/r pr view 3", ALLOW),
        ("gh pr list --state merged", ALLOW),
    ])
    return "flags"


def push_to_claims_is_blocked(r):
    expect_all(r, "gs-claims", [
        ("git push origin claims", BLOCK),
        ("git push origin refs/heads/claims", BLOCK),
        ("git push origin HEAD:claims", BLOCK),
        ("git push origin HEAD:refs/heads/claims", BLOCK),
        ("git push origin feat/claims-x", ALLOW),
        ("git push origin feat/x", ALLOW),
        ("git push -u origin feat/uak-111", ALLOW),
    ])
    return "claims"


def dynamic_ref_asks(r):
    expect_all(r, "gs-dyn", [
        ("git push origin $BRANCH", ASK),
        ("git push origin HEAD:$B", ASK),
        ("git push origin $(cat ref.txt)", ASK),
        ("git push origin `cat ref.txt`", ASK),
        ("git push origin ma\\in", ASK),
        ("gh pr $verb 3", ASK),
        ("git push --force origin $B", BLOCK),
        ("git push origin feat/x && echo $HOME", ALLOW),
        ("git push origin feat/x 2>&1", ALLOW),
        ("gh pr view $N", ALLOW),
    ])
    return "ask"


def narrowed_checks_stay_quiet(r):
    """Review of UAK-111: an `ask` stops an autonomous agent, so only what the guard cannot read asks."""
    nl = chr(10)
    expect_all(r, "gs-narrow", [
        ("gh pr view $PR --json mergeable", ALLOW),
        ("gh pr checks $PR", ALLOW),
        ('gh issue comment 5 --body "merge gate note $(date)"', ALLOW),
        ('gh pr create --title "x" --body "merge the $5 thing now"', ALLOW),
        ("gh pr create --title t --body merge $5", ALLOW),
        ("gh -R $REPO pr view 3", ALLOW),
        ("gh pr $verb 3", ASK),
        ("gh $sub list", ASK),
        ("gh pr merge $N", BLOCK),
        ('git -C "$WT" push origin feat/x', ALLOW),
        ('git -C "$(pwd)" push -u origin HEAD', ALLOW),
        ("git --git-dir=$G push origin feat/x", ALLOW),
        ('git push origin "$(git branch --show-current)"', ALLOW),
        ('git push -u origin "$(git rev-parse --abbrev-ref HEAD)"', ALLOW),
        ("git push origin `git branch --show-current`", ALLOW),
        ("git push -u origin `git rev-parse --abbrev-ref HEAD`", ALLOW),
        ('git push origin "$(git branch --show-current):main"', BLOCK),
        ('git push origin "$(echo other)"', ASK),
        ("git push origin $B", ASK),
        ("cat > f <<'EOF'" + nl + "git push --force" + nl + "gh pr merge 3" + nl + "`sudo ls` $(sudo ls)" + nl + "EOF", ALLOW),
        ('cat > f <<"EOF"' + nl + "git push --force" + nl + "EOF", ALLOW),
        ("cat > f <<\\EOF" + nl + "git push --force $(x)" + nl + "EOF", ALLOW),
        ("git commit -F - <<'EOF'" + nl + "docs: `gh pr merge` and $(git push $X)" + nl + "EOF", ALLOW),
        ("cat > f <<EOF" + nl + "$(git push --force)" + nl + "EOF", BLOCK),
        ("cat > f <<'EOF'" + nl + "x" + nl + "EOF" + nl + "git push --force", BLOCK),
        ("bash <<'EOF'" + nl + "git push --force" + nl + "EOF", BLOCK),
        ('git commit -m "docs: `gh pr merge` is blocked"', BLOCK),
        ('git commit -m "fix: `git push` handling"', ALLOW),
    ])
    d = repo(r, "gs-reason")
    out = check(r, d, 'git commit -m "docs: `gh pr merge` is blocked"')
    expect("single quotes or a heredoc with a quoted delimiter" in out.stderr and "gh pr merge skips the merge gate" in out.stderr, out.stderr)
    return "quiet"


def plain_commands_stay_on_builtins(r):
    f = r.fixture("gs-builtins", count=1)
    w = f.worktrees[0]
    args = [".uak/bin/guard", "bash", "claude"]
    n, out = processes(r, w, args, bash_payload("ls -la src"))
    expect(out.returncode == 0 and n <= 2, "ls: %d processes" % n)
    n, out = processes(r, w, args, bash_payload('git add a.txt && git commit -m "fix: the parser keeps the last line"'))
    expect(out.returncode == 0 and n <= 6, "commit: %d processes" % n)
    expect_all(r, "gs-plain", [
        ('git commit -m "three plain words"', ALLOW),
        ("git push origin feat/x", ALLOW),
        ("gh pr view 3", ALLOW),
        ('gh pr create --title "UAK-1: x y z" --body "a b c"', ALLOW),
        ("git status && git log --oneline", ALLOW),
    ])
    return "builtins"


TESTS = [substitution_in_double_quotes_is_checked, gh_merge_with_flags_is_blocked, push_to_claims_is_blocked,
         dynamic_ref_asks, narrowed_checks_stay_quiet, plain_commands_stay_on_builtins]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="uak-guard-subst-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ != args.case:
                continue
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("GUARD_SUBSTITUTION_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
