#!/usr/bin/env python3
"""UAK-133: `uak tokens --since DAYS` counts the messages whose own timestamp is inside the window (a long session file
touched today no longer brings in last month's tokens; Codex's cumulative total is cut at the window start), and `uak next`
and `uak status` print the TOKENS_BUDGET line of `tokens --budget-check` for the agent's live task once it crossed
Token-Budget: once per call, also on a read served from the cache, nothing without a budget. Synthetic transcripts in a
throwaway CLAUDE_CONFIG_DIR / CODEX_HOME, real Git, a local bare remote."""
import argparse
import datetime
import json
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_tokens_coverage import enc, env

HOME = "/home/someone"


def stamp(days_ago):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def line(msg_id, output, cwd, days_ago=None):
    rec = {"type": "assistant", "cwd": cwd,
           "message": {"id": msg_id, "model": "claude-x", "role": "assistant",
                       "content": [{"type": "tool_use", "id": "toolu_" + msg_id, "name": "Bash", "input": {"command": "ls"}}],
                       "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": output}}}
    if days_ago is not None:
        rec["timestamp"] = stamp(days_ago)
    return json.dumps(rec, ensure_ascii=False)


def setup(r, name):
    f = r.fixture("tw-" + name, count=2)
    main = Path(f.clones[0]).resolve().as_posix()
    cfg = r.scratch / (name + "-claude")
    return f, main, str(cfg)


def put(cfg, rel, lines):
    p = Path(cfg) / "projects" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def session(cfg, main, rows):
    """One session started in the main checkout: rows are (id, output, days_ago)."""
    put(cfg, enc(main) + "-wt-hack-001/s1.jsonl", [line(i, o, main + "-wt/hack-001", d) for i, o, d in rows])


def total(r, f, cfg, *args, **extra):
    out = r.run([r.bash, ".uak/bin/tokens", "--json", *args], cwd=f.clones[0], env=env(f, cfg, **extra), allowed=None)
    expect(out.returncode == 0, "tokens: " + out.stdout + out.stderr)
    return {row["key"]: row["output"] for row in json.loads(out.stdout)}


def since_counts_by_message_time(r):
    f, main, cfg = setup(r, "since")
    session(cfg, main, [("msg_old", 1000, 40), ("msg_mid", 200, 10), ("msg_new", 30, 0.1)])
    expect(total(r, f, cfg, "--since", "5") == {"HACK-001": 30}, "5 days: %s" % total(r, f, cfg, "--since", "5"))
    expect(total(r, f, cfg, "--since", "20") == {"HACK-001": 230}, "20 days: %s" % total(r, f, cfg, "--since", "20"))
    expect(total(r, f, cfg, "--since", "60") == {"HACK-001": 1230}, "60 days: %s" % total(r, f, cfg, "--since", "60"))
    # Messages without a timestamp (older transcripts) count whenever their file is in the window: totals unchanged.
    session(cfg, main, [("msg_a", 7, None), ("msg_b", 5, None)])
    expect(total(r, f, cfg) == {"HACK-001": 12}, "no timestamps, no --since: %s" % total(r, f, cfg))
    # Codex: the cumulative total of a session is cut at the window start.
    codex = Path(cfg) / "codex" / "sessions"
    codex.mkdir(parents=True)
    def tc(days, i, c, o):
        return json.dumps({"timestamp": stamp(days), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": i, "cached_input_tokens": c, "output_tokens": o}}}}, ensure_ascii=False)
    meta = json.dumps({"timestamp": stamp(40), "type": "session_meta", "payload": {"cwd": main + "-wt/hack-002"}}, ensure_ascii=False)
    (codex / "rollout-1.jsonl").write_text("\n".join([meta, tc(40, 100, 50, 20), tc(10, 300, 100, 60), tc(0.1, 400, 150, 90)]) + "\n", encoding="utf-8")
    e = {"CODEX_HOME": str(Path(cfg) / "codex")}
    expect(total(r, f, cfg, "--since", "5", **e).get("HACK-002") == 30, "codex 5 days: %s" % total(r, f, cfg, "--since", "5", **e))
    expect(total(r, f, cfg, "--since", "20", **e).get("HACK-002") == 70, "codex 20 days: %s" % total(r, f, cfg, "--since", "20", **e))
    return "by message time"


def an_old_message_in_a_new_file_is_out(r):
    f, main, cfg = setup(r, "oldnew")
    session(cfg, main, [("msg_1", 5000, 25), ("msg_2", 6000, 24), ("msg_3", 7, 0)])   # the file was just written
    got = total(r, f, cfg, "--since", "2")
    expect(got == {"HACK-001": 7}, "only today's message: %s" % got)
    out = r.run([r.bash, ".uak/bin/tokens", "--since", "2"], cwd=f.clones[0], env=env(f, cfg), allowed=None)
    expect("TOKENS total" in out.stdout, "the report still prints: " + out.stdout)
    return "out"


def live_task(r, name, budget):
    f, main, cfg = setup(r, name)
    session(cfg, main, [("msg_x", 3000, 0.1)])
    f.claim(0, "HACK-001")
    if budget:
        project = f.worktrees[0] / ".uak/PROJECT.md"
        project.write_text(project.read_text(encoding="utf-8") + "\nToken-Budget: 1k\n", encoding="utf-8", newline="\n")
    return f, cfg


def run_uak(r, f, cfg, *args):
    out = r.run([r.bash, ".uak/bin/uak", *args], cwd=f.worktrees[0], env=env(f, cfg, UAK_READ_CACHE="on", UAK_DEDUPE="off"), allowed=None)
    expect(out.returncode == 0, "uak %s: %s" % (" ".join(args), out.stdout + out.stderr))
    return out.stdout


def next_warns_over_budget(r):
    f, cfg = live_task(r, "next", True)
    out = run_uak(r, f, cfg, "next")
    got = [x for x in out.splitlines() if x.startswith("TOKENS_BUDGET: HACK-001 spent")]
    expect(len(got) == 1, "one budget line in next: " + out)
    expect(out.splitlines()[0].startswith("HACK-001 |"), "the first line stays the task: " + out)
    return "warned"


def status_warns_over_budget(r):
    f, cfg = live_task(r, "status", True)
    for args in (("status",), ("status", "--task", "HACK-001")):
        out = run_uak(r, f, cfg, *args)
        got = [x for x in out.splitlines() if x.startswith("TOKENS_BUDGET: HACK-001 spent")]
        expect(len(got) == 1, "%s: one budget line: %s" % (args, out))
    again = run_uak(r, f, cfg, "status")   # a read served from the cache says so and still warns
    expect("claims as of" in again and "TOKENS_BUDGET: HACK-001" in again, "a cached read warns too: " + again)
    return "warned"


def no_budget_prints_nothing(r):
    f, cfg = live_task(r, "none", False)
    for args in (("next",), ("status",), ("status", "--task", "HACK-001")):
        out = run_uak(r, f, cfg, *args)
        expect("TOKENS_BUDGET" not in out, "%s: no budget, no line: %s" % (args, out))
    f2, cfg2 = live_task(r, "notx", True)
    out = r.run([r.bash, ".uak/bin/uak", "next"], cwd=f2.worktrees[0], env=env(f2, str(Path(cfg2) / "empty")), allowed=None)
    expect(out.returncode == 0 and "TOKENS_BUDGET" not in out.stdout, "no transcript, no line: " + out.stdout + out.stderr)
    return "silent"


def raw_session(cfg, main, rows):
    """Like session(), but each row is (id, output, timestamp as written or None for no key)."""
    out = []
    for i, o, ts in rows:
        rec = json.loads(line(i, o, main + "-wt/hack-001"))
        if ts is not None:
            rec["timestamp"] = ts
        out.append(json.dumps(rec))
    put(cfg, enc(main) + "-wt-hack-001/s1.jsonl", out)


def a_malformed_timestamp_counts_like_a_missing_one(r):
    f, main, cfg = setup(r, "badts")
    raw_session(cfg, main, [("msg_ok", 10, stamp(0.1)), ("msg_bad", 100, "not-a-time"), ("msg_nokey", 1000, None),
                            ("msg_range", 10000, "2026-99-99T99:99:99.000Z"), ("msg_old", 100000, stamp(40))])
    probe = r.run([r.bash, ".uak/bin/tokens", "--json", "--since", "5"], cwd=f.clones[0], env=env(f, cfg), allowed=None)
    inside = {row["key"]: row["output"] for row in json.loads(probe.stdout)}
    expect(inside == {"HACK-001": 10}, "inside an explicit window only valid stamps count: %s stderr=%s transcript=%s" % (
        inside, probe.stderr[-600:], (Path(cfg) / "projects").rglob("*.jsonl").__next__().read_text()[:900]))
    plain = total(r, f, cfg)
    expect(plain == {"HACK-001": 11110}, "no --since: bad and missing stamps count, the old one is out of 30 days: %s" % plain)
    return "rule"


def since_zero_is_an_empty_window_and_help_says_so(r):
    f, main, cfg = setup(r, "zero")
    session(cfg, main, [("msg_new", 30, 0.001)])
    expect(total(r, f, cfg, "--since", "0") == {}, "--since 0 reads nothing: %s" % total(r, f, cfg, "--since", "0"))
    out = r.run([r.bash, ".uak/bin/tokens", "--help"], cwd=f.clones[0], env=env(f, cfg), allowed=None)
    expect("--since 0" in out.stdout and "mtime" in out.stdout and "touched" in out.stdout, "help documents both: " + out.stdout)
    return "documented"


def budget_project(r, name, budget):
    f, cfg = live_task(r, name, False)
    project = f.worktrees[0] / ".uak/PROJECT.md"
    project.write_text(project.read_text(encoding="utf-8") + "\nToken-Budget: %s\n" % budget, encoding="utf-8", newline="\n")
    return f, cfg


def a_bad_budget_prints_nothing(r):
    for n, bad in enumerate(["-5", "abc", ""]):
        f, cfg = budget_project(r, "bad%d" % n, bad)
        out = r.run([r.bash, ".uak/bin/uak", "status"], cwd=f.worktrees[0], env=env(f, cfg, UAK_READ_CACHE="on", UAK_DEDUPE="off"), allowed=None)
        expect(out.returncode == 0 and "TOKENS_BUDGET" not in out.stdout and "tokens" not in out.stderr, "budget %r: %s%s" % (bad, out.stdout, out.stderr))
        d = r.run([r.bash, ".uak/bin/tokens", "--budget-check", "HACK-001", "--local"], cwd=f.clones[0], env=env(f, cfg), allowed=None)
        expect(d.returncode == 0 and not d.stdout.strip() and not d.stderr.strip(), "budget %r direct: %s%s" % (bad, d.stdout, d.stderr))
    return "silent"


def wait_scan(f, want_cache=True):
    base = Path(f.clones[0]) / ".git" / "uak-budget"
    for _ in range(300):
        if not (base / "HACK-001.lock").exists() and (base / "HACK-001").exists() == want_cache:
            return base
        time.sleep(0.1)
    raise AssertionError("the background scan did not finish: %s" % (sorted(x.name for x in base.glob("*")) if base.exists() else "no dir"))


def the_scan_runs_in_the_background(r):
    f, cfg = live_task(r, "bg", True)
    first = run_uak_bg(r, f, cfg)
    expect("TOKENS_BUDGET" not in first, "a cold cache never makes status wait or warn: " + first)
    wait_scan(f)
    second = run_uak_bg(r, f, cfg)
    expect("TOKENS_BUDGET: HACK-001 spent" in second, "the finished scan is what status prints: " + second)
    return "background"


def run_uak_bg(r, f, cfg):
    out = r.run([r.bash, ".uak/bin/uak", "status"], cwd=f.worktrees[0], env=env(f, cfg, UAK_READ_CACHE="on", UAK_DEDUPE="off", UAK_TOKENS_SYNC=""), allowed=None)
    expect(out.returncode == 0, "status: " + out.stdout + out.stderr)
    return out.stdout


def one_scan_at_a_time_and_a_dead_one_is_replaced(r):
    f, cfg = live_task(r, "lock", True)
    base = Path(f.clones[0]) / ".git" / "uak-budget"
    lock = base / "HACK-001.lock"
    (lock / "x").mkdir(parents=True)
    (lock / "at").write_text(str(int(time.time())) + "\n")
    run_uak_bg(r, f, cfg)
    time.sleep(0.6)
    expect(lock.exists() and not (base / "HACK-001").exists(), "a live lock means no second scan")
    (lock / "at").write_text("1\n")   # a scan killed halfway left it behind long ago
    run_uak_bg(r, f, cfg)
    wait_scan(f)
    expect("TOKENS_BUDGET" in run_uak_bg(r, f, cfg), "the dead lock was replaced and the scan finished")
    return "locked"

TESTS = [since_counts_by_message_time, an_old_message_in_a_new_file_is_out, next_warns_over_budget, status_warns_over_budget, no_budget_prints_nothing,
         a_malformed_timestamp_counts_like_a_missing_one, since_zero_is_an_empty_window_and_help_says_so, a_bad_budget_prints_nothing,
         the_scan_runs_in_the_background, one_scan_at_a_time_and_a_dead_one_is_replaced]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-tokens-window-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        runner.env["UAK_TOKENS_SYNC"] = "1"   # the scan of the budget runs in the foreground, so a status is deterministic
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
    print("TOKENS_WINDOW_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
