## UAK-198 · The dashboard uses the whole screen on a wide monitor

- **Type:** fix
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-165
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_dashboard_layout.py, kit/.uak/tests/timings/test_dashboard_layout.txt, docs/DASHBOARD.md, docs/design/DIRECTION.md
- **Acceptance:**
  - on a window 1440, 1920 and 2560 px wide, every tab of the dashboard uses the width: the content's right edge is within 32 px of the window's right edge, and no tab leaves an empty band at the right. Why: on 2026-11-25 the human opened the dashboard on a desktop monitor and found "a giant empty space at the right"; `.page` and `.wide` stop at 1360 px and are aligned to the left, so at 1920 px the content ends at 1432 px and 488 px are blank. Every screenshot of UAK-162 and UAK-165 was taken at 1280 and 390 px, where it does not show
  - the extra width is used, not stretched: on the summary the side column grows and, from 1600 px, its blocks sit in two columns (or a third column holds them), the squares of all tasks use the row, the board's columns share the width, and tables and lists get more columns or wider ones; a line of running text is never longer than about 90 characters, and a block does not become a wide empty box with a few words in it
  - the arrangement of UAK-165 still means the same at every width: a viewer's main and side lists are kept, and how many columns the side shows is the page's decision from the width, not something saved
  - nothing changes at 1280 px and below: the screens the human approved (1280, 390) are pixel for pixel the same, compared by the test on the layout's box sizes
  - from 320 to 3840 px wide no tab scrolls sideways, and the header's controls stay at the right edge of the window
  - `docs/design/DIRECTION.md` says the widths every screen is shot at from now on: 390, 1280 and 1920; the task's own screenshots are at those three, light and dark, of every tab
- **Tests:** content_reaches_the_right_edge_on_wide_screens, wide_screens_add_columns_not_stretch, layout_is_unchanged_at_1280_and_below, no_sideways_scroll_from_320_to_3840
- **Verify:** `python3 kit/.uak/tests/test_dashboard_layout.py`
- **Next step:** `.page` and `.wide` in kit/.uak/bin/lib/dash.html (`max-width: 1360px`, line 224 at UAK-165) and the media queries at 1100, 900 and 640 px; the cases measure boxes in Chromium at each width (CI's Linux jobs have a browser since UAK-195) and print `SKIP name (no browser)` where there is none
