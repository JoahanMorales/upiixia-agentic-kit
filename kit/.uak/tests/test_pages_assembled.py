#!/usr/bin/env python3
"""UAK-200: the dashboard (dash.html) and the setup wizard (setup.html) are assembled from parts in pages/ by
scripts/gen_pages.py, so two tasks can work on a page at once. Why (plan "visual setup", 2026-11-23 to 25): every task
listed dash.html or setup.html, the protocol refuses two live claims on one path, so the tasks of a page ran one at a time
(`uak metrics`: 28 tasks integrated on 2026-11-21, 8 a day on the 24th and 25th). The first rule of the split: the generated
pages are byte for byte the pages of main at the task's base. Real files, real scripts/gen_pages.py, real Git in a scratch
fixture (git -C only, no inherited GIT_*), real install.sh, no network."""
import argparse
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "gen_pages.py"
BASE = "9658274928f3ec1a4e80bb217d118c6d5a8cce55"  # origin/main when UAK-200 began
# The pages of that commit, as sha256 of their bytes: what "the pages of today" means, and the one place it is written.
BASE_PAGES = {
    "dash": ("kit/.uak/bin/lib/dash.html", "1ba4b81131f374674450b0e7b2aa19e2bee99381e5eed7c2711406fbfedaa5c7"),
    "setup": ("kit/.uak/bin/lib/setup.html", "b8b85828283918e6109d2f2775ed29814d9d90675cdd1ae2f861dd8713ebaf36"),
}


def gen():
    spec = importlib.util.spec_from_file_location("gen_pages_under_test", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean_env(r):
    e = r.env.copy()
    for k in list(e):
        if k.startswith("GIT_") and k not in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_COUNT") and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            e.pop(k)
    return e


def git(r, repo, *args, allowed=(0,)):
    out = subprocess.run([r.git, "-C", str(repo), *map(str, args)], capture_output=True, text=True, errors="replace",
                         env=clean_env(r), timeout=120, stdin=subprocess.DEVNULL)
    expect(out.returncode in allowed, "git %s failed (%s): %s %s" % (" ".join(map(str, args)), out.returncode, out.stdout[-400:], out.stderr[-400:]))
    return out


def scratch_root(r, name):
    """A copy of the generator, the parts and the two pages in the layout of the repository: a root of its own."""
    root = r.scratch / name
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPT, root / "scripts" / "gen_pages.py")
    expect((REPO / "pages/dash/css-board.css").is_file(), "pages/dash holds the dashboard's parts")
    shutil.copytree(REPO / "pages", root / "pages")
    (root / "kit/.uak/bin/lib").mkdir(parents=True)
    for rel, _digest in BASE_PAGES.values():
        shutil.copy2(REPO / rel, root / rel)
    return root


def run_gen(root, *args, cwd=None):
    return subprocess.run([sys.executable, str(root / "scripts" / "gen_pages.py"), *args], capture_output=True, text=True,
                          errors="replace", cwd=str(cwd or root), timeout=120, stdin=subprocess.DEVNULL)


def order(root, page):
    return gen().parse_order((root / "pages" / page / "ORDER").read_text(encoding="utf-8"))


def parts_of(root):
    return [(page, name) for page in ("dash", "setup") for name in order(root, page)]


def other_eol(b):
    """The part with the line endings the other parts do not have (CRLF on a checkout of LF, LF on a CRLF checkout)."""
    return b.replace(b"\r\n", b"\n") if b"\r\n" in b else b.replace(b"\n", b"\r\n")


def flip_first_byte(path):
    b = bytearray(path.read_bytes())
    i = next(n for n, c in enumerate(b) if c not in (10, 13))
    b[i] = ord("Y") if b[i] != ord("Y") else ord("Z")
    path.write_bytes(bytes(b))


def split_commit_parts(r, page):
    """The parts of a page as the commit that first added pages/PAGE/ORDER has them (the split), or the working tree's when
    that commit does not exist yet (the task is not committed)."""
    log = git(r, REPO, "log", "--diff-filter=A", "--format=%H", "--", "pages/%s/ORDER" % page).stdout.split()
    if not log:
        return None, lambda rel: (REPO / "pages" / rel).read_bytes()
    sha = log[-1]

    def read(rel):
        out = subprocess.run([r.git, "-C", str(REPO), "show", "%s:pages/%s" % (sha, rel)], capture_output=True, env=clean_env(r),
                             timeout=60, stdin=subprocess.DEVNULL)
        if out.returncode:
            raise KeyError(rel)
        return out.stdout
    return sha, read


def generated_pages_equal_the_pages_of_today(r):
    g = gen()
    shown = []
    for page, (rel, digest) in BASE_PAGES.items():
        if subprocess.run([r.git, "-C", str(REPO), "cat-file", "-e", BASE + ":" + rel], capture_output=True, env=clean_env(r)).returncode == 0:
            base = subprocess.run([r.git, "-C", str(REPO), "show", BASE + ":" + rel], capture_output=True, env=clean_env(r)).stdout
            expect(hashlib.sha256(base).hexdigest() == digest, "the pinned digest of %s is the page on main at the base %s" % (rel, BASE[:8]))
        sha, read = split_commit_parts(r, page)
        data, _layout, found = g.assemble(REPO, read)
        expect(not found, "the split commit's parts of %s are well formed: %s" % (page, found))
        expect(hashlib.sha256(data[page]).hexdigest() == digest,
               "the parts that first made %s (commit %s) join into the page of main at the base, byte for byte" % (page, (sha or "working tree")[:8]))
        shown.append("%s %d bytes" % (page, len(data[page])))
    # and the pages in the tree are what the parts give today
    expect(not g.problems(REPO), "the pages in the tree are what their parts give: %s" % g.problems(REPO))
    return "; ".join(shown)


def check_names_the_part_that_differs(r):
    g = gen()
    root = scratch_root(r, "names")
    expect(not g.problems(root), "the scratch copy starts consistent")
    count = 0
    for page, name in parts_of(root):
        part = root / "pages" / name
        original = part.read_bytes()
        flip_first_byte(part)
        found = g.problems(root)
        expect(any(("pages/" + name) in f and "differs from its parts" in f for f in found if g.TARGETS[page] in f),
               "a changed byte of %s is named: %s" % (name, found[:3]))
        part.write_bytes(original)
        count += 1
    out = run_gen(root, "--check", cwd=root.parent)  # run from another directory
    expect(out.returncode == 0 and "ok" in out.stdout, "check is ok again, from another directory: %s %s" % (out.stdout, out.stderr))
    flip_first_byte(root / "pages/dash/js-14-tokens.js")
    out = run_gen(root, "--check", cwd=root.parent)
    expect(out.returncode == 1 and "pages/dash/js-14-tokens.js line 1" in out.stderr, "the command names the part and its line: " + out.stderr)
    expect(out.stderr.count("pages/") >= 1 and "pages/dash/js-13-share.js" not in out.stderr, "and not its neighbours")
    out = run_gen(root, cwd=root.parent)
    expect(out.returncode == 0, "regenerating works: " + out.stderr)
    expect(run_gen(root, "--check").returncode == 0, "and the check is ok after")
    return "%d parts mutated" % count


def hand_edit_of_a_generated_page_is_refused(r):
    root = scratch_root(r, "hand")
    page = root / "kit/.uak/bin/lib/dash.html"
    original = page.read_bytes()
    cut = original.index(b"function memory(v, d) {") + 5  # inside js-12-memory.js
    page.write_bytes(original[:cut] + b"X" + original[cut + 1:])
    out = run_gen(root, "--check")
    expect(out.returncode == 1, "a hand edit fails the check")
    expect("never edited by hand" in out.stderr and "edit pages/dash/js-12-memory.js" in out.stderr and "python3 scripts/gen_pages.py" in out.stderr,
           "with the sentence that says which part to edit: " + out.stderr)
    # appended at the end and removed from the end: still a named part (the last one)
    page.write_bytes(original + b"<!-- x -->\n")
    out = run_gen(root, "--check")
    expect(out.returncode == 1 and "pages/dash/03-end.html" in out.stderr, "an addition at the end names the last part: " + out.stderr)
    page.write_bytes(original[:-10])
    out = run_gen(root, "--check")
    expect(out.returncode == 1 and "pages/dash/03-end.html" in out.stderr, "a page cut short names the last part: " + out.stderr)
    page.unlink()
    out = run_gen(root, "--check")
    expect(out.returncode == 1 and "is missing" in out.stderr, "a missing page is refused: " + out.stderr)
    # the generator then writes the page the parts give, and nothing else changes
    out = run_gen(root)
    expect(out.returncode == 0 and page.read_bytes() == original, "regenerating restores the page byte for byte")
    # the pages carry no mark: no sentence about generation lives in them
    for rel, _d in BASE_PAGES.values():
        expect(b"gen_pages" not in (REPO / rel).read_bytes(), "%s carries no marker of its generation" % rel)
    return "refused with the part named"


def shared_block_comes_from_one_part(r):
    g = gen()
    shared = REPO / "pages/shared/system.css"
    expect(shared.is_file(), "the design system block is one shared part")
    dash, setup = order(REPO, "dash"), order(REPO, "setup")
    expect("shared/system.css" in dash and "shared/system.css" in setup, "both pages list it")
    holders = [p for p in sorted((REPO / "pages").rglob("*")) if p.is_file() and b"uak-system:begin" in p.read_bytes()]
    expect([h.relative_to(REPO / "pages").as_posix() for h in holders] == ["shared/system.css"], "no other part carries the block: %s" % holders)
    body = shared.read_bytes()
    for rel, _d in BASE_PAGES.values():
        expect(body in (REPO / rel).read_bytes(), "%s carries the shared part's bytes" % rel)
    # the same look script: also once
    expect("shared/look.js" in dash and "shared/look.js" in setup, "the look script is shared too")
    # a second copy of the block in a part is refused; so is a copy that differs by a byte
    root = scratch_root(r, "shared")
    part = root / "pages/dash/css-board.css"
    part.write_bytes(shared.read_bytes() + part.read_bytes())
    found = g.problems(root)
    expect(any("design system block" in f for f in found), "a duplicate of the block is refused: %s" % found)
    shutil.copy2(REPO / "pages/dash/css-board.css", part)
    (root / "pages/dash/css-board.css").write_bytes(part.read_bytes())
    order_file = root / "pages/setup/ORDER"
    text = order_file.read_text(encoding="utf-8")
    (root / "pages/setup/system-copy.css").write_bytes(body.replace(b"--ink", b"--INK", 1))
    order_file.write_text(text.replace("shared/system.css", "setup/system-copy.css"), encoding="utf-8")
    found = g.problems(root)
    expect(any("design system block" in f for f in found), "two copies that differ by a byte are refused, not unified: %s" % found)
    return "the block is in one part, %d bytes" % len(body)


def two_tasks_on_one_page_merge(r):
    fixture = r.scratch / "merge-fixture"
    fixture.mkdir()
    git(r, fixture, "init", "-q", "-b", "main")
    expect((REPO / "pages/dash/css-board.css").is_file(), "pages/dash holds the dashboard's parts")
    shutil.copytree(REPO / "pages", fixture / "pages")
    (fixture / "scripts").mkdir()
    shutil.copy2(SCRIPT, fixture / "scripts/gen_pages.py")
    (fixture / "kit/.uak/bin/lib").mkdir(parents=True)
    for rel, _d in BASE_PAGES.values():
        shutil.copy2(REPO / rel, fixture / rel)
    ident = ["-c", "user.name=Ana", "-c", "user.email=ana@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
    git(r, fixture, "add", "-A")
    git(r, fixture, *ident, "commit", "-q", "-m", "base")
    page = fixture / "kit/.uak/bin/lib/dash.html"

    def task(branch, part, old, new):
        git(r, fixture, "checkout", "-q", "-b", branch, "main")
        p = fixture / "pages/dash" / part
        raw = p.read_bytes()  # bytes: a CRLF checkout (Windows) keeps its line endings
        expect(raw.count(old.encode()) == 1, "%s holds %r once" % (part, old))
        p.write_bytes(raw.replace(old.encode(), new.encode()))
        out = run_gen(fixture)
        expect(out.returncode == 0, "the generator runs in the branch: " + out.stderr)
        git(r, fixture, "add", "-A")
        git(r, fixture, *ident, "commit", "-q", "-m", branch)
        git(r, fixture, "checkout", "-q", "main")
    # two tasks, two parts of the same page: each lists its part, never the generated page
    task("task-board", "css-board.css", "/* Board */", "/* Board (task A) */")
    task("task-tokens", "js-14-tokens.js", "// Tokens: what the data really holds", "// Tokens (task B): what the data really holds")
    for b in ("task-board", "task-tokens"):
        changed = git(r, fixture, "diff", "--name-only", "main", b).stdout.split()
        expect(sorted(c for c in changed if c.startswith("pages/")) == ["pages/dash/css-board.css" if b == "task-board" else "pages/dash/js-14-tokens.js"],
               "each branch changed one part: %s" % changed)
    git(r, fixture, *ident, "merge", "-q", "--no-edit", "task-board")
    git(r, fixture, *ident, "merge", "-q", "--no-edit", "task-tokens")  # a conflict fails here
    merged = page.read_bytes()
    expect(b"/* Board (task A) */" in merged and b"// Tokens (task B)" in merged, "the merged page carries both changes")
    out = run_gen(fixture)
    expect(out.returncode == 0, "the gate's regeneration runs on the merge: " + out.stderr)
    expect(page.read_bytes() == merged, "and gives the page the merge gave, byte for byte")
    expect(git(r, fixture, "status", "--porcelain").stdout.strip() == "", "nothing changed after regenerating")
    expect(run_gen(fixture, "--check").returncode == 0, "the check is ok on the merged result")
    # the same part from two branches is a conflict in the part, where a reviewer can read it
    task("task-a2", "css-board.css", "/* Board (task A) */", "/* Board (A2) */")
    root_commit = git(r, fixture, "rev-list", "--max-parents=0", "main").stdout.split()[0]
    git(r, fixture, "checkout", "-q", "-b", "task-b2", root_commit)
    p = fixture / "pages/dash/css-board.css"
    p.write_bytes(p.read_bytes().replace(b"/* Board */", b"/* Board (B2) */"))
    git(r, fixture, "add", "-A")
    git(r, fixture, *ident, "commit", "-q", "-m", "b2")
    clash = git(r, fixture, *ident, "merge", "--no-edit", "task-a2", allowed=(0, 1))
    expect(clash.returncode == 1 and "pages/dash/css-board.css" in clash.stdout, "two tasks on one part still conflict, in the part: " + clash.stdout[-300:])
    git(r, fixture, "merge", "--abort")
    return "two parts merged, one part conflicts"


def no_part_over_600_lines(r):
    g = gen()
    sizes = {}
    for f in sorted((REPO / "pages").rglob("*")):
        if f.is_file() and f.name != "ORDER":
            sizes[f.relative_to(REPO / "pages").as_posix()] = f.read_bytes().count(b"\n")
    big = {k: v for k, v in sizes.items() if v > g.MAX_LINES}
    expect(not big, "parts over %d lines: %s" % (g.MAX_LINES, big))
    root = scratch_root(r, "big")
    part = root / "pages/dash/css-board.css"
    original = part.read_bytes()
    filler = b"/* filler */\n"
    part.write_bytes(original + filler * (600 - original.count(b"\n")))
    expect(not [f for f in g.assemble(root)[2] if "lines" in f], "600 lines are allowed")
    part.write_bytes(original + filler * (601 - original.count(b"\n")))
    found = [f for f in g.assemble(root)[2] if "lines" in f]
    expect(len(found) == 1 and "pages/dash/css-board.css" in found[0] and "601" in found[0], "601 lines are refused, naming the part: %s" % found)
    return "largest part %d lines, %d parts" % (max(sizes.values()), len(sizes))


def broken_parts_are_refused(r):
    g = gen()
    root = scratch_root(r, "broken")

    def problems_with(change):
        fresh = scratch_root(r, "broken-%d" % problems_with.n)
        problems_with.n += 1
        change(fresh)
        return g.assemble(fresh)[2]
    problems_with.n = 0
    found = problems_with(lambda x: (x / "pages/dash/css-board.css").unlink())
    expect(any("css-board.css is listed but" in f for f in found), "a part listed but missing: %s" % found)
    found = problems_with(lambda x: (x / "pages/dash/stray.css").write_bytes(b"a\n"))
    expect(any("stray.css" in f and "no ORDER" in f for f in found), "a file in pages/ that no ORDER lists: %s" % found)
    found = problems_with(lambda x: (x / "pages/dash/css-board.css").write_bytes(other_eol((REPO / "pages/dash/css-board.css").read_bytes())))
    expect(any("line endings" in f for f in found), "a part with CRLF among LF parts: %s" % found)
    found = problems_with(lambda x: (x / "pages/dash/css-board.css").write_bytes((REPO / "pages/dash/css-board.css").read_bytes()[:-1]))
    expect(any("css-board.css" in f and "newline" in f for f in found), "a part without a final newline: %s" % found)
    found = problems_with(lambda x: (x / "pages/dash/css-board.css").write_bytes(b""))
    expect(any("is empty" in f for f in found), "an empty part: %s" % found)
    found = problems_with(lambda x: (x / "pages/dash/ORDER").write_text((x / "pages/dash/ORDER").read_text() + "dash/css-board.css\n"))
    expect(any("listed twice" in f for f in found), "a part listed twice: %s" % found)
    found = problems_with(lambda x: (x / "pages/dash/ORDER").write_text((x / "pages/dash/ORDER").read_text() + "../../scripts/gen_pages.py\n"))
    expect(any("not a path under pages/" in f for f in found), "a path that leaves pages/: %s" % found)
    found = problems_with(lambda x: (x / "pages/setup/ORDER").unlink())
    expect(any("pages/setup/ORDER" in f and "cannot be read" in f for f in found), "a missing ORDER: %s" % found)
    # the command exits non-zero and writes nothing when a part is broken
    (root / "pages/dash/css-board.css").unlink()
    before = (root / "kit/.uak/bin/lib/dash.html").read_bytes()
    out = run_gen(root, cwd=root.parent)
    expect(out.returncode == 1 and "css-board.css" in out.stderr and (root / "kit/.uak/bin/lib/dash.html").read_bytes() == before,
           "the generator stops and leaves the page alone: " + out.stderr)
    return "9 failure paths refused"


def parts_are_not_installed(r):
    d = r.scratch / "project"
    d.mkdir()
    git(r, d, "init", "-q", "-b", "main")
    e = clean_env(r)
    e["UAK_EXTERNAL_SKILLS"] = "off"
    out = subprocess.run([r.bash, str(r.package.parent / "install.sh"), "--mode", "sprint", str(d)], capture_output=True, text=True,
                         errors="replace", env=e, timeout=240, stdin=subprocess.DEVNULL)
    expect(out.returncode == 0, "install failed: " + out.stdout[-400:] + out.stderr[-400:])
    placed = [p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and ".git" not in p.relative_to(d).parts]
    parts = {p.name for p in (REPO / "pages").rglob("*") if p.is_file()} - {"ORDER"}
    expect(len(parts) > 40, "the kit's repository has its parts to leave out (%d)" % len(parts))
    expect(not (d / "pages").exists(), "no pages/ folder in a project")
    expect(not [p for p in placed if p.startswith("pages/") or p.split("/")[-1] == "gen_pages.py"], "no part and no generator in a project")
    expect(not [p for p in placed if "/" + "ORDER" in "/" + p and "pages" in p], "no ORDER file in a project")
    expect("scripts/gen_pages.py" not in placed, "no scripts/ folder of the kit's repository")
    for rel, digest in BASE_PAGES.values():
        inst = d / rel.replace("kit/", "", 1)
        expect(inst.is_file() and inst.read_bytes() == (REPO / rel).read_bytes(), "the generated page %s is installed whole" % inst.name)
    named = [p for p in placed if p.rsplit("/", 1)[-1] in parts and p.startswith("pages")]
    expect(not named, "no part name among the installed files: %s" % named)
    # and the installer never copies from pages/ on purpose: it names kit/ only
    script = (REPO / "install.sh").read_text(encoding="utf-8")
    expect("pages/" not in script, "install.sh does not mention pages/")
    # a part inside kit/ would be installed: the lint-side rule is that parts live outside it
    expect(not (REPO / "kit/pages").exists() and not list((REPO / "kit").rglob("ORDER")), "no part or ORDER under kit/")
    return "%d files installed, none of pages/" % len(placed)


TESTS = [generated_pages_equal_the_pages_of_today, check_names_the_part_that_differs, hand_edit_of_a_generated_page_is_refused,
         shared_block_comes_from_one_part, two_tasks_on_one_page_merge, no_part_over_600_lines, broken_parts_are_refused,
         parts_are_not_installed]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-pages-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ not in args.case:
                continue
            started = time.monotonic()
            try:
                note = test(runner)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started))
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("PAGES_ASSEMBLED_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
