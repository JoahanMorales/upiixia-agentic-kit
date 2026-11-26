## UAK-198 · The dashboard uses the whole screen on a wide monitor

- **Type:** fix
- **Priority:** P0
- **Estimate:** 4 h
- **Depends on:** UAK-165
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_dashboard_layout.py, kit/.uak/tests/timings/test_dashboard_layout.txt, docs/DASHBOARD.md, docs/design/DIRECTION.md
- **Acceptance:**
  - on a window 1440, 1920 and 2560 px wide, every tab of the dashboard uses the width: the content's right edge is within 32 px of the window's right edge, and no tab leaves an empty band at the right. Why: on 2026-11-25 the human opened the dashboard on a desktop monitor and found "a giant empty space at the right"; `.page` and `.wide` stop at 1360 px and are aligned to the left, so at 1920 px the content ends at 1432 px and 488 px are blank. Every screenshot of UAK-162 and UAK-165 was taken at 1280 and 390 px, where it does not show
  - the extra width is used by making the interface bigger, not longer (the human's choice on 2026-11-25 between three proposals shown live: A, scale up; B, three balanced columns; C, a docked detail panel — "definitely option A"; the first version stretched the main column and the human found the interface "quite elongated"): from about 1440 px the whole page grows with the window — type, squares, cards, charts and spacing — up to a cap, with the composition approved at 1280 px unchanged; text stays sharp, and what depends on real pixels keeps working at every scale: the Share card exports 1200×630 and 1080×1920 as before, a drag in arrange mode lands where its indicator says, the drawer, the dialogs and the listbox open in place; a line of running text is never longer than about 90 characters
  - the arrangement of UAK-165 still means the same at every width: a viewer's main and side lists are kept, and the scale is the page's decision from the width, not something saved
  - nothing changes at 1280 px and below: the screens the human approved (1280, 390) are pixel for pixel the same, compared by the test on the layout's box sizes
  - from 320 to 3840 px wide no tab scrolls sideways, and the header's controls stay at the right edge of the window
  - `docs/design/DIRECTION.md` says the widths every screen is shot at from now on: 390, 1280 and 1920; the task's own screenshots are at those three, light and dark, of every tab
- **Tests:** content_reaches_the_right_edge_on_wide_screens, wide_screens_scale_up_not_stretch, layout_is_unchanged_at_1280_and_below, no_sideways_scroll_from_320_to_3840
- **Verify:** `python3 kit/.uak/tests/test_dashboard_layout.py`
- **Next step:** `.page` and `.wide` in kit/.uak/bin/lib/dash.html (`max-width: 1360px`, line 224 at UAK-165) and the media queries at 1100, 900 and 640 px; the cases measure boxes in Chromium at each width (CI's Linux jobs have a browser since UAK-195) and print `SKIP name (no browser)` where there is none
