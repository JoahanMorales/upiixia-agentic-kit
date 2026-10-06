# Examples

| Example | What it shows |
|---|---|
| [`ai-hackathon/`](ai-hackathon/) | A 10-task backlog for a 24 h AI hackathon (chat with PDFs, cited answers). Wave 1 has 7 tasks that can start at once, so 6 agents never wait. Contracts replace hard dependencies. [Graph](ai-hackathon/graph.md). |

Try one:
```bash
cp examples/ai-hackathon/TASKS.md <your-repo>/.uak/TASKS.md
bash .uak/bin/uak graph --min-wave1 6   # waves, critical path, cycles
bash .uak/bin/uak up 6 --tmux           # claim the 6 best tasks and launch one agent per worktree
```
