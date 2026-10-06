# Graph engineering

Graph engineering means designing a multi-agent system as an explicit graph, not one big agent. You define its members, their mandates, the message paths between them, shared state, routing and traceability. In uak every edge of that graph is a file or a command, so it is inspectable and testable.

## The uak graph
| Concept | In uak | Where |
|---|---|---|
| **Members** | humans, agents (`UAK_AGENT`), subagents (runner, reviewer, design-critic, security-reviewer) | `.uak-env`, `.claude/agents/` |
| **Mandates** | each task's `Paths` (exclusive) and the shared-file owners | `.uak/TASKS.md`, `.uak/OWNERS.md` |
| **Execution graph** | a DAG of tasks: `Depends on` (hard edge) and `Uses contract` (soft edge, works on a mock) | `uak graph` |
| **Message paths** | typed messages: request, contract, review, approve, reject, integrated, human | `claims:inbox/log.md` |
| **State** | a single shared state, compare-and-swap via Git pushes | the `claims` branch |
| **Routing** | `uak next`: priority → deps INTEGRATED → no path overlap → owners → freeze → budget | `uak next` |
| **Context graph** | what each member loads, and when (AGENTS.md §7) | load-on-demand table |
| **Traceability** | every claim, event, decision, review and merge is a commit | `worklog/`, `DECISIONS.md`, `reviews/` |

## Design the execution graph (planner)
1. **Wide first wave.** At least 1 task per agent with no hard dependencies. Publish contracts and mocks first, so consumers use `Uses contract:` and never wait.
2. **Short critical path.** It is the longest chain of hard deps weighted by `Estimate`. Shorten it by splitting tasks or replacing hard deps with contracts.
3. **No cycles, no dangling IDs.** `uak lint` fails on both.
4. **Disjoint mandates.** Two tasks in the same wave must not share `Paths`. Shared files (lockfiles, schemas, CI) get one owner.
5. **Re-plan as a graph.** New tasks go in with `uak plan` (sprint) or a PR (marathon). Then check `uak graph` again.

```bash
bash .uak/bin/uak graph                 # waves, critical path, cycles, missing deps
bash .uak/bin/uak graph --min-wave1 4   # fail (exit 1) if fewer than 4 tasks can start now
bash .uak/bin/uak graph --mermaid       # paste into a PR, README or issue
```

Example output:
```
GRAPH 9 tasks · 3 waves · critical path 135 min: HACK-002 → HACK-006 → HACK-009
wave 1 (5): HACK-001 HACK-002 HACK-003 HACK-004 HACK-005
wave 2 (3): HACK-006 HACK-007 HACK-008
wave 3 (1): HACK-009
```

## Anti-patterns we measured (Hack-Nation 2026)
- **A serial bottleneck.** Every task depended on setup. Fix: skeleton and contracts in wave 1; everything else uses mocks.
- **A broadcast storm.** One `integrated` notice per related task gave 194 duplicates. Fix: one notice per owner, only for claimed tasks.
- **A hub reviewer.** One agent did most reviews and ran out of tokens. Fix: rotate reviewers by load.
- **Parentheses as edges.** `Depends on: None (uses mock of HACK-021)` created a fake hard edge. Fix: text in parentheses is ignored.
