# DESIGN · <product name>

> Written by `/uak-design-lock` from the direction the human picked by looking. Every field is required:
> `uak lint` fails a DESIGN.md that leaves one as `<...>`. Global changes after the lock need a human decision.

## Direction
- Name: `<direction name>` · Intent: `<one line>`
- The one memorable element: `<where the boldness goes; everything else is calm>`
- References: `<design-lock folder>/refs/<1-3 screenshots of real products for the same kind of screen>`

## Type
- Families: display `<face>` · body `<face>` (2 at most; never Inter, Roboto, Arial or Geist by default)
- Scale (px, ratio ≥ 1.25, 6 steps at most): `<12 / 14 / 16 / 20 / 28 / 48>`
- Body: `<16-18>` px · line height `<1.5>` · hero display `<48-72>` px · tabular figures for numbers: yes

## Space and shape
- Spacing scale (px): `4 / 8 / 12 / 16 / 24 / 32 / 48 / 64` (use 3-4 steps per screen)
- Radius family: `<e.g. 8 / 16 / 24>` · elevation: one level (`<shadow token>`), hairlines `1px <token>`
- Content width `<e.g. 1200>` px · side panel `<360-420>` px

## Color (tokens in the stack's tokens file: STACK.md `## UI paths`)
| Token | Value | Job |
|---|---|---|
| `--bg` | `<...>` | page |
| `--surface` | `<...>` | the one container level |
| `--text` / `--text-2` | `<...>` | body / secondary |
| `--accent` | `<...>` | the primary action and the brand moment, nothing else |
| `--accent-ink` | `<...>` | text on the accent (contrast ≥ 4.5:1, `design-lint` checks it) |
| `--ok` / `--warn` / `--bad` | `<...>` | data states only |
| `--ok-ink` / `--warn-ink` / `--bad-ink` | `<...>` | text on each state color (≥ 4.5:1) |
Disabled: `<how a disabled primary looks: a muted fill, not the accent at low opacity>`

## Shell (owned by the design lock task)
- `AppShell` · `NavBar` (brand mark, `<pill | segmented | sidebar>` for views, 6 entries at most, the rest in a menu) · `PageHeader` · `PageLayout`
- At 390 wide: `<what the nav becomes: a bottom bar or a menu>`

## Screens: one recipe and one hero each
| Screen | Recipe (skill `product-ui` §2) | Hero |
|---|---|---|
| `<wow screen>` | `<map + panel | dashboard | detail | flow | list>` | `<the element that is the biggest thing>` |
| `<second screen>` | `<...>` | `<...>` |
| `<third screen>` | `<...>` | `<...>` |
| Landing | `landing-story` | `<the wow as a real screenshot>` |

## AI tells we refuse
- A colored side stripe on rows or cards · a card inside a card · a grid of equal boxes
- Purple-blue gradients, glass on every surface, emoji as icons, tracked-out uppercase eyebrows over every heading
- Three equal pricing or feature cards · every label in the same weight · `demo:`, `undefined` or raw IDs on screen
- `<3 more for this product>`
