# The visual setup and dashboard

One local page installs the kit, tells you the next step, plans the project and shows its progress. The terminal only
starts it and stays open in the background.

```bash
git clone --depth 1 https://github.com/JoahanMorales/upiixia-agentic-kit ~/.uak-kit
bash ~/.uak-kit/install.sh --wizard /path/to/project     # opens your browser
bash ~/.uak-kit/install.sh --wizard /path/to/project --no-open   # prints the address only
```

The terminal prints `UAK SETUP http://127.0.0.1:PORT/#TOKEN`. Keep it open; press Ctrl+C there to stop the page.

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
| 1. Welcome | Read what will happen. |
| 2. Your project | Enter the full path of the repository root. Checking it installs nothing. |
| 3. Your workflow | Hackathon or prototype (`sprint`) or Product with real users (`marathon`); your coding tools (Claude Code, Codex, Cursor, Gemini CLI); "I'm the only human on this repository" (`--solo`). More options: a technology preset, anonymous kit diagnostics. |
| 4. Review & install | See every choice and what will be added (including `.mcp.json`), then install. Setup runs `install.sh` with those options. |
| 5. Get ready | "Check what's next" runs `uak start` and shows its result. Plan your project here (below). |

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
   `uak clock START DEADLINE ZONE --write` does and shows when new work stops and the time of the first claim.
3. **Publish the kit to main**: *Review the files* lists every kit file that will be committed; *Publish* commits
   exactly those, as your Git identity, and pushes that verified commit to `main`. `IDEA.md`, `.uak/TASKS.md` and
   `.uak/OWNERS.md` are never included: they reach `main` only when you approve the plan. It refuses, with the exact
   recovery, when other files are staged, when `origin/main` has commits this folder lacks, or when the branch has
   commits that are not on the remote.

When the gate needs something only a terminal can do (for example, adding a remote), the page shows a
**Do this in a terminal** box: the exact `cd` into your project with a Copy button, the step, and "come back and
press Check again". The next action is never only in Technical details.

Planning waits until the kit is on `main` (the plan's checks read it from there). If the plan's lint fails for a
reason that is not a plan problem (no `main` yet, Git, network), the page says so; **Check the plan again** reruns
the checks on the current files without running your coding tool again.

## Beginner and Advanced

A choice of presentation, kept in your browser only. It never changes permissions, the mode or any gate.

- **Beginner** shows one step at a time from the readiness gate: the step, why it matters, a checklist of what is
  already done, and one action. It re-checks every minute and when the tab regains focus (Configuration does too), so a
  fix you made in the terminal advances on its own. When the project is ready, it opens project progress.
- **Advanced** shows the full dashboard (board, agents, messages, black box, memory, tokens) and opens Technical
  details.

## Plan from the page

In "Get ready", after the kit is installed:

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

## Your app

Paste the deployed URL in Configuration. It is saved as `Live-URL:` in `.uak/PROJECT.md` and shown as a link on the
dashboard. Only an absolute `https` address with no user name or password is accepted; a malformed value already in
the file is treated as no link.

## Security model

The page listens on 127.0.0.1 only, on a random port. Every API call needs the session token from the address's
fragment (it is never sent in a URL); the server checks the Host header, and every write also checks the Origin.
JSON bodies are limited to 64 KB and nesting depth. Installation options are an allowlist passed as literal arguments,
never through a shell. Text from the project is shown as text. The terminal log never prints requests or tokens.

## Troubleshooting

| You see | Do |
|---|---|
| "This setup session expired. Reopen the address printed in the terminal." | The page lost its token (a new tab, a restarted setup). Open the `UAK SETUP` address from the terminal again. |
| "The installed kit version differs from this setup. Use Repair or update first…" | Choose **Repair or update kit**. It keeps your workflow and configuration. |
| "A file named … is blocking a folder the kit needs." | Rename or move that file yourself, then choose **Repair or update kit**. |
| "Visual setup needs Python 3.8+." | Install Python, or use `install.sh --mode sprint|marathon TARGET`. |
| No browser opened | Open the printed address yourself (or you used `--no-open`). |
| You want to stop | Press Ctrl+C in the terminal. Closing the tab does not stop the server. |
