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


def harness(r):
    h = r.scratch / "gate-scope-harness.sh"
    if not h.exists():
        h.write_text(HARNESS, encoding="utf-8", newline="\n")
    return h


def scene(r, name, files=None, index=None):
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
    for rel, text in BASE_FILES.items():
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
    return d, [harness(r).as_posix(), bindir.as_posix(), repo.as_posix(), base, tx.as_posix(),
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


TESTS = [scope_check_is_one_pass_for_200_files, the_same_reasons_for_new_and_edited_files_outside_paths,
         a_file_name_is_not_a_paths_pattern]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="uak-gate-scope-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        shims(runner)  # once, before the threads
        harness(runner)
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
