#!/usr/bin/env python3
"""uak v5.7: the installer and the setup skill after the Oct 2026 audit: an --update after --no-mcp brought the MCP
server back, an option left without its value exited 1 with no message, and the setup skill offered 2 of the 8
stacks and never said how to refresh an install. Real install.sh into fresh Git repositories."""
import argparse
import subprocess
import tempfile
import time
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def installer(r):
    inst = str(r.package.parent / "install.sh")
    def repo(name):
        d = r.scratch / ("v57-inst-" + name); d.mkdir(parents=True); r.g(d, "init", "-q", "-b", "main"); return d
    run = lambda *a: subprocess.run([r.bash, inst, *map(str, a)], capture_output=True, text=True, env=r.env, timeout=180,
                                    stdin=subprocess.DEVNULL)
    return repo, run


def an_update_keeps_no_mcp(r):
    """Installed with --no-mcp, a plain --update wrote .mcp.json, .cursor/mcp.json and the MCP blocks back."""
    repo, run = installer(r)
    d = repo("nomcp")
    expect(run("--mode", "sprint", "--no-mcp", d).returncode == 0, "installs without MCP")
    up = run("--update", "--mode", "sprint", d)
    expect(up.returncode == 0 and "kept off" in up.stdout, up.stdout[-400:] + up.stderr)
    expect(not (d / ".mcp.json").exists() and not (d / ".cursor/mcp.json").exists(), "no MCP config came back")
    expect("mcp_servers" not in (d / ".codex/config.toml").read_text(encoding="utf-8"), "codex config without MCP")
    expect('"mcpServers"' not in (d / ".gemini/settings.json").read_text(encoding="utf-8"), "gemini settings without MCP")
    back = run("--update", "--mode", "sprint", "--mcp", d)
    expect(back.returncode == 0 and (d / ".mcp.json").exists(), "--mcp adds it back: " + back.stdout[-300:])
    expect("[mcp_servers.uak]" in (d / ".codex/config.toml").read_text(encoding="utf-8"), "codex MCP block back")
    e = repo("withmcp")
    run("--mode", "sprint", e)
    again = run("--update", "--mode", "sprint", e)
    expect("kept off" not in again.stdout and (e / ".mcp.json").exists(), "an install with MCP keeps it")
    return {"mcp": "kept"}


def an_option_without_its_value_says_so(r):
    repo, run = installer(r)
    d = repo("novalue")
    for args in (("--mode",), ("--mode", "sprint", "--harness"), ("--mode", "sprint", "--stack"), ("--mode", "sprint", "--skills")):
        out = run(*args)
        expect(out.returncode == 2 and "needs a value" in out.stderr, "%s → rc=%d %r" % (args, out.returncode, out.stderr))
    expect(not (d / ".uak").exists(), "nothing installed")
    return {"usage": True}


def the_setup_skill_knows_every_stack(r):
    skill = (r.package.parent / "skills/setup/SKILL.md").read_text(encoding="utf-8")
    stacks = sorted(p.name for p in (r.package / ".uak/stacks").iterdir() if p.is_dir())
    missing = [s for s in stacks if "`%s`" % s not in skill]
    expect(not missing, "the setup skill does not offer: %s" % missing)
    expect("--update" in skill and "pull --ff-only" in skill, "a second run updates, and an old ~/.uak-kit is refreshed")
    return {"stacks": len(stacks)}


TESTS = [an_update_keeps_no_mcp, an_option_without_its_value_says_so, the_setup_skill_knows_every_stack]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ in args.case]
    results = []
    with tempfile.TemporaryDirectory(prefix="uak-v57i-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in tests:
            started = time.monotonic()
            try:
                test(runner)
                results.append((test.__name__, True, "%.2fs" % (time.monotonic() - started)))
            except Exception as exc:  # noqa: BLE001
                results.append((test.__name__, False, str(exc)[:1500]))
    for name, ok, info in results:
        print(("PASS " if ok else "FAIL ") + name + " (" + info + ")")
    passed = sum(1 for _, ok, _ in results if ok)
    print("V57_INSTALL_RESULT %s passed=%d failed=%d" % ("PASS" if passed == len(results) else "FAIL", passed, len(results) - passed))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
