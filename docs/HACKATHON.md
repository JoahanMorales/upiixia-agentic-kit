# Hackathon in one page (sprint mode)

For a team on its way to an event. Every command is real. The full rules are in `kit/.uak/modes/sprint.md`.
Lessons from past events: `docs/blackbox/reap-2026-10.md` (4 h, 12 agents) and `docs/blackbox/mlb-2026-10.md` (10 days, 4 Windows laptops).

## Before you arrive (10 min, each laptop)
- [ ] Claude Code v2.1.293 or later, Codex or Cursor, Git, and `gh auth login`. Use a token with **Pull requests: write**, or every PR will need a human click (`wt pr` prints the URL).
- [ ] Windows: use Git Bash, and keep the repo **outside OneDrive/Dropbox** (sync locks files git writes; `doctor` warns).
- [ ] Python projects: create `.venv` in the main checkout; the merge gate uses it.
- [ ] Your plan: on Pro, use 1 agent per person. On Max, use 2. Check it with `/status`.
- [ ] Optional: tmux, to run `uak up N --tmux`.

## Minute 0 (one person, then everyone pulls) — first claim within 20 min
At Reap, setup and planning took 2 of the 4 hours. Timebox them.
```bash
git clone --depth 1 https://github.com/JoahanMorales/upiixia-agentic-kit ~/.uak-kit
cd your-team-repo && bash ~/.uak-kit/install.sh --mode sprint --stack python-data .   # YOU choose the mode; stacks: fastapi-react nextjs django go expo python-data ai-agent
bash .uak/bin/uak clock "2026-10-09 17:00" "2026-10-09 21:00" America/Mexico_City --write   # schedule + Freeze-Epoch
bash .uak/bin/doctor                                               # every laptop, until DOCTOR PASS
```
Then open your agent in the repo:
1. `/uak-setup`: the event, the rubric, the humans and the submission owner. Commit.
2. `/uak-plan` turns IDEA.md into tasks with a wide wave 1 (short event: at most 2 tasks per agent, 45 min each).
3. One human registers every agent as reviewer, from the main checkout: `UAK_HUMAN=ana UAK_AGENT= bash .uak/bin/uak register-reviewer ana-1 ana-2 leo-1 leo-2`.
4. Start the agents: `UAK_HUMAN=ana bash .uak/bin/uak up 2 --tmux` (at most 2 per human). One identity = one live task.

## During the event
| You want | Run |
|---|---|
| See the team | `bash .uak/bin/uak board --watch 10` |
| Your queue (reviews, blockers, decisions) | `bash .uak/bin/uak digest` |
| Plan usage vs time left | `bash .uak/bin/uak pace` (also in the Claude Code status line) |
| Tokens spent, per task and model | `bash .uak/bin/uak tokens --team --by model` |
| Who should take the next tasks | `bash .uak/bin/uak graph --assign` |
| Pass a task to another agent | `bash .uak/bin/uak handover ID --to ana-2` |
| Add tasks (no PR) | `UAK_HUMAN=ana bash .uak/bin/uak plan wave2.md` |
| Allow a task after the freeze (audited) | `UAK_HUMAN=ana bash .uak/bin/uak allow HACK-010 --reason "demo breaks"` · everything in flight: `allow --in-flight --reason "..."` |
| A merge went to the human queue | read the reason; if the PR is fine, merge it on GitHub, then any agent: `bash .uak/bin/uak integrate ID` |
| An approved task nobody merged (20 min) | any agent: `bash .uak/bin/uak merge ID` (`next` says so) |
| More work on an integrated task | `bash .uak/bin/uak followup ID --title "what"` |
| An agent you closed for good | `UAK_HUMAN=ana bash .uak/bin/uak retire ana-3` |
| Stop a worktree's servers | `bash .uak/bin/wt stop` (never `pkill -f`) |
| Report a kit problem | `bash .uak/bin/uak bb add friction "what" --fix "idea"` |

Never tell an agent "the human authorizes everything" through another agent: run `uak allow` yourself.

## Budget and tokens (already on)
- The lead runs on the balanced model, scouts on the fast one, the strong model only at 3 checkpoints.
- `uak pace` raises or lowers subagent caps with your 5-hour window. Hard limits it never raises: 6 parallel subagents, 3 strong per session, 40 spawns per session, 8 per laptop, 6 per minute, 6 agents per `uak up`.
- Context: huge outputs are cut to head + tail (Claude Code, Codex and Cursor), repeated `status`/`inbox` print `= unchanged`, acks are refused, one message reaches many tasks in one line, and `LOOP:` stops retry loops.

## If something breaks
| Message | Fix |
|---|---|
| `No identity` | work inside the task worktree (`wt new` writes `.uak-env`), or `git config uak.agent NAME` |
| `already holds HACK-X` | finish or release it, or start another agent with its own name |
| `FREEZE: … not allowed` | a human runs `uak allow ID --reason TEXT`; otherwise review, rehearse, stop |
| `depends on X (REVIEW)` | its PR is merged: `uak integrate X` |
| `Shared resource/CI needs a human` | a human merges that PR on GitHub, then `uak integrate ID` |
| `gh pr create` 403 · `PREFLIGHT: gh …` | `bash .uak/bin/wt pr` and open the URL |
| `address already in use` | `bash .uak/bin/wt stop`; ports come from `$UAK_PORT` |
| `MERGE_WAIT` | no approval on that SHA yet: wait for the approve message (a clean merge of main keeps the approval) |
| `MERGE_BUSY` | another merge holds the queue: rerun in a few minutes |
| `Smoke red …: <error> (log: …)` | read the quoted line; Python: is there a `.venv` in the main checkout? |
| `… is already reviewing` | another agent has that review; take other work |
| `FREEZE in N min` | finish the criterion and `uak done`, or release |
| `RETRY … contention` | normal with many agents; it backs off and retries by itself |
| `LOOP:` | stop retrying that command; read the error |

## Events longer than a day
Nights are normal (`uak clock` prints LONG EVENT advice). To let deadlines advance with nobody online, rename
`.github/workflows/uak-tick.yml.example` to `uak-tick.yml` for the event (it bills ~96 Actions minutes a day). Approved tasks get merged by whichever agent is awake;
REVIEW leases expire without recovery noise; humans read one `uak digest` per morning. Retire identities you will
not reopen, so reviews stop going to them.

After the event: `/uak-retro`. The black box is already on the claims branch; `uak bb flush` sends what a laptop still has pending.
