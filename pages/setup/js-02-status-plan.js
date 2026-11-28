        function drawLiveUrl(url) {
          var link = el("live-url-link"),
            valid = typeof url === "string" && url.indexOf("https://") === 0;
          link.hidden = !valid;
          el("live-url-empty").hidden = valid;
          if (valid) {
            link.href = url;
            link.textContent = url;
          } else {
            link.removeAttribute("href");
            link.textContent = "";
          }
        }
        // Guided re-check: when the person comes back to the tab, and every minute while a blocker is shown,
        // in whichever section shows it (Configuration reads the status guidance, the Dashboard its own).
        var lastAutoCheck = 0;
        function autoCheck() {
          if (Date.now() - lastAutoCheck < 120000) return;
          var g =
            (currentSection === "dashboard" &&
              latestDashboard &&
              latestDashboard.guidance) ||
            state.guidance ||
            {};
          if (
            gone ||
            document.hidden ||
            document.body.dataset.profile !== "beginner" ||
            !state.installed ||
            operationBusy() ||
            requestBusy ||
            g.kind !== "todo"
          )
            return;
          lastAutoCheck = Date.now();
          startCheck(false);
          lastButton = currentSection === "dashboard" ? "next-check" : "check";
          api("check", {})
            .then(function () {
              checkRequested = true;
              return refresh();
            })
            .catch(function () {});
        }
        document.addEventListener("visibilitychange", autoCheck);
        // UAK-156: no timer runs the readiness check. It runs when the page loads, after an action and on a button;
        // coming back to the tab asks again at most every two minutes, and only while a blocker is shown.
        function operationBusy() {
          return isBusy(state.phase);
        }
        function isBusy(phase) {
          return ["installing", "checking", "planning", "approving", "publishing", "registering"].indexOf(phase) >= 0;
        }
        // The status heading (UI-012, r3): "ok" only when nothing is left to do; the gate's line in the page's language.
        function statusIcon(data) {
          if (isBusy(data.phase)) return "busy";
          if (data.ready) return "ok";
          var todo = (data.checks || []).some(function (c) { return c.state === "todo"; });
          return data.phase === "error" || todo || !data.installed ? "todo" : "ok";
        }
        function statusTitle(data) {
          var title = isBusy(data.phase)
            ? {
                installing: "Installing your workspace",
                planning: "Creating your plan",
                approving: "Publishing your plan",
                publishing: "Publishing the kit",
                registering: "Registering the reviewer…",
              }[data.phase] || "Checking your next steps"
            : data.ready
              ? "Your workspace is ready"
              : data.phase === "error"
                ? "Let’s resolve this step"
                : data.installed && (data.checks || []).length && data.guidance
                  ? data.guidance.title
                  : data.installed
                    ? data.phase === "installed"
                      ? "The kit is installed. Let’s get ready."
                      : "Kit files found. Let’s check your project."
                    : "Continue setting up your project";
          if (data.guidance && data.guidance.code && !isBusy(data.phase) && !data.ready && data.phase !== "error" &&
              data.installed && (data.checks || []).length)
            return UAKWorkspace.code(data.guidance.code, data.guidance.values);
          return UAKWorkspace.gate(UAKWorkspace.t(title || ""));
        }
        // Planning (UI-004). Plan text comes from files an agent wrote: it is shown with textContent only.
        var planView = null,
          planFor = "",
          plannerNames = { claude: "Claude Code", codex: "Codex", gemini: "Gemini CLI", cursor: "Cursor" };
        function selectedPlanner() {
          var input = document.querySelector("input[name=planner]:checked");
          return input ? input.value : "";
        }
        function setPlanBusy(busy) {
          var phase = busy ? state.phase : "",
            planned = !!(planView && planView.planned);
          // Waiting for an earlier step, or for a running operation, is blocked, not busy: it says why (UI-018,
          // UI-024 D-6.1). The publish-first reason lives only under Create the plan (A-F15: it was said 3 times).
          setWaiting(el("plan-create"), phase);
          if (!busy) setBlocked(el("plan-create"), planBlock(planView, selectedPlanner()));
          if (!busy && !planView) el("plan-create").disabled = true;
          setWaiting(el("plan-recheck"), phase);
          if (!planned) el("plan-recheck").disabled = true;
          el("plan-remote-note").hidden = !planView || !planView.remote_note;
          el("plan-remote-note").textContent = planView && planView.remote_note ? UAKWorkspace.t(planView.remote_note) : "";
          technical(el("plan-remote-note"), (planView && planView.remote_note && planView.remote_technical) || "");
          // The trust note is Claude Code's: shown only when Claude Code drafts the plan (D-1.1).
          el("plan-trust").hidden = !planView || !planView.trust_command || selectedPlanner() !== "claude";
          el("plan-trust-command").textContent = (planView && planView.trust_command) || "";
          trustLine(el("plan-trust-help"), planView && planView.trust_command ? planView.trust : undefined);
          setWaiting(el("plan-change"), phase, !planView || selectedPlanner() ? null : planBlock(planView, ""));
          if (!busy && !planView) el("plan-change").disabled = true;
          // A plan with problems: the click says what to do first (a rule break: undo it; lint: ask for changes).
          var why = !planned
            ? null
            : planView.violations.length
              ? { text: "Undo the planner's changes first, then create the plan again.", target: "plan-violations" }
              : planView.failed || !planView.lint.ok
                ? { text: "Fix the plan's problems first: ask for changes.", target: "plan-note" }
                : null;
          setWaiting(el("plan-approve"), phase, why);
          var blocked = !planned;
          if (!busy) el("plan-approve").disabled = blocked || (!why && !!planView.failed);
          setWaiting(el("idea-save"), phase);
          if (busy) el("approve-confirm").hidden = true;
        }
        async function loadPlan() {
          try {
            drawPlan(await api("plan"));
          } catch (e) {
            if (!e.gone) error(e.message);
          }
        }
        function drawPlan(view) {
          var chosen = selectedPlanner();
          planView = view;
          el("idea-goal-label").textContent = UAKWorkspace.t(
            view.mode === "marathon" ? "Spec goal" : "Judging rubric",
          );
          el("idea-status").textContent = view.idea
            ? UAKWorkspace.t("IDEA.md is saved. To replace it, fill in the form and save again.")
            : "";
          el("idea-saved").hidden = !view.idea;
          el("idea-saved-text").textContent = view.idea;
          el("planner-options").replaceChildren();
          view.planners.forEach(function (offer) {
            var label = document.createElement("label"),
              input = document.createElement("input"),
              text = document.createElement("span"),
              name = document.createElement("strong"),
              why = document.createElement("small");
            label.className = "choice";
            input.type = "radio";
            input.name = "planner";
            input.value = offer.harness;
            input.disabled = !offer.available;
            input.checked = offer.available && (chosen ? chosen === offer.harness : !document.querySelector("input[name=planner]:checked"));
            input.onchange = function () {
              setPlanBusy(operationBusy());
            };
            name.textContent = plannerNames[offer.harness] || offer.harness;
            why.textContent = UAKWorkspace.t(offer.available ? "Ready to draft the plan." : offer.reason);
            text.append(name, why);
            label.append(input, text);
            el("planner-options").append(label);
          });
          // A run that wrote no plan is a failed plan (UI-010): only what it changed is shown, the notice above says why
          // and "Create the plan" is the retry; there is no lint verdict, plan or approve button.
          el("plan-review").hidden = !view.planned && !(view.failed && view.violations.length);
          // UI-024 (D-7.1): after a rule break no green "passes" box and no "Ask for changes": one instruction, undo.
          el("plan-lint").hidden = !!view.failed || !!view.violations.length;
          el("plan-cards").hidden = !!view.failed;
          el("plan-files").parentNode.hidden = !!view.failed;
          el("plan-ask").hidden = !!view.failed || !!view.violations.length;
          el("plan-violations").hidden = !view.violations.length;
          var undo = view.undo || {};
          el("plan-undo-text").textContent = UAKWorkspace.t(undo.text || "");
          el("plan-undo-command").textContent = undo.command || "";
          el("plan-undo-run").hidden = !undo.command;
          el("plan-undo-status").textContent = "";
          el("plan-violation-list").replaceChildren();
          view.violations.forEach(function (line) {
            var li = document.createElement("li");
            li.textContent = line;
            el("plan-violation-list").append(li);
          });
          el("plan-lint").classList.toggle("error", !view.lint.ok);
          el("plan-lint-summary").textContent = UAKWorkspace.t(
            view.lint.ok
              ? "The plan passes the kit's checks (uak lint)."
              : "The kit's checks (uak lint) found problems. Ask for changes:",
          );
          el("plan-lint-lines").replaceChildren();
          view.lint.lines.forEach(function (line) {
            var li = document.createElement("li");
            li.textContent = line;
            el("plan-lint-lines").append(li);
          });
          el("plan-cards").replaceChildren();
          view.cards.forEach(function (card) {
            var li = document.createElement("li"),
              title = document.createElement("strong"),
              meta = document.createElement("span"),
              tests = document.createElement("span");
            title.textContent = card.id + " · " + plainText(card.title);
            title.dataset.noI18n = "";
            meta.className = "pills";
            [card.priority || "?", UAKWorkspace.format("wave {w}", { w: card.wave || "?" }),
              card.depends.length ? UAKWorkspace.format("after {d}", { d: card.depends.join(", ") }) : UAKWorkspace.t("starts first")].forEach(function (text) { meta.append(pill(text)); });
            tests.textContent = card.tests.length
              ? UAKWorkspace.t("Checks it must pass:") + " " + card.tests.join(", ").replace(/_/g, " ")
              : UAKWorkspace.t("Tests first:") + " " + (card.test_first || "-");
            tests.dataset.noI18n = "";
            li.append(title, meta, tests);
            el("plan-cards").append(li);
          });
          el("plan-files").textContent =
            "# .uak/TASKS.md\n\n" + view.tasks + "\n\n# .uak/OWNERS.md\n\n" + view.owners;
          el("approve-project").textContent = view.project;
          el("approve-publish").disabled = el("approve-name").value !== view.project;
          setPlanBusy(operationBusy());
          drawDone(state);
          drawPlanWin(state);
        }
        // While the coding tool plans (4 to 8 minutes in the test rounds) the page shows how long and its last output line.
        var planClock = null;
        function drawPlanProgress(data) {
          var progress = data.phase === "planning" ? data.plan_progress || {} : {};
          if (progress.elapsed === undefined) {
            planClock = null;
            el("plan-progress").hidden = true;
            return;
          }
          planClock = { at: Date.now() - progress.elapsed * 1000, last: progress.last || "" };
          tickPlanProgress();
        }
