# The visual setup and dashboard

One local page installs the kit, tells you the next step, plans the project and shows its progress. The terminal only
starts it and stays open in the background.

```bash
git clone --depth 1 https://github.com/JoahanMorales/upiixia-agentic-kit ~/.uak-kit
bash ~/.uak-kit/install.sh --wizard /path/to/project     # opens your browser
bash ~/.uak-kit/install.sh --wizard /path/to/project --no-open   # prints the address only
```

The terminal prints `UAK SETUP http://127.0.0.1:PORT/` and the path of a launcher file; the browser is opened on that file, which carries a one-time code (valid two minutes, used once) that the page exchanges for the session. The printed line holds no secret. Keep the terminal open; press Ctrl+C there to stop the page. One page per project: a second start for the same project opens the first one and starts nothing (the record is `uak-wizard.port` in the git directory). Setup ends by itself when the page is closed (and no action runs) or after 15 minutes with no request; SIGTERM, SIGHUP and Ctrl+C end it too. It prints why and the command that opens it again, frees its port at once and ends every child it started (git, `uak`, the planner, in groups it records; a start ends what a killed server left). The planner's limit is 10 minutes. An open page starts no process while nothing happens: the readiness check runs when the page loads, after an action and on a button, never on a timer; polls stop while the page is hidden and back off (20 s, 60 s, 120 s) while nothing changes; a dashboard refresh when nothing moved costs one `git ls-remote`. The wizard starts only for a human: on Linux and macOS it refuses unless its input is a terminal, and in every system it refuses in a process with an agent identity (`UAK_AGENT`, a `.uak-env` naming an agent, `uak.agent` in the git config, a linked worktree), and says how a human starts it.

## Prerequisites

| Need | Why |
|---|---|
| Git, and a project folder that is the root of a Git repository | The kit coordinates through Git. |
| Bash 3.2+ (macOS, Linux) or Git for Windows with Git Bash | The installer and `uak start` run in Bash. Setup uses the Bash that started it. |
| Python 3.8+ (`python3`, `python` or `py`) | The local page is a standard-library Python server. Without it, `--wizard` says so and exits. |
| A browser | Any current one. |

Setup itself needs no account and no API key. Planning from the page (below) uses Claude Code or Codex, signed in.

## The terminal path still works

Nothing above replaces the CLI. The same result without a browser:

```bash
bash ~/.uak-kit/install.sh --mode sprint .    # or --mode marathon; non-interactive, never starts a server
bash .uak/bin/uak start                        # every step to the first claim, in order
```

## The five steps

Nothing is written to your project before you press Install.

| Step | What you do |
|---|---|
| 1. Welcome | Read what will happen, and watch the 75-second demo if you like (a simulated walkthrough from an empty project to a deployed app; captions in English and Spanish; it never starts by itself). |
| 2. Your project | Enter the full path of the repository root. Checking it installs nothing. |
| 3. Your workflow | Hackathon or prototype (`sprint`) or Product with real users (`marathon`); your coding tools (Claude Code, Codex, Cursor, Gemini CLI); "I'm the only human on this repository" (`--solo`). More options: a technology preset, anonymous kit diagnostics. |
| 4. Review & install | See every choice and what will be added (including `.mcp.json`), then install. Setup runs `install.sh` with those options. |
| 5. Get ready | "Check what's next" runs `uak start` and shows its result. Plan your project here (below). |

Above every view, **the journey** stays visible: Install, Prepare, Plan (in this page), Start the team (in a
terminal), Follow progress (your agents do it), with the current one highlighted. The page installs the kit into your
project; the kit itself is downloaded only once. When a step finishes, the page moves you to the next one (after
installing: Prepare; after publishing the kit: Plan your project; after approving the plan: Start your team).

In Spanish, the readiness check's lines are shown translated (the engine's own text stays in Technical details), and
the Advanced dashboard has no English labels. Prepare says whose identity signs the commits and pull requests (the
project's `git config user.name`/`user.email` and `gh`'s login, nothing else from `gh`); if it does not look like
yours, for example on a friend's computer, it says so before anything is published. The typed approval shows the
folder name to type and "Type NAME to enable publishing" under the disabled button.

The page then becomes one workspace with two sections: **Configuration** (the steps, the readiness check, anonymous
diagnostics, usage pacing and the "Your app" link) and **Dashboard** (project progress). The header switches Spanish
or English and Auto, Light or Dark theme.

## Installed is not ready

| State | Means |
|---|---|
| Installed | The kit's files are in the project (`.uak/PROJECT.md`, `.uak/bin/uak`, `.uak/VERSION`). |
| Ready | `uak start` passes every gate: remote reachable, preflight (`doctor`), the kit pushed to `main`, a plan that lints, `Autonomy: yes`, and the plan approved (`Backlog-Approved: yes`). |

The page never decides readiness itself: the next step always comes from the last `uak start`. When it says ready,
the only command offered with a Copy button is the exact claim, `bash .uak/bin/wt new ID`. The gate's fix lines are
shown as text, because they carry branch names and remote URLs.

## Prepare from the page

After installing, the steps the gate asks for come in order in **Get ready**, and the page does them itself:

1. **Your name**: some steps only a person may do (publishing the kit, approving the plan). Setup records them with
   this name, so you never type `UAK_HUMAN=...` into a command.
2. **Event schedule**: start, end and time zone. It writes `Freeze-Epoch` exactly as
   `uak clock START DEADLINE ZONE --write` does and shows, with their dates and in the order they happen, when to take
   the first task and when new work stops. The time zone list starts with your browser's zone; a zone this computer
   does not know (for example `Mars/Base`) is refused at the field.
3. **Publish the kit to main**: *Review the files* lists every kit file that will be committed; *Publish* commits
   exactly those, as your Git identity, and pushes that verified commit to `main`. A kit file is one the installer
   placed: `install.sh` records them in `.uak/installed-files.txt`, so a file of yours under `.github/` or `.uak/` is
   never published. Before pushing, setup checks that the commit holds exactly what you reviewed (each file's content,
   type and mode, and every deletion); if a Git hook changed it, the commit is undone and nothing is published. `IDEA.md`, `.uak/TASKS.md` and
   `.uak/OWNERS.md` are never included: they reach `main` only when you approve the plan. It refuses, with the exact
   recovery, when other files are staged, when `origin/main` has commits this folder lacks, or when the branch has
   commits that are not on the remote.

When the gate needs something only a terminal can do (for example, adding a remote), the page shows a
**Do this in a terminal** box: the exact `cd` into your project with a Copy button, the step, and "come back and
press Check again". The next action is never only in Technical details.

Planning waits until the kit is on `main` (the plan's checks read it from there). If the plan's lint fails for a
reason that is not a plan problem (no `main` yet, Git, network), the page says so; **Check the plan again** reruns
the checks on the current files without running your coding tool again.

## What the page tells you

Every button that sends a request shows it inside the button while it runs ("Checking…", "Publishing…", with a small
spinner and the wait cursor), then a short line right next to it says how it ended: "Done at 21:04." or the error.
**Check what's next** always reports what it found, even when nothing changed: "Checked at 21:04 · nothing changed ·
2 things to do". When the gate's next step is something this page does (publishing the kit, saving your name or the
schedule, the plan), the page scrolls to that control, focuses it and highlights it.

A button that waits for an earlier step is not busy: it shows the not-allowed cursor and says why next to it (for
example, Create the plan: "Publish the kit to main first (step 3)."). Clicking it anyway opens a small notice on the
right (full width at the bottom on a phone) with what to do next and **Go there**; it closes with × or Escape and
hides by itself, but not while the pointer or the keyboard focus is on it. Polling never hides or rebuilds sections, so
the page does not jump while a check runs. Everything follows the page's language and the reduced-motion setting.

A form never sends you elsewhere to read what went wrong: an empty or refused field (the project folder, your name,
the schedule, the idea) shows the reason right under it, is marked invalid for screen readers and gets the focus. A
relative folder such as `my-app` asks for the full path. The page writes these messages itself, in its language, never
the browser's own bubbles. When Git cannot reach the remote, the page says why in one plain sentence with the advice
that fits (the address, the sign-in, the connection or a timeout); Git's own words stay folded under **Technical
details**.

## Coming back to a project

Setup restores where the project is, from the project's own Git (never the network): run the command again on an
installed project and the page opens on the furthest real step (the team step once the plan is approved on main), not
on Welcome. Finished Prepare steps show one done line ("Published on main (commit 9e6debb).") with **Change** to open
them again, and an approved plan is never offered again ("Plan approved on main (commit …)."). The readiness check runs
by itself once after you open or re-pick a project, without switching tabs or moving the focus; `uak start` stays the
only gate. Your name is remembered per project in `.git/uak-setup/human.json` (never committed, shared by the
project's worktrees); if it is missing, the team step asks for it there. Re-picking the same project within ten minutes
keeps its last check. A reload keeps the tab you had open and what you were typing (in this browser only; a restart is
a new address, so only the project's Git carries over). If setup closes, the page says once, in your language, "Setup
has closed: run the command again and open the new link.", stops every button that was waiting, and asks a few more
times (2, 4, 8, 16, 30, 30 s) before it stops; **Retry** asks once more.

## Beginner and Advanced

A choice of presentation, kept in your browser only. It never changes permissions, the mode or any gate.

- **Beginner** shows one step at a time from the readiness gate: the step, why it matters, a checklist of what is
  already done, and one action. It re-checks every minute and when the tab regains focus (Configuration does too), so a
  fix you made in the terminal advances on its own. When the project is ready, it opens project progress.
- **Advanced** shows the full dashboard (board, agents, messages, black box, memory, tokens) and opens Technical
  details. Above it, the same next step as Beginner, with its Copy button.

What the progress view counts is what can really happen (UI-023): a task whose dependencies are not integrated yet
is **Waiting on dependencies**, not available; a review approved for its current commit says **approved**; only a
merge the gate handed to a person counts as **Needs a human**, and that merge is the next step before anything else,
in one plain sentence with no path on your disk. Past the freeze every view says the project is frozen (setup reads
the freeze from `.uak/PROJECT.md` too). When the remote stops answering, the dashboard shows the last claims this
computer read, labelled with their age, instead of the plan with every task free. The board's tabs are ARIA tabs (arrow
keys, Home, End) that wrap on a phone, each view has a heading, small buttons are at least 24 px and text keeps a
contrast of 4.5:1 or more in light and dark.

In Spanish the whole page speaks to you as *tú*, the lines the engine prints (the readiness checks and their hints,
the freeze, the claim states) and every refusal have a Spanish version, and each control has one name. Beginner adds
**Words you will see** beside the steps: what a claim, the freeze, lint, a wave, a worktree, a PR, `origin` and MCP
mean. The planner writes the task titles, criteria and test names in the language of your idea.

Choosing coding tools explains the roles: one tool implements, the other reviews as a second identity. Claude Code +
Codex is the recommended pair. "I'm the only human on this repository" means your agents review each other under a
second name you register.

## The dashboard

One file, `<git dir>/uak-dash/index.html`, opened from `file://`; `data.js` beside it is refreshed by `uak dash --watch`
and the page reloads it by itself. It makes no request and starts no process. A rail at the left (a bar at the bottom on a
phone) has seven tabs: Overview, Board, Agents, Messages, Black box, Memory and Tokens. The tab's title says how many
things need you (`(2) project`) and nothing when none.

**Overview.** Built from eight blocks kept in one registry (`BLOCKS` in `dash.html`: a name, a title, a column, a maximum
of rows and one render function over the data), so a block can later be moved or hidden without a rewrite. Main column:
*Needs you* (a stale remote, a freeze, a merge in the human queue, a review waiting, a stalled task, each with the command to
look at it and its age, then the four figures: agents online, reviews waiting, stalled, needs a human); *Tasks* as a list
of what is moving (blocked, in review, in progress; at most 8 rows) or as four columns, with a search by task or agent;
*Who did what* (one lane per agent, at most 4, from the stories the page carries: builds, reviews, integrations, and a
review over its lease in red; its window is the last 6 hours, widening to 24 h, 3 d or 14 d when nothing is more recent,
and it says when the last move was if nothing moved in 14 days). Side column: *Progress* (one block per task up to 24,
one bar beyond), *Agents* (4, with the rest in the Agents tab), *Integrations* (6 to 8 bars; the period adapts to the
time elapsed, or is fixed at 1 h, 2 h, 4 h or a day, with the date at which the plan ends at that pace) and *Tokens*.
The summary never grows with the plan: 60 tasks add less than 50 px. An empty project shows the one next step and its
command (`bash .uak/bin/uak start`); a finished one says so and shows how to add work.

**All tasks as squares.** Under *Needs you* every task of the plan is one small square (a number inside, the state by colour
and by shape: filled, ringed for review, outlined for in progress, round for blocked, dashed for available, grey for waiting;
a red ring when it is late). Hover, focus (Tab) or tap a square: it lights the tasks it waits for (orange ring) and the ones it
unblocks (violet ring), dims the rest and says in one sentence why it cannot start ("UAK-165 cannot start: it waits for 1 task
- UAK-162 (in progress)") or that it is ready. On a touch screen the first tap selects, the second opens the task. A dependency
on a task that is not in the plan or is cancelled is named as such. The same squares, grouped by stage, are the board's
default view (**Map**; **Cards** shows the columns). A waiting task in the list says what it waits for (two ids and "and N more").

**Board.** Four stages: to do, in progress, in review, integrated. Blocked and late are conditions on the card (a red
border, a tag, the lease used), not columns. Each header says the one thing that matters ("1 waits for your decision",
"2 over their lease"); each column shows 8 cards and a "Show all". Review cards are grouped by what they wait for.
A click on a task (or Enter) opens its detail: header, time in each state, who took part with model and harness, every
move in order, totals. It closes with the button, Escape or a click outside.

In the task's detail, **Waits for / Unblocks** draws the task in the middle, its direct dependencies at the left and what it
unblocks at the right (each with its state and owner; a click opens it), and counts the blockers further back with a way to
expand them.

**Messages.** One conversation per task, told in the task's stages ("In progress", "In review · round 2", "Integrated").
At the left, the conversations as a panel (waiting for you, moving, closed, without a task) with filters (all, my
agents, for me, unread) and a search; at the right, the task, three figures (messages, rounds, changes requested) and who
is in the thread. Messages of your own agents sit at the right; what the engine did is a small centred line. "Unread"
counts what arrived since you first opened the page (kept in this browser). The page has no field to write: it has no server.

**Agents** show the model and harness the engine recorded for each (from the participants of each task and its story), and
"not recorded" when it did not; the page never guesses one. **Black box** is a search tool: counts per kind of event (click to
filter), the harness, the period (24 h, 7 days), a text search, and every entry opens to its command, time, harness and kit,
message and fix (the records carry no agent or task, so a task ID is searched as text). **Memory** has a list and a graph
(hand-written SVG, no library): the nodes are the entries and the tasks, files and agents that two or more of them
mention, and every link is a real reference in the entry (its task field, an ID or a file in its text, its paths, its author);
entries that link to nothing are only in the list. Under 640 px wide it shows the list and says why. **Tokens** break the
spend down by kind of token, harness, model, scope, agent (the owner of the task) and task, with the most expensive tasks and
the average and median per integrated task; the data carries no dates and no budget, and the page says so.

## Appearance: one design system, nine palettes

The setup page and the dashboard are drawn with the same tokens (`docs/design/DIRECTION.md`): one block of CSS custom
properties, the pill, the line of nodes, the window, the single bordered list and the three-figure footer are the same
text in `setup.html` and `dash.html` (a test compares them). One control, **Apariencia**, sets the theme (Auto, Light,
Dark) and the palette: Clásico (the exact colours of the dashboard of v6.8), Lavanda, Cielo, Menta, Salvia, Durazno, Rosa,
Arena and Grafito, each in light and dark. The choice is the viewer's: it stays in the browser (`localStorage`, key
`uak-look`) and changes no tracked file. A page starts in Lavanda in a checkout that never had a dashboard, and in Clásico
where the dashboard's output directory (`<git dir>/uak-dash`) already existed, so nobody's panel changes colour by itself;
the first answer is kept in `uak-dash/palette`.

Type is Inter for text and JetBrains Mono for IDs, commands, pills and counters, shipped as Latin subsets
(`kit/.uak/bin/lib/fonts/`, SIL Open Font License, `OFL.txt`), written next to the dashboard's page and served by the wizard
(`/fonts/…`, `font-src 'self'`), with the system stack behind them. Neither page makes a network request.

`design-lint --strict setup.html dash.html` reads whole HTML pages: colour literals outside the token rules, coloured side
stripes, glass, glow, gradients, emoji and glyphs used as icons, more than six font sizes, and more than one primary button
visible in a view. Status marks are inline SVG icons with their word, never a glyph.

## Plan from the page

In "Get ready", after the kit is installed:

**Claude Code trusts a folder once.** In a folder nobody has opened Claude Code in, it ignores the project's permissions ("this workspace has not been trusted") and the planner stops early. The planning step shows the command that opens Claude Code there (`cd 'FOLDER' && claude`): accept the trust question once and close it. A run that fails for that reason says so; each task worktree asks once too, in the team step's terminal.

1. **What are you building?** One line, who it is for, the judging rubric (sprint) or the spec goal
   (marathon), event length, team size.
   Setup saves `IDEA.md` as plain text. Replacing an existing `IDEA.md` needs your confirmation.
2. **Create the plan.** Claude Code or Codex runs in the background with a fixed command and a constant prompt (your
   text is never part of the command). It is offered only when the tool is installed in the project, found on this
   computer and signed in. Gemini CLI and Cursor cannot plan headless; the page says why. One run at a time.
3. Setup checks the run afterwards: only `.uak/TASKS.md` and `.uak/OWNERS.md` may change (HEAD, the index and its
   flags, Git config, hooks and every tracked, untracked or ignored file are compared). Then it runs `uak lint` itself.
   Anything else is a violation and approval is refused.
4. Read the plan as cards (ID, title, priority, wave, dependencies, tests) with the raw files one click away.
   **Ask for changes** reruns the planner with your note.
5. **Approve and publish.** Type the project folder name. Setup commits exactly `IDEA.md`, `.uak/TASKS.md`,
   `.uak/OWNERS.md` and `.uak/PROJECT.md` (with `Backlog-Approved: yes`), only if they still match what you reviewed,
   pushes that verified commit to `main` and re-checks readiness. It refuses on failing lint, staged files, another
   branch, local commits not on `origin/main`, or your own uncommitted edits in `PROJECT.md`.

## Start your team

After the readiness check says Ready, the dashboard shows **Start your team** (Beginner and Advanced). It stays after
the first claim: when every task is taken the check says "Your team is working" and the step keeps the reviewer
command and a line to reopen each of your claimed tasks.

1. **Register the reviewer.** One button registers `NAME-r` (NAME is the name you gave in Prepare). It is a human act:
   setup runs the engine's `uak register-reviewer NAME-r` from the main checkout with `UAK_HUMAN=NAME`, never from a
   task worktree. Before running, setup reads the claims branch: an identity that is already registered is reported
   with who registered it, a retired one is refused, and a checkout whose `.uak-env` or `git config uak.agent` names
   the reviewer is refused with where that name is set. The result is read back from claims, so a slow push that
   still landed is reported as registered. "Registered" is always read from this project's claims for this name
   (`roles/reviewers` minus `meta/retired`): another project, another name or a retired reviewer never inherits it.
2. **Your tools.** For each coding tool installed in the project and signed in on this computer (the same detection
   planning uses), choose who implements and who reviews. With both, the default is Claude Code implements and Codex
   reviews; any combination works. With one tool, it does both jobs under two names (`TOOL-NAME` writes the code in
   the task worktree, `NAME-r` reviews in the main checkout); the reviewer never reviews its own identity's work. A
   tool that is not installed, not found or not signed in is listed with the reason and never offered. The choice is
   yours: it is kept in `.git/uak-setup/roles.json` of this clone (never committed, never seen by teammates).
3. **The implementer** (Terminal 1, any folder): one Copy command claims the next task with `wt new`, enters its
   worktree and starts the chosen tool with its first prompt (`/uak-start` or `$uak-start`); a second line reopens the
   agent if that terminal closed. A task claimed since the last check is never offered again: the page says so and
   offers **Check what's next**. A second task uses your next free name (`claude-ana-2`).
4. **The reviewer** (Terminal 2, any folder): one Copy command starts the chosen tool as `NAME-r` (`UAK_AGENT`), which
   waits with `uak next` and reviews with `/uak-review` (Claude Code) or `$uak-review` (Codex). A `.uak-env` in the
   main checkout that names another agent would override `NAME-r`, so the page says so instead of a command.
5. **Tasks already claimed:** each claimed, blocked or in-review task, with its owner; yours that have a worktree here
   get a Copy line to reopen the agent there.

Codex runs with `--sandbox workspace-write --add-dir '<the project's .git folder>' -c
sandbox_workspace_write.network_access=true`: Codex keeps `.git` read-only and has no network in that sandbox by
default, and an agent must write refs and fetch and push claims. No approval or sandbox bypass is ever added.

Setup never runs these commands. They are built only from server values (the READY line's task, your name, the
chosen tools, the project folder and its Git folder), start with `UAK_HUMAN=` so no agent inherits human authority,
and are not offered when the folder name holds a quote mark or a control character. On Windows, paste them in Git
Bash, not PowerShell. The first time, each tool asks to approve the project's uak server (MCP): approve it.

**The first run (UI-024).** Agents start only once the reviewer is registered: before that both blocks show what each
terminal will run, with no command to copy, and one line says to register `NAME-r` first (`/api/team` answers
`commands: []`, `locked: {reason, target}` and `waiting: [{id, harness, tool}]`; the ready line of the check points to
the team step instead of the claim command). Claude Code's trust question starts on "No, exit": press ↓ until "Yes,
proceed" and then Enter; an English "Ignoring … permissions.allow entries" warning before it is expected the first
time. Setup reads only whether Claude Code already trusts a folder, from Claude Code's own config
(`$CLAUDE_CONFIG_DIR/.claude.json`, else `~/.claude.json`, read-only, booleans only) and never changes it: `/api/team`
has `trust: {project, worktree}` when a command starts Claude Code and `/api/plan` has `trust` (`true`, `false`, or
`null` when it could not be read; on Windows best effort). **Check again** reads it again after you accept.
`/api/team` also has `people` (from IDEA.md's team size): with two or more, each person runs their own page on their
own computer and never pastes a teammate's commands. While a check runs, `/api/status` keeps the last `checks` with
`checks_stale: true` (the page dims them), the check stops after 45 s (a stalled HTTP transfer after 10 s) and keeps
the old result with an error, `/api/dashboard` answers with the last good dashboard (`stale`, `checking`) or one built
from local copies (`connection: "checking"`), and `/api/team` with its last view or a view with no command
(`checking: true`). A planning run that broke a rule sets `outcome: "problems"` and `problem` in `/api/status`, and
`/api/plan` has `undo: {text, command}` (a `git reset`/`git restore` line when Git can restore everything, else
words); setup never runs it.

**Network.** Setup reads the remote (ls-remote, then a fetch into its own refs `refs/uak/setup-base` and
`refs/uak/setup-claims`, never `FETCH_HEAD`) with a 30 s timeout per command, outside the lock the status poll uses:
the page keeps answering while Git waits. One slow request can take up to two tool probes (20 s each) and three
network commands (30 s each). Offline, the step says setup cannot reach the remote and offers **Retry**, never
"publish"; a project with no remote says so. While an operation runs, the step keeps its last view.

**A remote with its own first commits.** When `main` on GitHub was created with a README, a `.gitignore` or a
license, it shares no history with your folder. Publishing then shows one exact command that keeps both histories
(`git pull --no-rebase --no-edit --allow-unrelated-histories origin main`); files that exist on both sides are first
renamed to `NAME.mine` (the command stops if that name is taken). When setup cannot make it safe, it only suggests
publishing to a new empty repository. A file you track and changed without committing (for example a `.gitignore`
the installer added lines to) gets no pull: the page asks you to commit it first, because Git would refuse to merge over
it; a tracked file on both sides ends in a conflict the page tells you how to resolve. Setup never runs it. When your
folder has commits of its own, a second command (`git push origin main`) sends them after the pull, so publishing then
sends only the kit. A quote mark in the project path is fine: the commands quote it.

**The right branch.** The kit lives on `main`. A folder with commits on another branch (a clone that opened on
`claims`, a detached HEAD, a project whose only branch is `master`) gets a warning when you check it, and Install
stops, with the one command that fixes it (`git switch main`, or `git branch -m master main`). When GitHub made
`claims` the repository's default branch (the first branch pushed to an empty repository), new clones open on
`claims`: the page says so and how to change it (on GitHub: Settings, General, Default branch, choose `main`, Update;
then `git remote set-head origin -a` in each clone).

## Your app

Paste the deployed URL in Configuration. It is saved as `Live-URL:` in `.uak/PROJECT.md` and shown as a link on the
dashboard. Only an absolute `https` address with no user name or password is accepted; a malformed value already in
the file is treated as no link.

## Security model

The page listens on 127.0.0.1 only, on a random port. Every API call needs the session token, which the page gets by exchanging the one-time code of the launcher file
once (the token is never printed, never in a process's arguments and never in a URL); a session with no action of the
person for 30 minutes ends and the terminal says how to open a new one. Your name is the Git identity of the checkout
(`git config user.name`, its first word), shown on the page and never typed; a request that names another is refused.
Registering a reviewer, approving the plan and publishing the kit each write one line to `uak-direct-main.log` in the
project's Git folder (when, who, what, the commit), as a human's direct push does. The server checks the Host header, and every write also checks the Origin.
JSON bodies are limited to 64 KB and nesting depth. Installation options are an allowlist passed as literal arguments,
never through a shell. Text from the project is shown as text. The terminal log never prints requests or tokens.

The demo video is served from the kit that runs setup (`.uak/media/`), never from your project: four fixed addresses
(`/media/tutorial.mp4`, `/media/tutorial-en.vtt`, `/media/tutorial-es.vtt`, `/media/tutorial-poster.jpg`), regular
files only (a symlink is refused), with `nosniff` and byte ranges so the player can seek. Like the page itself and
`workspace.js`, these addresses need the Host check but no token, because a `<video>` element cannot send one; they
carry no project data, and `Cross-Origin-Resource-Policy: same-origin` with a `Sec-Fetch-Site` check keeps other sites
from loading them. When a file is missing the welcome screen simply has no video.

## Troubleshooting

| You see | Do |
|---|---|
| "This setup session expired. Reopen the address printed in the terminal." | The page lost its token (a new tab, a restarted setup, 30 minutes idle). Stop setup (Ctrl+C) and start it again; it opens a new launcher with a new one-time code. |
| "The installed kit version differs from this setup. Use Repair or update first…" | Choose **Repair or update kit**. It keeps your workflow and configuration. |
| "A file named … is blocking a folder the kit needs." | Rename or move that file yourself, then choose **Repair or update kit**. |
| "Visual setup needs Python 3.8+." | Install Python, or use `install.sh --mode sprint|marathon TARGET`. |
| No browser opened | Open the printed address yourself (or you used `--no-open`). |
| You want to stop | Press Ctrl+C in the terminal. Closing the tab does not stop the server. |
