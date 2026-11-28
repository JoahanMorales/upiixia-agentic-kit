  // Tokens: what the data really holds (kind, harness, model, scope, task); it carries no dates and no budget, and the page says so.
  function tokens(v, d) {
    viewHeading(v, T("Tokens"));
    var t = d.tokens || { total: 0 }, wrap = h("div", { "class": "wide" }); v.appendChild(wrap);
    if (!t.total) { wrap.appendChild(h("div", { "class": "card empty" }, [h("b", { text: T("Tokens spent") + " · 0" }), T("No machine has published its spend yet: uak tokens --publish")])); return; }
    var tb = tokenBreak(t, d.tasks), kinds = t.by_kind || {}, kt = ["input", "cache_write", "cache_read", "output"], KL = { input: L('Input'), cache_write: L('Cache write'), cache_read: L('Cache read'), output: L('Output') };
    var head = h("div", { "class": "card pad", style: "margin-bottom:16px" }, [h("div", { "class": "big" }, [h("b", { text: M(t.total) }), h("span", { text: T("Tokens spent") + " · " + T("published by every machine with uak tokens") })])]);
    var ksum = kt.reduce(function (a, k) { return a + (kinds[k] || 0); }, 0);
    if (ksum) {
      var bar = h("div", { "class": "stack", role: "img", "aria-label": kt.map(function (k) { return KL[k] + " " + M(kinds[k] || 0); }).join(", ") }), kv = h("dl", { "class": "kv" });
      kt.forEach(function (k, i) { if (!kinds[k]) return; bar.appendChild(h("i", { style: "--c:var(--" + ["claimed", "review", "available", "integrated"][i] + ");flex:" + kinds[k] + " 1 0", tip: KL[k] + " · " + M(kinds[k]) })); kv.appendChild(h("dt", {}, [h("i", { "class": "sw", style: "--c:var(--" + ["claimed", "review", "available", "integrated"][i] + ")" }), KL[k]])); kv.appendChild(h("dd", { style: "margin:0" }, [h("b", { text: M(kinds[k]) + " · " + Math.round(100 * kinds[k] / ksum) + "%" })])); });
      head.appendChild(bar); head.appendChild(kv);
    }
    wrap.appendChild(head);
    var named = function (o) { var r = {}; Object.keys(o || {}).forEach(function (k) { r[k === "unknown" ? L('not recorded') : k] = o[k]; }); return r; };
    var g = h("div", { "class": "g2 tkg" }); wrap.appendChild(guard("tokens breakdowns", function () { return g; }));
    [[T("By harness"), named(t.by_harness)], [L('By model'), named(t.by_model)], [T("By scope"), named(t.by_scope)], [L('By agent (owner of the task)'), tb.perAgent, true]].forEach(function (x) {
      if (!Object.keys(x[1] || {}).length) return;   // an empty breakdown draws nothing; the others still draw
      g.appendChild(guard("tokens " + x[0], function () { var pn = panel(x[0], "", hbars(x[1], M, 10)); if (x[2]) { pn.style.gridColumn = "1 / -1"; pn.classList.add("full"); } return pn; }));
    });
    if (tb.top.length) wrap.appendChild(guard("tokens most expensive", function () {
    var ul = h("ul", { "class": "list rows" }), max = tb.top.length ? tb.top[0].n : 1;
    tb.top.slice(0, 10).forEach(function (x) { var st = DG.task[x.id] ? stateOf(DG.task[x.id]) : ""; ul.appendChild(storyable(h("li", {}, [h("span", { "class": "pill " + (PILL[st] || ""), text: st ? rowLabel(st) : L('not in the plan') }), tid(x.id), h("span", { "class": "t", text: x.title || "", title: x.title }), h("span", { "class": "meter", style: "margin:0" }, [h("i", { style: "width:" + Math.max(2, 100 * x.n / max) + "%" })]), h("span", { "class": "w num", text: M(x.n) })]), x.id)); });
    var foot = h("div", { "class": "win-f" }, [figure("", tb.done, L('integrated tasks with tokens'), ""), figure("", tb.done ? M(tb.avg) : "–", L('average per integrated task'), ""), figure("", tb.done ? M(tb.median) : "–", L('median per integrated task'), "")]);
    return (h("div", { style: "margin-top:16px" }, [panel(L('The most expensive tasks'), tb.top.length + T(" tasks") + " " + L('with tokens') + (tb.top.filter(function (x) { return x.state === "CANCELLED"; }).length ? " · " + tb.top.filter(function (x) { return x.state === "CANCELLED"; }).length + " " + L('cancelled among them') : ""), h("div", {}, [ul, foot]))]));
    }));
    if (tb.untied) wrap.appendChild(h("p", { "class": "muted", style: "margin-top:16px", text: L('Not tied to a task') + ": " + M(tb.untied) }));
    wrap.appendChild(h("p", { "class": "muted", style: "margin-top:16px", text: L('The tokens carry no dates or budget, so there is no chart over time.') }));
  }

  // A task's story (UAK-120): d.timelines[ID] is the compact copy of `uak timeline ID` (lib/dash.py compact_timeline), so
  var SK = { plan: ["var(--muted)", "M3 4h10M3 8h10M3 12h6", "planned"], amend: ["var(--violet)", "M3 13l1-3 7-7 2 2-7 7z", "amended"], decision: ["var(--muted)", "M8 2l6 6-6 6-6-6z", "decision"], claim: ["var(--claimed)", "M5 3l8 5-8 5z", "claimed"],
    takeover: ["var(--orange)", "M3 6h10M10 3l3 3-3 3M13 10H3M6 7l-3 3 3 3", "takeover"], checkpoint: ["var(--muted)", "", "checkpoint"], lease: ["var(--muted)", "", "lease"], red: ["var(--violet)", "M6 2h4M7 2v4L3 13h10L9 6V2", "red test"],
    done: ["var(--review)", "M8 13V3M4 7l4-4 4 4", "done"], tip: ["var(--review)", "M13 8a5 5 0 1 1-1.5-3.5M13 2v3h-3", "new tip"], approve: ["var(--integrated)", "M3 8.5l3 3 7-7", "approved"], reject: ["var(--blocked)", "M4 4l8 8M12 4l-8 8", "rejected"],
    ci: ["var(--critical)", "M8 3v6M8 12v.5", "CI failed"], human: ["var(--orange)", "M8 7a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5M3 14c0-3 2.5-5 5-5s5 2 5 5", "human step"], merge: ["var(--integrated)", "M4 3v10M4 8h5a3 3 0 0 0 3-3V3", "merged"], integrate: ["var(--integrated)", "M3 14V2M3 3h9l-2 3 2 3H3", "integrated"],
    handover: ["var(--violet)", "M3 8h9M9 4l4 4-4 4", "handover"], expired: ["var(--warning)", "M8 3a5 5 0 1 0 .01 0M8 5.5V8l2 1.5", "lease expired"], release: ["var(--muted)", "M8 3a5 5 0 1 0 .01 0M4.5 11.5l7-7", "released"], note: ["var(--muted)", "", "note"] };
  var SUBC = function (st, sub) { var x = (sub || st).toLowerCase();
    if (st === "CLAIMED") return "var(--claimed)"; if (st === "AVAILABLE") return "var(--available)"; if (st === "BLOCKED") return "var(--blocked)";
    if (x.indexOf("changes requested") === 0) return "var(--claimed)"; if (x.indexOf("re-review") === 0) return "var(--violet)"; if (x.indexOf("human") > -1) return "var(--orange)";
    if (x.indexOf("ci failed") > -1) return "var(--critical)"; if (x.indexOf("approved") === 0) return "var(--integrated)"; return "var(--review)"; };
  var PILL = { CLAIMED: "p-prog", REVIEW: "p-rev", INTEGRATED: "p-int", BLOCKED: "p-blk" };
  var LIFE = ["Claimed", "In progress", "In review", "Integrated"];
  function lifeLine(state) {
    var at = { CLAIMED: 1, REVIEW: 2, INTEGRATED: 3 }[state], ol = h("ol", { "class": "nodes", "aria-label": T("Your journey") });
    LIFE.forEach(function (name, i) { ol.appendChild(h("li", { "class": at !== undefined && i <= at ? "on" : "", "aria-current": i === at ? "step" : null }, [h("i", {}), h("span", { text: T(name) })])); });
    return h("div", { "class": "st-line" }, [ol]);
  }
  var storyEl = document.getElementById("story"), storyId = "", lastFocus = null;
  function clock(t) { return new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }); }
  function dayKey(t) { return new Date(t * 1000).toDateString(); }
  function dayLabel(t) { return new Date(t * 1000).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" }); }
  function gapEl(g, cls) { return g ? h("span", { "class": "gap" + (g > 3600 ? " long" : ""), text: "+" + span(g), title: "since the previous move" }) : null; }
  function whoModel(a, model, harness) {
    var out = [a === "-" ? h("span", { "class": "muted", text: "no agent" }) : who(a, 16)];
    if (model !== "unknown") out.push(h("span", { "class": "sep", text: "·" }), h("span", { "class": "mono", text: model }));
    if (harness !== "unknown") out.push(h("span", { "class": "sep", text: "·" }), h("span", { text: harness }));
    return out;
  }
  function lineEl(l, prev, i) {
    var k = l[1], sk = SK[k] || SK.note, quiet = k === "checkpoint" || k === "lease" || k === "note" && !l[6], gap = prev ? l[0] - prev[0] : 0;
    var cls = quiet ? "quiet" : k === "reject" ? "alert" : (k === "human" || k === "takeover") ? "hum" : "";
    var det = l[6], long = det && det.length > 260 && cls === "" , open = ui.open["st" + storyId + i];
    var li = h("li", { "class": cls, style: "--c:" + sk[0] }, [
      h("div", { "class": "when" }, [clock(l[0]), h("small", { text: "" }), gap ? gapEl(gap) : null]),
      h("span", { "class": "node", "aria-hidden": "true" }, sk[1] ? [icon(sk[1])] : []),
      h("div", { "class": "body" }, [
        h("div", { "class": "tm" }, [clock(l[0]), gap ? gapEl(gap) : null]),
        h("div", { "class": "head" }, [h("span", { "class": "kd", text: sk[2] }), h("span", { "class": "tx", text: l[5], title: l[8] || null })]),
        quiet && l[2] === "-" ? null : h("div", { "class": "by" }, whoModel(l[2], l[3], l[4])),
        det ? h("div", { "class": "dt" + (long && !open ? " clamp" : ""), text: det }) : null,
        long ? h("button", { "class": "more", text: open ? T("Show less") : T("Show all"), on: function () { ui.open["st" + storyId + i] = !open; fillStory(true); } }) : null])]);
    return li;
  }
