#!/usr/bin/env python3
"""UI-016: the kit ships a short demonstration video, from zero to a deployed product, for its local setup page.
Why: in the 2026-11-13 test rounds novices did not know which steps happen in the setup page, in a terminal or by the
agents. The video is small (H.264 MP4 <= 3 MB, JPEG poster <= 150 KB), under 90 s, captioned in English and Spanish
(WebVTT), rendered from pinned source in docs/video/, and installed with the kit in .uak/media/ (UI-017 shows it).
ffprobe checks the duration when it is installed (not on every CI runner); sizes, captions and the install always run."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MEDIA = ROOT / "kit" / ".uak" / "media"
MP4 = MEDIA / "tutorial.mp4"
POSTER = MEDIA / "tutorial-poster.jpg"
VTT = {"en": MEDIA / "tutorial-en.vtt", "es": MEDIA / "tutorial-es.vtt"}
FILES = ("tutorial.mp4", "tutorial-poster.jpg", "tutorial-en.vtt", "tutorial-es.vtt")
MAX_SECONDS = 90.0
MB = 1024 * 1024
TIME = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d\d\d) --> (\d\d):(\d\d):(\d\d)\.(\d\d\d)$")


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def seconds(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(path):
    """Return [(start, end, text)]; raise on a malformed file or cue."""
    expect(path.is_file(), "kit/.uak/media/%s exists" % path.name)
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    blocks = re.split(r"\n\s*\n", text)
    expect(blocks[0].split("\n")[0].startswith("WEBVTT"), "%s starts with WEBVTT" % path.name)
    cues = []
    for block in blocks[1:]:
        lines = block.split("\n")
        if not TIME.match(lines[0].strip()):
            lines = lines[1:]  # an optional cue identifier
        expect(len(lines) >= 2, "%s cue %d has a time line and text: %r" % (path.name, len(cues) + 1, block))
        m = TIME.match(lines[0].strip())
        expect(m, "%s cue %d has a valid time line: %r" % (path.name, len(cues) + 1, lines[0]))
        start, end = seconds(*m.groups()[:4]), seconds(*m.groups()[4:])
        expect(start < end, "%s cue %d starts before it ends" % (path.name, len(cues) + 1))
        expect(not cues or cues[-1][1] <= start, "%s cue %d does not overlap the previous one" % (path.name, len(cues) + 1))
        cues.append((start, end, " ".join(l.strip() for l in lines[1:])))
    expect(cues, "%s has cues" % path.name)
    return cues


def video_is_short_and_small():
    expect(MP4.is_file(), "kit/.uak/media/tutorial.mp4 exists")
    expect(MP4.stat().st_size <= 3 * MB, "the MP4 is at most 3 MB: %d bytes" % MP4.stat().st_size)
    data = MP4.read_bytes()
    expect(data[4:8] == b"ftyp", "the MP4 is an ISO media file (ftyp box)")
    expect(b"avc1" in data, "the MP4 video track is H.264 (avc1)")
    expect(POSTER.is_file(), "kit/.uak/media/tutorial-poster.jpg exists")
    expect(POSTER.stat().st_size <= 150 * 1024, "the poster is at most 150 KB: %d bytes" % POSTER.stat().st_size)
    expect(POSTER.read_bytes()[:3] == b"\xff\xd8\xff", "the poster is a JPEG")
    total = sum(p.stat().st_size for p in MEDIA.iterdir() if p.is_file())
    expect(total <= 3.5 * MB, "the installed kit grows by at most 3.5 MB: %d bytes" % total)
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
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        print("SKIP duration check: ffprobe is not installed (sizes, captions and the install were still checked)")
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
    last_end = parse_vtt(VTT["en"])[-1][1]
    expect(last_end <= duration + 0.5, "captions end with the video: %.1f > %.1f" % (last_end, duration))


def captions_exist_in_both_languages():
    en, es = parse_vtt(VTT["en"]), parse_vtt(VTT["es"])
    expect(len(en) >= 6, "the English captions tell the story in several cues: %d" % len(en))
    expect(len(en) == len(es), "both languages have the same cue count: en %d, es %d" % (len(en), len(es)))
    for i, (a, b) in enumerate(zip(en, es), 1):
        expect(a[:2] == b[:2], "cue %d has the same timing in both languages: %r vs %r" % (i, a[:2], b[:2]))
        expect(a[2] != b[2], "cue %d is translated: %r" % (i, a[2]))
    expect(en[-1][1] < MAX_SECONDS, "the captions end before 90 s: %.1f" % en[-1][1])
    words = " ".join(c[2] for c in en).lower()
    for word in ("install", "plan", "review", "merge", "deployed", "demonstration"):
        expect(word in words, "the English captions mention %r" % word)
    palabras = " ".join(c[2] for c in es).lower()
    for word in ("instala", "plan", "revisa", "desplegad", "demostración"):
        expect(word in palabras, "the Spanish captions mention %r" % word)


def blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def media_ships_with_the_kit():
    for name in FILES:
        expect((MEDIA / name).is_file(), "kit/.uak/media/%s exists" % name)
    known = set((ROOT / "kit/.uak/settings/known-files.txt").read_text(encoding="utf-8").split())
    for name in FILES:
        data = (MEDIA / name).read_bytes()
        # A Windows checkout may turn the captions' LF into CRLF; Git hashes what it stores (LF).
        sha = blob(data if name.endswith(".mp4") or name.endswith(".jpg") else data.replace(b"\r\n", b"\n"))
        expect(sha in known, "known-files.txt lists %s (run python3 scripts/kit_hashes.py)" % name)
    # A real install, then an --update over an old copy: .uak/media/ arrives and is refreshed.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_hack import resolve_binary
    bash, git = resolve_binary("bash"), resolve_binary("git")
    env = dict(os.environ, UAK_EXTERNAL_SKILLS="off", GIT_CONFIG_NOSYSTEM="1")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "cafeteria-queue"
        d.mkdir()
        for args in (("init", "-q", "-b", "main"), ("config", "user.name", "Ana"),
                     ("config", "user.email", "ana@example.invalid")):
            subprocess.run([git, *args], cwd=str(d), check=True, capture_output=True)
        installer = str(ROOT / "install.sh")
        out = subprocess.run([bash, installer, "--mode", "sprint", str(d)], capture_output=True, text=True,
                             errors="replace", env=env, timeout=300, stdin=subprocess.DEVNULL)
        expect(out.returncode == 0, "install: " + out.stdout[-600:] + out.stderr[-600:])
        for name in FILES:
            got = d / ".uak" / "media" / name
            expect(got.is_file(), "the install copies .uak/media/%s" % name)
            expect(got.read_bytes() == (MEDIA / name).read_bytes(), ".uak/media/%s is a faithful copy" % name)
        (d / ".uak" / "media" / "tutorial-en.vtt").write_text("WEBVTT\n", encoding="utf-8")
        out = subprocess.run([bash, installer, "--update", "--mode", "sprint", str(d)], capture_output=True, text=True,
                             errors="replace", env=env, timeout=300, stdin=subprocess.DEVNULL)
        expect(out.returncode == 0, "update: " + out.stdout[-600:] + out.stderr[-600:])
        expect((d / ".uak/media/tutorial-en.vtt").read_bytes() == VTT["en"].read_bytes(),
               "--update refreshes .uak/media/ with the engine")


def main():
    failed = 0
    for test in (video_is_short_and_small, captions_exist_in_both_languages, media_ships_with_the_kit):
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
