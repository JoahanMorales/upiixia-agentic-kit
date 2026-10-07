# Inspirations: what we took, what we changed

UAK is not the first agentic methodology. We read these projects and kept what survived a real hackathon.
Star counts checked on 2026-10-06 and are only there to show how big each community is.

| Project | What it gets right | What UAK takes | What UAK does differently |
|---|---|---|---|
| [AGENTS.md](https://github.com/agentsmd/agents.md) (★25k) | One open, tool-agnostic file for agent instructions | `AGENTS.md` is the core every tool reads; `CLAUDE.md` just imports it | We keep it under 100 lines (lint-enforced) and load the rest on demand |
| [GitHub Spec Kit](https://github.com/github/spec-kit) (★140k) | Constitution → specify → plan → tasks; specs as the source of truth | `marathon` mode: `PROJECT.md` constitution and `/uak-spec` (spec → plan → tasks) | `sprint` mode skips specs on purpose: a rubric plus vertical tasks beats documents when the clock is 24 h |
| [Kiro](https://kiro.dev) specs | EARS acceptance criteria ("When X, the system shall Y") | EARS in `templates/specs/spec.md` | The criteria feed a machine-checked `Cómo verificar` command per task |
| [BMAD-METHOD](https://github.com/bmad-code-org/BMAD-METHOD) (★54k) | Role personas (analyst, PM, architect, dev, QA) and story sharding | Planner / executor / reviewer / demo roles and small vertical tasks | Roles are hats, not separate agents: any agent can review. Fewer personas means fewer tokens |
| [Claude Task Master](https://github.com/eyaltoledano/claude-task-master) (★28k) | Dependency-aware task graph and a "next task" command | `uak next` picks the highest-priority eligible task (dependencies, path overlap, owners, freeze) | Task *state* lives in a Git branch shared by several humans and machines, not in a local JSON |
| [Cline Memory Bank](https://github.com/cline/cline) (★70k) | Persistent context files so a fresh session can resume | Every task keeps a 15-line "live summary" (done, decision, why, failing, commands, next) | The summary lives in the claims branch, so *another* agent on *another* machine can resume it, with a read token to prove it was read |
| [obra/superpowers](https://github.com/obra/superpowers) (★296k) | Battle-tested process skills: TDD, systematic debugging, verification before completion | Vendored and pinned; wired into `/uak-loop` and marathon mode | Installed per mode, to keep skill descriptions out of every session's context |
| [Anthropic skills](https://github.com/anthropics/skills) (★180k), [Vercel agent-skills](https://github.com/vercel-labs/agent-skills) (★32k), [taste-skill](https://github.com/Leonxlnx/taste-skill) (★93k) | Reusable, on-demand expertise | Vendored and pinned (`SOURCES.md`): webapp-testing, mcp-builder, react-best-practices and design-taste | Skills that download remote instructions at runtime were rejected: that is prompt injection by design |
| Claude Code best practices (hooks, subagents, worktrees) | Isolated context per subagent; `/clear` between tasks; native `--worktree` since early 2026 | Hooks for heartbeat, inbox, guard and prompt-guard; Haiku runner and Sonnet reviewer subagents | Worktrees are the *mechanism*; UAK adds the *protocol* across people: claims, leases, reviews and merges |
| [The advisor strategy](https://claude.com/blog/the-advisor-strategy) and Claude Code's advisor tool | A fast main model plus a stronger advisor at decision points | `advisorModel: opus`, with checkpoints at plan lock, stuck and done | Enforced budgets (guard), and a packet-based fallback for long sessions and providers without the advisor tool |
| [wshobson/agents](https://github.com/wshobson/agents) (★40k) | Per-agent model tiers: haiku for lookup, sonnet for building, opus for high-stakes judgment | The same tiering for our subagents, plus `effort` and `maxTurns` per agent | Tiers are enforced at spawn time by a hook, not just declared |
| Loop engineering (2026) | Design the cycle, not the prompt: trigger, verify, retry, stop | `uak loop` and the 5-part loop contract in LOOPS.md | Every loop must have a machine verifier, a budget and stuck detection; failures are fed back as tails, never full logs |
| Graph engineering (2026) | Explicit members, mandates, message paths and state instead of one mega-agent | GRAPH.md maps each concept to a file or command; `uak graph` | The graph is versioned in Git and lint-checked (no cycles, no dangling IDs, a wide wave 1) |
| Single-machine orchestrators (agent swarms, tmux or Docker fleets) | Spawn many agents fast | — | UAK has no server and no daemon. Four humans with their own laptops (one was a Jetson Orin Nano) coordinated through `git push` |

## The gap we fill

Most methodologies assume **one human driving one or many agents on one machine**. Hackathon teams and small startups are different: **several humans, each with 1–2 agents, on different machines and tools, pushing to the same repo**. That needs:

1. **Mutual exclusion without a server**: Git fast-forward pushes on a dedicated branch.
2. **Continuity when an agent dies**: leases, live summaries and read tokens.
3. **Trust boundaries**: the reviewer is not the author, the approved SHA must match, and the diff must stay inside the declared paths.
4. **Two speeds**: a hackathon and a product need opposite defaults, from the same engine.
