  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    if (attrs) for (var a in attrs) {
      var v = attrs[a]; if (v === null || v === undefined || v === false) continue;
      if (a === "text") el.textContent = typeof v === "string" ? v.replace(/`/g, "") : v; else if (a === "on") el.addEventListener("click", v);
      else if (a === "tip") el.setAttribute("data-tip", v); else el.setAttribute(a, v);
    }
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined && c !== false) el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c); });
    return el;
  }
  var NS = "http://www.w3.org/2000/svg";
  function icon(d, cls) { var s = document.createElementNS(NS, "svg"); s.setAttribute("viewBox", "0 0 16 16"); s.setAttribute("class", cls || "ic"); s.setAttribute("aria-hidden", "true"); s.innerHTML = '<path d="' + d + '"/>'; return s; }
  var I = {
    eye: "M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8ZM8 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4", pause: "M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13M6.5 5.8v4.4M9.5 5.8v4.4",
    hand: "M5.5 8V3.8a1 1 0 0 1 2 0V7m0-.5V2.8a1 1 0 0 1 2 0V7m0-1.6a1 1 0 0 1 2 0V9a5 5 0 0 1-5 5h-.3a4 4 0 0 1-3.2-1.7L1.7 10a1 1 0 0 1 1.6-1.2l2.2 1.6",
    check: "M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13M5.3 8.2l1.8 1.8 3.6-3.8", out: "M6 3.5H3.5v9h9V10M9 2.5h4.5V7M13.5 2.5 7.5 8.5",
    copy: "M5.5 5.5h7v8h-7zM3.5 10.5v-8h7", find: "M7 2.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9M10.5 10.5 14 14", x: "M3.5 3.5l9 9M12.5 3.5l-9 9"
  };
  function ago(t, now) { var s = Math.max(0, now - t); if (s < 90) return s + " s"; if (s < 5400) return Math.round(s / 60) + " min"; if (s < 172800) return Math.round(s / 3600) + " h"; return Math.round(s / 86400) + " d"; }
  function span(s) { s = Math.max(0, s); if (s < 90) return s + " s"; if (s < 5400) return Math.round(s / 60) + " min"; if (s < 172800) return Math.floor(s / 3600) + " h " + ("0" + Math.floor(s % 3600 / 60)).slice(-2) + " min"; return Math.floor(s / 86400) + " d " + ("0" + Math.floor(s % 86400 / 3600)).slice(-2) + " h"; }
  function color(s) { return "var(--" + s.toLowerCase() + ")"; }
  function fnv(s) { var x = 2166136261; for (var i = 0; i < s.length; i++) { x ^= s.charCodeAt(i); x = Math.imul(x, 16777619) >>> 0; } return x >>> 0; }
  function lang() { return window.UAKWorkspace ? UAKWorkspace.language() : undefined; }

  function idcells(name, human) {
    var bits = fnv("p:" + (human || name)), on = [];
    for (var y = 0; y < 5; y++) for (var x = 0; x < 3; x++) if ((bits >> (y * 3 + x)) & 1) { on.push([x, y]); if (x !== 2) on.push([4 - x, y]); }
    return { on: on.length ? on : [[2, 2]], hue: Math.round((fnv("c:" + name) * 137.508) % 360) };
  }
  function identicon(name, human, size, isHuman) {
    var k = idcells(name, human), svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "-1 -1 7 7"); svg.setAttribute("width", size); svg.setAttribute("height", size);
    svg.setAttribute("class", "idc" + (isHuman ? " human" : "")); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", name);
    svg.setAttribute("data-tip", name); svg.style.setProperty("--h", k.hue);
    function px(x, y, cls) { var r = document.createElementNS(NS, "rect"); r.setAttribute("x", x); r.setAttribute("y", y); r.setAttribute("width", cls === "bg" ? 7 : 1.02); r.setAttribute("height", cls === "bg" ? 7 : 1.02); r.setAttribute("class", cls); svg.appendChild(r); }
    px(-1, -1, "bg"); k.on.forEach(function (c) { px(c[0], c[1], "px"); });
    return svg;
  }
  function favicon(repo) {
    var svg = identicon(repo, repo, 32, false), hue = svg.style.getPropertyValue("--h");
    svg.setAttribute("xmlns", NS); svg.removeAttribute("style"); svg.removeAttribute("data-tip");
    document.getElementById("favicon").href = "data:image/svg+xml," + encodeURIComponent(new XMLSerializer().serializeToString(svg));
  }
  var AG = {};
  function avatar(name, size) {
    size = size || 22;
    if (name === "scheduler" || name === "github") return h("span", { "class": "bot", style: "width:" + size + "px;height:" + size + "px", tip: name, text: size < 20 ? "" : name === "github" ? "gh" : "sch" });
    var a = AG[name];
    return identicon(name, a ? a.human : name.replace(/-[A-Za-z0-9]+$/, ""), size, a ? a.is_human : false);
  }
  function who(name, size) { return h("span", { "class": "who" }, [avatar(name, size || 18), h("span", { text: name })]); }
  function pres(s) { return h("span", { "class": "pres " + s, "aria-hidden": "true" }); }
  function tid(id) { return h("button", { "class": "tid", text: id, title: T("Conversation about ") + id, on: function (e) { e.stopPropagation(); openStory(id); } }); }
  function go(tab, extra) { ui.tab = tab; for (var k in (extra || {})) ui[k] = extra[k]; save(); render(); document.getElementById("view").scrollIntoView({ block: "start" }); }

  var AGM = {}, DG = depGraph([]), SEL = "", ARMED = "", HOVER = !!(window.matchMedia && matchMedia("(hover: hover)").matches);
  function models(d) {
    AGM = {};
    function note(a, m, hn) { var x = AGM[a] = AGM[a] || {}; if (m && m !== "unknown") x.model = m; if (hn && hn !== "unknown") x.harness = hn; }
    d.tasks.forEach(function (t) { (t.harnesses || []).forEach(function (x) { note(x.agent, x.model, x.harness); }); });
    Object.keys(d.timelines || {}).forEach(function (id) { d.timelines[id].agents.forEach(function (a) { note(a[0], a[1], a[2]); }); });
  }
  function mh(n) { var x = AGM[n] || {}; return x.model || x.harness ? [x.harness, x.model].filter(Boolean).join(" · ") : L('not recorded'); }
  var NEWER = false, lastGen = -1, D = null, STATES = {}, focusTab = false;
  // A task whose dependencies are not integrated waits; it is not available (UI-023). The setup server marks waiting_on; `uak dash` alone computes the same.
  function waitingOn(t) {
    if (Object.prototype.toString.call(t.waiting_on) === "[object Array]") return t.waiting_on;
    if (t.state !== "AVAILABLE") return [];
    var seen = {}, out = [];
    ((t.depends || "").replace(/\([^)]*\)/g, "").match(/[A-Z][A-Z0-9]*-\d+/g) || []).forEach(function (x) {
      if (x !== t.id && !seen[x] && STATES[x] !== "INTEGRATED") { seen[x] = 1; out.push(x); }
    });
    return out;
  }
  function stateOf(t) { return waitingOn(t).length ? "WAITING" : t.state; }
  function approved(t, d) {
    if (typeof t.approved === "boolean") return t.approved;
    if (t.state !== "REVIEW" || d.offers.some(function (o) { return o.task === t.id; })) return false;
    var last = d.reviews.filter(function (r) { return r.task === t.id; }).sort(function (a, b) { return (a.at || 0) - (b.at || 0); }).pop();
    return !!last && last.verdict === "approve";
  }
  // Only the human queue is a person's job (a merge waiting for the queue is not), and reasons carry no disk path.
  function humanQueue(d) { return openHumanQueue(d.queue, d.tasks); }
  function noPath(text) {
    return String(text || "").replace(/\s*\(log: [^)]*\)/g, "").replace(/(^|[\s"'=])(?:[A-Za-z]:[\\/]|\/)[^\s;,()]+/g, function (m, pre) {
      var parts = m.slice(pre.length).replace(/[\\/]+$/, "").split(/[\\/]/); return pre + (parts[parts.length - 1] || "…");
    });
  }
  function frozenNow(d) { return !!d.freeze && d.freeze <= Math.max(d.generated, Math.floor(Date.now() / 1000)); }
  function viewHeading(v, text) { v.appendChild(h("h2", { "class": "sr-only", id: "view-h", text: text })); }
  function match(t) { var q = ui.q.toLowerCase(); return !q || (t.id + " " + (t.title || "") + " " + (t.owner || "")).toLowerCase().indexOf(q) >= 0; }
  function find(onchange) {
    var q = h("input", { id: "q", type: "search", placeholder: L('Search a task or an agent'), value: ui.q, "aria-label": L('Search a task or an agent') }), timer = 0;
    q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(function () { ui.q = q.value; save(); onchange(); }, 120); });
    return h("label", { "class": "find" }, [icon(I.find), q]);
  }
