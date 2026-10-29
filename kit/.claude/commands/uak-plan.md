---
model: opus
description: Use when turning IDEA.md or a spec into tasks: a verifiable backlog graph with Paths, Verify, owners and wave-1 contracts.
---
Read `.uak/PROJECT.md`, your mode's §Plan, `.uak/docs/GRAPH.md`, and then `IDEA.md` (sprint) or `docs/specs/*/plan.md` (marathon).

**Short event (`uak clock` printed SHORT EVENT, under 6 h):** you have until its "first claim by" time (20 min in a 4 h event). At Reap, planning a 4 h event took 1.5 h and the freeze arrived 1 h after the first claim. So: at most 2 tasks per agent, each 45 min or less; no spikes unless an external API is the product; Setup + Contract may be one task; skip the mermaid graph and show the table only; later work goes in wave 2 with `uak plan`.

Produce in ONE pass, in the format of `.uak/templates/TASKS.template.md`:
1. `.uak/TASKS.md`:
   - **Setup P0.** It owns lockfiles, the app entry and config. Add every foreseeable dependency at once, and the deploy files (`bash .uak/bin/uak deploy --write`: Dockerfile and a Render Blueprint, or Vercel for Next.js), so the walking skeleton deploys from its first merge. Why (Chilangatón): the deploy file was hand-written 30 min before the deadline.
   - **Contract P0.** Schemas, fixtures and mocks.
   - **Design lock P0** (any project with screens): its own task in wave 1, 30–45 min, run with `/uak-design-lock`, never merged into another task. Paths: `web/DESIGN.md`, the tokens (`web/src/index.css`), `web/src/lib/ui/`, the shell `web/src/App.tsx`, `web/public/design-lock/`. Verify: `test -s web/DESIGN.md && ls web/public/design-lock/screens/*-1280.png && bash .uak/bin/uak lint`. Every UI task's Acceptance names its row of the DESIGN.md table: `Recipe: <map + panel | dashboard | detail | flow | list> · Hero: <element>` (`uak lint` warns without it). A late polish task gets the shell and the UI kit in its Paths, or the design task does it. Why (Hacktoberfest): ten screens copied the one locked screen, and a nav restyle was rejected as "outside Paths". Never write the visual direction into the plan or the acceptance: the human picks it from screenshots. Every UI task lists it in `Depends on:`, so no view is built on improvised styles; until it lands, those agents take data and API tasks. Why (Chilangatón): the plan said "no time for 3 directions: the one in Appendix D (sober, public-document look)", the task shared 40 min with the map component, and 10 views started on their own colors and components; the UI was redone 3 hours in.
   - **Spikes P0.** One 30-min spike per external risk (API, model, data).
   - **Landing P0** (any product with a web UI, sprint and marathon): the page judges or users open first, built with the skill `landing-story` from `IDEA.md` (the one line, a sourced number, the wow as a real screen, three steps, the ask). It depends on the design lock and uses real screenshots of the app, so in sprint it lands in the last wave before the freeze with `Freeze-Allowed: yes`. Verify: `npm --prefix web run build && bash .uak/bin/design-lint` plus screenshots at 1280×720 and 390×844. Why (Chilangatón): the landing was a late task of a redesign wave, and the jury opened it first.
   - **Features.** Vertical P0 → P1 → P2 tasks with disjoint `Paths` and an `Estimate`. In sprint, each maps to a rubric criterion.
   - **Demo and submission** (sprint): `Freeze-Allowed: yes`.
   - **Dependencies.** `Depends on:` holds only real hard dependencies. Anything that can work on a mock goes in `Uses contract:`.
2. `.uak/OWNERS.md` from `.uak/templates/OWNERS.template.md`, with only existing IDs.
3. `bash .uak/bin/uak graph --min-wave1 <number of agents>` and `bash .uak/bin/uak lint` → `LINT_OK`. If wave 1 is too narrow or the critical path is long, replace hard deps with contracts.
4. Show the human one screen: ID · title · P · rubric/spec · deps · wave · suggested agent, plus `uak graph --mermaid`. On approval, set `Backlog-Approved: yes`.
5. Commit `plan: backlog v1` and push to `main`. This is the only direct push to main, made by the planner with human approval.

Later waves:
- **sprint**: write the new tasks to a file, then `UAK_HUMAN=<human> bash .uak/bin/uak plan file.md`. They are claimable instantly. A published task needs more Paths or a new Verify before its review: the same file format with `uak plan file.md --amend`.
- **marathon**: a reviewed `plan: <spec>` PR.
