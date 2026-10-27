---
name: product-ui
description: Make product screens look designed, not templated - dashboards, a map or canvas with side panels, data views, detail pages, forms and flows, lists, mobile screens. Use whenever you build or change an app screen, a view or a component in web/ (the landing hero and the visual direction itself are design-taste-frontend). Covers layout recipes, hierarchy, craft, the 3-second judge test and the design-lint gate.
---

# Product UI · screens that look designed

The visual direction comes from `/uak-design-lock` (skill `frontend-design`); the landing is `landing-story`.
App screens are this skill. Why (Chilangatón, a 7-hour sprint): the first UI was a column of white boxes with gray borders, raw
`stone-*`/`emerald-*` classes, every label `text-lg font-semibold`, and each view with its own badge and toggle. It
was redone from scratch 3 hours in, and the team nearly lost on it.

## 0. Before the first line
1. Read `web/DESIGN.md` and open the locked screenshot in `web/public/design-lock/`. Your screen must look like the
   same product as that image.
2. Build from the UI kit (`web/src/lib/ui`, `web/src/lib/map`). A piece is missing? Ask its owner
   (`uak msg <design task> --kind request "component · variant · why"`). Never a local copy: copies drift.
3. Name the screen's one job and its hero (the map, the number, the route, the form) in one line of the PR.

## 1. Accessibility is a floor, not a style
AA contrast, 16–18 px body, 44–48 px targets, visible focus, plain language and the reduced-motion path are
mandatory. They never mean gray, flat or a government-form look. A social-impact or public-sector brief is still a
product judged in 3 seconds on a projector. Use GOV.UK or USWDS only when the human asks for them.

## 2. Pick one layout recipe per screen
| Screen | Recipe |
|---|---|
| Map or canvas + controls | The hero is full-bleed: no border, no card around it. One panel of 360–420 px at 1280 wide, ONE surface (solid or `glass`). Sections are separated by 24–32 px of space or a hairline, never a box each. Legend big, on the map. |
| Dashboard | One hero metric (display font, 48–72 px) and 2–4 supporting stats in a row, then one primary chart. Never a grid of 9 equal cards. |
| Detail / profile | A header band with the identity (name, mark, status chip, the primary action), then 2/3 main content and 1/3 facts. |
| Flow / form | One step or one group at a time, with a progress indicator. Labels above full-width inputs, the primary action sticky at the bottom. |
| List / results | Rows, not cards, past 6 items. Each row: a leading visual (icon, thumbnail or number), the title, meta in secondary text, a trailing value or action. |
| Empty, loading, error | Designed like the screen: skeletons shaped like the content, an empty state with one sentence and one action, an error that says the fix. |

## 3. Hierarchy in five rules
1. **Three text levels per screen:** display (headline or hero number), body, secondary. Not six sizes of semibold.
2. **Size, weight and space carry hierarchy, not boxes.** One level of container at most: a card never sits in a
   card, and a panel's sections are not cards.
3. **One primary action per screen** in the brand accent; the rest secondary or ghost.
4. **Color has a job:** accent = action or brand moment; semantic colors = data states; neutrals = everything else.
   Only tokens: raw palette classes and hex in feature code fail `design-lint`.
5. **The most important number is the biggest thing on the screen:** tabular figures, unit, label and source.

## 4. Craft that separates designed from templated
- Spacing from the token scale (4/8 grid). Use 3–4 steps and the same padding in every panel.
- One radius family (for example 12 / 20 / 28). Soft layered shadows; borders only as 1 px low-contrast hairlines.
- The display font for headings (tight tracking), the body font for the rest: the pair in `DESIGN.md`.
- One icon set (Phosphor), one size and one stroke. No emoji as icons.
- Navigation with presence: brand mark, a pill or segmented control for views, depth (a surface or blur).
  A white bar with a gray border and text links reads "admin template".
- Motion with a reason: the hero enters, actions answer, state changes animate in 150–300 ms. Respect
  `prefers-reduced-motion`.
- Real content from the fixtures: real names, places and numbers. Never "Lorem", "Item 1" or "Sin dato" walls.

## 5. The 3-second judge test, before every UI PR
Screenshot the screen at 1280×720 (`webapp-testing`), look at it for 3 seconds, then answer:
1. What is this screen and what do I do here?
2. Is the hero the biggest and most colorful thing?
3. Could it pass for a Linear, Stripe or Airbnb-level product, or does it look like an admin template, a government
   form or default Tailwind? The second answer is a P1: fix it before review.
4. Put it next to one other screen of the product: same product?

Then run `bash .uak/bin/design-lint`, and the `design-critic` subagent.

## 6. Seen in real events: each one cost a redo
| Seen | Do instead |
|---|---|
| A side panel as a stack of white boxes with gray borders | One surface; sections by space or hairlines |
| `text-lg font-semibold` on every label | Three text levels |
| `stone-*` / `gray-*` plus one hand-typed orange | Tokens |
| Each view with its own badge, button or toggle | The UI kit's components |
| Tiny legend and labels on the map | A big legend with a labeled scale, on the map |
| A header that is a white bar with links | Brand mark, pill navigation, depth |
| A tracked-out ALL-CAPS eyebrow above every heading, `A · B · C` meta strings, a `→` on every link, the same rounded card and grey shadow on everything | These are the AI tells `frontend-design` lists: use one only when the brief asks for it. Spend boldness in one place |

## 7. The gate
`bash .uak/bin/design-lint` fails on raw palette classes, hex colors and local copies of UI kit components in
`web/src` (outside the UI kit and the stylesheets). A deliberate exception carries `design-lint: ok` and the reason
on the same line, for example a map paint color read once from a token. The stack's smoke and `design-critic` run it.
