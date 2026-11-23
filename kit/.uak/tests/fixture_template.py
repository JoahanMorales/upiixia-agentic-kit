"""A fixture built once per test file and copied for each case (UAK-152).

Why: on the Windows runners a case spent most of its time building its repositories (a copy of the engine, `git init`,
`add`, `commit`, `push`, `clone`, `worktree add`: about a dozen processes at 0.2 to 0.5 s each), and the contributed
test files build one per case. A template is built the normal way at a scratch path of its own; a case copies it to its
own path and rewrites the absolute paths that Git keeps in small text files (`.git/config`, `gitdir`, the `.git`
pointer of a worktree). No process runs, and every case still has its own copy to change.

Not a test file (smoke and CI only run `test_*.py`)."""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

_ROOT = []
_BUILT = {}


def template_root():
    if not _ROOT:
        _ROOT.append(Path(tempfile.mkdtemp(prefix="uak-template-")))
        atexit.register(shutil.rmtree, str(_ROOT[0]), True)
    return _ROOT[0]


def _forms(path):
    path = Path(path)
    return {str(path), path.as_posix()}


def _rewrite(top, old, new):
    """Replace the old path with the new one in the small text files Git keeps under every `.git` and in `.git` files."""
    pairs = []
    for o in sorted(_forms(old), key=len, reverse=True):
        pairs.append((o.encode("utf-8"), (str(new) if "\\" in o else new.as_posix()).encode("utf-8")))
    for dirpath, dirnames, filenames in os.walk(str(top)):
        parts = Path(dirpath).relative_to(top).parts
        inside_git = ".git" in parts or any(p.endswith(".git") for p in parts)
        if "objects" in dirnames:
            dirnames.remove("objects")
        for name in filenames:
            if not (inside_git or name == ".git"):
                continue
            p = os.path.join(dirpath, name)
            try:
                if os.path.getsize(p) > 65536:
                    continue
                data = open(p, "rb").read()
            except OSError:
                continue
            changed = data
            for o, n in pairs:
                changed = changed.replace(o, n)
            if changed != data:
                open(p, "wb").write(changed)


def relocate(src, dst, old=None, new=None):
    """Copy the folder `src` to `dst` (which may exist) and point the copy's Git files at `dst`; `old` and `new` are the
    paths to swap (default: src and dst)."""
    src, dst = Path(src), Path(dst)
    shutil.copytree(str(src), str(dst), symlinks=True, dirs_exist_ok=True)
    _rewrite(dst, Path(old or src), Path(new or dst))


def built(key, build):
    """The template for `key`, built once by `build(folder)` in a folder of its own; returns that folder."""
    if key not in _BUILT:
        folder = Path(tempfile.mkdtemp(prefix="t-", dir=str(template_root())))
        _BUILT[key] = (folder, build(folder))
    return _BUILT[key]


def copy_of(folder, dst):
    """`folder` copied into `dst`, Git files rewritten; the case's paths are the template's with `folder` swapped."""
    relocate(folder, dst)


def cached_fixture(r, name, **kwargs):
    """`r.fixture(name, **kwargs)` (test_hack.Runner) from a template built once per set of arguments."""
    key = ("hack", str(r.package), repr(sorted(kwargs.items())))
    folder, template = built(key, lambda f: r.fixture(str(f / "fx"), **kwargs))
    base = r.scratch / name
    relocate(folder / "fx", base)
    fixture = object.__new__(type(template))
    old = folder / "fx"

    def move(value):
        if isinstance(value, Path):
            try:
                return base / value.relative_to(old)
            except ValueError:
                return value
        if isinstance(value, list):
            return [move(v) for v in value]
        return value
    for attr, value in vars(template).items():
        setattr(fixture, attr, move(value))
    fixture.r = r
    return fixture

