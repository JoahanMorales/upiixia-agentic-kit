# Guide

Walkthroughs: what to do, in order, and what each step does. The lists of options and commands are in
[REFERENCE.md](REFERENCE.md); the measurements are in [EVIDENCE.md](EVIDENCE.md). Commands are written as they run in a
project where the kit is installed (`bash .uak/bin/uak ...`).

## The setup page

```bash
git clone --depth 1 https://github.com/JoahanMorales/upiixia-agentic-kit ~/.uak-kit
bash ~/.uak-kit/install.sh --wizard .
```

The terminal starts a local page (a Python standard-library server on `127.0.0.1`) and opens your browser on it.
Keep the terminal open; Ctrl+C there stops the page, and so does closing the page or leaving it idle. Nothing is
written to your project before you press Install. The page only starts for a person: it refuses inside an agent's
session or a task's worktree.

It has one screen per job, with the progress at the top and, at the right, what the screen will write:

1. **Your project**: what was found (a new or existing repository, a hook manager such as husky or lefthook, CI,
   tests, the stack), the mode proposed with its reason, and your coding tools.
2. **Install**: the files that will be written and how the kit's Git hooks sit beside the team's.
3. **Unblock**: only when something fails, one problem at a time with its fix.
4. **How your team will work**: the rules of `.uak/PROJECT.md` in plain words, with the mode's defaults.
5. **People**: your name, the reviewers, the roles.
6. **Schedule**: hackathon mode only; the start, the end and when new work stops.
7. **Publish the kit**: the kit's files committed and pushed to `main`, after you review the list.
8. **Idea and plan**: your idea, the design direction when the project has screens, the plan written by Claude Code or
   Codex, and your approval.
9. **Start**: the command for each agent, and a note when the first one has claimed a task.
10. **Dashboard**: the team's progress, deploying, extra skills, and "Close the wizard".

A command shown in a copy box also has a button that runs it from the page; "Start this agent" opens a terminal
window of your system in the project folder with the agent already running. When no window can be opened (a remote
machine, no display), the button says so and the copy box stays. The page runs only actions from a fixed list, never a
command line sent by the browser. Details: [DASHBOARD.md](DASHBOARD.md).

## Install from a terminal and reach the first claim

```bash
git clone --depth 1 https://github.com/JoahanMorales/upiixia-agentic-kit ~/.uak-kit
bash ~/.uak-kit/install.sh --mode sprint .
bash .uak/bin/uak start
```

There is no default mode: `sprint` for a deadline with judges, `marathon` for a product with users after launch. At a
terminal the installer ends by asking whether to continue in the browser or in the terminal; with no terminal (a
pipe, CI, an agent) it asks nothing and prints both commands. To update the kit later, run the installer again with
`--update`: it replaces the engine and keeps your `PROJECT.md`, `TASKS.md` and `OWNERS.md`; a kit file you edited
gets the new version beside it as `.uak-new`.

Then, in your coding tool: `/uak-setup` and `/uak-plan` (in Codex `$uak-setup` and `$uak-plan`). Codex, Cursor and
Gemini CLI read `AGENTS.md` by themselves. Run `bash .uak/bin/uak start` again until it prints `START READY` and the
command that claims the first task.

In Claude Code, the first time in a folder: run `claude` there once and accept the trust question, or Claude Code
ignores the repository's settings and an agent started without a window stops at its first command.

## When nothing can be claimed yet

The first claim needs the kit pushed to `main` (agents read `main`'s copy, not yours), an approved plan, and a
reviewer who is not the author. `uak start` checks these in order and names the fix for each:

```text
OK    1. kit installed (sprint, uak 6.8.0)
OK    2. remote origin reachable
TODO  3. preflight: doctor found 1 failure(s)
         · sprint without Freeze-Epoch: uak clock "START" "DEADLINE" [ZONE] --write sets it
TODO  4. push the kit to main: agents read .uak/PROJECT.md and .uak/TASKS.md from origin/main, and it has none yet
```

`bash .uak/bin/uak start --fix` does the mechanical fixes. An agent gets the same answer from `uak next`: with nothing
to offer, it gives the reason for each task (an unapproved plan, an overlap, a dependency).

**Alone on the repository.** GitHub never lets the author of a pull request approve it. Install with `--solo`: agent
identities review each other on the `claims` branch (`Review-Mode: claims`), and in `marathon` you still merge.

## A task from claim to merge

What one agent does, and what the kit checks at each step:

| Step | Command | What the kit checks |
|---|---|---|
| Pick | `bash .uak/bin/uak next` | priority, dependencies, overlapping `Paths`, the freeze |
| Claim | `bash .uak/bin/wt new HACK-001` | no claimed task overlaps these `Paths`; one live task per identity |
| Test first | `bash .uak/bin/uak red HACK-001` | the task's tests fail on an assertion before the code exists |
| Ship | `bash .uak/bin/uak done HACK-001 --pr URL --evidence "..."` | the named tests exist, no existing test was weakened, screenshots for screens |
| Wait | `bash .uak/bin/uak wait HACK-001 --for approve` | returns once, on the verdict |
| Review | another agent: `uak review HACK-001 --sha SHA --verdict approve` | the reviewer is not the author and names the exact commit |
| Merge | `bash .uak/bin/uak merge HACK-001` | the approved commit, the task's scope, the tests again on the merged result |

To start several agents at once: `bash .uak/bin/uak up 4 --tmux` claims four tasks and opens one agent per worktree
in tmux. A task that changes something other tasks use sends them a contract first:
`uak msg impact:HACK-001 --kind contract "what changed"`.

## Follow the work: board and dashboard

`bash .uak/bin/uak board --watch 10` prints the team's board in a terminal. `bash .uak/bin/uak dash --watch --open`
writes a local page from the `claims` branch and keeps it current: what needs a person first, every task as a square
by state, the task list, the board in four stages (to do, in progress, in review, integrated), the agents, the
conversation, the reviews waiting, the black box and the tokens spent. A click on a task opens its story: what it
waits for, the time in each state, who took part and every move in order (`uak timeline ID` prints the same). The
summary can be rearranged and the choice is kept in the browser. The page reads the branch and sends nothing
anywhere. The **Share** button draws an image of the project's figures to download.

## Bounded fix loops

```bash
bash .uak/bin/uak loop --verify "uv run pytest -q" --agent "claude -p --permission-mode acceptEdits" --max 5 --task HACK-007
```

`uak loop` runs any command-line agent that reads a prompt on standard input until the `--verify` command passes,
and stops after `--max` tries, when the same failure repeats, when the agent changed nothing, or when it edited the
test. The failure reaches the agent as the last lines of the log, never the whole log. With `--parallel N --each
"CMD {}"` it runs one small loop per failing test file. The loop rules are in
[LOOPS.md](../kit/.uak/docs/LOOPS.md).

## The task graph and the code map

`bash .uak/bin/uak graph` prints the plan as waves of tasks that can run in parallel and the longest chain of
dependencies; `--mermaid` draws it, `--assign` suggests which idle agent takes which ready task. `uak lint` fails on
dependency cycles and unknown IDs.

`uak map` is a map of the code built with Bash and awk on every change: the symbols, the imports and the calls.
`uak map find NAME` says where something is defined, `uak map users FILE` who imports a file, `uak map impact HACK-001`
which tasks a change touches. An agent reads the map instead of opening files.

`uak learn "what · where · what to do"` stores a lesson on the task's paths; `uak next` shows it to whoever works
there next. `uak recall ID --similar` finds past rejects, contracts and lessons of tasks with similar words.

## How agents are reminded of the tools

Rules in `AGENTS.md` are in the agent's context, but they are read once. The kit also puts the right command where
the decision happens: a short card at the start of each session (when X, run Y), one-line reminders after some tool
calls (many reads in a row: the code map; polling: `uak wait`), the slice of the code map for the task when it is
claimed, and the next step at the end of every command. The effect was measured: see [EVIDENCE.md](EVIDENCE.md).

The same commands are also an MCP server (`.uak/bin/uak-mcp`, Python standard library) for clients without a shell;
install with `--no-mcp` to leave it out. Both share the same state, so an agent can mix them.

## Screens and the design chain

For a project with screens, the plan's first wave includes a design lock: the agents draw several directions, the
person picks one by looking at them (`uak design-gallery`, or `uak design round` and `uak design pick` for a landing
page), and the lock ships the design tokens and the shared components. After that:

- the post-edit hook runs `uak design-lint` on each screen file an agent writes (raw colours, local copies of shared
  components, common generated-look patterns, low contrast);
- `uak done` on a task that changes screens needs screenshots at two widths and the `design-critic` subagent's
  `VERDICT: SHIP` for that commit.

The skills behind it are `frontend-design`, `product-ui` and `landing-story` (see [REFERENCE.md](REFERENCE.md)).

## Deploy

```bash
bash .uak/bin/uak deploy --write
```

`uak deploy` reads the project (FastAPI with or without React, Django, Next.js, a static Vite or Expo build, Go,
Spring Boot, Streamlit, a plain Python server) and proposes one service on Render, or Vercel for Next.js. `--write`
creates the `Dockerfile`, `.dockerignore` and `render.yaml`, never over a file that exists. Only the variable names
from `.env.example` go into `render.yaml`; `.env` is never read. `--disk PATH` gives the service a persistent disk for
the files the app writes. Deploy early, so the first version is online while there is time to fix it.

## The black box

Every `uak` error and guard block is recorded as one anonymous line, and agents add one when the kit slows them down
(`uak bb add friction "..." --fix "..."`). Lines carry no identities, paths, commit IDs or code, and anything that
looks like a secret is dropped. They go to the `claims` branch under `blackbox/`, so a public repository publishes
them. The maintainers read the black boxes of public repositories that use the kit to choose what to fix. Turn it off
with `Blackbox: off` in `.uak/PROJECT.md` or install with `--no-blackbox`. Details:
[BLACKBOX.md](../kit/.uak/docs/BLACKBOX.md).

## A hackathon

One page with the commands of minute 0, the schedule (`uak clock`), the freeze and the fixes per error:
[HACKATHON.md](HACKATHON.md).
