#!/usr/bin/env python3
"""UAK-028: the design-lock gallery the kit generates (design-lock/index.html) had `kbd { color: #1d1f1c }` outside :root,
so design-lint refused `done` for a hex in the kit's own page (DevDay hackathon). Every color outside :root is now a
var(--token). Real git repo in a temp dir."""
import argparse
import re
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000" "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def generated_gallery_passes_design_lint(r):
    t = r.scratch / "gl-repo"
    (t / "web/src").mkdir(parents=True)
    d = t / "web/public/design-lock"
    d.mkdir(parents=True)
    r.g(t, "init", "-q", "-b", "main")
    (t / "web/src/index.css").write_text(":root{--a:#fff}\n", encoding="utf-8")
    for name in ("1-1280.png", "1-390.png"):
        (d / name).write_bytes(PNG)
    gal = r.run([r.bash, str(r.package / ".uak/bin/design-gallery"), "--no-open"], cwd=t, allowed=None)
    expect(gal.returncode == 0, "design-gallery should succeed, rc %d" % gal.returncode)
    page = (d / "index.html").read_text(encoding="utf-8")
    outside = []
    depth_root = False
    for n, line in enumerate(page.splitlines(), 1):
        if re.search(r":root\s*\{", line):
            depth_root = True
        if not depth_root and re.search(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?([^0-9A-Za-z_]|$)", line) and not re.search(r"href=|src=|url\(#", line):
            outside.append(n)
        if depth_root and "}" in line:
            depth_root = False
    expect(not outside, "hex colors outside :root in the generated page, lines %s" % outside)
    lint = r.run([r.bash, str(r.package / ".uak/bin/design-lint")], cwd=t, allowed=None)
    expect(lint.returncode == 0 and "DESIGN_LINT_PASS" in lint.stdout, "design-lint on the generated gallery: expected DESIGN_LINT_PASS, got rc %d" % lint.returncode)
    return "DESIGN_LINT_PASS"


TESTS = [generated_gallery_passes_design_lint]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="uak-gallery-lint-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ != args.case:
                continue
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("GALLERY_LINT_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
