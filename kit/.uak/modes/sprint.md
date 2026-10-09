# Sprint mode · hackathons and fast AI prototypes

Goal: win the rubric with a demo people remember. Speed beats polish, and the frontend IS the product. `AGENTS.md` still applies; this file lists only what changes.

## Clock (T = official deadline)
| When | What | Who |
|---|---|---|
| T0 | The human chose `sprint` at install. `/uak-setup`: PROJECT.md (rubric, times, `Freeze-Epoch`) and `uak doctor` PASS on every machine, including "gh can create PRs". | human + agent |
| T0 | Product name and brand fixed in `IDEA.md`. Renaming after T-50% needs a human `uak decision`. | human |
| T0+30m | `/uak-plan` wave 1: contracts and mocks, walking skeleton, spikes. `uak graph --min-wave1 <agents>` passes. | planner |
| T0+1h | `/uak-design-lock`: 3 visual directions with screenshots; the human picks one; `web/DESIGN.md` and tokens frozen. | design agent + human |
| T0+2h | End-to-end walking skeleton up to the wow moment, on labeled mocks. | team |
| T-50% | First plan-B video of the whole flow. Wave 2 via `uak plan` (no PR). | demo |
| T-8h | A HUMAN owns submission: forms, platforms, videos, team roster. Never an agent low on tokens. | human |
| T-6h | Freeze (`Freeze-Epoch`): only `Freeze-Allowed: yes` demo fixes. | all |
| T-2h | Timed rehearsal from a clean clone, final plan-B video. | demo |
| T-1h | Submission sent and receipt saved. | human |

## Plan
1. Every P0 maps to a rubric criterion (`Rubric: C1`). If it scores no points, it is not P0.
2. Tasks take 60 min or less, with disjoint `Paths` per feature (`app/routers/<f>.py`, `web/src/features/<f>/`).
3. Wave 1 is wide: one task with no hard dependency per agent. Consumers use `Uses contract:` plus mocks.
4. At most 2 agents per human. More agents produce more messages than code.
5. Wave 2 onward: `UAK_HUMAN=<human> uak plan file.md` publishes tasks instantly, with no PR.
6. Start the team with `uak up <agents> --tmux`. Humans watch `uak board --watch 10` instead of asking agents for status.

## Speed
0. Orchestrate by cost (`.uak/docs/ORCHESTRATION.md`): Haiku scouts read, the Sonnet lead builds, and Opus is consulted only at plan lock, a repeated failure and done. The guard caps parallel subagents (4) and Opus subagents (2 per session). `uak pace` scales those with your 5-hour window, and fixed hard limits stop any runaway: 6 parallel, 3 Opus, 40 spawns per session, 8 per machine, 6 per minute, and 6 agents per `uak up`.
1. Mock first; switch to the real thing after its spike. Every mock shows `demo_data: true` in the UI.
2. Merge as soon as there is an `approve` and the gates are green (`Auto-Merge: yes`). The human gets a `digest`, not pings.
3. Stuck for 20 min, or the loop is stuck → `uak decision` with a reversible fallback, and move on.
4. Mechanical fixes (lint, types, a failing test with a clear error) go to `uak loop --verify <cmd> --agent <cli> --max 5`.
5. No free tasks: review PRs → demo-path tests → polish → rehearse.

## A stunning frontend (what judges see)
1. The wow moment happens within 90 s of the demo and is fully visible at 1280×720 (projector) without scrolling. Legal or "not a diagnosis" notices stay inside the viewport.
2. There is one visual direction in `web/DESIGN.md`, and every color comes from CSS tokens. A global redesign after the lock needs a human decision.
3. Every screen on the demo path has empty, loading, error and labeled sample-data states.
4. Before every UI PR, the `design-critic` subagent reviews screenshots at 1280×720 and 390×844. Fix its P1s before asking for review.
5. Skills:
   - `design-taste-frontend`, only for DESIGN.md and hero screens (it is large);
   - `redesign-existing-projects` during the freeze;
   - `webapp-testing` to verify.
6. Animations respect `prefers-reduced-motion`. UI checks run with reduced motion, so a slow GPU never fakes a failure.
7. On the demo path: AA contrast, visible focus, fully keyboard-operable.
8. Every number on screen has a source (tooltip or footnote). Judges ask "where does that number come from?".

## AI products
- Pin model IDs in one config file and check with a spike that they exist.
- Keep a recorded response per model call (`demo_data: true`) so the demo works offline and without keys. Add a `DEMO_MODE` switch.
- The LLM picks from given options and cites given IDs. Validate every model output against a schema before use.
- Use `mcp-builder` when the project exposes tools to agents.

## Defaults (`PROJECT.md`)
`Mode: sprint` · `Autonomy: yes` · `Auto-Merge: yes` · `Review-Mode: claims` · `Plan-Channel: claims` · `Lease-Seconds: 2700` · `Review-Lease-Seconds: 14400` · `Freeze-Epoch` required (`uak lint` and `uak doctor` fail without it).

## Submission checklist
- [ ] Product README in English: real screenshots, setup (`uv sync` / `npm ci`), `.env.example` variables, and how to run the demo with no keys.
- [ ] Videos within the event limits, with links open to judges.
- [ ] The demo is deployed, or reproducible from a clean clone in 5 min or less.
- [ ] Data and library licenses declared (non-commercial ones explicit).
- [ ] Submitted on EVERY platform the event requires, with a receipt.
- [ ] `/uak-retro` within 48 h: lessons improve this file.
