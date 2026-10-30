#!/usr/bin/env python3
"""uak v5.9.1: a Windows audit of HackADA on a teammate's laptop (Oct 2026). python3 was the Store alias and doctor said
OK; start printed "No such file or directory" and never said the kit was old when ~/.uak-kit was missing; the
project kept no tzdata, a Vite without envDir and a Node under Vite 8's engines, and nothing said so; Codex, Cursor and
Gemini hooks ran a bare `bash`, which is WSL from PowerShell; scripts were CRLF on disk. One test per fix.
Real Git, local bare remote, separate processes."""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary
from test_v571 import push_tasks


def start_asks_the_kit_remote_without_a_local_clone(r):
    """Row 9: no ~/.uak-kit (installed from another clone or the plugin) meant no warning, and a stray error line."""
    f = r.fixture("v591-start", count=1)
    kit = f.base / "kit-remote.git"
    r.g(f.base, "init", "-q", "--bare", kit)
    r.g(f.seed, "tag", "v99.0.0")
    r.g(f.seed, "push", "-q", str(kit), "v99.0.0")
    (f.seed / ".uak/PROJECT.md").write_text((f.seed / ".uak/PROJECT.md").read_text(encoding="utf-8") + "Mode: sprint\n", encoding="utf-8")
    out = r.run([r.bash, ".uak/bin/start"], cwd=f.seed, env={"UAK_KIT_URL": str(kit)}, allowed=None)
    expect("No such file" not in out.stderr, "no stray error: " + out.stderr)
    expect("update the kit: this project has uak" in out.stdout and "the kit's GitHub has 99.0.0" in out.stdout
           and "git clone --depth 1 " + str(kit) in out.stdout, out.stdout)
    return {"told": True}


def doctor_runs_python_instead_of_finding_it(r):
    """Rows 3 and 6: the Store's python3 printed "no se encontró Python…", exited 49, and doctor said OK python3."""
    f = r.fixture("v591-python", count=1)
    shim = f.base / "shim"
    shim.mkdir()
    for name in ("python3", "python", "py"):
        (shim / name).write_text("#!/bin/sh\necho 'Python was not found; run without arguments to install from the Microsoft Store' >&2\nexit 49\n", encoding="utf-8")
        os.chmod(shim / name, 0o755)
    out = r.run([r.bash, "-c", 'PATH="$(cd "$1" && pwd):$PATH"; bash .uak/bin/doctor', "_", shim.as_posix()], cwd=f.seed, allowed=None)
    expect("OK    python" not in out.stdout and "no Python that runs" in out.stdout, out.stdout)
    return {"alias": "not OK"}


def doctor_names_what_update_cannot_fix(r):
    """Rows 12 and 15: no tzdata in pyproject, Vite without envDir, Node 20.16 under Vite 8: the kit was current."""
    f = r.fixture("v591-product", count=1)
    s = f.seed
    (s / "pyproject.toml").write_text('[project]\nname = "app"\ndependencies = ["fastapi"]\n', encoding="utf-8")
    (s / "app").mkdir()
    (s / "app/clock.py").write_text('from zoneinfo import ZoneInfo\nTZ = ZoneInfo("America/Mexico_City")\n', encoding="utf-8")
    (s / "web").mkdir()
    (s / "web/vite.config.ts").write_text('export default defineConfig({ plugins: [react()] })\n', encoding="utf-8")
    (s / ".env.example").write_text("VITE_MAP_KEY=\n", encoding="utf-8")
    (s / "web/package.json").write_text(json.dumps({"name": "web", "devDependencies": {"vite": "^8.0.0"}}, indent=2) + "\n", encoding="utf-8")
    (s / "web/package-lock.json").write_text(json.dumps({"name": "web", "lockfileVersion": 3, "packages": {
        "": {"name": "web"}, "node_modules/vite": {"version": "8.0.1", "engines": {"node": "^20.19.0 || >=22.12.0"}}}}, indent=2) + "\n", encoding="utf-8")
    shim = f.base / "shim"
    shim.mkdir()
    (shim / "node").write_text("#!/bin/sh\necho v20.16.0\n", encoding="utf-8")
    os.chmod(shim / "node", 0o755)
    r.g(s, "add", "-A")
    r.g(s, "commit", "-q", "-m", "a product")
    doctor = lambda: r.run([r.bash, "-c", 'PATH="$(cd "$1" && pwd):$PATH"; bash .uak/bin/doctor', "_", shim.as_posix()], cwd=s, allowed=None).stdout
    out = doctor()
    expect("pyproject.toml: the code uses zoneinfo but tzdata is no dependency" in out, out)
    expect("web/vite.config.ts reads web/.env only" in out, out)
    expect("FAIL  Node 20.16.0 is too old for web: vite wants ^20.19.0 || >=22.12.0" in out, out)
    (s / "pyproject.toml").write_text('[project]\nname = "app"\ndependencies = ["fastapi", "tzdata"]\n', encoding="utf-8")
    (s / "web/vite.config.ts").write_text('export default defineConfig({ envDir: "..", plugins: [react()] })\n', encoding="utf-8")
    (shim / "node").write_text("#!/bin/sh\necho v22.12.0\n", encoding="utf-8")
    out = doctor()
    expect("tzdata" not in out and "envDir" not in out and "too old" not in out, out)
    return {"named": 3}


def every_hook_runs_without_a_bare_bash(r):
    """Row 19: from PowerShell or cmd, `bash` is System32's WSL launcher. Hooks go through git, whose shell is Git's."""
    f = r.fixture("v591-hooks", count=1)
    w = f.worktrees[0]
    commands = []
    for rel in (".codex/hooks.json", ".cursor/hooks.json", ".gemini/settings.json"):
        hooks = json.loads((r.package / rel).read_text(encoding="utf-8"))["hooks"]
        for groups in hooks.values():
            for g in groups:
                for h in g.get("hooks", [g]):
                    commands.append((rel, h["command"]))
    expect(len(commands) >= 20 and all(c.startswith("git -c ") for _, c in commands), str(commands))
    env = dict(r.env)
    if os.name == "nt":  # what a harness started from PowerShell sees: System32 (WSL's bash) first, Git's cmd/ only
        git_cmd = Path(r.git).parent.parent / "cmd"
        env["PATH"] = os.environ.get("SystemRoot", "C:\\Windows") + "\\System32;" + str(git_cmd if git_cmd.is_dir() else Path(r.git).parent)
    payload = json.dumps({"command": "git push --force origin main", "tool_name": "Bash", "hook_event_name": "PreToolUse",
                          "tool_input": {"command": "git push --force origin main"}, "cwd": str(w)})
    guards = [c for _, c in commands if "/guard bash" in c or "/guard shell" in c]
    expect(len(guards) >= 3, str(guards))
    for c in guards:
        out = subprocess.run(c, shell=True, cwd=w, env=env, input=payload, capture_output=True, text=True, errors="replace", timeout=120)
        expect(out.returncode == 2 and "UAK_GUARD: blocked" in out.stderr, c + " → %d %s %s" % (out.returncode, out.stdout, out.stderr))
    check = 'git -c "alias.uak-hook=!unset GIT_DIR GIT_WORK_TREE GIT_PREFIX GIT_CONFIG_PARAMETERS; exec bash -c \'uname -s; pwd; env\'" uak-hook'
    (w / "sub").mkdir()
    out = subprocess.run(check, shell=True, cwd=w / "sub", env=env, capture_output=True, text=True, errors="replace", timeout=60)
    lines = out.stdout.splitlines()
    expect(out.returncode == 0 and lines and (os.name != "nt" or lines[0].startswith(("MINGW", "MSYS"))), out.stdout + out.stderr)
    expect(not lines[1].endswith("/sub") and not any(l.startswith(("GIT_DIR=", "GIT_CONFIG_PARAMETERS=")) for l in lines),
           "from the top level, without the alias's git variables: " + out.stdout)
    return {"hooks": len(commands)}


def the_kit_scripts_stay_lf_with_autocrlf(r):
    """Row 18: Git for Windows sets core.autocrlf=true system-wide; every .uak/bin script was CRLF on disk."""
    if not (r.package.parent / "install.sh").is_file():
        return {"skipped": "an installed project has no install.sh"}
    t = r.scratch / "v591-lf"
    t.mkdir()
    r.g(t, "init", "-q", "-b", "main")
    r.run([r.bash, str(r.package.parent / "install.sh"), "--mode", "sprint", "--harness", "claude", str(t)], cwd=t)
    attrs = (t / ".gitattributes").read_text(encoding="utf-8")
    expect(".uak/** text=auto eol=lf" in attrs and "*.sh text=auto eol=lf" in attrs, attrs)
    r.g(t, "add", "-A")
    r.g(t, "commit", "-q", "-m", "kit")
    clone = r.scratch / "v591-lf-clone"
    r.g(r.scratch, "-c", "core.autocrlf=true", "clone", "-q", "-c", "core.autocrlf=true", t, clone)
    data = (clone / ".uak/bin/uak").read_bytes()
    expect(b"\r\n" not in data, "the checkout keeps LF under autocrlf=true")
    again = r.run([r.bash, str(r.package.parent / "install.sh"), "--mode", "sprint", "--harness", "claude", "--update", str(t)], cwd=t)
    expect(".gitattributes" not in again.stdout and (t / ".gitattributes").read_text(encoding="utf-8") == attrs, again.stdout)
    return {"lf": True}


TESTS = [start_asks_the_kit_remote_without_a_local_clone, doctor_runs_python_instead_of_finding_it,
         doctor_names_what_update_cannot_fix, every_hook_runs_without_a_bare_bash, the_kit_scripts_stay_lf_with_autocrlf]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    with tempfile.TemporaryDirectory(prefix="uak-v591-") as tmp:
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
    print("V591_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
