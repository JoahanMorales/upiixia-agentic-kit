  // The task drawer's Waits for / Unblocks: direct dependencies at the left, what it unblocks at the right, blockers further back counted.
  function depSection(id) {
    var dd = DG.dep[id] || [], un = DG.unb[id] || []; if (!dd.length && !un.length) return null;
    function node(x) { var t = DG.task[x], st = t ? stateOf(t) : "MISSING"; return h("button", { "class": "dn2", type: "button", disabled: t ? null : "", on: function () { openStory(x); } }, [h("span", { "class": "pill " + (PILL[st] || ""), text: depState(st) }), h("b", { "class": "mono", text: x }), h("span", { "class": "muted", text: t ? t.owner || "" : "" })]); }
    var far = behind(DG, id), open = ui.open["dep" + id], t0 = DG.task[id];
    return h("section", { "class": "st-sec" }, [h("h3", { text: L('Waits for') + " / " + L('Unblocks') }), h("div", { "class": "dg" }, [
      h("div", {}, dd.length ? dd.map(node) : [h("span", { "class": "muted", text: L('Nothing: it starts on its own') })]), h("i", { "class": "dl" }),
      h("div", { "class": "dm" }, [h("b", { "class": "mono", text: id }), h("span", { text: t0 ? depState(stateOf(t0)) : "" })]), h("i", { "class": "dl" }),
      h("div", {}, un.length ? un.map(node) : [h("span", { "class": "muted", text: L('Nothing waits for it') })])]),
      far.length ? h("div", { style: "margin-top:8px" }, [h("button", { "class": "expand", type: "button", text: ["+" + far.length, L('further back'), open ? "· " + T("Show less") : ""].join(" "), on: function () { ui.open["dep" + id] = !open; fillStory(true); } }), open ? h("div", { "class": "chips" }, far.map(function (x) { return node(x.id); })) : null]) : null]);
  }
  function fillStory(keep) {
    var tl = (D.timelines || {})[storyId], t = D.tasks.filter(function (x) { return x.id === storyId; })[0] || { id: storyId, title: "", state: "" };
    var old = storyEl.querySelector(".st-body"), top = old ? old.scrollTop : 0;
    var title = h("h2", { id: "story-title", text: t.title || t.paths || storyId });
    var close = h("button", { "class": "st-x", "aria-label": "Close the story", title: "Close (Escape)", on: function () { closeStory(); } }, [icon(I.x)]);
    var sum = h("div", { "class": "st-sum" }, []);
    var body = h("div", { "class": "st-body" }, []), dsec = depSection(storyId); if (dsec) body.appendChild(dsec);
    if (!tl) {
      body.appendChild(h("div", { "class": "st-note" }, ["The story of " + storyId + " is not embedded in this page: it keeps every open task and the last " + ((D.timeline_bound || {}).closed_kept || 15) + " closed ones, so data.js stays small. Run ", h("span", { "class": "mono", text: "bash .uak/bin/uak timeline " + storyId }), " for the whole story."]));
    } else if (!tl.lines.length) {
      body.appendChild(h("div", { "class": "st-note", text: "No history yet: " + storyId + " has no plan line, claim or move on the claims branch." }));
    } else {
      sum.appendChild(h("span", {}, ["Owner ", h("b", { text: t.owner || "–" })]));
      sum.appendChild(h("span", {}, ["Rounds ", h("b", { text: String(tl.rounds) }), tl.rejects ? h("b", { style: "color:var(--crit-ink)", text: " · " + tl.rejects + " " + (tl.rejects === 1 ? T("reject") : T("rejects")) }) : null]));
      sum.appendChild(h("span", {}, ["Moves ", h("b", { text: String(tl.lines.length) })]));
      var total = tl.states.reduce(function (a, x) { return a + x[2]; }, 0);
      if (total) {
        var bar = h("div", { "class": "sbar", role: "img", "aria-label": "Time in each state: " + tl.states.map(function (x) { return (x[1] || LABEL[x[0]] || x[0]) + " " + span(x[2]); }).join(", ") }, []);
        var leg = h("div", { "class": "slegend" }, []);
        tl.states.forEach(function (x) {
          var c = SUBC(x[0], x[1]), nm = x[1] ? (x[0] === "REVIEW" ? "Review: " : "") + x[1] : (LABEL[x[0]] || x[0]);
          bar.appendChild(h("span", { style: "--c:" + c + ";flex:" + x[2] + " 1 0", tip: nm + " · " + span(x[2]) }));
          leg.appendChild(h("div", { "class": "it", style: "--c:" + c }, [h("span", { "class": "sw" }), h("span", { "class": "nm", text: nm }), h("b", { text: span(x[2]) })]));
        });
        body.appendChild(h("section", { "class": "st-sec" }, [h("h3", { text: T("Time in each state") + (tl.open ? " (" + T("the open one counts to now") + ")" : "") }), bar, leg]));
      }
      body.appendChild(h("section", { "class": "st-sec" }, [h("h3", { text: "Who took part" }), h("div", { "class": "crewrow" }, tl.agents.map(function (a) {
        return h("div", { "class": "pcard" }, [avatar(a[0], 26), h("div", { style: "min-width:0" }, [h("div", { "class": "nm", text: a[0].replace(/^(.+)\/\1$/, "$1") }),
          h("div", { "class": "md" }, a[1] === "unknown" && a[2] === "unknown" ? [h("i", { text: L('Model and harness not recorded') })] : [(a[1] === "unknown" ? "model unknown" : a[1]) + " · " + (a[2] === "unknown" ? "harness unknown" : a[2])]),
          h("div", { "class": "rl", text: a[3] + " " + (a[3] === 1 ? T("move") : T("moves")) + ": " + a[4].join(", ") })])]);
      }))]));
      var ol = h("ol", { "class": "tl" }, []), prev = null, lastDay = "";
      tl.lines.forEach(function (l, i) {
        if (dayKey(l[0]) !== lastDay) { lastDay = dayKey(l[0]); ol.appendChild(h("li", { "class": "day", style: "padding:0" }, [h("span", { text: dayLabel(l[0]) })])); }
        ol.appendChild(lineEl(l, prev, i)); prev = l;
      });
      body.appendChild(h("section", { "class": "st-sec" }, [h("h3", { text: "Every move, in order" }), ol]));
      var ft = [h("div", {}, [h("b", { text: "Commands" }), tl.commands.length ? tl.commands.map(function (c) { return c[0] + " " + c[1] + (c[2] ? " (" + c[2] + " failed)" : ""); }).join(" · ") : "none in the ledger"]),
        h("div", {}, [h("b", { text: "Errors" }), tl.errors ? tl.errors + " in the ledger" : "none"]),
        h("div", {}, [h("b", { text: "Tokens" }), tl.tokens === null || tl.tokens === undefined ? "not published" : tl.tokens.toLocaleString()]),
        h("div", {}, [h("b", { text: "Reviews file history" }), tl.history])];
      body.appendChild(h("section", { "class": "st-sec" }, [h("h3", { text: "Totals" }), h("div", { "class": "st-ft" }, ft)]));
    }
    var hd = h("div", { "class": "st-h" }, [h("div", { "class": "ids" }, [h("span", { "class": "mono", text: storyId }), t.state ? h("span", { "class": "pill " + (PILL[t.state] || ""), text: rowLabel(t.state) }) : null,
      t.priority ? h("span", { "class": "tag", text: t.priority }) : null]), close, title, sum, lifeLine(t.state)]);
    storyEl.innerHTML = ""; storyEl.appendChild(h("div", { "class": "st" }, [hd, body]));
    if (keep) body.scrollTop = top;
  }
  function openStory(id) {
    storyId = id; lastFocus = document.activeElement; fillStory(false);
    if (!storyEl.open) { if (storyEl.showModal) storyEl.showModal(); else storyEl.setAttribute("open", ""); }
    var x = storyEl.querySelector(".st-x"); if (x) x.focus();
  }
  function closeStory() { storyId = ""; if (storyEl.close) storyEl.close(); else storyEl.removeAttribute("open"); if (lastFocus && lastFocus.focus) { try { lastFocus.focus({ preventScroll: true }); } catch (e) {} } }
