#!/usr/bin/env python3
"""UAK-008: the scope check of `uak merge` (rm_gate_scope) is one pass over the diff. It ran normalize_paths and one
overlaps per reserved path for every changed file, about 8 processes a file: a 200-file branch paid well over a
thousand of them, 20-50 ms each on Git Bash. A harness sources the engine's libraries and calls rm_gate_scope on a
candidate repository with the changes staged, as `uak merge` leaves its candidate: only the scope check is counted.
Processes are counted as test_claims_perf.py counts them (a traced shim per program, distinct $BASHPID); bash 3.2 has
no $BASHPID, so there the results are checked and the counts are not. Real Git."""
import argparse
import concurrent.futures
import os
import re
import tempfile
import time
from pathlib import Path

from test_hack import Failure, Runner, expect, resolve_binary
from test_claims_perf import shims, unique

# The whole check for a 200-file branch, the harness's own bash included. Independent of the file count.
LIMIT_ACCEPT = 25
# A refusal also names the file's owner (one normalize_paths per other task) and checks for generated files.
LIMIT_REFUSE = 45

HARNESS = r'''# $1 the engine's .uak/bin, $2 the candidate (changes staged over $3), $3 the base SHA, $4 the claims tree,
# $5 TASKS.md, $6 the merge temp dir (coord-source = PROJECT.md). Prints SCOPE OK or SCOPE REFUSED: the reason.
UAK_BIN=$1
for l in lib/core.sh uak-coordination lib/config.sh lib/backlog.sh lib/review-merge.sh; do . "$UAK_BIN/$l" || exit 9; done
RM_BUILD=$2 RM_BASE_TIP=$3 TX=$4 BACKLOG=$5 TXROOT=$6 ID=HACK-001 BASE=main RECORD=$4/tasks/HACK-001.md
if rm_gate_scope; then printf 'SCOPE OK\n'; else printf 'SCOPE REFUSED: %s\n' "$RM_REASON"; fi
'''

# UAK-148: the same, then the gate's check of a generated file against its command on the merged result. ROOT is the
# candidate so a refusal's log goes nowhere else; the lines after the verdict are the Generated: list the scope pass read.
GEN_HARNESS = HARNESS.replace("RM_BUILD=$2", "ROOT=$2 RM_BUILD=$2").replace(
    "if rm_gate_scope; then printf 'SCOPE OK\\n'; else",
    "if rm_gate_scope && git -C \"$RM_BUILD\" -c user.name=f -c user.email=f@e.test commit -q -m merge && rm_generated_check; then printf 'SCOPE OK\\n'; else") + (
    "[ ! -s \"$TXROOT/merge-generated-list\" ] || sed 's/^/LIST /' \"$TXROOT/merge-generated-list\"\n")

BACKLOG = ("# Tasks\n\n## HACK-001 · The task under merge\n- **Paths:** `src/app/`, `docs/canción.md`\n\n"
           "## HACK-002 · Another task\n- **Paths:** `src/other/`\n")
BASE_FILES = {"README.md": "fixture\n", "src/app/main.txt": "main\n", "src/other/x.txt": "HACK-002\n",
              "e2e/old.spec.ts": "old\n", "docs/canción.md": "letra\n"}
NEW_OUTSIDE = ("New file outside Paths: %s. Move it into the task's Paths, or a human adds its dir to Additive-Paths in "
               "PROJECT.md (new files there need no reservation)")
EDIT_OUTSIDE = ("Edits a file outside Paths: %s%s. Revert that file on the branch (git checkout origin/main -- %s), "
                "or the human merges the PR")


class Unbuildable(Exception):
    """Git for Windows refuses a name in the index ("error: Invalid path"): a newline or a carriage return."""


def bash_major(r):
    """The major version of the bash the tests run (r.bash). test_v592's runs a bare `bash` from PATH, which on Windows
    is not Git Bash: there it read 0 and nothing was counted (kit-r1, UAK-008)."""
    out = r.run([r.bash, "-c", "echo ${BASH_VERSINFO[0]}"], cwd=r.scratch, allowed=None).stdout.strip()
    return int(out) if out.isdigit() else 0


def processes(r, cwd, args):
    """Distinct processes of one call, as test_claims_perf counts them (a traced shim per program, distinct $BASHPID),
    called only when this file's bash_major(r) is 4 or more."""
    trace, stdin = unique(r, "gate-trace-"), unique(r, "gate-in-")
    script = ('exec 9>>"$1" < "$3"; PATH="$2:$PATH"; export PATH; shift 3; '
              "exec env BASH_XTRACEFD=9 'PS4=+$BASHPID ' SHELLOPTS=xtrace \"$@\"")
    out = r.run([r.bash, "-c", script, "_", trace.as_posix(), shims(r).as_posix(), stdin.as_posix(), "bash"] + args,
                cwd=cwd, allowed=None)
    pids = set(re.findall(r"(?m)^\++([0-9]+) ", trace.read_text(encoding="utf-8", errors="replace")))
    expect(pids, "the trace counted nothing: " + out.stderr[-300:])
    return len(pids), out


def gen_harness(r):
    h = r.scratch / "gate-generated-harness.sh"
    if not h.exists():
        h.write_text(GEN_HARNESS, encoding="utf-8", newline="\n")
    return h


def harness(r):
    h = r.scratch / "gate-scope-harness.sh"
    if not h.exists():
        h.write_text(HARNESS, encoding="utf-8", newline="\n")
    return h


def scene(r, name, files=None, index=None, base=None, gen=False):
    """A candidate: BASE_FILES committed, then `files` written and staged, and `index` staged without the working tree
    (names a file system cannot hold side by side: SRC/ next to src/, a newline). Returns (dir, args for the harness)."""
    d = r.scratch / name
    repo, tx, tmp = d / "repo", d / "tx", d / "tmp"
    for p in (repo, tx / "tasks", tmp):
        p.mkdir(parents=True)
    (tx / "tasks/HACK-001.md").write_text("ID: HACK-001\nState: REVIEW\nPaths: src/app/, docs/canción.md\n", encoding="utf-8")
    (tx / "tasks/HACK-002.md").write_text("ID: HACK-002\nState: CLAIMED\nPaths: src/other/\n", encoding="utf-8")
    (d / "TASKS.md").write_text(BACKLOG, encoding="utf-8")
    (tmp / "coord-source").write_text("# Project\nAdditive-Paths: e2e/\n", encoding="utf-8")
    def put(rel, text):
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    r.g(repo, "init", "-q")
    for rel, text in dict(BASE_FILES, **(base or {})).items():
        put(rel, text)
    r.g(repo, "add", "-A")
    r.g(repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.test", "commit", "-q", "-m", "base")
    base = r.g(repo, "rev-parse", "HEAD").stdout.strip()
    for rel, text in (files or {}).items():
        put(rel, text)
    if files:
        r.g(repo, "add", "-A")
    for i, (rel, text) in enumerate((index or {}).items()):
        blob = d / ("blob-%d" % i)
        blob.write_text(text, encoding="utf-8", newline="\n")
        sha = r.g(repo, "hash-object", "-w", blob.as_posix()).stdout.strip()
        staged = r.run([r.git, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (sha, rel)], cwd=repo, allowed=None)
        # Only on Windows, only for this refusal: Linux and macOS build every case.
        if staged.returncode and os.name == "nt" and "Invalid path" in staged.stderr:
            raise Unbuildable(rel)
        if staged.returncode:
            raise Failure("git update-index %r failed: %s" % (rel, staged.stderr[-300:]))
    bindir = r.package / ".uak" / "bin"
    return d, [(gen_harness(r) if gen else harness(r)).as_posix(), bindir.as_posix(), repo.as_posix(), base, tx.as_posix(),
               (d / "TASKS.md").as_posix(), tmp.as_posix()]


def scope(r, d, args, count=False):
    """rm_gate_scope's verdict, and the processes it started when count (None on bash 3.2)."""
    if count and bash_major(r) >= 4:
        n, out = processes(r, d, args)
    else:
        n, out = None, r.run([r.bash] + args, cwd=d, allowed=None)
    text = out.stdout.strip()
    expect(out.returncode == 0 and text.startswith("SCOPE "), "the harness ran rm_gate_scope: " + (out.stdout + out.stderr)[-600:])
    return n, text


def many(n):
    return {"src/app/f%03d.txt" % i: "file %d\n" % i for i in range(n)}


def scope_check_is_one_pass_for_200_files(r):
    """200 changed files in Paths, a new empty package marker and a new file under Additive-Paths: accepted. The same
    200 plus a new file outside Paths, last in diff order so every file is checked before it: refused. The process
    count is small and the same for 20 files as for 200."""
    ok_files = dict(many(200), **{"pkg/__init__.py": "", "e2e/new.spec.ts": "test\n"})
    d, args = scene(r, "one-pass-200", ok_files)
    n200, verdict = scope(r, d, args, count=True)
    expect(verdict == "SCOPE OK", "200 files in Paths: expected: SCOPE OK, got: " + verdict)
    d, args = scene(r, "one-pass-20", dict(many(20), **{"pkg/__init__.py": "", "e2e/new.spec.ts": "test\n"}))
    n20, verdict = scope(r, d, args, count=True)
    expect(verdict == "SCOPE OK", "20 files in Paths: expected: SCOPE OK, got: " + verdict)
    d, args = scene(r, "one-pass-200-out", dict(many(200), **{"zz/notes.md": "notes\n"}))
    nout, verdict = scope(r, d, args, count=True)
    want = "SCOPE REFUSED: " + NEW_OUTSIDE % "zz/notes.md"
    expect(verdict == want, "a new file outside Paths after 200 in Paths: expected: %r, got: %r" % (want, verdict))
    if n200 is None:
        return "results checked; processes not counted on bash %d (no $BASHPID); Linux and Windows count" % bash_major(r)
    expect(n200 <= LIMIT_ACCEPT, "scope check of 200 files: expected: at most %d processes, got: %d (20 files: %d)" % (LIMIT_ACCEPT, n200, n20))
    expect(n200 == n20, "scope check: expected: the same processes for 200 files as for 20, got: %d and %d" % (n200, n20))
    expect(nout <= LIMIT_REFUSE, "refusal after 200 files: expected: at most %d processes, got: %d" % (LIMIT_REFUSE, nout))
    return "accept: %d processes for 200 files, %d for 20; refusal: %d" % (n200, n20, nout)


# (name, files written and staged, files staged without the working tree, the expected verdict). The texts are the
# ones the per-file loop printed before UAK-008, captured from it.
CASES = [
    ("new-accented", {"src/app/a.txt": "a\n", "notas/José Pérez.md": "nota\n"}, None,
     "SCOPE REFUSED: " + NEW_OUTSIDE % "notas/José Pérez.md"),
    ("edit-unowned", {"src/app/a.txt": "a\n", "README.md": "edited\n"}, None,
     "SCOPE REFUSED: " + EDIT_OUTSIDE % ("README.md", "", "README.md")),
    ("edit-owned", {"src/app/a.txt": "a\n", "src/other/x.txt": "edited by HACK-001\n"}, None,
     "SCOPE REFUSED: " + EDIT_OUTSIDE % ("src/other/x.txt", " (Paths of HACK-002)", "src/other/x.txt")),
    ("new-owned", {"src/app/a.txt": "a\n", "src/other/new.txt": "carried\n"}, None,
     "SCOPE REFUSED: New file outside Paths: src/other/new.txt belongs to HACK-002 (its Paths), carried by a branch "
     "merge. Merge HACK-002 first, then git merge --no-edit origin/main here and uak merge HACK-001 again"),
    ("edit-additive", {"src/app/a.txt": "a\n", "e2e/old.spec.ts": "edited\n"}, None,
     "SCOPE REFUSED: " + EDIT_OUTSIDE % ("e2e/old.spec.ts", "", "e2e/old.spec.ts")),
    ("generated", {"src/app/a.txt": "a\n", "build/out.js": "bundle\n"}, None,
     "SCOPE REFUSED: Generated file committed: build/out.js. Remove it from the branch (git rm -r --cached "
     "build/out.js), add the pattern to .gitignore, push, and ask for review again"),
    ("shared", {"src/app/a.txt": "a\n", "db/migrations/001.sql": "create table t (id int);\n"}, None,
     "SCOPE REFUSED: Shared resource/CI needs a human: db/migrations/001.sql"),
    ("fixture-not-shared", {"src/app/a.txt": "a\n", "tests/fixtures/migrations/seed.sql": "insert;\n"}, None,
     "SCOPE REFUSED: " + NEW_OUTSIDE % "tests/fixtures/migrations/seed.sql"),
    ("first-in-diff-order", {"src/app/a.txt": "a\n", "notas/b.md": "b\n", "README.md": "edited\n"}, None,
     "SCOPE REFUSED: " + EDIT_OUTSIDE % ("README.md", "", "README.md")),
    ("accepted", {"src/app/a.txt": "a\n", "pkg/__init__.py": "", "e2e/new.spec.ts": "t\n"},
     {"SRC/APP/Upper.txt": "case\n", "docs/CANCIÓN.md": "fold\n"}, "SCOPE OK"),
    ("newline", {"src/app/a.txt": "a\n"}, {"src/app/two\nlines.txt": "x\n"},
     "SCOPE REFUSED: Path with newline not supported"),
    ("carriage-return", {"src/app/a.txt": "a\n"}, {"src/app/cr\r.txt": "x\n"},
     "SCOPE REFUSED: Path with newline not supported"),
]


def the_same_reasons_for_new_and_edited_files_outside_paths(r):
    """New and edited files outside Paths, an owned file, Additive-Paths, a generated file, a shared resource, a
    fixture, accents and a space, case folding, a newline: the verdicts and reason texts of the per-file loop."""
    def one(case):
        name, files, index, want = case
        try:
            d, args = scene(r, "reasons-" + name, files, index)
        except Unbuildable:
            return name, want, None
        _, verdict = scope(r, d, args)
        return name, want, verdict
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, CASES))
    wrong = ["%s: expected: %r, got: %r" % (name, want, got) for name, want, got in results if got is not None and got != want]
    expect(not wrong, "\n".join(wrong))
    skipped = [name for name, _, got in results if got is None]
    note = "%d cases" % (len(results) - len(skipped))
    if skipped:
        note += "; skipped %s: Git for Windows refuses the name in the index (Invalid path)" % ", ".join(skipped)
    return note


def a_file_name_is_not_a_paths_pattern(r):
    """A changed file's name was read as a Paths pattern: src/app,x.txt split at its comma into src/app and x.txt, and
    src/app[1].txt cut at its glob to src/: both passed as inside src/app/. A name is compared as it is."""
    out = []
    for name, rel in (("comma", "src/app,x.txt"), ("glob", "src/app[1].txt")):
        d, args = scene(r, "name-" + name, {"src/app/a.txt": "a\n", rel: "outside\n"})
        _, verdict = scope(r, d, args)
        want = "SCOPE REFUSED: " + NEW_OUTSIDE % rel
        expect(verdict == want, "%s: expected: %r, got: %r" % (rel, want, verdict))
        out.append(rel)
    return "refused: " + ", ".join(out)


# UAK-148. The command writes the file the generator would; `=` inside it must survive the one split.
GEN = "gen/known.txt"
GEN_CMD = "printf 'new=1\\n' > gen/known.txt"
GEN_TEXT = "new=1\n"
GEN_BASE = {GEN: "old\n"}


def project(*lines):
    return {".uak/PROJECT.md": "# Project\nAdditive-Paths: e2e/\n" + "".join(l + "\n" for l in lines)}


def generated(r, name, lines, files, index=None, base=None, after=None):
    d, args = scene(r, name, files, index, dict(GEN_BASE, **dict(project(*lines), **(base or {}))), gen=True)
    if after:
        after(d / "repo")
    out = r.run([r.bash] + args, cwd=d, allowed=None)
    text = out.stdout.strip().splitlines()
    expect(out.returncode == 0 and text and text[0].startswith("SCOPE "), "the harness ran: " + (out.stdout + out.stderr)[-600:])
    return text[0], [l[5:] for l in text[1:] if l.startswith("LIST ")]


def generated_file_is_not_out_of_scope(r):
    """known-files.txt regenerated by every task (v6.8, 21 tasks): with the key on the base, a changed generated file
    outside Paths is accepted when the command reproduces it, a file that is not generated still is not, and the
    `Generated:` parser takes the first `=` only, tolerates bold and backticks, and drops directories, globs and a missing
    command."""
    key = "Generated: %s = %s" % (GEN, GEN_CMD)
    verdict, listed = generated(r, "gen-ok", [key], {"src/app/a.txt": "a\n", GEN: GEN_TEXT})
    expect(verdict == "SCOPE OK", "a generated file the command reproduces: expected: SCOPE OK, got: " + verdict)
    expect(listed == ["%s\t%s" % (GEN, GEN_CMD)], "the list read from the base: " + repr(listed))
    verdict, _ = generated(r, "gen-other", [key], {"src/app/a.txt": "a\n", GEN: GEN_TEXT, "README.md": "edited\n"})
    want = "SCOPE REFUSED: " + EDIT_OUTSIDE % ("README.md", "", "README.md")
    expect(verdict == want, "another file outside Paths: expected: %r, got: %r" % (want, verdict))
    verdict, _ = generated(r, "gen-bold", ["- **Generated:** `%s` = `%s`" % (GEN, GEN_CMD)], {"src/app/a.txt": "a\\n", GEN: GEN_TEXT})
    expect(verdict == "SCOPE OK", "bold and backticks: expected: SCOPE OK, got: " + verdict)
    sample = r.scratch / "generated-lines.md"
    sample.write_text("\n".join([key, "Generated: gen/ = x", "Generated: gen/*.txt = x", "Generated: a.txt =", "Generated: ../a = x",
                                 "Generated: /a = x", "Generated: no equals", "Generated: b.txt = a=b; c"]) + "\n", encoding="utf-8", newline="\n")
    parsed = r.run([r.bash, "-c", ". '%s'; uak_generated_list < '%s'" % ((r.package / ".uak/bin/lib/config.sh").as_posix(), sample.as_posix())],
                   cwd=r.scratch, allowed=None)
    expect(parsed.stdout.splitlines() == ["%s\t%s" % (GEN, GEN_CMD), "b.txt\ta=b; c"], "parser: " + repr(parsed.stdout))
    return "accepted; parser: first = splits, directories, globs and empty commands dropped"


def gate_refuses_a_generated_file_that_differs(r):
    """The gate does not trust the content: a stale file, a command that fails, one that is missing, and one that changes
    another tracked file each refuse the merge with a reason that names the file and the command."""
    cases = [
        ("stale", GEN_CMD, {GEN: "stale\n"}, "Generated file %s differs from what its command produces (%s)" % (GEN, GEN_CMD)),
        ("fails", "exit 3", {GEN: GEN_TEXT}, "Generated file %s: its command failed or is missing (exit 3)" % GEN),
        ("missing", "uak148-no-such-generator", {GEN: GEN_TEXT},
         "Generated file %s: its command failed or is missing (uak148-no-such-generator)" % GEN),
        ("others", "printf 'x\\n' > README.md; " + GEN_CMD, {GEN: GEN_TEXT},
         "Generated file %s: its command (printf 'x\\n' > README.md; %s) changed other files too: README.md" % (GEN, GEN_CMD)),
    ]
    for name, cmd, files, want in cases:
        verdict, _ = generated(r, "gen-bad-" + name, ["Generated: %s = %s" % (GEN, cmd)], dict(files, **{"src/app/a.txt": "a\n"}))
        expect(verdict.startswith("SCOPE REFUSED: " + want), "%s: expected: %r, got: %r" % (name, want, verdict))
    return "refused: " + ", ".join(c[0] for c in cases)


def generated_never_releases_a_human_file(r):
    """A generated path that is a lock file, a migration, a workflow, a hook, the project file or one of the gate's own
    files stays the human's, and so does a symlink."""
    human = {"package-lock.json": "{}\n", "db/migrations/001.sql": "create table t (id int);\n",
             ".github/workflows/ci.yml": "on: push\n", ".githooks/pre-commit": "#!/bin/sh\n", ".uak/bin/lib/x.sh": "x\n",
             ".uak/PROJECT.md": "# Project\nedited\n"}
    def one(item):
        rel, text = item
        base = dict(GEN_BASE, **{rel: "old\n"})
        base.update({".uak/PROJECT.md": "# Project\nGenerated: %s = printf 'x' > %s\n" % (rel, rel)} if rel == ".uak/PROJECT.md" else project("Generated: %s = true" % rel))
        d, args = scene(r, "gen-human-" + rel.replace("/", "-").replace(".", "_"), {"src/app/a.txt": "a\n", rel: text}, None, base, gen=True)
        return rel, r.run([r.bash] + args, cwd=d, allowed=None).stdout.splitlines()[0]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one, human.items()))
    wrong = ["%s: got %r" % (rel, got) for rel, got in results if got != "SCOPE REFUSED: Shared resource/CI needs a human: " + rel]
    expect(not wrong, "expected the human's file to stay the human's:\n" + "\n".join(wrong))
    return "kept for the human: " + ", ".join(human)


def generated_key_is_read_from_the_base(r):
    """A branch that adds the key, or rewrites its command, gains nothing in the same merge: the list is the base's."""
    key = "Generated: %s = %s" % (GEN, GEN_CMD)
    edited = {"src/app/a.txt": "a\n", GEN: "forged\n", ".uak/PROJECT.md": "# Project\n" + key + "\n"}
    verdict, listed = generated(r, "gen-branch-adds", [], edited)
    expect(verdict == "SCOPE REFUSED: Shared resource/CI needs a human: .uak/PROJECT.md" and listed == [], "a key added by the branch: %r %r" % (verdict, listed))
    base_key = "Generated: %s = %s" % (GEN, GEN_CMD)
    forged = dict(edited, **{".uak/PROJECT.md": "# Project\nGenerated: %s = true\n" % GEN})
    verdict, listed = generated(r, "gen-branch-rewrites", [base_key], forged)
    expect(verdict.startswith("SCOPE REFUSED: Shared resource/CI needs a human") and listed == ["%s\t%s" % (GEN, GEN_CMD)],
           "a command rewritten by the branch: %r %r" % (verdict, listed))
    return "the list is the base's: nothing from the branch's PROJECT.md"


def no_key_no_change(r):
    """Without a usable `Generated:` line the verdicts are today's: the file is an edit outside Paths."""
    want = "SCOPE REFUSED: " + EDIT_OUTSIDE % (GEN, "", GEN)
    for name, lines in (("none", []), ("dir", ["Generated: gen/ = " + GEN_CMD]), ("glob", ["Generated: gen/*.txt = " + GEN_CMD]),
                        ("nocmd", ["Generated: " + GEN + " ="]), ("prose", ["Generated files are rebuilt by a script"])):
        verdict, listed = generated(r, "gen-none-" + name, lines, {"src/app/a.txt": "a\n", GEN: GEN_TEXT})
        expect(verdict == want and listed == [], "%s: expected: %r, got: %r %r" % (name, want, verdict, listed))
    return "no key, a directory, a glob, no command, prose"


def generated_file_is_checked_against_the_merge_commit(r):
    """D1: a generator that reads history (as kit_hashes.py does: git rev-list HEAD) must see the task's commits. A branch
    of two commits that each change a file, merged with --no-ff --no-commit over the base as the gate does: the file
    regenerated at the branch tip passes, one regenerated one commit too early is refused."""
    script = "for c in $(git rev-list HEAD); do git rev-parse \"$c:src/app/main.txt\" 2>/dev/null; done | sort -u > gen/known.txt\n"
    base = {"gen/history.sh": script, GEN: "stale\n"}
    ident = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.test"]
    out = []
    for name, early in (("tip", False), ("early", True)):
        d, args = scene(r, "gen-history-" + name, None, None, dict(base, **project("Generated: %s = bash gen/history.sh" % GEN)), gen=True)
        repo, sha = d / "repo", args[3]
        r.g(repo, "checkout", "-q", "-b", "br")
        for i, text in enumerate(("one\n", "two\n")):
            (repo / "src/app/main.txt").write_text(text, encoding="utf-8", newline="\n")
            r.g(repo, "add", "-A")
            r.g(repo, *ident, "commit", "-q", "-m", "c%d" % i)
            if early == (i == 0) :
                r.run([r.bash, "gen/history.sh"], cwd=repo)
                r.g(repo, "add", "-A")
                r.g(repo, *ident, "commit", "-q", "-m", "regenerated")
        r.g(repo, "checkout", "-q", "--detach", sha)
        r.g(repo, *ident, "merge", "-q", "--no-ff", "--no-commit", "br")
        res = r.run([r.bash] + args, cwd=d, allowed=None).stdout.strip().splitlines()[0]
        out.append(res)
        if early:
            expect(res.startswith("SCOPE REFUSED: Generated file %s differs from what its command produces" % GEN), "regenerated early: " + res)
        else:
            expect(res == "SCOPE OK", "regenerated at the branch tip: expected: SCOPE OK, got: " + res)
    return "tip passes, one commit early is refused"


def a_deletion_a_variant_a_mode_change_or_a_duplicate_is_the_humans(r):
    """D2 and D3: the path is compared exactly (GEN/Known.txt and a canción/CANCIÓN pair are other files), a deleted or
    chmod +x generated file is not released, and a PATH listed twice is not generated. The command that leaves an
    untracked file refuses the merge naming it."""
    key = "Generated: %s = %s" % (GEN, GEN_CMD)
    edit = "SCOPE REFUSED: " + EDIT_OUTSIDE % (GEN, "", GEN)
    def mode(repo):
        r.g(repo, "update-index", "--chmod=+x", GEN)
    def delete(repo):
        r.g(repo, "rm", "-q", "-f", GEN)
    keep = {"gen/keep.txt": "keep\n"}
    cases = [
        ("mode", [key], {"src/app/a.txt": "a\n", GEN: GEN_TEXT}, None, None, mode, edit),
        ("deleted", [key], {"src/app/a.txt": "a\n"}, None, keep, delete, edit),
        ("dup", [key, "Generated: %s = true" % GEN], {"src/app/a.txt": "a\n", GEN: GEN_TEXT}, None, None, None, edit),
        ("case", [key], {"src/app/a.txt": "a\n", GEN: GEN_TEXT}, {"GEN/Known.txt": "junk\n"}, None, None,
         "SCOPE REFUSED: " + NEW_OUTSIDE % "GEN/Known.txt"),
        ("accent", ["Generated: gen/canción.txt = true"], {"src/app/a.txt": "a\n"}, {"gen/CANCIÓN.txt": "junk\n"},
         {"gen/canción.txt": "x\n"}, None, "SCOPE REFUSED: " + NEW_OUTSIDE % "gen/CANCIÓN.txt"),
        ("untracked", ["Generated: %s = %s; printf x > gen/stray.txt" % (GEN, GEN_CMD)], {"src/app/a.txt": "a\n", GEN: GEN_TEXT}, None, None, None,
         "SCOPE REFUSED: Generated file %s: its command (%s; printf x > gen/stray.txt) left untracked files: gen/stray.txt" % (GEN, GEN_CMD)),
    ]
    for name, lines, files, index, base, after, want in cases:
        try:
            verdict, _ = generated(r, "gen-human-" + name, lines, files, index, base, after)
        except Unbuildable:
            continue
        expect(verdict.startswith(want), "%s: expected: %r, got: %r" % (name, want, verdict))
    return "refused: " + ", ".join(c[0] for c in cases)


TESTS = [scope_check_is_one_pass_for_200_files, the_same_reasons_for_new_and_edited_files_outside_paths,
         a_file_name_is_not_a_paths_pattern, generated_file_is_not_out_of_scope, gate_refuses_a_generated_file_that_differs,
         generated_never_releases_a_human_file, generated_key_is_read_from_the_base, no_key_no_change,
         generated_file_is_checked_against_the_merge_commit, a_deletion_a_variant_a_mode_change_or_a_duplicate_is_the_humans]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-gate-scope-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        shims(runner)  # once, before the threads
        harness(runner)
        gen_harness(runner)
        def one(test):
            started = time.monotonic()
            try:
                note = test(runner)
                return test.__name__, True, "%s, %.2fs" % (note, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, TESTS))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("GATE_SCOPE_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
