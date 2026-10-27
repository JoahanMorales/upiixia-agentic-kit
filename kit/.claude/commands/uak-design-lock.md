---
model: opus
description: (sprint) Use before building UI screens: three visual directions with screenshots; the human picks one and DESIGN.md is frozen.
---
Only when `Mode: sprint`, before the "design lock" time of `uak clock`. In any other mode, say so and stop.
Short event (under 6 h): ONE direction, not three. Write `web/DESIGN.md` from `IDEA.md` and the brand in 10 minutes, capture the wow screen once, and let the human say yes or adjust. Then go to step 5.
Never skip the screenshots or the human's pick, and never take the direction from a sentence in `IDEA.md` or the plan: it is chosen by looking at it. A hackathon is judged on how it looks in 3 seconds on a projector. Accessibility in the rubric (contrast, size, plain language) is a floor every direction meets, never a style: no GOV.UK, USWDS or "public document" look unless the human asks for it. Demo dials: `DESIGN_VARIANCE` 6–8, `MOTION_INTENSITY` 4–6, `VISUAL_DENSITY` 4–6. Each direction has a brand color, a display font for headlines and a body font.
1. Read `IDEA.md` §0–4 (brand, user, wow) and load the skill `design-taste-frontend`.
2. Propose 3 clearly different directions. Each has a name, a one-line intent, palette tokens (background, surface, text, accent, states), type, density, motion, and how the wow moment looks.
3. For each direction, build a static `web/public/design-lock/<n>.html` of the wow screen, and capture it at 1280×720 and 390×844 (skill `webapp-testing`).
4. Show the human the screenshots and recommend one, with a reason tied to the rubric. The human picks.
5. Write `web/DESIGN.md` (tokens, components, usage rules, 3 "never" rules), the CSS tokens and the UI kit in `web/src/lib/ui/` (button, card or surface, chip, stat or number, section header, and the product's data badge), so every view builds on it. Keep the winning screenshots in `web/public/design-lock/` (the reference for `product-ui` and `design-critic`); delete the losing HTML.
6. `bash .uak/bin/uak decision <contract-ID> --option "Direction <n>" --why "<human's pick>" --reversible no --authorized yes --class scope`.

From now on, any global visual change (theme, palette, type) needs a human-approved `uak decision`. At Hack-Nation 2026 we went through 4 visual directions in 8 h.
