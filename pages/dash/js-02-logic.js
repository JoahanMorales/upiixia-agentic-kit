  // The scale of a wide window (wideScale): the app is zoomed, the dialogs too (CSS), and what the script places with fixed
  // coordinates inside the zoomed app divides by it. Past the cap the page is wider than 1600 px once scaled: html.vw.
  var Z = 1;
  function fitScale() {
    var r = document.documentElement, app = document.querySelector && document.querySelector(".app");
    Z = wideScale(window.innerWidth || 0);
    if (r.style && r.style.setProperty) r.style.setProperty("--z", String(Z));
    if (app && app.style) app.style.zoom = Z > 1 ? String(Z) : "";
    if (r.classList) r.classList.toggle("vw", Z > 1 && window.innerWidth / Z >= 1600);
  }
  fitScale();
  var ui = { tab: "sum", agent: "", task: "", kind: "", q: "", view: "list", period: 0, mf: "all", bv: "cols", mv: "list", bk: "", bh: "", bp: "", bq: "", allDone: false, open: {}, more: {} };
  var store = null; try { store = window.localStorage; } catch (e) {}
  try { var saved = JSON.parse(store.getItem("uak-dash") || "{}"); ["tab", "agent", "task", "kind", "q", "view", "period", "mf", "bv", "mv", "bk", "bh", "bp", "bq"].forEach(function (k) { if (k in saved) ui[k] = saved[k]; }); } catch (e) {}
  function save() {
    try { store.setItem("uak-dash", JSON.stringify({ tab: ui.tab, agent: ui.agent, task: ui.task, kind: ui.kind, q: ui.q, view: ui.view, period: ui.period, mf: ui.mf, bv: ui.bv, mv: ui.mv, bk: ui.bk, bh: ui.bh, bp: ui.bp, bq: ui.bq })); } catch (e) {}
    try { history.replaceState(null, "", "#" + ui.tab); } catch (e) {}
  }
  function known(k) { return TABS.some(function (t) { return t[0] === k; }); }
  var hashTab = (location.hash || "").slice(1); if (known(hashTab)) ui.tab = hashTab;
  if (!known(ui.tab)) ui.tab = "sum";
  UAKLook.onchange(function () { reportSize(); });

  /* logic:begin (pure functions, no DOM: test_dashboard_truth runs this section under node) */
  var KIND = { exit1: "git error", exit2: "usage error", exit3: "conflict", exitguard: "guard block" };
  function label(r) { return r.source === "agent" ? "note: " + r.kind : (KIND[r.kind] || r.kind); }
  function depGraph(tasks) {
    var g = { dep: {}, unb: {}, task: {} };
    tasks.forEach(function (t) { g.task[t.id] = t; });
    tasks.forEach(function (t) {
      var seen = {};
      g.dep[t.id] = ((t.depends || "").replace(/\([^)]*\)/g, "").match(/[A-Z][A-Z0-9]*-\d+/g) || []).filter(function (x) { if (x === t.id || seen[x]) return false; seen[x] = 1; return true; });
    });
    tasks.forEach(function (t) { g.dep[t.id].forEach(function (x) { (g.unb[x] = g.unb[x] || []).push(t.id); }); });
    return g;
  }
  function kindOf(g, id) { var t = g.task[id]; return t ? t.state : "MISSING"; }
  function unmet(g, id) { return (g.dep[id] || []).filter(function (x) { return kindOf(g, x) !== "INTEGRATED"; }).map(function (x) { return { id: x, state: kindOf(g, x) }; }); }
  function behind(g, id) {
    var seen = {}, out = [], todo = unmet(g, id).map(function (x) { return x.id; }), direct = {};
    todo.forEach(function (x) { direct[x] = 1; });
    while (todo.length) {
      var x = todo.shift(); if (seen[x] || x === id) continue; seen[x] = 1;
      unmet(g, x).forEach(function (y) { if (!seen[y.id] && y.id !== id) { if (!direct[y.id]) out.push(y); todo.push(y.id); } });
    }
    return out;
  }
  var TID = /\b[A-Z][A-Z0-9]*-\d+\b/g, FILE = /[\w.\/-]+\.(?:py|sh|js|html|md|txt|json|yml|tsv)\b/g;
  function memGraph(lessons, decisions) {
    var nodes = {}, edges = [], entries = [];
    function node(id, type, lab) { return nodes[id] = nodes[id] || { id: id, type: type, label: lab, deg: 0 }; }
    function entry(e, key, kind, who) {
      var refs = {}, text = String(e.text || "");
      (text.match(TID) || []).forEach(function (x) { refs["t:" + x] = ["task", x]; });
      if (e.task && e.task !== "-") refs["t:" + e.task] = ["task", e.task];
      (text.match(FILE) || []).forEach(function (x) { refs["f:" + x] = ["file", x]; });
      String(e.paths || "").split(/,\s*/).forEach(function (x) { if (x) refs["f:" + x] = ["file", x]; });
      if (who) refs["a:" + who] = ["agent", who];
      entries.push({ id: key, kind: kind, text: text, who: who, t: e.t, refs: refs });
    }
    lessons.forEach(function (e, i) { entry(e, "l" + i, "lesson", e.agent); });
    decisions.forEach(function (e, i) { entry(e, "d" + i, "decision", e.who); });
    var count = {}; entries.forEach(function (e) { Object.keys(e.refs).forEach(function (k) { count[k] = (count[k] || 0) + 1; }); });
    var linked = 0;
    entries.forEach(function (e) {
      var any = false;
      Object.keys(e.refs).forEach(function (k) {
        if (count[k] < 2) return;
        any = true; var r = e.refs[k]; node(k, r[0], r[1]).deg++; edges.push([e.id, k]);
      });
      if (any) { node(e.id, e.kind, e.id).deg = 1; linked++; }
    });
    return { nodes: Object.keys(nodes).map(function (k) { return nodes[k]; }), edges: edges, entries: entries, linked: linked, isolated: entries.length - linked };
  }
  // Structure instead of one force blob: each task is the centre of a small cluster of the entries that cite it most, entries that
  // cite several tasks sit between them, clusters are packed side by side (largest component first), files and agents hang off
  // the entries they link to. The space is unbounded: the caller scales the view to fit, nothing is clamped.
  function nodeR(x) { return x.type === "task" ? 8 + Math.min(8, Math.round(x.deg / 2)) : x.type === "lesson" || x.type === "decision" ? 5 : x.type === "agent" ? 4.5 : 3.5; }
  function clusterLayout(nodes, edges) {
    var by = {}, adj = {}, pos = {}, tasks = [], cl = {}, comp = {};
    nodes.forEach(function (n) { by[n.id] = n; adj[n.id] = []; if (n.type === "task") tasks.push(n); });
    edges.forEach(function (e) { if (by[e[0]] && by[e[1]]) { adj[e[0]].push(e[1]); adj[e[1]].push(e[0]); } });
    function tasksOf(id) { return adj[id].filter(function (x) { return by[x].type === "task"; }); }
    var entries = nodes.filter(function (n) { return n.type === "lesson" || n.type === "decision"; }), home = {};
    entries.forEach(function (e) {
      var ts = tasksOf(e.id).sort(function (a, b) { return by[b].deg - by[a].deg || (a < b ? -1 : 1); });
      if (ts.length) { home[e.id] = ts[0]; (cl[ts[0]] = cl[ts[0]] || []).push(e.id); }
    });
    // components over tasks joined by an entry that cites both
    var up = {}; tasks.forEach(function (t) { up[t.id] = t.id; });
    function find(x) { while (up[x] !== x) { up[x] = up[up[x]]; x = up[x]; } return x; }
    entries.forEach(function (e) { var ts = tasksOf(e.id); for (var i = 1; i < ts.length; i++) up[find(ts[i])] = find(ts[0]); });
    var csize = {}; tasks.forEach(function (t) { var r = find(t.id); csize[r] = (csize[r] || 0) + 1 + (cl[t.id] || []).length; });
    var order = tasks.slice().sort(function (a, b) { return csize[find(b.id)] - csize[find(a.id)] || (find(a.id) < find(b.id) ? -1 : find(a.id) > find(b.id) ? 1 : 0) || (cl[b.id] || []).length - (cl[a.id] || []).length || (a.id < b.id ? -1 : 1); });
    var x = 0, y = 0, rowH = 0, area = 0;
    order.forEach(function (t) { var n = (cl[t.id] || []).length, dd = 2 * (n ? 34 + n * 2.4 : 0) + 110; area += dd * dd; });
    var maxW = Math.sqrt(area * 1.5);
    order.forEach(function (t) {
      var m = cl[t.id] || [], R = m.length ? 34 + m.length * 2.4 : 0, d = 2 * R + 110;
      if (x + d > maxW && x > 0) { x = 0; y += rowH; rowH = 0; }
      var cx = x + d / 2, cy = y + d / 2; pos[t.id] = { x: cx, y: cy };
      m.forEach(function (id, i) { var a = 6.2832 * i / m.length - 1.57; pos[id] = { x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R }; });
      x += d; rowH = Math.max(rowH, d);
    });
    entries.forEach(function (e) {   // an entry that cites several tasks sits between them
      var ts = tasksOf(e.id).filter(function (t) { return pos[t]; });
      if (ts.length > 1) { var sx = 0, sy = 0; ts.forEach(function (t) { sx += pos[t].x; sy += pos[t].y; }); pos[e.id] = { x: sx / ts.length, y: sy / ts.length }; }
    });
    var loose = nodes.filter(function (n) { return !pos[n.id] && n.type !== "file" && n.type !== "agent"; });
    loose.forEach(function (n, i) { pos[n.id] = { x: (i % 10) * 26, y: y + rowH + 20 + Math.floor(i / 10) * 26 }; });
    nodes.filter(function (n) { return n.type === "file" || n.type === "agent"; }).forEach(function (n, k) {
      var sx = 0, sy = 0, c = 0; adj[n.id].forEach(function (id) { if (pos[id]) { sx += pos[id].x; sy += pos[id].y; c++; } });
      var a = k * 2.4; pos[n.id] = c ? { x: sx / c + Math.cos(a) * 16, y: sy / c + Math.sin(a) * 16 } : { x: 0, y: y + rowH + 80 };
    });
    var x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    nodes.forEach(function (n) { var p = pos[n.id]; if (p) { x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); } });
    return { pos: pos, box: { x: x0, y: y0, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0) }, home: home };
  }
  function bbFilter(recs, f, now) {
    var PER = { d: 86400000, w: 7 * 86400000 }, ql = (f.q || "").toLowerCase();
    return recs.filter(function (r) {
      return (!f.k || label(r) === f.k) && (!f.h || r.harness === f.h) && (!f.p || now - Date.parse(r.time) <= PER[f.p]) && (!ql || (r.command + " " + r.what + " " + r.fix + " " + label(r)).toLowerCase().indexOf(ql) >= 0);
    });
  }
  function tokenBreak(tk, tasks) {
    var by = tk.by_task || {}, owner = {}, per = {}, top = [], done = [], untied = 0;
    tasks.forEach(function (t) { owner[t.id] = t; });
    Object.keys(by).forEach(function (id) {
      var t = owner[id]; if (!t) { untied += by[id]; return; }
      top.push({ id: id, n: by[id], state: t.state, owner: t.owner, title: t.title });
      if (t && t.owner) per[t.owner] = (per[t.owner] || 0) + by[id];
      if (t && t.state === "INTEGRATED") done.push(by[id]);
    });
    top.sort(function (a, b) { return b.n - a.n; }); done.sort(function (a, b) { return a - b; });
    var sum = done.reduce(function (a, b) { return a + b; }, 0);
    return { top: top, untied: untied, perAgent: per, done: done.length, avg: done.length ? Math.round(sum / done.length) : 0, median: done.length ? done[Math.floor(done.length / 2)] : 0 };
  }
  function shareStats(d) {
    var ag = d.agents.filter(function (a) { return !a.is_human; }), st = (d.progress.states || {}), began = ag.map(function (a) { return a.started; }).filter(Boolean);
    return { name: d.repo, integrated: st.INTEGRATED || 0, total: d.progress.total, agents: ag.length, tokens: d.tokens && d.tokens.total ? d.tokens.total : null,
      commits: typeof d.commits === "number" ? d.commits : null, since: began.length ? Math.min.apply(null, began) : null };
  }
  // One definition of "stalled" for the figure, the list and the board: no move for the stall limit, or a claim past its lease.
  function stalledMin(t, now) {
    if (t.stalled) return t.stalled;
    return t.state === "CLAIMED" && t.lease && t.lease < now ? Math.max(1, Math.round((now - (t.progress_changed || t.updated || t.lease)) / 60)) : 0;
  }
  // Counts that appear in two places are computed here once (figures_agree_across_tabs asserts them).
  function planCounts(tasks) { var c = { plan: 0, cancelled: 0 }; tasks.forEach(function (t) { if (t.state === "CANCELLED") c.cancelled++; else c.plan++; }); return c; }
  // A cancelled or integrated task is nobody's to decide: a human-queue entry that outlived its task is not shown (the claims branch keeps the entry after a cancel).
  function openHumanQueue(queue, tasks) {
    var by = {}; tasks.forEach(function (t) { by[t.id] = t; });
    return queue.filter(function (q) { return q.state === "HUMAN" && !(by[q.task] && (by[q.task].state === "CANCELLED" || by[q.task].state === "INTEGRATED")); });
  }
  // The time a review has waited is the task's own sub-state clock, for the figure and for the row alike.
  function reviewSince(o, tasks) { for (var i = 0; i < tasks.length; i++) if (tasks[i].id === o.task && tasks[i].sub && tasks[i].sub.since) return tasks[i].sub.since; return o.since; }
  // Labels placed inside the view, flipped to the left of their node near the right edge, and hidden when they would overlap one
  // already placed (the selected node's labels, marked "must", are always shown).
  function fitLabels(items, view) {
    var out = {}, placed = [];
    items.forEach(function (it) {
      var bx, by, anchor;
      if (it.below) { bx = it.x - it.w / 2; by = it.y + it.r + 2; anchor = "middle"; }
      else { bx = it.x + it.r + 4; by = it.y - it.h / 2; anchor = "start"; if (bx + it.w > view.x + view.w - 2) { bx = it.x - it.r - 4 - it.w; anchor = "end"; } }
      bx = Math.max(view.x + 2, Math.min(view.x + view.w - it.w - 2, bx)); by = Math.max(view.y + 2, Math.min(view.y + view.h - it.h - 2, by));
      var hit = placed.some(function (q) { return bx < q[0] + q[2] && q[0] < bx + it.w && by < q[1] + q[3] && q[1] < by + it.h; });
      if (hit && !it.must) return;
      placed.push([bx, by, it.w, it.h]);
      out[it.id] = { x: anchor === "middle" ? bx + it.w / 2 : anchor === "start" ? bx : bx + it.w, y: by + it.h * .8, anchor: anchor, box: [bx, by, it.w, it.h] };
    });
    return out;
  }
  // Entries with no visible link, grouped by title with a count.
  function groupOrphans(items) { var seen = {}, out = []; items.forEach(function (x) { if (seen[x.t]) seen[x.t].n++; else out.push(seen[x.t] = { t: x.t, full: x.full, n: 1 }); }); return out; }
  function lbMove(n, cur, key) {
    if (!n) return -1;
    if (key === 'Home') return 0; if (key === 'End') return n - 1;
    if (key === "ArrowDown") return Math.min(n - 1, cur + 1); if (key === "ArrowUp") return Math.max(0, cur - 1);
    return cur;
  }
  function lbType(labels, cur, buf) {
    var b = buf.toLowerCase(), n = labels.length, i, start = buf.length === 1 ? cur + 1 : cur;
    for (i = 0; i < n; i++) { var k = (start + i) % n; if (labels[k].toLowerCase().indexOf(b) === 0) return k; }
    return cur;
  }
  // What a page does when data.js names another page version: reload once, or, when the address says it already tried (storage may be
  // blocked), stay and say that a newer page exists.
  function reloadPlan(mine, theirs, stored, search) {
    var q = /[?&]uak=([^&#]*)/.exec(search || ""), tried = stored || "";
    if (q && q[1] === theirs) tried = theirs;
    if (pageIsNewer(mine, theirs, tried)) return "reload";
    return !!mine && mine !== "dev" && !!theirs && mine !== theirs ? "notice" : "stay";
  }
  function pageIsNewer(mine, theirs, tried) { return !!mine && !!theirs && mine !== "dev" && mine !== theirs && tried !== theirs; }
  // Share: what the page may offer, decided by testing a capability on an object that stands for navigator and window (never by the browser's name).
  // share: the system sheet takes a PNG file; copy: the async clipboard takes an image (a secure context only); download: a link with
  // "download" is honoured, which a phone does only from a secure context (a touch screen over plain http gets the image to press and hold).
  function shareCaps(e) {
    var n = e.nav || {}, can = false;
    try { can = typeof n.share === "function" && typeof n.canShare === "function" && !!e.files && n.canShare({ files: e.files }) === true; } catch (x) { can = false; }
    return { share: can, copy: !!(e.secure && n.clipboard && typeof n.clipboard.write === "function" && e.clipboardItem), download: !!(e.anchorDownload && (e.secure || !e.coarse)) };
  }
  // The id of the sentence for a refusal (null when the person only closed the system sheet): it says what to do instead.
  function shareRefusal(action, caps, err) {
    if (action === "share" && err && err.name === "AbortError") return null;
    if (action === "download") return "download";
    return action + (caps.download ? "-dl" : "");
  }
  // The bytes of a PNG data URL (null for anything else): the copy and the shared file are made from the same URL the image shows and the download links.
  function pngBytes(url) {
    var m = /^data:image\/png;base64,([A-Za-z0-9+\/=]+)$/.exec(url || "");
    if (!m) return null;
    var bin = atob(m[1]), b = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i);
    return b;
  }
  // The card as the PNG the dialog shows: a failure (toDataURL throws, or answers "data:," or a PNG that is not the card's size) is {error}, never a broken image.
  function exportCard(cv, w, h) {
    try {
      var url = cv.toDataURL("image/png"), b = pngBytes(url);
      if (!b || b.length < 24) return { error: "not-a-png:" + String(url).slice(0, 24) };
      var pw = b[16] * 16777216 + b[17] * 65536 + b[18] * 256 + b[19], ph = b[20] * 16777216 + b[21] * 65536 + b[22] * 256 + b[23];
      return pw === w && ph === h ? { url: url } : { error: "png-size:" + pw + "x" + ph };
    } catch (e) { return { error: String(e && e.message || e) }; }
  }
  // What the copy and the share hand over, made from the bytes of the image shown (env stands for window: its Blob, File and ClipboardItem).
  function copyImage(env, bytes) { return env.nav.clipboard.write([new env.ClipboardItem({ "image/png": new env.Blob([bytes], { type: "image/png" }) })]); }
  function shareImage(env, bytes, name, title) { return env.nav.share({ files: [new env.File([bytes], name, { type: "image/png" })], title: title }); }
  // The summary's arrangement (UAK-165): {main, side, hide}, lists of component names. def is [[name, column], ...] in the default
  // order. A stored arrangement is checked against it: a name it does not know is left out (note "unknown"), one that cannot be
  // read gives the default (note "corrupt"), a component it does not name takes its default place, "needs" is never hidden.
  function arrRead(def, raw) {
    var x = raw, out = { main: [], side: [], hide: [] }, seen = {}, home = {}, note = "";
    def.forEach(function (b) { home[b[0]] = b[1]; });
    if (typeof x === "string") { try { x = x.length > 4096 ? 0 : JSON.parse(x); } catch (e) { x = 0; } }
    if (x === null || x === undefined) x = {};
    else if (!x || typeof x !== "object" || !Array.isArray(x.main) || !Array.isArray(x.side)) { x = {}; note = "corrupt"; }
    ["main", "side", "hide"].forEach(function (k) {
      (Array.isArray(x[k]) ? x[k] : []).forEach(function (n) {
        if (typeof n !== "string" || !Object.prototype.hasOwnProperty.call(home, n)) { note = note || "unknown"; return; }
        if (seen[n] || (k === "hide" && n === "needs")) return;
        seen[n] = 1; out[k].push(n);
      });
    });
    def.forEach(function (b, i) {   // in its default column, after every component that precedes it by default there (else first)
      if (seen[b[0]]) return;
      var col = out[b[1]], at = 0;
      for (var j = 0; j < i; j++) at = Math.max(at, col.indexOf(def[j][0]) + 1);
      col.splice(at, 0, b[0]);
    });
    return { lay: out, note: note };
  }
  function arrCopy(a) { return { main: a.main.slice(), side: a.side.slice(), hide: a.hide.slice() }; }
  // dir -1 up, 1 down, 0 to the other column (same position). stacked: one column on screen, so up from the side's first and down
  // from the main's last cross over, as the eye sees them.
  function arrMove(a, name, dir, stacked) {
    var b = arrCopy(a), c = b.main.indexOf(name) >= 0 ? "main" : b.side.indexOf(name) >= 0 ? "side" : "", o = c === "main" ? "side" : "main";
    if (!c) return b;
    var l = b[c], i = l.indexOf(name), j = i + dir;
    if (!dir) { l.splice(i, 1); b[o].splice(Math.min(i, b[o].length), 0, name); }
    else if (j >= 0 && j < l.length) { l.splice(i, 1); l.splice(j, 0, name); }
    else if (stacked && (c === "main") === (dir > 0)) { l.splice(i, 1); if (dir > 0) b[o].unshift(name); else b[o].push(name); }
    return b;
  }
  // A drop: NAME (shown) at position AT of column COL.
  function arrPlace(a, name, col, at) {
    var b = arrCopy(a);
    if (b.hide.indexOf(name) >= 0 || !b[col]) return b;
    ["main", "side"].forEach(function (k) { var i = b[k].indexOf(name); if (i >= 0) b[k].splice(i, 1); });
    b[col].splice(Math.max(0, Math.min(at, b[col].length)), 0, name);
    return b;
  }
  function arrHide(a, name) {
    var b = arrCopy(a);
    if (name === "needs" || b.hide.indexOf(name) >= 0) return b;
    ["main", "side"].forEach(function (k) { var i = b[k].indexOf(name); if (i >= 0) { b[k].splice(i, 1); b.hide.push(name); } });
    return b;
  }
  function arrAdd(def, a, name) { return arrRead(def, { main: a.main, side: a.side, hide: a.hide.filter(function (n) { return n !== name; }) }).lay; }
  // How the summary uses its width (UAK-198). W: the width of its content; MAIN, SIDE: how many components each list shows. Up to
  // 1480 px it is the summary approved at 1280 px: the main column and a side of 296 px. From 1480 px (a window about 1600 px wide)
  // the side shows its components in two columns, from 2900 px in three, each 296 to 440 px (36 % of the width shared out), never
  // more columns than components; the main column takes the rest. A list alone on the page flows into the columns of its width.
  // Derived from the width at every draw, never stored: the viewer's arrangement stays the two lists.
  function sumCols(w, main, side) {
    var n = w >= 2900 ? 3 : w >= 1480 ? 2 : 1;
    if (!main || !side) return { flow: Math.max(1, Math.min(n, main + side)), side: 0, w: 0 };
    var k = Math.min(n, side), cw = n === 1 ? 296 : Math.max(296, Math.min(440, Math.round((w * 0.36 - 16 * (n - 1)) / n)));
    return { flow: 1, side: k, w: k * cw + 16 * (k - 1) };
  }
  // How much the page scales up on a wide window (UAK-198, the human's choice A): 1 up to 1432 px, then the window's width over
  // 1432 (the page is laid out as at 1432 px and drawn larger), at most 1.8.
  function wideScale(w) { return w > 1432 ? Math.min(1.8, Math.round(w / 1432 * 1000) / 1000) : 1; }
  // The memory graph's canvas: 760 x 560 in a card up to 800 px wide (the approved one); wider, the card's own width (labels keep
  // their size) and a height that fits the window, no taller than the graph needs at its largest scale (1.4).
  function graphBox(cw, vh, bw, bh) {
    if (!(cw > 800)) return { W: 760, H: 560 };
    var W = Math.round(cw), H = Math.min(Math.round(W * 0.74), Math.max(560, (vh || 0) - 240));
    if (bw > 0 && bh > 0) H = Math.min(H, Math.max(320, Math.round(bh * Math.min(1.4, (W - 80) / bw)) + 80));
    return { W: W, H: H };
  }
  /* logic:end */
