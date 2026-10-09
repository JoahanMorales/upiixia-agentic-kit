# Why each rule exists

Load only the row you need. Every rule cites the incident behind it. Data comes from Hack-Nation 2026: 5 agents, 4 humans, 3 machines, 76 PRs, ~14 h (`docs/RETRO-hacknation-2026.md` in the kit repo).

| Rule | Incident / reason |
|---|---|
| §1.3 No `sudo`, no money/accounts/publishing | A human offered their sudo password in chat. Agents never need it; privileged steps belong to the human. |
| §1.5 Secrets out of chat | An API key was pasted into chat. `guard prompt` now stops it before the model sees it. |
| §1.6 Never invent | An agent wrote DOIs from memory into curated data. Caught before publishing and replaced with verifiable IDs. |
| §1.7 + `guard` | A force-push and `worktree remove --force` slipped past the deny list when chained after `cd x &&`. Prefix matching can't see chains; `guard` checks every segment. |
| §3.1 State only on `claims` | Board state stored in code forces merges just to move a card. A Git branch serializes with fast-forward pushes and needs no server. |
| §3.5 Out of tokens → handoff + release | An agent ran out of tokens holding a task. Its work waited for the lease to expire. |
| §3.6 Read token to recover | There were 38 lease recoveries. The token proves the new owner read the summary. |
| §3.7 Port per worktree | Port 8000 was taken on the Jetson, and several agents ran servers at once. |
| Mode-aware and REVIEW leases | Most expired leases were tasks waiting for a review or a human merge, not dead agents. |
| `uak plan` | 8 PRs only added tasks; 3 merges fell to the human queue for touching TASKS.md. |
| Parentheses ignored in deps | `Depends on: None (uses mock of HACK-021)` blocked a claim, and it took 2 PRs to fix. |
| `uak graph` | Wave width and the critical path were checked by eye; lint now fails on cycles and unknown IDs. |
| §4.2 Bounded inner loop | Agents retried the same failing approach. Two identical failures means stop and escalate. |
| §4.3 `&&`, never `;` | Two contract messages carried a stale SHA because a failed commit (ruff) didn't stop the chain. |
| §4.6 Reduced motion in UI checks | With software WebGL, animations took 3–6 s, and "failures" were unfinished animations. |
| §4.7 Reviewer ≠ author, and runs Verify | A review caught a benchmark using a different `clip()` than production, which inflated the reported top-1. |
| Reviewer rotation | 2 agents gave 51 of 70 review verdicts, and the busiest agent (247 of 717 messages) ran out of tokens. |
| Scanner uses `grep -E` | mawk ignores awk `{n}` intervals: the secret scanner detected nothing for the whole event, and its suite was red unnoticed. |
| `uak doctor` at minute 0 | Humans merged all 75 PRs by hand, and one gh token couldn't create PRs at all. |
| §5 Only actionable messages injected | 717 messages in 14 h, 194 of them duplicate `integrated` notices. Now there is one per owner, and only for claimed tasks. |
| §5.3 Messages of 3 lines or fewer | Every injected message is paid for on every later turn of the receiver. |
| sprint: freeze required | `Freeze-Epoch` was 0: 8 PRs, including a product rename, in the last 6 h. |
| sprint: design lock | 4 global visual directions in 8 h. |
| sprint: name fixed at T0 | The product was renamed 5 h before the deadline. |
| sprint: a human owns submission from T−8 h | The submission task sat with an agent that ran out of tokens; its PR stayed open. |
| sprint: notices inside 1280×720 | The "not a diagnosis" notice fell below the projector viewport. |
| sprint: 2 agents per human | With 5 agents, coordination cost more messages than code for hours. |
| marathon: spec → plan → tasks | Without a clock the risk shifts from "not shipping" to "shipping wrong". Specs keep the why traceable. |
| marathon: human merge + CI | Sprint's auto-merge buys time. In production, a bad main costs more than waiting for a review. |
| marathon: dependency decisions | We used a CC-BY-NC library. In a product, that would have been a legal blocker. |
| §6.2 Route by cost | Most turns are routine. Running the strongest model on every turn pays its price for file discovery and grep. The documented advisor strategy (fast main + strong advisor at decision points) typically costs less than running the strong model throughout. |
| `guard agent` caps | Claude Code's concurrency cap (default 20) does not apply under ultracode, so one prompt can fan out many Opus subagents. Our hook enforces `Max-Parallel-Subagents` and `Opus-Subagents-Per-Session` regardless. |
| Spawn depth 1 | Nested subagents multiply context and cost without a reviewer in the loop. |
| `/uak-advise` packets | The advisor tool re-reads the whole transcript, uncached, on every call. In a long session, a ≤40-line packet to `uak-architect` is cheaper. Some providers have no advisor tool at all. |
| Black box (`uak bb`) | UpiixSol (Oct 2026): the same uak errors repeated across 3 sessions and 2 humans, and the only record was 30 MB of transcripts. One anonymous line per event makes kit failures countable across every repo that uses it. |
| `uak pace` | UpiixSol: the 5-hour limit hit overnight with tasks open, while other windows expired with most of the budget unused. Budget left ÷ time left is one number the guard can enforce. |
| `uak integrate` | UpiixSol: PRs merged on GitHub stayed REVIEW for hours because only their offline owner could record them, blocking dependents. The merge proof is verifiable, so anyone may record it. |
| Fork-point claim base | UpiixSol UPS-030: a claim taken after the code was written stored the finished tip as its base, so the task "had no changes". |
| Recent reviewers stay eligible | UpiixSol: reviewers lost the role when their own task merged; only a human could re-register them, so reviews stalled overnight. |
| `Additive-Paths` | UpiixSol: 4 of 11 decisions were "a new test file outside Paths", each waiting 15 min. |
| `.uak-env` beats exports | UpiixSol: a lead's exported `UAK_AGENT` put a subagent's claim under the lead's name. |
| No `pkill -f` | UpiixSol: a pattern kill matched the agent's own shell twice (exit 144). |
| Launch checklist | Vibe-coded backends look finished but routinely miss IDOR, rate limits, idempotency, transactions and restore drills. Each item now has a verifiable check, and the human-only items stay with humans. |
