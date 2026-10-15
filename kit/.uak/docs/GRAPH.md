# Graph engineering

Graph engineering means designing a multi-agent system as an explicit graph, not one big agent. You define its members, their mandates, the message paths between them, shared state, routing and traceability. In uak every edge of that graph is a file or a command, so it is inspectable and testable.

## The uak graph
| Concept | In uak | Where |
|---|---|---|
| **Members** | humans, agents (`UAK_AGENT`), subagents (runner, reviewer, design-critic, security-reviewer) | `.uak-env`, `.claude/agents/` |
| **Mandates** | each task's `Paths` (exclusive) and the shared-file owners | `.uak/TASKS.md`, `.uak/OWNERS.md` |
| **Execution graph** | a DAG of tasks: `Depends on` (hard edge) and `Uses contract` (soft edge, works on a mock) | `uak graph` |
| **Message paths** | typed messages: request, contract, review, approve, reject, integrated, human; `impact:ID` routes a contract along the code graph | `claims:inbox/log.md` |
| **State** | a single shared state, compare-and-swap via Git pushes | the `claims` branch |
| **Routing** | `uak next`: priority → deps INTEGRATED → no path overlap → owners → freeze → budget | `uak next` |
| **Code graph** | files, symbols and resolved imports; hubs, entry points, the files of each task and who imports them | `uak map` |
| **Memory graph** | lessons anchored to paths, retrieved by the paths a task touches | `uak learn`, `uak recall`, `uak next` |
| **Context graph** | what each member loads, and when (AGENTS.md §7) | load-on-demand table |
| **Traceability** | every claim, event, decision, review and merge is a commit | `worklog/`, `DECISIONS.md`, `reviews/` |

## The code graph: `uak map`
Agents learn a repository by opening file after file, and every file they open is re-sent on every later turn.
`uak map` builds the structure once, with no model and no dependency (Bash + awk, 0.2 s for 120 files), and an agent
reads a ~1.3k-token `MAP.md` instead:
```bash
bash .uak/bin/uak map show                 # areas, hubs (most imported), entry points, area dependencies, files per task
bash .uak/bin/uak map find data_path       # core/config.py:47  def data_path · mentioned in 4 files
bash .uak/bin/uak map users core/config.py --depth 2    # the blast radius of a change
bash .uak/bin/uak map path app/pages/card.py core/config.py   # card.py → core/cards.py → core/config.py
bash .uak/bin/uak map impact HACK-001      # files outside HACK-001 that import it, and the tasks that own them
bash .uak/bin/uak msg impact:HACK-001 --kind contract "data_path now takes a Path"   # one line to all of them
```
Two layers, labeled like graphify's edges:
- **EXTRACTED** (free, deterministic, always on): definitions, imports and call edges. A call `name(` resolves through
  the file's own definitions, its imports or its Go package, and the caller is the enclosing definition. No types and
  no dynamic dispatch: measured against `git grep` on a real repo it found 5/5, 26/28 and 41/44 of the calls of three
  functions (it counts each calling function once). `uak map callers NAME`, `calls NAME`; `impact` lists the exact
  functions another task uses.
- **INFERRED** (optional, `uak map notes`): the fast-tier model reads the most connected files once and returns a
  purpose and concepts; files sharing 2+ concept keywords without importing each other get an INFERRED edge. Cached
  by content hash (only changed files are sent again); ~1k input tokens per file on the fast tier.
The scout subagent asks the map before searching.

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
- **A serial bottleneck** (avoided by design). If every task depends on setup, nobody starts. Fix: skeleton and contracts in wave 1; everything else uses mocks.
- **A broadcast storm.** One `integrated` notice per related task gave 194 duplicates. Fix: one notice per owner, only for claimed tasks.
- **A hub reviewer.** 2 agents gave 51 of 70 verdicts while the busiest agent ran out of tokens. Fix: rotate reviewers by load.
- **Parentheses as edges.** `Depends on: None (uses mock of HACK-021)` created a fake hard edge. Fix: text in parentheses is ignored.
