  // One block's exception never blanks the rest of a tab: the block says it could not be drawn, the error is kept for the tests.
  var ERRORS = window.UAK_ERRORS = [];
  function guard(name, fn) {
    try { return fn(); } catch (e) { ERRORS.push(name + ": " + (e && e.message)); if (window.console) console.error("uak dash: " + name, e); return h("div", { "class": "card pad muted", role: "status", text: L('Could not draw this block') + " (" + name + ")" }); }
  }
  // The viewer's arrangement, kept in this browser per project: read once per page, then held here (a write that fails keeps it for
  // the page's life and says so). Without one of their own the viewer follows the team's (.uak/dash/layout.json), else the default.
  var LAY = null, LAYKEY = "", LAYNOTE = "", KEEPFAIL = false, FOCUS = "", ANN = "";
  function arrDef() { return BLOCKS.map(function (b) { return [b.name, b.col]; }); }
  function keepLay(l) { LAY = l; try { if (l) store.setItem(LAYKEY, JSON.stringify(l)); else store.removeItem(LAYKEY); KEEPFAIL = false; } catch (e) { KEEPFAIL = true; } }
  function arrangement(d) {
    if (LAYKEY !== "uak-layout:" + d.repo) {
      LAYKEY = "uak-layout:" + d.repo; LAY = null; LAYNOTE = "";
      var raw = null; try { raw = store.getItem(LAYKEY); } catch (e) {}
      // a stored null is no arrangement: the team's default applies
      if (typeof raw === "string" && raw !== "null") { var r = arrRead(arrDef(), raw); LAYNOTE = r.note; if (r.note) keepLay(r.note === "corrupt" ? null : r.lay); else LAY = r.lay; }
    }
    return LAY || arrRead(arrDef(), d.layout).lay;
  }
  // The button pressed stays where it was on the screen: the page scrolls by what the component moved, at once, so a component
  // moved up or down keeps its place under the pointer and the eye, and pressing again moves it again. A hide sends focus to the
  // Add button that undoes it: the keyboard follows it there, the pointer stays where it was.
  var ANCHOR = null;
  function arrGo(next, name, f, said, btn, e) { ANCHOR = btn ? { y: btn.getBoundingClientRect().top, mouse: !!(e && e.detail) } : null; keepLay(next); FOCUS = name + ":" + f; ANN = said; render(); }
  function keepInView(el, moved) {
    var add = /^add:/.test(el.getAttribute("data-f"));
    if (moved && ANCHOR && !add) scrollBy({ top: el.getBoundingClientRect().top - ANCHOR.y, behavior: "instant" });
    el.focus({ preventScroll: !moved || !!ANCHOR && !(add && !ANCHOR.mouse) });
  }
  function where(l, n) { var c = l.main.indexOf(n) >= 0 ? "main" : "side"; return (l[c].indexOf(n) + 1) + "/" + l[c].length + " · " + (c === "main" ? L('Main column') : L('Side column')); }
  function handles(b, el, c, i, lay, st) {
    var n = lay[c].length;
    function hb(f, ic, label, off, next) { return h("button", { type: "button", "class": "hnd", "data-f": b.name + ":" + f, title: label, "aria-label": label + " · " + b.title(), disabled: off ? "" : null, on: function (e) { arrGo(next(), b.name, f, b.title() + " · " + (f === "hide" ? L('Hidden') : where(next(), b.name)), this, e); } }, [icon(ic)]); }
    el.setAttribute("inert", "");
    return h("div", { "class": "arr", "data-blk": b.name, style: "--d:-" + ((i * 0.7 + (c === "side" ? 0.4 : 0)) % 1.6).toFixed(1) + "s" }, [h("div", { "class": "hbar" }, [
      h("span", { "class": "grip", "data-grip": b.name, title: L('Drag to move'), "aria-hidden": "true" }, [icon("M6 4h.01M10 4h.01M6 8h.01M10 8h.01M6 12h.01M10 12h.01")]), h("b", { text: b.title() }),
      hb("up", "M8 13V3M4 7l4-4 4 4", L('Move up'), !i && (!st || c === "main"), function () { return arrMove(lay, b.name, -1, st); }),
      hb("down", "M8 3v10M4 9l4 4 4-4", L('Move down'), i === n - 1 && (!st || c === "side"), function () { return arrMove(lay, b.name, 1, st); }),
      hb("col", "M2.5 3h11v10h-11zM9 3v10", L('To the other column'), false, function () { return arrMove(lay, b.name, 0, st); }),
      b.name === "needs" ? h("span", { "class": "muted", text: L('Always shown') }) : hb("hide", "M2 2l12 12M4.2 4.6C2.5 5.9 1.5 8 1.5 8s2.4 4.5 6.5 4.5c1.3 0 2.4-.4 3.4-1M7 3.6l1-.1c4.1 0 6.5 4.5 6.5 4.5s-.5.9-1.4 2", L('Hide'), false, function () { return arrHide(lay, b.name); })]), el]);
  }
  // Drag, on top of the buttons: only the grip takes the pointer (touch-action: none on it alone), so a finger anywhere else still
  // scrolls the page. A line shows where the component lands; the drop is the same change of the arrangement as the buttons make.
  var DRAG = null;
  function dropAt(x, y) {
    var best = null, bd = Infinity;
    Array.prototype.forEach.call(document.querySelectorAll("#view .col[data-col]"), function (c) {
      var r = c.getBoundingClientRect(), d = Math.max(r.left - x, 0, x - r.right) + Math.max(r.top - y, 0, y - r.bottom);
      if (d < bd) { bd = d; best = c; }
    });
    if (!best) return null;
    var boxes = Array.prototype.filter.call(best.children, function (a) { return a.classList.contains("arr") && a !== DRAG.box; }), r0 = best.getBoundingClientRect();
    if (!boxes.length) return { col: best.getAttribute("data-col"), at: 0, x: r0.left, w: r0.width, y: r0.top };
    // A column may show its components in several columns of its own (sumCols), read down the first, then the next: the pointer
    // is in the one nearest to it; the components of the ones before it and those above the pointer in it come first. Boxes
    // whose left edges are within 40 px share a column (a shaking box is turned by half a degree; columns are 296 px apart or more).
    var rs = boxes.map(function (a) { return a.getBoundingClientRect(); }), lane = 0, ld = Infinity, at = 0, last = 0;
    rs.forEach(function (r) { var d = Math.max(r.left - x, 0, x - r.right); if (d < ld) { ld = d; lane = r.left; } });
    function same(r) { return Math.abs(r.left - lane) < 40; }
    rs.forEach(function (r, i) { if ((r.left < lane && !same(r)) || (same(r) && y > r.top + r.height / 2)) at++; if (same(r)) last = i; });
    var next = at < rs.length && same(rs[at]) ? rs[at] : null, r1 = next || rs[last];
    return { col: best.getAttribute("data-col"), at: at, x: r1.left, w: r1.width, y: next ? next.top - 10 : r1.bottom + 8 };
  }
  document.addEventListener("pointerdown", function (e) {
    var g = ui.arr && e.target.closest && e.target.closest("[data-grip]");
    if (!g || e.button > 0) return;
    e.preventDefault();
    DRAG = { name: g.getAttribute("data-grip"), box: g.closest(".arr"), x: e.clientX, y: e.clientY, sy: scrollY, to: null, line: null };
    DRAG.box.classList.add("drag");
    try { g.setPointerCapture(e.pointerId); } catch (x) {}
  });
  document.addEventListener("pointermove", function (e) {
    if (!DRAG) return;
    DRAG.box.style.transform = "translate(" + (e.clientX - DRAG.x) / Z + "px," + (e.clientY - DRAG.y + scrollY - DRAG.sy) / Z + "px)";   // the box follows the pointer in the zoomed app
    var t = DRAG.to = dropAt(e.clientX, e.clientY);
    if (t) { DRAG.line = DRAG.line || document.body.appendChild(h("div", { "class": "dropline" })); DRAG.line.style.cssText = "left:" + t.x + "px;width:" + t.w + "px;top:" + t.y + "px"; }
    if (e.clientY < 48) scrollBy(0, -16); else if (e.clientY > innerHeight - 48) scrollBy(0, 16);
  });
  function endDrag(e) {
    if (!DRAG) return;
    var d = DRAG, t = d.to, l; DRAG = null;
    if (d.line) d.line.remove();
    d.box.classList.remove("drag"); d.box.style.transform = "";
    // released outside the window (a mouse let go beyond its edge): a cancel, never a drop at the nearest column
    if (e.type === "pointerup" && t && e.clientX >= 0 && e.clientY >= 0 && e.clientX <= innerWidth && e.clientY <= innerHeight) { l = arrPlace(arrangement(D), d.name, t.col, t.at); arrGo(l, d.name, "up", blockOf(d.name).title() + " · " + where(l, d.name)); }
  }
  ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (k) { document.addEventListener(k, endDrag); });
  function blockOf(n) { return BLOCKS.filter(function (b) { return b.name === n; })[0]; }
  function arrBar(d, lay, def) {
    if (!ui.arr) return h("div", { "class": "arrbar" }, [LAYNOTE ? h("p", { role: "status", text: LAYNOTE === "corrupt" ? L('Your saved arrangement could not be read: the summary shows the default.') : L('Your arrangement named components that no longer exist: they were left out.') }) : null,
      h("button", { "class": "ab", type: "button", "data-f": "arr:edit", on: function () { ui.arr = true; LAYNOTE = ""; FOCUS = "arr:done"; render(); } }, [icon("M3 13h3l7-7-3-3-7 7zM9 4l3 3"), L('Edit')])]);
    var add = lay.hide.map(function (n) { return h("button", { type: "button", "class": "addb", "data-f": "add:" + n, on: function (e) { var l = arrAdd(def, lay, n); arrGo(l, n, "up", blockOf(n).title() + " · " + where(l, n), this, e); } }, [h("b", {}, [icon("M8 3v10M3 8h10"), blockOf(n).title()]), h("span", { text: about(n) })]); });
    return h("div", { "class": "arrbar on" }, [h("p", { "class": "tip", text: L('Move, hide or add components. Done when you finish.') }),
      h("button", { "class": "ab", type: "button", "data-f": "arr:restore", disabled: LAY ? null : "", on: function () { keepLay(null); FOCUS = "arr:done"; ANN = d.layout ? L('The team\'s default is back') : L('The default is back'); render(); } }, [d.layout ? L('Restore the team\'s default') : L('Restore the default')]),
      h("button", { "class": "ab done", type: "button", "data-f": "arr:done", on: function () { ui.arr = false; FOCUS = "arr:edit"; render(); } }, [L('Done')]),
      h("div", { "class": "adds", role: "group", "aria-label": L('Add') }, [h("span", { "class": "muted", text: L('Add') })].concat(add.length ? add : [h("span", { text: L('Every component is shown.') })])),
      h("div", { "class": "team" }, [h("span", { "class": "muted", text: L('For the whole team: run this and commit the file it writes') }), copyBox("bash .uak/bin/uak dash layout --save" + ["main", "side", "hide"].map(function (c) { return lay[c].length ? " " + c + "=" + lay[c].join(",") : ""; }).join(""))]),
      KEEPFAIL ? h("p", { role: "status", text: L('This browser does not keep the arrangement: it lasts until the page is closed.') }) : null]);
  }
  function summary(v, d) {
    viewHeading(v, T("Overview"));
    var empty = !d.tasks.length, def = arrDef(), lay = arrangement(d), arr = ui.arr = ui.arr && !empty, st = !!(window.matchMedia && matchMedia("(max-width:1100px)").matches), by = {}, cols = {};
    BLOCKS.forEach(function (b) { by[b.name] = b; });
    ["main", "side"].forEach(function (c) {
      cols[c] = h("div", { "class": "col", "data-col": c });
      (empty ? (c === "main" && needs(d).length ? ["needs"] : []) : lay[c]).forEach(function (n, i) {
        var b = by[n], el = guard(n, function () { return b.render(d, b.max, b); });
        cols[c].appendChild(arr ? guard(n, function () { return handles(b, el, c, i, lay, st); }) : el);
      });
      if (arr && !lay[c].length) cols[c].appendChild(h("p", { "class": "arr-empty", text: L('Move a component here') }));
    });
    if (empty) cols.main.appendChild(h("div", { "class": "card next" }, [h("h2", { text: L('Your project has no plan yet') }), h("p", { text: L('Start the guide: it asks what you build and writes the plan.') }), copyBox("bash .uak/bin/uak start"),
      h("p", { "class": "muted", text: L('Nothing is claimed or integrated yet, so every figure is zero.') })]));
    var shown = ["main", "side"].filter(function (c) { return cols[c].children.length; }).map(function (c) { return cols[c]; });
    fitSummary(v.appendChild(h("div", { "class": "page" + (arr ? " arranging" : "") + (shown.length < 2 ? " one" : ""), style: shown.length < 2 ? "grid-template-columns:minmax(0,1fr)" : null }, [empty ? null : guard("arrange", function () { return arrBar(d, lay, def); })].concat(shown))));
  }
  // The summary at this width (sumCols): the side's width and how many columns each list shows. Nothing is set up to 1480 px.
  function fitSummary(p) {
    if (!p || !p.querySelector) return;
    var col = {}, n = {}, cs = window.getComputedStyle ? window.getComputedStyle(p) : null;
    ["main", "side"].forEach(function (c) { col[c] = p.querySelector('.col[data-col="' + c + '"]'); n[c] = col[c] ? Array.prototype.filter.call(col[c].children || [], function (e) { return !e.classList.contains("arr-empty"); }).length : 0; });
    var r = sumCols(p.clientWidth - (cs ? parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) : 0), n.main, n.side);
    if (col.main && col.side && n.main && n.side) p.style.gridTemplateColumns = r.w !== 296 ? "minmax(0,1fr) " + r.w + "px" : "";
    // a list alone flows only where it has the page's width: the main column, or the side when the main column is not drawn
    ["main", "side"].forEach(function (c) { if (!col[c]) return; var k = r.side ? (c === "side" ? r.side : 1) : n[c] && (c === "main" || !col.main) ? r.flow : 1; col[c].classList.toggle("flow", k > 1); col[c].style.columnCount = k > 1 ? String(k) : ""; });
  }
  var fitW = window.innerWidth, fitting = 0;
  window.addEventListener("resize", function () {
    if (fitting) return;
    fitting = requestAnimationFrame(function () {
      fitting = 0; if (window.innerWidth === fitW || DRAG) return; fitW = window.innerWidth;
      var z0 = Z; fitScale(); if (Z !== z0) { render(); return; }
      if (ui.tab === "sum") fitSummary(document.querySelector("#view .page")); else if (ui.tab === "memory" && ui.mv === "graph") render();
    });
  });

  var GROUPS = [["cifail", "Approved, CI failed"], ["changes", "Changes requested"], ["human", "Waiting for a human merge"], ["waiting", "Waiting for a reviewer"], ["rereview", "Re-review"],
                ["review", "In review"], ["owner", "Approved, owner to merge"]];
