        function serverBack(data) {
          if (!gone) return;
          gone = false;
          probeTries = 0;
          clearTimeout(probeTimer);
          probeTimer = null;
          el("server-gone").hidden = true;
          render(data);
          if (isBusy(data.phase)) refresh();
        }
        el("server-gone-retry").onclick = function () {
          probe();
        };
        document.addEventListener("visibilitychange", function () {
          if (gone && !document.hidden && !probeTimer) probe();
          // UAK-156: what stopped while the page was hidden starts again, once.
          if (!document.hidden && !gone) {
            api("status").catch(function () {}); // this page says it is here (another tab may have closed meanwhile)
            if (currentSection === "dashboard" && !dashboardTimer) loadDashboard();
            if (!timer && isBusy(state.phase)) refresh();
          }
        });
        // UAK-156: a page that closes says so, so setup can end by itself (a reload comes back within seconds and
        // keeps it; an action that runs keeps it too). The session may already be gone: nothing to do then.
        window.addEventListener("pagehide", function (event) {
          if (gone || !token) return;
          try {
            fetch("/api/closing", {
              method: "POST",
              keepalive: true,
              headers: { "X-UAK-Token": token, "X-UAK-Page": pageId, "Content-Type": "application/json" },
              body: "{}",
            }).catch(function () {});
          } catch (e) {}
        });
        window.addEventListener("pageshow", function (event) {
          if (event.persisted && !gone) refresh();
        });
        // UAK-159: which screen a project is on (pure, so the resume test can run it)
        var SCREENS = ["project", "install", "unblock", "update", "rules", "people", "schedule", "publish", "plan", "start", "dashboard", "closed"];
        var ORDER = ["project", "rules", "people", "schedule", "publish", "plan", "start", "dashboard"];
        // The names are `uak start --steps`' own; the nodes of the top line and the step rail are this one list.
        var RAIL = { project: "project", install: "project", unblock: "project", update: "project", rules: "rules", people: "people", schedule: "schedule", publish: "publish", plan: "plan", start: "start", dashboard: "start" };
        var TITLE = { project: "Check what we found in this project", install: "Install the kit into this project", unblock: "Fix this before you continue", update: "Update the kit in this project",
          rules: "Confirm how your team will work", people: "Say who is on your team", schedule: "Set the event schedule", publish: "Publish the kit to main",
          plan: "Describe your idea and approve the plan", start: "Start your agents", dashboard: "Follow your project", closed: "The wizard is closed" };
        var currentScreen = "", formOpen = false, modePicked = false, stackPicked = false, rulesDirty = false, closedWizard = false,
          checkStarting = false, busySince = 0, busyTimer = null, startTimer = null, updateSkipped = false;
        function modeOf(data) {
          var chosen = null;
          try { chosen = document.querySelector("input[name=mode]:checked"); } catch (e) {}
          return (data.settings || {}).Mode || (chosen && chosen.value) || (typeof choices !== "undefined" && choices.mode) || "";
        }
        function terminalCommand(target) {
          return target
            ? "cd '" + String(target).replace(/'/g, "'\\''") + "' && bash .uak/bin/uak start"
            : "bash path/to/upiixia-agentic-kit/install.sh --wizard";
        }
        // Where the person's project stands decides the screen (evidence only, as `uak start --steps` reads it).
        function screenFor(data, saved) {
          data = data || {};
          saved = saved || readSaved(data.target);
          var resume = data.resume || {}, g = data.guidance || {}, mode = modeOf(data);
          if (!data.installed && !data.can_repair) return data.phase === "installing" ? "install" : "project";
          if (data.phase === "installing") return "install";
          if (!data.installed) return "update";
          if (data.branch && data.branch.wrong) return "unblock";
          if ((data.versions || {}).older && !updateSkipped) return "update";
          // A project that is past the rules (its kit on main, a schedule, an approved plan, a claim) is not asked again.
          var beyond = resume.kit_on_main === true || resume.freeze > 0 || resume.plan_approved === true || (resume.claims || 0) > 0;
          if (!saved.rules && !beyond) return "rules";
          if (!data.human) return "people";
          if (mode === "sprint" && !(resume.freeze > 0)) return "schedule";
          // What the readiness check still needs from a terminal blocks the publishing, not the choices before it.
          if (g.terminal && data.checked && !data.ready) return "unblock";
          if (resume.kit_on_main !== true) return "publish";
          if (resume.plan_approved !== true) return "plan";
          return journeyStep(data) === "progress" || (resume.claims || 0) > 0 ? "dashboard" : "start";
        }
        function allowed(name, data) {
          if (SCREENS.indexOf(name) < 0 || name === "closed") return false;
          if (name === "project") return true;
          if (name === "install") return !!data.target;
          if (name === "schedule") return !!data.installed && modeOf(data) === "sprint";
          return !!data.installed;
        }
        // "dashboard" is the part of the flow after setup (Start and Dashboard); "setup" the part before it.
        // UI-019 resume: end
        function profile(value) {
          document.body.dataset.profile = value;
          el("profile").value = value;
          el("installation-options").open = value === "advanced";
          el("technical-details").open = value === "advanced";
          try {
            localStorage.setItem("uak-profile", value);
          } catch (e) {}
          if (latestDashboard) drawDashboard(latestDashboard);
        }
        var saved = "beginner";
        try {
          saved = localStorage.getItem("uak-profile") || saved;
        } catch (e) {}
        profile(saved === "advanced" ? "advanced" : "beginner");
        el("profile").addEventListener("change", function () {
          profile(this.value);
        });
        UAKWorkspace.start(document.body);
        // Apariencia: theme and palette are the viewer's, kept in this browser (UAKLook, in the head); the dashboard follows.
        UAKLook.onchange(sendDashboard);
        el("language").value = UAKWorkspace.language();
        el("language").onchange = function () {
          UAKWorkspace.setLanguage(this.value);
        };
        // UI-017: the demo video on the welcome screen. Shown only when the server has the four files, whose addresses
        // are set then (a hidden block requests nothing); never started by the page (it waits for the play button,
        // preload none); the captions follow the page's language.
        function showDemo(available) {
          var video = el("demo-video");
          el("demo").hidden = !available;
          el("demo-link").hidden = available;
          if (!available || video.getAttribute("src")) return;
          video.querySelectorAll("track").forEach(function (track) {
            track.src = track.dataset.src;
          });
          video.poster = video.dataset.poster;
          video.src = video.dataset.src;
          demoCaptions();
        }
        function demoCaptions() {
          var tracks = el("demo-video").querySelectorAll("track");
          for (var i = 0; i < tracks.length; i++) {
            var mine = tracks[i].srclang === UAKWorkspace.language();
            tracks[i].default = mine;
            if (tracks[i].track) tracks[i].track.mode = mine ? "showing" : "disabled";
          }
        }
        el("demo-video").addEventListener("error", function () {
          showDemo(false);
        });
        window.addEventListener("uak:language", function () {
          demoCaptions();
          // The heading, the checklist and who signs are drawn in the page's language, not by the body translation.
          if (state.installed || state.can_repair) render(state);
          if (latestDashboard) drawDashboard(latestDashboard);
        });
        el("open-setup").onclick = function () {
          openSection("setup");
        };
        el("open-dashboard").onclick = function () {
          openSection("dashboard");
          loadDashboard();
        };
        el("refresh-dashboard").onclick = loadDashboard;
        el("next-check").onclick = function () {
          action(this, async function () {
            startCheck(false);
            await api("check", {});
            checkRequested = true; // only once the server accepted it
            el("dashboard-status").hidden = false;
            el("dashboard-status").textContent = UAKWorkspace.t(
              "Checking your next steps",
            );
            await refresh();
            return false; // render reports what the check found
          });
        };
        // Start your team (UI-006): the reviewer registration (a human act) and one Copy command per agent, all
        // from /api/team; the commands are built by the server from its own values and shown as text.
        var teamFor = "";
        function copyText(text, status) {
          function done(ok) {
            el(status).textContent = UAKWorkspace.t(
              ok ? "Copied. Paste it where the block says." : "Select the command and copy it.",
            );
          }
          if (navigator.clipboard && navigator.clipboard.writeText)
            navigator.clipboard.writeText(text).then(
              function () { done(true); },
              function () { done(false); },
            );
          else done(false);
        }
        function drawAdvancedNext(guide) {
          guide = teamGuide(guide);
          el("advanced-next").hidden = document.body.dataset.profile !== "advanced" || !guide.title;
          el("advanced-next-heading").textContent = (guide.code ? UAKWorkspace.code(guide.code, guide.values || {}) : UAKWorkspace.gate(UAKWorkspace.t(guide.title || "")));
          el("advanced-next-description").textContent = UAKWorkspace.t(guide.detail || "");
          el("advanced-next-command").textContent = (guide.commands || []).join("\n");
          el("advanced-next-box").hidden = !(guide.commands || []).length;
        }
        // UI-009: the reviewer's state comes from this project's claims (null: could not be read); each person picks
        // which available tool implements and which reviews; claimed tasks stay listed with their resume line.
        var teamView = null;
        function toolLabel(id) {
          return id === "codex" ? "Codex" : "Claude Code";
        }
        function drawRoles(view) {
          var tools = view.tools || [],
            roles = view.roles || {},
            usable = tools.filter(function (t) { return t.available; }),
            missing = tools.filter(function (t) { return !t.available; });
          el("team-roles").hidden = !tools.length;
          ["implement", "review"].forEach(function (role) {
            var box = el("team-" + role + "-options");
            box.replaceChildren();
            usable.forEach(function (tool) {
              var label = document.createElement("label"),
                input = document.createElement("input"),
                name = document.createElement("span");
              input.type = "radio";
              input.name = "team-" + role;
              input.value = tool.id;
              input.checked = roles[role] === tool.id;
              input.disabled = operationBusy();
              input.onchange = function () { pickRole(role, tool.id); };
              name.textContent = tool.label;
              name.dataset.noI18n = "";
              label.append(input, name);
              box.append(label);
            });
          });
          el("team-same-tool").hidden = !roles.same_tool;
          el("team-same-tool-text").textContent = roles.same_tool
            ? UAKWorkspace.format("{tool} does both jobs under two names: {impl} writes the code and {who} reviews it in a separate session.", {
                tool: toolLabel(roles.implement),
                impl: (((view.commands || []).filter(function (c) { return c.id === "implement"; })[0]) || {}).identity || roles.implement + "-" + view.human,
                who: view.reviewer,
              })
            : "";
          el("team-roles-note").hidden = !roles.note;
          el("team-roles-note").textContent = UAKWorkspace.t(roles.note || "");
          el("team-unavailable").hidden = !missing.length;
          el("team-unavailable-list").replaceChildren();
          missing.forEach(function (tool) {
            var li = document.createElement("li");
            li.textContent = tool.label + ": " + UAKWorkspace.t(tool.reason);
            el("team-unavailable-list").append(li);
          });
        }
        function pickRole(role, tool) {
          var roles = (teamView && teamView.roles) || {},
            pick = { implement: roles.implement, review: roles.review };
          pick[role] = tool;
          if (!pick.implement || !pick.review) return;
          action(el("team-roles"), async function () {
            await api("team/roles", pick);
            await loadTeam();
          });
        }
        function drawClaimed(view) {
          var rows = view.claimed || [];
          el("team-claimed-block").hidden = !rows.length;
          el("team-claimed").replaceChildren();
          rows.forEach(function (row) {
            var li = document.createElement("li"),
              line = document.createElement("span");
            line.dataset.noI18n = "";
            line.textContent = row.task + " · " + UAKWorkspace.t({ CLAIMED: "In progress", BLOCKED: "Blocked", REVIEW: "In review" }[row.state] || row.state) + " · " + row.owner;
            li.append(line);
            if (row.resume) {
              var hint = document.createElement("p"),
                box = document.createElement("div"),
                code = document.createElement("code"),
                copy = document.createElement("button");
              hint.className = "hint";
              hint.textContent = UAKWorkspace.format("Reopen your agent for {task}:", { task: row.task });
              box.className = "next-command";
              code.dataset.noI18n = "";
              code.textContent = row.resume;
              copy.type = "button";
              copy.className = "secondary-button";
              copy.textContent = UAKWorkspace.t("Copy");
              copy.setAttribute("aria-label", UAKWorkspace.format("Copy the command for {task}", { task: row.task }));
              copy.onclick = function () { copyText(row.resume, "team-copy-status"); };
              box.append(code, copy);
              li.append(hint, box);
            }
            el("team-claimed").append(li);
          });
        }
