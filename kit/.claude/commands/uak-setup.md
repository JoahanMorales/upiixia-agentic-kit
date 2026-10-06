---
model: sonnet
description: Minute 0 with the human. Publishable PROJECT.md, doctor PASS, reviewers registered.
---
Read `.uak/PROJECT.md` and its `Mode:`. Ask ONLY for what is missing, all in one message:
- **sprint**: event, official URL, start and deadline (with IANA zone), submission platforms, video limits, rubric with weights, AI and prior-code rules, humans and agents (2 per human max), the human who owns submission, product name and brand.
- **marathon**: purpose, principles, measurable NFRs, environments, CODEOWNERS, coverage threshold.

1. Fill in `.uak/PROJECT.md`. In sprint, `Freeze-Epoch` = deadline − 6 h: `date -d "YYYY-MM-DD HH:MM TZ" +%s` (macOS: `date -j -f "%Y-%m-%d %H:%M" "..." +%s`).
2. sprint: copy `.uak/templates/IDEA.template.md` to `IDEA.md` and fill §0–4 with the human.
3. Run `bash .uak/bin/doctor --fix` on every machine until `DOCTOR PASS`. If gh cannot create PRs, tell the human NOW: get a token with *Pull requests: write*, or they will open every PR by hand.
4. Each human registers reviewers: `UAK_HUMAN=<human> bash .uak/bin/uak register-reviewer <agent>`.
5. The human confirms `Autonomy` and `Auto-Merge`. Commit `setup: project` and push to `main`. Next: `/uak-plan`.

Never ask for or write keys. The human puts them in `.env` from their editor.
