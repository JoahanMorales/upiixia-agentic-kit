#!/usr/bin/env python3
"""UAK-120: `uak timeline ID` prints a task's whole story from claims, and the dashboard embeds the same lines for a
card's dialog. Synthetic claims directory (--claims) in a folder with a space and an accent; no network.
Why (the human, 2026-11-21): "presionar sobre una tarea debe mostrar todo el mapa de agentes y movimientos de la tarea
super bien explicado para realmente poder auditar"."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_hack import expect, resolve_binary

T0 = 1800000000
H = 3600
A, B, C = "a" * 40, "b" * 40, "c" * 40


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def claims(tmp):
    c = Path(tmp) / "claims é dir"
    tail = " | Harness: claude-code | Model: m1"
    ev = [(T0, "CLAIMED", "ana-1", "claim; next: wire it" + tail),
          (T0 + H, "REVIEW", "ana-1", "done; PR https://x/pull/7; evidence: 3 PASS · red at abc1234: exit 1 (assertion); reviewer: -" + tail),
          (T0 + 2 * H, "REVIEW", "rev-1", "review; reject; SHA %s; reviewer rev-1 | Harness: codex | Model: m2" % A),
          (T0 + 3 * H, "REVIEW", "ana-1", "done; PR https://x/pull/7; evidence: 5 PASS · red at abc1234: exit 1 (assertion); reviewer: -" + tail),
          (T0 + 4 * H, "REVIEW", "rev-1", "review; approve; SHA %s; reviewer rev-1 | Harness: codex | Model: m2" % B),
          (T0 + 4 * H + 600, "REVIEW", "ana-1", "merge rechazado; Shared resource/CI needs a human: x.yml" + tail),
          (T0 + 6 * H, "INTEGRATED", "hum-1", "integrate; recorded by hum-1; merged " + C + "; proof ancestry; unreviewed")]
    put(c / "tasks" / "UAK-001.md", "ID: UAK-001\nState: INTEGRATED\nOwner: ana-1\nUpdated: %d\n" % (T0 + 6 * H))
    put(c / "worklog" / "WL-1-ana-1-UAK-001-x.md", "# worklog/WL-1.md · UAK-001\n\n## History\n" + "\n".join(
        "- %d | %s | %s | %s" % e for e in ev) + "\n")
    # An older task: no model on its events.
    put(c / "tasks" / "UAK-002.md", "ID: UAK-002\nState: CLAIMED\nOwner: old-1\nUpdated: %d\n" % T0)
    put(c / "worklog" / "WL-1-old-1-UAK-002-x.md", "# w · UAK-002\n\n## History\n- %d | CLAIMED | old-1 | claim; next: x\n" % T0)
    put(c / "tasks" / "UAK-003.md", "ID: UAK-003\nState: AVAILABLE\nOwner: -\nUpdated: %d\n" % T0)
    put(c / "inbox" / "log.md", "# log\n\n" + "\n".join([
        "- 1 | %d | ana-1 | agent:rev-1 | review | UAK-001 | ready (SHA %s)" % (T0 + H, A),
        "- 2 | %d | rev-1 | task:UAK-001 | reject | UAK-001 | Rejected SHA aaaaaaa by rev-1 · the retry never backs off: add a test with five failures" % (T0 + 2 * H),
        "- 3 | %d | ana-1 | agent:rev-1 | review | UAK-001 | ready (SHA %s)" % (T0 + 3 * H, B),
        "- 4 | %d | github | task:UAK-001 | request | UAK-001 | GitHub: #7 CI failed: lint https://x/1" % (T0 + 5 * H)]) + "\n")
    put(c / "DECISIONS.md", "# D\n\n- %d | plan | Dana/Dana | tasks added: UAK-001 UAK-002 | Why: b\n" % (T0 - H))
    put(c / "metrics" / "2027-01-01-1.tsv", "# ledger\n%d\tdone\tUAK-001\t1\tFAILED\t10\tana-1\tc\n%d\tdone\tUAK-001\t0\t-\t10\tana-1\tc\n" % (T0 + H, T0 + 3 * H))
    put(c / "tokens" / "2027-01.md", "- UAK-001 | c | x | task | m | 10 | 20 | 30 | 40\n")
    return c


def run(r, c, *args):
    env = dict(os.environ, UAK_NOW=str(T0 + 7 * H))
    p = subprocess.run([r["bash"], str(r["pkg"] / "bin" / "timeline")] + list(args) + ["--claims", str(c)], cwd=str(c.parent), env=env,
                       capture_output=True, text=True, encoding="utf-8")
    return p


def timeline_orders_every_move(r):
    c = claims(r["tmp"])
    p = run(r, c, "UAK-001")
    expect(p.returncode == 0, p.stderr)
    kinds = [l["kind"] for l in json.loads(run(r, c, "UAK-001", "--json").stdout)["lines"]]
    expect(kinds == ["plan", "claim", "red", "done", "reject", "done", "tip", "approve", "human", "ci", "integrate"], kinds)
    expect("Unreviewed" in p.stdout and "m2, codex" in p.stdout and "m1, claude-code" in p.stdout, p.stdout)
    old = run(r, c, "UAK-002").stdout
    expect("unknown, unknown" in old, old)
    none = run(r, c, "UAK-003").stdout
    expect("no history yet" in none or "planned" in none, none)
    return "%d moves in order" % len(kinds)


def a_reject_shows_reason_and_the_next_tip(r):
    c = claims(r["tmp"])
    out = run(r, c, "UAK-001").stdout
    expect("the retry never backs off: add a test with five failures" in out, out)
    expect("rejected aaaaaaa" in out and "new tip bbbbbbb after a reject by rev-1" in out, out)
    expect("the tip's SHA was not recorded" not in out and "files changed" in out, out)
    return "reason and next tip"


def totals_match_the_lines(r):
    c = claims(r["tmp"])
    tl = json.loads(run(r, c, "UAK-001", "--json").stdout)
    ls = tl["lines"]
    expect(sum(l["gap"] for l in ls) == ls[-1]["epoch"] - ls[0]["epoch"], "gaps")
    expect(tl["totals"]["seconds"] == ls[-1]["epoch"] - ls[0]["epoch"], "%s vs %s" % (tl["totals"]["seconds"], ls[-1]["epoch"] - ls[0]["epoch"]))
    expect(tl["totals"]["review_rounds"] == 2 and tl["totals"]["rejects"] == 1, tl["totals"])
    expect(tl["totals"]["tokens"] == 100 and tl["totals"]["commands"][0] == {"command": "done", "calls": 2, "errors": 1}, tl["totals"])
    return "gaps add up to %d s" % tl["totals"]["seconds"]


def json_has_stable_keys(r):
    c = claims(r["tmp"])
    tl = json.loads(run(r, c, "UAK-001", "--json").stdout)
    expect(sorted(tl) == ["empty", "lines", "now", "open", "owner", "sources", "state", "task", "title", "totals"], sorted(tl))
    expect(sorted(tl["lines"][0]) == ["agent", "detail", "epoch", "gap", "harness", "kind", "model", "sha", "text"], sorted(tl["lines"][0]))
    expect(sorted(tl["totals"]) == ["agents", "commands", "errors", "models", "rejects", "review_rounds", "seconds", "states", "tokens"], sorted(tl["totals"]))
    return "documented keys"


def dashboard_embeds_the_timeline(r):
    sys.path.insert(0, str(r["pkg"] / "bin" / "lib"))
    import dash
    c = claims(r["tmp"])
    os.environ["UAK_NOW"] = str(T0 + 7 * H)
    try:
        d = dash.build(c, "", "repo")
    finally:
        os.environ.pop("UAK_NOW", None)
    tl = d["timelines"]
    expect({"UAK-001", "UAK-002"} <= set(tl) and d["timeline_bound"]["closed_kept"] == dash.TL_EMBED_INTEGRATED, list(tl))
    rej = [l for l in tl["UAK-001"]["lines"] if l[1] == "reject"][0]
    expect("five failures" in rej[6] and rej[3] == "m2", rej)
    # bounded: more closed tasks than the cap embeds only the cap, open ones always
    for i in range(30):
        put(c / "tasks" / ("UAK-9%02d.md" % i), "ID: UAK-9%02d\nState: INTEGRATED\nOwner: a\nUpdated: %d\n" % (i, T0 + i))
    d = dash.build(c, "", "repo")
    expect(len(d["timelines"]) <= 2 + dash.TL_EMBED_INTEGRATED + 1, len(d["timelines"]))
    html = (r["pkg"] / "bin" / "lib" / "dash.html").read_text(encoding="utf-8")
    expect('<dialog id="story"' in html and "timelines" in html and "Escape" in html and 'src="http' not in html, "dialog markup")
    return "%d stories embedded of %d tasks" % (len(d["timelines"]), d["timeline_bound"]["tasks"])


TESTS = [timeline_orders_every_move, a_reject_shows_reason_and_the_next_tip, totals_match_the_lines, json_has_stable_keys, dashboard_embeds_the_timeline]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--case")
    a = ap.parse_args()
    failed = 0
    tests = [t for t in TESTS if not a.case or t.__name__ == a.case]
    with tempfile.TemporaryDirectory(prefix="uak timeline é ") as tmp:
        for t in tests:
            sub = tempfile.mkdtemp(dir=tmp)
            env = {"bash": resolve_binary("bash"), "pkg": a.package.resolve() / ".uak", "tmp": sub}
            try:
                print("PASS %s (%s)" % (t.__name__, t(env)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("TIMELINE_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
