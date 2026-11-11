# F0 · The failure catalog and the baseline

Phase F0 of the design roadmap: every frontend the kit has produced, scored by the human, so later phases have a
number to beat and a list of what actually looks wrong. Scored 2026-11-11 by JoahanMorales in the F0 gallery
(22 screens, each at 1280 and 390, captured the same day from the live deploys; UpiixSol from a local build with
its demo seed).

## The baseline: 2.8 / 5

| Frontend | Event | Score | Tells marked | The human's note |
|---|---|---|---|---|
| UpiixSol | Campus UPIIXIA, oct 2026 (3 days) | **5** | none | "esta muy bonito pero se rompían los botones y algunas animaciones pero es de los mejores frontend" (very nice, but buttons and some animations broke; one of the best) |
| SpeedHack | Hacktoberfest, oct 2026 | **4** | generic copy, flat hierarchy | "bastante simple, y la paleta de colores no tiene mucho sentido" (quite plain, and the palette makes no sense) |
| colonIA | Chilangatón / HackADA, oct 2026 | **3** | palette without character, gradients and glow, too cramped | "los botones y todo es gigante" (the buttons and everything are giant) |
| Pásala | juego-economia, oct 2026 | **3** | none | "esta bien pero simple" (fine but plain) |
| AXIA · Inspector que aprende | OpenAI × Kavak, nov 2026 | **1** | soft equal cards, generic copy, palette without character, flat hierarchy, too much empty space | "EST SUPER SIMPLE" (super plain) |
| SinSeñal | DevDay Exchange, nov 2026 | **1** | default font, soft equal cards, palette without character, generic copy, flat hierarchy, too cramped, breaks on mobile | "cosas super grandes y full ai slop" (things super big, full AI slop) |

Mean 2.83 (17/30). Two of six score 1; only one reaches 5. The two newest frontends (November) are the two worst.

## What the human actually marked

How often each tell was marked, across the six:

| Tell | Times | Where |
|---|---|---|
| Palette without character | 3 | AXIA, colonIA, SinSeñal |
| Generic copy | 3 | AXIA, SinSeñal, SpeedHack |
| Flat hierarchy | 3 | AXIA, SinSeñal, SpeedHack |
| Soft equal cards | 2 | AXIA, SinSeñal |
| Too cramped | 2 | colonIA, SinSeñal |
| Too much empty space, gradients and glow, default font, breaks on mobile | 1 each | |
| **Centered hero, emoji as icons, looks like a template** | **0** | |

The tells the kit already bans (`landing-story`, `product-ui`, `design-taste-frontend`, `design-lint`: centered
hero, emoji icons, template look) were marked **zero** times. The gates did their job on those, and it did not
make the frontends good. What the human objects to now is not covered by any gate: **scale, plainness, and
palette logic.**

## The four failures, with measurements

Measured on the live landing pages at 1280×800 (computed styles of visible text and buttons).

### 1. Everything is oversized (SinSeñal, colonIA)

| | largest text | body text | buttons | distinct colors |
|---|---|---|---|---|
| colonIA | **207 px** | 18 px | 52 px | 22 |
| SinSeñal | **168 px** | 18 px | 45 px | 9 |
| Pásala (host screen) | 84 px | 16 px | 60 px | 5 |
| SpeedHack | 48 px | 16 px | 45 px | 6 |
| AXIA | 36 px | 16 px | 48 px | 11 |
| **UpiixSol (scored 5)** | **36 px** | **16 px, median 14** | **44 px** | **5** |

The two frontends the human called "giant" have display type of 168–207 px and 18 px body text. The one they
called the best tops out at 36 px. The kit's own skills push the wrong way: `landing-story` asks for "bigger type,
the brand color at full strength, the display face doing real work"; `product-ui` checks "Is the hero the biggest
and most colorful thing?" and "the most saturated thing on screen". Agents read "bold" as "huge".

Examples: `f0/devday-0-1280.webp`, `f0/colonia-0-1280.webp`, `f0/colonia-0-390.webp`.

### 2. Plain, with nothing to look at (AXIA, Pásala, SpeedHack)

"Super simple" / "simple" / "bastante simple" on three of six. AXIA uses the system font stack (`ui-sans-serif`,
no typeface chosen), one column of text, numbered steps, and no image of a car anywhere in an app about car damage.
Pásala's player screen is two inputs and a button on a black page. Plainness here is not minimalism: there is no
subject-specific material (a photo, the map, the object itself) and nothing made by hand.

Examples: `f0/axia-0-1280.webp`, `f0/pasala-0-1280.webp`.

### 3. Palettes chosen by rule, not by meaning (AXIA, colonIA, SinSeñal, SpeedHack)

Marked on three and named in SpeedHack's note ("la paleta de colores no tiene mucho sentido"). colonIA uses 22
distinct colors on one landing (magenta, yellow, green, blue hexes, glow); UpiixSol uses 5, and every one comes from
its brand (the green and orange of the logo and mascot). The kit asks for "a palette as named hex values" and
bans purple gradients, but never asks *why* a color belongs to this subject.

Example: `f0/speedhack-2-1280.webp`.

### 4. Flat hierarchy and generic copy (AXIA, SinSeñal, SpeedHack)

Marked together on three. `product-ui` already demands three text levels; the frontends either collapse to one
level (AXIA: everything 14–16 px under a 36 px title) or jump from 168 px straight to 18 px with nothing between
(SinSeñal). Copy reads as explanation of the product instead of the product doing something.

## What the 5 had that the 1s did not

UpiixSol was built with the kit over three days, about the same as a hackathon, so time does not explain it. The
differences visible in the captures and the repo:

- **Human-made brand assets from the first commit.** `assets/brand/` (logo and the axolotl mascot) came in with
  `setup: project`; the palette and the display face (Fredoka) follow from them. No other frontend had a human
  asset to start from.
- **A product layout, not a landing.** Sidebar navigation, a feed, cards with real content (`f0/upiixsol-2-1280.webp`,
  `f0/upiixsol-3-1280.webp`). The 1s are landing pages explaining the idea.
- **Restrained scale.** 36 px maximum, 14 px median, 44 px buttons, 5 colors.
- **Inter as the body font**, which the kit's skills list as a default to avoid. The human did not care; the
  restraint around it is what read as good.

Its failure was functional (buttons and animations that broke), not visual. F0 scores looks only.

## Also found while capturing

- SinSeñal: reloading a deep link (`/tienda`) returns FastAPI's `{"detail":"Not Found"}`; the SPA fallback is
  missing.
- Pásala: the host screen scrolls sideways at 390 wide (`f0/pasala-2-390.webp`).
- The Render free tier serves a wake-up page for 20–40 s; the first captures and measurements hit it. Capture
  scripts must wait for the app's own title, not for `networkidle`.

## What this changes in the roadmap

1. **Targets.** F6 is met when new frontends average **≥ 4.0** in a blind score against these six, with none at
   1–2. F4's critic may pre-filter only when it puts the human's picks in its top 10 at least 4 times in 5.
2. **Genome bounds from F0.** Variants in F1 rounds keep display type ≤ 72 px on app screens (≤ 96 px on a
   landing hero), body 14–16 px, controls 36–48 px, and at most 6 palette colors unless a gene says otherwise. Size
   is a gene with a range, not "bigger".
3. **The skills that push scale up get fixed** (`landing-story` line 44, `product-ui` self-check 2–3): "the hero is
   the most important thing", not "the biggest and most saturated".
4. **Every round starts from material.** If the team has a logo, a mascot, a photo or a real map, it is an input
   to round 1; if not, the brief asks for one before generating. The only 5 had one.
5. **Product screens over landings.** Rounds score the working screen first; the landing is optional.
6. **The tell list grows from this catalog:** oversized type, plain (no subject material), palette without a
   reason, one-level hierarchy. The banned tells stay banned but no longer count as "design done".

Raw scores: `f0/scores.json`. The roadmap: [roadmap.md](roadmap.md).
