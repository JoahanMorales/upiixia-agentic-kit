---
name: stack-frontend
description: Frontend conventions for the FastAPI + React stack (web/, Vite, React, TypeScript, Tailwind v4, Motion). Use when creating or changing any screen, component or style in web/, deciding visual design, or verifying UI in a browser.
---
# Frontend · FastAPI + React stack
Initial setup: `.uak/stacks/fastapi-react/STACK.md` (Frontend section).

```text
web/DESIGN.md                # the project's ONLY visual direction; owner: design task
web/src/App.tsx              # the shell (AppShell + NavBar from lib/ui), auto-discovers features; owner: design task
web/src/index.css            # Tailwind @theme tokens (font, color, radii); owner: design
web/src/lib/api.ts           # api<T>("/x") → fetch("/api/x"); owner: setup
web/src/features/<f>/index.tsx  # one folder per task: `export default` + `export const order = N`
```
A task reserves `web/src/features/<f>/`. `package.json`, the lockfile, `vite.config.ts`, `index.css`, `App.tsx`, `lib/` and `DESIGN.md` have owners: ask them with `uak msg <owner-ID> --kind request "file · change · why"`.

| Situation | Skill | Cost |
|---|---|---|
| Define the visual direction (once) | `/uak-design-lock` with `frontend-design` → `web/DESIGN.md`, tokens, UI kit, screenshots | medium, once |
| Landing or hero page | `landing-story` (the story from IDEA.md, real screens) + `frontend-design` for the look | medium; that page only |
| Product screens (dashboards, maps with panels, forms, lists) | `product-ui` + `web/DESIGN.md` (your screen's recipe row) + the locked screen with that recipe in `web/public/design-lock/screens/` + the UI kit in `web/src/lib/ui` | low; every screen |
| React performance patterns | `vercel-react-best-practices`: read only the relevant `rules/<rule>.md` | low |
| Verify the UI works | `webapp-testing` (`with_server.py` + Playwright) | low if you print only the verdict |
| Polish during the freeze | `redesign-existing-projects` | medium |

Here there is no RSC or `next/font` (fonts come from `@fontsource`), Motion comes from `motion/react`, and icons from `@phosphor-icons/react`. Before `uak done` on a screen: capture it into `.uak-shots/<ID>/` and run the `design-critic` subagent (done checks its verdict).

Rules:
- Accessibility (AA, 18 px, 48 px targets, focus) is a floor every screen meets, never a style: no gray government-form look unless the human asks.
- Colors only from tokens and components only from `web/src/lib/ui`: `bash .uak/bin/design-lint` fails raw palette classes, hex colors and local copies.
- Call the backend only through `api<T>()`, under `/api`. Until an endpoint exists, use a labeled mock with the contract's shape.
- Every data view has loading (skeleton), empty and error states.
- No "Lorem ipsum", "John Doe" or "Acme". Respect `prefers-reduced-motion`.

```bash
npm --prefix web run dev       # Vite on :5173, proxy /api → API port
bash .uak/bin/q npm --prefix web run lint
bash .uak/bin/q npm --prefix web run build
bash .uak/bin/q uv run python .claude/skills/webapp-testing/scripts/with_server.py \
  --server "uv run uvicorn app.main:app --port $UAK_PORT" --port "$UAK_PORT" -- uv run python /tmp/check_<f>.py
```
The Playwright script prints one verdict line, saves screenshots to `/tmp/`, and fails on a missing element or a console error. Never paste the DOM into context.
