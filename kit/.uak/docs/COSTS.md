# Costs, plans and pacing

Verified 2026-10-09 against the official pages linked at the end. Prices change: run `uak pace` for your real
remaining budget instead of trusting this table.

## API prices (USD per 1M tokens)
| Harness | Tier | Model | Input | Cache read | Output | vs fast |
|---|---|---|---|---|---|---|
| Claude | fast | Haiku 5.5 (prompt ≤100k) | 0.10 | 0.01 | 0.50 | 1× |
| Claude | fast | Haiku 5.5 (prompt >100k) | 0.50 | 0.05 | 2.50 | 5× |
| Claude | balanced | Sonnet 5.5 | 2 | 0.10 | 10 | 20× |
| Claude | strong | Opus 5.5 | 4 | 0.20 | 20 | 40× |
| Codex | fast | GPT-6 Luna | 2.5 cr | 0.25 cr | 12.5 cr | 1× |
| Codex | balanced | GPT-6.1 Sol | 50 cr | 2.5 cr | 250 cr | 20× |
| Codex | strong | GPT-6 Astra | 250 cr | 25 cr | 1,250 cr | 100× |
| Codex/Cursor | fast | GPT-5.6 Luna | 0.20 | 0.02 | 1.20 | 1× |
| Codex/Cursor | balanced | GPT-5.6 Terra | 2 | 0.20 | 12 | 10× |
| Codex/Cursor | strong | GPT-5.6 Sol (promo to Nov 21) | 4 | 0.40 | 20 | 17–20× |
| Cursor | fast | Composer 2.5 (Cursor pool) | 0.50 | 0.20 | 2.50 | — |

`cr` = Codex credits (the unit OpenAI publishes for GPT-6 models in Codex). Fast mode costs 2× (GPT-5.6 in Cursor) or
more (`claude-opus-5-5-fast`: 8/40).

**Rule of thumb.** One strong subagent costs as much as 40 to 100 fast ones. Haiku 5.5 is cheap only under 100k
prompt tokens: a scout that reads 30 files crosses it and costs 5×. That is why scouts return 15 lines or fewer.

## Subscription plans and their windows
| Product | Plan | Price/mo | Window | What we know |
|---|---|---|---|---|
| Claude | Pro | $20 ($17 annual) | 5 h rolling + weekly | baseline (1×); Claude and Claude Code share it |
| Claude | Max 5x | from $100 | 5 h rolling + weekly | 5× Pro; separate weekly limit for Fable |
| Claude | Max 20x | see claude.com/pricing | 5 h rolling + weekly | 20× Pro |
| Codex | Plus | $20 | 5 h + weekly | local messages per 5 h: Astra 5–45 · 6.1 Sol 15–160 · Luna 350–3,000 |
| Codex | Pro | $100 / $200 / $500 | weekly only | "no five-hour limit" today; weekly allowance |
| Codex | Business | $20–25/user | 5 h + weekly | same 5 h estimates as Plus |
| Cursor | Pro / Pro+ / Ultra | $20 / $60 / $200 | monthly pools | Pro+ 3×, Ultra 20× agent usage; Cursor pool (Composer, Grok) + API pool |

Where to read live usage:
- **Claude Code:** the status line gets `rate_limits.five_hour` and `seven_day` (Pro/Max, after the first reply).
  `.uak/bin/statusline` caches them for `uak pace`. You can also check `/status`.
- **Codex:** `/status`. `uak pace` reads the last `rate_limits` from `~/.codex/sessions/**.jsonl`.
- **Cursor and Gemini:** the dashboard. Copy it once with `uak pace set 60 --resets +12d --window 30d`.

## Pacing: spend the plan at the right speed
`ratio = (% budget left) / (% of the window left)`. The tightest window (5 h or weekly) decides:

| Ratio | Level | Caps (from `Max-Parallel-Subagents` P and `Opus-Subagents-Per-Session` S) | Do |
|---|---|---|---|
| ≥ 1.6 | **surge** | 2×P (max 8), S+2 | budget will expire unused: `uak up 2`, more scouts, strong model at every checkpoint |
| 1.0–1.6 | normal | P, S | default routing |
| 0.6–1.0 | conserve | P/2, 1 | fast model for every read, strong only when stuck twice |
| < 0.6 or ≥ 90% used | critical | 1, 0 | finish the criterion, `uak checkpoint`, `/uak-handoff` before the wall |

Examples:
- 1 h left of 5 h with 70% left: 0.7/0.2 = 3.5, so **surge**.
- 3 h left with 50% left: 0.5/0.6 = 0.83, so **conserve**.

`guard agent` applies the caps on every subagent spawn. `hook tick` tells the agent once whenever the level changes.
To turn it off, set `Pace: off` in PROJECT.md or `UAK_PACE=off`.

## Starting points per plan (our recommendation, not a vendor number)
| Plan | Lead | Swarm | Max-Parallel-Subagents | Opus-Subagents-Per-Session | Worktree agents per human |
|---|---|---|---|---|---|
| Claude Pro | Sonnet medium | Haiku | 2 | 1 | 1 |
| Claude Max 5x | Sonnet medium | Haiku | 4 | 2 | 2 |
| Claude Max 20x | Sonnet high | Haiku | 6 | 4 | 3–4 |
| Codex Plus | 6.1 Sol medium | Luna | 3 | 1 (Astra: 5–45 msgs/5 h) | 1–2 |
| Codex Pro | 6.1 Sol high | Luna | 6 | 3 | 3–4 |
| Cursor Pro | your pick (`inherit`) | Composer 2.5 | 3 | 1 | 1–2 |
| Cursor Ultra | your pick | Composer 2.5 | 6 | 3 | 3–4 |

Sources: [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing) ·
[Claude plans](https://claude.com/pricing) · [Claude Code status line](https://code.claude.com/docs/en/statusline) ·
[Codex pricing](https://learn.chatgpt.com/docs/pricing) · [Codex models](https://learn.chatgpt.com/docs/models) ·
[Cursor models & pricing](https://cursor.com/docs/models-and-pricing).
