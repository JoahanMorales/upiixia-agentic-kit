#!/usr/bin/env python3
"""uak v5.8: the frontend gate reaches every screen. From two frontend audits (Oct 2026): a hackathon whose ten
screens copied the one locked screen (grey panels, striped rows, a bare nav nobody owned), approvals of UI nobody
looked at, and an experiment that followed the kit literally and shipped white on amber at 2.2:1. One test per
fix: design-lint's new checks, the screenshot + critic gate on done, the UI brief at claim, DESIGN.md lint, and
what a sprint install gives a web stack."""
import argparse
import concurrent.futures
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_v57 import set_project

PROJECT = ("Backlog-Approved: yes\nAutonomy: yes\nAuto-Merge: yes\nReview-Mode: claims\nEvents-Per-Session: 100\n"
           "Checkpoint-Percent: 60\nUI-Paths: src/\n")


def lint(r, d, *args):
    return r.run([r.bash, str(r.package / ".uak/bin/design-lint"), *args], cwd=d, allowed=None)


def design_lint_sees_the_tells(r):
    """Side stripes, gradients, color literals, arbitrary pixels, eyebrows, sparkles, Geist, glass, heavy shadows,
    keyed tiles, low-contrast token pairs and hand-typed hex in the lock directions all passed the old lint."""
    d = r.scratch / "v58-lint"
    (d / "web/src/features/a").mkdir(parents=True)
    (d / "web/public/design-lock").mkdir(parents=True)
    r.g(d, "init", "-q")
    (d / "web/src/index.css").write_text(":root{\n  --bg:#ffffff; --surface: var(--bg); --text:#111111;\n"
                                         "  --warn:#f5a524; --warn-ink:#ffffff;\n}\n", encoding="utf-8")
    spark = "✨"
    (d / "web/src/features/a/index.tsx").write_text(
        'import { Geist } from "next/font/google";\n'
        'export const A = () => <div className="border-l-4 p-[13px] shadow-2xl backdrop-blur-md">\n'
        '<p className="bg-gradient-to-r backdrop-blur-sm" style={{color: "rgb(10, 20, 30)"}}>' + spark + '</p>\n'
        '<span className="uppercase tracking-widest">Live</span></div>;\n', encoding="utf-8")
    (d / "web/public/design-lock/1.html").write_text('<style>:root{--bg:#fff}</style>\n<b style="color:#ff0000">146</b>\n'
                                                    '<img src="https://a.basemaps.cartocdn.com/1/1/1.png">\n', encoding="utf-8")
    out = lint(r, d)
    text = out.stdout
    for what in ("side stripe", "gradient", "color literal", "arbitrary value p-[13px]", "eyebrow", "emoji",
                 "Geist", "glass surfaces", "heavy shadow", "contrast --warn-ink on --warn", "hex color outside :root",
                 "tile server"):
        expect(what in text, "design-lint names %s: %s" % (what, text))
    expect(out.returncode == 1, "and fails")
    (d / "web/src/index.css").unlink()
    (d / "web/DESIGN.md").write_text("# DESIGN\n", encoding="utf-8")
    none = lint(r, d)
    expect(none.returncode == 1 and "no stylesheet defines its tokens" in none.stdout, "after the lock, no tokens fails: " + none.stdout)
    return {"tells": 12}


def done_ships_ui_with_what_was_seen(r):
    """Approvals said "UI not walked in browser" and "no 390x844 screenshot"; the critic ran on a few PRs."""
    f = r.fixture("v58-shots", count=1)
    set_project(f, PROJECT)
    f.claim(0, "HACK-001")
    wt = f.worktrees[0]
    (wt / "src").mkdir(exist_ok=True)
    (wt / "src/one.txt").write_text("ui\n", encoding="utf-8")
    f.r.g(wt, "add", "src/one.txt"); f.r.g(wt, "commit", "-q", "-m", "ui"); f.r.g(wt, "push", "-q", "origin", f.branches[0])
    sha = f.r.g(wt, "rev-parse", "--short=7", "HEAD").stdout.strip()
    done = lambda *extra: f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", *extra,
                                 now=1000010, allowed=None)
    bare = done()
    expect(bare.returncode == 3 and "1280.png 390.png critic.txt" in bare.stderr, bare.stdout + bare.stderr)
    shots = wt / ".uak-shots/HACK-001"
    shots.mkdir(parents=True)
    for name in ("1280.png", "390.png"):
        (shots / name).write_bytes(b"\x89PNG fake")
    (shots / "critic.txt").write_text("VERDICT: FIX %s\nwow · hero too small · 48 px\n" % sha, encoding="utf-8")
    fix = done()
    expect(fix.returncode == 3 and "said FIX" in fix.stderr, fix.stdout + fix.stderr)
    (shots / "critic.txt").write_text("VERDICT: SHIP 0000000\n", encoding="utf-8")
    old = done()
    expect(old.returncode == 3 and "another commit" in old.stderr, old.stdout + old.stderr)
    (shots / "critic.txt").write_text("VERDICT: SHIP %s\n" % sha, encoding="utf-8")
    ok = done()
    expect(ok.returncode == 0 and "REVIEW" in ok.stdout, ok.stdout + ok.stderr)
    return {"gate": "shots + critic"}


def a_change_with_nothing_visible_says_why(r):
    """--no-ui records the reason instead of screenshots."""
    f = r.fixture("v58-no-ui", count=1)
    set_project(f, PROJECT)
    f.claim(0, "HACK-001")
    wt = f.worktrees[0]
    (wt / "src").mkdir(exist_ok=True)
    (wt / "src/one.txt").write_text("types only\n", encoding="utf-8")
    f.r.g(wt, "add", "src/one.txt"); f.r.g(wt, "commit", "-q", "-m", "types"); f.r.g(wt, "push", "-q", "origin", f.branches[0])
    ok = f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "tsc", "--no-ui",
                "types only, nothing renders differently", now=1000010)
    expect("no visible change: types only" in f.show("tasks/HACK-001.md"), f.show("tasks/HACK-001.md"))
    return {"no_ui": ok.returncode}


def a_ui_claim_says_what_to_open(r):
    """product-ui reached agents only when its description happened to match; DESIGN.md was read by a few."""
    f = r.fixture("v58-brief", count=1)
    set_project(f, PROJECT)
    out = f.claim(0, "HACK-001")
    expect("UI TASK: before the first line, read web/DESIGN.md" in out.stdout and ".uak-shots/HACK-001/" in out.stdout, out.stdout)
    return {"brief": True}


def lint_wants_a_filled_design_and_recipes(r):
    """The lock had a 15 px body and no screen table, and ten screens copied the one locked screen."""
    f = r.fixture("v58-design-lint", count=1)
    set_project(f, PROJECT)
    tmpl = (r.package / ".uak/templates/DESIGN.template.md").read_text(encoding="utf-8")
    (f.seed / "web").mkdir()
    (f.seed / "web/DESIGN.md").write_text(tmpl, encoding="utf-8")
    f.r.g(f.seed, "add", "web/DESIGN.md"); f.r.g(f.seed, "commit", "-q", "-m", "DESIGN"); f.r.g(f.seed, "push", "-q", "origin", "main")
    out = f.r.run([f.r.bash, ".uak/bin/uak", "lint"], cwd=f.seed, env={"UAK_AGENT": "agent-1", "UAK_NOW": "1000005",
                                                                        "UAK_REMOTE": "origin", "UAK_HUMAN": ""}, allowed=None)
    expect("still has template fields" in out.stderr, out.stdout + out.stderr)
    expect("HACK-001 writes UI but names no recipe" in out.stderr, out.stdout + out.stderr)
    return {"lint": True}


def a_sprint_web_install_sets_the_gate(r):
    """design-taste-frontend (1,206 lines) contradicted product-ui and the lock; the gate needs UI-Paths."""
    d = r.scratch / "v58-install"
    d.mkdir()
    r.g(d, "init", "-q", "-b", "main")
    r.run([r.bash, str(r.package.parent / "install.sh"), "--mode", "sprint", "--stack", "fastapi-react", "--harness", "claude", str(d)], cwd=d)
    expect(not (d / ".claude/skills/design-taste-frontend").exists(), "not installed by default")
    expect((d / ".claude/skills/product-ui/SKILL.md").exists(), "product-ui is")
    expect("UI-Paths: web/src/" in (d / ".uak/PROJECT.md").read_text(encoding="utf-8"), "UI-Paths for the stack")
    expect(".uak-shots/" in (d / ".gitignore").read_text(encoding="utf-8").splitlines(), "screenshots stay out of git")
    expect((d / ".uak/templates/DESIGN.template.md").exists(), "the DESIGN template ships")
    e = r.scratch / "v58-install-taste"
    e.mkdir()
    r.g(e, "init", "-q", "-b", "main")
    r.run([r.bash, str(r.package.parent / "install.sh"), "--mode", "sprint", "--stack", "fastapi-react", "--skills", "taste",
           "--harness", "claude", str(e)], cwd=e)
    expect((e / ".claude/skills/design-taste-frontend/SKILL.md").exists(), "--skills taste opts in")
    return {"install": True}


TESTS = [design_lint_sees_the_tells, done_ships_ui_with_what_was_seen, a_change_with_nothing_visible_says_why,
         a_ui_claim_says_what_to_open, lint_wants_a_filled_design_and_recipes, a_sprint_web_install_sets_the_gate]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    if not (args.package.parent / "install.sh").is_file():
        tests = [t for t in tests if t is not a_sprint_web_install_sets_the_gate]
    with tempfile.TemporaryDirectory(prefix="uak-v58-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        def one(test):
            started = time.monotonic()
            try:
                test(runner)
                return test.__name__, True, "%.2fs" % (time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001
                return test.__name__, False, str(exc)[:1500]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            results = list(pool.map(one, tests))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("V58_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
