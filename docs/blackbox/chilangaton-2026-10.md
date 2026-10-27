# Black box · Chilangatón (Oct 25, 2026) · one-day sprint, reconstructed from claims

Source: one 7-hour sprint-mode hackathon (5 humans, 10 Claude Code identities on macOS and Windows laptops, 35 tasks,
33 reviews, 176 messages, 32 decisions), read from the claims branch: `blackbox/*.md` from 5 machines, `inbox/log.md`,
`DECISIONS.md` and the task worklogs. Venue Wi-Fi dropped twice (≈19:45Z and 20:18–20:29Z). Same line format as `uak bb`.
Status column: what this PR does about it (**fixed**, **proposed** for the maintainers, or **kept** as designed).

| # | Kind | Command | What happened | Count | Status |
|---|---|---|---|---|---|
| 1 | bug | `uak merge` | An adopter merged an approved task (Merge-Adopt) while its owner's `merge` waited on "Queue busy". The owner's next lock found no claim: human queue as "Task without claim; cannot merge", `Next: Humano: …` written on the INTEGRATED record, a message to the human that stayed in the digest | 1 | **fixed**: `OK merge ID \| already INTEGRATED by NAME` |
| 2 | bug | `uak done` | "Could not read PROJECT.md on remote main" from 18:38Z to 20:29Z: the full fetch of the base (done/integrate/merge) had no retry and dropped git's error, so the cause (Wi-Fi drop, or a slow full-history fetch cut by the 1000 B/s limit) was never shown | 10 (6 lines) | **fixed**: 3 tries, git's first error line in the message |
| 3 | bug | `uak done` | After a handover Windows → macOS, the claim kept the Windows worktree path; `done` died with "Missing worktree to record Task-Tip". Way out: release and re-claim (one decision, two heartbeat/handover conflicts) | 1 | **fixed**: `done` adopts this checkout when it is on the task's branch |
| 4 | friction | `guard` | Reviewers' detached checkouts (`git worktree add ../review-ID origin/<branch>`) kept Verify's untracked build output; the plain remove refused, `--force` was blocked, and the hint `wt rm ID` names the owner's worktree | 11 + 1 `rm -r` | **fixed**: `wt rm --review PATH` |
| 5 | bug | product stack | `ZoneInfo("America/Mexico_City")` → `ZoneInfoNotFoundError` on Windows: no tzdata. The fix touched `pyproject.toml`/`uv.lock` (owned by setup), so it needed a follow-up task and a human merge | 1 | **fixed**: the FastAPI stack adds `tzdata` at setup |
| 6 | friction | merge gate | Lockfiles always go to the human queue, even when the task holds them in its own Paths (the follow-up above: `uv.lock`), and the setup task's `.uak/bin/.smoke-project.provenance` | 2 | **proposed**: a lockfile listed by exact path in the task's Paths, next to its manifest, could merge without a human; the provenance file stays human-gated |
| 7 | friction | claims | "done/review/status retry 10+ times and take over 8 min" with 10 agents and their hooks pushing claims. Backoff with jitter exists; `done`/`integrate`/`merge` also refetch the whole base on every retry (`coord_init` runs per try directory) | 1 note | **proposed**: fetch the base once per call and reuse its objects across attempts |
| 8 | friction | network | "Remote unreachable (3 tries)" on heartbeat, inbox, claim, review, msg, tick and pr-sync during the two outages | 14 | kept: the 3 tries worked for short drops; a 10-min outage is beyond any retry |
| 9 | friction | history | A branch commit carried an unwanted attribution trailer; force-push is blocked (rightly), so a human squash-merged on GitHub and an agent recorded `integrate` | 1 | **proposed**: a `Merge-Strategy: squash` option for `uak merge` |
| 10 | friction | `wt new` | One machine's https remote had no credentials; `wt new` failed at the claim push | 1 | kept: `doctor` already does a dry-run push; that machine skipped it |
| 11 | friction | `uak review` | "X is already reviewing ID at this SHA" after review offers to `all` | 9 | kept: the lock did its job; each refusal cost one call |
| 12 | friction | `uak review` | "HEAD moved: N commit(s) after your SHA" | 5 | kept: the message says what to diff |
| 13 | friction | freeze | 4 claims refused after the freeze; 5 human `allow` exceptions, each with a reason | 4 | kept: the human decided every one |
| 14 | friction | `guard` | `pkill -f` (4) and reading `.env` (3) blocked | 7 | kept |
| 15 | friction | leases | 2 `REQUIRES_RECOVERY` (one recovered by another agent with the read token) | 2 | kept |
| 16 | praise | protocol | Rejects with `file:line` caught real bugs before the demo (an inverted demo dataset, a view that crashed with the live API, simulated data presented as real in the script) | 7 rejects | kept |

## As black box lines (anonymized; SHAs and task IDs kept, names and paths removed)

```text
- 2026-10-25T18:05Z | v5.3.0 | claude-code | sprint | agent | friction | - | claim push fails: no GitHub credentials for https remote on this machine, wt new gives up | fix: doctor should check push auth to origin before the first claim
- 2026-10-25T18:32Z | v5.3.0 | claude-code | sprint | agent | friction | - | many agents pushing claims at once: done/review/status retry 10+ times and take over 8 min | fix: batch claim writes or back off with jitter; show progress while retrying
- 2026-10-25T20:20Z | v5.3.0 | claude-code | sprint | auto | exit1 | uak done | GIT_ERROR: Could not read PROJECT.md on remote main. (x2) | fix: -
- 2026-10-25T20:29Z | v5.3.0 | claude-code | sprint | auto | exit1 | uak done | GIT_ERROR: Could not read PROJECT.md on remote main. (x2) | fix: -
- 2026-10-25T20:22Z | v5.3.0 | claude-code | sprint | auto | exit1 | uak review | GIT_ERROR: Remote unreachable (3 tries). fatal: unable to access '<remote>': Recv failure: Connection reset by peer | fix: -
- 2026-10-25T20:39Z | v5.3.0 | claude-code | sprint | auto | exit2 | uak done | ERROR: Missing worktree to record Task-Tip. | fix: -
- 2026-10-25T20:39Z | v5.3.0 | claude-code | sprint | auto | exit3 | uak handover | CONFLICT: PB-027 already belongs to <agent>. | fix: -
- 2026-10-25T20:20Z | v5.3.0 | claude-code | sprint | auto | exitguard | uak guard | worktree remove --force loses uncommitted changes. Use bash .uak/bin/wt rm ID. | fix: -
- 2026-10-25T19:59Z | v5.3.0 | claude-code | sprint | auto | exitguard | uak guard | pkill -f/killall match by pattern and can kill your own shell or other agents' servers (UpiixSol). Kill exact PIDs: bash .uak/bin/wt stop, or kill $(lsof -ti tcp:$UAK_PORT). | fix: -
- 2026-10-25T19:41Z | v5.3.0 | claude-code | sprint | auto | exit3 | uak claim | CONFLICT: pyproject.toml belongs to PB-001; split the work or request its contract. | fix: -
- 2026-10-25T20:51Z | v5.3.0 | claude-code | sprint | auto | exit3 | uak integrate | CONFLICT: Missing verifiable approval on claims. Approve the merged SHA first: uak review PB-027 --sha <sha> --verdict approve | fix: -
```

The merge race (#1) and the human-queue entries (#6) left no black box line: they are in `inbox/log.md` (kind `human`)
and the task worklog (`merge rechazado; Task without claim; cannot merge`, 19 s after `INTEGRATED … merge` by the adopter).
