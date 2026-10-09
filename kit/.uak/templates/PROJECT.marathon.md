# PROJECT · <product name> (marathon mode)

> The project constitution. Humans change it by reviewed PR. uak reads the last block from the remote `main`.

## Purpose
`<For whom, what problem, what measurable outcome.>`

## Non-negotiable principles
1. Secure and private by default: least privilege, personal data encrypted and minimized.
2. Nothing reaches `main` without green CI and human CODEOWNERS approval.
3. Every decision that is costly to reverse has an ADR.
4. `<domain principle, e.g. "every clinical number cites its source">`

## Non-functional requirements (measurable)
| Attribute | Target | Measured by |
|---|---|---|
| Latency | p95 `<300 ms>` on `<critical endpoint>` | `<load test in CI / APM>` |
| Availability | `<99.5 %>` monthly | `<monitor>` |
| Data | RPO `<1 h>` · RTO `<4 h>` | `<backup + rehearsed restore>` |
| Frontend | `<200 KB>` initial JS · LCP `<2.5 s>` | `<Lighthouse CI>` |
| Coverage | `<80 %>` on domain and services | `<pytest --cov / vitest>` |
| Cost | `<USD per 1k users/month>` | `<billing>` |

## Environments and ownership
| Env | URL | Deploys | Secrets in |
|---|---|---|---|
| dev | `<...>` | CI on merge | `<manager>` |
| prod | `<...>` | a human, via a semver release | `<manager>` |

CODEOWNERS: `<paths → people>` · On-call: `<person>` · Runbook: `docs/runbook.md`.

## Executable config
```text
Mode: marathon
Backlog-Proposed-Epoch: 0
Backlog-Approved: no
Autonomy: yes
Auto-Merge: no
Review-Mode: gh
Plan-Channel: main
Freeze-Epoch: 0
Lease-Seconds: 14400
Review-Lease-Seconds: 86400
Events-Per-Session: 150
Checkpoint-Percent: 60
Merge-Lease-Seconds: 1800
Merge-Wait-Seconds: 180
Max-Parallel-Subagents: 3
Opus-Subagents-Per-Session: 4
Pace: auto
Subagent-Hard-Cap: 4
Strong-Hard-Cap: 4
Subagents-Per-Session: 30
Subagents-Per-Machine: 6
Subagent-Burst-Per-Minute: 6
Max-Worktree-Agents: 4
Blackbox: on
Additive-Paths: -
```
