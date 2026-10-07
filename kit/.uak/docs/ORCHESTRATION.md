# Subagent orchestration: Haiku swarms, Sonnet builds, Opus advises

Goal: the best result per token. The strongest model wakes up only where judgment changes the outcome. Verified against the Claude Code docs (Oct 2026: Haiku 5.5, Sonnet 5.5, Opus 5.5; `advisorModel`; subagent `model`/`effort`/`maxTurns`).

## Roles
| Tier | Model | Does | Never does |
|---|---|---|---|
| **Lead** | Sonnet 5.5 (`model: sonnet`; sprint `effortLevel: medium`, marathon `high`) | owns the task: plans, edits, runs Verify, decides | reads 20 files to "get context" (send scouts) |
| **Scouts** | Haiku 5.5 (`uak-scout`, `uak-runner`, `effort: low`) | find files, symbols, call sites, docs; run noisy commands; return ≤15-line summaries | edit, decide, call the advisor, spawn subagents |
| **Specialists** | Sonnet (`uak-reviewer`, `design-critic`) | independent review of a PR or UI | edit the reviewed code |
| **Advisor** | Opus 5.5 (`advisorModel: opus`, server-side advisor tool) | reviews at 3 checkpoints with the full transcript | run on routine turns |
| **Architect** | Opus 5.5 (`uak-architect`, `security-reviewer`) | the same 3 checkpoints from a compact packet; security reviews | swarm, or join routine work |
| **Planner** | Opus (the `/uak-plan` command runs on `model: opus`) | builds the backlog graph once per wave | implement |

## The 3 checkpoints (the only times Opus is consulted)
1. **Plan lock**, before a plan that touches more than 2 files or any contract. Check for missing auth or data invariants, schema or contract breaks, and wrong ordering.
2. **Stuck**, when the same test or compiler error fails twice. Check whether it's the root cause or a rabbit hole, and which single experiment decides.
3. **Done**, before `uak done` on risky diffs (auth, data, money, migrations, more than 300 lines). Check for hidden regressions, weakened tests and SECURITY.md items.

How to consult:
- **Short session, Anthropic API:** say "consult the advisor" (advisor tool). It reads the whole transcript, uncached, on every call, so it is cheap only in short sessions. One task per session keeps it cheap.
- **Long session, or Bedrock/Vertex/Foundry (no advisor tool):** `/uak-advise <plan|stuck|done>` builds a packet of 40 lines or fewer for `uak-architect`. That costs fewer tokens than replaying a long transcript.
- The advisor timing is model-driven: Claude Code cannot force or cap advisor calls. These checkpoints are instructions in CLAUDE.md and the `/uak-*` commands.

## Delegation rules (lead)
- **Delegate** when a lookup needs about 3 or more searches or reads, or when output may exceed about 30 lines. Run up to 3 scouts **in parallel** on **disjoint** questions in one message.
- **Do it yourself** when it's one `rg` or one file read: spawning a subagent costs more than doing it.
- **Ask precise questions.** "Where is session expiry enforced? Give file:line" beats "look at auth".
- **Never fan out Opus.** The guard caps Opus subagents per session (`Opus-Subagents-Per-Session`, sprint 2, marathon 4), with `UAK_ALLOW_OPUS=1` as the human override.
- **No nested swarms.** `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` means subagents cannot spawn subagents.
- **Parallel cap.** `Max-Parallel-Subagents` (sprint 4, marathon 3) is enforced by `guard agent`, **including under ultracode**, which bypasses Claude Code's own cap. `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` is set to match.
- **Cheap default.** `general-purpose` and other subagents with no `model` default to Haiku (`CLAUDE_CODE_SUBAGENT_MODEL=haiku`). For edit-heavy delegated work, pass `model: sonnet` explicitly.
- **Scouts return summaries, never files.** Their output enters the lead's context once and is re-sent on every later turn.

## Configuration (installed by `install.sh`)
| Where | Setting |
|---|---|
| `.claude/settings.json` | `"model": "sonnet"`, `"advisorModel": "opus"`, `"effortLevel": "medium"` (sprint) or `"high"` (marathon) |
| `.claude/settings.json` → `env` | `CLAUDE_CODE_SUBAGENT_MODEL=haiku`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=4`/`3`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` |
| `.claude/settings.json` → hooks | PreToolUse `Agent\|Task` → `guard agent` (parallel cap + Opus budget + log) · SubagentStop → `guard agent-stop` |
| `.claude/agents/*.md` | each subagent pins `model`, `effort` and `maxTurns`, and drops `Agent`, `Edit`, `Write` where it only reads |
| `.uak/PROJECT.md` | `Max-Parallel-Subagents`, `Opus-Subagents-Per-Session` |

These need Claude Code v2.1.293 or later for Haiku 5.5. On Bedrock, Vertex or Foundry, `haiku` resolves to Haiku 4.5 and the advisor tool is unavailable: use `/uak-advise`.

To check what was spent: `uak stats` reads `.git/uak-agents.log` (subagents by tier and type) and the session's `/usage`.

## Verified end to end (2026-10-07, Claude Code 2.1.293)
In a fresh repo with the kit installed, one headless run of `claude -p "Use the uak-scout subagent to answer: which file tests the search function…"` gave:
- the lead ran on `claude-sonnet-5-5` and the scout on `claude-haiku-5-5`, from the installed settings and agent frontmatter;
- `guard agent` logged `haiku uak-scout`;
- the total cost was **0.085 USD**;
- the scout flagged an unrelated instruction that an account-level connector had injected into its context, and ignored it (AGENTS.md §1.4).

## What we did NOT adopt (claims that circulate online)
| Claim | Status |
|---|---|
| `claude --advisor opus` · `/advisor` · `advisorModel` | **real**; adopted |
| `--subagents haiku` flag | **does not exist**; use subagent `model:` or `CLAUDE_CODE_SUBAGENT_MODEL` |
| "parallel dispatcher pool (3x workers)" setting | **does not exist**; the real knob is `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` (default 20, ultracode exempt), so we add our own guard |
| "auto-summon the advisor when a test fails twice" | **cannot be enforced**; it's an instruction, so we wrote it into the loop rules |
| "JEV micro-fork layer resolves 1,500 branches in 16 ms", "340 tok/s" | **no evidence**; ignored. Our deterministic layer is the `uak` CLI itself (claims, gates, loops) |
