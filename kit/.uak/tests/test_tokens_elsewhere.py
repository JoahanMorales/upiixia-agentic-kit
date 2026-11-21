#!/usr/bin/env python3
"""UAK-122: `uak tokens` answered "no transcripts of this project found" in the kit's own repo, because every session that
drives it starts in the home directory. A transcript whose session started outside the repo now counts when its tool calls
ran in the main checkout or in a worktree under <repo>-wt/ (the paths of the calls and the cwd the lines record); a
subagent's transcript goes to the task whose worktree it worked in; `--by step` splits a task into author, review, merge
and lead; `Token-Budget: N` is checked by `tokens --budget-check ID`; no transcript text ever leaves the machine.
Synthetic transcripts in a temp config dir, real Git, a local bare remote."""
import argparse
import json
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_tokens_coverage import enc, env

SECRET = "SECRET-PROMPT-TEXT-9f3a"


def line(msg_id, output, cwd, tool=None, text=None, model="claude-x", sidechain=False):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    if tool is not None:
        content.append({"type": "tool_use", "id": "toolu_" + msg_id, "name": tool[0], "input": tool[1]})
    return json.dumps({"type": "assistant", "isSidechain": sidechain, "sessionId": "s", "cwd": cwd,
                       "message": {"id": msg_id, "model": model, "role": "assistant", "content": content,
                                   "usage": {"input_tokens": 1, "cache_creation_input_tokens": 0,
                                             "cache_read_input_tokens": 10, "output_tokens": output}}}, ensure_ascii=False)


def put(cfg, rel, lines):
    p = Path(cfg) / "projects" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def setup(r, name):
    f = r.fixture("te-" + name, count=2)
    main = Path(f.clones[0]).resolve().as_posix()
    cfg = r.scratch / (name + "-claude")
    return f, main, str(cfg), "/home/someone"


def tokens(r, f, cfg, *args):
    return r.run([r.bash, ".uak/bin/tokens", *args], cwd=f.clones[0], env=env(f, cfg), allowed=None)


def by(r, f, cfg, what):
    out = tokens(r, f, cfg, "--json", "--by", what)
    expect(out.returncode == 0, "tokens --by %s: %s" % (what, out.stdout + out.stderr))
    return {row["key"]: row["output"] for row in json.loads(out.stdout)}


def a_session_started_elsewhere_counts(r):
    f, main, cfg, home = setup(r, "elsewhere")
    put(cfg, enc(home) + "/s1.jsonl", [
        line("msg_00", 7, home, text="before any call in the repository"),
        line("msg_00b", 4000, home, tool=("Bash", {"command": "ls %s-other/x" % main})),   # a sibling folder is not the repository
        line("msg_01", 100, home, tool=("Bash", {"command": 'cd "%s-wt/uak-124" && ls' % main})),
        line("msg_02", 20, home, text="reading the result"),
        line("msg_03", 300, home, tool=("Read", {"file_path": main + "/README.md"})),
    ])
    put(cfg, enc("/home/someone/else") + "/s2.jsonl", [line("msg_09", 9000, "/home/someone/else", tool=("Bash", {"command": "ls /tmp"}))])
    got = by(r, f, cfg, "task")
    expect(got.get("UAK-124") == 120, "calls in the worktree (and the message after them) count for its task: %s" % got)
    expect(got.get("main") == 300 and "UAK-1240" not in got, "a call in the main checkout counts for main: %s" % got)
    expect(sum(got.values()) == 120 + 300, "only what ran in the repository: before the first call and an unrelated session are not counted: %s" % got)
    # A session that started in a worktree keeps counting from its folder, as before.
    put(cfg, enc(main) + "-wt-uak-122/s3.jsonl", [line("msg_05", 55, main + "-wt/uak-122")])
    expect(by(r, f, cfg, "task").get("UAK-122") == 55, "a session started in a worktree still belongs to its task")
    return "counted"


def subagent_tokens_go_to_their_task(r):
    f, main, cfg, home = setup(r, "subagent")
    put(cfg, enc(home) + "/s1.jsonl", [line("msg_l1", 11, home, tool=("Bash", {"command": "cd %s && git status" % main}))])
    put(cfg, enc(home) + "/s1/subagents/agent-a.jsonl", [
        line("msg_a1", 500, home, tool=("Edit", {"file_path": main + "-wt/uak-122/kit/x.sh"}), sidechain=True),
        line("msg_a2", 50, home, text="done", sidechain=True)])
    put(cfg, enc(home) + "/s1/subagents/agent-b.jsonl", [
        line("msg_b1", 700, home, tool=("Edit", {"file_path": main + "-wt/uak-124/kit/y.sh"}), sidechain=True)])
    task = by(r, f, cfg, "task")
    expect(task.get("UAK-122") == 550 and task.get("UAK-124") == 700 and task.get("main") == 11, "each subagent to the task it worked in: %s" % task)
    scope = by(r, f, cfg, "scope")
    expect(scope.get("subagent") == 1250 and scope.get("lead") == 11, "still told apart from the lead: %s" % scope)
    return "attributed"


def tokens_by_step(r):
    f, main, cfg, home = setup(r, "step")
    wt = main + "-wt/uak-124"
    put(cfg, enc(home) + "/s1.jsonl", [
        line("msg_s1", 1000, home, tool=("Bash", {"command": "cd %s && bash .uak/bin/q go test" % wt})),
        line("msg_s2", 20, home, text="the tests pass"),
        line("msg_s3", 30, home, tool=("Bash", {"command": "cd %s && UAK_AGENT=kit-r1 bash .uak/bin/uak review UAK-124 --sha abc --verdict approve" % main})),
        line("msg_s4", 40, home, text="approved"),
        line("msg_s5", 50, home, tool=("Bash", {"command": "cd %s && UAK_AGENT=kit-r1 bash .uak/bin/uak merge UAK-124" % main})),
        line("msg_s6", 60, home, text="merged"),
        line("msg_s7", 70, home, tool=("Bash", {"command": "cd %s && bash .uak/bin/uak status --task UAK-124" % main})),
    ])
    step = by(r, f, cfg, "step")
    expect(step == {"author": 1020, "review": 70, "merge": 110, "lead": 70}, "split of the task: %s" % step)
    task = by(r, f, cfg, "task")
    expect(task == {"UAK-124": 1020 + 70 + 110 + 70}, "review, merge and status of UAK-124 belong to UAK-124: %s" % task)
    # Published too: the step travels in the machine's file and --team shows it.
    f.claim(1, "HACK-002")
    pub = tokens(r, f, cfg, "--publish")
    expect(pub.returncode == 0 and "published" in pub.stdout, "publish: " + pub.stdout + pub.stderr)
    team = tokens(r, f, cfg, "--team", "--json", "--by", "step")
    got = {row["key"]: row["output"] for row in json.loads(team.stdout)}
    expect(got == step, "--team --by step: %s %s" % (got, team.stderr))
    return "split"


def budget_warns_once_crossed(r):
    f, main, cfg, home = setup(r, "budget")
    put(cfg, enc(home) + "/s1.jsonl", [line("msg_x", 2000, home, tool=("Bash", {"command": "cd %s-wt/uak-124 && ls" % main}))])   # 2011 tokens
    project = Path(f.clones[0]) / ".uak/PROJECT.md"
    base = project.read_text(encoding="utf-8")
    ask = lambda task="UAK-124": tokens(r, f, cfg, "--budget-check", task)
    none = ask()
    expect(none.returncode == 0 and none.stdout.strip() == "", "no budget, no warning: %r" % none.stdout)
    for value, crossed in (("1M", False), ("2011", False), ("1k", True), ("1,500", True), ("`1k`", True)):
        project.write_text(base + "\nToken-Budget: %s\n" % value, encoding="utf-8")
        out = ask()
        expect(out.returncode == 0, "rc 0: " + out.stderr)
        if crossed:
            expect(out.stdout.startswith("TOKENS_BUDGET: UAK-124 spent") and "Token-Budget of " in out.stdout, "%s crossed: %r" % (value, out.stdout))
        else:
            expect(out.stdout.strip() == "", "%s not crossed: %r" % (value, out.stdout))
    project.write_text(base + "\n- **Token-Budget:** `1k`\n", encoding="utf-8")
    expect(ask("UAK-122").stdout.strip() == "", "another task has spent nothing")
    expect(ask("uak-124").stdout.startswith("TOKENS_BUDGET: UAK-124"), "the ID is case-insensitive")
    return "warned"


def no_content_leaves_the_machine(r):
    f, main, cfg, home = setup(r, "content")
    put(cfg, enc(home) + "/s1.jsonl", [
        line("msg_c1", 10, home, text="my password is " + SECRET, tool=("Bash", {"command": "cd %s-wt/uak-124 && echo %s" % (main, SECRET)})),
        line("msg_c2", 10, home, text=SECRET)])
    f.claim(1, "HACK-002")
    out = tokens(r, f, cfg, "--publish")
    expect(out.returncode == 0 and SECRET not in out.stdout + out.stderr, "nothing printed: " + out.stdout + out.stderr)
    team = tokens(r, f, cfg, "--team")
    expect(SECRET not in team.stdout + team.stderr, "nothing shown")
    clone = f.base / "content-check"
    r.g(f.base, "clone", "-q", "-b", "claims", f.remote, clone)
    published = [p for p in (clone / "tokens").glob("*.md")]
    expect(published, "a file was published")
    body = "\n".join(p.read_text(encoding="utf-8") for p in published)
    expect(SECRET not in body and "UAK-124" in body and "claude-x" in body and "author" in body, "only task IDs, model names and counts: " + body[-400:])
    allfiles = r.g(clone, "grep", "-c", SECRET, allowed=(0, 1)).stdout
    expect(allfiles.strip() == "", "no file of claims carries the text: " + allfiles)
    return "counts only"


TESTS = [a_session_started_elsewhere_counts, subagent_tokens_go_to_their_task, tokens_by_step, budget_warns_once_crossed, no_content_leaves_the_machine]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-tokens-elsewhere-") as tmp:
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
    print("TOKENS_ELSEWHERE_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
