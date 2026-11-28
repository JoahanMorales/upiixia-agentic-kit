        function drawPrepare(data) {
          var g = data.guidance || {},
            done = stepsDone(data),
            show = !!data.installed && !data.ready && data.phase !== "installing" &&
              (planningVisible(data) || !(done.name && done.schedule && done.publish) ||
                g.action === "schedule" || g.action === "publish");
          el("prepare").hidden = !show;
          ["name-step", "schedule-form", "publish-step"].forEach(function (id) {
            el(id).classList.remove("current");
          });
          if (g.action === "schedule") el("schedule-form").classList.add("current");
          if (g.action === "publish") el("publish-step").classList.add("current");
          if ((g.action === "schedule" || g.action === "publish") && !data.human) el("name-step").classList.add("current");
          // The step the gate asks for stays open even when it looks done (UI-019).
          ["name-step", "schedule-form", "publish-step"].forEach(function (id) {
            if (el(id).classList.contains("current")) el(id).setAttribute("data-open", "");
          });
          drawDone(data);
          if (document.activeElement !== el("human-name"))
            el("human-name").value = data.human || data.git_human || "";
          el("human-status").textContent = data.human
            ? UAKWorkspace.format("Saved: {name}.", { name: data.human }) + (humanNote ? " " + UAKWorkspace.t(humanNote) : "")
            : "";
          // The dates are never guessed (UI-010): the fields stay empty until the person chooses them.
          if (!el("schedule-zone").value) {
            try {
              el("schedule-zone").value = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
            } catch (e) {
              el("schedule-zone").value = "UTC";
            }
          }
          fillZones();
          var box = g.terminal;
          el("terminal-step").hidden = !box;
          if (box) {
            el("terminal-cd").textContent = box.cd;
            el("terminal-steps").replaceChildren();
            (box.steps || []).forEach(function (line, at) {
              var li = document.createElement("li");
              // A doctor line reads in the page's language; a command matches no pattern and stays as it is (UI-012).
              li.textContent = UAKWorkspace.t(line);
              if (box.items && box.items[at] && box.items[at].code) li.textContent = UAKWorkspace.code(box.items[at].code, box.items[at].values || {});
              el("terminal-steps").append(li);
            });
          }
          // A running operation blocks these with its reason (UI-024, D-6.1); publishing is a human act: before a
          // name is saved, the button says so instead of failing (UI-018).
          ["human-save", "schedule-save", "publish-kit"].forEach(function (id) {
            setWaiting(el(id), data.phase);
          });
          setWaiting(el("publish-preview"), data.phase, nameBlock(data));
        }
        el("copy-terminal-cd").onclick = function () {
          var text = el("terminal-cd").textContent,
            done = function () {
              el("copy-terminal-cd").textContent = UAKWorkspace.t("Copied");
            };
          try {
            navigator.clipboard.writeText(text).then(done, function () {});
          } catch (e) {}
        };
        el("human-save").onclick = function () {
          var name = el("human-name").value.trim().toLowerCase();
          action(this, async function () {
            var answer = await api("human", { name: name });
            humanNote = answer.note || "";
            try {
              localStorage.setItem("uak-human", name);
            } catch (e) {}
            dropDrafts(["human-name", "team-name"]);
            el("name-step").removeAttribute("data-open");
            await refresh();
          });
        };
        // The zone list: the browser's own zone first, then every zone the browser knows (D top 2).
        function fillZones() {
          var list = el("schedule-zones");
          if (list.options.length) return;
          var here = "UTC", zones = [];
          try {
            here = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
          } catch (e) {}
          try {
            zones = Intl.supportedValuesOf ? Intl.supportedValuesOf("timeZone") : [];
          } catch (e) {}
          [here, "UTC"].concat(zones).forEach(function (zone, i, all) {
            if (all.indexOf(zone) !== i) return;
            var option = document.createElement("option");
            option.value = zone;
            list.append(option);
          });
        }
        el("schedule-form").onsubmit = function (event) {
          event.preventDefault();
          var body = {
            start: el("schedule-start").value.replace("T", " "),
            end: el("schedule-end").value.replace("T", " "),
            zone: el("schedule-zone").value.trim(),
          };
          if (!el("schedule-start").value || !el("schedule-end").value) {
            // Never guessed (UI-010); said at the empty field, never in a browser bubble (UI-021).
            fieldError(el("schedule-start").value ? "schedule-end" : "schedule-start", "Choose the start and end dates of the event.");
            return;
          }
          action(el("schedule-save"), async function () {
            // Nothing is written until the person has seen a freeze that is past or about to start.
            var look = await api("schedule", Object.assign({ preview: true }, body));
            if (
              look.soon &&
              !window.confirm(
                UAKWorkspace.t("That freeze is in the past or less than an hour away. Save it anyway?") +
                  "\n" +
                  UAKWorkspace.when(look.freeze_at || look.freeze),
              )
            )
              return;
            var result = await api("schedule", body);
            // In the order they happen, with their dates (UI-021); the engine writes the weekday in English, in the
            // event's zone ("Fri 2026-11-13 03:30"), and when() puts it in the page's language (UI-012, r1).
            el("schedule-status").textContent = UAKWorkspace.format(
              "Saved. Take the first task by {first}; new work stops at {freeze}.",
              {
                first: UAKWorkspace.when(result.first_claim_at || result.first_claim || "-"),
                freeze: UAKWorkspace.when(result.freeze_at || result.freeze),
              },
            );
            dropDrafts(["schedule-start", "schedule-end", "schedule-zone"]);
            el("schedule-form").removeAttribute("data-open");
            startCheck(false);
            await api("check", {});
            checkRequested = true;
            await refresh();
          });
        };
        var publishDigest = "";
        el("publish-preview").onclick = function () {
          action(this, async function () {
            var preview;
            try {
              preview = await api("publish-kit");
            } catch (e) {
              drawWayOut(e.body && e.body.way_out, e.message);
              throw e;
            }
            drawWayOut(null);
            publishDigest = preview.digest;
            el("publish-count").textContent = UAKWorkspace.format(
              "{count} kit files will be committed as your Git identity and uploaded to main. IDEA.md and the plan are not included.",
              { count: preview.files.length },
            );
            el("publish-files").textContent = preview.files.join("\n");
            el("publish-confirm").hidden = false;
            el("publish-kit").focus();
          });
        };
        el("publish-cancel").onclick = function () {
          el("publish-confirm").hidden = true;
          el("publish-preview").focus();
        };
        el("publish-kit").onclick = function () {
          action(this, async function () {
            try {
              await api("publish-kit", { digest: publishDigest });
            } catch (e) {
              drawWayOut(e.body && e.body.way_out, e.message);
              throw e;
            }
            el("publish-confirm").hidden = true;
            el("publish-step").removeAttribute("data-open");
            await refresh();
          });
        };
        el("plan-recheck").onclick = function () {
          action(this, async function () {
            await api("plan/check", {});
            await loadPlan();
          });
        };
        el("check").onclick = function () {
          action(this, async function () {
            if (!state.installed) {
              el("repair").click();
              return false; // it only opens the choices
            }
            startCheck(true);
            await api("check", {});
            checkRequested = true; // only once the server accepted it
            await refresh();
            return false; // render reports what the check found
          });
        };
        el("rules-confirm").onclick = function () {
          action(this, async function () {
            var file = state.settings || {}, values = ruleValues(state), changes = {};
            Object.keys(values).forEach(function (key) {
              if ((file[key] || RULE_NAMES[key][1]) !== values[key]) changes[key] = values[key];
            });
            var box = el("diagnostics").checked ? "on" : "off", pace = el("pacing").checked ? "auto" : "off";
            if ((file.Blackbox || "on") !== box) changes.Blackbox = box;
            if ((file.Pace || "auto") !== pace) changes.Pace = pace;
            // Only what the person confirmed is written: nothing at all when every line stays as it is.
            if (Object.keys(changes).length) await api("settings", changes);
            writeSaved(state.target, { rules: true });
            rulesDirty = false;
            await refresh();
            show(screenFor(state), true);
          });
        };
        el("save").onclick = function () {
          action(this, async function () {
            var link = el("live-url-input").value.trim();
            if (link.indexOf("https://") !== 0) throw Error(UAKWorkspace.t("The app link must start with https://"));
            await api("settings", { "Live-URL": link });
            el("save-status").textContent = UAKWorkspace.t("Saved. The dashboard shows it as your app.");
            await refresh();
          });
        };
        el("update-run").onclick = function () {
          var d = state.detected || {};
          choices = { mode: (state.settings || {}).Mode || (document.querySelector("input[name=mode]:checked") || {}).value, stack: "none", blackbox: (state.settings || {}).Blackbox !== "off" };
          if ((d.harness || []).length) choices.harness = d.harness;
          action(this, async function () {
            await api("repair", choices);
            await refresh();
          });
        };
        el("idea-edit").onclick = function () { ideaEditing = true; drawPlanWin(state); el("idea-text").focus(); };
        el("update-skip").onclick = function () { updateSkipped = true; show(screenFor(state), true); };
        el("unblock-again").onclick = function () {
          action(this, async function () {
            state = await api("inspect", { target: state.target });
            drawBranch(state);
            if (state.branch && state.branch.wrong) { drawScreens(state); return; }
            if (state.installed) {
              startCheck(true);
              await api("check", {});
              checkRequested = true;
              await refresh();
              return false;
            }
            show(screenFor(state), true);
          });
        };
        el("change-folder").onclick = function () {
          formOpen = !formOpen;
          drawScreens(state);
          if (formOpen) el("target").focus();
        };
        document.querySelectorAll("[data-exit]").forEach(function (button) { button.onclick = function () { closeWizard(button); }; });
        el("close-wizard").onclick = function () { closeWizard(this); };
        document.querySelectorAll("[data-go]").forEach(function (button) { button.onclick = function () { show(button.dataset.go, true); }; });
        document.querySelectorAll("[data-next]").forEach(function (button) {
          button.onclick = function () {
            var next = screenFor(state), at = ORDER.indexOf(currentScreen);
            if (currentScreen === "start") next = "dashboard";
            else if (next === currentScreen || ORDER.indexOf(next) <= at) next = ORDER[at + 1] || next;
            if (next === "schedule" && modeOf(state) !== "sprint") next = "publish";
            show(next, true);
          };
        });
        el("copy-terminal-command").onclick = function () { copyText(el("terminal-command").dataset.full, "copy-status"); };
        el("copy-closed").onclick = function () { var b = this; copyText(el("closed-command").dataset.full, "copy-status"); b.textContent = UAKWorkspace.t("Copied"); };
        window.addEventListener("popstate", function (event) {
          var name = (event.state || {}).screen || new URLSearchParams(location.search).get("step");
          if (name && allowed(name, state)) show(name, true, "pop");
        });
        document.querySelectorAll("input[name=mode]").forEach(function (i) { i.addEventListener("change", function () { modePicked = true; drawJourney(); drawScreens(state); }); });
        document.querySelectorAll("input[name=harness]").forEach(function (i) { i.addEventListener("change", function () { drawScreens(state); }); });
        el("stack").addEventListener("change", function () { stackPicked = true; });
        el("rules-advanced").addEventListener("change", function () { rulesDirty = true; drawScreens(state); });
        ["schedule-start", "schedule-end"].forEach(function (id) { el(id).addEventListener("input", function () { drawSchedule(state); }); });
        var humanNote = "";
        function render(data) {
          var previous = state.phase;
          state = data;
          // Another tab re-picked a project on this server: land on it here too (UI-019).
          if (landedFor && data.target && data.target !== landedFor) {
            planView = null;
            teamView = null;
            latestDashboard = null;
            teamFor = "";
            setTimeout(function () {
              landOn(state, landing(state, readSaved(state.target)), false);
            }, 0);
          }
          landedFor = data.target || landedFor;
          // The check goes first, before any view that may probe the coding tools (UI-019).
          maybeAutoCheck(data);
          var busy = isBusy(data.phase);
          el("status-heading").classList.toggle("working", busy);
          el("status-icon").replaceChildren(icon(statusIcon(data)));
          el("result-title").textContent = statusTitle(data);
          el("result-description").textContent = busy
            ? "This can take a moment. Keep the terminal and this page open."
            : data.ready
              ? "Your project passed the existing readiness checks. Continue with the next action below."
              : data.installed
                ? (data.phase === "installed"
                    ? "Installation is complete. "
                    : "") +
                  "Your project may still need a plan, a remote connection, or approval before agents can work. You can also repair or update the kit."
                : "Review the details below, correct the issue, and try again. Existing files are preserved.";
          document.body.classList.toggle("installed", !!data.installed); // UI-024: the rail hides after install
          el("operation-status").textContent =
            data.error ||
            (data.phase === "checking" && (data.checks || []).length
              ? "Your last result stays below until the new one arrives."
              : busy
              ? "Working in the background. You can expand technical details below."
              : data.ready
                ? "Ready for the next task."
                : data.installed && (data.checks || []).length && data.guidance
                  ? UAKWorkspace.t(data.guidance.detail)
                  : "Next: check what your project needs before starting work.");
          el("operation-status").classList.toggle("error", !!data.error);
          drawPlanProgress(data);
          el("output").textContent = data.details || UAKWorkspace.t("No technical output yet.");
          drawChecks(data);
          // Preferences and Repair stay in place while an operation runs (hiding them made the page jump, UI-018).
          el("preferences").hidden = !data.installed;
          setWaiting(el("save"), data.phase);
          if (!rulesDirty) {
            el("diagnostics").checked = (data.settings || {}).Blackbox === "on";
            el("pacing").checked = (data.settings || {}).Pace !== "off";
          }
          if (document.activeElement !== el("live-url-input"))
            el("live-url-input").value = (data.settings || {})["Live-URL"] || "";
          setWaiting(el("check"), data.phase);
          setWaiting(el("next-check"), data.phase);
          setWaiting(el("change-project"), data.phase);
          el("repair").hidden = !data.can_repair;
          setWaiting(el("repair"), data.phase);
          setLabel(el("check"), data.installed
            ? data.ready
              ? "Check again"
              : "Check what’s next"
            : "Review choices");
          // Planning shows while the kit is installed and the project is not ready yet.
          el("planning").hidden = !planningVisible(data); // never "Create the plan" for an approved plan (B-04)
          drawPrepare(data);
          if (!el("planning").hidden && !isBusy(data.phase) && (previous === "planning" || previous === "publishing" || planFor !== data.target)) {
            planFor = data.target;
            loadPlan();
          }
          setPlanBusy(isBusy(data.phase));
          syncRunningControls();
          drawPhaseButtons(data, previous);
          if (previous === "registering" && !isBusy(data.phase)) {
            if (data.error) el("team-reviewer-status").textContent = UAKWorkspace.t(data.error);
            else loadTeam();
          } else if (isBusy(previous) && !isBusy(data.phase) && (data.ready || data.team)) {
            loadTeam();
          }
          // A finished readiness check moves on by itself: to project progress when ready, and it refreshes the
          // dashboard's next step when the check was started from there.
          // A fast check can finish before the first poll ever sees "checking": remember that one was asked.
          if (
            (previous === "checking" || previous === "approving" || checkRequested) &&
            !isBusy(data.phase)
          ) {
            // The check says what it found next to the button that asked, even when nothing changed (UI-018), and
            // when the next step is one this page does, it points there.
            if (previous === "checking" || checkRequested) {
              if (data.error) failed(checkOwner(), data.error);
              else report(checkOwner(), checkSummary(checkBefore, data, new Date()));
              var control = pointAfterCheck && !checkAuto && !data.ready && currentSection === "setup" ? nextControl(data) : "";
              pointAfterCheck = false;
              if (control) setTimeout(function () { pointTo(control); }, 0);
            }
            checkRequested = false;
            // A check the page ran by itself never switches the tab or moves focus (A-F11): the landing chose it.
            var automatic = checkAuto;
            checkAuto = false;
            if (automatic) {
              if (currentSection === "dashboard") loadDashboard();
            } else if (data.ready || currentSection === "dashboard") {
              var moved = currentSection !== "dashboard";
              openSection("dashboard");
              loadDashboard();
              if (moved) el("dashboard-shell").focus();
            }
          }
          drawJourney();
          drawIdentity(data);
          drawBranch(data);
          // Who signs is read in the background after choosing the project: ask again until it arrives (a few tries).
          if (data.target && !data.identity && identityTries < 8 && !isBusy(data.phase)) {
            identityTries += 1;
            setTimeout(refresh, 700);
          } else if (data.identity) identityTries = 0;
          drawScreens(data);
          if (previous === "installing" && !isBusy(data.phase) && !data.error && data.installed) show(screenFor(data), true);
        }
        async function refresh() {
          if (timer) clearTimeout(timer);
          if (gone) return;
          try {
            var data = await api("status");
            render(data);
            // Progress of a running action: every 1.2 s while it runs and the page is shown, never while it is hidden.
            if ((isBusy(data.phase) || runsActive(data)) && !document.hidden)
              timer = setTimeout(refresh, 1200);
          } catch (e) {
            if (e.gone) return; // the banner says it once (UI-019)
            error(
              "Lost connection to setup. Keep the terminal open, then reload the original address printed there. " +
                e.message,
            );
          }
        }
        // Apply a landing (UI-019): the panel, then the section; the dashboard loads when it is the one shown.
function landOn(data, where, focus) {
          landedFor = data.target || "";
          if (data.installed || data.can_repair) render(data);
          if (isBusy(data.phase) || runsActive(data)) refresh();
          show(where.screen, focus === true, "replace");
        }
        session
          .then(function () {
            return api("status");
          })
          .then(function (data) {
            state = data;
            showDemo(data.demo);
            el("target").value = data.target || "";
            var saved = readSaved(data.target),
              wanted = new URLSearchParams(location.search).get("step"),
              where = landing(data, saved, wanted);
            landOn(data, where, false);
            restoreDrafts(saved);
            // A folder given on the command line is read at once, so the first screen says what it found.
            if (data.target && !data.installed && !data.detected) {
              inspectFolder(data.target).catch(function (e) {
                if (e.gone) return;
                formOpen = true;
                drawScreens(state);
                fieldError("target", e.message);
              });
            }
          })
          .catch(function (e) {
            if (!e.gone) error(e.message);
          })
          .then(function () {
            // The panel shows once it knows which step is current: no welcome screen flashing first (UI-018).
            el("content").removeAttribute("data-loading");
            drawScreens(state);
          });
      })();
