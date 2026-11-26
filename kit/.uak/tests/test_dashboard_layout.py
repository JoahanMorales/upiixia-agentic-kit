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


# ---------------------------------------------------------------- UAK-198: the whole screen on a wide monitor
# On 2026-11-25 the human opened the dashboard on a desktop monitor and found "a giant empty space at the right": .page and .wide
# stopped at 1360 px, aligned left, so at 1920 px 488 px were blank. Every shot of UAK-162 and UAK-165 was 1280 or 390 px wide.
# These cases load the page with the kit's own fonts (copied beside it), a frozen clock, UTC and en-US, so the boxes they measure
# are the same on any Linux with Chromium; every view of every tab is drawn by clicking, as a person does.
WIDE_VIEWS = ["sum", "arr", "board-map", "board-cards", "agents", "talk", "bb", "mem-list", "mem-graph", "tokens"]
WIDE_WORDS = ("the summary keeps every task in view while agents claim review and integrate work across a plan whose tests fail "
              "first then pass on the branch before a reviewer reads the diff and the human merges it on main").split()


def prose(n, seed):
    out = " ".join(WIDE_WORDS[(seed * 7 + i * 5) % len(WIDE_WORDS)] for i in range(n))
    return out[0].upper() + out[1:]


def wide_data(tasks=60, agents=14, humans=2):
    """A project in full swing, deterministic: integrated, in review (waiting, changes requested), in progress (one stalled with a
    long note), blocked, available with dependencies; online, recent, away and offline agents and two people; conversations
    with long messages; lessons and decisions citing tasks and files; a black box; tokens by harness, model, scope and task."""
    d = truth.fixture_data(agents=0, tasks=0)
    g = d["generated"]
    ts = []
    for i in range(tasks):
        k = i / float(max(1, tasks))
        state = "INTEGRATED" if k < .55 else "REVIEW" if k < .62 else "CLAIMED" if k < .72 else "BLOCKED" if k < .74 else "AVAILABLE"
        t = {"id": "T-%d" % (i + 1), "title": prose(5 + (i * 7) % 17, i), "priority": "P%d" % (i % 3), "depends": "None", "state": state,
             "owner": "kit-%d" % (i % max(1, agents)) if agents else "", "pr": "-", "progress": "", "updated": g - 3600 * (tasks - i) // 3, "stalled": 0,
             "lease": g + 900, "paths": "kit/x%d.sh" % (i % 5), "next": "", "away": 0, "outside": False, "participants": "",
             "harnesses": [{"agent": "kit-%d" % (i % max(1, agents)), "harness": "claude-code", "model": "opus"}]}
        if state == "REVIEW":
            t["sub"] = {"kind": ["waiting", "changes", "rereview"][i % 3], "text": ["waiting for a reviewer", "changes requested (round 2)", "re-review"][i % 3],
                        "since": g - 900 - 60 * i, "late": i % 4 == 0, "rounds": i % 3, "rejects": i % 2}
        if state == "AVAILABLE" and i % 2:
            t["depends"] = "T-%d, T-%d" % (i - 3, i - 1)
        ts.append(t)
    claimed = [t for t in ts if t["state"] == "CLAIMED"]
    if claimed:
        claimed[0].update(stalled=200, progress=prose(40, 3) + " · at 1795000000")
    ags = []
    for i in range(agents):
        st = "online" if i < 4 else "recent" if i < 6 else "away" if i < 8 else "offline"
        live = [{"id": t["id"], "state": t["state"]} for t in ts if t["owner"] == "kit-%d" % i and t["state"] in ("CLAIMED", "REVIEW", "BLOCKED")][:3]
        ags.append({"name": "kit-%d" % i, "human": "ana", "is_human": False, "last_seen": g - [60, 4000, 20000, 900000][["online", "recent", "away", "offline"].index(st)] - i,
                    "status": st, "tasks": live, "sessions": 1, "events": 3, "checkpoints": i % 4, "messages": i % 7, "verdicts": i % 3, "started": g - 90000, "role": "reviewer" if i % 5 == 1 else ""})
    for i in range(humans):
        ags.append({"name": ["ana", "luis"][i % 2] + ("" if i < 2 else str(i)), "human": "", "is_human": True, "last_seen": g - 300 * (i + 1), "status": "online", "tasks": [],
                    "sessions": 0, "events": 0, "checkpoints": 0, "messages": 1, "verdicts": 0, "started": g - 90000, "role": ""})
    d.update(tasks=ts, agents=ags, repo="demo")
    states = {}
    for t in ts:
        states[t["state"]] = states.get(t["state"], 0) + 1
    done = states.get("INTEGRATED", 0)
    d["progress"] = {"done": 100 * done // max(1, tasks), "weighted": min(100, 100 * done // max(1, tasks) + 6), "total": tasks, "states": states, "outside": 0}
    rev = [t for t in ts if t["state"] == "REVIEW"]
    d["offers"] = [{"task": t["id"], "to": ["all"], "since": t["sub"]["since"], "owner": t["owner"]} for t in rev if t["sub"]["kind"] == "waiting"]
    d["queue"] = [{"task": rev[0]["id"], "state": "HUMAN", "reason": prose(24, 9), "at": g - 500}] if rev else []
    kinds = ["review", "reject", "contract", "approve", "human", "reply"]
    d["messages"] = [{"n": n + 1, "t": g - 4000 + 120 * n, "from": "kit-%d" % (n % 3) if agents else "ana", "to": ["agent:kit-%d" % ((n + 1) % 3)], "kind": kinds[n % 6],
                      "task": rev[n % len(rev)]["id"] if rev else "", "text": prose(8 + (n * 13) % 70, n)} for n in range(30 if tasks else 0)]
    d["lessons"] = [{"n": str(n + 1), "t": g - 3000 + n, "agent": "kit-%d" % (n % 3), "task": ts[(n * 5) % len(ts)]["id"] if ts else "-", "paths": "kit/x%d.sh" % (n % 4),
                     "text": "%s %s" % (ts[(n * 5) % len(ts)]["id"] if ts else "", prose(12 + (n * 11) % 40, n + 20))} for n in range(16 if tasks else 0)]
    d["decisions"] = [{"t": g - 2000 + n, "kind": ["plan", "amend", "contract"][n % 3], "who": "ana/ana",
                       "text": "tasks added: %s %s | Why: %s" % (ts[n % len(ts)]["id"], ts[(n + 3) % len(ts)]["id"], prose(10 + (n * 9) % 30, n + 40))} for n in range(10 if tasks else 0)]
    d["blackbox"] = [{"time": "2026-11-%02dT%02d:00Z" % (10 + n % 8, n % 24), "kit": "v6.9", "harness": ["claude-code", "codex", "cursor"][n % 3], "source": "agent" if n % 3 else "auto",
                      "kind": ["exit3", "friction", "need", "idea"][n % 4], "command": "uak claim" if n % 2 else "-", "what": prose(10 + (n * 7) % 50, n + 60), "fix": prose(8, n)} for n in range(24)]
    d["usage"] = {"claude-code": {"claim": 9, "done": 7, "map": 12, "lens": 3, "wait": 4, "status": 9}, "codex": {"claim": 3, "done": 2, "map": 1}, "cursor": {"claim": 1, "done": 1}}
    by_task = {t["id"]: 1000000 * (1 + (i * 37) % 90) for i, t in enumerate(ts[:40])}
    total = sum(by_task.values()) + 5000000
    d["tokens"] = {"total": total, "by_task": dict(by_task, main=5000000), "by_harness": {"claude-code": total * 7 // 10, "codex": total * 2 // 10, "cursor": total - total * 9 // 10},
                   "by_scope": {"lead": total * 6 // 10, "subagent": total - total * 6 // 10}, "by_model": {"opus": total // 2, "sonnet": total // 4, "haiku": total // 8, "fable": total - total // 2 - total // 4 - total // 8},
                   "by_kind": {"input": total // 50, "cache_write": total // 20, "cache_read": total - total // 50 - total // 20 - total // 100, "output": total // 100}} if tasks else {"total": 0, "by_task": {}, "by_harness": {}, "by_scope": {}}
    def story(t, moves):   # the compact copy of `uak timeline` (lib/dash.py compact_timeline)
        lines = [[at, kind, who, "opus", "claude-code", "%s %s" % (kind, prose(6, at % 97)), "", "", ""] for at, kind, who in moves]
        return {"state": t["state"], "open": t["state"] != "INTEGRATED", "now": g, "lines": lines, "states": [["CLAIMED", "", 3600], ["REVIEW", "waiting for a reviewer", 1200]],
                "agents": [[t["owner"], "opus", "claude-code", len(lines), ["claim", "done"]]], "rounds": 1, "rejects": 0, "tokens": 0, "commands": [], "errors": 0, "history": "read"}
    tl, s1, s2 = {}, 300 if len(ts) <= 60 else 12000 // len(ts), 200 if len(ts) <= 60 else 8000 // len(ts)   # every move in the past
    for i, t in enumerate(ts):
        a = t["owner"]
        if t["state"] == "INTEGRATED" and i >= len(ts) * .45:
            tl[t["id"]] = story(t, [[g - 20000 + s1 * i, "claim", a], [g - 15000 + s1 * i, "done", a], [g - 14000 + s1 * i, "approve", "kit-1"], [g - 13000 + s1 * i, "integrate", a]])
        elif t["state"] in ("CLAIMED", "REVIEW", "BLOCKED"):
            tl[t["id"]] = story(t, [[g - 9000 + s2 * i, "claim", a]] + ([[g - 3000, "done", a]] if t["state"] == "REVIEW" else []))
    d["timelines"] = tl
    return d


def wide_data_named(name):
    """The forced edges: no task, one task, 300 tasks, 4 agents, 40 agents."""
    return {"empty": lambda: wide_data(tasks=0, agents=0, humans=1), "one": lambda: wide_data(tasks=1, agents=1), "300": lambda: wide_data(tasks=300, agents=20),
            "4 agents": lambda: wide_data(tasks=60, agents=4), "40 agents": lambda: wide_data(tasks=60, agents=40)}[name]()


@contextlib.contextmanager
def screen(root, tmp, data, width, height=None, phone=False, lang="en", seed=None, scale=1):
    """The page in Chromium at WIDTH, with the kit's fonts beside it (loaded before anything is measured), Date.now frozen at the
    data's moment, UTC and en-US, reduced motion (the arrange mode does not shake: its boxes are measurable). Raises NoBrowser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise NoBrowser()
    lib = root / ".uak/bin/lib"
    shutil.copy(str(lib / "dash.html"), str(tmp / "index.html"))
    shutil.copy(str(lib / "workspace.js"), str(tmp / "workspace.js"))
    if not (tmp / "fonts").exists():
        shutil.copytree(str(lib / "fonts"), str(tmp / "fonts"))
    (tmp / "data.js").write_text("window.UAK_DATA = " + json.dumps(data) + ";", encoding="utf-8")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001  (Playwright without its Chromium)
            raise NoBrowser() from exc
        try:
            h = height or (844 if phone else 1440 if width >= 2560 else 1080 if width >= 1600 else 900)
            opts = dict(viewport={"width": width, "height": h}, device_scale_factor=2, is_mobile=True, has_touch=True) if phone else dict(viewport={"width": width, "height": h}, device_scale_factor=scale)
            ctx = b.new_context(reduced_motion="reduce", timezone_id="UTC", locale="en-US", **opts)
            first = dict({"uak-dash": json.dumps({"tab": "sum"}), "uak-language": lang}, **(seed or {}))
            ctx.add_init_script("""(function () { try { var now = %d; Date.now = function () { return now; };
              if (!/index\\.html$/.test(location.pathname)) return;
              var m = /^uak-test-carry:([\\s\\S]*)$/.exec(window.name), s = m ? JSON.parse(m[1]) : window.name === 'uak-test-seeded' ? null : %s;
              window.name = 'uak-test-seeded';
              if (s) Object.keys(s).forEach(function (k) { if (s[k] === null) localStorage.removeItem(k); else localStorage.setItem(k, s[k]); }); } catch (e) {} })();""" % ((data["generated"] + 5) * 1000, json.dumps(first)))
            pg = ctx.new_page()
            pg.errors = []
            pg.on("pageerror", lambda e: pg.errors.append(str(e)))
            pg.url0 = "file://" + str(tmp / "index.html")
            pg.goto(pg.url0)
            pg.wait_for_function("document.getElementById('view').childElementCount > 0")
            assert pg.evaluate("document.fonts.ready.then(() => document.fonts.check('13px Inter') && document.fonts.check('11px \"JetBrains Mono\"'))"), "the kit's fonts load"
            yield pg
        finally:
            b.close()


def show(pg, view):
    """Draw VIEW by clicking the page's own controls (a tab, the board's Map or Cards, the memory's List or Graph, Edit), then wait
    two frames (the conversation unclamps its short bubbles in one)."""
    tab = {"sum": "sum", "arr": "sum", "board-map": "board", "board-cards": "board", "agents": "agents", "talk": "talk", "bb": "bb",
           "mem-list": "memory", "mem-graph": "memory", "tokens": "tokens"}[view]
    pg.evaluate("""([tab, view]) => { const on = document.querySelector('.arrbar.on'); if (on) document.querySelector('[data-f="arr:done"]').click();
      document.getElementById('tab-' + tab).click();
      const pick = (sel, i) => { const b = document.querySelectorAll(sel)[i]; if (b && b.getAttribute('aria-pressed') !== 'true') b.click(); };
      if (view === 'board-map') pick('#view .wide > .bh .seg button', 0); if (view === 'board-cards') pick('#view .wide > .bh .seg button', 1);
      if (view === 'mem-list') pick('#view .wide > .filters .seg button', 0); if (view === 'mem-graph') pick('#view .wide > .filters .seg button', 1);
      const ed = view === 'arr' && document.querySelector('[data-f="arr:edit"]'); if (ed) ed.click();
      scrollTo({ top: 0, left: 0, behavior: 'instant' }); }""", [tab, view])
    pg.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


# The layout's boxes: the header, the rail, the view, and every block of every tab (columns, sections, cards, grids), in document
# order, as [x, y, width, height] rounded to the pixel, and the cells of the rows of what needs you and of the tasks. Text inside a
# box is not measured on its own: its lines are the box's height.
BOXES_JS = """() => {
  const S = '.head, #tabs, #view, #view .page, #view .page > *, #view .col > *, #view .wide, #view .wide > *, #view .bd > *, #view .g2 > *, #view .cv > *, #view .gv > *, #view .gv svg, #view .agrid > *, #view .tmap, #view .mini > *, #view .hb, #view .win-f, #view .need > li > *, #view .rows > li > *';
  return Array.from(document.querySelectorAll(S)).filter(e => e.getClientRects().length).map(e => { const r = e.getBoundingClientRect();
    return [Math.round(r.left + scrollX), Math.round(r.top + scrollY), Math.round(r.width), Math.round(r.height)]; }); }"""


def layout_boxes(root, tmp, width):
    """{view: [[x, y, w, h], …]} for every view at WIDTH (a phone at 390)."""
    out = {}
    with screen(root, tmp, wide_data(), width, phone=width < 640) as pg:
        for view in WIDE_VIEWS:
            show(pg, view)
            out[view] = pg.evaluate(BOXES_JS)
        assert not pg.errors, pg.errors
    return out


# Measured with layout_boxes() on main at aa8b0845 (the dash.html of UAK-165, before UAK-198), twice, with the same numbers: the
# screens the human approved, per width and view, "x,y,w,h" per box in document order.
APPROVED_BOXES = {
    "1280": {
        "sum": "0,0,72,900 72,0,1208,53 72,53,1208,1455 72,53,1208,1455 96,69,1160,28 96,113,848,1355 96,113,848,369 110,175,24,24 146,163,524,48 682,173,248,28 110,230,24,24 146,228,516,28 674,228,256,28 110,275,24,24 146,273,516,28 674,273,256,28 110,349,24,24 146,318,568,87 726,347,204,28 97,413,846,68 96,498,848,234 109,551,822,92 96,748,848,450 109,802,96,19 217,797,72,28 301,801,330,20 643,805,112,13 767,803,164,16 109,848,96,19 217,844,72,28 301,848,330,20 643,851,112,13 767,842,164,31 109,896,96,19 217,892,72,28 301,896,330,20 643,899,112,13 767,890,164,31 109,944,96,19 217,940,72,28 301,944,330,20 643,947,112,13 767,938,164,31 109,991,96,19 217,987,72,28 301,991,330,20 643,994,112,13 767,993,164,16 109,1038,96,19 217,1033,72,28 301,1037,330,20 643,1041,112,13 767,1032,164,31 109,1084,96,19 217,1080,72,28 301,1084,330,20 643,1087,112,13 767,1086,164,16 109,1129,96,19 217,1125,72,28 301,1129,330,20 643,1132,112,13 767,1131,164,16 97,1162,846,35 96,1214,848,254 960,113,296,1074 960,113,296,309 960,438,296,285 960,739,296,245 960,999,296,188",
        "arr": "0,0,72,900 72,0,1208,53 72,53,1208,1543 72,53,1208,1543 96,69,1160,116 96,201,848,1355 96,201,848,369 110,263,24,24 146,251,524,48 682,261,248,28 110,318,24,24 146,316,516,28 674,316,256,28 110,363,24,24 146,361,516,28 674,361,256,28 110,437,24,24 146,406,568,87 726,435,204,28 97,501,846,68 96,586,848,234 109,639,822,92 96,836,848,450 109,890,96,19 217,885,72,28 301,889,330,20 643,893,112,13 767,891,164,16 109,936,96,19 217,932,72,28 301,936,330,20 643,939,112,13 767,930,164,31 109,984,96,19 217,980,72,28 301,984,330,20 643,987,112,13 767,978,164,31 109,1032,96,19 217,1028,72,28 301,1032,330,20 643,1035,112,13 767,1026,164,31 109,1079,96,19 217,1075,72,28 301,1079,330,20 643,1082,112,13 767,1081,164,16 109,1126,96,19 217,1121,72,28 301,1125,330,20 643,1129,112,13 767,1120,164,31 109,1172,96,19 217,1168,72,28 301,1172,330,20 643,1175,112,13 767,1174,164,16 109,1217,96,19 217,1213,72,28 301,1217,330,20 643,1220,112,13 767,1219,164,16 97,1250,846,35 96,1302,848,254 960,201,296,1074 960,201,296,309 960,526,296,285 960,827,296,245 960,1087,296,188",
        "board-map": "0,0,72,900 72,0,1208,53 72,53,1208,544 72,53,1208,544 96,69,1160,32 96,113,1160,20 96,133,1160,94 109,186,1134,28 96,239,1160,94 109,292,1134,28 96,345,1160,94 109,398,1134,28 96,451,1160,94 109,504,1134,28",
        "board-cards": "0,0,72,900 72,0,1208,53 72,53,1208,1274 72,53,1208,1274 96,69,1160,32 96,109,1160,1178 96,109,281,1156 389,109,281,1103 682,109,281,1178 975,109,281,724",
        "agents": "0,0,72,900 72,0,1208,53 72,53,1208,1103 72,53,1208,1103 96,69,1160,228 96,109,226,188 330,109,226,188 563,109,226,188 797,109,226,188 96,321,1160,228 96,361,226,188 330,361,226,188 96,573,1160,138 96,613,190,98 290,613,190,98 96,735,1160,138 96,775,190,98 290,775,190,98 484,775,190,98 678,775,190,98 872,775,190,98 1066,775,190,98 96,896,1160,196 96,936,226,156 330,936,226,156",
        "talk": "0,0,72,900 72,0,1208,53 72,53,1208,1100 72,53,1208,1100 96,69,1160,30 96,115,1160,998 96,115,280,445 392,115,584,998 992,115,264,311 993,227,262,70",
        "bb": "0,0,72,900 72,0,1208,53 72,53,1208,875 72,53,1208,875 96,69,1160,30 96,115,1160,24 96,155,1160,278 96,155,572,278 97,196,570,236 684,155,572,204 96,449,1160,439",
        "mem-list": "0,0,72,900 72,0,1208,53 72,53,1208,931 72,53,1208,931 96,69,1160,30 96,115,1160,829 96,115,572,829 684,115,572,785",
        "mem-graph": "0,0,72,900 72,0,1208,53 72,53,1208,738 72,53,1208,738 96,69,1160,30 96,115,1160,28 96,159,1160,592 96,159,763,592 97,160,761,560 875,159,381,399",
        "tokens": "0,0,72,900 72,0,1208,53 72,53,1208,1412 72,53,1208,1412 96,69,1160,174 96,259,1160,517 96,259,376,141 97,300,374,99 488,259,376,168 489,300,374,126 880,259,376,113 881,300,374,71 96,443,1160,333 97,484,1158,291 96,792,1160,549 110,846,96,19 218,842,72,28 302,846,640,20 954,852,112,8 1078,848,164,16 110,891,96,19 218,887,72,28 302,891,640,20 954,897,112,8 1078,893,164,16 110,936,96,19 218,932,72,28 302,936,640,20 954,942,112,8 1078,938,164,16 110,981,96,19 218,977,72,28 302,981,640,20 954,987,112,8 1078,983,164,16 110,1026,96,19 218,1022,72,28 302,1026,640,20 954,1032,112,8 1078,1028,164,16 110,1071,96,19 218,1067,72,28 302,1071,640,20 954,1077,112,8 1078,1073,164,16 110,1116,96,19 218,1112,72,28 302,1116,640,20 954,1122,112,8 1078,1118,164,16 110,1161,96,19 218,1157,72,28 302,1161,640,20 954,1167,112,8 1078,1163,164,16 110,1206,96,19 218,1202,72,28 302,1206,640,20 954,1212,112,8 1078,1208,164,16 110,1251,96,19 218,1247,72,28 302,1251,640,20 954,1257,112,8 1078,1253,164,16 97,1284,1158,56 96,1357,1160,20 96,1392,1160,20",
    },
    "1100": {
        "sum": "0,0,72,900 72,0,1028,53 72,53,1028,2553 72,53,1028,2553 96,69,980,28 96,113,980,1402 96,113,980,417 110,175,24,24 146,163,656,48 814,173,248,28 110,230,24,24 146,228,648,28 806,228,256,28 110,275,24,24 146,273,648,28 806,273,256,28 110,339,24,24 146,318,700,67 858,337,204,28 97,394,978,135 96,546,980,234 109,599,954,92 96,796,980,450 109,849,96,19 217,845,72,28 301,849,462,20 775,852,112,13 899,851,164,16 109,896,96,19 217,891,72,28 301,895,462,20 775,899,112,13 899,890,164,31 109,944,96,19 217,939,72,28 301,944,462,20 775,947,112,13 899,938,164,31 109,992,96,19 217,988,72,28 301,992,462,20 775,995,112,13 899,986,164,31 109,1039,96,19 217,1034,72,28 301,1038,462,20 775,1042,112,13 899,1040,164,16 109,1085,96,19 217,1081,72,28 301,1085,462,20 775,1088,112,13 899,1079,164,31 109,1132,96,19 217,1127,72,28 301,1132,462,20 775,1135,112,13 899,1133,164,16 109,1177,96,19 217,1172,72,28 301,1177,462,20 775,1180,112,13 899,1178,164,16 97,1209,978,35 96,1261,980,254 96,1531,980,1035 96,1531,980,289 96,1836,980,285 96,2137,980,225 96,2378,980,188",
        "arr": "0,0,72,900 72,0,1028,53 72,53,1028,2667 72,53,1028,2667 96,69,980,142 96,227,980,1402 96,227,980,417 110,289,24,24 146,277,656,48 814,287,248,28 110,344,24,24 146,342,648,28 806,342,256,28 110,389,24,24 146,387,648,28 806,387,256,28 110,453,24,24 146,432,700,67 858,451,204,28 97,508,978,135 96,660,980,234 109,713,954,92 96,910,980,450 109,963,96,19 217,959,72,28 301,963,462,20 775,966,112,13 899,965,164,16 109,1010,96,19 217,1005,72,28 301,1009,462,20 775,1013,112,13 899,1004,164,31 109,1058,96,19 217,1053,72,28 301,1058,462,20 775,1061,112,13 899,1052,164,31 109,1106,96,19 217,1102,72,28 301,1106,462,20 775,1109,112,13 899,1100,164,31 109,1153,96,19 217,1148,72,28 301,1152,462,20 775,1156,112,13 899,1154,164,16 109,1199,96,19 217,1195,72,28 301,1199,462,20 775,1202,112,13 899,1193,164,31 109,1246,96,19 217,1241,72,28 301,1246,462,20 775,1249,112,13 899,1247,164,16 109,1291,96,19 217,1286,72,28 301,1291,462,20 775,1294,112,13 899,1292,164,16 97,1323,978,35 96,1375,980,254 96,1645,980,1035 96,1645,980,289 96,1950,980,285 96,2251,980,225 96,2492,980,188",
        "board-map": "0,0,72,900 72,0,1028,53 72,53,1028,576 72,53,1028,576 96,69,980,32 96,113,980,20 96,133,980,94 109,186,954,28 96,239,980,94 109,292,954,28 96,345,980,94 109,398,954,28 96,451,980,126 109,504,954,60",
        "board-cards": "0,0,72,900 72,0,1028,53 72,53,1028,2213 72,53,1028,2213 96,69,980,32 96,109,980,2117 96,109,484,1059 592,109,484,1005 96,1180,484,1046 592,1180,484,707",
        "agents": "0,0,72,900 72,0,1028,53 72,53,1028,1205 72,53,1028,1205 96,69,980,228 96,109,239,188 343,109,239,188 590,109,239,188 837,109,239,188 96,321,980,228 96,361,239,188 343,361,239,188 96,573,980,138 96,613,193,98 293,613,193,98 96,735,980,239 96,775,193,98 293,775,193,98 490,775,193,98 686,775,193,98 883,775,193,98 96,876,193,98 96,998,980,196 96,1038,239,156 343,1038,239,156",
        "talk": "0,0,72,900 72,0,1028,53 72,53,1028,1719 72,53,1028,1719 96,69,980,30 96,115,980,1617 96,115,980,445 96,576,980,882 96,1474,980,258 97,1546,978,56",
        "bb": "0,0,72,900 72,0,1028,53 72,53,1028,875 72,53,1028,875 96,69,980,30 96,115,980,24 96,155,980,278 96,155,482,278 97,196,480,236 594,155,482,204 96,449,980,439",
        "mem-list": "0,0,72,900 72,0,1028,53 72,53,1028,990 72,53,1028,990 96,69,980,30 96,115,980,888 96,115,482,888 594,115,482,843",
        "mem-graph": "0,0,72,900 72,0,1028,53 72,53,1028,650 72,53,1028,650 96,69,980,30 96,115,980,28 96,159,980,504 96,159,643,504 97,160,641,472 755,159,321,399",
        "tokens": "0,0,72,900 72,0,1028,53 72,53,1028,1541 72,53,1028,1541 96,69,980,174 96,259,980,646 96,259,482,141 97,300,480,99 594,259,482,168 595,300,480,126 96,443,482,113 97,484,480,71 96,572,980,333 97,613,978,291 96,921,980,549 110,975,96,19 218,971,72,28 302,975,460,20 774,981,112,8 898,977,164,16 110,1020,96,19 218,1016,72,28 302,1020,460,20 774,1026,112,8 898,1022,164,16 110,1065,96,19 218,1061,72,28 302,1065,460,20 774,1071,112,8 898,1067,164,16 110,1110,96,19 218,1106,72,28 302,1110,460,20 774,1116,112,8 898,1112,164,16 110,1155,96,19 218,1151,72,28 302,1155,460,20 774,1161,112,8 898,1157,164,16 110,1200,96,19 218,1196,72,28 302,1200,460,20 774,1206,112,8 898,1202,164,16 110,1245,96,19 218,1241,72,28 302,1245,460,20 774,1251,112,8 898,1247,164,16 110,1290,96,19 218,1286,72,28 302,1290,460,20 774,1296,112,8 898,1292,164,16 110,1335,96,19 218,1331,72,28 302,1335,460,20 774,1341,112,8 898,1337,164,16 110,1380,96,19 218,1376,72,28 302,1380,460,20 774,1386,112,8 898,1382,164,16 97,1413,978,56 96,1486,980,20 96,1521,980,20",
    },
    "900": {
        "sum": "0,839,900,61 0,0,900,53 0,53,900,3021 0,53,900,3021 24,69,852,28 24,113,852,1870 24,113,852,417 38,175,24,24 74,163,528,48 614,173,248,28 38,230,24,24 74,228,520,28 606,228,256,28 38,275,24,24 74,273,520,28 606,273,256,28 38,339,24,24 74,318,572,67 658,337,204,28 25,394,850,135 24,546,852,234 37,599,826,92 24,796,852,918 37,849,68,19 117,845,746,28 37,877,826,20 37,900,826,13 37,917,826,16 37,954,83,19 132,950,731,28 37,982,826,20 37,1005,826,13 37,1022,826,16 37,1059,83,19 132,1055,731,28 37,1087,826,20 37,1110,826,13 37,1127,826,16 37,1164,83,19 132,1160,731,28 37,1192,826,20 37,1215,826,13 37,1232,826,16 37,1269,83,19 132,1265,731,28 37,1297,826,20 37,1320,826,13 37,1337,826,16 37,1375,83,19 132,1370,731,28 37,1402,826,20 37,1426,826,13 37,1443,826,16 37,1480,98,19 147,1475,716,28 37,1507,826,20 37,1531,826,13 37,1548,826,16 37,1585,98,19 147,1580,716,28 37,1612,826,20 37,1636,826,13 37,1653,826,16 25,1677,850,35 24,1729,852,254 24,1999,852,1035 24,1999,852,289 24,2304,852,285 24,2605,852,225 24,2846,852,188",
        "arr": "0,839,900,61 0,0,900,53 0,53,900,3135 0,53,900,3135 24,69,852,142 24,227,852,1870 24,227,852,417 38,289,24,24 74,277,528,48 614,287,248,28 38,344,24,24 74,342,520,28 606,342,256,28 38,389,24,24 74,387,520,28 606,387,256,28 38,453,24,24 74,432,572,67 658,451,204,28 25,508,850,135 24,660,852,234 37,713,826,92 24,910,852,918 37,963,68,19 117,959,746,28 37,991,826,20 37,1014,826,13 37,1031,826,16 37,1068,83,19 132,1064,731,28 37,1096,826,20 37,1119,826,13 37,1136,826,16 37,1173,83,19 132,1169,731,28 37,1201,826,20 37,1224,826,13 37,1241,826,16 37,1278,83,19 132,1274,731,28 37,1306,826,20 37,1329,826,13 37,1346,826,16 37,1383,83,19 132,1379,731,28 37,1411,826,20 37,1434,826,13 37,1451,826,16 37,1489,83,19 132,1484,731,28 37,1516,826,20 37,1540,826,13 37,1557,826,16 37,1594,98,19 147,1589,716,28 37,1621,826,20 37,1645,826,13 37,1662,826,16 37,1699,98,19 147,1694,716,28 37,1726,826,20 37,1750,826,13 37,1767,826,16 25,1791,850,35 24,1843,852,254 24,2113,852,1035 24,2113,852,289 24,2418,852,285 24,2719,852,225 24,2960,852,188",
        "board-map": "0,839,900,61 0,0,900,53 0,53,900,576 0,53,900,576 24,69,852,32 24,113,852,20 24,133,852,94 37,186,826,28 24,239,852,94 37,292,826,28 24,345,852,94 37,398,826,28 24,451,852,126 37,504,826,60",
        "board-cards": "0,839,900,61 0,0,900,53 0,53,900,2252 0,53,900,2252 24,69,852,32 24,109,852,2156 24,109,420,1078 456,109,420,1005 24,1199,420,1066 456,1199,420,712",
        "agents": "0,839,900,61 0,0,900,53 0,53,900,1318 0,53,900,1318 24,69,852,381 24,109,279,169 311,109,279,169 597,109,279,169 24,286,279,164 24,474,852,209 24,514,279,169 311,514,279,169 24,706,852,138 24,746,210,98 238,746,210,98 24,868,852,239 24,908,210,98 238,908,210,98 452,908,210,98 666,908,210,98 24,1009,210,98 238,1009,210,98 24,1131,852,177 24,1171,279,137 311,1171,279,137",
        "talk": "0,839,900,61 0,0,900,53 0,53,900,1719 0,53,900,1719 24,69,852,30 24,115,852,1617 24,115,852,445 24,576,852,882 24,1474,852,258 25,1546,850,56",
        "bb": "0,839,900,61 0,0,900,53 0,53,900,903 0,53,900,903 24,69,852,30 24,115,852,52 24,183,852,278 24,183,418,278 25,224,416,236 458,183,418,223 24,477,852,439",
        "mem-list": "0,839,900,61 0,0,900,53 0,53,900,1087 0,53,900,1087 24,69,852,30 24,115,852,985 24,115,418,985 458,115,418,921",
        "mem-graph": "0,839,900,61 0,0,900,53 0,53,900,587 0,53,900,587 24,69,852,30 24,115,852,28 24,159,852,441 24,159,557,441 25,160,555,409 597,159,279,399",
        "tokens": "0,839,900,61 0,0,900,53 0,53,900,2092 0,53,900,2092 24,69,852,174 24,259,852,646 24,259,418,141 25,300,416,99 458,259,418,168 459,300,416,126 24,443,418,113 25,484,416,71 24,572,852,333 25,613,850,291 24,921,852,1100 38,975,90,19 140,971,722,28 38,1003,824,20 38,1026,90,8 38,1038,824,16 38,1075,83,19 133,1071,729,28 38,1103,824,20 38,1126,83,8 38,1138,824,16 38,1175,90,19 140,1171,722,28 38,1203,824,20 38,1226,90,8 38,1238,824,16 38,1275,90,19 140,1271,722,28 38,1303,824,20 38,1326,90,8 38,1338,824,16 38,1375,90,19 140,1371,722,28 38,1403,824,20 38,1426,90,8 38,1438,824,16 38,1475,90,19 140,1471,722,28 38,1503,824,20 38,1526,90,8 38,1538,824,16 38,1576,90,19 140,1571,722,28 38,1603,824,20 38,1627,90,8 38,1639,824,16 38,1676,90,19 140,1671,722,28 38,1703,824,20 38,1727,90,8 38,1739,824,16 38,1776,83,19 133,1771,729,28 38,1803,824,20 38,1827,83,8 38,1839,824,16 38,1876,90,19 140,1871,722,28 38,1903,824,20 38,1927,90,8 38,1939,824,16 25,1963,850,56 24,2037,852,20 24,2072,852,20",
    },
    "640": {
        "sum": "0,839,640,61 0,0,640,121 0,121,640,3658 0,121,640,3658 16,137,608,44 16,197,608,2468 16,197,608,732 30,267,24,24 66,247,544,64 30,323,580,46 30,396,24,24 66,386,544,44 30,442,580,46 30,515,24,24 66,505,544,44 30,561,580,46 30,663,24,24 66,624,544,103 30,738,580,46 17,793,606,135 16,945,608,282 29,998,582,140 16,1243,608,1140 29,1371,68,19 109,1358,502,44 29,1406,582,20 29,1430,582,13 29,1447,582,16 29,1492,83,19 124,1479,487,44 29,1527,582,39 29,1570,582,13 29,1587,582,16 29,1632,83,19 124,1620,487,44 29,1668,582,20 29,1691,582,13 29,1708,582,16 29,1753,83,19 124,1741,487,44 29,1789,582,20 29,1812,582,13 29,1829,582,16 29,1874,83,19 124,1862,487,44 29,1910,582,20 29,1933,582,13 29,1950,582,16 29,1996,83,19 124,1983,487,44 29,2031,582,20 29,2055,582,13 29,2072,582,16 29,2117,98,19 139,2104,472,44 29,2152,582,20 29,2176,582,13 29,2193,582,16 29,2238,98,19 139,2225,472,44 29,2273,582,20 29,2297,582,13 29,2314,582,16 17,2338,606,44 16,2399,608,266 16,2681,608,1058 16,2681,608,289 16,2986,608,294 16,3296,608,239 16,3551,608,188",
        "arr": "0,839,640,61 0,0,640,121 0,121,640,3794 0,121,640,3794 16,137,608,176 16,329,608,2438 16,329,608,744 30,411,24,24 66,391,544,64 30,467,580,46 30,540,24,24 66,530,544,44 30,586,580,46 30,659,24,24 66,649,544,44 30,705,580,46 30,807,24,24 66,768,544,103 30,882,580,46 17,937,606,135 16,1089,608,294 29,1154,582,140 16,1399,608,1086 29,1473,68,19 109,1460,502,44 29,1508,582,20 29,1532,582,13 29,1549,582,16 29,1594,83,19 124,1581,487,44 29,1629,582,39 29,1672,582,13 29,1689,582,16 29,1734,83,19 124,1722,487,44 29,1770,582,20 29,1793,582,13 29,1810,582,16 29,1855,83,19 124,1843,487,44 29,1891,582,20 29,1914,582,13 29,1931,582,16 29,1976,83,19 124,1964,487,44 29,2012,582,20 29,2035,582,13 29,2052,582,16 29,2098,83,19 124,2085,487,44 29,2133,582,20 29,2157,582,13 29,2174,582,16 29,2219,98,19 139,2206,472,44 29,2254,582,20 29,2278,582,13 29,2295,582,16 29,2340,98,19 139,2327,472,44 29,2375,582,20 29,2399,582,13 29,2416,582,16 17,2440,606,44 16,2501,608,266 16,2783,608,1092 16,2783,608,301 16,3100,608,306 16,3422,608,237 16,3675,608,200",
        "board-map": "0,839,640,61 0,0,640,121 0,121,640,698 0,121,640,698 16,137,608,98 16,247,608,20 16,267,608,98 29,320,582,32 16,377,608,98 29,430,582,32 16,487,608,98 29,540,582,32 16,597,608,170 29,650,582,104",
        "board-cards": "0,839,640,61 0,0,640,121 0,121,640,4339 0,121,640,4339 16,137,608,98 16,243,608,4177 16,243,608,1156 16,1411,608,1059 16,2481,608,1107 16,3600,608,821",
        "agents": "0,839,640,61 0,0,640,121 0,121,640,1443 0,121,640,1443 16,137,608,425 16,177,300,189 324,177,300,189 16,374,300,189 324,374,300,189 16,586,608,229 16,626,300,189 324,626,300,189 16,839,608,158 16,879,200,118 220,879,200,118 16,1020,608,279 16,1060,200,118 220,1060,200,118 424,1060,200,118 16,1182,200,118 220,1182,200,118 424,1182,200,118 16,1323,608,177 16,1363,300,137 324,1363,300,137",
        "talk": "0,839,640,61 0,0,640,121 0,121,640,1955 0,121,640,1955 16,137,608,98 16,251,608,1785 16,251,608,445 16,712,608,1050 16,1778,608,258 17,1850,606,56",
        "bb": "0,839,640,61 0,0,640,121 0,121,640,1222 0,121,640,1222 16,137,608,98 16,251,608,92 16,359,608,480 16,359,608,278 17,400,606,236 16,653,608,186 16,855,608,448",
        "mem-list": "0,839,640,61 0,0,640,121 0,121,640,1855 0,121,640,1855 16,137,608,46 16,199,608,1737 16,199,608,947 16,1162,608,774",
        "mem-graph": "0,839,640,61 0,0,640,121 0,121,640,1136 0,121,640,1136 16,137,608,46 16,199,608,148 16,363,608,854 16,363,608,479 17,364,606,447 16,858,608,359",
        "tokens": "0,839,640,61 0,0,640,121 0,121,640,2564 0,121,640,2564 16,137,608,174 16,327,608,803 16,327,608,141 17,368,606,99 16,483,608,168 17,524,606,126 16,667,608,113 17,708,606,71 16,796,608,333 17,837,606,291 16,1145,608,1416 30,1208,90,19 132,1195,478,44 30,1243,580,20 30,1267,90,8 30,1279,580,16 30,1324,83,19 125,1311,485,44 30,1359,580,20 30,1383,83,8 30,1395,580,16 30,1440,90,19 132,1427,478,44 30,1475,580,39 30,1518,90,8 30,1530,580,16 30,1575,90,19 132,1563,478,44 30,1611,580,39 30,1654,90,8 30,1666,580,16 30,1711,90,19 132,1698,478,44 30,1746,580,39 30,1789,90,8 30,1801,580,16 30,1846,90,19 132,1834,478,44 30,1882,580,39 30,1925,90,8 30,1937,580,16 30,1982,90,19 132,1970,478,44 30,2018,580,39 30,2061,90,8 30,2073,580,16 30,2118,90,19 132,2105,478,44 30,2153,580,39 30,2196,90,8 30,2208,580,16 30,2253,83,19 125,2241,485,44 30,2289,580,39 30,2332,83,8 30,2344,580,16 30,2389,90,19 132,2376,478,44 30,2424,580,39 30,2467,90,8 30,2479,580,16 17,2504,606,56 16,2577,608,20 16,2613,608,20",
    },
    "390": {
        "sum": "0,783,390,61 0,0,390,121 0,121,390,4042 0,121,390,4042 16,137,358,44 16,197,358,2853 16,197,358,849 30,286,24,24 66,247,294,103 30,362,330,46 30,444,24,24 66,425,294,64 30,500,330,46 30,583,24,24 66,563,294,64 30,639,330,46 30,760,24,24 66,702,294,142 30,855,330,46 17,910,356,135 16,1062,358,426 29,1115,332,248 16,1504,358,1242 29,1655,68,19 109,1643,252,44 29,1691,332,20 29,1714,332,13 29,1731,332,16 29,1776,83,19 124,1764,237,44 29,1812,332,39 29,1855,332,13 29,1872,332,16 29,1917,83,19 124,1904,237,44 29,1952,332,39 29,1995,332,13 29,2012,332,16 29,2057,83,19 124,2045,237,44 29,2093,332,20 29,2116,332,13 29,2133,332,16 29,2178,83,19 124,2166,237,44 29,2214,332,39 29,2257,332,13 29,2274,332,16 29,2319,83,19 124,2307,237,44 29,2355,332,39 29,2398,332,13 29,2415,332,16 29,2460,98,19 139,2447,222,44 29,2495,332,39 29,2538,332,13 29,2555,332,16 29,2600,98,19 139,2588,222,44 29,2636,332,20 29,2659,332,13 29,2676,332,16 17,2701,356,44 16,2762,358,288 16,3066,358,1058 16,3066,358,289 16,3371,358,294 16,3681,358,239 16,3936,358,188",
        "arr": "0,783,390,61 0,0,390,121 0,121,390,4191 0,121,390,4191 16,137,358,212 16,365,358,2799 16,365,358,861 30,466,24,24 66,427,294,103 30,542,330,46 30,624,24,24 66,605,294,64 30,680,330,46 30,763,24,24 66,743,294,64 30,819,330,46 30,940,24,24 66,882,294,142 30,1035,330,46 17,1090,356,135 16,1242,358,438 29,1307,332,248 16,1696,358,1164 29,1770,68,19 109,1757,252,44 29,1805,332,20 29,1829,332,13 29,1846,332,16 29,1891,83,19 124,1878,237,44 29,1926,332,39 29,1969,332,13 29,1986,332,16 29,2031,83,19 124,2019,237,44 29,2067,332,39 29,2110,332,13 29,2127,332,16 29,2172,83,19 124,2159,237,44 29,2207,332,20 29,2231,332,13 29,2248,332,16 29,2293,83,19 124,2280,237,44 29,2328,332,39 29,2371,332,13 29,2388,332,16 29,2434,83,19 124,2421,237,44 29,2469,332,39 29,2512,332,13 29,2529,332,16 29,2574,98,19 139,2562,222,44 29,2610,332,39 29,2653,332,13 29,2670,332,16 29,2715,98,19 139,2702,222,44 29,2750,332,20 29,2774,332,13 29,2791,332,16 17,2815,356,44 16,2876,358,288 16,3180,358,1092 16,3180,358,301 16,3497,358,306 16,3819,358,237 16,4072,358,200",
        "board-map": "0,783,390,61 0,0,390,121 0,121,390,794 0,121,390,794 16,137,358,122 16,271,358,20 16,291,358,134 29,344,332,68 16,437,358,98 29,490,332,32 16,547,358,98 29,600,332,32 16,657,358,206 29,710,332,140",
        "board-cards": "0,783,390,61 0,0,390,121 0,121,390,4634 0,121,390,4634 16,137,358,122 16,267,358,4449 16,267,358,1253 16,1532,358,1156 16,2700,358,1183 16,3895,358,821",
        "agents": "0,783,390,61 0,0,390,121 0,121,390,2249 0,121,390,2249 16,137,358,794 16,177,358,189 16,374,358,189 16,570,358,189 16,767,358,164 16,955,358,401 16,995,358,164 16,1167,358,189 16,1379,358,158 16,1419,177,118 197,1419,177,118 16,1561,358,401 16,1601,177,118 197,1601,177,118 16,1722,177,118 197,1722,177,118 16,1844,177,118 197,1844,177,118 16,1985,358,321 16,2025,358,137 16,2170,358,137",
        "talk": "0,783,390,61 0,0,390,121 0,121,390,2064 0,121,390,2064 16,137,358,98 16,251,358,1894 16,251,358,445 16,712,358,1125 16,1853,358,292 17,1945,356,70",
        "bb": "0,783,390,61 0,0,390,121 0,121,390,1307 0,121,390,1307 16,137,358,98 16,251,358,140 16,407,358,517 16,407,358,278 17,448,356,236 16,701,358,223 16,940,358,448",
        "mem-list": "0,783,390,61 0,0,390,121 0,121,390,2401 0,121,390,2401 16,137,358,46 16,199,358,2283 16,199,358,1220 16,1435,358,1047",
        "mem-graph": "0,783,390,61 0,0,390,121 0,121,390,2428 0,121,390,2428 16,137,358,74 16,227,358,2283 16,227,358,1220 16,1462,358,1047",
        "tokens": "0,783,390,61 0,0,390,121 0,121,390,2715 0,121,390,2715 16,137,358,193 16,346,358,803 16,346,358,141 17,387,356,99 16,503,358,168 17,544,356,126 16,687,358,113 17,728,356,71 16,816,358,333 17,857,356,291 16,1165,358,1528 30,1227,90,19 132,1215,228,44 30,1263,330,20 30,1286,90,8 30,1298,330,16 30,1343,83,19 125,1331,235,44 30,1379,330,20 30,1402,83,8 30,1414,330,16 30,1459,90,19 132,1447,228,44 30,1495,330,59 30,1557,90,8 30,1569,330,16 30,1614,90,19 132,1602,228,44 30,1650,330,59 30,1712,90,8 30,1724,330,16 30,1769,90,19 132,1757,228,44 30,1805,330,59 30,1867,90,8 30,1879,330,16 30,1924,90,19 132,1912,228,44 30,1960,330,59 30,2022,90,8 30,2034,330,16 30,2080,90,19 132,2067,228,44 30,2115,330,59 30,2178,90,8 30,2190,330,16 30,2235,90,19 132,2222,228,44 30,2270,330,39 30,2313,90,8 30,2325,330,16 30,2370,83,19 125,2358,235,44 30,2406,330,39 30,2449,83,8 30,2461,330,16 30,2506,90,19 132,2493,228,44 30,2541,330,39 30,2584,90,8 30,2596,330,16 17,2621,356,70 16,2708,358,20 16,2744,358,39",
    },
}


def layout_is_unchanged_at_1280_and_below(root, tmp):
    """At 1280, 1100, 900, 640 and 390 px every box of every tab (the header, the rail, the columns, every block, card and grid) is
    where it was and as big as it was on the screens the human approved: the same numbers as main before UAK-198, within a pixel."""
    for width in (1280, 1100, 900, 640, 390):
        got = layout_boxes(root, tmp, width)
        for view in WIDE_VIEWS:
            want = [[int(n) for n in b.split(",")] for b in APPROVED_BOXES[str(width)][view].split()]
            have = got[view]
            assert len(have) == len(want), "%d px, %s: %d boxes, the approved screen has %d: %r" % (width, view, len(have), len(want), have)
            bad = [(i, a, b) for i, (a, b) in enumerate(zip(have, want)) if any(abs(x - y) > 1 for x, y in zip(a, b))]
            assert not bad, "%d px, %s: boxes moved (index, now, approved): %r" % (width, view, bad[:6])
    return "browser"


RIGHT_JS = """() => { const v = document.getElementById('view'), W = document.documentElement.clientWidth;
  const els = Array.from(v.querySelectorAll('.card, .list, .win, .bh, .ac, .filters, .page > .col > *, .page > .arrbar')).filter(e => e.getClientRects().length);
  const right = Math.max(...els.map(e => e.getBoundingClientRect().right));
  const ctl = Array.from(document.querySelectorAll('.head > *')).filter(e => e.getClientRects().length).map(e => e.getBoundingClientRect().right);
  return { W: W, right: Math.round(right), head: Math.round(Math.max(...ctl)), scroll: document.documentElement.scrollWidth }; }"""


def content_reaches_the_right_edge_on_wide_screens(root, tmp):
    """At 1440, 1920 and 2560 px every view of every tab reaches within 32 px of the window's right edge and never past it, the
    header's controls end at the right edge, the summary's side column is at the right, and a task's detail opens against the
    right edge, as tall as the window and as wide as 760 px scaled, while Share opens centred inside the window."""
    for width in (1440, 1920, 2560):
        with screen(root, tmp, wide_data(), width) as pg:
            for view in WIDE_VIEWS:
                show(pg, view)
                m = pg.evaluate(RIGHT_JS)
                assert width - 32 <= m["right"] <= width and m["scroll"] <= width, "%d px, %s: the content ends at %d px (an empty band of %d px), or past the window: %r" % (width, view, m["right"], width - m["right"], m)
                assert width - 32 <= m["head"] <= width, "%d px, %s: the header's controls end at %d px" % (width, view, m["head"])
            show(pg, "sum")
            side = pg.evaluate("Math.round(document.querySelector('#view .col[data-col=side]').getBoundingClientRect().right)")
            assert side >= width - 32, "%d px: the side column ends at %d" % (width, side)
            pg.evaluate("document.querySelector('#view .rows [data-story]').click()")
            pg.wait_for_function("document.getElementById('story').open")
            st = pg.evaluate("(() => { const r = document.getElementById('story').getBoundingClientRect(); return [r.left, r.right, r.width, r.top, r.bottom, innerHeight, wideScale_z()]; })()".replace("wideScale_z()", "parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--z')) || 1"))
            assert abs(st[1] - width) <= 1 and abs(st[2] - 760 * st[6]) <= 2 and abs(st[3]) <= 1 and abs(st[4] - st[5]) <= 2, "%d px: the task's detail sits against the right edge, as tall as the window: %r" % (width, st)
            pg.keyboard.press("Escape")
            pg.wait_for_function("!document.getElementById('story').open")
            pg.evaluate("document.getElementById('share-btn').click()")
            pg.wait_for_function("document.getElementById('share').open")
            sh = pg.evaluate("(() => { const r = document.getElementById('share').getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom, innerHeight]; })()")
            assert sh[0] >= 0 and sh[1] <= width and abs(sh[0] - (width - sh[1])) <= 2 and sh[2] >= 0 and sh[3] <= sh[4], "%d px: Share is centred in the window: %r" % (width, sh)
            pg.keyboard.press("Escape")
            assert not pg.errors, pg.errors
    return "browser"


LINES_JS = """() => { document.querySelectorAll('#view details').forEach(d => { d.open = true; });   // what a person can open, open
  const out = [], w = document.createTreeWalker(document.getElementById('view'), NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) { const t = n.nodeValue; if (t.trim().length < 90) continue; const p = n.parentElement;
    if (!p.getClientRects().length || p.closest('code, .cmd') || /nowrap|pre$/.test(getComputedStyle(p).whiteSpace)) continue;   // a command is not prose
    if (p.checkVisibility && !p.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true })) continue;
    const r = document.createRange(), lines = {}; let at = null;
    for (let i = 0; i < t.length; i++) { if (/\\s/.test(t[i])) { if (at !== null) lines[at]++; continue; }
      r.setStart(n, i); r.setEnd(n, i + 1); const b = r.getClientRects()[0]; if (!b || !b.width) continue; at = Math.round(b.top); lines[at] = (lines[at] || 0) + 1; }
    const tops = Object.keys(lines); if (!tops.length) continue;
    out.push([Math.max(...tops.map(k => lines[k])), t.trim().slice(0, 50)]); }
  return out.filter(x => x[0] > 95); }"""


ZOOM_JS = "parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--z')) || 1"


def wide_screens_scale_up_not_stretch(root, tmp):
    """The human's choice (A): a wide window scales the approved page up instead of stretching it. The rule, pure, under node: the
    scale is 1 up to 1432 px, then the window's width over 1432 (continuous: 1433 px is 1.001), at most 1.8, so a 3840 px window
    is not absurd; past the cap the summary's side gains columns (sumCols). In Chromium at 1920 and 2560 px: every box of every
    view is the box of the 1432 px page times the scale (the composition approved at 1280 px, drawn larger, the squares
    28 px times the scale); a task row's status sits next to its title and the row is no wider than its columns; no line of
    running text is over about 90 characters (95, spaces counted). What places itself with the pointer or the window's
    coordinates still lands right in the zoomed page: the task's list box opens under its button, a square's tip sits at the
    pointer, a node of the memory graph is chosen where it is clicked, Share exports the same two PNG images as at 1280 px, and
    in arrange mode at 2560 px the moved component follows the pointer, the drop line shows where it lands and it lands there.
    The viewer's arrangement means the same at every width: what is kept is the two lists and the hidden ones, never a scale or a
    column count, and an arrangement saved before UAK-198 is drawn as saved."""
    out = truth.under_node(root, """return [wideScale(1280), wideScale(1432), wideScale(1433), wideScale(1920), wideScale(2560), wideScale(2578), wideScale(3840), wideScale(NaN),
      sumCols(1312, 4, 4), sumCols(2013, 4, 4), sumCols(2013, 4, 1), sumCols(2013, 8, 0), graphBox(763, 900, 500, 400), graphBox(1316, 1080, 300, 60)];""")
    if out is not None:
        assert out[0] == 1 and out[1] == 1 and out[7] == 1, "no scale up to 1432 px: %r" % out[:2]
        assert 1 < out[2] <= 1.001 and out[3] == 1.341 and out[4] == 1.788 and out[5] == 1.8 and out[6] == 1.8, "the width over 1432, continuous, at most 1.8: %r" % out[2:7]
        assert out[8] == {"flow": 1, "side": 1, "w": 296}, "the approved summary at the 1432 px layout: %r" % out[8]
        assert out[9]["side"] == 2 and out[10]["side"] == 1 and out[11]["flow"] == 2, "past the cap, columns: %r" % out[9:12]
        assert out[12] == {"W": 760, "H": 560} and out[13]["H"] < 560, "the graph's canvas: %r" % out[12:]
    # The composition: at 1920 and 2560 px every box is where the 1432 px page has it, and as wide, times the scale (the window
    # as tall in page units; the side gutters are 24 px on the screen at every scale, so the 1432 px page gets the same gutters).
    # Heights are not compared: a line of text set at 17 px may wrap a word earlier than the same line at 13 px.
    for width, height in ((1920, 1080), (2560, 1440)):
        z = round(width / 1432.0, 3)
        base = {}
        with screen(root, tmp, wide_data(), 1432, height=int(round(height / z))) as pg:
            pg.add_style_tag(content=".head, .page, .wide { padding-left: %.4fpx !important; padding-right: %.4fpx !important; }" % (24 / z, 24 / z))
            for view in WIDE_VIEWS:
                show(pg, view)
                base[view] = pg.evaluate(BOXES_JS)
        with screen(root, tmp, wide_data(), width, height=height) as pg:
            assert abs(pg.evaluate(ZOOM_JS) - z) < 0.0005, "the page's scale at %d px: %r" % (width, pg.evaluate(ZOOM_JS))
            for view in WIDE_VIEWS:
                show(pg, view)
                got = pg.evaluate(BOXES_JS)
                assert len(got) == len(base[view]), "%d px, %s: %d boxes, %d at 1432 px" % (width, view, len(got), len(base[view]))
                bad = [(i, a, b) for i, (a, b) in enumerate(zip(got, base[view])) if abs(a[0] / z - b[0]) > 2 or abs(a[2] / z - b[2]) > 2]
                assert not bad, "%d px, %s: a box is not where the 1432 px page has it, times %.3f (index, here, at 1432): %r" % (width, view, z, bad[:4])
            show(pg, "sum")
            sq = pg.evaluate("document.querySelector('#view .b-map .sq').getBoundingClientRect().width")
            assert abs(sq - 28 * z) <= 1, "%d px: a square is 28 px times the scale: %r" % (width, sq)
            rows = pg.evaluate("""() => Array.from(document.querySelectorAll('#view .b-tasks .rows > li[data-story]')).map(li => { const t = li.querySelector('.t').getBoundingClientRect(),
              p = li.querySelector('.pipe').getBoundingClientRect(), w = li.querySelector('.w').getBoundingClientRect(), a = li.firstElementChild.getBoundingClientRect();
              return { gap: Math.round(p.left - t.right), used: Math.round(w.right - a.left) }; })""")
            assert rows and all(r["gap"] <= 12 * z + 2 and r["used"] <= 975 * z for r in rows), "%d px: a row's status next to its title: %r" % (width, rows[:3])
            for view in WIDE_VIEWS:
                show(pg, view)
                long = pg.evaluate(LINES_JS)
                assert not long, "%d px, %s: lines of running text over about 90 characters: %r" % (width, view, long[:4])
            # what is placed with the window's coordinates
            show(pg, "bb")
            lb = pg.evaluate("""() => new Promise(done => { const b = document.querySelector('#view .lbb'); b.click(); requestAnimationFrame(() => {
              const p = document.querySelector('#view .lbp:not([hidden])').getBoundingClientRect(), r = b.getBoundingClientRect(); done([r.left, r.bottom, p.left, p.top]); }); })""")
            assert abs(lb[2] - lb[0]) <= 2 and 0 <= lb[3] - lb[1] <= 6 * z + 2, "%d px: the list box opens under its button: %r" % (width, lb)
            pg.keyboard.press("Escape")
            show(pg, "sum")
            sq = pg.locator("#view .b-map .sq").nth(5).bounding_box()
            pg.mouse.move(sq["x"] + sq["width"] / 2, sq["y"] + sq["height"] / 2)
            pg.mouse.move(sq["x"] + sq["width"] / 2 + 2, sq["y"] + sq["height"] / 2 + 1)
            pg.wait_for_function("document.getElementById('tip').className === 'on'")
            tip = pg.evaluate("(() => { const r = document.getElementById('tip').getBoundingClientRect(); return [r.left, r.top]; })()")
            px, py = sq["x"] + sq["width"] / 2 + 2, sq["y"] + sq["height"] / 2 + 1
            assert abs(tip[0] - (px + 12)) <= 2 or tip[0] + 12 <= px, "%d px: the tip sits at the pointer: %r %r" % (width, tip, (px, py))
            pg.mouse.move(5, 5)
            show(pg, "mem-graph")
            node = pg.locator("#view svg.mg .gn.n-task").first.bounding_box()
            pg.mouse.click(node["x"] + node["width"] / 2, node["y"] + node["height"] / 2)
            pg.wait_for_function("document.querySelector('#view svg.mg .gn.sel')")
            assert not pg.errors, pg.errors
    # Share exports the same images at every scale
    cards = {}
    for width in (1280, 1920, 2560):
        with screen(root, tmp, wide_data(), width) as pg:
            pg.evaluate("document.getElementById('share-btn').click()")
            pg.wait_for_function("document.querySelectorAll('#share img.share-img').length === 2")
            cards[width] = pg.evaluate("""async () => { const im = Array.from(document.querySelectorAll('#share img.share-img')); await Promise.all(im.map(i => i.decode()));
              return im.map(i => [i.naturalWidth, i.naturalHeight, i.src]); }""")
    assert cards[1280][0][:2] == [1200, 630] and cards[1280][1][:2] == [1080, 1920], "the two cards' sizes: %r" % [c[:2] for c in cards[1280]]
    assert cards[1920] == cards[1280] and cards[2560] == cards[1280], "Share exports the same PNG at every scale"
    # arrange mode at 2560: buttons, crossing and a drag that lands where the line shows
    with screen(root, tmp, wide_data(), 2560) as pg:
        edit(pg)
        press(pg, '[data-f="tasks:up"]')
        pg.wait_for_function("document.querySelector('#view .col[data-col=main]').children[1].getAttribute('data-blk') === 'tasks'")
        press(pg, '[data-f="tokens:col"]')
        pg.wait_for_function("document.querySelector('#view .col[data-col=main] .arr[data-blk=tokens]')")
        pg.evaluate("scrollTo({ top: Math.min(document.querySelector('[data-grip=pace]').getBoundingClientRect().top, document.querySelector('#view .arr[data-blk=map]').getBoundingClientRect().top) + scrollY - 60, behavior: 'instant' })")
        src, dst = pg.locator('[data-grip="pace"]').bounding_box(), pg.locator('#view .arr[data-blk="map"]').bounding_box()
        assert 0 <= src["y"] < 1380 and 0 <= dst["y"] < 1380, "both ends of the drag are on screen: %r %r" % (src, dst)
        pg.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
        pg.mouse.down()
        tx, ty = dst["x"] + 40, dst["y"] + 4
        for k in range(1, 9):
            pg.mouse.move(src["x"] + src["width"] / 2 + (tx - src["x"] - src["width"] / 2) * k / 8, src["y"] + src["height"] / 2 + (ty - src["y"] - src["height"] / 2) * k / 8)
        pg.wait_for_function("document.querySelector('.dropline')")
        mid = pg.evaluate("""() => { const l = document.querySelector('.dropline').getBoundingClientRect(), g = document.querySelector('[data-grip=pace]').getBoundingClientRect(),
          m = document.querySelector('#view .arr[data-blk=map]').getBoundingClientRect(); return { line: l.top, map: m.top, gx: g.left + g.width / 2, gy: g.top + g.height / 2 }; }""")
        assert -24 <= mid["line"] - mid["map"] <= 0, "the drop line shows the place above map: %r" % mid
        assert abs(mid["gx"] - tx) <= 6 and abs(mid["gy"] - ty) <= 6, "the moved component follows the pointer: %r %r" % (mid, (tx, ty))
        pg.mouse.up()
        pg.wait_for_function("document.querySelector('#view .col[data-col=main] .arr[data-blk=pace]')")
        lay = layout_in(pg)
        assert lay["main"].index("pace") == lay["main"].index("map") - 1 and "tokens" in lay["main"], "it lands where the line showed: %r" % lay
        kept = json.loads(pg.evaluate("(k) => localStorage.getItem(k)", KEY))
        assert sorted(kept) == ["hide", "main", "side"] and kept["main"] == lay["main"], "what is kept is the two lists and the hidden ones: %r" % kept
        assert not pg.errors, pg.errors
    old = {"main": ["needs", "lanes", "tasks"], "side": ["tokens", "progress", "map", "agents"], "hide": ["pace"]}
    with screen(root, tmp, wide_data(), 1920, seed={KEY: json.dumps(old)}) as pg:
        assert layout_in(pg) == {"main": old["main"], "side": old["side"]}, "an arrangement saved before UAK-198 is drawn as saved: %r" % layout_in(pg)
        assert pg.evaluate("(k) => localStorage.getItem(k)", KEY) == json.dumps(old), "and kept as it was: nothing about the width is added"
        assert not pg.errors, pg.errors
    return "browser"


# What sticks out of its column on the summary (a column 296 px wide holding a block made for the main one).
SPILL_JS = """() => Array.from(document.querySelectorAll('#view .col[data-col]')).flatMap(c => { const R = c.getBoundingClientRect().right;
  return Array.from(c.querySelectorAll('*')).filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > R + 6; }).map(e => c.getAttribute('data-col') + ': ' + e.tagName + '.' + e.className + ' ' + (e.textContent || '').slice(0, 30)); })"""
SCROLL_JS = """() => { const d = document.documentElement, ctl = Array.from(document.querySelectorAll('.head > *')).filter(e => e.getClientRects().length).map(e => e.getBoundingClientRect().right);
  return { sw: d.scrollWidth, cw: d.clientWidth, head: Math.round(Math.max(...ctl)) }; }"""


def no_sideways_scroll_from_320_to_3840(root, tmp):
    """From 320 to 3840 px no view of any tab scrolls sideways and the header's controls end at the window's right edge; the same
    with no task, one task, 300 tasks, 4 and 40 agents, with every side block hidden, with every block in the main column or in the
    side, with what needs you in the side (arranging too: on main it pushed a 296 px side past the window at 1280 px), at browser
    zoom 67 % to 175 % of a 1920 px screen, and at 1920 px zoomed to 200 % (960 px of CSS), where the page is the 960 px page."""
    for width in (320, 360, 390, 414, 640, 768, 900, 1024, 1100, 1280, 1366, 1440, 1600, 1920, 2560, 3840):
        with screen(root, tmp, wide_data(), width, phone=width < 640) as pg:
            for view in WIDE_VIEWS:
                show(pg, view)
                m = pg.evaluate(SCROLL_JS)
                assert m["sw"] <= m["cw"], "%d px, %s: the page scrolls sideways (%d > %d)" % (width, view, m["sw"], m["cw"])
                assert width - 32 <= m["head"] <= width, "%d px, %s: the header's controls end at %d" % (width, view, m["head"])
            assert not pg.errors, pg.errors
    names = [n for n, _ in ORDER]
    edges = [("empty", None), ("one", None), ("300", None), ("4 agents", None), ("40 agents", None),
             ("every side block hidden", {"main": names[:4], "side": [], "hide": names[4:]}), ("all in main", {"main": names, "side": [], "hide": []}), ("all in the side", {"main": [], "side": names, "hide": []}),
             ("what needs you in the side", {"main": ["map", "tasks", "lanes"], "side": ["needs", "progress", "agents", "pace", "tokens"], "hide": []})]
    for name, arr in edges:
        data = wide_data() if arr else wide_data_named(name)
        for width in (320, 1920, 3840):
            with screen(root, tmp, data, width, phone=width < 640, seed={KEY: json.dumps(arr)} if arr else None) as pg:
                for view in WIDE_VIEWS:
                    show(pg, view)
                    m = pg.evaluate(SCROLL_JS)
                    assert m["sw"] <= m["cw"] and width - 32 <= m["head"] <= width, "%s, %d px, %s: %r" % (name, width, view, m)
                    if view in ("sum", "arr"):
                        spill = pg.evaluate(SPILL_JS)
                        assert not spill, "%s, %d px, %s: sticks out of its column: %r" % (name, width, view, spill[:4])
                if width > 640 and name != "empty":
                    show(pg, "sum")
                    r = pg.evaluate(RIGHT_JS)
                    assert width - 32 <= r["right"] <= width, "%s, %d px: the summary reaches the right edge: %r" % (name, width, r)
                assert not pg.errors, pg.errors
    for zf in (0.67, 0.75, 0.9, 1.1, 1.25, 1.5, 1.75):   # a 1920 px screen at browser zoom 67 % to 175 %: the window in CSS px is 1920 / zoom
        width = int(round(1920 / zf))
        with screen(root, tmp, wide_data(), width, height=int(round(1080 / zf)), scale=zf) as pg:
            for view in WIDE_VIEWS:
                show(pg, view)
                m = pg.evaluate(SCROLL_JS)
                assert m["sw"] <= m["cw"] and width - 32 <= m["head"] <= width, "browser zoom %d %%, %s: %r" % (zf * 100, view, m)
                if width > 1432 and view != "mem-graph":
                    r = pg.evaluate(RIGHT_JS)
                    assert width - 32 <= r["right"] <= width, "browser zoom %d %%, %s: the content reaches the right edge: %r" % (zf * 100, view, r)
            assert not pg.errors, pg.errors
    with screen(root, tmp, wide_data(), 960, height=540, scale=2) as zoomed:
        show(zoomed, "sum")
        z = zoomed.evaluate(BOXES_JS)
        assert zoomed.evaluate(SCROLL_JS)["sw"] <= 960
    with screen(root, tmp, wide_data(), 960, height=540) as plain:
        show(plain, "sum")
        assert plain.evaluate(BOXES_JS) == z, "1920 px at 200 % is the 960 px page"
    return "browser"


TESTS = [summary_is_a_list_of_components, arrange_mode_shakes_and_respects_reduced_motion, move_hide_and_add_persist_per_viewer,
         needs_you_cannot_be_hidden, team_default_is_used_when_the_viewer_has_none, unknown_component_falls_back,
         arranging_works_with_the_keyboard, corrupt_arrangement_gives_the_default, language_is_applied_before_first_paint]
TESTS += [content_reaches_the_right_edge_on_wide_screens, wide_screens_scale_up_not_stretch, layout_is_unchanged_at_1280_and_below,
          no_sideways_scroll_from_320_to_3840]


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
