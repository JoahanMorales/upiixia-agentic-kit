#!/usr/bin/env python3
"""UI-016: the README (the kit's landing) shows a short demonstration video, from zero to a deployed product.
Why: in the 2026-11-13 test rounds novices did not know which steps happen in the setup page, in a terminal or by the
agents. The video is small (H.264 MP4 <= 3 MB, poster GIF <= 1.5 MB), under 90 s, captioned in English and Spanish,
rendered from pinned source in docs/video/. ffprobe checks the duration when it is installed (not on every CI runner);
sizes, markup and captions are always checked."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MEDIA = ROOT / "docs" / "media"
MP4 = MEDIA / "tutorial.mp4"
GIF = MEDIA / "tutorial-poster.gif"
SRT = {"en": MEDIA / "tutorial-en.srt", "es": MEDIA / "tutorial-es.srt"}
MAX_SECONDS = 90.0
TIME = re.compile(r"^(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)$")


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def seconds(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(path):
    """Return [(start, end, text)]; raise on a malformed cue."""
    expect(path.is_file(), "docs/media/%s exists" % path.name)
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
    expect(text, "%s is not empty" % path.name)
    cues = []
    for n, block in enumerate(re.split(r"\n\s*\n", text), 1):
        lines = block.split("\n")
        expect(len(lines) >= 3, "%s cue %d has an index, a time line and text: %r" % (path.name, n, block))
        expect(lines[0].strip() == str(n), "%s cue %d is numbered %d, not %r" % (path.name, n, n, lines[0]))
        m = TIME.match(lines[1].strip())
        expect(m, "%s cue %d has a valid time line: %r" % (path.name, n, lines[1]))
        start, end = seconds(*m.groups()[:4]), seconds(*m.groups()[4:])
        expect(start < end, "%s cue %d starts before it ends" % (path.name, n))
        expect(not cues or cues[-1][1] <= start, "%s cue %d does not overlap the previous one" % (path.name, n))
        cues.append((start, end, " ".join(l.strip() for l in lines[2:])))
    return cues


def video_is_short_and_small():
    expect(MP4.is_file(), "docs/media/tutorial.mp4 exists")
    expect(MP4.stat().st_size <= 3 * 1024 * 1024, "the MP4 is at most 3 MB: %d bytes" % MP4.stat().st_size)
    head = MP4.read_bytes()
    expect(head[4:8] == b"ftyp", "the MP4 is an ISO media file (ftyp box)")
    expect(b"avc1" in head, "the MP4 video track is H.264 (avc1)")
    expect(GIF.is_file(), "docs/media/tutorial-poster.gif exists")
    expect(GIF.stat().st_size <= 1.5 * 1024 * 1024, "the poster GIF is at most 1.5 MB: %d bytes" % GIF.stat().st_size)
    expect(GIF.read_bytes()[:6] in (b"GIF89a", b"GIF87a"), "the poster is a GIF")
    # Source: pinned versions and one documented render command.
    video = ROOT / "docs" / "video"
    pkg = json.loads((video / "package.json").read_text(encoding="utf-8"))
    deps = dict(pkg.get("dependencies", {}), **pkg.get("devDependencies", {}))
    expect(deps, "docs/video/package.json names its dependencies")
    for name, ver in deps.items():
        expect(re.match(r"^\d+\.\d+\.\d+$", ver), "%s is pinned to an exact version, not %r" % (name, ver))
    expect((video / "package-lock.json").is_file(), "docs/video has a lockfile")
    expect("render" in pkg.get("scripts", {}), "package.json has a render script")
    expect("npm run render" in (video / "README.md").read_text(encoding="utf-8"), "docs/video/README.md names the command")
    expect(not (video / "node_modules").exists() or "node_modules" in
           (ROOT / ".gitignore").read_text(encoding="utf-8"), "node_modules is never committed")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        print("SKIP duration check: ffprobe is not installed (sizes, markup and captions were still checked)")
        return
    out = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height",
                          "-of", "default=noprint_wrappers=1", str(MP4)], capture_output=True, text=True, check=True)
    info = dict(l.split("=", 1) for l in out.stdout.split() if "=" in l)
    duration = float(info["duration"])
    expect(duration < MAX_SECONDS, "the video is under 90 s: %.1f s" % duration)
    expect(duration >= 30, "the video walks the whole story (at least 30 s): %.1f s" % duration)
    expect(info.get("codec_name") == "h264", "ffprobe sees H.264: %r" % info.get("codec_name"))
    expect((info.get("width"), info.get("height")) in (("1280", "720"), ("960", "540")),
           "the video is 1280x720 or 960x540: %sx%s" % (info.get("width"), info.get("height")))
    last_end = parse_srt(SRT["en"])[-1][1]
    expect(last_end <= duration + 0.5, "captions end with the video: %.1f > %.1f" % (last_end, duration))


def readme_shows_the_demo():
    lines = (ROOT / "README.md").read_text(encoding="utf-8").split("\n")
    text = "\n".join(lines)
    poster = re.search(r'\[<img src="docs/media/tutorial-poster\.gif"[^>]*alt="[^"]+"[^>]*>\]\(docs/media/tutorial\.mp4\)',
                       text)
    expect(poster, "the README shows the poster GIF linking to docs/media/tutorial.mp4 (with alt text)")
    row = text[:poster.start()].count("\n")
    banner = next((i for i, l in enumerate(lines) if "docs/media/banner.png" in l), None)
    first_section = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    expect(banner is not None and banner < row < first_section,
           "the poster sits near the top: after the banner (line %s), before the first section (line %d), at %d"
           % (banner, first_section, row))
    caption = next((l for l in lines if "Demo (simulated)" in l), "")
    expect(caption, "a line names the demo as simulated")
    expect("from zero to a deployed product" in caption, "the line says what the demo shows: %r" % caption)
    expect("(docs/media/tutorial-en.srt)" in caption and "(docs/media/tutorial-es.srt)" in caption,
           "the line links the English and Spanish captions: %r" % caption)
    expect("English" in caption and "Español" in caption, "the caption links are named by language: %r" % caption)


def captions_exist_in_both_languages():
    en, es = parse_srt(SRT["en"]), parse_srt(SRT["es"])
    expect(len(en) >= 6, "the English captions tell the story in several cues: %d" % len(en))
    expect(len(en) == len(es), "both languages have the same cue count: en %d, es %d" % (len(en), len(es)))
    for i, (a, b) in enumerate(zip(en, es), 1):
        expect(a[:2] == b[:2], "cue %d has the same timing in both languages: %r vs %r" % (i, a[:2], b[:2]))
        expect(a[2] != b[2], "cue %d is translated: %r" % (i, a[2]))
    expect(en[-1][1] < MAX_SECONDS, "the captions end before 90 s: %.1f" % en[-1][1])
    words = " ".join(c[2] for c in en).lower()
    for word in ("install", "plan", "review", "merge", "deployed", "demonstration"):
        expect(word in words, "the English captions mention %r" % word)


def main():
    failed = 0
    for test in (video_is_short_and_small, readme_shows_the_demo, captions_exist_in_both_languages):
        try:
            test()
            print("PASS " + test.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL %s: %s" % (test.__name__, exc))
    print("TUTORIAL_VIDEO_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
