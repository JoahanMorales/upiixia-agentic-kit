# Porting the engine to Go (or Rust): an estimate

Status: proposal, Nov 2026. Nothing here is decided; it sizes the work so the owner can.

## What there is to port (measured on v5.10.0)

| Piece | Size | Notes |
|---|---|---|
| Engine scripts (`kit/.uak/bin`, `lib/*.sh`, `install.sh`) | ~7,700 lines of bash in 40 files | `uak` 1,994 · `review-merge.sh` 856 · `hook` 739 · `uak-coordination` 696 · `map` 539 · `guard` 474 · `messages.sh` 453 |
| Embedded programs | 257 inline awk programs, 63 lines of `.awk`, 525 `git` invocations | the claims transaction is git plumbing driven from bash |
| Python in the engine | `uak-mcp` (662 lines), `dash.py` | optional today: the MCP server and the dashboard |
| CLI output contract | 386 `say`/`die`/`conflict` messages | agents and tests read these lines |
| Tests | 260 black-box tests, 7,700 lines of Python, 25 files | they run the CLI as separate processes against real Git: they do not care what language the engine is |
| Text that stays text | AGENTS.md, modes, docs, 13 skills (3,000 lines), templates, hook configs | not code; unchanged by a port |

What the code spends its effort on: 140 comments document a portability workaround (bash 3.2 on macOS, BSD
awk/sed, mawk, Git Bash/MSYS, CRLF); 22 of the last 83 commits are fixes, most of them one of those. This session alone
added three (a quadratic `${s//…}` on bash 3.2, a fork per here-document on Git Bash, `$BASHPID` missing on 3.2).

## Why a compiled engine

- **One process instead of 30 to 200.** On Git Bash a process costs 20–50 ms; `uak next` starts about 200. A Go
  binary parses the claims in memory: one process plus the git calls it cannot avoid (fetch, push), 2–10 ms of its
  own on Windows.
- **The portability tax goes away.** No bash 3.2 vs 5, no BSD vs GNU awk/sed, no MSYS path conversion, no CRLF in
  scripts, no Store `python3` alias. One codebase, cross-compiled for 6 targets (Linux, macOS, Windows × amd64,
  arm64). Most of the 140 workarounds and their tests become unnecessary.
- **Real data structures.** Claims, tasks, messages and leases become typed structs, parsed once; JSON (hooks, MCP,
  transcripts for `tokens`/`pace`) uses a real parser instead of awk and parameter expansion.
- **Concurrency where it helps.** The kit's coordination is between processes and machines through Git (an optimistic
  transaction on the `claims` branch with retries); goroutines do not change that design. They help inside one
  command: fetching claims while reading the backlog, the merge gate's checks in parallel, `wait` without a polling
  shell loop, the MCP server serving several calls.

## Go or Rust

| | Go | Rust |
|---|---|---|
| Fit for this workload (git, files, text, network) | very good: stdlib covers process exec, JSON, regexp, HTTP, embed | very good |
| Startup | ~1–3 ms | ~1 ms (no measurable difference here: the time is in git and the network) |
| Cross-compilation | `GOOS/GOARCH`, built in | needs `cross` or zig for some targets |
| Speed of writing and changing it, by agents and humans | fast compile, small language, agents write it well | slower: the borrow checker and longer compiles mean more iterations per change |
| Concurrency model | goroutines and channels, simple | async (tokio) or threads; more ceremony |
| Effort for the same port | 1× | about 1.4–1.8× |

Recommendation: **Go**. The kit is I/O-bound (git, files, network): Rust's raw speed buys nothing measurable, and its
cost is paid on every future change. Rust would earn its place only for a CPU-heavy part (a tree-sitter code map),
and that can be a library later.

Note: GitHub's Spec Kit is Python (98% by GitHub's language count, installed with `uv tool install specify-cli`), not
Go. Python would also remove the bash/awk tax, but every laptop would need a working Python (the Windows audit found
the Store alias in its place) and it starts in 30–60 ms per call; a static Go binary needs nothing installed.

## What gets harder (and how to handle it)

- **Agents can no longer read and patch the engine inside a project.** Today `.uak/bin` is readable bash an agent can
  inspect when the kit misbehaves. Mitigation: `uak explain CMD` prints what a command checks and why (from WHY.md),
  the black box keeps reporting upstream, the source is open, and fixes ship as releases.
- **Supply chain.** Projects would run a downloaded binary. Releases need SHA-256 checksums, GitHub artifact
  attestations (or cosign), the version pinned in `.uak/VERSION`, and `install.sh` verifying before it installs.
- **Windows SmartScreen and antivirus** flag unsigned Go binaries now and then. Sign Windows builds (SignPath is free
  for open source; a commercial OV certificate costs roughly US$200–400 a year).
- **Offline installs** (event Wi-Fi): the binary is cached in `~/.uak-kit` like the clone is today; `install.sh` can
  take a local binary path.
- **A second toolchain in CI**: Go 1.2x on the 3 runners, plus goreleaser for releases.

## The plan: strangler, test-first, never a big bang

The 260 black-box tests are the specification: they invoke `.uak/bin/uak` as a process. During the port
`.uak/bin/uak` becomes a 3-line shim that runs the Go binary when present (`UAK_ENGINE=bash` forces the old engine).
Every phase ships when the whole suite is green on both engines and a differential run (old vs new, same inputs, the
method used for `guard` in v5.9.2) shows identical output.

| Phase | Scope | Estimate (one developer driving agents) |
|---|---|---|
| 0. Foundations | Go module (`cmd/uak`, `internal/{config,backlog,claims,gitx,msgs,memory}`), the dispatcher with the same usage and messages, goreleaser with checksums and attestations, `install.sh` downloading and verifying the binary, the shim, CI on 3 OS | 3–5 days |
| 1. Hot paths (no claims) | `guard`, `hook` (tick, output, wrap, stop), `q`, `cap`, `red`, `design-lint` (RE2 handles its ERE patterns), `secret-scan` | 1–1.5 weeks |
| 2. The claims engine | the transaction on git plumbing without a checkout (`cat-file --batch`, `commit-tree`, `push` with retries), `next`, `status`, `claim`, `heartbeat`, `release`, `handover`, `done` with its gates, `review`, messages, `inbox`, `wait`, `learn`/`recall` (BM25), `plan`, `lint` | 2–3 weeks |
| 3. The rest | the merge gate (`review-merge`), `wt`, `map`, `graph`, `board`/`stats`/`dash`, `deploy`, `doctor`/`start`, `tokens`/`pace`, `garden`, `demo`, `up` | 1.5–2 weeks |
| 4. MCP server in Go | the 15 tools, resources and prompts (removes the Python dependency) | 3–5 days |
| 5. Cut-over | one release with both engines, then bash removed; docs, WHY.md, contributor guide | 1 week |
| **Total** | about 12,000–16,000 lines of Go | **7–10 weeks** part-time, **4–6 weeks** full-time |

Token budget (an estimate, not a quote): 150–300 agent sessions, mostly Sonnet with Opus at plan lock and review;
roughly US$300–1,500 at API prices, or several weeks of a Max plan's windows.

## The cheaper alternative

Stay in bash and do the claims-transaction redesign of the roadmap (a persistent claims repo, one awk pass, a
tip-keyed cache): **2–3 weeks** for most of the Windows speed. It keeps the portability tax: expect one or two
platform bugs per release, now caught earlier by `scripts/kit_lint.py`.

## Decision points for the owner

1. Go (recommended), Rust, or stay in bash with the transaction redesign.
2. Signing Windows builds: SignPath (free, needs approval) or a paid certificate.
3. Whether projects may run a downloaded binary at all (some teams forbid it): if not, keep the bash engine as a
   supported fallback for one or two releases.
