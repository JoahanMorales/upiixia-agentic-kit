#!/usr/bin/env python3
"""UAK-030: the UI gate of `done` wanted exactly 1280.png and 390.png in .uak-shots/ID/. The critic approved
landing-1280.png and voz-1280.png and `done` refused twice (DevDay hackathon). Now 1280.png or exactly ONE *-1280.png
counts (same for 390); two candidates are refused by name. Real git, a local bare remote."""
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


def a_prefixed_main_shot_is_accepted(r):
    f, shots = ui_task(r, "us-prefixed")
    for name in ("landing-1280.png", "landing-390.png"):
        (shots / name).write_bytes(b"\x89PNG fake")
    out = done(f)
    expect(out.returncode == 0 and "REVIEW" in out.stdout, "one landing-1280.png and one landing-390.png should pass: rc %d" % out.returncode)
    return "accepted"


def two_prefixed_shots_are_refused_by_name(r):
    f, shots = ui_task(r, "us-two")
    for name in ("landing-1280.png", "voz-1280.png", "landing-390.png"):
        (shots / name).write_bytes(b"\x89PNG fake")
    out = done(f)
    text = out.stdout + out.stderr
    expect(out.returncode == 3, "two *-1280.png and no 1280.png must be refused, rc %d" % out.returncode)
    expect("landing-1280.png" in text and "voz-1280.png" in text and "main screen" in text,
           "the refusal names both candidates and asks which is the main screen: " + text[-400:])
    (shots / "1280.png").write_bytes(b"\x89PNG fake")
    ok = done(f)
    expect(ok.returncode == 0, "an exact 1280.png wins over the prefixed ones: rc %d" % ok.returncode)
    critic = (r.package / ".claude/agents/design-critic.md").read_text(encoding="utf-8")
    expect("must be saved as `1280.png` and `390.png`" in critic, "design-critic.md tells the critic the exact names")
    return "refused by name"


TESTS = [a_prefixed_main_shot_is_accepted, two_prefixed_shots_are_refused_by_name]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="uak-ui-shots-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ != args.case:
                continue
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("UI_SHOT_NAMES_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
