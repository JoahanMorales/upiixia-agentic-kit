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
| Scope = what the merge changes in the current base | Reap buildathon (Oct 2026): 6 of 13 integrated tasks went to the human queue as "Diff outside Paths" for files the branch inherited from main (`.env.example`, a workflow, PROJECT.md, another task's router). Diffing Task-Base..tip counted other tasks' work. |
| `uak clock` (freeze scaled to the event) | Reap: a 4 h event. A fixed "deadline − 6 h" does not fit; the hand-compressed freeze fell 1 h after the first claim: 153 refused claims, 3 PRs only to flip `Freeze-Allowed`, and a moved deadline. |
| `uak allow` (human freeze exception) | Reap: with no command, humans edited TASKS by PR, and agents relayed "the human authorizes all merges" in messages, which the rules (rightly) do not accept as authorization. |
| Quiet `next` probes · `(xN)` lines | Reap: 153 of 290 black box lines were one FREEZE refusal per candidate tested by `uak next`. |
| One identity = one live task | Reap: two sessions shared `agent-2` on two tasks; two Codex terminals edited one worktree. |
| Jittered backoff · shallow claims fetch | Reap: 12 agents retried in lockstep; one approval took 14 attempts and a checkpoint 8. Each attempt cloned the full claims history (600+ commits). |
| One line per message · no acks · `review --note` | Reap: 365 messages; 63 were the same contract copied per task, 46 approvals for 15 merges (each with a second detail message), 11 replies were only "Recibido". |
| `= unchanged` on repeated reads | Reap: `inbox` was called 295 times and `status` 258; unacked messages were reprinted on every call and stayed in context. |
| Output cap (Claude PostToolUse; Codex and Cursor preToolUse rewrite since v4.3) | A teammate on Cursor: tool output "hogs the whole context". Cursor's postToolUse cannot edit shell results, so the command is wrapped before it runs; only low-risk noisy commands, because `allow` is the only way to pass `updated_input`. Teams reported tool output "hogging the context": one test run or log can add 30k+ tokens that are re-sent every turn. Head + tail + a saved log keeps the signal. |
| `next` without identity | Reap: "No identity" from `uak next` was the top error (24): agents in other harnesses run it in the main checkout before `wt new`. |
| `LOOP:` hint | Reap: the same refusal retried within minutes (20 identical errors in one minute from one machine). |
| `MSYS2_ARG_CONV_EXCL` | Reap: Git Bash on Windows turned `refs/uak/config:.uak/TASKS.md` into a path list, so tasks were "not in TASKS.md" and the board showed everything AVAILABLE. |
| Prose is not a command (guard) | Reap: `codex exec "… never cat .env …"` was blocked as a `.env` read. |
| `review --start` lock | Reap: 2–3 agents reviewed the same SHA at once (full diff + fresh Verify + smoke each), the most expensive duplicate of the event. |
| `MERGE_WAIT` | Reap: HACK-008 and HACK-010 ran merge before any review and landed in the human queue. |
| Superseded contracts | Reap: two different contracts for one endpoint (#127, #129) minutes apart; the consumer had to ask which was final. |
| Freeze warning · short-event plan | Reap: 6 PRs open at the extended deadline; planning a 4 h event took 1.5 h. |
| No coordinator identities | Reap: a "coordinator" agent and a human working under an agent-like name relayed "the human authorizes all merges". |
| Heartbeat = lease/3 | Reap: 11 agents beating every 8 min, each beat with a status, kept the claims branch contended. |
| Idle reviewers first | Reap: rotation picked agents busy on their own task ("can't review now"); a review cycle took 10–15 min. |
| Approval survives clean merges of main | MLB hackathon (Oct 2026, 4 Windows laptops, Claude Code + Codex + Cursor): after "update branch" or `git merge origin/main`, the approved SHA went stale; re-reviews of pure merges of main were requested by message (#42, #66) and `integrate` refused a merged PR (HACK-031: "approve the merged SHA first"). |
| Any agent merges an approved task after 20 min | MLB: approved tasks waited 7–13 h for their owner's `uak merge` (HACK-016 blocked 4 tasks for 10 h); two agents relayed "stop delaying and merge" to the humans. |
| No recovery for REVIEW leases | MLB: 22 of 62 DECISIONS lines were REQUIRES_RECOVERY receipts; 19 of them were for tasks waiting in REVIEW (a reviewer, a merge, the night). |
| Gate finds the `.venv` · keeps its log | MLB: 6 of 17 human-queue entries were "Smoke red": the gate's fresh clone had no Python env; agents prepended `<main>/.venv/Scripts` by hand. Codex: "merge smoke failed without exposing the diagnostic log". |
| Scope reasons: new vs edited, owner, fix · empty files allowed | MLB: 6 human-queue entries were "Diff outside Paths" with the same "add the dir to Additive-Paths" hint, including two empty `__init__.py` and the kit's own smoke provenance file. |
| `MERGE_BUSY` is not a human entry | MLB: "Queue busy" landed in the human queue. |
| `retire` · rotation skips ghosts · asks the rejecter · another human first | MLB: three retired identities of one human (x-3, x-4, x-5) had no session and got 15 of 44 rotation reviews; a human told every agent by message they "no longer exist"; the lead's paper was assigned to the lead's second agent (same human); every re-review took 3 messages (rotation, "re-review X", "ready" to the rejecter), 9 times. |
| `done --to/--note` · one integrated line | MLB: the same re-review fan-out; one integration produced one message per dependent owner. |
| `followup ID` | MLB: 3 follow-up PRs of integrated tasks (#17, #24, #27) went around the kit; `uak review` refused them and one was approved only by message. |
| `review --stop` · moved-HEAD explanation | MLB: a Cursor reviewer that could not finish said by message "my lock expires in 20 min"; "the review must match the task's current HEAD" appeared 5 times with no hint of what moved. |
| Output cap on Windows (base64 to `cap`) · Codex pre-rewrite · diff index | MLB: `hook wrap` skipped Git Bash, so the 4 Windows laptops never got the Cursor cap; Codex's PostToolUse block cut documentation reads and "interrupted the tool batch"; a reviewer "could not read the diff" of a large PR. |
| Dedupe without `ps -o` | MLB: Git Bash has no `ps -o`, so `= unchanged` never fired on Windows; the hook's session id is the key now. |
| `status`/`next` survive a failed reconcile · `git init` cause | MLB: 6 "GIT_ERROR: git init failed." from Cursor on Windows made `status` and `next` exit with an error, and the cause was never shown. |
| `--help` per command · case-insensitive IDs · identity prefix | MLB: `uak status --help` was an error; 4 bare "Invalid ID."; 16 "No identity" from the main checkout, where several agents share one git config. |
| Heartbeat/integrate on finished tasks are OK | MLB: Cursor heartbeated integrated tasks ("no active claim") and agents re-ran `integrate` on INTEGRATED tasks (2 conflicts). |
| OneDrive warning · hook executable bit · one `q` log per run | MLB: the worktrees lived in OneDrive; Codex found `.githooks/pre-commit` skipped for a missing executable bit and concurrent Verify/smoke overwriting one `q` log. |
| `uak tokens` (real spend, per task/model/scope) | Reap and MLB: "it burns tokens reading the same stuff again and again"; the kit only counted calls (status 225, inbox 172 at MLB), so tiers, the output cap and dedupe could not be checked against the bill. |
| Loop stops when the agent changes nothing | LOOPS.md rule 3 ("detect lack of progress") was text only: an idle agent burned one more full iteration before "stuck". |
| Loop stops when an existing test is edited | LOOPS.md rule 5 ("a loop never edits its own verifier") was text only; reviewers at MLB rejected weakened claims, and a loop is unattended. |
| `loop --parallel` per failing file | Roadmap v3.2: one prompt per failing file keeps each agent's context small; a full-suite tail mixes unrelated failures. |
| `handover ID --to NAME` | MLB: the tasks of three abandoned identities were redistributed by messages (#135, #137), then each needed `release --expired` with a read token and a new claim. |
| `graph --assign` | MLB: after three identities were abandoned, an agent proposed the redistribution by message (#137: "you take 023 and 020, I take 035, 018 and 033") although claims already knew who had integrated what in each folder. |
| Scheduled `uak tick` (opt-in Action) | MLB (10 days): deadlines and expired leases waited every night until the first `uak status` of the morning. Opt-in because a 15-min schedule bills ~96 Actions minutes a day. |
| Stack presets (Next.js, Django, Go, Expo, data/ML, AI agent) | Only FastAPI + React existed; MLB's Python data stack rediscovered the venv, data-path and "numbers from the CSV" rules by review. |
| One network round trip per call · SSH reuse · clock cached 1 h · `next` prefilter | Measured on the MLB repo (GitHub over SSH): `uak next` 10.4–12.2 s and `status` 7.3–9.2 s, from 4–5 round trips of ~1.2 s each, a GitHub clock call per call and every backlog task probed in a subshell. After: next 1.5–2.1 s, status 1.7 s (reads against GitHub, writes disabled). |
| `uak wait` instead of polling | MLB: 225 `status` and 172 `inbox` calls; agents checked again and again whether a review, a dependency or a reply had arrived, and each check re-sent its output into the context. |
| Claims check every 20 s, inbox read on change | The 2-min full inbox read was the delivery latency of every message; most reads found nothing. |
| New identities start with the last 6 h of messages | MLB: 5 identities joined mid-event and got up to 22 unread broadcasts, 60 h old. |
| `uak map` (code graph) · `msg impact:ID` | Reap and MLB: "it burns tokens reading the same stuff again and again"; at MLB 27 tasks imported HACK-001's files and contract changes reached them by hand-picked messages. graphify reports 71.5x fewer tokens per question with a graph on a 52-file corpus (its own benchmark). |
| `uak learn` / `recall` (path-anchored memory) | MLB: a label that shifts with the measured effect was rejected in 3 tasks and "numbers must come from the CSV" in 4 rejects; a pandas gotcha lived only in a day-1 contract message. 2026 work on long-running agents: situational knowledge works when the harness retrieves it, not when the agent must remember to look. |
| `karpathy-guidelines` skill | The most cited general-purpose rules of 2026 (assumptions stated, minimum code, surgical diffs, verifiable goals); short, no runtime fetches. "Ask" maps to `uak decision`/`uak msg`. |
| Quick card at session start · event-driven reminders · next step in every output | Adoption eval (docs/evals): with AGENTS.md in context, a Sonnet agent sent the contract to the importing task in 0 of 3 runs; with the card and the `done` check, 3 of 3. MLB: 486 status/inbox/board/digest calls and 4 black box notes in 60 h. OpenDev (arXiv 2603.05344): attention to the initial rules fades after ~15 tool calls; capped, event-driven user-role reminders fix it. |
| `uak done` checks the code graph for importing tasks | Same eval: the change reached a live task's import with no message in every baseline run. |
| Installer ignores `__pycache__/`, `*.pyc`, `node_modules/`… · generated-file reason in the gate | Same eval: an agent's `git add -A` after a test run committed `__pycache__` and the merge gate stopped on "New file outside Paths". |
| MCP server (`uak-mcp`), dual-era | Comparison with MCP Agent Mail + Beads and Claude Code agent teams: agents treat MCP tools as native, with a "when to use" description, while CLI commands live in rules they must recall. MCP 2026-07-28 removed the `initialize` handshake; Claude Code and other clients still speak 2025-11-25, so the server serves both. |
| MCP tools return text only, no `structuredContent` | Adoption eval, MCP-only run: Claude Code handed the model `{"ok": true, "exitCode": 0}` instead of the text, so the agent never saw "APPROVED … by judge" and polled status and inbox (3 polls); text only: 1 poll. |
| Presence · review offers that move on (`Review-Offer-Seconds`) | MLB, the v5 week (Oct 2026): 67 review requests went to one named agent and that agent gave 14 of the verdicts; median 55 min and p90 11.5 h to a verdict; 22 messages asked around for a reviewer. "Active" meant any message in 3 h, so closed sessions and a human's own name were picked. |
| Messages to offline identities reach their tasks · `next` shows them to the same human | MLB: over 10 days 28 messages (15 review offers, 11 requests) went to identities that never acted again; one human ran 8 identities and the live one never saw what reached the closed ones. |
| `wt new ID` reuses a free identity | MLB: 18 identities for 4 humans, 8 for one of them; `retire` was used once. One name per agent keeps one inbox and one review history. |
| Human authority only from the shell (`UAK_AGENT_HUMAN` in worktrees) | Kit audit after MLB: `.uak-env` and Claude's `settings.local.json` exported `UAK_HUMAN`, so every agent in a task worktree passed `allow`, `plan`, `retire` and handover of others' tasks. |
| The map is pushed: `map brief` on claim, `map lens` after searches and reads | MLB, v5 week: agent calls of the map per claimed task were 0.1 in Claude Code, 0.4 in Codex, 1.0 in Cursor; a pilot study (grep vs LSP, 2026) measured 0-6% routing to the semantic tool when grep was there, and better runs when the answer came as path:line beside the step the agent already took. |
| `uak plan --amend` before review | MLB, v5 week: a fix needed fixtures and tests outside the published Paths; republishing was refused, so the work went outside Paths or into a new task. |
| Progress on every heartbeat · `uak away` on SessionEnd | MLB: 74 checkpoints for 130 claims, 5 handoffs and 14 releases, 43 lease recoveries; recoveries read a summary that said what the task was, not where it stood, and closed identities kept getting reviews. |
| `recall --similar` (BM25 over lessons, rejects, contracts, decisions) | MLB: the same rejects came back on tasks with other Paths ("numbers must come from the CSV" in 4 rejects, a label that shifts with altitude in 3); path-matched lessons missed them, and agents ran `recall` 10 times for 130 claims. Lexical retrieval needs no model or network; a 2026 study of 11 production harnesses found none using vector embeddings. |
| `map drift` in the hook and in `done` | STORM (arXiv 2605.20563): mediating edits at write time beat one-worktree-per-agent by +18.7 on Commit0-Lite; at MLB breaks between tasks surfaced only in the merge gate, after a review. |
| `uak pr-sync` (CI failures and PR comments → task) | MLB: 52 of 59 integrations merged on GitHub; CI results and human review comments reached agents only through a human. Composio's Agent Orchestrator routes both back to the session that opened the PR. |
| An OWNERS row yields to a task its owner depends on · `plan` and `lint` name unclaimable tasks | A team's black box (Oct 2026, a marathon project): the root task created a mock file inside a mocks package that OWNERS.md gave to a second task, and that task depended on the root. Every claim of the root was `CONFLICT` (exit 3), `uak next` offered nothing, and the project stalled at its first task; two agents logged the same bug. A dependent owner cannot start first, so there is no second writer. |
| `install.sh --update` updates unedited old kit files (`known-files.txt`) · keeps the team's hooks | Kit audit (Oct 2026): an update from v5.0 left 16 `.uak-new` files nobody had edited (settings.json among them, so the v5.1 hooks never arrived), removed a pre-commit the team had extended, and replaced a husky `core.hooksPath`. |
| `uak start` · `next` says why it offers nothing · `lint` groups template owners | The same solo marathon project: two hours before the first claim. Each blocker (the kit not on main, an unapproved plan, `gh` review with one human, an OWNERS row) was one line to fix, and each was found by hand: `next` printed only "No eligible candidate". The template's OWNERS rows name HACK-001, so a plan with another prefix got 12 identical lint lines. |
| `--solo` · `Review-Mode: claims` for one human · `doctor` checks collaborators | A solo marathon project (Oct 2026): two hours in, "it asks for the approval of another GitHub account and I am alone on the repo". GitHub never lets a PR's author approve it, so the default `Review-Mode: gh` could never pass and no message said so. |
