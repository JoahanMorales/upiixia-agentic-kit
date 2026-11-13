#!/usr/bin/env python3
"""The claims redesign changed how the engine reads and writes the claims branch (UAK-003: one awk pass for status and
next; UAK-008: the merge gate's scope in one pass; UAK-016: STATE.md in one pass), not what it says or writes.
This runs the engine from before it (main at OLD, just before UAK-003) and today's side by side: the same fixture, the
same protocol commands in the same order, the same clock (UAK_NOW). After every command the exit code, stdout and the
whole claims tree must be identical, once the fixture's own folder is written as <BASE> and each of its commits by
what it is (<SHA main:Fixture main#1>): a SHA is compared, by commit, not hidden.

    python3 scripts/claims_diff.py [--keep]

Real Git, a local bare remote, nothing leaves this machine. The old engine comes from this repository's history
(`git archive OLD kit`); a shallow clone fetches that one commit first. Standard library only."""
import argparse
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kit" / ".uak" / "tests"))
from test_hack import Runner, expect, resolve_binary  # noqa: E402

OLD = "c949f9057dc8a691b1dcb5f0e821f8ae21a67606"  # Merge UAK-011, the last main before UAK-003
# Fixed bugs that changed output on purpose, kept out of the scenario: merge from a worktree (UAK-012), a CRLF
# checkout (UAK-014), bash 3.2 (UAK-013), a dependency listed after its dependent (UAK-017).
TASKS = {"HACK-001": "src/one/", "HACK-002": "src/two/", "HACK-003": "src/three/", "HACK-004": "src/four/",
         "HACK-005": "src/five/", "HACK-006": "src/six/"}
DEPENDS = {"HACK-005": "HACK-001"}
# A worklog's name ends with its transaction's temp folder (mktemp hack.XXXXXX): random on every run, either engine.
TEMP = re.compile(r"(?<=-hack\.)[A-Za-z0-9]{6}(?=\.md)")
# status --summary's read token is the cksum of the claim record, which names that worklog: the sum differs, the
# length after the dash (the record's size) is still compared.
TOKEN = re.compile(r"(?<=Read-token: )[0-9]+(?=-[0-9]+)")
# Git's relative date of the last commit ("6 seconds ago") follows the wall clock, not UAK_NOW.
AGO = re.compile(r"\([0-9]+ (?:second|minute|hour)s? ago\)")
# The kit's version (`status` prints "uak v6.0.0 | remote claims …"): a release changes it, the engine does not.
VERSION = re.compile(r"(?<=^uak v)[0-9]+\.[0-9]+\.[0-9]+(?= \|)", re.M)


def git_bytes(r, cwd, *args):
    out = subprocess.run([r.git, *args], cwd=str(cwd), env=r.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    expect(out.returncode == 0, "git %s: %s" % (" ".join(args), out.stderr.decode("utf-8", "replace")[-400:]))
    return out.stdout


def old_package(r, dest):
    """kit/ as it was at OLD, extracted to dest/kit."""
    probe = subprocess.run([r.git, "cat-file", "-e", OLD + "^{commit}"], cwd=str(ROOT), env=r.env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode:
        # Only a shallow clone (CI's checkout) lacks it; there one more shallow commit changes nothing.
        git_bytes(r, ROOT, "fetch", "-q", "--depth", "1", "origin", OLD)
    data = git_bytes(r, ROOT, "archive", "--format=tar", OLD, "kit")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            expect(not m.name.startswith(("/", "..")) and ".." not in Path(m.name).parts, "unsafe path in archive: " + m.name)
            expect(m.isfile() or m.isdir(), "a link or device in the archive: " + m.name)
        tar.extractall(str(dest))
    return dest / "kit"


def path_forms(base):
    """Every spelling of the fixture's folder an output may carry: native, posix, Git Bash (/c/...)."""
    forms = {str(base), base.as_posix()}
    p = base.as_posix()
    if re.match(r"^[A-Za-z]:/", p):
        forms.add("/" + p[0].lower() + p[2:])
    return sorted(forms, key=len, reverse=True)


# The fixture's folder as Git Bash may spell it when Python saw another form (Windows: C:\Users\RUNNER~1\… for
# Python, /c/Users/runneradmin/… in the records): the run's own folder name is unique, so match on it.
BASE = re.compile(r"[^\s'\"`]*uak-claims-diff-[A-Za-z0-9_]+[/\\][on][/\\]diff(?![A-Za-z0-9_])")


def normalize(text, base, shas=None):
    for form in path_forms(base):
        text = text.replace(form, "<BASE>")
    text = BASE.sub("<BASE>", text)
    # Each of the fixture's commits, full or abbreviated (a short SHA can be all digits: 5403068), by its label: an
    # engine that recorded another commit (HEAD~1 for HEAD, kit-r1 on 7d8d7db) shows up as another label.
    for sha, label in (shas or {}).items():
        text = re.sub(r"(?<![0-9a-f])%s[0-9a-f]{0,33}(?![0-9A-Za-z])" % sha[:7], "<SHA %s>" % label, text)
    text = TOKEN.sub("<CKSUM>", AGO.sub("(<AGO>)", TEMP.sub("<TMP>", text.replace("\r\n", "\n"))))
    return VERSION.sub("<VERSION>", text)


def fixture_shas(r, f):
    """sha -> a label the same on both engines: the branch, the commit's subject and its place among the commits of
    that subject (oldest first, first parents). Both engines make the same commits in the same order; only their
    SHAs differ (the seed holds a different kit)."""
    labels, seen = {}, {}
    refs = git_bytes(r, f.remote, "for-each-ref", "--format=%(refname:short)", "refs/heads").decode().split()
    sources = [(f.remote, ref) for ref in sorted(refs)] + [(wt, "HEAD") for wt in f.worktrees]
    for repo, ref in sources:
        log = git_bytes(r, repo, "log", "--first-parent", "--reverse", "--format=%H %s", ref).decode("utf-8", "replace")
        for line in log.splitlines():
            sha, _, subject = line.partition(" ")
            if sha in labels:
                continue
            key = (ref if repo == f.remote else "worktree", subject)
            seen[key] = seen.get(key, 0) + 1
            labels[sha] = "%s:%s#%d" % (key[0], subject, seen[key])
    return labels


def claims_tree(r, f, shas):
    """path -> normalized content of every file on the remote's claims branch."""
    data = git_bytes(r, f.remote, "archive", "--format=tar", "claims")
    tree = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            if m.isfile():
                tree[normalize(m.name, f.base, shas)] = normalize(tar.extractfile(m).read().decode("utf-8", "replace"), f.base, shas)
    return tree


def scenario(r):
    """The protocol, step by step: (label, exit code, stdout, claims tree) after each command."""
    f = r.fixture("diff", paths=TASKS, count=3, dependencies=DEPENDS)
    steps, raw = [], []
    now = [1000000]

    def step(label, index, *args, human=False, cwd=None):
        now[0] += 7
        if cwd is None:
            out = f.hack(index, *args, now=now[0], allowed=None, human=human)
        else:
            env = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": str(now[0]), "UAK_REMOTE": "origin",
                   "UAK_HUMAN": "human-fixture" if human else ""}
            out = r.run([r.bash, ".uak/bin/uak", *args], cwd=cwd, env=env, allowed=None)
        shas = fixture_shas(r, f)
        tree = claims_tree(r, f, shas) if r.g(f.remote, "rev-parse", "-q", "--verify", "refs/heads/claims", allowed=None).returncode == 0 else {}
        raw.append(out.stdout)
        steps.append((label, out.returncode, normalize(out.stdout, f.base, shas), tree))

    step("status before any claim", 0, "status")
    step("next before any claim", 0, "next")
    step("claim HACK-001", 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(),
         "--next", "write the first test")
    step("claim HACK-002", 1, "claim", "HACK-002", "--branch", f.branches[1], "--worktree", f.worktrees[1].as_posix(),
         "--next", "read the spec")
    step("claim of a taken task", 2, "claim", "HACK-001", "--branch", f.branches[2], "--worktree", f.worktrees[2].as_posix())
    step("claim before its dependency", 2, "claim", "HACK-005", "--branch", f.branches[2], "--worktree", f.worktrees[2].as_posix())
    step("heartbeat", 0, "heartbeat", "HACK-001")
    step("status", 0, "status")
    step("status --full", 0, "status", "--full")
    step("status --task", 0, "status", "--task", "HACK-001")
    step("status --task --summary", 0, "status", "--task", "HACK-001", "--summary")
    step("next with a claim", 0, "next")
    step("next of an idle agent", 2, "next", cwd=f.clones[2])
    step("msg request", 1, "msg", "HACK-001", "src/one/a.txt · add a line · the spec asks for it", "--kind", "request")
    step("inbox", 0, "inbox")
    step("inbox --ack", 0, "inbox", "--ack")
    step("log", 1, "log", "HACK-002", "a progress note")
    step("log BLOCKED", 1, "log", "HACK-002", "--state", "BLOCKED", "fixture error: exit 1")
    step("status with a BLOCKED task", 0, "status")
    step("checkpoint", 0, "checkpoint", "HACK-001", "--done", "first test", "--decision", "keep it small", "--why",
         "one criterion", "--fails", "none", "--commands", "true", "--next", "the second test")
    step("decision", 0, "decision", "HACK-001", "--option", "a flat file", "--why", "simplest", "--reversible", "yes",
         "--authorized", "yes", "--class", "routine")
    step("release", 1, "release", "HACK-002")
    step("claim again after a release", 2, "claim", "HACK-002", "--branch", f.branches[2], "--worktree", f.worktrees[2].as_posix())
    (f.worktrees[0] / "src" / "one").mkdir(parents=True, exist_ok=True)
    (f.worktrees[0] / "src" / "one" / "a.txt").write_text("a line\n", encoding="utf-8")
    r.g(f.worktrees[0], "add", "src/one/a.txt")
    r.g(f.worktrees[0], "commit", "-q", "-m", "HACK-001: a line")
    r.g(f.worktrees[0], "push", "-q", "origin", f.branches[0])
    tip = r.g(f.worktrees[0], "rev-parse", "HEAD").stdout.strip()
    step("done", 0, "done", "HACK-001", "--pr", "https://example.invalid/pull/1", "--evidence", "a.txt has the line",
         "--no-red", "fixture task")
    step("status with a task in REVIEW", 1, "status")
    step("register a reviewer", 0, "register-reviewer", "agent-2", human=True)
    step("review --start", 1, "review", "HACK-001", "--start")
    step("review approve", 1, "review", "HACK-001", "--sha", tip, "--verdict", "approve", "--note", "a.txt:1 · fine")
    step("next of the author in REVIEW", 0, "next")
    step("digest", 0, "digest", human=True)
    # Ten days later every lease has expired (claims, and REVIEW's longer one): what status and next say about it,
    # and the recovery of an expired claim with its summary's read token.
    now[0] += 10 * 86400
    step("status with expired leases", 0, "status")
    step("status --full with expired leases", 1, "status", "--full")
    step("next with an expired claim", 2, "next")
    # "next of the reviewer" is out of the scenario on purpose (UAK-069): a registered reviewer is no longer offered
    # implementation work, so the old engine's output is no longer the expectation (test_next_reviewer.py covers it).
    step("summary of an expired claim", 1, "status", "--task", "HACK-002", "--summary")
    token = re.search(r"Read-token: (\S+)", raw[-1])
    expect(token is not None, "no read token in: " + raw[-1][-400:])
    step("release --expired", 1, "release", "HACK-002", "--expired", "--read-summary", token.group(1))
    step("claim after an expired release", 1, "claim", "HACK-002", "--branch", f.branches[1], "--worktree", f.worktrees[1].as_posix())
    step("status at the end", 2, "status", "--full")
    return steps


def compare(old, new):
    problems = []
    expect(len(old) == len(new), "the scenario ran %d steps on the old engine and %d on the new" % (len(old), len(new)))
    for (label, rc_o, out_o, tree_o), (_, rc_n, out_n, tree_n) in zip(old, new):
        if rc_o != rc_n:
            problems.append("%s: exit %d before, %d now" % (label, rc_o, rc_n))
        if out_o != out_n:
            import difflib
            d = "\n".join(difflib.unified_diff(out_o.splitlines(), out_n.splitlines(), "before", "now", lineterm=""))
            problems.append("%s: stdout differs\n%s" % (label, d[:1500]))
        if tree_o != tree_n:
            only = sorted(set(tree_o) ^ set(tree_n))
            changed = sorted(k for k in set(tree_o) & set(tree_n) if tree_o[k] != tree_n[k])
            detail = ""
            if changed:
                import difflib
                k = changed[0]
                detail = "\n".join(difflib.unified_diff(tree_o[k].splitlines(), tree_n[k].splitlines(), "before", "now", lineterm=""))[:1200]
            problems.append("%s: claims tree differs: only in one %s, changed %s\n%s" % (label, only[:6], changed[:6], detail))
    return problems


def run(keep=False):
    """Both engines through the scenario; returns (steps, problems)."""
    tmp = Path(tempfile.mkdtemp(prefix="uak-claims-diff-")).resolve()
    try:
        bash, git = resolve_binary("bash"), resolve_binary("git")
        probe = Runner(ROOT / "kit", tmp, bash, git)
        old_kit = old_package(probe, tmp / "old-src")
        results = {}
        for name, package in (("o", old_kit), ("n", (ROOT / "kit").resolve())):
            (tmp / name).mkdir()
            results[name] = scenario(Runner(package, tmp / name, bash, git))
        return len(results["n"]), compare(results["o"], results["n"])
    finally:
        if keep:
            print("kept: " + str(tmp))
        else:
            import shutil
            shutil.rmtree(str(tmp), ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--keep", action="store_true", help="keep the fixtures (their path is printed)")
    args = parser.parse_args()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    steps, problems = run(args.keep)
    for p in problems:
        print("DIFF " + p)
    print("CLAIMS_DIFF %s steps=%d differences=%d (old %s)" % ("PASS" if not problems else "FAIL", steps, len(problems), OLD[:7]))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
