#!/usr/bin/env python3
"""UAK-060: /uak-design-lock starts with a landing round the human picks from (F0, 2026-11-11: the human scored six
frontends 2.8/5 on oversized type and plainness). The command text and its generated harness copies carry the round;
a short event gets one round of 4 and builds the landing for real. Text checks, no temp files, no network."""
import argparse
import re
import subprocess
import sys
from pathlib import Path


def expect(ok, msg):
    if not ok:
        raise AssertionError(msg)


def flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


def design_lock_runs_a_landing_round(pkg):
    t = flat(pkg / ".claude/commands/uak-design-lock.md")
    for needle in ("uak design round --screen landing --n 6", "8 when the event is 24 h or more", "one agent per variant in parallel",
                   "uak design shoot", "uak design pick", "--k 2", "design round --from", "bred round of 4",
                   "genome fills", "DESIGN.md", "type, scale, color, components, motion", "landing-story"):
        expect(needle in t, "uak-design-lock names: " + needle)
    expect("Propose 3 directions" not in t, "the old steps 2-4 are replaced")
    for needle in ("WITHOUT `--yes`", "cost line", "design pick R<k> --k 1", "also under 6 h", "stay under `.uak/design/rounds`",
                   "rebuilt in the stack's landing route", "not copied as static HTML"):
        expect(needle in t, "uak-design-lock names: " + needle)
    expect("Delete the losing HTML" not in t, "the stale delete step is gone")
    for kept in ("5. Lock it", "AppShell", "three locked screens", "design-critic", "uak decision"):
        expect(kept in t or kept.lower() in t.lower(), "step 5-6 kept: " + kept)


def short_event_single_round(pkg):
    t = flat(pkg / ".claude/commands/uak-design-lock.md")
    expect(re.search(r"under 6 h\)?:? one round of 4, no breeding", t), "short event: one round of 4, no breeding")
    expect("built for real in the first hours" in t and "not left for the last hour" in t, "the landing is built early")


def generated_harness_matches(pkg):
    for rel in (".gemini/commands/uak-design-lock.toml", ".agents/skills/uak-design-lock/SKILL.md"):
        expect("uak design round --screen landing" in (pkg / rel).read_text(encoding="utf-8"), rel + " carries the round")
    expect((pkg / ".agents/skills/uak-design-lock/agents/openai.yaml").is_file(), "openai.yaml exists")
    gen = pkg.parent / "scripts" / "gen_harness.py"
    if gen.is_file():
        out = subprocess.run([sys.executable, str(gen), "--check"], capture_output=True, text=True, errors="replace", timeout=120)
        expect(out.returncode == 0, "gen_harness.py --check: " + (out.stdout + out.stderr)[-500:])


TESTS = [design_lock_runs_a_landing_round, short_event_single_round, generated_harness_matches]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    pkg = args.package.resolve()
    fails = 0
    for t in TESTS:
        try:
            t(pkg)
            print("PASS " + t.__name__)
        except AssertionError as e:
            fails += 1
            print("FAIL %s (%s)" % (t.__name__, e))
    print("DESIGN_LOCK_ROUND_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
