        function drawScreens(data) {
          data = data || {};
          drawProject(data); drawProjectWindow(data); drawInstall(data); drawUnblock(data); drawUpdate(data); drawRules(data); drawPeople(data);
          drawSchedule(data); drawPublish(data); drawPlanWin(data); drawStart(data); drawDashboardWin(data);
          var command = terminalCommand(data.target);
          ["terminal-command", "closed-command"].forEach(function (id) {
            el(id).textContent = shown(command); el(id).title = command; el(id).dataset.full = command;
          });
          followFooters();
          var here = el("screen-" + currentScreen);
          if (here) Array.from(here.querySelectorAll("[data-p]")).forEach(function (b) { b.classList.remove("primary"); b.classList.add("secondary-button"); });
          arbitrate();
          drawBusy(data);
        }
        // One primary per view: of the candidate buttons the page shows, the one with the lowest order is the primary.
        function arbitrate() {
          var here = el("screen-" + currentScreen);
          if (!here) return;
          var best = null;
          Array.from(here.querySelectorAll("[data-p]")).forEach(function (b) {
            if (b.getClientRects().length && (!best || Number(b.dataset.p) < Number(best.dataset.p))) best = b;
          });
          if (best) { best.classList.add("primary"); best.classList.remove("secondary-button"); }
        }
        // A button the page shows or hides later (a team view that arrives, a plan that appears) changes which one leads.
        if (typeof MutationObserver === "function") {
          var arbiter = null;
          new MutationObserver(function () {
            if (arbiter) return;
            arbiter = setTimeout(function () { arbiter = null; followFooters(); arbitrate(); }, 0);
          }).observe(document.getElementById("content"), { subtree: true, attributes: true, attributeFilter: ["hidden", "data-on", "aria-disabled"] });
        }
        var BUSY_WORDS = { installing: "Installing the kit", checking: "Checking your project", planning: "Drafting the plan", approving: "Publishing the plan", publishing: "Publishing the kit", registering: "Registering the reviewer" };
        // A running action says what it is doing and for how long, next to its button.
        function drawBusy(data) {
          var note = el("note-" + currentScreen);
          if (!note) return;
          if (isBusy(data.phase)) {
            if (!busySince) busySince = Date.now();
            if (!busyTimer) busyTimer = setInterval(function () { drawBusy(state); }, 1000);
            note.textContent = UAKWorkspace.t(BUSY_WORDS[data.phase] || "Working") + " · " + Math.round((Date.now() - busySince) / 1000) + " s";
          } else {
            busySince = 0;
            if (busyTimer) { clearInterval(busyTimer); busyTimer = null; }
            if (/ · \d+ s$/.test(note.textContent)) note.textContent = "";
          }
        }
        function closeWizard(button) {
          action(button, async function () {
            await api("close", {});
            closedWizard = true;
            gone = true;
            if (timer) clearTimeout(timer);
            show("closed", true);
            drawJourney();
            try { window.close(); } catch (e) {}
          });
        }
        function error(message) {
          // The dashboard hides the setup panel: show the failure where the person is looking.
          if (currentSection === "dashboard") {
            el("dashboard-status").hidden = false;
            el("dashboard-status").textContent = UAKWorkspace.t(message);
            el("dashboard-status").classList.add("error");
            return;
          }
          el("error").textContent = UAKWorkspace.t(message);
          el("error").hidden = false;
        }
        // A second start of setup for this project opened another page: the answer says how many since this page began.
        function reopenedNotice(response) {
          var count = parseInt(response.headers.get("X-UAK-Reopens") || "0", 10);
          if (count > 0 && el("reopened").hidden) {
            el("reopened-text").textContent = UAKWorkspace.format(
              "Another page of setup was opened at {time} from a second start in a terminal. If you did that, there is nothing to do. If not, press Ctrl+C in the terminal where setup runs.",
              { time: response.headers.get("X-UAK-Reopened-At") || "" },
            );
            el("reopened").hidden = false;
          }
        }
        el("reopened-dismiss").onclick = function () {
          el("reopened").hidden = true;
        };
        async function api(path, data) {
          var options = { headers: { "X-UAK-Token": token } };
          if (typeof pageId === "string") options.headers["X-UAK-Page"] = pageId;
          if (data !== undefined) {
            options.method = "POST";
            options.headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(data);
          }
          var response, body;
          try {
            response = await fetch("/api/" + path, options);
            if (typeof reopenedNotice === "function" && response.headers) reopenedNotice(response);
            body = await response.json();
          } catch (e) {
            throw serverLost(e); // no answer, or not setup's answer: setup has closed (UI-019)
          }
          if (response.status === 403 && /session expired/.test(String((body || {}).error || "")))
            throw serverLost(body);
          if (!response.ok) {
            var failure = Error(
              body.error || "The action could not finish. Please retry.",
            );
            failure.status = response.status;
            failure.body = body;
            throw failure;
          }
          return body;
        }
        // Every request: the busy label in its button while it runs, then a result line next to it (UI-018). An
        // operation that goes on in the background keeps its button busy; render says how it ended. fn() returning
        // false reports by itself (a check reports what it found).
        async function action(button, fn) {
          if (requestBusy) return;
          requestBusy = true;
          lastButton = (button && button.id) || "";
          button.disabled = true;
          setBusy(button, true);
          el("error").hidden = true;
          var outcome, failure = null, tech = "", atField = false;
          try {
            outcome = await fn();
          } catch (e) {
            failure = e;
            tech = (e.body && e.body.technical) || "";
            atField = !!(e.body && e.body.field && fieldError(fieldInput(e.body.field, button), e.message));
          } finally {
            requestBusy = false;
            button.disabled =
              step === 4 && isBusy(state.phase);
            var running = isBusy(state.phase) && phaseOwner(state.phase) === button;
            if (!running) setBusy(button, false);
            // The reason is under its field already: the result line only points there (said once, A-F15).
            if (failure) failed(button, atField ? "See the message under the field." : failure.message, tech);
            else if (!running && outcome !== false) done(button);
          }
        }
        // UI-018 feedback: begin. Dylan's run (2026-11-13): a blocked button looked busy and said nothing, and a check
        // seemed to do nothing. Every request shows its busy label inside its button and how it ended right next to it;
        // a button that waits for an earlier step says why (aria-disabled, so a click can explain it in a toast).
        // team-roles is a block, not a button (saving the roles guards it): setBusy leaves non-buttons as they are.
        // UI-021 (QA round D, top 1): a refused field said so in a box ~2,900 px away with the focus on <body>. The
        // server names the field; the message goes under it, the field is marked invalid and gets the focus.
        var FIELD_INPUT = {
          target: "target",
          name: "human-name",
          start: "schedule-start",
          end: "schedule-end",
          zone: "schedule-zone",
          idea: "idea-text",
          audience: "idea-audience",
          rubric: "idea-goal",
          goal: "idea-goal",
          event_length: "idea-length",
          team_size: "idea-team",
        };
        function fieldInput(field, button) {
          if (field === "name" && button && button.id === "team-name-save") return "team-name";
          return FIELD_INPUT[field] || "";
        }
        // The message under the field; false when the field is not on screen (the global box says it then).
        function fieldError(id, message) {
          var input = id && el(id);
          if (!input || !input.getClientRects().length) return false;
          var box = el(id + "-error");
          if (!box) {
            box = document.createElement("p");
            box.id = id + "-error";
            box.className = "field-error";
            box.setAttribute("role", "alert");
            // Under the row of a side-by-side group (name and Save, the three schedule fields): the row keeps its line.
            (input.closest(".prepare-row") || input).after(box);
          }
          box.textContent = UAKWorkspace.t(message);
          input.setAttribute("aria-invalid", "true");
          var described = (input.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
          if (described.indexOf(box.id) < 0) described.push(box.id);
          input.setAttribute("aria-describedby", described.join(" "));
          input.focus();
          return true;
        }
        function clearFieldError(input) {
          if (!input || input.getAttribute("aria-invalid") !== "true") return;
          input.removeAttribute("aria-invalid");
          var box = el(input.id + "-error");
          if (box) box.textContent = "";
        }
        document.addEventListener("input", function (event) {
          clearFieldError(event.target);
        });
        // The page's own messages, never the browser's (English) bubbles: the first empty or invalid field of a form.
        function checkFields(form) {
          var fields = form.querySelectorAll("input[required], textarea[required]");
          for (var i = 0; i < fields.length; i++) {
            var input = fields[i];
            if (!input.getClientRects().length || input.type === "radio" || input.type === "checkbox") continue;
            clearFieldError(input);
            if (!input.value.trim()) return !fieldError(input.id, "Fill in this field.");
            if (input.type === "number" && !/^\d+$/.test(input.value.trim())) return !fieldError(input.id, "Use a whole number from 1 to 50.");
          }
          return true;
        }
        // Git's own words under a result line, folded: the line says what happened in plain words (UI-021).
        function technical(anchor, text) {
          if (!anchor) return;
          var box = el(anchor.id + "-technical");
          if (!text) {
            if (box) box.remove();
            return;
          }
          if (!box) {
            box = document.createElement("details");
            box.id = anchor.id + "-technical";
            box.className = "technical";
            var summary = document.createElement("summary"),
              pre = document.createElement("pre");
            summary.textContent = UAKWorkspace.t("Technical details");
            pre.dataset.noI18n = "";
            box.append(summary, pre);
            anchor.after(box);
          }
          box.querySelector("pre").textContent = text;
        }
        var BUSY_LABEL = {
          check: "Checking…",
          "next-check": "Checking…",
          "team-retry": "Checking…",
          install: "Installing…",
          "publish-preview": "Reading the files…",
          "publish-kit": "Publishing…",
          "human-save": "Saving…",
          "schedule-save": "Saving…",
          "idea-save": "Saving…",
          save: "Saving…",
          "plan-create": "Creating the plan…",
          "plan-change": "Creating the plan…",
          "plan-recheck": "Checking the plan…",
          "approve-publish": "Publishing…",
          "team-register": "Registering…",
          "team-roles": "Saving…",
          "team-name-save": "Saving…",
          "check-folder": "Checking…",
          "unblock-again": "Checking…",
          "rules-confirm": "Saving…",
          "update-run": "Updating…",
          "close-wizard": "Closing…",
        };
        // The background operation of each phase and the buttons that start it (the one pressed, or the first).
        var PHASE_BUTTONS = {
          checking: ["check", "next-check"],
          installing: ["install"],
          publishing: ["publish-kit"],
          planning: ["plan-create", "plan-change"],
          approving: ["approve-publish"],
          registering: ["team-register"],
        };
        var lastButton = "",
          checkBefore = null,
          pointAfterCheck = false,
          checksKey = "",
          toastTimer = null,
          toastLeft = 0,
          toastAt = 0,
          toastFrom = null,
          TOAST_MS = 8000;
        function clock(date) {
          var pad = function (n) {
            return (n < 10 ? "0" : "") + n;
          };
          return pad(date.getHours()) + ":" + pad(date.getMinutes());
        }
        function isButton(node) {
          return !!node && node.tagName === "BUTTON" && !!node.id;
        }
        // A label drawn while the button is busy waits until the request ends.
        function setLabel(button, text) {
          button.dataset.label = text;
          if (button.getAttribute("aria-busy") !== "true") button.textContent = text;
        }
        function setBusy(button, busy) {
          if (!isButton(button)) return;
          if (busy && button.getAttribute("aria-busy") !== "true") {
            // Not busy, the text is the current label (code may have changed it since the last request).
            button.dataset.label = button.textContent.trim();
            button.setAttribute("aria-busy", "true");
            button.textContent = UAKWorkspace.t(BUSY_LABEL[button.id] || "Working…");
          } else if (!busy && button.getAttribute("aria-busy") === "true") {
            button.removeAttribute("aria-busy");
            button.textContent = button.dataset.label || "";
          }
        }
        // A confirmation that closes when it succeeds reports next to the button that opened it.
        var RESULT_AT = { "publish-kit": "publish-preview", "approve-publish": "plan-approve" };
        // The result line of a button: under its row of actions, or right after it.
        function resultLine(button) {
          var line = el(button.id + "-result");
          if (!line) {
            line = document.createElement("p");
            line.id = button.id + "-result";
            line.className = "action-result";
            line.setAttribute("role", "status");
            line.setAttribute("aria-live", "polite");
            line.dataset.noI18n = "";
            var row = button.parentNode;
            (row && row.classList.contains("actions") ? row : button).after(line);
          }
          return line;
        }
        function report(button, text, failed, details) {
          if (button && RESULT_AT[button.id] && el(RESULT_AT[button.id])) button = el(RESULT_AT[button.id]);
          if (!isButton(button)) return;
          var line = resultLine(button);
          if (failed && (button.id === "publish-preview" || button.id === "publish-kit")) showFix(text);
          line.textContent = text;
          line.classList.toggle("error", !!failed);
          technical(line, details || "");
        }
        function done(button) {
          report(button, UAKWorkspace.format("Done at {time}.", { time: clock(new Date()) }));
        }
        function failed(button, message, details) {
          report(
            button,
            UAKWorkspace.format("Failed at {time}: {error}", { time: clock(new Date()), error: UAKWorkspace.t(message) }),
            true,
            details,
          );
        }
        function phaseOwner(phase) {
          var ids = PHASE_BUTTONS[phase] || [];
          return el(ids.indexOf(lastButton) >= 0 ? lastButton : ids[0]);
        }
        function checkOwner() {
          return phaseOwner("checking");
        }
        // While a background operation runs, the button that started it stays busy; when it ends it says how.
        function drawPhaseButtons(data, previous) {
          Object.keys(PHASE_BUTTONS).forEach(function (phase) {
            var owner = phaseOwner(phase);
            PHASE_BUTTONS[phase].forEach(function (id) {
              setBusy(el(id), data.phase === phase && el(id) === owner);
            });
          });
          if (isBusy(previous) && previous !== "checking" && !isBusy(data.phase)) {
            if (data.error) failed(phaseOwner(previous), data.error);
            else if (previous === "planning" && data.outcome === "problems")
              // UI-024 (D-7.1): a plan written after a rule break is not "Done".
              report(
                phaseOwner(previous),
                UAKWorkspace.format("Finished with problems at {time}: {problem}", {
                  time: clock(new Date()),
                  problem: UAKWorkspace.t(data.problem || ""),
                }),
                true,
              );
            else done(phaseOwner(previous));
          }
        }
        // "Checked at 21:04 · nothing changed · 2 things to do": a check that changed nothing still says so.
        function checkSummary(before, data, now) {
          var checks = data.checks || [],
            todo = checks.filter(function (c) {
              return c.state === "todo";
            }).length,
            parts = [UAKWorkspace.format("Checked at {time}", { time: clock(now) })];
          if (before && JSON.stringify(before) === JSON.stringify(checks)) parts.push(UAKWorkspace.t("nothing changed"));
          parts.push(
            data.ready || !todo
              ? UAKWorkspace.t("everything is ready")
              : todo === 1
                ? UAKWorkspace.t("1 thing to do")
                : UAKWorkspace.format("{count} things to do", { count: todo }),
          );
          return parts.join(" · ");
        }
        function startCheck(byPerson) {
          checkBefore = state.checks || [];
          if (byPerson) pointAfterCheck = true;
        }
        // The gate's next step, when it is something this page does: its control.
        function nextControl(data) {
          var action = (data.guidance || {}).action;
          if ((action === "publish" || action === "schedule") && !data.human) return "human-name";
          if (action === "publish") return "publish-preview";
          if (action === "schedule") return "schedule-start";
          if (action === "plan") return planView && planView.planned ? "plan-approve" : "plan-create";
          return "";
        }
        function pointTo(id) {
          var node = el(id), home = node && node.closest ? node.closest(".screen") : null;
          if (home && !home.hasAttribute("data-on") && typeof show === "function") show(home.dataset.screen, false);
          if (!node || node.offsetParent === null) return false;
          var still = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
          node.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
          node.focus({ preventScroll: true });
          node.classList.add("spotlight");
          setTimeout(function () {
            node.classList.remove("spotlight");
          }, 4000);
          return true;
        }
        // Why Create the plan waits, in the order of the page's steps.
        function planBlock(view, planner) {
          if (!view) return null;
          if (!view.kit_on_main) return { text: "Publish the kit to main first (step 3).", target: "publish-preview" };
          if (!view.idea) return { text: "Save the idea first.", target: "idea-text" };
          if (!planner) return { text: "Choose the coding tool that drafts the plan.", target: "planner-choice" };
          return null;
        }
        function nameBlock(data) {
          return data.installed && !data.human ? { text: "Save your name first (step 1).", target: "human-name" } : null;
        }
        // Blocked is not busy: aria-disabled (the button stays focusable and its click explains itself), the reason
        // in text next to it when the page has a place for it (#ID-why), and the not-allowed cursor.
        function setBlocked(button, why) {
          if (why) {
            button.setAttribute("aria-disabled", "true");
            button.dataset.blockedText = why.text;
            button.dataset.blockedTarget = why.target || "";
          } else {
            button.removeAttribute("aria-disabled");
            delete button.dataset.blockedText;
            delete button.dataset.blockedTarget;
          }
          var line = el(button.id + "-why");
          if (line) {
            line.textContent = why ? UAKWorkspace.t(why.text) : "";
            line.hidden = !why;
          }
        }
        function showToast(why, from) {
          el("toast-text").textContent = UAKWorkspace.t(why.text || "");
          el("toast-go").hidden = !why.target;
          el("toast-go").dataset.target = why.target || "";
          el("toast").hidden = false;
          toastFrom = from || null;
          toastLeft = TOAST_MS;
          armToast();
        }
        function armToast() {
          clearTimeout(toastTimer);
          toastAt = Date.now();
          toastTimer = setTimeout(hideToast, toastLeft);
        }
        function pauseToast() {
          if (toastTimer === null) return;
          clearTimeout(toastTimer);
          toastTimer = null;
          toastLeft = Math.max(2000, toastLeft - (Date.now() - toastAt));
        }
        function resumeToast() {
          if (!el("toast").hidden && toastTimer === null) armToast();
        }
        function hideToast() {
          clearTimeout(toastTimer);
          toastTimer = null;
          el("toast").hidden = true;
        }
