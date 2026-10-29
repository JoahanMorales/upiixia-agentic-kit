---
name: product-ui
description: Make product screens look designed, not templated - dashboards, a map or canvas with side panels, data views, detail pages, forms and flows, lists, mobile screens. Use whenever you build or change an app screen, a view or a component in web/ (the landing is landing-story; the visual direction is /uak-design-lock). Covers layout recipes, hierarchy, craft, the 3-second judge test and the design-lint gate.
---

# Product UI · screens that look designed

The visual direction comes from `/uak-design-lock` (skill `frontend-design`); the landing is `landing-story`.
App screens are this skill. Why (Chilangatón, a 7-hour sprint): the first UI was a column of white boxes with gray borders, raw
`stone-*`/`emerald-*` classes, every label `text-lg font-semibold`, and each view with its own badge and toggle. It
was redone from scratch 3 hours in, and the team nearly lost on it.

## 0. Before the first line
1. Read `web/DESIGN.md`: your screen's row of `## Screens` names its recipe and hero. Open (Read the PNG) the
   locked screen with that recipe in `web/public/design-lock/screens/`, not only the wow screen: copy its layout,
   not another feature's. Your screen sits inside `AppShell`; never build a header or a nav of your own.
2. Build from the UI kit (the stack's UI paths: `web/src/lib/ui` or `src/components/ui`). A piece or a size is missing?
   Ask its owner (`uak msg <design task> --kind request "component · variant · why"`); when the design task is done
   and nobody owns the kit any more, add the variant to the kit itself. Never a local copy, never the wrong size.
   Every state color has an ink token (`--warn` + `--warn-ink`): white on amber is 2.2:1.
3. Name the screen's one job and its hero (the map, the number, the route, the form) in one line of the PR.

## 1. Accessibility is a floor, not a style
AA contrast, 16–18 px body, 44–48 px targets, visible focus, plain language and the reduced-motion path are
mandatory. They never mean gray, flat or a government-form look. A social-impact or public-sector brief is still a
product judged in 3 seconds on a projector. Use GOV.UK or USWDS only when the human asks for them.

## 2. Pick one layout recipe per screen
| Screen | Recipe |
|---|---|
| Map or canvas + controls | The hero is full-bleed: no border, no card around it. One panel of 360–420 px at 1280 wide, ONE solid surface. Sections are separated by 24–32 px of space or a hairline, never a box each. The basemap is muted and needs no key (MapLibre + OpenFreeMap `positron`, or OSM tiles with `filter: grayscale(1) contrast(.85)`); data colors never repeat its road or POI hues; legend on the map, 12–16 px swatches with labels. |
| Dashboard | One hero metric (display font, 48–72 px) and 2–4 supporting stats in a row, then one primary chart. Never a grid of 9 equal cards. On app screens the hero metric is required; on the landing the wow is a real screenshot, not a stat (that is the default `frontend-design` warns about). |
| Chart | One library for the whole app; 2 px lines, direct labels instead of a legend, at most 3 hairline gridlines, one annotation on the moment that matters ("empties at 8:42"); a forecast shows its uncertainty as a band at 15% of the accent. A product that predicts shows the prediction on its main screen, not only a number. |
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
- Navigation with presence: `NavBar` from the UI kit: brand mark, a pill or segmented control for views, depth (the surface and shadow tokens).
  A white bar with a gray border and text links reads "admin template".
- Motion with a reason: the hero enters, actions answer, state changes animate in 150–300 ms. Respect
  `prefers-reduced-motion`.
- Real content from the fixtures: real names, places and numbers. Never "Lorem", "Item 1" or "Sin dato" walls.

## 5. The 3-second judge test, before every UI PR
Screenshot the screen at 1280×720 (`webapp-testing`), look at it for 3 seconds, then answer:
1. What is this screen and what do I do here?
2. Is the hero the biggest and most colorful thing?
3. Is the one memorable element of `DESIGN.md` visible? Is the hero the most saturated thing on screen? Does the
   product's core claim show as a visual (the forecast, the route, the match), not only as a sentence? Any no is a
   P1: fix it before review.
4. Put it next to one other screen of the product: same product?

Then run `bash .uak/bin/design-lint`, capture 1280 and 390 into `.uak-shots/<ID>/`, and run the `design-critic`
subagent: `uak done` refuses a task in `UI-Paths` without its `SHIP` for the current commit.

## 6. Seen in real events: each one cost a redo
| Seen | Do instead |
|---|---|
| A side panel as a stack of white boxes with gray borders | One surface; sections by space or hairlines |
| `text-lg font-semibold` on every label | Three text levels |
| `stone-*` / `gray-*` plus one hand-typed orange | Tokens |
| Each view with its own badge, button or toggle | The UI kit's components |
| Tiny legend and labels on the map | A big legend with a labeled scale, on the map |
| A header that is a white bar with links | Brand mark, pill navigation, depth |
| Rows or cards with a colored stripe on the left, each panel the same grey box, ten screens with one layout | One recipe per screen from DESIGN.md; a leading icon, chip or weight instead of a stripe (design-lint flags `border-l-4`) |
| A bare row of 10 text links as the nav, clipped at 390 wide | `NavBar` from the UI kit: brand mark, 6 entries at most, a menu at 390 |
| A tracked-out ALL-CAPS eyebrow above every heading, `A · B · C` meta strings, a `→` on every link, the same rounded card and grey shadow on everything | These are the AI tells `frontend-design` lists: use one only when the brief asks for it. Spend boldness in one place |

## 7. The gate
`bash .uak/bin/design-lint` fails on raw palette classes, hex colors and local copies of UI kit components in
`web/src` (outside the UI kit and the stylesheets). A deliberate exception carries `design-lint: ok` and the reason
on the same line, for example a map paint color read once from a token. The stack's smoke and `design-critic` run it.
