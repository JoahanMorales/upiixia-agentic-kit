---
model: opus
description: (marathon) Spec → plan with threat model → tasks, before any code
argument-hint: "<feature-name>"
---
Only when `Mode: marathon`. In any other mode, say so and stop. Feature: $ARGUMENTS
1. Read `.uak/PROJECT.md` (principles, NFRs) and the relevant ADRs in `docs/adr/`.
2. Write `docs/specs/NNN-<name>/spec.md` from `.uak/templates/specs/spec.md`: problem, users, EARS criteria, out of scope, open questions. Show it to the human and wait for an OK.
3. Write `plan.md` from `.uak/templates/specs/plan.md`:
   - design, data and migrations (expand/contract), contracts;
   - a STRIDE threat model, if the feature touches a sensitive area;
   - observability, flag, rollout, rollback and cost.
4. Anything costly to reverse gets an ADR (`.uak/templates/specs/adr.md`).
5. Add tasks of 1 day or less to `.uak/TASKS.md`, each starting with a test. Run `uak graph` and `uak lint`, then open the `plan: <name>` PR for human review.
