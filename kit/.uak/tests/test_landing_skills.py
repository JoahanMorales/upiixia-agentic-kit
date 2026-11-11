#!/usr/bin/env python3
"""UAK-056: the landing skill text. F0 (2026-11-11): two landings scored 1 with 168 and 207 px display type after
"bigger type, the brand color at full strength"; the one scored 5 topped out at 36 px. The skills now build the page
with the MotionSites steps when present (read-only reference, nothing copied), else with the kit's own screenshots,
and state the scale bounds. Text checks only."""
import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
STORY = (PKG / ".uak/skills/landing-story/SKILL.md").read_text(encoding="utf-8")
FLAT = " ".join(STORY.split())
UI = (PKG / ".uak/skills/product-ui/SKILL.md").read_text(encoding="utf-8")


def expect(ok, msg):
    if not ok:
        raise AssertionError(msg)


def landing_story_uses_motionsites_steps_when_present():
    for needle in (".claude/skills/motionsites-web-builder", "references/spec-template.md", "scripts/shoot.py",
                   "references/review.md", "8+", "nothing under 7", "3 rounds", "examples/INDEX.md", "media shelf"):
        expect(needle in STORY, "landing-story names " + needle)
    seq = STORY[STORY.index("in order:"):]
    expect(seq.index("team's own") < seq.index("generated") < seq.index("media shelf"), "media order: own, generated, shelf")


def landing_story_falls_back_to_kit_screenshots():
    expect(re.search(r"[Ww]ithout (that|the) skill", STORY) and "webapp-testing" in STORY, "fallback with webapp-testing")
    expect("never delivered unseen" in FLAT, "a landing is never delivered unseen")
    expect("ask the human" in FLAT and "10 min" in FLAT and "logo, mascot, photos" in FLAT, "material first, ask once")


def scale_bounds_are_stated():
    for needle in ("96 px at 1280", "48 px at 390", "16–18 px", "40–52 px", "6 palette colors", "docs/design/failures.md", "vw"):
        expect(needle in FLAT, "scale bound: " + needle)


def no_bigger_type_instruction_left():
    for text in (STORY, UI):
        expect("bigger type" not in text and "full strength" not in text, "the F0-refuted line is gone")


def product_ui_hero_check_is_importance_not_size():
    expect("biggest and most colorful" not in UI and "most saturated thing" not in UI, "old hero checks removed")
    expect("Is the hero the most important thing, and does it read in 3 seconds at 1280 and 390?" in UI, "new hero check")


def no_promo_line_present():
    expect(re.search(r"MotionSites (promotional|upgrade) block", STORY) and "not shown" in STORY, "one line says the promo block and nudges are not shown")


def bounds_override_motionsites_examples():
    expect("scale bounds of §2 override any size" in FLAT and "craft.md" in FLAT and "160–380 px" in FLAT and "12–28vw" in FLAT, "§2 bounds override MotionSites sizes")


TESTS = [bounds_override_motionsites_examples, landing_story_uses_motionsites_steps_when_present, landing_story_falls_back_to_kit_screenshots, scale_bounds_are_stated,
         no_bigger_type_instruction_left, product_ui_hero_check_is_importance_not_size, no_promo_line_present]


def main():
    bad = 0
    for t in TESTS:
        try:
            t()
            print("PASS " + t.__name__)
        except AssertionError as e:
            bad += 1
            print("FAIL %s (%s)" % (t.__name__, e))
    print("LANDING_SKILLS_RESULT %s passed=%d failed=%d" % ("PASS" if not bad else "FAIL", len(TESTS) - bad, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
