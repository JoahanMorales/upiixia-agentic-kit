---
name: setup
description: Install the UPIIXIA Agentic Kit (uak) into the current Git repository so several AI coding agents (Claude Code, Codex, Cursor, Gemini CLI) can work in parallel with claims, leases, bounded verify-fix loops, reviews and merges. Use when the user wants multi-agent coordination, parallel agents, a hackathon setup (sprint mode) or a production agent workflow (marathon mode).
---
# Install the UPIIXIA Agentic Kit

1. Confirm the current directory is the root of a Git repository (`git rev-parse --show-toplevel`). If not, ask the user.
2. Ask only what's missing, in one message:
   - the mode, chosen by the user: `sprint` (hackathon or prototype with a deadline: speed, auto-merge, a great frontend) or `marathon` (real product with users after launch: specs, security, human merges, CI). Never pick or infer it for them, even if the repo or request hints at one; if they are unsure, show both lines and wait;
   - the stack: `fastapi-react` or `none`;
   - whether the project builds AI tools (`--skills ai`).
3. Find the installer: `install.sh` is two directories above this skill's base directory. If it isn't there, clone the pinned kit:
   `git clone --depth 1 https://github.com/JoahanMorales/upiixia-agentic-kit "$HOME/.uak-kit"` and use `$HOME/.uak-kit/install.sh`.
4. Run `bash <install.sh> --mode <mode> [--stack <stack>] [--skills ai] .`, then `bash .uak/bin/doctor`. Report any FAIL lines to the user with their fix.
5. Tell the user, in 3 lines: the files added (and any `.uak-new` to merge), then the next steps: `/uak-setup` → `/uak-plan` → `bash .uak/bin/wt new ID --agent NAME` per agent.

Never overwrite user files (the installer writes `.uak-new` copies instead). Never ask for or handle secrets.
