#!/usr/bin/env python3
"""UI-018: the setup page always says what it is doing, why a button is blocked, and what changed.
Evidence: Dylan's real run (2026-11-13, a Spanish hackathon project on macOS): at the plan step the layout jumped and the
preferences row broke into one line; a disabled "Create the plan" showed the spinning wait cursor and nothing said why
it was blocked; "Check what's next" seemed to do nothing (no progress near the button, no result).
These tests run the page's own feedback code in Node against a fake DOM built from the real setup.html (every element
with its attributes and parent), with the real workspace.js catalog; without Node they read the sources only."""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

ROOT = None
BEGIN = "// UI-018 feedback: begin"
END = "// UI-018 feedback: end"


def lib(name):
    return (ROOT / ".uak/bin/lib" / name).read_text(encoding="utf-8")


def page():
    return lib("setup.html")


def script(html):
    return html[html.index('<script nonce="__NONCE__">'):]


def styles(html):
    return html[html.index("<style>"):html.index("</style>")]


def catalog():
    text = lib("workspace.js")
    pairs = re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)
    return {json.loads(a): json.loads(b) for a, b in pairs}


def rules(html):
    """(selector, body) of every CSS rule, media queries flattened (their selectors keep the @media prefix)."""
    css = re.sub(r"/\*[\s\S]*?\*/", "", styles(html))
    found, media = [], ""
    for m in re.finditer(r"(@media[^{]*)\{|([^{}]+)\{([^{}]*)\}|\}", css):
        if m.group(1):
            media = m.group(1).strip()
        elif m.group(2):
            found.append(((media + " " if media else "") + m.group(2).strip(), m.group(3)))
        else:
            media = ""
    return found


def block(code):
    """The page's UI-018 feedback block, one contiguous piece of the main script."""
    assert BEGIN in code and END in code, "the page keeps its feedback code between %r and %r" % (BEGIN, END)
    return code[code.index(BEGIN):code.index(END)]


def page_function(code, name):
    m = re.search(r"\n( *)(?:async )?function %s\([\s\S]*?\n\1\}" % re.escape(name), code)
    assert m, "the page defines function %s()" % name
    return m.group(0)


class Tree(HTMLParser):
    """Every element of the page's body: tag, attributes and parent index (the fake DOM's skeleton)."""

    VOID = ("input", "br", "img", "meta", "link", "hr", "source", "track")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes, self.stack, self.inside = [], [], False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.inside = True
        if not self.inside or tag in ("script", "style"):
            return
        self.nodes.append({"tag": tag, "attrs": {k: (v if v is not None else "") for k, v in attrs},
                           "parent": self.stack[-1] if self.stack else -1, "text": ""})
        if tag not in self.VOID:
            self.stack.append(len(self.nodes) - 1)

    def handle_endtag(self, tag):
        if not self.inside or tag in ("script", "style"):
            return
        while self.stack:
            if self.nodes[self.stack.pop()]["tag"] == tag:
                break

    def handle_data(self, data):
        if self.stack and data.strip():
            node = self.nodes[self.stack[-1]]
            node["text"] = (node["text"] + " " + " ".join(data.split())).strip()


def tree(html):
    parser = Tree()
    parser.feed(html)
    return parser.nodes


NODE_PROGRAM = r"""
const vm = require("vm"), fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const ids = new Map(), timers = [], listeners = {};
let activeElement = null, timerId = 0, now = Date.parse("2026-11-13T21:04:00");
function matches(node, sel) {
  return sel.split(",").some(function (one) {
    const m = one.trim().match(/^([a-z]*)((?:\[[^\]]+\]|\.[\w-]+|#[\w-]+)*)$/i);
    if (!m) throw Error("fake DOM: unsupported selector " + one);
    if (m[1] && node.tagName !== m[1].toUpperCase()) return false;
    const parts = m[2].match(/\[[^\]]+\]|\.[\w-]+|#[\w-]+/g) || [];
    return parts.every(function (p) {
      if (p[0] === ".") return node.classList.contains(p.slice(1));
      if (p[0] === "#") return node.id === p.slice(1);
      const a = p.slice(1, -1).match(/^([\w-]+)(?:="?([^"]*)"?)?$/);
      return a[2] === undefined ? node.getAttribute(a[1]) !== null : node.getAttribute(a[1]) === a[2];
    });
  });
}
class ClassList {
  constructor(node) { this.node = node; }
  get set() { return new Set((this.node.attrs["class"] || "").split(/\s+/).filter(Boolean)); }
  write(s) { this.node.attrs["class"] = Array.from(s).join(" "); }
  add(c) { const s = this.set; s.add(c); this.write(s); }
  remove(c) { const s = this.set; s.delete(c); this.write(s); }
  contains(c) { return this.set.has(c); }
  toggle(c, force) { const on = force === undefined ? !this.contains(c) : !!force; on ? this.add(c) : this.remove(c); return on; }
}
class FakeNode {
  constructor(tag, attrs, text) {
    this.tagName = tag.toUpperCase(); this.attrs = Object.assign({}, attrs || {}); this.children = [];
    this.parentNode = null; this.text = text || ""; this.classList = new ClassList(this); this.listeners = {};
    this.focusCount = 0; this.scrolls = []; this.replaced = 0; this.dataset = {};
    Object.keys(this.attrs).forEach((k) => { if (k.indexOf("data-") === 0) this.dataset[k.slice(5).replace(/-([a-z])/g, (a, b) => b.toUpperCase())] = this.attrs[k]; });
  }
  get id() { return this.attrs.id || ""; }
  set id(v) { this.attrs.id = String(v); }
  get className() { return this.attrs["class"] || ""; }
  set className(v) { this.attrs["class"] = String(v); }
  get hidden() { return "hidden" in this.attrs; }
  set hidden(v) { if (v) this.attrs.hidden = ""; else delete this.attrs.hidden; }
  get disabled() { return "disabled" in this.attrs; }
  set disabled(v) { if (v) this.attrs.disabled = ""; else delete this.attrs.disabled; }
  get textContent() { return this.children.length ? this.children.map((c) => c.textContent).join("") : this.text; }
  set textContent(v) { this.children = []; this.text = String(v); }
  get offsetParent() { for (let n = this; n; n = n.parentNode) if (n.hidden) return null; return this.parentNode; }
  get nextElementSibling() { const s = this.parentNode ? this.parentNode.children : []; return s[s.indexOf(this) + 1] || null; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  adopt(c) { if (c.parentNode) c.parentNode.children.splice(c.parentNode.children.indexOf(c), 1); c.parentNode = this; index(c); }
  append() { Array.from(arguments).forEach((c) => { if (typeof c === "string") c = text(c); this.adopt(c); this.children.push(c); }); }
  appendChild(c) { this.append(c); return c; }
  replaceChildren() { this.replaced += 1; this.children = []; this.text = ""; this.append.apply(this, arguments); }
  after(c) { const p = this.parentNode; p.adopt(c); p.children.splice(p.children.indexOf(this) + 1, 0, c); }
  closest(sel) { for (let n = this; n && n.tagName; n = n.parentNode) if (matches(n, sel)) return n; return null; }
  matches(sel) { return matches(this, sel); }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) { const out = []; (function walk(n) { n.children.forEach((c) => { if (c.tagName && matches(c, sel)) out.push(c); walk(c); }); })(this); return out; }
  addEventListener(type, fn, capture) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  removeEventListener() {}
  focus() { this.focusCount += 1; activeElement = this; }
  blur() { if (activeElement === this) activeElement = null; }
  scrollIntoView(options) { this.scrolls.push(options || {}); }
  getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; }
  get style() { return {}; }
}
function text(value) { const n = new FakeNode("#text"); n.tagName = ""; n.text = value; return n; }
function index(node) { if (node.id) ids.set(node.id, node); node.children.forEach(index); }
function fire(target, type, extra) {
  const event = Object.assign({ type: type, target: target, defaultPrevented: false, stopped: false,
    preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; },
    stopImmediatePropagation() { this.stopped = true; } }, extra || {});
  (listeners[type] || []).forEach((fn) => fn.call(document, event));  // capture on document first
  if (event.stopped) return event;
  for (let n = target; n && !event.stopped; n = n.parentNode) {
    (n.listeners[type] || []).forEach((fn) => fn.call(n, event));
    if (n["on" + type] && !event.stopped) n["on" + type].call(n, event);
    if (type === "mouseenter" || type === "mouseleave") break;
  }
  return event;
}
const body = new FakeNode("body");
const nodes = input.tree.map((n) => new FakeNode(n.tag, n.attrs, n.text));
input.tree.forEach((n, i) => { (n.parent < 0 ? body : nodes[n.parent]).append(nodes[i]); });
const document = {
  body: body, documentElement: body,
  getElementById: (id) => { const n = ids.get(id); return n && (function attached(x) { for (; x; x = x.parentNode) if (x === body) return true; return false; })(n) ? n : null; },
  createElement: (tag) => new FakeNode(tag),
  querySelector: (sel) => body.querySelector(sel), querySelectorAll: (sel) => body.querySelectorAll(sel),
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  get activeElement() { return activeElement; }, hidden: false,
};
const store = { "uak-language": input.language };
const ctx = {
  document: document, console: console, navigator: { language: input.language },
  localStorage: { getItem: (k) => store[k] || null, setItem: () => {} },
  setTimeout: (fn, ms) => { timerId += 1; timers.push({ id: timerId, fn: fn, ms: ms, at: now + (ms || 0) }); return timerId; },
  clearTimeout: (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); },
  setInterval: () => 0, Event: function (type) { this.type = type; },
  matchMedia: (q) => ({ matches: !!input.reduced && /reduce/.test(q) }),
  NodeFilter: { SHOW_TEXT: 4 }, Date: class extends Date { constructor(v) { super(v === undefined ? now : v); } static now() { return now; } },
  fire: fire, timers: timers, nodes: nodes,
  advance: (ms) => { now += ms; timers.slice().sort((a, b) => a.at - b.at).forEach((t) => { if (t.at <= now) { ctx.clearTimeout(t.id); t.fn(); } }); },
};
ctx.window = ctx;
ctx.dispatchEvent = () => {};
ctx.addEventListener = () => {};
vm.createContext(ctx);
input.sources.forEach((s) => vm.runInContext(s, ctx));
vm.runInContext("(async function () {" + input.scenario + "})()", ctx).then(
  (out) => process.stdout.write(JSON.stringify(out === undefined ? null : out)),
  (e) => { process.stderr.write(String(e && e.stack || e)); process.exit(3); });
"""

# The page's own helpers the feedback block calls, and the state it reads (as the page declares them).
PRELUDE = """
var UAKWorkspace = window.UAKWorkspace, state = {phase: ""}, step = 4, requestBusy = false, planView = null,
  latestDashboard = null, currentSection = "setup";
"""


def run_page(scenario, language="en", reduced=False):
    """Run SCENARIO (an async function body) with workspace.js, the page's el/isBusy/error/action and its feedback
    block over a fake DOM of setup.html. Returns its JSON value, or None without Node."""
    node = shutil.which("node")
    if not node:
        print("  note: no Node.js here, so the page logic is checked by reading it only")
        return None
    html = page()
    code = script(html)
    sources = [lib("workspace.js"), PRELUDE] + [page_function(code, name) for name in ("el", "isBusy", "error")]
    sources += [block(code), page_function(code, "action")]
    with tempfile.TemporaryDirectory(prefix="uak-feedback-js-") as folder:
        program = Path(folder) / "run.js"
        program.write_text(NODE_PROGRAM, encoding="utf-8")
        done = subprocess.run([node, str(program)], input=json.dumps({"language": language, "sources": sources,
                                                                      "tree": tree(html), "scenario": scenario,
                                                                      "reduced": reduced}),
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert done.returncode == 0, "the page logic runs: %s" % done.stderr[-2000:]
    return json.loads(done.stdout)


def blocked_buttons_say_why(root, tmp):
    html = page()
    code = script(html)
    feedback = block(code)
    # Create the plan says why it waits, in text next to it, and is described by that text.
    button = re.search(r'<button[^>]*id="plan-create"[^>]*>', html).group(0)
    assert 'aria-describedby="plan-create-why"' in button, "Create the plan is described by its reason: %s" % button
    after = html[html.index(button):]
    assert re.match(r'[\s\S]*?</button>\s*<p[^>]*id="plan-create-why"', after), "the reason sits right after the button"
    assert re.search(r"function planBlock\(view, planner\)", feedback), "planBlock(view, planner) names what is missing"
    assert re.search(r'setBlocked\(el\("plan-create"\), planBlock\(', code), "setPlanBusy blocks Create the plan with its reason"
    es = catalog()
    reasons = ("Publish the kit to main first (step 3).", "Save the idea first.",
               "Choose the coding tool that drafts the plan.", "Save your name first (step 1).")
    for text in reasons:
        assert text in feedback, "the page can say %r" % text
        assert text in es, "%r has a Spanish translation" % text
    out = run_page("""
        var cases = [[{idea: "x", kit_on_main: false}, "claude"], [{idea: "", kit_on_main: true}, "claude"],
                     [{idea: "x", kit_on_main: true}, ""], [{idea: "x", kit_on_main: true}, "claude"]];
        var why = cases.map(function (c) { return planBlock(c[0], c[1]); });
        var button = el("plan-create");
        setBlocked(button, why[0]);
        var blocked = {aria: button.getAttribute("aria-disabled"), native: button.disabled,
                       line: el("plan-create-why").textContent, shown: !el("plan-create-why").hidden};
        setBlocked(button, null);
        var free = {aria: button.getAttribute("aria-disabled"), shown: !el("plan-create-why").hidden};
        // The gate's next step is something the page does: it points to that control (scroll, focus, highlight).
        el("finish").hidden = false;
        el("prepare").hidden = false;
        var spot = pointTo(why[0].target), target = el(why[0].target);
        return {why: why, blocked: blocked, free: free, spot: spot, focused: target.focusCount,
                scrolled: target.scrolls.length, lit: target.classList.contains("spotlight"),
                publish: nextControl({guidance: {action: "publish"}, human: "ana"}),
                name: nextControl({guidance: {action: "publish"}, human: ""}),
                none: nextControl({guidance: {action: ""}, human: "ana"})};
    """, language="es")
    if out is None:
        return
    why = out["why"]
    assert why[0] == {"text": "Publish the kit to main first (step 3).", "target": "publish-preview"}, why
    assert why[1]["text"] == "Save the idea first." and why[1]["target"] == "idea-text", why
    assert why[2]["text"] == "Choose the coding tool that drafts the plan.", why
    assert why[3] is None, "nothing blocks a ready plan: %r" % why[3]
    blocked = out["blocked"]
    assert blocked["aria"] == "true" and not blocked["native"], "blocked is aria-disabled, never native: %r" % blocked
    assert blocked["shown"] and blocked["line"] == es["Publish the kit to main first (step 3)."], blocked
    assert out["free"] == {"aria": None, "shown": False}, out["free"]
    assert out["spot"] and out["focused"] == 1 and out["scrolled"] == 1 and out["lit"], \
        "the page points to its own Publish control: %r" % out
    assert out["publish"] == "publish-preview" and out["name"] == "human-name" and out["none"] == "", out


def actions_show_busy_and_result(root, tmp):
    html = page()
    code = script(html)
    labels = re.search(r"var BUSY_LABEL = (\{[\s\S]*?\});", block(code))
    assert labels, "var BUSY_LABEL maps each action button to its in-button busy label"
    busy = json.loads(re.sub(r"(\{|,)\s*([a-z][\w-]*):", r'\1"\2":', re.sub(r",\s*\}", "}", labels.group(1))))
    started = set(re.findall(r'el\("([\w-]+)"\)\.onclick = function \(\) \{\s*(?:var [^;]*;\s*)?action\(this', code))
    started |= set(re.findall(r'action\(el\("([\w-]+)"\)', code))
    assert {"check", "install", "publish-kit", "human-save", "save", "idea-save"} <= started, started
    started |= {"plan-create", "plan-change"}  # through startPlanning(this, note)
    missing = sorted(started - set(busy))
    assert not missing, "every button that runs a request has a busy label: %r" % missing
    es = catalog()
    for label in set(busy.values()) | {"Done at {time}.", "Failed at {time}: {error}"}:
        assert label in es, "%r has a Spanish translation" % label
    assert re.search(r'<p[^>]*id="check-result"[^>]*role="status"[^>]*aria-live="polite"', html) or \
        re.search(r'<p[^>]*id="check-result"[^>]*aria-live="polite"[^>]*role="status"', html), \
        "Check what's next has a result line announced to screen readers"
    out = run_page("""
        var release, gate = new Promise(function (r) { release = r; }), button = el("save");
        var running = action(button, function () { return gate; });
        var during = {busy: button.getAttribute("aria-busy"), text: button.textContent, native: button.disabled};
        release();
        await running;
        var line = el("save-result");
        var after = {busy: button.getAttribute("aria-busy"), text: button.textContent.trim(), native: button.disabled,
                     result: line.textContent, live: line.getAttribute("aria-live"), role: line.getAttribute("role"),
                     next: button.nextElementSibling === line};
        var failing = action(el("human-save"), async function () { throw Error("The name must be lowercase letters."); });
        await failing;
        var bad = el("human-save-result");
        return {during: during, after: after, failed: bad.textContent, error: bad.classList.contains("error")};
    """, language="es")
    if out is None:
        return
    assert out["during"] == {"busy": "true", "text": es["Saving…"], "native": True}, out["during"]
    after = out["after"]
    assert after["busy"] is None and after["text"] == "Save preferences" and not after["native"], after
    assert after["result"] == "Listo a las 21:04.", after
    assert after["live"] == "polite" and after["role"] == "status" and after["next"], after
    assert out["failed"].startswith("Falló a las 21:04: ") and out["error"], out


def check_reports_even_when_nothing_changed(root, tmp):
    code = script(page())
    render = page_function(code, "render")
    assert re.search(r"report\(checkOwner\(\), checkSummary\(", render), \
        "render reports a finished check next to the button that asked for it"
    es = catalog()
    for text in ("Checked at {time}", "nothing changed", "{count} things to do", "1 thing to do", "everything is ready"):
        assert text in es, "%r has a Spanish translation" % text
    out = run_page("""
        var todo = [{state: "ok", text: "1. kit"}, {state: "todo", text: "2. push the kit to main"},
                    {state: "todo", text: "3. a plan"}];
        var done = todo.slice(0, 1).concat([{state: "ok", text: "2. kit on main"}]);
        var when = new Date("2026-11-13T21:04:00");
        return {same: checkSummary(todo, {checks: todo}, when), changed: checkSummary(todo, {checks: done.concat([todo[2]])}, when),
                ready: checkSummary(todo, {checks: done, ready: true}, when), fresh: checkSummary(null, {checks: todo}, when)};
    """, language="es")
    if out is None:
        return
    assert out["same"] == "Revisado a las 21:04 · no cambió nada · 2 cosas por hacer", out
    assert out["changed"] == "Revisado a las 21:04 · 1 cosa por hacer", out
    assert out["ready"] == "Revisado a las 21:04 · todo está listo", out
    assert out["fresh"] == "Revisado a las 21:04 · 2 cosas por hacer", out
    english = run_page("return checkSummary([], {checks: []}, new Date('2026-11-13T09:05:00'));")
    assert english == "Checked at 09:05 · nothing changed · everything is ready", english


def no_wait_cursor_on_blocked_buttons(root, tmp):
    html = page()
    found = rules(html)
    for selector, body in found:
        if re.search(r"cursor:\s*wait", body):
            assert re.search(r'aria-busy="true"', selector) and ":disabled" not in selector, \
                "the wait cursor is only for a running request: %s { %s }" % (selector, body.strip())
    blocked = [s for s, b in found if re.search(r"cursor:\s*not-allowed", b)]
    assert any(":disabled" in s for s in blocked), "a disabled button shows not-allowed: %r" % blocked
    assert any('[aria-disabled="true"]' in s for s in blocked), "a blocked (aria-disabled) button too: %r" % blocked
    assert any('aria-busy="true"' in s and re.search(r"cursor:\s*wait", b) for s, b in found), \
        "a running button shows the wait cursor"
    spinner = [b for s, b in found if 'aria-busy="true"]::before' in s]
    assert spinner and "animation" in spinner[0], "a small spinner turns inside the running button"
    still = [s for s, b in found if s.startswith("@media (prefers-reduced-motion: reduce)") and "animation: none" in b]
    assert still, "reduced motion stops the spinner"
    out = run_page("""
        var button = el("plan-create");
        setBlocked(button, planBlock({idea: "x", kit_on_main: false}, "claude"));
        return {busy: button.getAttribute("aria-busy"), aria: button.getAttribute("aria-disabled")};
    """)
    if out is not None:
        assert out == {"busy": None, "aria": "true"}, "blocked is never busy: %r" % out


def layout_is_stable_across_refresh(root, tmp):
    html = page()
    code = script(html)
    found = rules(html)
    reserved = [b for s, b in found if re.search(r"(^|[\s,])\.action-result\s*$", s)]
    assert reserved and re.search(r"min-height:\s*\S+", reserved[0]), "result lines reserve their space: %r" % reserved
    url = [b for s, b in found if re.search(r'#preferences input\[type="url"\]', s)]
    assert url and re.search(r"width:\s*100%", url[0]), "the app link input takes the whole row"
    hint = [b for s, b in found if re.search(r"#live-url-hint", s)]
    assert hint and re.search(r"display:\s*block", hint[0]), "its hint goes on its own line, under the input"
    render = page_function(code, "render")
    # Polling during an operation never hides whole sections or buttons (Dylan's run: the page jumped).
    assert not re.search(r'el\("preferences"\)\.hidden = [^;]*busy', render), "preferences stay while a check runs"
    assert not re.search(r'el\("repair"\)\.hidden = [^;]*busy', render), "Repair stays; it is disabled while busy"
    assert re.search(r"drawChecks\(data\)", render), "render draws the checklist through drawChecks"
    # Before the first status arrives the page shows no panel at all (it flashed the welcome screen).
    content = re.search(r'<main[^>]*id="content"[^>]*>', html).group(0)
    assert "data-loading" in content, "the panel waits for the first status: %s" % content
    assert any("#content[data-loading]" in s and re.search(r"(visibility:\s*hidden|display:\s*none)", b)
               for s, b in found), "a loading panel hides its sections"
    assert re.search(r'el\("content"\)\.removeAttribute\("data-loading"\)', code), "the first status shows the panel"
    out = run_page("""
        var data = {checks: [{state: "ok", text: "1. kit"}, {state: "todo", text: "2. push the kit to main"}]};
        var first = drawChecks(data), list = el("checks"), count = list.replaced, rows = list.children.length;
        var again = drawChecks(JSON.parse(JSON.stringify(data)));
        var changed = drawChecks({checks: data.checks.slice(0, 1)});
        return {first: first, again: again, changed: changed, rows: rows, replacedTwice: list.replaced - count};
    """, language="es")
    if out is None:
        return
    assert out["first"] and not out["again"] and out["changed"], "unchanged data keeps the same DOM: %r" % out
    assert out["rows"] == 2 and out["replacedTwice"] == 1, out


def out_of_order_click_explains_the_next_step(root, tmp):
    html = page()
    found = rules(html)
    region = re.search(r'<div[^>]*id="toast-region"[^>]*>', html)
    assert region and 'aria-live="polite"' in region.group(0), "the toast lives in a polite live region"
    toast = re.search(r'<div[^>]*id="toast"[^>]*>', html)
    assert toast and "hidden" in toast.group(0), "one toast element, hidden until needed"
    close = re.search(r'<button[^>]*id="toast-close"[^>]*>', html)
    assert close and 'data-i18n-aria="Dismiss"' in close.group(0), "the close button is named, in both languages"
    assert any(s.strip().endswith(".toast") and "position: fixed" in b and re.search(r"right:\s*\d", b) for s, b in found), \
        "the toast sits on the right"
    mobile = [b for s, b in found if s.startswith("@media (max-width: 600px)") and s.endswith(".toast")]
    assert mobile and re.search(r"left:\s*16px", mobile[0]) and re.search(r"right:\s*16px", mobile[0]), \
        "full width at the bottom on a phone: %r" % mobile
    assert any(s.startswith("@media (prefers-reduced-motion: reduce)") and ".toast" in s and "transition: none" in b
               for s, b in found), "reduced motion: no toast transition"
    es = catalog()
    for text in ("Go there", "Dismiss", "Not yet"):
        assert text in es, "%r has a Spanish translation" % text
    out = run_page("""
        el("finish").hidden = false;
        el("prepare").hidden = false;
        el("planning").hidden = false;
        var button = el("plan-create"), clicked = 0;
        button.onclick = function () { clicked += 1; };
        setBlocked(button, planBlock({idea: "x", kit_on_main: false}, "claude"));
        var event = fire(button, "click");
        var box = el("toast"), shown = {hidden: box.hidden, text: el("toast-text").textContent, go: !el("toast-go").hidden,
                                         prevented: event.defaultPrevented, clicked: clicked};
        // Hover pauses the auto-hide; leaving resumes it; it hides by itself afterwards.
        fire(box, "mouseenter");
        var paused = timers.length;
        advance(60000);
        var stillShown = !box.hidden;
        fire(box, "mouseleave");
        var resumed = timers.length;
        advance(60000);
        var autoHidden = box.hidden;
        // Focus inside pauses it too.
        fire(button, "click");
        fire(el("toast-go"), "focusin");
        advance(60000);
        var focusKeeps = !box.hidden;
        // One at a time: a second blocked click replaces the text in the same toast.
        setBlocked(el("publish-preview"), {text: "Save your name first (step 1).", target: "human-name"});
        fire(el("publish-preview"), "click");
        var second = {count: document.querySelectorAll(".toast").length, text: el("toast-text").textContent};
        // Go there points to the control; the toast closes.
        fire(el("toast-go"), "click");
        var went = {hidden: box.hidden, focused: el("human-name").focusCount, lit: el("human-name").classList.contains("spotlight")};
        fire(button, "click");
        fire(el("toast-close"), "click");
        var dismissed = box.hidden;
        setBlocked(button, null);
        fire(button, "click");
        return {shown: shown, paused: paused, stillShown: stillShown, resumed: resumed, autoHidden: autoHidden,
                focusKeeps: focusKeeps, second: second, went: went, dismissed: dismissed, freeClick: clicked};
    """, language="es")
    if out is None:
        return
    shown = out["shown"]
    assert not shown["hidden"] and shown["prevented"] and shown["clicked"] == 0, \
        "a blocked click explains itself instead of acting: %r" % shown
    assert es["Publish the kit to main first (step 3)."] in shown["text"] and shown["go"], shown
    assert out["paused"] == 0 and out["stillShown"], "hover pauses the auto-hide: %r" % out
    assert out["resumed"] == 1 and out["autoHidden"], "leaving resumes it and it hides by itself: %r" % out
    assert out["focusKeeps"], "focus inside the toast keeps it open"
    assert out["second"] == {"count": 1, "text": es["Save your name first (step 1)."]}, out["second"]
    assert out["went"] == {"hidden": True, "focused": 1, "lit": True}, "Go there points to the control: %r" % out["went"]
    assert out["dismissed"], "the close button dismisses it"
    assert out["freeClick"] == 1, "an unblocked button acts normally"


TESTS = [blocked_buttons_say_why, actions_show_busy_and_result, check_reports_even_when_nothing_changed,
         no_wait_cursor_on_blocked_buttons, layout_is_stable_across_refresh, out_of_order_click_explains_the_next_step]


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    ROOT = args.package.resolve()
    failed = 0
    for test in [t for t in TESTS if not args.case or t.__name__ in args.case]:
        tmp = Path(tempfile.mkdtemp(prefix="uak-feedback-"))
        started = time.monotonic()
        try:
            test(ROOT, tmp)
            print("PASS %s (%.2fs)" % (test.__name__, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s: %s)" % (test.__name__, type(exc).__name__, str(exc)[:1500]))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)
    print("SETUP_FEEDBACK_RESULT %s failed=%d" % ("PASS" if not failed else "FAIL", failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
