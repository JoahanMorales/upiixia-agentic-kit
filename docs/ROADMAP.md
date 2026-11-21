# Roadmap

## Now: v6.6 → v7.0 (from the audit of Nov 2026, `docs/audit-2026-11.md`)

**v6.6 · The defects the audit found (shipped 2026-11-21).** One live task per identity holds for heartbeat, log and checkpoint; the MCP
`uak_cli` cannot run a passed command unseen; the guard treats substitutions inside quotes as code, sees `gh … merge`
with flags and refuses a plain push to claims; the merge lock's renewer dies with its parent; an unapproved task cannot be
recorded INTEGRATED by its owner; temp files and Python subprocesses get names and timeouts.

Left from v6.6: a pre-push hook that reads the real ref (the guard only reads text), `guard` reading `Mode`
case-insensitively, the P2 items of the audit (#9 other Python helpers, #11 identities).

**v6.7 · Everything measurable (shipped 2026-11-21).** A ledger of every command (name, outcome, milliseconds) published with the black box;
`uak metrics`: calls and error rate per command, time per step, review rejections, rework after a reject, reverts and
reopened tasks, human interventions with their reason, work outside the kit (commits on main without a task, and a
`manual` note for "I had to do this by hand"), tokens per task and per step. Each speed number next to an instability
number. `uak autopsy` writes the event report (timeline, top issues, metrics) from claims.
Who did what: every task records the agents that touched it (author, reviewers, who merged) and the model and harness
each one ran, per step. The board explains itself: REVIEW is split into what it is really waiting for (a reviewer,
changes after a reject with the count, CI, a human merge) with the time spent in each, so a card that sits for hours
says why. Clicking a task opens its whole story: every move with its time, agent, model, verdict and reason, the
rejects and what changed after each, CI runs, tokens, drawn as a timeline a human can audit.

Left from v6.7, now tasks of v6.8: the `Merge-Commit` field (UAK-132), `tokens --since` and the budget warning
(UAK-133), sub-states in `board` and `--json status` (UAK-134), the hooks in `doctor` and `wt` (UAK-135), the ledger of
commands that replace the shell (UAK-136), the autopsy's classes (UAK-137), the three flaky tests (UAK-138).

**v6.8 · Lighter, and what v6.7 left broken.** Plan: `docs/plans/plan-v68.md` (UAK-127…139, checked with
`uak plan --check`, waiting for the human to publish). An install without the kit's own tests and with skills on demand
(535 files → under 200, UAK-127); Windows CI in shards and one run per commit (121 jobs → at most 24, UAK-128); the
reviewer runs Verify and the tests the diff touches, the full suite runs once, at the merge gate (UAK-129); `status` and
`next` read one cached fetch of claims (UAK-130); `Merge-Engine: ci`, so an approved engine change with every check
green does not wait for a human (38 of 39 queued tasks did, UAK-131); the demo records models (UAK-139). The process
target of `heartbeat` (139, target 20) stays open: it is a write, and needs the claims transaction itself to change.

**v7.0 · A kit that improves itself, behind a gate.** Scenario evals (`uak eval`): seeded mini-repos that replay each
failure class of the black boxes against the engine, reported as k of n; mutation tests of the guard and the gates (remove
a rule, a scenario must fail). While agents work: a repeated error in a session brings its lesson into context, and a
correction made twice becomes a candidate check. After an event: `uak improve` clusters the black box, proposes a
lesson, a hint or a rule as a PR, and it is adopted only if the evals pass and a human approves; it never edits the guard
or the gates, and every adoption can be reverted.

**v7.1 · Marathon in a codebase that already exists.** `install --adopt`: reads the stack, the test command and the CI
that are there, writes a short PROJECT.md and a map for a human to trim, takes over no file; tasks imported from the
issues the team already has; a pilot scope (one module's paths) before the whole repo; quality gates that use the
project's own checks. Two modes stay (sprint, marathon): adoption is a way to install marathon, not a third mode.

**v7.2 · The project's video.** `uak video`: a script built only from the repo's facts, ElevenLabs narration with word
timings, real captures of the app, the terminal and the dashboard, a HyperFrames render with burned captions and a
measured MP4; `/uak-video` runs it end to end. Plan: `docs/plans/video.md` (written 2026-11-10, not published yet).

Waiting: the fork with the TLA+ model of claims, the revert rate in `stats`, WHY.md enforcers and verification skills
(merge when its author finishes); external PR #2 (visual setup).

## Still open from earlier roadmaps

- **Process targets of the claims engine.** v6.0 shipped the redesign below (persistent claims repo, reads without a
  checkout, tip-keyed cache, reused worktree), but the counts did not reach their targets: `next` 93 processes (target
  40), `status` 61 (30), `heartbeat` 139 (20), kept as expected failures in `test_claims_perf`. The reads are in v6.8 (UAK-130); `heartbeat` stays open.
- A harness eval set from black box failures, run per release → v7.0 (`uak eval`).
- Token budgets per task (`Token-Budget`, warned by `next`) → v6.7.
- Lessons ranked by how often they were recalled, expiry for stale ones → v7.0.
- A live Windows Cursor session and a live Codex session with the rewritten hooks, drift recorded with `uak bb`.
- Antigravity CLI support (the successor of Gemini CLI) once its hook and config docs settle.
- Cursor token spend, if Cursor publishes a usage API or a local log.
- `uak map`: optional tree-sitter backend, and call edges (not only imports).
- `uak board --watch` in the demo animation.
- Ideas: Linear and Jira ID prefixes with two-way sync (see v7.1's issue import); localized agent-facing texts
  (`UAK_LANG`); `uak loop --parallel` for more test runners.

## Shipped

What each release shipped is in `CHANGELOG.md`; the plans they were built from are in `docs/plans/`.

- **v6.5** (Nov 2026): eight fixes from the black box harvest of 14 repos. **v6.4**: the creativity index for design
  rounds. **v6.3**: a design taste the kit learns and ships. **v6.2**: landing rounds with human picks.
  **v6.1**: what two hackathons taught.
- **v6.0 · The claims transaction without the process storm.** The design this file used to list as "next", built as
  UAK-001 … UAK-008: a persistent claims repo per clone, reads through one `git cat-file --batch` into one awk pass, a
  tip-keyed cache of the parsed state, mutations on a reused worktree, old and new engines proven identical on the
  protocol suites, `hook stop` and `session-start` on the new read path. Why: on Git Bash a process costs 20–50 ms and
  `uak next` started about 200.
- **v5.11**: the kit developed with itself; one config reader, a command registry, result codes and `--json`.
  Porting the engine to Go or Rust was estimated and decided against (`docs/plans/port-go.md`).
- **v5.0**: one round trip per call, `uak wait`, `uak map`, path-anchored memory, `uak tokens`, `uak loop`,
  `handover`, stack presets, the weekly black box harvest, the animated demo.
- v4.3 (MLB autopsy) and v4.2 (Reap autopsy): `docs/blackbox/`. v3.1: `uak stats`, `uak board`, `uak up`, `uak demo`.
