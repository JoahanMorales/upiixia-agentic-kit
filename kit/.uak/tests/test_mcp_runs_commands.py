#!/usr/bin/env python3
"""UAK-112: uak_cli refused `loop`, `up`, `q`... (commands that run a command you pass, which through MCP never meets
guard) only when the first argument was the command name: `["--json", "loop", ...]` got past, and `red ID -- CMD`
was not in the set at all (audit of v6.5.0, #2). Now the refusal looks past leading flags, and a test compares the
set with commands.tsv so a new command of that kind cannot be forgotten. uak-mcp is loaded as a module."""
import argparse
import importlib.machinery
import importlib.util
import re
from pathlib import Path

from test_hack import expect


def load(package):
    path = package / ".uak" / "bin" / "uak-mcp"
    loader = importlib.machinery.SourceFileLoader("uak_mcp_under_test", str(path))
    spec = importlib.util.spec_from_loader("uak_mcp_under_test", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def refused(mod, args):
    try:
        mod.cli_args({"args": args})
    except ValueError as exc:
        return str(exc)
    return None


def json_prefix_does_not_hide_the_command(package):
    mod = load(package)
    for args in (["loop", "--verify", "true"], ["--json", "loop", "--verify", "true"], ["--json", "--x", "up", "2"],
                 ["-q", "q", "true"], ["--json", "smoke"], ["--json", "init-smoke", "--command", "true"]):
        msg = refused(mod, args)
        expect(msg and "shell" in msg and "guard" in msg, "%r must be refused, naming the shell: %r" % (args, msg))
    for args in (["status"], ["--json", "status"], ["--json", "board"], ["--json"], []):
        expect(refused(mod, args) is None, "%r is an ordinary command" % (args,))
    expect(mod.cli_args({"args": ["--json", "board"]}) == ["uak", "--json", "board"], "an allowed command is passed unchanged")
    return "flags skipped"


def red_is_refused(package):
    mod = load(package)
    for args in (["red", "UAK-1", "--", "git reset --hard"], ["--json", "red", "--cmd", "true"], ["red"]):
        expect(refused(mod, args), "%r must be refused" % (args,))
    return "red"


def registry_and_set_agree(package):
    """Every registry row that takes a command (a COMMAND/CMD placeholder in its usage, or marked shell) is in the
    set; the explicit extras are real commands or scripts, not typos."""
    mod = load(package)
    rows = []
    for line in (package / ".uak" / "bin" / "lib" / "commands.tsv").read_text(encoding="utf-8").splitlines():
        c = line.rstrip("\r").split("\t")
        if line and not line.startswith("#") and len(c) == 6:
            rows.append(c)
    expect(rows, "commands.tsv has rows")
    takes = {c[0] for c in rows if c[4] == "shell" or re.search(r"\b(CMD|COMMAND)\b", c[5])}
    expect({"loop", "up", "init-smoke", "red"} <= takes, "the placeholder rule finds the known ones: %s" % sorted(takes))
    missing = takes - mod.RUNS_COMMANDS
    expect(not missing, "commands that run a passed command but are not refused by uak_cli: %s" % sorted(missing))
    names = {c[0] for c in rows}
    scripts = {"q", "smoke"}
    stray = mod.RUNS_COMMANDS - names - scripts
    expect(not stray, "the set names commands that do not exist: %s" % sorted(stray))
    return "%d commands" % len(takes)


TESTS = [json_prefix_does_not_hide_the_command, red_is_refused, registry_and_set_agree]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    package = args.package.resolve()
    for test in TESTS:
        if args.case and test.__name__ != args.case:
            continue
        try:
            print("PASS %s (%s)" % (test.__name__, test(package)))
        except Exception as exc:  # noqa: BLE001
            ok_all = False
            print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("MCP_RUNS_COMMANDS_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
