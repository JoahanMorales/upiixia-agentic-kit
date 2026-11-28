  // REVIEW: one group per sub-state (lib/dash.py review_substate; the words are the same as `uak status`): who has to act comes first.
  // The review sub-state headings, in the page's language (one L() literal each so the translation test sees them).
  function gname(k) { return { cifail: L('Approved, CI failed'), changes: L('Changes requested'), human: L('Waiting for a human merge'), waiting: L('Waiting for a reviewer'), rereview: L('Re-review'), review: T("In review"), owner: L('Approved, owner to merge') }[k]; }
  // The engine writes the review state in English; the page shows it in its language.
  var SUBES = [['approved, waiting for a human merge', 'aprobada, espera una integración humana'], ['approved, waiting for the merge', 'aprobada, espera la integración'], ['approved, owner to merge', 'aprobada, el dueño integra'], ['approved, CI failed', 'aprobada, falló CI'], ['waiting for a reviewer', 'espera a un revisor'], ['changes requested', 'cambios pedidos'], ['re-review', 'nueva revisión'], ['in review', 'en revisión'], ['round', 'ronda']];
  function trSub(t) { if (!(window.UAKWorkspace && UAKWorkspace.language() === "es")) return t; SUBES.forEach(function (x) { t = String(t).split(x[0]).join(x[1]); }); return t; }
  function reviewGroups(list) {
    var out = [];
    GROUPS.forEach(function (g) {
      var items = list.filter(function (t) { return (t.sub || { kind: "waiting" }).kind === g[0]; });
      if (!items.length) return;
      items.sort(function (a, b) { return ((a.sub || {}).since || 0) - ((b.sub || {}).since || 0) || (a.id < b.id ? -1 : 1); });
      var lateN = items.filter(function (t) { return t.sub && t.sub.late; }).length;
      out.push({ g: g, items: items, late: lateN });
    });
    return out;
  }
  function crew(t) {
    var rows = [];
    if (t.participants) t.participants.split("; ").forEach(function (x) { rows.push(h("li", { text: x })); });
    (t.harnesses || []).forEach(function (x) { rows.push(h("li", {}, [h("span", { "class": "mono", text: x.agent }), " " + L('ran on') + " " + x.harness + " " + L('with') + " " + x.model])); });
    if (!rows.length) return null;
    return h("details", { "class": "crew muted" }, [h("summary", { text: L('Who touched it') }), h("ul", { style: "margin:4px 0 0;padding-left:16px" }, rows)]);
  }
  function prLink(t) {
    if (!t.pr || !/^https:\/\//.test(t.pr)) return null;
    var n = t.pr.match(/\/pull\/(\d+)/);
    return h("a", { "class": "pr", href: t.pr, target: "_blank", rel: "noopener", title: t.pr, text: n ? "#" + n[1] : "PR" });
  }
  function leaseUsed(t) { return t.lease ? Math.min(1, Math.max(0, 1 - (t.lease - D.generated) / LEASE)) : 0; }
  function card(t, s) {
    var prog = t.progress ? t.progress.replace(/ · at \d+$/, "") : "", sub = s === "REVIEW" ? t.sub : null, gen = D.generated;
    return storyable(h("article", { "class": "tk" + (late(t) ? " late" : "") }, [
      h("div", { "class": "top" }, [tid(t.id), t.priority ? h("span", { "class": "tag" + (t.priority === "P0" ? " info" : ""), text: t.priority }) : null,
        t.state === "BLOCKED" ? h("span", { "class": "tag crit", text: rowLabel("BLOCKED") }) : null,
        s === "REVIEW" && approved(t, D) ? h("span", { "class": "tag info", text: T("approved") }) : null,
        t.stalled ? h("span", { "class": "tag crit", text: T("stalled ") + t.stalled + " min" }) : null, t.away ? h("span", { "class": "tag", text: T("owner away") }) : null,
        sub && sub.rounds ? h("span", { "class": "tag", title: sub.rounds + " " + L('review verdict(s) on this task'), text: L('round') + " " + (sub.kind === "rereview" ? sub.rounds + 1 : sub.rounds) }) : null,
        sub && sub.rejects ? h("span", { "class": "tag crit", title: sub.rejects + " " + L('reject(s) so far'), text: sub.rejects + " " + (sub.rejects === 1 ? T("reject") : T("rejects")) }) : null]),
      h("p", { text: t.title || t.paths, title: t.title || t.paths }),
      sub ? h("div", { "class": "why" + (sub.late ? " bad" : ""), title: sub.late ? L('Longer than the review lease') : "" }, [trSub(sub.text) + " · " + span(gen - sub.since) + " " + T("here") + (sub.late ? " · " + T("over the review lease") : "")]) : null,
      s === "CLAIMED" && t.lease ? h("div", { "class": "lease", role: "img", "aria-label": L('Lease used') + " " + Math.round(leaseUsed(t) * 100) + "%", title: L('Lease used') + " " + Math.round(leaseUsed(t) * 100) + "%" }, [h("i", { style: "width:" + Math.round(leaseUsed(t) * 100) + "%" })]) : null,
      h("div", { "class": "ft" }, [t.owner && s !== "AVAILABLE" && s !== "WAITING" ? who(t.owner) : h("span", { text: s === "WAITING" ? T("waits on ") + waitingOn(t).join(", ") : t.depends && t.depends !== "None" ? T("after ") + t.depends : T("free to claim") }), s !== "AVAILABLE" && s !== "WAITING" ? prLink(t) : null]),
      prog ? h("div", { "class": "ft", style: "display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, [h("span", { "class": "prog", text: T(prog), title: prog })]) : null,
      sub ? crew(t) : null]), t.id);
  }
  function board(v, d) {
    viewHeading(v, T("Board"));
    var wrap = h("div", { "class": "wide" + (ui.bv !== "cols" ? " bmap" : "") }), g = d.generated;
    wrap.appendChild(h("div", { "class": "bh" }, [h("h2", { text: T("Board") }), h("span", { "class": "n", text: planCounts(d.tasks).plan + T(" tasks") + (planCounts(d.tasks).cancelled ? " · " + planCounts(d.tasks).cancelled + " " + L('cancelled') : "") }), h("div", { "class": "x" }, [find(render), seg([["map", L('Map')], ["cols", L('Cards')]], ui.bv, function (x) { ui.bv = x; save(); render(); }, L('Show the board as'))])]));
    var by = { todo: [], prog: [], rev: [], done: [] };
    d.tasks.forEach(function (t) { if (!match(t)) return; var s = stateOf(t); (s === "AVAILABLE" || s === "WAITING" ? by.todo : s === "CLAIMED" || s === "BLOCKED" ? by.prog : s === "REVIEW" ? by.rev : s === "INTEGRATED" ? by.done : []).push(t); });
    by.done.sort(function (a, b) { return (b.updated || 0) - (a.updated || 0) || (a.id < b.id ? 1 : -1); });
    var free = by.todo.filter(function (t) { return stateOf(t) === "AVAILABLE"; }).length, stuck = by.prog.filter(function (t) { return stalledMin(t, g) || t.state === "BLOCKED"; }).length;
    var revLate = by.rev.filter(function (t) { return t.sub && t.sub.late; }).length, waiting = by.rev.filter(function (t) { return t.sub && (t.sub.kind === "waiting" || t.sub.kind === "rereview"); }).length;
    var cols = [
      ["todo", L('To do'), "AVAILABLE", by.todo.length ? free + " " + T("available") + (by.todo.length - free ? " · " + (by.todo.length - free) + " " + T("waiting on dependencies") : "") : T("Empty"), false],
      ["prog", T("In progress"), "CLAIMED", by.prog.length ? (stuck ? T("Stalled") + " / " + T("Blocked") + " " + stuck : T("every task is moving")) : T("Nobody is on a task"), stuck > 0],
      ["rev", T("In review"), "REVIEW", by.rev.length ? (waiting ? T("Reviews waiting") + " " + waiting : T("Waiting for review")) + (revLate ? " · " + revLate + " " + T("over the review lease") : "") : T("Empty"), revLate > 0],
      ["done", T("Integrated"), "INTEGRATED", by.done.length ? L('last') + " " + ago(by.done[0].updated || g, g) + T(" ago") : T("Empty"), false]];
    if (ui.bv !== "cols") {
      wrap.appendChild(depline());
      cols.forEach(function (c) {
        var list = by[c[0]];
        wrap.appendChild(h("section", { "class": "card pad", style: "margin-bottom:12px", "aria-label": c[1] }, [h("div", { "class": "bh" }, [h("h2", { text: c[1] }), h("span", { "class": "n", text: String(list.length) }), h("div", { "class": "x", text: c[3] })]), list.length ? squares(list) : h("span", { "class": "muted", text: T("Empty") })]));
      });
      v.appendChild(wrap); return;
    }
    var bd = h("div", { "class": "bd" });
    cols.forEach(function (c) { bd.appendChild(guard("board " + c[1], function () {
      var list = by[c[0]], cut = ui.more[c[0]] ? list.length : MAXTASKS, body = h("div", { "class": "bb" });
      if (!list.length) body.appendChild(h("div", { "class": "muted", style: "padding:8px", text: ui.q ? T("No messages match") : T("Empty") }));
      if (c[0] === "rev") {
        var n = 0; reviewGroups(list).forEach(function (gr) { var part = gr.items.filter(function () { return n++ < cut; }); if (!part.length) return; body.appendChild(h("div", { "class": "gh", text: gname(gr.g[0]) + " · " + gr.items.length + (gr.late ? " · " + gr.late + " " + L('late') : "") })); part.forEach(function (t) { body.appendChild(card(t, "REVIEW")); }); });
      } else if (c[0] === "done") list.slice(0, cut).forEach(function (t) { body.appendChild(storyable(h("div", { "class": "dn" }, [tid(t.id), h("span", { "class": "t", text: t.title || t.paths, title: t.title }), h("small", { text: (t.owner || "") + " · " + ago(t.updated || g, g) + T(" ago") })]), t.id)); });
      else list.slice(0, cut).forEach(function (t) { body.appendChild(card(t, stateOf(t))); });
      if (list.length > MAXTASKS) body.appendChild(h("button", { "class": "more", text: ui.more[c[0]] ? T("Show less") : T("Show all ") + list.length, on: function () { ui.more[c[0]] = !ui.more[c[0]]; render(); } }));
      return (h("section", { "class": "card bcol", "aria-label": c[1] }, [h("header", {}, [h("b", {}, [h("i", { "class": "sw", style: "--c:" + color(c[2]) }), c[1], h("span", { text: String(list.length) })]), h("small", { "class": c[4] ? "bad" : "", text: c[3] })]), body]));
    })); });
    wrap.appendChild(bd); v.appendChild(wrap);
  }

  // 1 message, 2 messages: the singular and the plural both come from the language's labels.
