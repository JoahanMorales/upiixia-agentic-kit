---
model: sonnet
description: Pre-launch security audit of a backend against the kit's launch checklist; delegates the sensitive review to security-reviewer
---
Read `.uak/docs/SECURITY.md` §Launch checklist.
1. Send up to 3 `uak-scout` subagents in parallel to locate evidence: auth and session code; input validation and DB access; config, CORS, rate limits, logging and health. Each returns file:line per checklist item.
2. Send the evidence (not the files) to `security-reviewer` for a verdict on every item: PASS, FAIL (file:line + fix) or N/A.
3. Write `docs/security/launch-<YYYY-MM-DD>.md`: a table of item · status · evidence · fix. For every FAIL, open a task (`uak plan` in sprint, a PR in marathon).
4. List the **human-only** items separately (key rotation, cloud 2FA, restore drill, watching logs during launch) and ask the human to tick them. Never claim them yourself.
Never print or read secret values. Only check that secrets are absent from code and history (`bash .uak/bin/secret-scan --tracked`).
