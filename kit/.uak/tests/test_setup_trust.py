#!/usr/bin/env python3
"""Workspace trust from the setup UI (UI-008): in a new folder Claude Code ignores the project's allow rules until the
folder is trusted once interactively. The page says so before planning, names that cause when a planning run fails on
it, and the planner reads files with its Read tool so one denied command does not end the run.
Real HTTP, real Git with a local bare remote, and a fake planner in place of the coding tool."""
import argparse
import importlib.util
import json
import re
import subprocess
import tempfile
from pathlib import Path

import test_setup_planning as plans
import test_setup_wizard as wizard

UNTRUSTED = ("Ignoring 51 permissions.allow entries from .claude/settings.json: this workspace has not been trusted. "
             "Run Claude Code interactively here once and accept the trust dialog.\n")


class UntrustedPlanner(plans.FakePlanner):
    """The coding tool in an untrusted folder: it prints Claude Code's trust warning, and writes the plan or not."""

    def __init__(self, writes):
        super().__init__()
        self.writes = writes

    def __call__(self, command, cwd=None, timeout=120, **kwargs):
        name = Path(command[0]).name.lower().replace(".exe", "").replace(".cmd", "")
        if name not in ("claude", "codex") or command[1:3] in (["auth", "status"], ["login", "status"]):
            return super().__call__(command, cwd=cwd, timeout=timeout, **kwargs)
        if self.writes:
            result = super().__call__(command, cwd=cwd, timeout=timeout, **kwargs)
            return subprocess.CompletedProcess(command, 0, result.stdout, UNTRUSTED)
        self.calls.append({"argv": list(command), "cwd": cwd})
        return subprocess.CompletedProcess(command, 0, '{"type":"result","result":"Bash(cat IDEA.md) was denied"}\n',
                                           UNTRUSTED)


def lib(root, name):
    return (root / ".uak/bin/lib" / name).read_text(encoding="utf-8")


def catalog(root):
    text = lib(root, "workspace.js")
    pairs = re.findall(r'\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,?\s*\]', text)
    return {json.loads(a): json.loads(b) for a, b in pairs}


def section(html, ident):
    start = html.rindex("<", 0, html.index('id="%s"' % ident))
    tag = re.match(r"<(\w+)", html[start:]).group(1)
    depth = 0
    for m in re.finditer(r"<(/?)%s\b[^>]*>" % tag, html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start:start + m.end()]
    raise AssertionError("unclosed #%s" % ident)


def visible(fragment):
    fragment = re.sub(r"<(code|script|style)\b[\s\S]*?</\1>", " ", fragment)
    return [" ".join(t.split()) for t in re.split(r"<[^>]+>", fragment) if re.search(r"[A-Za-z]{2}", t)]


def trust_step_is_shown_before_planning(root, tmp):
    target, _ = plans.project(root, tmp)
    with plans.live(target, plans.FakePlanner()) as srv:
        assert plans.post(srv, "/api/inspect", {"target": str(target)})[0] == 200
        status, view = plans.get(srv, "/api/plan")
        assert status == 200, view
        expected = "cd '%s' && claude" % target.resolve().as_posix()
        assert view.get("trust_command") == expected, "the plan view gives the exact trust command: %r" % view.get(
            "trust_command")
    (tmp / "codex only").mkdir()
    codex, _ = plans.project(root, tmp / "codex only", harnesses=("codex",))
    with plans.live(codex, plans.FakePlanner()) as srv:
        assert plans.post(srv, "/api/inspect", {"target": str(codex)})[0] == 200
        assert not plans.get(srv, "/api/plan")[1].get("trust_command"), "a Codex-only project shows no trust notice"
    html = lib(root, "setup.html")
    planning = section(html, "planning")
    assert 'id="plan-trust"' in planning, "the planning step has a trust notice"
    assert planning.index('id="plan-trust"') < planning.index('id="plan-create"'), "it comes before Create the plan"
    trust = section(html, "plan-trust")
    assert 'id="plan-trust-command"' in trust and 'id="copy-plan-trust"' in trust, "the command has a Copy button"
    words = " ".join(visible(trust)).lower()
    assert "trust" in words and "once" in words, "it says to accept the trust question once: %r" % words
    es = catalog(root)
    missing = [t for t in visible(trust) if t not in es]
    assert not missing, "every line of the trust notice has Spanish: %r" % missing
    team = " ".join(visible(section(html, "team-implement"))).lower()
    assert "trust" in team, "the team step says Claude Code asks to trust the worktree folder the first time"
    readme = (root.parent / "README.md").read_text(encoding="utf-8") if (root.parent / "README.md").is_file() else ""
    assert re.search(r"trust", readme, re.I) and "not been trusted" in readme, \
        "README says to open Claude Code once in the folder and accept trust"


def untrusted_planning_run_names_the_cause(root, tmp):
    target, _ = plans.project(root, tmp)
    with plans.live(target, UntrustedPlanner(writes=False)) as srv:
        plans.planned(srv, target)
        status, state = plans.get(srv, "/api/status")
        assert status == 200
        assert state.get("phase") == "error", "a run that wrote no plan is not 'planned': %r" % state.get("phase")
        error = state.get("error", "")
        assert "trust" in error.lower() and "Claude Code" in error, "the cause is named: %r" % error
        assert error in catalog(root), "the trust error has Spanish: %r" % error
        assert "not been trusted" in state.get("details", ""), "Technical details keep the tool's own line"
    (tmp / "second").mkdir()
    target2, _ = plans.project(root, tmp / "second")
    with plans.live(target2, UntrustedPlanner(writes=True)) as srv:
        plans.planned(srv, target2)
        status, state = plans.get(srv, "/api/status")
        assert state.get("phase") == "planned" and not state.get("error"), \
            "the warning alone does not fail a run that wrote the plan: %r" % state


def planner_survives_a_denied_read(root, tmp):
    prompt = plans.PLANNING.PLANNER_PROMPT
    assert "Read tool" in prompt, "the planner reads files with its Read tool, not shell commands"
    assert "stop and report" not in prompt, "a denied command no longer ends the run"
    assert re.search(r"denied.{0,80}continue", prompt), "a denied command is skipped and the run continues: %r" % prompt
    assert not re.search(r"[%^&|<>\"`]", prompt), "the prompt still survives a Windows .cmd shim"
    argv = plans.PLANNING.planner_command("claude", tmp, binary="/fake/bin/claude")
    tools = argv[argv.index("--tools") + 1].split(",")
    assert "Read" in tools and "Glob" in tools, tools


TESTS = [trust_step_is_shown_before_planning, untrusted_planning_run_names_the_cause, planner_survives_a_denied_read]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    root = args.package.resolve()
    spec = importlib.util.spec_from_file_location("trust_setup", root / ".uak/bin/lib/setup.py")
    wizard.MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard.MODULE)
    spec = importlib.util.spec_from_file_location("trust_planning", root / ".uak/bin/lib/planning.py")
    plans.PLANNING = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plans.PLANNING)
    failed = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        with tempfile.TemporaryDirectory(prefix="uak-trust-") as folder:
            try:
                test(root, Path(folder))
                print("PASS " + test.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL %s: %s: %s" % (test.__name__, type(exc).__name__, exc))
    print("SETUP_TRUST_RESULT failed=%d" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
