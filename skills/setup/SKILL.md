---
name: setup
description: Install the UPIIXIA Agentic Kit (uak) into the current Git repository so several AI coding agents (Claude Code, Codex, Cursor, Gemini CLI) can work in parallel with claims, leases, bounded verify-fix loops, reviews and merges. Use when the user wants multi-agent coordination, parallel agents, a hackathon setup (sprint mode) or a production agent workflow (marathon mode).
---
# Install the UPIIXIA Agentic Kit

1. Confirm the current directory is the root of a Git repository (`git rev-parse --show-toplevel`). If not, ask the user.
   If `.uak/` already exists, the kit is installed: refresh it with `--update` and the mode in `.uak/PROJECT.md`
   (step 4), never a second plain install.
2. Ask only what's missing, in one message:
   - the mode, chosen by the user: `sprint` (hackathon or prototype with a deadline: speed, auto-merge, a great frontend) or `marathon` (real product with users after launch: specs, security, human merges, CI). Never pick or infer it for them, even if the repo or request hints at one; if they are unsure, show both lines and wait;
   - the stack: `fastapi-react`, `nextjs`, `django`, `go`, `expo`, `python-data`, `ai-agent`, `spring-boot` or `none`;
   - in marathon, whether they are the only human on the GitHub repo (`--solo`: GitHub never lets a PR's author approve it, so reviews happen between agent identities on claims);
   - whether the project builds AI tools (`--skills ai`).
3. Find the installer: `install.sh` is two directories above this skill's base directory. If it isn't there, use the
   kit in `$HOME/.uak-kit`: refresh it when it exists (`git -C "$HOME/.uak-kit" pull --ff-only`), otherwise clone it
   (`git clone --depth 1 https://github.com/JoahanMorales/upiixia-agentic-kit "$HOME/.uak-kit"`), and use
   `$HOME/.uak-kit/install.sh`. If the pull fails, say so and ask before using the old copy.
4. Run `bash <install.sh> --mode <mode> [--stack <stack>] [--skills ai] [--solo] .` (an existing install:
   `bash <install.sh> --update --mode <its mode> .`), then `bash .uak/bin/uak start`. Report each TODO line to the user with its fix (it runs doctor; after `/uak-plan`, run it again until `START READY`).
5. Tell the user, in 3 lines: the files added (and any `.uak-new` to merge), then the next steps: `/uak-setup` → `/uak-plan` → `bash .uak/bin/uak start` → the `wt new ID` it prints.

Never overwrite user files (the installer writes `.uak-new` copies instead). Never ask for or handle secrets.
