# Subagent orchestration: fast swarms, a balanced lead, a strong advisor

Goal: the best result per token, in every harness. The strongest model wakes up only where judgment changes the
outcome. Verified 2026-10-09 against the Claude Code, Codex, Cursor and Gemini CLI docs. Prices and plans: `COSTS.md`.

## Tiers (harness-neutral)
| Tier | Claude Code | Codex | Cursor | Gemini CLI | Does |
|---|---|---|---|---|---|
| **fast** (swarm) | Haiku 5.5 | GPT-6 Luna (`gpt-6-luna`) | Composer 2.5 | `gemini-3-flash-preview` | scouts and runners: find, read, run noisy commands, return ≤15 lines |
| **balanced** (lead) | Sonnet 5.5 | GPT-6.1 Sol (`gpt-6.1-sol`) | your model (`inherit`) | your model (`inherit`) | owns the task: plans, edits, runs Verify, decides; reviewers |
| **strong** (advisor) | Opus 5.5 | GPT-6 Astra (`gpt-6-astra`) | `claude-opus-5-5[effort=high]` | `gemini-3-pro-preview` | 3 checkpoints and security reviews; never swarms |

GPT-5.6 family (still rolling out, older accounts): Sol is strong, Terra is balanced, Luna is fast. Replace the IDs in
`.codex/config.toml` and `.codex/agents/*.toml`. The guard already maps both families to the right tier.

The same 6 subagents exist in every harness. `scripts/gen_harness.py` generates them from `.claude/agents/*.md`:
| Agent | Tier | Read-only | Use |
|---|---|---|---|
| `uak-scout` | fast | yes | where/how is X; file:line evidence |
| `uak-runner` | fast | runs commands | tests, smoke, app, probes; verdict only |
| `uak-reviewer` | balanced | yes | independent PR review → `uak review` |
| `design-critic` (sprint) | balanced | yes | UI screenshots vs DESIGN.md |
| `security-reviewer` (marathon) | strong | yes | auth, data, payments, uploads |
| `uak-architect` | strong | yes | the 3 checkpoints from a compact packet |

## The 3 checkpoints (the only times the strong tier is consulted)
1. **Plan lock**, before a plan that touches more than 2 files or any contract. Check for missing auth or data
   invariants, schema or contract breaks, and wrong ordering.
2. **Stuck**, when the same test or compiler error fails twice. Check whether it's the root cause or a rabbit hole,
   and which single experiment decides.
3. **Done**, before `uak done` on risky diffs (auth, data, money, migrations, more than 300 lines). Check for hidden
   regressions, weakened tests and SECURITY.md items.

How to consult:
- **Claude Code, short session, Anthropic API:** say "consult the advisor" (`advisorModel: opus`). It reads the whole
  transcript, uncached, on every call.
- **Long session, or any other harness:** `/uak-advise <plan|stuck|done>` (or ask for `uak-architect`) with a
  packet of 40 lines or fewer.
- Advisor timing is model-driven: no harness can force or cap advisor calls. The checkpoints are instructions; the
  guard caps strong **subagents**.

## Delegation rules (lead)
- **Delegate** when a lookup needs about 3 or more searches or reads, or output may exceed about 30 lines. Run up to
  3 scouts **in parallel** on **disjoint** questions in one message.
- **Do it yourself** when it is one search or one file read.
- **Ask precise questions.** "Where is session expiry enforced? Give file:line" beats "look at auth".
- **Never fan out the strong tier.** The guard caps it per session (`Opus-Subagents-Per-Session`). The human
  override is `UAK_ALLOW_OPUS=1`.
- **No nested swarms.** Claude: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`. Gemini: subagents can't spawn. Cursor:
  depth 2 at most. The scouts' prompts forbid spawning in every harness.
- **Cheap default.** A subagent without a model runs on the fast tier: Claude `CLAUDE_CODE_SUBAGENT_MODEL=haiku`,
  Codex `default_subagent_model = "gpt-6-luna"`. For edit-heavy delegated work, ask for the balanced model.
- **Summaries, never files.** A subagent's output enters the lead's context once, and is re-sent on every later turn.

## Pacing (`uak pace`)
The caps follow plan usage. With 1 h left of the 5 h window and 70% of the budget left, `surge` doubles parallel
subagents and adds 2 strong ones. With 3 h left and 50% left, `conserve` halves them and allows 1 strong one.
`critical` (ratio < 0.6 or ≥ 90% used) allows 1 subagent and no strong ones. The full table and examples are in
`COSTS.md`.

## Enforcement per harness
| | Claude Code | Codex | Cursor | Gemini CLI |
|---|---|---|---|---|
| Lead model | `.claude/settings.json` `model: sonnet` | `.codex/config.toml` `model` | user's pick | user's pick |
| Subagent files | `.claude/agents/*.md` | `.codex/agents/*.toml` | `.cursor/agents/*.md` | `.gemini/agents/*.md` |
| Shell guard | PreToolUse `Bash` | PreToolUse `Bash` (`.codex/hooks.json`) | `beforeShellExecution` (`.cursor/hooks.json`) | `guard check` by hand |
| Spawn cap | PreToolUse `Agent\|Task` (blocks) | SubagentStart (logs; `max_concurrent_threads_per_session` caps) | `subagentStart` (exit 2) | `max_turns`/`timeout_mins` per agent |
| Usage source | statusline `rate_limits` | `~/.codex/sessions` `rate_limits` | `uak pace set` | `uak pace set` |
| Black box flush | Stop hook | Stop hook | `stop` hook | `uak bb flush` |

Codex loads project `.codex/` files only when you trust the project. Review hooks with `/hooks`.

## Configuration installed by `install.sh`
| Where | Setting |
|---|---|
| `.claude/settings.json` | `model: sonnet`, `advisorModel: opus`, `effortLevel` medium (sprint) or high (marathon), `statusLine`, env `CLAUDE_CODE_SUBAGENT_MODEL=haiku`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=4`/`3`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` |
| `.codex/config.toml` | `model = "gpt-6.1-sol"`, effort medium/high, `[agents] max_concurrent_threads_per_session = 4`/`3`, `default_subagent_model = "gpt-6-luna"` |
| `.codex/hooks.json` · `.cursor/hooks.json` | guard, spawn caps, inbox and black box hooks |
| `.uak/PROJECT.md` | `Max-Parallel-Subagents`, `Opus-Subagents-Per-Session`, `Pace`, `Blackbox`, `Additive-Paths` |

To check what was spent: `uak stats` (subagents by tier and type, from `.git/uak-agents.log`) and `uak pace`.

## Verified end to end (2026-10-07, Claude Code 2.1.293)
In a fresh repo with the kit installed, one headless run of `claude -p "Use the uak-scout subagent to answer: which
file tests the search function…"` gave:
- the lead on `claude-sonnet-5-5` and the scout on `claude-haiku-5-5`;
- `guard agent` logged the scout as fast tier;
- a total cost of **0.085 USD**;
- the scout flagged an injected instruction from an account-level connector and ignored it.

Re-run on 2026-10-09 with v4.1 and pacing set to `critical` (`uak pace set 95 --resets +2h`): the lead ran on
`claude-sonnet-5-5`, the scout on `claude-haiku-5-5`, the guard allowed exactly one fast subagent and logged
`fast uak-scout`, and the total was 0.12 USD.

The Codex, Cursor and Gemini files follow their official schemas (validated as TOML/JSON in CI). Their guard
payloads are covered by `test_v41.py`. They have not yet had a paid live run: report results with `uak bb add`.

## What we did NOT adopt (claims that circulate online)
| Claim | Status |
|---|---|
| `claude --advisor opus` · `/advisor` · `advisorModel` | **real**; adopted |
| `--subagents haiku` flag | **does not exist**; use subagent `model:` or `CLAUDE_CODE_SUBAGENT_MODEL` |
| "parallel dispatcher pool (3x workers)" setting | **does not exist**; the real knob is `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (default 20, ultracode exempt), so we add our own guard |
| "auto-summon the advisor when a test fails twice" | **cannot be enforced**; it's an instruction in the loop rules |
| "JEV micro-fork layer resolves 1,500 branches in 16 ms", "340 tok/s" | **no evidence**; ignored |
