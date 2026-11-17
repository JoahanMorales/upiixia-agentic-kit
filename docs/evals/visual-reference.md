# Visual-reference eval

This offline eval compares working pages built from the same brief, seed and time budget. One page uses the normal design flow; the other may use `visual-reference` as an input. Generate both with the same stack and content, run `uak design shoot`, and keep the real `1280.png` and `390.png` captures. Synthetic concept images are never scored as pages.

## Record a blind comparison

For each brief, show the two desktop and mobile captures under shuffled A/B labels, without naming the recipe. A human scores each page from 1 to 5 using the scale in `docs/design/f0/scores.json` and notes functional or mobile failures separately. Reveal the conditions only after scores are saved. Copy the four browser captures into a case directory beside the manifest; retain the original round IDs and any reference source in the experiment log.

The manifest is JSON version 1. Paths are relative to the manifest directory. Each pair has one brief and one shared seed; `baseline` and `reference` contain the two scores, real capture paths, and reported tokens. Set tokens to `null` when the builder did not report usage. The reference arm records the tool or human source as provenance; it does not prove the reference was used.

```json
{
  "version": 1,
  "pairs": [
    {
      "brief": "repair-desk",
      "seed": 17,
      "baseline": {
        "score": 3,
        "captures": {"desktop": "captures/repair-desk/A/1280.png", "mobile": "captures/repair-desk/A/390.png"},
        "tokens": 41000
      },
      "reference": {
        "score": 4,
        "captures": {"desktop": "captures/repair-desk/B/1280.png", "mobile": "captures/repair-desk/B/390.png"},
        "tokens": null,
        "source": {"kind": "imagegen", "id": "concept-1"}
      }
    }
  ]
}
```

Run `python3 scripts/visual_reference_eval.py path/to/manifest.json`. The script checks paired records and capture files, then prints JSON with each score difference, wins/ties/losses, mean difference and token totals. A missing token value makes that arm's total `null`. Invalid input exits nonzero. It does not judge design quality or modify a skill.

The file check catches missing files, synthetic concept paths and truncated PNG structure. It cannot prove a capture came from a browser, decodes correctly or shows a working page; the reviewer inspects the original round and functional findings.

## Improvement gate

Use briefs held out from prompt editing and report the sample size. Compare them before proposing a change to `visual-reference` or the design prior. Check the human scores alongside mobile, accessibility and functional findings; the [existing design target](../design/failures.md) is a blind mean of at least 4.0/5 with no 1–2 scores. Put the manifest, raw captures, cost and proposed diff in a PR for another human to review. If the result is weak or the sample is incomplete, keep the current recipe and record the failure with `uak learn`/`uak garden` rather than letting the agent rewrite its own instructions.
