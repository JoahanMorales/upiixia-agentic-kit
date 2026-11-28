#!/usr/bin/env python3
"""gen_pages: the dashboard and the setup wizard are each one HTML file, assembled from parts in pages/.

    python3 scripts/gen_pages.py            # rewrite kit/.uak/bin/lib/dash.html and setup.html from the parts
    python3 scripts/gen_pages.py --check    # exit 1 when a generated page differs from its parts (CI, kit_lint)

pages/dash/ORDER and pages/setup/ORDER list the parts of each page, one path (relative to pages/) per line, in the order
they are joined; blank lines and lines starting with # are comments. The page is the plain concatenation of the bytes of
its parts: no template, no marker, no whitespace changes. A part that both pages carry byte for byte (the design system
block, the look script) lives once, in pages/shared/, and both ORDER files list it. A page nobody wrote by hand carries
nothing that says so; when it differs from its parts, --check names the part that holds the first differing byte.
pages/ is not part of the kit (install.sh copies kit/ only): whoever installs or uses the kit gets the two files and no build.
Why (UAK-200, plan "visual setup", 2026-11-23 to 25): every task listed dash.html or setup.html, and the protocol refuses two
live claims on one path, so the tasks of a page ran one at a time. A task now lists the parts it edits; the gate regenerates
the page (Generated: in .uak/PROJECT.md).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"dash": "kit/.uak/bin/lib/dash.html", "setup": "kit/.uak/bin/lib/setup.html"}
MAX_LINES = 600
SHARED_MARK = b"uak-system:begin"
REGEN = "python3 scripts/gen_pages.py"


def parse_order(text):
    """The parts an ORDER text lists, in order."""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def assemble(root, read=None):
    """({page: bytes}, {page: [(part, start_offset, length)]}, problems) for the parts under root/pages.

    read(relpath) -> bytes lets a caller read the parts from somewhere else (a commit); None reads the files."""
    root = Path(root)
    pages_dir = root / "pages"
    disk = read is None
    read = read or (lambda rel: (pages_dir / rel).read_bytes())
    found, data, layout, listed, marked = [], {}, {}, set(), {}
    for page in TARGETS:
        try:
            names = parse_order(read(page + "/ORDER").decode("utf-8"))
        except (OSError, KeyError, UnicodeDecodeError) as e:
            found.append("pages/%s/ORDER · cannot be read (%s)" % (page, e.__class__.__name__))
            continue
        if not names:
            found.append("pages/%s/ORDER · lists no part" % page)
            continue
        out, spans, seen, eols = b"", [], set(), set()
        for name in names:
            p = Path(name)
            if p.is_absolute() or ".." in p.parts or name.endswith("ORDER") or name.startswith("/"):
                found.append("pages/%s/ORDER · %s is not a path under pages/" % (page, name))
                continue
            if name in seen:
                found.append("pages/%s/ORDER · %s is listed twice" % (page, name))
                continue
            seen.add(name)
            try:
                b = read(name)
            except (OSError, KeyError):
                found.append("pages/%s/ORDER · %s is listed but pages/%s does not exist" % (page, name, name))
                continue
            listed.add(name)
            if SHARED_MARK in b:
                marked.setdefault(name, []).append(page)
            if not b:
                found.append("pages/%s · is empty (remove it from the ORDER or give it its text)" % name)
            elif not b.endswith(b"\n"):
                found.append("pages/%s · does not end with a newline (a part is whole lines, so parts join without a glue)" % name)
            crlf, lf = b.count(b"\r\n"), b.count(b"\n") - b.count(b"\r\n")
            if crlf and lf:
                found.append("pages/%s · mixes CRLF and LF line endings" % name)
            elif b:
                eols.add("crlf" if crlf else "lf")
            if b.count(b"\n") > MAX_LINES:
                found.append("pages/%s · has %d lines, more than %d: split it by area and list both parts in pages/%s/ORDER"
                             % (name, b.count(b"\n"), MAX_LINES, page))
            spans.append((name, len(out), len(b)))
            out += b
        if len(eols) > 1:
            found.append("pages/%s/ORDER · its parts do not all use the same line endings" % page)
        data[page], layout[page] = out, spans
    if len(marked) != 1 or any(len(v) != len(TARGETS) for v in marked.values()):
        found.append("pages · the design system block (uak-system:begin) must live in one shared part that both ORDER files list; found in %s"
                     % ", ".join("%s (%s)" % (k, " ".join(v)) for k, v in sorted(marked.items())))
    if disk and pages_dir.is_dir():
        for f in sorted(pages_dir.rglob("*")):
            rel = f.relative_to(pages_dir).as_posix()
            if f.is_file() and rel not in listed and rel not in {p + "/ORDER" for p in TARGETS}:
                found.append("pages/%s · is in no ORDER (list it in the page that carries it, or delete it)" % rel)
    return data, layout, found


def locate(layout, generated, wanted):
    """The part that holds the first byte where the generated page and what the parts give differ, and its line."""
    n = 0
    for n, (a, b) in enumerate(zip(generated, wanted)):
        if a != b:
            break
    else:
        n = min(len(generated), len(wanted))
    for name, start, length in layout:
        if start <= n < start + length:
            return name, wanted.count(b"\n", start, n) + 1, n
    name, start, length = layout[-1]
    return name, wanted.count(b"\n", start) + 1, n


def problems(root=ROOT):
    """What kit_lint and --check report: the parts' own defects, then a generated page that differs from them."""
    root = Path(root)
    data, layout, found = assemble(root)
    for page, wanted in data.items():
        target = root / TARGETS[page]
        if not target.is_file():
            found.append("%s · is missing: run %s" % (TARGETS[page], REGEN))
            continue
        have = target.read_bytes()
        if have != wanted:
            part, line, n = locate(layout[page], have, wanted)
            found.append("%s · differs from its parts at byte %d, in pages/%s line %d: a generated page is never edited by hand; edit pages/%s and run %s"
                         % (TARGETS[page], n, part, line, part, REGEN))
    return found


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    check = "--check" in argv
    if [a for a in argv if a != "--check"]:
        print("usage: python3 scripts/gen_pages.py [--check]", file=sys.stderr)
        return 2
    if check:
        found = problems()
        for f in found:
            print("gen_pages: " + f, file=sys.stderr)
        print("gen_pages --check: %s" % ("ok" if not found else "%d problem(s)" % len(found)))
        return 1 if found else 0
    data, layout, found = assemble(ROOT)
    if found:
        for f in found:
            print("gen_pages: " + f, file=sys.stderr)
        return 1
    for page, b in data.items():
        (ROOT / TARGETS[page]).write_bytes(b)
        print("wrote %s (%d parts, %d bytes)" % (TARGETS[page], len(layout[page]), len(b)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
