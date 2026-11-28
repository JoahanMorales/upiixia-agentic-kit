  // Message text: URLs become short links, 40-hex SHAs show as 7 characters (the full one on hover).
  function rich(text) {
    text = String(text).replace(/`([^`]*)`/g, "$1").replace(/lease\/([A-Za-z0-9-]+)\/\d+/g, "lease of $1").replace(/(Paths: )([^|\n;]+)/g, function (m, k, list) {
      var seen = {}, all = list.split(/,\s*/).filter(function (x) { return x && !seen[x] && (seen[x] = 1); });
      return all.length > 3 ? k + all.slice(0, 2).join(", ") + " +" + (all.length - 2) : k + all.join(", ");
    });
    var frag = document.createDocumentFragment(), re = /(https?:\/\/[^\s)]+)|\b([0-9a-f]{40})\b/g, at = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > at) frag.appendChild(document.createTextNode(text.slice(at, m.index)));
      if (m[1]) {
        var u = m[1].replace(/[.,;:]+$/, ""), short = u.replace(/^https?:\/\/(www\.)?/, "");
        var gh = u.match(/github\.com\/[^/]+\/[^/]+\/(pull\/\d+|compare\/[^?#]+|actions\/runs\/\d+|commit\/[0-9a-f]+)/);
        if (gh) short = gh[1].replace(/^compare\/.*?\.\.\.?/, "compare ").replace(/^pull\//, "PR #").replace(/^actions\/runs\//, T("CI run ")).replace(/^commit\/([0-9a-f]{7}).*/, "commit $1");
        else if (short.length > 48) short = short.slice(0, 45) + "…";
        frag.appendChild(h("a", { href: u, target: "_blank", rel: "noopener", title: u, text: short }));
        if (u.length < m[1].length) frag.appendChild(document.createTextNode(m[1].slice(u.length)));
      } else frag.appendChild(h("span", { "class": "sha", title: m[2], text: m[2].slice(0, 7) }));
      at = m.index + m[0].length;
    }
    if (at < text.length) frag.appendChild(document.createTextNode(text.slice(at)));
    return frag;
  }
  // Messages: one conversation per task (rule 12 of docs/design/DIRECTION.md), told in the task's stages. The page has no server: it cannot send.
  function viewer() { var v = ""; D.agents.forEach(function (a) { if (a.is_human && (!v || a.last_seen > AG[v].last_seen)) v = a.name; }); return v; }
  function mine(n, me) { var a = AG[n]; return !!a && (n === me || a.human === me); }
  var SEEN = {}; try { SEEN = JSON.parse(store.getItem("uak-seen") || "{}"); } catch (e) {}
  function seen(k, now) { if (!SEEN._0) SEEN._0 = now; if (k) SEEN[k] = now; try { store.setItem("uak-seen", JSON.stringify(SEEN)); } catch (e) {} }
  // The stages a conversation is told in, from the task's story: in progress, in review (round n), integrated.
  function stagesOf(id) {
    var out = [], r = 0;
    ((D.timelines || {})[id] || { lines: [] }).lines.forEach(function (l) {
      if (l[1] === "claim") out.push([l[0], T("In progress")]); else if (l[1] === "done") out.push([l[0], T("In review") + " · round " + (++r)]); else if (l[1] === "integrate") out.push([l[0], T("Integrated")]);
    });
    return out;
  }
  function convos(d, me) {
    var by = {}, hq = {}; humanQueue(d).forEach(function (q) { hq[q.task] = 1; });
    d.messages.forEach(function (m) {
      var c = by[m.task || ""] = by[m.task || ""] || { id: m.task || "", msgs: [], who: {}, rej: 0, rev: 0, me: false };
      c.msgs.push(m); c.who[m.from] = 1; m.to.forEach(function (x) { if (/^agent:/.test(x)) c.who[x.slice(6)] = 1; });
      if (m.kind === "reject") c.rej++; if (m.kind === "review") c.rev++;
      if (m.kind === "human" || m.to.indexOf("agent:" + me) >= 0) c.me = true;
    });
    return Object.keys(by).map(function (k) {
      var c = by[k], t = d.tasks.filter(function (x) { return x.id === k; })[0]; c.task = t; c.last = c.msgs[c.msgs.length - 1];
      c.you = !!hq[k];
      c.group = !k ? "general" : c.you ? "you" : t && t.state !== "INTEGRATED" && t.state !== "CANCELLED" ? "moving" : "closed";
      return c;
    }).sort(function (a, b) { return b.last.t - a.last.t; });
  }
  function talk(v, d) {
    viewHeading(v, T("Conversation"));
    var wrap = h("div", { "class": "wide" }); v.appendChild(wrap);
    var me = viewer(), all = convos(d, me), g = d.generated; if (!SEEN._0) seen("", g);
    var f = h("div", { "class": "filters", role: "search" }, [find(render), seg([["all", L('All')], ["mine", L('My agents')], ["me", L('For me')], ["new", L('Unread')]], ui.mf, function (x) { ui.mf = x; save(); render(); }, L('Show'))]);
    if (ui.q || ui.mf !== "all") f.appendChild(h("button", { "class": "clear", text: T("Clear filters"), on: function () { ui.q = ""; ui.mf = "all"; save(); render(); } }));
    f.appendChild(h("span", { "class": "count", text: cnt(d.messages.length, L('message'), L('messages')) }));
    wrap.appendChild(f);
    if (!d.messages.length) { wrap.appendChild(h("div", { "class": "card empty" }, [h("b", { text: T("No messages yet") }), L('Reviews, contracts and replies between agents show up here as they happen.')])); return; }
    var q = ui.q.toLowerCase(), list = all.filter(function (c) {
      if (ui.mf === "mine" && !Object.keys(c.who).some(function (n) { return mine(n, me); })) return false;
      if (ui.mf === "me" && !c.me && !c.you) return false;
      if (ui.mf === "new" && c.last.t <= Math.max(SEEN[c.id] || 0, SEEN._0)) return false;
      return !q || (c.id + " " + (c.task ? c.task.title + " " + c.task.owner : "") + " " + Object.keys(c.who).join(" ")).toLowerCase().indexOf(q) >= 0;
    });
    if (!list.length) { wrap.appendChild(h("div", { "class": "card empty" }, [h("b", { text: T("No messages match") }), L('Try another agent or task, or clear the search.')])); return; }
    var order = ["you", "moving", "closed", "general"], cur = list.filter(function (c) { return c.id === ui.task; })[0] || list.slice().sort(function (a, b) { return order.indexOf(a.group) - order.indexOf(b.group); })[0];
    var left = h("div", { "class": "card cl" });
    [["you", L('Waiting for you')], ["moving", L('Moving')], ["closed", L('Closed')], ["general", L('General')]].forEach(function (gr) {
      var items = list.filter(function (c) { return c.group === gr[0]; }); if (!items.length) return;
      left.appendChild(h("div", { "class": "cg", text: gr[1] + " · " + items.length }));
      items.slice(0, ui.more["c" + gr[0]] ? items.length : 5).forEach(function (c) {
        var last = c.last, unread = last.t > Math.max(SEEN[c.id] || 0, SEEN._0);
        left.appendChild(h("button", { "class": "th", type: "button", "aria-current": String(c === cur), on: function () { ui.task = c.id; seen(c.id, g); save(); render(); } }, [
          h("b", { text: c.id || L('General') }), h("time", { text: ago(last.t, g) }), h("span", { "class": "tt", text: c.task ? c.task.title : L('Messages to everyone') }),
          h("p", {}, [avatar(last.from, 16), h("span", { text: last.text.replace(/\s+/g, " ") })]), unread ? h("i", { "class": "u", "aria-label": L('Unread') }) : null]));
      });
      if (items.length > 5) left.appendChild(h("button", { "class": "more", text: ui.more["c" + gr[0]] ? T("Show less") : T("Show all ") + items.length, on: function () { ui.more["c" + gr[0]] = !ui.more["c" + gr[0]]; render(); } }));
    });
    var t = cur.task, tl = (d.timelines || {})[cur.id], rounds = tl ? tl.rounds : cur.rev;
    var head = h("div", { "class": "win-h" }, [h("i"), h("i"), h("i"), h("span", { text: (cur.id || L('General')) + (t ? " · " + (t.title || "") : "") }), cur.id ? h("button", { "class": "chip", style: "margin-left:auto", type: "button", text: L('See the task'), on: function () { openStory(cur.id); } }) : null]);
    var chat = h("div", { "class": "chat" }), st = stagesOf(cur.id), si = 0, from = ui.more["t" + cur.id] ? 0 : Math.max(0, cur.msgs.length - 25);
    if (from) chat.appendChild(h("button", { "class": "more", text: L('Show earlier messages') + " (" + from + ")", on: function () { ui.more["t" + cur.id] = true; render(); } }));
    var shown = cur.msgs.slice(from), runs = [];
    shown.forEach(function (m) { var k = m.from + "|" + m.text.slice(0, 22), r = runs[runs.length - 1]; if (r && r.k === k && m.kind === r.m[0].kind) r.m.push(m); else runs.push({ k: k, m: [m] }); });
    runs.forEach(function (r) {
      if (r.m.length > 2 && !ui.open["run" + r.m[0].n]) { drawMsg(r.m[0]); chat.appendChild(h("button", { "class": "more", type: "button", text: "+" + (r.m.length - 1) + " " + L('similar messages'), on: function () { ui.open["run" + r.m[0].n] = true; render(); } })); }
      else r.m.forEach(drawMsg);
    });
    function drawMsg(m) {
      while (si < st.length && st[si][0] <= m.t) { chat.appendChild(h("div", { "class": "stg" }, [h("span", { text: st[si][1] })])); si++; }
      if (m.from === "scheduler" || m.from === "github") { chat.appendChild(h("div", { "class": "sys" }, [h("time", { "class": "mono", text: ago(m.t, g) + T(" ago") }), h("span", { text: m.text.replace(/\s+/g, " ").slice(0, 140) })])); return; }
      var toTask = false, to = h("span", { "class": "who" }, ["→"].concat(m.to.map(function (x) {
        if (/^agent:/.test(x)) return avatar(x.slice(6), 16);
        if (x === "task:" + m.task) { toTask = true; return null; }
        return h("span", { "class": "tag", text: x.replace(/^task:/, "") });
      })));
      var long = m.text.length > 200, open = ui.open[m.n];
      chat.appendChild(h("article", { "class": "msg k-" + m.kind + (mine(m.from, me) ? " me" : "") }, [avatar(m.from, 24), h("div", { style: "min-width:0" }, [
        h("div", { "class": "head2" }, [h("b", { text: m.from }), to, h("span", { "class": "kind", text: m.kind }), h("span", { "class": "num", title: new Date(m.t * 1000).toLocaleString(), text: "#" + m.n + " · " + ago(m.t, g) + T(" ago") })]),
        h("div", { "class": "bub" + (long && !open ? " clamp" : "") }, [rich(m.text)]),
        long ? h("button", { "class": "expand", text: open ? T("Show less") : T("Show more"), on: function () { ui.open[m.n] = !ui.open[m.n]; render(); } }) : null])]));
    }
    while (si < st.length) { chat.appendChild(h("div", { "class": "stg" }, [h("span", { text: st[si][1] })])); si++; }
    var side = h("div", { "class": "card cs" }, [h("div", { "class": "pad" }, [t ? h("span", { "class": "pill " + (PILL[t.state] || ""), text: rowLabel(t.state) }) : null, h("p", { style: "margin:8px 0 0;font-weight:600", text: t ? t.title : L('Messages to everyone') })]),
      h("div", { "class": "win-f" }, [figure("", cur.msgs.length, T("Messages"), ""), figure("", rounds, L('Rounds'), ""), figure(cur.rej ? "warm" : "", cur.rej, L('Changes requested'), "")]),
      h("div", { "class": "pad" }, [h("div", { "class": "gh", text: L('In the thread') })].concat(Object.keys(cur.who).map(function (n) { return h("div", { "class": "who", style: "display:flex;padding:4px 0" }, [avatar(n, 20), h("span", { text: n }), mine(n, me) ? h("span", { "class": "tag info", text: L('yours') }) : null]); })))]);
    wrap.appendChild(h("div", { "class": "cv" }, [left, h("div", { "class": "win" }, [head, chat]), side]));
    requestAnimationFrame(function () { Array.prototype.forEach.call(chat.querySelectorAll(".bub.clamp"), function (el) { if (el.scrollHeight <= el.clientHeight + 2) { el.classList.remove("clamp"); if (el.nextSibling) el.nextSibling.remove(); } }); });
  }

  function hbars(obj, fmt, limit) {
    var keys = Object.keys(obj).sort(function (a, b) { return obj[b] - obj[a]; }).slice(0, limit || 20), max = keys.length ? obj[keys[0]] : 1, g = h("div", { "class": "hb" });
    keys.forEach(function (k) {
      var val = fmt ? fmt(obj[k]) : String(obj[k]);
      g.appendChild(h("span", { "class": "l", text: k, title: k }));
      g.appendChild(h("span", {}, [h("span", { "class": "b", style: "width:" + Math.max(1, 100 * obj[k] / max) + "%", tip: k + " · " + val })]));
      g.appendChild(h("span", { "class": "v", text: val }));
    });
    return g;
  }
  function capped(ul, key, list, draw) {
    list.slice(0, ui.more[key] ? list.length : MAXTASKS).forEach(function (x) { ul.appendChild(draw(x)); });
    if (list.length > MAXTASKS) ul.appendChild(h("li", { "class": "mre" }, [h("button", { "class": "more", text: ui.more[key] ? T("Show less") : T("Show all ") + list.length, on: function () { ui.more[key] = !ui.more[key]; render(); } })]));
  }
  function panel(title, n, body) { return h("section", {}, [h("div", { "class": "bh" }, [h("h2", { text: title }), n ? h("span", { "class": "n", text: n }) : null]), h("div", { "class": "card" }, [body])]); }
  function none(a, b) { return h("div", { "class": "empty" }, [h("b", { text: a }), b || ""]); }
