# Marathon mode · real products

Goal: software that survives real users. It is secure, scalable and maintainable; correctness beats speed. `AGENTS.md` still applies; this file lists only what changes.

## Spec-driven flow
1. **Constitution** in `.uak/PROJECT.md` §Principles: measurable NFRs (p95, availability, RPO/RTO, bundle budget, cost per user) and non-negotiables.
2. **Spec** per feature with `/uak-spec`, in `docs/specs/NNN-name/`:
   - `spec.md`: what and why, users, EARS criteria ("When X, the system shall Y"), out of scope.
   - `plan.md`: design, data and migrations, contracts, threat model, rollout and rollback.
   - The tasks go to `.uak/TASKS.md` through a reviewed PR.
3. **ADR** in `docs/adr/NNNN-title.md` for anything costly to reverse: data, auth, vendors, architecture.
4. Tasks take 1 day or less. Each lists its behaviors as `Tests:` (test names) and starts with their red (skill `test-first`, `uak red ID`).
5. Check the execution graph: `uak graph`. Shorten the critical path with contracts.

## Integration
1. `main` is protected: it changes only through a PR with green CI and human CODEOWNERS approval.
   **One human on the repo:** GitHub never lets a PR's author approve it, so `Review-Mode: gh` would wait forever. Use `Review-Mode: claims` (`install.sh --solo`): another agent identity reviews with `uak review`, the human merges, and branch protection requires green CI, not approvals.
2. Agents pre-review (`uak review --verdict approve`) and never merge. `guard` blocks `gh pr merge` and pushes to main (in every mode since v5.7).
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
7. Deploy from day one: `bash .uak/bin/uak deploy --write` reads the stack and writes a Dockerfile and a Render Blueprint (health check, `.env.example` names as dashboard secrets, `--disk PATH` for files the app writes), or points Next.js to Vercel. A staging service redeploys on every merge; production promotes a tested image.

## Frontend (users judge the product by its screens)
1. `/uak-design-lock` before the first screen: 3 directions with screenshots, a human picks one; `web/DESIGN.md`, the tokens and the locked screens are the source. A global redesign needs a human `uak decision`.
2. Every screen from the UI kit and its recipe row in `web/DESIGN.md` (skill `product-ui`); the public landing tells the idea in 5 seconds with real screens (skill `landing-story`); polishing an existing screen uses `redesign-existing-projects`.
3. Empty, loading, error and permission-denied states on every screen; long text, i18n and 390 px widths do not break the layout.
4. WCAG 2.2 AA: contrast, visible focus, keyboard-operable, labels on every control, `prefers-reduced-motion`.
5. `done` on a task in `UI-Paths` needs `design-lint`, screenshots at 1280 and 390 in `.uak-shots/ID/` and the `design-critic` SHIP for that commit; e2e covers the critical journeys in a real browser (skill `webapp-testing`).
6. Performance budgets in CI: LCP, CLS and bundle KB of the critical page.

## Orchestration
- The Sonnet lead runs on `effortLevel: high`. Every multi-file plan and every risky diff passes the Opus advisor checkpoint (or `/uak-advise`). `security-reviewer` (Opus) covers sensitive areas. Caps: 3 parallel subagents, 4 Opus subagents per session.
- Run `/uak-secure` (the launch checklist) before the first real user, and again on every auth or payment change.

## Tests and loops (skill `test-first`)
1. Names, red, green: the task's `Tests:` names exist, `uak red ID` saw them fail on an assertion, then the code. `done` checks both (`Test-First: yes`).
2. Tests only grow: `done` refuses a changed or removed assertion, a skip or a deselect. A wrong test is reported (`uak msg human`); a human allows the change (`uak allow ID --tests`).
3. By layer: unit for the domain (ms), integration on the production database engine in its own container (never SQLite for Postgres, never a mocked DB), contract tests for every endpoint and between services, architecture tests for the layers (`import-linter`, `dependency-cruiser`), e2e for critical journeys. The coverage threshold lives in PROJECT.md.
4. Fakes with state for every external dependency (payments, mail, clock, randomness); assert outcomes, not calls.
5. Bug → the test that reproduces it fails first (skills `systematic-debugging`, `test-first`), then the fix.
6. `uak loop` may fix tests and types, but never on deploy or migration commands, and never by weakening a test.
7. Before any "done": skill `verification-before-completion`.

## Pace
- 1 or 2 agents per human. Lease is 4 h; review wait is 24 h.
- A task that changes behavior closes with its docs updated (README, ADR or runbook).
- Run `/uak-retro` and `uak garden` at every milestone: prune rules nobody needed, turn repeated corrections into checks.

## Defaults (`PROJECT.md`)
`Mode: marathon` · `Autonomy: yes` · `Auto-Merge: no` · `Review-Mode: gh` · `Plan-Channel: main` · `Lease-Seconds: 14400` · `Review-Lease-Seconds: 86400` · `Freeze-Epoch: 0` (humans control releases).
