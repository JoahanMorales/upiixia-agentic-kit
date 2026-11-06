#!/usr/bin/env python3
"""uak v5.11: an engine that is easier to change without breaking it. One reader of PROJECT.md (13 copies disagreed),
one command registry (help, dispatch, CLI.md and the MCP tools were five hand-kept lists), `uak` split into one file
per command family (it was 1,995 lines), and `uak --json` with stable result codes for programs that should not parse
prose. Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def config_reader_reads_every_form(r):
    """Bold, a list bullet, backticks, CRLF, trailing spaces, no final newline, stdin: one answer for each."""
    d = r.scratch / "v511-config"
    d.mkdir()
    (d / "P.md").write_bytes(b"# Project\r\n- **Mode:** `marathon`  \r\n* UI-Paths: web/src, app/ \r\nFreeze-Epoch:0\r\n"
                             b"- **Empty:**\r\nDup: 1\r\nDup: 2\r\nReview-Mode: claims\r\nLast: noeol")
    script = ('. "$1/.uak/bin/lib/config.sh"; for k in Mode UI-Paths Freeze-Epoch Empty Dup Last Missing; do '
              'uak_cfg_var "$2" "$k" DEF; printf "%s=[%s]\\n" "$k" "$CFG"; done; '
              'printf "Mode: sprint\\n" | uak_cfg - Mode; uak_cfg "$2" Review-Mode')
    out = r.run([r.bash, "-c", script, "_", r.package.as_posix(), (d / "P.md").as_posix()]).stdout
    want = ["Mode=[marathon]", "UI-Paths=[web/src, app/]", "Freeze-Epoch=[0]", "Empty=[DEF]", "Dup=[1]", "Last=[noeol]",
            "Missing=[DEF]", "sprint", "claims"]
    expect(out.split() == " ".join(want).split(), out)
    # A consumer that used its own copy (up): a bold, backticked Max-Worktree-Agents is the limit.
    t = r.scratch / "v511-up"
    t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    (t / ".uak").mkdir()
    (t / ".uak/PROJECT.md").write_text("- **Mode:** sprint\n- **Max-Worktree-Agents:** `2`\n", encoding="utf-8")
    up = r.run([r.bash, (r.package / ".uak/bin/up").as_posix(), "3"], cwd=t, env={"UAK_HUMAN": "ana"}, allowed=None)
    expect(up.returncode == 2 and "exceeds Max-Worktree-Agents (2)" in up.stderr, up.stdout + up.stderr)
    return {"forms": len(want)}


def json_envelope_reports_results_and_codes(r):
    """A program reads the result, a stable code and the task's state without parsing the text."""
    j = json
    f = r.fixture("v511-json", paths={"HACK-001": "src/a/", "HACK-002": "src/a/b.py"}, count=2)
    f.claim(0, "HACK-001")
    ok = f.hack(0, "--json", "heartbeat", "HACK-001")
    o = j.loads(ok.stdout)
    expect(o["v"] == 1 and o["ok"] is True and o["exit"] == 0 and o["result"] == "OK" and o["code"] == "ok"
           and o["cmd"] == "heartbeat" and o["id"] == "HACK-001" and o["state"] == "CLAIMED", ok.stdout)
    clash = f.hack(1, "--json", "claim", "HACK-002", "--branch", f.branches[1], "--worktree", f.worktrees[1].as_posix(), allowed=None)
    c = j.loads(clash.stdout)
    expect(clash.returncode == 3 and c["ok"] is False and c["exit"] == 3 and c["result"] == "CONFLICT"
           and c["code"] == "overlap" and "overlaps HACK-001" in c["message"] and c["stderr"], clash.stdout)
    # The text a person or an agent reads is unchanged.
    text = f.claim(1, "HACK-002", allowed=None)
    expect(text.returncode == 3 and text.stderr.startswith("CONFLICT: HACK-002 overlaps HACK-001"), text.stderr)
    st = f.hack(1, "--json", "status")
    s = j.loads(st.stdout)
    tasks = {t["id"]: t for t in s["tasks"]}
    expect(tasks["HACK-001"]["state"] == "CLAIMED" and tasks["HACK-001"]["owner"] == "agent-1" and tasks["HACK-001"]["expired"] is False
           and tasks["HACK-002"]["state"] == "AVAILABLE" and tasks["HACK-002"]["owner"] is None, st.stdout)
    unknown = f.hack(0, "--json", "bogus", allowed=None)
    u = j.loads(unknown.stdout)
    expect(unknown.returncode == 2 and u["code"] == "unknown-command" and u["result"] == "ERROR", unknown.stdout)
    # Backslashes, quotes, tabs and control characters stay valid JSON with every awk (mawk, gawk, BSD). Windows: no
    # quote or control character in argv (the command line is re-parsed there).
    odd = 'bo\\g"us\t\x01x' if os.name != "nt" else 'bo\\gus'
    weird = f.hack(0, "--json", odd, allowed=None)
    w = j.loads(weird.stdout)
    expect(w["code"] == "unknown-command" and odd in w["message"], weird.stdout)
    # UAK_JSON=1 works for a script of its own too; a command's own --json (after the command) is left alone.
    env = {"UAK_AGENT": "agent-1", "UAK_JSON": "1"}
    g = r.run([r.bash, ".uak/bin/uak", "graph", "--file", ".uak/TASKS.md"], cwd=f.worktrees[0], env=env)
    expect(j.loads(g.stdout)["ok"] is True and any("HACK-001" in l for l in j.loads(g.stdout)["stdout"]), g.stdout)
    pace = r.run([r.bash, ".uak/bin/uak", "pace", "--json"], cwd=f.worktrees[0], env={"UAK_AGENT": "agent-1"}, allowed=None)
    expect('"stdout":' not in pace.stdout, pace.stdout)
    return {"codes": [c["code"], u["code"]]}


def registry_drives_help_and_dispatch(r):
    """One row in lib/commands.tsv is a command: help lists it and uak runs it. Nothing else to edit."""
    f = r.fixture("v511-registry", paths={"HACK-001": "src/a/"}, count=1)
    wt = f.worktrees[0]
    rows = [l.split("\t") for l in (wt / ".uak/bin/lib/commands.tsv").read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    help_text = f.hack(0, "help").stdout
    expect(all(row[5] in help_text for row in rows), "help misses a registry row")
    expect(len({row[0] for row in rows}) >= 50, "registry rows: %d" % len(rows))
    (wt / ".uak/bin/hello").write_text('#!/usr/bin/env bash\nprintf "HELLO %s\\n" "$*"\n', encoding="utf-8")
    with open(wt / ".uak/bin/lib/commands.tsv", "a", encoding="utf-8") as fh:
        fh.write("hello\texec\t-\thello\tuak_cli\thello [NAME]   says hello\n")
    expect("hello [NAME]   says hello" in f.hack(0, "help").stdout, "a new row reaches help")
    expect(f.hack(0, "hello", "ana").stdout.strip() == "HELLO ana", "a new row is dispatched")
    expect(f.hack(0, "hello", "--help").stdout.strip() == "hello [NAME]   says hello", "CMD --help prints its row")
    return {"rows": len(rows)}


def engine_is_split_and_finds_its_libraries(r):
    """uak is a dispatcher over one file per family, found from wherever uak is run; a missing one says how to fix it."""
    f = r.fixture("v511-split", paths={"HACK-001": "src/a/"}, count=1)
    wt = f.worktrees[0]
    uak = (wt / ".uak/bin/uak").read_text(encoding="utf-8")
    expect(len(uak.splitlines()) <= 300, "uak grew back to %d lines: put a command's code in its family file" % len(uak.splitlines()))
    for lib in ("core", "backlog", "tx", "claim", "done", "plan", "status", "wait", "lint", "config", "json"):
        expect((wt / ".uak/bin/lib" / (lib + ".sh")).is_file(), lib)
    (wt / "src/a").mkdir(parents=True)
    env = {"UAK_AGENT": "agent-1", "UAK_REMOTE": "origin", "UAK_NOW": "1000000"}
    rel = r.run([r.bash, "../../.uak/bin/uak", "status"], cwd=wt / "src/a", env=env)
    expect(rel.stdout.startswith("uak v"), rel.stdout)
    absolute = r.run([r.bash, (wt / ".uak/bin/uak").as_posix(), "version"], cwd=wt / "src/a", env=env)
    expect(absolute.stdout.strip() == (wt / ".uak/VERSION").read_text(encoding="utf-8").strip(), absolute.stdout)
    (wt / ".uak/bin/lib/plan.sh").unlink()
    broken = r.run([r.bash, ".uak/bin/uak", "status"], cwd=wt, env=env, allowed=None)
    expect(broken.returncode == 1 and "lib/plan.sh: reinstall the kit" in broken.stderr, broken.stdout + broken.stderr)
    return {"lines": len(uak.splitlines())}


def an_engine_in_another_folder_runs_whole(r):
    """Dogfooding: the kit's repo runs the engine of kit/ through 3-line shims in .uak/bin. Every library and script
    (graph, secret-scan) comes from the engine's folder, not from the checkout's .uak/bin."""
    t = r.scratch / "v511-shim"
    (t / ".uak/bin").mkdir(parents=True)
    r.g(t, "init", "-q", "-b", "main")
    import shutil
    shutil.copytree(r.package / ".uak", t / "engine/.uak", ignore=shutil.ignore_patterns("__pycache__", "tests"))
    (t / ".uak/bin/uak").write_text('#!/usr/bin/env bash\nexec bash "$(dirname "$0")/../../engine/.uak/bin/uak" "$@"\n', encoding="utf-8")
    (t / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    (t / ".uak/PROJECT.md").write_text("Mode: marathon\nTest-First: yes\n", encoding="utf-8")
    (t / ".uak/OWNERS.md").write_text("# Owners\n", encoding="utf-8")
    (t / ".github").mkdir()
    shutil.copy2(r.package / ".github/pull_request_template.md", t / ".github/pull_request_template.md")
    task = "## T-00%d · t%d\n\n- **Type:** docs\n- **Priority:** P1\n- **Depends on:** T-00%d\n- **Paths:** docs/%d.md\n- **Verify:** `true`\n\n"
    (t / ".uak/TASKS.md").write_text("# TASKS\n\n" + task % (1, 1, 2, 1) + task % (2, 2, 1, 2), encoding="utf-8")
    lint = r.run([r.bash, ".uak/bin/uak", "lint"], cwd=t, env={"UAK_AGENT": "a-1", "UAK_REMOTE": "none"}, allowed=None)
    expect(lint.returncode == 1 and "CYCLE" in lint.stderr and "LINT_FAILED" in lint.stdout, lint.stdout + lint.stderr)
    return {"lint": "cycle found through the engine's own graph"}


def a_human_reads_zero_events_not_blanks(r):
    """A human's next said "Events: /90 alert (total )": its file on claims has no counters."""
    f = r.fixture("v511-human", paths={"HACK-001": "src/a/"}, count=1)
    env = {"UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_REMOTE": "origin", "UAK_NOW": "1000000", "UAK_DEDUPE": "off"}
    r.run([r.bash, ".uak/bin/uak", "next"], cwd=f.worktrees[0], env=env)
    out = r.run([r.bash, ".uak/bin/uak", "next"], cwd=f.worktrees[0], env=env).stdout
    expect("Events: 0/" in out and "(total 0)" in out, out)
    return {"events": "0"}


def secret_scan_reads_every_file_in_one_pass(r):
    """The scan started about 20 processes per tracked file (git show, hash-object, a grep pipeline per rule): 8,244
    for the kit's own 374 files, 11 s on Linux and minutes on Git Bash, twice per merge. Now one pass per rule. And a
    key in a binary file is found: GNU grep 3.5+ sent "Binary file matches" to stderr, which the scan discarded."""
    from test_v592 import processes
    t = r.scratch / "v511-scan"
    t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    (t / ".uak/bin").mkdir(parents=True)
    shutil.copy2(r.package / ".uak/bin/secret-scan", t / ".uak/bin/secret-scan")
    for i in range(150):
        (t / ("f%03d.txt" % i)).write_text("line\n" * 5, encoding="utf-8")
    r.g(t, "add", "-A")
    clean = r.run([r.bash, ".uak/bin/secret-scan", "--tracked"], cwd=t)
    expect("SECRET_SCAN_PASS files=151" in clean.stdout, clean.stdout + clean.stderr)
    n, out = processes(r, t, [".uak/bin/secret-scan", "--tracked"], "")
    expect(out.returncode == 0 and n <= 60, "secret-scan of 151 files: %d processes" % n)
    (t / "font.bin").write_bytes(b"\x00\x01binary\nsk-" + b"G" * 25 + b"\n")
    (t / "f007.txt").write_text("a\nb\nAKIA" + "Z" * 16 + "\n", encoding="utf-8")
    r.g(t, "add", "-A")
    found = r.run([r.bash, ".uak/bin/secret-scan", "--tracked"], cwd=t, allowed=None)
    expect(found.returncode == 1 and "SECRET_FOUND: f007.txt:3 SEC_CLOUD_ACCESS" in found.stderr
           and "SECRET_FOUND: font.bin:2 SEC_OPENAI" in found.stderr and "findings=2" in found.stderr, found.stderr)
    staged = r.run([r.bash, ".uak/bin/secret-scan", "--staged"], cwd=t, allowed=None)
    expect(staged.returncode == 1 and "font.bin:2" in staged.stderr, staged.stderr)
    return {"processes": n}


def gate_runs_smoke_and_verify_with_the_callers_ssh_env(r):
    """uak exports GIT_SSH_COMMAND (BatchMode, timeouts, ControlMaster) for its own git calls when the remote is SSH.
    The merge gate ran the project's smoke and Verify as children, so they inherited it. Found by dogfooding: the
    gate of UAK-009 failed test_v5 latency_paths ("https remotes are left alone") on an SSH remote."""
    import test_review_merge as rm
    from test_v43 import push_main
    f = rm.fixture(r, "v511-ssh-env", count=2)
    check = ('if [ -n "${GIT_SSH_COMMAND+x}" ] || [ -n "${GIT_SSH+x}" ]; then echo "the gate leaked GIT_SSH_COMMAND=${GIT_SSH_COMMAND-}"; exit 1; fi\n'
             # A uak this smoke starts must save its own caller's settings: none of uak's bookkeeping reaches it.
             'if [ -n "${UAK_CALLER_SSH_SAVED+x}" ]; then echo "the gate leaked UAK_CALLER_SSH_SAVED"; exit 1; fi\n')
    push_main(f, {".uak/bin/smoke-project": "#!/usr/bin/env bash\n" + check}, "Product smoke: the caller's SSH environment")
    for w in f.worktrees:
        r.g(w, "merge", "--no-edit", "origin/main")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f); rm.approve(f, "HACK-001", tip)
    # An SSH-looking remote that git maps back to the local bare repository: uak turns its SSH settings on, no
    # network is touched.
    fake = "git@example.invalid:team/product.git"
    cfg = r.scratch / "v511-ssh-env.gitconfig"
    cfg.write_text('[user]\n\tname = fixture\n\temail = fixture@example.invalid\n[url "%s"]\n\tinsteadOf = %s\n'
                   % (f.remote.as_posix(), fake), encoding="utf-8")
    r.g(f.clones[0], "remote", "set-url", "origin", fake)
    env = {"UAK_AGENT": "agent-1", "UAK_HUMAN": "", "UAK_NOW": "1000030", "UAK_REVIEW_MODE": "claims",
           "GIT_CONFIG_GLOBAL": cfg.as_posix()}
    # The caller here has no SSH settings of its own, whatever the machine running the suite has (PuTTY's GIT_SSH on
    # Windows, a GIT_SSH_COMMAND): Runner.env copies os.environ, so they are unset in the command itself.
    out = r.run([r.bash, "-c", "unset GIT_SSH_COMMAND GIT_SSH UAK_CALLER_SSH_SAVED UAK_CALLER_SSH_HAD UAK_CALLER_GIT_SSH_COMMAND "
                 "UAK_CALLER_GIT_SSH; exec bash .uak/bin/uak merge HACK-001"], cwd=f.worktrees[0], env=env, allowed=None)
    text = out.stdout + out.stderr
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout,
           "the gate's smoke sees the caller's SSH environment: expected: INTEGRATED, got: " + text[-600:])
    return {"merged": True}


def merge_runs_the_main_checkouts_engine_not_the_branchs(r):
    """`uak merge` run from a task worktree ran that branch's engine: the gate a branch must pass was the branch's own
    code, so a branch could rewrite its gate and merge itself. Found by dogfooding (UAK-012): the kit's shims run the
    checkout's kit/, so a merge from a worktree ran the engine under review. From a linked worktree, merge runs the
    main checkout's engine; from the main checkout nothing changes."""
    f = r.fixture("v511-merge-engine", paths={"HACK-001": "src/a/"}, count=1)
    wt, clone = f.worktrees[0], f.clones[0]
    lib = wt / ".uak/bin/lib/review-merge.sh"
    lib.write_text(lib.read_text(encoding="utf-8") + "\nmerge_run() { echo BRANCH_ENGINE; exit 7; }\n", encoding="utf-8")
    env = {"UAK_AGENT": "agent-1", "UAK_HUMAN": "", "UAK_REMOTE": "origin", "UAK_NOW": "1000000"}
    note = "the gate runs the main checkout's engine"
    for args in (["merge", "HACK-001"], ["--json", "merge", "HACK-001"]):
        out = r.run([r.bash, ".uak/bin/uak", *args], cwd=wt, env=env, allowed=None)
        text = out.stdout + out.stderr
        expect("BRANCH_ENGINE" not in text and out.returncode != 7,
               "uak %s from a worktree ran the branch's own engine: %s" % (" ".join(args), text[-600:]))
        expect(note in out.stderr, "uak %s: no note that the main engine runs: %s" % (" ".join(args), text[-600:]))
    # The branch's other commands still run its own engine: only the gate moves.
    status = r.run([r.bash, ".uak/bin/uak", "status"], cwd=wt, env=env, allowed=None)
    expect(note not in status.stderr, status.stderr)
    main = r.run([r.bash, ".uak/bin/uak", "merge", "HACK-001"], cwd=clone, env=env, allowed=None)
    expect(note not in main.stderr and "BRANCH_ENGINE" not in main.stdout, main.stdout + main.stderr)
    return {"engine": "main checkout"}


def comsub_case_misparses(text):
    """Lines of the `$( … )` that bash 3.2 cuts short at a bare case pattern `pat)`. bash 3.2 reads a command
    substitution by counting parens (parse_matched_pair), with no idea of `case`, inside double quotes too. This walks
    the script the same way: quotes, $'…', escapes, backticks, comments and heredocs are skipped like the shell
    does; each substitution's own unquoted words must open and close their case (nested substitutions apart)."""
    import re
    n, found = len(text), []
    word = re.compile(r"(?<![\w$#{}/.:=-])(case|esac)(?![\w-])")
    heredoc = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
    pending = []

    def skip_heredocs(i):
        # i is just past a newline: skip the bodies of the heredocs opened on the line before.
        while pending:
            strip, delim = pending.pop(0)
            while i < n:
                end = text.find("\n", i)
                end = n if end < 0 else end
                line = text[i:end]
                i = end + 1
                if (line.lstrip("\t") if strip else line) == delim:
                    break
        return i

    def single(i):  # i at the opening quote
        k = text.find("'", i + 1)
        return n if k < 0 else k + 1

    def ansi(i):  # i at the quote of $'…'
        k = i + 1
        while k < n and text[k] != "'":
            k += 2 if text[k] == "\\" else 1
        return k + 1

    def backtick(i):
        k = i + 1
        while k < n and text[k] != "`":
            k += 2 if text[k] == "\\" else 1
        return k + 1

    def dq(i):  # i at the opening quote; returns past the closing one
        k = i + 1
        while k < n and text[k] != '"':
            if text[k] == "\\":
                k += 2
            elif text.startswith("$((", k):
                k = code(k + 3, arith=True)
            elif text.startswith("$(", k):
                k = comsub(k)
            elif text[k] == "`":
                k = backtick(k)
            else:
                k += 1
        return k + 1

    def comsub(i):  # i at `$(`; returns past bash 3.2's matching `)`
        out = []
        k = code(i + 2, out=out)
        if word.findall("".join(out)).count("case") > word.findall("".join(out)).count("esac"):
            found.append(text.count("\n", 0, i) + 1)
        return k

    def code(k, out=None, arith=False, top=False):
        # $(( … )) is entered past both of its parens and ends past both: bash 3.2 counts them as two (UAK-015).
        depth = 2 if arith else 1
        while k < n:
            c = text[k]
            if c == "\\":
                k += 2
                continue
            if c == "\n":
                if out is not None:
                    out.append(c)
                k = skip_heredocs(k + 1)
                continue
            if c == "'" and not arith:
                k = single(k); out is not None and out.append(" "); continue
            if text.startswith("$'", k):
                k = ansi(k + 1); out is not None and out.append(" "); continue
            if c == '"':
                k = dq(k); out is not None and out.append(" "); continue
            if c == "`":
                k = backtick(k); out is not None and out.append(" "); continue
            if c == "#" and not arith and (k == 0 or text[k - 1] in " \t\n;|&("):
                e = text.find("\n", k)
                k = n if e < 0 else e
                continue
            if text.startswith("$((", k):
                k = code(k + 3, arith=True); continue
            if text.startswith("$(", k):
                k = comsub(k); out is not None and out.append(" "); continue
            m = heredoc.match(text, k) if not arith and c == "<" and not text.startswith("<<<", k) else None
            if m:
                pending.append((m.group(1) == "-", m.group(3)))
                k = m.end(); continue
            if not top:
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                    if depth == 0:
                        return k + 1
            if out is not None:
                out.append(c)
            k += 1
        return k

    code(0, top=True)
    return found


def the_dispatcher_parses_on_bash_3_2(r):
    """bash 3.2 (macOS) reads `$( … )` by counting parens: `case $x in pat) …;; esac` inside one ends the
    substitution at `pat)`, a syntax error for the whole file ("line 27: syntax error near unexpected token `;;'", CI
    on 7b37537). bash 5 parses it, so Linux never saw it. The engine writes such patterns as `(pat)`."""
    # The checker itself, on what bash 3.2 cuts (bare, in double quotes, after a heredoc, after $'…', after a comment)
    # and on what it reads whole. kit-r1 (UAK-013): a "$(case … pat) …)" in doctor went unseen by a first version.
    samples = {
        'x=$(case $a in b) echo 1;; esac)\n': [1],
        'y=$(case $a in (b) echo 1;; esac)\n': [],
        'v="$(case $x in a) echo 1;; esac)"\n': [1],
        'w="$(case " $l " in *" uv "*) printf x;; esac)"\n': [1],
        'z=$(echo "(a)" \'(\' # )\n)\n': [],
        'cat <<EOF\nit\'s (\nEOF\nq=$(case $a in b) :;; esac)\n': [4],
        "s=$'it\\'s'; q=$(case $a in b) :;; esac)\n": [1],
        'q=$(# it\'s\ncase $a in b) :;; esac)\n': [1],
        'q=$(echo lower-case ${x#case})\n': [],
        'q=$((1 + (2)))\n': [],
        # $(( … )) opens two parens and closes two: a checker that took one ")" for it ended the outer $( … ) one
        # paren early (UAK-015): a false positive on the first, a false negative on the second.
        'y=$(case $a in (b) echo $((1));; esac)\n': [],
        'y=$(echo $((1+1)); case $a in b) :;; esac)\n': [1],
    }
    for sample, want in samples.items():
        expect(comsub_case_misparses(sample) == want, "the checker itself on %r: %s" % (sample, comsub_case_misparses(sample)))
    bad, checked = {}, 0
    for f in sorted((r.package / ".uak/bin").rglob("*")):
        if not f.is_file() or f.suffix not in ("", ".sh"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if f.suffix == "" and not text.startswith("#!"):
            continue
        checked += 1
        lines = comsub_case_misparses(text)
        if lines:
            bad[f.relative_to(r.package).as_posix()] = lines
    expect(checked > 20 and not bad, "a case pattern without its ( inside $( … ): bash 3.2 fails to parse it: " + str(bad))
    return {"checked": checked}


TESTS = [config_reader_reads_every_form, json_envelope_reports_results_and_codes, registry_drives_help_and_dispatch,
         engine_is_split_and_finds_its_libraries, an_engine_in_another_folder_runs_whole, a_human_reads_zero_events_not_blanks,
         secret_scan_reads_every_file_in_one_pass, gate_runs_smoke_and_verify_with_the_callers_ssh_env,
         merge_runs_the_main_checkouts_engine_not_the_branchs, the_dispatcher_parses_on_bash_3_2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v511-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("V511_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
