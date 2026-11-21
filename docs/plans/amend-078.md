## UAK-078 · Colors combine well: palettes built with harmony rules from the brand, picked by the human before building, measured on the page

- **Type:** feature
- **Priority:** P1
- **Estimate:** 3.5 h
- **Depends on:** UAK-077
- **Paths:** kit/.uak/bin/lib/design_round.py, kit/.uak/bin/lib/design_color.py, kit/.uak/bin/lib/design_taste.py, kit/.uak/bin/lib/gallery_pick.py, kit/.uak/tests/test_design_color.py
- **Acceptance:**
  - palettes are built from the project's brand colors with harmony rules, not as a list of hex: one dominant hue; neutrals (ground, ink, borders) tinted toward the dominant hue instead of pure grey/black/white; at most 2 saturated hues in one view; every other brand color used only as a small accent or desaturated; lightness and saturation adjusted so adjacent saturated colors don't vibrate (no complementary pair at equal lightness side by side); never all brand colors at full saturation together
  - each palette has roles and area shares (ground, surface, ink, primary, accent; e.g. 60/30/10) with the exact hex per role, and passes contrast (ink on ground ≥ 7:1, buttons and body text ≥ 4.5:1) before any page is built
  - `uak design palettes [--n 6]` makes a cheap palette round first (no agents, no tokens): N harmonious palettes from the brand, shown in the pick page as swatch strips and as a tiny mock (ground, a headline, a button, a chart line); the human picks 1–2 in seconds; the landing round's variants use the picked palettes (still split light/dark per UAK-072)
  - the capture measures color use at the 1920 fold (saturated share, dark share, dominant colors, how much each palette role covers, hue clashes found) into metrics.json; the pick page shows the measured strip next to the planned one, and a variant that drifted from its palette is flagged
  - the taste profile learns palette features (dominant hue family, number of saturated hues, neutral temperature, saturation share) from the picks of both rounds, and the kit prior (UAK-075) only takes palette rules that held across projects
  - Why (2026-11-12, the human: "the taste profile uses colors very badly … it doesn't combine them correctly and it isn't pretty"): measured at the fold, AXIA R3 pages were 1–3 % saturated, an almost monochrome navy; colonIA v4 put a washed pink on cream; the gene only said "ink + one accent" with no palette, roles or harmony, and the profile learned labels, not combinations
- **Tests:** dominant_hue_and_tinted_neutrals, at_most_two_saturated_hues, no_vibrating_pairs, contrast_checked_before_build, palette_round_needs_no_agents, variants_use_picked_palette, capture_flags_palette_drift, taste_learns_palette_features
- **Verify:** `python3 kit/.uak/tests/test_design_color.py`
- **Next step:** a new kit/.uak/bin/lib/design_color.py (OKLCH-like lightness/chroma math in the stdlib, harmony rules, contrast, measuring a PNG), then `uak design palettes`
