#!/usr/bin/env python3
"""uak v5.7.1: the rest of the audit lists. Fixture folders that hold a real migration, servers a gate's Verify
leaves running, `done --to` names that cannot review, humans with a dash in their name, retired names offered as
"Known:", a Verify that needs another task's scaffold, and accented capitals in Paths. Real Git, local bare
remote, separate processes."""
import argparse
import concurrent.futures
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
import test_review_merge as rm


def push_tasks(f, transform):
    """Rewrite .uak/TASKS.md on main, as a human's PR would."""
    p = f.seed / ".uak/TASKS.md"
    p.write_text(transform(p.read_text(encoding="utf-8")), encoding="utf-8")
    f.r.g(f.seed, "add", ".uak/TASKS.md")
    f.r.g(f.seed, "commit", "-q", "-m", "TASKS.md")
    f.r.g(f.seed, "push", "-q", "origin", "main")
    for clone, worktree in zip(f.clones, f.worktrees):
        f.r.g(clone, "fetch", "-q", "origin", "main")
        f.r.g(worktree, "merge", "-q", "--no-edit", "origin/main", allowed=None)


def a_migration_under_fixtures_is_still_shared(r):
    """db/migration/fixtures/V9__x.sql skipped the human check, though Flyway runs it as a migration."""
    f = rm.fixture(r, "v571-fixtures", count=1)
    f.claim(0, "HACK-001")
    extra = f.worktrees[0] / "db/migration/fixtures/V9__seed.sql"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("insert into t values (1);\n", encoding="utf-8")
    f.r.g(f.worktrees[0], "add", "db")
    tip = rm.publish(f, 0, "HACK-001")
    f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", now=1000010)
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    out = rm.actor(f, "agent-1", "merge", "HACK-001", now=1000030, allowed=None, timeout=300)
    expect(out.returncode == 3 and "Shared resource" in out.stdout and "db/migration/fixtures" in out.stdout,
           out.stdout + out.stderr)
    return {"shared": True}


def the_gate_stops_what_verify_started(r):
    """A server started by a gate's Verify (npm run dev &) outlived the candidate and answered a later gate."""
    if os.name == "nt":
        return {"skipped": "nt"}
    f = rm.fixture(r, "v571-server", count=1)
    mark = "uakmark-" + uuid.uuid4().hex[:10]
    serve = f.base / mark
    serve.mkdir()
    def verify(text):
        return text.replace('test "$(cat src/value-1.txt)" = ready-HACK-001',
                            '(python3 -m http.server "$UAK_PORT" --bind 127.0.0.1 --directory %s >/dev/null 2>&1 &) ; '
                            'sleep 2; test "$(cat src/value-1.txt)" = ready-HACK-001' % serve.as_posix())
    push_tasks(f, verify)
    tip = rm.ready(f, 0, "HACK-001")
    rm.judge(f)
    rm.approve(f, "HACK-001", tip)
    out = rm.actor(f, "agent-1", "merge", "HACK-001", now=1000030, allowed=None, timeout=300)
    expect(out.returncode == 0 and "INTEGRATED" in out.stdout, out.stdout + out.stderr)
    time.sleep(1)
    alive = subprocess.run(["pgrep", "-f", mark], capture_output=True, text=True).stdout.split()
    for pid in alive:
        subprocess.run(["kill", pid])
    expect(not alive, "no server of the gate left running: " + " ".join(alive))
    return {"stopped": True}


def done_to_names_someone_who_can_review(r):
    """--to took any name: a retired identity, a human or a typo, and the offer waited 15 min for its re-offer."""
    f = rm.fixture(r, "v571-to", count=3)
    f.claim(1, "HACK-002")
    f.hack(2, "msg", "all", "--kind", "info", "agent-3 here at src/x", now=1000002)
    f.hack(2, "retire", "agent-3", now=1000003)
    rm.actor(f, "boss", "msg", "all", "--kind", "info", "the human here at src/x", human=True, now=1000004)
    f.claim(0, "HACK-001")
    rm.publish(f, 0, "HACK-001")
    for name, why in (("agent-3", "retired"), ("boss", "human"), ("agnet-2", "never been seen")):
        out = f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", "--to", name,
                     now=1000010, allowed=None)
        expect(out.returncode == 3 and why in out.stderr, name + ": " + out.stdout + out.stderr)
    ok = f.hack(0, "done", "HACK-001", "--pr", "https://example.test/pull/1", "--evidence", "ok", "--to", "agent-2",
                now=1000011)
    expect(ok.returncode == 0, ok.stderr)
    return {"to": "agent-2"}


def a_human_with_a_dash_is_a_human(r):
    """"juan-pablo" next to "juan-pablo-1" was taken for an agent: a message by name went to an agent inbox."""
    f = r.fixture("v571-dash", count=1)
    f.claim(0, "HACK-001")
    for who in ("juan-pablo", "juan-pablo-1"):
        f.r.run([f.r.bash, ".uak/bin/uak", "msg", "all", "--kind", "info", who + " is here at src/x"], cwd=f.worktrees[0],
                env={"UAK_AGENT": who, "UAK_HUMAN": "", "UAK_NOW": "1000005", "UAK_REMOTE": "origin"})
    f.hack(0, "msg", "juan-pablo", "--kind", "request", "approve the domain purchase", now=1000010)
    line = [l for l in f.show("inbox/log.md").splitlines() if "domain purchase" in l][-1]
    expect("| human | request |" in line, line)
    return {"to": "human"}


def known_names_skip_the_retired(r):
    """The "Known:" list for a typo suggested retired identities, and messaging those is refused."""
    f = r.fixture("v571-known", count=2)
    f.claim(0, "HACK-001")
    f.hack(1, "msg", "all", "--kind", "info", "agent-2 here at src/x", now=1000002)
    f.hack(1, "retire", "agent-2", now=1000003)
    out = f.hack(0, "msg", "agnet-9", "--kind", "info", "typo at src/x", now=1000010)
    expect("never been seen" in out.stdout and "agent-2" not in out.stdout.split("Known:")[-1], out.stdout)
    return {"known": "no retired"}


def lint_names_a_missing_scaffold_dependency(r):
    """12 backend tasks said "Depends on: None" while their `uv run pytest` needed the scaffold's pyproject."""
    f = r.fixture("v571-scaffold", count=1, paths={"HACK-001": "pyproject.toml", "HACK-002": "app/api.py"})
    push_tasks(f, lambda t: t.replace("- **Verify:** .uak/bin/smoke --package-only", "- **Verify:** uv run pytest -q", 2))
    out = f.hack(0, "lint", allowed=None)
    expect("HACK-002's Verify needs pyproject.toml, which HACK-001 creates" in out.stderr, out.stdout + out.stderr)
    return {"lint": "warning"}


def accented_capitals_are_the_same_path(r):
    """Botón and BOTÓN are one file on macOS and Windows; the overlap check saw two."""
    f = r.fixture("v571-accent", count=2, paths={"HACK-001": "src/Botón.tsx", "HACK-002": "src/BOTÓN.tsx"})
    f.claim(0, "HACK-001")
    out = f.claim(1, "HACK-002", allowed=None)
    expect(out.returncode == 3 and "overlap" in (out.stdout + out.stderr).lower(), out.stdout + out.stderr)
    return {"accent": "folded"}


def map_impact_reads_a_crlf_checkout(r):
    """With core.autocrlf=true the last path of every task kept a \\r, so map impact found no importer on Windows."""
    f = r.fixture("v571-mapcrlf", count=1, paths={"HACK-001": "src/b.ts", "HACK-002": "src/a.ts"})
    wt = f.worktrees[0]
    (wt / "src").mkdir(exist_ok=True)
    (wt / "src/b.ts").write_text("export const b = 1;\n", encoding="utf-8")
    (wt / "src/a.ts").write_text('import { b } from "./b";\nexport const a = b;\n', encoding="utf-8")
    tasks = wt / ".uak/TASKS.md"
    tasks.write_bytes(tasks.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    out = f.r.run([f.r.bash, ".uak/bin/map", "impact", "--tasks", "src/b.ts"], cwd=wt, allowed=None)
    expect("HACK-002" in out.stdout, "the importer's task is found: " + out.stdout + out.stderr)
    return {"crlf": True}


def a_windows_plan_publishes(r):
    """A plan file written on Windows (CRLF) died "Invalid ID in plan", and a list-form Verify broke the gate."""
    f = r.fixture("v571-plancrlf", count=1)
    p = f.seed / ".uak/PROJECT.md"
    p.write_text(p.read_text(encoding="utf-8") + "Plan-Channel: claims\n", encoding="utf-8")
    f.r.g(f.seed, "add", ".uak/PROJECT.md"); f.r.g(f.seed, "commit", "-q", "-m", "plan channel"); f.r.g(f.seed, "push", "-q", "origin", "main")
    plan = f.base / "plan.md"
    plan.write_bytes(b"## PB-030\r\n- **Priority:** P0\r\n- **Paths:** src/pb.txt\r\n- **Depends on:** none\r\n"
                     b"- **Verify:**\r\n  - `true`\r\n")
    out = f.r.run([f.r.bash, ".uak/bin/uak", "plan", str(plan)], cwd=f.seed,
                  env={"UAK_AGENT": "", "UAK_HUMAN": "boss", "UAK_NOW": "1000005", "UAK_REMOTE": "origin"}, allowed=None)
    expect(out.returncode == 0, out.stdout + out.stderr)
    st = f.hack(0, "status", "--task", "PB-030", now=1000006)
    expect("Verify: `true`" in st.stdout and "\r" not in st.stdout, repr(st.stdout))
    return {"plan": "crlf"}


def pace_reads_codex_under_a_spaced_home(r):
    """`ls -t $recent` split "C:/Users/José Pérez" and pace never saw Codex usage."""
    home = r.scratch / "v571 José Pérez"
    sess = home / ".codex/sessions/2026/10/29"
    sess.mkdir(parents=True)
    resets = int(time.time()) + 3 * 3600          # a fixed epoch expired mid-CI and pace rightly dropped it
    (sess / "rollout-1.jsonl").write_text('{"type":"event_msg","payload":{"rate_limits":{"primary":{"used_percent":42.0,'
                                          '"window_minutes":300,"resets_at":%d}}}}\n' % resets, encoding="utf-8")
    d = r.scratch / "v571-pace"
    d.mkdir()
    r.g(d, "init", "-q")
    out = r.run([r.bash, str(r.package / ".uak/bin/pace")], cwd=d, env={"HOME": str(home), "CODEX_HOME": "", "UAK_PACE_CLAUDE": "0"}, allowed=None)
    expect("42%" in out.stdout, out.stdout + out.stderr)
    return {"pace": "spaced home"}


def identities_differ_in_more_than_case(r):
    """Ana-1 next to ana-1: on macOS and Windows one file, and git add committed one identity over the other."""
    f = r.fixture("v571-case", count=2)
    f.claim(0, "HACK-001")
    out = f.r.run([f.r.bash, ".uak/bin/uak", "msg", "all", "--kind", "info", "hello at src/x"], cwd=f.worktrees[1],
                  env={"UAK_AGENT": "Agent-1", "UAK_HUMAN": "", "UAK_NOW": "1000005", "UAK_REMOTE": "origin"}, allowed=None)
    expect(out.returncode == 3 and "only in case" in out.stderr, out.stdout + out.stderr)
    return {"case": "refused"}


TESTS = [a_migration_under_fixtures_is_still_shared, the_gate_stops_what_verify_started,
         done_to_names_someone_who_can_review, a_human_with_a_dash_is_a_human, known_names_skip_the_retired,
         lint_names_a_missing_scaffold_dependency, accented_capitals_are_the_same_path,
         map_impact_reads_a_crlf_checkout, a_windows_plan_publishes, pace_reads_codex_under_a_spaced_home,
         identities_differ_in_more_than_case]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v571-") as tmp:
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
    print("V571_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
