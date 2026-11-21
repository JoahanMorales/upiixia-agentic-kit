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

BOUND = 260
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


TESTS = [install_has_no_kit_tests, with_tests_installs_them, update_removes_only_known_test_files, skill_add_copies_one,
         marathon_install_under_260_files]


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
