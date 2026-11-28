  storyEl.addEventListener("click", function (e) { if (e.target === storyEl) closeStory(); });   // a click on the backdrop
  storyEl.addEventListener("cancel", function (e) { e.preventDefault(); closeStory(); });         // Escape
  storyEl.addEventListener("close", function () { storyId = ""; });
  var tip = document.getElementById("tip");
  document.addEventListener("mouseover", function (e) {
    var el = e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!el) { tip.className = ""; return; }
    tip.textContent = el.getAttribute("data-tip"); tip.className = "on";
  });
  document.addEventListener("mousemove", function (e) {
    if (!tip.className) return;
    var x = e.clientX + 12, y = e.clientY + 14, w = tip.offsetWidth, hh = tip.offsetHeight;
    if (x + w > window.innerWidth - 8) x = e.clientX - w - 12;
    if (y + hh > window.innerHeight - 8) y = e.clientY - hh - 12;
    tip.style.transform = "translate(" + x + "px," + y + "px)";
  });
  document.addEventListener("scroll", function () { tip.className = ""; }, true);

  mountLanguage();
  (function () { var tb = document.getElementById("theme-box"); function mt() { tb.innerHTML = ""; tb.appendChild(listbox([["", T("Auto")], ["light", T("Light")], ["dark", T("Dark")]], UAKLook.get().theme === "auto" ? "" : UAKLook.get().theme, function (v) { UAKLook.set({ theme: v }); }, T("Theme"))); } mt(); window.addEventListener("uak:language", mt); })();
  render();
  setInterval(fresh, 5000);
  // A page that outlived a newer one (the file was rewritten, the tab kept the old copy) reloads itself once.
  function newerPage() {
    var m = document.querySelector('meta[name="uak-page"]'), mine = m ? m.content : "", theirs = window.UAK_DATA && window.UAK_DATA.page, stored = "";
    try { stored = sessionStorage.getItem("uak-page-tried") || ""; } catch (e) {}
    var plan = reloadPlan(mine, theirs, stored, location.search);
    NEWER = plan === "notice";
    if (plan !== "reload") return false;
    try { sessionStorage.setItem("uak-page-tried", theirs); } catch (e) {}
    location.href = location.pathname + "?uak=" + theirs + (location.hash || ""); return true;
  }
  function reload() {
    var s = document.createElement("script"); s.src = "data.js?t=" + Date.now();
    s.onload = function () { if (newerPage()) return; if (window.UAK_DATA && window.UAK_DATA.generated !== lastGen) render(); else fresh(); s.remove(); };
    s.onerror = function () { s.remove(); };
    document.body.appendChild(s);
  }
  if (!window.UAK_EMBEDDED) setInterval(reload, 1000 * Math.max(5, (window.UAK_DATA && window.UAK_DATA.refresh) || 20));
  document.addEventListener("uak:state", function () { if (window.UAK_DASH_LOOK) UAKLook.set(window.UAK_DASH_LOOK, false); if (window.UAKWorkspace && window.UAK_DASH_LANGUAGE) UAKWorkspace.setLanguage(window.UAK_DASH_LANGUAGE); else render(); });
  window.addEventListener("uak:language", function () { render(); if(window.UAKWorkspace){UAKWorkspace.apply(document.body);mountLanguage();} reportSize(); });
  // A hook for the tests: draw one tab from the given data (test_dashboard_truth drives it under node with a stub document).
  window.UAK_TEST_RENDER = function (tab, data, extra) { window.UAK_DATA = data; ui.tab = tab; for (var k in extra || {}) ui[k] = extra[k]; render(); return document.getElementById("view"); };
  function reportSize() { if(window.UAK_EMBEDDED)window.parent.postMessage({type:"uak:dashboard-size",height:document.documentElement.scrollHeight},"*"); }
  if(window.UAKWorkspace)UAKWorkspace.start(document.body);
  if(window.UAK_EMBEDDED){document.querySelector(".head").hidden=true;document.getElementById("embedded-title").hidden=false;}

})();
