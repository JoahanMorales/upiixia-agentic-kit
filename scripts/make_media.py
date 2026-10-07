#!/usr/bin/env python3
"""Regenerate docs/media/banner.png (1280x640) and docs/media/demo.gif from a REAL `uak demo` run.

    uv run --with playwright --with pillow python scripts/make_media.py

HTML/CSS is rendered in headless Chromium (Inter + JetBrains Mono, cached locally); frames are
assembled into a GIF with Pillow. Every line shown in the GIF comes from the actual demo output.
"""
import io
import re
import subprocess
import sys
import urllib.request
from html import escape
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media"
FONTS = Path.home() / ".cache" / "uak-media-fonts"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
CSS_URL = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800"
           "&family=JetBrains+Mono:wght@400;500;700&display=swap")


def fonts_css():
    local = FONTS / "local.css"
    if not local.exists():
        FONTS.mkdir(parents=True, exist_ok=True)
        css = urllib.request.urlopen(urllib.request.Request(CSS_URL, headers={"User-Agent": UA})).read().decode()
        for url in sorted(set(re.findall(r"https://[^)]+\.woff2", css))):
            name = url.rsplit("/", 1)[1]
            if not (FONTS / name).exists():
                (FONTS / name).write_bytes(urllib.request.urlopen(url).read())
        local.write_text(re.sub(r"url\(https://[^)]*/([^/)]+\.woff2)\)", r"url(\1)", css))
    return local


BASE_CSS = """
:root { --bg:#06080d; --panel:#0d1117; --line:rgba(255,255,255,.08); --fg:#e6edf3; --mut:#8b949e; --dim:#6e7681;
  --green:#3fb950; --blue:#58a6ff; --violet:#bc8cff; --amber:#e3b341; --red:#ff7b72; --cyan:#39c5cf; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--fg); font-family:Inter, sans-serif; -webkit-font-smoothing:antialiased; }
.mono { font-family:'JetBrains Mono', monospace; }
.glow { position:absolute; border-radius:50%; filter:blur(90px); opacity:.55; }
.grid { position:absolute; inset:0; background-image:radial-gradient(rgba(255,255,255,.07) 1px, transparent 1px);
  background-size:26px 26px; mask-image:radial-gradient(ellipse at 60% 40%, #000 30%, transparent 75%); }
.win { background:linear-gradient(180deg,#11161f,#0b0f16); border:1px solid var(--line); border-radius:16px;
  box-shadow:0 40px 90px rgba(0,0,0,.65), 0 0 0 1px rgba(255,255,255,.02) inset; overflow:hidden; }
.bar { height:40px; display:flex; align-items:center; gap:8px; padding:0 16px; background:rgba(255,255,255,.025);
  border-bottom:1px solid var(--line); }
.dot { width:12px; height:12px; border-radius:50%; } .r{background:#ff5f57} .y{background:#febc2e} .g{background:#28c840}
.bar .t { margin-left:auto; margin-right:auto; color:var(--mut); font-size:13px; font-weight:500; transform:translateX(-26px); }
.pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:12px; font-weight:700; letter-spacing:.02em; }
.p-claimed{background:rgba(88,166,255,.14);color:var(--blue)} .p-review{background:rgba(227,179,65,.14);color:var(--amber)}
.p-integrated{background:rgba(63,185,80,.15);color:var(--green)} .p-available{background:rgba(139,148,158,.14);color:var(--mut)}
"""


_FONT_CSS = None


def inline_fonts():
    """@font-face rules with base64 data URIs: set_content pages cannot load file:// stylesheets."""
    global _FONT_CSS
    if _FONT_CSS is None:
        import base64
        css = fonts_css().read_text()
        _FONT_CSS = re.sub(r"url\(([^)]+\.woff2)\)", lambda m: "url(data:font/woff2;base64," +
                           base64.b64encode((FONTS / m.group(1)).read_bytes()).decode() + ")", css)
    return _FONT_CSS


def page_html(body, w, h, extra_css=""):
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{inline_fonts()}</style>"
            f"<style>{BASE_CSS} body{{width:{w}px;height:{h}px;position:relative;overflow:hidden}} {extra_css}</style>"
            f"</head><body>{body}</body></html>")


# ---------------------------------------------------------------- banner
def banner_html():
    rows = [("claimed", "CLAIMED", "HACK-003", "ana-1", "lease 41m", "Search API"),
            ("review", "REVIEW", "HACK-004", "bob-1", "PR #12", "Results UI"),
            ("claimed", "CLAIMED", "HACK-006", "cy-1", "lease 18m", "Ranking"),
            ("integrated", "INTEGRATED", "HACK-001", "", "", "Contracts + mocks"),
            ("available", "AVAILABLE", "HACK-007", "P0", "wave 2", "Export")]
    trs = "".join(f"<tr><td><span class='pill p-{k}'>{s}</span></td><td class='id'>{i}</td><td class='who'>{w}</td>"
                  f"<td class='inf'>{n}</td><td class='ttl'>{t}</td></tr>" for k, s, i, w, n, t in rows)
    tiers = [("var(--green)", "Haiku 5.5", "swarms", "scouts · runners"),
             ("var(--blue)", "Sonnet 5.5", "builds", "the lead"),
             ("var(--violet)", "Opus 5.5", "advises", "3 checkpoints")]
    chips = "".join(f"<div class='chip'><i style='background:{c};box-shadow:0 0 14px {c}'></i><b>{m}</b><span>{v}</span>"
                    f"<em>{d}</em></div>" for c, m, v, d in tiers)
    body = f"""
<div class='glow' style='width:620px;height:620px;right:-120px;top:-260px;background:#6d28d9'></div>
<div class='glow' style='width:520px;height:520px;left:-200px;bottom:-280px;background:#0e7490'></div>
<div class='glow' style='width:380px;height:380px;right:260px;bottom:-240px;background:#15803d;opacity:.35'></div>
<div class='grid'></div>
<div class='left'>
  <div class='eyebrow mono'><i></i> v4 · multi-agent orchestration</div>
  <h1>UPIIXIA<br>Agentic Kit</h1>
  <p class='sub'>Run a team of AI coding agents in parallel.<br><span>One Git branch. No server. No chaos.</span></p>
  <div class='chips'>{chips}</div>
  <div class='foot mono'>Claude Code · Codex · Cursor · Gemini CLI <b>·</b> Bash + Git <b>·</b> MIT</div>
</div>
<div class='right'>
  <div class='win'>
    <div class='bar'><span class='dot r'></span><span class='dot y'></span><span class='dot g'></span><span class='t mono'>~/team · uak board</span></div>
    <div class='term mono'>
      <div class='cmd'><span class='pr'>human ❯</span> uak board</div>
      <div class='hdr'>main@0909dbf · 6 tasks · freeze in 5h59m</div>
      <table>{trs}</table>
      <div class='graph'>
        <div class='lane'><span class='lbl'>claims</span><div class='track'>
          <b style='left:3%'><u>claim</u></b><b style='left:21%'><u>heartbeat</u></b><b class='a' style='left:40%'><u>conflict</u></b>
          <b style='left:58%'><u>loop ✓</u></b><b class='v' style='left:77%'><u>review ✓</u></b><b class='gr' style='left:96%'><u>merge</u></b></div></div>
      </div>
    </div>
  </div>
  <div class='stats'><div><b>76</b><span>PRs shipped at<br>Hack-Nation 2026</span></div>
  <div><b>5 × 4</b><span>agents × humans<br>on 3 machines</span></div><div><b>0</b><span>servers · daemons<br>just Bash + Git</span></div></div>
</div>"""
    css = """
.left{position:absolute;left:72px;top:64px;width:600px}
.eyebrow{display:inline-flex;align-items:center;gap:9px;font-size:13px;color:#c9d1d9;padding:6px 13px;border:1px solid rgba(255,255,255,.12);
  border-radius:999px;background:rgba(255,255,255,.03)} .eyebrow i{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green)}
h1{margin-top:22px;font-size:76px;line-height:.98;font-weight:800;letter-spacing:-.035em;
  background:linear-gradient(180deg,#fff 30%,#b8c4ff);-webkit-background-clip:text;color:transparent}
.sub{margin-top:22px;font-size:24px;line-height:1.38;color:#c9d1d9;font-weight:500;letter-spacing:-.01em} .sub span{color:var(--mut);font-weight:400}
.chips{margin-top:30px;display:flex;flex-direction:column;gap:10px}
.chip{display:flex;align-items:center;gap:12px;width:430px;padding:11px 16px;border:1px solid rgba(255,255,255,.09);border-radius:12px;
  background:linear-gradient(90deg,rgba(255,255,255,.045),rgba(255,255,255,.01))}
.chip i{width:9px;height:9px;border-radius:50%} .chip b{font-size:17px;font-weight:700;width:104px} .chip span{font-size:17px;color:#e6edf3}
.chip em{margin-left:auto;font-style:normal;font-size:13px;color:var(--dim);font-family:'JetBrains Mono'}
.foot{position:absolute;top:510px;font-size:14px;color:var(--mut)} .foot b{color:#3d444d;margin:0 6px}
.right{position:absolute;right:56px;top:64px;width:540px;transform:perspective(1800px) rotateY(-5deg) rotateX(2deg);transform-origin:left center}
.term{padding:18px 20px 20px;font-size:13.5px}
.cmd{color:#e6edf3} .pr{color:var(--violet);font-weight:700} .hdr{margin:10px 0 12px;color:var(--mut);font-size:12.5px}
table{border-collapse:collapse;width:100%} td{padding:6px 6px 6px 0;white-space:nowrap} .id{color:#e6edf3;font-weight:500} .who{color:var(--cyan)}
.inf{color:var(--mut)} .ttl{color:#c9d1d9;font-family:Inter;font-size:13.5px}
.graph{margin-top:18px;padding-top:16px;border-top:1px dashed rgba(255,255,255,.09)}
.lane{display:flex;align-items:center;gap:12px} .lbl{color:var(--mut);font-size:12px;width:50px}
.track{position:relative;flex:1;height:2px;background:linear-gradient(90deg,#3d444d,#58a6ff,#3fb950)}
.track b{position:absolute;top:-5px;width:12px;height:12px;border-radius:50%;background:#0d1117;border:2px solid var(--blue);transform:translateX(-50%)}
.track b.v{border-color:var(--violet)} .track b.a{border-color:var(--amber)} .track b.gr{border-color:var(--green);background:var(--green)}
.graph{padding-bottom:22px} .stats{display:flex;gap:14px;margin-top:26px} .stats div{flex:1;padding:12px 16px;border:1px solid rgba(255,255,255,.08);border-radius:12px;background:rgba(255,255,255,.025)} .stats b{display:block;font-size:26px;font-weight:800;letter-spacing:-.02em;background:linear-gradient(90deg,#fff,#b8c4ff);-webkit-background-clip:text;color:transparent} .stats span{display:block;margin-top:3px;font-size:12px;line-height:1.35;color:var(--mut)} .track b u{position:absolute;top:18px;left:50%;transform:translateX(-50%);text-decoration:none;font-size:10.5px;color:var(--dim);white-space:nowrap;font-family:'JetBrains Mono'}
"""
    return page_html(body, 1280, 640, css)


# ---------------------------------------------------------------- demo → scenes
def demo_output():
    out = subprocess.run(["bash", str(ROOT / "kit/.uak/bin/uak"), "demo", "--fast"], capture_output=True, text=True,
                         timeout=600).stdout
    if "Done: 3 agents" not in out:
        sys.exit("demo did not finish; refusing to render")
    out = re.sub(r"/tmp/uak-demo\.[A-Za-z0-9]+", "~/demo", out)
    return re.sub(r"\b([0-9a-f]{7})[0-9a-f]{33}\b", r"\1", out)


def block(out, cmd_pattern):
    """Return (who, command, output lines) for the first command matching the pattern, from real output."""
    lines = out.splitlines()
    for i, l in enumerate(lines):
        m = re.match(r"\s*(\S+)\$ (.*)", l)
        if m and re.search(cmd_pattern, m.group(2)):
            res = []
            for nxt in lines[i + 1:]:
                if re.match(r"\s*(\S+)\$ ", nxt) or nxt.startswith("▶") or not nxt.strip():
                    break
                res.append(nxt.strip())
            cmd = m.group(2).replace("bash .uak/bin/uak ", "uak ").replace("bash .uak/bin/wt ", "wt ")
            cmd = re.sub(r"bash \.uak/bin/(\w+)", r"uak \1", cmd)
            cmd = re.sub(r"--agent bash \S+fake-agent\.sh", "--agent ./fake-agent.sh", cmd)
            cmd = cmd.replace("--verify bash tests/api_test.sh", '--verify "bash tests/api_test.sh"')
            cmd = re.sub(r" --evidence .*", ' --evidence "tests pass"', cmd)
            return m.group(1), cmd, [r for r in res if not r.startswith("Next: cd")]
    sys.exit("pattern not in demo output: " + cmd_pattern)


def scenes(out):
    pick = lambda p: block(out, p)
    after = out.split("dependent task unlocks", 1)[1]
    return [
        ("Plan", "The backlog is a graph: waves and a critical path", [pick(r"uak graph")]),
        ("Claim", "3 agents start at once. An overlapping claim is rejected", [pick(r"wt new HACK-001"), pick(r"wt new HACK-002"), pick(r"wt new HACK-004")]),
        ("Watch", "Humans read one board, not ten chats", [pick(r"board$")]),
        ("Loop", "A bounded verify → fix loop (stand-in agent, no API key)", [pick(r"uak loop")]),
        ("Review", "Another agent reviews the exact SHA → gated merge", [pick(r"uak review"), pick(r"uak merge")]),
        ("Unlock", "The dependent task becomes available by itself", [block(after, r"uak next"), block(after, r"wt new HACK-003")]),
    ]


AGENT_COLOR = {"ana-1": "var(--cyan)", "bob-1": "var(--amber)", "cy-1": "var(--violet)", "human": "var(--green)", "planner": "var(--blue)"}


def fmt_out(line):
    t = escape(line)
    for k in ("CLAIMED", "REVIEW", "INTEGRATED", "AVAILABLE"):
        if line.startswith(k + " ") or line == k:
            return f"<span class='pill bp p-{k.lower()}'>{k}</span>" + escape(line[len(k):].lstrip())
    if line.startswith("CONFLICT"):
        return f"<span class='bad'>✗ {t}</span>"
    if line.startswith("LOOP_FAIL"):
        return f"<span class='warn'>{t}</span>"
    if line.startswith(("LOOP_PASS", "OK merge")):
        return f"<span class='ok'>✓ {t}</span>"
    if line.startswith(("OK ", "WT_READY")):
        return f"<span class='ok2'>{t}</span>"
    if line.startswith(("GRAPH", "UAK BOARD", "HACK-003 | AVAILABLE")):
        return f"<span class='hi'>{t}</span>"
    return f"<span class='mut'>{t}</span>"


GIF_CSS = """
.accent{position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,#39c5cf,#58a6ff,#bc8cff)} .stage{position:absolute;inset:0;padding:30px 40px}
.top{display:flex;align-items:center;gap:14px;height:46px}
.n{font-family:'JetBrains Mono';font-size:13px;color:var(--mut);padding:5px 11px;border:1px solid rgba(255,255,255,.12);border-radius:999px}
.k{font-size:15px;font-weight:700;color:var(--violet);letter-spacing:.08em;text-transform:uppercase}
.cap{font-size:22px;font-weight:600;letter-spacing:-.015em;color:#e6edf3}
.prog{position:absolute;left:40px;right:40px;top:88px;height:3px;border-radius:3px;background:rgba(255,255,255,.06);overflow:hidden}
.prog i{display:block;height:100%;background:linear-gradient(90deg,#58a6ff,#bc8cff)}
.win{position:absolute;left:40px;right:40px;top:110px;bottom:34px}
.bp{width:118px;text-align:center;margin-right:14px;font-size:12px} .body{padding:22px 26px;font-size:16px;line-height:1.62;white-space:pre-wrap;word-break:break-word}
.pr{font-weight:700} .cmd{color:#e6edf3} .cur{display:inline-block;width:9px;height:19px;background:#e6edf3;vertical-align:-3px;margin-left:2px}
.o{padding-left:22px} .ok{color:var(--green);font-weight:700} .ok2{color:#9fd8a8} .warn{color:var(--amber)} .bad{color:var(--red);font-weight:700}
.hi{color:#e6edf3;font-weight:500} .mut{color:var(--mut)} .gap{height:10px}
.end{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.end h2{font-size:64px;font-weight:800;letter-spacing:-.035em;background:linear-gradient(180deg,#fff 30%,#b8c4ff);-webkit-background-clip:text;color:transparent}
.end p{margin-top:14px;font-size:22px;color:#c9d1d9} .end .tag{font-family:'JetBrains Mono';font-size:14px;color:var(--green);margin-bottom:18px} .end .c{margin-top:30px;text-align:left;line-height:1.7;font-family:'JetBrains Mono';font-size:17px;color:#e6edf3;
  padding:14px 22px;border:1px solid rgba(255,255,255,.12);border-radius:12px;background:rgba(255,255,255,.04)}
.end .c b{color:var(--violet)} .end .s{margin-top:22px;font-size:15px;color:var(--mut)}
"""
W, H = 1120, 560


def frame_html(idx, total, key, caption, lines_html, cursor=False):
    bg = "<div class='accent'></div>"
    body = "".join(lines_html) + ("<span class='cur'></span>" if cursor else "")
    return page_html(bg + f"""<div class='stage'><div class='top'><span class='n'>{idx}/{total}</span><span class='k'>{key}</span>
<span class='cap'>{escape(caption)}</span></div><div class='prog'><i style='width:{100 * idx / total:.1f}%'></i></div>
<div class='win'><div class='bar'><span class='dot r'></span><span class='dot y'></span><span class='dot g'></span>
<span class='t mono'>uak demo · real run in a temp repo</span></div><div class='body mono'>{body}</div></div></div>""", W, H, GIF_CSS)


def end_html():
    bg = "<div class='accent'></div>"
    return page_html(bg + """<div class='end'><div class='tag'>try it in 30 seconds · no setup · no API key</div><h2>UPIIXIA Agentic Kit</h2>
<p>3 agents · 1 conflict avoided · 1 bounded loop · 1 independent review · 1 gated merge</p>
<div class='c'><b>$</b> git clone https://github.com/JoahanMorales/upiixia-agentic-kit<br><b>$</b> bash upiixia-agentic-kit/kit/.uak/bin/uak demo</div>
<div class='s'>Haiku swarms · Sonnet builds · Opus advises — Claude Code · Codex · Cursor · Gemini CLI</div></div>""", W, H, GIF_CSS)


def build_gif(page, out):
    sc = scenes(out)
    frames = []  # (png bytes, ms)

    def shot(html, ms):
        page.set_content(html, wait_until="load")
        page.evaluate("document.fonts.ready")
        frames.append((page.screenshot(), ms))

    for n, (key, cap, blocks) in enumerate(sc, 1):
        done = []
        for who, cmd, res in blocks:
            color = AGENT_COLOR.get(who, "var(--blue)")
            prompt = f"<span class='pr' style='color:{color}'>{escape(who)} ❯</span> "
            step = max(3, len(cmd) // 9)
            for k in range(0, len(cmd) + 1, step):
                shot(frame_html(n, len(sc), key, cap, done + [prompt + f"<span class='cmd'>{escape(cmd[:k])}</span>"], True), 45)
            done.append(prompt + f"<span class='cmd'>{escape(cmd)}</span>\n")
            for r in res[:8]:
                done.append(f"<div class='o'>{fmt_out(r)}</div>")
                pause = 650 if r.startswith(("CONFLICT", "LOOP_PASS", "OK merge", "LOOP_FAIL")) else 170
                shot(frame_html(n, len(sc), key, cap, done), pause)
            done.append("<div class='gap'></div>")
        shot(frame_html(n, len(sc), key, cap, done, True), 1900)
    shot(end_html(), 4200)

    imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b, _ in frames]
    picks = sorted(set([len(imgs) - 1] + list(range(0, len(imgs), max(1, len(imgs) // 10)))))
    sample = Image.new("RGB", (W, H * len(picks)))
    for i, k in enumerate(picks):
        sample.paste(imgs[k], (0, H * i))
    pal = sample.quantize(colors=255, method=Image.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.NONE) for im in imgs]
    q[0].save(OUT / "demo.gif", save_all=True, append_images=q[1:], duration=[ms for _, ms in frames], loop=0, optimize=True)
    return len(frames)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    out = demo_output()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 640})
        page.set_content(banner_html(), wait_until="load"); page.evaluate("document.fonts.ready")
        page.screenshot(path=str(OUT / "banner.png"))
        page.set_viewport_size({"width": W, "height": H})
        n = build_gif(page, out)
        b.close()
    for f in ("banner.png", "demo.gif"):
        print(f, (OUT / f).stat().st_size // 1024, "KB")
    print("frames", n)


if __name__ == "__main__":
    main()
