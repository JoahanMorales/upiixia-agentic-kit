---
name: stack-nextjs
description: Conventions for the Next.js App Router stack (src/app/<f>/, route handlers, Tailwind, Playwright). Use when adding a page, an API route, a component or a test in this repo.
---
# Next.js stack
Setup: `.uak/stacks/nextjs/STACK.md`. React performance rules: `vercel-react-best-practices` (read one rule file, not all).

| Rule | Why |
|---|---|
| One feature = `src/app/<f>/` + `src/app/api/<f>/` + `src/components/<f>/`; never edit another feature's folder | disjoint claims |
| Server Components by default; `"use client"` only for state, effects or browser APIs | smaller bundles |
| Data from `src/app/api/<f>/route.ts` or server code; external calls with a timeout and a labeled mock (`demo_data: true`) | the demo survives a dead API |
| Shared types and helpers in `src/lib/` belong to their owner: ask with `uak msg ID --kind request` | one writer per contract |
| Dependencies: ask the owner of `package.json`; never commit a lockfile from a feature task | lockfiles go to the human queue |
| Secrets only in `.env.local` (git-ignored), read on the server; never `NEXT_PUBLIC_` for a secret | the scanner blocks them |
| Every data view has loading, empty and error states | reviewers check them |

```bash
bash .uak/bin/q npm run lint && bash .uak/bin/q npx playwright test tests/<f>.spec.ts
```
