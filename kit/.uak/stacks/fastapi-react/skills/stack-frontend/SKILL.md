---
name: stack-frontend
description: Frontend conventions for the FastAPI + React stack (web/, Vite, React, TypeScript, Tailwind v4, Motion). Use when creating or changing any screen, component or style in web/, deciding visual design, or verifying UI in a browser.
---
# Frontend · FastAPI + React stack
Initial setup: `.uak/stacks/fastapi-react/STACK.md` (Frontend section).

```text
web/DESIGN.md                # the project's ONLY visual direction; owner: design task
web/src/App.tsx              # auto-discovers features; nobody edits it after setup
web/src/index.css            # Tailwind @theme tokens (font, color, radii); owner: design
web/src/lib/api.ts           # api<T>("/x") → fetch("/api/x"); owner: setup
web/src/features/<f>/index.tsx  # one folder per task: `export default` + `export const order = N`
```
A task reserves `web/src/features/<f>/`. `package.json`, the lockfile, `vite.config.ts`, `index.css`, `App.tsx`, `lib/` and `DESIGN.md` have owners: ask them with `uak msg --kind request`.

| Situation | Skill | Cost |
|---|---|---|
| Define the visual direction (once) | `design-taste-frontend` → writes `web/DESIGN.md` | high, once |
| Hero, landing, wow screen | `design-taste-frontend` (sections 4, 9, pre-flight 14) | high; those screens only |
| Product screens (forms, lists, panels) | `web/DESIGN.md` + loading/empty/error + AA contrast | low |
| React performance patterns | `vercel-react-best-practices`: read only the relevant `rules/<rule>.md` | low |
| Verify the UI works | `webapp-testing` (`with_server.py` + Playwright) | low if you print only the verdict |
| Polish during the freeze | `redesign-existing-projects` | medium |

`design-taste-frontend` assumes Next.js. Here there is no RSC or `next/font` (use `@fontsource`), Motion comes from `motion/react`, and icons from `@phosphor-icons/react`.

Rules:
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
