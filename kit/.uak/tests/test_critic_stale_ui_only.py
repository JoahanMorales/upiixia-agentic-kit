#!/usr/bin/env python3
"""UAK-093: critic.txt about commit A made `done` refuse at commit B ("critic.txt is about another commit", 3 times in
one night on a private sprint) even when A..B touched no UI path. It stays valid across commits that touch no UI path;
a UI change keeps the refusal; the missing and stale messages name the fallback for sessions whose Agent tool does not
list design-critic (UpiixSol, Nov 2026). Real git, a local bare remote."""
import argparse
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_v57 import set_project

PROJECT = ("Backlog-Approved: yes\nAutonomy: yes\nAuto-Merge: yes\nReview-Mode: claims\nEvents-Per-Session: 100\n"
           "Checkpoint-Percent: 60\nUI-Paths: src/\n")


def ui_task(r, name):
    f = r.fixture(name, count=1)
    set_project(f, PROJECT)
    f.claim(0, "HACK-001")
    wt = f.worktrees[0]
    (wt / "src").mkdir(exist_ok=True)
    (wt / "src/one.txt").write_text("ui\n", encoding="utf-8")
    r.g(wt, "add", "src/one.txt")
    r.g(wt, "commit", "-q", "-m", "ui")
    r.g(wt, "push", "-q", "origin", f.branches[0])
    sha = r.g(wt, "rev-parse", "--short=7", "HEAD").stdout.strip()
    shots = wt / ".uak-shots/HACK-001"
    shots.mkdir(parents=True)
    (shots / "critic.txt").write_text("VERDICT: SHIP %s\n" % sha, encoding="utf-8")
    return f, shots


def done(f):
    return f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1000010, allowed=None)


def shots_ok(shots):
    for name in ("1280.png", "390.png"):
        (shots / name).write_bytes(b"\x89PNG fake")


def commit(r, f, rel, text, msg):
    wt = f.worktrees[0]
    (wt / rel).parent.mkdir(parents=True, exist_ok=True)
    (wt / rel).write_text(text, encoding="utf-8")
    r.g(wt, "add", rel)
    r.g(wt, "commit", "-q", "-m", msg)
    r.g(wt, "push", "-q", "origin", f.branches[0])


def critique_valid_after_non_ui_commit(r):
    f, shots = ui_task(r, "cs-non-ui")
    shots_ok(shots)
    commit(r, f, "notes/readme.txt", "no UI here\n", "a note outside UI-Paths")
    out = done(f)
    expect(out.returncode == 0 and "REVIEW" in out.stdout, "critic.txt still counts after a non-UI commit: rc %d %s" % (out.returncode, (out.stdout + out.stderr)[-500:]))
    return "valid"


def critique_stale_after_ui_commit(r):
    f, shots = ui_task(r, "cs-ui")
    shots_ok(shots)
    commit(r, f, "src/two.txt", "more UI\n", "a UI change")
    out = done(f)
    text = out.stdout + out.stderr
    expect(out.returncode == 3 and "about another commit" in text, "a UI commit keeps the refusal: rc %d %s" % (out.returncode, text[-500:]))
    return "stale"


def messages_name_the_fallback(r):
    f, shots = ui_task(r, "cs-msgs")
    shots_ok(shots)
    commit(r, f, "src/two.txt", "more UI\n", "a UI change")
    stale = done(f)
    expect("design-critic.md" in stale.stdout + stale.stderr and "writing the same critic.txt" in stale.stdout + stale.stderr,
           "the stale message names the fallback: " + (stale.stdout + stale.stderr)[-600:])
    (shots / "critic.txt").unlink()
    missing = done(f)
    expect("design-critic.md" in missing.stdout + missing.stderr and "writing the same critic.txt" in missing.stdout + missing.stderr,
           "the missing message names the fallback: " + (missing.stdout + missing.stderr)[-600:])
    skill = (r.package / ".uak/skills/product-ui/SKILL.md").read_text(encoding="utf-8")
    expect("design-critic.md" in skill and "same critic.txt" in skill, "the product-ui skill documents the fallback")
    return "named"


TESTS = [critique_valid_after_non_ui_commit, critique_stale_after_ui_commit, messages_name_the_fallback]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="uak-critic-stale-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ != args.case:
                continue
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("CRITIC_STALE_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
