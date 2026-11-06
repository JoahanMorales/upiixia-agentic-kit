# Windows hot paths: what an agent waits for on every tool call

On Git Bash a process costs 20-50 ms (fork and exec are emulated; Defender may scan each one). The kit is bash scripts
that start many short processes, and three of them run around every shell command Claude Code sends: `guard bash`
before it, `hook tick` and `hook output` after it. On a teammate's laptop that was 5.1 s per command.

## How it was measured

`bash scripts/perf_hooks.sh WORKTREE [RUNS]`, in a worktree with an identity and a claimed task (a project made with
`install.sh --mode sprint`, a local bare remote and `wt new HACK-001`).

- **processes**: distinct PIDs in an xtrace of one call (`PS4` prints `$BASHPID`, children inherit `SHELLOPTS`), with a
  traced shim in front of each program, so every bash fork and every program counts once.
- **programs**: how many of those were programs (git, sed, awk…), from the shims.
- **time**: the mean of RUNS untraced calls after one warm call. `tick` is measured on its common path: nothing due
  (the beat, the 20 s poll, pace and drift were done by the warm call).

PC: Windows 11 Pro 26200, Git for Windows 2.45.2 (bash 5.2.26), Nov 2026. Old (`main`, 5.9.1) and new were measured
back to back in the same 10 minutes, since the same command varied up to 2x across the day on this machine.

## Before and after

| command | when it runs | processes before → after | time before → after |
|---|---|---|---|
| guard bash (`ls -la src`) | before every command (all harnesses) | 35 → 1 | 1064 → 79 ms |
| guard bash (`git add … && git commit -m "…"`) | | 81 → 4 | 2074 → 177 ms |
| hook tick | after every tool call | 85 → 3 | 3395 → 222 ms |
| hook output | after every Bash call (Claude Code) | 22 → 3 | 627 → 222 ms |
| hook wrap codex | before every command (Codex, Cursor, Gemini) | 85 → 22 | 2633 → 985 ms |
| guard prompt | every human message | 27 → 1 | 695 → 91 ms |
| hook stop | end of turn | 70 → 53 | 3069 → 2744 ms |
| hook session-start | session start | 360 → 344 | not compared |
| uak next / uak status | when the agent asks | 203 / 173 → unchanged | unchanged |

One Bash command in Claude Code (guard bash + tick + output): **5.1 s → 0.52 s**.

A long heredoc in a command (guard bash, the same machine): 300 lines took **35 s** and 2000 lines **222 s**, past the
5 s hook timeout, and a timed-out hook lets the command run. Now 1.2 s and 3.9 s. The cause was `json_field`, an awk
loop that appended one character at a time; it is now one `match()`.

## What changed

- **guard**: the payload is read with `read` and parsed by parameter expansion (awk over 4 KB). Segments are split by
  parameter expansion. Each rule runs its grep only when the segment holds the words its regex needs (`case`, a
  builtin), with here-strings instead of `printf | grep`. The regexes and messages are the same. The mode is read
  once, and only for a segment a marathon rule could match. Each secret pattern of `guard prompt` runs only when its
  literal prefix is in the message.
- **hook**: stdin by `read`; one `git rev-parse --show-toplevel --git-dir`; `.uak-env`, `session_id`, `tool_name`,
  `tool_input.command` and `Output-Cap-Chars` read by builtins (sed and awk keep payloads over 64 KB or with `\001`);
  `coach`, `lens` and `uilint` called without subshells; the clock once (`printf '%(%s)T'`, `date` on bash < 4.2);
  the hook's state files hold their epoch and `fresh` reads it back (a file without one still goes by its mtime
  through `find`); `net.sh` only before the poll or pace that use it; `wrap` uses `OSTYPE` instead of `uname`.

## How we know the answers did not change

- guard: a differential run of the old and the new guard (`check`, `bash` payloads and `prompt`, in sprint and
  marathon projects, CRLF PROJECT.md included) over 3,620 cases: 140 curated commands for every rule and the known
  bypasses, raw payloads (field order, escapes, a lone backslash, unterminated strings, over 4 KB, `\001`), 25
  prompts, and 3,000 random commands built from rule words and delimiters. No difference in exit code, stdout or
  stderr. A one-character mutation of a rule was caught (it is a real test).
- hook: the new readers were fuzzed against the pipelines they replace (`jdecode`, the sed of `session_id` and
  `tool_name`, the per-line cut of `lens`, the first word of `coach`) on 300 payloads with escapes, truncation and
  multi-line JSON: no difference; a mutation was caught (20 of 100).
- Tests on this PC: test_policy 25/25, test_v21_security 8/8, test_v42 11/11, test_v592 3/3. test_v5, test_v51 and
  test_v591 fail here only on commands that take over the runner's 240 s (`uak merge`, a `git commit` of the whole kit
  through the pre-commit scanner); `main` fails the same cases on this PC, run back to back.
- `.uak/tests/test_v592.py` counts the processes of guard bash, guard prompt, tick and output and times the 300-line
  heredoc; on `main` all three cases fail.

## Not done

- `uak next` and `uak status` (203 and 173 processes; about 38 git calls each, most of them the claims transaction).
  A change to `coord_config` and `coord_source_field` saved 15%, but test_v42's `scope_uses_current_base` then timed
  out on this PC where `main` passed, so it was left out. A 3x cut needs fewer git calls in the transaction: a design
  change of its own.
- `hook stop` (one `uak inbox --peek` per turn, 19 git calls) and `session-start` (once per session).
- Every 5 min `tick` runs `pace --caps` in the foreground (about 40 processes); it could move to the background like
  the poll.

## For the human (not measured here)

- A Windows Defender exclusion for the repository folder and for `C:\Program Files\Git` may cut the cost of each
  process further. It is a security trade-off for the person who owns the machine; this work did not change any
  system setting and did not measure it.
- Keep repositories outside OneDrive (HACKATHON.md already says so): sync locks the files git writes.

## Review on Linux (before the merge)

The table above is the common path: a short command and a short output. The review measured the hook on long
payloads too, old (5.9.1) and new on the same machine (aarch64, bash 5.1, mawk, `es_MX.UTF-8`), best of 3:

| `hook tick` payload | 5.9.1 | this branch as pushed | merged |
|---|---|---|---|
| 10-line heredoc | 105 ms | 22 ms | 22 ms |
| 200-line heredoc (4 KB) | 123 ms | 755 ms | 62 ms |
| 800-line heredoc (16 KB) | 177 ms | 10.4 s | 93 ms |
| `pytest -q`, 40 KB of output | 169 ms | 1.26 s | 52 ms |
| `pytest -q`, 480 KB of output | 638 ms | 435 ms | 139 ms |

- **The builtin readers were quadratic under 64 KB.** `jdecode_var` copied the rest of the payload at each escape
  (`\"`, `\n`), and a PostToolUse payload carries the whole output after the command; `json_id`'s `${line%"KEY"*}`
  tried every end position (0.55 s on 40 KB in a UTF-8 locale). Above 64 KB awk took over, so the Windows table never
  saw it. Now: the readers look at the payload's first 4 KB (`IN_HEAD`), where the harnesses put the ids and the
  command; a key also present past it, a key not in it, or a value cut by its end goes to the sed or awk they
  replaced, so the answer is the old one. `jdecode_var` reads a 2 KB window, sends a value with more than 64
  backslashes to awk, and remembers its last answer (coach and lens both read the command).
- **stdin**: `read` takes a pipe a byte at a time (0.3 s for 480 KB). The first 8 KB by `read`, the rest by `cat`.
- **A command over 4 KB** goes to the old `sed`/`awk` for coach's first words and lens's segments (a loop copied it at
  every line).
- **test_v43** faked Windows with a `uname` shim; `wrap` reads `OSTYPE` now, so the test sets `UAK_TEST_WINDOWS=1`
  (it failed on Linux and macOS CI, and the suite stops at the first failure).
- Checked: the readers against `sed`/`awk` on 600 payloads with keys and values around the 4 KB boundary, and the
  2 KB window on 1,500; the hybrid stdin read against `$(cat)` at the 8 KB boundary (ASCII, `é`, `日`, trailing
  newlines, C and UTF-8); the old and new guard on 3,000 more random cases with mawk: no difference.
  `test_v592.tick_stays_fast_on_a_long_payload` fails on the branch as pushed (10.6 s) and passes on 5.9.1 and here.

## The claims commands: next, status, heartbeat (UAK-001 … UAK-017, Nov 2026)

The row "uak next / uak status · unchanged" above was left for a design change of its own. This is that change:
the claims state is read in one awk pass instead of a `$(field …)` subshell per field (UAK-003), the merge gate's
scope check is one awk pass (UAK-008), and STATE.md, which every mutation rewrites, is one awk pass too (UAK-016).

### Processes

Counted by `kit/.uak/tests/test_claims_perf.py` (UAK-001's counter: distinct PIDs in an xtrace, a traced shim in
front of each program, `ps` included) on its fixture: 12 tasks, 3 live claims, a local bare remote. Old is `main` at
c949f90, the last commit before UAK-003; new is 0ec9f2f. Same machine, back to back.

| command | old → new | target | what is left |
|---|---|---|---|
| `uak next` (an agent with a claim) | 208 → 93 | 40 | the claims transaction: a fresh shallow clone, its config fetch |
| `uak next` (an idle agent choosing) | 258 → 122 | 40 | the same, plus one gate probe per candidate |
| `uak status` | 190 → 61 | 30 | the clone and the base's PROJECT.md |
| `uak heartbeat` | 240 → 139 | 20 | clone, commit, secret check, push: a mutation's whole transaction |

STATE.md alone went from 130 processes on 12 task records and 346 on 48 to 4 for any number (test_snapshot.py).

### Time

`bash scripts/perf_claims.sh RUNS` (the median of RUNS calls after a warm one), old and new back to back:

| machine | `next` | `status` | `heartbeat` |
|---|---|---|---|
| Windows 11 Pro 26200, Git for Windows 2.45.2 (bash 5.2.26), 2 rounds of 5 | 5.1 → 3.6 s (−30%) | 4.5 → 2.9 s (−36%) | 6.3 → 5.0 s (−20%) |
| Linux, aarch64 (Jetson), bash 5.1, mawk, 7 runs | 0.68 → 0.49 s | 0.63 → 0.44 s | 0.78 → 0.65 s |

Windows: the medians of the two rounds were within 0.1 s of each other (next 5.12 and 5.08 → 3.64 and 3.53 s, status
4.55 and 4.54 → 2.98 and 2.89 s, heartbeat 6.26 and 6.25 → 5.06 and 4.95 s). The same seconds saved on Linux are
about 8x as many on Windows (next: 0.19 s there, 1.5 s here). To measure again, in Git Bash at the repository's root:

    git archive c949f90 kit | (mkdir -p "$TMP/uak-old/scripts" && tar -x -C "$TMP/uak-old") &&
      cp scripts/perf_claims.sh "$TMP/uak-old/scripts/" && bash "$TMP/uak-old/scripts/perf_claims.sh" 5
    bash scripts/perf_claims.sh 5

A heartbeat still takes about 5 s on this PC: the clone, commit and push of its transaction are what is
left. `next` and `status`, the reads an agent waits on, are 1.5 s faster each.

### Targets dropped, and why

The targets (`next` ≤ 40, `status` ≤ 30, `heartbeat` ≤ 20) stay in test_claims_perf.py's XFAIL set: none is met.
What is left is mostly the claims transaction itself, one fresh shallow clone of the claims branch per call (and a
commit and a push per mutation). UAK-002 and UAK-005 were to keep a persistent claims repository per clone and reuse
it; they were cancelled: the cut was about 5 processes per call, for a lock shared between processes (two agents of
one clone) that raced on CI. The tip-keyed cache of the parsed state (UAK-004) is merged but not wired: with the
clone still paid on every call it saves one awk, and a put after a commit could store an old state under the new tip
(`uak learn` #1 on kit/.uak/bin/lib/).

### How we know the answers did not change

`python3 scripts/claims_diff.py` runs the old engine (c949f90, from this repository's history) and the new one through
the same 31 protocol steps on the same fixture and clock (`UAK_NOW`): status and next before any claim, claims (one
taken, one before its dependency), heartbeat, status (`--full`, `--task`, `--summary`), next with a claim and for an
idle agent, a request message, inbox and its ack, log and BLOCKED, checkpoint, decision, release and a claim again,
done, a reviewer registered, review start and approve, next while in REVIEW, digest. After every step the exit code,
stdout and the whole claims tree are identical once these are written the same way: the fixture's folder, commit
SHAs, the transaction's temp-folder suffix in worklog names, the read token's checksum (it covers that worklog name;
its length is still compared) and git's "N seconds ago". A one-character change to STATE.md's text makes it fail at
the first step. test_claims_perf.py runs it as `old_and_new_engines_print_the_same_and_write_the_same_tree`.

Left out on purpose, because they changed output to fix a bug: `uak merge` from a task worktree (UAK-012), a CRLF
checkout (UAK-014), bash 3.2 (UAK-013), and a task listed before a dependency nobody has claimed (UAK-017).
`uak merge` itself is not in the scenario (its gate runs the fixture's smoke); the scope check UAK-008 rewrote is
tested on its own in test_gate_scope.py (the same verdicts and reasons, 200 files, file names that look like
patterns), not against the old engine.
