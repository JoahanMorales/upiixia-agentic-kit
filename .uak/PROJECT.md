# PROJECT · UPIIXIA Agentic Kit (developed with itself)

> This repository develops the kit with the kit: its roadmap is `.uak/TASKS.md`, agents claim those tasks on the
> `claims` branch of this repo, work in worktrees and ship through review and the merge gate. The engine is the one in
> `kit/` of the same checkout (`.uak/bin/*` are 3-line shims). Rules for working here: the root `AGENTS.md`.

## Purpose
A multi-agent coordination kit that a team installs in one command and that keeps working on Windows, macOS and
Linux. Every change ships with a test that fails without it, on all three.

## Non-negotiable principles
1. Bash 3.2 + POSIX tools for the engine, Python 3.8+ standard library for the MCP server, tests and scripts. No new
   runtime (decided Nov 2026: no Go or Rust engine).
2. Nothing reaches `main` without the suite (`kit/.uak/bin/smoke --package-only`) and `scripts/kit_lint.py` green.
3. Agents' output is a contract: a changed message is a changed API (`docs/ARCHITECTURE.md`).

## Executable config
```text
Mode: marathon
Backlog-Proposed-Epoch: 0
Backlog-Approved: no
Autonomy: yes
Auto-Merge: no
Review-Mode: claims
Plan-Channel: claims
Freeze-Epoch: 0
Lease-Seconds: 14400
Review-Lease-Seconds: 86400
Events-Per-Session: 150
Checkpoint-Percent: 60
Merge-Lease-Seconds: 1800
Merge-Wait-Seconds: 180
Max-Parallel-Subagents: 3
Opus-Subagents-Per-Session: 4
Pace: auto
Max-Worktree-Agents: 4
Blackbox: on
Additive-Paths: -
Test-First: yes
```
