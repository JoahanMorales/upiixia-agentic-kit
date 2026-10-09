# Hackathon in one page (sprint mode)

For a team on its way to an event. Every command is real. The full rules are in `kit/.uak/modes/sprint.md`.

## Before you arrive (10 min, each laptop)
- [ ] Claude Code v2.1.293 or later (`claude --version`), Git, and `gh auth login`. Use a token with **Pull requests: write**, or every PR will need a human click (`wt pr` prints the URL).
- [ ] Your plan: on Pro, use 1 agent per person. On Max, use 2. Check it with `/status`.
- [ ] Optional: tmux, to run `uak up N --tmux`.

## Minute 0 (one person, then everyone pulls)
```bash
git clone --depth 1 https://github.com/JoahanMorales/upiixia-agentic-kit ~/.uak-kit
cd your-team-repo && bash ~/.uak-kit/install.sh --mode sprint .   # YOU choose the mode; there is no default
bash .uak/bin/doctor                                               # every laptop, until DOCTOR PASS
```
Then open Claude Code in the repo:
1. `/uak-setup` asks for the event, the deadline with its time zone, the rubric, the humans and the submission owner. It sets `Freeze-Epoch` = deadline − 6 h and commits.
2. `/uak-plan` turns IDEA.md into tasks with a wide wave 1. Approve it and it pushes.
3. Each human registers the other humans' agents as reviewers: `UAK_HUMAN=ana bash .uak/bin/uak register-reviewer luis-1`.
4. Start the agents: `UAK_HUMAN=ana bash .uak/bin/uak up 2 --tmux` (at most 2 per human). Without tmux it prints one `cd … && claude` per terminal.

## During the event
| You want | Run |
|---|---|
| See the team | `bash .uak/bin/uak board --watch 10` |
| Your queue (reviews, blockers, decisions) | `bash .uak/bin/uak digest` |
| Plan usage vs time left | `bash .uak/bin/uak pace` (also in the Claude Code status line) |
| Add tasks (no PR) | `UAK_HUMAN=ana bash .uak/bin/uak plan wave2.md` |
| A PR merged on GitHub while its agent was away | `bash .uak/bin/uak integrate ID` |
| Stop a worktree's servers | `bash .uak/bin/wt stop` (never `pkill -f`) |
| Report a kit problem | `bash .uak/bin/uak bb add friction "what" --fix "idea"` |

Clock: design lock at T+1 h (`/uak-design-lock`), the walking skeleton by T+2 h, plan-B video at T−50%, a human owns submission from T−8 h, freeze at T−6 h, a clean rehearsal at T−2 h (`/uak-demo`), and submit at T−1 h.

## Budget safety (already on)
- The lead runs on Sonnet, scouts on Haiku, and Opus only at 3 checkpoints.
- `uak pace` raises or lowers subagent caps with your 5-hour window. When you hit `critical`, agents hand off before the wall.
- Hard limits that pacing never raises: 6 parallel subagents, 3 Opus per session, 40 spawns per session, 8 per laptop, 6 per minute, and 6 agents per `uak up`.

## If something breaks
| Message | Fix |
|---|---|
| `No identity` | work inside the task worktree (`wt new` writes `.uak-env`), or `git config uak.agent NAME` |
| `depends on X (REVIEW)` | its PR is merged: `uak integrate X` |
| `Diff outside Paths: e2e/…` | add the tests dir to `Additive-Paths` in PROJECT.md (human, via main) |
| `gh pr create` 403 | `bash .uak/bin/wt pr` and open the URL |
| `address already in use` | `bash .uak/bin/wt stop`; ports come from `$UAK_PORT` |
| A subagent was blocked | read the reason: pace level or a hard limit. Do the step yourself or wait |

After the event: `/uak-retro`, then `uak bb export`, and commit `.uak/BLACKBOX.md`. That's how the kit gets better.
