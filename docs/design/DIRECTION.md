# The kit's visual direction

Chosen by the human on 2026-11-23, after six rounds on a working mock (`direction/mock.html`: open it in a browser;
"Panel" and "Asistente" at the top, "Apariencia" for the theme and the palette, a switch between an 11-task and a
60-task plan). The mock is the reference for layout, sizes and behaviour; this file states the rules it follows.
UAK-158 (one design system), UAK-159 (the wizard's flow), UAK-162 (the dashboard) and UAK-163 (the join path) build it.

## Where it comes from

- **The kit's banner** (`docs/media/banner.png`): the ground, the state pills in mono capitals, and the line of nodes
  from claim to merge, which is the recurring figure (a task's row, the wizard's progress, the task's detail).
- **The one frontend the human scored 5** (`failures.md`): a product layout with an icon rail, restrained scale,
  few colours.
- **The dashboard that ships today**: its task detail (time in each state, who took part, every move in order) is
  kept as a structure, and its colours stay available as the palette "Clásico".

## Rules

1. **Scale.** Body 13 px, secondary 12 and 11 px, the largest figure 26 px, headings of a screen 22 to 24 px.
   Controls 28 to 36 px high (44 px touch targets at phone width). Radii 6 and 8 px. One shadow, on popovers only.
2. **Type.** One sans for text, one mono for IDs, commands, state pills and small counters. No decorative face.
3. **Colour is a preference, not the design.** The structure is the same under every palette. A palette sets one hue
   and its saturation; grounds, lines and inks are tinted from it. Shipped palettes: Clásico (the exact colours of
   the dashboard of v6.8, where in progress is amber and in review is blue), Lavanda, Cielo, Menta, Salvia, Durazno,
   Rosa, Arena, Grafito. Light and dark for each. The choice is the viewer's, kept in the browser, set from
   "Apariencia"; it never changes a tracked file.
4. **Pastel, not hard.** Fills are soft tones; text on a fill is dark. State colours (integrated, in review, in
   progress, blocked) are separate from the accent and are never the only signal: a state always has its word.
   A green palette must keep "integrated" distinguishable from the accent.
5. **Dark is designed, not inverted.** A near-black neutral ground, three clear steps (ground, panel, card), no
   translucent fills.
6. **The summary never grows with the plan.** Every list on the summary has a maximum and a link to its own tab:
   tasks show what is moving (blocked, in review, in progress), 8 rows; agents 4; progress is one block per task up
   to 24 tasks and one proportional bar beyond. A plan of 60 tasks adds less than 50 px to the page.
7. **Order of the summary.** What needs the person first, then tasks (list or columns), then activity; at the side:
   progress, agents, integrations per period, tokens. Activity is the smallest of these.
8. **Integrations per period.** The period adapts to the time elapsed so that 6 to 8 bars show: by the hour early
   in a hackathon, then 2, 3, 4, 6 or 12 hours, by the day in a long project; the viewer can fix it (1 h, 2 h, 4 h,
   day).
9. **The board has four stages**: to do, in progress, in review, integrated. Blocked and overdue are conditions
   shown on the card, not columns. A card says who, which step, and how much of the lease is used; a to-do card says
   whether it can be claimed or what it waits for; integrated tasks are rows with their commit. Each column says the
   one thing that matters in its header ("1 waits for your decision", "2 over their lease"). The page scrolls;
   columns do not scroll inside; each shows 8 and a "more".
10. **The task's detail** keeps the structure of v6.8: header (ID, state, priority, title, owner, rounds, moves,
    branch), time in each state, who took part (with model and harness), every move in order (time, elapsed, who,
    note; key moves with a labelled node, heartbeats as dots), then the acceptance criteria with their tests.
11. **The wizard**: the line of nodes as progress at the top with "continue in the terminal"; the choices at the
    left; at the right a window that shows what will be written, changing as the person chooses; one primary button
    at the bottom. The panel reuses its pieces: the window, the single bordered list, the three figures in a footer.
12. **Words.** No subtitle that restates the title, no slogan, no filler line under a heading: a title and a count.
    A notice is one line: what, and the limit it passed.

## Open

- Fonts: the mock loads Inter and JetBrains Mono from the network; the dashboard may not make a request. Either the
  system stack or an embedded subset (the page's weight limit decides). To be settled in UAK-158.
- The tabs Agents, Messages, Black box, Memory and Tokens, the empty project and the finished project are not in the
  mock; UAK-162 designs them in the same language and shows them to the human before they are built.
