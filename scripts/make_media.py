#!/usr/bin/env python3
"""The README's images (UAK-202: all of them in the dark theme, Lavanda).

    python3 scripts/make_media.py --from DIR     the art drawn by docs/video (UAK-199): first
        cd docs/video && npm ci && npx playwright-core install chromium-headless-shell && npm run readme -- DIR
      then this copies DIR's banner.png, parallel-loop.webp, parallel-loop.gif and lanes-into-main.png into docs/media/,
      the still images and the animated WebP with rounded corners of their own (GitHub shows them on a light page too),
      and writes docs/media/banner.version. Run it again after kit/.uak/VERSION moves: the banner says its major.minor.
    uv run --with playwright --with pillow python scripts/make_media.py --dash
      docs/media/dash.png and dash-task.png: this repository's own dashboard, dark, Lavanda.
    uv run --with playwright --with pillow python scripts/make_media.py --fallback [--gif] [--out DIR]
      a banner drawn here without Node (banner_html, the same direction), and with --gif the legacy demo.gif.
      It writes into DIR, a new temporary folder when --out is absent, never into docs/media/ on its own.
The terminal animation is docs/media/demo.svg, made by scripts/render_demo.py (no browser needed).

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

# Pillow and Playwright load where they are used: the banner's text and its version stamp need neither (UAK-094).

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media"
VERSION_FILE = ROOT / "kit" / ".uak" / "VERSION"
FONTS = Path.home() / ".cache" / "uak-media-fonts"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
CSS_URL = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800"
           "&family=JetBrains+Mono:wght@400;500;700&display=swap")


def banner_version():
    """major.minor of kit/.uak/VERSION: the banner's eyebrow and docs/media/banner.version (kit_lint compares them)."""
    return ".".join(VERSION_FILE.read_text(encoding="utf-8").strip().split(".")[:2])


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
    """The README's banner, in the kit's direction (docs/design/DIRECTION.md, UAK-202): the Lavanda palette
    in the dark theme, Inter for text and JetBrains Mono for IDs and state pills, one hairline per panel, no glow, no gradient, no shadow.
    It carries no figure: the old one said "~2 s" and "144x" with no source. The board's rows are the cast of `uak demo`."""
    rows = [("integrated", "INTEGRATED", "HACK-001", "ana-1", "Search API", "reviewed by bob-1 · merged"),
            ("claimed", "IN PROGRESS", "HACK-002", "bob-1", "Results UI", "its own branch and worktree"),
            ("claimed", "IN PROGRESS", "HACK-003", "cy-1", "Ranking", "opened when HACK-001 merged"),
            ("blocked", "REFUSED", "HACK-004", "cy-1", "API cache", "its files overlap HACK-001")]
    trs = "".join(f"<tr><td><span class='pill p-{k}'>{st}</span></td><td class='id'>{i}</td><td class='who'>{w}</td>"
                  f"<td class='ttl'>{t}<span>{n}</span></td></tr>" for k, st, i, w, t, n in rows)
    steps = ["claim", "test first", "review", "merge"]
    line = "".join(f"<li class='{'on' if n < 3 else 'end'}'><i></i><span>{x}</span></li>" for n, x in enumerate(steps))
    body = f"""
<div class='left'>
  <div class='eyebrow mono'><i></i>v{banner_version()} · multi-agent orchestration</div>
  <h1>UPIIXIA<br>Agentic Kit</h1>
  <p class='aim'>Several people and their coding agents on one repository, in parallel, without stepping on each other.</p>
  <ol class='nodes mono'>{line}</ol>
  <div class='foot mono'>Claude Code · Codex · Cursor · Gemini CLI<b>|</b>Bash + Git<b>|</b>MIT</div>
</div>
<div class='right'>
  <div class='panel'>
    <div class='head'><span class='mark mono'>uak</span><b>Team board</b><span class='src mono'>from the claims branch</span></div>
    <table class='rows'>{trs}</table>
  </div>
</div>"""
    css = """
body{background:#0e0e12;color:hsl(250 25% 96%)}
.left{position:absolute;left:72px;top:92px;width:560px}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:500;color:hsl(250 12% 78%);padding:5px 11px;
  border:1px solid hsl(250 8% 27%);border-radius:999px;background:hsl(250 9% 10%);letter-spacing:.02em}
.eyebrow i{width:7px;height:7px;border-radius:50%;background:hsl(250 72% 68%)}
h1{margin-top:26px;font-size:64px;line-height:1.04;font-weight:700;letter-spacing:-.03em;color:hsl(250 25% 96%)}
.aim{margin-top:22px;font-size:22px;line-height:1.42;color:hsl(250 12% 78%);font-weight:400;max-width:520px}
.nodes{list-style:none;display:flex;margin-top:34px;width:480px}
.nodes li{flex:1;position:relative;font-size:12px;color:hsl(250 12% 78%)}
.nodes li i{display:block;width:12px;height:12px;border-radius:50%;background:#0e0e12;border:2px solid hsl(250 72% 74%);position:relative;z-index:1}
.nodes li.end i{background:hsl(250 72% 68%)}
.nodes li:not(:last-child)::after{content:'';position:absolute;left:12px;right:0;top:5px;height:2px;background:hsl(250 36% 30%)}
.nodes li span{display:block;margin-top:9px;text-transform:uppercase;letter-spacing:.06em;font-size:11px;font-weight:500}
.foot{position:absolute;top:470px;font-size:13px;color:hsl(250 7% 60%)} .foot b{color:hsl(250 8% 27%);margin:0 10px;font-weight:400}
.right{position:absolute;right:64px;top:150px;width:520px}
.panel{background:hsl(250 9% 10%);border:1px solid hsl(250 8% 17.5%);border-radius:8px;overflow:hidden}
.head{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid hsl(250 8% 17.5%)}
.mark{width:30px;height:30px;border-radius:6px;background:hsl(250 72% 86%);color:hsl(250 45% 20%);display:grid;place-items:center;font-size:11px;font-weight:700}
.head b{font-size:15px;font-weight:600} .src{margin-left:auto;font-size:11px;color:hsl(250 7% 60%)}
.rows{border-collapse:collapse;width:100%}
.rows td{padding:15px 0 15px 18px;border-top:1px solid hsl(250 8% 17.5%);vertical-align:top;white-space:nowrap}
.rows tr:first-child td{border-top:0} .rows td:last-child{padding-right:18px;white-space:normal}
.pill{display:inline-block;padding:3px 8px;border-radius:999px;font:600 10px/1.3 'JetBrains Mono',monospace;letter-spacing:.06em}
.p-integrated{background:#16301f;color:#a3dcbd} .p-claimed{background:#16273d;color:#a9cdf3} .p-blocked{background:#361d19;color:#f5a79e}
.id{font:500 13px 'JetBrains Mono',monospace;color:hsl(250 25% 96%)} .who{font:400 12px 'JetBrains Mono',monospace;color:hsl(250 72% 82%)}
.ttl{font-size:14px;font-weight:500;color:hsl(250 25% 96%)} .ttl span{display:block;margin-top:3px;font-size:12px;font-weight:400;color:hsl(250 7% 60%)}
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

    from PIL import Image
    imgs = [Image.open(io.BytesIO(b)).convert("RGB") for b, _ in frames]
    picks = sorted(set([len(imgs) - 1] + list(range(0, len(imgs), max(1, len(imgs) // 10)))))
    sample = Image.new("RGB", (W, H * len(picks)))
    for i, k in enumerate(picks):
        sample.paste(imgs[k], (0, H * i))
    pal = sample.quantize(colors=255, method=Image.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.NONE) for im in imgs]
    q[0].save(OUT / "demo.gif", save_all=True, append_images=q[1:], duration=[ms for _, ms in frames], loop=0, optimize=True)
    return len(frames)


# ---------------------------------------------------------------- the art of docs/video (UAK-199 → UAK-202)
README_ART = ("banner.png", "lanes-into-main.png", "parallel-loop.webp", "parallel-loop.gif")


def rounded(img, radius=18):
    """IMG (RGBA) with transparent rounded corners."""
    from PIL import Image, ImageDraw
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def import_art(src):
    """Copy the README's art drawn by docs/video from SRC into docs/media/: PNGs and the animated WebP get rounded
    corners; the GIF (the fallback for readers without WebP) is copied as it is."""
    import shutil
    from PIL import Image, ImageSequence
    src = Path(src)
    for name in README_ART:
        if not (src / name).is_file():
            sys.exit("missing %s in %s: run `npm run readme -- %s` in docs/video first" % (name, src, src))
    for name in ("banner.png", "lanes-into-main.png"):
        rounded(Image.open(src / name).convert("RGBA")).save(OUT / name, optimize=True)
    anim = Image.open(src / "parallel-loop.webp")
    frames, durations = [], []
    for f in ImageSequence.Iterator(anim):
        frames.append(rounded(f.convert("RGBA"), radius=14))
        durations.append(f.info.get("duration", 83))
    frames[0].save(OUT / "parallel-loop.webp", save_all=True, append_images=frames[1:], duration=durations, loop=0,
                   quality=80, method=6, minimize_size=True)
    shutil.copy(src / "parallel-loop.gif", OUT / "parallel-loop.gif")
    (OUT / "banner.version").write_text(banner_version() + "\n", encoding="utf-8")  # kit_lint: the banner is not stale
    for name in README_ART:
        print(name, (OUT / name).stat().st_size // 1024, "KB")


# ---------------------------------------------------------------- dashboard screenshots (UAK-202)
DASH_GROUND = (14, 14, 18)   # the dark theme's page ground under Lavanda (hsl 250 9% 6%), as the frame of the shot


def framed(src, dest, pad=16, radius=18):
    """The shot on a dark rounded ground of its own, transparent outside the corners: dark art on GitHub's light
    page reads as a deliberate card, and on its dark page as the page itself."""
    from PIL import Image, ImageDraw
    shot = Image.open(src).convert("RGBA")
    w, h = shot.size[0] + 2 * pad, shot.size[1] + 2 * pad
    card = Image.new("RGBA", (w, h), DASH_GROUND + (255,))
    card.paste(shot, (pad, pad))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    out.save(dest, optimize=True)


def dash_shots(task="UAK-165"):
    """docs/media/dash.png and dash-task.png: this repository's own dashboard (its public claims branch), dark theme,
    Lavanda, 1280x760, English; the task opened is TASK. Run from a checkout of this repository with its claims."""
    import tempfile
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, str(ROOT / "kit/.uak/bin/lib/dash.py"), "--out", tmp], cwd=str(ROOT), check=True)
        page_file = Path(tmp) / "index.html"
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": 1280, "height": 760}, color_scheme="dark")
            ctx.add_init_script("try{localStorage.setItem('uak-look',JSON.stringify({theme:'dark',pal:'lavanda'}));"
                                "localStorage.setItem('uak-language','en')}catch(e){}")
            page = ctx.new_page()
            page.goto(page_file.as_uri())
            page.wait_for_timeout(2000)
            page.screenshot(path=str(Path(tmp) / "dash.png"))
            page.locator("text='%s'" % task.split("-")[-1]).first.click()
            page.wait_for_timeout(1500)
            page.screenshot(path=str(Path(tmp) / "dash-task.png"))
            b.close()
        for name in ("dash.png", "dash-task.png"):
            framed(Path(tmp) / name, OUT / name)
            print(name, (OUT / name).stat().st_size // 1024, "KB")


def main():
    global OUT
    OUT.mkdir(parents=True, exist_ok=True)
    if "--dash" in sys.argv:   # the README's dashboard shots only (UAK-202)
        dash_shots(); return
    if "--from" in sys.argv:   # the README's art, drawn by docs/video (UAK-199)
        import_art(sys.argv[sys.argv.index("--from") + 1]); return
    if "--html" in sys.argv:   # no Playwright browser: render the HTML with any Chromium, e.g.
        # chromium --headless --screenshot=banner.png --window-size=1280,640 --virtual-time-budget=3000 file://…/banner.html
        dest = Path(sys.argv[sys.argv.index("--html") + 1])
        dest.write_text(banner_html(), encoding="utf-8"); print(dest); return
    if "--fallback" not in sys.argv:
        sys.exit(__doc__)
    from playwright.sync_api import sync_playwright
    OUT = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else Path(tempfile.mkdtemp(prefix="uak-media-"))
    OUT.mkdir(parents=True, exist_ok=True)
    print("writing into", OUT)
    gif = "--gif" in sys.argv
    out = demo_output() if gif else None
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 640})
        page.set_content(banner_html(), wait_until="load"); page.evaluate("document.fonts.ready")
        page.screenshot(path=str(OUT / "banner.png"))
        if gif:
            page.set_viewport_size({"width": W, "height": H})
            print("frames", build_gif(page, out))
        b.close()
    (OUT / "banner.version").write_text(banner_version() + "\n", encoding="utf-8")  # kit_lint: the banner is not stale
    for f in ("banner.png", "demo.gif") if gif else ("banner.png",):
        print(f, (OUT / f).stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
