#!/usr/bin/env python3
"""uak v5.4: the Chilangatón autopsy (Oct 2026): 5 humans, 10 Claude Code identities on macOS and Windows, 35
tasks in 7 hours on venue Wi-Fi. One test per kit failure seen there: a merge that lost a race, a base fetch with
no retry, a done after a cross-machine handover, and reviewers who could not clean up their review checkouts.
Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import os
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm
from test_v43 import push_main
from test_coordination import hack


def merge_of_a_merged_task_is_done(r):
    """PB-024: an adopter merged the approved task; 19 s later its owner's `uak merge` went to the human queue as
    "Task without claim; cannot merge", wrote "Humano: …" on the INTEGRATED record and messaged the human."""
    f = rm.fixture(r, "v54-merged", count=2)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    f.claim(1, "HACK-002")                                  # the adopter is an agent with work of its own
    adopted = f.hack(1, "merge", "HACK-001", now=1000021 + 1300, allowed=None)
    expect(adopted.returncode == 0 and "INTEGRATED" in adopted.stdout, "the adopter merges: " + adopted.stdout + adopted.stderr)
    late = f.hack(0, "merge", "HACK-001", now=1000021 + 1320, allowed=None)
    out = late.stdout + late.stderr
    expect(late.returncode == 0 and "already INTEGRATED by agent-2" in out, "the owner's late merge is done: " + out)
    expect("MERGE_HUMAN" not in out, "no human queue: " + out)
    record = f.show("tasks/HACK-001.md")
    expect("Humano" not in record and "State: INTEGRATED" in record, "the record stays clean: " + record)
    expect("in human queue" not in f.show("inbox/log.md"), "no message to the human")
    expect("State: HUMAN" not in f.show("queue/HACK-001.md"), "no HUMAN queue entry")
    return {"merged": True}


def merge_that_loses_the_queue_race_is_done(r):
    """The PB-024 order: the adopter holds the merge lock (its candidate's smoke runs) while the owner's merge waits
    on "Queue busy"; when the adopter finalizes, the owner's next lock finds the task INTEGRATED."""
    f = rm.fixture(r, "v54-race", count=2)
    slow = (f.seed / ".uak/bin/smoke-project").read_text(encoding="utf-8")
    push_main(f, {".uak/bin/smoke-project": "sleep 6\n" + slow}, "slow product smoke")
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip, now=1000021)
    f.claim(1, "HACK-002")
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        adopter = pool.submit(f.hack, 1, "merge", "HACK-001", now=1000021 + 1300, allowed=None)
        deadline = time.monotonic() + 60
        while "merge-lock.md" not in " ".join(f.files("queue")):
            expect(time.monotonic() < deadline and not adopter.done(), "the adopter takes the lock")
            time.sleep(0.2)
        owner = f.hack(0, "merge", "HACK-001", now=1000021 + 1310, allowed=None)
        adopted = adopter.result(timeout=240)
    expect(adopted.returncode == 0 and "INTEGRATED" in adopted.stdout, "the adopter merges: " + adopted.stdout + adopted.stderr)
    out = owner.stdout + owner.stderr
    expect(owner.returncode == 0 and "already INTEGRATED by agent-2" in out and "MERGE_HUMAN" not in out,
           "the owner who lost the race is done: " + out)
    expect("Humano" not in f.show("tasks/HACK-001.md"), "the record stays clean")
    expect("in human queue" not in f.show("inbox/log.md"), "no message to the human")
    expect("State: HUMAN" not in f.show("queue/HACK-001.md"), "no HUMAN queue entry")
    return {"race": True}


def base_fetch_retries_and_says_why(r):
    """10 `done` failed as "Could not read PROJECT.md on remote main" on venue Wi-Fi: one try, git's error hidden."""
    if os.name == "nt":
        return {"skipped": "Git Bash's launcher puts its own git before a PATH shim"}
    f = rm.fixture(r, "v54-flaky", count=1)
    f.claim(0, "HACK-001")
    rm.publish(f, 0, "HACK-001")
    shim = f.base / "shim"; shim.mkdir()
    flag = f.base / "failures"
    (shim / "git").write_text(
        "#!/usr/bin/env bash\n"
        "case \" $* \" in *' fetch '*refs/uak/config*)\n"
        "  n=$(cat \"$SHIM_FLAG\" 2>/dev/null || echo 0)\n"
        "  if [ \"$n\" -lt \"$SHIM_FAILS\" ]; then echo $((n + 1)) > \"$SHIM_FLAG\"\n"
        "    echo \"fatal: unable to access 'https://example.test/x.git/': Could not resolve host: example.test\" >&2; exit 128; fi;;\n"
        "esac\nexec \"$REAL_GIT\" \"$@\"\n", encoding="utf-8")
    os.chmod(shim / "git", 0o755)
    env = {"PATH": shim.as_posix() + os.pathsep + r.env.get("PATH", ""), "REAL_GIT": r.git,
           "SHIM_FLAG": flag.as_posix(), "UAK_AGENT": "agent-1", "UAK_NOW": "1000010", "UAK_HUMAN": ""}
    done = lambda fails, allowed: r.run([r.bash, ".uak/bin/uak", "done", "HACK-001", "--pr", "https://example.test/pull/1",
                                         "--evidence", "Fixture product acceptance"], cwd=f.worktrees[0],
                                        env={**env, "SHIM_FAILS": str(fails)}, allowed=allowed)
    down = done(9, None)
    out = down.stdout + down.stderr
    expect(down.returncode != 0 and "3 tries" in out and "Could not resolve host" in out, "the real reason: " + out)
    flag.unlink()
    once = done(1, None)
    expect(once.returncode == 0 and "REVIEW" in once.stdout, "one dropped fetch is retried: " + once.stdout + once.stderr)
    return {"retried": True}


def done_after_a_cross_machine_handover(r):
    """PB-027 moved from a Windows laptop to a Mac: done read the Windows path and died with "Missing worktree to
    record Task-Tip"; release and re-claim were the way out."""
    f = rm.fixture(r, "v54-handover", count=1)
    f.claim(0, "HACK-001")
    tip = rm.publish(f, 0, "HACK-001")
    moved = f.base / "other-machine"
    r.g(f.clones[0], "worktree", "move", f.worktrees[0], moved)
    f.worktrees[0] = moved
    done = f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance",
                  now=1000010, allowed=None)
    expect(done.returncode == 0 and "REVIEW" in done.stdout, "done from the new checkout: " + done.stdout + done.stderr)
    record = f.show("tasks/HACK-001.md")
    expect("Task-Tip: " + tip in record, "the tip of this checkout: " + record)
    where = moved.resolve().as_posix()
    if os.name == "nt":  # Git Bash records /c/Users/..., its own form, everywhere
        where = "/" + where[0].lower() + where[2:]
    expect("Worktree: " + where in record, "the new path is recorded: " + record)
    g = rm.fixture(r, "v54-handover-main", count=1)
    g.claim(0, "HACK-001")
    rm.publish(g, 0, "HACK-001")
    r.g(g.clones[0], "worktree", "remove", g.worktrees[0])
    r.g(g.clones[0], "checkout", "-q", g.branches[0])
    main = r.run([r.bash, ".uak/bin/uak", "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok"],
                 cwd=g.clones[0], env={"UAK_AGENT": "agent-1", "UAK_NOW": "1000010"}, allowed=None)
    expect(main.returncode == 2 and "is not on this machine" in main.stderr, "never the main checkout: " + main.stdout + main.stderr)
    return {"handover": True}


def review_checkout_is_removed_safely(r):
    """11 guard blocks on `worktree remove --force`: reviewers' detached checkouts kept Verify's build output, so a
    plain remove refused, and the guard's hint (`wt rm ID`) named the owner's worktree."""
    f = rm.fixture(r, "v54-review-rm", count=1)
    clone = f.clones[0]
    wt = lambda *a: r.run([r.bash, ".uak/bin/wt", "rm", *map(str, a)], cwd=clone, allowed=None)
    review = f.base / "review-HACK-001"
    r.g(clone, "worktree", "add", "-q", review, "origin/main")
    (review / "build.log").write_text("vite build\n", encoding="utf-8")
    plain = r.g(clone, "worktree", "remove", review, allowed=None)
    expect(plain.returncode != 0, "the plain remove refuses untracked output")
    gone = wt("--review", review)
    expect(gone.returncode == 0 and "WT_REMOVED" in gone.stdout and not review.exists(), gone.stdout + gone.stderr)

    r.g(clone, "worktree", "add", "-q", review, "origin/main")
    (review / ".uak/TASKS.md").write_text("edited\n", encoding="utf-8")
    edited = wt("--review", review)
    expect(edited.returncode == 2 and "edits to tracked files" in edited.stderr and review.exists(), edited.stderr)

    r.g(review, "checkout", "-q", "--", ".uak/TASKS.md")
    r.g(review, "-c", "user.name=R", "-c", "user.email=r@example.invalid", "commit", "-q", "--allow-empty", "-m", "local")
    stray = wt("--review", review)
    expect(stray.returncode == 2 and "commits on no branch" in stray.stderr and review.exists(), stray.stderr)

    branch = wt("--review", f.worktrees[0])
    expect(branch.returncode == 2 and "is on a branch" in branch.stderr and f.worktrees[0].exists(), branch.stderr)
    main = wt("--review", clone)
    expect(main.returncode == 2 and "not a worktree" in main.stderr, main.stderr)
    guard = lambda cmd: r.run([r.bash, ".uak/bin/guard", "check", cmd], cwd=clone, allowed=None)
    ok = guard("bash .uak/bin/wt rm --review ../review-HACK-001")
    expect(ok.returncode == 0 and "allowed" in ok.stdout, "the review cleanup passes the guard: " + ok.stdout + ok.stderr)
    blocked = guard("git worktree remove --force ../review-HACK-001")
    expect(blocked.returncode != 0 and "wt rm --review PATH" in blocked.stdout + blocked.stderr,
           "--force is still blocked, and the block names the review cleanup: " + blocked.stdout + blocked.stderr)
    return {"review_rm": True}


def reviews_go_to_agents_only(r):
    """14 of 48 review offers went to "github" (the sender of pr-sync messages: idle, no verdicts, so the rotation's
    best pick) and 3 to a human's UAK_HUMAN name; each sat 15 min until the re-offer."""
    f = rm.fixture(r, "v54-reviewer", count=2)
    f.claim(0, "HACK-001")
    f.claim(1, "HACK-002")                                   # the only other agent: busy, with a task of its own
    events = f.base / "gh-events.txt"
    events.write_text("comment\tIC_1\t#1 @alice: rename it\n", encoding="utf-8")
    fake = f.base / "gh"
    fake.write_text("#!/usr/bin/env bash\n[ \"$1 $2\" = \"pr view\" ] || exit 1\ncat '%s'\n" % events, encoding="utf-8")
    os.chmod(fake, 0o755)
    hack(f, 0, "pr-sync", "HACK-001", now=1000005, UAK_GH=str(fake))
    r.run([r.bash, ".uak/bin/uak", "msg", "all", "plan approved, go"], cwd=f.clones[0],
          env={"UAK_AGENT": "", "UAK_HUMAN": "Boss", "UAK_NOW": "1000006"})
    expect("| github |" in f.show("inbox/log.md") and "| Boss |" in f.show("inbox/log.md"), "github and a human were seen")
    rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance", now=1000010)
    offer = [l for l in f.show("inbox/log.md").splitlines() if "| review | HACK-001 |" in l][-1]
    expect("| agent:agent-2 |" in offer, "the offer goes to the other agent, never github or a human: " + offer)
    return {"reviewer": "agent-2"}


def pr_sync_tells_a_forge_merge(r):
    """PB-027 and PB-035 were merged on GitHub and stayed in REVIEW on claims after the event: nothing said so."""
    f = rm.fixture(r, "v54-forge-merge", count=1)
    rm.ready(f, 0, "HACK-001")
    events = f.base / "gh-events.txt"
    events.write_text("merged\t7\t#7 was merged on GitHub; the task is still open on claims\n", encoding="utf-8")
    fake = f.base / "gh"
    fake.write_text("#!/usr/bin/env bash\n[ \"$1 $2\" = \"pr view\" ] || exit 1\ncat '%s'\n" % events, encoding="utf-8")
    os.chmod(fake, 0o755)
    out = hack(f, 0, "pr-sync", "HACK-001", now=1000030, UAK_GH=str(fake))
    line = [l for l in f.show("inbox/log.md").splitlines() if "| github |" in l][-1]
    expect("HACK-001 (1)" in out.stdout and "uak integrate HACK-001" in line, "the task hears it, with the command: " + line)
    github = (r.package / ".uak/bin/lib/github.sh").read_text(encoding="utf-8")
    expect("coderabbitai" in github and 'test("^\\\\s*<!--")' in github, "bot logins and generated bodies are not human comments")
    return {"merged": True}


def hook_stops_beating_a_task_that_moved(r):
    """After a Windows → macOS handover the old session kept heartbeating PB-027 ("belongs to", "has no active
    claim") into the black box."""
    import json
    f = rm.fixture(r, "v54-gone", count=2)
    f.claim(1, "HACK-001")                                   # the task is agent-2's now
    w = f.worktrees[0]
    (w / ".uak-env").write_text("UAK_AGENT=agent-1\nUAK_TASK=HACK-001\n", encoding="utf-8")
    gd = Path(r.g(w, "rev-parse", "--absolute-git-dir").stdout.strip())
    payload = json.dumps({"session_id": "s1", "hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}})
    (w / ".git-payload.json").write_text(payload, encoding="utf-8")
    tick = lambda: r.run([r.bash, "-c", "bash .uak/bin/hook tick < .git-payload.json"], cwd=w, env={"UAK_NOW": "1000100"}, allowed=None)
    tick()
    deadline = time.monotonic() + 90
    while not (gd / "uak-task-gone").exists():
        expect(time.monotonic() < deadline, "the beat that conflicts marks the task: " + (gd / "uak-heartbeat.log").read_text(encoding="utf-8", errors="replace")
               if (gd / "uak-heartbeat.log").exists() else "no heartbeat log")
        time.sleep(0.5)
    told = tick()
    expect("HACK-001 is no longer this worktree's" in told.stdout, "the agent hears it once: " + told.stdout)
    (gd / "uak-heartbeat").unlink()
    again = tick()
    expect("no longer" not in again.stdout, "once: " + again.stdout)
    time.sleep(2)
    expect((gd / "uak-heartbeat").exists() is False, "no more beats for a task that moved")
    return {"gone": True}


def errors_say_the_fix(r):
    """`done` "Invalid option." with no name, `checkpoint needs all six fields` twice, `plan` "no ## ID sections";
    approvals waited 11 min on average for their owner's merge in a 7-hour sprint (12 "merge it now" messages)."""
    f = rm.fixture(r, "v54-errors", count=1)
    f.claim(0, "HACK-001")
    bad = f.hack(0, "done", "HACK-001", "--summary", allowed=None)
    expect(bad.returncode == 2 and "Invalid option --summary for done. Usage: done ID --pr URL" in bad.stderr, bad.stderr)
    cp = f.hack(0, "checkpoint", "HACK-001", "--done", "x", "--next", "y", allowed=None)
    expect("missing: --decision --why --fails --commands" in cp.stderr, cp.stderr)
    plan = f.base / "plan.md"; plan.write_text("## pb-030 · lower-case id\n", encoding="utf-8")
    pl = r.run([r.bash, ".uak/bin/uak", "plan", str(plan)], cwd=f.clones[0], env={"UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_NOW": "1000001"}, allowed=None)
    expect("## PB-030 · Title" in pl.stderr or "Plan-Channel" in pl.stderr, pl.stderr)
    sprint = (r.package / ".uak/templates/PROJECT.sprint.md").read_text(encoding="utf-8")
    expect("Merge-Adopt-Seconds: 300" in sprint, "sprint: any agent merges an approval after 5 min")
    ci = (r.package / ".github/workflows/uak.yml").read_text(encoding="utf-8")
    expect(ci.index("astral-sh/setup-uv") < ci.index("Product smoke") and "actions/setup-node" in ci, "CI installs the stack's tools before the smoke")
    return {"errors": True}


def a_retry_reuses_the_base(r):
    """"done/review/status retry 10+ times and take over 8 min" on venue Wi-Fi: done/integrate/merge fetched the
    whole base again from the remote on every retry. A pre-push hook moves claims once, so done retries for real."""
    f = rm.fixture(r, "v54-refetch", count=1)
    f.claim(0, "HACK-001")
    rm.publish(f, 0, "HACK-001")
    remote = r.g(f.clones[0], "config", "--get", "remote.origin.url").stdout.strip()
    tpl = f.base / "tpl"; (tpl / "hooks").mkdir(parents=True)
    state = f.base / "moved-once"
    (tpl / "hooks/pre-push").write_text(
        "#!/usr/bin/env bash\n[ -e '%s' ] && exit 0\n: > '%s'\n"
        "tip=$(git ls-remote '%s' refs/heads/claims | cut -f1)\n"
        "c=$(git -c user.name=x -c user.email=x@x.invalid commit-tree \"$tip^{tree}\" -p \"$tip\" -m race)\n"
        "git push -q --no-verify '%s' \"$c:refs/heads/claims\"\nexit 0\n" % (state, state, remote, remote), encoding="utf-8")
    os.chmod(tpl / "hooks/pre-push", 0o755)
    trace = f.base / "git-trace.log"
    done = r.run([r.bash, ".uak/bin/uak", "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance"],
                 cwd=f.worktrees[0], env={"UAK_AGENT": "agent-1", "UAK_NOW": "1000010", "GIT_TEMPLATE_DIR": str(tpl), "GIT_TRACE": str(trace)}, allowed=None)
    expect(done.returncode == 0 and "attempt 2" in done.stdout, "done retried once: " + done.stdout + done.stderr)
    log = trace.read_text(encoding="utf-8", errors="replace")
    remote_base = [l for l in log.splitlines() if "built-in: git fetch" in l and "refs/heads/main:refs/uak/config" in l and " origin " in l]
    expect(len(remote_base) == 1, "the base came from the remote once, not once per try: %d\n%s" % (len(remote_base), "\n".join(remote_base)))
    return {"fetches": len(remote_base)}


def frontend_uses_the_design_system(r):
    """The first UI of the event was redone 3 hours in: the plan wrote the direction as a sentence ("sober, public
    document"), skipped the screenshots, and 10 views started before the design system, each on raw stone-*/emerald-*
    classes, a hand-typed orange and its own badge. design-taste-frontend says on line 1 it is not for app screens."""
    pkg = r.package.parent
    t = r.scratch / "v54-design"; (t / "web/src/lib/ui").mkdir(parents=True); (t / "web/src/features/mapa").mkdir(parents=True)
    r.g(t, "init", "-q", "-b", "main")
    lint = lambda: r.run([r.bash, str(r.package / ".uak/bin/design-lint")], cwd=t, allowed=None)
    (t / "web/src/features/mapa/index.tsx").write_text('<div className="bg-stone-400 p-4">x</div>\n', encoding="utf-8")
    skip = lint()
    expect(skip.returncode == 0 and "DESIGN_LINT_SKIP: no design tokens yet" in skip.stdout, "nothing to enforce before the lock: " + skip.stdout)
    (t / "web/src/lib/ui/tokens.css").write_text(":root { --pb-acento: #c8006e; }\n", encoding="utf-8")
    (t / "web/src/lib/ui/Boton.tsx").write_text("export function Boton() { return null }\n", encoding="utf-8")
    (t / "web/src/features/mapa/index.tsx").write_text(
        '<div className="bg-stone-400 p-4">x</div>\n'
        'const naranja = "#c2410c";\n'
        'function Boton() { return null }\n'
        '<a href="#/sedeco" className="text-[var(--pb-acento,#c8006e)]">ok</a>\n'
        'const capa = "#e6007e"; // design-lint: ok · Mapbox paint reads the token once at start\n', encoding="utf-8")
    bad = lint()
    out = bad.stdout
    expect(bad.returncode == 1 and "DESIGN_LINT_FAIL 3 finding(s)" in out, "three findings: " + out)
    expect("index.tsx:1 · raw palette class bg-stone-400" in out and "index.tsx:2 · hex color #c2410c" in out
           and "index.tsx:3 · local Boton" in out, "each finding names line, what and fix: " + out)
    expect("#c8006e" not in out and "#/sedeco" not in out and "e6007e" not in out, "fallbacks, routes and waived lines pass: " + out)
    (t / "web/src/features/mapa/index.tsx").write_text('import { Boton } from "../../lib/ui/Boton";\n<div className="bg-[var(--pb-acento)]" />\n', encoding="utf-8")
    good = lint()
    expect(good.returncode == 0 and "DESIGN_LINT_PASS files=1" in good.stdout, good.stdout)

    for mode, stack, want in (("sprint", "none", True), ("marathon", "fastapi-react", True), ("marathon", "none", False)):
        d = r.scratch / ("v54-design-" + mode + "-" + stack); d.mkdir()
        r.g(d, "init", "-q", "-b", "main")
        r.run([r.bash, str(pkg / "install.sh"), "--mode", mode, "--stack", stack, "--harness", "claude", str(d)], cwd=d)
        expect((d / ".claude/skills/product-ui/SKILL.md").exists() == want, "product-ui installed for %s/%s: %s" % (mode, stack, want))
        expect((d / ".claude/skills/landing-story/SKILL.md").exists() == want, "landing-story installed for %s/%s: %s" % (mode, stack, want))
    text = lambda rel: (r.package / rel).read_text(encoding="utf-8")
    expect("**Design lock P0**" in text(".claude/commands/uak-plan.md") and "never merged into another task" in text(".claude/commands/uak-plan.md")
           and "ls web/public/design-lock/screens/*-1280.png" in text(".claude/commands/uak-plan.md"), "the plan makes the design lock its own task, verified by screenshots")
    expect("Never skip the screenshots" in text(".claude/commands/uak-design-lock.md") and "a floor every direction meets" in text(".claude/commands/uak-design-lock.md"),
           "the lock is picked by looking; accessibility is a floor, not a style")
    expect("design-lint" in text(".claude/agents/design-critic.md") and "VERDICT: SHIP" in text(".claude/agents/design-critic.md") and "did not open" in text(".claude/agents/design-critic.md"), "the critic runs the gate, looks at the screenshots and writes the verdict done checks")
    expect("`product-ui`" in text(".uak/stacks/fastapi-react/skills/stack-frontend/SKILL.md"), "app screens route to product-ui")
    expect("**Landing P0**" in text(".claude/commands/uak-plan.md") and "landing-story" in text(".claude/agents/design-critic.md")
           and "`landing-story`" in text(".uak/stacks/fastapi-react/skills/stack-frontend/SKILL.md"), "the landing is planned, built and judged as a story")
    story = text(".uak/skills/landing-story/SKILL.md")
    expect("IDEA.md" in story and "5-second test" in story and "fake dashboard" in story and "cover the logo" in story, "the landing skill works from the idea, with real screens")
    expect("bash .uak/bin/design-lint &&" in text(".uak/stacks/fastapi-react/STACK.md"), "the stack smoke runs the gate")
    return {"design": True}


def done_checks_the_design_and_humans_record_forge_merges(r):
    """The design gate at the moment the agent can still fix it (done), on the lines the task adds only; and PB-027:
    merged on GitHub by a human with no approval on claims, integrate refused and the task stayed in REVIEW."""
    f = r.fixture("v54-done-design", paths={"HACK-001": "web/src/features/mapa/"}, count=1)
    push_main(f, {"web/src/lib/ui/tokens.css": ":root { --pb-acento: #c8006e; }\n",
                  "web/src/features/mapa/old.tsx": '<div className="bg-stone-400" />\n'}, "design system and an old view")
    f.claim(0, "HACK-001")
    w = f.worktrees[0]
    r.g(w, "merge", "-q", "origin/main")
    (w / "web/src/features/mapa/index.tsx").write_text('<div className="bg-[var(--pb-acento)]" />\nconst c = "#c2410c";\n', encoding="utf-8")
    r.g(w, "add", "-A"); r.g(w, "commit", "-q", "-m", "feat: mapa"); r.g(w, "push", "-q", "-u", "origin", "HEAD")
    changed = r.run([r.bash, ".uak/bin/design-lint", "--changed"], cwd=w, allowed=None)
    expect(changed.returncode == 1 and "index.tsx:2 · hex color #c2410c" in changed.stdout and "old.tsx" not in changed.stdout,
           "only the lines this task adds: " + changed.stdout)
    done = lambda: f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "Fixture product acceptance",
                          now=1000010, allowed=None)
    refused = done()
    expect(refused.returncode == 2 and "break the design system" in refused.stderr and "#c2410c" in refused.stderr,
           "done refuses before anyone reviews it: " + refused.stdout + refused.stderr)
    (w / "web/src/features/mapa/index.tsx").write_text('<div className="bg-[var(--pb-acento)]" />\n', encoding="utf-8")
    r.g(w, "commit", "-q", "-am", "fix: token"); r.g(w, "push", "-q")
    ok = done()
    expect(ok.returncode == 0 and "REVIEW" in ok.stdout, "clean lines pass: " + ok.stdout + ok.stderr)

    forge = f.base / "forge"
    r.g(f.base, "clone", "-q", f.remote, forge)
    r.g(forge, "-c", "user.name=Forge", "-c", "user.email=f@example.invalid", "merge", "-q", "--no-ff", "-m", "Merge pull request #1", "origin/" + f.branches[0])
    r.g(forge, "push", "-q", "origin", "HEAD:main")
    agent = f.hack(0, "integrate", "HACK-001", now=1000040, allowed=None)
    expect(agent.returncode == 3 and "UAK_HUMAN=NAME UAK_AGENT= bash .uak/bin/uak integrate HACK-001" in agent.stderr,
           "no approval: an agent cannot, and the error says who can: " + agent.stderr)
    human = r.run([r.bash, ".uak/bin/uak", "integrate", "HACK-001"], cwd=f.clones[0],
                  env={"UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_NOW": "1000041"}, allowed=None)
    record = f.show("tasks/HACK-001.md")
    expect(human.returncode == 0 and "State: INTEGRATED" in record and "Reviewer: human:boss" in record,
           "the human who merged it records it: " + human.stdout + human.stderr + record)
    return {"design_at_done": True, "human_integrate": True}


def deploy_reads_the_project(r):
    """The deploy file was hand-written 30 min before the deadline, outside the kit."""
    deploy = lambda t, *a: r.run([r.bash, str(r.package / ".uak/bin/deploy"), *a], cwd=t, allowed=None)
    t = r.scratch / "v54-deploy"; (t / "app").mkdir(parents=True); (t / "web").mkdir()
    r.g(t, "init", "-q", "-b", "main")
    (t / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\ndependencies = ["fastapi"]\n', encoding="utf-8")
    (t / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (t / "app/main.py").write_text('@app.get("/api/health")\ndef health(): ...\n', encoding="utf-8")
    (t / "web/package.json").write_text('{"scripts": {"build": "vite build"}}\n', encoding="utf-8")
    (t / ".env.example").write_text("OPENAI_API_KEY=\nexport VITE_MAPBOX_TOKEN=pk.example\nPORT=8000\n", encoding="utf-8")
    (t / ".env").write_text("OPENAI_API_KEY=sk-live-secret-123\n", encoding="utf-8")
    plan = deploy(t)
    expect(plan.returncode == 0 and "DEPLOY fastapi-react" in plan.stdout and "health /api/health" in plan.stdout
           and "OPENAI_API_KEY VITE_MAPBOX_TOKEN" in plan.stdout and not (t / "Dockerfile").exists(), "a plan, nothing written: " + plan.stdout)
    wrote = deploy(t, "--write", "--disk", "data/live")
    dockerfile = (t / "Dockerfile").read_text(encoding="utf-8"); blueprint = (t / "render.yaml").read_text(encoding="utf-8")
    expect(wrote.returncode == 0 and "COPY --from=web /src/web/dist web/dist" in dockerfile and "ARG VITE_MAPBOX_TOKEN" in dockerfile
           and ".venv/bin/uvicorn app.main:app" in dockerfile, "one image: the React build and FastAPI: " + dockerfile)
    expect("healthCheckPath: /api/health" in blueprint and "key: OPENAI_API_KEY\n        sync: false" in blueprint
           and "mountPath: /app/data/live" in blueprint and "key: PORT" not in blueprint, "the Blueprint: " + blueprint)
    leaked = [f for f in ("Dockerfile", "render.yaml", ".dockerignore") if "sk-live-secret" in (t / f).read_text(encoding="utf-8")]
    expect(not leaked and ".env" in (t / ".dockerignore").read_text(encoding="utf-8").split(), "no secret value anywhere; .env stays out of the image")
    (t / "render.yaml").write_text("# ours\n", encoding="utf-8")
    again = deploy(t, "--write")
    expect("kept your render.yaml" in again.stdout and (t / "render.yaml").read_text(encoding="utf-8") == "# ours\n"
           and (t / "render.yaml.uak-new").exists(), "never over a file: " + again.stdout)
    n = r.scratch / "v54-deploy-next"; n.mkdir(); r.g(n, "init", "-q", "-b", "main")
    (n / "package.json").write_text('{"dependencies": {"next": "16.0.0"}}\n', encoding="utf-8")
    expect("DEPLOY nextjs · target Vercel" in deploy(n).stdout, "Next.js goes to Vercel")
    g = r.scratch / "v54-deploy-go"; (g / "cmd/api").mkdir(parents=True); r.g(g, "init", "-q", "-b", "main")
    (g / "go.mod").write_text("module x\n", encoding="utf-8"); (g / "cmd/api/main.go").write_text("package main\n", encoding="utf-8")
    deploy(g, "--write")
    expect("go build -o /out/app ./cmd/api" in (g / "Dockerfile").read_text(encoding="utf-8"), "Go builds its cmd/ main")
    e = r.scratch / "v54-deploy-none"; e.mkdir(); r.g(e, "init", "-q", "-b", "main")
    expect(deploy(e).returncode == 1, "no stack, no guess")
    return {"deploy": True}


def ui_edits_get_the_gate_at_once(r):
    """Findings reach the agent right after it writes a UI file (Impeccable runs its detector from a post-edit hook),
    and the gate knows the AI tells: emoji icons, bounce easing, default typefaces."""
    import json
    f = r.fixture("v54-uilint", paths={"HACK-001": "web/src/features/a/"}, count=1)
    push_main(f, {"web/src/lib/ui/tokens.css": ":root { --pb-acento: #c8006e; }\n"}, "tokens")
    w = f.worktrees[0]
    r.g(w, "merge", "-q", "origin/main")
    (w / ".uak-env").write_text("UAK_AGENT=agent-1\nUAK_TASK=HACK-001\n", encoding="utf-8")
    view = w / "web/src/features/a/index.tsx"; view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text('<div className="animate-bounce">\U0001F680 Lanzar</div>\n', encoding="utf-8")
    (w / "web/src/index.css").write_text('body { font-family: "Inter", sans-serif; }\n', encoding="utf-8")
    full = r.run([r.bash, ".uak/bin/design-lint"], cwd=w, allowed=None)
    expect("bounce easing" in full.stdout and "emoji in the UI" in full.stdout and "default typeface" in full.stdout, full.stdout)
    payload = {"session_id": "s1", "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": str(view)}}
    (w / ".git-payload.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tick = r.run([r.bash, "-c", "bash .uak/bin/hook tick < .git-payload.json"], cwd=w, env={"UAK_NOW": "1000100"}, allowed=None)
    expect("UAK design-lint on index.tsx" in tick.stdout and "bounce easing" in tick.stdout, "the agent hears it after the edit: " + tick.stdout)
    view.write_text('<div className="bg-[var(--pb-acento)]">Lanzar</div>\n', encoding="utf-8")
    clean = r.run([r.bash, "-c", "bash .uak/bin/hook tick < .git-payload.json"], cwd=w, env={"UAK_NOW": "1000101"}, allowed=None)
    expect("design-lint" not in clean.stdout, "a clean file says nothing: " + clean.stdout)
    expect((r.package / ".uak/skills/frontend-design/LICENSE.txt").exists() and "frontend-design" in (r.package / ".uak/skills/SOURCES.md").read_text(encoding="utf-8"),
           "Anthropic's frontend-design is vendored with its license and pinned")
    return {"hook": True}


def the_human_sees_the_directions(r):
    """In a terminal the design lock's screenshots were files nobody opened; the look was decided from a sentence."""
    t = r.scratch / "v54-gallery"; d = t / "web/public/design-lock"; d.mkdir(parents=True)
    r.g(t, "init", "-q", "-b", "main")
    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000" "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
    for name in ("1-1280.png", "1-390.png", "2-1280.png", "extra.png"):
        (d / name).write_bytes(png)
    (d / "1.md").write_text("Night market <script>\nPink and marigold on ink; the 3D map is the hero.\nRecommended: yes\n", encoding="utf-8")
    out = r.run([r.bash, str(r.package / ".uak/bin/design-gallery"), "--no-open"], cwd=t, allowed=None)
    page = (d / "index.html").read_text(encoding="utf-8")
    expect(out.returncode == 0 and "DESIGN_GALLERY 2 direction(s)" in out.stdout and "file://" in out.stdout, out.stdout + out.stderr)
    expect('src="1-1280.png"' in page and 'src="1-390.png"' in page and 'src="2-1280.png"' in page and "More screens" in page and "extra.png" in page, page[:400])
    expect("Night market &lt;script&gt;" in page and "<script>" not in page and "work pick" in page and "Direction 2" in page and "3 directions" not in page, "names escaped, the pick marked")
    expect("http" not in page.replace("http-equiv", ""), "no network: the page works from the folder")
    empty = r.scratch / "v54-gallery-empty"; (empty / "web/public/design-lock").mkdir(parents=True); r.g(empty, "init", "-q", "-b", "main")
    none = r.run([r.bash, str(r.package / ".uak/bin/design-gallery"), "--no-open"], cwd=empty, allowed=None)
    expect(none.returncode == 1 and "no screenshots" in none.stderr, none.stderr)
    expect("uak design-gallery" in (r.package / ".claude/commands/uak-design-lock.md").read_text(encoding="utf-8"), "the lock opens them for the human")
    import urllib.request
    served = r.run([r.bash, str(r.package / ".uak/bin/design-gallery"), "--serve", "18790"], cwd=t, allowed=None)
    try:
        urls = [l.split("http://localhost:", 1)[1].split("/", 1)[0] for l in served.stdout.splitlines() if "http://localhost:" in l]
        expect(urls, "the server printed its URL: " + served.stdout + served.stderr)
        port = urls[0]
        expect(served.returncode == 0 and "ssh -L %s:127.0.0.1:%s" % (port, port) in served.stdout, "the tunnel to use over SSH: " + served.stdout + served.stderr)
        body = urllib.request.urlopen("http://127.0.0.1:%s/" % port, timeout=10).read().decode("utf-8")
        expect("Design lock" in body and 'src="1-1280.png"' in body, "served on localhost, in the background: " + body[:200])
        expect("0.0.0.0" not in served.stdout, "never on every interface")
    finally:
        stop = r.run([r.bash, str(r.package / ".uak/bin/design-gallery"), "--stop"], cwd=t, allowed=None)
    expect("stopped" in stop.stdout and not (d / ".gallery.pid").exists(), stop.stdout)
    return {"gallery": True}


def doctor_never_waits_on_the_terminal(r):
    """On macOS doctor hung at minute 0: BSD awk ignores -W, runs "version" as the program and reads the terminal."""
    import shutil, subprocess
    t = r.scratch / "v54-doctor-tty"; t.mkdir(); r.g(t, "init", "-q", "-b", "main")
    shim = r.scratch / "v54-bsd-awk"; shim.mkdir()
    (shim / "awk").write_text('#!/bin/sh\nif [ "$1" = -W ]; then shift 2; cat >/dev/null; exit 0; fi\nexec "%s" "$@"\n' % shutil.which("awk"), encoding="utf-8")
    (shim / "awk").chmod(0o755)
    env = r.env.copy(); env["PATH"] = "%s%s%s" % (shim, os.pathsep, env["PATH"])
    read_end, write_end = os.pipe()
    try:
        doc = subprocess.run([r.bash, str(r.package / ".uak/bin/doctor")], cwd=t, env=env, stdin=read_end, text=True,
                             capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        doc = None
    finally:
        os.close(read_end); os.close(write_end)
    expect(doc is not None and "bash" in doc.stdout and "git" in doc.stdout, "doctor finishes with an open terminal: " + (doc.stdout[-500:] if doc else "it hung"))
    return {"doctor": True}


def verify_never_reads_the_terminal(r):
    """A human ran Verify in a terminal: vitest saw a TTY, entered watch mode and wrote to a log nobody saw end."""
    if os.name == "nt":
        return {"skipped": "no pty module on Windows"}
    import base64, pty, subprocess
    t = r.scratch / "v54-verify-tty"; t.mkdir(); r.g(t, "init", "-q", "-b", "main")
    probe = ["bash", "-c", "[ ! -t 0 ]"]
    leader, follower = pty.openpty()
    try:
        run = lambda cmd: subprocess.run(cmd, cwd=t, env=r.env, stdin=follower, text=True, capture_output=True, timeout=60)
        q = run([r.bash, str(r.package / ".uak/bin/q"), *probe])
        cap = run([r.bash, str(r.package / ".uak/bin/cap"), "--b64", base64.b64encode(b"[ ! -t 0 ]").decode()])
    finally:
        os.close(leader); os.close(follower)
    expect(q.returncode == 0, "q gives Verify no terminal: " + q.stdout + q.stderr)
    expect(cap.returncode == 0, "cap gives the command no terminal: " + cap.stdout + cap.stderr)
    for path, needle in ((".uak/bin/loop", 'bash -c "$verify" > "$out" 2>&1 < /dev/null'), (".uak/bin/lib/review-merge.sh", 'bash -c "$verify" < /dev/null')):
        expect(needle in (r.package / path).read_text(encoding="utf-8"), path + " runs Verify without the terminal")
    hints = "".join((r.package / p).read_text(encoding="utf-8") for p in (".uak/bin/uak", ".uak/bin/map", ".uak/bin/uak-coordination", ".uak/bin/lib/review-merge.sh"))
    expect("git merge origin/" not in hints and "git merge %s" not in hints, "every merge hint says --no-edit: git opens an editor in a terminal")
    for mode in ("sprint", "marathon"):
        allowed = (r.package / (".uak/settings/settings.%s.json" % mode)).read_text(encoding="utf-8")
        expect('"Bash(git merge --no-edit origin/main)"' in allowed, mode + " allows the hint it gives, without a permission prompt")
    return {"tty": True}


def transcripts_of_a_home_with_an_accent(r):
    """C:\\Users\\José: Claude Code names the transcript folder per UTF-16 unit; the kit counted bytes and found none."""
    import subprocess
    src = (r.package / ".uak/bin/tokens").read_text(encoding="utf-8")
    enc = src[src.index("enc() {"):src.index("\n}\n", src.index("enc() {")) + 3]
    for path in ("/Users/José/app", "C:/Users/Peña Núñez/app", "/home/ana/😀/app"):
        out = subprocess.run([r.bash, "-c", enc + 'enc "$1"', "_", path], capture_output=True, timeout=30).stdout.decode("utf-8")
        want = "".join("-" * (len(ch.encode("utf-16-le")) // 2) if not (ch.isascii() and ch.isalnum()) else ch for ch in path)
        expect(out == want, "%s -> %s, Claude Code: %s" % (path, out, want))
    return {"accent": True}


TESTS = [merge_of_a_merged_task_is_done, merge_that_loses_the_queue_race_is_done, base_fetch_retries_and_says_why, done_after_a_cross_machine_handover,
         review_checkout_is_removed_safely, reviews_go_to_agents_only, pr_sync_tells_a_forge_merge, hook_stops_beating_a_task_that_moved,
         errors_say_the_fix, a_retry_reuses_the_base, frontend_uses_the_design_system,
         done_checks_the_design_and_humans_record_forge_merges, deploy_reads_the_project, ui_edits_get_the_gate_at_once,
         the_human_sees_the_directions, doctor_never_waits_on_the_terminal,
         verify_never_reads_the_terminal, transcripts_of_a_home_with_an_accent]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v54-") as tmp:
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
    print("V54_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
