#!/usr/bin/env python3
"""design-gallery --round R<k> (uak design pick): one offline page with every variant of a design round at 1280 and
390, its genome under it, keyboard picking, notes, and Save -> R<k>/picks.json through a tiny local server.

    bash .uak/bin/uak design-gallery --round R<k> [--k 3] [--no-open] [--port N] | --round R<k> --stop

The server binds 127.0.0.1 and the Tailscale address (100.x) only, never 0.0.0.0 or the LAN, refuses a foreign Host
header (DNS rebinding) and only writes R<k>/picks.json: {picked: [ids in order], notes: {id: text}, by, at}.
The page makes no network request but to its own server. The server runs in the background; over SSH (or --no-open)
the command prints the URLs and returns, like design-gallery --serve.
Why (F0, Nov 11 2026): the human picks designs by looking, and the pick has to reach the next round as data, not as
a sentence typed into a chat. Python 3.8+ standard library only."""
import functools
import html
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design_metrics  # noqa: E402
import design_taste  # noqa: E402
from design_round import GENES, project_root, qa_warnings, read_qa  # noqa: E402

DEFAULT_K = 3
FIRST_PORT = 8791
MAX_NOTE = 400


def tailscale_ip():
    """The machine's tailnet IPv4 (100.x) or None: the only non-loopback address the server may use."""
    exe = shutil.which("tailscale")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True, timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return out[0] if out and re.match(r"^100\.\d+\.\d+\.\d+$", out[0]) else None


def bind_addresses():
    ts = tailscale_ip()
    return ["127.0.0.1"] + ([ts] if ts else [])


def load_variants(rnd):
    vs = []
    for v in sorted((p for p in rnd.iterdir() if p.is_dir() and re.match(r"^v\d+$", p.name)), key=lambda p: int(p.name[1:])):
        try:
            g = json.loads((v / "genome.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            g = {}
        vs.append({"id": v.name, "genes": g.get("genes", {}), "recipe": g.get("recipe", ""),
                   "has1280": (v / "1280.png").is_file(), "has390": (v / "390.png").is_file(),
                   "has1280full": (v / "1280-full.png").is_file(), "has390full": (v / "390-full.png").is_file(),
                   "hasIndex": (v / "index.html").is_file(), "has1920": (v / "1920.png").is_file(),
                   "has1920full": (v / "1920-full.png").is_file(), "qa": qa_warnings(read_qa(v)), "metrics": design_metrics.variant_view(rnd, v.name)})
    return vs


def load_picks(rnd):
    try:
        d = json.loads((rnd / "picks.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


CSS = """
:root { --wall: #c9ccc6; --wall-2: #bfc3bc; --mat: #fbfbf9; --ink: #1d1f1c; --ink-2: #4e534c; --rule: #a9aea6; --mark: #d63a2f; --on-mark: #fbfbf9;
  --ok: #1f6b3a; --hang: 0 2px 3px rgb(30 32 28 / .18), 0 18px 34px -12px rgb(30 32 28 / .45); }
@media (prefers-color-scheme: dark) { :root { --wall: #33363a; --wall-2: #2c2f33; --mat: #f4f3ef; --ink: #ecebe6; --ink-2: #b4b5ae; --rule: #55595e;
  --mark: #ff5a4c; --on-mark: #1d1f1c; --ok: #6fd392; --hang: 0 2px 3px rgb(0 0 0 / .4), 0 22px 40px -14px rgb(0 0 0 / .7); } }
* { box-sizing: border-box; margin: 0; }
html { background: var(--wall); }
body { min-height: 100vh; color: var(--ink); font: 400 16px/1.5 "Avenir Next", Avenir, "Segoe UI", system-ui, sans-serif;
  background: radial-gradient(120% 70% at 50% 0%, var(--wall) 40%, var(--wall-2) 100%); padding: 24px clamp(16px, 4vw, 56px) 96px; }
main { max-width: 1480px; margin: 0 auto; }
.bar { position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 8px 24px; align-items: center; padding: 14px 0; background: var(--wall); border-bottom: 1px solid var(--rule); }
h1 { font-size: 24px; font-weight: 600; letter-spacing: -0.02em; margin-right: auto; }
h1 em { font-style: normal; color: var(--ink-2); font-weight: 400; }
.count { color: var(--ink-2); }
.count.warn { color: var(--mark); font-weight: 600; }
button, input { font: inherit; color: var(--ink); }
button { background: var(--ink); color: var(--wall); border: 0; border-radius: 6px; padding: 10px 22px; min-height: 44px; cursor: pointer; font-weight: 600; }
.status { min-width: 12ch; }
.status.ok { color: var(--ok); font-weight: 600; }
.status.bad { color: var(--mark); font-weight: 600; }
.help { color: var(--ink-2); font-size: 14px; padding: 12px 0 0; }
.room { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); gap: 56px 48px; margin-top: 32px; align-items: start; }
.card { display: grid; gap: 14px; padding: 12px; border-radius: 8px; outline-offset: 2px; }
.card:focus-visible { outline: 3px solid var(--ink); }
.card.picked { outline: 3px solid var(--mark); }
.wall { position: relative; padding-bottom: 34px; }
.desk, .phone { display: block; background: var(--mat); padding: 10px; box-shadow: var(--hang); }
.desk img, .phone img { display: block; width: 100%; height: auto; }
.full .desk, .full .phone { max-height: 85vh; overflow: auto; }
.qa { list-style: none; font-size: 13px; color: var(--mark); display: grid; gap: 2px; }
.cost { font-size: 13px; color: var(--ink-2); }
.totals { font-size: 14px; color: var(--ink); padding-top: 8px; }
.live { font-size: 14px; color: var(--ink-2); }
.live a { color: var(--ink); }
.view { display: flex; align-items: center; gap: 8px; color: var(--ink-2); font-size: 14px; }
.phone { position: absolute; right: -8px; bottom: 0; width: 21%; min-width: 84px; padding: 5px; border-radius: 4px; }
.missing { display: grid; place-items: center; min-height: 160px; color: var(--ink-2); background: var(--mat); text-align: center; padding: 12px; font-size: 14px; }
.head { display: flex; align-items: center; gap: 12px; }
.plate { font: 600 15px/1 ui-monospace, Menlo, Consolas, monospace; border: 1px solid var(--rule); min-width: 44px; height: 34px; display: grid; place-items: center; padding: 0 6px; }
.badge { display: none; width: 34px; height: 34px; border-radius: 50%; background: var(--mark); color: var(--on-mark); place-items: center; font-weight: 700; }
.picked .badge { display: grid; }
.recipe { color: var(--ink-2); font-size: 14px; }
dl.genes { display: grid; grid-template-columns: auto 1fr; gap: 2px 14px; font-size: 14px; }
dt { color: var(--ink-2); }
dd { margin: 0; }
.note { width: 100%; background: var(--mat); border: 1px solid var(--rule); border-radius: 6px; padding: 8px 10px; min-height: 40px; color: var(--ink); }
label.n { font-size: 14px; color: var(--ink-2); display: grid; gap: 4px; }
.pick-btn { background: transparent; color: var(--ink); border: 1px solid var(--ink); }
.picked .pick-btn { background: var(--mark); color: var(--on-mark); border-color: var(--mark); }
"""

JS = """
(function () {
  var init = JSON.parse(document.getElementById('init').textContent);
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var order = init.picked.filter(function (id) { return init.ids.indexOf(id) >= 0; });
  var cur = 0, saving = false;
  var count = document.getElementById('count'), status = document.getElementById('status'), by = document.getElementById('by');
  function render() {
    cards.forEach(function (c) {
      var i = order.indexOf(c.dataset.id), on = i >= 0;
      c.classList.toggle('picked', on);
      c.querySelector('.badge').textContent = on ? String(i + 1) : '';
      c.querySelector('.pick-btn').textContent = on ? 'Picked (' + (i + 1) + ') - remove' : 'Pick';
      c.querySelector('.pick-btn').setAttribute('aria-pressed', on ? 'true' : 'false');
      c.querySelector('label.n span').textContent = on ? 'Why this one (one line)' : 'Note (optional)';
    });
    var n = order.length;
    count.textContent = 'Picked ' + n + ' of ' + init.k + (n === init.k ? '' : ' - you can save anyway');
    count.classList.toggle('warn', n !== init.k);
  }
  function dirty() { status.textContent = 'Not saved yet'; status.className = 'status'; }
  function toggle(id) {
    var i = order.indexOf(id);
    if (i >= 0) order.splice(i, 1); else order.push(id);
    render(); dirty();
  }
  function focusCard(i) { cur = Math.max(0, Math.min(cards.length - 1, i)); cards[cur].focus(); cards[cur].scrollIntoView({block: 'nearest'}); }
  function save() {
    if (saving) return;
    saving = true; status.textContent = 'Saving...'; status.className = 'status';
    var notes = {};
    cards.forEach(function (c) { var t = c.querySelector('.note').value.trim(); if (t) notes[c.dataset.id] = t; });
    fetch('save', {method: 'POST', headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify({picked: order, notes: notes, by: by.value.trim()})})
      .then(function (r) { return r.json().then(function (j) { return {ok: r.ok && j.ok, j: j}; }); })
      .then(function (x) {
        saving = false;
        if (x.ok) { status.textContent = 'Saved' + (x.j.warn ? ' (' + x.j.warn + ')' : '') + (x.j.taste ? ' - ' + x.j.taste : '') + (x.j.taste_error ? ' - ' + x.j.taste_error : ''); status.className = x.j.taste_error ? 'status bad' : 'status ok'; }
        else { status.textContent = 'Not saved: ' + (x.j.error || 'refused'); status.className = 'status bad'; }
      })
      .catch(function () { saving = false; status.textContent = 'Not saved: open this page through the command\\'s URL, not as a file'; status.className = 'status bad'; });
  }
  cards.forEach(function (c, i) {
    c.querySelector('.pick-btn').addEventListener('click', function () { cur = i; toggle(c.dataset.id); });
    c.querySelector('.note').addEventListener('input', dirty);
    c.addEventListener('focus', function () { cur = i; });
  });
  by.addEventListener('input', dirty);
  document.getElementById('full').addEventListener('change', function (ev) {  // the fold by default, the whole page on the toggle
    var on = ev.target.checked;
    document.body.classList.toggle('full', on);
    Array.prototype.forEach.call(document.querySelectorAll('img[data-fold]'), function (im) { im.src = on ? im.dataset.full : im.dataset.fold; });
  });
  document.getElementById('save').addEventListener('click', save);
  document.addEventListener('keydown', function (ev) {
    var t = ev.target && ev.target.tagName;
    if (t === 'INPUT' || t === 'TEXTAREA' || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var k = ev.key;
    if (k === 'ArrowRight' || k === 'ArrowDown') { ev.preventDefault(); focusCard(cur + 1); }
    else if (k === 'ArrowLeft' || k === 'ArrowUp') { ev.preventDefault(); focusCard(cur - 1); }
    else if (k === ' ' || ev.code === 'Space') { if (t === 'BUTTON') return; ev.preventDefault(); toggle(cards[cur].dataset.id); }
    else if (/^[1-9]$/.test(k) && cards[+k - 1]) { focusCard(+k - 1); toggle(cards[+k - 1].dataset.id); }
    else if (k === 's' || k === 'S') { ev.preventDefault(); save(); }
  });
  render();
  if (cards.length) cards[0].setAttribute('tabindex', '0');
})();
"""


def default_name(prior):
    """The name field: what the last save typed, else UAK_HUMAN, else git user.name (the CLI's own default, so the page and
    the command fill the same profile), else the account name."""
    who = str(prior.get("by", "") or "").strip() or os.environ.get("UAK_HUMAN", "").strip()
    if not who:
        try:
            who = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        except OSError:
            who = ""
    return who or os.environ.get("UAK_AGENT", "") or os.environ.get("USER", "")


def build_page(rnd, name, k, project):
    vs = load_variants(rnd)
    prior = load_picks(rnd)
    notes = prior.get("notes") if isinstance(prior.get("notes"), dict) else {}
    esc = html.escape
    cards = []
    for v in vs:
        i = v["id"]
        # the projector first: the 1920 shot is the main picture when the capture made one, 1280 otherwise
        big, bigfull = ("1920", "1920-full") if v["has1920"] else ("1280", "1280-full")
        desk = ('<a class="desk" href="%s/%s.png" target="_blank"><img src="%s/%s.png" data-fold="%s/%s.png" data-full="%s" alt="%s at %s wide"></a>'
                % (i, big, i, big, i, big, "%s/%s.png" % (i, bigfull if v["has1920full" if v["has1920"] else "has1280full"] else big), i, big)
                if (v["has1920"] or v["has1280"]) else '<div class="missing">1280 capture missing<br>bash .uak/bin/uak design shoot %s</div>' % esc(name))
        phone = ('<a class="phone" href="%s/390.png" target="_blank"><img src="%s/390.png" data-fold="%s/390.png" data-full="%s" alt="%s at 390 wide"></a>' % (i, i, i, i + "/390-full.png" if v["has390full"] else i + "/390.png", i)) if v["has390"] else ""
        live = ('<p class="live"><a href="%s/index.html" target="_blank" rel="noopener">Open the live page</a> (this server, %s/index.html)</p>' % (i, i)
                if v["hasIndex"] else "")
        m = v["metrics"]
        cost = ""
        if m:
            cost = '<p class="cost">tokens %s &middot; %s &middot; %s</p>' % (
                design_metrics.fmt_tokens(m["tokens"]) if m["tokens"] else "not reported",
                "%.1f min" % (m["seconds"] / 60.0) if m["seconds"] is not None else "minutes n/a",
                "%d look-and-fix passes" % m["passes"] if m["passes"] is not None else "passes n/a")
        live = cost + live
        qa = ('<ul class="qa">%s</ul>' % "".join("<li>%s: %s</li>" % (esc(str(vp)), esc(t)) for vp, t in v["qa"])) if v["qa"] else ""
        genes = "".join("<dt>%s</dt><dd>%s</dd>" % (esc(g), esc(str(v["genes"].get(g, "-")))) for g in GENES)
        cards.append(
            '<article class="card" tabindex="-1" data-id="%s"><div class="wall">%s%s</div>'
            '<div class="head"><span class="plate">%s</span><span class="badge" aria-hidden="true"></span><span class="recipe">recipe %s</span></div>'
            '%s%s<dl class="genes">%s</dl><button type="button" class="pick-btn" aria-pressed="false">Pick</button>'
            '<label class="n"><span>Note (optional)</span><input class="note" type="text" maxlength="%d" value="%s"></label></article>'
            % (i, desk, phone, i, esc(v["recipe"] or "-"), live, qa, genes, MAX_NOTE, esc(str(notes.get(i, "")))))
    sm = design_metrics.round_summary(rnd)
    totals = ""
    if sm["rows"]:
        totals = '<p class="totals">Round cost: %s &middot; %s wall in parallel (longest variant)%s</p>\n' % (
            "%s tokens" % design_metrics.fmt_tokens(sm["tokens"]) + ("" if sm["reported"] == sm["n"] else " (%d of %d variants reported)" % (sm["reported"], sm["n"])) if sm["tokens"] else "tokens not reported",
            "%.1f min" % (sm["wall"] / 60.0) if sm["wall"] is not None else "minutes n/a",
            " &middot; %s per picked variant" % design_metrics.fmt_tokens(sm["per_picked"]) if sm["per_picked"] else "")
    init = json.dumps({"ids": [v["id"] for v in vs], "picked": prior.get("picked", []) if isinstance(prior.get("picked"), list) else [], "k": k}).replace("</", "<\\/")
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>Pick · %s %s</title><style>%s</style></head><body><main>\n"
            "<div class=\"bar\"><h1>%s <em>· %s</em></h1><span id=\"count\" class=\"count\"></span>"
            "<label class=\"n\"><span>Your name</span><input id=\"by\" class=\"note\" type=\"text\" list=\"names\" autocomplete=\"off\" value=\"%s\"><datalist id=\"names\">%s</datalist></label>"
            "<label class=\"view\"><input type=\"checkbox\" id=\"full\">Full page</label>"
            "<span id=\"status\" class=\"status\" role=\"status\"></span><button type=\"button\" id=\"save\">Save picks</button></div>\n"
            "<p class=\"help\">Keys: <b>1-9</b> pick that variant, <b>arrows</b> move, <b>space</b> picks the focused one, <b>s</b> saves. "
            "Pick in order of preference; the first is your favorite. Choose by looking.</p>\n%s"
            "<section class=\"room\">%s</section></main>\n<script type=\"application/json\" id=\"init\">%s</script>\n<script>%s</script></body></html>\n"
            % (esc(project), esc(name), CSS, esc(project), esc(name), esc(default_name(prior)), "".join('<option value="%s">' % esc(n) for n in design_taste.profile_names()),
               totals, "".join(cards), init, JS))


def save_picks(rnd, data, k):
    """Validate and write picks.json; returns (status, body)."""
    ids = [v["id"] for v in load_variants(rnd)]
    if not isinstance(data, dict) or not isinstance(data.get("picked"), list):
        return 400, {"ok": False, "error": "picked must be a list"}
    picked = data["picked"]
    if not all(isinstance(x, str) and x in ids for x in picked) or len(set(picked)) != len(picked):
        return 400, {"ok": False, "error": "unknown or repeated variant in picked"}
    raw = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    notes = {i: str(t).strip()[:MAX_NOTE] for i, t in raw.items() if i in ids and str(t).strip()}
    doc = {"picked": picked, "notes": notes, "by": str(data.get("by") or "")[:80],
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    fd, tmp = tempfile.mkstemp(prefix=".picks-", dir=str(rnd))
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, str(rnd / "picks.json"))  # a second save replaces the first, never half of it
    warn = "" if len(picked) == k else "picked %d, K is %d" % (len(picked), k)
    body = {"ok": True, "warn": warn}
    # Why (v6.2, the human): the kit learns what the human likes from every save, right away. A failure to write the
    # profile never fails the save: picks.json is already on disk; the page says the profile was not updated.
    try:
        import design_taste
        who = doc["by"].strip() or design_taste.default_human()
        prof = design_taste.update(rnd.parents[3], who)
        body["taste"] = "taste profile of %s updated (%d picks, confidence: %s)" % (who, design_taste.pick_count(prof), design_taste.confidence(prof))
    except Exception as exc:  # noqa: BLE001
        body["taste_error"] = "taste profile not updated: %s" % str(exc)[:200]
    return 200, body


def make_handler(rnd, k, hosts):
    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _host_ok(self):
            return (self.headers.get("Host") or "") in hosts

        def _json(self, code, body):
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = unquote(self.path.split("?", 1)[0].split("#", 1)[0])  # decode first: /%2epick.pid is /.pick.pid
            if not self._host_ok():
                return self.send_error(403, "foreign Host")
            parts = path.replace("\\", "/").split("/")
            if any(p.startswith(".") or p == ".." for p in parts) or "\x00" in path or (path.endswith("/") and path != "/"):
                return self.send_error(404)
            real = os.path.realpath(os.path.join(str(rnd), *[p for p in parts if p]))
            if path != "/" and not (real == os.path.realpath(str(rnd)) or real.startswith(os.path.realpath(str(rnd)) + os.sep)):
                return self.send_error(404)
            if path == "/":
                self.path = "/pick.html"
            return super().do_GET()

        def do_POST(self):
            if not self._host_ok():
                return self._json(403, {"ok": False, "error": "foreign Host"})
            if self.path.split("?", 1)[0] != "/save":
                return self._json(404, {"ok": False, "error": "not found"})
            # Why (kit-r1 review, Nov 11 2026): a text/plain cross-origin form POST needs no preflight; require JSON
            # and, when the browser names an Origin, that it is this very server.
            origin = self.headers.get("Origin")
            if origin is not None and origin.split("://", 1)[-1] not in hosts:
                return self._json(403, {"ok": False, "error": "foreign Origin"})
            if (self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                return self._json(415, {"ok": False, "error": "Content-Type must be application/json"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 200000:
                    return self._json(413, {"ok": False, "error": "too large"})
                data = json.loads(self.rfile.read(n).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"ok": False, "error": "bad JSON"})
            try:
                code, body = save_picks(rnd, data, k)
            except OSError as exc:
                code, body = 500, {"ok": False, "error": "could not write picks.json: %s" % exc}
            self._json(code, body)
    return H


def serve_foreground(rnd, name, k, port, project):
    (rnd / "pick.html").write_text(build_page(rnd, name, k, project), encoding="utf-8", newline="\n")
    addrs = bind_addresses()
    for p in range(port, port + 20):
        servers, bound = [], []
        hosts = {"127.0.0.1:%d" % p, "localhost:%d" % p} | {"%s:%d" % (a, p) for a in addrs}
        handler = functools.partial(make_handler(rnd, k, hosts), directory=str(rnd))
        for a in addrs:
            try:
                servers.append(http.server.ThreadingHTTPServer((a, p), handler))
                bound.append(a)
            except OSError:
                if a == "127.0.0.1":
                    break  # loopback is the one that must work; try the next port
        if bound and bound[0] == "127.0.0.1":
            break
        for s in servers:
            s.server_close()
    else:
        sys.exit("no free port from %d" % port)
    for a in bound:
        print("BIND", a, flush=True)
    print("PORT", p, flush=True)
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    servers[0].serve_forever()


def stop(rnd):
    pidf = rnd / ".pick.pid"
    try:
        pid = int(pidf.read_text().strip())
        os.kill(pid, 15)
        print("DESIGN_PICK stopped (pid %d)" % pid)
    except (OSError, ValueError):
        print("DESIGN_PICK: no server running for %s" % rnd.name)
    try:
        pidf.unlink()
    except OSError:
        pass
    return 0


def main(argv):
    name, k, port, no_open, do_stop, fg = None, DEFAULT_K, FIRST_PORT, False, False, False
    it = iter(argv)
    try:
        for a in it:
            if a == "--round":
                name = next(it)
            elif a == "--k":
                k = int(next(it))
            elif a == "--port":
                port = int(next(it))
            elif a == "--no-open":
                no_open = True
            elif a == "--stop":
                do_stop = True
            elif a == "--serve-foreground":
                fg = True
            elif a == "--serve":
                pass
            else:
                raise ValueError(a)
    except (StopIteration, ValueError):
        print("Usage: design-gallery --round R<k> [--k 3] [--no-open] [--port N] | --round R<k> --stop", file=sys.stderr)
        return 2
    if not name or not re.match(r"^R\d+$", name) or k < 1:
        print("Usage: design-gallery --round R<k> [--k 3] [--no-open] [--stop]", file=sys.stderr)
        return 2
    root = project_root()
    rnd = root / ".uak" / "design" / "rounds" / name
    if not rnd.is_dir():
        print("DESIGN_PICK: no round %s (expected %s; make one with: bash .uak/bin/uak design round)" % (name, rnd), file=sys.stderr)
        return 1
    if do_stop:
        return stop(rnd)
    project = root.name
    if fg:
        serve_foreground(rnd, name, k, port, project)
        return 0
    vs = load_variants(rnd)
    if not vs:
        print("DESIGN_PICK: %s has no variants" % name, file=sys.stderr)
        return 1
    stop(rnd)
    log = rnd / ".pick.log"
    try:
        log.unlink()
    except OSError:
        pass
    kw = {"creationflags": 0x00000008 | 0x00000200} if os.name == "nt" else {"start_new_session": True}
    with open(str(log), "wb") as lf:
        proc = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--round", name, "--k", str(k), "--port", str(port), "--serve-foreground"],
                                cwd=str(root), stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
    (rnd / ".pick.pid").write_text("%d\n" % proc.pid)
    got, binds = None, []
    for _ in range(400):  # up to 40 s: a cold Python on a loaded runner bound late (design-gallery, CI Oct 2026)
        txt = log.read_text(errors="replace") if log.exists() else ""
        binds = re.findall(r"^BIND (\S+)", txt, re.M)
        m = re.search(r"^PORT (\d+)", txt, re.M)
        if m:
            got = int(m.group(1))
            break
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if not got:
        print("DESIGN_PICK: the server did not start: %s" % (log.read_text(errors="replace").strip().splitlines() or ["?"])[-1], file=sys.stderr)
        return 1
    print("DESIGN_PICK %s · %d variants · K=%d · http://127.0.0.1:%d/pick.html" % (name, len(vs), k, got))
    for a in binds[1:]:
        print("DESIGN_PICK open on your laptop (Tailscale): http://%s:%d/pick.html" % (a, got))
    try:
        host = os.uname().nodename
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
    except AttributeError:
        host, user = os.environ.get("COMPUTERNAME", "host"), os.environ.get("USERNAME", "user")
    print("DESIGN_PICK or tunnel it: ssh -L %d:127.0.0.1:%d %s@%s, then http://localhost:%d/pick.html (VS Code Remote forwards the port itself)" % (got, got, user, host, got))
    print("DESIGN_PICK saves to %s; serving in the background (pid %d); stop it: bash .uak/bin/uak design-gallery --round %s --stop" % (rnd / "picks.json", proc.pid, name))
    over_ssh = bool(os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"))
    if not no_open and os.environ.get("UAK_NO_OPEN") != "1" and not over_ssh:
        url = "http://127.0.0.1:%d/pick.html" % got
        if sys.platform == "darwin":
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            os.startfile(url)  # noqa: S606
        elif (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print("DESIGN_PICK: no display here; open the URL above in a browser")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
