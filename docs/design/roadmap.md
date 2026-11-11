# Roadmap: frontends people want to look at (the kit's design loop)

Owner: JoahanMorales (the human picks; agents generate and measure). Long-running: many rounds, not one release.
Status: proposed 2026-11-10. F0 done 2026-11-11: baseline 2.8 / 5, catalog in [failures.md](failures.md).
Its tasks get planned phase by phase.

## The problem, honestly
Every frontend the kit has produced looks like AI output (the "slop" look): same type pairs, centered hero, soft
cards, gradient accents, emoji icons, generic copy. The gates added in v5.8–v5.10 (design-lint, design-critic,
design lock, product-ui) catch *tells*, but they do not produce *taste*. A critic that is itself a model approves
what a model likes. The only reliable judge of "bonito" here is the human, so the loop has to be built around
human choices and has to learn from them.

## Method: interactive evolution with human selection
Known as interactive evolutionary computation (Takagi, 2001) and design galleries (Marks et al., SIGGRAPH 1997):
generate a wide, deliberately diverse set, a human selects, the next set is bred from the selection.

1. **Wide:** 20 variants of the same screen and the same content (only the design changes), each built for real
   (static HTML + the team's stack where possible), captured at 1280 and 390.
2. **Select:** the human picks 5 (and may write one line on each: "this type", "this density", "hate the color").
   Picks take minutes: one page, keyboard shortcuts, no setup.
3. **Breed:** 20 new variants from the 5: mutations along one axis at a time, crossovers of two picks
   (A's type + B's layout), and 2–3 "wildcards" so the search does not collapse early.
4. **Repeat** until the human's top pick stops changing for two rounds, or after N rounds.
5. **Distill:** the winner's genome becomes DESIGN.md + tokens + the UI kit for the project, and the round history
   becomes the human's taste profile for the next project.

Every variant has a **design genome**, so variety is real and not 20 copies with different hues:
type pair · scale and density · color system (palette, contrast, accent use) · grid and layout archetype ·
component style (borders, radius, elevation) · imagery and iconography · motion · copy voice. A round may not
contain two variants that share more than 3 genes.

## Phases

### F0 · Baseline and the failure catalog (1–2 days)
- Capture every frontend the kit made (DevDay, deus-ex-machina, Chilangatón, Hacktoberfest, Pásala, UpiixSol):
  1280 + 390 screenshots in one gallery.
- The human scores each 1–5 and marks what is ugly. Output: `docs/design/failures.md`, a catalog with an example of
  each tell, and the baseline score that later phases must beat.

### F1 · The tournament tool (2–3 days)
- `uak design round [--brief FILE] [--n 20]`: writes `.uak/design/rounds/R<k>/v<i>/` (HTML, genome.json, shots).
- `uak design pick`: a local picker page (extends design-gallery) where the human chooses K, adds notes, and saves
  `picks.json`. Works over SSH/Tailscale like the gallery does today.
- Cost shown before each round (variants × tokens per variant); the human approves the round.

### F2 · Generators: skills, stacks and references (ongoing)
- Each variant is made by a recipe = skill set × stack × reference set. Candidates to try:
  - the kit's own skills (frontend-design, product-ui, design-taste-frontend, landing-story) and other public
    design skills;
  - stacks such as plain HTML/CSS, Tailwind v4, shadcn/ui + Radix, and motion libraries;
  - reference sets: screenshots of real products the human likes, used as mood boards (never copied);
  - other design tools when available (a Figma connector, image models for mood only, never for the UI itself).
- Track which recipes the human picks. Recipes nobody picks after 3 rounds are dropped.

### F3 · Breeding and diversity control (2 days)
- Mutation and crossover over the genome, the "max 3 shared genes" rule, wildcards, and the stop rule.

### F4 · Taste profile and critic calibration (3–4 days)
- From all picks: a taste profile (genes the human picks and genes they reject) saved per human.
- The design-critic is measured against the human: given a round, does it rank the human's 5 in its top 10?
  Only when agreement is high enough (target set in F0, e.g. 4 of 5) may the critic pre-filter 100 → 20, so the
  human sees better candidates for the same effort. The critic never replaces the human's final pick.

### F5 · Into the kit (2–3 days)
- `/uak-design-lock` runs 2–3 short rounds (about 45 min in sprint) instead of picking among 3 directions.
- DESIGN.md and tokens come from the winning genome; product-ui and design-lint learn the catalog from F0.
- Hackathon mode: the profile from earlier rounds seeds round 1, so the team starts from the human's taste.

### F6 · Proof (each event)
- Blind comparison: the human scores the new frontends against the F0 baseline without knowing which is which.
  The roadmap is done when new work beats the baseline clearly and consistently, not when the tool exists.

## Rules for the whole roadmap
- The human's choice is the only measure of "bonito"; model critics are tools, calibrated against it.
- Same content in every variant of a round (so the comparison is about design).
- Real screenshots of real HTML, never generated images of a UI.
- Every round leaves its files, picks and cost on disk, so progress is measurable and nothing is invented.
- Rounds cost tokens: start with Sonnet for generation, keep the strong tier for breeding decisions, show cost first.

## Next step
F1: the tournament tool, with the genome bounds and targets that F0 set (failures.md, "What this changes").
