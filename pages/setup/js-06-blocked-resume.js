        function onBlockedClick(event) {
          var button = event.target && event.target.closest ? event.target.closest('button[aria-disabled="true"]') : null;
          if (!button) return;
          event.preventDefault();
          event.stopImmediatePropagation();
          showToast({ text: button.dataset.blockedText, target: button.dataset.blockedTarget }, button);
        }
        document.addEventListener("click", onBlockedClick, true);
        el("toast").addEventListener("mouseenter", pauseToast);
        el("toast").addEventListener("mouseleave", resumeToast);
        el("toast").addEventListener("focusin", pauseToast);
        el("toast").addEventListener("focusout", function (event) {
          if (!event.relatedTarget || !el("toast").contains(event.relatedTarget)) resumeToast();
        });
        el("toast-close").onclick = function () {
          var back = toastFrom;
          hideToast();
          if (back) back.focus();
        };
        el("toast-go").onclick = function () {
          var id = this.dataset.target;
          hideToast();
          pointTo(id);
        };
        document.addEventListener("keydown", function (event) {
          if (event.key === "Escape" && !el("toast").hidden) el("toast-close").onclick();
        });
        // UI-024 (D-6.1, QA round D): a button natively disabled during an operation said nothing. It is blocked like
        // any other: focusable, aria-disabled, and its click says what it waits for. The button that started the
        // operation keeps its busy label (UI-018).
        var BUSY_REASON = {
          installing: "Wait: the kit is being installed.",
          checking: "Wait: setup is checking your project.",
          planning: "Wait: the coding tool is drafting the plan.",
          approving: "Wait: the plan is being approved.",
          publishing: "Wait: the kit is being published.",
          registering: "Wait: the reviewer is being registered.",
        };
        function setWaiting(button, phase, why) {
          if (!button) return;
          var busy = isBusy(phase),
            owner = busy && phaseOwner(phase) === button;
          button.disabled = owner;
          setBlocked(button, owner ? null : busy ? { text: BUSY_REASON[phase] } : why || null);
        }
        // UI-024 (A-F6): Claude Code's trust question starts on "No, exit" and an English warning comes first. Whether
        // Claude Code already trusts the folder (true, false, or null: unknown), and how to answer; undefined hides it.
        var TRUST_LINES = [
          "Before it, you may see an English warning such as \"Ignoring 51 permissions.allow entries … has not been trusted\". That is expected the first time and goes away once you accept.",
          "The question starts on \"No, exit\": press ↓ until \"Yes, proceed\" is selected, then press Enter.",
          "If you pressed Enter on \"No, exit\", Claude Code closes: paste the same command again.",
        ];
        var TRUST_WORDS = /(No, exit|Yes, proceed|Ignoring 51 permissions\.allow entries … has not been trusted|↓|Enter)/;
        function trustText(text) {
          var line = document.createElement("p");
          line.className = "hint";
          String(text)
            .split(TRUST_WORDS)
            .forEach(function (part, i) {
              if (!part) return;
              if (i % 2 === 0) return line.append(part);
              // What the terminal shows stays English; keys are keys.
              var key = part === "↓" || part === "Enter",
                node = document.createElement(key ? "kbd" : "span");
              if (!key) node.setAttribute("lang", "en");
              node.textContent = part;
              line.append(node);
            });
          return line;
        }
        function trustLine(box, value) {
          if (!box) return;
          box.replaceChildren();
          box.hidden = value === undefined;
          if (value === undefined) return;
          var head = document.createElement("p"),
            mark = document.createElement("span"),
            text = document.createElement("span");
          mark.className = "trust-mark";
          function drawn(kind) { if (!document.createElementNS) return null; var NS = "http://www.w3.org/2000/svg", s = document.createElementNS(NS, "svg"), p = document.createElementNS(NS, "path"); s.setAttribute("viewBox", "0 0 16 16"); s.setAttribute("class", "ic"); s.setAttribute("aria-hidden", "true"); p.setAttribute("d", { ok: "M3 8.5l3 3 7-7", no: "M4 4l8 8M12 4l-8 8", todo: "M8 3.5v6M8 12.5v.5", info: "M8 7.5v5M8 4v.5" }[kind]); s.appendChild(p); return s; }
          var shape = drawn(value === true ? "ok" : value === false ? "no" : "info");
          if (shape) mark.append(shape);
          mark.setAttribute("aria-label", UAKWorkspace.t(value === true ? "Trusted" : value === false ? "Not trusted yet" : "Not known"));
          text.textContent =
            " " +
            UAKWorkspace.t(
              value === true
                ? "Claude Code already trusts this folder."
                : value === false
                  ? "Claude Code does not trust this folder yet, so it will ask first."
                  : "Setup could not read whether Claude Code trusts this folder. If it asks, answer as below.",
            );
          head.append(mark, text);
          box.append(head);
          if (value !== true)
            TRUST_LINES.forEach(function (line) {
              box.append(trustText(UAKWorkspace.t(line)));
            });
          var mcp = document.createElement("p"),
            again = document.createElement("button");
          mcp.className = "hint";
          mcp.textContent = UAKWorkspace.t("Then approve this project's uak server (MCP).");
          again.type = "button";
          again.className = "link-button trust-recheck";
          again.textContent = UAKWorkspace.t("Check again");
          // After accepting in the terminal, the mark turns from not trusted to trusted: setup reads Claude Code's config again.
          again.onclick = function () {
            if (box.dataset.reload === "plan") loadPlan();
            else loadTeam();
          };
          box.append(mcp, again);
        }
        // The checklist is redrawn only when its data changes, so polling never rebuilds (or resizes) it.
        // UI-024 (A-F7): while a check runs the last list stays, dimmed and marked busy, until the new one arrives.
        function drawChecks(data) {
          var list = el("checks"),
            waiting = data.phase === "checking";
          list.classList.toggle("stale", waiting);
          if (waiting) list.setAttribute("aria-busy", "true");
          else list.removeAttribute("aria-busy");
          if (waiting) return false;
          var registered = (data.reviewer || {}).registered === true;
          var key = JSON.stringify([UAKWorkspace.language(), data.checks || [], !!data.ready, data.guidance || null, registered]);
          if (key === checksKey) return false;
          checksKey = key;
          el("checks").replaceChildren();
          (data.checks || []).forEach(function (check) {
            var li = document.createElement("li"),
              mark = document.createElement("span"),
              word = document.createElement("span"),
              text = document.createElement("span");
            li.className = check.state;
            function drawn(kind) { if (!document.createElementNS) return null; var NS = "http://www.w3.org/2000/svg", s = document.createElementNS(NS, "svg"), p = document.createElementNS(NS, "path"); s.setAttribute("viewBox", "0 0 16 16"); s.setAttribute("class", "ic"); s.setAttribute("aria-hidden", "true"); p.setAttribute("d", { ok: "M3 8.5l3 3 7-7", no: "M4 4l8 8M12 4l-8 8", todo: "M8 3.5v6M8 12.5v.5", info: "M8 7.5v5M8 4v.5" }[kind]); s.appendChild(p); return s; }
            mark.className = "mk mk-" + (check.state === "ok" ? "ok" : check.state === "todo" ? "todo" : "info");
            var shape = drawn(check.state === "ok" ? "ok" : check.state === "todo" ? "todo" : "info");
            if (shape) mark.append(shape);
            word.className = "sr-only";
            word.textContent = UAKWorkspace.t(check.state === "ok" ? "Passed" : check.state === "todo" ? "Action needed" : "Information");
            mark.append(word);
            // The gate's first line in the page's language.
            // The lines under it (doctor's failures, the fix) through the catalog: a command stays as it is (UI-012).
            var lines = String(check.text || "").split("\n");
            text.textContent = check.code
              ? [UAKWorkspace.code(check.code, check.values || {})].concat((check.hints || []).map(function (h) { return UAKWorkspace.code(h.code || "", h.values || {}); })).join("\n")
              : [UAKWorkspace.gate(lines[0])].concat(lines.slice(1).map(function (line) {
                  var indent = line.match(/^\s*/)[0];
                  return indent + UAKWorkspace.t(line.slice(indent.length));
                })).join("\n");
            li.append(mark, text);
            el("checks").append(li);
          });
          if (data.ready) {
            // The next action is visible here, never only in Technical details.
            var li = document.createElement("li"),
              text = document.createElement("span"),
              code = document.createElement("code"),
              progress = document.createElement("button");
            li.className = "ready-next";
            text.textContent = UAKWorkspace.t("Next: run this in your coding tool's terminal.");
            code.dataset.noI18n = "";
            var ready = data.guidance || {};
            // UI-024 (A-F11, D-3.2): the claim command waits for the reviewer; until then this line points there.
            code.textContent = registered ? (ready.commands || []).join("\n") : "";
            code.hidden = !code.textContent;
            if (!registered) text.textContent = UAKWorkspace.t("Next: register your reviewer in Start your team.");
            else if (code.hidden) text.textContent = UAKWorkspace.t(ready.detail || "Your project is ready");
            progress.type = "button";
            progress.className = "primary";
            progress.textContent = UAKWorkspace.t(registered ? "See project progress" : "Register the reviewer");
            progress.onclick = function () {
              if (!registered) {
                openSection("setup");
                pointTo("team-register");
                return;
              }
              openSection("dashboard");
              loadDashboard();
            };
            li.append(text, code, progress);
            el("checks").append(li);
          }
          return true;
        }
        // UI-018 feedback: end
        // UI-019 resume: begin. Dylan's live run and the QA rounds of 2026-11-14 (A-F2, A-F3, A-F4, A-F8, A-F11, B-04,
        // B-05, B-14): after a refresh, a restart or re-picking the project the page landed on Welcome or Prepare with
        // empty forms, offered publishing and "Create the plan" for an approved plan, and a closed setup showed a raw
        // "Failed to fetch" while polling forever. The server says where the project is (status.resume, from local Git);
        // this block lands there, folds finished steps, keeps the tab and the drafts of a reload, and says once when setup
        // has closed. Storage is per port (a restart is a new origin): it only helps a reload, never decides a step.
        var SAVED_PREFIX = "uak-setup:v1:",
          SAVED_DAYS = 7,
          DRAFT_MAX = 20000,
          DRAFT_FIELDS = ["human-name", "team-name", "schedule-start", "schedule-end", "schedule-zone", "idea-text",
            "idea-audience", "idea-goal", "idea-length", "idea-team"],
          GONE_TEXT = "Setup has closed: run the command again and open the new link.",
          PROBE_DELAYS = [2000, 4000, 8000, 16000, 30000, 30000],
          gone = false,
          probeTries = 0,
          probeTimer = null,
          autoCheckedFor = "",
          checkAuto = false,
          landedFor = "",
          draftTimer = null;
        function savedKey(target) {
          return SAVED_PREFIX + target;
        }
        // What a reload of this tab may restore for TARGET; {} for anything unexpected (old, foreign, another version).
        function readSaved(target) {
          if (!target) return {};
          try {
            var raw = localStorage.getItem(savedKey(target));
            if (!raw) return {};
            var saved = JSON.parse(raw);
            if (!saved || typeof saved !== "object" || Array.isArray(saved) || saved.v !== 1 || saved.target !== target)
              return {};
            if (typeof saved.at !== "number" || Date.now() - saved.at > SAVED_DAYS * 864e5) return {};
            if (saved.section !== undefined && ["setup", "dashboard"].indexOf(saved.section) < 0) return {};
            var drafts = {};
            if (saved.drafts && typeof saved.drafts === "object")
              DRAFT_FIELDS.forEach(function (id) {
                if (typeof saved.drafts[id] === "string") drafts[id] = saved.drafts[id].slice(0, DRAFT_MAX);
              });
            var out = { v: 1, target: target, at: saved.at, drafts: drafts };
            if (saved.section) out.section = saved.section;
            if (saved.rules === true) out.rules = true;
            return out;
          } catch (e) {
            return {};
          }
        }
        function writeSaved(target, patch) {
          if (!target) return;
          var saved = readSaved(target),
            next = { v: 1, target: target, at: Date.now(), drafts: saved.drafts || {} };
          if (saved.section) next.section = saved.section;
          if (patch.rules === true || saved.rules === true) next.rules = true;
          if (patch.section === "setup" || patch.section === "dashboard") next.section = patch.section;
          Object.keys(patch.drafts || {}).forEach(function (id) {
            var value = patch.drafts[id];
            if (DRAFT_FIELDS.indexOf(id) < 0) return;
            if (value === null || value === undefined || value === "") delete next.drafts[id];
            else next.drafts[id] = String(value).slice(0, DRAFT_MAX);
          });
          try {
            localStorage.setItem(savedKey(target), JSON.stringify(next));
          } catch (e) {}
        }
        // Where the page opens: the server's step decides; a reload keeps the tab the person had chosen.
function landing(data, saved, wanted) {
          data = data || {};
          return { screen: wanted && allowed(wanted, data) ? wanted : screenFor(data, saved) };
        }
        // A step is done only on evidence (null: no local copy to read, never drawn as done).
        function stepsDone(data) {
          var resume = (data && data.resume) || {};
          return {
            name: !!(data && data.human),
            schedule: resume.freeze > 0,
            publish: resume.kit_on_main === true,
            plan: resume.plan_approved === true,
          };
        }
        function planningVisible(data) {
          return !!data.installed && !data.ready && data.phase !== "installing" &&
            (data.resume || {}).plan_approved !== true;
        }
        function shouldAutoCheck(data) {
          return !!data && !!data.installed && !data.checked && !data.ready && !data.error && !isBusy(data.phase) &&
            data.phase !== "installed" && !requestBusy && !gone && !(data.branch && data.branch.wrong) &&
            autoCheckedFor !== data.target + ":" + data.inspect;
        }
        function probeDelay(n) {
          return PROBE_DELAYS[n];
        }
        // A field gets its draft back only when it is empty and not being typed in; a value from the server wins.
        function restoreDrafts(saved) {
          var drafts = (saved && saved.drafts) || {},
            resume = (state && state.resume) || {};
          Object.keys(drafts).forEach(function (id) {
            var node = el(id);
            if (!node || node.value || document.activeElement === node) return;
            if ((id === "human-name" || id === "team-name") && state && state.human) return;
            if (id.indexOf("idea-") === 0 && resume.idea) return;
            node.value = drafts[id];
          });
        }
        function saveDrafts() {
          draftTimer = null;
          var drafts = {};
          DRAFT_FIELDS.forEach(function (id) {
            var node = el(id);
            if (node) drafts[id] = node.value || null;
          });
          writeSaved(state && state.target, { drafts: drafts });
        }
        function dropDrafts(ids) {
          var drafts = {};
          ids.forEach(function (id) {
            drafts[id] = null;
          });
          writeSaved(state && state.target, { drafts: drafts });
        }
        DRAFT_FIELDS.forEach(function (id) {
          var node = el(id);
          if (!node) return;
          node.addEventListener("input", function () {
            clearTimeout(draftTimer);
            draftTimer = setTimeout(saveDrafts, 300);
          });
        });
        // The check runs by itself once per inspect (B-04): no focus move, no toast, no tab switch (A-F11).
        function maybeAutoCheck(data) {
          if (!shouldAutoCheck(data)) return;
          autoCheckedFor = data.target + ":" + data.inspect;
          startCheck(false);
          lastButton = currentSection === "dashboard" ? "next-check" : "check";
          checkAuto = true;
          checkStarting = true;
          syncRunningControls();
          api("check", {}).then(
            function () {
              checkRequested = true;
              return refresh().then(function () { checkStarting = false; syncRunningControls(); });
            },
            function (e) {
              checkAuto = false;
              checkStarting = false;
              syncRunningControls();
              if (!e.gone && e.status === 400) failed(checkOwner(), e.message);
            },
          );
        }
        // Finished steps: one done line and a folded body (A-F4, A-F8). Unknown (null) keeps what is drawn.
        function markDone(id, done, text) {
          var step = el(id),
            line = el(id.replace("-form", "").replace("-step", "") + "-done");
          if (done === null || done === undefined) return;
          if (done) step.setAttribute("data-done", "");
          else {
            step.removeAttribute("data-done");
            step.removeAttribute("data-open");
          }
          line.hidden = !done;
          el(line.id + "-text").textContent = done ? text : "";
        }
        function drawDone(data) {
          var resume = data.resume || {},
            done = stepsDone(data),
            kit = planView && planView.kit_on_main === true ? true : resume.kit_on_main;
          markDone("name-step", done.name, UAKWorkspace.format("Saved: {name}.", { name: data.human || "" }));
          markDone("schedule-form", typeof resume.freeze === "number" ? done.schedule : null,
            UAKWorkspace.format("Freeze set: {when}.", {
              when: resume.freeze ? new Date(resume.freeze * 1000).toLocaleString(UAKWorkspace.language()) : "",
            }));
          markDone("publish-step", kit === true ? true : kit === false ? false : null,
            UAKWorkspace.format("Published on main (commit {sha}).", { sha: resume.base_sha || "?" }));
          var approved = !!data.installed && resume.plan_approved === true;
          el("plan-done").hidden = !approved;
          el("plan-done").replaceChildren();
          if (approved)
            el("plan-done").append(icon("ok"), document.createTextNode(UAKWorkspace.format("Plan approved on main (commit {sha}).", { sha: resume.base_sha || "?" })));
        }
        ["name", "schedule", "publish"].forEach(function (name) {
          var button = el(name + "-reopen");
          if (!button) return;
          button.onclick = function () {
            var step = el(name === "schedule" ? "schedule-form" : name + "-step");
            step.setAttribute("data-open", "");
            var first = step.querySelector(".step-body input, .step-body button");
            if (first) first.focus();
          };
        });
        // Setup has closed (A-F3): one translated banner, nothing left busy, a few probes that back off, then stop.
        function serverLost(e) {
          if (!gone) {
            gone = true;
            el("server-gone-text").textContent = UAKWorkspace.t(GONE_TEXT);
            el("server-gone").hidden = false;
            clearTimeout(timer);
            timer = null;
            clearTimeout(dashboardTimer);
            dashboardTimer = null;
            Object.keys(BUSY_LABEL).forEach(function (id) {
              if (el(id)) setBusy(el(id), false);
            });
            Object.keys(PHASE_BUTTONS).forEach(function (phase) {
              PHASE_BUTTONS[phase].forEach(function (id) {
                if (el(id)) setBusy(el(id), false);
              });
            });
            probeTries = 0;
            scheduleProbe();
          }
          var lost = Error(UAKWorkspace.t(GONE_TEXT));
          lost.gone = true;
          lost.cause = e;
          return lost;
        }
        function scheduleProbe() {
          clearTimeout(probeTimer);
          probeTimer = null;
          if (document.hidden) return; // back in view, the visibilitychange below asks once
          var delay = probeDelay(probeTries);
          if (delay === undefined) return;
          probeTries += 1;
          probeTimer = setTimeout(probe, delay);
        }
        function probe() {
          clearTimeout(probeTimer);
          probeTimer = null;
          return api("status").then(serverBack, function () {
            if (gone) scheduleProbe();
          });
        }
