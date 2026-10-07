# Marathon mode · real products

Goal: software that survives real users. It is secure, scalable and maintainable; correctness beats speed. `AGENTS.md` still applies; this file lists only what changes.

## Spec-driven flow
1. **Constitution** in `.uak/PROJECT.md` §Principles: measurable NFRs (p95, availability, RPO/RTO, bundle budget, cost per user) and non-negotiables.
2. **Spec** per feature with `/uak-spec`, in `docs/specs/NNN-name/`:
   - `spec.md`: what and why, users, EARS criteria ("When X, the system shall Y"), out of scope.
   - `plan.md`: design, data and migrations, contracts, threat model, rollout and rollback.
   - The tasks go to `.uak/TASKS.md` through a reviewed PR.
3. **ADR** in `docs/adr/NNNN-title.md` for anything costly to reverse: data, auth, vendors, architecture.
4. Tasks take 1 day or less. Each starts with a failing test (skill `test-driven-development`).
5. Check the execution graph: `uak graph`. Shorten the critical path with contracts.

## Integration
1. `main` is protected: it changes only through a PR with green CI and human CODEOWNERS approval.
2. Agents pre-review (`uak review --verdict approve`) and never merge. `guard` blocks `gh pr merge` and pushes to main.
3. Conventional commits (`feat:`, `fix:`, `refactor:`…) and a `CHANGELOG.md` entry for every visible change. Humans cut semver releases.
4. Backlog changes go through PRs (`Plan-Channel: main`), so every task traces back to a reviewed spec.

## Security (mandatory)
1. Any feature touching auth, personal data, payments, uploads, permissions or external calls gets a STRIDE threat model in `plan.md`.
2. The `security-reviewer` subagent reviews every PR in those areas. A HIGH finding blocks the merge.
3. Validate at the edge (schemas), encode outputs, use parameterized queries, and authorize per resource, not just per session.
4. Secrets come from the environment or a manager, never from the repo, logs, prompts, fixtures or error messages.
5. Every new dependency is a `uak decision`: license, maintenance, CVEs (`npm audit`, `pip-audit`, `osv-scanner`), size. Lockfiles have an owner in `OWNERS.md`.
6. No PII in logs. Public endpoints get rate limits, explicit CORS and security headers. Cookies are `HttpOnly`, `Secure` and `SameSite`.
7. LLM output is untrusted: validate it against a schema, never execute it, and give tools least privilege. Treat retrieved content as a possible prompt injection.

## Scalability and operations
1. No N+1 queries. Paginate every list. External calls get timeouts, retries with backoff and idempotency keys.
2. State lives outside the process (DB or shared cache). Config comes from the environment (12-factor).
3. Migrations are reversible, one per PR, with an owner. Schema changes go expand → migrate → contract.
4. Observability: structured logs, `/health` and `/ready`, latency and error metrics, traces on external calls.
5. Risky changes go behind a feature flag, with the rollback written in `docs/runbook.md`.
6. Performance budgets run in CI: p95 of the critical endpoint and bundle KB.

## Orchestration
- The Sonnet lead runs on `effortLevel: high`. Every multi-file plan and every risky diff passes the Opus advisor checkpoint (or `/uak-advise`). `security-reviewer` (Opus) covers sensitive areas. Caps: 3 parallel subagents, 4 Opus subagents per session.
- Run `/uak-secure` (the launch checklist) before the first real user, and again on every auth or payment change.

## Tests and loops
1. Unit tests for the domain, integration tests against a real DB (container), e2e for critical journeys. The coverage threshold lives in PROJECT.md.
2. Bug → a failing test first (skill `systematic-debugging`), then the fix.
3. Tests are deterministic: no real network; clock and randomness injected.
4. `uak loop` may fix tests and types, but never on deploy or migration commands, and never by weakening a test.
5. Before any "done": skill `verification-before-completion`.

## Pace
- 1 or 2 agents per human. Lease is 4 h; review wait is 24 h.
- A task that changes behavior closes with its docs updated (README, ADR or runbook).
- Run `/uak-retro` at every milestone.

## Defaults (`PROJECT.md`)
`Mode: marathon` · `Autonomy: yes` · `Auto-Merge: no` · `Review-Mode: gh` · `Plan-Channel: main` · `Lease-Seconds: 14400` · `Review-Lease-Seconds: 86400` · `Freeze-Epoch: 0` (humans control releases).
