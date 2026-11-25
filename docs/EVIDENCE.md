# Evidence

What was measured, when, how, and where the raw data is. A number that could not be traced to a file or a run was
left out. Everything else in the kit's rules points back here or to [WHY.md](../kit/.uak/docs/WHY.md), which gives the
incident or measurement behind each rule. Each section ends with how to measure it again; a snapshot keeps its
date, because the numbers of a living repository move.

## This repository, built with the kit

The kit is developed with itself: its tasks are claimed, reviewed and merged through its own gates, and every command
leaves a line that `uak metrics` reads. Snapshot of `bash .uak/bin/uak metrics` on 2026-11-25 (UAK-202), over the 159
tasks on this repository's `claims` branch:

| What | Value |
|---|---|
| Tasks integrated, 2026-11-03 to 2026-11-25 | 152 |
| Integrated tasks reopened later | 0 of 152 |
| Integrated tasks that needed a follow-up task | 16 of 152 (11%) |
| Time from claim to integrated, median | 1.3 h |
| Reviewed tasks rejected at least once | 56 of 154 (36%) |
| Review rounds per task | 1.61 (248 rounds in 154 tasks, 77 of them rejects) |
| Tasks the merge gate handed to a person | 77 of 101 that reached its queue (69 for shared files or CI) |
| Commits on `main` with no task | 202 of 362 first-parent commits (56%) |

The last two rows are the weak points: most merges of this repository still need a person, because most tasks touch
the kit's engine or CI, which the gate never merges alone; and more than half of the commits on `main` (plans,
releases, hash updates) reach it outside a task.

To measure again: `bash .uak/bin/uak metrics` in a checkout of this repository (`--since DAYS` for a window, `--json`
for the raw values). The counts grow with every task, so a new run gives the current values, not these.

## Speed of the commands

Every `uak` command is at least one round trip to the Git remote. From the same snapshot (GitHub over SSH, from the
machines that worked on this repository):

| Command | Timed calls | Median | 95th percentile |
|---|---:|---:|---:|
| `uak status` | 335 | 2.0 s | 4.9 s |
| `uak next` | 10 | 2.6 s | not enough calls |
| `uak claim` | 72 | 4.2 s | 9.9 s |
| `uak heartbeat` | 308 | 3.7 s | 8.9 s |
| `uak done` | 148 | 8.0 s | 14.4 s |
| `uak review` | 109 | 5.5 s | 14.4 s |
| `uak merge` | 54 | 19.0 s | 1383 s (the gate runs the test suite and may wait for the queue) |

`uak demo` took 27.5 s of wall-clock time on 2026-11-25 on an ARM Linux single-board computer, for UAK-202. To
measure again: `time bash kit/.uak/bin/uak demo` from a checkout of this repository; the time depends on the machine.

To measure the command times again: the same `uak metrics` run as above (its "per command" lines).

On a Windows laptop with Git Bash, the hooks that run around every shell command an agent sends took 5.1 s before
v5.9.2 and 0.52 s after it ([perf-windows.md](perf-windows.md), with the method and each hook's processes).

The read-only audit of v6.5.0 measured the hooks at 3 to 7 ms per call on a 6-core ARM Linux machine and the context the kit loads in every
session at about 3,500 tokens ([audit-2026-11.md](audit-2026-11.md)). To measure again: `bash scripts/perf_hooks.sh
WORKTREE RUNS` in a task worktree of a project made with `install.sh`, as perf-windows.md describes; the audit
describes how it counted the tokens.

## Do agents use the tools when they should

[docs/evals/README.md](evals/README.md) runs a real Claude Code session (Sonnet) on a task whose change another task
imports, with a prompt that names no command, and reads the transcript.

| Kit | Contract sent to the importing task before `uak done` | Source |
|---|---|---|
| before the session-start card (2026-10-15) | 0 of 3 runs | `adoption-baseline-*.json` |
| with it | 3 of 3 runs | `adoption-v5-*.json` |

| Kit | Tests written and seen failing before the code | Source |
|---|---|---|
| v5.9.2 (control) | 0 of 2 runs | `adoption-v592-control-*.json` |
| v5.10 (`uak red`, named tests) | 2 of 2 runs | `adoption-v510-*.json` |

Limits written there: one scenario, one model, a small repository; Codex and Cursor were not run. To measure again:
`python3 scripts/adoption_eval.py --label NAME --out docs/evals/adoption-NAME.json` (it runs real Claude Code sessions,
so it needs a signed-in `claude` and costs tokens).

## Team events

Each event's claims branch was read after it and turned into a report; each report's findings became a release. The
numbers are the reports' own, recounted from the raw files. To check one again: each report names the branch and
files it was counted from; `bash .uak/bin/uak autopsy --claims DIR` writes the same kind of report from a claims
branch checked out in DIR.

| Event | Team | Report | Release |
|---|---|---|---|
| Hack-Nation 2026, 2026-10-03 | 4 humans, 5 agents (Claude Code and Codex), 3 machines, about 14 h, 76 pull requests, 717 messages | [retro](RETRO-hacknation-2026.md) | v3 |
| UpiixSol, 2026-10-06 to 09 | marathon mode, 2 humans, 6 agent identities, 38 tasks | [black box](blackbox/upiixsol-2026-10.md) | v4.1 |
| Reap buildathon, 2026-10-09 | 4 h, 5 humans, 11 identities on Codex, Cursor and Claude Code; 2 h from install to the first claim | [autopsy](blackbox/reap-2026-10.md) | v4.2 |
| MLB hackathon, first 60 h | 4 humans on 4 Windows laptops, 13 identities, 32 of 36 tasks integrated | [autopsy](blackbox/mlb-2026-10.md) | v4.3 |
| MLB hackathon, the v5 week | 81 of 89 tasks integrated by the deadline | [autopsy](blackbox/mlb-2026-10-week2.md) | v5.2 |
| Chilangatón, 2026-10-25, first place ([CHANGELOG](../CHANGELOG.md)) | 7 h, 5 humans, 10 Claude Code identities on macOS and Windows, 35 tasks | [black box](blackbox/chilangaton-2026-10.md) | v5.4 |
| Hacktoberfest, 2026-10-27 to 28 | about 16 h, 5 humans, 13 identities on Claude Code and Codex, 33 of 35 tasks integrated | [black box](blackbox/hacktoberfest-2026-10.md) | v5.5 |
| HackADA, 2026-10-29, first place | about 4 h, 9 Claude Code identities on 4 laptops, 25 of 27 tasks integrated, on a repository copied with kit v5.3.0 | [black box](blackbox/hackada-2026-10.md) | v5.9 |
| HackADA on a Windows laptop, 2026-10-30 | the kit's suite and the product on Git Bash; 19 findings | [audit](blackbox/windows-audit-2026-10.md) | v5.9.1 |
| DevDay-Exchange and deus-ex-machina (first place), 2026-11-07 to 09 | DevDay: 37 of 41 tasks integrated; deus: 6 of 23 tasks integrated and 120 of 155 commits outside tasks | [autopsy](blackbox/devday-deus-2026-11.md) | v6.1 |
| Black box harvest, 2026-11-11 to 19 | 1,409 events from the 14 repositories that have the kit | [harvest](blackbox/harvest-2026-11.md) | v6.5 |

### Hack-Nation 2026 in detail

From the [retro](RETRO-hacknation-2026.md), the incidents that shaped the first rules:

| What happened | What the kit does since |
|---|---|
| The secret scanner detected nothing all event: Ubuntu's `mawk` ignores the regex `{n}` | `grep -E` rules, a regression test, a `doctor` check |
| A force-push passed the deny list when chained after `cd x &&` | `guard` checks every segment of a command |
| A person pasted an API key and a sudo password into the chat | `guard prompt` blocks it before the model reads it |
| 194 of 717 messages were duplicate notices; one agent sent 247 | one notice per owner, only actionable kinds reach the agent |
| 38 expired leases, mostly tasks waiting for review | leases per mode; a task in review waits four times longer |
| 8 pull requests only added tasks to the backlog | `uak plan` publishes tasks on the `claims` branch |
| No freeze: 8 pull requests and a product rename in the last 6 h | a freeze is required in `sprint` |

## Tests

The kit's tests run against real Git processes and local bare remotes. On 2026-11-25 there were 159 test files in
`kit/.uak/tests/`. Pull requests run all of them on Linux and a selected part on macOS and Windows; `main` runs all
of them on the three systems (the rules are in the repository's [AGENTS.md](../AGENTS.md), rule 8). To count again:
`ls kit/.uak/tests/test_*.py | wc -l`.
