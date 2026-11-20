#!/usr/bin/env python3
"""UAK-090: the black box harvest finds repos with `gh search code TEXT --filename NAME`.
Why (2026-11-20): `gh search code "path:.uak filename:PROJECT.md Mode"` returns nothing; the weekly workflow was green
and never opened an issue. The module's gh() is replaced by a recorder (no `gh`, no network, no shell stub on PATH:
a stub would need a .cmd on Windows)."""
import argparse
import base64
import importlib.util
import io
import json
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from test_hack import expect

REPO = Path(__file__).resolve().parents[3]
KIT_LINE = "- 2026-11-10T10:00Z | v6.4 | claude | kit | auto | error | uak claim | boom | fix: -"


def harvest():
    p = REPO / "scripts" / "blackbox_harvest.py"
    if not p.is_file():
        return None
    spec = importlib.util.spec_from_file_location("blackbox_harvest_under_test", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stub(mod, found, files, error=""):
    """found: {filename: [repos]}; files: {(repo, path): text}. Returns the recorded gh calls."""
    calls = []

    def fake(*args):
        calls.append(args)
        if args[:2] == ("search", "code"):
            mod.GH_ERROR = error
            names = found.get(args[args.index("--filename") + 1] if "--filename" in args else "", [])
            return json.dumps([{"repository": {"nameWithOwner": n}} for n in names])
        if args[0] == "api":
            url = args[1].split("?")[0]
            _, _, rest = url.partition("repos/")
            repo = "/".join(rest.split("/")[:2])
            path = rest.split("/", 3)[3]
            text = files.get((repo, path))
            if text is None:
                return ""
            return json.dumps({"content": base64.b64encode(text.encode()).decode()})
        return ""
    mod.gh = fake
    return calls


def run_main(mod, out, extra=()):
    old = mod.sys.argv
    mod.sys.argv = ["blackbox_harvest.py", "--out", str(out), *extra]
    o, e = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(o), redirect_stderr(e):
            code = mod.main()
    finally:
        mod.sys.argv = old
    return code, o.getvalue(), e.getvalue()


def discovery_uses_filename_flag(mod, tmp):
    calls = stub(mod, {"PROJECT.md": ["a/one"], "BLACKBOX.md": ["b/two"]}, {("a/one", ".uak/BLACKBOX.md"): KIT_LINE})
    run_main(mod, tmp / "r1.md")
    searches = [c for c in calls if c[:2] == ("search", "code")]
    expect(len(searches) == 2, "two code searches expected: %r" % (searches,))
    expect(searches[0][2] == "Plan-Channel" and searches[0][3:5] == ("--filename", "PROJECT.md"), "PROJECT.md search: %r" % (searches[0],))
    expect(searches[1][2] == "uak" and searches[1][3:5] == ("--filename", "BLACKBOX.md"), "BLACKBOX.md search: %r" % (searches[1],))
    expect(not any("path:" in a or "filename:" in a for c in searches for a in c), "no qualifiers in the query text")
    return "two searches"


def repos_without_kit_lines_are_dropped(mod, tmp):
    stub(mod, {"PROJECT.md": ["a/with", "c/without"], "BLACKBOX.md": ["c/without"]},
         {("a/with", ".uak/BLACKBOX.md"): KIT_LINE, ("c/without", ".uak/BLACKBOX.md"): "# notes, no kit lines\n"})
    out = tmp / "r2.md"
    code, so, se = run_main(mod, out, ["--show-repos"])
    text = out.read_text(encoding="utf-8")
    expect(code == 0, "exit %s: %s" % (code, se))
    expect("2 scanned, 1 with entries" in text, "counts: " + text[:300])
    expect("a/with" in text and "c/without" not in text, "only the repo with kit lines is kept: " + text[-200:])
    return "dropped"


def empty_discovery_exits_1(mod, tmp):
    stub(mod, {}, {}, error="HTTP 401: Bad credentials")
    out = tmp / "r3.md"
    code, so, se = run_main(mod, out)
    expect(code == 1, "empty discovery must exit 1, got %s" % code)
    expect("HTTP 401: Bad credentials" in se, "gh's error is shown: " + se)
    expect(not out.exists(), "no report for nothing")
    wf = (REPO / ".github" / "workflows" / "blackbox-harvest.yml")
    if wf.is_file():
        expect("::error::" in wf.read_text(encoding="utf-8"), "the workflow step must fail loudly, not end green")
    return "exit 1"


TESTS = [discovery_uses_filename_flag, repos_without_kit_lines_are_dropped, empty_discovery_exits_1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.parse_args()
    if harvest() is None:
        print("PASS skipped (no kit source repository here: scripts/blackbox_harvest.py is not shipped)")
        print("HARVEST_DISCOVERY_RESULT PASS")
        return 0
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak harvést-") as tmp:
        for test in TESTS:
            try:
                print("PASS %s (%s)" % (test.__name__, test(harvest(), Path(tmp))))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("HARVEST_DISCOVERY_RESULT %s" % ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
