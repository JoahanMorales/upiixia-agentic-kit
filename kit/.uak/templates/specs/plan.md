# Plan NNN · <name>

## Design
<Components, flow, and why this option over 1–2 alternatives.>

## Data and migrations
<Tables/fields. Migration expand → migrate → contract, reversible.>

## Contracts
<Endpoints/events with schema and version. Affected consumers.>

## Threat model (STRIDE; mandatory for sensitive areas)
| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| Spoofing | | | |
| Tampering | | | |
| Repudiation | | | |
| Information disclosure | | | |
| Denial of service | | | |
| Elevation of privilege | | | |

## Observability
<Logs (no PII), metrics, alerts.>

## Rollout and rollback
<Flag, % of users, promotion criterion, rollback step.>

## Cost
<Infra and API cost per 1k users.>

## Tasks
<IDs in .uak/TASKS.md, each starting with a test. `uak graph` passes.>
