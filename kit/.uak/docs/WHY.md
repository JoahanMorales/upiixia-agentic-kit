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
| Reviewer rotation | One agent did most reviews (247 of 720 messages were theirs) and ran out of tokens. |
| Scanner uses `grep -E` | mawk ignores awk `{n}` intervals: the secret scanner detected nothing for the whole event, and its suite was red unnoticed. |
| `uak doctor` at minute 0 | Humans merged all 75 PRs by hand, and one gh token couldn't create PRs at all. |
| §5 Only actionable messages injected | 720 messages in 14 h, 194 of them duplicate `integrated` notices. Now there is one per owner, and only for claimed tasks. |
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
