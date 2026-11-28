        function tickPlanProgress() {
          if (!planClock || gone) return;
          var seconds = Math.max(0, Math.floor((Date.now() - planClock.at) / 1000)),
            time = Math.floor(seconds / 60) + ":" + (seconds % 60 < 10 ? "0" : "") + (seconds % 60);
          el("plan-progress").hidden = false;
          el("plan-progress").textContent = planClock.last
            ? UAKWorkspace.format("Planning for {time}. Last output: {line}", { time: time, line: planClock.last })
            : UAKWorkspace.format("Planning for {time}. Waiting for the first output.", { time: time });
        }
        setInterval(tickPlanProgress, 1000);
        function ideaFields() {
          var fields = {
            idea: el("idea-text").value,
            audience: el("idea-audience").value,
            event_length: el("idea-length").value,
            team_size: parseInt(el("idea-team").value, 10),
          };
          fields[planView && planView.mode === "marathon" ? "goal" : "rubric"] = el("idea-goal").value;
          if (!el("idea-overwrite-row").hidden) fields.overwrite = el("idea-overwrite").checked;
          return fields;
        }
        el("idea-form").onsubmit = function (event) {
          event.preventDefault();
          if (!checkFields(this)) return;
          action(el("idea-save"), async function () {
            try {
              await api("idea", ideaFields());
            } catch (e) {
              if (e.status === 409) {
                el("idea-overwrite-row").hidden = false;
                el("idea-overwrite").focus();
              }
              throw e;
            }
            el("idea-overwrite-row").hidden = true;
            el("idea-overwrite").checked = false;
            dropDrafts(["idea-text", "idea-audience", "idea-goal", "idea-length", "idea-team"]);
            await loadPlan();
            el("idea-status").textContent = UAKWorkspace.t("IDEA.md is saved. Next: create the plan.");
          });
        };
        function startPlanning(button, note) {
          action(button, async function () {
            var body = { harness: selectedPlanner() };
            if (note) body.note = note;
            await api("plan", body);
            el("approve-confirm").hidden = true;
            await refresh();
          });
        }
        el("plan-create").onclick = function () {
          startPlanning(this, "");
        };
        el("plan-change").onclick = function () {
          var note = el("plan-note").value.trim();
          if (!note) {
            error("Write what should change in the plan first.");
            el("plan-note").focus();
            return;
          }
          startPlanning(this, note);
        };
        // The typed approval says exactly what to type (UI-007): the folder name as placeholder, and under the disabled
        // button "Type NAME to enable publishing".
        function approveHint() {
          var project = (planView && planView.project) || "";
          el("approve-hint").textContent = UAKWorkspace.format("Type {name} to enable publishing", { name: project });
          el("approve-hint").hidden = !el("approve-publish").disabled;
        }
        el("plan-approve").onclick = function () {
          el("approve-confirm").hidden = false;
          el("approve-name").value = "";
          el("approve-name").placeholder = (planView && planView.project) || "";
          el("approve-publish").disabled = true;
          approveHint();
          el("approve-name").focus();
        };
        el("approve-name").oninput = function () {
          el("approve-publish").disabled = !planView || this.value !== planView.project;
          approveHint();
        };
        el("approve-cancel").onclick = function () {
          el("approve-confirm").hidden = true;
          el("plan-approve").focus();
        };
        el("approve-publish").onclick = function () {
          var typed = el("approve-name").value;
          action(this, async function () {
            await api("plan/approve", { confirm: typed, digest: planView.digest });
            el("approve-confirm").hidden = true;
            el("plan-note").value = "";
            await refresh();
          });
        };
        // The journey (UI-007): where the person is, from the server's state only; it stays visible above every view.
        function journeyStep(data) {
          if (!data || !data.installed) return "install";
          var resume = data.resume || {};
          // UI-019: before a check finishes, the step the project's Git shows; never Plan for an approved plan.
          if (!data.checked && resume.step && resume.step !== "install") return resume.step;
          if (data.ready || data.team) return latestDashboard && (latestDashboard.tasks || []).some(function (t) { return t.state !== "AVAILABLE"; }) ? "progress" : "team";
          if (resume.plan_approved !== true &&
              (["planning", "planned", "approving"].indexOf(data.phase) >= 0 || (data.guidance || {}).action === "plan")) return "plan";
          return "prepare";
        }
        // Whose identity signs (UI-007): the project's Git name/email and gh's login, as the server parsed them. On someone
        // else's computer they are not the person's: say so before anything is published under that name.
        // UI-012: each account is checked on its own (r4: "ana" matched the Git name and hid that the pull requests
        // opened as someone else), and names match without case or accents (José = jose, Ana García = anagarcia).
        // Words also break where camelCase or digits start (AnaLopez, ana_garcia92 → ana lopez, ana garcia 92).
        function plainWords(text) {
          return String(text || "")
            .normalize("NFD")
            .replace(new RegExp("\\p{M}", "gu"), "")
            .replace(new RegExp("(\\p{Ll})(\\p{Lu})", "gu"), "$1 $2")
            .replace(new RegExp("(\\p{Lu})(\\p{Lu}\\p{Ll})", "gu"), "$1 $2")
            .replace(new RegExp("(\\p{L})(\\p{N})", "gu"), "$1 $2")
            .replace(new RegExp("(\\p{N})(\\p{L})", "gu"), "$1 $2")
            .toLowerCase()
            .split(new RegExp("[^\\p{L}\\p{N}]+", "u"))
            .filter(Boolean);
        }
        // True when an account word STARTS with the person's whole name, letters or digits after it allowed: dylan
        // = DylanMCDS, ana = analopez, luis = luisg, and a name of several words may run across the account's words
        // (ana-garcia = "Ana García", anagarcia, ana_garcia92). The name inside a word (ana in mariana, banana) or one
        // shared word of a longer name (maria-garcia vs Juan Garcia, mariana vs Ana Lopez) is not enough (reviews of
        // 4af5789 and 3bc4018: a whole-word-only match warned on people's own accounts).
        function sameName(words, human) {
          var me = plainWords(human).join("");
          if (!me) return false;
          for (var i = 0; i < words.length; i++) {
            var w = "";
            for (var j = i; j < words.length; j++) {
              w += words[j];
              if (w.indexOf(me) === 0) return true; // the name, then anything: DylanMCDS, ana_garcia92
              if (me.indexOf(w) !== 0) break; // whole words of the name so far ("ana" of ana-garcia), or not this run
            }
          }
          return false;
        }
        // Which account looks like someone else's: {git, gh}. An empty account (no gh login) is nobody's, never someone
        // else's; without the person's name nothing can be compared. The Git name and the email are each a whole.
        function sharedIdentity(ident, human) {
          ident = ident || {};
          if (!plainWords(human).length) return { git: false, gh: false };
          var name = plainWords(ident.git_name),
            mail = plainWords(String(ident.git_email || "").split("@")[0]),
            login = plainWords(ident.gh_login);
          return {
            git: !!(name.length || mail.length) && !(sameName(name, human) || sameName(mail, human)),
            gh: !!login.length && !sameName(login, human),
          };
        }
        // The notice: who signs the commits and opens the pull requests, then which account belongs to someone else.
        function identityWarning(ident, human) {
          ident = ident || {};
          var git = (ident.git_name || "?") + (ident.git_email ? " <" + ident.git_email + ">" : ""),
            gh = ident.gh_login ? "@" + ident.gh_login : UAKWorkspace.t("nobody (gh is not signed in)"),
            text = UAKWorkspace.format("Commits will be signed as {git} and pull requests opened as {gh}.", { git: git, gh: gh }),
            unnamed = !human,
            other = sharedIdentity(ident, human);
          if (unnamed)
            text += " " + UAKWorkspace.t("Tell setup your name (Your name, below) so it can check that this identity is yours.");
          else if (other.git && other.gh)
            text += " " + UAKWorkspace.t("This looks like someone else's identity. If this is not your computer, set your own before publishing: git config user.name and user.email, and gh auth login.");
          else if (other.gh)
            text += " " + UAKWorkspace.format("The GitHub login {gh} does not match your name, so it looks like someone else's account: sign in as yourself with gh auth login before publishing.", { gh: gh });
          else if (other.git)
            text += " " + UAKWorkspace.format("The Git name and email {git} do not match your name, so they look like someone else's: set your own with git config user.name and user.email before publishing.", { git: git });
          return { text: text, git: unnamed || other.git, gh: unnamed || other.gh };
        }
        function drawIdentity(data) {
          var ident = data.identity || {},
            box = el("identity-warning");
          if (!ident.git_name && !ident.gh_login) {
            box.hidden = true;
            return;
          }
          // With no name the notice asks for it (review of 949eca1).
          var unnamed = !data.human,
            shown = identityWarning(ident, unnamed ? "" : data.human);
          box.textContent = shown.text;
          box.classList.toggle("error", !unnamed && (shown.git || shown.gh));
          box.hidden = false;
        }

        // A finished operation moves the person to the heading of the step that comes next (amendment 8).
        var identityTries = 0;
        function drawDashboard(data) {
          latestDashboard = data;
          drawJourney();
          el("dashboard-project").textContent = state.target || "";
          // The notice under the title says only what needs saying (a warning); it never repeats the heading.
          var warning = data.warning ? UAKWorkspace.t(data.warning) : "";
          el("dashboard-status").textContent = warning;
          el("dashboard-status").hidden = !warning;
          el("dashboard-status").classList.remove("error");
          el("beginner-dashboard").classList.toggle("stale", !!(data.stale && data.checking));
          drawLiveUrl(data.live_url);
          drawDashboardWin(state);
          var p = data.progress,
            states = p.states;
          el("simple-completed").textContent =
            (states.INTEGRATED || 0) + " / " + p.total;
          el("simple-working").textContent = states.CLAIMED || 0;
          el("simple-review").textContent = states.REVIEW || 0;
          var frozen =
            !!data.freeze &&
            data.freeze <=
              Math.max(data.generated, Math.floor(Date.now() / 1000));
          el("dashboard-freeze").hidden = !data.freeze;
          el("dashboard-freeze").classList.toggle("error", frozen);
          el("dashboard-freeze").textContent =
            UAKWorkspace.t(
              frozen
                ? "Project changes are frozen. A human must authorize any new work."
                : "A project freeze is scheduled. Check the deadline before taking new work.",
            ) +
            (data.freeze
              ? " · " +
                new Date(data.freeze * 1000).toLocaleString(
                  UAKWorkspace.language(),
                )
              : "");
          // The next step comes from the server, which derives it from `uak start` (the same gate as
          // Configuration), so this view never offers work that the gate still blocks.
          drawNext(data.guidance || state.guidance || {});
          el("simple-tasks").replaceChildren();
          // UI-023 (B-12, B-13): one row reads in the singular, a task waiting on its dependencies is not
          // available, and an approved review says so.
          var ROW_LABEL = {
            AVAILABLE: "available",
            CLAIMED: "in progress",
            BLOCKED: "blocked",
            REVIEW: "in review",
            INTEGRATED: "integrated",
          };
          data.tasks.slice(0, 8).forEach(function (task) {
            var row = document.createElement("li"),
              title = document.createElement("span"),
              status = document.createElement("span"),
              waits = (task.waiting_on || []).length;
            title.dataset.noI18n = "";
            title.textContent = task.id + " · " + plainText(task.title);
            status.textContent = UAKWorkspace.t(
              waits
                ? "waiting on dependencies"
                : task.approved
                  ? "approved"
                  : ROW_LABEL[task.state] || task.state,
            );
            if (waits) status.title = UAKWorkspace.t("waits on ") + task.waiting_on.join(", ");
            row.append(title, status);
            el("simple-tasks").append(row);
          });
          var advanced = document.body.dataset.profile === "advanced";
          // Advanced keeps the same next step as Beginner (its guidance), above the dashboard frame.
          drawAdvancedNext(data.guidance || state.guidance || {});
          if (teamFor !== [state.target, state.human, state.ready, state.team].join(":")) {
            teamFor = [state.target, state.human, state.ready, state.team].join(":");
            loadTeam();
          }
          el("beginner-dashboard").hidden = advanced;
          el("dashboard-frame").hidden = !advanced;
          if (advanced && !el("dashboard-frame").getAttribute("src"))
            el("dashboard-frame").src = "/dashboard";
          sendDashboard();
        }
        var dashboardTries = 0;
        // UAK-156: the dashboard asks again after 20 s, then 60 s, then 120 s while nothing changes, and not at all
        // while the page is hidden (it asks once when the page is shown again).
        var DASH_BACKOFF = [20000, 60000, 120000];
        function dashboardDelay(unchanged) {
          return DASH_BACKOFF[Math.min(unchanged, DASH_BACKOFF.length - 1)];
        }
        function scheduleDashboard(soon) {
          if (dashboardTimer) clearTimeout(dashboardTimer);
          dashboardTimer = null;
          if (gone || document.hidden || currentSection !== "dashboard") return;
          dashboardTimer = setTimeout(loadDashboard, soon ? 1500 : dashboardDelay(dashboardUnchanged));
        }
        function dashboardChanged(data) {
          var signature = JSON.stringify([data.progress, data.counts, (data.tasks || []).map(function (t) {
            return t.id + ":" + t.status;
          }), (data.agents || []).length, (data.messages || []).length, data.connection, data.stale, data.source]);
          var changed = signature !== dashboardSignature;
          dashboardSignature = signature;
          dashboardUnchanged = changed ? 0 : dashboardUnchanged + 1;
        }
        async function loadDashboard() {
          if (gone) return;
          // A request while one is in flight (e.g. a check just finished) loads again right after it.
          if (dashboardLoading) {
            dashboardAgain = true;
            return;
          }
          if (dashboardTimer) clearTimeout(dashboardTimer);
          // Opened before the first status arrived (a fast click after load): ask the server, not the empty page state.
          if (!state.target) {
            try {
              state = await api("status");
            } catch (e) {}
          }
          if (!state.target || state.phase === "welcome") {
            el("dashboard-status").hidden = false;
            el("dashboard-status").textContent = UAKWorkspace.t(
              "Choose a project to see its dashboard.",
            );
            el("dashboard-choose-project").hidden = false;
            return;
          }
          el("dashboard-choose-project").hidden = true;
          el("dashboard-status").hidden = false;
            el("dashboard-status").textContent = UAKWorkspace.t(
            "Loading your project dashboard…",
          );
          el("refresh-dashboard").disabled = true;
          dashboardLoading = true;
          var target = state.target,
            soon = false;
          try {
            var data = await api("dashboard");
            if (state.target === target) drawDashboard(data);
            dashboardChanged(data);
            dashboardTries = 0;
          } catch (e) {
            if (e.gone) {
              el("dashboard-status").hidden = true; // the banner says it once
              return;
            }
            // An operation that just ended may still be finishing (409): ask again shortly, a few times (UI-019).
            soon = e.status === 409 && dashboardTries < 4;
            if (soon) dashboardTries += 1;
            el("dashboard-status").hidden = false;
            // A check that is still running (409) ends by loading the dashboard again (render).
            el("dashboard-status").textContent = UAKWorkspace.t(e.status === 409 ? "Checking your next steps" : e.message);
          } finally {
            dashboardLoading = false;
            el("refresh-dashboard").disabled = false;
            if (dashboardAgain && currentSection === "dashboard") {
              dashboardAgain = false;
              loadDashboard();
            } else scheduleDashboard(soon);
          }
        }
// ---- UAK-159: the ten screens of the wizard. One screen is shown at a time; its step is in the address
        // (/?step=rules), so reload stays on it and the browser's Back and Forward move between steps.
        // A check the page is about to start (or has just asked for) already blocks the buttons that need the project idle.
        function waitingPhase() {
          if (isBusy(state.phase)) return state.phase;
          return checkStarting || shouldAutoCheck(state) ? "checking" : state.phase;
        }
        function openSection(section) {
          var next = screenFor(state), after = next === "start" || next === "dashboard";
          if (section === "dashboard") {
            if (currentSection !== "dashboard") show(after ? next : "start", false);
          } else if (currentSection === "dashboard") show(after ? "rules" : next, false);
          if (section === "setup" && dashboardTimer) clearTimeout(dashboardTimer);
          document.querySelector(".skip").href = "#content";
        }
        function show(name, focus, how) {
          if (SCREENS.indexOf(name) < 0) name = "project";
          var was = currentScreen;
          currentScreen = name;
          currentSection = name === "dashboard" || name === "start" ? "dashboard" : "setup";
          if (state.target && name !== "closed") writeSaved(state.target, { section: currentSection });
          SCREENS.forEach(function (n) {
            if (n === name) el("screen-" + n).setAttribute("data-on", ""); else el("screen-" + n).removeAttribute("data-on");
          });
          el("error").hidden = true;
          document.title = UAKWorkspace.t(TITLE[name] || "") + " · UPIIXIA";
          if (how !== "pop" && was !== name) {
            try { history[!was || how === "replace" ? "replaceState" : "pushState"]({ screen: name }, "", "/?step=" + name); } catch (e) {}
          }
          drawJourney();
          drawScreens(state);
          syncRunningControls();
          if (name === "start" || name === "people") loadTeam();
          if (startTimer) { clearInterval(startTimer); startTimer = null; }
          // The first claim of an agent shows without a reload: the team view reads the claims again every 20 s.
          if (name === "start") startTimer = setInterval(function () { if (!document.hidden && !gone) loadTeam().then(function () { drawStart(state); }); }, 20000);
          if (name === "dashboard" && !dashboardLoading) loadDashboard();
          if (focus !== false) {
            var heading = el("screen-" + name).querySelector("h1");
            if (heading) heading.focus({ preventScroll: true });
            window.scrollTo(0, 0);
          }
        }
        function drawJourney() {
          if (currentScreen === "closed") {
            Array.from(el("journey").querySelectorAll("li")).forEach(function (li) { li.removeAttribute("aria-current"); li.classList.remove("done"); });
            return;
          }
          var here = RAIL[currentScreen] || "project", seen = false, sprint = modeOf(state) === "sprint", shown = [], count = 0, at = 0;
          Array.from(el("journey").querySelectorAll("li")).forEach(function (li) {
            var mine = li.dataset.step === here;
            li.hidden = li.dataset.step === "schedule" && !sprint;
            if (!li.hidden) { count += 1; if (mine) at = count; }
            if (mine) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
            li.classList.toggle("done", !seen && !mine);
            if (mine) seen = true;
          });
          el("journey").setAttribute("aria-label", UAKWorkspace.format("Step {n} of {total}", { n: at, total: count }));
        }
        // A cell reads in the page's language: its words only, spaces and paths as they are ("was yes" says what it was).
        function tr(text) {
          var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(String(text)), was = /^was (.+)$/.exec(m[2]);
          return m[1] + (was ? UAKWorkspace.format("was {value}", { value: UAKWorkspace.t(was[1]) }) : UAKWorkspace.t(m[2])) + m[3];
        }
        function setRows(id, rows) {
          var box = el(id);
          box.replaceChildren();
          rows.forEach(function (row) {
            var line = document.createElement("div"), a = document.createElement("span"), b = document.createElement("span");
            line.className = "row " + (row[0] || "");
            a.textContent = tr(row[1]); b.textContent = tr(row[2] || "");
            line.dataset.noI18n = "";
            line.append(a, b);
            box.append(line);
          });
        }
        function setFigs(id, figs) {
          var box = el(id);
          box.replaceChildren();
          figs.forEach(function (f) {
            var cell = document.createElement("span"), n = document.createElement("b");
            n.textContent = f[0];
            cell.append(n, document.createTextNode(UAKWorkspace.t(f[1])));
            box.append(cell);
          });
        }
        function drawWindow(name, title, rows, figs) {
          el("win-" + name + "-title").textContent = title;
          setRows("win-" + name + "-body", rows);
          setFigs("win-" + name + "-foot", figs);
        }
        function folderName(path) { return String(path || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "project"; }
        function chosenTools() {
          return Array.from(document.querySelectorAll("input[name=harness]:checked")).map(function (i) { return i.value; });
        }
        function kitFiles(data) {
          var files = ((data.detected || {}).kit_files) || {}, total = files.base || 0, tools = chosenTools();
          tools.forEach(function (t) { total += files["." + t] || 0; });
          return { base: files.base || 0, total: total, files: files, tools: tools };
        }
        // The proposal: facts only, from the server; the sentence is composed here so it can be translated.
        function proposal(d) {
          if (!d || !d.repo) return null;
          if (d.repo === "new") return { mode: "sprint", reason: UAKWorkspace.t("A new repository with no history: a hackathon or prototype is the usual start.") };
          var n = d.commits || 0;
          if (n >= 30 || d.ci)
            return { mode: "marathon", reason: d.ci
              ? UAKWorkspace.format("The repository already has {n} commits and {ci}: a product with real users.", { n: n, ci: d.ci })
              : UAKWorkspace.format("The repository already has {n} commits: a product with real users.", { n: n }) };
          return { mode: "sprint", reason: UAKWorkspace.format("A small repository ({n} commits) with no CI: a hackathon or prototype fits.", { n: n }) };
        }
        function foundRow(label, value, code) {
          var li = document.createElement("li"), k = document.createElement("span"), v = document.createElement("span");
          k.className = "k"; v.className = "v";
          k.textContent = UAKWorkspace.t(label);
          if (code) { var c = document.createElement("code"); c.textContent = value; c.dataset.noI18n = ""; v.append(c); } else v.textContent = value;
          li.append(k, v);
          return li;
        }
