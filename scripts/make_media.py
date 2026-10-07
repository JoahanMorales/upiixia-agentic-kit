#!/usr/bin/env python3
"""Regenerate docs/media/demo.gif (from a REAL `uak demo` run) and docs/media/banner.png (1280x640).

Usage: python3 scripts/make_media.py        (needs Pillow; fonts: DejaVu Sans Mono / DejaVu Sans)
The GIF is rendered from the actual demo output, so it never drifts from what the kit does.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media"
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "/System/Library/Fonts/Supplemental"]
BG, BAR, FG, DIM = (13, 17, 23), (22, 27, 34), (201, 209, 217), (125, 133, 144)
CYAN, GREEN, YELLOW, RED, PURPLE = (88, 166, 255), (63, 185, 80), (210, 153, 34), (248, 81, 73), (188, 140, 255)


def font(name, size):
    for d in FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def demo_lines():
    env = dict(os.environ, TMPDIR="/tmp")
    out = subprocess.run(["bash", str(ROOT / "kit/.uak/bin/uak"), "demo", "--fast"], capture_output=True,
                         text=True, env=env, timeout=600).stdout
    lines = []
    for raw in out.splitlines():
        line = re.sub(r"/tmp/uak-demo\.[A-Za-z0-9]+", "~/demo", raw.rstrip())
        line = re.sub(r"[0-9a-f]{40}", lambda m: m.group(0)[:7], line)
        line = line.replace("--verify bash tests/api_test.sh --agent bash ~/demo/fake-agent.sh --max 5 --task HACK-001", '--verify "bash tests/api_test.sh" --agent fake-agent.sh --task HACK-001')
        if not line.strip() or "Next: cd" in line or "Explore it" in line:
            continue
        lines.append(line[:96])
    if not any("Done: 3 agents" in l for l in lines):
        sys.exit("demo did not finish; refusing to render a fake GIF")
    return lines


def color(line):
    s = line.strip()
    if s.startswith("▶"):
        return CYAN
    if s.startswith("✓") or "LOOP_PASS" in s or "INTEGRATED" in s and "OK merge" in s:
        return GREEN
    if "CONFLICT" in s or "LOOP_FAIL" in s:
        return YELLOW
    if s.split("$")[0].strip() in ("planner", "ana-1", "bob-1", "cy-1", "human") and "$" in s:
        return PURPLE
    if s.startswith(("OK ", "WT_READY", "GRAPH", "UAK BOARD", "HACK-003 | AVAILABLE")):
        return FG
    return DIM if s.startswith(("wave", "Idle", "No eligible")) else FG


def gif(lines):
    W, H, LH, ROWS = 1100, 640, 22, 25
    mono, bold = font("DejaVuSansMono.ttf", 15), font("DejaVuSansMono-Bold.ttf", 15)
    title = font("DejaVuSans-Bold.ttf", 14)
    frames, durations = [], []

    def frame(upto):
        im = Image.new("P", (W, H))
        im.putpalette(sum([list(c) for c in (BG, BAR, FG, DIM, CYAN, GREEN, YELLOW, RED, PURPLE, (255, 95, 86), (255, 189, 46), (39, 201, 63))], []) + [0] * (256 - 12) * 3)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 36], fill=BAR)
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([16 + i * 22, 12, 28 + i * 22, 24], fill=c)
        d.text((W // 2 - 190, 10), "uak demo · 3 agents, one Git branch, no server", font=title, fill=DIM)
        view = lines[max(0, upto - ROWS):upto]
        for i, l in enumerate(view):
            c = color(l)
            d.text((18, 50 + i * LH), l, font=bold if c in (CYAN, GREEN) else mono, fill=c)
        return im

    frames.append(frame(0)); durations.append(600)
    for k in range(1, len(lines) + 1):
        frames.append(frame(k))
        l = lines[k - 1].strip()
        durations.append(1100 if l.startswith("▶") else 900 if any(x in l for x in ("CONFLICT", "LOOP_PASS", "OK merge", "✓")) else 220)
    frames.append(frame(len(lines))); durations.append(4000)
    OUT.mkdir(parents=True, exist_ok=True)
    frames[0].save(OUT / "demo.gif", save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)


def banner():
    W, H = 1280, 640
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 40):  # subtle grid
        d.line([(x, 0), (x, H)], fill=(18, 23, 30))
    for y in range(0, H, 40):
        d.line([(0, y), (W, y)], fill=(18, 23, 30))
    big, mid, small = font("DejaVuSans-Bold.ttf", 68), font("DejaVuSans.ttf", 30), font("DejaVuSansMono.ttf", 21)
    d.text((70, 70), "UPIIXIA Agentic Kit", font=big, fill=(240, 246, 252))
    d.text((72, 160), "Ship with a team of AI coding agents —", font=mid, fill=FG)
    d.text((72, 200), "in parallel, without chaos.", font=mid, fill=FG)
    rows = [("CLAIMED", "HACK-003", "ana-1", "lease 41m", CYAN), ("REVIEW", "HACK-004", "bob-1", "PR#12", YELLOW),
            ("INTEGRATED", "HACK-001", "HACK-002", "", GREEN), ("AVAILABLE", "HACK-005", "P0", "wave 2", DIM)]
    d.rounded_rectangle([70, 280, 760, 470], radius=14, fill=BAR)
    d.text((92, 294), "$ uak board", font=small, fill=PURPLE)
    for i, (st, idd, who, info, c) in enumerate(rows):
        d.text((92, 330 + i * 32), f"{st:<11}{idd:<10}{who:<10}{info}", font=small, fill=c)
    tiers = [("Haiku", "swarms", (63, 185, 80)), ("Sonnet", "builds", (88, 166, 255)), ("Opus", "advises", (188, 140, 255))]
    for i, (m, v, c) in enumerate(tiers):
        y = 290 + i * 62
        d.rounded_rectangle([810, y, 1210, y + 50], radius=12, outline=c, width=2)
        d.text((832, y + 10), f"{m} {v}", font=font("DejaVuSans-Bold.ttf", 26), fill=c)
    d.text((72, 520), "Claude Code · Codex · Cursor · Gemini CLI    Bash + Git    MIT", font=font("DejaVuSans.ttf", 24), fill=DIM)
    d.text((72, 562), "sprint mode for hackathons  ·  marathon mode for real products", font=font("DejaVuSans.ttf", 24), fill=DIM)
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / "banner.png", optimize=True)


if __name__ == "__main__":
    banner()
    gif(demo_lines())
    for f in ("banner.png", "demo.gif"):
        print(f, (OUT / f).stat().st_size // 1024, "KB")
