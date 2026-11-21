#!/usr/bin/env python3
"""UAK-124: the kit's pre-push hook reads the refs git is about to update (stdin) and refuses a push by an agent to the base
branch or the claims branch, whatever built the ref. Why (review of UAK-111): the guard reads command text, so a ref made by
a command or by a script written to a file and then run is invisible to it; git knows the real ref at push time. The engine's
own pushes run in a temporary repository (claims transactions, the merge gate) where no project hook exists, so they pass;
a human passes with UAK_DIRECT_MAIN=1, as pre-commit. Also: `Mode: Marathon ` is marathon for the guard.
Real Git, a local bare remote."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm
from test_direct_main import with_hook, commit_in

AGENT = {"UAK_AGENT": "agent-1", "UAK_DIRECT_MAIN": ""}


def push(r, cwd, *args, env=None):
    return r.run([r.git, "push", "-q", *args], cwd=cwd, env=env, allowed=None)


def push_anon(r, cwd, *args):
    """A push with no UAK_AGENT in the environment (the base env may carry one on a developer machine)."""
    return r.run(["env", "-u", "UAK_AGENT", "UAK_DIRECT_MAIN=", r.git, "push", "-q", *args], cwd=cwd, allowed=None)


def text(out):
    return out.stdout + out.stderr


def commit_main(r, clone, name):
    # The pre-commit hook has its own override; the push is what is under test.
    out = commit_in(r, clone, name, "x\n", env={"UAK_DIRECT_MAIN": "1"})
    expect(out.returncode == 0, "setup commit: " + text(out)[-300:])


def push_to_base_is_refused_for_an_agent(r):
    f = with_hook(r, "pp-base")
    clone = f.clones[0]
    remote_main = lambda: r.g(f.remote, "rev-parse", "main").stdout.strip()
    before = remote_main()
    commit_main(r, clone, "direct.txt")
    out = push(r, clone, "origin", "main", env=AGENT)
    expect(out.returncode != 0 and "a push to main skips the merge gate" in text(out) and "bash .uak/bin/uak merge ID" in text(out), "refused with the guard's reason: " + text(out)[-400:])
    expect(remote_main() == before, "the remote did not move")
    # A ref the text filter cannot read: the destination is only known to git.
    out = push(r, clone, "origin", "HEAD:refs/heads/main", env=AGENT)
    expect(out.returncode != 0 and remote_main() == before, "refs/heads form refused: " + text(out)[-300:])
    r.g(clone, "branch", "-f", "scratch-ref")
    out = push(r, clone, "origin", "scratch-ref:main", env=AGENT)
    expect(out.returncode != 0 and remote_main() == before, "renamed destination refused: " + text(out)[-300:])
    # The identity may come from the worktree's .uak-env instead of the shell.
    wt = f.worktrees[0]
    (wt / ".uak-env").write_text("UAK_AGENT=agent-2\nUAK_TASK=HACK-001\n", encoding="utf-8")
    ahead = commit_in(r, wt, "src/value-1.txt", "work\n", env={"UAK_DIRECT_MAIN": ""})   # git runs no hook for nothing to push
    expect(ahead.returncode == 0, "setup commit in the worktree: " + text(ahead)[-300:])
    out = push_anon(r, wt, "origin", "HEAD:main")
    expect(out.returncode != 0 and remote_main() == before, ".uak-env identity refused: " + text(out)[-300:])
    # A feature branch is the way, and the same agent pushes it freely.
    ok = push(r, wt, "origin", "HEAD:refs/heads/feat/pp-one", env=AGENT)
    expect(ok.returncode == 0, "a feat branch is not refused: " + text(ok)[-300:])
    return "refused"


def push_to_claims_is_refused(r):
    f = with_hook(r, "pp-claims")
    clone = f.clones[0]
    f.claim(1, "HACK-002")   # creates the claims branch
    before = r.g(f.remote, "rev-parse", "claims").stdout.strip()
    r.g(clone, "branch", "-f", "tmp-claims", "HEAD")
    out = push(r, clone, "origin", "tmp-claims:claims", env=AGENT)
    expect(out.returncode != 0 and "the claims branch is written only by uak commands" in text(out), "refused with the guard's reason: " + text(out)[-400:])
    out = push(r, clone, "origin", "tmp-claims:refs/heads/claims", env=AGENT)
    expect(out.returncode != 0 and r.g(f.remote, "rev-parse", "claims").stdout.strip() == before, "claims did not move: " + text(out)[-300:])
    return "refused"


def engine_pushes_pass(r):
    f = with_hook(r, "pp-engine")
    clone = f.clones[0]
    f.claim(1, "HACK-002")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    r.g(clone, "config", "core.hooksPath", ".githooks")
    claims0 = r.g(f.remote, "rev-parse", "claims").stdout.strip()
    main0 = r.g(f.remote, "rev-parse", "main").stdout.strip()
    out = f.hack(0, "merge", "HACK-001", now=1000023)
    expect("INTEGRATED" in out.stdout, "uak merge (claims and base in one push) passes with the hook on: " + text(out)[-400:])
    expect(r.g(f.remote, "rev-parse", "claims").stdout.strip() != claims0 and r.g(f.remote, "rev-parse", "main").stdout.strip() != main0, "both refs moved")
    # The transactions and the gate push from a fresh `git init` repository: the project's hooks are not there at all.
    for name in ("tx.sh", "review-merge.sh"):
        src = (r.package / ".uak/bin/lib" / name).read_text(encoding="utf-8")
        expect("hooksPath" not in src and "--no-verify" not in src, name + " pushes from its temporary repository")
    return "engine ok"


def human_override_passes(r):
    f = with_hook(r, "pp-human")
    clone = f.clones[0]
    commit_main(r, clone, "hotfix.txt")
    # No agent identity at all (the maintainer's own shell, this repo included): passes.
    h = push_anon(r, clone, "origin", "main")
    expect(h.returncode == 0, "maintainer with no identity: " + text(h)[-300:])
    commit_main(r, clone, "hotfix2.txt")
    ov = push(r, clone, "origin", "main", env={"UAK_AGENT": "agent-1", "UAK_DIRECT_MAIN": "1"})
    expect(ov.returncode == 0, "UAK_DIRECT_MAIN=1 passes even with an agent identity: " + text(ov)[-300:])
    common = r.g(clone, "rev-parse", "--git-common-dir").stdout.strip()
    log = clone / common / "uak-direct-main.log"
    expect(log.is_file() and "push" in log.read_text(encoding="utf-8"), "the override is logged")
    expect(r.g(f.remote, "rev-parse", "main").stdout.strip() == r.g(clone, "rev-parse", "HEAD").stdout.strip(), "main moved")
    return "override"


def guard_reads_mode_case_insensitively(r):
    for i, line in enumerate(("Mode: marathon", "Mode:   Marathon  ", "- **Mode:** `MARATHON`")):
        d = r.scratch / ("pp-mode-%d" % i)
        (d / ".uak").mkdir(parents=True)
        r.g(d, "init", "-q")
        (d / ".uak/PROJECT.md").write_text("# P\n\n" + line + "\r\n", encoding="utf-8")
        out = r.run([r.bash, str(r.package / ".uak/bin/guard"), "check", "git push origin release/1.0"], cwd=d, allowed=None)
        expect(out.returncode == 2 and "marathon mode" in text(out), "%r is marathon: rc %d %s" % (line, out.returncode, text(out)[-200:]))
    d = r.scratch / "pp-mode-sprint"
    (d / ".uak").mkdir(parents=True)
    r.g(d, "init", "-q")
    (d / ".uak/PROJECT.md").write_text("Mode: sprint\n", encoding="utf-8")
    out = r.run([r.bash, str(r.package / ".uak/bin/guard"), "check", "git push origin release/1.0"], cwd=d, allowed=None)
    expect(out.returncode == 0, "sprint is not marathon: " + text(out)[-200:])
    return "case-insensitive"


TESTS = [push_to_base_is_refused_for_an_agent, push_to_claims_is_refused, engine_pushes_pass, human_override_passes, guard_reads_mode_case_insensitively]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-pre-push-") as tmp:
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
    print("PRE_PUSH_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
