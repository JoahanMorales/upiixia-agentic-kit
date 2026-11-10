#!/usr/bin/env python3
"""UAK-041: skills survive a Windows clone. Git for Windows defaults to core.symlinks=false, so a repo installed on macOS
or Linux with .agents/skills and .cursor/skills committed as symlinks (mode 120000) is checked out with one-line text
files ("../.claude/skills") and Codex, Cursor and Gemini lose every skill. Why (DevDay and deus-ex-machina, v6.0.0): both
commit those links; a Codex teammate on Windows only reported "PowerShell". The installer now writes real copies,
refreshed on every update; doctor flags a link checked out as a file, or a stale copy, and --fix / uak start repairs it.
Real install.sh and real Git; core.symlinks=false is simulated in a clone."""
import argparse
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def installer(r):
    inst = str(r.package.parent / "install.sh")
    def run(*a):
        out = subprocess.run([r.bash, inst, *map(str, a)], capture_output=True, text=True, errors="replace", env=r.env, timeout=180,
                             stdin=subprocess.DEVNULL)
        expect(out.returncode == 0, "install failed: " + out.stdout[-300:] + out.stderr[-300:])
        return out
    return run


def repo(r, name):
    d = r.scratch / ("wc-" + name)
    d.mkdir(parents=True)
    r.g(d, "init", "-q", "-b", "main")
    r.g(d, "config", "user.name", "Ana")
    r.g(d, "config", "user.email", "ana@example.invalid")
    return d


def v600_repo(r, name):
    """What v6.0.0 committed: .agents/skills and .cursor/skills as symlinks to ../.claude/skills."""
    d = repo(r, name)
    installer(r)("--mode", "sprint", d)
    for link in (".agents/skills", ".cursor/skills"):
        p = d / link
        if p.is_symlink() or p.is_file():
            p.unlink()
        else:
            subprocess.run(["rm", "-rf", str(p)], check=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.symlink_to("../.claude/skills")
    r.g(d, "add", "-A")
    r.g(d, "commit", "-q", "-m", "install the kit")
    return d


def windows_clone(r, src, name):
    dst = r.scratch / ("wc-clone-" + name)
    r.g(r.scratch, "clone", "-q", "-c", "core.symlinks=false", src, dst)
    r.g(dst, "config", "user.name", "Wendy")
    r.g(dst, "config", "user.email", "wendy@example.invalid")
    return dst


def doctor(r, d, *a):
    return r.run([r.bash, ".uak/bin/doctor", *a], cwd=d, allowed=None)


def skill_lines(out):
    return [l for l in out.stdout.splitlines() if ".agents/skills" in l or ".cursor/skills" in l]


def windows_clone_without_symlinks_has_skills(r):
    src = v600_repo(r, "src")
    c = windows_clone(r, src, "fix")
    expect((c / ".agents/skills").is_file(), "the simulated clone has the link as a text file")
    expect(not (c / ".agents/skills/test-first/SKILL.md").exists(), "and no skills there")
    out = doctor(r, c, "--fix")
    expect((c / ".agents/skills").is_dir() and not (c / ".agents/skills").is_symlink(), "--fix made .agents/skills a real folder: " + out.stdout[-700:])
    expect((c / ".agents/skills/test-first/SKILL.md").is_file(), "with the skills in it")
    expect(not (c / ".cursor/skills").is_file(), "the broken .cursor/skills file is gone (Cursor reads .agents/skills)")
    again = doctor(r, c)
    expect(not [l for l in skill_lines(again) if l.startswith("FAIL")], "doctor is clean afterwards: " + again.stdout[-700:])
    # uak start --fix repairs it too.
    c2 = windows_clone(r, src, "start")
    st = r.run([r.bash, ".uak/bin/uak", "start", "--fix"], cwd=c2, env={"UAK_AGENT": "wendy-1"}, allowed=None)
    expect((c2 / ".agents/skills/test-first/SKILL.md").is_file(), "uak start --fix repairs it: " + st.stdout[-600:])
    return "repaired"


def doctor_flags_a_symlink_checked_out_as_a_file(r):
    src = v600_repo(r, "flag")
    ok = doctor(r, src)
    expect(not [l for l in skill_lines(ok) if l.startswith("FAIL")], "a working symlink is not an error on Mac/Linux: " + ok.stdout[-500:])
    c = windows_clone(r, src, "flag")
    out = doctor(r, c)
    bad = [l for l in skill_lines(out) if l.startswith("FAIL")]
    expect(bad and "doctor --fix" in bad[0] and "core.symlinks" in bad[0], "a FAIL line names the cause and the fix: " + out.stdout[-700:])
    expect(out.returncode != 0, "doctor fails")
    # A stale copy: the folder is real but a skill differs from .claude/skills.
    s = repo(r, "stale")
    installer(r)("--mode", "sprint", s)
    (s / ".agents/skills/test-first/SKILL.md").write_text("an older version\n", encoding="utf-8")
    stale = doctor(r, s)
    expect([l for l in skill_lines(stale) if l.startswith("FAIL") and "stale" in l], "a stale copy is flagged: " + stale.stdout[-700:])
    doctor(r, s, "--fix")
    expect((s / ".agents/skills/test-first/SKILL.md").read_text(encoding="utf-8") == (s / ".claude/skills/test-first/SKILL.md").read_text(encoding="utf-8"),
           "--fix refreshes it")
    return "flagged"


def gemini_only_install_gets_skills(r):
    d = repo(r, "gemini")
    installer(r)("--mode", "sprint", "--harness", "gemini", d)
    expect((d / ".agents/skills/test-first/SKILL.md").is_file(), "Gemini reads .agents/skills: the skills are there without codex")
    expect((d / ".agents/skills/uak-plan/SKILL.md").is_file() and (d / ".gemini/commands/uak-plan.toml").is_file(), "and the phase scripts")
    expect(not (d / ".codex").exists() and not (d / ".cursor").exists(), "no other harness folder")
    return "skills for gemini alone"


def update_refreshes_copied_skills(r):
    d = repo(r, "update")
    run = installer(r)
    run("--mode", "sprint", d)
    # A Windows install of an older kit left stale copies in both folders.
    (d / ".agents/skills/test-first/SKILL.md").write_text("stale\n", encoding="utf-8")
    cur = d / ".cursor/skills"
    cur.mkdir(parents=True)
    (cur / "test-first").mkdir()
    (cur / "test-first/SKILL.md").write_text("stale too\n", encoding="utf-8")
    run("--update", "--mode", "sprint", d)
    expect((d / ".agents/skills/test-first/SKILL.md").read_text(encoding="utf-8") == (d / ".claude/skills/test-first/SKILL.md").read_text(encoding="utf-8"),
           "--update refreshes .agents/skills")
    expect(not (d / ".cursor/skills").exists(), "the kit's old copy in .cursor/skills is removed (Cursor reads .agents/skills)")
    # A folder the team made themselves stays.
    (d / ".cursor/skills/mine").mkdir(parents=True)
    (d / ".cursor/skills/mine/SKILL.md").write_text("theirs\n", encoding="utf-8")
    run("--update", "--mode", "sprint", d)
    expect((d / ".cursor/skills/mine/SKILL.md").is_file(), "a skill of the team's own in .cursor/skills stays")
    # An update over a link checked out as a text file (a Windows clone) works.
    src = v600_repo(r, "upd-src")
    c = windows_clone(r, src, "upd")
    run("--update", "--mode", "sprint", c)
    expect((c / ".agents/skills/test-first/SKILL.md").is_file() and (c / ".agents/skills").is_dir(), "--update over a text-file link makes the folder")
    return "refreshed"


TESTS = [windows_clone_without_symlinks_has_skills, doctor_flags_a_symlink_checked_out_as_a_file, gemini_only_install_gets_skills,
         update_refreshes_copied_skills]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-skills-win-") as tmp:
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
    print("SKILLS_WINDOWS_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
