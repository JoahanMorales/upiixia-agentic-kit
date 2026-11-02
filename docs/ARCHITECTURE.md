# Architecture: how the kit is built, where to change what, and how it keeps scaling

For whoever changes the kit (a human or an agent). The rules for agents that USE the kit are in `kit/AGENTS.md`; the
rules for working on this repo are in the root `AGENTS.md`.

## The pieces

```
install.sh ──copies──▶ a project:  AGENTS.md · .claude/ .codex/ .cursor/ .gemini/ (hooks, agents, commands, skills)
                                   .uak/ (bin = the engine, docs, modes, templates, stacks, settings, tests)
                                   .githooks/ · .github/ (CI, PR template)

harness (Claude Code, Codex, Cursor, Gemini) ──hooks──▶ .uak/bin/guard  (before a command: block or allow)
                                              └──────▶ .uak/bin/hook   (after a tool: beat, poll, coach, lens, cap)
agent ──CLI or MCP──▶ .uak/bin/uak (+ uak-coordination, lib/*.sh) ──git──▶ the `claims` branch on the remote
                       └── scripts: wt, map, graph, red, garden, design-lint, deploy, doctor, start, tokens, pace…
```

- **State lives in one place**: the `claims` branch (tasks, claims, worklogs, messages, decisions, lessons, black
  box). `.uak/TASKS.md` on the base branch is a stateless backlog. Every mutation is a transaction: a fresh shallow
  fetch of claims, the change, a secret check, a commit, a push; a rejected push retries on the new tip.
- **The CLI's output is its API.** Agents, hooks, the MCP server and the 260 tests read its lines (`OK …`,
  `CONFLICT: …`, `RED_OK …`, `Next: …`). Changing a message is a contract change.
- **Gates, not prose.** What must hold is checked where it matters: `guard` (destructive commands), `done` (scope, UI
  screenshots, tests only grow, named tests, the red), the merge gate (Verify and smoke on the merged result),
  `lint` (budgets, the backlog), `design-lint` (the design system).
- **Text is the other half**: AGENTS.md (≤ 100 lines), the mode files, skills, commands, subagents. A rule reaches an
  agent at the moment it applies: the claim's briefs, `next`, the session card, a gate's refusal with the exact fix.

## Where to change what

| To add | Change | Checked by |
|---|---|---|
| a `uak` command | `uak` (usage + parsing + `mutate` or a script in `.uak/bin` routed by the `exec` list), a CLI.md row, a test | `kit_lint` (documented, test registered) · the suite |
| a check at `done` | a `*_gate` function called from `done` (see `ui_gate`, `test_gate`), its message with the exact fix, a WHY.md row | a test that fails without it |
| a guard rule | a `case` prefilter on the words the regex needs, then the grep; the message says what to do instead | `test_policy`, `test_v21_security`, the old-vs-new differential (see `docs/perf-windows.md`) |
| a PROJECT.md key | read it with the same `sed -n 's/^[-* ]*KEY:[* ]*//p'` form (bold and CRLF tolerated), a default, CLI.md's field list, both templates | the suite |
| a skill | `kit/.uak/skills/NAME/SKILL.md`, `install.sh`'s list per mode, SOURCES.md | `kit_lint` (vendored and recorded) |
| a hook behavior | `hook` (keep the common path free of processes: Windows pays 20–50 ms each) | `test_v592` counts processes |
| a portability fix | the fix plus a `kit_lint` rule when the pattern can come back | `kit_lint` in CI |

Every engine change ships a test that fails without it (the kit applies test-first to itself), runs on Linux (mawk),
macOS (bash 3.2, BSD awk) and Windows (Git Bash, CRLF checkout), and a release updates CHANGELOG, README, WHY.md,
`llms.txt`, the demo and the version files.

## Why it got hard to change (measured, v5.10)

- ~7,700 lines of bash in 40 files; `uak` alone is 1,994 lines with 129 global variables and a 255-line `mutate`.
- 13 copies of the PROJECT.md key reader in 10 scripts; 20 scripts call the CLI recursively.
- 140 comments describe a portability workaround; 22 of the last 83 commits are fixes, most of them platform bugs that
  only CI on another OS found.
- Tests are grouped by release (`test_v591.py`, `test_v592.py`…), not by area, so finding the tests of `done` means
  reading many files.

## The scaling plan

**Done in v5.10.1**
- `scripts/kit_lint.py` in CI: the portability rules as checks (bash 4+ syntax, GNU-only flags without a BSD
  fallback, awk intervals, `awk -W version` without `/dev/null`, class substitutions unbounded on bash 3.2, CRLF,
  `bash -n`), structure checks (every command documented, every test file in `smoke` and the Windows matrix, every
  installed skill vendored and recorded, scripts executable, the AGENTS.md budget), and `uak garden` on a fresh
  install of each mode (no doc names a missing command, script, doc or skill). It found a real bug on its first run
  (a heredoc of HTML or tabs was quadratic on bash 3.2).
- The kit's own adoption eval measures whether a real agent uses a rule (`docs/evals/`): a rule that no agent follows
  and no gate enforces is a candidate to delete.

**Next (in order)**
1. **One config reader** (`lib/config.sh`, `uak_cfg KEY DEFAULT`) replacing the 13 copies; `kit_lint` then refuses a
  new copy.
2. **Stable result codes** on every command (`OK`, `CONFLICT`, `ERROR`, `BLOCKED` plus a short code) and a `--json`
  mode, so the MCP server and the hooks stop parsing prose.
3. **A command registry**: one table (name, usage, routing, doc anchor, test) that generates `uak help`, the CLI.md
  table and the MCP tool list, so they cannot drift.
4. **Split `uak`** into one file per command family (`lib/cmd-claim.sh`, `lib/cmd-done.sh`, `lib/cmd-review.sh`…)
  behind the same dispatcher, and tests regrouped by area (`test_done.py`, `test_guard.py`…) with the release history
  kept in their docstrings.
5. **Develop the kit with the kit** (dogfooding): the roadmap as `.uak/TASKS.md` with `Tests:` per task, a `claims`
  branch on this repo, agents claiming roadmap tasks in worktrees, the merge gate running this repo's suite, `uak
  garden` and the black box on the kit's own development. It needs an owner decision: it adds `.uak/` and a `claims`
  branch to the public repo, and the root `AGENTS.md` (for kit developers) has to coexist with the one the installer
  writes.
6. **The Go engine** (`docs/plans/port-go.md`): the structural fix for the portability tax and the process count;
  the 260 black-box tests are already its specification.
