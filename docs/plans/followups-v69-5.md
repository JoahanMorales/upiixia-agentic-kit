## UAK-194 · The Share card can be saved on a phone

- **Type:** fix
- **Priority:** P0
- **Estimate:** 3 h
- **Depends on:** UAK-162
- **Paths:** kit/.uak/bin/lib/dash.html, kit/.uak/tests/test_dashboard_truth.py, docs/DASHBOARD.md
- **Acceptance:**
  - on an iPhone, with the dashboard opened over plain `http://` from another machine or from a file, the person leaves the Share dialog with the image saved or shared: the dialog shows the card as a real image (an `<img>` whose source is the exported PNG, in both formats), so a long press offers "Save to Photos", "Copy" and "Share", and one sentence under it says so. Why: on 2026-11-25 the human could neither copy nor download the card on an iPhone; the dialog drew a `<canvas>` (a long press on a canvas offers nothing), "Copy image" needs the clipboard API, which browsers give only to `https://` or `localhost`, and "Download PNG" used a link with `download` on a blob, which Safari on iOS ignores from a page like that
  - where the browser can share a file (`navigator.canShare` with the PNG), a "Share" button hands the image to the system's sheet (Instagram, Photos, Messages); where it cannot, the button is not shown
  - "Copy image" and "Download PNG" are shown only where they work, decided by testing the capability and not the browser's name; a button that cannot work is not on the screen, and when none of the three can, the image and its sentence are what remains. No button fails in silence: a refusal says what to do instead
  - nothing of this needs a network request or a server; the image shown is byte for byte the PNG that would be downloaded, at 1200×630 and 1080×1920
  - the dialog fits a phone: at 390×844 the image, the format switch and the actions are visible without scrolling sideways, and the image is not shown smaller than half its width allows
- **Tests:** share_dialog_shows_a_real_image, share_buttons_follow_capability, share_refusal_says_what_to_do, share_image_equals_the_download
- **Verify:** `python3 kit/.uak/tests/test_dashboard_truth.py`
- **Next step:** the Share dialog in kit/.uak/bin/lib/dash.html (search `toBlob` and `clipboard`); the capability checks are pure functions over an object that stands for `navigator`, so the cases run under node without a browser, and in Chromium with a phone profile when Playwright is present
