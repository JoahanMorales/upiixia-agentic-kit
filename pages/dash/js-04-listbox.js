  // One listbox for every choice in the page (a native select cannot be styled in its opened list): button + role=listbox.
  var LBOPEN = null;
  function listbox(items, value, onpick, label) {
    var cur = Math.max(0, items.map(function (x) { return x[0]; }).indexOf(value)), active = cur, buf = "", bufT = 0, id = "lb" + Math.floor(Math.random() * 1e6);
    var btn = h("button", { "class": "lbb", type: "button", "aria-haspopup": "listbox", "aria-expanded": "false", "aria-label": label }, [h("span", { text: items[cur][1] }), icon("M4 6l4 4 4-4")]);
    var pop = h("ul", { "class": "lbp", role: "listbox", tabindex: "-1", "aria-label": label, id: id, hidden: "" });
    var box = h("span", { "class": "lb" }, [btn, pop]);
    function paint() { Array.prototype.forEach.call(pop.children, function (li, i) { li.setAttribute("aria-selected", String(i === cur)); li.classList.toggle("act", i === active); if (i === active) { pop.setAttribute("aria-activedescendant", li.id); li.scrollIntoView({ block: "nearest" }); } }); }
    function close(back) { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); LBOPEN = null; if (back) btn.focus(); }
    function pick(i) { close(true); if (i !== cur) { cur = i; btn.firstChild.textContent = items[i][1]; onpick(items[i][0]); } }
    function open() {
      if (LBOPEN && LBOPEN !== close) LBOPEN(false);
      pop.hidden = false; btn.setAttribute("aria-expanded", "true"); LBOPEN = close; active = cur;
      var r = btn.getBoundingClientRect(), h2 = Math.min(pop.scrollHeight, 280), below = innerHeight - r.bottom;
      // in the zoomed app a fixed position is in the app's own units: what the window measures divides by Z
      pop.style.minWidth = r.width / Z + "px"; pop.style.left = Math.max(8, Math.min(r.left, innerWidth - pop.offsetWidth * Z - 8)) / Z + "px";
      pop.style.top = (below >= h2 * Z + 8 || below >= r.top ? r.bottom + 4 : r.top - h2 * Z - 4) / Z + "px"; paint(); pop.focus();
    }
    items.forEach(function (x, i) { pop.appendChild(h("li", { role: "option", id: id + "-" + i, text: x[1], on: function () { pick(i); } })); });
    btn.addEventListener("click", function () { if (pop.hidden) open(); else close(true); });
    btn.addEventListener("keydown", function (e) { if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
    pop.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); }   // the list closes first, not the popover it sits in
      else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(active); }
      else if (e.key === "Tab") close(false);
      else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) { clearTimeout(bufT); buf += e.key; bufT = setTimeout(function () { buf = ""; }, 700); active = lbType(items.map(function (x) { return x[1]; }), active, buf); paint(); }
      else { var n = lbMove(items.length, active, e.key); if (n !== active) { e.preventDefault(); active = n; paint(); } }
    });
    document.addEventListener("click", function (e) { if (!pop.hidden && !box.contains(e.target)) close(false); });
    window.addEventListener("scroll", function (e) { if (!pop.hidden && !pop.contains(e.target)) close(false); }, true);
    return box;
  }
  function seg(items, cur, set, label) {
    return h("span", { "class": "seg", role: "group", "aria-label": label }, items.map(function (x) { return h("button", { type: "button", text: x[1], "aria-pressed": String(cur === x[0]), on: function () { set(x[0]); } }); }));
  }
