#!/usr/bin/env python3
"""Record a real `uak demo` run and render it as an animated terminal SVG for the README.

    python3 scripts/render_demo.py [--out docs/media/demo.svg] [--rows 22] [--speed 1.0]

No external tools: the SVG uses CSS keyframes (works on GitHub, loops forever, ~30 KB). Temp paths are
replaced with ~/demo so the recording holds nothing from this machine.
"""
import argparse
import html
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"head": "#e5c07b", "prompt": "#61afef", "ok": "#98c379", "bad": "#e06c75", "dim": "#7f848e", "text": "#d7dae0"}


def record():
    proc = subprocess.Popen(["bash", "kit/.uak/bin/uak", "demo"], cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    start, lines = time.monotonic(), []
    for raw in proc.stdout:
        lines.append((time.monotonic() - start, raw.rstrip("\n")))
    proc.wait()
    if proc.returncode != 0:
        raise SystemExit("uak demo failed")
    return lines


def clean(text):
    text = re.sub(r"/(?:tmp|private/var|var/folders)[^ ]*?/uak-demo\.[A-Za-z0-9]+", "~/demo", text)
    text = re.sub(r"\b([0-9a-f]{7})[0-9a-f]{33}\b", r"\1", text)
    text = re.sub(r"loop-[0-9]+-[0-9]+\.log", "loop.log", text)
    return text[:118]


def color(text):
    s = text.strip()
    if s.startswith("▶"):
        return COLORS["head"]
    if re.match(r"^[a-z0-9-]+\$ ", s):
        return COLORS["prompt"]
    if s.startswith(("CONFLICT", "LOOP_FAIL", "ERROR")):
        return COLORS["bad"]
    if s.startswith(("OK ", "✓", "LOOP_PASS", "WT_READY", "INTEGRATED")):
        return COLORS["ok"]
    if s.startswith(("SECRET_SCAN", "Next:", "LOOP_SUMMARY")):
        return COLORS["dim"]
    return COLORS["text"]


def render(lines, rows, speed):
    # Real timing, compressed: long pauses (merge gate, clones) are capped, every line gets a beat.
    t, times = 0.4, []
    prev = 0.0
    for at, _ in lines:
        t += min(max((at - prev) / speed, 0.06), 1.1)
        prev = at
        times.append(t)
    total = t + 4.0
    lh, cw, pad, bar = 17, 7.2, 14, 28
    width = int(118 * cw + 2 * pad)
    height = rows * lh + 2 * pad + bar
    pct = lambda s: "%.3f%%" % (100.0 * s / total)
    css, body = [], []
    for i, ((_, text), at) in enumerate(zip(lines, times)):
        css.append("@keyframes l%d{0%%,%s{opacity:0}%s,100%%{opacity:1}}.l%d{animation:l%d %.2fs infinite}"
                   % (i, pct(max(at - 0.01, 0)), pct(at), i, i, total))
        body.append('<text class="l%d" x="%d" y="%d" fill="%s">%s</text>'
                    % (i, pad, bar + pad + (i + 1) * lh - 4, color(text), html.escape(clean(text)) or " "))
    steps = ["0%{transform:translateY(0)}"]
    for i, at in enumerate(times):
        if i >= rows:
            steps.append("%s{transform:translateY(-%dpx)}" % (pct(at), (i - rows + 1) * lh))
    steps.append("100%%{transform:translateY(-%dpx)}" % (max(len(lines) - rows, 0) * lh))
    css.append("@keyframes scroll{%s}.scroll{animation:scroll %.2fs steps(1,end) infinite}" % ("".join(steps), total))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" role="img" '
            'aria-label="uak demo: three agents claim, collide, loop, review and merge">'
            '<title>uak demo</title><style>text{font:12.5px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;'
            'white-space:pre}%s</style>'
            '<rect width="100%%" height="100%%" rx="8" fill="#1e2127"/>'
            '<circle cx="18" cy="14" r="5" fill="#e06c75"/><circle cx="36" cy="14" r="5" fill="#e5c07b"/>'
            '<circle cx="54" cy="14" r="5" fill="#98c379"/>'
            '<text x="%d" y="18" fill="#7f848e" text-anchor="middle">bash .uak/bin/uak demo · real run, no AI key</text>'
            '<clipPath id="c"><rect x="0" y="%d" width="%d" height="%d"/></clipPath>'
            '<g clip-path="url(#c)"><g class="scroll">%s</g></g></svg>\n'
            % (width, height, width, height, "".join(css), width // 2, bar, width, height - bar, "".join(body)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/media/demo.svg")
    ap.add_argument("--rows", type=int, default=22)
    ap.add_argument("--speed", type=float, default=1.0)
    args = ap.parse_args()
    lines = [(at, text) for at, text in record() if text.strip()]
    out = ROOT / args.out
    out.write_text(render(lines, args.rows, args.speed), encoding="utf-8")
    print("DEMO_SVG %s · %d lines · %d KB" % (args.out, len(lines), out.stat().st_size // 1024))


if __name__ == "__main__":
    main()
