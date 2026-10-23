---
model: sonnet
description: Use at minute 0 with the human: PROJECT.md, doctor PASS, reviewers registered, schedule from uak clock.
---
Read `.uak/PROJECT.md` and its `Mode:`. The mode is the human's decision, already made with `install.sh --mode`. Never pick, infer or switch it. If `Mode:` is missing or the human hesitates, show this and let them choose:
| sprint | marathon |
|---|---|
| fixed deadline in hours or days (hackathon, demo day, prototype) | real users, data or money after launch |
| judges score a live demo; speed beats polish | maintained for months; correctness beats speed |
| agents auto-merge after an independent review | every merge needs a human and green CI |

Then ask ONLY for what is missing, all in one message:
- **sprint**: event, official URL, start and deadline (with IANA zone), submission platforms, video limits, rubric with weights, AI and prior-code rules, humans and agents (2 per human max), the human who owns submission, product name and brand.
- **marathon**: purpose, principles, measurable NFRs, environments, CODEOWNERS, coverage threshold, and how many humans can approve PRs on GitHub. **Only one**: set `Review-Mode: claims` (GitHub never lets an author approve their own PR, so `gh` mode blocks every merge); agent identities review each other with `uak review`, the human merges, and branch protection requires green CI but no approvals.

1. Fill in `.uak/PROJECT.md`. In sprint, run `bash .uak/bin/uak clock "START" "DEADLINE" ZONE --write`: it sets `Freeze-Epoch` scaled to the event (a fixed −6 h froze a 4 h event one hour after the first claim) and prints the schedule; copy it into the Event table. Timebox setup + plan to the "first claim by" time it prints.
2. sprint: copy `.uak/templates/IDEA.template.md` to `IDEA.md` and fill §0–4 with the human.
3. Run `bash .uak/bin/doctor --fix` on every machine until `DOCTOR PASS`. If gh cannot create PRs, tell the human NOW: get a token with *Pull requests: write*, or they will open every PR by hand.
4. One human registers every agent as reviewer in one call, from the main checkout: `UAK_HUMAN=<human> UAK_AGENT= bash .uak/bin/uak register-reviewer ana-1 ana-2 leo-1 leo-2`.
5. The human confirms `Autonomy` and `Auto-Merge`. Commit `setup: project` and push to `main`. Next: `/uak-plan`.
6. After the plan: `bash .uak/bin/uak start` until `START READY`. Each TODO is one step (push to main, approve the plan, an OWNERS row, a reviewer when alone); the human-only ones go to the human, in its words.

Never ask for or write keys. The human puts them in `.env` from their editor.
