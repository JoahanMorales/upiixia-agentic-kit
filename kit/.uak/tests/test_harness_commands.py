#!/usr/bin/env python3
"""UAK-040: the 13 /uak-* phase scripts reach Codex, Cursor and Gemini CLI natively, from one source
(.claude/commands/uak-X.md). Why (a teammate, 2026-11-10): in Codex and Cursor the kit's commands "were not up to date";
neither had a /uak-*, and Codex no longer reads custom prompts. Codex and Cursor load Agent Skills from
.agents/skills/NAME/SKILL.md ($NAME or /NAME), Gemini CLI has .gemini/commands/NAME.toml. Real install.sh into fresh
Git repositories; gen_harness.py run on a copy of the sources."""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def phases(r):
    return sorted(p.stem for p in (r.package / ".claude/commands").glob("uak-*.md"))


def rd(path):
    expect(path.is_file(), "missing: %s" % path.name)
    return path.read_text(encoding="utf-8")


def install(r, name, *args):
    d = r.scratch / ("hc-" + name)
    d.mkdir(parents=True)
    r.g(d, "init", "-q", "-b", "main")
    out = subprocess.run([r.bash, str(r.package.parent / "install.sh"), "--mode", "sprint", *args, str(d)], capture_output=True,
                         text=True, errors="replace", env=r.env, timeout=180, stdin=subprocess.DEVNULL)
    expect(out.returncode == 0, "install failed: " + out.stdout[-300:] + out.stderr[-300:])
    return d


def every_phase_command_reaches_every_harness(r):
    names = phases(r)
    expect(len(names) == 13, "13 phase scripts, found %d" % len(names))
    d = install(r, "all")
    for n in names:
        expect((d / ".claude/commands" / (n + ".md")).is_file(), "Claude Code: /%s" % n)
        expect((d / ".agents/skills" / n / "SKILL.md").is_file(), "Codex and Cursor: .agents/skills/%s/SKILL.md" % n)
        toml = d / ".gemini/commands" / (n + ".toml")
        expect(toml.is_file() and 'prompt = """' in toml.read_text(encoding="utf-8"), "Gemini CLI: .gemini/commands/%s.toml" % n)
        expect(not (d / ".claude/skills" / n).exists(), "Claude Code would show /%s twice (command and skill)" % n)
        text = (d / ".agents/skills" / n / "SKILL.md").read_text(encoding="utf-8")
        expect(re.search(r"^name: %s$" % n, text, re.M) and re.search(r"^description: \S", text, re.M), "%s has name and description" % n)
    expect(not (d / ".agents/skills").is_symlink(), ".agents/skills must be a real directory (a link would write into .claude/skills)")
    expect((d / ".agents/skills/test-first/SKILL.md").is_file(), "the kit's regular skills are still there for Codex and Cursor")
    expect(not (d / ".cursor/commands").exists(), "Cursor reads the skills; a second /uak-X from .cursor/commands would be a duplicate")
    # Only the harnesses the team installed.
    only = install(r, "codex", "--harness", "codex")
    expect((only / ".agents/skills/uak-plan/SKILL.md").is_file() and not (only / ".gemini").exists(), "--harness codex: skills, no Gemini files")
    gem = install(r, "gemini", "--harness", "gemini")
    expect((gem / ".gemini/commands/uak-plan.toml").is_file(), "--harness gemini: its commands")
    claude = install(r, "claude", "--harness", "claude")
    expect(not (claude / ".agents").exists() and not (claude / ".gemini").exists(), "--harness claude: .claude only")
    return {"phases": len(names)}


def phase_skills_are_not_model_invoked(r):
    for n in phases(r):
        base = r.package / ".agents/skills" / n
        skill = rd(base / "SKILL.md")
        head = skill.split("---")[1]
        expect(re.search(r"^disable-model-invocation: true$", head, re.M), "%s: Cursor needs disable-model-invocation: true" % n)
        yaml = rd(base / "agents/openai.yaml")
        expect(re.search(r"^policy:\n  allow_implicit_invocation: false$", yaml, re.M), "%s: Codex needs allow_implicit_invocation: false" % n)
        # Gemini CLI skills have no such switch: the text itself says to run only when asked.
        expect("only when the user" in skill.lower(), "%s: the skill text says it runs only when the user asks (Gemini)" % n)
        expect("model:" not in head, "%s: a Claude model name means nothing to the other harnesses" % n)
    return {"checked": len(phases(r))}


def generated_commands_match_their_source(r):
    tmp = r.scratch / "hc-gen"
    (tmp / "scripts").mkdir(parents=True)
    shutil.copy(r.package.parent / "scripts/gen_harness.py", tmp / "scripts/gen_harness.py")
    shutil.copytree(r.package / ".claude", tmp / "kit/.claude")
    gen = lambda *a: subprocess.run([sys.executable, "-I", str(tmp / "scripts/gen_harness.py"), *a], capture_output=True, text=True)
    expect(gen().returncode == 0, "generation works")
    ok = gen("--check")
    expect(ok.returncode == 0, "fresh output is not stale: " + ok.stdout)
    src = tmp / "kit/.claude/commands/uak-plan.md"
    text = src.read_text(encoding="utf-8")
    skill = rd(tmp / "kit/.agents/skills/uak-plan/SKILL.md")
    first = [l for l in text.split("---\n", 2)[2].splitlines() if l.strip()][0]
    expect(first in skill, "the script's body is in the skill")
    expect(first in rd(tmp / "kit/.gemini/commands/uak-plan.toml"), "and in the Gemini command")
    src.write_text(text + "A new last step.\n", encoding="utf-8")
    bad = gen("--check")
    expect(bad.returncode == 1 and "uak-plan" in bad.stdout, "an edited source makes --check fail: rc %d %s" % (bad.returncode, bad.stdout))
    gen()
    expect(gen("--check").returncode == 0, "regenerating fixes it")
    src.unlink()
    orphan = gen("--check")
    expect(orphan.returncode == 1 and "uak-plan" in orphan.stdout, "a generated copy of a removed script is stale: " + orphan.stdout)
    return {"stale": "caught"}


TESTS = [every_phase_command_reaches_every_harness, phase_skills_are_not_model_invoked, generated_commands_match_their_source]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-harness-cmd-") as tmp:
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
    print("HARNESS_COMMANDS_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
