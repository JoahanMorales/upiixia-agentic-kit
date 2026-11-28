  function cnt(n, one, many) { return n + " " + (n === 1 ? one : many); }
  function agents(v, d) {
    viewHeading(v, T("Agents"));
    var wrap = h("div", { "class": "wide agw" }); v.appendChild(wrap);
    var groups = [["online", T("Online"), T("active in the last 30 min")], ["recent", T("Recently active"), T("seen in the last 3 h")], ["away", T("Away"), T("session ended")], ["offline", T("Offline"), T("not seen for 3 h or more")], ["retired", T("Retired"), T("identity retired")]];
    if (!d.agents.length) { wrap.appendChild(h("div", { "class": "card empty" }, [h("b", { text: T("No agents yet") }), T("An agent appears here after its first uak command.")])); return; }
    groups.push(["people", L('People'), L('the humans of the project')]);
    groups.forEach(function (gr) { wrap.appendChild(guard("agents " + gr[0], function () {
      var list = d.agents.filter(function (a) { return gr[0] === "people" ? a.is_human : a.status === gr[0] && !a.is_human; }).sort(function (a, b) { return b.last_seen - a.last_seen || a.name.localeCompare(b.name); });
      if (!list.length) return document.createDocumentFragment();
      var compact = gr[0] === "offline" || gr[0] === "retired" || gr[0] === "away", grid = h("div", { "class": "agrid" + (compact ? " sm" : "") });
      list.forEach(function (a) {
        var ts = a.tasks.slice(0, 2), mhs = a.is_human ? "" : mh(a.name);
        grid.appendChild(h("article", { "class": "ac" }, [
          h("div", { "class": "ac-h" }, [avatar(a.name, 28), h("b", { text: a.name, title: a.name }), a.is_human ? h("span", { "class": "tag info", text: T("human") }) : null,
            a.role === "reviewer" ? h("span", { "class": "tag", text: T("reviewer") }) : null]),
          // last_seen 0: registered but never active (UI-012: "20770 d ago" was the time since 1970).
          h("div", { "class": "sub" }, [pres(a.status), " " + T(a.status) + " · " + (a.last_seen ? ago(a.last_seen, d.generated) + T(" ago") : T("never seen"))]),
          compact && !ts.length ? null : h("div", { "class": "chips", style: "margin:0" }, ts.length ? ts.map(function (t) { return h("button", { "class": "chip", on: function () { openStory(t.id); } }, [h("i", { "class": "sw", style: "--c:" + color(t.state), "aria-hidden": "true" }), h("span", { "class": "mono", text: t.id }), compact ? null : h("span", { "class": "muted", text: rowLabel(t.state) })]); }).concat(a.tasks.length > 2 ? [h("span", { "class": "muted", text: "+" + (a.tasks.length - 2) })] : []) : [h("span", { "class": "muted", text: T("No live task") })]),
          mhs && !compact ? h("div", { "class": "sub ell", title: mhs, text: mhs }) : null,
          compact ? null : h("div", { "class": "sub num", title: cnt(a.messages, L('message'), L('messages')) + " · " + cnt(a.verdicts, L('verdict'), L('verdicts')) + " · " + cnt(a.checkpoints, L('checkpoint'), L('checkpoints')), text: cnt(a.messages, L('message'), L('messages')) + " · " + cnt(a.verdicts, L('verdict'), L('verdicts')) + " · " + cnt(a.checkpoints, L('checkpoint'), L('checkpoints')) })]));
      });
      return (h("section", { style: "margin-bottom:24px;--n:" + list.length + (compact ? ";--cw:170px;--cx:240px" : "") }, [h("div", { "class": "bh" }, [h("h2", { text: gr[1] }), h("span", { "class": "n", text: String(list.length) }), h("div", { "class": "x", text: gr[2] })]), grid]));
    })); });
  }

