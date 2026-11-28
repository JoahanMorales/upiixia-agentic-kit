  function render() {
    var d = window.UAK_DATA; if (!d || DRAG) return;   // a refresh waits for the drop: the box being dragged stays in the page
    D = d; lastGen = d.generated;
    AG = {}; d.agents.forEach(function (a) { AG[a.name] = a; }); models(d); DG = depGraph(d.tasks); SEL = "";
    var act = document.activeElement, caret = act && act.id === "q" ? act.selectionStart : -1, f = FOCUS || (act && act.getAttribute && act.getAttribute("data-f"));
    Object.keys(HEADING).forEach(function (key) { LABEL[key] = T(HEADING[key]); });
    STATES = {}; d.tasks.forEach(function (t) { STATES[t.id] = t.state; });
    header(d); tabs(d);
    var v = document.getElementById("view"); v.innerHTML = "";
    guard(ui.tab, function () { ({ sum: summary, board: board, agents: agents, talk: talk, bb: blackbox, memory: memory, tokens: tokens })[ui.tab](v, d); return v; });
    if (storyId) fillStory(true);
    reportSize();
    if (f) { var fe = document.querySelector('[data-f="' + f + '"]') || document.querySelector('[data-f="add:' + f.split(":")[0] + '"]'); if (fe && fe.disabled) fe = fe.parentNode.querySelector("button:not([disabled])"); if (fe) keepInView(fe, !!FOCUS); }
    FOCUS = ""; ANCHOR = null; if (ANN) { document.getElementById("arr-live").textContent = ANN; ANN = ""; }
    if (caret >= 0) { var q = document.getElementById("q"); if (q) { q.focus(); q.setSelectionRange(caret, caret); } }
  }
  function header(d) {
    var n = needs(d).length;
    document.title = (n ? "(" + n + ") " : "") + d.repo + " · uak dash";
    var logo = document.getElementById("logo"); logo.innerHTML = ""; logo.appendChild(identicon(d.repo, d.repo, 28, false));
    favicon(d.repo);
    document.getElementById("embedded-title").textContent = d.repo + " · " + T("Project dashboard");
    document.getElementById("repo").textContent = d.repo;
    var sb = document.getElementById("share-btn"); sb.innerHTML = ""; sb.appendChild(icon("M8 10V2M5 5l3-3 3 3M3 9v4h10V9")); sb.appendChild(h("span", { "class": "sbt", text: L('Share') })); sb.setAttribute("aria-label", L('Share')); sb.onclick = openShare;
    document.getElementById("pal-label").textContent = L('Palette');
    var mc = document.getElementById("modechip"); mc.hidden = !d.mode; mc.textContent = d.mode || "";
    var fz = document.getElementById("freeze");
    if (d.freeze) { fz.hidden = false; fz.textContent = !frozenNow(d) ? T("Freeze in ") + ago(d.generated, d.freeze) : T("Frozen"); } else fz.hidden = true;
    fresh();
  }
  // Freshness uses the real clock: a page whose data stopped moving says so instead of looking live.
  function fresh() {
    if (!D) return;
    var age = Math.max(0, Math.round(Date.now() / 1000 - D.generated)), stale = D.stale || age > Math.max(90, 3 * (D.refresh || 20));
    var p = document.getElementById("fresh"); p.className = "fresh" + (stale ? " stale" : "");
    if (D.stale && D.claims_at) document.getElementById("freshtxt").textContent = T("Last known state · ") + ago(D.claims_at, D.generated + age) + T(" ago");
    else document.getElementById("freshtxt").textContent = (stale ? T("Snapshot · ") : T("Live · ")) + ago(D.generated, D.generated + age) + T(" ago");
    p.title = stale ? T("data.js is not being refreshed: run uak dash --watch") : T("Refreshes every ") + D.refresh + " s";
    if (NEWER) { p.className = "fresh stale"; document.getElementById("freshtxt").textContent = L('A newer page exists: reload this tab'); }
  }
  function tabs(d) {
    var counts = { sum: needs(d).length, board: null, agents: null, talk: null, bb: null, memory: null, tokens: null };
    var t = document.getElementById("tabs"); t.innerHTML = "";
    TABS.forEach(function (x) {
      var on = ui.tab === x[0], n = counts[x[0]];
      t.appendChild(h("button", { "class": on ? "on" : "", role: "tab", id: "tab-" + x[0], "aria-selected": on ? "true" : "false", "aria-controls": "view", tabindex: on ? "0" : "-1", on: function () { ui.tab = x[0]; save(); render(); } },
        [icon(x[2]), T(x[1]), n ? h("span", { "class": "cnt", text: String(n), title: L('Things that need you') }) : null]));
    });
    document.getElementById("view").setAttribute("aria-labelledby", "tab-" + ui.tab);
    if (focusTab) { focusTab = false; var cur = document.getElementById("tab-" + ui.tab); if (cur) cur.focus(); }
  }
  document.getElementById("tabs").addEventListener("keydown", function (e) {
    var keys = TABS.map(function (x) { return x[0]; }), i = keys.indexOf(ui.tab), next = -1;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (i + 1) % keys.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (i - 1 + keys.length) % keys.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = keys.length - 1;
    if (next < 0) return;
    e.preventDefault(); ui.tab = keys[next]; focusTab = true; save(); render();
  });

