"""UAK-136: an exec'd Python command closes its own ledger line (see ledger.sh: ledger_handoff). The dispatcher exports
UAK_LG_OWED (the git common dir), UAK_LG_CMD, UAK_LG_TASK, UAK_LG_AGENT and UAK_LG_T0 (microseconds, bash 5 only); `run(main)`
calls main, writes one line (epoch, command, task, exit, code, ms, agent, harness) with its return value or SystemExit code,
and gives the result back. No marker (called directly): nothing is written. Same line format as ledger_end."""
import os
import re
import time


def _harness():
    e = os.environ
    if e.get("UAK_HARNESS"):
        h = e["UAK_HARNESS"]
    elif e.get("CLAUDECODE"):
        h = "claude-code"
    elif e.get("CODEX_SANDBOX") or e.get("CODEX_THREAD_ID") or e.get("CODEX_HOME"):
        h = "codex"
    elif e.get("CURSOR_TRACE_ID") or e.get("CURSOR_AGENT") or e.get("CURSOR_VERSION"):
        h = "cursor"
    elif e.get("GEMINI_CLI"):
        h = "gemini-cli"
    else:
        h = "other"
    return h if re.match(r"^[A-Za-z0-9._-]+$", h) else "other"


def _write(owed, t0, rc):
    e = os.environ
    now = time.time()
    ms = int((now * 1000000 - t0) / 1000) if t0 else int((now - START) * 1000)
    task = e.get("UAK_LG_TASK", "")
    task = task if re.match(r"^[A-Z][A-Za-z0-9-]*-[0-9]+$", task) else "-"
    agent = e.get("UAK_LG_AGENT", "")
    agent = agent if re.match(r"^[A-Za-z0-9_.-]+$", agent) else "-"
    cmd = (e.get("UAK_CALLER") + "-" if e.get("UAK_CALLER") else "") + e.get("UAK_LG_CMD", "?")
    try:
        with open(os.path.join(owed, "uak-ledger.pending"), "a", encoding="utf-8", newline="") as f:
            f.write("\t".join([str(int(now)), cmd, task, str(rc), "-", str(max(ms, 0)), agent, _harness()]) + "\n")
    except OSError:
        pass


START = time.time()


def run(main):
    """main() -> exit code. Used as sys.exit(ledger_py.run(main))."""
    owed = os.environ.pop("UAK_LG_OWED", "")
    t0 = os.environ.get("UAK_LG_T0", "")
    t0 = int(t0) if t0.isdigit() and len(t0) >= 15 else 0
    if not owed:
        return main()
    try:
        rc = main()
    except SystemExit as exc:
        c = exc.code
        _write(owed, t0, c if isinstance(c, int) else (0 if c is None else 1))
        raise
    except BaseException:
        _write(owed, t0, 1)
        raise
    _write(owed, t0, rc if isinstance(rc, int) else 0)
    return rc
