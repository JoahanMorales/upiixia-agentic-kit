# Visual Reference Evals Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task by task. Steps use checkboxes for tracking.

**Goal:** Measure whether optional visual references improve real page designs, using blind human scores and existing design-round artifacts.

**Architecture:** A source-repo-only Python script reads one JSON manifest and checks real desktop and mobile captures for each paired baseline and reference variant. It reports paired score differences and measured token usage. The script never edits skills, design priors, scores or round files; a human reviews any proposed prompt or prior change in a separate PR.

**Tech Stack:** Python 3.8 standard library, existing `.uak/design/rounds/R<k>/v<i>/` captures and `metrics.json`.

**Spec:** [visual-reference.md](../../evals/visual-reference.md)

## Global Constraints

- Evaluate working pages through `1280.png` and `390.png`, not synthetic concepts under `.uak-shots/visual-reference/`.
- Both variants of a pair use the same brief and seed; the human scores images under neutral A/B labels.
- A score is an integer from 1 to 5. Unknown tokens stay `null`; no inferred cost.
- No external service, dependency, runtime hook or automatic self-editing.

---

### Task 1: Offline paired evaluator (UAK-901)

**Files:**
- Create: `scripts/visual_reference_eval.py`
- Create: `kit/.uak/tests/test_visual_reference_eval.py`
- Create: `docs/evals/visual-reference.md`

**Interface:** `python3 scripts/visual_reference_eval.py MANIFEST.json` prints JSON with each pair's score difference, aggregate wins/ties/losses and known token totals; invalid manifests exit nonzero with a concise error.

- [ ] Write `scores_paired_real_captures`: two pairs with valid `1280.png` and `390.png`, scores `(3, 4)` and `(4, 4)`, assert one reference win and one tie.
- [ ] Write `refuses_missing_or_synthetic_captures`: reject a missing mobile capture and a path under `.uak-shots/visual-reference/`.
- [ ] Write `refuses_invalid_or_unpaired_scores`: reject score 0, score `3.5`, and a pair without a reference arm.
- [ ] Write `preserves_unknown_token_usage`: one arm has `tokens: null`; assert its total remains `null` and the report never converts it to zero.
- [ ] Add a stub `main()` that returns the wrong result and run `bash .uak/bin/uak red UAK-901`; expect RED_OK on an assertion.
- [ ] Implement only the manifest validation and paired calculation needed by the four tests. Accept paths relative to the manifest, require the capture filenames exactly, and print a stable JSON result.
- [ ] Run `python3 kit/.uak/tests/test_visual_reference_eval.py`, `python3 scripts/kit_lint.py`, and `cd kit && bash .uak/bin/smoke --package-only`.
- [ ] Inspect the diff, commit and push the task branch, then submit it for independent review.

### Evaluation protocol

Use briefs held out from prompt editing and report the sample size. For each, build baseline and reference variants with the same seed and time budget. Capture both at 1280 and 390, shuffle neutral A/B labels, collect one human score per variant, then run the evaluator. A proposed skill or prior change must be compared on these held-out briefs and receive a separate human-reviewed PR. Keep raw manifests, screenshots and scores so another reviewer can reproduce the result.
