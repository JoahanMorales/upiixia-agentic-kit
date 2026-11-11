#!/usr/bin/env python3
"""UAK-066: design-lint counts CSS custom properties inside an .html file's <style> as design tokens, so a folder of
static pages (a design round: .uak/design/rounds/R<k>/v*/index.html) is not skipped with "no design tokens yet" and
its scale warnings (UAK-061) run, each finding naming the variant. Why (AXIA R1, Nov 2026): design-lint skipped all six
variants of the first real round because their tokens live in <style>. The real R2 of AXIA is checked too when present."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

REAL_R2 = Path("/home/joahan/Proyectos/design-rounds/axia/.uak/design/rounds/R2")
PAGE = "<!doctype html>\n<html><head><style>\n:root{--ink:#111;--paper:#fff}\n%s\n</style></head><body><h1>x</h1></body></html>\n"


def rounds(r, name, variants):
    t = r.scratch / ("dh-" + name)
    t.mkdir(parents=True)
    r.g(t, "init", "-q", "-b", "main")
    for v, css in variants.items():
        d = t / ".uak/design/rounds/R1" / v
        d.mkdir(parents=True)
        (d / "index.html").write_text(PAGE % css, encoding="utf-8")
    return t


def lint(r, t, *args):
    return r.run([r.bash, str(r.package / ".uak/bin/design-lint"), *args], cwd=t, allowed=None)


def warns(out):
    return [l for l in out.stdout.splitlines() if l.startswith("DESIGN_LINT_WARN")]


def html_style_tokens_count(r):
    t = rounds(r, "tok", {"v1": "h1{font-size:40px}"})
    out = lint(r, t, ".uak/design/rounds/R1")
    expect("DESIGN_LINT_SKIP" not in out.stdout and "DESIGN_LINT_PASS" in out.stdout, "tokens in <style> count: rc %d %s" % (out.returncode, out.stdout))
    # a page with no custom property and no stylesheet token is still a skip
    t2 = r.scratch / "dh-none"
    (t2 / "pages/v1").mkdir(parents=True)
    r.g(t2, "init", "-q", "-b", "main")
    (t2 / "pages/v1/index.html").write_text("<html><style>h1{font-size:40px}</style></html>\n", encoding="utf-8")
    o2 = lint(r, t2, "pages")
    expect("DESIGN_LINT_SKIP" in o2.stdout, "no tokens anywhere is still a skip: " + o2.stdout)
    # a custom property outside <style> (prose in the body) is not a token
    (t2 / "pages/v1/index.html").write_text("<html><body><p>use --ink: #111 here</p></body></html>\n", encoding="utf-8")
    expect("DESIGN_LINT_SKIP" in lint(r, t2, "pages").stdout, "only <style> counts")
    return "style tokens count"


def round_folder_lints_each_variant(r):
    t = rounds(r, "each", {"v1": "h1{font-size:168px}", "v2": "h1{font-size:60px}", "v3": ".hero{font-size:7rem}", "v4": "h1{font-size:12vw}"})
    out = lint(r, t, ".uak/design/rounds/R1")
    expect(out.returncode == 0 and "DESIGN_LINT_PASS" in out.stdout, "warnings do not fail: rc %d %s" % (out.returncode, out.stdout))
    for v in ("v1", "v3"):
        expect(any(v + "/index.html" in l and "96 px" in l for l in warns(out)), "%s warns: %s" % (v, out.stdout))
    expect(not any("v2/index.html" in l or "v4/index.html" in l for l in warns(out)), "v2 and v4 are inside the bounds: " + out.stdout)
    expect("files=4" in out.stdout, "the pass line counts the four pages: " + out.stdout)
    return "v1 and v3 warned"


def scale_warning_names_the_variant(r):
    t = rounds(r, "name", {"v1": "p{font-size:16px}", "v2": "h1{font-size:200px}"})
    out = lint(r, t, ".uak/design/rounds/R1")
    ws = warns(out)
    expect(len(ws) == 1 and ".uak/design/rounds/R1/v2/index.html:" in ws[0], "one warning, naming R1/v2: " + out.stdout)
    strict = lint(r, t, ".uak/design/rounds/R1", "--strict")
    expect(strict.returncode == 1 and "R1/v2/index.html" in strict.stdout, "--strict fails on it: " + strict.stdout)
    if REAL_R2.is_dir():
        # the six real variants of AXIA R2 plus its pick.html, read-only: linted where they live, with no skip
        root = REAL_R2.parents[3]
        real = lint(r, root, ".uak/design/rounds/R2")
        expect("DESIGN_LINT_SKIP" not in real.stdout and "DESIGN_LINT_PASS" in real.stdout and "files=7" in real.stdout, "real R2 runs: rc %d %s" % (real.returncode, real.stdout))
    return "named"


TESTS = [html_style_tokens_count, round_folder_lints_each_variant, scale_warning_names_the_variant]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-html-") as tmp:
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
    print("DESIGN_LINT_HTML_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
