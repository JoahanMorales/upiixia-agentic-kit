# Loop engineering

Loop engineering means designing the cycles that run agents, instead of prompting them one turn at a time. Every uak loop declares five things, and a loop missing any of them is not allowed:

| Part | Question | Default |
|---|---|---|
| **Trigger** | What starts an iteration? | a command, a hook event, a schedule or a message |
| **Verifier** | What machine check says "done"? | the task's `Verify` command, exit 0 |
| **Budget** | Max iterations, minutes and tokens? | 5 iterations; failure tail fed back as 40 lines or fewer |
| **Stop** | When must it stop, even if not done? | pass · budget exhausted · same failure twice (stuck) |
| **Escalation** | Who takes over and with what? | `uak log ID --state BLOCKED "<exact error>"` or `uak decision`, then pick another task |

## The loops in uak
| Loop | Trigger | Verifier | Stop / escalation |
|---|---|---|---|
| **Inner (verify → fix)** | the agent finishes an edit | `bash .uak/bin/q <Verify>` | 5 attempts or 2 identical failures → BLOCKED with the error |
| **Autonomous (`uak loop`)** | you run it, or cron or CI | `--verify CMD` | `--max`, `--minutes`, or stuck → exit 3, task BLOCKED |
| **Heartbeat** | every tool call (hook), throttled to 8 min | lease renewed | none; the lease expires if the agent dies |
| **Inbox (hook loop)** | every tool call, throttled to 2 min | new actionable message | injects at most 24 lines; `Stop` blocks until handled |
| **Review** | `uak done` | reviewer runs Verify on the SHA | reject → owner fixes and repeats `/uak-ship`; approve → merge |
| **Deadline (cron loop)** | `next`/`status`, or `*/5 * * * * uak tick` | receipts on claims | each deadline fires once (CAS receipt) |
| **Human** | `uak digest` | the human decides | batched, never one ping per PR |
| **Retro** | end of event or milestone | data from claims | `/uak-retro` proposes rule changes with evidence |

## `uak loop`: autonomous runs (Ralph-style, but bounded)
```bash
bash .uak/bin/uak loop --verify "uv run pytest -q tests/test_api.py" \
  --agent "claude -p --permission-mode acceptEdits" --max 5 --task HACK-007
# Other agents: --agent "codex exec -" · --agent "gemini -p" · any CLI that reads the prompt from stdin
```
Each iteration runs Verify and exits 0 on a pass. On failure it pipes the agent a short prompt on stdin: goal, command, exit code and the last `--tail` lines. Agent output goes to `.git/uak-loop.log`, so it never floods your context.
- It stops when the same failure repeats twice in a row (it compares a hash of the failure), so tokens are not burned on a loop going nowhere.
- With `--task ID` it renews the heartbeat every iteration and marks the task BLOCKED on exhaustion.
- `--prompt FILE` adds task context, for example the task section from TASKS.md.
- Safety: the agent runs with ITS OWN permissions. Keep the uak guard hooks on, and never loop on a command that deploys or publishes.

## Rules
- Verify from a clean build. An e2e suite that passes against a stale `dist/` or cache proves nothing (UpiixSol: 12/12 green, 3 failures after a fresh build).
1. No loop without a machine verifier. "Looks good" is not a verifier.
2. Feed back failures, not history: the error tail and the diff stat, never full logs.
3. Detect lack of progress (the same error, or the same diff) and stop early.
4. Every loop leaves a trace: the worklog event, the loop log and the final status.
5. A loop never widens its own permissions or edits its own verifier. Changing a test to pass is a reviewable change, not a fix.
