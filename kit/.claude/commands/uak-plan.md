---
model: opus
description: Planner. IDEA or spec → verifiable backlog graph, OWNERS and wave-1 contracts.
---
Read `.uak/PROJECT.md`, your mode's §Plan, `.uak/docs/GRAPH.md`, and then `IDEA.md` (sprint) or `docs/specs/*/plan.md` (marathon).

Produce in ONE pass, in the format of `.uak/templates/TASKS.template.md`:
1. `.uak/TASKS.md`:
   - **Setup P0.** It owns lockfiles, the app entry and config. Add every foreseeable dependency at once.
   - **Contract P0.** Schemas, fixtures and mocks, plus a provisional `web/DESIGN.md`.
   - **Spikes P0.** One 30-min spike per external risk (API, model, data).
   - **Features.** Vertical P0 → P1 → P2 tasks with disjoint `Paths` and an `Estimate`. In sprint, each maps to a rubric criterion.
   - **Demo and submission** (sprint): `Freeze-Allowed: yes`.
   - **Dependencies.** `Depends on:` holds only real hard dependencies. Anything that can work on a mock goes in `Uses contract:`.
2. `.uak/OWNERS.md` from `.uak/templates/OWNERS.template.md`, with only existing IDs.
3. `bash .uak/bin/uak graph --min-wave1 <number of agents>` and `bash .uak/bin/uak lint` → `LINT_OK`. If wave 1 is too narrow or the critical path is long, replace hard deps with contracts.
4. Show the human one screen: ID · title · P · rubric/spec · deps · wave · suggested agent, plus `uak graph --mermaid`. On approval, set `Backlog-Approved: yes`.
5. Commit `plan: backlog v1` and push to `main`. This is the only direct push to main, made by the planner with human approval.

Later waves:
- **sprint**: write the new tasks to a file, then `UAK_HUMAN=<human> bash .uak/bin/uak plan file.md`. They are claimable instantly.
- **marathon**: a reviewed `plan: <spec>` PR.
