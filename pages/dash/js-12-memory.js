  function memory(v, d) {
    viewHeading(v, T("Memory"));
    var wrap = h("div", { "class": "wide" }), g = h("div", { "class": "g2 mem" }); v.appendChild(wrap);
    var wide = window.innerWidth >= 640, graph = ui.mv === "graph" && wide;
    wrap.appendChild(h("div", { "class": "filters" }, [seg([["list", L('List')], ["graph", L('Graph')]], ui.mv, function (x) { ui.mv = x; save(); render(); }, L('Show the memory as')), ui.mv === "graph" && !wide ? h("span", { "class": "muted", text: L('The graph needs a wider screen: showing the list.') }) : null]));
    if (graph) { memGraphView(wrap, d); return; }
    wrap.appendChild(g);
    var l = h("ul", { "class": "list" });
    capped(l, "les", d.lessons.slice().reverse(), function (x) { return (h("li", { "class": "row", style: "grid-template-columns:24px minmax(0,1fr)" }, [avatar(x.agent, 24), h("div", { style: "min-width:0" }, [h("div", {}, [rich(x.text)]), h("div", { "class": "sub" }, [x.agent, x.task !== "-" ? " · " : "", x.task !== "-" ? tid(x.task) : null, x.paths ? " · " + x.paths : ""])])])); });
    g.appendChild(guard("panel", function () { return panel(T("Lessons"), "uak learn", d.lessons.length ? l : none(T("No lessons yet"), L('What an agent learns the hard way shows up here.'))); }));
    var dc = h("ul", { "class": "list" });
    capped(dc, "dec", d.decisions.slice().reverse(), function (x) { return (h("li", { "class": "row", style: "grid-template-columns:24px minmax(0,1fr)" }, [avatar(x.who || "?", 24), h("div", { style: "min-width:0" }, [h("div", {}, [rich(x.text)]), h("div", { "class": "sub" }, [h("span", { "class": "tag", text: x.kind }), " " + x.who + " · " + ago(x.t, d.generated) + T(" ago")])])])); });
    g.appendChild(guard("panel", function () { return panel(T("Decisions"), "DECISIONS.md", d.decisions.length ? dc : none(T("No decisions yet"), L('Agreed contracts and calls land here.'))); }));
  }
  var SEL_NODE = "", GZ = { z: 1, x: 0, y: 0 }, GHIDE = { file: true, agent: true }, GQ = "";
  // Memory as a graph: entries and the tasks they cite by default (files and agents are one chip away), real references only.
  function memGraphView(wrap, d) {
    var W = 760, H = 560, SV = "http://www.w3.org/2000/svg", mg = memGraph(d.lessons, d.decisions);
    if (mg.nodes.length < 4) { wrap.appendChild(h("div", { "class": "card empty" }, [h("b", { text: L('Too few links for a graph') }), mg.entries.length + " " + L('entries, of which') + " " + mg.linked + " " + L('share a task, a file or an agent with another one.')])); return; }
    var by = {}, ent = {}, near = {}, kinds = { entry: 0, task: 0, file: 0, agent: 0 };
    mg.nodes.forEach(function (x) { by[x.id] = x; }); mg.entries.forEach(function (e) { ent[e.id] = e; });
    function kindOfNode(x) { return x.type === "lesson" || x.type === "decision" ? "entry" : x.type; }
    mg.nodes.forEach(function (x) { kinds[kindOfNode(x)]++; });
    var vis = {}; mg.nodes.forEach(function (x) { if (!GHIDE[kindOfNode(x)]) vis[x.id] = 1; });
    var edges = mg.edges.filter(function (e) { return vis[e[0]] && vis[e[1]]; }), linked = {}; edges.forEach(function (e) { linked[e[0]] = linked[e[1]] = 1; });
    var shown = mg.nodes.filter(function (x) { return vis[x.id] && linked[x.id]; }); vis = linked;
    var lay = clusterLayout(shown, edges), pos = lay.pos;
    var sel = SEL_NODE && by[SEL_NODE] ? SEL_NODE : "", ql = GQ.toLowerCase();
    mg.edges.forEach(function (e) { if (e[0] === sel) near[e[1]] = 1; if (e[1] === sel) near[e[0]] = 1; });
    function text(x) { return ent[x.id] ? ent[x.id].text : x.label; }
    function hit(x) { return !ql || (x.label + " " + text(x)).toLowerCase().indexOf(ql) >= 0; }
    // A short human title: the kind and the first meaningful words, cut at a word; the full text is in the side panel.
    function lab(x) {
      if (!ent[x.id]) return x.label.length > 24 ? "…" + x.label.slice(-23) : x.label;
      var t = ent[x.id].text.replace(/\s+/g, " ").replace(/^(tasks added|test change allowed by [^:]*|test change|amended|why|[A-Z][A-Z0-9]*-\d+)\s*[:|]?\s*/i, "").replace(/\|\s*Why:\s*/i, " · ").replace(/\b[A-Z][A-Z0-9]*-\d+\b/g, "").replace(/\s+/g, " ").trim();
      var cut = t.length > 26 ? t.slice(0, 26).replace(/\s+\S*$/, "") + "…" : t;
      return (x.type === "lesson" ? L('Lesson') : L('Decision')) + ": " + (cut || ent[x.id].kind || "");
    }
    var tools = h("div", { "class": "filters" }, [["entry", L('Entries')], ["task", T("Tasks")], ["file", L('File')], ["agent", T("Agents")]].map(function (k) { return h("button", { "class": "chip", type: "button", "aria-pressed": String(!GHIDE[k[0]]), style: GHIDE[k[0]] ? null : "background:var(--accent-wash)", on: function () { GHIDE[k[0]] = !GHIDE[k[0]]; render(); } }, [k[1], h("b", { "class": "num", text: String(kinds[k[0]]) })]); }));
    var q = h("input", { type: "search", placeholder: L('Search the memory'), value: GQ, "aria-label": L('Search the memory') }), qt = 0;
    q.addEventListener("input", function () { clearTimeout(qt); qt = setTimeout(function () { GQ = q.value; render(); }, 150); });
    tools.appendChild(h("label", { "class": "find" }, [icon(I.find), q]));
    [["+", 1.4], ["-", 1 / 1.4]].forEach(function (z) { tools.appendChild(h("button", { "class": "chip", type: "button", "aria-label": z[0] === "+" ? L('Zoom in') : L('Zoom out'), text: z[0], on: function () { GZ.z = Math.max(1, Math.min(6, GZ.z * z[1])); render(); } })); });
    tools.appendChild(h("button", { "class": "chip", type: "button", text: L('Fit'), on: function () { GZ = { z: 1, x: 0, y: 0 }; render(); } }));
    // The canvas: the width the graph's card has here (graphBox), measured on an empty copy of the two columns.
    var probe = wrap.appendChild(h("div", { "class": "gv" }, [h("div", { "class": "card" }), h("div", { "class": "card pad gside" })])), gb = graphBox(probe.firstChild.clientWidth, window.innerHeight / Z, lay.box.w, lay.box.h);
    probe.remove(); W = gb.W; H = gb.H;
    // Scale to fit, with a padding, over the unbounded layout: nothing is clamped to the frame.
    var pad = 40, sc = Math.min(1.4, (W - 2 * pad) / lay.box.w, (H - 2 * pad) / lay.box.h), fw = W / sc, fh = H / sc, fx = lay.box.x - (fw - lay.box.w) / 2, fy = lay.box.y - (fh - lay.box.h) / 2;
    var vw = fw / GZ.z, vh = fh / GZ.z, vx = Math.max(fx, Math.min(fx + fw - vw, GZ.x || fx)), vy = Math.max(fy, Math.min(fy + fh - vh, GZ.y || fy));
    if (GZ.z === 1) { vx = fx; vy = fy; }
    var u = 1 / (sc * GZ.z);   // user units per pixel
    var svg = document.createElementNS(SV, "svg"); svg.setAttribute("viewBox", vx + " " + vy + " " + vw + " " + vh); svg.setAttribute("class", "mg"); svg.setAttribute("role", "group"); svg.setAttribute("aria-label", L('Memory graph'));
    function el(tag, at, parent) { var e = document.createElementNS(SV, tag); for (var k in at) e.setAttribute(k, at[k]); (parent || svg).appendChild(e); return e; }
    edges.forEach(function (e) { var a = pos[e[0]], b = pos[e[1]], on = sel && (e[0] === sel || e[1] === sel); el("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y, "class": "ge" + (on ? " on" : sel ? " dim" : ""), "stroke-width": (on ? 2 : 1) * u }); });
    var labelItems = shown.filter(function (x) { return x.type === "task" || x.id === sel || near[x.id] || (ql && hit(x)); }).sort(function (a, b) { return (b.id === sel ? 2 : near[b.id] ? 1 : 0) - (a.id === sel ? 2 : near[a.id] ? 1 : 0); }).map(function (x) { var t = lab(x); return { id: x.id, x: pos[x.id].x, y: pos[x.id].y, r: nodeR(x) * Math.max(1, u * .9), w: t.length * 6.8 * u, h: 13 * u, below: x.type === "task", must: x.id === sel || !!near[x.id] }; });
    var labelAt = fitLabels(labelItems, { x: vx, y: vy, w: vw, h: vh });
    shown.forEach(function (x) {
      var p = pos[x.id], r = nodeR(x) * Math.max(1, u * .9), on = sel === x.id, dim = (sel && !on && !near[x.id]) || (ql && !hit(x));
      var g = el("g", { "class": "gn n-" + x.type + (on ? " sel" : "") + (dim ? " dim" : "") + (ql && hit(x) ? " hit" : ""), tabindex: "0", role: "button", "aria-label": x.type + " " + lab(x) + ", " + x.deg + " " + L('links') });
      if (x.type === "task") el("rect", { x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r, rx: r * .25 }, g);
      else if (x.type === "file") el("rect", { x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r, transform: "rotate(45 " + p.x + " " + p.y + ")" }, g);
      else el("circle", { cx: p.x, cy: p.y, r: r, "stroke-width": 2 * u }, g);
      // labels: every task by its id; an entry only when selected, next to the selection, or found by the search
      var pl = labelAt[x.id];
      if (pl) { var tx = el("text", { x: pl.x, y: pl.y, "text-anchor": pl.anchor, "font-size": 11 * u }, g); tx.textContent = lab(x); }
      var t2 = el("title", {}, g); t2.textContent = x.type + " · " + lab(x);
      function choose() { SEL_NODE = SEL_NODE === x.id ? "" : x.id; render(); }
      g.addEventListener("click", choose); g.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(); } });
    });
    var drag = null;
    svg.addEventListener("pointerdown", function (e) { if (GZ.z > 1 && e.target === svg) drag = { x: e.clientX, y: e.clientY, gx: vx, gy: vy }; });
    svg.addEventListener("pointermove", function (e) { if (!drag) return; var k = vw / svg.getBoundingClientRect().width; GZ.x = drag.gx - (e.clientX - drag.x) * k; GZ.y = drag.gy - (e.clientY - drag.y) * k; svg.setAttribute("viewBox", Math.max(fx, Math.min(fx + fw - vw, GZ.x)) + " " + Math.max(fy, Math.min(fy + fh - vh, GZ.y)) + " " + vw + " " + vh); });
    svg.addEventListener("pointerup", function () { drag = null; });
    var leg = h("div", { "class": "legend" }, [["task", T("Tasks")], ["lesson", L('Lesson')], ["decision", L('Decision')], ["file", L('File')], ["agent", T("Agents")]].filter(function (x) { return shown.some(function (n) { return n.type === x[0]; }); }).map(function (x) { return h("span", {}, [h("i", { "class": "sw g-" + x[0], "aria-hidden": "true" }), x[1]]); }));
    var side = h("div", { "class": "card pad gside" }), orphans = mg.entries.filter(function (e) { return !vis[e.id]; });
    function chip(id, t) { return h("button", { "class": "chip", type: "button", text: t, title: t, on: function () { SEL_NODE = id; render(); } }); }
    if (!sel) {
      var top = mg.nodes.filter(function (x) { return x.type === "task"; }).sort(function (a, b) { return b.deg - a.deg; }).slice(0, 5);
      side.appendChild(h("div", { "class": "bh" }, [h("h2", { text: shown.length + " " + L('nodes') + " · " + edges.length + " " + L('links') })]));
      side.appendChild(h("div", { "class": "gh", text: L('Tasks with the most entries') }));
      side.appendChild(h("div", { "class": "chips", style: "margin-bottom:12px" }, top.map(function (x) { return h("button", { "class": "chip", type: "button", on: function () { SEL_NODE = x.id; render(); } }, [x.label, h("b", { "class": "num", text: String(x.deg) })]); })));
      if (orphans.length) {
        var groups = groupOrphans(orphans.map(function (e) { return { t: lab({ id: e.id, type: e.kind }), full: e.text.replace(/\s+/g, " ") }; }));
        side.appendChild(h("div", { "class": "gh", text: orphans.length + " " + L('entries with no link shown') + " · " + groups.length }));
        side.appendChild(h("div", { "class": "chips" }, groups.slice(0, ui.more.orph ? groups.length : 12).map(function (g) { return h("button", { "class": "chip ell", type: "button", style: "max-width:100%", text: g.t + (g.n > 1 ? " ×" + g.n : ""), title: g.full, on: function () { SEL_NODE = ""; GQ = g.full.slice(0, 20); render(); } }); }).concat(groups.length > 12 ? [h("button", { "class": "chip", type: "button", text: ui.more.orph ? T("Show less") : "+" + (groups.length - 12) + " " + L('more'), on: function () { ui.more.orph = !ui.more.orph; render(); } })] : [])));
      }
    } else {
      var x = by[sel], es = ent[sel] ? [ent[sel]] : mg.entries.filter(function (e) { return e.refs[sel]; });
      side.appendChild(h("div", { "class": "bh" }, [h("h2", { text: x.type + " · " + lab(x) }), h("span", { "class": "n", text: x.deg + " " + L('links') }), h("button", { "class": "chip", style: "margin-left:auto", type: "button", text: L('Clear'), on: function () { SEL_NODE = ""; render(); } })]));
      es.slice(0, 6).forEach(function (e) { side.appendChild(h("div", { style: "padding:8px 0;border-top:1px solid var(--line)" }, [h("div", { "class": "sub muted", text: e.kind + " · " + (e.who || "") + (e.t ? " · " + ago(e.t, d.generated) + T(" ago") : "") }), h("div", {}, [rich(e.text)]), ent[sel] ? null : chip(e.id, lab(by[e.id] || { id: e.id, type: e.kind, label: e.id }))])); });
      if (es.length > 6) side.appendChild(h("div", { "class": "muted", text: "+" + (es.length - 6) + " " + L('more') }));
      var nb = mg.edges.filter(function (e) { return e[0] === sel || e[1] === sel; }).map(function (e) { return e[0] === sel ? e[1] : e[0]; });
      if (ent[sel] && nb.length) { side.appendChild(h("div", { "class": "gh", text: L('Links') })); side.appendChild(h("div", { "class": "chips" }, nb.map(function (id) { return chip(id, lab(by[id])); }))); }
    }
    wrap.appendChild(tools);
    wrap.appendChild(h("div", { "class": "gv" }, [h("div", { "class": "card" }, [svg, leg]), side]));
  }
