#!/usr/bin/env python3
"""UI-017: the welcome screen of the local setup page offers the demo video that UI-016 ships in .uak/media/.
Evidence: Dylan, 2026-11-13: "the landing of the kit is the interface it opens"; novices in the test rounds did not know
which steps happen in the page, in a terminal or by the agents.
The server serves four fixed names from the engine's own kit (never a path from the request), with the page's Host
check, nosniff, the right Content-Type and HTTP Range so the browser can seek. The page never autoplays and hides the
block when the files are missing. Fixtures: a copy of bin/lib with tiny media files in a temporary folder."""
import argparse
import http.client
import importlib.util
import json
import os
import re
import shutil
import tempfile
import threading
import time
import traceback
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


TESTS = [welcome_offers_the_demo, demo_is_served_safely, demo_never_autoplays, missing_demo_hides_the_block]


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    ROOT = args.package.resolve()
    failed = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-tutorial-"))
        started = time.monotonic()
        try:
            test(ROOT, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            frame = traceback.extract_tb(exc.__traceback__)[-1]
            print("FAIL %s (%s: %s) line %s" % (test.__name__, type(exc).__name__, str(exc)[:1500], frame.lineno))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_TUTORIAL_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
