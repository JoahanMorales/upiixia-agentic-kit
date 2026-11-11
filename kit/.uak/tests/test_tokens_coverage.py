#!/usr/bin/env python3
"""UAK-036: the token bill covers every machine. deus-ex-machina published tokens from 1 of 3 Macs (185 M tokens, 100 %
"main"); DevDay 406 M with 78 % "main". A failed background publish now leaves a black box line with the reason,
`tokens --team` names the machines that worked but never published, and the main checkout's share is shown and warned
above 50 %. The hooks publish from session-start and from the Codex tick too. Real Git, a local bare remote, fake
transcripts under a throwaway CLAUDE_CONFIG_DIR."""
import argparse
import concurrent.futures
import os
import re
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def enc(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def transcript(cfg, dirname, name, cache_read):
    d = Path(cfg) / "projects" / dirname
    d.mkdir(parents=True, exist_ok=True)
    (d / (name + ".jsonl")).write_text(
        '{"type":"assistant","message":{"id":"msg_%s","model":"claude-x","usage":{"input_tokens":10,'
        '"cache_creation_input_tokens":0,"cache_read_input_tokens":%d,"output_tokens":5}}}\n' % (name, cache_read), encoding="utf-8")


def env(f, cfg, **extra):
    e = {"UAK_AGENT": "agent-1", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "CLAUDE_CONFIG_DIR": str(cfg),
         "CODEX_HOME": str(Path(cfg) / "nocodex"), "UAK_BLACKBOX": "", "UAK_NOW": "1000000"}
    e.update(extra)
    return e


def tokens(r, f, cfg, *args, cwd=None, **extra):
    return r.run([r.bash, ".uak/bin/tokens", *args], cwd=cwd or f.clones[0], env=env(f, cfg, **extra), allowed=None)


def spend(r, f, name, main_reads, task_reads):
    cfg = r.scratch / (name + "-claude")
    main = Path(f.clones[0]).resolve()
    transcript(cfg, enc(main), "m1", main_reads)
    transcript(cfg, enc(main) + "-wt-hack-001", "t1", task_reads)
    return cfg


def raw_claims(r, f, files):
    """Files straight onto claims (what other machines' publishes and black box flushes leave)."""
    clone = f.base / ("raw-%d" % time.monotonic_ns())
    r.g(f.base, "clone", "-q", "-b", "claims", f.remote, clone)
    for rel, text in files.items():
        (clone / rel).parent.mkdir(parents=True, exist_ok=True)
        (clone / rel).write_text(text, encoding="utf-8")
    r.g(clone, "add", "-A")
    r.g(clone, "-c", "user.name=raw", "-c", "user.email=raw@example.invalid", "commit", "-qm", "raw")
    r.g(clone, "push", "-q", "origin", "claims")


def this_machine(r):
    """The name `tokens` publishes under (.uak/bin/tokens machine(): the host name's cksum, modulo 100000)."""
    return r.run([r.bash, "-c", "(hostname 2>/dev/null || uname -n) | cksum | awk '{print $1 % 100000}'"]).stdout.strip()


def machine_tokens(r, f):
    """This machine's tokens file on the remote's claims, or None when it has none yet."""
    shown = r.g(f.remote, "show", "claims:tokens/%s.md" % this_machine(r), allowed=None)
    return shown.stdout if shown.returncode == 0 else None


def pending_text(common):
    path = common / "uak-blackbox.pending"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def publish_baseline(r, f, common):
    """What a publish must change: this machine's tokens file, judged against the black box as it is now."""
    return {"tokens": machine_tokens(r, f), "pending": len(pending_text(common))}


def publish_landed(r, f, common, before, seconds=60):
    """The background `tokens --publish` replaced THIS machine's tokens file on claims with new totals. A publish
    failure recorded since the baseline is reported first; another commit on claims is not a publish."""
    deadline = time.monotonic() + seconds
    while True:
        recorded = pending_text(common)[before["pending"]:]
        if "tokens publish failed" in recorded:
            raise AssertionError("the background publish failed: " + recorded[-400:])
        now = machine_tokens(r, f)
        if now is not None and now != before["tokens"]:
            return
        if time.monotonic() >= deadline:
            raise AssertionError("the background publish never reached claims within %d s" % seconds)
        time.sleep(0.25)


def publish_wait_needs_this_machines_new_totals(r):
    """The wait itself (review of 9c3888a): an unrelated claims commit while this machine's tokens file is unchanged is
    not a publish, and a publish failure in the black box is reported before anything else."""
    f = with_claims(r, "tk-wait")
    cfg = spend(r, f, "tk-wait", 800000, 100000)
    w = f.worktrees[0]
    common = Path(r.g(w, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    expect(tokens(r, f, cfg, "--publish", "--quiet").returncode == 0, "first publish")
    before = publish_baseline(r, f, common)
    raw_claims(r, f, {"notes/other.md": "- another machine's commit\n"})
    try:
        publish_landed(r, f, common, before, seconds=2)
    except AssertionError as exc:
        expect("never reached" in str(exc), "an unrelated claims commit is not this machine's publish: %s" % exc)
    else:
        raise AssertionError("old totals and an unrelated claims commit were taken for a publish")
    with open(common / "uak-blackbox.pending", "a", encoding="utf-8") as stream:
        stream.write("- tokens publish failed: push to claims failed: denied\n")
    raw_claims(r, f, {"notes/again.md": "- x\n"})
    try:
        publish_landed(r, f, common, before, seconds=2)
    except AssertionError as exc:
        expect("publish failed" in str(exc), "a recorded publish failure is reported: %s" % exc)
    else:
        raise AssertionError("a recorded publish failure was taken for a publish")
    return "unrelated commits and failures are not a publish"


def released(folder, seconds=60):
    """Wait until no process works inside folder. The hook also starts `map build` and `bb flush` with nohup, and on
    Windows a folder that is some process's working directory cannot be renamed or removed: cleaning up then fails with
    WinError 32 (UAK-009: PR #3 runs 43030820800 and 43036311089). Elsewhere the first rename succeeds."""
    probe = Path(str(folder) + ".released")
    deadline = time.monotonic() + seconds
    while True:
        try:
            os.rename(str(folder), str(probe))
            os.rename(str(probe), str(folder))
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise AssertionError("background processes still work in %s after %d s" % (folder, seconds))
            time.sleep(0.25)


def with_claims(r, name):
    f = r.fixture(name, count=1)
    f.claim(0, "HACK-001")
    return f


def publish_failure_is_recorded(r):
    f = with_claims(r, "tk-fail")
    cfg = spend(r, f, "tk-fail", 800000, 100000)
    hook = f.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'denied by the test remote' >&2\nexit 1\n")
    os.chmod(hook, 0o755)
    out = tokens(r, f, cfg, "--publish", "--quiet")
    expect(out.returncode == 0, "a background publish never fails the caller: " + out.stderr)
    common = Path(r.g(f.clones[0], "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    pending = (common / "uak-blackbox.pending").read_text(encoding="utf-8") if (common / "uak-blackbox.pending").exists() else ""
    expect("tokens publish failed" in pending and "denied by the test remote" in pending,
           "one black box line with the reason, got: " + pending[-600:] + out.stdout + out.stderr)
    return "black box line"


def team_view_names_machines_that_never_reported(r):
    f = with_claims(r, "tk-team")
    cfg = spend(r, f, "tk-team", 800000, 100000)
    pub = tokens(r, f, cfg, "--publish", "--quiet")
    expect(pub.returncode == 0, "publish: " + pub.stderr)
    # Two more machines worked (their black box files) and never published; one task ran in a worktree elsewhere.
    raw_claims(r, f, {"blackbox/2026-11-09-11111.md": "- x\n", "blackbox/2026-11-09-22222.md": "- y\n"})
    out = tokens(r, f, cfg, "--team")
    expect(out.returncode == 0, "team: " + out.stderr)
    expect("NOT REPORTED: 2 machine(s)" in out.stdout and "11111" in out.stdout and "22222" in out.stdout, out.stdout)
    expect("Totals are from 1 of 3 machines" in out.stdout, "the total says how many reported: " + out.stdout)
    return "2 machines named"


def main_share_is_reported_and_warned(r):
    f = with_claims(r, "tk-main")
    cfg = spend(r, f, "tk-main", 800000, 100000)
    out = tokens(r, f, cfg)
    expect("main (coordination and work outside tasks) 89%" in out.stdout and "WARNING" in out.stdout, "tokens shows the main share: " + out.stdout)
    low = spend(r, f, "tk-main-low", 100000, 800000)
    ok = tokens(r, f, low)
    expect("main (coordination and work outside tasks) 11%" in ok.stdout and "WARNING" not in ok.stdout, "no warning under 50 %: " + ok.stdout)
    # The digest says it too, with how many machines the bill covers.
    pub = tokens(r, f, cfg, "--publish", "--quiet")
    raw_claims(r, f, {"blackbox/2026-11-09-11111.md": "- x\n", "blackbox/2026-11-09-22222.md": "- y\n"})
    dig = r.run([r.bash, ".uak/bin/uak", "digest", "--full"], cwd=f.clones[0], env=env(f, cfg), allowed=None)
    expect("from 1 of 3 machines" in dig.stdout and "main (coordination and work outside tasks) 89%" in dig.stdout and "above 50%" in dig.stdout,
           "digest Tokens line: " + dig.stdout[-700:] + dig.stderr[-300:])
    return "share and digest"


def hooks_publish_from_session_start_and_codex(r):
    f = with_claims(r, "tk-hooks")
    cfg = spend(r, f, "tk-hooks", 800000, 100000)
    w = f.worktrees[0]
    common = Path(r.g(w, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip())
    e = env(f, cfg)
    stamp = common / "uak-tokens.published"
    expect(not stamp.exists(), "no stamp yet")
    before = publish_baseline(r, f, common)
    r.run([r.bash, "-c", "echo '{\"session_id\":\"s1\"}' | bash .uak/bin/hook session-start"], cwd=w, env=e, allowed=None)
    expect(stamp.exists(), "session-start publishes (tried now)")
    # The publish runs in the background: wait for it, so the next hook and the cleanup never race it (UAK-009).
    publish_landed(r, f, common, before)
    stamp.unlink()
    # New spend since session-start, so the tick's publish has new totals to push (an identical file pushes nothing).
    transcript(cfg, enc(Path(f.clones[0]).resolve()), "m2", 5000)
    before = publish_baseline(r, f, common)
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    (gd / "uak-harness").write_bytes(b"codex\r\n")  # as Windows writes it
    r.run([r.bash, "-c", "echo '{}' | bash .uak/bin/hook tick"], cwd=w, env=e, allowed=None)
    expect(stamp.exists(), "the Codex tick publishes")
    publish_landed(r, f, common, before)
    released(w)
    return "session-start and codex tick"


def team_view_without_black_box_files_still_reads_the_tokens(r):
    """claims with tokens/ and tasks/ but no blackbox/ (the common case early on): --team reads them (macOS CI, bsdtar)."""
    f = with_claims(r, "tk-noblackbox")
    cfg = spend(r, f, "tk-noblackbox", 800000, 100000)
    expect(tokens(r, f, cfg, "--publish", "--quiet").returncode == 0, "publish")
    out = tokens(r, f, cfg, "--team", "--by", "agent", "--json")
    expect(out.returncode == 0 and '"main"' in out.stdout and "agent-1" in out.stdout, "team view: rc %d %s%s" % (out.returncode, out.stdout, out.stderr))
    return "team view"


TESTS = [publish_wait_needs_this_machines_new_totals, team_view_without_black_box_files_still_reads_the_tokens, publish_failure_is_recorded, team_view_names_machines_that_never_reported, main_share_is_reported_and_warned,
         hooks_publish_from_session_start_and_codex]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-tokens-coverage-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))

        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        selected = [t for t in TESTS if not args.case or t.__name__ in args.case]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, selected))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("TOKENS_COVERAGE_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
