        function drawProject(data) {
          var kk = kitFiles(data), proj = folderName(data.target);
          // What will happen here, in two sentences.
          el("project-says").textContent = data.detected
            ? UAKWorkspace.format("Setup adds the kit to {folder}: about {n} files, and none of your own files are replaced.", { folder: proj, n: kk.total || 0 }) + " " + UAKWorkspace.t("Nothing is committed or pushed until you publish.")
            : "";
          var d = data.detected, has = !!data.target;
          el("project-where").hidden = !has;
          el("project-form").hidden = has && !formOpen;
          el("selected-project").textContent = tilde(data.target || ""); el("selected-project").title = data.target || "";
          el("change-folder").textContent = UAKWorkspace.t(formOpen ? "Keep this folder" : "Change");
          var list = el("found");
          list.replaceChildren();
          list.hidden = !d;
          if (d) {
            var t = UAKWorkspace;
            list.append(foundRow("Repository", d.repo === "new" ? t.t("New: no commits yet") : t.format("Existing: {n} commits", { n: d.commits })));
            list.append(foundRow("Hooks", d.hooks ? t.format("{name}: it keeps its hooks; the kit's checks are called from it", { name: d.hooks }) : t.t("No hook manager: the kit sets its own")));
            list.append(foundRow("CI", d.ci || t.t("None found")));
            list.append(foundRow("Tests", d.tests || t.t("None found"), !!d.tests));
            list.append(foundRow("Stack", d.stack ? (el("stack").querySelector('option[value="' + d.stack + '"]') || {}).textContent || d.stack : t.t("Not recognised")));
            var p = proposal(d);
            if (p) {
              if (!modePicked && !document.querySelector("input[name=mode]:checked") && !data.can_repair) {
                var radio = document.querySelector("input[name=mode][value=" + p.mode + "]");
                if (radio) radio.checked = true;
              }
              el("tag-marathon").hidden = p.mode !== "marathon";
              el("tag-sprint").hidden = p.mode !== "sprint";
              el("mode-reason").textContent = p.reason;
            }
            if (!stackPicked && d.stack && el("stack").value === "none") el("stack").value = d.stack;
          }
          var repair = !!data.can_repair, mode = (data.settings || {}).Mode;
          document.querySelectorAll("input[name=mode]").forEach(function (input) { if (repair && mode) { input.disabled = input.value !== mode; if (input.value === mode) input.checked = true; } });
        }
        function drawInstall(data) {
          var k = kitFiles(data), d = data.detected || {}, busy = isBusy(data.phase);
          el("install-says").textContent = k.total
            ? UAKWorkspace.format("Installing adds about {n} files to {folder}. Nothing is committed or pushed.", { n: k.total, folder: folderName(data.target) })
            : UAKWorkspace.format("Installing adds the kit's files to {folder}. Nothing is committed or pushed.", { folder: folderName(data.target) });
          var facts = el("install-facts");
          facts.replaceChildren();
          facts.append(foundRow("Hooks", d.hooks
            ? UAKWorkspace.format("Your {name} hooks stay as they are. Call the kit's checks from its pre-commit: bash .uak/githooks/pre-commit", { name: d.hooks })
            : UAKWorkspace.t("The kit sets git's hooks path to .uak/githooks: the secret scan runs on every commit.")));
          facts.append(foundRow("Your files", UAKWorkspace.t("Existing files are kept. A file that differs is saved beside it as .uak-new.")));
          el("install").hidden = !!data.installed && !busy && !data.can_repair;
          el("status-heading").hidden = !(busy || data.error);
          el("operation-status").hidden = !el("operation-status").textContent;
          drawWindow("install", folderName(data.target) + " · " + UAKWorkspace.t("what will be written"), installRows(data), [[k.total ? "~" + k.total : "–", "files added"], [String(k.tools.length), "tools"], ["0", "files replaced"]]);
        }
        function installRows(data) {
          var k = kitFiles(data), f = k.files, rows = [["", folderName(data.target) + "/", ""]];
          rows.push(["add", "  .uak/ " + UAKWorkspace.t("engine, docs, templates"), f.base ? "~" + f.base : ""]);
          var names = { claude: "Claude Code", codex: "Codex", cursor: "Cursor", gemini: "Gemini CLI" };
          k.tools.forEach(function (t) { rows.push(["add", "  ." + t + "/ " + names[t], f["." + t] ? String(f["." + t]) : ""]); });
          rows.push(["add", "  AGENTS.md  .mcp.json", ""]);
          rows.push(["mod", "  .gitignore", "lines added"]);
          rows.push(["keep", "  your code", "untouched"]);
          return rows;
        }
        // The browser writes only what grants no authority: the test rule here, the diagnostics and the pacing. Who may
        // review and how a change merges are read from .uak/PROJECT.md on main; they are shown, never written (SECURITY.md).
        var RULE_NAMES = { "Test-First": ["rule-test-first", "warn"] };
        var RULE_WORDS = {
          "Test-First": { yes: "Required", warn: "Warn only", no: "Off" },
          "Review-Mode": { claims: "Inside the kit", gh: "On GitHub", auto: "Automatic" },
          "Review-Independence": { agent: "Another agent", human: "Another human's agent" },
          "Auto-Merge": { yes: "Automatic", no: "A human" },
        };
        function ruleValues(data) {
          var out = {};
          Object.keys(RULE_NAMES).forEach(function (key) {
            out[key] = rulesDirty ? el(RULE_NAMES[key][0]).value : (data.settings || {})[key] || RULE_NAMES[key][1];
          });
          return out;
        }
        function shownRule(data, key, fallback) {
          var value = (data.settings || {})[key] || fallback;
          return RULE_WORDS[key][value] ? RULE_WORDS[key][value] : value;
        }
        function drawRules(data) {
          var mode = modeOf(data), values = ruleValues(data), file = data.settings || {}, sprint = mode === "sprint";
          if (!rulesDirty) {
            Object.keys(RULE_NAMES).forEach(function (key) { el(RULE_NAMES[key][0]).value = values[key]; });
            el("diagnostics").checked = file.Blackbox === "on";
            el("pacing").checked = file.Pace !== "off";
          }
          el("rules-mode").textContent = UAKWorkspace.format("These are the defaults of {mode} mode. Nothing is written until you confirm.", { mode: UAKWorkspace.t(sprint ? "Hackathon" : "Product") });
          var list = el("rules-list");
          list.replaceChildren();
          function item(title, why, value, where) {
            var li = document.createElement("li"), left = document.createElement("span"), strong = document.createElement("strong"), small = document.createElement("span"), val = document.createElement("span");
            strong.textContent = UAKWorkspace.t(title); small.className = "why"; small.textContent = UAKWorkspace.t(why); val.className = "val"; val.textContent = UAKWorkspace.t(value);
            if (where) val.append(" ", pill(where === "here" ? "set here" : "in PROJECT.md", where === "here" ? "int" : ""));
            left.append(strong, small); li.append(left, val); list.append(li);
          }
          item("Tests come first", "An agent writes the failing test before the code.", RULE_WORDS["Test-First"][values["Test-First"]], "here");
          item("Where reviews happen", "Another identity reviews every change before it merges.", shownRule(data, "Review-Mode", sprint ? "claims" : "gh"), "file");
          item("Who may review", "An agent of another human, or any other agent identity.", shownRule(data, "Review-Independence", "agent"), "file");
          item("Merging", "What happens after a review approves a change.", shownRule(data, "Auto-Merge", sprint ? "yes" : "no"), "file");
          item("The merge engine", "A change to the merge gate itself always goes to a human.", "Human", "file");
          item("Generated files", "Files a command writes, so a change to them is checked, not reviewed by eye.", "None declared", "file");
          item("Token budget", sprint ? "Agents checkpoint after 100 events in a session." : "Agents checkpoint after 150 events in a session.", sprint ? "100 events" : "150 events");
          var cmd = el("rules-cmd");
          cmd.replaceChildren();
          var lead = document.createElement("p"); lead.className = "hint"; lead.textContent = UAKWorkspace.t("The rules marked in PROJECT.md grant authority, so the browser never writes them. Change them there with a reviewed pull request:");
          cmd.append(lead, copyRow("open-rules", inProject("${EDITOR:-nano} .uak/PROJECT.md")));
          var rows = [["", ".uak/PROJECT.md", ""]], changed = 0;
          function line(key, now, before) {
            var differs = now !== before;
            changed += differs ? 1 : 0;
            rows.push([differs ? "mod" : "keep", "  " + key + ": " + now, differs ? "was " + before : "as is"]);
          }
          Object.keys(RULE_NAMES).forEach(function (key) { line(key, values[key], file[key] || RULE_NAMES[key][1]); });
          line("Blackbox", el("diagnostics").checked ? "on" : "off", file.Blackbox || "on");
          line("Pace", el("pacing").checked ? "auto" : "off", file.Pace || "auto");
          rows.push(["keep", "  " + UAKWorkspace.t("every other line"), UAKWorkspace.t("as is")]);
          drawWindow("rules", ".uak/PROJECT.md · " + UAKWorkspace.t("lines that change"), rows, [[String(changed), "lines change"], [String(rows.length - 2 - changed + 1), "stay as they are"], ["0", "files outside .uak/"]]);
        }

        function drawSchedule(data) {
          var done = stepsDone(data), start = Date.parse(el("schedule-start").value), end = Date.parse(el("schedule-end").value), rows = [];
          el("go-schedule").hidden = !done.schedule;
          var figs = [["–", "event"], ["–", "freeze before the end"], ["0", "tasks started"]];
          function when(ms) { return new Date(ms).toLocaleString(UAKWorkspace.language(), { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); }
          if (start && end && end > start) {
            var length = end - start, freeze = Math.min(6 * 3600e3, Math.max(30 * 60e3, length * 0.15));
            rows = [["add", UAKWorkspace.t("Start"), when(start)], ["mod", UAKWorkspace.t("Freeze"), when(end - freeze)], ["", UAKWorkspace.t("End"), when(end)]];
            figs = [[Math.round(length / 360e3) / 10 + " h", "event"], [Math.round(freeze / 6e4) + " min", "freeze before the end"], ["0", "tasks started"]];
          } else rows = [["keep", UAKWorkspace.t("Choose the start and the end"), ""]];
          drawWindow("schedule", UAKWorkspace.t("the clock"), rows, figs);
        }



        function drawUnblock(data) {
          var rows = [], g = data.guidance || {};
          if (data.branch && data.branch.wrong) rows.push(["mod", UAKWorkspace.t("Branch"), data.branch.head || ""]);
          if (g.terminal) rows.push(["mod", UAKWorkspace.t("Needs a terminal"), ""]);
          if (!rows.length) rows.push(["keep", UAKWorkspace.t("Nothing blocks the next step"), ""]);
          drawWindow("unblock", UAKWorkspace.t("what is blocked"), rows, [[String(rows.length), "problems"], ["0", "files changed"], ["–", "waiting"]]);
          var wrong = !!(data.branch && data.branch.wrong);
          // One problem at a time: the branch first; the terminal steps when it is on the right branch.
          el("branch-warning").hidden = !wrong;
          el("setup-branch-warning").hidden = true; // the same warning as the one above, from the old Check step
          el("terminal-step").hidden = wrong || !g.terminal;
          document.querySelectorAll("#screen-unblock .next-command code").forEach(function (c) { c.title = c.textContent; });
          setLabel(el("unblock-again"), UAKWorkspace.t(wrong ? "Check project folder again" : "Check again"));
        }
        function drawProjectWindow(data) {
          var k = kitFiles(data);
          drawWindow("project", folderName(data.target) + " · " + UAKWorkspace.t("what will be written"), installRows(data), [[k.total ? "~" + k.total : "–", "files added"], [String(k.tools.length), "tools"], ["0", "files replaced"]]);
        }


        // ---- the late screens: a bordered list of rows, a window that shows the real thing, one primary below
        function tilde(path) {
          var home = state.home || "", p = String(path || "");
          return home && p.indexOf(home) === 0 ? "~" + p.slice(home.length) : p;
        }
        // The line the person sees must work as typed: a home folder becomes ~ only where the path needs no quoting
        // (cd ~/proyectos/tienda-api), otherwise the full quoted path stays. Copy always puts the full line.
        function shown(command) {
          var home = state.home || "", text = String(command);
          if (!home) return text;
          var escaped = home.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          return text.replace(new RegExp("'" + escaped + "(/[A-Za-z0-9_./-]*)'", "g"), "~$1");
        }
        // One command in one line: the text is cut visually, the whole line is what Copy puts on the clipboard.
        // UAK-192: every copy box names its action. When the server's table says the action has a button (it runs here,
        // or opens a terminal window), the button comes beside the copy box; the page sends the NAME, never the command.
        var RUN_UI = {
          "start-agent": { label: "Start this agent", what: "Starting the agent" },
          "deploy-help": { label: "Show how to deploy", what: "Deploy help", details: true },
          "smoke": { label: "Run the smoke test", what: "Smoke test", details: true },
          "skill-add": { label: "Add the skill", what: "Adding the skill", input: "Skill name", details: true },
          "readiness": { label: "Check now", what: "Readiness check", details: true },
          "open-rules": { label: "Open PROJECT.md", what: "Opening PROJECT.md" },
        };
        var runLocal = {}, runInput = {};
        function runKind(name) { var a = (state.run_actions || {})[name]; return a ? a.kind : ""; }
        function runsActive(data) {
          return Object.keys((data || {}).runs || {}).some(function (n) { return data.runs[n].state === "running"; });
        }
        function plainRow(full) {
          var row = document.createElement("div"), code = document.createElement("code"), button = document.createElement("button");
          row.className = "copyrow";
          code.textContent = shown(full); code.title = full; code.dataset.noI18n = ""; code.dataset.full = full;
          button.type = "button"; button.className = "secondary-button"; button.textContent = UAKWorkspace.t("Copy");
          button.onclick = function () {
            var done = function () { button.textContent = UAKWorkspace.t("Copied"); setTimeout(function () { button.textContent = UAKWorkspace.t("Copy"); }, 1600); };
            try { navigator.clipboard.writeText(full).then(done, function () {}); } catch (e) {}
          };
          row.append(code, button);
          return row;
        }
        function copyRow(name, full, fields) {
          var row = plainRow(full), kind = runKind(name);
          return kind === "run" || kind === "terminal" ? runControl(name, fields || {}, row) : row;
        }
        function runWords(name, key, fields) {
          // [text, isError, tail, open] of the line under the button, from what the server says and what the click got.
          var ui = RUN_UI[name], local = runLocal[key] || {}, job = (state.runs || {})[name], agent = (state.agents || {})[fields.role];
          var what = UAKWorkspace.t(ui.what), t = job ? String(job.seconds) : "";
          if (local.error) return [UAKWorkspace.t(local.sentence), true, [], false];
          if (name === "start-agent")
            return agent ? [UAKWorkspace.format("Opened a terminal window for {tool} at {time}. It is yours: it stays open if you close the wizard.", { tool: agent.tool, time: clock(new Date(agent.at * 1000)) }), false, [], false] : ["", false, [], false];
          if (!job) return ["", false, [], false];
          if (job.state === "running") return ["", false, job.tail, false];
          if (job.state === "done") return [UAKWorkspace.format("{what}: done in {time} s.", { what: what, time: t }), false, job.tail, !!ui.details];
          if (job.state === "stopped") return [UAKWorkspace.format("{what} was stopped after {time} s.", { what: what, time: t }) + " " + UAKWorkspace.t("Stopped. Nothing is left running."), false, job.tail, false];
          return [UAKWorkspace.format("{what} failed after {time} s.", { what: what, time: t }) + (job.advice ? " " + UAKWorkspace.t(job.advice) : ""), true, job.tail, true];
        }
        function runControl(name, fields, row) {
          var ui = RUN_UI[name], key = name + (fields.role ? ":" + fields.role : ""), box = document.createElement("div"), bar = document.createElement("div");
          var job = (state.runs || {})[name], running = !!(job && job.state === "running"), local = runLocal[key] || {};
          var go = document.createElement("button"), words = runWords(name, key, fields), input = null;
          box.className = "runctl"; box.dataset.action = name; bar.className = "run-bar";
          if (ui.input) {
            input = document.createElement("input"); input.type = "text"; input.autocomplete = "off"; input.spellcheck = false;
            input.placeholder = "frontend-design"; input.setAttribute("aria-label", UAKWorkspace.t(ui.input)); input.value = runInput[key] || "";
            input.oninput = function () { runInput[key] = input.value; input.removeAttribute("aria-invalid"); if (runLocal[key]) runLocal[key].field = false; };
            // UAK-160: a name the server refused is marked invalid and read with its message (the field's own error).
            if (local.field) { input.setAttribute("aria-invalid", "true"); input.setAttribute("aria-describedby", "run-status-" + key.replace(/[^a-z0-9]+/gi, "-")); }
            bar.append(input);
          }
          go.type = "button"; go.className = "secondary-button run-go";
          go.textContent = UAKWorkspace.t(running ? "Running…" : local.busy ? "Working…" : ui.label);
          go.disabled = running || !!local.busy;
          if (go.disabled) go.setAttribute("aria-busy", "true");
          go.onclick = function () {
            if (runLocal[key] && runLocal[key].busy) return;
            runAction(key, name, input ? { name: input.value.trim() } : fields);
          };
          bar.append(go);
          if (running) {
            var stop = document.createElement("button"), time = document.createElement("span");
            stop.type = "button"; stop.className = "secondary-button run-stop"; stop.textContent = UAKWorkspace.t("Stop");
            stop.onclick = function () { stopRun(); };
            time.className = "run-time"; time.textContent = UAKWorkspace.format("Running: {what}, {time} s", { what: UAKWorkspace.t(ui.what), time: job.seconds });
            bar.append(stop, time);
          }
          var status = document.createElement("p");
          status.className = "run-status" + (words[1] ? " error" : ""); status.setAttribute("role", "status"); status.dataset.noI18n = "";
          status.id = "run-status-" + key.replace(/[^a-z0-9]+/gi, "-");
          status.textContent = words[0];
          box.append(bar, row, status);
          if (words[2].length) {
            var tech = document.createElement("details"), sum = document.createElement("summary"), pre = document.createElement("pre");
            tech.className = "run-tech"; tech.open = words[3] || running; sum.textContent = UAKWorkspace.t("Technical details"); pre.textContent = words[2].join("\n"); pre.dataset.noI18n = "";
            tech.append(sum, pre); box.append(tech);
          }
          return box;
        }
        async function runAction(key, name, fields) {
          if (runLocal[key] && runLocal[key].busy) return;
          runLocal[key] = { busy: true };
          drawScreens(state);
          try {
            var answer = await api("run", Object.assign({ action: name }, fields));
            runLocal[key] = name === "start-agent" && !answer.opened ? { error: true, sentence: answer.sentence } : {};
          } catch (e) {
            if (e.gone) return;
            runLocal[key] = { error: true, sentence: e.message, field: !!(e.body && e.body.field === "name") };
          }
          await refresh();
          drawScreens(state);
        }
        async function stopRun() {
          try { await api("run/stop", {}); } catch (e) { if (e.gone) return; }
          await refresh();
        }
        // A box is drawn again only when what it shows changed: a poll must not take the focus out of a field.
        function redraw(box, sig, build) {
          var text = JSON.stringify(sig);
          if (box.dataset.sig === text) return;
          box.dataset.sig = text;
          build();
        }
        // A refusal that names the git command to run puts it in a copy box, next to the step's list.
        function showFix(text) {
          var box = el("publish-fix"), found = /\((git [^)]+)\)/.exec(String(text || ""));
          box.replaceChildren();
          box.hidden = !found;
          if (found) { var h = document.createElement("h2"); h.className = "sec"; h.textContent = UAKWorkspace.t("Run this in a terminal, then try again"); box.append(h, copyRow("publish-way-out", inProject(found[1]))); }
        }
        function inProject(command) { return state.target ? "cd '" + String(state.target).replace(/'/g, "'\\''") + "' && " + command : command; }
        function pill(text, kind) {
          var s = document.createElement("span");
          s.className = "pill" + (kind ? " p-" + kind : ""); s.textContent = UAKWorkspace.t(text);
          return s;
        }
        function plainText(text) { return String(text || "").replace(/<[^>]*>/g, ""); }
        function listRows(id, rows) {
          var box = el(id);
          box.replaceChildren();
          rows.forEach(function (row) {
            var li = document.createElement("li"), k = document.createElement("span"), v = document.createElement("span");
            k.className = "k"; v.className = "v";
            k.textContent = UAKWorkspace.t(row[0]);
            if (row[1] && row[1].nodeType) v.append(row[1]); else { v.textContent = row[1]; v.dataset.noI18n = ""; }
            (row.slice(2) || []).forEach(function (extra) { if (extra) v.append(" ", extra); });
            li.append(k, v); box.append(li);
          });
        }
        function followFooters() {
          document.querySelectorAll("[data-needs],[data-unless]").forEach(function (g) {
            var need = g.dataset.needs, unless = g.dataset.unless, hide = false;
            if (need) hide = !el(need) || el(need).hidden;
            if (unless) hide = !el(unless) || !el(unless).hidden;
            g.hidden = hide;
          });
          // A button of the bottom bar that stands for one in the page: it says what that one says and does what it does.
          document.querySelectorAll("[data-proxy]").forEach(function (bar) {
            var real = el(bar.dataset.proxy);
            if (!real) return;
            bar.textContent = real.textContent.trim();
            if (real.getAttribute("aria-disabled")) bar.setAttribute("aria-disabled", "true"); else bar.removeAttribute("aria-disabled");
            if (real.getAttribute("aria-busy")) bar.setAttribute("aria-busy", "true"); else bar.removeAttribute("aria-busy");
            bar.disabled = real.disabled;
            bar.onclick = function () { real.click(); };
          });
        }
        function drawPeople(data) {
          var done = stepsDone(data), who = data.human || data.git_human || "", view = teamView, roles = (view && view.roles) || {},
            onMain = (data.resume || {}).kit_on_main === true, registered = view && view.registered && view.registered.registered === true;
          el("go-people").hidden = !done.name;
          // The reviewer can be registered only on a kit that is on main: until then the person is told, and nothing is offered.
          if (!onMain) el("team-register").hidden = true;
          var names = { claude: "Claude Code", codex: "Codex", cursor: "Cursor", gemini: "Gemini CLI" };
          drawWindow("people", UAKWorkspace.t("people and roles"), [
            ["", UAKWorkspace.t("You"), who || UAKWorkspace.t("no name yet")],
            [registered ? "add" : "keep", UAKWorkspace.t("Your reviewer"), who ? who + "-r" : ""],
            ["", UAKWorkspace.t("Implements"), names[roles.implement] || roles.implement || "–"],
            ["", UAKWorkspace.t("Reviews"), names[roles.review] || roles.review || "–"],
            ["keep", UAKWorkspace.t("Reviewer"), registered ? UAKWorkspace.t("registered") : onMain ? UAKWorkspace.t("not registered yet") : UAKWorkspace.t("after the kit is on main")],
          ], [[who ? "1" : "0", "people"], [registered ? "1" : "0", "reviewers"], ["0", "agents running"]]);
        }
        function drawPublish(data) {
          var done = stepsDone(data), k = kitFiles(data), r = data.resume || {}, name = folderName(data.target);
          el("go-publish").hidden = !done.publish;
          listRows("publish-list", [
            ["Goes to main", k.total ? UAKWorkspace.format("the kit: about {n} files in .uak/, the agents' folders and AGENTS.md", { n: k.total }) : UAKWorkspace.t("the kit's files")],
            ["Stays local", UAKWorkspace.t("your code, your idea and your plan: they wait for your approval")],
            ["Destination", "origin/main"],
            ["Remote", r.kit_on_main === true ? UAKWorkspace.format("the kit is on main (commit {sha})", { sha: r.base_sha || "" }) : r.kit_on_main === false ? UAKWorkspace.t("main does not have the kit yet") : UAKWorkspace.t("not read yet: Review the files reads it")],
          ]);
          drawWindow("publish", name + " · " + UAKWorkspace.t("what goes to main"), [
            ["add", ".uak/", k.base ? "~" + k.base : ""],
            ["add", "AGENTS.md  .mcp.json", ""],
          ].concat(k.tools.map(function (t) { return ["add", "." + t + "/", k.files["." + t] ? String(k.files["." + t]) : ""]; })).concat([
            ["keep", UAKWorkspace.t("your code"), UAKWorkspace.t("stays local")],
            ["keep", "IDEA.md  TASKS.md", UAKWorkspace.t("after you approve")],
          ]), [[done.publish ? "1" : "0", "commit pushed"], [k.total ? "~" + k.total : "–", "files"], ["0", "of your own files"]]);
        }
        var ideaEditing = false;
        function planStage(data) {
          if ((data.resume || {}).plan_approved === true) return "done";
          if (planView && planView.planned) return "review";
          return planView && planView.idea ? "draft" : "idea";
        }
        function drawPlanWin(data) {
          var done = stepsDone(data), cards = (planView && planView.cards) || [], stage = planStage(data), order = ["idea", "draft", "review", "done"];
          el("go-plan").hidden = !done.plan;
          var form = ideaEditing || stage === "idea" || stage === "draft";
          el("screen-plan").setAttribute("data-stage", form ? "idea" : "review");
          Array.from(el("plan-stages").querySelectorAll("li")).forEach(function (li) {
            var at = order.indexOf(li.dataset.stage), now = order.indexOf(stage);
            li.classList.toggle("done", at < now || stage === "done");
            if (at === now && stage !== "done") li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
          });
          var recap = el("idea-recap"), have = !form && stage !== "idea" && stage !== "draft";
          recap.hidden = !have; el("idea-edit-line").hidden = !have;
          if (have) {
            var text = (planView && planView.idea) || "", pick = function (re) { var m = re.exec(text); return m ? plainText(m[1].trim()) : ""; };
            listRows("idea-recap", [["Idea", el("idea-text").value || pick(/## 1\. One line\n(.+)/) || "–"], ["For", el("idea-audience").value || pick(/^For: (.+)$/m) || "–"],
              ["Team", [pick(/Team size: (.+)/) || el("idea-team").value, pick(/Length: (.+)/) || el("idea-length").value].filter(Boolean).join(" · ") || "–"]]);
          }
          var design = data.design || {};
          el("design-block").hidden = !design.screens;
          if (design.screens) {
            listRows("design-list", [["Direction", design.locked ? UAKWorkspace.t("locked in web/DESIGN.md") : UAKWorkspace.t("not locked yet")],
              ["Creativity index", String(design.creativity) + " / 5"], ["Rounds made", String(design.rounds)]]);
            var box = el("design-cmds");
            box.replaceChildren();
            if (!design.locked) box.append(copyRow("design-round", inProject("bash .uak/bin/uak design round")), copyRow("design-gallery", inProject("bash .uak/bin/uak design-gallery")));
          }
          var rows = [["add", "IDEA.md", ""], ["add", ".uak/TASKS.md", cards.length ? cards.length + " " + UAKWorkspace.t("tasks") : ""], ["add", ".uak/OWNERS.md", ""], ["mod", ".uak/PROJECT.md", "Backlog-Approved: yes"]];
          if (design.screens) rows.push([design.locked ? "keep" : "mod", "web/DESIGN.md", design.locked ? UAKWorkspace.t("locked") : UAKWorkspace.t("not locked yet")]);
          drawWindow("plan", UAKWorkspace.t("what approval publishes"), rows, [[String(cards.length || "–"), "tasks"], [String(design.screens ? 5 : 4), "files"], [done.plan ? "yes" : "no", "approved"]]);
          followFooters();
        }
        function agentRow(role, tool, state, pillKind, command, note, key) {
          var li = document.createElement("li"), head = document.createElement("div"), title = document.createElement("strong");
          head.className = "head"; title.textContent = UAKWorkspace.t(role) + " · " + tool; title.dataset.noI18n = "";
          head.append(title, pill(state, pillKind));
          li.append(head);
          if (note) { var n = document.createElement("span"); n.className = "why"; n.textContent = UAKWorkspace.t(note); li.append(n); }
          if (command) li.append(copyRow("start-agent", command, { role: key }));
          return li;
        }
        function drawStart(data) {
          var view = teamView || {}, byId = {}, claimed = view.claimed || [], list = el("agents-list"), names = { claude: "Claude Code", codex: "Codex", cursor: "Cursor", gemini: "Gemini CLI" };
          (view.commands || []).forEach(function (c) { byId[c.id] = c; });
          var count = teamView && teamView.claimed ? claimed.length : (data.resume || {}).claims || 0, roles = view.roles || {};
          var impl = byId.implement, rev = byId.review, locked = view.locked;
          var registered = view.registered && view.registered.registered === true;
          redraw(list, [view, count, state.runs, state.agents, runLocal, state.run_actions], function () {
            list.replaceChildren();
            if (view.reviewer || impl) {
              list.append(agentRow("Implements", (impl && impl.tool) || names[roles.implement] || "–", count ? UAKWorkspace.format("claimed {id}", { id: (claimed[0] && (claimed[0].id || claimed[0])) || "" }) : "waiting", count ? "prog" : "", impl ? impl.command : "", locked ? locked.reason : "", "implement"));
              list.append(agentRow("Reviews", (rev && rev.tool) || names[roles.review] || "–", registered ? "waiting" : "needs a reviewer", registered ? "" : "blk", rev ? rev.command : "", registered ? "" : "Register the reviewer on the People screen first.", "review"));
            }
          });
          el("start-hint").textContent = /Win/.test(navigator.platform || "") ? UAKWorkspace.t("On Windows, paste these in Git Bash, not PowerShell.") : "";
          el("note-start").textContent = count
            ? (count === 1 ? UAKWorkspace.t("1 task claimed: an agent has started.") : UAKWorkspace.format("{n} tasks claimed: an agent has started.", { n: count }))
            : UAKWorkspace.t("No agent has claimed a task yet. This page tells you when one does.");
          drawWindow("start", UAKWorkspace.t("your agents"), [
            [count ? "add" : "keep", UAKWorkspace.t("Implements"), count ? UAKWorkspace.format("claimed {id}", { id: (claimed[0] && (claimed[0].id || claimed[0])) || "" }) : UAKWorkspace.t("waiting")],
            [registered ? "keep" : "mod", UAKWorkspace.t("Reviews"), registered ? UAKWorkspace.t("waiting") : UAKWorkspace.t("needs a reviewer")],
            ["", UAKWorkspace.t("Claimed tasks"), String(count)],
          ], [[String(count), "tasks claimed"], [registered ? "1" : "0", "reviewers"], ["0", "tasks integrated"]]);
        }
        function drawUpdate(data) {
          var v = data.versions || {};
          listRows("update-list", [["Kit in this project", v.installed || "?"], ["Kit in this setup", v.current || "?"],
            ["Your rules", UAKWorkspace.t("kept: .uak/PROJECT.md is not replaced")], ["A file you changed", UAKWorkspace.t("kept; the new version is saved beside it as .uak-new")], ["Your code", UAKWorkspace.t("untouched")]]);
          var k = kitFiles(data);
          drawWindow("update", folderName(data.target) + " · " + UAKWorkspace.t("what the update changes"), [["mod", ".uak/", (v.installed || "?") + " → " + (v.current || "?")], ["mod", "AGENTS.md  .claude/  .codex/", UAKWorkspace.t("if unedited")], ["keep", UAKWorkspace.t("your code"), UAKWorkspace.t("untouched")]],
            [["1", "kit updated"], [k.total ? "~" + k.total : "–", "files"], ["0", "files of yours replaced"]]);
        }
        function drawDashboardWin(data) {
          var p = (latestDashboard || {}).progress, s = (p && p.states) || {}, tasks = (latestDashboard || {}).tasks || [];
          var rows = [["", UAKWorkspace.t("Mode"), modeOf(data) === "sprint" ? UAKWorkspace.t("Hackathon") : UAKWorkspace.t("Product")], ["", UAKWorkspace.t("Tasks"), p ? String(p.total) : "–"]];
          drawWindow("dashboard", folderName(data.target) + " · " + UAKWorkspace.t("progress"), rows, [[String(s.INTEGRATED || 0) + (p ? " / " + p.total : ""), "completed"], [String(s.CLAIMED || 0), "working"], [String(s.REVIEW || 0), "in review"]]);
          document.querySelectorAll("#more .cmd[data-cmd]").forEach(function (box) {
            var name = box.dataset.action;
            redraw(box, [box.dataset.cmd, state.target, state.runs && state.runs[name], runLocal[name], state.run_actions], function () { box.replaceChildren(copyRow(name, inProject(box.dataset.cmd))); });
          });
        }
