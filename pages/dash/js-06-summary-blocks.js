  // What needs the person, most urgent first: the title count, the rail's badge and the first block all read this one list.
  function needs(d) {
    var out = [], g = d.generated;
    if (d.stale) out.push({ k: "warn", i: I.pause, t: [T("The remote did not answer: this is the last state this computer read.")], at: d.claims_at || 0 });
    if (frozenNow(d)) out.push({ k: "crit", i: I.hand, t: [T("Project changes are frozen. A human must authorize any new work.")] });
    humanQueue(d).forEach(function (q) { out.push({ k: "warn", i: I.hand, id: q.task, t: [tid(q.task), T(" needs a human")], text: noPath(q.reason), at: q.at }); });
    d.offers.map(function (o) { return { task: o.task, to: o.to, owner: o.owner, since: reviewSince(o, d.tasks) }; }).sort(function (a, b) { return a.since - b.since; }).forEach(function (o) {
      var to = (o.to || []).map(function (x) { x = x.replace(/^(agent|task):/, ""); return x === "all" ? T("all") : x; }).join(", "), late = g - o.since > 3600;
      out.push({ k: late ? "crit" : "info", i: I.eye, id: o.task, t: [tid(o.task), T(" waits for review")], text: T("owner ") + o.owner + T(" · offered to ") + (to || T("all")), at: o.since });
    });
    d.tasks.filter(function (t) { return stalledMin(t, g); }).forEach(function (t) {
      out.push({ k: "crit", i: I.pause, id: t.id, t: [tid(t.id), T(" has not moved in ") + stalledMin(t, g) + " min"], text: t.progress ? T(t.progress) : t.title, at: t.away ? -1 : 0 });
    });
    return out;
  }
  function copyBox(text) {
    var b = h("button", { type: "button", "aria-label": T("Copy") + " " + text, title: T("Copy"), on: function () {
      try { navigator.clipboard.writeText(text).then(function () { b.title = T("Copied"); }); } catch (e) { var r = document.createRange(); r.selectNodeContents(code); var s = getSelection(); s.removeAllRanges(); s.addRange(r); }
    } }, [icon(I.copy)]), code = h("code", { text: text, "data-no-i18n": "" });
    return h("div", { "class": "cmd" }, [code, b]);
  }
  // A block of the summary is one entry of BLOCKS: a name, a title, a column, a maximum of rows and one render over the data.
  function frame(b, n, extra, body) {
    return h("section", { "class": "blk b-" + b.name, "aria-labelledby": "h-" + b.name }, [h("div", { "class": "bh" }, [h("h2", { id: "h-" + b.name, text: b.title() }), n ? h("span", { "class": "n", text: n }) : null, extra ? h("div", { "class": "x" }, extra) : null]), body]);
  }
  function figure(cls, n, label, det, title) { return h("div", { "class": cls, title: title || null }, [h("b", { text: String(n) }), label, h("small", { text: det })]); }
  function needsBlock(d, max, b) {
    var list = needs(d), g = d.generated, p = d.progress, finished = p.total > 0 && p.done === 100;
    var online = d.agents.filter(function (a) { return a.status === "online" && !a.is_human; });
    var rw = d.tasks.filter(function (t) { return t.state === "REVIEW" && t.sub && (t.sub.kind === "waiting" || t.sub.kind === "rereview"); });
    var oldest = rw.reduce(function (m, t) { return Math.min(m, t.sub.since); }, Infinity);
    var stalled = d.tasks.filter(function (t) { return stalledMin(t, g); }), human = humanQueue(d);
    var ul = h("ul", { "class": "list need" });
    list.slice(0, max).forEach(function (n) {
      ul.appendChild(h("li", { "class": n.k === "crit" ? "hot" : "" }, [h("span", { "class": "ico" }, [icon(n.i)]),
        h("div", {}, [h("b", {}, n.t), n.text ? h("p", { text: n.text }) : null]),
        n.id ? h("div", { "class": "act" }, [copyBox("uak status --task " + n.id), n.at > 0 ? h("div", { "class": "when num", text: ago(n.at, g) }) : null]) : n.at > 0 ? h("span", { "class": "when num", text: ago(n.at, g) }) : null]));
    });
    if (list.length > max) ul.appendChild(h("li", { "class": "mre muted", style: "padding:8px 12px", text: "+" + (list.length - max) + " " + L('more') }));
    if (!list.length) ul.appendChild(h("li", { "class": "allclear" }, [h("span", { "class": "ico" }, [icon(I.check)]), h("div", {}, [finished ? [h("b", { text: L('Everything is integrated') }), h("p", { text: p.total + T(" tasks") + ". " + L('To add work, write a plan file and run') })] : h("p", { text: T("Nothing needs you right now: no review waiting, nothing stalled, nothing for a human.") })].reduce(function (a, x) { return a.concat(x); }, [])), finished ? copyBox("bash .uak/bin/uak plan FILE") : null]));
    var foot = h("div", { "class": "win-f f4" }, [
      figure("", online.length, T("Agents online"), online.length ? online.slice(0, 2).map(function (a) { return a.name; }).join(", ") + (online.length > 2 ? " +" + (online.length - 2) : "") : T("none in the last 30 min"), L('online = seen in the last 30 min')),
      figure(rw.length && g - oldest > 3600 ? "warm" : "", rw.length, T("Reviews waiting"), rw.length ? T("oldest ") + ago(oldest, g) : T("none waiting")),
      figure(stalled.length ? "hot" : "", stalled.length, T("Stalled"), stalled.length ? stalled.map(function (t) { return t.id; }).join(", ") : T("every task is moving")),
      figure(human.length ? "warm" : "", human.length, T("Needs a human"), human.length ? human.map(function (q) { return q.task; }).join(", ") : T("nothing for you"))]);
    return frame(b, list.length ? list.length + " " + (list.length === 1 ? L('thing, the most urgent first') : L('things, the most urgent first')) : "", null, h("div", { "class": "win" }, [ul, foot]));
  }

  var STAGE = { AVAILABLE: 0, WAITING: 0, CLAIMED: 1, BLOCKED: 1, REVIEW: 2, INTEGRATED: 3 }, PILL = { CLAIMED: "p-prog", REVIEW: "p-rev", INTEGRATED: "p-int", BLOCKED: "p-blk" };
  function pipe(s) {
    var at = STAGE[s], ol = h("ol", { "class": "nodes pipe" + (s === "INTEGRATED" ? " int" : s === "BLOCKED" ? " blk" : ""), role: "img", "aria-label": rowLabel(s) });
    for (var i = 0; i < 4; i++) ol.appendChild(h("li", { "class": i <= at ? "on" : "", "aria-current": i === at && s !== "INTEGRATED" ? "step" : null }, [h("i")]));
    return ol;
  }
  // A task is late when it stalled, its review is over the lease, or a claim passed its lease.
  function late(t) { return !!(stalledMin(t, D.generated) || (t.sub && t.sub.late) || (t.state === "CLAIMED" && t.lease && t.lease < D.generated)); }
  function when(t, s) {
    var g = D.generated, sub = t.sub;
    if (s === "REVIEW" && sub) return trSub(sub.text) + " · " + span(g - sub.since);
    if (s === "AVAILABLE") return t.depends && t.depends !== "None" ? T("after ") + t.depends : T("free to claim");
    if (s === "WAITING") { var w = waitingOn(t); return T("waits on ") + w.slice(0, 2).join(", ") + (w.length > 2 ? " " + L('and') + " " + (w.length - 2) + " " + L('more') : ""); }
    if (t.stalled) return (t.owner || "") + " · " + T("stalled ") + t.stalled + " min";
    return (t.owner || "") + " · " + ago(t.progress_changed || t.updated || g, g);
  }
  function storyable(el, id) {
    el.setAttribute("data-story", id); el.setAttribute("tabindex", "0"); el.setAttribute("aria-haspopup", "dialog");
    el.addEventListener("click", function (e) { if (e.target.closest && e.target.closest("a, button, summary, details")) return; openStory(id); });
    el.addEventListener("keydown", function (e) { if (e.target === el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openStory(id); } });
    return el;
  }
  function taskRow(t) {
    var s = stateOf(t);
    return storyable(h("li", { "class": late(t) ? "late" : "" }, [h("span", { "class": "pill " + (PILL[s] || ""), text: s === "WAITING" ? T("Waiting") : rowLabel(s) }), tid(t.id), h("span", { "class": "t", text: t.title || t.paths, title: t.title }), pipe(s), h("span", { "class": "w", text: when(t, s).replace(/ (min|h|d|s)\b/g, "\u00a0$1"), title: when(t, s) })]), t.id);
  }
  function moving(d) {
    var rank = { BLOCKED: 0, REVIEW: 1, CLAIMED: 2 };
    var m = d.tasks.filter(function (t) { return rank[t.state] !== undefined && match(t); });
    m.sort(function (a, b) { return rank[a.state] - rank[b.state] || (late(b) ? 1 : 0) - (late(a) ? 1 : 0) || (a.id < b.id ? -1 : 1); });
    return m;
  }
  function tasksBlock(d, max, b) {
    var live = moving(d), all = d.tasks.filter(function (t) { return t.state !== "CANCELLED"; }), shown = live, todo = false;
    if (!live.length && !ui.q) { shown = all.filter(function (t) { return t.state === "AVAILABLE"; }); todo = shown.length > 0; if (!todo) shown = all.filter(function (t) { return t.state === "INTEGRATED"; }).sort(function (a, c) { return (c.updated || 0) - (a.updated || 0); }); }
    var x = [find(render), seg([["list", L('List')], ["cols", L('Columns')]], ui.view, function (v) { ui.view = v; save(); render(); }, L('Show the tasks as'))], body;
    if (ui.view === "cols") {
      var cols = [["AVAILABLE", T("Available")], ["CLAIMED", T("In progress")], ["REVIEW", T("In review")], ["INTEGRATED", T("Integrated")]], g = d.generated;
      body = h("div", { "class": "card mini" }, cols.map(function (c) {
        var l = all.filter(function (t) { return (c[0] === "AVAILABLE" ? (t.state === "AVAILABLE") : c[0] === "CLAIMED" ? (t.state === "CLAIMED" || t.state === "BLOCKED") : t.state === c[0]) && match(t); });
        if (c[0] === "INTEGRATED") l.sort(function (a, b) { return (b.updated || 0) - (a.updated || 0); });
        var col = h("div", {}, [h("h3", {}, [h("span", { text: c[1] }), h("span", { "class": "n mono muted", text: String(l.length) })])]);
        l.slice(0, 3).forEach(function (t) { col.appendChild(storyable(h("div", { "class": "it" }, [h("span", {}, [tid(t.id), t.state === "BLOCKED" ? h("span", { "class": "tag crit", text: rowLabel("BLOCKED") }) : null]), h("p", { text: t.title || t.paths }), h("span", { "class": "muted", text: c[0] === "INTEGRATED" ? ago(t.updated || g, g) + T(" ago") : when(t, t.state) })]), t.id)); });
        if (l.length > 3) col.appendChild(h("button", { "class": "more", text: "+" + (l.length - 3) + " " + L('more'), on: function () { go("board"); } }));
        return col;
      }));
    } else {
      var ul = h("ul", { "class": "list rows" });
      shown.slice(0, max).forEach(function (t) { ul.appendChild(taskRow(t)); });
      if (!shown.length) ul.appendChild(h("li", { "class": "empty mre" }, [h("b", { text: ui.q ? T("No messages match") : T("Nobody is on a task") }), ui.q ? L('Try another agent or task, or clear the search.') : L('Nothing is claimed yet.')]));
      if (shown.length > max) ul.appendChild(h("li", { "class": "mre" }, [h("button", { "class": "more", text: "+" + (shown.length - max) + " " + L('more in the board'), on: function () { go("board"); } })]));
      body = ul;
    }
    return frame(b, all.length + T(" tasks") + (planCounts(d.tasks).cancelled ? " · " + planCounts(d.tasks).cancelled + " " + L('cancelled') : ""), x, h("div", {}, [todo ? h("p", { "class": "muted", style: "margin:0 0 8px", text: L('Nothing is moving: the next tasks to claim.') }) : null, body]));
  }

  // Who did what: lanes from the stories the page already carries (claim to done is a build, done to a verdict is a review).
  function lanesBlock(d, max, b) {
    var g = d.generated, segs = [], lastBy = {}, tls = d.timelines || {};
    Object.keys(tls).forEach(function (id) {
      var open = null, rv = null, by = null, t = d.tasks.filter(function (x) { return x.id === id; })[0];
      tls[id].lines.forEach(function (l) {
        if (l[1] === "claim") { open = { a: l[2], s: l[0] }; by = l[2]; }
        else if (l[1] === "done" && open) { segs.push({ id: id, a: open.a, s: open.s, e: l[0], k: "build" }); open = null; rv = l[0]; }
        else if ((l[1] === "approve" || l[1] === "reject") && rv) { segs.push({ id: id, a: l[2], s: rv, e: l[0], k: "rev" }); rv = null; }
        else if (l[1] === "integrate" && by) segs.push({ id: id, a: by, s: l[0], e: l[0], k: "int" });
      });
      if (open) segs.push({ id: id, a: open.a, s: open.s, e: g, k: "build" });
      if (rv) segs.push({ id: id, a: (t && t.owner) || by || "?", s: rv, e: g, k: "rev", late: !!(t && t.sub && t.sub.late) });
    });
    var wins = [6, 24, 72, 336], W = 0;
    for (var i = 0; i < wins.length && !W; i++) if (segs.some(function (s) { return s.e >= g - wins[i] * 3600; })) W = wins[i];
    var body, x = null;
    if (!W) {
      var lastMove = 0, lastTask = ""; Object.keys(tls).forEach(function (id) { tls[id].lines.forEach(function (l) { if (l[0] > lastMove) { lastMove = l[0]; lastTask = id; } }); });
      body = h("div", { "class": "card empty" }, [h("b", { text: lastMove ? L('Nothing moved in the last 14 days') : L('No work recorded yet') }), lastMove ? L('The last move was') + " " + ago(lastMove, g) + T(" ago") + " (" + lastTask + ")." : L('The moves of each task appear here once an agent claims it.')]);
    }
    else {
      var from = g - W * 3600, lanes = {};
      segs.forEach(function (s) { if (s.e >= from) (lanes[s.a] = lanes[s.a] || []).push(s); });
      var names = Object.keys(lanes).sort(function (a, c) { return Math.max.apply(null, lanes[c].map(function (s) { return s.e; })) - Math.max.apply(null, lanes[a].map(function (s) { return s.e; })); });
      var box = h("div", { "class": "lanes" });
      names.slice(0, max).forEach(function (n) {
        var tr = h("div", { "class": "track" }, [25, 50, 75].map(function (x) { return h("i", { "class": "tick", style: "left:" + x + "%" }); }));
        lanes[n].forEach(function (s) {
          var l = Math.max(0, (s.s - from) / (W * 3600)) * 100, w = (Math.min(g, s.e) - Math.max(from, s.s)) / (W * 3600) * 100;
          tr.appendChild(h("span", { "class": "seg-b " + s.k + (s.late ? " late" : ""), style: "left:" + (s.k === "int" ? Math.min(98, l) : l) + "%;width:" + Math.max(w, 0.8) + "%", tip: s.a + " (" + mh(s.a) + ") · " + s.id + " · " + (s.k === "int" ? T("Integrated") : s.k === "rev" ? T("In review") : T("In progress")) + (s.k === "int" ? "" : " · " + span(s.e - s.s)), text: s.k === "int" ? "" : w > 12 ? s.id.replace(/^[A-Z]+-/, "") : "" }));
        });
        box.appendChild(h("div", { "class": "lane" }, [h("b", { text: n, title: n }), tr]));
      });
      var wl = function (f) { return "-" + (W >= 48 ? Math.round(W * f / 24 * 10) / 10 + " d" : Math.round(W * f * 10) / 10 + " h"); };
      box.appendChild(h("div", { "class": "laxis num" }, [h("span", { text: wl(1) }), h("span", { text: wl(.5) }), h("span", { text: T("now") })]));
      body = h("div", { "class": "card" }, [box, h("div", { "class": "legend" }, [["--accent-line", L('Builds')], ["--claimed", T("In review")], ["--integrated", T("Integrated")], ["--blocked", L('Without a reviewer, over the lease')]].map(function (c) { return h("span", {}, [h("i", { "class": "sw", style: "--c:var(" + c[0] + ")" }), c[1]]); }))]);
      x = [W >= 48 ? L('last') + " " + Math.round(W / 24) + " d" : L('last') + " " + W + " h"];
      if (names.length > max) x.push(h("button", { "class": "chip", text: "+" + (names.length - max) + " " + T("Agents"), on: function () { go("agents"); } }));
    }
    return frame(b, "", x, body);
  }

  function progressBlock(d, max, b) {
    var p = d.progress, st = {}, waiting = d.tasks.filter(function (t) { return waitingOn(t).length; }).length;
    for (var k in p.states) st[k] = p.states[k];
    st.AVAILABLE = Math.max(0, (st.AVAILABLE || 0) - waiting); st.WAITING = waiting;
    var total = BAR.reduce(function (a, s) { return a + (st[s] || 0); }, 0), vis = BAR.filter(function (s) { return st[s]; }), viz;
    if (total <= 24) { viz = h("div", { "class": "blocks", role: "img", "aria-label": BAR.map(function (s) { return LABEL[s] + " " + (st[s] || 0); }).join(", ") }); BAR.forEach(function (s) { for (var i = 0; i < (st[s] || 0); i++) viz.appendChild(h("i", { style: "--c:" + color(s), "class": s === "AVAILABLE" || s === "WAITING" ? "e" : null, tip: LABEL[s] })); }); }
    else { viz = h("div", { "class": "stack", role: "img", "aria-label": BAR.map(function (s) { return LABEL[s] + " " + (st[s] || 0); }).join(", ") }); vis.forEach(function (s) { viz.appendChild(h("i", { style: "--c:" + color(s) + ";flex:" + st[s] + " 1 0", tip: LABEL[s] + " · " + st[s] + T(" of ") + total + " (" + Math.round(100 * st[s] / Math.max(1, total)) + "%)" })); }); }
    var kv = h("dl", { "class": "kv" }); BAR.forEach(function (s) { if (s === "WAITING" && !st[s]) return; kv.appendChild(h("dt", {}, [h("i", { "class": "sw", style: "--c:" + color(s) }), LABEL[s]])); kv.appendChild(h("dd", { style: "margin:0" }, [h("b", { text: String(st[s] || 0) })])); });
    return frame(b, "", null, h("div", { "class": "card pad" }, [h("div", { "class": "big" }, [h("b", { text: p.done + "%" }), h("span", { text: (st.INTEGRATED || 0) + T(" of ") + p.total + T(" tasks integrated.") })]), viz, kv,
      h("p", { "class": "note muted", text: p.weighted + T("% counting the work in review and in progress.") })]));
  }
  function bars(counts, labels, tips) {
    var max = Math.max.apply(null, counts.concat([1])), box = h("div", { "class": "cols", role: "img", "aria-label": tips.join(", ") });
    counts.forEach(function (c, k) { box.appendChild(h("div", { "class": k === counts.length - 1 ? "now" : "", tip: tips[k] }, [h("i", { style: "height:" + (c ? Math.max(6, 100 * c / max) : 0) + "%" }), h("span", { text: c ? String(c) : "" }), h("span", { text: labels[k] })])); });
    return box;
  }
  // Integrations per period: the period adapts to the time elapsed so that 6 to 8 bars show; the viewer can fix it.
  function paceBlock(d, max, b) {
    var g = d.generated, done = d.tasks.filter(function (t) { return t.state === "INTEGRATED" && t.updated; }), PS = [3600, 7200, 10800, 14400, 21600, 43200, 86400];
    if (!done.length) return frame(b, "", null, h("div", { "class": "card pad muted", text: L('Nothing has been integrated yet: the first integration starts this chart.') }));
    var el = g - Math.min.apply(null, done.map(function (t) { return t.updated; })), p = ui.period;
    if (!p) { p = 86400; for (var i = 0; i < PS.length; i++) if (el / PS[i] <= 8) { p = PS[i]; break; } }
    var n = Math.min(8, Math.max(6, Math.ceil(el / p))), counts = [], labels = [], tips = [], total = 0;
    for (var k = 0; k < n; k++) { var a = g - (n - k) * p, z = a + p, c = done.filter(function (t) { return t.updated >= a && t.updated < z; }).length; counts.push(c); total += c;
      labels.push(k === n - 1 ? T("now") : p >= 86400 ? new Date(a * 1000).toLocaleDateString(lang(), { weekday: "short" }) : "-" + Math.round((n - 1 - k) * p / 3600) + "h"); tips.push((p >= 86400 ? new Date(a * 1000).toLocaleDateString(lang(), { month: "short", day: "numeric" }) : "-" + Math.round((n - k) * p / 3600) + " h") + " · " + c + (c === 1 ? T(" task") : T(" tasks"))); }
    var week = done.filter(function (t) { return t.updated >= g - 7 * 86400; }).length, left = d.tasks.filter(function (t) { return t.state !== "INTEGRATED" && t.state !== "CANCELLED"; }).length, note = null;
    if (week && left) note = h("p", { "class": "note" }, [L('At this pace the plan ends on') + " ", h("b", { text: new Date((g + left / (week / 7) * 86400) * 1000).toLocaleDateString(lang(), { weekday: "long", month: "short", day: "numeric" }) })]);
    var per = p >= 86400 ? T("day") : p / 3600 + " h";
    return frame(b, "", [seg([[0, T("Auto")], [3600, "1 h"], [7200, "2 h"], [14400, "4 h"], [86400, T("day")]], ui.period, function (v) { ui.period = v; save(); render(); }, L('Period'))], h("div", { "class": "card pad" }, [h("span", { "class": "muted", text: L('Integrated every') + " " + per + " · " + total + T(" in range · peak ") + Math.max.apply(null, counts) }), bars(counts, labels, tips), note]));
  }
  function agentsBlock(d, max, b) {
    var list = d.agents.filter(function (a) { return !a.is_human; }), order = { online: 0, recent: 1, away: 2, offline: 3, retired: 4 };
    list.sort(function (a, c) { return order[a.status] - order[c.status] || c.last_seen - a.last_seen; });
    var online = list.filter(function (a) { return a.status === "online"; }), ul = h("ul", { "class": "list ppl" });
    list.slice(0, max).forEach(function (a) {
      var t = a.tasks[0];
      ul.appendChild(h("li", { "class": a.status === "online" || a.status === "recent" ? "" : "off" }, [avatar(a.name, 24), h("div", { style: "min-width:0" }, [h("b", { text: a.name }), h("small", { text: (t ? rowLabel(t.state) + " " + t.id : T("No live task")) + " · " + mh(a.name) })]), h("span", { "class": "muted num", text: a.last_seen ? ago(a.last_seen, d.generated) : T("never seen") })]));
    });
    if (!list.length) ul.appendChild(h("li", { "class": "empty" }, [h("b", { text: T("No agents yet") }), T("An agent appears here after its first uak command.")]));
    if (list.length > max) ul.appendChild(h("li", { "class": "mre" }, [h("button", { "class": "more", text: "+" + (list.length - max) + " · " + T("Agents"), on: function () { go("agents"); } })]));
    return frame(b, online.length + " " + T("online"), [pres(online.length ? "online" : "offline")], h("div", { "class": "card" }, [ul]));
  }
  function M(n) { return n >= 1e9 ? (n / 1e9).toFixed(2) + "B" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : Math.round(n / 1e3) + "k"; }
  function tokensBlock(d, max, b) {
    var t = d.tokens || { total: 0 }, hs = Object.keys(t.by_harness || {}).sort(function (a, c) { return t.by_harness[c] - t.by_harness[a]; }).slice(0, 3);
    if (!t.total) return frame(b, "", null, h("div", { "class": "card pad muted", text: T("No machine has published its spend yet: uak tokens --publish") }));
    var kv = h("dl", { "class": "kv" }), meter = h("div", { "class": "meter", role: "img", "aria-label": hs.map(function (k) { return k + " " + M(t.by_harness[k]); }).join(", ") });
    hs.forEach(function (k, i) { kv.appendChild(h("dt", { text: k })); kv.appendChild(h("dd", { style: "margin:0" }, [h("b", { text: M(t.by_harness[k]) })])); if (i < 2) meter.appendChild(h("i", { style: "width:" + 100 * t.by_harness[k] / t.total + "%" })); });
    return frame(b, "", null, h("div", { "class": "card pad" }, [h("div", { "class": "big" }, [h("b", { text: M(t.total) }), h("span", { text: T("Tokens spent") })]), meter, kv]));
  }
  // Every task as one small square: state by colour and by shape, the number inside, the rest on hover or in the detail.
  var SQ = { INTEGRATED: "int", REVIEW: "rev", CLAIMED: "prog", BLOCKED: "blk", AVAILABLE: "av", WAITING: "wt" };
  function depWords(id) {
    var t = DG.task[id]; if (!t) return id;
    var u = unmet(DG, id), n = u.length, up = (DG.unb[id] || []).length;
    if (t.state !== "AVAILABLE") return id + " · " + rowLabel(t.state) + (up ? " · " + L('unblocks') + " " + up : "");
    if (!n) return id + " " + L('is ready: nothing blocks it') + (up ? " · " + L('unblocks') + " " + up : "");
    return id + " " + L('cannot start: it waits for') + " " + n + " " + (n === 1 ? T(" task").trim() : T(" tasks").trim()) + " — " + u.slice(0, 3).map(function (x) { return x.id + " (" + depState(x.state) + ")"; }).join(", ") + (n > 3 ? ", " + L('and') + " " + (n - 3) + " " + L('more') : "");
  }
  function depState(s) { return s === "WAITING" ? T("Waiting") : s === "MISSING" ? L('not in the plan') : s === "CANCELLED" ? L('cancelled') : rowLabel(s); }
  function pick(id) {
    SEL = id; var w = {}, u = {};
    if (id) { unmet(DG, id).forEach(function (x) { w[x.id] = 1; }); (DG.unb[id] || []).forEach(function (x) { u[x] = 1; }); }
    Array.prototype.forEach.call(document.querySelectorAll(".sq[data-id]"), function (b) { var x = b.getAttribute("data-id"); b.classList.toggle("dim", !!id && x !== id && !w[x] && !u[x]); b.classList.toggle("w", !!w[x]); b.classList.toggle("u", !!u[x]); b.classList.toggle("sel", x === id); });
    Array.prototype.forEach.call(document.querySelectorAll(".depline"), function (p) { p.textContent = id ? depWords(id) : L('Point at a task to see what it waits for'); });
  }
  function depline() { return h("p", { "class": "depline", role: "status", text: L('Point at a task to see what it waits for') }); }
  function squares(list) {
    var box = h("div", { "class": "tmap", role: "list" });
    list.forEach(function (t) {
      var s = stateOf(t), tip = t.id + " · " + (s === "WAITING" ? T("Waiting") : rowLabel(s)) + (t.owner ? " · " + t.owner : "") + " · " + (t.title || ""), b = h("button", { "class": "sq s-" + SQ[s] + (late(t) ? " late" : ""), type: "button", role: "listitem", "data-id": t.id, style: "--c:" + color(s), tip: tip, "aria-label": tip, text: t.id.replace(/^[A-Z]+-0*/, "") || t.id });
      if (HOVER) { b.addEventListener("mouseenter", function () { pick(t.id); }); b.addEventListener("mouseleave", function () { pick(""); }); b.addEventListener("focus", function () { pick(t.id); }); b.addEventListener("blur", function () { pick(""); }); }
      b.addEventListener("click", function () { if (HOVER || ARMED === t.id) { ARMED = ""; openStory(t.id); } else { ARMED = t.id; pick(t.id); } });
      box.appendChild(b);
    });
    return box;
  }
  document.addEventListener("click", function (e) { if (!HOVER && !(e.target.closest && e.target.closest(".sq"))) { ARMED = ""; if (SEL) pick(""); } });
  function mapBlock(d, max, b) {
    var all = d.tasks.filter(function (t) { return t.state !== "CANCELLED"; }), list = all.filter(match).sort(function (a, c) { return a.id < c.id ? -1 : 1; }), st = {};
    all.forEach(function (t) { var s = stateOf(t); st[s] = (st[s] || 0) + 1; });
    var leg = h("div", { "class": "legend" }, BAR.filter(function (s) { return st[s]; }).map(function (s) { return h("span", {}, [h("i", { "class": "sq sm s-" + SQ[s], style: "--c:" + color(s), "aria-hidden": "true" }), (s === "WAITING" ? T("Waiting") : rowLabel(s)) + " " + st[s]]); }));
    return frame(b, all.length + T(" tasks") + (planCounts(d.tasks).cancelled ? " · " + planCounts(d.tasks).cancelled + " " + L('cancelled') : ""), null, h("div", { "class": "card pad" }, [list.length ? squares(list) : h("span", { "class": "muted", text: T("No messages match") }), depline(), leg]));
  }
  // What each component shows: the one line under its name in Add.
  function about(n) {
    return { needs: L('What waits for you: reviews, stalled tasks, the human queue'),
             map: L('Every task as a square, with what it waits for'),
             tasks: L('The tasks that are moving, as a list or columns'),
             lanes: L('Who built and reviewed what, over time'),
             progress: L('How much of the plan is integrated'),
             agents: L('Who is online and on which task'),
             pace: L('Tasks integrated per period'),
             tokens: L('Tokens spent, by harness') }[n];
  }
  var BLOCKS = [
    { name: "needs", title: function () { return L('Needs you'); }, col: "main", max: 6, render: needsBlock },
    { name: "map", title: function () { return L('All tasks'); }, col: "main", max: 999, render: mapBlock },
    { name: "tasks", title: function () { return T("Tasks"); }, col: "main", max: MAXTASKS, render: tasksBlock },
    { name: "lanes", title: function () { return L('Who did what'); }, col: "main", max: 4, render: lanesBlock },
    { name: "progress", title: function () { return L('Progress'); }, col: "side", max: 24, render: progressBlock },
    { name: "agents", title: function () { return T("Agents"); }, col: "side", max: 4, render: agentsBlock },
    { name: "pace", title: function () { return L('Integrations'); }, col: "side", max: 8, render: paceBlock },
    { name: "tokens", title: function () { return T("Tokens"); }, col: "side", max: 3, render: tokensBlock }
  ];
