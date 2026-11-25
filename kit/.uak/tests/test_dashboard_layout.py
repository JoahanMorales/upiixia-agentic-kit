#!/usr/bin/env python3
"""UAK-165: the summary of `uak dash` is made of components the viewer arranges (move, hide, add), kept in their browser per
project; a team may ship a default (`uak dash layout --save` writes .uak/dash/layout.json). Three levels, each a behaviour:
the layout model as pure functions under node (the page's logic section), the page's own script drawn under node against a
stub document with a storage that works, is blocked or is full, and the real page in Chromium (mouse, keyboard, a phone with
touch, reduced motion) when Playwright is installed. A case that needs Chromium and finds none prints `SKIP name (no browser)`
(the convention of UAK-195), never PASS. No network, no server; Git only in a throwaway fixture (always `-C`, no inherited
GIT_* variables)."""
import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import test_dashboard_truth as truth
from test_hack import resolve_binary

# Today's order (the default): what needs the person, the squares, the tasks, who did what; at the side progress, agents,
# integrations per period, tokens (docs/design/DIRECTION.md, rule 7).
ORDER = [("needs", "main"), ("map", "main"), ("tasks", "main"), ("lanes", "main"),
         ("progress", "side"), ("agents", "side"), ("pace", "side"), ("tokens", "side")]
DEF_JS = "var DEF = %s;" % json.dumps([[n, c] for n, c in ORDER])
DEFAULT = {"main": [n for n, c in ORDER if c == "main"], "side": [n for n, c in ORDER if c == "side"], "hide": []}
KEY = "uak-layout:demo"


class NoBrowser(Exception):
    """The case needs Chromium and there is none here."""


# ---------------------------------------------------------------- the page's script under node, with a storage of our own
STUB_EDITS = [
    ("var sandbox = {", "var KEPT = cfg.storage || {}, MODE = cfg.mode || \"ok\";\n"
     "var MEM = { getItem: function (k) { if (MODE === \"blocked\") throw new Error(\"SecurityError\"); return Object.prototype.hasOwnProperty.call(KEPT, k) ? KEPT[k] : null; },\n"
     "  setItem: function (k, v) { if (MODE !== \"ok\") throw new Error(\"QuotaExceededError\"); KEPT[k] = String(v); },\n"
     "  removeItem: function (k) { if (MODE !== \"ok\") throw new Error(\"QuotaExceededError\"); delete KEPT[k]; } };\n"
     "function tree(el) { if (!el || el.nodeType !== 1) return null; return { t: el.tag, a: el.attrs, x: el._text, k: (el.children || []).map(tree).filter(Boolean) }; }\n"
     "var sandbox = {"),
    ("localStorage: store(false),", "localStorage: MEM,"),
    ("sandbox.UAK_TEST_RENDER(run.tab, data)", "sandbox.UAK_TEST_RENDER(run.tab, data, run.ui)"),
    ("r.texts = texts(view, []);", "r.texts = texts(view, []); r.tree = tree(view); r.kept = JSON.parse(JSON.stringify(KEPT)); r.live = document.getElementById(\"arr-live\").textContent;"),
]


def page_load(root, tmp, runs, base=None, storage=None, mode="ok", lang="en"):
    """One load of the page under node: its script runs once, then draws each run (a dict: tab, ui, mutate) in order.
    Returns the runs' results (texts, tree, the storage after it, the live region) or None when node is missing."""
    node = shutil.which("node")
    if not node:
        return None
    js = truth.STUB_JS
    for a, b in STUB_EDITS:
        assert js.count(a) == 1, "the stub of test_dashboard_truth changed: %r" % a
        js = js.replace(a, b)
    text = (root / ".uak/bin/lib/workspace.js").read_text(encoding="utf-8")
    catalog = {json.loads(a): json.loads(b) for a, b in re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)}
    cfg = {"html": str(root / ".uak/bin/lib/dash.html"), "base": base or truth.rich_data(), "runs": runs, "lang": lang, "catalog": catalog,
           "storage": storage or {}, "mode": mode}
    (tmp / "layout-stub.json").write_text(json.dumps(cfg), encoding="utf-8")
    (tmp / "layout-stub.js").write_text(js, encoding="utf-8")
    done = subprocess.run([node, str(tmp / "layout-stub.js"), str(tmp / "layout-stub.json")], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[:1500]
    return json.loads(done.stdout)["results"]


def walk(t):
    yield t
    for k in t.get("k", []):
        yield from walk(k)


def classes(t):
    return (t.get("a") or {}).get("class", "").split()


def columns(tree):
    """{main: [...], side: [...]}: the components drawn in each column, in order (a block section b-NAME or an arrange box)."""
    out = {}
    for t in walk(tree):
        col = (t.get("a") or {}).get("data-col")
        if t["t"] == "div" and col:
            names = []
            for k in t["k"]:
                a = k.get("a") or {}
                if a.get("data-blk"):
                    names.append(a["data-blk"])
                else:
                    names += [c[2:] for c in classes(k) if c.startswith("b-")]
            out[col] = names
    return out


def find(tree, pred):
    return [t for t in walk(tree) if pred(t)]


def text_of(t):
    return (t.get("x") or "") + "".join(text_of(k) for k in t.get("k", []))


def notice(r):
    """The sentences the arrange bar says in a role=status line (empty when it says nothing)."""
    return [text_of(t) for t in find(r["tree"], lambda t: "arrbar" in classes(t)) for t in find(t, lambda x: (x.get("a") or {}).get("role") == "status")]


# ---------------------------------------------------------------- the real page in Chromium
@contextlib.contextmanager
def browser(root, tmp, data, phone=False, reduced=False, lang="en", seed=None):
    """The page from file:// in Chromium. seed: {key: value} written into localStorage before the page's first script, by an
    init script in the page itself. A test never relies on a storage write surviving a reload: Chromium commits localStorage
    to disk asynchronously, and a reload right after a write can read the old value or none (measured: 10 of 200 reloads here,
    and in review the value was gone even after another document had read it). What a reload must carry is passed to the next
    load through window.name (kept by the tab, written at once) and written by that load before its scripts run: see carry().
    Raises NoBrowser without Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise NoBrowser()
    lib = root / ".uak/bin/lib"
    shutil.copy(str(lib / "dash.html"), str(tmp / "index.html"))
    shutil.copy(str(lib / "workspace.js"), str(tmp / "workspace.js"))
    (tmp / "data.js").write_text("window.UAK_DATA = " + json.dumps(data) + ";", encoding="utf-8")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001  (Playwright without its Chromium)
            raise NoBrowser() from exc
        try:
            opts = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True) if phone else dict(viewport={"width": 1280, "height": 900})
            ctx = b.new_context(reduced_motion="reduce" if reduced else "no-preference", **opts)
            first = dict({"uak-dash": json.dumps({"tab": "sum"}), "uak-language": lang}, **(seed or {}))
            ctx.add_init_script("""(function () { try {
              if (!/index\\.html$/.test(location.pathname)) return;
              var m = /^uak-test-carry:([\\s\\S]*)$/.exec(window.name), s = m ? JSON.parse(m[1]) : window.name === 'uak-test-seeded' ? null : %s;
              window.name = 'uak-test-seeded';
              if (s) Object.keys(s).forEach(function (k) { if (s[k] === null) localStorage.removeItem(k); else localStorage.setItem(k, s[k]); }); } catch (e) {} })();""" % json.dumps(first))
            pg = ctx.new_page()
            pg.errors = []
            pg.on("pageerror", lambda e: pg.errors.append(str(e)))
            pg.url0 = "file://" + str(tmp / "index.html")
            pg.goto(pg.url0)
            pg.wait_for_function("document.querySelector('#view .page .col')")
            yield pg
        finally:
            b.close()


def carry(pg, keys, url=None):
    """Reload (or go to URL) with what this document holds under KEYS: read here, where the page wrote it, then written by the
    next load before its scripts run. This tests what a person relies on (the page keeps its choice and honours it on the next
    load) without racing the browser's commit of localStorage to disk. A person who changes something and reloads within that
    commit could see the previous state: that is the browser's flush, not the page (the page writes on every change and reads
    whatever storage gives it at load). Returns the values carried."""
    held = pg.evaluate("(ks) => { const o = {}; ks.forEach(k => { o[k] = localStorage.getItem(k); }); return o; }", keys)
    pg.evaluate("(v) => { window.name = 'uak-test-carry:' + v; }", json.dumps(held))
    if url:
        pg.goto(url)
    else:
        pg.reload()
    pg.wait_for_function("document.querySelector('#view .page .col')")
    return held


def compact(v):
    return json.dumps(v, separators=(",", ":"))   # JSON.stringify's spelling


def layout_in(pg):
    return pg.evaluate("""() => { const o = {}; document.querySelectorAll('#view .col[data-col]').forEach(c => {
      o[c.getAttribute('data-col')] = Array.from(c.children).map(x => x.getAttribute('data-blk') || ((x.className.match(/\\bb-([a-z]+)/) || [])[1]) || '').filter(Boolean); }); return o; }""")


def press(pg, sel, tap=False):
    """Click or tap the middle of SEL with the real pointer. Not locator.click(): in arrange mode the components shake (the one
    under the pointer stops), so Playwright's wait for a stable box never ends, and force=True would skip that wait while the
    page's smooth scroll (html { scroll-behavior: smooth }) is still moving: the click then lands where the button was. Here
    the element is scrolled into view at once (behavior: instant), the page is waited on until it has not scrolled for five
    frames (a smooth scroll started by a focus may still be running), and the element's middle is read after that."""
    x, y = pg.evaluate("""(s) => new Promise(done => { const e = document.querySelector(s); e.scrollIntoView({ block: 'center', behavior: 'instant' });
      let y = scrollY, still = 0; (function frame() { requestAnimationFrame(() => { if (scrollY === y) still++; else { still = 0; y = scrollY; }
        if (still < 5) return frame(); if (e.getBoundingClientRect().bottom < 0 || e.getBoundingClientRect().top > innerHeight) e.scrollIntoView({ block: 'center', behavior: 'instant' });
        const r = e.getBoundingClientRect(); done([r.x + r.width / 2, r.y + r.height / 2]); }); })(); })""", sel)
    pg.touchscreen.tap(x, y) if tap else pg.mouse.click(x, y)


def edit(pg):
    press(pg, '[data-f="arr:edit"]')
    pg.wait_for_function("document.querySelector('.arrbar.on') && document.querySelectorAll('#view .arr').length > 0")


# ---------------------------------------------------------------- the cases
def summary_is_a_list_of_components(root, tmp):
    """Each block of the summary is a component (name, title, column, maximum of rows, one render, a line saying what it shows);
    the summary is a list of names per column whose default is today's order; the page and `uak dash layout` know the same
    components; and the summary never grows with the plan in any position: a 60-task plan with every component in the main
    column, every one in the side column, or the default, never draws more rows than each component's maximum."""
    out = truth.under_node(root, DEF_JS + "return [arrRead(DEF, null), arrRead(DEF, undefined), arrRead(DEF, '')];")
    if out is not None:
        assert out[0] == {"lay": DEFAULT, "note": ""} and out[1] == out[0], "no arrangement is today's order, with no notice: %r" % out[:2]
    dash = (root / ".uak/bin/lib/dash.html").read_text(encoding="utf-8")
    blocks = re.findall(r'\{ name: "([a-z]+)", title: function \(\) \{[^}]*\}, col: "(main|side)", max: [A-Z0-9]+, render: [a-zA-Z]+ \}', dash)
    assert blocks == ORDER, "BLOCKS lists every component with name, title, column, maximum and render, in today's order: %r" % blocks
    about = dash[dash.index("  function about(n) {"):dash.index("  var BLOCKS = [")]
    assert re.findall(r"(\w+): L\('[^']{12,}'\)", about) == [n for n, _ in ORDER], "each component has one line saying what it shows"
    spec = __import__("importlib.util").util.spec_from_file_location("dash_layout_mod", root / ".uak/bin/lib/dash.py")
    mod = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert [list(x) for x in mod.LAYOUT_COMPONENTS] == [list(x) for x in ORDER], "dash.py knows the page's components: %r" % (mod.LAYOUT_COMPONENTS,)
    # drawn: the default, and the rule of the summary in every position
    big = truth.fixture_data(agents=30, tasks=60)
    g = big["generated"]
    for i, t in enumerate(big["tasks"]):
        t["state"] = ["CLAIMED", "REVIEW", "BLOCKED"][i % 3]
        if t["state"] == "REVIEW":
            t["sub"] = {"kind": "waiting", "text": "waiting for a reviewer", "since": g - 600 - i, "late": False, "rounds": 0, "rejects": 0}
    big["agents"] = [dict(a, status="online", last_seen=g - 30) for a in big["agents"]]
    big["offers"] = [{"task": t["id"], "to": ["all"], "since": g - 900 - i, "owner": "kit-0"} for i, t in enumerate(big["tasks"]) if t["state"] == "REVIEW"]
    big["timelines"] = {t["id"]: {"lines": [[g - 3000, "claim", "kit-%d" % (i % 30)], [g - 100, "done", "kit-%d" % (i % 30)]], "agents": []} for i, t in enumerate(big["tasks"])}
    names = [n for n, _ in ORDER]
    arrangements = {"default": None, "all main": {"main": names, "side": [], "hide": []}, "all side": {"main": [], "side": names, "hide": []}}
    for label, arr in arrangements.items():
        res = page_load(root, tmp, [{"name": label, "tab": "sum"}, {"name": label + " arranging", "tab": "sum", "ui": {"arr": True}}], base=big,
                        storage={KEY: json.dumps(arr)} if arr else {})
        if res is None:
            return
        for r in res:
            assert not r["thrown"] and not r["errors"], "%s: %s %s" % (r["name"], r["thrown"], r["errors"])
            cols = columns(r["tree"])
            want = arr or DEFAULT
            drawn = {c: cols.get(c, []) for c in ("main", "side")}
            assert drawn == {"main": want["main"], "side": want["side"]}, "%s: the columns are the arrangement: %r" % (r["name"], drawn)
            rows = {
                "needs": sum(len(x["k"]) for x in find(r["tree"], lambda t: t["t"] == "ul" and "need" in classes(t))),
                "tasks": sum(len(x["k"]) for x in find(r["tree"], lambda t: "rows" in classes(t))),
                "agents": sum(len(x["k"]) for x in find(r["tree"], lambda t: "ppl" in classes(t))),
                "lanes": len(find(r["tree"], lambda t: "lane" in classes(t))),
            }
            assert rows["needs"] <= 7 and rows["tasks"] <= 9 and rows["agents"] <= 5 and rows["lanes"] <= 4, \
                "%s: a list grew with the plan (max + one 'more' row): %r" % (r["name"], rows)
        # Add lists the hidden ones, each with its line; with nothing hidden it says so
        arranging = res[1]
        assert "Every component is shown." in arranging["texts"], "Add says when nothing is hidden: %r" % arranging["texts"][:20]
    res = page_load(root, tmp, [{"name": "hidden", "tab": "sum", "ui": {"arr": True}}], storage={KEY: json.dumps({"main": ["needs"], "side": ["progress"], "hide": [n for n in names if n not in ("needs", "progress")]})})
    adds = find(res[0]["tree"], lambda t: (t.get("a") or {}).get("data-f", "").startswith("add:"))
    assert [t["a"]["data-f"][4:] for t in adds] == [n for n in names if n not in ("needs", "progress")], "Add lists every hidden component"
    for t in adds:
        words = text_of(t)
        assert len(words) > 20, "each one says what it shows: %r" % words


def arrange_mode_shakes_and_respects_reduced_motion(root, tmp):
    """Arranging is unmistakable: every component gets a dashed outline, its handles and a slow shake out of step with its
    neighbours, and one line at the top says what can be done. The component under the pointer or with focus holds still;
    nothing shakes outside the mode; under prefers-reduced-motion nothing moves and the outline, handles and line remain."""
    res = page_load(root, tmp, [{"name": "normal", "tab": "sum"}, {"name": "arranging", "tab": "sum", "ui": {"arr": True}}, {"name": "done", "tab": "sum", "ui": {"arr": False}}])
    if res is not None:
        normal, arr, done = res
        assert not find(normal["tree"], lambda t: "arr" in classes(t)) and not find(done["tree"], lambda t: "arr" in classes(t)), "no arrange box outside the mode"
        boxes = find(arr["tree"], lambda t: "arr" in classes(t))
        assert len(boxes) == len(ORDER), "every component is in an arrange box: %d" % len(boxes)
        delays = [re.search(r"--d:(-?[0-9.]+)s", t["a"].get("style", "")).group(1) for t in boxes]
        assert all(a != b for a, b in zip(delays, delays[1:])), "neighbours shake out of step: %r" % delays
        assert "Move, hide or add components. Done when you finish." in arr["texts"], "the line at the top"
    with browser(root, tmp, truth.rich_data()) as pg:
        anim = "() => Array.from(document.querySelectorAll('#view *')).filter(e => getComputedStyle(e).animationName !== 'none').length"
        assert pg.evaluate(anim) == 0, "nothing shakes before Edit"
        edit(pg)
        st = pg.evaluate("""() => Array.from(document.querySelectorAll('#view .arr')).map(e => { const s = getComputedStyle(e);
          return { n: s.animationName, d: s.animationDelay, dur: parseFloat(s.animationDuration), o: s.outlineStyle, h: e.querySelectorAll('.hbar button').length }; })""")
        assert st and all(x["n"] == "jig" and x["o"] == "dashed" and x["h"] >= 3 and x["dur"] >= 1 for x in st), "each shakes slowly with a dashed outline and handles: %r" % st
        assert all(a["d"] != b["d"] for a, b in zip(st, st[1:])), "out of step: %r" % [x["d"] for x in st]
        deg = pg.evaluate("""() => { const k = Array.from(document.styleSheets).flatMap(s => Array.from(s.cssRules)).find(r => r.name === 'jig');
          return Array.from(k.cssRules).map(r => r.style.transform); }""")
        turn = [float(re.search(r"(-?[0-9.]+)deg", x).group(1)) for x in deg]
        assert 0.6 <= max(turn) - min(turn) <= 1.6, "about one degree in all: %r" % deg
        assert pg.is_visible(".arrbar .tip") and "Move, hide or add components" in pg.inner_text(".arrbar .tip")
        box = pg.locator('#view .arr[data-blk="tasks"] .hbar b').bounding_box()
        pg.mouse.move(box["x"] + 4, box["y"] + box["height"] / 2)
        pg.wait_for_function("getComputedStyle(document.querySelector('#view .arr[data-blk=\"tasks\"]')).animationName === 'none'")
        pg.focus('[data-f="agents:up"]')
        pg.wait_for_function("getComputedStyle(document.querySelector('#view .arr[data-blk=\"agents\"]')).animationName === 'none'")
        press(pg, '[data-f="arr:done"]')
        pg.wait_for_function("!document.querySelector('.arrbar.on')")
        assert pg.evaluate(anim) == 0, "the shake stops with Done"
        assert not pg.errors, pg.errors
    with browser(root, tmp, truth.rich_data(), reduced=True) as pg:
        edit(pg)
        st = pg.evaluate("""() => Array.from(document.querySelectorAll('#view .arr')).map(e => { const s = getComputedStyle(e);
          return { n: s.animationName, t: s.transform, o: s.outlineStyle, h: e.querySelectorAll('.hbar button').length }; })""")
        assert st and all(x["n"] == "none" and x["t"] == "none" and x["o"] == "dashed" and x["h"] >= 3 for x in st), "reduced motion: still, outlined, with handles: %r" % st
        assert pg.evaluate("document.getAnimations().length") == 0 and pg.is_visible(".arrbar .tip")
    return "browser"


def move_hide_and_add_persist_per_viewer(root, tmp):
    """Moving, hiding and adding change the viewer's arrangement only: kept in this browser per project (another project's page
    keeps its own), survives a reload and the page's own reload (?uak=), writes no file; a storage that is blocked or full keeps
    the arrangement for the page's life and says so in one sentence; everything in one column draws one full-width column."""
    body = DEF_JS + """
      var a = arrRead(DEF, null).lay, s = [];
      s.push(arrMove(a, "tasks", -1, false)); s.push(arrMove(a, "needs", -1, false)); s.push(arrMove(a, "lanes", 1, false));
      s.push(arrMove(a, "lanes", 1, true)); s.push(arrMove(a, "progress", -1, true)); s.push(arrMove(a, "map", 0, false));
      s.push(arrHide(a, "tokens")); s.push(arrAdd(DEF, arrHide(arrHide(a, "tokens"), "map"), "map")); s.push(arrMove(a, "nope", 1, false));
      s.push(arrPlace(a, "tokens", "main", 1)); s.push(arrPlace(arrHide(a, "tokens"), "tokens", "main", 0)); s.push(a);
      return s;"""
    out = truth.under_node(root, body)
    if out is not None:
        m, sd = DEFAULT["main"], DEFAULT["side"]
        assert out[0]["main"] == ["needs", "tasks", "map", "lanes"], "up: %r" % out[0]
        assert out[1] == DEFAULT and out[2] == DEFAULT, "nothing above the first or below the last of a column: %r %r" % (out[1], out[2])
        assert out[3]["main"] == m[:3] and out[3]["side"] == ["lanes"] + sd, "stacked on a phone, down from the main's last goes to the side's first: %r" % out[3]
        assert out[4]["side"] == sd[1:] and out[4]["main"] == m + ["progress"], "and up from the side's first to the main's last: %r" % out[4]
        assert out[5]["main"] == ["needs", "tasks", "lanes"] and out[5]["side"] == ["progress", "map", "agents", "pace", "tokens"], "to the other column, same position: %r" % out[5]
        assert out[6]["side"] == sd[:3] and out[6]["hide"] == ["tokens"], "hide: %r" % out[6]
        assert out[7]["main"] == m and out[7]["hide"] == ["tokens"], "add puts it back in its default place: %r" % out[7]
        assert out[8] == DEFAULT and out[11] == DEFAULT, "an unknown name changes nothing; the input is never changed: %r" % out[8]
        assert out[9]["main"] == ["needs", "tokens", "map", "tasks", "lanes"] and out[10]["hide"] == ["tokens"], "a drop places a shown component: %r %r" % (out[9], out[10])
    # the page under node: per project, and storage that refuses
    mine = {"main": ["tasks", "needs", "lanes"], "side": ["agents", "map", "progress", "pace"], "hide": ["tokens"]}
    other = truth.rich_data()
    other["repo"] = "other"
    res = page_load(root, tmp, [{"name": "mine", "tab": "sum"}], storage={KEY: json.dumps(mine)})
    if res is not None:
        got = columns(res[0]["tree"])
        assert got == {"main": mine["main"], "side": mine["side"]}, "the saved arrangement is drawn: %r" % got
        res = page_load(root, tmp, [{"name": "other project", "tab": "sum"}], base=other, storage={KEY: json.dumps(mine)})
        assert columns(res[0]["tree"]) == {"main": DEFAULT["main"], "side": DEFAULT["side"]}, "another project's page is not this one's arrangement"
        for mode in ("blocked", "full"):
            res = page_load(root, tmp, [{"name": mode, "tab": "sum", "ui": {"arr": True}}], storage={KEY: json.dumps(mine)}, mode=mode)
            r = res[0]
            assert not r["thrown"] and not r["errors"] and len(columns(r["tree"])["main"]) >= 1, "%s storage: the page draws: %r" % (mode, r["thrown"] or r["errors"])
    with browser(root, tmp, truth.rich_data()) as pg:
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp.iterdir() if p.is_file()}
        edit(pg)
        press(pg, '[data-f="tasks:up"]')
        pg.wait_for_function("document.querySelector('#view .col[data-col=main]').children[1].getAttribute('data-blk') === 'tasks'")
        press(pg, '[data-f="tokens:hide"]')
        pg.wait_for_function("document.querySelector('[data-f=\"add:tokens\"]')")
        press(pg, '[data-f="lanes:col"]')
        pg.wait_for_function("Array.from(document.querySelectorAll('#view .col[data-col=side] .arr')).some(e => e.getAttribute('data-blk') === 'lanes')")
        want = {"main": ["needs", "tasks", "map"], "side": ["progress", "agents", "pace", "lanes"]}   # to the other column at the same position (3), here its end
        assert layout_in(pg) == want, layout_in(pg)
        saved = {"main": want["main"], "side": want["side"], "hide": ["tokens"]}
        held = carry(pg, [KEY])
        assert held[KEY] == compact(saved), "the page keeps every change: %r" % held
        assert layout_in(pg) == want, "a reload keeps it: %r" % layout_in(pg)
        carry(pg, [KEY], pg.url0 + "?uak=a-newer-page")   # what the page's own reload does
        assert layout_in(pg) == want, "the page's own reload keeps it: %r" % layout_in(pg)
        edit(pg)
        press(pg, '[data-f="add:tokens"]')
        pg.wait_for_function("document.querySelector('#view .arr[data-blk=tokens]')")
        assert layout_in(pg)["side"][-1] == "tokens", "add brings it back to its default place: %r" % layout_in(pg)
        # everything in one column: one full-width column, no empty one
        for n in ("progress", "lanes", "agents", "pace", "tokens"):
            press(pg, '[data-f="%s:col"]' % n)
            pg.wait_for_function("(n) => document.querySelector('#view .col[data-col=main] .arr[data-blk=' + n + ']')", arg=n)
        press(pg, '[data-f="arr:done"]')
        pg.wait_for_function("!document.querySelector('.arrbar.on')")
        one = pg.evaluate("() => ({ cols: document.querySelectorAll('#view .col[data-col]').length, w: document.querySelector('#view .col').getBoundingClientRect().width, page: document.querySelector('#view .page').getBoundingClientRect().width })")
        assert one["cols"] == 1 and one["w"] > one["page"] - 60, "everything in one column is one full-width column: %r" % one
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp.iterdir() if p.is_file()}
        assert before == after, "arranging writes no file"
        assert not pg.errors, pg.errors
    with browser(root, tmp, truth.rich_data(), seed={"uak-layout:other": json.dumps({"main": ["needs"], "side": [], "hide": []})}) as pg:
        assert layout_in(pg) == {"main": DEFAULT["main"], "side": DEFAULT["side"]}, "another project's arrangement is not this page's: %r" % layout_in(pg)
    with browser(root, tmp, truth.rich_data(), phone=True) as pg:   # storage that refuses every write: kept for the page, said once
        pg.evaluate("Storage.prototype.setItem = function () { throw new DOMException('full', 'QuotaExceededError'); }; Storage.prototype.removeItem = Storage.prototype.setItem; 0")
        edit(pg)
        press(pg, '[data-f="tokens:hide"]', tap=True)
        pg.wait_for_function("document.querySelector('[data-f=\"add:tokens\"]')")
        said = pg.inner_text(".arrbar.on")
        assert "does not keep the arrangement" in said and not pg.errors, "a full or blocked storage says so: %r %r" % (said[-200:], pg.errors)
    return "browser"


def needs_you_cannot_be_hidden(root, tmp):
    """"Needs you" moves like any component but has no Hide: a stored or team arrangement that hides it still shows it, and
    hiding it through the model changes nothing."""
    out = truth.under_node(root, DEF_JS + """var a = arrRead(DEF, null).lay;
      return [arrHide(a, "needs"), arrRead(DEF, { main: ["map"], side: [], hide: ["needs"] }), arrMove(a, "needs", 0, false), arrRead(DEF, { main: [], side: [], hide: ["needs", "map", "tasks", "lanes", "progress", "agents", "pace", "tokens"] })];""")
    if out is not None:
        assert out[0] == DEFAULT, "hiding needs changes nothing: %r" % out[0]
        assert out[1]["lay"]["main"][0] == "needs" and "needs" not in out[1]["lay"]["hide"], "a stored hide of needs is not honoured: %r" % out[1]
        assert out[2]["side"][0] == "needs", "it can be moved: %r" % out[2]
        assert out[3]["lay"]["main"] == ["needs"] and out[3]["lay"]["side"] == [], "everything hidden still shows needs, never an empty page: %r" % out[3]
    res = page_load(root, tmp, [{"name": "arranging", "tab": "sum", "ui": {"arr": True}}, {"name": "drawn", "tab": "sum", "ui": {"arr": False}}],
                    storage={KEY: json.dumps({"main": [], "side": [], "hide": [n for n, _ in ORDER]})})
    if res is not None:
        fs = [t["a"]["data-f"] for t in find(res[0]["tree"], lambda t: (t.get("a") or {}).get("data-f", "").startswith("needs:"))]
        assert "needs:hide" not in fs and "needs:up" in fs and "needs:col" in fs, "needs has move handles and no Hide: %r" % fs
        assert any("Always shown" in s for s in res[0]["texts"]), "it says why"
        assert columns(res[1]["tree"]).get("main") == ["needs"], columns(res[1]["tree"])
    with browser(root, tmp, truth.rich_data()) as pg:
        edit(pg)
        assert pg.locator('[data-f="needs:hide"]').count() == 0 and pg.is_visible('[data-f="needs:col"]')
        for n in [n for n, _ in ORDER if n != "needs"]:
            press(pg, '[data-f="%s:hide"]' % n)
            pg.wait_for_function("(n) => document.querySelector('[data-f=\"add:' + n + '\"]')", arg=n)
        press(pg, '[data-f="arr:done"]')
        pg.wait_for_function("!document.querySelector('.arrbar.on')")
        assert layout_in(pg) == {"main": ["needs"]}, "only needs is left, and it is shown: %r" % layout_in(pg)
        assert pg.is_visible("#view .b-needs") and not pg.errors
    return "browser"


def fixture_repo(tmp):
    fx = tmp / "proj é"
    fx.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    git = resolve_binary("git")
    for args in (["init", "-q", "-b", "main"], ["config", "user.name", "Fixture"], ["config", "user.email", "fx@example.invalid"]):
        subprocess.run([git, "-C", str(fx)] + args, check=True, capture_output=True, env=env)
    (fx / ".uak").mkdir()
    (fx / ".uak/TASKS.md").write_text("# Plan\n\n## APP-001 · First\n- **Priority:** P0\n", encoding="utf-8")
    return fx, env


def run_dash(root, fx, env, *args):
    return subprocess.run([sys.executable, str(root / ".uak/bin/lib/dash.py")] + list(args), cwd=str(fx), env=env, capture_output=True, text=True, timeout=120)


def symlink_cases(root, tmp, env):
    """--save writes .uak/dash/layout.json of this repository and nothing else, whatever symlinks were planted (UAK-165 review)."""
    out = tmp / "outside"
    out.mkdir()
    def snapshot():
        return sorted(p.relative_to(out).as_posix() for p in out.rglob("*"))
    def link(src, dst, is_dir=False):
        try:
            os.symlink(str(dst), str(src), target_is_directory=is_dir)
            return True
        except (OSError, NotImplementedError):   # Windows without the right to create symlinks: nothing to plant
            return False
    save = ["layout", "--save", "main=needs,tasks", "side=progress"]
    # a symlinked .uak, and a symlinked .uak/dash: refused with one sentence, nothing written outside
    for case in ("uak", "dash"):
        fx = tmp / ("sym-" + case)
        fx.mkdir()
        subprocess.run([resolve_binary("git"), "-C", str(fx), "init", "-q"], check=True, capture_output=True, env=env)
        target = out / ("d-" + case)
        target.mkdir()
        if case == "uak":
            planted = link(fx / ".uak", target, True)
        else:
            (fx / ".uak").mkdir()
            planted = link(fx / ".uak" / "dash", target, True)
        if not planted:
            continue
        r = run_dash(root, fx, env, *save)
        assert r.returncode == 2 and "symlink" in (r.stdout + r.stderr) and not list(target.iterdir()), "a symlinked %s is refused: %r %r" % (case, r.returncode, r.stdout + r.stderr)
    # a symlink planted where a temporary file could be, and one at layout.json itself
    fx = tmp / "sym-files"
    (fx / ".uak/dash").mkdir(parents=True)
    subprocess.run([resolve_binary("git"), "-C", str(fx), "init", "-q"], check=True, capture_output=True, env=env)
    planted = link(fx / ".uak/dash/layout.json.tmp", out / "via-tmp") and link(fx / ".uak/dash/layout.json", out / "via-target")
    before = snapshot()
    r = run_dash(root, fx, env, *save)
    assert r.returncode == 0, r.stdout + r.stderr
    assert snapshot() == before, "nothing is written outside the repository: %r" % snapshot()
    lay = fx / ".uak/dash/layout.json"
    assert not lay.is_symlink() and json.loads(lay.read_text(encoding="utf-8"))["main"] == ["needs", "tasks"], "layout.json is a file of the repository"
    if planted:
        assert (fx / ".uak/dash/layout.json.tmp").is_symlink(), "the planted name is left alone, not used"
    assert sorted(p.name for p in (fx / ".uak/dash").iterdir()) == sorted(["layout.json"] + (["layout.json.tmp"] if planted else [])), "no temporary file is left"


def team_default_is_used_when_the_viewer_has_none(root, tmp):
    """`uak dash layout --save main=… side=… hide=…` writes .uak/dash/layout.json and nothing else; unknown names, a component
    named twice, needs hidden or a word it does not know are refused with a sentence and write nothing; `uak dash` carries the
    file in data.js; a viewer with no arrangement of their own draws it, their own wins, and Restore goes back to the team's.
    The write stays inside the repository: a symlinked .uak or .uak/dash is refused, a symlink planted at a temporary name is
    never followed, and a symlink at layout.json is replaced, not written through."""
    fx, env = fixture_repo(tmp)
    files = lambda: sorted(p.relative_to(fx).as_posix() for p in fx.rglob("*") if ".git" not in p.parts)
    start = files()
    for bad, word in ((["main=needs,bogus"], "bogus"), (["main=needs,map", "side=map"], "twice"), (["main=map", "hide=needs"], "cannot be hidden"),
                      (["main=needs", "middle=map"], "middle"), ([], "main="), (["main=needs/../x"], "needs/../x"), (["main=", "side=needs"], "names no component")):
        r = run_dash(root, fx, env, "layout", "--save", *bad)
        assert r.returncode == 2 and word in (r.stdout + r.stderr) and files() == start, "refused with a sentence, nothing written: %r -> %r %r" % (bad, r.returncode, r.stdout + r.stderr)
    r = run_dash(root, fx, env, "layout")
    assert r.returncode == 0 and "no team default" in r.stdout, r.stdout + r.stderr
    symlink_cases(root, tmp, env)
    team = {"main": ["tasks", "needs"], "side": ["progress", "map", "agents", "pace"], "hide": ["tokens", "lanes"]}
    r = run_dash(root, fx, env, "layout", "--save", "main=tasks,needs", "side=progress,map,agents,pace", "hide=tokens,lanes")
    assert r.returncode == 0 and ".uak/dash/layout.json" in r.stdout, r.stdout + r.stderr
    assert files() == sorted(start + [".uak/dash", ".uak/dash/layout.json"]), "only the layout file is written: %r" % files()
    saved = json.loads((fx / ".uak/dash/layout.json").read_text(encoding="utf-8"))
    assert {k: saved[k] for k in ("main", "side", "hide")} == team, saved
    assert "tasks" in run_dash(root, fx, env, "layout").stdout, "`uak dash layout` prints the team default"
    claims, out = tmp / "claims", tmp / "out"
    (claims / "meta").mkdir(parents=True)
    r = run_dash(root, fx, env, "--claims", str(claims), "--out", str(out))
    assert r.returncode == 0, r.stderr[-800:]
    data = json.loads((out / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    assert data.get("layout") == team, "data.js carries the team's arrangement: %r" % data.get("layout")
    (fx / ".uak/dash/layout.json").write_text("{not json", encoding="utf-8")
    r = run_dash(root, fx, env, "--claims", str(claims), "--out", str(out))
    data = json.loads((out / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    assert r.returncode == 0 and data.get("layout") is None, "a broken team file is no layout, never a failure: %r" % data.get("layout")
    base = truth.rich_data()
    base["layout"] = team
    res = page_load(root, tmp, [{"name": "team", "tab": "sum"}, {"name": "team arranging", "tab": "sum", "ui": {"arr": True}}], base=base)
    if res is not None:
        assert columns(res[0]["tree"]) == {"main": team["main"], "side": team["side"]}, "no arrangement of my own: the team's: %r" % columns(res[0]["tree"])
        assert any("Restore the team's default" in s for s in res[1]["texts"]), "Restore says where it goes"
        cmd = [s for s in res[1]["texts"] if s.startswith("bash .uak/bin/uak dash layout")]
        assert cmd == ["bash .uak/bin/uak dash layout --save main=tasks,needs side=progress,map,agents,pace hide=tokens,lanes"], "the command for the team is the arrangement shown: %r" % cmd
        res = page_load(root, tmp, [{"name": "mine", "tab": "sum"}], base=base, storage={KEY: json.dumps(DEFAULT)})
        assert columns(res[0]["tree"]) == {"main": DEFAULT["main"], "side": DEFAULT["side"]}, "my own arrangement wins"
        res = page_load(root, tmp, [{"name": "stored null", "tab": "sum"}], base=base, storage={KEY: "null"})
        assert columns(res[0]["tree"]) == {"main": team["main"], "side": team["side"]}, "a stored null is no arrangement: the team's applies: %r" % columns(res[0]["tree"])
    data = truth.rich_data()
    data["layout"] = team
    with browser(root, tmp, data) as pg:
        assert layout_in(pg) == {"main": team["main"], "side": team["side"]}, layout_in(pg)
        edit(pg)
        press(pg, '[data-f="map:up"]')
        pg.wait_for_function("document.querySelector('#view .col[data-col=side]').children[0].getAttribute('data-blk') === 'map'")
        press(pg, '[data-f="arr:restore"]')
        pg.wait_for_function("document.querySelector('#view .col[data-col=side]').children[0].getAttribute('data-blk') === 'progress'")
        assert pg.evaluate("localStorage.getItem('%s')" % KEY) is None, "Restore forgets my arrangement, so I follow the team's again"
        assert not pg.errors, pg.errors
    return "browser"


def unknown_component_falls_back(root, tmp):
    """A saved arrangement from an older page: the names it does not know are dropped, the rest is kept, a component it does
    not name (added since) takes its default place, one notice says so, once (the next load is quiet)."""
    old = {"main": ["tasks", "gone", "needs"], "side": ["agents", "progress", "removed"], "hide": ["pace", "x"]}
    out = truth.under_node(root, DEF_JS + "return [arrRead(DEF, %s), arrRead(DEF, %s)];" % (json.dumps(json.dumps(old)), json.dumps(json.dumps({"main": ["needs", "constructor", "__proto__", 5, None], "side": [], "hide": []}))))
    if out is not None:
        lay = out[0]["lay"]
        assert out[0]["note"] == "unknown", out[0]
        assert lay["main"] == ["tasks", "needs", "map", "lanes"] and lay["side"] == ["agents", "progress", "tokens"] and lay["hide"] == ["pace"], "kept, dropped, new after the ones that precede it by default: %r" % lay
        assert out[1]["note"] == "unknown" and out[1]["lay"]["main"] == DEFAULT["main"], "names that are not components (even object keys) are dropped: %r" % out[1]
    res = page_load(root, tmp, [{"name": "first", "tab": "sum"}, {"name": "redraw", "tab": "sum"}], storage={KEY: json.dumps(old)})
    if res is not None:
        first, redraw = res
        assert not first["thrown"] and not first["errors"], first["thrown"] or first["errors"]
        assert columns(first["tree"]) == {"main": ["tasks", "needs", "map", "lanes"], "side": ["agents", "progress", "tokens"]}, columns(first["tree"])
        assert any("no longer exist" in s for s in notice(first)), "one notice says so: %r" % notice(first)
        assert json.loads(first["kept"][KEY]) == {"main": ["tasks", "needs", "map", "lanes"], "side": ["agents", "progress", "tokens"], "hide": ["pace"]}, "the repaired arrangement is kept"
        again = page_load(root, tmp, [{"name": "next load", "tab": "sum"}], storage=first["kept"])
        assert not notice(again[0]), "the next load is quiet: %r" % notice(again[0])
    with browser(root, tmp, truth.rich_data(), seed={KEY: json.dumps(old)}) as pg:
        assert layout_in(pg) == {"main": ["tasks", "needs", "map", "lanes"], "side": ["agents", "progress", "tokens"]}, layout_in(pg)
        assert "no longer exist" in pg.inner_text("#view .arrbar"), pg.inner_text("#view .arrbar")
        kept = pg.evaluate("(k) => localStorage.getItem(k)", KEY)
        assert kept == compact({"main": ["tasks", "needs", "map", "lanes"], "side": ["agents", "progress", "tokens"], "hide": ["pace"]}) and not pg.errors, "the repaired arrangement replaces the old one: %r" % kept
    with browser(root, tmp, truth.rich_data(), seed={KEY: kept}) as pg:   # the next load reads what the first one kept
        assert "no longer exist" not in pg.inner_text("#view .arrbar") and not pg.errors, "said once"
    return "browser"


def arranging_works_with_the_keyboard(root, tmp):
    """Edit, every handle, Add, Restore and Done are buttons reached with Tab and pressed with Enter or Space; focus stays on
    the moved component (or the button that undoes a hide), is visible, and each move is announced; at 390 px with touch the
    handles are 44 px and work by tap, a drag on a component's grip moves it without scrolling the page, a drag anywhere else
    scrolls; with a mouse the grip drags across columns."""
    with browser(root, tmp, truth.rich_data()) as pg:
        pg.focus('[data-f="arr:edit"]')
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.activeElement && document.activeElement.getAttribute('data-f') === 'arr:done'")
        tabbed = []
        for _ in range(8):
            pg.keyboard.press("Tab")
            tabbed.append(pg.evaluate("document.activeElement.getAttribute('data-f') || document.activeElement.tagName"))
        assert any(x.startswith("needs:") for x in tabbed), "Tab reaches the handles: %r" % tabbed
        pg.focus('[data-f="tasks:up"]')
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.querySelector('#view .col[data-col=main]').children[1].getAttribute('data-blk') === 'tasks'")
        st = pg.evaluate("""() => { const a = document.activeElement, s = getComputedStyle(a); return { f: a.getAttribute('data-f'), o: s.outlineStyle, w: parseFloat(s.outlineWidth),
          live: document.getElementById('arr-live').textContent }; }""")
        assert st["f"] == "tasks:up" and st["o"] != "none" and st["w"] >= 2, "focus stays on the moved component and is visible: %r" % st
        assert "2/4" in st["live"] and "Main column" in st["live"], "the move is announced: %r" % st["live"]
        pg.keyboard.press(" ")
        pg.wait_for_function("document.querySelector('#view .col[data-col=main]').children[0].getAttribute('data-blk') === 'tasks'")
        assert pg.evaluate("document.activeElement.getAttribute('data-f')") == "tasks:down", "at the top, focus moves to the handle that still works"
        pg.focus('[data-f="tokens:hide"]')
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.activeElement && document.activeElement.getAttribute('data-f') === 'add:tokens'")
        assert "Hidden" in pg.evaluate("document.getElementById('arr-live').textContent")
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.querySelector('#view .arr[data-blk=tokens]') && document.activeElement.closest('.arr[data-blk=tokens]')")
        pg.focus('[data-f="arr:restore"]')
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.querySelector('#view .col[data-col=main]').children[0].getAttribute('data-blk') === 'needs'")
        assert pg.evaluate("document.getElementById('arr-live').textContent") == "The default is back", "Restore says it was done: %r" % pg.evaluate("document.getElementById('arr-live').textContent")
        pg.focus('[data-f="arr:done"]')
        pg.keyboard.press("Enter")
        pg.wait_for_function("document.activeElement && document.activeElement.getAttribute('data-f') === 'arr:edit'")
        # a mouse drag on a grip, to the other column
        edit(pg)
        pg.evaluate("scrollTo({ top: Math.min(document.querySelector('[data-grip=pace]').getBoundingClientRect().top, document.querySelector('#view .arr[data-blk=tasks]').getBoundingClientRect().top) + scrollY - 60, behavior: 'instant' })")
        src = pg.locator('[data-grip="pace"]').bounding_box()
        dst = pg.locator('#view .arr[data-blk="tasks"]').bounding_box()
        assert 0 <= src["y"] < 860 and 0 <= dst["y"] < 860, "both ends of the drag are on screen: %r %r" % (src, dst)
        pg.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
        pg.mouse.down()
        for k in range(1, 9):
            pg.mouse.move(src["x"] + (dst["x"] + 40 - src["x"]) * k / 8, src["y"] + (dst["y"] + 4 - src["y"]) * k / 8)
        pg.mouse.up()
        pg.wait_for_function("document.querySelector('#view .col[data-col=main] .arr[data-blk=pace]')")
        main = layout_in(pg)["main"]
        assert main.index("pace") == main.index("tasks") - 1, "the drop lands where the line showed, before tasks: %r" % main
        # a drag released outside the window is a cancel, never a drop at the nearest column
        before = layout_in(pg)
        g = pg.locator('[data-grip="agents"]').bounding_box()
        pg.mouse.move(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2)
        pg.mouse.down()
        pg.mouse.move(300, 300, steps=4)
        pg.wait_for_function("document.querySelector('.dropline')")
        pg.evaluate("document.dispatchEvent(new PointerEvent('pointerup', { clientX: -40, clientY: innerHeight + 40, bubbles: true }))")
        pg.mouse.up()
        pg.wait_for_function("!document.querySelector('.dropline') && !document.querySelector('.arr.drag')")
        assert layout_in(pg) == before, "a release outside the window moves nothing: %r" % layout_in(pg)
        assert not pg.errors, pg.errors
    with browser(root, tmp, truth.rich_data(), phone=True) as pg:
        edit(pg)
        sizes = pg.evaluate("() => Array.from(document.querySelectorAll('#view .hbar button, #view .hbar .grip, .arrbar button')).filter(b => b.offsetParent).map(b => { const r = b.getBoundingClientRect(); return [r.width, r.height]; })")
        assert sizes and all(w >= 44 and hh >= 44 for w, hh in sizes), "44 px targets at phone width: %r" % [s for s in sizes if s[0] < 44 or s[1] < 44]
        assert pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), "no sideways scroll at 390 px"
        press(pg, '[data-f="agents:down"]', tap=True)
        pg.wait_for_function("(() => { const s = Array.from(document.querySelectorAll('#view .col[data-col=side] .arr')).map(e => e.getAttribute('data-blk')); return s.indexOf('agents') === 2; })()")
        cdp = pg.context.new_cdp_session(pg)

        def touch_drag(x0, y0, x1, y1):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y0}]})
            for k in range(1, 11):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x0 + (x1 - x0) * k / 10, "y": y0 + (y1 - y0) * k / 10}]})
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        pg.evaluate("scrollTo({ top: document.querySelector('#view .arr[data-blk=progress]').getBoundingClientRect().top + scrollY - 100, behavior: 'instant' })")
        y0 = pg.evaluate("scrollY")
        g = pg.locator('[data-grip="pace"]').bounding_box()
        prev = pg.locator('#view .arr[data-blk="progress"]').bounding_box()
        assert 60 < prev["y"] < g["y"] < 800, "the grip and the place it goes to are on screen: %r %r" % (prev, g)
        target = prev["y"] + 4
        touch_drag(g["x"] + g["width"] / 2, g["y"] + g["height"] / 2, g["x"] + g["width"] / 2, target)
        pg.wait_for_function("(() => { const s = Array.from(document.querySelectorAll('#view .col[data-col=side] .arr')).map(e => e.getAttribute('data-blk')); return s.indexOf('pace') < s.indexOf('progress'); })()")
        assert abs(pg.evaluate("scrollY") - y0) < 80, "a drag on the grip does not scroll the page: %r -> %r" % (y0, pg.evaluate("scrollY"))
        y1 = pg.evaluate("scrollY")
        before = layout_in(pg)
        touch_drag(195, 700, 195, 150)
        pg.wait_for_function("(y) => Math.abs(scrollY - y) > 50", arg=y1)
        assert layout_in(pg) == before, "a drag on the content scrolls and moves nothing"
        assert not pg.errors, pg.errors
    return "browser"


def corrupt_arrangement_gives_the_default(root, tmp):
    """A stored value that cannot be read (not JSON, the wrong shape, over 4 KiB) gives the default and says so once; storage
    that throws on read or write leaves a working page; a component that throws while being moved says it could not be drawn
    and can still be moved and hidden; no case leaves an exception or an empty summary."""
    names = truth.under_node(root, DEF_JS + """return arrRead(DEF, JSON.stringify({ main: ["toString", "__proto__", "constructor", "needs"], side: ["hasOwnProperty", "valueOf"], hide: ["isPrototypeOf"] }));""")
    if names is not None:
        assert names == {"lay": DEFAULT, "note": "unknown"}, "names of Object's own properties are not components: %r" % names
    bad = ["{", "x" * 5000, json.dumps({"main": ["needs"] * 900, "side": [], "hide": []}), "[]", "5", "null", json.dumps({"main": "needs", "side": []}), json.dumps({"side": ["map"]})]
    # the two long values are built in node: a program passed with -e has to fit Windows' command line (32,767 characters)
    out = truth.under_node(root, DEF_JS + """var bad = %s; bad[1] = new Array(5001).join("x"); bad[2] = JSON.stringify({ main: new Array(901).join("n,").split(",").slice(0, 900).map(function () { return "needs"; }), side: [], hide: [] });
      return [bad[1].length === 5000 && bad[2].length > 4096].concat(bad.map(function (v) { return arrRead(DEF, v); }));""" % json.dumps([b if len(b) < 100 else "" for b in bad]))
    if out is not None:
        assert out.pop(0) is True, "the long values are what they claim"
        for v, r in zip(bad, out):
            note = "" if v == "null" else "corrupt"
            assert r == {"lay": DEFAULT, "note": note}, "%r gives the default (%s): %r" % (v[:40], note or "no note", r)
    res = page_load(root, tmp, [{"name": "corrupt", "tab": "sum"}, {"name": "redraw", "tab": "sum"}], storage={KEY: "{not json"})
    if res is not None:
        r = res[0]
        assert not r["thrown"] and not r["errors"] and columns(r["tree"]) == {"main": DEFAULT["main"], "side": DEFAULT["side"]}, r["thrown"] or columns(r["tree"])
        assert any("could not be read" in s for s in notice(r)), "it says so: %r" % notice(r)
        assert KEY not in r["kept"], "the unreadable value is forgotten, so it is said once"
        assert not notice(page_load(root, tmp, [{"name": "next", "tab": "sum"}], storage=r["kept"])[0]), "said once"
        for mode in ("blocked", "full"):
            r = page_load(root, tmp, [{"name": mode, "tab": "sum"}, {"name": mode + " arranging", "tab": "sum", "ui": {"arr": True}}], storage={KEY: "{"}, mode=mode)
            for x in r:
                assert not x["thrown"] and not x["errors"] and columns(x["tree"]).get("main"), "%s: %r" % (x["name"], x["thrown"] or x["errors"])
        broken = page_load(root, tmp, [{"name": "throws while arranging", "tab": "sum", "ui": {"arr": True}, "mutate": "d.agents[0].tasks=null;"}])[0]
        assert broken["thrown"] is None and any(e.startswith("agents:") for e in broken["errors"]), broken["errors"]
        box = [t for t in find(broken["tree"], lambda t: (t.get("a") or {}).get("data-blk") == "agents")]
        assert box and "Could not draw this block (agents)" in text_of(box[0]) and find(box[0], lambda t: (t.get("a") or {}).get("data-f") == "agents:hide"), "the broken one is said and keeps its handles"
    with browser(root, tmp, truth.rich_data(), seed={KEY: "x" * 5000}) as pg:
        assert layout_in(pg) == {"main": DEFAULT["main"], "side": DEFAULT["side"]} and "could not be read" in pg.inner_text("#view .arrbar") and not pg.errors
    with browser(root, tmp, truth.rich_data()) as pg:   # storage that throws on every read: a page, no exception
        pg.add_init_script("Storage.prototype.getItem = function () { throw new DOMException('denied', 'SecurityError'); };")
        pg.reload()
        pg.wait_for_function("document.querySelector('#view .page .col')")
        assert layout_in(pg) == {"main": DEFAULT["main"], "side": DEFAULT["side"]} and not pg.errors, pg.errors
    data = truth.rich_data()
    data["agents"][0]["tasks"] = None
    with browser(root, tmp, data) as pg:   # a component that throws, moved and hidden
        edit(pg)
        assert "Could not draw this block (agents)" in pg.inner_text('#view .arr[data-blk="agents"]')
        press(pg, '[data-f="agents:up"]')
        pg.wait_for_function("document.querySelector('#view .col[data-col=side]').children[0].getAttribute('data-blk') === 'agents'")
        press(pg, '[data-f="agents:hide"]')
        pg.wait_for_function("document.querySelector('[data-f=\"add:agents\"]')")
        assert pg.locator("#view .col .arr").count() == len(ORDER) - 1 and not pg.errors, pg.errors
    return "browser"


PAINT_PROBE = """(function () {
  window.__frames = [];
  function visible() {
    var out = [], w = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT), n;
    while ((n = w.nextNode())) {
      var t = n.nodeValue.trim(); if (!t) continue;
      var r = document.createRange(); r.selectNodeContents(n); var b = r.getBoundingClientRect(), p = n.parentElement;
      if (!p || b.width < 1 || b.height < 1 || b.right < 0 || b.bottom < 0 || b.left > innerWidth || b.top > innerHeight) continue;
      if (p.checkVisibility && !p.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true, opacityProperty: true })) continue;   // a closed popover's content is not on screen
      out.push(t);
    }
    return { lang: document.documentElement.lang, text: out };
  }
  (function next() { requestAnimationFrame(function () { window.__frames.push(document.body ? visible() : { lang: document.documentElement.lang, text: [] }); if (window.__frames.length < 6) next(); }); })();
})();"""
ENGLISH = re.compile(r"\b(loading|Overview|Needs you|Snapshot|Live|ago|Share|Skip to content|Theme|Palette|Tasks|Progress|Agents|Board|Messages|Tokens spent|Edit)\b")


def language_is_applied_before_first_paint(root, tmp):
    """On a Spanish page every painted frame, from the first one after a load or a reload, is in Spanish: no English word is
    ever on screen and the document's language is es before the first frame. The arrange mode's own words (the line at the top,
    the handles, Add and its lines, Restore, the notices) are drawn in Spanish too."""
    old = {"main": ["tasks", "gone", "needs"], "side": ["agents"], "hide": ["tokens", "lanes"]}
    res = page_load(root, tmp, [{"name": "es", "tab": "sum"}, {"name": "es arranging", "tab": "sum", "ui": {"arr": True}}], storage={KEY: json.dumps(old)}, mode="full", lang="es")
    if res is not None:
        words = res[0]["texts"] + res[1]["texts"]
        leaks = sorted(set(w for w in words if re.search(r"Move, hide|Move up|Move down|other column|Always shown|Restore the|Every component|For the whole team|does not keep|no longer exist|could not be read|Drag to move|What waits for you|Tokens spent, by|Who built and|Main column|Side column|\bEdit\b|\bAdd\b|\bHide\b", w)))
        assert not leaks, "English left in the Spanish arrange mode: %r" % leaks[:10]
        for es in ("Mueve, oculta o añade componentes. Hecho cuando termines.", "Añadir", "Subir", "Bajar", "A la otra columna", "Siempre visible", "Tokens gastados, por arnés",
                   "Quién construyó y revisó qué, en el tiempo", "Volver a la predeterminada", "Hecho", "Arrastra para mover"):
            assert any(es in w for w in words), "the Spanish arrange mode says %r: %r" % (es, words[:30])
        assert any("ya no existen" in w for w in notice(res[0])) and any("no guarda la disposición" in w for w in notice(res[1])), (notice(res[0]), notice(res[1]))
        assert any("Editar" in w for w in res[0]["texts"]), "Edit reads in Spanish"
    with browser(root, tmp, truth.rich_data(), lang="es") as pg:
        pg.context.add_init_script(PAINT_PROBE)
        for how in ("load", "reload", "load"):
            carry(pg, ["uak-language", "uak-dash"], None if how == "reload" else pg.url0)
            pg.wait_for_function("window.__frames && window.__frames.length >= 6")
            frames = pg.evaluate("window.__frames")
            english = [(i, [t for t in f["text"] if ENGLISH.search(t)]) for i, f in enumerate(frames)]
            english = [x for x in english if x[1]]
            assert not english, "%s: English on screen in frame(s) %r" % (how, english[:3])
            assert all(f["lang"] == "es" for f in frames), "%s: the document's language before the first frame: %r" % (how, [f["lang"] for f in frames])
            assert any("Te necesita a ti" in t for f in frames for t in f["text"]), "the summary was painted in those frames: %r" % frames[-1]["text"][:20]
    return "browser"


TESTS = [summary_is_a_list_of_components, arrange_mode_shakes_and_respects_reduced_motion, move_hide_and_add_persist_per_viewer,
         needs_you_cannot_be_hidden, team_default_is_used_when_the_viewer_has_none, unknown_component_falls_back,
         arranging_works_with_the_keyboard, corrupt_arrangement_gives_the_default, language_is_applied_before_first_paint]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    for key in [k for k in os.environ if k.startswith("UAK_")]:
        del os.environ[key]
    failed = skipped = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-layout-"))
        started = time.monotonic()
        try:
            how = test(root, tmp)
            print("PASS %s (%s%.2fs)" % (test.__name__, "browser, " if how == "browser" else "", time.monotonic() - started))
        except NoBrowser:
            skipped += 1
            print("SKIP %s (no browser)" % test.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s: %s)" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("TEST_DASHBOARD_LAYOUT_RESULT %s failed=%d skipped=%d" % ("PASS" if not failed else "FAIL", failed, skipped))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
