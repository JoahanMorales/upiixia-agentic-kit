/* uak-look:begin (the same script in setup.html and dash.html): theme and palette are the viewer's, kept in this browser only */
(function () {
  var PALS = [["clasico", "Clásico", 213, 71], ["lavanda", "Lavanda", 250, 72], ["cielo", "Cielo", 212, 72], ["menta", "Menta", 164, 55], ["salvia", "Salvia", 128, 28],
    ["durazno", "Durazno", 22, 80], ["rosa", "Rosa", 338, 70], ["arena", "Arena", 42, 45], ["grafito", "Grafito", 230, 0]];
  var root = document.documentElement, state = { theme: "auto", pal: root.getAttribute("data-pal") || "clasico" }, listeners = [];
  var dark = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function known(p) { return PALS.some(function (x) { return x[0] === p; }); }
  function get() { return { theme: state.theme, pal: state.pal }; }
  function paint() {
    root.setAttribute("data-theme", state.theme === "auto" ? (dark && dark.matches ? "dark" : "light") : state.theme);
    root.setAttribute("data-pal", state.pal);
  }
  function sync() {
    var box = document.getElementById("look");
    if (!box) return;
    box.querySelector("select").value = state.theme === "auto" ? "" : state.theme;
    Array.prototype.forEach.call(box.querySelectorAll("[data-pal-set]"), function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-pal-set") === state.pal)); });
  }
  function tell() { listeners.forEach(function (f) { f(get()); }); }
  function set(change, keep) {
    if (change.theme !== undefined) state.theme = change.theme === "light" || change.theme === "dark" ? change.theme : "auto";
    if (known(change.pal)) state.pal = change.pal;
    paint(); sync();
    if (keep !== false) { try { localStorage.setItem("uak-look", JSON.stringify(state)); } catch (e) {} }
    tell();
  }
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem("uak-look") || "null") || { theme: localStorage.getItem("uak-dash-theme") }; } catch (e) {}
  if (saved.theme === "light" || saved.theme === "dark") state.theme = saved.theme;
  if (known(saved.pal)) state.pal = saved.pal;
  paint();
  if (dark && dark.addEventListener) dark.addEventListener("change", function () { if (state.theme === "auto") { paint(); tell(); } });
  function mount() {
    var box = document.getElementById("look"), grid = box && box.querySelector(".pals");
    if (!grid) return;
    PALS.forEach(function (p) {
      var b = document.createElement("button"), dot = document.createElement("i");
      b.type = "button"; b.setAttribute("data-pal-set", p[0]);
      dot.style.setProperty("--h", p[2]); dot.style.setProperty("--sa", p[3] + "%");
      b.append(dot, p[1]); grid.append(b);
      b.addEventListener("click", function () { set({ pal: p[0] }); });
    });
    box.querySelector("select").addEventListener("change", function () { set({ theme: this.value }); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && box.open) { box.open = false; box.querySelector("summary").focus(); } });
    document.addEventListener("click", function (e) { if (box.open && !box.contains(e.target)) box.open = false; });
    sync();
  }
  window.UAKLook = { get: get, set: set, onchange: function (f) { listeners.push(f); } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
})();
/* uak-look:end */
