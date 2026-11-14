#!/usr/bin/env python3
"""UAK-091: a newer kit release never blocks a working project (QA rounds 2026-11-14: A-F1, B-02, C-4, and a live
project). When the kit's GitHub tagged 6.3.0, every `uak start` on a published 6.2.0 project became "TODO update the
kit": READY never came, the setup page hid the team step, and the hint named ~/.uak-kit, another clone. UAK_KIT_PIN was
the only way out, and the setup page strips UAK_* variables. Here the kit's GitHub is a local bare repo behind its real
URL (url.insteadOf), and start runs with every UAK_* variable removed, as the setup page runs it.
Real Git, a real install.sh, a fake gh, separate processes."""
import argparse
import concurrent.futures
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

KIT_URL = "https://github.com/JoahanMorales/upiixia-agentic-kit"
TASKS = """## APP-001 · Core
- **Priority:** P0
- **Paths:** src/core.sh
- **Depends on:** None
- **Verify:** true
"""
# The setup page's environment: no UAK_* variable reaches start (lib/setup.py safe_environment).
STRIPPED = 'for v in $(env | sed -n "s/^\\(UAK_[A-Za-z0-9_]*\\)=.*/\\1/p"); do unset "$v"; done; exec bash .uak/bin/start "$@"'


def kit_github(r, name):
    """A bare "kit GitHub" with one old release; the test tags a newer one when it needs it."""
    src = r.scratch / (name + "-kitsrc")
    src.mkdir()
    r.g(src, "init", "-q", "-b", "main")
    r.g(src, "config", "user.name", "Kit"); r.g(src, "config", "user.email", "kit@example.invalid")
    (src / "install.sh").write_text("echo fake installer\n", encoding="utf-8")
    r.g(src, "add", "."); r.g(src, "commit", "-qm", "kit"); r.g(src, "tag", "v0.0.1")
    bare = r.scratch / (name + "-kit.git")
    r.g(r.scratch, "clone", "-q", "--bare", src, bare)
    return src, bare


def release(r, src, bare, version):
    r.g(src, "tag", "v" + version)
    r.g(src, "push", "-q", str(bare), "v" + version)


def ready_project(r, name):
    """A marathon project installed with install.sh, published on main, planned and approved: start says READY."""
    pkg = r.package.parent
    kit_src, kit_bare = kit_github(r, name)
    t = r.scratch / name
    t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.g(t, "config", "user.name", "Solo"); r.g(t, "config", "user.email", "solo@example.invalid")
    remote = r.scratch / (name + "-remote.git")
    r.g(r.scratch, "init", "-q", "--bare", remote)
    bin_dir = r.scratch / (name + "-bin")
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/usr/bin/env bash\ncase \"$1 $2\" in\n  'auth status') echo 'Token scopes: repo';;\n"
                                "  'api repos/solo/app/collaborators?per_page=2') echo 1;;\n  'api repos/solo/app') echo true,true,true;;\n"
                                "esac\nexit 0\n", encoding="utf-8")
    os.chmod(bin_dir / "gh", 0o755)
    home = r.scratch / (name + "-home")   # each test its own ~ (one of them puts a clone at ~/.uak-kit)
    home.mkdir()
    env = {"HOME": str(home), "PATH": bin_dir.as_posix() + os.pathsep + r.env.get("PATH", ""),
           "GIT_CONFIG_COUNT": "4",
           "GIT_CONFIG_KEY_2": "url." + remote.as_posix() + ".insteadOf", "GIT_CONFIG_VALUE_2": "https://github.com/solo/app.git",
           "GIT_CONFIG_KEY_3": "url." + kit_bare.as_posix() + ".insteadOf", "GIT_CONFIG_VALUE_3": KIT_URL}
    r.run([r.bash, str(pkg / "install.sh"), "--mode", "marathon", "--harness", "claude", str(t)], cwd=t, env=env)
    git = lambda *a: r.run([r.git, *a], cwd=t, env=env)
    git("remote", "add", "origin", "https://github.com/solo/app.git")
    r.run([r.bash, ".uak/bin/uak", "start", "--fix"], cwd=t, env=env, allowed=None)
    (t / ".uak/TASKS.md").write_text(TASKS, encoding="utf-8")
    (t / ".uak/OWNERS.md").write_text("# Shared-file owners\n\n| Pattern | Owner task |\n|---|---|\n", encoding="utf-8")
    project = t / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8").replace("Backlog-Approved: no", "Backlog-Approved: yes"), encoding="utf-8")
    git("add", "-A"); git("commit", "-qm", "chore: uak setup"); git("push", "-q", "-u", "origin", "main")
    start = lambda cwd=t, *a: r.run([r.bash, "-c", STRIPPED, "start", *a], cwd=cwd, env=env, allowed=None)
    out = start()
    expect(out.returncode == 0 and "START READY" in out.stdout, "the fixture is READY before any newer release: " + out.stdout)
    return t, env, start, kit_src, kit_bare


def newer_release_is_a_note_after_publish(r):
    """The kit is on main: a newer release is a NOTE with the update command, never a TODO, and READY stays."""
    t, env, start, kit_src, kit_bare = ready_project(r, "gate-note")
    release(r, kit_src, kit_bare, "99.0.0")
    out = start()
    expect(out.returncode == 0 and "START READY" in out.stdout, "a newer release does not block: " + out.stdout)
    expect("TODO" not in out.stdout, "no TODO for a newer release: " + out.stdout)
    note = [l for l in out.stdout.splitlines() if l.startswith("NOTE") and "99.0.0" in l]
    expect(note and "update the kit" in note[0], "the newer release is a NOTE: " + out.stdout)
    expect("--update" in out.stdout, "the NOTE still says how to update: " + out.stdout)
    return {"note": True}


def update_hint_names_the_installing_kit(r):
    """The hint names the clone recorded for this checkout, never ~/.uak-kit when that is another clone; unknown, it
    says how to find the installing kit instead of guessing one."""
    t, env, start, kit_src, kit_bare = ready_project(r, "gate-hint")
    installer = r.scratch / "gate-hint-installer"
    r.g(r.scratch, "clone", "-q", kit_bare, installer)
    other = Path(env["HOME"]) / ".uak-kit"   # a different clone at the default place
    r.g(r.scratch, "clone", "-q", kit_bare, other)
    release(r, kit_src, kit_bare, "99.0.0")
    # What the install records for this checkout (local Git config: per clone, never committed).
    r.g(t, "config", "uak.kitHome", installer.as_posix())
    out = start()
    expect(installer.as_posix() + "/install.sh" in out.stdout and "git -C " + installer.as_posix() + " pull --ff-only" in out.stdout,
           "the hint names the installing kit: " + out.stdout)
    expect(other.as_posix() not in out.stdout and "~/.uak-kit" not in out.stdout, "never the other clone: " + out.stdout)
    r.g(t, "config", "--unset", "uak.kitHome")
    out = start()
    expect("99.0.0" in out.stdout and other.as_posix() not in out.stdout and "~/.uak-kit" not in out.stdout,
           "unknown installer: no clone named as fact: " + out.stdout)
    expect("the kit folder you installed this project from" in out.stdout and "git clone --depth 1 " + KIT_URL in out.stdout,
           "unknown installer: how to find it: " + out.stdout)
    return {"hint": True}


def teammate_clone_is_ready(r):
    """A teammate clones the READY project after a newer release and runs uak start --fix once (its hooks): READY,
    no env var, no pin."""
    t, env, start, kit_src, kit_bare = ready_project(r, "gate-mate")
    release(r, kit_src, kit_bare, "99.0.0")
    mate = r.scratch / "gate-mate-clone"
    r.run([r.git, "clone", "-q", "-b", "main", "https://github.com/solo/app.git", str(mate)], cwd=r.scratch, env=env)
    r.g(mate, "config", "user.name", "Mate"); r.g(mate, "config", "user.email", "mate@example.invalid")
    start(mate, "--fix")   # a clone's first step: the hooks (core.hooksPath is per clone)
    out = start(mate)
    expect(out.returncode == 0 and "START READY" in out.stdout and "TODO" not in out.stdout,
           "a fresh teammate clone is READY: " + out.stdout + out.stderr)
    return {"ready": True}


TESTS = [newer_release_is_a_note_after_publish, update_hint_names_the_installing_kit, teammate_clone_is_ready]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-gate-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("GATE_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
