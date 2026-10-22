# Adoption eval: does the agent use the harness when it should?

A harness can have good tools and still fail if the agent does not know **when** to use them. Rules in `AGENTS.md`
are in context from the first turn, but attention to them fades over a session, and nothing ties a rule to the moment
it applies. This eval measures that with a real agent instead of guessing.

```bash
python3 scripts/adoption_eval.py --label v5 --out docs/evals/adoption-v5.json        # this checkout's kit
python3 scripts/adoption_eval.py --kit ../kit-at-old-commit --label baseline         # any other version
```

**Scenario.** A throwaway team repo (kit installed, local bare remote, no network) with 11 Python files. The agent is
`ana-1`, in the worktree of HACK-001: add a `region` argument to `price_with_tax`. HACK-002, claimed by `bob-1`, imports
that function, so the change is a contract other work depends on. A reviewer approves the pushed SHA ~40 s after
`uak done`. The prompt is what a human would say ("do HACK-001 end to end following the repo's rules, ship it, stay
until the verdict, report it"); it does not name any uak command.

**What it reads from the transcript** (`claude -p --output-format stream-json`):

| Metric | Good behavior |
|---|---|
| `contract_before_done` | a contract message reaches HACK-002 or its owner before `uak done` |
| `used_wait`, `polls_after_done` | one `uak wait`, no polling of status/inbox/board |
| `explore_before_map`, `used_map` | the code map before reading many files (only matters in large repos) |
| `done`, `verdict_reported` | the task reached review and the verdict came back to the human |
| `tool_calls`, tokens, `cost_usd` | the cost of the session |

**Why this design.** Anthropic's guidance for agent tools is to evaluate them on realistic multi-step tasks and read
the transcripts. The MLB hackathon showed the gap: 486 status/inbox/board/digest calls, 4 black box notes in 60 h, and
the code map, `wait` and `learn` documented only in `AGENTS.md`.

## Results (2026-10-15, Claude Code 2.1.301, `claude -p --model sonnet`, 3 runs each)

| | kit before the adoption layer | kit with it |
|---|---|---|
| contract sent to the importing task before `uak done` | **0 / 3** | **3 / 3** |
| waited with one `uak wait`, no polling | 3 / 3 | 3 / 3 |
| reached `done` and reported the verdict | 3 / 3 | 3 / 3 |
| tool calls · seconds | 7–14 · 70–170 | 7 · 85–104 |
| cost per session | $0.13–0.18 | $0.13–0.14 |

The rule ("tell them BEFORE pushing", AGENTS.md §5.1) was in context in every run. What changed the behavior was
the quick card at session start (when X → run Y): in all three runs the contract went out before `uak done`, so the
`done` check on the code graph (which warns when the contract is missing) was a backstop that never had to fire. One
baseline run also lost a review cycle to a committed `__pycache__` file; the installer now ignores it.
With the MCP server installed (3 runs) the agent still chose the Bash forms the card shows: 3/3 contract, 3/3
`uak wait`, 2/3 opened the code map. With the CLI blocked (MCP only) the whole flow ran through `uak_ship`,
`uak_message`, `uak_wait`: contract, verdict reported. That run found a server bug: Claude Code gives the model a
tool's `structuredContent` instead of its text, so the agent saw `{"ok": true}` and polled; the server now returns
text only (polls 3 → 1). Claude Code also defers MCP tool schemas behind tool search, one reason agents start with Bash.
**v5.1 (2026-10-22, 2 runs):** contract before `done` 2/2, one `uak wait` 2/2, no polling, verdict reported 2/2,
7 tool calls, $0.13 per session. The post-tool hook pushed one code-map line per session (`lens_pushed`, read from the
team repo's call log, since stream-json does not show hook context); the hooks' own uak calls (7–8) are counted
apart. The contract metric now uses the last `uak done` (one earlier run retried a `done` that failed on its
arguments, after sending the contract). Raw: `adoption-v51-*.json`.
Limits: one scenario, one model, a small repo (the code map is not needed for 11 files, so map adoption is not
measured here); Codex and Cursor were not run. Raw results: `adoption-*.json`.
