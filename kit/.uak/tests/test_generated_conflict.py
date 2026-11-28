#!/usr/bin/env python3
"""UAK-203: a conflict between a task's branch and the base that lies only in files declared `Generated: PATH = COMMAND`
in the BASE's PROJECT.md is resolved by the gate: in its own clone it takes the branch's side, runs the base's COMMAND
on a merge commit of the two (in a worktree of that clone, after the scope check and the secret scan), puts the result
in the merge, and the usual check of a generated file on the merge commit, the smoke and Verify follow. Anything else
is refused as before.

  generated_conflict_is_regenerated_at_merge  two tasks regenerate gen/known.txt; the second lands through the gate,
                                              the tree is the plain merge but for that file; add/add, binary, CRLF
  other_conflict_is_still_refused             another file, a mixed conflict, a deletion, a rename, a symlink, a
                                              duplicate line, a line only the branch declares: today's refusal
  failing_generator_is_refused                COMMAND fails, is missing, runs too long, changes another file, leaves
                                              one, writes in the gate's clone, commits, deletes the file, changes its mode
  done_does_not_warn_for_a_generated_file     `uak done` says the gate regenerates it; another file keeps UPSTREAM
  record_names_the_regenerated_files          `Regenerated:` in the record, the forge sentence, the human's 3 commands
  project_without_generated_is_unchanged      no `Generated:` line: the same output as before, and the happy path
                                              (no conflict) starts no new git command and one clone

Why: on 2026-11-24 and 25 UAK-162, UAK-192, UAK-194, UAK-195, UAK-165 and UAK-160 each lost a round (push, CI, done,
review) because another task merged first and both had regenerated kit/.uak/settings/known-files.txt.
Real Git and real `uak merge` (claims review mode); the conflict kinds through a harness that sources the engine's
libraries and calls the gate's own functions on a merge in a scratch repository. Standard library only.
Run: python3 kit/.uak/tests/test_generated_conflict.py [--case NAME]."""
import argparse
import concurrent.futures
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hack import Failure, Runner, expect, resolve_binary  # noqa: E402
from test_review_merge import approve, judge  # noqa: E402

GEN = "gen/known.txt"
CMD = "bash gen/make.sh"
PR = "https://github.com/org/repo/pull/1"
REFUSAL = "Conflict with current base; a human must resolve and request a new review"
MARK = ('[ -z "${GEN_MARK:-}" ] || pwd -P >> "$GEN_MARK"\n')
MAKE = "set -eu\n" + MARK + "cat src/*.txt | LC_ALL=C sort > gen/known.txt\n"
MAKE_FAILS = "set -eu\n" + MARK + "if grep -q FAIL src/one.txt 2>/dev/null; then exit 7; fi\ncat src/*.txt | LC_ALL=C sort > gen/known.txt\n"
SHARED = "1\n2\n3\n4\n5\n6\n7\n"
PROJECT = ("# Fixture\nMode: sprint\nAutonomy: yes\nAuto-Merge: yes\nBacklog-Approved: yes\nBacklog-Proposed-Epoch: 1000000\n"
           "Freeze-Epoch: 9999999\nReview-Mode: claims\nEvents-Per-Session: 100000\nCheckpoint-Percent: 60\n"
           "Merge-Lease-Seconds: 1800\nMerge-Wait-Seconds: 600\n")
NEW_GIT = ("worktree", "commit-tree", "update-index", "checkout-index", "ls-files -u")

HARNESS = r'''# $1 the engine's .uak/bin, $2 a repository at the base tip (the gate's clone), $3 the base tip, $4 the task tip,
# $5 a temp dir, $6 classify|regen. What rm_prepare_candidate does: merge --no-ff --no-commit, the conflict check, then
# (regen) the regeneration. ROOT is the candidate, so a refusal's log goes nowhere else.
UAK_BIN=$1
for l in lib/core.sh uak-coordination lib/config.sh lib/backlog.sh lib/review-merge.sh lib/hints.sh; do . "$UAK_BIN/$l" || exit 9; done
RM_BUILD=$2 RM_BASE_TIP=$3 RM_REVIEWED_TIP=$4 TXROOT=$5 ROOT=$2 ID=HACK-001 BASE=main NOW=1
RM_GATE_PATH=$PATH RM_MAIN=$5 RM_GATE_PORT=9999 RM_REGEN= RM_REGENERATED= RM_GEN_HINT=
# GC_LINK: a node_modules the gate linked into its clone (rm_gate_node), listed in gate-links as the gate lists it.
[ -z "${GC_LINK:-}" ] || { ln -s "$GC_LINK" "$RM_BUILD/node_modules" && printf '%s\n' "$RM_BUILD/node_modules" > "$TXROOT/gate-links"; }
: > "$TXROOT/merge-generated"
if git -C "$RM_BUILD" merge --no-ff --no-commit "$RM_REVIEWED_TIP" > "$TXROOT/merge.log" 2>&1; then echo "VERDICT CLEAN"
elif rm_generated_conflict; then echo "VERDICT RESOLVED"; else echo "VERDICT REFUSED"; fi
printf 'UNMERGED %s\n' "$(git -C "$RM_BUILD" ls-files -u | wc -l | tr -d ' ')"
[ -z "$RM_GEN_HINT" ] || printf '%s\n' "$RM_GEN_HINT" | sed 's/^/HINT /'
if [ "$6" = regen ] && [ -n "$RM_REGEN" ]; then
  git -C "$RM_BUILD" show "$RM_BASE_TIP:.uak/PROJECT.md" > "$TXROOT/merge-engine-project"
  started=$(date +%s)
  if rm_regenerate; then printf 'REGEN OK %s\n' "$RM_REGENERATED"; else printf 'REGEN REFUSED: %s\n' "$RM_REASON"; fi
  printf 'SECONDS %s\n' "$(( $(date +%s) - started ))"
fi
printf 'BLOB %s\n' "$(git -C "$RM_BUILD" rev-parse -q --verify ":gen/known.txt" 2>/dev/null)"
git -C "$RM_BUILD" diff --quiet && echo "DIRTY no" || echo "DIRTY yes"
printf 'WORKTREES %s\n' "$(git -C "$RM_BUILD" worktree list | wc -l | tr -d ' ')"
sed 's/^/GENLIST /' "$TXROOT/merge-generated"
'''

_lock = threading.Lock()
_results = {}


# ---------------------------------------------------------------- the conflict kinds (harness, a scratch repository)

def harness(r):
    h = r.scratch / "generated-conflict-harness.sh"
    with _lock:
        if not h.exists():
            h.write_text(HARNESS, encoding="utf-8", newline="\n")
    return h


def write(repo, rel, data):
    target = repo / rel
    if target.is_symlink():
        raise Failure("refusing to write through a symlink: %s" % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def commit(r, repo, changes, message):
    """changes: path -> text|bytes, None (delete) or ("link", target) (a symlink staged with mode 120000)."""
    links = {}
    for rel, data in changes.items():
        if data is None:
            r.g(repo, "rm", "-q", "--", rel)
        elif isinstance(data, tuple):
            links[rel] = data[1]
        else:
            write(repo, rel, data)
    r.g(repo, "add", "-A")
    for rel, to in links.items():
        blob = repo.parent / ("link-%s" % abs(hash(rel)))
        blob.write_text(to, encoding="utf-8", newline="")
        sha = r.g(repo, "hash-object", "-w", blob.as_posix()).stdout.strip()
        r.g(repo, "rm", "-q", "--cached", "--", rel)
        r.g(repo, "update-index", "--add", "--cacheinfo", "120000,%s,%s" % (sha, rel))
    r.g(repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.test", "commit", "-q", "-m", message)
    return r.g(repo, "rev-parse", "HEAD").stdout.strip()


def project(*lines):
    return "# Project\n" + "".join(l + "\n" for l in lines)


def case(r, name, base, tip, moved, mode="classify", env=None):
    """base (the merge base), then the task's commit on a branch, then the base's own commit: the harness merges the
    task's tip into the base tip in the repository itself. Returns the harness's lines as a dict of lists."""
    d = r.scratch / ("kind-" + name)
    repo, tmp = d / "repo", d / "tmp"
    repo.mkdir(parents=True)
    tmp.mkdir()
    r.g(repo, "init", "-q")
    r.g(repo, "config", "user.name", "gate")
    r.g(repo, "config", "user.email", "gate@example.test")
    r.g(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    commit(r, repo, dict({"README.md": "fixture\n", "src/a.txt": "a\n", "gen/make.sh": MAKE}, **base), "base")
    r.g(repo, "checkout", "-q", "-b", "task")
    tip_sha = commit(r, repo, tip, "task")
    r.g(repo, "checkout", "-q", "-f", "main")  # a symlink staged over a plain file leaves the file in the tree
    base_sha = commit(r, repo, moved, "moved")
    r.g(repo, "checkout", "-q", "--detach", base_sha)
    out = r.run([r.bash, harness(r).as_posix(), (r.package / ".uak" / "bin").as_posix(), repo.as_posix(), base_sha, tip_sha,
                 tmp.as_posix(), mode], cwd=d, env=env, allowed=None)
    res = {}
    for line in out.stdout.splitlines():
        key, _, rest = line.partition(" ")
        res.setdefault(key, []).append(rest)
    expect(out.returncode == 0 and "VERDICT" in res, "%s: the harness ran: %s" % (name, (out.stdout + out.stderr)[-1500:]))
    res["repo"], res["tip"] = repo, tip_sha
    return res


def one(res, key):
    return (res.get(key) or [""])[0]


def blob(r, res):
    sha = one(res, "BLOB")
    return r.run([r.git, "cat-file", "blob", sha], cwd=res["repo"], allowed=None).stdout.encode("utf-8", "surrogateescape") if sha else None


def blob_bytes(r, repo, sha):
    import subprocess
    return subprocess.run([r.git, "cat-file", "blob", sha], cwd=str(repo), stdout=subprocess.PIPE, env=r.env).stdout


def both(make_cmd=CMD, gen=("a\n", "a\nt\n", "a\nm\n"), extra=(), base_extra=None):
    """A generated file both sides changed: (base, tip, moved) for case()."""
    lines = ["Generated: %s = %s" % (GEN, make_cmd)] + list(extra)
    base = {".uak/PROJECT.md": project(*lines), GEN: gen[0]}
    base.update(base_extra or {})
    return base, {"src/t.txt": "t\n", GEN: gen[1]}, {"src/m.txt": "m\n", GEN: gen[2]}


def handled_kinds(r):
    """Both modified, add/add, binary and CRLF: resolved, regenerated with the base's command, the clone left with the
    regenerated blob in its index and working tree, the file queued for the check on the merge commit, no worktree left."""
    binary_cmd = "{ printf '\\000\\001'; cat src/*.txt | LC_ALL=C sort; } > gen/known.txt"
    crlf_cmd = "cat src/*.txt | LC_ALL=C sort | awk '{printf \"%s\\r\\n\", $0}' > gen/known.txt"
    add_base = {".uak/PROJECT.md": project("Generated: %s = %s" % (GEN, CMD))}
    kinds = {
        "modified": (both(), b"a\nm\nt\n", CMD),
        "add-add": ((add_base, {"src/t.txt": "t\n", GEN: "a\nt\n"}, {"src/m.txt": "m\n", GEN: "a\nm\n"}), b"a\nm\nt\n", CMD),
        "binary": (both(binary_cmd, (b"\x00\x01a\n", b"\x00\x01a\nt\n", b"\x00\x01a\nm\n")), b"\x00\x01a\nm\nt\n", binary_cmd),
        "crlf": (both(crlf_cmd, ("a\r\n", "a\r\nt\r\n", "a\r\nm\r\n")), b"a\r\nm\r\nt\r\n", crlf_cmd),
    }
    seen = []
    for name, ((base, tip, moved), want, cmd) in kinds.items():
        res = case(r, "ok-" + name, base, tip, moved, mode="regen")
        expect(one(res, "VERDICT") == "RESOLVED", "%s: resolved: %s" % (name, res))
        expect(one(res, "REGEN") == "OK " + GEN, "%s: regenerated: %s" % (name, res.get("REGEN")))
        got = blob_bytes(r, res["repo"], one(res, "BLOB"))
        expect(got == want, "%s: the regenerated file: expected %r, got %r" % (name, want, got))
        expect(one(res, "UNMERGED") == "0" and one(res, "DIRTY") == "no" and one(res, "WORKTREES") == "1",
               "%s: the clone is resolved, its tree matches its index, no worktree is left: %s" % (name, res))
        expect("%s\t%s" % (GEN, cmd) in res.get("GENLIST", []), "%s: queued for the check on the merge commit: %s" % (name, res.get("GENLIST")))
        seen.append(name)
    if os.name != "nt":  # the gate links with mklink /J there; this case makes its link with ln -s
        modules = r.scratch / "kind-node-modules-target"
        modules.mkdir()
        (modules / "marker.js").write_text("kept\n", encoding="utf-8")
        cmd = "test -f node_modules/marker.js && " + CMD
        base, tip, moved = both(cmd)
        res = case(r, "ok-node-modules", base, tip, moved, mode="regen", env={"GC_LINK": modules.as_posix()})
        expect(one(res, "REGEN") == "OK " + GEN, "node_modules: the command sees the clone's node_modules: %s" % res)
        expect((modules / "marker.js").exists(), "node_modules: the link was undone, its target kept")
        expect(not (res["repo"].parent / "tmp" / "regen").exists(), "node_modules: the worktree folder is gone")
        seen.append("node_modules")
    return seen


def refused_kinds(r):
    """Each kind the gate does not resolve: today's refusal, nothing resolved (every unmerged entry still there), the
    generator never run."""
    mark = r.scratch / "kind-refused-mark.txt"
    gen_line = "Generated: %s = %s" % (GEN, CMD)
    seed = "".join("line %d\n" % i for i in range(1, 13))
    kinds = {
        "other-file": ({".uak/PROJECT.md": project(gen_line), "src/c.txt": "c\n"}, {"src/c.txt": "c\nt\n"}, {"src/c.txt": "c\nm\n"}, 3),
        "mixed": (dict(both()[0], **{"src/c.txt": "c\n"}), dict(both()[1], **{"src/c.txt": "c\nt\n"}),
                  dict(both()[2], **{"src/c.txt": "c\nm\n"}), 6),
        "deleted-on-base": (both()[0], both()[1], {"src/m.txt": "m\n", GEN: None}, 2),
        "deleted-on-branch": (both()[0], {"src/t.txt": "t\n", GEN: None}, both()[2], 2),
        "rename-into": ({".uak/PROJECT.md": project(gen_line), "gen/seed.txt": seed}, {"gen/seed.txt": seed + "t\n"},
                        {"gen/seed.txt": None, GEN: seed + "m\n"}, None),
        "symlink": (both()[0], {"src/t.txt": "t\n", GEN: ("link", "../README.md")}, both()[2], None),
        "duplicate": both(extra=["Generated: %s = true" % GEN]) + (3,),
        "branch-declared": ({".uak/PROJECT.md": project(gen_line), "src/c.txt": "c\n"},
                            {".uak/PROJECT.md": project(gen_line, "Generated: src/c.txt = true"), "src/c.txt": "c\nt\n"},
                            {"src/c.txt": "c\nm\n"}, 3),
    }
    seen = []
    for name, (base, tip, moved, unmerged) in kinds.items():
        res = case(r, "no-" + name, base, tip, moved, mode="regen", env={"GEN_MARK": mark.as_posix()})
        expect(one(res, "VERDICT") == "REFUSED", "%s: refused: %s" % (name, res))
        expect(unmerged is None or one(res, "UNMERGED") == str(unmerged),
               "%s: nothing resolved, %s unmerged entries expected: %s" % (name, unmerged, res.get("UNMERGED")))
        expect(int(one(res, "UNMERGED") or 0) > 0, "%s: the conflict is left as it was: %s" % (name, res))
        expect("REGEN" not in res and not mark.exists(), "%s: the generator never ran" % name)
        if name == "mixed":
            expect(res.get("HINT") == ["%s\t%s" % (GEN, CMD)], "mixed: the generated file is named for the human's hint: %s" % res.get("HINT"))
        if name in ("other-file", "branch-declared"):
            expect("HINT" not in res, "%s: no generated file, no hint: %s" % (name, res.get("HINT")))
        seen.append(name)
    return seen


def failing_kinds(r):
    """COMMAND fails, is missing, runs over Generated-Seconds, changes another tracked file, leaves an untracked file,
    writes in the gate's clone (outside its worktree), commits, deletes the file, changes its mode: refused, the
    reason names the file and the command, the clone keeps the branch's side and no worktree."""
    into_clone = 'bash gen/make.sh; printf x >> "$(git worktree list --porcelain | sed -n "s/^worktree //p" | head -n 1)/src/a.txt"'
    kinds = [
        ("fails", "bash gen/make.sh; exit 3", "its command failed"),
        ("missing", "uak203-no-such-generator", "its command failed"),
        ("timeout", "sleep 30", "ran over 2 s"),
        ("other-file", "bash gen/make.sh; printf x >> src/a.txt", "changed other files too: src/a.txt"),
        ("untracked", "bash gen/make.sh; printf x > stray.txt", "left untracked files: stray.txt"),
        ("into-clone", into_clone, "wrote in the gate's clone"),
        ("commits", "bash gen/make.sh; git add -A; git -c user.name=x -c user.email=x@example.test commit -qm x", "moved HEAD or staged changes"),
        ("deleted", "rm gen/known.txt", "is not in the result"),
    ]
    if os.name != "nt":  # Git for Windows keeps no executable bit (core.filemode false)
        kinds.append(("mode", "bash gen/make.sh; chmod +x gen/known.txt", "changed its mode"))
    seen = []
    for name, cmd, why in kinds:
        base, tip, moved = both(cmd, extra=["Generated-Seconds: 2"])
        res = case(r, "fail-" + name, base, tip, moved, mode="regen")
        reason = one(res, "REGEN")
        expect(one(res, "VERDICT") == "RESOLVED", "%s: a conflict in the generated file only: %s" % (name, res))
        expect(reason.startswith("REFUSED: Generated file %s: conflict with main" % GEN) and why in reason and cmd in reason,
               "%s: refused naming the file, the command and %r: %s" % (name, why, reason))
        tip_blob = r.g(res["repo"], "rev-parse", "%s:%s" % (res["tip"], GEN)).stdout.strip()
        expect(one(res, "BLOB") == tip_blob, "%s: nothing regenerated was written into the clone's index: %s" % (name, res))
        expect(one(res, "WORKTREES") == "1", "%s: the regeneration worktree is gone: %s" % (name, res))
        if name == "timeout":
            expect(int(one(res, "SECONDS") or 99) < 15, "timeout: stopped after the limit: %s s" % one(res, "SECONDS"))
        seen.append(name)
    return seen


# ---------------------------------------------------------------- the whole gate (real uak done and uak merge)

def gen_text(files):
    lines = []
    for rel in sorted(files):
        if rel.startswith("src/") and rel.endswith(".txt") and "/" not in rel[4:]:
            lines += files[rel].splitlines(True)
    return "".join(sorted(lines))


def uak(r, f, index, *args, now, env=None):
    e = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": str(now), "UAK_REMOTE": "origin", "UAK_HUMAN": ""}
    e.update(env or {})
    return r.run([r.bash, ".uak/bin/uak", *args], cwd=f.worktrees[index], env=e, allowed=None, timeout=400)


def git_trace(r, name):
    """GIT_TRACE to a file: every git command the gate runs, as git itself names it after its options (-C, -c) on every
    system (a `git` shim first in PATH was not used by Git Bash on Windows)."""
    log = r.scratch / ("git-" + name + ".log")
    return {"GIT_TRACE": log.as_posix()}, log


def scene(r, name, generated=True, make=MAKE):
    f = r.fixture("gc-" + name, paths={"HACK-001": "src/one.txt, src/shared.txt", "HACK-002": "src/two.txt, src/shared.txt"}, count=2)
    tasks = (f.seed / ".uak/TASKS.md").read_text(encoding="utf-8").split("## ")
    for i, part in enumerate(tasks):
        for t, path in (("HACK-001", "src/one.txt"), ("HACK-002", "src/two.txt")):
            if part.startswith(t):
                tasks[i] = part.replace(".uak/bin/smoke --package-only", "grep -q ready-%s %s" % (t, path))
    (f.seed / ".uak/TASKS.md").write_text("## ".join(tasks), encoding="utf-8")
    (f.seed / ".uak/PROJECT.md").write_text(PROJECT + ("Generated: %s = %s\n" % (GEN, CMD) if generated else ""), encoding="utf-8")
    (f.seed / ".uak/bin/smoke").write_text(
        "#!/usr/bin/env bash\nset -eu\ncd \"$(dirname \"$0\")/../..\"\nbash -n .uak/bin/uak\n"
        "[ -f .uak/bin/smoke-project ] || { echo PRODUCT_UNVERIFIED; exit 2; }\nbash .uak/bin/smoke-project\necho FIXTURE_PRODUCT_PASS\n",
        encoding="utf-8")
    (f.seed / ".uak/bin/smoke-project").write_text("#!/usr/bin/env bash\nset -eu\n[ ! -f .red-product-gate ]\n", encoding="utf-8")
    for rel, text in (("gen/make.sh", make), ("src/shared.txt", SHARED), (GEN, gen_text({"src/shared.txt": SHARED}))):
        write(f.seed, rel, text)
    r.g(f.seed, "add", "-A")
    r.g(f.seed, "commit", "-m", "Configure the fixture")
    r.g(f.seed, "push", "origin", "main")
    for wt in f.worktrees:
        r.g(wt, "fetch", "origin", "main")
        r.g(wt, "merge", "-q", "--ff-only", "origin/main")
    f.files = {"src/shared.txt": SHARED}
    judge(f)
    return f


def task_files(f, task, line):
    path = "src/one.txt" if task == "HACK-001" else "src/two.txt"
    shared = SHARED.splitlines(True)
    shared[line] = "%s\n" % task
    return {path: "ready-%s%s\n" % (task, " FAIL" if getattr(f, "fail", False) and task == "HACK-001" else ""), "src/shared.txt": "".join(shared)}


def ship(r, f, index, task, files, now):
    """claim, write the files and the regenerated file, commit, push, done, approved by the registered judge."""
    out = uak(r, f, index, "claim", task, "--branch", f.branches[index], "--worktree", f.worktrees[index].as_posix(),
              "--next", "Implement it", now=now)
    expect(out.returncode == 0, "claim %s: %s" % (task, out.stdout + out.stderr))
    wt = f.worktrees[index]
    for rel, text in files.items():
        write(wt, rel, text)
    write(wt, GEN, gen_text(dict(f.files, **files)))
    r.g(wt, "add", "-A")
    r.g(wt, "commit", "-m", "Implement " + task)
    r.g(wt, "push", "origin", f.branches[index])
    tip = r.g(wt, "rev-parse", "HEAD").stdout.strip()
    done = uak(r, f, index, "done", task, "--pr", PR, "--evidence", "Fixture acceptance", now=now + 10)
    expect(done.returncode == 0, "done %s: %s" % (task, done.stdout + done.stderr))
    approve(f, task, tip, now=now + 11)
    return tip, done


def land_on_main(r, f, files):
    """The base moves without the gate (another task landed): the seed pushes HACK-002's files and the regenerated file."""
    for rel, text in files.items():
        write(f.seed, rel, text)
    f.files.update(files)
    write(f.seed, GEN, gen_text(f.files))
    r.g(f.seed, "add", "-A")
    r.g(f.seed, "commit", "-m", "HACK-002 landed")
    r.g(f.seed, "push", "origin", "main")


def git_cmds(log):
    """The built-in git commands of a GIT_TRACE log: `clone -q ...`, `worktree add ...`."""
    if not log.exists():
        return []
    key = "trace: built-in: git "
    return [l.split(key, 1)[1] for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if key in l]


def marks(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def run_scene(r, name):
    """regen: HACK-002 lands through the gate (happy path, git counted), then HACK-001, whose only conflict is the
    generated file. clash: both edit line 1 of src/shared.txt too. plain: no Generated: line. fail: the generator
    fails on HACK-001's files."""
    mark = r.scratch / ("mark-" + name + ".txt")
    f = scene(r, name, generated=(name != "plain"), make=(MAKE_FAILS if name == "fail" else MAKE))
    f.fail = name == "fail"
    res = {"f": f, "mark": mark}
    env = {"GEN_MARK": mark.as_posix()}
    if name == "regen":
        tip2, _ = ship(r, f, 1, "HACK-002", task_files(f, "HACK-002", 6), 1000000)
        shim, log = git_trace(r, name + "-happy")
        res["happy"] = uak(r, f, 1, "merge", "HACK-002", now=1000030, env=dict(env, **shim))
        res["happy_git"] = git_cmds(log)
        res["happy_marks"] = marks(mark)
        f.files.update(task_files(f, "HACK-002", 6))
    else:
        land_on_main(r, f, task_files(f, "HACK-002", 0 if name == "clash" else 6))
    for wt in f.worktrees:
        r.g(wt, "fetch", "origin", "main")
    res["main_before"] = r.g(f.remote, "rev-parse", "main").stdout.strip()
    res["tip"], res["done"] = ship(r, f, 0, "HACK-001", task_files(f, "HACK-001", 0), 1000040)
    before = len(marks(mark))
    shim, log = git_trace(r, name + "-merge")
    res["merge"] = uak(r, f, 0, "merge", "HACK-001", now=1000070, env=dict(env, **shim))
    res["merge_git"] = git_cmds(log)
    res["merge_marks"] = marks(mark)[before:]
    res["main_after"] = r.g(f.remote, "rev-parse", "main").stdout.strip()
    res["record"] = f.show("tasks/HACK-001.md")
    res["queue"] = f.show("queue/HACK-001.md")
    return res


def scene_result(r, name):
    res = _results.get(name)
    if res is None:
        raise Failure("the %s scene was not built" % name)
    if isinstance(res, Exception):
        raise Failure("the %s scene failed: %s" % (name, str(res)[:2500]))
    return res


def field(text, key):
    for line in text.splitlines():
        if line.startswith(key + ": "):
            return line[len(key) + 2:]
    return None


def physical(p):
    return os.path.normcase(os.path.realpath(str(p)))


# ---------------------------------------------------------------- the named tests

def generated_conflict_is_regenerated_at_merge(r):
    res = scene_result(r, "regen")
    f, out = res["f"], res["merge"]
    expect(res["happy"].returncode == 0, "HACK-002 lands first: " + res["happy"].stdout + res["happy"].stderr)
    expect(out.returncode == 0 and "OK merge HACK-001 | INTEGRATED" in out.stdout, "HACK-001 lands: " + out.stdout + out.stderr)
    landed = res["main_after"]
    parents = r.g(f.remote, "rev-list", "--parents", "-n", "1", landed).stdout.split()[1:]
    expect(parents == [res["main_before"], res["tip"]], "the landed commit merges the base tip and the reviewed tip: %s" % parents)
    shared = SHARED.splitlines(True)
    shared[0], shared[6] = "HACK-001\n", "HACK-002\n"
    want = gen_text(dict(f.files, **dict(task_files(f, "HACK-001", 0), **{"src/shared.txt": "".join(shared)})))
    expect(r.g(f.remote, "show", "%s:src/shared.txt" % landed).stdout == "".join(shared), "src/shared.txt merged by git")
    got = r.g(f.remote, "show", "%s:%s" % (landed, GEN)).stdout
    expect(got == want, "the generated file is the base's command run on the merge: %r != %r" % (got, want))
    # Property 1: every other path is exactly what a plain merge of the two gives; the generated file is its only conflict.
    plain = r.scratch / "gc-regen-plain"
    r.g(r.scratch, "clone", "-q", "--no-checkout", f.remote.as_posix(), plain.as_posix())
    r.g(plain, "checkout", "-q", "--detach", res["main_before"])
    r.g(plain, "-c", "user.name=x", "-c", "user.email=x@example.test", "merge", "--no-ff", "--no-commit", res["tip"], allowed=None)
    stage0, unmerged = {}, set()
    for line in r.g(plain, "ls-files", "-s").stdout.splitlines():
        meta, path = line.split("\t", 1)
        mode, sha, st = meta.split()
        if st == "0":
            stage0[path] = (mode, sha)
        else:
            unmerged.add(path)
    expect(unmerged == {GEN}, "the plain merge conflicts only in the generated file: %s" % sorted(unmerged))
    tree = {}
    for line in r.g(f.remote, "ls-tree", "-r", landed).stdout.splitlines():
        meta, path = line.split("\t", 1)
        mode, _, sha = meta.split()
        tree[path] = (mode, sha)
    gen_entry = tree.pop(GEN)
    expect(tree == stage0, "every path but the generated one is the plain merge: %s" %
           sorted(set(tree.items()) ^ set(stage0.items()))[:6])
    expect(gen_entry[0] == "100644", "the regenerated file keeps mode 100644: %s" % gen_entry[0])
    # Property 4: the command ran in the gate's clone (a worktree of it, then the check in the clone itself), never in
    # an author's worktree, clone or the seed.
    places = res["merge_marks"]
    forbidden = [physical(p) for p in list(f.worktrees) + list(f.clones) + [f.seed]]
    expect(len(places) == 2 and places[0].endswith("/regen") and places[1].endswith("/candidate"),
           "regenerated in the clone's worktree, then checked in the clone: %s" % places)
    expect(not any(physical(p) == x or physical(p).startswith(x + os.sep) for p in places for x in forbidden),
           "never in a worktree or clone of the authors: %s" % places)
    expect(sum(1 for l in res["merge_git"] if l.startswith("clone")) == 1, "one clone on the conflict path too")
    expect(any(l.startswith("worktree add") for l in res["merge_git"]), "the git log saw the regeneration")
    kinds = handled_kinds(r)
    return "lands as the plain merge but %s; %s" % (GEN, ", ".join(kinds))


def other_conflict_is_still_refused(r):
    res = scene_result(r, "clash")
    out = res["merge"]
    lines = out.stdout.splitlines()
    expect(out.returncode == 3 and lines and lines[0] == "MERGE_HUMAN HACK-001 | " + REFUSAL,
           "a mixed conflict is today's refusal: " + out.stdout + out.stderr)
    expect(res["main_after"] == res["main_before"], "the base did not move")
    expect(not res["merge_marks"], "nothing regenerated: %s" % res["merge_marks"])
    plain = scene_result(r, "plain")
    for key in ("State", "Next"):
        expect(field(res["record"], key) == field(plain["record"], key),
               "%s as today (no Generated: line): %r != %r" % (key, field(res["record"], key), field(plain["record"], key)))
    expect(field(res["queue"], "State") == field(plain["queue"], "State"), "queue state as today")
    kinds = refused_kinds(r)
    return "mixed conflict refused as today; " + ", ".join(kinds)


def failing_generator_is_refused(r):
    res = scene_result(r, "fail")
    out = res["merge"]
    expect(out.returncode == 3 and ("MERGE_HUMAN HACK-001 | Generated file %s: conflict with main, and its command failed" % GEN) in out.stdout
           and CMD in out.stdout, "a failing generator goes to the human with the reason: " + out.stdout + out.stderr)
    expect(res["main_after"] == res["main_before"], "the base did not move")
    plain = scene_result(r, "plain")
    expect(field(res["record"], "State") == field(plain["record"], "State") and field(res["queue"], "State") == field(plain["queue"], "State"),
           "the task's state is that of any refusal: %r / %r" % (field(res["record"], "State"), field(res["queue"], "State")))
    expect("Regenerated" not in res["record"], "nothing recorded as regenerated")
    kinds = failing_kinds(r)
    return "refused at the gate; " + ", ".join(kinds)


def done_does_not_warn_for_a_generated_file(r):
    res = scene_result(r, "regen")
    text = res["done"].stdout
    expect("UPSTREAM: %s" % GEN not in text, "no UPSTREAM warning for the generated file: " + text)
    expect(("GENERATED: %s changed on main too: the merge gate regenerates it (%s)" % (GEN, CMD)) in text,
           "says the gate regenerates it: " + text)
    expect("UPSTREAM: src/shared.txt changed on main too" in text and "you both edit it" in text and "Fix now, not at merge" in text,
           "another file both edit keeps the warning and the fix: " + text)
    plain = scene_result(r, "plain")["done"].stdout
    expect("UPSTREAM: %s changed on main too" % GEN in plain and "GENERATED:" not in plain,
           "without a Generated: line the warning stays: " + plain)
    return "GENERATED sentence for %s, UPSTREAM kept for src/shared.txt" % GEN


def record_names_the_regenerated_files(r):
    res = scene_result(r, "regen")
    expect(field(res["record"], "Regenerated") == GEN, "Regenerated: in the record: " + res["record"])
    note = [l for l in res["merge"].stdout.splitlines() if "forge" in l]
    expect(len(note) == 1 and note[0].startswith("NOTE HACK-001: ") and "conflicting" in note[0] and note[0].count(". ") == 0,
           "one sentence says the forge may still show the pull request as conflicting: %s" % note)
    hint = "HUMAN: %s is generated and conflicts with main: git fetch origin && git merge --no-edit origin/main; %s; git add %s && git commit --no-edit" % (GEN, CMD, GEN)
    for name in ("fail", "clash"):
        expect(hint in scene_result(r, name)["merge"].stdout.splitlines(), "%s: the human's three commands: %s" % (name, scene_result(r, name)["merge"].stdout))
    expect("Regenerated" not in scene_result(r, "plain")["record"], "no record line without a regeneration")
    return "Regenerated: %s; NOTE line; the three commands" % GEN


PLAIN_OUT = ["MERGE_HUMAN HACK-001 | " + REFUSAL,
             "HUMAN: review the reason; if the PR is fine, merge %s on the forge, then any agent runs: bash .uak/bin/uak integrate HACK-001" % PR]


def project_without_generated_is_unchanged(r):
    res = scene_result(r, "plain")
    out = res["merge"]
    expect(out.returncode == 3 and out.stdout.splitlines() == PLAIN_OUT, "the same output as before UAK-203: %r" % out.stdout)
    expect(res["main_after"] == res["main_before"] and not res["merge_marks"], "nothing landed, nothing ran")
    expect(not any(l.startswith(NEW_GIT) for l in res["merge_git"]),
           "no new git command: %s" % [l for l in res["merge_git"] if l.startswith(NEW_GIT)])
    k = case(r, "no-key", {"README.md": "x\n", GEN: "a\n"}, {GEN: "a\nt\n"}, {GEN: "a\nm\n"}, mode="regen")
    expect(one(k, "VERDICT") == "REFUSED" and "HINT" not in k and "REGEN" not in k, "the harness: refused, no hint: %s" % k)
    # The happy path (HACK-002, no conflict, with a Generated: line): one clone and none of the commands UAK-203 adds;
    # the generator ran once, as before (the check of a generated file on the merge commit).
    happy = scene_result(r, "regen")
    clones = sum(1 for l in happy["happy_git"] if l.startswith("clone"))
    added = [l for l in happy["happy_git"] if l.startswith(NEW_GIT)]
    expect(clones == 1 and not added and len(happy["happy_marks"]) == 1,
           "happy path: %d clone(s), new commands %s, generator runs %s" % (clones, added, happy["happy_marks"]))
    return "same two lines; happy path: 1 clone, %d git calls, no new command" % len(happy["happy_git"])


TESTS = [generated_conflict_is_regenerated_at_merge, other_conflict_is_still_refused, failing_generator_is_refused,
         done_does_not_warn_for_a_generated_file, record_names_the_regenerated_files, project_without_generated_is_unchanged]
NEEDS = {"generated_conflict_is_regenerated_at_merge": ("regen",), "other_conflict_is_still_refused": ("clash", "plain"),
         "failing_generator_is_refused": ("fail", "plain"), "done_does_not_warn_for_a_generated_file": ("regen", "plain"),
         "record_names_the_regenerated_files": ("regen", "fail", "clash", "plain"), "project_without_generated_is_unchanged": ("plain", "regen")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    scenes = sorted({s for t in tests for s in NEEDS[t.__name__]})
    with tempfile.TemporaryDirectory(prefix="uak-generated-conflict-") as tmp:
        r = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        harness(r)

        def build(name):
            started = time.monotonic()
            try:
                _results[name] = run_scene(r, name)
            except Exception as exc:  # noqa: BLE001
                _results[name] = exc
            return name, time.monotonic() - started

        def one_test(test):
            started = time.monotonic()
            try:
                return test.__name__, True, "%s, %.1fs" % (test(r), time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:2500]

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for name, secs in pool.map(build, scenes):
                print("scene %s %.1fs" % (name, secs), flush=True)
            results = list(pool.map(one_test, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("GENERATED_CONFLICT_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
