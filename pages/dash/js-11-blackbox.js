  function blackbox(v, d) {
    viewHeading(v, T("Black box"));
    var wrap = h("div", { "class": "wide bbw" }), g = h("div", { "class": "g2" }); v.appendChild(wrap); wrap.appendChild(g);
    var kinds = {}; d.blackbox.forEach(function (r) { var k = label(r); kinds[k] = (kinds[k] || 0) + 1; });
    g.appendChild(guard("panel", function () { return panel(T("Events by kind"), d.blackbox.length + T(" recorded"), Object.keys(kinds).length ? hbars(kinds) : none(T("No events yet"), L('Kit errors and agent notes land here.'))); }));
    var t2 = h("table", { "class": "tbl" }, [h("tr", {}, [T("Harness"), T("Claims"), T("Map / task"), T("Lens / task"), T("Wait / done"), T("Polls / done")].map(function (x, i) { return h("th", { "class": i ? "n" : null, text: x }); }))]);
    Object.keys(d.usage).forEach(function (hn) {
      var u = d.usage[hn], cl = u.claim || 0, dn = u.done || 0;
      function r(x, y) { return y ? (x / y).toFixed(1) : "–"; }
      t2.appendChild(h("tr", {}, [hn, String(cl), r(u.map || 0, cl), r(u.lens || 0, cl), r(u.wait || 0, dn), r((u.status || 0) + (u.inbox || 0) + (u.board || 0) + (u.digest || 0), dn)].map(function (x, i) { return h("td", { "class": i ? "n" : null, text: x }); })));
    });
    g.appendChild(guard("panel", function () { return panel(T("Harness adoption"), T("agent calls per claim and per done"), Object.keys(d.usage).length ? t2 : none(T("No usage recorded yet."))); }));
    var recs = d.blackbox.slice().reverse(), counts = {}, hs = {}; recs.forEach(function (r) { var k = label(r); counts[k] = (counts[k] || 0) + 1; hs[r.harness] = 1; });
    var list = bbFilter(recs, { k: ui.bk, h: ui.bh, p: ui.bp, q: ui.bq }, d.generated * 1000);
    var q = h("input", { type: "search", placeholder: L('Search the black box'), value: ui.bq, "aria-label": L('Search the black box') }), timer = 0;
    q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(function () { ui.bq = q.value; save(); render(); }, 150); });
    var hsel = listbox([["", T("Harness")]].concat(Object.keys(hs).sort().map(function (x) { return [x, x]; })), ui.bh, function (x) { ui.bh = x; save(); render(); }, T("Harness"));
    var f = h("div", { "class": "filters", role: "search" }, [h("label", { "class": "find" }, [icon(I.find), q]), hsel, seg([["", T("Auto")], ["d", "24 h"], ["w", "7 " + T("days")]], ui.bp, function (x) { ui.bp = x; save(); render(); }, L('Period'))]);
    if (ui.bk || ui.bh || ui.bp || ui.bq) f.appendChild(h("button", { "class": "clear", text: T("Clear filters"), on: function () { ui.bk = ui.bh = ui.bp = ui.bq = ""; save(); render(); } }));
    f.appendChild(h("span", { "class": "count", text: list.length + " / " + recs.length }));
    var kinds = h("div", { "class": "chips", style: "margin:0 0 16px" }, Object.keys(counts).sort(function (a, c) { return counts[c] - counts[a]; }).map(function (k) {
      return h("button", { "class": "chip", type: "button", "aria-pressed": String(ui.bk === k), style: ui.bk === k ? "background:var(--accent-wash)" : null, on: function () { ui.bk = ui.bk === k ? "" : k; save(); render(); } }, [k, h("b", { "class": "num", text: String(counts[k]) })]);
    }));
    var ul = h("ul", { "class": "list bbx" });
    capped(ul, "bb", list, function (r) {
      var k = label(r), err = /error|conflict|guard/.test(k), when = r.time.replace(/^\d{4}-/, "").replace("T", " ").replace(/:\d\dZ?$|Z$/, "");
      return h("li", {}, [h("details", {}, [h("summary", {}, [h("span", { "class": "mono num", text: when }), h("span", { "class": "tag" + (err ? " crit" : r.source === "agent" ? " info" : ""), text: k }), h("span", { "class": "t", text: (r.command !== "-" ? r.command + " " : "") + r.what })]),
        h("dl", { "class": "kv", style: "margin-top:8px" }, [["command", r.command], [T("Time"), r.time], [T("Harness"), r.harness + " · kit " + r.kit], [T("What happened"), r.what], [T("Fix"), r.fix]].reduce(function (a, x) { return x[1] && x[1] !== "-" ? a.concat([h("dt", { text: x[0] }), h("dd", { style: "margin:0;text-align:left;overflow-wrap:anywhere", text: x[1] })]) : a; }, []))])]);
    });
    var notes = guard("notes", function () { return panel(T("Agent notes and kit errors"), T("newest first"), !d.blackbox.length ? none(T("The black box is empty.")) : list.length ? h("div", {}, [ul]) : none(T("No messages match"), L('Try another kind or period, or clear the filters.'))); });
    wrap.insertBefore(f, g); wrap.insertBefore(kinds, g);
    notes.style.marginTop = "16px"; wrap.appendChild(notes);
  }
