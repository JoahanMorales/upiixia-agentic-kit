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
