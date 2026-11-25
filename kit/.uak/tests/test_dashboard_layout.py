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
    """The forced edges: no task, one task, 300 tasks, 40 agents."""
    return {"empty": lambda: wide_data(tasks=0, agents=0, humans=1), "one": lambda: wide_data(tasks=1, agents=1), "300": lambda: wide_data(tasks=300, agents=20),
            "40 agents": lambda: wide_data(tasks=60, agents=40)}[name]()


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
# order, as [x, y, width, height] rounded to the pixel. Text inside a box is not measured on its own: its lines are the box's height.
BOXES_JS = """() => {
  const S = '.head, #tabs, #view, #view .page, #view .page > *, #view .col > *, #view .wide, #view .wide > *, #view .bd > *, #view .g2 > *, #view .cv > *, #view .gv > *, #view .gv svg, #view .agrid > *, #view .tmap, #view .mini > *, #view .hb, #view .win-f';
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


# Measured with layout_boxes() on main at 425a1d81 (the dash.html of UAK-165, before UAK-198), twice, with the same numbers: the
# screens the human approved, per width and view, "x,y,w,h" per box in document order.
APPROVED_BOXES = {
    "1280": {
        "sum": "0,0,72,900 72,0,1208,53 72,53,1208,1455 72,53,1208,1455 96,69,1160,28 96,113,848,1355 96,113,848,369 97,413,846,68 96,498,848,234 109,551,822,92 96,748,848,450 96,1214,848,254 960,113,296,1074 960,113,296,309 960,438,296,285 960,739,296,245 960,999,296,188",
        "arr": "0,0,72,900 72,0,1208,53 72,53,1208,1543 72,53,1208,1543 96,69,1160,116 96,201,848,1355 96,201,848,369 97,501,846,68 96,586,848,234 109,639,822,92 96,836,848,450 96,1302,848,254 960,201,296,1074 960,201,296,309 960,526,296,285 960,827,296,245 960,1087,296,188",
        "board-map": "0,0,72,900 72,0,1208,53 72,53,1208,544 72,53,1208,544 96,69,1160,32 96,113,1160,20 96,133,1160,94 109,186,1134,28 96,239,1160,94 109,292,1134,28 96,345,1160,94 109,398,1134,28 96,451,1160,94 109,504,1134,28",
        "board-cards": "0,0,72,900 72,0,1208,53 72,53,1208,1274 72,53,1208,1274 96,69,1160,32 96,109,1160,1178 96,109,281,1156 389,109,281,1103 682,109,281,1178 975,109,281,724",
        "agents": "0,0,72,900 72,0,1208,53 72,53,1208,1103 72,53,1208,1103 96,69,1160,228 96,109,226,188 330,109,226,188 563,109,226,188 797,109,226,188 96,321,1160,228 96,361,226,188 330,361,226,188 96,573,1160,138 96,613,190,98 290,613,190,98 96,735,1160,138 96,775,190,98 290,775,190,98 484,775,190,98 678,775,190,98 872,775,190,98 1066,775,190,98 96,896,1160,196 96,936,226,156 330,936,226,156",
        "talk": "0,0,72,900 72,0,1208,53 72,53,1208,1100 72,53,1208,1100 96,69,1160,30 96,115,1160,998 96,115,280,445 392,115,584,998 992,115,264,311 993,227,262,70",
        "bb": "0,0,72,900 72,0,1208,53 72,53,1208,875 72,53,1208,875 96,69,1160,30 96,115,1160,24 96,155,1160,278 96,155,572,278 97,196,570,236 684,155,572,204 96,449,1160,439",
        "mem-list": "0,0,72,900 72,0,1208,53 72,53,1208,931 72,53,1208,931 96,69,1160,30 96,115,1160,829 96,115,572,829 684,115,572,785",
        "mem-graph": "0,0,72,900 72,0,1208,53 72,53,1208,738 72,53,1208,738 96,69,1160,30 96,115,1160,28 96,159,1160,592 96,159,763,592 97,160,761,560 875,159,381,399",
        "tokens": "0,0,72,900 72,0,1208,53 72,53,1208,1412 72,53,1208,1412 96,69,1160,174 96,259,1160,517 96,259,376,141 97,300,374,99 488,259,376,168 489,300,374,126 880,259,376,113 881,300,374,71 96,443,1160,333 97,484,1158,291 96,792,1160,549 97,1284,1158,56 96,1357,1160,20 96,1392,1160,20",
    },
    "1100": {
        "sum": "0,0,72,900 72,0,1028,53 72,53,1028,2553 72,53,1028,2553 96,69,980,28 96,113,980,1402 96,113,980,417 97,394,978,135 96,546,980,234 109,599,954,92 96,796,980,450 96,1261,980,254 96,1531,980,1035 96,1531,980,289 96,1836,980,285 96,2137,980,225 96,2378,980,188",
        "arr": "0,0,72,900 72,0,1028,53 72,53,1028,2667 72,53,1028,2667 96,69,980,142 96,227,980,1402 96,227,980,417 97,508,978,135 96,660,980,234 109,713,954,92 96,910,980,450 96,1375,980,254 96,1645,980,1035 96,1645,980,289 96,1950,980,285 96,2251,980,225 96,2492,980,188",
        "board-map": "0,0,72,900 72,0,1028,53 72,53,1028,576 72,53,1028,576 96,69,980,32 96,113,980,20 96,133,980,94 109,186,954,28 96,239,980,94 109,292,954,28 96,345,980,94 109,398,954,28 96,451,980,126 109,504,954,60",
        "board-cards": "0,0,72,900 72,0,1028,53 72,53,1028,2213 72,53,1028,2213 96,69,980,32 96,109,980,2117 96,109,484,1059 592,109,484,1005 96,1180,484,1046 592,1180,484,707",
        "agents": "0,0,72,900 72,0,1028,53 72,53,1028,1205 72,53,1028,1205 96,69,980,228 96,109,239,188 343,109,239,188 590,109,239,188 837,109,239,188 96,321,980,228 96,361,239,188 343,361,239,188 96,573,980,138 96,613,193,98 293,613,193,98 96,735,980,239 96,775,193,98 293,775,193,98 490,775,193,98 686,775,193,98 883,775,193,98 96,876,193,98 96,998,980,196 96,1038,239,156 343,1038,239,156",
        "talk": "0,0,72,900 72,0,1028,53 72,53,1028,1719 72,53,1028,1719 96,69,980,30 96,115,980,1617 96,115,980,445 96,576,980,882 96,1474,980,258 97,1546,978,56",
        "bb": "0,0,72,900 72,0,1028,53 72,53,1028,875 72,53,1028,875 96,69,980,30 96,115,980,24 96,155,980,278 96,155,482,278 97,196,480,236 594,155,482,204 96,449,980,439",
        "mem-list": "0,0,72,900 72,0,1028,53 72,53,1028,990 72,53,1028,990 96,69,980,30 96,115,980,888 96,115,482,888 594,115,482,843",
        "mem-graph": "0,0,72,900 72,0,1028,53 72,53,1028,650 72,53,1028,650 96,69,980,30 96,115,980,28 96,159,980,504 96,159,643,504 97,160,641,472 755,159,321,399",
        "tokens": "0,0,72,900 72,0,1028,53 72,53,1028,1541 72,53,1028,1541 96,69,980,174 96,259,980,646 96,259,482,141 97,300,480,99 594,259,482,168 595,300,480,126 96,443,482,113 97,484,480,71 96,572,980,333 97,613,978,291 96,921,980,549 97,1413,978,56 96,1486,980,20 96,1521,980,20",
    },
    "900": {
        "sum": "0,839,900,61 0,0,900,53 0,53,900,3021 0,53,900,3021 24,69,852,28 24,113,852,1870 24,113,852,417 25,394,850,135 24,546,852,234 37,599,826,92 24,796,852,918 24,1729,852,254 24,1999,852,1035 24,1999,852,289 24,2304,852,285 24,2605,852,225 24,2846,852,188",
        "arr": "0,839,900,61 0,0,900,53 0,53,900,3135 0,53,900,3135 24,69,852,142 24,227,852,1870 24,227,852,417 25,508,850,135 24,660,852,234 37,713,826,92 24,910,852,918 24,1843,852,254 24,2113,852,1035 24,2113,852,289 24,2418,852,285 24,2719,852,225 24,2960,852,188",
        "board-map": "0,839,900,61 0,0,900,53 0,53,900,576 0,53,900,576 24,69,852,32 24,113,852,20 24,133,852,94 37,186,826,28 24,239,852,94 37,292,826,28 24,345,852,94 37,398,826,28 24,451,852,126 37,504,826,60",
        "board-cards": "0,839,900,61 0,0,900,53 0,53,900,2252 0,53,900,2252 24,69,852,32 24,109,852,2156 24,109,420,1078 456,109,420,1005 24,1199,420,1066 456,1199,420,712",
        "agents": "0,839,900,61 0,0,900,53 0,53,900,1318 0,53,900,1318 24,69,852,381 24,109,279,169 311,109,279,169 597,109,279,169 24,286,279,164 24,474,852,209 24,514,279,169 311,514,279,169 24,706,852,138 24,746,210,98 238,746,210,98 24,868,852,239 24,908,210,98 238,908,210,98 452,908,210,98 666,908,210,98 24,1009,210,98 238,1009,210,98 24,1131,852,177 24,1171,279,137 311,1171,279,137",
        "talk": "0,839,900,61 0,0,900,53 0,53,900,1719 0,53,900,1719 24,69,852,30 24,115,852,1617 24,115,852,445 24,576,852,882 24,1474,852,258 25,1546,850,56",
        "bb": "0,839,900,61 0,0,900,53 0,53,900,903 0,53,900,903 24,69,852,30 24,115,852,52 24,183,852,278 24,183,418,278 25,224,416,236 458,183,418,223 24,477,852,439",
        "mem-list": "0,839,900,61 0,0,900,53 0,53,900,1087 0,53,900,1087 24,69,852,30 24,115,852,985 24,115,418,985 458,115,418,921",
        "mem-graph": "0,839,900,61 0,0,900,53 0,53,900,587 0,53,900,587 24,69,852,30 24,115,852,28 24,159,852,441 24,159,557,441 25,160,555,409 597,159,279,399",
        "tokens": "0,839,900,61 0,0,900,53 0,53,900,2092 0,53,900,2092 24,69,852,174 24,259,852,646 24,259,418,141 25,300,416,99 458,259,418,168 459,300,416,126 24,443,418,113 25,484,416,71 24,572,852,333 25,613,850,291 24,921,852,1100 25,1963,850,56 24,2037,852,20 24,2072,852,20",
    },
    "640": {
        "sum": "0,839,640,61 0,0,640,121 0,121,640,3658 0,121,640,3658 16,137,608,44 16,197,608,2468 16,197,608,732 17,793,606,135 16,945,608,282 29,998,582,140 16,1243,608,1140 16,2399,608,266 16,2681,608,1058 16,2681,608,289 16,2986,608,294 16,3296,608,239 16,3551,608,188",
        "arr": "0,839,640,61 0,0,640,121 0,121,640,3794 0,121,640,3794 16,137,608,176 16,329,608,2438 16,329,608,744 17,937,606,135 16,1089,608,294 29,1154,582,140 16,1399,608,1086 16,2501,608,266 16,2783,608,1092 16,2783,608,301 16,3100,608,306 16,3422,608,237 16,3675,608,200",
        "board-map": "0,839,640,61 0,0,640,121 0,121,640,698 0,121,640,698 16,137,608,98 16,247,608,20 16,267,608,98 29,320,582,32 16,377,608,98 29,430,582,32 16,487,608,98 29,540,582,32 16,597,608,170 29,650,582,104",
        "board-cards": "0,839,640,61 0,0,640,121 0,121,640,4339 0,121,640,4339 16,137,608,98 16,243,608,4177 16,243,608,1156 16,1411,608,1059 16,2481,608,1107 16,3600,608,821",
        "agents": "0,839,640,61 0,0,640,121 0,121,640,1443 0,121,640,1443 16,137,608,425 16,177,300,189 324,177,300,189 16,374,300,189 324,374,300,189 16,586,608,229 16,626,300,189 324,626,300,189 16,839,608,158 16,879,200,118 220,879,200,118 16,1020,608,279 16,1060,200,118 220,1060,200,118 424,1060,200,118 16,1182,200,118 220,1182,200,118 424,1182,200,118 16,1323,608,177 16,1363,300,137 324,1363,300,137",
        "talk": "0,839,640,61 0,0,640,121 0,121,640,1955 0,121,640,1955 16,137,608,98 16,251,608,1785 16,251,608,445 16,712,608,1050 16,1778,608,258 17,1850,606,56",
        "bb": "0,839,640,61 0,0,640,121 0,121,640,1222 0,121,640,1222 16,137,608,98 16,251,608,92 16,359,608,480 16,359,608,278 17,400,606,236 16,653,608,186 16,855,608,448",
        "mem-list": "0,839,640,61 0,0,640,121 0,121,640,1855 0,121,640,1855 16,137,608,46 16,199,608,1737 16,199,608,947 16,1162,608,774",
        "mem-graph": "0,839,640,61 0,0,640,121 0,121,640,1136 0,121,640,1136 16,137,608,46 16,199,608,148 16,363,608,854 16,363,608,479 17,364,606,447 16,858,608,359",
        "tokens": "0,839,640,61 0,0,640,121 0,121,640,2564 0,121,640,2564 16,137,608,174 16,327,608,803 16,327,608,141 17,368,606,99 16,483,608,168 17,524,606,126 16,667,608,113 17,708,606,71 16,796,608,333 17,837,606,291 16,1145,608,1416 17,2504,606,56 16,2577,608,20 16,2613,608,20",
    },
    "390": {
        "sum": "0,783,390,61 0,0,390,121 0,121,390,4042 0,121,390,4042 16,137,358,44 16,197,358,2853 16,197,358,849 17,910,356,135 16,1062,358,426 29,1115,332,248 16,1504,358,1242 16,2762,358,288 16,3066,358,1058 16,3066,358,289 16,3371,358,294 16,3681,358,239 16,3936,358,188",
        "arr": "0,783,390,61 0,0,390,121 0,121,390,4191 0,121,390,4191 16,137,358,212 16,365,358,2799 16,365,358,861 17,1090,356,135 16,1242,358,438 29,1307,332,248 16,1696,358,1164 16,2876,358,288 16,3180,358,1092 16,3180,358,301 16,3497,358,306 16,3819,358,237 16,4072,358,200",
        "board-map": "0,783,390,61 0,0,390,121 0,121,390,794 0,121,390,794 16,137,358,122 16,271,358,20 16,291,358,134 29,344,332,68 16,437,358,98 29,490,332,32 16,547,358,98 29,600,332,32 16,657,358,206 29,710,332,140",
        "board-cards": "0,783,390,61 0,0,390,121 0,121,390,4634 0,121,390,4634 16,137,358,122 16,267,358,4449 16,267,358,1253 16,1532,358,1156 16,2700,358,1183 16,3895,358,821",
        "agents": "0,783,390,61 0,0,390,121 0,121,390,2249 0,121,390,2249 16,137,358,794 16,177,358,189 16,374,358,189 16,570,358,189 16,767,358,164 16,955,358,401 16,995,358,164 16,1167,358,189 16,1379,358,158 16,1419,177,118 197,1419,177,118 16,1561,358,401 16,1601,177,118 197,1601,177,118 16,1722,177,118 197,1722,177,118 16,1844,177,118 197,1844,177,118 16,1985,358,321 16,2025,358,137 16,2170,358,137",
        "talk": "0,783,390,61 0,0,390,121 0,121,390,2064 0,121,390,2064 16,137,358,98 16,251,358,1894 16,251,358,445 16,712,358,1125 16,1853,358,292 17,1945,356,70",
        "bb": "0,783,390,61 0,0,390,121 0,121,390,1307 0,121,390,1307 16,137,358,98 16,251,358,140 16,407,358,517 16,407,358,278 17,448,356,236 16,701,358,223 16,940,358,448",
        "mem-list": "0,783,390,61 0,0,390,121 0,121,390,2401 0,121,390,2401 16,137,358,46 16,199,358,2283 16,199,358,1220 16,1435,358,1047",
        "mem-graph": "0,783,390,61 0,0,390,121 0,121,390,2428 0,121,390,2428 16,137,358,74 16,227,358,2283 16,227,358,1220 16,1462,358,1047",
        "tokens": "0,783,390,61 0,0,390,121 0,121,390,2715 0,121,390,2715 16,137,358,193 16,346,358,803 16,346,358,141 17,387,356,99 16,503,358,168 17,544,356,126 16,687,358,113 17,728,356,71 16,816,358,333 17,857,356,291 16,1165,358,1528 17,2621,356,70 16,2708,358,20 16,2744,358,39",
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
    right edge (at most 760 px wide) while Share opens centred inside the window."""
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
            st = pg.evaluate("(() => { const r = document.getElementById('story').getBoundingClientRect(); return [r.left, r.right, r.width]; })()")
            assert abs(st[1] - width) <= 1 and st[2] <= 760, "%d px: the task's detail sits against the right edge: %r" % (width, st)
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


def wide_screens_add_columns_not_stretch(root, tmp):
    """The extra width is used, not stretched. The rule (pure, under node): up to 1480 px of content the summary is the approved
    one (a side of 296 px); from 1480 px the side shows its components in two columns, from 2900 px in three, each 296 to 440 px;
    a list alone flows into those columns; the memory graph's canvas is the card's width and fits the window. In Chromium at 1920
    and 2560 px: the side's blocks sit in two columns, none wider than 460 px; the squares fill the row; the board's four columns
    share the width; the Agents grid has more cards per row, none stretched (360 px at most, a group alone in its heading's width); the tokens' panels sit three or more to a row and
    the long breakdown in two groups; lessons and decisions in two columns; the black box's panels beside its notes; the graph
    on a larger canvas with labels at their size; no line of running text over about 90 characters (95, spaces counted).
    The viewer's arrangement means the same at every width: arrange mode moves, crosses and drags at 2560 px, the side's columns
    are never stored, and an arrangement saved before UAK-198 is drawn as it was saved."""
    out = truth.under_node(root, """return [sumCols(1160, 4, 4), sumCols(1320, 4, 4), sumCols(1479, 4, 4), sumCols(1480, 4, 4), sumCols(1800, 4, 4), sumCols(2440, 4, 4),
      sumCols(3720, 4, 4), sumCols(1800, 4, 1), sumCols(3720, 2, 2), sumCols(1800, 8, 0), sumCols(1160, 8, 0), sumCols(1800, 0, 8), sumCols(3720, 1, 0), sumCols(NaN, 4, 4),
      graphBox(763, 900, 500, 400), graphBox(NaN, 900, 500, 400), graphBox(1316, 1080, 900, 600), graphBox(1904, 1440, 900, 700), graphBox(1316, 1080, 300, 60)];""")
    if out is not None:
        narrow = {"flow": 1, "side": 1, "w": 296}
        assert out[0] == narrow and out[1] == narrow and out[2] == narrow and out[13] == narrow, "up to 1480 px the approved summary: %r" % out[:3]
        assert out[3] == {"flow": 1, "side": 2, "w": 608}, "from 1480 px two side columns of 296: %r" % out[3]
        assert out[4] == {"flow": 1, "side": 2, "w": 648} and out[5] == {"flow": 1, "side": 2, "w": 878}, "the side grows with the width: %r %r" % (out[4], out[5])
        assert out[6] == {"flow": 1, "side": 3, "w": 1340}, "three columns from 2900 px: %r" % out[6]
        assert out[7] == {"flow": 1, "side": 1, "w": 316} and out[8] == {"flow": 1, "side": 2, "w": 888}, "never more columns than components: %r %r" % (out[7], out[8])
        assert out[9] == {"flow": 2, "side": 0, "w": 0} and out[10] == {"flow": 1, "side": 0, "w": 0} and out[11] == {"flow": 2, "side": 0, "w": 0} and out[12] == {"flow": 1, "side": 0, "w": 0}, \
            "a list alone flows into the columns of its width: %r" % out[9:13]
        assert out[14] == {"W": 760, "H": 560} and out[15] == {"W": 760, "H": 560}, "the approved graph up to 800 px: %r" % out[14:16]
        assert out[16]["W"] == 1316 and 560 <= out[16]["H"] <= 1080 - 240 and out[17]["W"] == 1904 and out[17]["H"] <= 1440 - 240, "a larger canvas that fits the window: %r" % out[16:18]
        assert out[18]["W"] == 1316 and out[18]["H"] < 560, "a flat graph gets a flat canvas, not a tall empty one: %r" % out[18]
    with screen(root, tmp, wide_data(), 1280) as pg:
        show(pg, "sum")
        rows1280 = pg.evaluate("new Set(Array.from(document.querySelectorAll('#view .b-map .sq')).map(e => Math.round(e.getBoundingClientRect().top))).size")
        show(pg, "agents")
        show(pg, "talk")
        thread1280 = pg.evaluate("document.querySelector('#view .cv > .win').getBoundingClientRect().width")
    PER_ROW = """() => { const g = Array.from(document.querySelectorAll('#view .agrid')).sort((a, b) => b.children.length - a.children.length)[0], c = Array.from(g.children).map(e => e.getBoundingClientRect());
      return { per: c.filter(x => Math.round(x.top) === Math.round(c[0].top)).length, w: Math.round(Math.max(...Array.from(document.querySelectorAll('#view .agrid > *')).map(e => e.getBoundingClientRect().width))) }; }"""
    per = {}
    for width in (1280, 1920, 2560):
        with screen(root, tmp, wide_data_named("40 agents"), width) as pg:
            show(pg, "agents")
            per[width] = pg.evaluate(PER_ROW)
    for width in (1920, 2560):
        assert per[width]["per"] > per[1280]["per"] and per[width]["w"] <= 360, "%d px: more agent cards per row, none stretched: %r" % (width, per)
        with screen(root, tmp, wide_data(), width) as pg:
            show(pg, "sum")
            s = pg.evaluate("""() => { const q = (x) => Array.from(document.querySelectorAll(x)), r = (e) => e.getBoundingClientRect();
              const side = q('#view .col[data-col=side] > *'), main = r(document.querySelector('#view .col[data-col=main]')), map = document.querySelector('#view .b-map .tmap'), sq = q('#view .b-map .sq');
              const top0 = Math.round(r(sq[0]).top), first = sq.filter(e => Math.round(r(e).top) === top0);
              return { lefts: new Set(side.map(e => Math.round(r(e).left))).size, widths: side.map(e => Math.round(r(e).width)), main: Math.round(main.width),
                       rows: new Set(sq.map(e => Math.round(r(e).top))).size, gap: Math.round(r(map).right - r(first[first.length - 1]).right) }; }""")
            assert s["lefts"] >= 2 and all(296 <= w <= 460 for w in s["widths"]) and s["main"] >= 848, "%d px: the side's blocks in two columns of 296 to 460 px: %r" % (width, s)
            assert s["rows"] < rows1280 and s["gap"] < 40, "%d px: the squares fill the row (%d rows here, %d at 1280): %r" % (width, s["rows"], rows1280, s)
            show(pg, "board-cards")
            b = pg.evaluate("""() => { const c = Array.from(document.querySelectorAll('#view .bd > *')).map(e => e.getBoundingClientRect()), bd = document.querySelector('#view .bd').getBoundingClientRect();
              return { n: c.length, tops: new Set(c.map(x => Math.round(x.top))).size, w: c.map(x => Math.round(x.width)), bd: Math.round(bd.width) }; }""")
            assert b["n"] == 4 and b["tops"] == 1 and max(b["w"]) - min(b["w"]) <= 2 and sum(b["w"]) >= b["bd"] - 40, "%d px: the board's four columns share the width: %r" % (width, b)
            show(pg, "board-map")
            m = pg.evaluate("""() => { const c = Array.from(document.querySelectorAll('#view .wide > section')).map(e => e.getBoundingClientRect()), W = document.querySelector('#view .wide').clientWidth;
              return { tops: c.map(x => Math.round(x.top)), w: c.map(x => Math.round(x.width)), W: W }; }""")
            assert len(set(m["tops"])) < len(m["tops"]) and m["w"][0] < m["W"] / 2, "%d px: the stages with few tasks sit side by side, none a wide empty box: %r" % (width, m)
            show(pg, "agents")
            a = pg.evaluate(PER_ROW)
            assert a["w"] <= 360, "%d px: no agent card is stretched: %r" % (width, a)
            show(pg, "tokens")
            k = pg.evaluate("""() => { const p = Array.from(document.querySelectorAll('#view .g2 > *')).map(e => e.getBoundingClientRect()), t = Math.round(p[0].top);
              const full = document.querySelector('#view .g2 > .full .hb'), dts = Array.from(document.querySelectorAll('#view .tkh .kv dt')).map(e => Math.round(e.getBoundingClientRect().top));
              return { row: p.filter(x => Math.round(x.top) === t).length, groups: full ? new Set(Array.from(full.querySelectorAll('.l')).map(e => Math.round(e.getBoundingClientRect().left))).size : 0, kv: new Set(dts).size }; }""")
            assert k["row"] >= 3 and k["groups"] >= 2 and k["kv"] == 1, "%d px: the tokens' panels flow into columns: %r" % (width, k)
            show(pg, "mem-list")
            ml = pg.evaluate("new Set(Array.from(document.querySelectorAll('#view .g2 > section:first-child .list > li')).map(e => Math.round(e.getBoundingClientRect().left))).size")
            assert ml >= 2, "%d px: the lessons sit in two columns: %r" % (width, ml)
            show(pg, "mem-graph")
            g = pg.evaluate("""() => { const s = document.querySelector('#view svg.mg').getBoundingClientRect(), t = document.querySelector('#view svg.mg text');
              return { w: Math.round(s.width), h: Math.round(s.height), top: Math.round(s.top), vh: innerHeight, label: t ? Math.round(t.getBoundingClientRect().height) : 0 }; }""")
            assert g["w"] > 1000 and g["top"] + g["h"] <= g["vh"] + 40 and 8 <= g["label"] <= 16, "%d px: the graph on a larger canvas that fits the window, labels at their size: %r" % (width, g)
            show(pg, "bb")
            bb = pg.evaluate("""() => { const g = document.querySelector('#view .g2').getBoundingClientRect(), n = document.querySelector('#view .wide > section:last-child').getBoundingClientRect();
              return { g: Math.round(g.left), n: Math.round(n.right), top: Math.round(g.top), ntop: Math.round(n.top) }; }""")
            assert bb["g"] > bb["n"] and bb["top"] < bb["ntop"] + 200, "%d px: the black box's panels sit beside its notes: %r" % (width, bb)
            show(pg, "talk")
            t = pg.evaluate("Math.round(document.querySelector('#view .cv > .win').getBoundingClientRect().width)")
            assert t > thread1280 + 200, "%d px: the conversation is wider (%d at 1280): %r" % (width, thread1280, t)
            for view in WIDE_VIEWS:
                show(pg, view)
                long = pg.evaluate(LINES_JS)
                assert not long, "%d px, %s: lines of running text over about 90 characters: %r" % (width, view, long[:4])
            assert not pg.errors, pg.errors
    # the arrangement at 2560: arrange mode works, the columns are not stored, an older arrangement is drawn as saved
    with screen(root, tmp, wide_data(), 2560) as pg:
        show(pg, "arr")
        assert pg.evaluate("new Set(Array.from(document.querySelectorAll('#view .col[data-col=side] > .arr')).map(e => Math.round(e.getBoundingClientRect().left))).size") >= 2, "arranging keeps the side's columns"
        def drag(grip, onto):
            pg.evaluate("scrollTo({ top: 0, behavior: 'instant' })")
            src, dst = pg.locator('[data-grip="%s"]' % grip).bounding_box(), pg.locator('#view .arr[data-blk="%s"]' % onto).bounding_box()
            pg.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
            pg.mouse.down()
            for k in range(1, 9):
                pg.mouse.move(src["x"] + (dst["x"] + 40 - src["x"]) * k / 8, src["y"] + (dst["y"] + 4 - src["y"]) * k / 8)
            pg.mouse.up()
            return src, dst
        # a drag inside the side, onto the top of its second column: it lands there, after the first column's components
        src, dst = drag("tokens", "pace")
        assert dst["x"] > pg.locator('#view .arr[data-blk="progress"]').bounding_box()["x"] + 100, "pace heads the side's second column: %r" % dst
        pg.wait_for_function("Array.from(document.querySelectorAll('#view .col[data-col=side] > .arr')).map(e => e.getAttribute('data-blk')).join() === 'progress,agents,tokens,pace'")
        press(pg, '[data-f="agents:down"]')
        pg.wait_for_function("document.querySelector('#view .col[data-col=side]').children[2].getAttribute('data-blk') === 'agents'")
        press(pg, '[data-f="pace:col"]')
        pg.wait_for_function("document.querySelector('#view .col[data-col=main] .arr[data-blk=pace]')")
        drag("tokens", "tasks")
        pg.wait_for_function("document.querySelector('#view .col[data-col=main] .arr[data-blk=tokens]')")
        lay = layout_in(pg)
        assert lay == {"main": ["needs", "map", "tokens", "tasks", "pace", "lanes"], "side": ["progress", "agents"]}, "moves, crossing and drags at 2560 px: %r" % lay
        kept = json.loads(pg.evaluate("(k) => localStorage.getItem(k)", KEY))
        assert sorted(kept) == ["hide", "main", "side"] and kept["side"] == ["progress", "agents"], "what is kept is the two lists and the hidden ones, never a column count: %r" % kept
        assert not pg.errors, pg.errors
    old = {"main": ["needs", "lanes", "tasks"], "side": ["tokens", "progress", "map", "agents"], "hide": ["pace"]}
    with screen(root, tmp, wide_data(), 1920, seed={KEY: json.dumps(old)}) as pg:
        assert layout_in(pg) == {"main": old["main"], "side": old["side"]}, "an arrangement saved before UAK-198 is drawn as saved: %r" % layout_in(pg)
        assert pg.evaluate("new Set(Array.from(document.querySelectorAll('#view .col[data-col=side] > *')).map(e => Math.round(e.getBoundingClientRect().left))).size") >= 2
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
    with no task, one task, 300 tasks and 40 agents, with every side block hidden, with every block in the main column or in the
    side, with what needs you in the side (arranging too: on main it pushed a 296 px side past the window at 1280 px), and at
    1920 px zoomed to 200 % (960 px of CSS), where the page is the 960 px page."""
    for width in (320, 360, 390, 414, 640, 768, 900, 1024, 1100, 1280, 1366, 1440, 1600, 1920, 2560, 3840):
        with screen(root, tmp, wide_data(), width, phone=width < 640) as pg:
            for view in WIDE_VIEWS:
                show(pg, view)
                m = pg.evaluate(SCROLL_JS)
                assert m["sw"] <= m["cw"], "%d px, %s: the page scrolls sideways (%d > %d)" % (width, view, m["sw"], m["cw"])
                assert width - 32 <= m["head"] <= width, "%d px, %s: the header's controls end at %d" % (width, view, m["head"])
            assert not pg.errors, pg.errors
    names = [n for n, _ in ORDER]
    edges = [("empty", None), ("one", None), ("300", None), ("40 agents", None),
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
TESTS += [content_reaches_the_right_edge_on_wide_screens, wide_screens_add_columns_not_stretch, layout_is_unchanged_at_1280_and_below,
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
