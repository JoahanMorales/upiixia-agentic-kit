#!/usr/bin/env python3
"""UAK-058: `design-gallery --round R<k>` (uak design pick) hangs a round's variants on one offline page, picks by keyboard,
and saves R<k>/picks.json through a tiny server bound to 127.0.0.1 (+ the Tailscale address when there is one). Real
subprocesses and sockets on loopback; no real network, browser or Tailscale (a fake `tailscale` on PATH)."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from test_hack import expect, resolve_binary

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000" "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
GENES = {"type": "grotesk", "scale": "bold", "color": "dark media", "layout": "split hero", "components": "glass",
         "imagery": "video loop", "motion": "entrance", "voice": "plain"}


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = Path(package) / ".uak"  # the candidate under test (smoke passes --package), not this worktree
        self.tool = self.pkg / "bin" / "design-gallery"

    def project(self, name, n=3):
        d = self.tmp / name
        rnd = d / ".uak/design/rounds/R1"
        for i in range(1, n + 1):
            v = rnd / ("v%d" % i)
            v.mkdir(parents=True)
            (v / "1280.png").write_bytes(PNG)
            (v / "390.png").write_bytes(PNG)
            g = dict(GENES, layout=["split hero", "scroll story", "editorial column"][i % 3], type="serif display" if i == 2 else "grotesk")
            (v / "genome.json").write_text(json.dumps({"id": "R1-v%d" % i, "variant": i, "genes": g, "recipe": "landing-story"}), encoding="utf-8")
        return d

    def run(self, cwd, *args, path_extra=None):
        env = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester")
        for k in ("SSH_CONNECTION", "SSH_TTY"):
            env.pop(k, None)
        if path_extra:
            env["PATH"] = str(path_extra) + os.pathsep + env["PATH"]
        return subprocess.run([self.bash, str(self.tool)] + list(args), cwd=str(cwd), env=env, capture_output=True, text=True, timeout=90)

    def start(self, d, *extra, path_extra=None):
        out = self.run(d, "--round", "R1", "--no-open", *extra, path_extra=path_extra)
        expect(out.returncode == 0, "start rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        m = re.search(r"http://127\.0\.0\.1:(\d+)/", out.stdout)
        expect(m, "prints the local URL: " + out.stdout)
        return int(m.group(1)), out.stdout

    def stop(self, d):
        self.run(d, "--round", "R1", "--stop")


def post(port, body, host=None, raw=None):
    req = urllib.request.Request("http://127.0.0.1:%d/save" % port, data=raw if raw is not None else json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def pick_page_lists_every_variant(e):
    d = e.project("pg", n=4)
    port, out = e.start(d)
    try:
        page = (d / ".uak/design/rounds/R1/pick.html").read_text(encoding="utf-8")
        for i in range(1, 5):
            for needle in ('v%d/1280.png' % i, 'v%d/390.png' % i):
                expect(needle in page, "page shows %s" % needle)
        expect("serif display" in page and "split hero" in page and "landing-story" in page, "genome shown under each variant")
        expect(not re.search(r"""(src|href)=["']https?://|@import|<link[^>]+stylesheet|url\(\s*["']?https?:""", page), "no network references")
        expect("keydown" in page and "ArrowRight" in page and "'Space'" in page.replace('" "', "'Space'") or "' '" in page or '" "' in page, "keyboard picking")
        expect(">Saved<" not in page, "Saved is never in the static page: it appears after the server answers")
        with urllib.request.urlopen("http://127.0.0.1:%d/pick.html" % port, timeout=10) as r:
            expect(r.status == 200 and "v4/1280.png" in r.read().decode("utf-8"), "the server serves the page")
        with urllib.request.urlopen("http://127.0.0.1:%d/v1/390.png" % port, timeout=10) as r:
            expect(r.read() == PNG, "and the PNGs")
    finally:
        e.stop(d)
    return "4 variants on the page"


def save_writes_picks_json(e):
    d = e.project("sv")
    port, _ = e.start(d)
    try:
        st, res = post(port, {"picked": ["v2", "v1"], "notes": {"v2": "the type carries it", "v3": "maybe the layout"}, "by": "ana"})
        expect(st == 200 and res.get("ok") is True, "saved: %s %s" % (st, res))
        f = d / ".uak/design/rounds/R1/picks.json"
        got = json.loads(f.read_text(encoding="utf-8"))
        expect(got["picked"] == ["v2", "v1"] and got["notes"]["v2"] == "the type carries it" and got["by"] == "ana" and got["at"], "picks.json: %s" % got)
        expect(set(got) == {"picked", "notes", "by", "at"}, "exact shape: %s" % list(got))
        st, _ = post(port, {"picked": ["v3"], "notes": {}})
        expect(json.loads(f.read_text(encoding="utf-8"))["picked"] == ["v3"], "a second save replaces the first")
        st, _ = post(port, {"picked": ["v9"], "notes": {}})
        expect(st == 400 and json.loads(f.read_text(encoding="utf-8"))["picked"] == ["v3"], "an unknown id is refused and changes nothing")
        st, _ = post(port, None, raw=b"not json")
        expect(st == 400, "bad JSON refused")
        again = (d / ".uak/design/rounds/R1/pick.html")
        e.stop(d)
        port2, _ = e.start(d)
        with urllib.request.urlopen("http://127.0.0.1:%d/pick.html" % port2, timeout=10) as r:
            expect('"v3"' in r.read().decode("utf-8"), "reopening shows the saved pick")
    finally:
        e.stop(d)
    return "picks.json written, replaced, validated"


def wrong_count_warns_but_saves(e):
    d = e.project("wc")
    port, _ = e.start(d, "--k", "3")
    try:
        st, res = post(port, {"picked": ["v1", "v2"], "notes": {}})
        expect(st == 200 and res.get("ok") and res.get("warn") and "3" in res["warn"] and "2" in res["warn"], "warns about 2 of 3: %s" % res)
        expect(json.loads((d / ".uak/design/rounds/R1/picks.json").read_text(encoding="utf-8"))["picked"] == ["v1", "v2"], "saved anyway")
        st, res = post(port, {"picked": ["v1", "v2", "v3"], "notes": {}})
        expect(st == 200 and not res.get("warn"), "no warning at exactly K: %s" % res)
    finally:
        e.stop(d)
    return "warns, saves"


def server_binds_local_only(e):
    sys.path.insert(0, str(e.pkg / "bin" / "lib"))
    import gallery_pick as gp
    fake = e.tmp / "fakebin"
    fake.mkdir(exist_ok=True)
    for ip, name in (("192.168.1.5", "lan"), ("0.0.0.0", "any"), ("100.64.0.9", "ts")):
        sub = fake / name
        sub.mkdir(exist_ok=True)
        if os.name == "nt":  # Windows runs no #!/bin/sh file; shutil.which finds a .cmd through PATHEXT
            (sub / "tailscale.cmd").write_text("@echo %s\r\n" % ip, encoding="utf-8")
        else:
            (sub / "tailscale").write_text("#!/bin/sh\necho %s\n" % ip, encoding="utf-8")
            (sub / "tailscale").chmod(0o755)
    old = os.environ["PATH"]
    try:
        got = {}
        for name in ("lan", "any", "ts"):
            os.environ["PATH"] = str(fake / name) + os.pathsep + old
            got[name] = gp.bind_addresses()
        (e.tmp / "empty").mkdir(exist_ok=True)
        os.environ["PATH"] = str(e.tmp / "empty")
        got["none"] = gp.bind_addresses()
    finally:
        os.environ["PATH"] = old
    expect(got["lan"] == ["127.0.0.1"] and got["any"] == ["127.0.0.1"] and got["none"] == ["127.0.0.1"], "only 127.0.0.1 unless a tailnet address: %s" % got)
    expect(got["ts"] == ["127.0.0.1", "100.64.0.9"], "127.0.0.1 + the Tailscale address: %s" % got)
    d = e.project("bl")
    port, out = e.start(d, path_extra=fake / "lan")
    try:
        log = (d / ".uak/design/rounds/R1/.pick.log").read_text(encoding="utf-8")
        binds = re.findall(r"^BIND (\S+)", log, re.M)
        expect(binds == ["127.0.0.1"], "listens on 127.0.0.1 only: %s" % binds)
        expect("0.0.0.0" not in log and "192.168" not in out, "never the LAN")
        st, _ = post(port, {"picked": ["v1"], "notes": {}}, host="evil.example:%d" % port)
        expect(st == 403, "a foreign Host header (DNS rebinding) is refused, got %s" % st)
    finally:
        e.stop(d)
    return "loopback only"


def raw_request(port, method, path, headers, body=b""):
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.putrequest(method, path, skip_host=("Host" in headers))
    for k, v in dict(headers, **{"Content-Length": str(len(body))}).items():
        c.putheader(k, v)
    c.endheaders(body)
    r = c.getresponse()
    out = (r.status, r.read())
    c.close()
    return out


def encoded_dotfile_is_refused(e):
    d = e.project("df")
    port, _ = e.start(d)
    try:
        for path in ("/%2epick.pid", "/%2Epick.log", "/.pick.pid", "/v1/%2e%2e/.pick.pid", "/%2e%2e/%2e%2e/etc/passwd", "/v1/..%2f.pick.pid"):
            st, body = raw_request(port, "GET", path, {"Host": "127.0.0.1:%d" % port})
            expect(st in (400, 404) and b"python" not in body and not body.strip().isdigit(), "%s must be refused, got %s %r" % (path, st, body[:40]))
        st, _ = raw_request(port, "GET", "/v1/1280.png", {"Host": "127.0.0.1:%d" % port})
        expect(st == 200, "a real PNG still served")
    finally:
        e.stop(d)
    return "encoded dotfiles 404"


def cross_origin_save_is_refused(e):
    d = e.project("co")
    port, _ = e.start(d)
    try:
        body = json.dumps({"picked": ["v1"], "notes": {}}).encode("utf-8")
        for origin in ("http://evil.example", "https://127.0.0.1:%d.evil.example" % port, "null"):
            st, _ = raw_request(port, "POST", "/save", {"Host": "127.0.0.1:%d" % port, "Origin": origin, "Content-Type": "text/plain"}, body)
            expect(st in (403, 415), "Origin %s: %s" % (origin, st))
            st, _ = raw_request(port, "POST", "/save", {"Host": "127.0.0.1:%d" % port, "Origin": origin, "Content-Type": "application/json"}, body)
            expect(st == 403, "Origin %s with JSON: %s" % (origin, st))
        expect(not (d / ".uak/design/rounds/R1/picks.json").exists(), "nothing written")
        st, _ = raw_request(port, "POST", "/save", {"Host": "127.0.0.1:%d" % port, "Origin": "http://127.0.0.1:%d" % port, "Content-Type": "application/json"}, body)
        expect(st == 200, "the page's own origin works: %s" % st)
    finally:
        e.stop(d)
    return "foreign Origin 403"


def json_content_type_required(e):
    d = e.project("ct")
    port, _ = e.start(d)
    try:
        body = json.dumps({"picked": ["v1"], "notes": {}}).encode("utf-8")
        for ct in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"):
            st, _ = raw_request(port, "POST", "/save", {"Host": "127.0.0.1:%d" % port, "Content-Type": ct}, body)
            expect(st == 415, "%s refused with 415, got %s" % (ct, st))
        expect(not (d / ".uak/design/rounds/R1/picks.json").exists(), "nothing written")
        st, _ = raw_request(port, "POST", "/save", {"Host": "127.0.0.1:%d" % port, "Content-Type": "application/json; charset=utf-8"}, body)
        expect(st == 200, "json with a charset is fine")
    finally:
        e.stop(d)
    return "415 unless JSON"


TESTS = [encoded_dotfile_is_refused, cross_origin_save_is_refused, json_content_type_required, pick_page_lists_every_variant, save_writes_picks_json, wrong_count_warns_but_saves, server_binds_local_only]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-pick-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_PICK_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
