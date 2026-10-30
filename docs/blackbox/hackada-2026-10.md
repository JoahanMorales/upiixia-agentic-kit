# Black box · HackADA (Oct 29, 2026) · a 4-hour sprint on a copied repo, reconstructed from claims

Source: one sprint-mode hackathon (first place) on kit **v5.3.0**, 9 agent identities on Claude Code on 4 laptops (macOS and
Windows), 27 tasks in ~4 h, 25 reviews, 97 messages, 25 decisions. Read from the claims branch
(`blackbox/*.md` from 4 machines, `inbox/log.md`, `memory/LESSONS.md`, `DECISIONS.md`, worklogs, reviews) and the
product on `main`. 25 of 27 tasks integrated, 2 cancelled.
Status column: what v5.9.0 does about it (**fixed**, **already fixed** by a release the event did not have, or **kept**).

The root cause of most rows: the repository started as a copy of the previous hackathon's, `.uak/` included, so it
ran uak 5.3.0 while five releases of fixes (v5.4 to v5.8: the frontend gate among them) sat in the kit.

| # | Kind | Where | What happened | Count | Status |
|---|---|---|---|---|---|
| 1 | hole | install | The repo was a copy of the previous event's and kept its kit, v5.3.0. Nothing said a newer kit was installed on the same laptops | the event | **fixed**: `uak start` compares the project's kit with `~/.uak-kit` and the kit's latest tag, and says `install.sh --mode … --update .` (`UAK_KIT_PIN=1` to stay) |
| 2 | bug | plan | A published Verify had an unbalanced quote (`bash -c '…' && … '`). It was approved, then red at the gate as "unexpected end of file"; an agent diagnosed it by hand | 1 | **fixed**: `uak plan` (and `--amend`) refuses a Verify `bash -n` cannot parse; `uak lint` fails it |
| 3 | bug | merge gate | `! rg -n -i "old brand" …` in Verify: where rg is missing (Git Bash on Windows), "command not found" is a failure and `!` makes it a success, so the check passed for any code | 1 task | **fixed**: the gate refuses a green Verify whose log says "command not found"; lint warns about a negated rg |
| 4 | friction | Windows | `uv` was not on PATH on two Windows laptops; agents ran `python -m uv` or `pip install --user uv` task by task | 2 laptops | **fixed**: `doctor` lists the tools the plan's Verify commands run that this machine lacks, with the winget line for uv |
| 5 | bug | Windows | `zoneinfo` without `tzdata`: the app failed to import (ZoneInfoNotFoundError); the request to add it went to a human and waited; agents ran `uv run --with tzdata` | 2 laptops | **already fixed** in v5.4 (the stack adds `tzdata`) |
| 6 | bug | CI | Every PR's CI check failed: the product smoke could not find `uv` (exit 127) | all PRs | **already fixed** in v5.4 (`setup-uv` before the smoke) |
| 7 | bug | product | Vite read only `web/.env` while the one `.env` lived at the repo root, and worktrees had no `.env` at all: the map said "needs a Mapbox key", and that screenshot went into the README | every worktree | **fixed**: the stack's `vite.config.ts` has `envDir: ".."`; `wt new` links the main checkout's git-ignored `.env` files into the worktree (a copy on Windows) |
| 8 | bug | product | The map rendered blank in production: its container had no height | 1 | **fixed** (rule): `product-ui`'s map recipe gives the container a real height; already, a keyless basemap (v5.8) and the screenshot gate (v5.8) would have shown both |
| 9 | hole | frontend | Without the v5.8 gate: cards inside panels, a tracked-out eyebrow, a disabled button as the accent at low opacity, "not tested in a browser" in an approval | the UI | **already fixed** in v5.8 (screens ship with screenshots and the critic's SHIP; design-lint flags these) |
| 10 | friction | merge gate | 4 approved merges went to the human queue for files outside Paths (`web/package.json`, another task's `index.tsx`, a new test fixture, another task's service); humans merged 4 PRs on GitHub | 4 | **already fixed** in v5.7 (`done` warns with SCOPE? before review) |
| 11 | friction | `uak done` | `done` without `--pr`, then without `--evidence`, then "Invalid option" | 8 | **already fixed** in v5.5 (one error names both flags and the whole command) |
| 12 | friction | identity | `inbox` and `followup` from the main checkout without `UAK_AGENT` | 2 | kept: the error gives the prefix |
| 13 | praise | guard | Blocked `rm -r` outside the worktree (3), `worktree remove --force`, two reads of `.env`, and a session at its 40th subagent | 7 | kept |
| 14 | praise | review | The one reject named the files outside Paths and the clash with another task on one service; an agent's request named the broken quotes of row 2 | 1 reject | kept |

What v5.9.0 changes, with a test each in `kit/.uak/tests/test_v59.py` (all 5 fail on v5.8.0): rows 1, 2, 3, 4 and 7.
