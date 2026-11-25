#!/usr/bin/env python3
"""UAK-127: a light install. Why (audit of v6.5.0, docs/audit-2026-11.md section 1): an install put 535 files and 9.3 MB
in a project, 111 of them the kit's own protocol tests and 114 the whole skill library: heavy in files, not in context.
install.sh now leaves the tests out (--with-tests brings them back), places only the skills the mode, stack and --skills
ask for, and `uak skill add NAME` copies one more from the kit's checkout or from the pinned release (git only, every
file checked against known-files.txt). --update removes the kit's own test and library files by hash and keeps the
team's. Real install.sh and real Git, a local bare repo as the release remote, never the network."""
import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_skills_windows_clone import repo

BOUND = 270  # 260 before the visual setup's four files in bin/lib (setup.py, setup.html, workspace.js, planning.py); the case keeps its name
SUB = "plugins/ext/skills/motionsites-web-builder"
NAME = "motionsites-web-builder"
REAL_PINNED_FILES = 63  # the real pinned skill (settings/external-skills.tsv) places this many files under .claude/skills


def install(r, d, *args, env=None):
    e = r.env.copy()
    e["UAK_EXTERNAL_SKILLS"] = "off"
    e.update(env or {})
    out = subprocess.run([r.bash, str(r.package.parent / "install.sh"), *args, str(d)], capture_output=True, text=True,
                         errors="replace", env=e, timeout=240, stdin=subprocess.DEVNULL)
    expect(out.returncode == 0, "install failed: " + out.stdout[-400:] + out.stderr[-400:])
    return out


def files(d):
    return [p for p in d.rglob("*") if p.is_file() and ".git" not in p.relative_to(d).parts]


def uak(r, d, *args, env=None):
    e = r.env.copy()
    e.update(env or {})
    return subprocess.run([r.bash, ".uak/bin/uak", *args], cwd=d, capture_output=True, text=True, errors="replace", env=e,
                          timeout=240, stdin=subprocess.DEVNULL)


def install_has_no_kit_tests(r):
    d = repo(r, "light")
    install(r, d, "--mode", "sprint")
    expect(not (d / ".uak/tests").exists(), "no .uak/tests in a light install")
    expect(not (d / ".uak/skills").exists(), "no whole skill library in a light install")
    expect((d / ".claude/skills/test-first/SKILL.md").is_file(), "the skills the mode asks for are placed")
    expect(not (d / ".claude/skills/mcp-builder").exists(), "and only those")
    r.g(d, "add", "-A")
    r.g(d, "commit", "-q", "-m", "kit")
    sm = subprocess.run([r.bash, ".uak/bin/smoke", "--package-only"], cwd=d, capture_output=True, text=True, errors="replace",
                        env=r.env, timeout=240, stdin=subprocess.DEVNULL)
    expect(sm.returncode == 0, "smoke runs its own checks without the tests: %s %s" % (sm.stdout[-400:], sm.stderr[-400:]))
    expect("runs in the kit's repository" in sm.stdout, "and says where the suite runs: " + sm.stdout[-400:])
    expect("PACKAGE_UNVERIFIED" not in sm.stdout + sm.stderr, "not an unverified package")
    ps = subprocess.run([r.bash, ".uak/bin/smoke"], cwd=d, capture_output=True, text=True, errors="replace", env=r.env,
                        timeout=240, stdin=subprocess.DEVNULL)
    expect("runs in the kit's repository" in ps.stdout, "plain smoke says it too: " + ps.stdout[-300:])
    doc = subprocess.run([r.bash, ".uak/bin/doctor"], cwd=d, capture_output=True, text=True, errors="replace", env=r.env,
                         timeout=240, stdin=subprocess.DEVNULL)
    expect(".uak/tests" not in doc.stdout + doc.stderr, "doctor does not ask for the test directory: " + doc.stdout[-500:])
    return "%d files" % len(files(d))


def with_tests_installs_them(r):
    d = repo(r, "with-tests")
    install(r, d, "--mode", "sprint", "--with-tests")
    names = [p.name for p in (d / ".uak/tests").glob("test_*.py")]
    kit_names = [p.name for p in (r.package / ".uak/tests").glob("test_*.py")]
    expect(sorted(names) == sorted(kit_names) and len(names) > 50, "every kit test is installed: %d of %d" % (len(names), len(kit_names)))
    expect(not (d / ".uak/skills").exists(), "--with-tests does not bring the skill library")
    return "%d tests" % len(names)


def update_removes_only_known_test_files(r):
    d = repo(r, "update")
    install(r, d, "--mode", "sprint", "--with-tests")
    tests = d / ".uak/tests"
    edited = tests / "test_hack.py"
    edited.write_text(edited.read_text(encoding="utf-8") + "\n# the team's edit\n", encoding="utf-8")
    own = tests / "test_ours.py"
    own.write_text("print('ours')\n", encoding="utf-8")
    # an older install's whole library: the kit's files go, a skill of the team's own and an edited one stay
    lib = d / ".uak/skills"
    shutil.copytree(r.package / ".uak/skills/test-first", lib / "test-first")
    (lib / "ours").mkdir()
    (lib / "ours/SKILL.md").write_text("# ours\n", encoding="utf-8")
    skill_md = lib / "test-first/SKILL.md"
    skill_md.write_text(skill_md.read_text(encoding="utf-8") + "\nteam edit\n", encoding="utf-8")
    shutil.copytree(r.package / ".uak/skills/webapp-testing", lib / "webapp-testing")
    install(r, d, "--mode", "sprint", "--update")
    # What must stay: the edit, the team's own, and any kit test whose hash known-files.txt does not list (a stale list is
    # kit_hashes --check's finding, not this test's). Every other kit test goes.
    known = set((r.package / ".uak/settings/known-files.txt").read_text(encoding="utf-8").split())
    unlisted = set()
    def blob(b):
        return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()
    for p in (r.package / ".uak/tests").iterdir():
        if p.is_file():
            raw = p.read_bytes()
            if blob(raw) not in known and blob(raw.replace(b"\r", b"")) not in known:
                unlisted.add(p.name)
    want = sorted({"test_hack.py", "test_ours.py"} | unlisted)
    left = sorted(p.name for p in tests.iterdir()) if tests.exists() else []
    expect(left == want, "only the edited, the added and the unlisted tests stay: got %s want %s" % (left[:8], want[:8]))
    expect("team's edit" in edited.read_text(encoding="utf-8"), "the edit is intact")
    expect((lib / "ours/SKILL.md").is_file() and skill_md.is_file(), "the team's skill and the edited one stay")
    expect(not (lib / "webapp-testing").exists(), "an unedited library skill goes")
    return "kept %s" % left


def skill_add_copies_one(r):
    d = repo(r, "skill-add")
    install(r, d, "--mode", "sprint")
    expect(not (d / ".claude/skills/mcp-builder").exists(), "not installed by the mode")
    home = str(r.package.parent)
    out = uak(r, d, "skill", "add", "mcp-builder", env={"UAK_KIT_HOME": home})
    expect(out.returncode == 0, "skill add from a checkout: " + out.stdout[-400:] + out.stderr[-400:])
    for base in (".claude/skills", ".agents/skills"):
        expect((d / base / "mcp-builder/SKILL.md").is_file(), base + " has the skill: " + out.stdout[-300:])
    bad = uak(r, d, "skill", "add", "no-such-skill", env={"UAK_KIT_HOME": home})
    expect(bad.returncode != 0 and "no-such-skill" in bad.stdout + bad.stderr, "an unknown skill is an error")
    evil = uak(r, d, "skill", "add", "../x", env={"UAK_KIT_HOME": home})
    expect(evil.returncode != 0, "a path is not a skill name")
    # no checkout: the pinned release, from a local bare remote; every file must be one the kit shipped
    ver = (r.package / ".uak/VERSION").read_text(encoding="utf-8").strip()
    w = r.scratch / "release-src"
    (w / "kit/.uak/skills").mkdir(parents=True)
    shutil.copytree(r.package / ".uak/skills/mcp-builder", w / "kit/.uak/skills/mcp-builder")
    r.g(w, "init", "-q", "-b", "main")
    r.g(w, "config", "user.name", "Ana")
    r.g(w, "config", "user.email", "ana@example.invalid")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", "release")
    r.g(w, "tag", "v" + ver)
    bare = r.scratch / "release.git"
    r.g(r.scratch, "clone", "-q", "--bare", w, bare)
    env = {"UAK_KIT_HOME": str(r.scratch / "no-checkout"), "UAK_KIT_REPO": bare.resolve().as_uri()}
    d2 = repo(r, "skill-add-remote")
    install(r, d2, "--mode", "sprint")
    ok = uak(r, d2, "skill", "add", "mcp-builder", env=env)
    expect(ok.returncode == 0 and (d2 / ".claude/skills/mcp-builder/SKILL.md").is_file(), "from the release: " + ok.stdout[-400:] + ok.stderr[-400:])
    # a CRLF checkout of the release (Windows) is still the kit's file
    crlf = r.scratch / "release-crlf"
    shutil.copytree(w, crlf, ignore=shutil.ignore_patterns(".git"))
    for f in (crlf / "kit/.uak/skills/mcp-builder").rglob("*"):
        if f.is_file() and f.suffix in (".md", ".txt"):
            f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    r.g(crlf, "init", "-q", "-b", "main")
    r.g(crlf, "config", "user.name", "Ana")
    r.g(crlf, "config", "user.email", "ana@example.invalid")
    r.g(crlf, "config", "core.autocrlf", "false")
    r.g(crlf, "add", "-A")
    r.g(crlf, "commit", "-q", "-m", "release")
    r.g(crlf, "tag", "v" + ver)
    d4 = repo(r, "skill-add-crlf")
    install(r, d4, "--mode", "sprint")
    cr = uak(r, d4, "skill", "add", "mcp-builder", env={"UAK_KIT_HOME": str(r.scratch / "no-checkout"), "UAK_KIT_REPO": crlf.resolve().as_uri()})
    expect(cr.returncode == 0 and (d4 / ".claude/skills/mcp-builder/SKILL.md").is_file(), "CRLF release: " + cr.stdout[-300:] + cr.stderr[-300:])
    # an existing (maybe edited) folder is never overwritten, even when the other harness folder lacks the skill
    d5 = repo(r, "skill-add-keep")
    install(r, d5, "--mode", "sprint")
    mine = d5 / ".agents/skills/mcp-builder/SKILL.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("team edit\n", encoding="utf-8")
    uak(r, d5, "skill", "add", "mcp-builder", env={"UAK_KIT_HOME": home})
    expect(mine.read_text(encoding="utf-8") == "team edit\n" and (d5 / ".claude/skills/mcp-builder/SKILL.md").is_file(), "the edited .agents copy stays")
    # a release whose file the kit never shipped is refused
    (w / "kit/.uak/skills/mcp-builder/SKILL.md").write_text("tampered\n", encoding="utf-8")
    r.g(w, "commit", "-qam", "tamper")
    r.g(w, "tag", "-f", "v" + ver)
    bare2 = r.scratch / "release2.git"
    r.g(r.scratch, "clone", "-q", "--bare", w, bare2)
    d3 = repo(r, "skill-add-tampered")
    install(r, d3, "--mode", "sprint")
    env["UAK_KIT_REPO"] = bare2.resolve().as_uri()
    no = uak(r, d3, "skill", "add", "mcp-builder", env=env)
    expect(no.returncode != 0 and not (d3 / ".claude/skills/mcp-builder").exists(), "a tampered release installs nothing: " + no.stdout[-300:])
    return "copied one, two sources"


def external_remote(r):
    """A bare repo standing in for the pinned external skill; returns the TSV row. The real one places REAL_PINNED_FILES
    files; the fixture has as many, so the count below is the count of a default install."""
    w = r.scratch / "ext-fixture-src"
    for i in range(REAL_PINNED_FILES - 1):
        f = w / SUB / ("references" if i % 2 else "examples") / ("f%d.md" % i)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("fixture %d\n" % i, encoding="utf-8")
    (w / SUB / "SKILL.md").write_text("---\nname: motionsites-web-builder\n---\nbody\n", encoding="utf-8")
    r.g(w, "init", "-q", "-b", "main")
    r.g(w, "config", "user.name", "Ana")
    r.g(w, "config", "user.email", "ana@example.invalid")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", "skill")
    commit = r.g(w, "rev-parse", "HEAD").stdout.strip()
    tree = r.g(w, "rev-parse", "HEAD:" + SUB).stdout.strip()
    bare = r.scratch / "ext-fixture.git"
    r.g(r.scratch, "clone", "-q", "--bare", w, bare)
    tsv = r.scratch / "ext-fixture.tsv"
    tsv.write_text("\t".join([NAME, bare.resolve().as_uri(), commit, SUB, tree]) + "\n", encoding="utf-8", newline="\n")
    return tsv


def marathon_install_under_260_files(r):
    d = repo(r, "marathon")
    tsv = external_remote(r)
    # default install for Claude Code: external skills ON (fetched from the local fixture, never the network)
    out = install(r, d, "--mode", "marathon", "--harness", "claude", env={"UAK_EXTERNAL_SKILLS": "on", "UAK_EXTERNAL_SKILLS_TSV": str(tsv)})
    expect("+ external skill %s" % NAME in out.stdout, "the external skill was fetched: " + out.stdout[-400:])
    expect((d / ".claude/skills" / NAME / "SKILL.md").is_file(), "and placed")
    fs = files(d)
    size = sum(p.stat().st_size for p in fs)
    print("marathon install for Claude Code, external skills on: %d files, %d bytes (was 535 files, 9.3 MB)" % (len(fs), size))
    expect(len(fs) < BOUND, "%d files, bound %d" % (len(fs), BOUND))
    return "%d files, %d bytes" % (len(fs), size)


PARTS = ("bin", "bin/lib", "docs", "modes", "templates", "settings", "stacks", "tests", "skills/test-first",
         "skills/frontend-design", "skills/mcp-builder")
ALL_HARNESS = "claude,codex,cursor,gemini"


def kit_copy(r, name):
    """A copy of the kit used as the install source: a test never writes into the real kit, where another shard of the
    smoke may be importing from it."""
    root = r.scratch / ("src-" + name)
    shutil.copytree(r.package, root / "kit", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(r.package.parent / "install.sh", root / "install.sh")
    return root


def plant_bytecode(root):
    """Bytecode in every folder the installer copies, in skill folders and a stack's skills; returns what it planted."""
    uak_dir = root / "kit/.uak"
    folders = [uak_dir / p for p in PARTS] + [p for p in (uak_dir / "stacks").glob("*/skills") if p.is_dir()]
    folders += [root / "kit/.claude/commands", root / "kit/.agents/skills"]
    planted = []
    for f in folders:
        if not f.is_dir():
            continue
        for rel in ("stray.pyc", "__pycache__/mod.cpython-311.pyc", "__pycache__/mod.cpython-38.opt-1.pyc", "__pycache__/mod.cpython-311.pyc.140234"):  # the last: the temporary name Python writes first
            q = f / rel
            q.parent.mkdir(exist_ok=True)
            q.write_bytes(b"\x00bytecode")
            planted.append(q)
    return planted


def tree(root):
    out = {}
    for p in sorted(root.rglob("*")):
        out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
    return out


def run_install(r, root, d, *args, env=None):
    e = r.env.copy()
    e["UAK_EXTERNAL_SKILLS"] = "off"
    e.update(env or {})
    return subprocess.run([r.bash, str(root / "install.sh"), *args, str(d)], capture_output=True, text=True, errors="replace",
                          env=e, timeout=240, stdin=subprocess.DEVNULL)


def install_from(r, root, d, *args):
    out = run_install(r, root, d, *args)
    expect(out.returncode == 0, "install failed: " + out.stdout[-400:] + out.stderr[-400:])


def bytecode_in(d):
    return sorted(p.relative_to(d).as_posix() for p in d.rglob("*")
                  if ".git" not in p.relative_to(d).parts and (p.name == "__pycache__" or p.suffix == ".pyc")
                  and p.relative_to(d).parts[0] not in ("app", "web"))


def bytecode_fixture(r):
    """One planted kit copy and one install per configuration, shared by the four cases (Windows pays for every install)."""
    if hasattr(r, "bytecode_fixture"):
        return r.bytecode_fixture
    fx = {"root": kit_copy(r, "planted")}
    fx["planted"] = plant_bytecode(fx["root"])
    fx["before"] = tree(fx["root"])
    for name, mode, args in (("marathon", "marathon", ("--harness", "claude")), ("sprint", "sprint", ("--with-tests", "--harness", ALL_HARNESS))):
        d = repo(r, "bc-" + name)
        own = d / "app/__pycache__/own.cpython-311.pyc"
        own.parent.mkdir(parents=True)
        own.write_bytes(b"the project's own")
        install_from(r, fx["root"], d, "--mode", mode, *args)
        fx[name] = {"dir": d, "own": own, "left": bytecode_in(d), "files": len(files(d)) - 1}
    d = fx["sprint"]["dir"]
    web = d / "web/__pycache__/own.pyc"
    web.parent.mkdir(parents=True)
    web.write_bytes(b"own")
    install_from(r, fx["root"], d, "--mode", "sprint", "--update", "--with-tests", "--harness", ALL_HARNESS)
    fx["update"] = {"own": web, "left": bytecode_in(d)}
    fx["after"] = tree(fx["root"])
    r.bytecode_fixture = fx
    return fx


def install_copies_no_bytecode(r):
    fx = bytecode_fixture(r)
    expect(len(fx["planted"]) > 30, "bytecode planted in every folder: %d" % len(fx["planted"]))
    for name in ("marathon", "sprint"):
        expect(not fx[name]["left"], "%s: bytecode installed: %s" % (name, fx[name]["left"][:5]))
        expect((fx[name]["dir"] / ".uak/bin/lib").is_dir() and (fx[name]["dir"] / ".claude/skills/test-first/SKILL.md").is_file(), "the install itself is whole")
        expect(fx[name]["own"].read_bytes() == b"the project's own", "a project's own __pycache__ is untouched")
    return "none of %d planted copied" % len(fx["planted"])


def update_copies_no_bytecode(r):
    fx = bytecode_fixture(r)
    expect(not fx["update"]["left"], "update installed bytecode: %s" % fx["update"]["left"][:5])
    expect(fx["update"]["own"].read_bytes() == b"own", "the project's own bytecode stays after an update")
    return "update clean"


def count_is_the_same_with_bytecode_in_the_kit(r):
    fx = bytecode_fixture(r)
    d = repo(r, "cnt-clean")  # a kit without planted bytecode: the real one, which is only read
    install_from(r, r.package.parent, d, "--mode", "marathon", "--harness", "claude")
    clean = len([p for p in files(d) if "__pycache__" not in p.parts])
    expect(clean == fx["marathon"]["files"], "files with a clean kit %d, with bytecode in it %d" % (clean, fx["marathon"]["files"]))
    return "%d files either way" % clean


def source_folder_is_left_as_it_was(r):
    fx = bytecode_fixture(r)
    expect(all(p.is_file() for p in fx["planted"]), "the planted bytecode is still in the source")
    expect(fx["before"] == fx["after"], "the source changed: %s" % sorted({k for k in set(fx["before"]) | set(fx["after"]) if fx["before"].get(k) != fx["after"].get(k)})[:5])
    return "%d entries unchanged" % len(fx["after"])


def a_failed_copy_stops_the_install(r, out, d, part):
    expect(out.returncode != 0, "the install said success: " + out.stdout[-300:])
    expect("could not copy .uak/%s" % part in out.stderr, "it names the part: " + out.stderr[-400:])
    expect("Continue in the terminal" not in out.stdout, "and does not go on: " + out.stdout[-300:])
    expect(not (d / ".uak" / part).exists(), "no half-copied %s is left as installed" % part)
    expect((d / ".uak/INSTALLING").exists(), "the install is still marked incomplete")


def unreadable_source_file_fails_the_install(r):
    if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        return "skipped: file modes do not apply on Windows or as root"
    root = bytecode_fixture(r)["root"]
    victim = root / "kit/.uak/bin/lib/setup.py"
    mode = victim.stat().st_mode
    victim.chmod(0)
    try:
        d = repo(r, "unreadable")
        out = run_install(r, root, d, "--mode", "sprint")
    finally:
        victim.chmod(mode)
    a_failed_copy_stops_the_install(r, out, d, "bin")
    return "exit %d, bin not left behind" % out.returncode


def unwritable_destination_fails_the_install(r):
    if os.name == "nt":
        return "skipped: the stand-in tar is a POSIX script"
    root = bytecode_fixture(r)["root"]
    shim = r.scratch / "shim-tar"
    shim.mkdir()
    real = shutil.which("tar", path=r.env.get("PATH"))
    (shim / "tar").write_text('#!/bin/sh\ncase "$*" in *-xf*) echo "tar: cannot write: No space left on device" >&2; exit 2;; esac\nexec %s "$@"\n' % real, newline="\n")
    (shim / "tar").chmod(0o755)
    d = repo(r, "unwritable")
    out = run_install(r, root, d, "--mode", "sprint", env={"PATH": str(shim) + os.pathsep + r.env.get("PATH", "")})
    a_failed_copy_stops_the_install(r, out, d, "bin")
    return "exit %d, bin not left behind" % out.returncode


TESTS = [install_has_no_kit_tests, with_tests_installs_them, update_removes_only_known_test_files, skill_add_copies_one,
         marathon_install_under_260_files, install_copies_no_bytecode, update_copies_no_bytecode,
         count_is_the_same_with_bytecode_in_the_kit, source_folder_is_left_as_it_was,
         unreadable_source_file_fails_the_install, unwritable_destination_fails_the_install]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-install-light-") as tmp:
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
    print("INSTALL_LIGHT_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
