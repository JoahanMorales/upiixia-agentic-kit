# Architecture: how the kit is built, where to change what, and how it keeps scaling

For whoever changes the kit (a human or an agent). The rules for agents that USE the kit are in `kit/AGENTS.md`; the
rules for working on this repo are in the root `AGENTS.md`. The engine stays in Bash 3.2 + POSIX tools, with Python
3.8+ (standard library) for the MCP server, the dashboard, the tests and the scripts: decided in November 2026, no Go
or Rust engine (the estimate that informed it is `docs/plans/port-go.md`).

## The pieces

```
install.sh ──copies──▶ a project:  AGENTS.md · .claude/ .codex/ .cursor/ .gemini/ (hooks, agents, commands, skills)
                                   .uak/ (bin = the engine, docs, modes, templates, stacks, settings, tests)
                                   .githooks/ · .github/ (CI, PR template)

harness (Claude Code, Codex, Cursor, Gemini) ──hooks──▶ .uak/bin/guard  (before a command: block or allow)
                                              └──────▶ .uak/bin/hook   (after a tool: beat, poll, coach, lens, cap)
agent ──CLI or MCP──▶ .uak/bin/uak ──▶ lib/commands.tsv (the registry: which code runs each command)
                         │              ├─ exec: a script of its own (wt, map, graph, red, garden, deploy, doctor…)
                         │              └─ a function in its family file (lib/claim.sh, lib/done.sh, lib/plan.sh…)
                         └──git──▶ the `claims` branch on the remote (lib/tx.sh: one transaction per write)
```

- **State lives in one place**: the `claims` branch (tasks, claims, worklogs, messages, decisions, lessons, black
  box). `.uak/TASKS.md` on the base branch is a stateless backlog. Every write is a transaction (`lib/tx.sh`): a fresh
  shallow fetch of claims, the command's mutation, a secret check, a commit, a push; a rejected push retries on the
  new tip.
- **The CLI's text is its contract with agents.** Agents, hooks and the tests read its lines (`OK …`,
  `CONFLICT: …`, `RED_OK …`, `Next: …`); changing a message is a contract change. Programs use `uak --json CMD`
  instead: the same run as one JSON object with a stable `code` (CLI.md, Result codes).
- **Gates, not prose.** What must hold is checked where it matters: `guard` (destructive commands), `done` (scope, UI
  screenshots, tests only grow, named tests, the red), the merge gate (Verify and smoke on the merged result),
  `lint` (budgets, the backlog), `design-lint` (the design system), `scripts/kit_lint.py` (the kit's own rules).
- **Text is the other half**: AGENTS.md (≤ 100 lines), the mode files, skills, commands, subagents. A rule reaches an
  agent at the moment it applies: the claim's briefs, `next`, the session card, a gate's refusal with the exact fix.

## The engine, file by file

| File | What it holds |
|---|---|
| `uak` (≤ 300 lines, a test holds it there) | Environment and identity from `.uak-env`, `--json`, the option parser, then dispatch through the registry |
| `lib/commands.tsv` | The registry: per command its route (`exec`, `tx`, a function), its mutation, its file, its MCP tool, its help line |
| `lib/core.sh` | `say`, the three failures (`die` 2, `conflict` 3, `gitfail` 1) with their result codes, IDs, identity, the registry reader |
| `lib/config.sh` | `uak_cfg FILE KEY [DEFAULT]`: the only reader of PROJECT.md keys (builtins, so guard and hook use it too) |
| `lib/tx.sh` | The transaction, the record and worklog helpers, the STATE.md snapshot |
| `lib/backlog.sh` | Task fields, Paths as reserved prefixes, OWNERS |
| `lib/claim.sh` · `lib/done.sh` · `lib/plan.sh` | A task's life: claim … handover; done and integrate with their gates; plan and amend |
| `lib/status.sh` · `lib/wait.sh` · `lib/lint.sh` | Reads (status, next, digest, de-duplication); wait; lint |
| `lib/messages.sh` · `lib/memory.sh` · `lib/review-merge.sh` · `lib/tests.sh` · `lib/github.sh` · `lib/security.sh` | Messages and inbox; lessons and recall; review and the merge gate; test-first checks; pr-sync; secret exceptions |
| `uak-coordination` | Config from the remote base, deadlines (tick), decisions, `next`'s choice |
| `lib/json.sh` | `uak --json`: runs the command as a child and prints the envelope |

## Where to change what

| To add | Change | Checked by |
|---|---|---|
| a `uak` command | one row in `lib/commands.tsv`; its code in its family file (or a script in `.uak/bin` with run `exec`); its flags in `uak`'s parser; a prose row in CLI.md; `python3 scripts/gen_registry.py` | `kit_lint` (the route exists, its function is in the file named, a CLI.md row, the generated index) · a test |
| a refusal agents will meet often | `UAK_CODE=short-code conflict "…the exact fix"`, a row in CLI.md's Result codes | `kit_lint` (every code documented) · a test of the code with `--json` |
| a check at `done` | a `*_gate` function in `lib/done.sh` called from `done_mutate`, its message with the exact fix, a WHY.md row | a test that fails without it |
| a guard rule | a `case` prefilter on the words the regex needs, then the grep; the message says what to do instead | `test_policy`, `test_v21_security`, the old-vs-new differential (see `docs/perf-windows.md`) |
| a PROJECT.md key | read it with `uak_cfg FILE KEY DEFAULT` (never a new `sed -n 's/^[-* ]*KEY…'`), CLI.md's field list, both templates | `kit_lint` refuses a copy of the reader |
| a skill | `kit/.uak/skills/NAME/SKILL.md`, `install.sh`'s list per mode, SOURCES.md | `kit_lint` (vendored and recorded) |
| a hook behavior | `hook` (keep the common path free of processes: Windows pays 20–50 ms each) | `test_v592` counts processes |
| a portability fix | the fix plus a `kit_lint` rule when the pattern can come back | `kit_lint` in CI |

Every engine change ships a test that fails without it (the kit applies test-first to itself), runs on Linux (mawk),
macOS (bash 3.2, BSD awk) and Windows (Git Bash, CRLF checkout), and a release updates CHANGELOG, README, WHY.md,
`llms.txt`, the demo and the version files.

## Developing the kit with the kit

This repository coordinates its own development with the kit (root `AGENTS.md`, "Developing the kit with the kit"):
the roadmap is `.uak/TASKS.md` (test-first: every task names its `Tests:`), its state lives on this repo's `claims`
branch, and `.uak/bin/{uak,wt,q,smoke,secret-scan}` are 3-line shims to `kit/.uak/bin` of the same checkout, so a
task worktree runs its own branch's engine. The merge gate runs `.uak/bin/smoke` on the merged result: `kit_lint`
plus the whole protocol suite. `kit_lint` lints that backlog offline on every push.

## Why it got hard to change, and what v5.11 did about it

Measured on v5.10: `uak` was 1,995 lines with 129 globals and a 255-line `mutate`; 13 copies of the PROJECT.md reader
in 10 scripts; the command list was kept by hand in five places (help, two dispatch lists, CLI.md, the MCP tools); 140
comments described a portability workaround and 22 of 83 commits were fixes, most of them found only by CI on
another OS.

| Step | Status |
|---|---|
| `scripts/kit_lint.py` in CI: portability rules, structure, `garden` on a fresh install | v5.10.1 |
| The adoption eval: does a real agent use a rule (`docs/evals/`) | v5.10 |
| 1. One config reader (`lib/config.sh`); `kit_lint` refuses a new copy | v5.11 |
| 2. Stable result codes and `uak --json` | v5.11 |
| 3. One command registry for help, dispatch, the CLI.md index and the MCP tools | v5.11 |
| 4. `uak` split into one file per command family (1,995 → 258 lines) | v5.11 |
| 5. The kit developed with the kit | v5.11 |
| 6. The claims transaction without the process storm (`next` ≤ 40 processes) | next: `.uak/TASKS.md`, UAK-001 … UAK-007 |
| Tests regrouped by area (`test_done.py`, `test_guard.py`…) | open: today they are grouped by release |
