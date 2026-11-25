#!/usr/bin/env python3
"""UI-017: the welcome screen of the local setup page offers the demo video that UI-016 ships in .uak/media/.
Evidence: Dylan, 2026-11-13: "the landing of the kit is the interface it opens"; novices in the test rounds did not know
which steps happen in the page, in a terminal or by the agents.
The server serves four fixed names from the engine's own kit (never a path from the request), with the page's Host
check, nosniff, the right Content-Type and HTTP Range so the browser can seek. The page never autoplays and hides the
block when the files are missing. Fixtures: a copy of bin/lib with tiny media files in a temporary folder."""
import argparse
import hashlib
import http.client
import importlib.util
import json
import math
import os
import re
import shutil
import struct
import tempfile
import threading
import time
import traceback
import zlib
from pathlib import Path

ROOT = None
NAMES = ("tutorial.mp4", "tutorial-en.vtt", "tutorial-es.vtt", "tutorial-poster.jpg")
TYPES = {"tutorial.mp4": "video/mp4", "tutorial-en.vtt": "text/vtt; charset=utf-8",
         "tutorial-es.vtt": "text/vtt; charset=utf-8", "tutorial-poster.jpg": "image/jpeg"}
MP4 = bytes(range(256)) * 4  # 1024 bytes, each offset recognizable


def lib(name):
    return (ROOT / ".uak/bin/lib" / name).read_text(encoding="utf-8")


def catalog():
    text = lib("workspace.js")
    pairs = re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)
    return {json.loads(a): json.loads(b) for a, b in pairs}


def section(html, ident):
    assert 'id="%s"' % ident in html, "the page has #%s" % ident
    start = html.rindex("<", 0, html.index('id="%s"' % ident))
    tag = re.match(r"<(\w+)", html[start:]).group(1)
    depth = 0
    for m in re.finditer(r"<(/?)%s\b[^>]*>" % tag, html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start:start + m.end()]
    raise AssertionError("unclosed %s" % ident)


def visible_texts(fragment):
    body = re.sub(r"<(script|style)\b[\s\S]*?</\1>", " ", fragment)
    return [" ".join(t.split()) for t in re.split(r"<[^>]*>", body) if re.search(r"[A-Za-z]{2}", t)]


def script(html):
    return html[html.index('<script nonce="__NONCE__">'):]


def fixture_kit(tmp, media=True):
    """A copy of the engine's bin/lib in a temporary kit, with tiny media files; returns the loaded setup module."""
    kit = tmp / "kit/.uak"
    shutil.copytree(str(ROOT / ".uak/bin/lib"), str(kit / "bin/lib"))
    folder = kit / "media"
    folder.mkdir()
    if media:
        (folder / "tutorial.mp4").write_bytes(MP4)
        (folder / "tutorial-en.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n", encoding="utf-8")
        (folder / "tutorial-es.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola\n", encoding="utf-8")
        (folder / "tutorial-poster.jpg").write_bytes(b"\xff\xd8\xff\xe0poster\xff\xd9")
    (folder / "secret.txt").write_text("not served", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("tutorial_setup_%d" % id(tmp), kit / "bin/lib/setup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, folder


class Live:
    def __init__(self, module, target=""):
        self.server = module.make_server(target, installer=Path(os.devnull), run=None)

    def __enter__(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.server

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)


def get(server, path, headers=None, host=None, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host or "127.0.0.1:%d" % server.server_port)
        for key, value in (headers or {}).items():
            conn.putheader(key, value)
        conn.endheaders()
        res = conn.getresponse()
        return res.status, res.read(), {k.lower(): v for k, v in res.getheaders()}
    finally:
        conn.close()


def status(server):
    code, body, _ = get(server, "/api/status", {"X-UAK-Token": server.token})
    assert code == 200, (code, body)
    return json.loads(body.decode("utf-8"))


def welcome_offers_the_demo(root, tmp):
    html = lib("setup.html")
    welcome = section(html, "welcome")
    assert 'id="demo"' in welcome, "the demo block sits on the welcome screen"
    demo = section(html, "demo")
    words = " ".join(visible_texts(demo))
    assert "Watch the 75-second demo" in words, words
    es = catalog()
    for text in visible_texts(demo):
        assert text in es, "%r has a Spanish translation in workspace.js" % text
    assert re.search(r'aria-labelledby="demo-heading"', demo) and 'id="demo-heading"' in demo, "a labelled region"
    video = re.search(r"<video\b[^>]*>", demo)
    assert video, "a <video> element plays the demo in the page"
    tag = video.group(0)
    for attr in ("controls", 'preload="none"', "playsinline", 'data-src="/media/tutorial.mp4"',
                 'data-poster="/media/tutorial-poster.jpg"'):
        assert re.search(r"\s%s(\s|>|=|$)" % re.escape(attr), tag) or attr in tag, "%s on the video: %s" % (attr, tag)
    tracks = re.findall(r"<track\b[^>]*>", demo)
    langs = {}
    for t in tracks:
        assert 'kind="captions"' in t, t
        langs[re.search(r'srclang="(\w+)"', t).group(1)] = re.search(r'data-src="([^"]+)"', t).group(1)
    assert langs == {"en": "/media/tutorial-en.vtt", "es": "/media/tutorial-es.vtt"}, langs
    code = script(html)
    m = re.search(r"function demoCaptions\(\) \{([\s\S]*?)\n        \}", code)
    assert m, "demoCaptions() picks the caption track of the page's language"
    assert "UAKWorkspace.language()" in m.group(1) and '"showing"' in m.group(1) and "default" in m.group(1), m.group(1)
    assert re.search(r'addEventListener\("uak:language"[\s\S]{0,300}demoCaptions\(\)', code), \
        "changing the language switches the captions"
    csp = re.search(r'"Content-Security-Policy", "([^"]+)"', lib("setup.py")).group(1)
    assert "media-src 'self'" in csp and re.search(r"img-src [^;]*'self'", csp), csp
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp, "the rest of the policy stays: %s" % csp
    module, _ = fixture_kit(tmp)
    with Live(module) as server:
        assert status(server).get("demo") is True, "the status tells the page the demo can be shown"


def demo_is_served_safely(root, tmp):
    module, folder = fixture_kit(tmp)
    project = tmp / "project"
    (project / ".uak/media").mkdir(parents=True)
    (project / ".uak/media/tutorial.mp4").write_bytes(b"the project's copy is never served")
    with Live(module, str(project)) as server:
        for name in NAMES:
            code, body, headers = get(server, "/media/" + name)
            assert code == 200, (name, code, body[:200])
            assert body == (folder / name).read_bytes(), "%s comes from the engine's kit, whole" % name
            assert headers.get("content-type") == TYPES[name], (name, headers.get("content-type"))
            assert headers.get("x-content-type-options") == "nosniff", name
            assert headers.get("accept-ranges") == "bytes", name
            assert headers.get("content-length") == str(len(body)), name
            assert headers.get("cross-origin-resource-policy") == "same-origin", name
        # Range: the browser seeks with single ranges.
        cases = {"bytes=10-19": (10, 19), "bytes=1000-": (1000, 1023), "bytes=-5": (1019, 1023),
                 "bytes=1020-5000": (1020, 1023), "bytes=0-0": (0, 0)}
        for header, (a, b) in cases.items():
            code, body, headers = get(server, "/media/tutorial.mp4", {"Range": header})
            assert code == 206, (header, code)
            assert body == MP4[a:b + 1], (header, len(body))
            assert headers.get("content-range") == "bytes %d-%d/1024" % (a, b), (header, headers.get("content-range"))
            assert headers.get("content-length") == str(b - a + 1), header
            assert headers.get("content-type") == "video/mp4", header
        for header in ("bytes=1024-", "bytes=5000-6000", "bytes=-0"):
            code, _, headers = get(server, "/media/tutorial.mp4", {"Range": header})
            assert code == 416, (header, code)
            assert headers.get("content-range") == "bytes */1024", (header, headers.get("content-range"))
        for header in ("bytes=0-1,5-6", "items=0-1", "bytes=9-3", "bytes=abc"):
            code, body, _ = get(server, "/media/tutorial.mp4", {"Range": header})
            assert code == 200 and body == MP4, "an unusable Range is ignored: %s → %d" % (header, code)
        # Only the four names, never a path from the request.
        for path in ("/media/../setup.py", "/media/%2e%2e/setup.py", "/media/..%2fsetup.py", "/media/secret.txt",
                     "/media/", "/media", "/media/tutorial.MP4", "/media/tutorial.mp4/", "/media/tutorial.mp4?x=1",
                     "/media//tutorial.mp4", "/media/tutorial.mp4%00", "/media/./tutorial.mp4",
                     "/media/tutorial", "/.uak/media/tutorial.mp4", "/media/other.mp4"):
            code, body, _ = get(server, path)
            assert code == 404, "%s → %d %r" % (path, code, body[:80])
            assert b"not served" not in body and b"import" not in body, path
        # The page's protections: the loopback Host, and no other site may load it.
        for host in ("localhost:%d" % server.server_port, "evil.example", "127.0.0.1:1"):
            code, body, _ = get(server, "/media/tutorial.mp4", host=host)
            assert code == 403 and MP4 not in body, (host, code)
        for site in ("cross-site", "same-site"):
            code, body, _ = get(server, "/media/tutorial.mp4", {"Sec-Fetch-Site": site})
            assert code == 403 and MP4 not in body, (site, code)
        for site in ("same-origin", "none"):
            code, _, _ = get(server, "/media/tutorial.mp4", {"Sec-Fetch-Site": site})
            assert code == 200, (site, code)
        code, _, _ = get(server, "/media/tutorial.mp4", method="POST")
        assert code in (403, 404, 405, 501), "media is read-only: %d" % code
        # A symlink in the media folder is not followed, even to a real file.
        (folder / "tutorial-poster.jpg").unlink()
        try:
            os.symlink(str(folder / "secret.txt"), str(folder / "tutorial-poster.jpg"))
        except (OSError, NotImplementedError):
            print("  note: no symlink privilege here, the symlink case is skipped")
        else:
            code, body, _ = get(server, "/media/tutorial-poster.jpg")
            assert code == 404 and b"not served" not in body, (code, body[:80])
            assert status(server).get("demo") is False, "a symlinked file hides the block"


def demo_never_autoplays(root, tmp):
    html = lib("setup.html")
    demo = section(html, "demo")
    assert "autoplay" not in html.lower(), "nothing on the page autoplays"
    assert not re.search(r"<video\b[^>]*\smuted\b", demo), "no muted autoplay"
    assert 'preload="none"' in demo, "nothing is downloaded until the person presses play"
    code = script(html)
    assert not re.search(r"\.play\(", code), "the script never starts the video"
    style = html[:html.index("</style>")]
    rules = re.findall(r"([^{}]*\.demo[^{}]*)\{([^{}]*)\}", style)
    assert rules, "the demo block has its own styles"
    for selector, body in rules:
        assert "animation" not in body and "transition" not in body, "no animated poster: %s" % selector
    assert re.search(r"@media \(prefers-reduced-motion: reduce\)", style), "the page honors reduced motion"


def missing_demo_hides_the_block(root, tmp):
    html = lib("setup.html")
    demo = re.search(r'<section\b[^>]*id="demo"[^>]*>', html)
    assert demo and re.search(r"\shidden(\s|>|=)", demo.group(0)), "the block starts hidden: %s" % demo
    code = script(html)
    m = re.search(r"function showDemo\(available\) \{([\s\S]*?)\n        \}", code)
    assert m, "showDemo(available) shows the block only when the server has the files"
    assert re.search(r'el\("demo"\)\.hidden = !available', m.group(1)), m.group(1)
    assert not re.search(r'\s(src|poster)="/media/', html), "a hidden block requests nothing: addresses wait in data-*"
    for line in ("track.src = track.dataset.src", "video.poster = video.dataset.poster", "video.src = video.dataset.src"):
        assert line in m.group(1), "showDemo(true) sets %s" % line
    assert m.group(1).index("!available") < m.group(1).index("video.src ="), "only when available"
    assert re.search(r"showDemo\(data\.demo\)", code), "the first status decides"
    handler = re.search(r'el\("demo-video"\)\.addEventListener\("error", function \(\) \{([\s\S]*?)\}\);', code)
    assert handler and "showDemo(false)" in handler.group(1), "a file that fails to load hides the block"
    assert "error(" not in handler.group(1).replace("showDemo(false)", ""), "without an error banner"
    module, folder = fixture_kit(tmp, media=False)
    with Live(module) as server:
        assert status(server).get("demo") is False, "no media: the block stays hidden"
        for name in NAMES:
            code, _, headers = get(server, "/media/" + name)
            assert code == 404 and headers.get("content-type", "").startswith("application/json"), (name, code)
    (folder / "tutorial.mp4").write_bytes(MP4)
    with Live(module) as server:
        assert status(server).get("demo") is False, "one file is not the whole demo: still hidden"


# UAK-199: the media themselves. Why: the review of UAK-158 found the poster still showing the old dark card with a
# purple glow (the look from before docs/design/DIRECTION.md) and the frames showing screens of v6.8. The poster and three
# frames extracted at render time (docs/video/render.mjs) are read here in pure Python, without ffmpeg: their dominant
# colours must be the Lavanda palette of the kit's own design system (the uak-system block of setup.html).
SHIPPED = {"tutorial.mp4": 820642, "tutorial-poster.jpg": 38328}  # the sizes of v6.8: the new media are not heavier
MAX_SECONDS = 75.0
FRAMES = ("tutorial-frame-1.png", "tutorial-frame-2.png", "tutorial-frame-3.png")
FRAME_BYTES = 40 * 1024
GROUNDS = ("page", "surface", "raised", "hover", "accent-wash", "line")


class Skip(Exception):
    """The case cannot run here: an installed project (install.sh --with-tests) has neither the media nor docs/video."""


def kit_media(name):
    """docs/video and .uak/media live in the kit's repository; a project with --with-tests has neither (a skip, counted)."""
    media, video = ROOT / ".uak/media", ROOT.parent / "docs/video"
    if not video.is_dir() and not media.is_dir():
        raise Skip("no media and no docs/video: not the kit's repository")
    assert video.is_dir(), "docs/video exists beside the kit"
    assert media.is_dir(), "kit/.uak/media exists"
    return media, video


def lavanda():
    """{token: (r, g, b)} for the Lavanda palette in light, computed from the uak-system block of setup.html."""
    css = lib("setup.html")
    css = css[css.index("/* uak-system:begin"):css.index("/* uak-system:end")]
    pal = re.search(r'\[data-pal="lavanda"\] \{ --h: (\d+); --sa: (\d+)%; \}', css)
    assert pal, "setup.html names the Lavanda hue and saturation"
    hue, sat = float(pal.group(1)), float(pal.group(2))
    block = re.search(r':root\[data-pal\]:not\(\[data-pal="clasico"\]\) \{([^}]*)\}', css).group(1)

    def hsl(h, s, l):
        s, l = s / 100.0, l / 100.0
        c = (1 - abs(2 * l - 1)) * s
        x = c * (1 - abs((h / 60.0) % 2 - 1))
        r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h // 60) % 6]
        m = l - c / 2
        return tuple(int(round((v + m) * 255)) for v in (r, g, b))

    def part(text, kind):
        text = text.strip()
        if text == "var(--h)":
            return hue
        if text == "var(--sa)":
            return sat
        m = re.match(r"calc\(var\(--sa\) \* ([\d.]+)\)$", text)
        if m:
            return sat * float(m.group(1))
        return float(text.rstrip("%"))

    out = {}
    for name, value in re.findall(r"--([a-z0-9-]+):\s*([^;]+);", block):
        value = value.strip()
        if re.match(r"#[0-9a-f]{6}$", value):
            out[name] = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
            continue
        m = re.match(r"hsl\((var\(--h\)|[\d.]+) (var\(--sa\)|calc\(var\(--sa\) \* [\d.]+\)|[\d.]+%) ([\d.]+%)\)$", value)
        if m:
            out[name] = hsl(part(m.group(1), "h"), part(m.group(2), "s"), part(m.group(3), "l"))
    for name in GROUNDS + ("ink", "btn", "accent-line", "integrated", "review", "claimed"):
        assert name in out, "the Lavanda palette has --%s" % name
    return out


def png_pixels(path):
    """(width, height, [(r, g, b), ...]) of an 8-bit RGB or RGBA PNG, and its tEXt chunks."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "%s is a PNG" % path.name
    pos, idat, text, head = 8, b"", {}, None
    while pos < len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + size]
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"tEXt":
            key, _, value = body.partition(b"\0")
            text[key.decode("latin-1")] = value.decode("latin-1")
        pos += size + 12
    width, height, depth, ctype, _, _, interlace = head
    assert depth == 8 and ctype in (2, 6) and interlace == 0, "%s: 8-bit RGB(A), not interlaced" % path.name
    bpp = 3 if ctype == 2 else 4
    raw, stride, rows, prev = zlib.decompress(idat), width * bpp, [], bytearray(width * bpp)
    for y in range(height):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    pixels = [tuple(row[x * bpp:x * bpp + 3]) for row in rows for x in range(width)]
    return width, height, pixels, text


def jpeg_blocks(path):
    """The average colour of every 8x8 block of a baseline JPEG: only the DC coefficients are decoded (no IDCT), which is
    all a dominant-colour check needs. Returns (width, height, [(r, g, b), ...]) with one entry per luma block."""
    data = path.read_bytes()
    assert data[:2] == b"\xff\xd8", "%s is a JPEG" % path.name
    pos, qt, ht, comps, restart = 2, {}, {}, [], 0
    while True:
        while data[pos] != 0xFF:
            pos += 1
        marker = data[pos + 1]
        pos += 2
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        size = struct.unpack(">H", data[pos:pos + 2])[0]
        seg = data[pos + 2:pos + size]
        if marker == 0xDB:
            i = 0
            while i < len(seg):
                prec, tid = seg[i] >> 4, seg[i] & 15
                qt[tid] = struct.unpack(">H", seg[i + 1:i + 3])[0] if prec else seg[i + 1]
                i += 1 + 64 * (2 if prec else 1)
        elif marker == 0xC4:
            i = 0
            while i < len(seg):
                cls, tid, counts = seg[i] >> 4, seg[i] & 15, seg[i + 1:i + 17]
                syms, code, table, k = seg[i + 17:i + 17 + sum(counts)], 0, {}, 0
                for length in range(1, 17):
                    for _ in range(counts[length - 1]):
                        table[(length, code)] = syms[k]
                        code, k = code + 1, k + 1
                    code <<= 1
                ht[(cls, tid)] = table
                i += 17 + sum(counts)
        elif marker == 0xC0 or marker == 0xC1:
            height, width, n = struct.unpack(">HHB", seg[1:6])
            for c in range(n):
                cid, hv, q = seg[6 + 3 * c:9 + 3 * c]
                comps.append({"id": cid, "h": hv >> 4, "v": hv & 15, "q": q})
        elif 0xC2 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            raise AssertionError("%s is not a baseline JPEG (marker %02X)" % (path.name, marker))
        elif marker == 0xDD:
            restart = struct.unpack(">H", seg[:2])[0]
        elif marker == 0xDA:
            n = seg[0]
            for c in range(n):
                cid, tables = seg[1 + 2 * c], seg[2 + 2 * c]
                for comp in comps:
                    if comp["id"] == cid:
                        comp["dc"], comp["ac"] = ht[(0, tables >> 4)], ht[(1, tables & 15)]
            pos += size
            break
        pos += size
    assert len(comps) in (1, 3), "%s has 1 or 3 components" % path.name
    # The entropy-coded data, split at restart markers, with the stuffed zero bytes removed.
    parts, cur, i = [], bytearray(), pos
    while i < len(data) - 1:
        if data[i] == 0xFF:
            nxt = data[i + 1]
            if nxt == 0x00:
                cur.append(0xFF)
                i += 2
                continue
            if 0xD0 <= nxt <= 0xD7:
                parts.append(bytes(cur))
                cur = bytearray()
                i += 2
                continue
            if nxt == 0xFF:
                i += 1
                continue
            break
        cur.append(data[i])
        i += 1
    parts.append(bytes(cur))
    hmax, vmax = max(c["h"] for c in comps), max(c["v"] for c in comps)
    mcux, mcuy = -(-width // (8 * hmax)), -(-height // (8 * vmax))

    class Bits:
        def __init__(self, raw):
            self.raw, self.pos = raw, 0

        def bit(self):
            byte = self.raw[self.pos >> 3] if (self.pos >> 3) < len(self.raw) else 0xFF
            self.pos += 1
            return (byte >> (7 - ((self.pos - 1) & 7))) & 1

        def bits(self, n):
            v = 0
            for _ in range(n):
                v = (v << 1) | self.bit()
            return v

        def sym(self, table):
            code = 0
            for length in range(1, 17):
                code = (code << 1) | self.bit()
                if (length, code) in table:
                    return table[(length, code)]
            raise AssertionError("%s: a Huffman code that is not in its table" % path.name)

    def extend(v, n):
        return v - (1 << n) + 1 if n and v < (1 << (n - 1)) else v

    planes = [dict() for _ in comps]
    total, part_i = mcux * mcuy, 0
    bits, pred = Bits(parts[0]), [0] * len(comps)
    for m in range(total):
        if restart and m and m % restart == 0:
            part_i += 1
            bits, pred = Bits(parts[part_i]), [0] * len(comps)
        my, mx = divmod(m, mcux)
        for ci, comp in enumerate(comps):
            for by in range(comp["v"]):
                for bx in range(comp["h"]):
                    n = bits.sym(comp["dc"])
                    pred[ci] += extend(bits.bits(n), n)
                    k = 1
                    while k < 64:
                        rs = bits.sym(comp["ac"])
                        if rs == 0:
                            break
                        bits.bits(rs & 15)
                        k += (rs >> 4) + 1
                    planes[ci][(mx * comp["h"] + bx, my * comp["v"] + by)] = pred[ci] * qt[comp["q"]] / 8.0 + 128
    out, bw, bh = [], -(-width // 8), -(-height // 8)
    for y in range(bh):
        for x in range(bw):
            vals = []
            for ci, comp in enumerate(comps):
                vals.append(planes[ci].get((x * comp["h"] // hmax, y * comp["v"] // vmax), 128))
            if len(vals) == 1:
                vals = [vals[0], 128, 128]
            yy, cb, cr = vals
            rgb = (yy + 1.402 * (cr - 128), yy - 0.344136 * (cb - 128) - 0.714136 * (cr - 128), yy + 1.772 * (cb - 128))
            out.append(tuple(max(0, min(255, int(round(v)))) for v in rgb))
    return width, height, out


def palette_verdict(name, pixels, palette):
    """Why the colours of an image are not the palette's ('' when they are): the most common colour is a light ground of
    the palette, at least 80% of the image is a palette colour, and dark or saturated violet areas stay small (the old
    card: a near-black ground with a purple glow)."""
    def dist(a, b):
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    near, counts, dark, glow = 0, {}, 0, 0
    tokens = list(palette.items())
    for p in pixels:
        key = tuple(v // 6 * 6 for v in p)
        counts[key] = counts.get(key, 0) + 1
        if min(dist(p, c) for _, c in tokens) <= 18:
            near += 1
        lum = (0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2]) / 255.0
        if lum < 0.25:
            dark += 1
        mx, mn = max(p), min(p)
        if mx > 40 and (mx - mn) / float(mx) > 0.35 and p[2] >= p[1] and p[0] >= p[1] and p[2] > p[0] * 0.9:
            glow += 1
    n = float(len(pixels))
    top = max(counts.items(), key=lambda kv: kv[1])[0]
    ground = min(GROUNDS, key=lambda g: dist(top, palette[g]))
    if dist(top, palette[ground]) > 12:
        return "%s: its most common colour %s is not a ground of the palette (nearest --%s %s)" % (
            name, "#%02x%02x%02x" % top, ground, "#%02x%02x%02x" % palette[ground])
    if near / n < 0.80:
        return "%s: only %.0f%% of it is a palette colour (at least 80%%)" % (name, 100 * near / n)
    if dark / n > 0.12:
        return "%s: %.0f%% of it is dark (at most 12%%): a light design, not a dark card" % (name, 100 * dark / n)
    if glow / n > 0.08:
        return "%s: %.0f%% of it is saturated violet (at most 8%%): no purple card, no glow" % (name, 100 * glow / n)
    return ""


def mp4_seconds(path):
    """The duration of an MP4 from its movie header (moov/mvhd), without ffprobe."""
    data = path.read_bytes()

    def boxes(start, end):
        pos = start
        while pos + 8 <= end:
            size, kind = struct.unpack(">I4s", data[pos:pos + 8])
            head = 8
            if size == 1:
                size, head = struct.unpack(">Q", data[pos + 8:pos + 16])[0], 16
            elif size == 0:
                size = end - pos
            yield kind, pos + head, pos + size
            pos += size

    for kind, a, b in boxes(0, len(data)):
        if kind == b"moov":
            for kind2, c, d in boxes(a, b):
                if kind2 == b"mvhd":
                    if data[c] == 1:
                        scale, dur = struct.unpack(">IQ", data[c + 20:c + 32])
                    else:
                        scale, dur = struct.unpack(">II", data[c + 12:c + 20])
                    return dur / float(scale)
    raise AssertionError("%s has no movie header" % path.name)


def scenes_of(video):
    html = (video / "scenes.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="scenes">([\s\S]*?)</script>', html)
    assert m, "scenes.html lists its scenes as JSON in <script id=\"scenes\">"
    scenes = json.loads(m.group(1))
    assert scenes and all({"id", "page", "start", "end"} <= set(s) for s in scenes), "each scene has id, page, start, end"
    return scenes


def vtt_cues(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    blocks = re.split(r"\n\s*\n", text)
    assert blocks[0].startswith("WEBVTT"), "%s starts with WEBVTT" % path.name
    cues = []
    for block in blocks[1:]:
        lines = block.split("\n")
        if "-->" not in lines[0]:
            lines = lines[1:]
        m = re.match(r"(\d\d):(\d\d):(\d\d)\.(\d\d\d) --> (\d\d):(\d\d):(\d\d)\.(\d\d\d)$", lines[0].strip())
        assert m, "%s: a valid time line: %r" % (path.name, lines[0])
        g = [int(v) for v in m.groups()]
        cues.append((g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0,
                     " ".join(l.strip() for l in lines[1:])))
    return cues


def poster_uses_the_kit_palette(root, tmp):
    media, _ = kit_media("poster_uses_the_kit_palette")
    poster = media / "tutorial-poster.jpg"
    assert poster.is_file(), "kit/.uak/media/tutorial-poster.jpg exists"
    width, height, blocks = jpeg_blocks(poster)
    assert (width, height) == (1280, 720), "the poster is 1280x720: %dx%d" % (width, height)
    verdict = palette_verdict("tutorial-poster.jpg", blocks, lavanda())
    assert not verdict, verdict


def frames_use_the_kit_palette(root, tmp):
    media, video = kit_media("frames_use_the_kit_palette")
    palette, scenes = lavanda(), scenes_of(video)
    sha = hashlib.sha256((media / "tutorial.mp4").read_bytes()).hexdigest()
    pages, seen = set(), set()
    for name in FRAMES:
        path = media / name
        assert path.is_file(), "kit/.uak/media/%s exists (render.mjs extracts it from the video)" % name
        width, height, pixels, text = png_pixels(path)
        source = re.match(r"tutorial\.mp4 sha256=([0-9a-f]{64}) t=([\d.]+)$", text.get("Source", ""))
        assert source, "%s says which video and which second it comes from: %r" % (name, text.get("Source"))
        assert source.group(1) == sha, "%s was extracted from another tutorial.mp4: render again (npm run render)" % name
        t = float(source.group(2))
        scene = [s for s in scenes if s["start"] <= t < s["end"]]
        assert scene, "%s: second %.1f is inside a scene" % (name, t)
        assert scene[0]["id"] not in seen, "the three frames come from three different scenes"
        seen.add(scene[0]["id"])
        pages.add(scene[0]["page"])
        verdict = palette_verdict(name, pixels, palette)
        assert not verdict, verdict
    assert {"wizard", "dashboard"} <= pages, "the frames show the wizard and the dashboard: %s" % sorted(pages)


def captions_match_the_scenes(root, tmp):
    media, video = kit_media("captions_match_the_scenes")
    scenes = scenes_of(video)
    cues = json.loads((video / "captions.json").read_text(encoding="utf-8"))
    duration = scenes[-1]["end"]
    assert scenes[0]["start"] == 0, "the first scene starts at 0"
    for a, b in zip(scenes, scenes[1:]):
        assert a["end"] == b["start"], "scenes follow each other: %s ends at %s, %s starts at %s" % (
            a["id"], a["end"], b["id"], b["start"])
    assert duration <= MAX_SECONDS, "the scenes last %.1f s (at most %.0f)" % (duration, MAX_SECONDS)
    starts, ends = {c["start"] for c in cues}, {c["end"] for c in cues}
    for s in scenes:
        assert s["start"] in starts, "scene %s starts at %s with a caption" % (s["id"], s["start"])
        assert s["end"] in ends, "scene %s ends at %s with its last caption" % (s["id"], s["end"])
    for i, c in enumerate(cues, 1):
        inside = [s for s in scenes if s["start"] <= c["start"] and c["end"] <= s["end"]]
        assert len(inside) == 1, "caption %d (%s-%s) sits inside one scene" % (i, c["start"], c["end"])
        assert c["end"] - c["start"] >= 3.0, "caption %d stays at least 3 s on screen" % i
        for lang in ("en", "es"):
            assert len(c[lang]) / (c["end"] - c["start"]) <= 21, "caption %d (%s) can be read in its time: %r" % (
                i, lang, c[lang])
    assert cues[-1]["end"] == duration, "the captions end with the last scene"
    for lang in ("en", "es"):
        got = vtt_cues(media / ("tutorial-%s.vtt" % lang))
        want = [(round(c["start"], 3), round(c["end"], 3), c[lang]) for c in cues]
        assert got == want, "tutorial-%s.vtt is captions.json rendered (npm run render): %r" % (
            lang, [(g, w) for g, w in zip(got, want) if g != w][:2] or (len(got), len(want)))
    seconds = mp4_seconds(media / "tutorial.mp4")
    assert abs(seconds - duration) <= 0.15, "the video lasts as long as its scenes: %.2f s, scenes %.2f s" % (
        seconds, duration)


def media_is_not_heavier(root, tmp):
    media, _ = kit_media("media_is_not_heavier")
    for name, limit in SHIPPED.items():
        size = (media / name).stat().st_size
        assert size <= limit, "%s weighs %d bytes, more than the %d of v6.8" % (name, size, limit)
    seconds = mp4_seconds(media / "tutorial.mp4")
    assert seconds <= MAX_SECONDS, "the video lasts %.1f s (at most %.0f)" % (seconds, MAX_SECONDS)
    for name in FRAMES:
        assert (media / name).is_file(), "kit/.uak/media/%s exists" % name
        size = (media / name).stat().st_size
        assert size <= FRAME_BYTES, "%s weighs %d bytes (a small image: at most %d)" % (name, size, FRAME_BYTES)


TESTS = [welcome_offers_the_demo, demo_is_served_safely, demo_never_autoplays, missing_demo_hides_the_block,
         poster_uses_the_kit_palette, frames_use_the_kit_palette, captions_match_the_scenes, media_is_not_heavier]


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    ROOT = args.package.resolve()
    failed = skipped = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-tutorial-"))
        started = time.monotonic()
        try:
            test(ROOT, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Skip as why:
            skipped += 1
            print("SKIP %s (%s)" % (test.__name__, why))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            frame = traceback.extract_tb(exc.__traceback__)[-1]
            print("FAIL %s (%s: %s) line %s" % (test.__name__, type(exc).__name__, str(exc)[:1500], frame.lineno))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_TUTORIAL_RESULT %s failed=%d skipped=%d" % ("PASS" if not failed else "FAIL", failed, skipped))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
