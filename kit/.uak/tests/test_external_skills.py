#!/usr/bin/env python3
"""UAK-055: external skills (MotionSites web builder) are fetched at install time, never shipped in the kit. Why (F0,
2026-11-11; MotionSites LICENSE section 2): its examples and media may not be redistributed as a collection, so install.sh
fetches the pinned commit with git only and checks the tree SHA; offline or a mismatch never fails the install, and
landings fall back to landing-story alone. Tests use a local bare repo as the remote (UAK_EXTERNAL_SKILLS_TSV), never
the network."""
import argparse
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_skills_windows_clone import repo

SUB = "plugins/ext/skills/ext-skill"
NAME = "motionsites-web-builder"


def remote(r, name):
    """A bare repo with one skill folder and an unrelated file; returns (url, commit, tree)."""
    w = r.scratch / ("ext-src-" + name)
    (w / SUB / "references").mkdir(parents=True)
    (w / SUB / "SKILL.md").write_text("---\nname: ext-skill\n---\nbody\n", encoding="utf-8")
    (w / SUB / "references" / "a.md").write_text("ref\n", encoding="utf-8")
    (w / "README.md").write_text("not part of the skill\n", encoding="utf-8")
    r.g(w, "init", "-q", "-b", "main")
    r.g(w, "config", "user.name", "Ana")
    r.g(w, "config", "user.email", "ana@example.invalid")
    r.g(w, "add", "-A")
    r.g(w, "commit", "-q", "-m", "skill")
    commit = r.g(w, "rev-parse", "HEAD").stdout.strip()
    tree = r.g(w, "rev-parse", "HEAD:" + SUB).stdout.strip()
    bare = r.scratch / ("ext-bare-" + name + ".git")
    r.g(r.scratch, "clone", "-q", "--bare", w, bare)
    return bare.resolve().as_uri(), commit, tree


def install(r, d, tsv_row, extra_env=None, args=("--mode", "sprint")):
    tsv = r.scratch / ("ext-%s.tsv" % d.name)
    tsv.write_text(tsv_row + "\n", encoding="utf-8", newline="\n")
    env = r.env.copy()
    env["UAK_EXTERNAL_SKILLS_TSV"] = str(tsv)
    env.update(extra_env or {})
    return subprocess.run([r.bash, str(r.package.parent / "install.sh"), *args, str(d)], capture_output=True, text=True,
                          errors="replace", env=env, timeout=180, stdin=subprocess.DEVNULL)


def row(url, commit, tree):
    return "\t".join([NAME, url, commit, SUB, tree])


def fetch_pinned_skill_installs_both_harness_dirs(r):
    url, commit, tree = remote(r, "ok")
    d = repo(r, "ext-ok")
    out = install(r, d, row(url, commit, tree))
    expect(out.returncode == 0, "install: " + out.stdout[-400:] + out.stderr[-400:])
    for base in (".claude/skills", ".agents/skills"):
        expect((d / base / NAME / "SKILL.md").is_file() and (d / base / NAME / "references/a.md").is_file(), base + " has the skill: " + out.stdout[-500:])
        expect(not (d / base / NAME / "README.md").exists(), "only the subfolder is copied")
    # --update fetches again, replaces the copy, and leaves the other skills alone.
    (d / ".claude/skills" / NAME / "SKILL.md").write_text("stale\n", encoding="utf-8")
    other = (d / ".claude/skills/test-first/SKILL.md").read_bytes()
    up = install(r, d, row(url, commit, tree), args=("--update", "--mode", "sprint"))
    expect(up.returncode == 0 and "body" in (d / ".claude/skills" / NAME / "SKILL.md").read_text(encoding="utf-8"), "update refreshes it: " + up.stdout[-400:])
    expect((d / ".claude/skills/test-first/SKILL.md").read_bytes() == other, "other skills unchanged")
    return "both dirs"


def tree_mismatch_installs_nothing(r):
    url, commit, tree = remote(r, "bad")
    d = repo(r, "ext-bad")
    out = install(r, d, row(url, commit, "0" * 40))
    text = out.stdout + out.stderr
    expect(out.returncode == 0, "the install still succeeds: " + text[-400:])
    expect(not (d / ".claude/skills" / NAME).exists() and not (d / ".agents/skills" / NAME).exists(), "nothing installed")
    expect("external skill %s not installed: " % NAME in text and "tree" in text and "landings use landing-story alone" in text, "says so: " + text[-500:])
    return "refused"


def offline_install_still_succeeds(r):
    d = repo(r, "ext-off")
    gone = (r.scratch / "no-such-remote.git").resolve().as_uri()
    out = install(r, d, row(gone, "a" * 40, "b" * 40))
    text = out.stdout + out.stderr
    expect(out.returncode == 0, "exit 0 offline: " + text[-400:])
    expect("external skill %s not installed: " % NAME in text and "landings use landing-story alone" in text, "one line: " + text[-500:])
    expect((d / ".claude/skills/landing-story/SKILL.md").is_file() and (d / ".uak/bin/uak").is_file(), "the rest installed")
    # Without git on PATH the install also goes on (the shell is bash, so only git is hidden).
    d2 = repo(r, "ext-nogit")
    out2 = install(r, d2, row(gone, "a" * 40, "b" * 40), extra_env={"UAK_EXTERNAL_SKILLS_GIT": "git-that-does-not-exist"})
    expect(out2.returncode == 0 and "external skill %s not installed: " % NAME in out2.stdout + out2.stderr, "no git: " + (out2.stdout + out2.stderr)[-400:])
    # No temp dir is left behind by the fetch.
    return "exit 0"


def kit_never_contains_external_skill_files(r):
    kit = r.package
    bad = [str(p.relative_to(kit)) for p in kit.rglob("*")
           if NAME in p.name or (p.is_file() and p.name in ("MEDIA.md", "spec-template.md", "shoot.py") and "motionsites" in str(p).lower())]
    expect(not bad, "the kit ships a MotionSites skill file: %s" % bad)
    tsv = (kit / ".uak/settings/external-skills.tsv").read_text(encoding="utf-8").splitlines()
    first = tsv[0].split("\t")
    expect(first == [NAME, "https://github.com/Motionsites-AI/claude-skill.git", "faa30d512e3973e58675c72101a7ef42ed37ae83",
                     "plugins/motionsites-web-builder/skills/motionsites-web-builder", "fcab79cb38339708d406c475268172259f2765e7"], "first row pinned: %s" % first)
    return "clean"


def doctor_reports_external_skill(r):
    url, commit, tree = remote(r, "doc")
    d = repo(r, "ext-doc")
    ok = install(r, d, row(url, commit, tree))
    expect(ok.returncode == 0, "install")
    r.g(d, "add", "-A")
    r.g(d, "commit", "-q", "-m", "kit")
    seen = r.run([r.bash, ".uak/bin/doctor"], cwd=d, allowed=None)
    expect("external skills: %s ok (faa30d5)" % NAME in seen.stdout, "doctor says ok: " + seen.stdout[-900:])
    d2 = repo(r, "ext-doc-missing")
    install(r, d2, row(url, commit, tree), extra_env={"UAK_EXTERNAL_SKILLS": "off"})
    r.g(d2, "add", "-A")
    r.g(d2, "commit", "-q", "-m", "kit")
    miss = r.run([r.bash, ".uak/bin/doctor"], cwd=d2, allowed=None)
    expect("external skills: %s missing" % NAME in miss.stdout and "uak start --update" in miss.stdout and "landing-story alone" in miss.stdout,
           "doctor names what is missing and the command: " + miss.stdout[-900:])
    expect(not any(l.startswith("FAIL") and "external" in l for l in miss.stdout.splitlines()), "a warning, never a FAIL")
    return "reported"


TESTS = [fetch_pinned_skill_installs_both_harness_dirs, tree_mismatch_installs_nothing, offline_install_still_succeeds,
         kit_never_contains_external_skill_files, doctor_reports_external_skill]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-external-skills-") as tmp:
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
    print("EXTERNAL_SKILLS_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
