# PROJECT · <event name> (sprint mode)

> Filled in by `/uak-setup` with the human at minute 0. uak reads the flat fields of the last block from
> the remote `main`, so a stale worktree can never change permissions.

## Event
| Field | Value |
|---|---|
| Event / challenge | `<name, number, official URL>` |
| Start | `<YYYY-MM-DD HH:MM IANA zone>` |
| Official deadline | `<YYYY-MM-DD HH:MM IANA zone>` · platforms: `<platform, form, repo>` |
| Freeze | `<deadline − 6 h>` → `Freeze-Epoch` |
| Clean rehearsal / plan B | `<deadline − 2 h>` |
| Internal submission | `<deadline − 1 h>` |
| Humans | `<name: role>` · submission owner: `<name>` (starts at T−8 h) |
| Agents | `<name-1, name-2>` per human (max 2) |
| Machines | `<laptop, Jetson…>` · ports already taken: `<8000…>` |

## Official rubric (weights sum to 100)
| ID | Criterion | Weight | Evidence in the demo |
|---|---|---:|---|
| C1 | `<criterion>` | `<%>` | `<step or artifact>` |

## Event rules
| Topic | Confirmed rule | Source |
|---|---|---|
| AI use / prior code | `<...>` | `<URL>` |
| Data and licenses | `<...>` | `<URL>` |
| Format and video limits | `<...>` | `<URL>` |

## Plan B
- A video of the whole flow at `<path>` (v1 at T−50%, final at T−2 h). Use it if `<network, mic, external API>` fails.

## Executable config
A human sets `yes`. A missing field means `no`.

```text
Mode: sprint
Backlog-Proposed-Epoch: 0
Backlog-Approved: no
Autonomy: yes
Auto-Merge: yes
Review-Mode: claims
Plan-Channel: claims
Freeze-Epoch: 0
Lease-Seconds: 2700
Review-Lease-Seconds: 14400
Events-Per-Session: 100
Checkpoint-Percent: 60
Merge-Lease-Seconds: 1800
Merge-Wait-Seconds: 180
Max-Parallel-Subagents: 4
Opus-Subagents-Per-Session: 2
Pace: auto
Subagent-Hard-Cap: 6
Strong-Hard-Cap: 3
Subagents-Per-Session: 40
Subagents-Per-Machine: 8
Subagent-Burst-Per-Minute: 6
Max-Worktree-Agents: 6
Blackbox: on
Additive-Paths: -
```
