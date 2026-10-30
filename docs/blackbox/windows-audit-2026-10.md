# Black box · a Windows audit of HackADA (Oct 30, 2026) · the kit and the product on a teammate's laptop

Source: after the [HackADA autopsy](hackada-2026-10.md), a teammate ran the kit's suite and the HackADA product on a
Windows 11 laptop of the event, with Git Bash (MSYS 3.4, Git for Windows 2.45, `core.autocrlf=true` system-wide), Node
20.16, the official Python installer and the Microsoft Store aliases on PATH, and no uv or rg. Kit v5.9.0, project kit
v5.3.0 and then updated to v5.9.0 with `install.sh --update`. Nothing hung; 19 rows.
Status column: what v5.9.1 does about it.

The root cause of most rows: what the kit checks by finding a program (`command -v python3`, a bare `bash`) is not what
runs on Windows, and what `install.sh --update` refreshes (`.uak/`) is not where the stack's fixes live in a project
that already exists (`pyproject.toml`, `vite.config.ts`, the Node on the laptop).

| # | Kind | Where | What happened | Status |
|---|---|---|---|---|
| 1 | bug | doctor | `python3` is the Store alias: it prints "Python was not found…" and exits 49, and doctor said `OK python3` | **fixed**: doctor runs `python3`, `python` and `py` and names the first that answers |
| 2 | bug | tests | 4 suites ran a bare `python3` (the MCP client, a lint call, the product CI step) or decoded the alias's cp1252 message as UTF-8 and lost the output | **fixed**: the tests run `sys.executable` and decode with `errors="replace"`; the product CI step falls back to `python` |
| 3 | bug | start | Without `~/.uak-kit`: "line 45: …/VERSION: No such file or directory", and no word that the kit was old (the tag lookup ran inside the missing clone) | **fixed**: the redirect is quiet, and without a clone `start` asks the kit's GitHub for its latest tag and says `git clone … ~/.uak-kit, then install.sh --update` |
| 4 | hole | doctor | The project had no `tzdata` after the update: test collection failed with 11 errors (`ZoneInfoNotFoundError`); `pip install tzdata` made 156 tests pass | **fixed**: doctor finds `zoneinfo` in the code with no `tzdata` in `pyproject.toml` or `uv.lock` (FAIL on Windows, WARN elsewhere) |
| 5 | hole | doctor | Node 20.16 under Vite 8's `^20.19.0 \|\| >=22.12.0`: npm skipped the native `@rolldown/binding-win32-x64-msvc` and the build failed with "Cannot find module" | **fixed**: doctor checks the Node on PATH against the `engines` of each `package.json` and its direct dependencies in `package-lock.json` (FAIL, with the winget/brew/nvm line) |
| 6 | hole | doctor | The project's `web/vite.config.ts` had no `envDir` after the update (the fix was only in the stack template) | **fixed**: doctor warns when a Vite one level down has no `envDir` and no `.env` of its own while the root has `VITE_` keys |
| 7 | risk | hooks | Codex, Cursor and Gemini hooks ran a bare `bash`; from PowerShell or cmd that is System32's WSL launcher (here: `execvpe(/bin/bash) failed`) | **fixed**: every hook goes through `git -c alias…`, whose shell is Git's own, from the top level, without the alias's git variables; a test runs each guard with System32 first on PATH |
| 8 | risk | install | No `.gitattributes`: with `autocrlf=true` every `.uak/bin` script was CRLF on disk (Git Bash copes; WSL, Docker or a CI container would not) | **fixed**: `install.sh` adds `text=auto eol=lf` for `.uak/**`, `.githooks/**` and `*.sh` |
| 9 | flaky | tests | A push to the fixture's local bare repo dropped once ("unexpected disconnect while reading sideband packet") | **fixed**: the test harness retries a push the remote hung up on, once |
| 10 | bug | tests | The handover test expected `/c/Users/…/Temp`; Git Bash records `/tmp/…`, its mount of `%TEMP%` | **fixed**: the test asks bash for the path |
| 11 | friction | tests | `test_mcp_tools.py` left a pipe open ("ResourceWarning: unclosed file") | **fixed** |
| 12 | slow | suite | The suite took about 75 min on this laptop against about 4 on Linux; `uak start` 45 to 54 s; one merge test 220 s | kept: no hang, and CI's Windows runner is faster; measured, not explained |
| 13 | praise | doctor | v5.9's Verify-tools check named `uv rg`, the winget line and the negated `rg` note | kept |
| 14 | praise | start | With a kit clone present, v5.9's "update the kit" step appeared with the command | kept |
| 15 | praise | install | `install.sh --update` from 5.3.0 to 5.9.0: 16 s, no `.uak-new` file | kept |
| 16 | env | laptop | No uv, no rg, Node under the stack's minimum | the laptop's; doctor names all three |
| 17 | env | laptop | `ln -s` makes a copy without developer mode | kept: `wt new` already copies the `.env` on Windows |
| 18 | env | product | HackADA's own `pyproject.toml` lacks `tzdata` | the project's: `uv add tzdata` there |
| 19 | not verified | hooks | Codex and Cursor themselves were not on the laptop | row 7 covers the shell; the harnesses were not run |

What v5.9.1 changes, with a test each in `kit/.uak/tests/test_v591.py`: rows 1, 3, 4, 5, 6, 7 and 8; rows 2, 9, 10 and
11 are changes to the tests themselves.
