# Stack · Next.js (App Router, TypeScript, Tailwind)

Setup for the first task and structure reference. Conventions: the `stack-nextjs` skill (+ `vercel-react-best-practices`).

## Structure

```text
src/app/layout.tsx · src/app/page.tsx   # owner: setup (the home lists features; nobody edits it after)
src/app/<f>/page.tsx                    # one route per task
src/app/api/<f>/route.ts                # its API route (GET/POST handlers)
src/components/<f>/                     # its components
src/lib/                                # shared helpers and types; owner: setup / contract task
tests/<f>.spec.ts                       # Playwright e2e per feature · src/**/*.test.ts with Vitest if used
package.json · package-lock.json · next.config.ts · tailwind setup   # single owner (setup)
```
A task reserves `src/app/<f>/, src/app/api/<f>/, src/components/<f>/, tests/<f>.spec.ts`: routes are folders, so claims stay disjoint.

## Setup (~5 min)

```bash
npx create-next-app@latest . --ts --app --eslint --tailwind --src-dir --import-alias "@/*" --use-npm
npm install --save-dev @playwright/test && npx playwright install chromium
mkdir -p tests src/components src/lib
```

## Product smoke

```bash
bash .uak/bin/uak init-smoke --command "npm ci --prefer-offline --no-audit --no-fund --loglevel=error && npm run lint && npm run build"
```

## Run

| Mode | Command |
|---|---|
| Development | `npm run dev -- -p $UAK_PORT` |
| Demo | `npm run build && npm start -- -p $UAK_PORT` |
| e2e | `npx playwright test tests/<f>.spec.ts` (point `baseURL` at `http://127.0.0.1:$UAK_PORT`) |
