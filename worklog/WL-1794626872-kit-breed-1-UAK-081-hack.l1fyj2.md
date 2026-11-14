# worklog/WL-1794626872-kit-breed-1-UAK-081-hack.l1fyj2.md · UAK-081

## Live summary
- Done: Verify exit 0 (4/4, real Chromium and fake); perf/density/shoot_qa/round/stage green; kit_lint pass; smoke rc 0; real AXIA R1/v2 flags loop.png and resultados-60.png · red at d963879: exit 1 (no assertion line recognized: the reviewer reads the log)
- Decision: flag only when nothing preserves the ratio (not cover/contain/none/scale-down); backgrounds only with both axes sized
- Why: AXIA R1 squashed images
- Failing: -
- Commands: python3 kit/.uak/tests/test_design_aspect.py
- Next: Integrated in main: 576f26d8beedee1015ef8592d071c04ad21001e9 (recorded by kit-breed-1)

## History
- 1794626872 | CLAIMED | kit-breed-1 | claim; next: QA_JS in kit/.uak/bin/lib/design_round.py (next to the upscaled-raster check)
- 1794627454 | CLAIMED | kit-breed-1 | heartbeat; lease until 1794641854
- 1794627457 | CLAIMED | kit-breed-1 | checkpoint; next: done
- 1794627460 | REVIEW | kit-breed-1 | done; PR https://github.com/JoahanMorales/upiixia-agentic-kit/tree/feat/uak-081; evidence: Verify exit 0 (4/4, real Chromium and fake); perf/density/shoot_qa/round/stage green; kit_lint pass; smoke rc 0; real AXIA R1/v2 flags loop.png and resultados-60.png · red at d963879: exit 1 (no assertion line recognized: the reviewer reads the log); reviewer: -
- 1794627812 | REVIEW | kit-r1 | review; approve; SHA fde39280baae1ccd0661378b50213233c7c9135f; reviewer kit-r1
- 1794628218 | INTEGRATED | kit-breed-1 | integrate; recorded by kit-breed-1; PR https://github.com/JoahanMorales/upiixia-agentic-kit/tree/feat/uak-081; merged 576f26d8beedee1015ef8592d071c04ad21001e9; proof ancestry
