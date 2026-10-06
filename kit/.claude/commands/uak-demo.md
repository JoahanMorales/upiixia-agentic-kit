---
model: sonnet
description: (sprint) Freeze, clean rehearsal, plan B and the submission checklist
---
Only when `Mode: sprint`. Read `.uak/modes/sprint.md` §Submission and the §Plan B section of `.uak/PROJECT.md`.
1. `bash .uak/bin/uak digest`: list what is pending in REVIEW or BLOCKED, and propose to the human what to merge and what to cut (P0 first).
2. Clean clone: `git clone <origin> /tmp/uak-clean && cd /tmp/uak-clean && <README setup> && bash .uak/bin/smoke`. Record the result.
3. Walk the demo up to the wow with `webapp-testing`, reduced motion and 1280×720, and give a one-line verdict. Then the human walks it, timed. Every failure becomes a P0 task with `Freeze-Allowed: yes`.
4. A pitch script of 3 min or less: problem (20 s) → live demo to the wow (90 s or less) → how it works (40 s) → impact (30 s). Map each part to a rubric criterion.
5. Remind the human to record the videos (you can't) and to check the duration limits.
6. Tick the checklist with evidence. Only the authorized person submits; you prepare links and texts.
