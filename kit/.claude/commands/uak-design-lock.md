---
model: opus
description: (sprint) Three visual directions with screenshots; the human picks; DESIGN.md is frozen
---
Only when `Mode: sprint`, before T0+1h. In any other mode, say so and stop.
1. Read `IDEA.md` §0–4 (brand, user, wow) and load the skill `design-taste-frontend`.
2. Propose 3 clearly different directions. Each has a name, a one-line intent, palette tokens (background, surface, text, accent, states), type, density, motion, and how the wow moment looks.
3. For each direction, build a static `web/public/design-lock/<n>.html` of the wow screen, and capture it at 1280×720 and 390×844 (skill `webapp-testing`).
4. Show the human the screenshots and recommend one, with a reason tied to the rubric. The human picks.
5. Write `web/DESIGN.md` (tokens, components, usage rules, 3 "never" rules) and the CSS tokens. Delete the losing proposals.
6. `bash .uak/bin/uak decision <contract-ID> --option "Direction <n>" --why "<human's pick>" --reversible no --authorized yes --class scope`.

From now on, any global visual change (theme, palette, type) needs a human-approved `uak decision`. At Hack-Nation 2026 we went through 4 visual directions in 8 h.
