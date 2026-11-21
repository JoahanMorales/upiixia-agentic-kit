#!/usr/bin/env python3
"""UAK-094: the banner says the version of kit/.uak/VERSION, and kit_lint fails when it does not.
Why (release v6.4.0, 2026-11-16): the banner still said v6.1 after three releases; the eyebrow was a literal and no
check read it. Neither Playwright nor Pillow is needed: make_media.py loads them where it renders."""
import argparse
import importlib.util
import tempfile
from pathlib import Path

from test_hack import expect

REPO = Path(__file__).resolve().parents[3]


def load(name):
    p = REPO / "scripts" / (name + ".py")
    if not p.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name + "_under_test", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def banner_text_uses_version_file(tmp):
    mod = load("make_media")
    mod._FONT_CSS = ""  # no font download, no browser
    version = tmp / "VERSION"
    version.write_text("9.8.7\n", encoding="utf-8")
    mod.VERSION_FILE = version
    expect(mod.banner_version() == "9.8", "major.minor expected, got %r" % mod.banner_version())
    html = mod.banner_html()
    expect("v9.8 · multi-agent orchestration" in html, "the eyebrow must carry VERSION's major.minor")
    expect("v6.4 ·" not in html, "no literal version left in the banner")
    version.write_bytes(b"10.2.0\r\n")  # CRLF on Windows
    expect(mod.banner_version() == "10.2", "CRLF in VERSION: %r" % mod.banner_version())
    return "9.8 and 10.2"


def lint_flags_a_stale_banner(tmp):
    lint = load("kit_lint")
    root = tmp / "repo"
    (root / "kit/.uak").mkdir(parents=True)
    (root / "docs/media").mkdir(parents=True)
    (root / "kit/.uak/VERSION").write_text("6.5.0\n", encoding="utf-8")
    (root / "docs/media/banner.png").write_bytes(b"png")
    (root / "docs/media/banner.version").write_text("6.4\n", encoding="utf-8")
    lint.ROOT = root
    found = []
    lint.check_banner(found)
    expect(len(found) == 1 and "6.4" in found[0] and "6.5" in found[0], "a stale banner is one finding: %r" % found)
    expect("scripts/make_media.py" in found[0], "the finding names the regenerate command: " + found[0])
    (root / "docs/media/banner.version").write_text("6.5\r\n", encoding="utf-8")
    found = []
    lint.check_banner(found)
    expect(not found, "a current banner is clean: %r" % found)
    real = REPO / "docs/media/banner.version"
    expect(real.is_file(), "docs/media/banner.version is committed for the current banner")
    lint.ROOT = REPO
    found = []
    lint.check_banner(found)
    expect(not found, "this repo's banner matches VERSION: %r" % found)
    return "stale flagged"


TESTS = [banner_text_uses_version_file, lint_flags_a_stale_banner]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.parse_args()
    if load("make_media") is None:
        print("PASS skipped (no kit source repository here: scripts/ is not shipped)")
        print("BANNER_VERSION_RESULT PASS")
        return 0
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak bánner-") as tmp:
        for test in TESTS:
            try:
                print("PASS %s (%s)" % (test.__name__, test(Path(tmp))))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("BANNER_VERSION_RESULT %s" % ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
