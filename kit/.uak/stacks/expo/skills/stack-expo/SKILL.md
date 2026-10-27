---
name: stack-expo
description: Conventions for the Expo / React Native stack (Expo Router screens per task, components/<f>, lib owners). Use when adding a screen, component, navigation or API call in this app.
---
# Expo stack
Setup: `.uak/stacks/expo/STACK.md`.

| Rule | Why |
|---|---|
| One task = one route file or folder in `app/` + `components/<f>/`; `_layout.tsx` belongs to setup | disjoint claims |
| Native modules only with `npx expo install` and through the owner of `package.json`/`app.json` | config plugins change the build |
| API calls through `lib/api.ts` with a timeout and a labeled mock (`demo_data: true`) | the demo survives no network at the venue |
| Test on web first (`expo export --platform web` in smoke), then on one real device before the demo | the gate has no simulator |
| Every list has loading, empty and error states; tap targets at least 44 pt | reviewers check them |
| Screens follow `product-ui` and the design lock; colors only from the theme tokens, components only from `components/ui` (`bash .uak/bin/design-lint`) | at Chilangatón 10 views built their own colors and components and the UI was redone |

```bash
bash .uak/bin/q npx tsc --noEmit
```
