#!/usr/bin/env python3
"""UAK-135: doctor and wt look after the pre-push hook as they do pre-commit, and nothing points git at no hooks.
Why (v6.7.0): the kit's own repository had `core.hooksPath=.githooks` with no such directory for weeks, set by `wt`
(it wrote the setting without looking), so neither the secret scan nor the pre-push ran there and nothing said so;
doctor and wt were written before UAK-124 added pre-push. Now: doctor checks pre-push (present, executable, the kit's
own or called from another hook manager; --fix restores the kit's own and never overwrites a team's), doctor FAILS on a
core.hooksPath that names no directory, and wt sets core.hooksPath only to a directory that holds the kit's hooks (else
it leaves the setting alone and says so once). Real install.sh and real Git; one installed repository is shared."""
import argparse
import os
import re
import stat
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_skills_windows_clone import installer, repo

POSIX = os.name != "nt"   # Windows filesystems have no executable bit: its checks are skipped there too
SHARED = {}


def hook_lines(out):
    return [l for l in out.stdout.splitlines() if re.search(r"pre-push|pre-commit|hooksPath|githooks|\.husky", l)]


def bad_lines(out):
    return [l for l in hook_lines(out) if l.startswith(("FAIL", "WARN"))]


def doctor(r, d, *args):
    env = {"UAK_KIT_HOME": str(r.package.parent), "UAK_AGENT": "", "UAK_HUMAN": ""}
    return r.run([r.bash, str(r.package / ".uak/bin/doctor"), *args], cwd=d, env=env, allowed=None)


def put(path, text, mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    if POSIX:
        path.chmod(mode)


def cfg(r, d, value):
    if value is None:
        r.g(d, "config", "--unset", "core.hooksPath", allowed=(0, 5))
    else:
        r.g(d, "config", "core.hooksPath", value)


def installed(r):
    """One installed repository for every doctor case; reset() puts it back as install.sh left it."""
    if "d" not in SHARED:
        d = repo(r, "hh-shared")
        installer(r)("--mode", "sprint", d)
        SHARED["d"] = d
        SHARED["pristine"] = {n: (d / ".uak/githooks" / n).read_bytes() for n in ("pre-commit", "pre-push")}
    d = SHARED["d"]
    for n, data in SHARED["pristine"].items():
        p = d / ".uak/githooks" / n
        p.write_bytes(data)
        if POSIX:
            p.chmod(0o755)
    for extra in (".husky", ".githooks"):
        if (d / extra).exists():
            for f in (d / extra).iterdir():
                f.unlink()
            (d / extra).rmdir()
    cfg(r, d, ".uak/githooks")
    return d


def light(r, name):
    """A bare repository with no kit: only the hook settings are under test."""
    d = r.scratch / ("hh-" + name)
    d.mkdir(parents=True)
    r.g(d, "init", "-q", "-b", "main")
    r.g(d, "config", "user.name", "Ana")
    r.g(d, "config", "user.email", "ana@example.invalid")
    return d


def doctor_checks_pre_push(r):
    d = installed(r)
    out = doctor(r, d)
    expect([l for l in hook_lines(out) if l.startswith("OK") and "pre-push" in l], "an OK line names pre-push: " + out.stdout[-900:])
    expect(not bad_lines(out), "a fresh install has no hook warning: " + "\n".join(bad_lines(out)))
    # Missing: a FAIL that says how to fix it; --fix restores the kit's own, once.
    kit = (r.package / ".githooks/pre-push").read_bytes()
    (d / ".uak/githooks/pre-push").unlink()
    out = doctor(r, d)
    gone = [l for l in out.stdout.splitlines() if l.startswith("FAIL") and "pre-push" in l]
    expect(gone and "doctor --fix" in gone[0] and out.returncode != 0, "a missing pre-push fails and names the fix: " + out.stdout[-900:])
    fixed = doctor(r, d, "--fix")
    expect((d / ".uak/githooks/pre-push").read_bytes() == kit, "--fix restored the kit's pre-push: " + fixed.stdout[-900:])
    if POSIX:
        expect(os.access(d / ".uak/githooks/pre-push", os.X_OK), "restored hook is executable")
    again = doctor(r, d, "--fix")
    expect(not [l for l in again.stdout.splitlines() if "fixed" in l], "--fix twice changes nothing: " + again.stdout[-900:])
    expect((d / ".uak/githooks/pre-push").read_bytes() == kit and not bad_lines(again), "same file, no warning after the second --fix")
    # Not executable (macOS and Linux; the bit does not exist on Windows filesystems, where doctor skips the check).
    if POSIX:
        (d / ".uak/githooks/pre-push").chmod(0o644)
        out = doctor(r, d)
        expect([l for l in out.stdout.splitlines() if l.startswith("FAIL") and "pre-push" in l and "not executable" in l], "pre-push without the bit fails: " + out.stdout[-900:])
        doctor(r, d, "--fix")
        expect(os.access(d / ".uak/githooks/pre-push", os.X_OK), "--fix made it executable")
    # Another hook manager: the kit's pre-commit is called, its pre-push is not: a warning naming the line, not a failure.
    put(d / ".husky/pre-commit", "#!/usr/bin/env bash\nbash .uak/githooks/pre-commit\n")
    put(d / ".husky/pre-push", "#!/usr/bin/env bash\necho team\n")
    cfg(r, d, ".husky")
    out = doctor(r, d)
    warn = [l for l in out.stdout.splitlines() if l.startswith("WARN") and "pre-push" in l]
    expect(warn and 'bash .uak/githooks/pre-push "$@"' in warn[0], "a WARN names the line to add: " + out.stdout[-900:])
    expect(not [l for l in hook_lines(out) if l.startswith("FAIL")], "not a failure: " + "\n".join(hook_lines(out)))
    put(d / ".husky/pre-push", '#!/usr/bin/env bash\n# bash .uak/githooks/pre-push "$@"\n')
    out = doctor(r, d)
    expect([l for l in out.stdout.splitlines() if l.startswith("WARN") and "pre-push" in l], "a commented-out call is not a call: " + "\n".join(hook_lines(out)))
    put(d / ".husky/pre-push", '#!/usr/bin/env bash\nbash .uak/githooks/pre-push "$@"\n')
    out = doctor(r, d)
    expect(not bad_lines(out) and [l for l in out.stdout.splitlines() if l.startswith("OK") and "pre-push" in l and ".husky" in l], "calling the kit's pre-push is accepted: " + "\n".join(hook_lines(out)))
    # The kit's own repository: thin wrappers in .githooks that exec kit/.githooks/*.
    w = light(r, "own")
    wrapper = '#!/usr/bin/env bash\nset -u\nroot=$(git rev-parse --show-toplevel) || exit 0\nexec bash "$root/kit/.githooks/%s" "$@"\n'
    put(w / ".githooks/pre-commit", wrapper % "pre-commit")
    put(w / ".githooks/pre-push", wrapper % "pre-push")
    cfg(r, w, ".githooks")
    out = doctor(r, w)
    expect(not bad_lines(out), "a wrapper that calls the kit's hook is accepted: " + "\n".join(hook_lines(out)))
    expect([l for l in out.stdout.splitlines() if l.startswith("OK") and "pre-push" in l], "and pre-push is named OK: " + "\n".join(hook_lines(out)))
    return "pre-push checked"


def hooks_path_forms_and_worktrees(r):
    d = installed(r)
    for value in (".uak/githooks/", str(d / ".uak/githooks"), "./.uak/githooks"):
        cfg(r, d, value)
        out = doctor(r, d)
        expect(not bad_lines(out), "hooksPath %r is the kit's dir: %s" % (value, "\n".join(hook_lines(out))))
    cfg(r, d, ".uak/githooks")
    # A task worktree reads the same setting and finds the hooks in its own checkout.
    r.g(d, "add", "-A")
    r.run([r.git, "-c", "core.hooksPath=", "commit", "-q", "-m", "install"], cwd=d, allowed=None)
    wt = d.parent / "hh-shared-wt"
    r.g(d, "worktree", "add", "-q", "-b", "hh-branch", wt)
    out = doctor(r, wt)
    expect(not bad_lines(out) and [l for l in hook_lines(out) if l.startswith("OK") and "pre-push" in l], "a worktree sees the kit's hooks: " + "\n".join(hook_lines(out)))
    # UAK-146: a directory that differs only in case is a different directory where the disk tells them apart (Linux);
    # doctor compares by device and inode, not by lowercased text. Skipped on a case-insensitive disk (macOS, Windows).
    probe = r.scratch / "hh-case-probe"
    (probe / "a").mkdir(parents=True)
    (probe / "A").mkdir(parents=True, exist_ok=True)
    if len(list(probe.iterdir())) == 2:
        other = d / ".UAK/githooks"
        put(other / "pre-commit", "#!/usr/bin/env bash\necho team\n")
        put(other / "pre-push", "#!/usr/bin/env bash\necho team\n")
        cfg(r, d, ".UAK/githooks")
        out = doctor(r, d)
        expect(not [l for l in out.stdout.splitlines() if l.startswith("OK") and "active (.uak/githooks)" in l], "a different .UAK/githooks is not the kit's: " + "\n".join(hook_lines(out)))
        expect([l for l in out.stdout.splitlines() if l.startswith("WARN") and ".UAK/githooks" in l], "it is another dir whose hooks do not call the kit's: " + "\n".join(hook_lines(out)))
        import shutil
        shutil.rmtree(d / ".UAK")
        cfg(r, d, ".uak/githooks")
    return "forms ok"


def doctor_fails_on_a_missing_hooks_dir(r):
    d = installed(r)
    for value in (".githooks-gone", str(d / "nowhere")):
        cfg(r, d, value)
        out = doctor(r, d)
        fail = [l for l in out.stdout.splitlines() if l.startswith("FAIL") and "core.hooksPath" in l]
        expect(out.returncode != 0 and fail, "a missing dir fails: " + out.stdout[-900:])
        expect(value in fail[0] and "no hook" in fail[0] and "doctor --fix" in fail[0], "the message names the path, the effect and the fix: " + fail[0])
    # Another manager's directory that its install has not made yet: --fix does not repoint it (husky, lefthook, pre-commit).
    cfg(r, d, ".husky/_")
    out = doctor(r, d, "--fix")
    expect(r.g(d, "config", "--get", "core.hooksPath").stdout.strip() == ".husky/_", "a husky path is not repointed: " + out.stdout[-600:])
    fail = [l for l in out.stdout.splitlines() if l.startswith("FAIL") and "core.hooksPath" in l]
    expect(fail and "install" in fail[0] and "bash .uak/githooks/pre-commit" in fail[0] and out.returncode != 0, "the FAIL stays and names the way: " + out.stdout[-600:])
    cfg(r, d, ".git-hooks-gone")
    put(d / "lefthook.yml", "pre-commit:\n")
    doctor(r, d, "--fix")
    expect(r.g(d, "config", "--get", "core.hooksPath").stdout.strip() == ".git-hooks-gone", "a lefthook repo is not repointed either")
    (d / "lefthook.yml").unlink()
    cfg(r, d, ".githooks-gone")
    doctor(r, d, "--fix")
    expect(r.g(d, "config", "--get", "core.hooksPath").stdout.strip() == ".uak/githooks", "--fix points at the kit's dir")
    expect(not bad_lines(doctor(r, d)), "and doctor is quiet then")
    # The kit's own incident: .githooks was set and was not there; a repository with no kit hooks cannot be fixed by doctor.
    w = light(r, "gone")
    cfg(r, w, ".githooks")
    out = doctor(r, w, "--fix")
    fail = [l for l in out.stdout.splitlines() if l.startswith("FAIL") and "core.hooksPath" in l]
    expect(fail and "--unset core.hooksPath" in fail[0], "nothing to point at: the message says to unset it: " + out.stdout[-700:])
    expect(r.g(w, "config", "--get", "core.hooksPath").stdout.strip() == ".githooks", "--fix did not invent a setting")
    # Unset: still the old failure (the scanner is off), fixed by --fix.
    cfg(r, d, None)
    out = doctor(r, d)
    expect([l for l in out.stdout.splitlines() if l.startswith("FAIL") and "core.hooksPath is not set" in l], "unset still fails: " + out.stdout[-700:])
    doctor(r, d, "--fix")
    expect(r.g(d, "config", "--get", "core.hooksPath").stdout.strip() == ".uak/githooks", "--fix sets it")
    return "fails"


def fix_keeps_a_teams_hook(r):
    d = installed(r)
    mine = "#!/usr/bin/env bash\necho team pre-push\n"
    put(d / ".husky/pre-commit", "#!/usr/bin/env bash\nbash .uak/githooks/pre-commit\n")
    put(d / ".husky/pre-push", mine)
    cfg(r, d, ".husky")
    before = (d / ".husky/pre-push").read_bytes()
    out = doctor(r, d, "--fix")
    expect((d / ".husky/pre-push").read_bytes() == before, "a team's pre-push is not overwritten")
    expect(r.g(d, "config", "--get", "core.hooksPath").stdout.strip() == ".husky", "nor is its hooksPath changed")
    expect([l for l in out.stdout.splitlines() if l.startswith("WARN") and "pre-push" in l], "and it is still warned: " + out.stdout[-700:])
    # A team's dir without a pre-push: --fix does not create one there.
    (d / ".husky/pre-push").unlink()
    doctor(r, d, "--fix")
    expect(not (d / ".husky/pre-push").exists(), "no file added to another manager's dir")
    # The kit's dir whose pre-push the team edited: kept as it is.
    cfg(r, d, ".uak/githooks")
    put(d / ".uak/githooks/pre-push", mine)
    doctor(r, d, "--fix")
    expect((d / ".uak/githooks/pre-push").read_text(encoding="utf-8") == mine, "an edited pre-push in .uak/githooks is not overwritten")
    return "kept"


def notes(out):
    return [l for l in (out.stdout + out.stderr).splitlines() if "core.hooksPath" in l and l.startswith("wt:")]


def wt_does_not_point_at_nothing(r):
    paths = {"HACK-00%d" % i: "src/n%d.txt" % i for i in range(1, 7)}
    f = r.fixture("hh-wt", paths=paths, count=2)
    clone = f.clones[1]
    env = {"UAK_AGENT": "", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000100"}

    def new(task, agent):
        out = r.run([r.bash, ".uak/bin/wt", "new", task, "--agent", agent], cwd=clone, env=env, allowed=None)
        expect(out.returncode == 0 and "WT_READY" in out.stdout + out.stderr, "wt new %s: %s" % (task, (out.stdout + out.stderr)[-500:]))
        return out

    def hooks_path():
        return r.g(clone, "config", "--get", "core.hooksPath", allowed=(0, 1)).stdout.strip()

    # Neither .uak/githooks nor .githooks: the setting is left alone (unset), and the notice comes once.
    import shutil
    shutil.rmtree(clone / ".githooks")
    first = new("HACK-001", "hh-a")
    expect(hooks_path() == "", "core.hooksPath stays unset: %r" % hooks_path())
    expect(len(notes(first)) == 1, "one notice the first time: " + (first.stdout + first.stderr)[-500:])
    second = new("HACK-002", "hh-b")
    expect(hooks_path() == "" and not notes(second), "and none the second time: " + (second.stdout + second.stderr)[-500:])
    # A directory that exists but holds no kit hook is not pointed at either.
    (clone / ".githooks").mkdir()
    new("HACK-003", "hh-c")
    expect(hooks_path() == "", "an empty .githooks is not set: %r" % hooks_path())
    # A setting that already names a missing directory is not touched either (doctor says what to do).
    r.g(clone, "config", "core.hooksPath", ".githooks-gone")
    new("HACK-004", "hh-d")
    expect(hooks_path() == ".githooks-gone", "the existing setting is left alone: %r" % hooks_path())
    # The kit's hooks are there: wt sets them, as before.
    r.g(clone, "config", "--unset", "core.hooksPath")
    shutil.rmtree(clone / ".githooks")
    r.g(clone, "checkout", "--", ".githooks")
    out = r.run([r.bash, ".uak/bin/wt", "new", "HACK-005", "--agent", "hh-e"], cwd=clone, env=env, allowed=None)
    expect(out.returncode == 0, "wt new with hooks: " + (out.stdout + out.stderr)[-400:])
    expect(r.g(clone, "config", "--get", "core.hooksPath").stdout.strip() == ".githooks", "wt sets the dir that holds the kit's hooks")
    expect(not notes(out), "and says nothing about it")
    # UAK-146: a valid setting of another hook manager is not replaced, even though the kit's hooks are there; the
    # notice (once: its marker is deleted here to start afresh) tells the team to call the kit's hooks from theirs.
    r.g(clone, "config", "core.hooksPath", ".husky")
    put(clone / ".husky/pre-commit", "#!/usr/bin/env bash\necho team\n")
    marker = Path(r.g(clone, "rev-parse", "--git-common-dir").stdout.strip())
    marker = (marker if marker.is_absolute() else clone / marker) / "uak-hooks-noted"
    marker.unlink()
    out = new("HACK-006", "hh-f")
    expect(hooks_path() == ".husky", "a team's valid hooksPath is kept: %r" % hooks_path())
    expect(len(notes(out)) == 1 and "bash .uak/githooks/pre-commit" in notes(out)[0], "one notice says how to call the kit's hooks: " + (out.stdout + out.stderr)[-500:])
    # Doctor tells the truth afterwards: the kit's hooks do not run until the team's call them.
    doc = doctor(r, clone)
    expect([l for l in doc.stdout.splitlines() if l.startswith("WARN") and ".husky" in l and "pre-commit" in l], "doctor warns: " + "\n".join(hook_lines(doc)))
    return "left alone"


TESTS = [doctor_checks_pre_push, hooks_path_forms_and_worktrees, doctor_fails_on_a_missing_hooks_dir, fix_keeps_a_teams_hook, wt_does_not_point_at_nothing]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-hooks-health-") as tmp:
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
    print("HOOKS_HEALTH_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
