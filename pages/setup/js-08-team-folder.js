        function drawTeam(view) {
          var wasLocked = !!(teamView && teamView.locked);
          teamView = view;
          var reviewer = view.registered || {};
          el("team-step").hidden = false;
          el("team-name-block").hidden = true;
          el("team-reviewer").hidden = false;
          el("team-reviewer-name").textContent = view.reviewer;
          el("team-register").textContent = UAKWorkspace.format("Register {name}", { name: view.reviewer });
          // Unknown (offline) or retired: no Register button and no claim about the reviewer's state.
          el("team-register").hidden = reviewer.registered !== false || !!reviewer.retired;
          el("team-reviewer-status").textContent = reviewer.retired
            ? UAKWorkspace.t(reviewer.message || "")
            : reviewer.registered === null
              ? UAKWorkspace.format("{name}'s registration could not be read right now.", { name: view.reviewer })
              : reviewer.registered
                ? UAKWorkspace.format(
                    reviewer.registered_by && reviewer.registered_by !== view.human
                      ? "{name} was already registered by {by}."
                      : "{name} is registered: it reviews your agents' work.",
                    { name: view.reviewer, by: reviewer.registered_by || "" },
                  )
                : "";
          var byId = {};
          (view.commands || []).forEach(function (c) { byId[c.id] = c; });
          el("team-note").hidden = !view.note;
          el("team-note").textContent = UAKWorkspace.t(view.note || "");
          technical(el("team-note"), (view.note && view.technical) || "");
          el("team-review-note").hidden = !view.review_note || view.review_note === view.note;
          el("team-review-note").textContent = UAKWorkspace.t(view.review_note || "");
          el("team-retry").hidden = !view.retry;
          el("team-check").hidden = !view.can_check;
          el("team-note-actions").hidden = !view.retry && !view.can_check;
          drawRoles(view);
          // UI-024 (D-3.2): before the reviewer is registered both blocks are placeholders: what each terminal will
          // run, no command and no Copy button, and the one reason above them.
          var locked = view.locked || null,
            waiting = {};
          (view.waiting || []).forEach(function (w) { waiting[w.id] = w; });
          el("team-locked-why").hidden = !locked;
          el("team-locked-why").textContent = locked ? UAKWorkspace.t(locked.reason) : "";
          // A view drawn during a check may be outdated: dimmed, and its Copy buttons say why (B-10).
          el("team-step").classList.toggle("stale", !!view.stale);
          ["copy-team-implement", "copy-team-resume", "copy-team-review"].forEach(function (id) {
            setBlocked(el(id), view.stale ? { text: BUSY_REASON[state.phase] || BUSY_REASON.checking } : null);
          });
          // A-F19: with two or more people, who runs what.
          el("team-two-people").hidden = view.people === 1;
          var trust = view.trust || {},
            TERMINAL = {
              implement: "Terminal 1: a new terminal window on your computer, any folder",
              review: "Terminal 2: another new terminal window on your computer, any folder",
            };
          [["implement", "2. {tool} implements", "worktree"], ["review", "3. {tool} reviews", "project"]].forEach(function (row) {
            var id = row[0],
              block = el("team-" + id),
              shown = byId[id] || waiting[id];
            block.hidden = !shown;
            if (!shown) return;
            block.querySelectorAll(".next-command").forEach(function (box) { box.hidden = !byId[id]; });
            block.querySelectorAll(".resume-only").forEach(function (line) { line.hidden = !byId[id]; });
            el("team-" + id + "-heading").textContent = UAKWorkspace.format(row[1], { tool: shown.tool });
            el("team-" + id + "-terminal").textContent = UAKWorkspace.t(byId[id] ? byId[id].terminal : TERMINAL[id]);
            el("team-" + id + "-command").textContent = byId[id] ? byId[id].command : "";
            if (id === "implement") el("team-implement-resume").textContent = byId[id] ? byId[id].resume : "";
            block.querySelectorAll("[data-tool]").forEach(function (p) { p.hidden = p.dataset.tool !== shown.harness; });
            // A-F6: Claude Code's trust question, answered before it is asked.
            trustLine(el("team-" + id + "-trust"), shown.harness === "claude" && view.trust ? trust[row[2]] : undefined);
          });
          if (wasLocked && !locked && byId.implement) el("team-implement-heading").focus();
          drawClaimed(view);
          teamReady = !!byId.implement;
          teamTool = byId.implement ? byId.implement.tool : "Claude Code";
          drawPeople(state); drawStart(state);
          var guide = (latestDashboard && latestDashboard.guidance) || state.guidance || {};
          drawNext(guide);
          drawAdvancedNext(guide);
        }
        // UI-019: the team step asks for what it needs (the name, A-F2) instead of hiding; only these blocks show then.
        function teamAsk(need, message) {
          el("team-step").hidden = false;
          ["team-reviewer", "team-roles", "team-implement", "team-review", "team-claimed-block", "team-note-actions",
            "team-review-note"].forEach(function (id) {
            el(id).hidden = true;
          });
          el("team-name-block").hidden = need !== "human";
          el("team-note").hidden = need === "human";
          el("team-note").textContent = need === "human" ? "" : UAKWorkspace.t(message);
          if (need === "human") {
            el("team-name-status").textContent = UAKWorkspace.t(message);
            if (!el("team-name").value) el("team-name").value = el("human-name").value || "";
          }
        }
        var teamTries = 0;
        async function loadTeam() {
          var step = (state.resume || {}).step;
          if (gone) return;
          if (!state.ready && !state.team && step !== "team" && step !== "progress" && currentScreen !== "start" && currentScreen !== "people") {
            el("team-step").hidden = true;
            return;
          }
          try {
            drawTeam(await api("team"));
            teamTries = 0;
          } catch (e) {
            var need = (e.body || {}).need;
            if (e.gone) return;
            // A refusal (400) says what it needs, or hides the step; a busy server or a network error keeps what is drawn.
            if (e.status === 400 && need === "human") teamAsk("human", e.message);
            else if (e.status === 400 && need === "check" && (!state.checked || isBusy(state.phase)))
              teamAsk("check", "Checking your project…");
            else if (e.status === 400) {
              el("team-step").hidden = true;
            } else {
              // The operation that just ended may still be finishing: ask again shortly, a few times.
              if (e.status === 409 && teamTries < 3) {
                teamTries += 1;
                setTimeout(loadTeam, 1500);
              }
              if (!el("team-step").hidden) {
                el("team-note").hidden = false;
                el("team-note").textContent = UAKWorkspace.t(e.message);
              }
            }
          }
        }
        el("team-name-save").onclick = function () {
          var name = el("team-name").value.trim().toLowerCase();
          action(this, async function () {
            var answer = await api("human", { name: name });
            humanNote = answer.note || "";
            el("team-name-status").textContent = humanNote ? UAKWorkspace.t(humanNote) : "";
            el("human-name").value = name;
            dropDrafts(["team-name", "human-name"]);
            await refresh();
            await loadTeam();
          });
        };
        window.addEventListener("uak:language", function () {
          if (teamView && !el("team-step").hidden) drawTeam(teamView);
        });
        // UI-024 (A-F6): back from the terminal where Claude Code asked about trust, the trust mark is read again.
        document.addEventListener("visibilitychange", function () {
          if (!document.hidden && teamView && !el("team-step").hidden && !operationBusy() && !requestBusy) loadTeam();
        });
        el("team-retry").onclick = function () {
          action(this, loadTeam);
        };
        el("team-check").onclick = function () {
          el("next-check").click();
        };
        el("copy-publish-way-out").onclick = function () {
          copyText(el("publish-way-out-command").textContent, "publish-way-out-status");
        };
        el("copy-publish-way-out-push").onclick = function () {
          copyText(el("publish-way-out-push").textContent, "publish-way-out-status");
        };
        // UI-020 (B-01, Dylan's live run): the branch this folder is on, and the remote's default branch.
        el("copy-branch-warning").onclick = function () {
          copyText(el("branch-warning-command").textContent, "branch-warning-status");
        };
        el("copy-setup-branch-warning").onclick = function () {
          copyText(el("setup-branch-warning-command").textContent, "setup-branch-warning-status");
        };
        function drawBranch(data) {
          var branch = (data && data.branch) || {};
          ["branch-warning", "setup-branch-warning"].forEach(function (id) {
            el(id).hidden = !branch.wrong;
            el(id + "-text").textContent = branch.wrong ? UAKWorkspace.t(branch.message || "") : "";
            el(id + "-run").hidden = !(branch.wrong && branch.command);
            el(id + "-command").textContent = branch.wrong ? branch.command || "" : "";
          });
          var note = branch.remote_note ? UAKWorkspace.t(branch.remote_note) : "";
          el("branch-warning-remote").hidden = !note;
          el("branch-warning-remote").textContent = note;
          el("remote-default-warning").hidden = !note;
          el("remote-default-text").textContent = note;
          el("dashboard-remote-default").hidden = !note; // a ready project opens on the dashboard
          el("dashboard-remote-default").textContent = note;
        }
        window.addEventListener("uak:language", function () {
          drawBranch(state);
        });
        function drawWayOut(out, message) {
          el("publish-way-out").hidden = !out;
          if (!out) return;
          el("publish-way-out-error").textContent = UAKWorkspace.t(message || "");
          el("publish-way-out-run").hidden = !out.command;
          el("publish-way-out-command").textContent = out.command || "";
          el("publish-way-out-push-run").hidden = !out.push; // B-03: the push after the pull
          el("publish-way-out-push").textContent = out.push || "";
          el("publish-way-out-steps").replaceChildren();
          (out.steps || []).forEach(function (line) {
            var li = document.createElement("li");
            li.textContent = UAKWorkspace.t(line);
            el("publish-way-out-steps").append(li);
          });
        }
        el("team-register").onclick = function () {
          var name = el("team-reviewer-name").textContent;
          action(this, async function () {
            var answer = await api("team/reviewer", { confirm: name });
            if (answer.phase === "registering") {
              el("team-reviewer-status").textContent = UAKWorkspace.t("Registering the reviewer…");
              await refresh();
            }
            await loadTeam();
          });
        };
        el("copy-plan-trust").onclick = function () {
          copyText(el("plan-trust-command").textContent, "idea-status");
        };
        el("copy-plan-undo").onclick = function () {
          copyText(el("plan-undo-command").textContent, "plan-undo-status");
        };
        el("copy-team-implement").onclick = function () {
          copyText(el("team-implement-command").textContent, "team-copy-status");
        };
        el("copy-team-resume").onclick = function () {
          copyText(el("team-implement-resume").textContent, "team-copy-status");
        };
        el("copy-team-review").onclick = function () {
          copyText(el("team-review-command").textContent, "team-copy-status");
        };
        el("copy-advanced-next").onclick = function () {
          copyText(el("advanced-next-command").textContent, "team-copy-status");
        };
        el("copy-next-command").onclick = function () {
          var command = el("next-command").textContent;
          function done(ok) {
            el("copy-status").textContent = UAKWorkspace.t(
              ok
                ? "Copied. Paste it in your coding tool's terminal."
                : "Select the command and copy it.",
            );
          }
          if (navigator.clipboard && navigator.clipboard.writeText)
            navigator.clipboard.writeText(command).then(
              function () {
                done(true);
              },
              function () {
                done(false);
              },
            );
          else done(false);
        };
        el("dashboard-choose-project").onclick = function () {
          show(1);
        };
        el("dashboard-frame").onload = sendDashboard;
        window.addEventListener("message", function (event) {
          if (
            event.source !== el("dashboard-frame").contentWindow ||
            !event.data ||
            event.data.type !== "uak:dashboard-size"
          )
            return;
          var height = Number(event.data.height);
          if (Number.isFinite(height))
            el("dashboard-frame").style.height =
              Math.min(6000, Math.max(560, height)) + "px";
        });
        el("back-from-finish").onclick = function () { show("project"); };
        el("back-to-progress").onclick = function () { show(screenFor(state)); };
        el("begin").onclick = function () { show("project"); };
        el("project-form").onsubmit = function (event) {
          event.preventDefault();
          if (!checkFields(this)) return;
          clearFieldError(el("target"));
          // A refusal names its field: action() puts it under the field, above the buttons, and says so next to the button.
          action(el("check-folder"), async function () {
            await inspectFolder(el("target").value);
            formOpen = false;
            drawScreens(state);
          });
        };
        async function inspectFolder(target) {
          var previousTarget = state.target;
          state = await api("inspect", { target: target });
          drawBranch(state);
          if (previousTarget !== state.target) {
            latestDashboard = null;
            planView = null;
            teamView = null;
            teamFor = "";
            modePicked = stackPicked = rulesDirty = false;
            el("dashboard-frame").removeAttribute("src");
            el("beginner-dashboard").hidden = true;
            el("dashboard-frame").hidden = true;
            document.querySelectorAll("input[name=mode]").forEach(function (input) { input.disabled = false; input.checked = false; });
          }
          el("target").value = state.target || "";
          if (state.branch && state.branch.wrong) show("unblock", true);
          else if (state.installed || state.can_repair) landOn(state, landing(state, readSaved(state.target)), true);
          else show("project", false);
          maybeAutoCheck(state);
        }
        el("workflow-form").onsubmit = function (event) {
          event.preventDefault();
          var modes = document.querySelector("input[name=mode]:checked"),
            tools = chosenTools(),
            problem = el("workflow-error");
          problem.textContent = "";
          if (!state.target) {
            fieldError("target", UAKWorkspace.t("Enter the full path to an existing Git repository."));
            return;
          }
          if (state.installed && !state.can_repair) { show(screenFor(state), true); return; }
          if (!modes) {
            problem.textContent = UAKWorkspace.t("Choose Hackathon or Product before installing.");
            document.querySelector("input[name=mode]").focus();
            return;
          }
          if (!tools.length) {
            problem.textContent = UAKWorkspace.t("Choose at least one coding tool.");
            return;
          }
          choices = { mode: modes.value, harness: tools, stack: el("stack").value, solo: el("solo").checked, blackbox: el("blackbox").checked };
          var names = { claude: "Claude Code", codex: "Codex", cursor: "Cursor", gemini: "Gemini CLI" },
            rows = [
              ["Workflow", choices.mode === "sprint" ? "Hackathon or prototype" : "Product with real users"],
              ["Coding tools", tools.map(function (t) { return names[t] || t; }).join(", ")],
              ["Team", choices.solo ? "One human, independent agent reviewers" : "Multiple collaborators"],
              ["Technology preset", el("stack").selectedOptions[0].textContent],
              ["Kit diagnostics", choices.blackbox ? "On · stored on your coordination branch" : "Off"],
            ];
          el("summary").replaceChildren();
          rows.forEach(function (row) {
            var wrap = document.createElement("div"), term = document.createElement("dt"), value = document.createElement("dd");
            term.textContent = row[0];
            value.textContent = row[1];
            wrap.append(term, value);
            el("summary").append(wrap);
          });
          show("install", true);
        };
        el("install").onclick = function () {
          action(this, async function () {
            if (!choices.mode) { show("project", true); return false; }
            await api(state.can_repair ? "repair" : "install", choices);
            await refresh();
            // A quick install is over before the first poll sees it running: move on from here.
            if (state.installed && !isBusy(state.phase) && !state.error && currentScreen === "install") show(screenFor(state), true);
          });
        };
        el("repair").onclick = function () { el("update-run").click(); };
        el("change-project").onclick = function () {
          if (timer) clearTimeout(timer);
          formOpen = true;
          show("project", true);
        };
        // Prepare (UI-005). The page does the gate's terminal steps itself; anything else gets a terminal box.
        function storedHuman() {
          try {
            return localStorage.getItem("uak-human") || "";
          } catch (e) {
            return "";
          }
        }
        function localInput(date) {
          var pad = function (n) {
            return (n < 10 ? "0" : "") + n;
          };
          return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + "T" +
            pad(date.getHours()) + ":" + pad(date.getMinutes());
        }
