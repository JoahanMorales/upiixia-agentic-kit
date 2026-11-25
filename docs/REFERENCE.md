# Reference

The lists: install options, modes, stacks, coding tools, commands and files. The full list of commands, each with
every option, is [CLI.md](../kit/.uak/docs/CLI.md); it is generated from `kit/.uak/bin/lib/commands.tsv`, the one
registry the `uak` command reads. Walkthroughs are in [GUIDE.md](GUIDE.md).

## Requirements and platforms

| Need | For |
|---|---|
| Git with worktrees, and one remote everyone pushes to (GitHub, GitLab or a bare repository) | all coordination |
| Bash 3.2 or newer and POSIX tools (no jq) | the installer and every command; macOS's Bash 3.2 works |
| Git Bash on Windows | Windows; the kit's hooks and MCP server start through Git, never WSL's bash |
| Python 3.8 or newer | the setup page, the dashboard server and the MCP server; the commands do not need it |
| `gh` (optional) | pull requests, and `Review-Mode: gh` |

`uak doctor` names what a machine lacks, including the tools the project's `Verify` commands use.

## Install options

`bash ~/.uak-kit/install.sh [options] TARGET` (the header of `install.sh` is its help):

| Option | Effect |
|---|---|
| `--wizard` | start the setup page instead of installing from the terminal (a person only) |
| `--mode sprint` or `--mode marathon` | the mode; there is no default |
| `--stack NAME` | a stack preset: `fastapi-react`, `nextjs`, `django`, `go`, `expo`, `python-data`, `ai-agent`, `spring-boot`, or `none` |
| `--harness claude,codex,cursor,gemini` | only the folders of the coding tools you use |
| `--skills ai,tdd,taste` | extra skill groups |
| `--solo` | you are the only person on the repository: agents review each other on `claims` |
| `--no-mcp` / `--mcp` | leave out, or add back, the MCP server configuration |
| `--no-blackbox` | the black box off from the start |
| `--with-tests` | also copy the kit's own tests |
| `--update` | replace the engine and keep `PROJECT.md`, `TASKS.md` and `OWNERS.md` |
| `--terminal` | answer "continue in the terminal" to the question at the end of the install |

The installer never overwrites a file of yours: when one differs, the kit's version is written beside it as
`FILE.uak-new`. A file that is an older kit version nobody edited is replaced by `--update`. A hook manager (husky,
lefthook) keeps its `core.hooksPath`.

## Modes

The mode is one line, `Mode:` in `.uak/PROJECT.md`, and only a person changes it.

| | `sprint` (hackathon, prototype) | `marathon` (product with users) |
|---|---|---|
| Planning | idea, scoring rubric, vertical tasks | constitution, spec, plan with threat model, tasks |
| Plan changes | `uak plan` publishes them on `claims` | a reviewed pull request |
| Merge | an agent, after review and the checks | a person, with required CI; agents review first |
| Screens | design lock in the first hours, screenshots and the design critic | the same chain, plus accessibility and performance budgets |
| Safety | a freeze before the deadline (`uak clock`), a recorded demo, a person owns the submission | `security-reviewer`, dependency decisions, architecture decision records |
| Lease / wait in review | 45 min / 4 h | 4 h / 24 h |

The rules of each mode: [sprint.md](../kit/.uak/modes/sprint.md), [marathon.md](../kit/.uak/modes/marathon.md).

## Stacks

`kit/.uak/stacks/` holds one preset per stack: `fastapi-react`, `nextjs`, `django`, `go`, `expo`, `python-data`,
`ai-agent`, `spring-boot`. Each preset holds the stack's notes for agents (`STACK.md`), the skills it adds and an
example smoke test that boots the app (`smoke-project.example`).

## Coding tools

| Tool | What the kit installs for it |
|---|---|
| Claude Code | hooks (guard, prompt guard, heartbeat, inbox, subagent caps, pacing), status line, slash commands, subagents, skills, plugin, MCP server (`.mcp.json`) |
| Codex CLI | `AGENTS.md`, the phase scripts as skills (`$uak-plan`), `.codex/config.toml`, `.codex/agents/`, `.codex/hooks.json`, MCP server |
| Cursor | `.cursor/rules/uak.mdc`, `.cursor/agents/`, `.cursor/hooks.json`, skills, `.cursor/mcp.json` |
| Gemini CLI | `.gemini/settings.json` (reads `AGENTS.md`, hooks), `.gemini/agents/`, `.gemini/commands/`, skills, MCP server |
| any other agent | `AGENTS.md` and the `uak` commands; `uak loop --agent` runs any CLI that reads a prompt on standard input |

The coordination lives in Git, so a team can mix tools.

## Subagent tiers

Every coding tool gets the same six subagents in three tiers, generated from `kit/.claude/agents/` by
`scripts/gen_harness.py`:

| Tier | Job | Claude Code |
|---|---|---|
| fast | read, search, run noisy commands, return a short summary | Haiku |
| balanced | the lead: plans, edits, runs `Verify`, reviews | Sonnet |
| strong | only at plan lock, the same failure twice, and done on risky changes | Opus |

The models for Codex, Cursor and Gemini CLI, and the caps on parallel and strong subagents the `guard agent` hook
enforces, are in [ORCHESTRATION.md](../kit/.uak/docs/ORCHESTRATION.md). `/uak-advise plan|stuck|done` sends the strong
model a short packet instead of the whole session.

## Usage pacing

`uak pace` compares the plan usage left with the time left in each usage window and sets a level the guard applies:
`surge` (usage would expire unspent: more parallel subagents), `normal`, `conserve` (fewer, the fast tier for reads),
`critical` (one subagent, no strong model: finish, checkpoint, hand off). Fixed hard caps in `.uak/PROJECT.md` are
never raised by pacing. The readings come from Claude Code's status line, Codex's session logs, or
`uak pace set` by hand. Levels, caps and plan prices: [COSTS.md](../kit/.uak/docs/COSTS.md).

## Token use

- `kit/AGENTS.md` is the only rules file every agent reads; lint keeps it at 100 lines or fewer, and the rest loads
  on demand from its table.
- `q CMD` prints one line when a test command passes and the last lines when it fails.
- A shell output over 12,000 characters (`Output-Cap-Chars`) reaches the agent as its head, its tail and the path
  of the full log; a large diff becomes an index of files and line ranges.
- The same `status`, `next` or `inbox` twice in a session prints `= unchanged`.
- Only messages an agent must act on are put in its context.
- Skills are installed per mode and stack: each installed skill's description costs tokens in every session.
- `uak tokens` reads the transcripts Claude Code and Codex already write (no API key) and splits the spend by task,
  model, coding tool and subagent.

## Commands

Run as `bash .uak/bin/uak COMMAND`. The most used ones:

| Command | What it does |
|---|---|
| `start [--fix \| --steps \| --wizard]` | each step from install to the first claim, in order, and the fix for the first one missing |
| `next` | what this agent should do now; with nothing to offer, why, per task |
| `doctor [--fix]` | checks the machine: remote, `gh` permissions, hooks, freeze, ports, tools |
| `plan FILE [--amend]` | publish or amend tasks on `claims` (a person: `UAK_HUMAN`) |
| `red [ID]` | records that the task's tests fail on an assertion before the code |
| `done ID --pr URL --evidence TEXT` | send the task to review |
| `review ID --sha SHA --verdict approve\|reject` | review the exact commit |
| `merge ID` | the gated merge |
| `wait [ID] --for approve\|integrated\|message` | returns once when that happens, instead of polling |
| `msg TO TEXT [--kind KIND]` · `inbox` · `digest` | messages between agents · an agent's inbox · a person's summary |
| `handover ID --to NAME` · `release ID` · `followup ID --title TEXT` | pass a task on · free it · more work on an integrated task |
| `integrate ID` | record a task whose approved commit reached `main` another way |
| `up N [--tmux]` | claim N tasks and start one agent per worktree |
| `board` · `dash [--watch] [--open]` | the team's state in a terminal · on a local page |
| `metrics` · `timeline ID` · `stats` · `autopsy` | speed next to instability · one task's story · counts · an event's report |
| `graph` · `map` · `learn` · `recall` | the task graph · the code map · lessons tied to paths |
| `loop --verify CMD --agent CMD` | a bounded fix loop |
| `deploy [--write]` | how the project deploys, and the files for it |
| `design-lint` · `design-gallery` · `design` | the design system check · the design directions side by side · landing rounds |
| `pace` · `tokens` | plan usage pacing · the real token spend |
| `bb add KIND TEXT` | a black box line |
| `skill add NAME` | add one more skill from the kit |
| `allow ID --reason TEXT` | a person lets a task run after the freeze, or change its tests (`--tests`) |

`bash .uak/bin/wt new ID` starts a task (branch, worktree, identity, port, claim); `wt stop` stops its servers;
`wt pr` prints the pull request URL when `gh` cannot open one. `uak --json COMMAND` gives programs the result with a
stable code.

Slash commands (`kit/.claude/commands/`; `$uak-X` in Codex): `/uak-setup`, `/uak-plan`, `/uak-start`, `/uak-loop`,
`/uak-advise`, `/uak-ship`, `/uak-review`, `/uak-handoff`, `/uak-secure`, `/uak-retro`, `/uak-design-lock`, plus
`/uak-demo` in `sprint` and `/uak-spec` in `marathon`.

## MCP server

`.uak/bin/uak-mcp` (Python standard library) offers the commands as 15 MCP tools (`uak_next`, `uak_claim`,
`uak_ship`, `uak_review`, `uak_merge`, `uak_wait`, `uak_map`, `uak_memory` and others), the code map and team state as
resources, and the slash commands as prompts. Every tool runs the same command and the same checks as the shell. It is
optional: `--no-mcp` leaves it out.

## What the install adds

```
AGENTS.md                     the rules every agent reads (.claude/CLAUDE.md points Claude Code to it)
.uak/PROJECT.md               the project's rules: mode, review, merge, freeze, limits
.uak/OWNERS.md · TASKS.md     who owns shared files · the plan, once written
.uak/bin/                     the commands: uak, wt, q, guard, hook, and one file per command family
.uak/docs/                    CLI, PROTOCOL, LOOPS, GRAPH, ORCHESTRATION, COSTS, BLACKBOX, SECURITY, WHY
.uak/githooks/                the Git hooks (pre-commit, pre-push)
.uak/modes/ · templates/ · stacks/ · settings/
.claude/ · .codex/ · .cursor/ · .gemini/ · .agents/skills/   per coding tool, only those you chose
.github/                      the CI workflow and a pull request template
```

Third-party skills are pinned to a commit and keep their licenses: [SOURCES.md](../kit/.uak/skills/SOURCES.md).
