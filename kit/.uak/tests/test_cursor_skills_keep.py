#!/usr/bin/env python3
"""UAK-047: install --update deleted a kit skill folder from .cursor/skills when only its name matched .claude/skills,
so a team's edited copy was lost (v6.1.0 review of UAK-041). A folder goes only when every file in it equals a version
the kit shipped (known-files.txt hashes, as the rest of --update decides); an edited copy stays and is named."""
import argparse
import shutil
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_skills_windows_clone import installer, repo

KEPT = "kept .cursor/skills/test-first: edited by the team; Cursor also reads .agents/skills"


def installed_with_cursor_copy(r, name):
    d = repo(r, name)
    run = installer(r)
    run("--mode", "sprint", d)
    cur = d / ".cursor/skills"
    cur.mkdir(parents=True, exist_ok=True)
    shutil.copytree(d / ".claude/skills/test-first", cur / "test-first")
    return d, run


def unedited_kit_skill_copy_is_removed(r):
    d, run = installed_with_cursor_copy(r, "ck-plain")
    out = run("--update", "--mode", "sprint", d)
    expect(not (d / ".cursor/skills/test-first").exists(), "an unedited kit copy is removed: " + out.stdout[-500:])
    expect("kept .cursor/skills" not in out.stdout, "and nothing is said about keeping it")
    # A checkout with CRLF line endings is still the kit's version.
    d2, run2 = installed_with_cursor_copy(r, "ck-crlf")
    f = d2 / ".cursor/skills/test-first/SKILL.md"
    f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    run2("--update", "--mode", "sprint", d2)
    expect(not (d2 / ".cursor/skills/test-first").exists(), "a CRLF copy of the kit's files is removed too")
    return "removed"


def edited_kit_skill_copy_is_kept_and_named(r):
    d, run = installed_with_cursor_copy(r, "ck-edited")
    f = d / ".cursor/skills/test-first/SKILL.md"
    f.write_text(f.read_text(encoding="utf-8") + "\nOur team rule.\n", encoding="utf-8")
    (d / ".cursor/skills/mine").mkdir()
    (d / ".cursor/skills/mine/SKILL.md").write_text("theirs\n", encoding="utf-8")
    out = run("--update", "--mode", "sprint", d)
    expect("Our team rule." in f.read_text(encoding="utf-8"), "the edited copy stays: " + out.stdout[-500:])
    expect(KEPT in out.stdout, "and install names it: " + out.stdout[-600:])
    expect((d / ".cursor/skills/mine/SKILL.md").is_file(), "the team's own skill stays")
    # An extra file in an otherwise unedited copy counts as an edit.
    d2, run2 = installed_with_cursor_copy(r, "ck-extra")
    (d2 / ".cursor/skills/test-first/NOTES.md").write_text("ours\n", encoding="utf-8")
    out2 = run2("--update", "--mode", "sprint", d2)
    expect((d2 / ".cursor/skills/test-first/NOTES.md").is_file() and KEPT in out2.stdout, "a copy with a file of the team's stays: " + out2.stdout[-500:])
    return "kept and named"


TESTS = [unedited_kit_skill_copy_is_removed, edited_kit_skill_copy_is_kept_and_named]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-cursor-keep-") as tmp:
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
    print("CURSOR_SKILLS_KEEP_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
