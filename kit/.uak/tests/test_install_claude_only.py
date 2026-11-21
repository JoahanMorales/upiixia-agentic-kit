#!/usr/bin/env python3
"""UAK-011: an external skill must not leave Claude-only installs with a partial shared skills copy.

Real installs and doctor runs; the pinned external skill comes from a disposable local Git remote.
"""
import argparse
import shutil
import tempfile
import time
from pathlib import Path

from test_external_skills import NAME, install, remote, row
from test_hack import Runner, expect, resolve_binary
from test_skills_windows_clone import doctor, repo, skill_lines


def pinned_skill(r, name):
    return row(*remote(r, "claude-only-" + name))


def installed(r, name, harness, external_row, update=False, external=True):
    d = r.scratch / ("wc-" + name) if update else repo(r, name)
    args = ("--mode", "sprint", "--harness", harness)
    if update:
        args = ("--update",) + args
    out = install(r, d, external_row, extra_env={"UAK_EXTERNAL_SKILLS": "on" if external else "off"}, args=args)
    expect(out.returncode == 0, "install failed: " + out.stdout[-600:] + out.stderr[-600:])
    return d


def shared_copy_matches(d):
    shared = d / ".agents/skills"
    if not shared.exists():
        return
    expect(shared.is_dir() and not shared.is_symlink(), "shared skills are a real directory")
    for skill in (d / ".claude/skills").iterdir():
        if not skill.is_dir():
            continue
        original = {p.relative_to(skill): p.read_bytes() for p in skill.rglob("*") if p.is_file()}
        copied = shared / skill.name
        actual = {p.relative_to(copied): p.read_bytes() for p in copied.rglob("*") if p.is_file()}
        expect(actual == original, "assertion failed: .agents/skills/%s is not a faithful copy" % skill.name)


def no_skills_failure(r, d):
    out = doctor(r, d)
    bad = [line for line in skill_lines(out) if line.startswith("FAIL")]
    expect(not bad, "assertion failed: doctor skills check: " + "\n".join(bad))


def claude_only_install_passes_doctor_skills_check(r):
    external_row = pinned_skill(r, "claude")
    d = installed(r, "claude-only", "claude", external_row)
    expect((d / ".claude/skills" / NAME / "SKILL.md").is_file(), "local external skill installed")
    no_skills_failure(r, d)
    shared_copy_matches(d)
    expect(not any((d / h).exists() for h in (".codex", ".cursor", ".gemini")), "only Claude harness installed")
    off = installed(r, "claude-offline", "claude", external_row, external=False)
    expect(not (off / ".agents/skills").exists(), "Claude alone without external skills needs no shared directory")
    no_skills_failure(r, off)
    shared_copy_matches(off)
    # Earlier Claude-only installs created a shared directory with only the external skill.
    partial = off / ".agents/skills" / NAME
    partial.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(d / ".claude/skills" / NAME, partial)
    mine = partial.parent / "team-skill/SKILL.md"
    mine.parent.mkdir()
    mine.write_text("team-owned skill\n", encoding="utf-8")
    installed(r, "claude-offline", "claude", external_row, update=True, external=False)
    no_skills_failure(r, off)
    shared_copy_matches(off)
    expect(mine.read_text(encoding="utf-8") == "team-owned skill\n", "update preserves the team's shared skill")
    return "external, offline and update"


def multi_harness_install_keeps_agents_skills_in_sync(r):
    external_row = pinned_skill(r, "multi")
    for harness in ("claude,codex", "claude,cursor"):
        name = harness.replace(",", "-")
        d = installed(r, name, harness, external_row)
        expect((d / ".agents/skills" / NAME / "references/a.md").is_file(), "external skill shared")
        expect((d / ".agents/skills/uak-plan/SKILL.md").is_file(), "phase skill installed")
        shared_copy_matches(d)
        no_skills_failure(r, d)
        (d / ".agents/skills/test-first/SKILL.md").write_text("stale\n", encoding="utf-8")
        installed(r, name, harness, external_row, update=True)
        shared_copy_matches(d)
        no_skills_failure(r, d)
    return "Codex and Cursor install/update"


def really_stale_copy_is_still_reported(r):
    external_row = pinned_skill(r, "stale")
    d = installed(r, "really-stale", "claude,codex", external_row)
    (d / ".agents/skills/test-first/SKILL.md").write_text("an older skill\n", encoding="utf-8")
    out = doctor(r, d)
    expect(out.returncode != 0, "doctor rejects stale skills")
    expect(any(line.startswith("FAIL") and ".agents/skills is a stale copy" in line for line in skill_lines(out)),
           "doctor reports a really stale copy: " + out.stdout)
    return "stale copy rejected"


TESTS = [claude_only_install_passes_doctor_skills_check, multi_harness_install_keeps_agents_skills_in_sync,
         really_stale_copy_is_still_reported]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    if not (args.package.resolve().parent / "install.sh").is_file():
        print("INSTALL_CLAUDE_ONLY_RESULT SKIP (installer tests run from the kit source checkout)")
        return 0
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-claude-only-") as tmp:
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
    print("INSTALL_CLAUDE_ONLY_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
