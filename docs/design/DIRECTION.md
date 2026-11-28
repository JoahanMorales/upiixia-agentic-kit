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
   progress, agents, integrations per period, tokens. Activity is the smallest of these. This is the default: the viewer
   may arrange the summary (UAK-165: move, hide, add; what needs the person can be moved, never hidden), a team may ship
   its own default, and rule 6 holds in every position.
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
12. **Messages** are one conversation per task, told in the task's stages: the thread is divided by labelled
    stages ("in progress", "in review · round 2", "integrated"); the messages of the viewer's own agents sit at the
    right, the others at the left; a review request, a request for changes, an approval and a question to the human
    each have their own soft state colour; what the engine did is a small centred line. At the left, the list of
    conversations as a panel (waiting for you, tasks that are moving, closed, general) with filters (all, my agents,
    for me, unread) and a search; at the right, the task's line and three figures (messages, rounds, changes
    requested) and who is in the thread. The thread sits in a window with "See the task". The panel has no field to
    write or answer: it has no server and does not pretend to send. The page scrolls as a whole.
13. **Words.** No subtitle that restates the title, no slogan, no filler line under a heading: a title and a count.
    A notice is one line: what, and the limit it passed.
14. **A wide window scales the page up** (UAK-198, the human's choice). Up to 1432 px the screens are the ones
    approved at 1280 and 390 px, box for box. Wider, the whole page grows with the window, by the window's width over
    1432 and at most 1.8: type, squares, cards, charts, spacing, the task's detail and Share, with the composition approved
    at 1280 px unchanged (laid out as at 1432 px) and the side gutters 24 px on the screen, so every tab reaches the right
    edge. Text stays sharp (the page is laid out again at its size, not magnified). Within it what should not stretch is
    held: a line of running text stays under about 90 characters, a task row's status sits next to its title. Past the
    cap (a window of about 2900 px) the extra width becomes columns, the summary's side in two. The scale is decided by the
    page from the width, never saved with the viewer's arrangement.
15. **Every screen is shot at 390, 1280 and 1920 px**, light and dark, before it is shown or reviewed (UAK-198: the
    blank band at 1920 px went unseen because every shot was 1280 or 390 px).

## Open

- Settled by the human on 2026-11-23: the type of the mock stays (Inter and JetBrains Mono), shipped in the kit as
  subset `woff2` files with their licence and loaded from files beside the page, never from the network; the default
  palette is Lavanda in a new install and Clásico where a dashboard of v6.8 or earlier was already in use.
- The tabs Agents, Black box, Memory and Tokens, the empty project and the finished project are not in the
  mock; UAK-162 designs them in the same language and shows them to the human before they are built.
- Settled by the human on 2026-11-24, on the screens of UAK-162 (they change rule 6 for the task squares): the summary
  shows every task as a small square that explains itself, whatever the size of the plan, and a square says what it
  waits for and what it unblocks; "Needs you" stays one grouped block; the Agents tab is a grid of compact cards as in
  v6.8; the Board opens on its columns; the page has no native select; Memory has a list and a graph of task clusters;
  the Share card comes horizontal and vertical with a very small credit to the kit; the page may weigh up to 200 KiB.
  The human signed off those screens the same day.
- Found by the human on 2026-11-25 on a desktop monitor ("a giant empty space at the right"; UAK-198): the dashboard uses
  the whole width, and from now on every screen is shot at 390, 1280 and 1920 px (rule 15). A first version stretched the
  main column and added columns ("quite elongated"); of three proposals shown live (A scale up, B three balanced columns,
  C a docked task detail) the human chose A, "definitely option A" (rule 14).

## Where a page's code lives, and the Paths of the open tasks (UAK-200)

Each page is assembled from parts in `pages/` (`pages/dash/`, `pages/setup/`, `pages/shared/`; the order is `pages/PAGE/ORDER`);
`kit/.uak/bin/lib/dash.html` and `setup.html` are generated by `python3 scripts/gen_pages.py`. A task lists the parts it edits, runs the generator and commits the regenerated page with them
(the page needs no entry in its Paths: it is declared `Generated:`). The parts are named by area: the dashboard has `css-shell`, `css-summary`, `css-board`, `css-arrange`,
`css-drawer`, `css-wide-window`, `02-body.html` (shell and header) and `js-01-prelude` (words and constants), `js-02-logic`
(the pure functions), `js-03-helpers`, `js-04-listbox`, `js-05-render-header`, `js-06-summary-blocks`, `js-07-arrange`,
`js-08-board`, `js-09-agents`, `js-10-messages`, `js-11-blackbox`, `js-12-memory`, `js-13-share`, `js-14-tokens`,
`js-15-drawer`, `js-16-boot`; the wizard has `css-*`, `02-shell-rail.html`, one `screen-NAME.html` per screen and
`js-01-core` ... `js-09-prepare-boot` (see its ORDER). `shared/system.css` (the `uak-system` block) and `shared/look.js` are
carried by both pages, once.

Proposed amendment of the Paths of the open tasks of plan "visual setup", for the human to publish (replace
`kit/.uak/bin/lib/dash.html` and `kit/.uak/bin/lib/setup.html` by the parts below; every other path stays; a task that finds it
needs another part adds that part, and two live tasks cannot hold the same one):

- UAK-163 (join): `pages/setup/js-01-core.js, pages/setup/js-06-blocked-resume.js, pages/setup/js-07-closed-roles.js, pages/setup/js-09-prepare-boot.js, pages/setup/screen-project.html, pages/setup/screen-start.html, pages/dash/js-05-render-header.js, pages/dash/js-16-boot.js, pages/dash/02-body.html`
- UAK-164 (intake and plan): `pages/setup/screen-plan.html, pages/setup/css-checks-plan-team.css, pages/setup/js-02-status-plan.js, pages/setup/js-03-plan-identity-dashboard.js, pages/setup/js-05-requests-feedback.js`
- UAK-166 (dashboard layout and truth): `pages/dash/js-02-logic.js, pages/dash/js-06-summary-blocks.js, pages/dash/js-07-arrange.js, pages/dash/css-summary.css, pages/dash/css-arrange.css, pages/dash/css-wide-window.css`
- UAK-167 (widget spec; touches both pages): `pages/dash/js-02-logic.js, pages/dash/js-06-summary-blocks.js, pages/dash/js-07-arrange.js, pages/dash/css-summary.css, pages/setup/screen-plan.html, pages/setup/js-03-plan-identity-dashboard.js, pages/setup/js-04-screens-run-buttons.js`

Overlaps that remain, because the work really is the same code: UAK-166 and UAK-167 on the dashboard's summary parts, UAK-164 and
UAK-167 on `screen-plan.html` and `js-03-plan-identity-dashboard.js`. Those pairs still run one at a time; the others can run together.
