    <script nonce="__NONCE__">
      (function () {
        "use strict";
        // UAK-153: the address carries a one-time code, not the session. The server exchanges it once for the token.
        // UAK-156: each page has an id, so setup knows which pages are open (closing one tab leaves the other's server).
        var pageId = Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
        var token = "",
          session = Promise.resolve(),
          codeMatch = /^#code=([A-Za-z0-9_-]+)$/.exec(location.hash);
        try {
          token = sessionStorage.getItem("uak-setup-token") || "";
        } catch (e) {}
        if (codeMatch) {
          // Asynchronous, so nothing blocks the page: the first request (below) waits for it.
          session = fetch("/api/session", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-UAK-Page": pageId },
            body: JSON.stringify({ code: codeMatch[1] }),
          })
            .then(function (response) {
              return response.ok ? response.json() : null;
            })
            .then(function (body) {
              if (!body || !body.token) return;
              token = body.token;
              try {
                sessionStorage.setItem("uak-setup-token", token);
              } catch (e) {}
            })
            .catch(function () {});
        }
        history.replaceState(null, "", location.pathname + location.search);
        var state = {},
          choices = {},
          step = 4,
          timer = null,
          requestBusy = false;
        var latestDashboard = null,
          dashboardTimer = null,
          currentSection = "setup",
          dashboardLoading = false,
          dashboardAgain = false,
          dashboardUnchanged = 0,
          dashboardSignature = "",
          checkRequested = false,
          lastStepTitle = "";
        // Status marks are drawn, never typed: an inline SVG with its word beside it (UAK-158).
        var ICON_PATHS = { ok: "M3 8.5l3 3 7-7", todo: "M8 3.5v6M8 12.5v.5", info: "M8 7.5v5M8 4v.5", no: "M4 4l8 8M12 4l-8 8", busy: "M3 8h.5M8 8h.5M12.5 8h.5" };
        function icon(kind) {
          var NS = "http://www.w3.org/2000/svg",
            svg = document.createElementNS(NS, "svg"),
            path = document.createElementNS(NS, "path");
          svg.setAttribute("viewBox", "0 0 16 16");
          svg.setAttribute("class", "ic");
          svg.setAttribute("aria-hidden", "true");
          path.setAttribute("d", ICON_PATHS[kind] || ICON_PATHS.info);
          svg.appendChild(path);
          return svg;
        }
        function el(id) {
          return document.getElementById(id);
        }
        function operationRunning() {
          return isBusy(state.phase);
        }
        function syncRunningControls() {
          var busy = operationRunning();
          document
            .querySelectorAll(
              "#project-form input,#workflow-form input,#workflow-form select",
            )
            .forEach(function (input) {
              if (busy && !input.hasAttribute("data-job-disabled")) {
                input.dataset.jobDisabled = input.disabled ? "true" : "false";
                input.disabled = true;
              } else if (!busy && input.hasAttribute("data-job-disabled")) {
                input.disabled = input.dataset.jobDisabled === "true";
                delete input.dataset.jobDisabled;
              }
            });
          document
            .querySelectorAll(
              "#project-form button[type=submit],#workflow-form button[type=submit],#install,#rules-confirm,#update-run",
            )
            .forEach(function (button) {
              setWaiting(button, waitingPhase());
            });
          el("running-review").hidden = !busy || step === 4;
        }

        function sendDashboard() {
          el("dashboard-frame").title = UAKWorkspace.t("Dashboard");
          if (latestDashboard && el("dashboard-frame").contentWindow)
            el("dashboard-frame").contentWindow.postMessage(
              {
                type: "uak:dashboard",
                snapshot: latestDashboard,
                language: UAKWorkspace.language(),
                look: UAKLook.get(),
              },
              "*",
            );
        }
        // One way to start a task: once Start your team shows its commands, the bare claim command is not offered
        // again (two Copy buttons for the same claim confused the simulation's person).
        var teamReady = false,
          teamTool = "Claude Code";
        // UI-024 (D-3.2, review of a8c124f): before the reviewer is registered no next step carries the claim
        // command; it points to registering the reviewer in Start your team.
        function reviewerReady() {
          return (state.reviewer || {}).registered === true ||
            !!(teamView && teamView.registered && teamView.registered.registered === true);
        }
        function teamGuide(g) {
          if (g.kind === "ready" && !reviewerReady())
            return { kind: g.kind, title: g.title, detail: "Next: register your reviewer in Start your team.", commands: [], steps: [] };
          return g.kind === "ready" && teamReady
            ? { kind: g.kind, title: g.title, detail: UAKWorkspace.format("Use the Start screen: its first command claims this task for {tool}.", { tool: teamTool }), commands: [], steps: [] }
            : g;
        }
        // UAK-160: a check the engine coded is written by the page from its code (UAKWorkspace.code); one without a code
        // (an older kit's `uak start`) keeps the old path through the gate's patterns.
        function drawNext(g) {
          g = teamGuide(g);
          el("next-heading").textContent = (g.code ? UAKWorkspace.code(g.code, g.values || {}) : UAKWorkspace.gate(UAKWorkspace.t(g.title || "Check what your project needs")));
          el("next-description").textContent = UAKWorkspace.t(g.detail || "");
          // Only `commands` (the exact claim command) is copyable; the gate's fix lines are text.
          var command = (g.commands || []).join("\n");
          el("next-command").textContent = command;
          el("next-command-box").hidden = !command;
          el("next-steps").replaceChildren();
          (g.items && g.items.length ? g.items.map(function (i) { return UAKWorkspace.code(i.code, i.values || {}); }) : (g.steps || []).map(function (line) { return UAKWorkspace.t(line); })).forEach(function (line) {
            var li = document.createElement("li");
            li.textContent = line;
            el("next-steps").append(li);
          });
          el("next-steps").hidden = !(g.items && g.items.length) && !(g.steps || []).length;
          el("next-check").hidden = ["check", "todo", "ready", "error", "waiting"].indexOf(g.kind) < 0;
          setWaiting(el("next-check"), state.phase);
          setLabel(el("next-check"), UAKWorkspace.t(
            g.kind === "check" ? "Check what’s next" : "Check again",
          ));
          el("copy-status").textContent = "";
          // Guided Beginner: why this step matters, and what the readiness check already passed.
          el("beginner-why").textContent = UAKWorkspace.t(
            {
              install:
                "The kit adds the files your coding tools read to work as a team.",
              todo: "Agents cannot start until this is done. The check below confirms it for you.",
              check:
                "It only reads your project; nothing is changed.",
              ready:
                "Your coding tool creates a separate workspace for this task, so agents never overwrite each other.",
              frozen:
                "After the deadline, new work needs a person's decision.",
              error: "Fix this first; the next step appears right after.",
              busy: "",
            }[g.kind] || "",
          );
          var done = state.completed || [];
          el("beginner-checklist").replaceChildren();
          done.forEach(function (line, at) {
            var li = document.createElement("li"),
              item = (state.completed_items || [])[at];
            li.append(icon("ok"), document.createTextNode(UAKWorkspace.gate(line)));
            if (item && item.code) li.lastChild.nodeValue = UAKWorkspace.code(item.code, item.values || {});
            el("beginner-checklist").append(li);
          });
          el("beginner-checklist").hidden = !done.length;
          el("beginner-done-label").hidden = !done.length;
          // A step that changed after an automatic re-check is announced, politely.
          if (lastStepTitle && g.title && g.title !== lastStepTitle && g.kind !== "busy")
            el("copy-status").textContent =
              UAKWorkspace.t("Step complete. Next:") + " " + UAKWorkspace.t(g.title);
          if (g.kind !== "busy") lastStepTitle = g.title || "";
        }
