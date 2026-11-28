  // Share: a 1200x630 card drawn on a canvas from the same numbers as the page (shareStats), with the kit's own identicons.
  function tok(n) { var e = document.createElement("i"); e.style.color = "var(--" + n + ")"; document.body.appendChild(e); var c = getComputedStyle(e).color; e.remove(); return c; }
  function shareFigs(S) {
    return [[S.tokens ? M(S.tokens) : null, T("Tokens spent")], [S.agents ? String(S.agents) : null, T("Agents")], [S.total ? S.integrated + " / " + S.total : null, T("Integrated")], [S.commits !== null ? String(S.commits) : null, L('Commits on main')]].filter(function (f) { return f[0] !== null; });
  }
  // Two compositions of the same numbers: "h" 1200x630 (drawn at 2x) and "v" 1080x1920 for a story, which keeps its top 250 px
  // and bottom 340 px free of anything important (the story's own interface covers them).
  var SAFE_TOP = 250, SAFE_BOTTOM = 340;
  function drawCard(cv, d, fmt) {
    var S = shareStats(d), v = fmt === "v", W = v ? 1080 : 1200, H = v ? 1920 : 630, k2 = 1, c = cv.getContext("2d"), rs = getComputedStyle(document.documentElement), sans = rs.getPropertyValue("--sans"), mono = rs.getPropertyValue("--mono");
    cv.width = W * k2; cv.height = H * k2; c.scale(k2, k2);
    function box(x, y, w, h, r, fill) { c.beginPath(); if (c.roundRect) c.roundRect(x, y, w, h, r); else c.rect(x, y, w, h); if (fill) { c.fillStyle = fill; c.fill(); } }
    function text(t, x, y, size, w, col, font, align) { c.font = w + " " + size + "px " + (font || sans); c.fillStyle = col; c.textAlign = align || "left"; c.fillText(t, x, y); }
    function fit(t, size, max) { c.font = "700 " + size + "px " + sans; while (size > 28 && c.measureText(t).width > max) { size -= 4; c.font = "700 " + size + "px " + sans; } return size; }
    function idc(n, human, x, y, z) {
      var k = idcells(n, human), q = function (r) { return rs.getPropertyValue("--idc-" + r).trim(); }, u = z / 7;
      box(x, y, z, z, z * .16, "hsl(" + k.hue + " " + q("bg-s") + " " + q("bg-l") + ")"); c.fillStyle = "hsl(" + k.hue + " " + q("px-s") + " " + q("px-l") + ")";
      k.on.forEach(function (p) { c.fillRect(x + (p[0] + 1) * u, y + (p[1] + 1) * u, u + .3, u + .3); });
    }
    var f = shareFigs(S), ag = d.agents.filter(function (a) { return !a.is_human; }).sort(function (a, b) { return b.last_seen - a.last_seen; }), since = S.since ? L('since') + " " + new Date(S.since * 1000).toLocaleDateString(lang(), { year: "numeric", month: "short", day: "numeric" }) : "";
    box(0, 0, W, H, 0, tok("surface"));
    if (v) {
      idc(S.name, S.name, 90, SAFE_TOP + 40, 150); var fs = fit(S.name, 84, 900); text(S.name, 90, SAFE_TOP + 330, fs, 700, tok("ink")); if (since) text(since, 90, SAFE_TOP + 390, 34, 500, tok("muted"));
      ag.slice(0, ag.length > 7 ? 6 : 7).forEach(function (a, i) { idc(a.name, a.human, 90 + i * 130, SAFE_TOP + 470, 110); });
      if (S.total) { box(90, SAFE_TOP + 610, 900, 14, 7, tok("hover")); box(90, SAFE_TOP + 610, 900 * S.integrated / S.total, 14, 7, tok("accent-line")); }
      if (ag.length > 7) { box(90 + 6 * 130, SAFE_TOP + 470, 110, 110, 18, tok("hover")); text("+" + (ag.length - 6), 90 + 6 * 130 + 55, SAFE_TOP + 540, 36, 600, tok("ink-2"), null, "center"); }
      f.forEach(function (x, i) { var y = SAFE_TOP + 760 + i * 170; text(x[0], 90, y, 104, 700, tok("ink")); text(x[1], 90, y + 44, 30, 500, tok("muted")); });
      if (S.total) text(Math.round(100 * S.integrated / S.total) + "%", W - 90, SAFE_TOP + 130, 96, 700, tok("accent-ink"), null, "right");
    } else {
      idc(S.name, S.name, 64, 64, 88); var fs2 = fit(S.name, 56, 640); text(S.name, 176, 118, fs2, 700, tok("ink")); if (since) text(since, 176, 158, 24, 500, tok("muted"));
      if (S.total) { text(Math.round(100 * S.integrated / S.total) + "%", W - 64, 118, 84, 700, tok("accent-ink"), null, "right"); text(T("Integrated"), W - 64, 158, 24, 500, tok("muted"), null, "right"); box(W - 364, 178, 300, 8, 4, tok("hover")); box(W - 364, 178, 300 * S.integrated / S.total, 8, 4, tok("accent-line")); }
      var px = 64; f.forEach(function (x) { text(x[0], px, 340, 64, 700, tok("ink")); text(x[1], px, 378, 22, 500, tok("muted")); c.font = "700 64px " + sans; var w1 = c.measureText(x[0]).width; c.font = "500 22px " + sans; px += Math.max(w1, c.measureText(x[1]).width) + 72; });
      ag.slice(0, 16).forEach(function (a, i) { idc(a.name, a.human, 64 + i * 64, 470, 52); });
      if (ag.length > 16) text("+" + (ag.length - 16), 64 + 16 * 64, 508, 26, 600, tok("muted"));
    }
    // The kit's credit: a very small mark and name in a corner, low contrast.
    var cx = W - (v ? 250 : 190), cy = v ? H - SAFE_BOTTOM - 50 : H - 44;
    c.globalAlpha = .55; idc("UPIIXIA Agentic Kit", "UPIIXIA", cx, cy, 14); text("UPIIXIA Agentic Kit", cx + 22, cy + 12, 12, 500, tok("muted"), mono); c.globalAlpha = 1;
    return f;
  }
  var shareEl = document.getElementById("share"), shareOpener = null;
  function shareEnv() {
    var f = null, a = document.createElement("a");
    try { f = [new File([new Uint8Array(1)], "card.png", { type: "image/png" })]; } catch (e) {}
    return { nav: window.navigator || {}, secure: window.isSecureContext === true, coarse: !!(window.matchMedia && matchMedia("(pointer: coarse)").matches), anchorDownload: "download" in a, clipboardItem: typeof window.ClipboardItem === "function", files: f, Blob: window.Blob, File: window.File, ClipboardItem: window.ClipboardItem };
  }
  function say(code) {
    return { "copy": L('Could not copy the image. Press and hold it to save it.'), "copy-dl": L('Could not copy the image. Use Download PNG, or press and hold the image.'),
      "share": L('Could not share the image. Press and hold it to save it.'), "share-dl": L('Could not share the image. Use Download PNG, or press and hold the image.'),
      "download": L('The browser did not save the file. Press and hold the image to save it.') }[code];
  }
  function openShare() {
    var figs = h("dl", { "class": "kv", style: "margin-top:12px" }), msg = h("p", { "class": "muted", role: "status", style: "margin:8px 0 0;min-height:20px" }), cvs = [], blocks = [], sw = h("div", { "class": "fsw", role: "group", "aria-label": L('Format') }), env = shareEnv(), caps = shareCaps(env), inner = h("div"), failed = false;
    shareOpener = document.activeElement;
    function name(fmt) { return D.repo.replace(/[^\w.-]+/g, "-") + (fmt === "v" ? "-story" : "") + ".png"; }
    function refuse(action, err) { var c = shareRefusal(action, caps, err); msg.textContent = c ? say(c) : ""; }
    function block(fmt, title) {
      var cv = h("canvas"), img = h("img", { "class": "share-img" + (fmt === "v" ? " v" : ""), alt: title, width: fmt === "v" ? 1080 : 1200, height: fmt === "v" ? 1920 : 630 }), acts = [];
      cvs.push([cv, fmt, img]);
      if (caps.share) acts.push(h("button", { "class": "chip", type: "button", text: L('Share'), on: function () {
        try { shareImage(env, pngBytes(img.src), name(fmt), D.repo).then(function () { msg.textContent = ""; }, function (e) { refuse("share", e); }); } catch (e) { refuse("share", e); }
      } }));
      if (caps.copy) acts.push(h("button", { "class": "chip", type: "button", text: L('Copy image'), on: function () {
        try { copyImage(env, pngBytes(img.src)).then(function () { msg.textContent = L('Copied to the clipboard'); }, function () { refuse("copy"); }); } catch (e) { refuse("copy"); }
      } }));
      if (caps.download) acts.push(h("button", { "class": "chip", type: "button", text: L('Download PNG'), on: function () {
        try { var a = h("a", { href: img.src, download: name(fmt) }); document.body.appendChild(a); a.click(); a.remove(); msg.textContent = ""; } catch (e) { refuse("download"); }
      } }));
      var el = h("div", { "class": "sc", hidden: fmt === "v" ? "" : null }, [img, h("p", { "class": "muted hold", text: L('Press and hold the image to save or share it (right-click on a computer).') }), h("div", { "class": "chips acts", style: "margin-top:8px" }, acts)]);
      blocks.push([fmt, el]);
      var pick = h("button", { "class": "chip", type: "button", "aria-pressed": fmt === "h" ? "true" : "false", text: title, on: function () {
        blocks.forEach(function (x) { x[1].hidden = x[0] !== fmt; }); Array.prototype.forEach.call(sw.children, function (c) { c.setAttribute("aria-pressed", c === pick ? "true" : "false"); }); msg.textContent = "";
      } });
      sw.appendChild(pick);
      return el;
    }
    // The canvas only draws, off the page; the PNG is exported once and is the image's source, the download's link and (decoded) the copy and the shared file.
    function draw() {
      if (failed) return;
      var f = [], bad = null;
      cvs.forEach(function (x) {
        if (bad) return;
        try { f = drawCard(x[0], D, x[1]); } catch (e) { bad = "draw:" + (e && e.message); return; }
        var r = exportCard(x[0], x[1] === "v" ? 1080 : 1200, x[1] === "v" ? 1920 : 630); x[0].width = x[0].height = 0;
        if (r.error) bad = r.error; else x[2].src = r.url;
      });
      if (bad) {
        failed = true; ERRORS.push("share-export:" + bad); if (window.console) console.error("uak dash: share export", bad);
        inner.innerHTML = ""; inner.appendChild(h("p", { role: "status", text: L('The image could not be made on this device. Reload the page and try again, or take a screenshot of it.') })); return;
      }
      figs.innerHTML = ""; f.forEach(function (x) { figs.appendChild(h("dt", { text: x[1] })); figs.appendChild(h("dd", { style: "margin:0" }, [h("b", { text: x[0] })])); });
    }
    shareEl.innerHTML = "";
    var bh = block("h", "1200 x 630"), bv = block("v", L('Story') + " 1080 x 1920");
    [sw, h("div", { "class": "scs" }, [bh, bv]), msg, figs].forEach(function (c) { inner.appendChild(c); });
    shareEl.appendChild(h("div", { "class": "pad" }, [h("div", { "class": "bh" }, [h("h2", { id: "share-t", text: L('Share') }), h("button", { "class": "st-x", type: "button", "aria-label": L('Close'), style: "margin:0 0 0 auto", on: function () { shareEl.close(); } }, [icon(I.x)])]), inner]));
    draw(); if (document.fonts && document.fonts.load) document.fonts.load("700 20px Inter").then(function () { if (shareEl.firstChild) draw(); }, function () {});
    if (shareEl.showModal) shareEl.showModal(); else shareEl.setAttribute("open", "");
  }
  // Closing releases the two PNGs (about a megabyte of base64 each) held by the images.
  // The close event runs after the dialog closed, in a task of its own: a dialog opened again before it (a close and a click in
  // one task) is not emptied (Linux CI with a browser, run 45669137198).
  shareEl.addEventListener("close", function () { if (shareEl.open) return; shareEl.innerHTML = ""; try { if (shareOpener && shareOpener.focus) shareOpener.focus(); } catch (e) {} shareOpener = null; });
  shareEl.addEventListener("click", function (e) { if (e.target === shareEl) shareEl.close(); });
