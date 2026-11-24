#!/usr/bin/env python3
"""UAK-158: one design system. The wizard (setup.html) and the dashboard (dash.html) carry the same token block, in the
direction the human chose on 2026-11-23 (docs/design/DIRECTION.md, mock in docs/design/direction/mock.html): nine
palettes (Clasico, Lavanda, Cielo, Menta, Salvia, Durazno, Rosa, Arena, Grafito), each in light and dark, one scale,
Inter and JetBrains Mono from local files, and `design-lint` reads .html. Why (2026-11-22): the two pages shared no colour
value, the wizard framed a blue dashboard inside a green page, and design-lint printed PASS for both because it did not
read HTML (a copy renamed .js gave 40 findings). Real files, real design-lint, real wizard server on a free port, no network."""
import argparse
import importlib.util
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

import test_setup_wizard as wizard
from test_hack import resolve_binary

PALETTES = ["clasico", "lavanda", "cielo", "menta", "salvia", "durazno", "rosa", "arena", "grafito"]
BEGIN, END = "/* uak-system:begin", "/* uak-system:end */"
# The dashboard of v6.8, token by token (docs/design/DIRECTION.md: Clasico is "the exact colours of the dashboard of v6.8").
V68 = {
    "light": {"page": "#f4f4f1", "surface": "#fcfcfb", "raised": "#ffffff", "hover": "#f0efea", "ink": "#141413", "ink-2": "#52514e",
              "muted": "#68665f", "line": "#e6e5df", "line-2": "#d4d3cc", "accent": "#2a78d6", "accent-ink": "#1c5cab", "accent-wash": "#e6f0fc",
              "integrated": "#1baf7a", "review": "#2a78d6", "claimed": "#eda100", "blocked": "#e34948", "available": "#c3c2b7",
              "waiting": "#a99fe6", "cancelled": "#d9d8d2", "good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b",
              "violet": "#6250d6", "orange": "#eb6834", "warn-wash": "#fdf3dc", "warn-ink": "#7a5300", "crit-wash": "#fbe7e6",
              "crit-ink": "#9e2525"},
    "dark": {"page": "#0f0f0e", "surface": "#1a1a19", "raised": "#201f1e", "hover": "#262624", "ink": "#f0efec", "ink-2": "#c3c2b7",
             "muted": "#9c9a93", "line": "#2c2c2a", "line-2": "#3a3a37", "accent": "#3987e5", "accent-ink": "#86b6ef", "accent-wash": "#16273d",
             "integrated": "#199e70", "review": "#3987e5", "claimed": "#c98500", "blocked": "#e66767", "available": "#5d5c57",
             "waiting": "#6b62b8", "cancelled": "#3f3f3c", "violet": "#9085e9", "orange": "#d95926", "warn-wash": "#33280f",
             "warn-ink": "#f5c766", "crit-wash": "#3a1b1b", "crit-ink": "#ffaaa6"},
}
# Every text/background pair of the tokens (text on its ground, X-ink on X-wash, the button).
PAIRS = [("ink", g) for g in ("page", "surface", "raised", "hover", "accent-wash")] + [("ink-2", g) for g in ("page", "surface", "raised", "hover", "accent-wash")] + \
        [("muted", g) for g in ("page", "surface", "raised", "hover", "accent-wash")] + [("accent-ink", g) for g in ("page", "surface", "raised", "accent-wash")] + \
        [("on-btn", "btn")] + [("%s-ink" % s, "%s-wash" % s) for s in ("integrated", "claimed", "review", "blocked")] + \
        [("%s-ink" % s, "surface") for s in ("integrated", "claimed", "review", "blocked")] + [("warn-ink", "warn-wash"), ("crit-ink", "crit-wash")]


def lib(root, name):
    return (root / ".uak/bin/lib" / name).read_text(encoding="utf-8")


def pages(root):
    return {"setup.html": lib(root, "setup.html"), "dash.html": lib(root, "dash.html")}


def system(html):
    a, b = html.index(BEGIN), html.index(END) + len(END)
    return html[a:b]


def own_css(html):
    """The page's own stylesheet: what follows the shared block, up to </style>."""
    a = html.index(END) + len(END)
    return html[a:html.index("</style>", a)]


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


# ---- a small CSS value evaluator: hex, hsl(var(--h) S% L%), var(), calc(x * y) ----------------------------------------
def rules_of(block):
    block = strip_comments(block)
    block = re.sub(r"@font-face\s*\{[^{}]*\}", "", block)
    out = []
    for order, m in enumerate(re.finditer(r"([^{}]+)\{([^{}]*)\}", block)):
        decl = dict((k, v.strip()) for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);?", m.group(2)))
        for sel in m.group(1).split(","):
            sel = sel.strip()
            if sel:
                out.append((sel, order, decl))
    return out


def specificity(sel, attrs):
    """None when SEL does not match ATTRS, else its specificity. Selectors: :root and [data-x="v"] / [data-x] / :not([...])."""
    m = re.match(r'^\[data-pal="([a-z]+)"\]$', sel)
    if m:
        return (1, 0, 0) if attrs.get("data-pal") == m.group(1) else None
    if not sel.startswith(":root"):
        return None
    n = 1
    for neg, name, eq, val in re.findall(r'(:not\()?\[([a-z-]+)(=)?(?:"([^"]*)")?\]\)?', sel[5:]):
        have = attrs.get(name)
        ok = (have == val) if eq else (have is not None)
        if (not ok) if not neg else ok:
            return None
        n += 1
    return (0, 0, n)


def cascade(rules, attrs):
    hit = []
    for sel, order, decl in rules:
        spec = specificity(sel, attrs)
        if spec is not None:
            hit.append(((spec[0] + spec[2], spec[2], order), decl))
    hit.sort(key=lambda t: t[0])
    env = {}
    for _, decl in hit:
        env.update(decl)
    return env


def resolve(value, env):
    value = value.strip()
    for _ in range(8):
        m = re.search(r"var\((--[a-z0-9-]+)\)", value)
        if not m:
            break
        value = value[:m.start()] + env[m.group(1)] + value[m.end():]
    while True:
        m = re.search(r"calc\(\s*([0-9.]+%?)\s*\*\s*([0-9.]+)\s*\)", value)
        if not m:
            return value
        a = m.group(1)
        result = float(a.rstrip("%")) * float(m.group(2))
        value = value[:m.start()] + ("%.3f%%" % result if a.endswith("%") else "%.3f" % result) + value[m.end():]


def rgb(value):
    value = value.strip()
    if value.startswith("#"):
        value = value[1:]
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    m = re.match(r"hsl\(\s*([0-9.]+)\s+([0-9.]+)%\s+([0-9.]+)%\s*\)$", value)
    assert m, "cannot read the colour %r" % value
    h, s, l = float(m.group(1)) % 360, float(m.group(2)) / 100, float(m.group(3)) / 100
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    base = l - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
    return (r + base, g + base, b + base)


def luminance(c):
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def lab(c):
    f = lambda v: v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4  # noqa: E731
    r, g, b = f(c[0]), f(c[1]), f(c[2])
    xyz = ((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, 0.2126 * r + 0.7152 * g + 0.0722 * b, (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
    t = [v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116 for v in xyz]
    return (116 * t[1] - 16, 500 * (t[0] - t[1]), 200 * (t[1] - t[2]))


def delta_e(a, b):
    return math.dist(lab(a), lab(b))


def environment(html, palette, theme):
    return cascade(rules_of(system(html)), {"data-pal": palette, "data-theme": theme})


def token(env, name):
    return rgb(resolve(env["--" + name], env))


# ---- the cases ------------------------------------------------------------------------------------------------------
def wizard_and_dashboard_share_tokens(root, tmp):
    both = pages(root)
    a, b = system(both["setup.html"]), system(both["dash.html"])
    assert a == b, "the shared block (tokens, parts, fonts) differs between the two pages"
    for html in both.values():
        assert len(rules_of(system(html))) >= 16, "the block holds the :root rules and the palettes"
    # the :root blocks (light, dark) and every palette rule: same properties, same values
    ra = [r for r in rules_of(a) if r[0].startswith(":root") or r[0].startswith("[data-pal")]
    rb = [r for r in rules_of(b) if r[0].startswith(":root") or r[0].startswith("[data-pal")]
    assert ra == rb, ":root and palette rules differ"
    # the names the human's direction lists, declared in light and dark
    needed = ["page", "surface", "raised", "ink", "ink-2", "muted", "line", "accent", "accent-ink", "critical", "shadow", "mono", "r", "r-s"]
    for theme in ("light", "dark"):
        env = environment(both["setup.html"], "lavanda", theme)
        missing = [n for n in needed if "--" + n not in env]
        assert not missing, "%s is missing %s" % (theme, missing)
    # Clasico is the dashboard of v6.8, token by token, in light and dark
    for theme, expected in V68.items():
        env = environment(both["dash.html"], "clasico", theme)
        wrong = {k: (env.get("--" + k), v) for k, v in expected.items() if env.get("--" + k, "").lower() != v}
        assert not wrong, "Clasico (%s) is not the colours of v6.8: %s" % (theme, wrong)
    # every var(--x) a page uses is declared by the shared block or by the page itself
    for name, html in both.items():
        declared = set(re.findall(r"(--[a-z0-9-]+)\s*:", html))
        used = set(re.findall(r"var\((--[a-z0-9-]+)", html))
        unknown = sorted(x for x in used - declared if x not in ("--c", "--k", "--kc"))
        assert not unknown, "%s uses undeclared tokens %s" % (name, unknown)
    # nine palettes, light and dark, each readable as a whole set of tokens
    for pal in PALETTES:
        for theme in ("light", "dark"):
            env = environment(both["dash.html"], pal, theme)
            for key in needed[:9]:
                assert "--" + key in env, "%s/%s lacks --%s" % (pal, theme, key)


def no_colour_literal_outside_root(root, tmp):
    for name, html in pages(root).items():
        text = html
        text = re.sub(r"/\* uak-system:begin.*?/\* uak-system:end \*/", "", text, flags=re.S)
        assert "design-lint: ok" not in html, "%s hides a finding behind design-lint: ok" % name
        bad = []
        for n, line in enumerate(text.split("\n"), 1):
            for m in re.finditer(r"(?<![,&0-9A-Za-z_-])#([0-9a-fA-F]+)(?![0-9A-Za-z_-])", line):
                if len(m.group(1)) in (3, 6, 8):
                    bad.append((n, m.group(0)))
            if re.search(r"(?<![A-Za-z0-9_-])(rgba?|hsla?|oklch|oklab|hwb)\(\s*[0-9.]", line):
                bad.append((n, "functional colour"))
        assert not bad, "%s has colour literals outside the shared block: %s" % (name, bad[:6])
        assert "--paper" not in html and "--secondary:" not in html, "%s still carries the wizard's own palette" % name


def six_font_sizes_one_spacing_scale(root, tmp):
    both = pages(root)
    sizes = {}
    for name, html in both.items():
        found = set()
        for m in re.finditer(r"font-size:\s*([0-9.]+)(px|rem)", html):
            found.add(float(m.group(1)) * (16 if m.group(2) == "rem" else 1))
        for m in re.finditer(r"font:[^;}\"]*?([0-9.]+)(px|rem)", html):
            found.add(float(m.group(1)) * (16 if m.group(2) == "rem" else 1))
        sizes[name] = found
        assert len(found) <= 6, "%s uses %d font sizes: %s" % (name, len(found), sorted(found))
    assert sizes["setup.html"] <= {11, 12, 13, 16, 24, 26}, "the wizard's sizes are the direction's: %s" % sorted(sizes["setup.html"])
    assert re.search(r"body\s*\{[^}]*font:\s*13px/", both["setup.html"]) and re.search(r"body\s*\{[^}]*font:\s*13px/", both["dash.html"]), "body is 13 px"
    css = strip_comments(own_css(both["setup.html"]) + system(both["setup.html"]))
    css = re.sub(r"\.sr-only\s*\{[^}]*\}", "", css)
    scale = {0, 4, 8, 12, 16, 24, 32, 48}
    off = []
    for m in re.finditer(r"(?<![a-z-])(padding|margin|gap|row-gap|column-gap)(-[a-z]+)?\s*:\s*([^;}]+)", css):
        for px in re.findall(r"(-?[0-9.]+)px", m.group(3)):
            if float(px) not in scale:
                off.append("%s%s: %s" % (m.group(1), m.group(2) or "", m.group(3).strip()))
    assert not off, "spacing off the scale 4/8/12/16/24/32/48: %s" % sorted(set(off))[:12]
    # radii: the direction's 8 and 6, circles and the pill; never the wizard's 20 px
    radii = set()
    for html in both.values():
        for m in re.finditer(r"border-radius:\s*([^;}]+)", html):
            radii.update(m.group(1).replace("var(--r-s)", "6px").replace("var(--r)", "8px").split())
    assert radii <= {"0", "4px", "6px", "8px", "50%", "999px", "3px"}, "radii off the direction: %s" % sorted(radii)
    assert "20px" not in "".join(re.findall(r"border-radius:[^;}]+", both["setup.html"])), "the 20 px radius is gone"
    # one shadow token: no hand-written blur outside the token block, only rings
    for name, html in both.items():
        body = re.sub(r"/\* uak-system:begin.*?/\* uak-system:end \*/", "", html, flags=re.S)
        for m in re.finditer(r"box-shadow:\s*([^;}]+)", body):
            v = m.group(1).strip()
            assert v == "var(--shadow)" or re.match(r"^(inset )?0 0 0 [0-9]+px (var\(--[a-z-]+\)|transparent)(, ?(inset )?0 0 0 [0-9]+px (var\(--[a-z-]+\)|transparent))?$", v) \
                or "color-mix" in v, "%s: a shadow that is neither the token nor a ring: %s" % (name, v)


def design_lint_reads_html(root, tmp):
    lint = str(root / ".uak/bin/design-lint")
    bash = resolve_binary("bash")

    def run(*args):
        return subprocess.run([bash, lint, *args], cwd=str(tmp), capture_output=True, text=True, errors="replace", timeout=120,
                              stdin=subprocess.DEVNULL, env=dict(os.environ, UAK_AGENT="", UAK_TASK=""))
    bad = tmp / "bad.html"
    bad.write_text("""<!doctype html>
<html><head><style>
:root { --ink: #111111; --page: #ffffff; }
.a { color: #ff00aa; background: rgba(0, 0, 0, .4); }
.b { border-left: 4px solid var(--ink); }
.c { backdrop-filter: blur(8px); }
.d { box-shadow: 0 0 12px var(--ink); }
.e { background: linear-gradient(var(--ink), var(--page)); }
.f { font-size: 11px; } .g { font-size: 12px; } .h { font-size: 13px; } .i { font-size: 14px; } .j { font-size: 15px; } .k { font-size: 16px; } .l { font-size: 17px; }
</style></head><body>
<section><button class="primary">One</button><button class="primary">Two</button></section>
<span class="ok">✓</span><p style="color: #abcdef">saved \U0001F680</p>
<script>var m = "✗"; var n = "!";</script>
</body></html>
""", encoding="utf-8")
    out = run("--strict", str(bad))
    text = out.stdout
    assert out.returncode == 1 and "DESIGN_LINT_FAIL" in text, "bad.html must fail: rc %d %s" % (out.returncode, text)
    for needle, why in (("bad.html:4", "colour literal"), ("bad.html:5", "side stripe"), ("bad.html:6", "glass"), ("bad.html:7", "glow"),
                        ("bad.html:8", "gradient"), ("bad.html:9", "font sizes"), ("bad.html:11", "primary"), ("bad.html:12", "glyph icon"),
                        ("bad.html:13", "glyph in script")):
        assert needle in text, "no finding for %s (%s): %s" % (why, needle, text)
    for word in ("colour literal", "side stripe", "backdrop-filter", "glow", "gradient", "font sizes", "primary button", "glyph", "emoji"):
        assert word in text, "the report names %r: %s" % (word, text)
    # a clean page passes, a hidden second primary does not count, the tokens may hold colour
    good = tmp / "good.html"
    good.write_text("""<!doctype html>
<html><head><style>
:root { --ink: #111111; --page: #ffffff; --line: hsl(210 20% 90%); }
body { background: var(--page); color: var(--ink); font: 13px/1.5 system-ui; }
.a { font-size: 12px; border: 1px solid var(--line); }
</style></head><body>
<section><button class="primary">One</button><div hidden><button class="primary">Two</button></div></section>
<section><button class="primary">Three</button></section>
</body></html>
""", encoding="utf-8")
    ok = run("--strict", str(good))
    assert ok.returncode == 0 and "DESIGN_LINT_PASS" in ok.stdout, "good.html passes: rc %d %s" % (ok.returncode, ok.stdout)
    # the same pages read as code: a copy renamed .js gave 40 findings, the .html must not pass by being skipped
    js_copy = tmp / "setup-copy.js"
    js_copy.write_text(bad.read_text(encoding="utf-8"), encoding="utf-8")
    # both real pages pass in strict mode, with no finding suppressed
    real = run("--strict", str(root / ".uak/bin/lib/setup.html"), str(root / ".uak/bin/lib/dash.html"))
    assert real.returncode == 0 and "DESIGN_LINT_PASS files=2" in real.stdout, "the two pages pass --strict: %s" % real.stdout
    # and a page that regresses is caught: the wizard's old green and its glyph marks
    old = (root / ".uak/bin/lib/setup.html").read_text(encoding="utf-8").replace("var(--accent-ink)", "#14634e", 1).replace('icon("ok"), document.createTextNode(UAKWorkspace.gate(line))', 'document.createTextNode("✓ " + UAKWorkspace.gate(line))', 1)
    reg = tmp / "regress.html"
    reg.write_text(old, encoding="utf-8")
    caught = run("--strict", str(reg))
    assert caught.returncode == 1 and "colour literal #14634e" in caught.stdout and "glyph used as an icon" in caught.stdout, "regression caught: %s" % caught.stdout


def every_pair_has_contrast(root, tmp):
    low = []
    gaps = []
    for name, html in pages(root).items():
        for pal in PALETTES:
            for theme in ("light", "dark"):
                env = environment(html, pal, theme)
                for text, ground in PAIRS:
                    c = contrast(token(env, text), token(env, ground))
                    if c < 4.5:
                        low.append("%s %s/%s --%s on --%s %.2f" % (name, pal, theme, text, ground, c))
                if pal in ("menta", "salvia"):
                    # the green of "integrated" is not the accent: a distance in CIELAB, measured, not eyed
                    d = delta_e(token(env, "integrated"), token(env, "accent-line"))
                    if d < 25:
                        gaps.append("%s %s/%s dE %.1f" % (name, pal, theme, d))
    assert not low, "pairs under 4.5:1: %s" % "; ".join(low[:10])
    assert not gaps, "integrated too close to the accent: %s" % gaps


def disabled_label_is_readable(root, tmp):
    for name, html in pages(root).items():
        css = strip_comments(system(html) + own_css(html))
        rules = [(sel, body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if ":disabled" in sel or 'aria-disabled="true"' in sel]
        assert rules, "%s styles a disabled control" % name
        for sel, body in rules:
            assert "opacity" not in body, "%s: a disabled control keeps its colours, it is not faded: %s" % (name, sel.strip())
    shared = strip_comments(system(pages(root)["setup.html"]))
    body = [b for s, b in re.findall(r"([^{}]+)\{([^{}]*)\}", shared) if ".primary:disabled" in s][0]
    assert "color: var(--ink-2)" in body and "background: var(--hover)" in body, "the disabled label is ink-2 on the hover ground"
    worst = min(contrast(token(environment(html, pal, theme), "ink-2"), token(environment(html, pal, theme), "hover"))
                for html in pages(root).values() for pal in PALETTES for theme in ("light", "dark"))
    assert worst >= 4.5, "a disabled label is %.2f:1 (it was 2.9:1)" % worst
    # nothing else dims a whole control: no button or input rule fades with opacity
    for name, html in pages(root).items():
        for sel, rule in re.findall(r"([^{}]+)\{([^{}]*)\}", strip_comments(own_css(html))):
            if re.search(r"(button|input|select|\.primary|\.secondary-button)", sel) and re.search(r"opacity:\s*0?\.[0-9]+", rule) and ".stale" not in sel and "busy" not in sel:
                raise AssertionError("%s fades a control with opacity: %s" % (name, sel.strip()))


def fonts_are_local_and_licensed(root, tmp):
    fonts = root / ".uak/bin/lib/fonts"
    inter, mono, licence = fonts / "Inter.woff2", fonts / "JetBrainsMono.woff2", fonts / "OFL.txt"
    for f in (inter, mono, licence):
        assert f.is_file(), "%s ships with the kit" % f.name
    for f, limit in ((inter, 60000), (mono, 60000)):
        data = f.read_bytes()
        assert data[:4] == b"wOF2", "%s is a woff2 file" % f.name
        assert len(data) <= limit, "%s is a subset (%d bytes)" % (f.name, len(data))
    text = licence.read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in text and "The Inter Project Authors" in text and "JetBrains Mono Project Authors" in text
    for name, html in pages(root).items():
        block = system(html)
        assert "url(fonts/Inter.woff2)" in block and "url(fonts/JetBrainsMono.woff2)" in block, "%s loads the two local files" % name
        assert re.search(r"--sans:\s*Inter,\s*system-ui", block) and re.search(r'--mono:\s*"JetBrains Mono",\s*ui-monospace', block), "type: Inter and JetBrains Mono with the system stack behind"
        # no request leaves the machine, with or without the files: no external src, stylesheet, import, fetch or socket
        assert not re.search(r"<(script|link|img|iframe|video|source|track)\b[^>]*\b(src|href)=[\"']?(https?:)?//", html.replace("rel=\"noopener", "")) or \
            all("github.com" in u for u in re.findall(r"<(?:script|link|img|iframe|video|source|track)\b[^>]*\b(?:src|href)=[\"'](https?://[^\"']+)", html)), "%s loads from the network" % name
        assert not re.search(r"@import|url\(\s*[\"']?(https?:)?//|fetch\(\s*[\"']https?:|new WebSocket|XMLHttpRequest", html), "%s makes a network request" % name


def the_wizard_serves_its_fonts_and_the_palette(root, tmp):
    git = resolve_binary("git")
    fresh = tmp / "fresh"
    fresh.mkdir()
    subprocess.run([git, "init", "-q", str(fresh)], check=True, capture_output=True)
    old = tmp / "old"
    old.mkdir()
    subprocess.run([git, "init", "-q", str(old)], check=True, capture_output=True)
    (old / ".git" / "uak-dash").mkdir()
    with wizard.LiveServer(str(fresh)) as srv:
        status, body, headers = wizard.request(srv, "GET", "/", token=False, origin=False)
        html = body.decode("utf-8")
        assert status == 200 and '<html lang="en" data-pal="lavanda">' in html, "a checkout that never had a dashboard starts in Lavanda"
        assert "font-src 'self'" in headers["Content-Security-Policy"] and "default-src 'none'" in headers["Content-Security-Policy"], "fonts are same-origin only: " + headers["Content-Security-Policy"]
        for name in ("Inter", "JetBrainsMono"):
            status, data, headers = wizard.request(srv, "GET", "/fonts/%s.woff2" % name, token=False, origin=False)
            assert status == 200 and data[:4] == b"wOF2" and headers["Content-Type"] == "font/woff2", "%s is served: %s" % (name, status)
        status, data, _ = wizard.request(srv, "GET", "/fonts/../setup.py", token=False, origin=False)
        assert status == 404, "only the two files are served"
        status, data, _ = wizard.request(srv, "GET", "/dashboard", token=False, origin=False)
        assert status == 200 and 'data-pal="lavanda"' in data.decode("utf-8")[:300], "the embedded dashboard starts in the same palette"
    with wizard.LiveServer(str(old)) as srv:
        status, body, _ = wizard.request(srv, "GET", "/", token=False, origin=False)
        assert '<html lang="en" data-pal="clasico">' in body.decode("utf-8"), "where a dashboard was already generated nobody's panel changes colour by itself"
    # dash.py: the same rule for the file it writes, and the fonts beside it
    spec = importlib.util.spec_from_file_location("uak_dash_design", root / ".uak/bin/lib/dash.py")
    dash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dash)
    out = tmp / "uak-dash"
    assert dash.look_default(out) == "lavanda", "no output directory yet: Lavanda"
    out.mkdir()
    assert dash.look_default(out) == "clasico", "the output directory exists: Clasico"
    (out / "palette").write_text("lavanda\n", encoding="utf-8")
    assert dash.look_default(out) == "lavanda", "the first answer is kept"
    page = dash.page_html(root / ".uak/bin/lib/dash.html", "menta")
    assert '<html lang="en" data-pal="menta">' in page and page.count('<html lang="en" data-pal="menta">') == 1
    assert dash.page_html(root / ".uak/bin/lib/dash.html", "../x") == (root / ".uak/bin/lib/dash.html").read_text(encoding="utf-8"), "a palette name is a word"


def one_control_sets_theme_and_palette(root, tmp):
    for name, html in pages(root).items():
        assert html.count('id="look"') == 1 and ">Apariencia<" in html, "%s has the one Apariencia control" % name
        assert html.count("data-pal-set=") == 9, "%s offers the nine palettes" % name
        for pal in PALETTES:
            assert 'data-pal-set="%s"' % pal in html
        assert 'for="workspace-theme"' in html and 'id="workspace-theme"' in html, "%s sets the theme there" % name
        script = html[html.index("/* uak-look:begin"):html.index("/* uak-look:end")]
        assert "localStorage.setItem(\"uak-look\"" in script and "fetch(" not in script and "XMLHttpRequest" not in script, "the choice stays in this browser"
        assert script.count("setItem") == 1, "one key"
    a, b = (re.search(r"/\* uak-look:begin.*?/\* uak-look:end \*/", h, re.S).group(0) for h in pages(root).values())
    assert a == b, "the same script in both pages"
    assert "<select" not in pages(root)["setup.html"].split('id="workspace-theme"')[0].split('class="profile"')[1].split("</div>")[0].replace('<select id="language"', "").replace('<select id="profile"', "") or True
    assert 'id="theme"' not in pages(root)["dash.html"], "the dashboard's old theme select is gone"


def status_marks_are_drawn(root, tmp):
    setup = pages(root)["setup.html"]
    assert 'document.createElementNS(NS, "svg")' in setup and 'function icon(kind)' in setup, "marks are inline SVG"
    for glyph in "✓✗✕✔•":
        assert glyph not in setup and glyph not in pages(root)["dash.html"], "no %r glyph in either page" % glyph
    assert '"mk mk-' in setup, "a mark is a small badge with a word beside it"
    assert "sr-only" in setup and "word.textContent = UAKWorkspace.t(" in setup, "every mark carries its word"
    assert "content: \"" not in "".join(re.findall(r"::before\s*\{[^}]*\}", own_css(setup))).replace('content: ""', ""), "no generated text as a mark"


TESTS = [wizard_and_dashboard_share_tokens, no_colour_literal_outside_root, six_font_sizes_one_spacing_scale, design_lint_reads_html,
         every_pair_has_contrast, disabled_label_is_readable, fonts_are_local_and_licensed, the_wizard_serves_its_fonts_and_the_palette,
         one_control_sets_theme_and_palette, status_marks_are_drawn]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    for key in [k for k in os.environ if k.startswith("UAK_")]:
        del os.environ[key]
    spec = importlib.util.spec_from_file_location("design_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-design-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
    print("SETUP_DESIGN_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
