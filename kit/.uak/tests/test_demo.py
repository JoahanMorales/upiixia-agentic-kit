#!/usr/bin/env python3
"""UAK-139: `uak demo` runs its three agents with a model and a harness of their own, marked as the demo's, so the
timeline and the dashboard drawer of the team repo it leaves behind name them instead of "unknown"; what the demo
prints is what it printed before.

  demo_timeline_names_models   `uak timeline HACK-001` in the kept team repo has no "unknown" for an agent
  demo_output_unchanged        the demo's step titles, commands and closing line, digits and hashes masked, are the
                               ones recorded before this change

Why (2026-11-21, the README capture): the first thing a new user opens showed "unknown" eight times in the feature
v6.7 added. Standard library only. Run: python3 kit/.uak/tests/test_demo.py [--case NAME]."""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hack import resolve_binary  # noqa: E402  (Git Bash on Windows: a bare "bash" is WSL's launcher)

BASH = resolve_binary("bash")
# The demo's lines as they were before UAK-139: steps, each agent command, the checks and the closing line.
GOLDEN = """▶ A team repo with a backlog of N tasks (temp dir: TMP)
  planner$ bash .uak/bin/uak graph
▶ Minute N: uak start checks every step from install to the first claim
  human$ bash .uak/bin/uak start
▶ Three agents start at once — overlapping paths are rejected at claim time
  ana-N$ bash .uak/bin/wt new HACK-N --agent ana-N
  bob-N$ bash .uak/bin/wt new HACK-N --agent bob-N
  cy-N$ bash .uak/bin/wt new HACK-N --agent cy-N
  ✓ cy-N cannot take HACK-N: it overlaps ana-N's src/api.sh
  cy-N$ bash .uak/bin/uak next
  human$ bash .uak/bin/board
▶ ana-N sees the test fail on its assertion before touching the code (test-first)
  ana-N$ bash .uak/bin/uak red HACK-N
▶ ana-N fixes the failing API with a bounded loop (fake agent: no AI key needed)
  ana-N$ bash .uak/bin/uak loop --verify bash tests/api_test.sh --agent bash TMP/fake-agent.sh --max N --task HACK-N
▶ ana-N ships: push + PR + evidence → a reviewer is asked by rotation
  ana-N$ bash .uak/bin/uak done HACK-N --pr https://github.com/example/demo/pull/N --evidence bash tests/api_test.sh exit N
▶ bob-N (not the author) reviews the exact SHA, then the gated merge queue integrates it
  bob-N$ bash .uak/bin/uak review HACK-N --sha SHA --verdict approve
  ana-N$ bash .uak/bin/uak merge HACK-N
▶ The dependent task unlocks by itself
  cy-N$ bash .uak/bin/uak next
  cy-N$ bash .uak/bin/wt new HACK-N --agent cy-N
▶ What the human sees: one board, one set of numbers
  human$ bash .uak/bin/board
  human$ bash .uak/bin/stats
✓ Done: N agents, N conflict avoided, N red before the code, N bounded loop, N independent review, N gated merge."""


class Failure(Exception):
    pass


def expect(cond, msg):
    if not cond:
        raise Failure(msg)


_cache = {}


def native(path):
    """A path Git Bash printed, as Windows Python can open it."""
    if os.name != "nt":
        return Path(path)
    out = subprocess.run([str(Path(BASH).parent / "cygpath.exe") if (Path(BASH).parent / "cygpath.exe").is_file() else "cygpath", "-w", path],
                         capture_output=True, text=True, errors="replace")
    return Path(out.stdout.strip() or path)


def demo():
    """One `uak demo --keep --fast` for both tests: (its output, the team repo as printed, the same as a native path)."""
    if not _cache:
        env = {k: v for k, v in os.environ.items() if k not in ("UAK_AGENT", "UAK_HUMAN", "UAK_MODEL", "UAK_HARNESS", "UAK_NOW")}
        out = subprocess.run([BASH, str(KIT / ".uak/bin/demo"), "--keep", "--fast"], capture_output=True, text=True,
                             errors="replace", encoding="utf-8", env=env, timeout=600)
        expect(out.returncode == 0, "demo rc %d: %s" % (out.returncode, (out.stdout + out.stderr)[-1500:]))
        m = re.search(r"^  Explore it: cd (.+)$", out.stdout, re.M)  # the path may hold spaces
        expect(m, "the demo prints where its team repo is")
        team = m.group(1).strip()  # as the demo prints it: a Git Bash path (/tmp/...) on Windows
        _cache["v"] = (out.stdout, team, native(team))
    return _cache["v"]


def mask(line, tmp):
    # The loop line prints the fake agent's path shell-quoted (printf %q): spaces, accents and $'...' escapes all
    # depend on the machine's TMPDIR, so what sits between "--agent bash " and " --max" is masked whole.
    line = re.sub(r"(--agent bash ).*?( --max )", r"\1TMP/fake-agent.sh\2", line.replace(tmp, "TMP"))
    return re.sub(r"[0-9]+", "N", re.sub(r"[0-9a-f]{7,40}", "SHA", line))


def demo_timeline_names_models():
    _, _, team = demo()
    env = dict(os.environ, UAK_AGENT="tester")
    for k in ("UAK_MODEL", "UAK_HARNESS"):
        env.pop(k, None)
    out = subprocess.run([BASH, ".uak/bin/uak", "timeline", "HACK-001"], cwd=str(team), capture_output=True, text=True,
                         errors="replace", encoding="utf-8", env=env, timeout=120)
    expect(out.returncode == 0, "timeline: " + out.stdout + out.stderr)
    expect("unknown" not in out.stdout, "the timeline still says unknown:\n" + out.stdout)
    agents = re.search(r"^agents: (.*)$", out.stdout, re.M)
    expect(agents and "ana-1 demo-" in agents.group(1) and "bob-1 demo-" in agents.group(1), "agents line: %s" % (agents and agents.group(1)))
    expect(re.search(r"ana-1 \(demo-[A-Za-z0-9._-]+, demo-[A-Za-z0-9._-]+\)", out.stdout), "a move shows the demo's model and harness")
    models = set(re.findall(r"(?:ana|bob|cy)-1 \((demo-[A-Za-z0-9._-]+),", out.stdout))
    expect(len(models) >= 2, "each agent has a model of its own: %s" % models)
    return "ana-1 and bob-1 carry demo models and harnesses"


def demo_output_unchanged():
    stdout, team, _ = demo()
    got = [mask(l, team.rsplit("/team", 1)[0]) for l in stdout.splitlines() if re.match(r"(▶|  [A-Za-z0-9-]+\$|  ✓|✓)", l)]
    want = GOLDEN.splitlines()
    expect(got == want, "the demo's printed lines changed:\n--- want\n%s\n--- got\n%s" % ("\n".join(want), "\n".join(got)))
    return "%d step and command lines identical" % len(want)


TESTS = [demo_timeline_names_models, demo_output_unchanged]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--package")  # smoke passes it to every test; this one reads its own tree
    args = parser.parse_args()
    failed = 0
    for t in [t for t in TESTS if not args.case or t.__name__ == args.case]:
        try:
            print("PASS %s (%s)" % (t.__name__, t()), flush=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s)" % (t.__name__, str(exc)[:2500]), flush=True)
    print("DEMO_RESULT %s" % ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
