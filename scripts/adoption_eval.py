#!/usr/bin/env python3
"""Adoption eval: does a real agent use the harness at the right moments, without being told in the prompt?

    python3 scripts/adoption_eval.py [--agent "claude -p --model sonnet"] [--out docs/evals/adoption-LABEL.json] [--label L]

Builds a throwaway team repo (kit installed, local bare remote, no network): a small Python codebase, task HACK-001
(change a function that HACK-002, claimed by another agent, imports) and a reviewer that approves the SHA ~40 s after
`uak done`. Then it runs ONE headless agent session as ana-1 in the HACK-001 worktree with a plain human request and
reads its transcript (stream-json). Metrics:
  - explore: Read/Grep/Glob/cat calls before the first `uak map` (or none), and whether the map was used at all
  - contract: a message to HACK-002 / its owner / impact: before `uak done`
  - wait: polls of status/inbox/board/next/digest after `uak done`, and whether `uak wait` was used
  - outcome: done reached, the verdict reported, tool calls, tokens and cost (from the result event)
Why: Anthropic's tool guidance — evaluate tools with realistic multi-step tasks and read the transcripts; at MLB the
agents made 486 "look" calls (status, inbox, board, digest) and wrote 4 black box notes in 60 h.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CODE = {
    "lib/__init__.py": "",
    "lib/pricing.py": "TAX = {'MX': 0.16, 'US': 0.08}\n\n\ndef price_with_tax(amount, country):\n    rate = TAX[country]\n    return round(amount * (1 + rate), 2)\n\n\ndef discount(amount, pct):\n    return amount * (1 - pct / 100)\n",
    "lib/money.py": "def fmt(amount):\n    return f\"${amount:,.2f}\"\n",
    "lib/inventory.py": "STOCK = {'tee': 10, 'mug': 4}\n\n\ndef in_stock(sku):\n    return STOCK.get(sku, 0) > 0\n",
    "app/__init__.py": "",
    "app/checkout.py": "from lib.pricing import price_with_tax, discount\nfrom lib.money import fmt\n\n\ndef total(items, country):\n    s = sum(price_with_tax(p, country) for p in items)\n    return fmt(s)\n\n\ndef total_with_coupon(items, country, pct):\n    return fmt(discount(sum(price_with_tax(p, country) for p in items), pct))\n",
    "app/cart.py": "from lib.inventory import in_stock\n\n\ndef add(cart, sku):\n    if in_stock(sku):\n        cart.append(sku)\n    return cart\n",
    "reports/__init__.py": "",
    "reports/sales.py": "from lib.money import fmt\n\n\ndef summary(rows):\n    return fmt(sum(r['amount'] for r in rows))\n",
    "tests/__init__.py": "",
    "tests/test_pricing.py": "import unittest\n\nfrom lib.pricing import price_with_tax\n\n\nclass Pricing(unittest.TestCase):\n    def test_mx(self):\n        self.assertEqual(price_with_tax(100, 'MX'), 116.0)\n",
    "tests/test_checkout.py": "import unittest\n\nfrom app.checkout import total\n\n\nclass Checkout(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([100, 50], 'US'), '$162.00')\n",
}
TASKS = """# TASKS — static backlog

## HACK-001 · Tax by region and a currency label in pricing

- **Type:** feature
- **Priority:** P0
- **Paths:** lib/pricing.py, tests/test_pricing.py
- **Depends on:** ninguna
- **Acceptance:**
  - `price_with_tax(amount, country, region=None)`: when `region` is given, use `REGION_TAX[(country, region)]` if present (add `REGION_TAX = {('US', 'CA'): 0.0725, ('US', 'NY'): 0.04}`), else the country rate.
  - Existing calls keep working unchanged. Tests cover a region and the fallback.
- **Verify:** `python3 -m unittest discover -s tests -t .`

## HACK-002 · Checkout totals by region

- **Type:** feature
- **Priority:** P0
- **Paths:** app/checkout.py, tests/test_checkout.py
- **Depends on:** ninguna
- **Acceptance:**
  - `total()` takes an optional region and passes it to pricing.
- **Verify:** `python3 -m unittest discover -s tests -t .`

## HACK-003 · Sales report by month

- **Type:** feature
- **Priority:** P1
- **Paths:** reports/
- **Depends on:** ninguna
- **Acceptance:**
  - `summary_by_month(rows)`.
- **Verify:** `python3 -m unittest discover -s tests -t .`
"""
PROJECT = """# PROJECT · adoption eval (sprint mode)

```text
Mode: sprint
Backlog-Approved: yes
Autonomy: yes
Auto-Merge: yes
Review-Mode: claims
Plan-Channel: claims
Freeze-Epoch: 9999999999
Lease-Seconds: 2700
Merge-Wait-Seconds: 60
Blackbox: off
Additive-Paths: tests/
```
"""
PROMPT = ("You are ana-1, an agent of this team, in the worktree of your task HACK-001. "
          "Do HACK-001 end to end following the repo's rules (AGENTS.md): implement it, verify it, ship it for review, "
          "and stay until the review verdict for it arrives; then answer with one line: the verdict and who gave it. "
          "There is no GitHub here: when a PR URL is required use https://example.test/pull/1. Work autonomously; "
          "nobody will answer questions.")


def sh(cmd, cwd, env=None, check=True):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run(cmd, cwd=cwd, env=e, shell=isinstance(cmd, str), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"setup failed: {cmd}\n{r.stdout}\n{r.stderr}")
    return r


KIT = ROOT


def build(base):
    remote = base / "remote.git"
    sh(["git", "init", "-q", "--bare", "-b", "main", str(remote)], base)
    seed = base / "team"
    seed.mkdir()
    sh(["git", "init", "-q", "-b", "main"], seed)
    sh(["bash", str(KIT / "install.sh"), "--mode", "sprint", "--stack", "python-data", str(seed)], base)
    for rel, text in CODE.items():
        p = seed / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    (seed / ".uak/TASKS.md").write_text(TASKS, encoding="utf-8")
    (seed / ".uak/PROJECT.md").write_text(PROJECT, encoding="utf-8")
    for k, v in (("user.name", "eval"), ("user.email", "eval@example.invalid")):
        sh(["git", "config", k, v], seed)
    sh(["git", "remote", "add", "origin", str(remote)], seed)
    sh(["git", "add", "-A"], seed)
    sh(["git", "commit", "-qm", "team repo"], seed)
    sh(["git", "push", "-q", "-u", "origin", "main"], seed)
    sh(["bash", ".uak/bin/uak", "register-reviewer", "judge"], seed, {"UAK_HUMAN": "lead", "UAK_AGENT": ""})
    sh(["bash", ".uak/bin/wt", "new", "HACK-002", "--agent", "bob-1"], seed, {"UAK_AGENT": "bob-1"})
    sh(["bash", ".uak/bin/wt", "new", "HACK-001", "--agent", "ana-1"], seed, {"UAK_AGENT": "ana-1"})
    wt = [Path(l.split(" ", 1)[1]) for l in sh(["git", "worktree", "list", "--porcelain"], seed).stdout.splitlines()
          if l.startswith("worktree ") and l.endswith("hack-001")][0]
    return seed, wt


def reviewer(seed, stop, log):
    """Approves every new SHA of HACK-001 ~40 s after it enters REVIEW, like a teammate (a fixed branch pushed after a
    blocked merge gets reviewed again)."""
    seen, approved = {}, set()
    while not stop.is_set():
        r = sh(["bash", ".uak/bin/uak", "status", "--task", "HACK-001", "--full"], seed, {"UAK_AGENT": "judge", "UAK_DEDUPE": "off"}, check=False)
        tip = sh(["git", "ls-remote", "origin", "refs/heads/feat/hack-001"], seed, check=False).stdout.split()
        if "HACK-001 | REVIEW" in r.stdout and tip and tip[0] not in approved:
            seen.setdefault(tip[0], time.time())
            if time.time() - seen[tip[0]] >= 40:
                a = sh(["bash", ".uak/bin/uak", "review", "HACK-001", "--sha", tip[0], "--verdict", "approve", "--note", "eval reviewer: Verify passed"],
                       seed, {"UAK_AGENT": "judge"}, check=False)
                log.append({"t": time.time(), "sha": tip[0][:7], "review": (a.stdout.strip() + a.stderr.strip())[:200]})
                if a.returncode == 0 or "already approved" in a.stdout:
                    approved.add(tip[0])
        time.sleep(5)


def analyze(stream):
    raw_text = stream
    calls, final, usage, cost = [], "", {}, None
    for line in stream.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    calls.append((b.get("name"), json.dumps(b.get("input", {}))))
        if ev.get("type") == "result":
            final, usage, cost = ev.get("result", ""), ev.get("usage", {}), ev.get("total_cost_usd")
    # MCP tools (mcp__uak__uak_wait …) count as the same uak commands as their Bash forms.
    MCP = {"uak_map": "uak map", "uak_ship": "uak done HACK-001", "uak_wait": "uak wait", "uak_status": "uak status",
           "uak_inbox": "uak inbox", "uak_next": "uak next", "uak_message": "uak msg", "uak_memory": "uak learn"}
    norm = []
    for name, inp in calls:
        short = name.split("__")[-1] if name.startswith("mcp__uak__") else None
        if short:
            a = json.loads(inp)
            extra = " --ack" if a.get("ack") else ""
            norm.append(("Bash", json.dumps({"command": MCP.get(short, "uak " + short) + " " + json.dumps(a) + extra, "mcp": True})))
        else:
            norm.append((name, inp))
    mcp_calls = sum(1 for n, _ in calls if n.startswith("mcp__uak__"))
    calls = norm
    def bash(c):
        return c[0] == "Bash"
    def has(c, pat):
        return re.search(pat, c[1]) is not None
    explore = [i for i, c in enumerate(calls) if c[0] in ("Read", "Grep", "Glob") or (bash(c) and has(c, r'"command": "(cat|rg|grep|find|ls|sed -n|head)\b'))]
    map_i = [i for i, c in enumerate(calls) if bash(c) and has(c, r"uak map|\.uak/bin/map")]
    done_i = [i for i, c in enumerate(calls) if bash(c) and has(c, r"uak done [A-Z]+-[0-9]+")]
    # The ship that worked: the last `uak done` (a first one can fail on its arguments and be retried).
    first_done = done_i[-1] if done_i else len(calls)
    # A contract counts when it is sent before `uak done`: in an earlier call, or earlier in the same command line.
    contract = [i for i, c in enumerate(calls[:first_done + 1]) if bash(c) and has(c, r"uak msg") and has(c, r"impact:|related:|HACK-002|bob-1")
                and (i < first_done or c[1].find("uak msg") < c[1].find("uak done"))]
    polls = [i for i, c in enumerate(calls[first_done:]) if bash(c) and has(c, r"uak (status|inbox|board|next|digest)") and not has(c, r"inbox --ack")]
    waits = [i for i, c in enumerate(calls) if bash(c) and has(c, r"uak wait")]
    sleeps = [i for i, c in enumerate(calls[first_done:]) if bash(c) and has(c, r"sleep [0-9]")]
    return {
        "tool_calls": len(calls),
        "mcp_calls": mcp_calls,
        "explore_calls": len(explore),
        "explore_before_map": len([i for i in explore if not map_i or i < map_i[0]]),
        "used_map": bool(map_i),
        "contract_before_done": bool(contract),
        "done": bool(done_i),
        "polls_after_done": len(polls),
        "sleeps_after_done": len(sleeps),
        "used_wait": bool(waits),
        "verdict_reported": bool(re.search(r"approv|aprob", final, re.I)) and "judge" in final,
        "final": final[-300:],
        "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"),
        "cache_read": usage.get("cache_read_input_tokens"), "cost_usd": cost,
        "uak_commands": sorted({m.group(1) for _, inp in calls for m in re.finditer(r"uak (\w[\w-]*)", inp)}),
        # v5.1: the map pushed into the loop (the claim's slice and the post-tool lines), counted in the raw stream.
        "map_brief_seen": "TASK MAP " in raw_text,
        "map_lens_lines": raw_text.count("uak map: "),   # stream-json omits PostToolUse context: see lens_pushed
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="claude -p --model sonnet")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", default="")
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--setup-only", action="store_true")
    ap.add_argument("--kit", default="", help="install the kit from this checkout (e.g. a worktree of an older commit)")
    a = ap.parse_args()
    global KIT
    if a.kit:
        KIT = Path(a.kit).resolve()
    base = Path(tempfile.mkdtemp(prefix="uak-adopt-"))
    seed, wt = build(base)
    if a.setup_only:
        print("SETUP", seed, wt); print(sh(["bash", ".uak/bin/uak", "next"], wt, {"UAK_AGENT": "ana-1"}, check=False).stdout); return 0
    if True:
        stop, log = threading.Event(), []
        t = threading.Thread(target=reviewer, args=(seed, stop, log), daemon=True)
        t.start()
        cmd = shlex.split(a.agent) + ["--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
                                 "--allowedTools", "Bash", "Read", "Edit", "Write", "Grep", "Glob", "mcp__uak", "--", PROMPT]
        started = time.time()
        r = subprocess.run(cmd, cwd=wt, capture_output=True, text=True, timeout=a.timeout,
                           env=dict(os.environ, UAK_AGENT="ana-1"))
        stop.set()
        res = analyze(r.stdout)
        res.update({"label": a.label, "seconds": round(time.time() - started), "reviewer": log, "agent": a.agent})
        # Hook-side counts (the black box call log of the team repo): map lines pushed by the post-tool hook, and the
        # hooks' own uak calls, which stream-json does not show.
        calls_log = seed / ".git" / "uak-blackbox.calls"
        counted = calls_log.read_text(encoding="utf-8").split() if calls_log.exists() else []
        res.update({"lens_pushed": counted.count("lens"), "hook_calls": sum(1 for c in counted if c.startswith("hook-"))})
        (base / "transcript.jsonl").write_text(r.stdout, encoding="utf-8")
        print(json.dumps(res, indent=2))
        if a.out:
            out = ROOT / a.out
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        print("transcript:", base / "transcript.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
