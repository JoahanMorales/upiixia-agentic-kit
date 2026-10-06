#!/usr/bin/env python3
"""Plazos, continuidad y disponibilidad contra Git real y reloj simulado."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def config(f, **values):
    settings = {
        "Backlog-Proposed-Epoch": "1000000", "Backlog-Approved": "yes",
        "Autonomy": "yes", "Auto-Merge": "no", "Freeze-Epoch": "0",
        "Events-Per-Session": "100", "Checkpoint-Percent": "60",
        "Review-Mode": "claims", "Merge-Lease-Seconds": "1800",
        "Merge-Wait-Seconds": "180",
    }
    settings.update({key.replace("_", "-"): str(value) for key, value in values.items()})
    (f.seed / ".uak/PROJECT.md").write_text(
        "# Explicit fixture authority\n" + "".join(key + ": " + value + "\n" for key, value in settings.items()),
        encoding="utf-8")
    f.r.g(f.seed, "add", ".uak/PROJECT.md")
    f.r.g(f.seed, "commit", "-m", "Explicit coordination authority")
    f.r.g(f.seed, "push", "origin", "main")


def hack(f, index, *args, now=1000000, allowed=(0,), **extra):
    env = {"UAK_AGENT": "agent-%d" % (index + 1), "UAK_NOW": str(now),
           "UAK_REMOTE": "origin", "UAK_HUMAN": "", **extra}
    return f.r.run([f.r.bash, ".uak/bin/uak", *map(str, args)], cwd=f.worktrees[index],
                   env=env, allowed=allowed)


def cp(f, index=0, now=1000010, **extra):
    return hack(f, index, "checkpoint", "HACK-001", "--done", "Fixture",
                "--decision", "Mantener incremento", "--why", "Continuidad",
                "--fails", "-", "--commands", "true", "--next", "Ejecutar paso pendiente",
                now=now, **extra)


def receipt(f, prefix):
    return [name for name in f.files("deadlines/") if name.startswith("deadlines/" + prefix)]


def backlog_boundary(r):
    f = r.fixture("coord-backlog", count=1)
    config(f, Backlog_Approved="no")
    hack(f, 0, "tick", now=1000599)
    expect(not receipt(f, "backlog-"), "599 s: backlog not due yet")
    blocked = f.claim(0, "HACK-001", now=1000599, allowed=None)
    expect(blocked.returncode == 3, "Claim before the deadline must be refused")
    hack(f, 0, "tick", now=1000600)
    expect(len(receipt(f, "backlog-")) == 1, "600 s produce exactamente un receipt")
    expect("Effect: ALLOW_P0" in f.show(receipt(f, "backlog-")[0]), "Only P0 authorized")
    f.claim(0, "HACK-001", now=1000600)
    return {"before": 599, "at": 600, "receipts": 1, "claim_at_boundary": "PASS"}


def missing_authority(r):
    f = r.fixture("coord-no-authority", count=1)
    config(f, Backlog_Approved="no", Autonomy="no")
    hack(f, 0, "tick", now=1000600)
    denied = f.claim(0, "HACK-001", now=1000600, allowed=None)
    expect(denied.returncode == 3, "A timeout cannot grant missing autonomy")
    expect("Effect: WAIT_AUTHORIZATION" in f.show(receipt(f, "backlog-")[0]), "Receipt keeps the block")
    cfg = f.show("meta/config.md")
    expect("Autonomy: no" in cfg and "Auto-Merge: no" in cfg, "Permisos siguen ausentes")
    # A local worktree cannot change the authoritative remote config.
    (f.worktrees[0] / ".uak/PROJECT.md").write_text("Autonomy: yes\nAuto-Merge: yes\n", encoding="utf-8")
    denied = f.claim(0, "HACK-001", now=1000601, allowed=None)
    expect(denied.returncode == 3, "Alterar HACKATHON local no concede permisos")
    return {"timeout_grants_permission": False, "local_config_grants_permission": False}


def decision_boundary_and_r04(r):
    f = r.fixture("coord-decision", count=1)
    config(f)
    f.claim(0, "HACK-001")
    hack(f, 0, "log", "HACK-001", "--state", "BLOCKED", "Service unavailable")
    hack(f, 0, "decision", "HACK-001", "--option", "Labeled synthetic data",
         "--why", "Service unavailable", "--reversible", "yes", "--authorized", "yes", "--class", "routine")
    hack(f, 0, "tick", now=1000899)
    expect(not receipt(f, "decision-"), "899 s: not decided yet")
    hack(f, 0, "tick", now=1000900)
    expect(len(receipt(f, "decision-")) == 1, "900 s triggers the decision")
    expect("Effect: REVERSIBLE_AND_LOG" in f.show(receipt(f, "decision-")[0]), "Applies the authorized option")
    task = f.show("tasks/HACK-001.md")
    expect("State: CLAIMED" in task and "Next: Apply option: Labeled synthetic data" in task,
           "Tick unblocks and updates the next step without the owner")
    log = f.show(f.worklog("HACK-001"))
    expect("- Decision: Labeled synthetic data" in log and "- Why: Service unavailable" in log,
           "Live summary shows the applied decision and why")
    expect(log.count("| scheduler | deadline decision HACK-001-1000000;") == 1, "One task event per deadline")
    hack(f, 0, "log", "HACK-001", "--state", "BLOCKED", "Money needs authorization", now=1000901)
    hack(f, 0, "decision", "HACK-001", "--option", "Comprar servicio",
         "--why", "Bloqueo externo", "--reversible", "yes", "--authorized", "yes", "--class", "money", now=1000901)
    hack(f, 0, "tick", now=1001801)
    receipts = receipt(f, "decision-")
    money = [name for name in receipts if "-1000901-" in name]
    expect(len(money) == 1 and "Effect: BLOCKED_OTHER_TASK" in f.show(money[0]), "Dinero no se autoriza por timeout/flag")
    expect("Auto-Merge: no" in f.show("meta/config.md"), "Decisions never change merge authorization")
    expect("State: BLOCKED" in f.show("tasks/HACK-001.md"), "A sensitive decision keeps the task blocked")
    return {"routine_boundary": [899, 900], "money_stays_blocked": True, "routine_unblocks_and_updates_next": True}


def lease_boundary_preserves_summary(r):
    f = r.fixture("coord-lease", count=1)
    config(f)
    f.claim(0, "HACK-001")
    claim_before = f.show("claims/HACK-001.md")
    wl = f.worklog("HACK-001"); summary_before = f.show(wl)
    hack(f, 0, "tick", now=1001799)
    expect(not receipt(f, "lease-"), "1799 s: lease not expired yet")
    hack(f, 0, "tick", now=1001800)
    expect(len(receipt(f, "lease-")) == 1, "1800 s records expiry once")
    expect("Effect: REQUIRES_RECOVERY" in f.show(receipt(f, "lease-")[0]), "Explicit recovery guard")
    expect(f.show("claims/HACK-001.md") == claim_before, "Tick keeps claim bytes and token")
    expect(f.show(wl) == summary_before, "Tick keeps the live summary/history")
    view = hack(f, 0, "next", now=1001800).stdout
    expect("LEASE EXPIRED" in view and len(view.splitlines()) <= 15, "Next shows recovery within budget")
    return {"lease_boundary": [1799, 1800], "claim_and_worklog_preserved": True, "next_lines": len(view.splitlines())}


def concurrent_tick(r):
    f = r.fixture("coord-tick-race")
    config(f, Backlog_Approved="no", Freeze_Epoch="1000600")
    hack(f, 0, "tick", now=1000000)
    barrier = threading.Barrier(4)
    def run(index):
        barrier.wait(timeout=20)
        out = hack(f, index, "tick", now=1000600, allowed=None)
        return {"agent": index + 1, "code": out.returncode, "stdout": out.stdout.strip(), "stderr": out.stderr.strip()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        processes = list(pool.map(run, range(4)))
    expect(all(item["code"] == 0 for item in processes), "Los cuatro tick concurrentes deben terminar: " + json.dumps(processes))
    expect(len(receipt(f, "backlog-")) == 1 and len(receipt(f, "freeze-")) == 1, "One action per deadline")
    decisions = f.show("DECISIONS.md")
    expect(decisions.count("deadline backlog/") == 1 and decisions.count("deadline freeze/") == 1, "Sin duplicar eventos publicados")
    before = r.g(f.remote, "rev-parse", "claims").stdout.strip()
    hack(f, 0, "tick", now=1000600)
    after = r.g(f.remote, "rev-parse", "claims").stdout.strip()
    expect(before == after, "A repeated idle tick creates no commit")
    return {"processes": processes, "backlog_actions": 1, "freeze_actions": 1, "repeat_no_commit": True}


def budget_checkpoint(r):
    f = r.fixture("coord-budget", count=2, shared_repo=True)
    config(f, Events_Per_Session="5", Checkpoint_Percent="60")
    f.claim(0, "HACK-001")
    hack(f, 0, "log", "HACK-001", "Evento 2", now=1000001)
    hack(f, 0, "log", "HACK-001", "Evento 3", now=1000002)
    status = hack(f, 0, "status", now=1000003).stdout
    expect("3/3" in status and "CHECKPOINT NOW" in status, "Past 60% status demands a checkpoint")
    args = ("claim", "HACK-002", "--branch", f.branches[1], "--worktree", f.worktrees[1].as_posix())
    blocked = hack(f, 0, *args, now=1000003, allowed=None)
    expect(blocked.returncode == 3 and "CHECKPOINT NOW" in blocked.stderr, "New task blocked without checkpoint")
    cp(f, now=1000004)
    hack(f, 0, *args, now=1000005)
    expect("Owner: agent-1" in f.show("claims/HACK-002.md"), "Checkpoint permite retomar claims")
    expect("Events-Since-Checkpoint: 1" in f.show("meta/agents/agent-1.md"), "Counter resets only on checkpoint")
    hack(f, 0, "release", "HACK-001", now=1000006)
    hack(f, 0, "release", "HACK-002", now=1000007)
    expect(not f.files("claims/"), "The last release leaves the owner without claims")
    expect("Events-Since-Checkpoint: 3" in f.show("meta/agents/agent-1.md"), "Último release alcanza umbral")
    cp(f, now=1000008)
    expect(not f.files("claims/"), "Checkpoint terminal no recrea reservas")
    f.claim(0, "HACK-001", now=1000009)

    role = r.fixture("coord-role-checkpoint", count=2)
    config(role, Events_Per_Session="5", Checkpoint_Percent="60")
    role.claim(0, "HACK-001")
    role.hack(0, "register-reviewer", "agent-2", human=True, now=1000010)
    for stamp in (1000011, 1000012, 1000013):
        hack(role, 1, "review", "HACK-001", "--sha", role.main_head, "--verdict", "approve", now=stamp)
    denied = role.claim(1, "HACK-002", now=1000014, allowed=None)
    expect(denied.returncode == 3 and "CHECKPOINT NOW" in denied.stderr, "A role-only reviewer also hits the budget")
    task_before = role.show("tasks/HACK-001.md")
    hack(role, 1, "checkpoint", "--session", "--done", "Three reviews saved", "--decision", "Take an own task",
         "--why", "Preserve reviewer context", "--fails", "-", "--commands", "true", "--next", "Claim HACK-002", now=1000015)
    expect(role.show("tasks/HACK-001.md") == task_before, "A session checkpoint does not change another task")
    expect(role.files("claims/") == ["claims/HACK-001.md"], "A session checkpoint creates no claim")
    expect("- Next: Claim HACK-002" in role.show("meta/profiles/agent-agent-2.md"), "Own profile keeps the next step")
    role.claim(1, "HACK-002", now=1000016)
    return {"budget": 5, "alert_percent": 60, "threshold": 3, "blocked_code": blocked.returncode,
            "resumed": True, "terminal_checkpoint_resumes": True, "role_only_session_checkpoint_resumes": True}


def session_handoff(r):
    f = r.fixture("coord-sessions", count=1)
    config(f)
    hack(f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(), UAK_SESSION="one")
    cp(f, now=1000010, UAK_SESSION="two")
    view = hack(f, 0, "handoff", "HACK-001", now=1000011, UAK_SESSION="two").stdout
    expect("Observed sessions: 2" in view and "Ejecutar paso pendiente" in view, "Handoff evita reexplorar y cuenta sesiones observadas")
    expect("Sessions: 2" in f.show("tasks/HACK-001.md"), "Repeating a session does not double count")
    expect("Started: 1000010" in f.show("meta/sessions/agent-agent-1/session-two.md"), "Session start persisted")
    hack(f, 0, "release", "HACK-001", now=1000012, UAK_SESSION="two")
    hack(f, 0, "claim", "HACK-001", "--branch", f.branches[0], "--worktree", f.worktrees[0].as_posix(),
         now=1000013, UAK_SESSION="three")
    expect("Sessions: 3" in f.show("tasks/HACK-001.md"), "Reclaim keeps historical task counters")
    return {"observed_sessions": 3, "handoff_preserves_pending": True, "reclaim_preserves_counters": True}


def next_selects_eligible(r):
    f = r.fixture("coord-next", paths={"HACK-001": "src/shared", "HACK-002": "src/shared/two.txt",
                   "HACK-003": "src/three.txt", "HACK-004": "src/four.txt"},
                  dependencies={"HACK-003": "HACK-001"})
    config(f)
    f.claim(0, "HACK-001")
    view = hack(f, 1, "next").stdout
    expect("HACK-004 | AVAILABLE | P0" in view, "Next evita reservada, traslape y dependencia pendiente")
    expect(len(view.splitlines()) <= 15, "Next fits in 15 lines")
    live = hack(f, 0, "next").stdout
    expect("HACK-001 | CLAIMED | agent-1" in live and "Live summary:" in live, "Next resumes the active task with its summary")
    expect(len(live.splitlines()) <= 15, "Active next fits in 15 lines")
    return {"candidate": "HACK-004", "candidate_lines": len(view.splitlines()), "active_lines": len(live.splitlines())}


def freeze_gate(r):
    f = r.fixture("coord-freeze", count=1)
    config(f, Freeze_Epoch="1000000")
    denied = f.claim(0, "HACK-001", allowed=None)
    expect(denied.returncode == 3 and "FREEZE" in denied.stderr, "Freeze refuses a feature without marker")
    backlog = f.seed / ".uak/TASKS.md"
    text = backlog.read_text(encoding="utf-8").replace("## HACK-001 — Fixture verificable", "## HACK-001 — Fixture verificable\n\n- **Freeze-Allowed:** yes")
    backlog.write_text(text, encoding="utf-8")
    r.g(f.seed, "add", ".uak/TASKS.md")
    r.g(f.seed, "commit", "-m", "Fix permitido durante freeze")
    r.g(f.seed, "push", "origin", "main")
    f.claim(0, "HACK-001")
    expect("State: CLAIMED" in f.show("claims/HACK-001.md"), "An authorized demo fix can be claimed")
    return {"unmarked_feature_rejected": True, "marked_fix_accepted": True}


def next_reads_published_backlog(r):
    f = r.fixture("coord-published-backlog", count=1)
    config(f)
    backlog = f.seed / ".uak/TASKS.md"
    text = backlog.read_text(encoding="utf-8").replace("- **Priority:** P0", "- **Priority:** P2")
    split = text.index("## HACK-004")
    text = text[:split] + text[split:].replace("- **Priority:** P2", "- **Priority:** P0", 1)
    backlog.write_text(text, encoding="utf-8")
    r.g(f.seed, "add", ".uak/TASKS.md"); r.g(f.seed, "commit", "-m", "Current planner priorities")
    r.g(f.seed, "push", "origin", "main")
    first = hack(f, 0, "next").stdout
    expect("HACK-004 | AVAILABLE | P0" in first, "Next usa prioridad publicada aunque worktree tenga plan anterior")
    text = text.replace("- **Priority:** P0", "- **Priority:** P2")
    text += ("\n## HACK-005 — New published task\n\nPriority: P0\nPaths: src/five.txt\n"
             "Depends on: none\nVerify: true\nNext step: Implement new planner task\n")
    backlog.write_text(text, encoding="utf-8")
    r.g(f.seed, "add", ".uak/TASKS.md"); r.g(f.seed, "commit", "-m", "Nueva candidata publicada")
    r.g(f.seed, "push", "origin", "main")
    expect("HACK-005" not in (f.worktrees[0] / ".uak/TASKS.md").read_text(encoding="utf-8"), "Worktree keeps the previous snapshot")
    second = hack(f, 0, "next").stdout
    expect("HACK-005 | AVAILABLE | P0" in second and "new planner task" in second,
           "Next finds the new candidate without pull or re-exploration")
    f.claim(0, "HACK-005")
    expect("Paths: src/five.txt" in f.show("claims/HACK-005.md"), "Claim usa criterios nuevos publicados")
    return {"priority_from_remote": "HACK-004", "new_task_from_remote": "HACK-005", "claim_without_local_backlog_update": True}


def degraded_and_reconcile(r):
    f = r.fixture("coord-degraded", count=1)
    config(f)
    hack(f, 0, "status")
    before = r.g(f.remote, "rev-parse", "claims").stdout.strip()
    unavailable = f.base / "remote-offline.git"
    f.remote.rename(unavailable)
    try:
        view = hack(f, 0, "status").stdout
        expect("NO REMOTE: local tests, rehearsal and local review only" in view, "Explicit degraded status")
        denied = f.claim(0, "HACK-001", allowed=None)
        expect(denied.returncode != 0, "No se permiten claims offline")
    finally:
        unavailable.rename(f.remote)
    recovered = hack(f, 0, "status", now=1000001).stdout
    expect("SIN REMOTO" not in recovered, "Status se reconcilia al volver remoto")
    expect(not f.files("claims/"), "No orphan claims from an offline attempt")
    expect(r.g(f.remote, "rev-parse", "claims").stdout.strip() == before, "Reconciling without deadlines invents no commits")
    return {"status_degraded_code": 0, "offline_claim_code": denied.returncode, "orphan_claims": 0, "recovered": True}


def clock_boundaries(r):
    f = r.fixture("coord-clock", count=1)
    config(f)
    at = hack(f, 0, "status", UAK_REMOTE_NOW="999940").stdout
    over = hack(f, 0, "status", UAK_REMOTE_NOW="999939").stdout
    expect("CLOCK_SKEW" not in at and "60 s" in at, "Exactly 60 s does not exceed the limit")
    expect("CLOCK_SKEW" in over and "61 s" in over, "61 s warns about drift")
    simulated = hack(f, 0, "status").stdout
    expect("simulated" in simulated and "not checked" in simulated, "Does not compare a fixture epoch with real time")
    return {"accepted_seconds": 60, "warned_seconds": 61, "real_github_clock_verified": False}


TESTS = [backlog_boundary, missing_authority, decision_boundary_and_r04,
         lease_boundary_preserves_summary, concurrent_tick, budget_checkpoint,
         session_handoff, next_selects_eligible, freeze_gate, degraded_and_reconcile, clock_boundaries]
TESTS.insert(9, next_reads_published_backlog)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", default=os.environ.get("UAK_COORD_REPORT"))
    parser.add_argument("--work-dir", default=os.environ.get("UAK_COORD_WORK_DIR"))
    parser.add_argument("--bash"); parser.add_argument("--git")
    parser.add_argument("--jobs", type=int, default=3)
    args = parser.parse_args()
    package = args.package.resolve()
    temporary = None
    if args.work_dir:
        scratch = Path(args.work_dir).resolve()
        expect(not scratch.exists(), "--work-dir must be a new directory")
        scratch.mkdir(parents=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="hack-coordination-")
        scratch = Path(temporary.name)
    runner = Runner(package, scratch, resolve_binary("bash", args.bash), resolve_binary("git", args.git))
    revision_files = sorted((package / ".uak" / "bin").rglob("*")) + [Path(__file__).resolve(), package / ".uak/tests/test_hack.py"]
    hashes = {path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in revision_files if path.is_file()}
    report = {"suite": "coordination-v2.1", "system": os.name, "tests": [], "work_dir": str(scratch),
              "package_sha256": hashes, "jobs": max(1, args.jobs)}
    try:
        def run_test(test):
            started = time.monotonic()
            item = {"name": test.__name__}
            try:
                item["evidence"] = test(runner); item["status"] = "PASS"
            except Exception as error:
                item["status"] = "FAIL"; item["error"] = str(error)
            item["seconds"] = round(time.monotonic() - started, 3)
            print("%s %s (%ss)" % (item["status"], test.__name__, item["seconds"]), flush=True)
            if item["status"] == "FAIL": print(item["error"], flush=True)
            return item
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            report["tests"] = list(pool.map(run_test, TESTS))
        report["passed"] = sum(item["status"] == "PASS" for item in report["tests"])
        report["failed"] = len(report["tests"]) - report["passed"]
        report["status"] = "FAIL" if report["failed"] else "PASS"
        if args.report:
            path = Path(args.report).resolve(); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("COORDINATION_RESULT %s passed=%d failed=%d" % (report["status"], report["passed"], report["failed"]))
        return 1 if report["failed"] else 0
    finally:
        if temporary: temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
