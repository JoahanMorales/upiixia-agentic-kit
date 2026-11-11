#!/usr/bin/env python3
"""UAK-061: design-lint warns on the scale failures of F0 (docs/design/failures.md, 2026-11-11): display type above 96 px
(168 and 207 px landings scored 1), vw type above 12vw, and a button or input taller than 56 px. Warnings, never
failures, so a hackathon is not blocked; --strict fails. A deliberate line carries `design-lint: ok <reason>`."""
import argparse
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def project(r, name, files):
    t = r.scratch / ("ds-" + name)
    (t / "web/src").mkdir(parents=True)
    r.g(t, "init", "-q", "-b", "main")
    (t / "web/src/index.css").write_text(":root{--a:#fff}\n", encoding="utf-8")
    for rel, text in files.items():
        (t / "web/src" / rel).write_text(text, encoding="utf-8")
    return t


def lint(r, t, *args):
    return r.run([r.bash, str(r.package / ".uak/bin/design-lint"), *args], cwd=t, allowed=None)


def warns(out):
    return [l for l in out.stdout.splitlines() if l.startswith("DESIGN_LINT_WARN")]


def has(out, where, bound):
    return any(where in l and bound in l for l in warns(out))


def px_rem_and_tailwind_sizes_over_bound_warn(r):
    t = project(r, "px", {
        "a.css": "h1 { font-size: 168px; }\nh2 { font-size: 7rem; }\nh3 { font-size: 96px; }\nh4 { font-size: 6rem; }\np { font-size: 17px; }\n",
        "b.tsx": 'export const A = () => <h1 className="text-[7.5rem]">x</h1>;\nexport const B = () => <h1 className="md:text-9xl">x</h1>;\n'
                 'export const C = () => <h1 className="text-8xl">x</h1>;\nexport const D = () => <h1 className="text-7xl">x</h1>;\n'
                 'export const E = () => <h1 style={{ fontSize: 207 }}>x</h1>;\n',
    })
    out = lint(r, t)
    expect(out.returncode == 0 and "DESIGN_LINT_PASS" in out.stdout, "warnings do not fail: rc %d %s" % (out.returncode, out.stdout))
    for where in ("a.css:1", "a.css:2", "b.tsx:1", "b.tsx:2", "b.tsx:3"):
        expect(has(out, where, "96 px"), "%s warns and names the F0 bound: %s" % (where, out.stdout))
    for where in ("a.css:3", "a.css:4", "a.css:5", "b.tsx:4"):
        expect(not any(where in l for l in warns(out)), "%s is inside the bound: %s" % (where, out.stdout))
    expect("failures.md" in out.stdout, "the warning points to the F0 catalog")
    hb = project(r, "h", {"c.css": ".btn { height: 64px; }\nbutton.x { min-height: 4rem; }\n.btn-ok { height: 52px; }\n.card { height: 300px; }\ninput { line-height: 80px; }\n",
                          "d.tsx": 'export const A = () => <button className="h-16">go</button>;\nexport const B = () => <button className="h-12">go</button>;\n'
                                   'export const C = () => <input className="h-[60px]" />;\n'})
    o2 = lint(r, hb)
    for where in ("c.css:1", "c.css:2", "d.tsx:1", "d.tsx:3"):
        expect(has(o2, where, "56 px"), "%s: button/input height warns: %s" % (where, o2.stdout))
    for where in ("c.css:3", "c.css:4", "c.css:5", "d.tsx:2"):
        expect(not any(where in l for l in warns(o2)), "%s is fine: %s" % (where, o2.stdout))
    return "warned"


def clamp_max_counts(r):
    t = project(r, "clamp", {"a.css": "h1 { font-size: clamp(3rem, 10vw, 12rem); }\nh2 { font-size: clamp(1rem, 5vw, 4rem); }\nh3 { font-size: clamp(2rem, 20vw, 5rem); }\n",
                             "b.tsx": 'export const A = () => <h1 className="text-[clamp(2rem,8vw,10rem)]">x</h1>;\n'})
    out = lint(r, t)
    expect(has(out, "a.css:1", "96 px") and has(out, "b.tsx:1", "96 px"), "the max of the clamp (192 and 160 px) warns: " + out.stdout)
    expect(not any("a.css:2" in l or "a.css:3" in l for l in warns(out)), "a clamp that tops out at 64 or 80 px is fine, whatever its middle: " + out.stdout)
    return "max counts"


def vw_over_bound_warns(r):
    t = project(r, "vw", {"a.css": "h1 { font-size: 14vw; }\nh2 { font-size: 12vw; }\nh3 { width: 40vw; }\n",
                          "b.tsx": 'export const A = () => <h1 className="text-[20vw]">x</h1>;\n'})
    out = lint(r, t)
    expect(has(out, "a.css:1", "12vw") and has(out, "b.tsx:1", "12vw"), "14vw and 20vw warn: " + out.stdout)
    expect(not any("a.css:2" in l or "a.css:3" in l for l in warns(out)), "12vw and a width are fine: " + out.stdout)
    return "vw"


def ok_comment_silences(r):
    t = project(r, "ok", {"a.css": "h1 { font-size: 168px; } /* design-lint: ok the human picked mega type in round 2 */\nh2 { font-size: 14vw; }\n"})
    out = lint(r, t)
    expect(not any("a.css:1" in l for l in warns(out)) and has(out, "a.css:2", "12vw"), "only the marked line is silent: " + out.stdout)
    return "silenced"


def strict_fails(r):
    t = project(r, "strict", {"a.css": "h1 { font-size: 168px; }\n"})
    plain = lint(r, t)
    strict = lint(r, t, "--strict")
    expect(plain.returncode == 0 and strict.returncode == 1 and "DESIGN_LINT_FAIL" in strict.stdout and "a.css:1" in strict.stdout,
           "--strict fails: rc %d %s" % (strict.returncode, strict.stdout))
    clean = project(r, "strict-clean", {"a.css": "h1 { font-size: 64px; }\n"})
    expect(lint(r, clean, "--strict").returncode == 0, "--strict passes a clean project")
    return "strict"


TESTS = [px_rem_and_tailwind_sizes_over_bound_warn, clamp_max_counts, vw_over_bound_warns, ok_comment_silences, strict_fails]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-scale-") as tmp:
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
    print("DESIGN_LINT_SCALE_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
