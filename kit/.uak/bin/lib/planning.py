#!/usr/bin/env python3
"""Planning from the setup UI (UI-004); Python 3.8 standard library.

The person writes the idea, the project's own coding tool drafts the plan in the background, and the person approves
and publishes it in the browser. The guarantee is not the planner's prompt or its permission flags: it is this
module checking, after the run, that only the plan files changed, and committing exactly what the person reviewed.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

SUPPORTED = ("claude", "codex")
UNSUPPORTED = {
    "gemini": "Gemini CLI cannot run the plan's checks without a person to approve them. Plan with it interactively.",
    "cursor": "Cursor's command line needs a permission-bypass flag to write files. Plan with it interactively.",
}
HARNESS_DIR = {"claude": ".claude", "codex": ".codex"}
AUTH = {"claude": ("auth", "status"), "codex": ("login", "status")}
PLAN_FILES = ("IDEA.md", ".uak/TASKS.md", ".uak/OWNERS.md", ".uak/PROJECT.md")
CHANGEABLE = (".uak/TASKS.md", ".uak/OWNERS.md")
NOTE_FILE = ".uak/plan-request.md"
PLAN_TIMEOUT = 1800
GIT = ("git", "-c", "core.fsmonitor=false")

# One line, no % ^ & | < > " or backticks: it survives a Windows .cmd shim, and it is never passed through a shell.
PLANNER_PROMPT = (
    "HEADLESS RUN started by the kit setup UI. Nobody can answer questions or approve prompts: never ask, decide "
    "and note your assumptions in .uak/TASKS.md. Read IDEA.md, and .uak/plan-request.md if it exists: it holds the "
    "changes the human asked for. Do only steps 1 to 3 of the plan: write .uak/TASKS.md and .uak/OWNERS.md, then run "
    "bash .uak/bin/uak graph and bash .uak/bin/uak lint and fix the backlog until lint prints LINT_OK. Do NOT do "
    "steps 4 and 5: never set Backlog-Approved, never run git add, git commit or git push, never run uak plan, uak "
    "deploy or any wt command, and edit no file other than .uak/TASKS.md and .uak/OWNERS.md. Read and list files "
    "with your Read tool (and Glob, Grep), never with shell commands. If a command is denied, do not retry it: "
    "continue without it, and stop only if you cannot write .uak/TASKS.md. Finish with the one-screen table of step 4."
)
CLAUDE_ALLOW = ("bash .uak/bin/uak graph *", "bash .uak/bin/uak lint *", "bash .uak/bin/uak clock *",
                "bash .uak/bin/uak graph", "bash .uak/bin/uak lint")
CLAUDE_DENY = ("git add *", "git commit *", "git push *", "bash .uak/bin/uak plan *", "bash .uak/bin/uak done *",
               "bash .uak/bin/uak merge *", "bash .uak/bin/uak deploy *", "bash .uak/bin/wt *")


# Claude Code in a folder nobody has trusted interactively ignores the project's allow rules and prints this line
# (test rounds, Nov 2026: the headless planner's first read was denied and the run wrote no plan).
UNTRUSTED = "has not been trusted"
UNTRUSTED_ERROR = ("Claude Code has not trusted this folder yet. Open Claude Code once in the project folder (the command "
                   "above Create the plan), accept the trust question, close it, then try again.")


def trust_command(root):
    """The one command that opens Claude Code in the project folder so the person can accept its trust question."""
    return "cd '%s' && claude" % Path(root).resolve().as_posix().replace("'", "'\\''")


MISSING_PLAN_ERROR = ("The planner finished without writing a plan (.uak/TASKS.md). Check Technical details, then try "
                      "again.")
PROGRESS_MAX = 200


def progress_line(line):
    """One readable line for the page from one line of the coding tool's output (UI-010): the text or the tool use of a
    stream-json event, or a plain line as it is; "" when there is nothing to read. Secrets never reach the page."""
    line = (line or "").strip()
    if not line:
        return ""
    shown = line
    if line.startswith("{"):
        shown = ""
        try:
            event = json.loads(line)
        except ValueError:
            event = None
        if isinstance(event, dict):
            message = event.get("message") if isinstance(event.get("message"), dict) else {}
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str) and block["text"].strip():
                    shown = block["text"].strip()
                elif block.get("type") == "tool_use":
                    data = block.get("input") if isinstance(block.get("input"), dict) else {}
                    target = next((str(data[k]) for k in ("file_path", "path", "pattern", "command") if data.get(k)), "")
                    shown = ("%s %s" % (block.get("name", "tool"), target)).strip()
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            if not shown and isinstance(item.get("text"), str):  # Codex --json
                shown = item["text"].strip()
    shown = re.sub(r"\s+", " ", shown)
    shown = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", shown)
    shown = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})", "[redacted]", shown)
    shown = re.sub(r"(?i)((?:token|password|secret|api[_-]?key)\s*[=:]\s*)\S+", r"\1[redacted]", shown)
    return shown[:PROGRESS_MAX]


class Conflict(ValueError):
    """The request is valid but would overwrite something the person has not confirmed."""


def find_binary(name):
    return shutil.which(name)


def planner_command(harness, root, binary=None):
    """The fixed argument list for one planning run: the only variable parts are the binary and the project root."""
    if harness not in SUPPORTED:
        raise ValueError("Only Claude Code and Codex can create the plan from setup.")
    binary = binary or find_binary(harness)
    if not binary:
        raise ValueError("%s was not found on this computer." % harness)
    if harness == "codex":
        return [binary, "exec", "--cd", str(root), "--sandbox", "workspace-write", "--json", "$uak-plan " + PLANNER_PROMPT]
    # Without Git Bash on Windows, Claude Code runs commands through its PowerShell tool: the same rules apply there.
    tools = ("Bash", "PowerShell") if os.name == "nt" else ("Bash",)
    allow = ["%s(%s)" % (tool, rule) for tool in tools for rule in CLAUDE_ALLOW]
    deny = ["%s(%s)" % (tool, rule) for tool in tools for rule in CLAUDE_DENY] + ["mcp__uak"]
    # The prompt follows -p directly: --allowedTools and --disallowedTools take several values.
    return ([binary, "-p", "/uak-plan " + PLANNER_PROMPT, "--permission-mode", "acceptEdits",
             "--permission-prompts", "none", "--tools", "Read,Write,Edit,Glob,Grep," + ",".join(tools),
             "--strict-mcp-config", "--allowedTools"] + allow + ["--disallowedTools"] + deny +
            ["--output-format", "stream-json", "--verbose"])


def available_planners(root, run):
    """Each harness, whether this project and this computer can plan with it, and why not."""
    offers = []
    for harness in SUPPORTED:
        reason = ""
        binary = find_binary(harness)
        if not (Path(root) / HARNESS_DIR[harness]).is_dir():
            reason = "Not installed in this project."
        elif not binary:
            reason = "Not found on this computer."
        else:
            try:
                if run([binary] + list(AUTH[harness]), cwd=str(root), timeout=20).returncode:
                    reason = "Sign in to it in a terminal first."
            except (OSError, ValueError) as exc:
                reason = "Could not run it: %s" % exc
        offers.append({"harness": harness, "available": not reason, "reason": reason})
    for harness, reason in UNSUPPORTED.items():
        offers.append({"harness": harness, "available": False, "reason": reason})
    return offers


def one_line(value, limit, label):
    if not isinstance(value, str):
        raise ValueError("%s must be text." % label)
    value = " ".join("".join(ch if ch.isprintable() else " " for ch in value).split())
    if not value or len(value) > limit:
        raise ValueError("%s needs between 1 and %d characters." % (label, limit))
    return value


def regular_file(root, name):
    """A plan path inside the project that is a regular file or absent: never a symbolic link out of the repo."""
    root = Path(root).resolve()
    path = root / name
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("%s must be a regular file in the project, not a link or a folder." % name)
    parent = path.parent.resolve()
    if parent != root and root not in parent.parents:
        raise ValueError("%s must live inside the project." % name)
    return path


def write_atomic(path, data):
    fd, name = tempfile.mkstemp(prefix=".uak-setup-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(name, path.stat().st_mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_idea(root, data, mode):
    """IDEA.md as plain text from the "What are you building?" form. An existing file needs overwrite: true."""
    goal = "rubric" if mode == "sprint" else "goal"
    needed = {"idea", "audience", goal, "event_length", "team_size"}
    if not isinstance(data, dict) or set(data) - needed - {"overwrite"} or not needed <= set(data):
        raise ValueError("Fill in the idea, who it is for, the %s, the event length and the team size."
                         % ("judging rubric" if goal == "rubric" else "spec goal"))
    if not isinstance(data.get("overwrite", False), bool):
        raise ValueError("Invalid overwrite confirmation.")
    team = data["team_size"]
    if isinstance(team, bool) or not isinstance(team, int) or not 1 <= team <= 50:
        raise ValueError("The team size is a number from 1 to 50.")
    idea = one_line(data["idea"], 300, "The idea")
    audience = one_line(data["audience"], 300, "Who it is for")
    target = one_line(data[goal], 1000, "The judging rubric" if goal == "rubric" else "The spec goal")
    length = one_line(data["event_length"], 60, "The event length")
    path = regular_file(root, "IDEA.md")
    if path.exists() and not data.get("overwrite"):
        raise Conflict("IDEA.md already exists. Confirm that setup may replace it.")
    text = "\n".join([
        "# IDEA · " + idea, "",
        "> Written by the kit's setup page as plain text. The planner reads it; edit it freely.", "",
        "## 1. One line", idea, "",
        "## 2. Users", "For: " + audience, "",
        ("## 8. Rubric → evidence" if goal == "rubric" else "## Spec goal"), target, "",
        "## Event", "- Length: " + length, "- Team size: %d %s" % (team, "person" if team == 1 else "people"), ""])
    write_atomic(path, text.encode("utf-8"))
    return text


def git(run, root, *args, timeout=60):
    return run(list(GIT) + ["-C", str(root)] + list(args), cwd=str(root), timeout=timeout)


def git_out(run, root, *args, timeout=60):
    result = git(run, root, *args, timeout=timeout)
    if result.returncode:
        raise ValueError("git %s failed: %s" % (args[0], (result.stderr or result.stdout).strip()[-400:]))
    return result.stdout


def file_hash(path):
    try:
        if path.is_symlink():
            return "link:" + os.readlink(str(path))
        if path.is_dir():
            return "dir"
        if not path.exists():
            return "absent"
        stat = path.stat()
        if stat.st_size > 4 * 1024 * 1024:
            return "big:%d:%d" % (stat.st_size, stat.st_mtime_ns)
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        return "error:%s" % exc


def folder_hash(path):
    total = hashlib.sha256()
    if path.is_dir():
        for item in sorted(path.rglob("*")):
            total.update(str(item.relative_to(path)).encode("utf-8", "replace") + b"\0" + file_hash(item).encode() + b"\0")
    return total.hexdigest()


def absolute(root, text):
    path = Path(text.strip())
    return path if path.is_absolute() else (Path(root) / path).resolve()


def snapshot(run, root):
    """What a planning run could change: the commit, the index with its flags, Git's config and hooks, every tracked
    file by content, and every untracked or ignored file. Tracked files are hashed directly, never through `git
    status`, which an --assume-unchanged or --skip-worktree flag silences (review of dce95aa)."""
    root = Path(root)
    git_dir = absolute(root, git_out(run, root, "rev-parse", "--absolute-git-dir"))
    common = absolute(root, git_out(run, root, "rev-parse", "--git-common-dir"))
    hooks = absolute(root, git_out(run, root, "rev-parse", "--git-path", "hooks"))
    head = git(run, root, "rev-parse", "--verify", "-q", "HEAD").stdout.strip()
    # -v tags each entry (h = assume-unchanged, S = skip-worktree): setting a flag changes this hash.
    index = hashlib.sha256(git_out(run, root, "ls-files", "--stage", "-v", "-z").encode("utf-8", "replace")).hexdigest()
    status = git_out(run, root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored")
    files, skip = {}, False
    for entry in status.split("\0"):
        if skip:
            skip = False
            continue
        if len(entry) < 4:
            continue
        if entry[0] in "RC":
            skip = True  # the next entry is the rename's source
        files[entry[3:].rstrip("/")] = file_hash(root / entry[3:])
    for name in git_out(run, root, "ls-files", "-z").split("\0"):
        if name:
            files.setdefault(name, file_hash(root / name))
    for name in PLAN_FILES:
        files.setdefault(name, file_hash(root / name))
    config = "".join(file_hash(p) for p in (common / "config", git_dir / "config", git_dir / "config.worktree"))
    # The effective hooks folder and Git's default one: a hook dropped in .git/hooks wakes up once core.hooksPath goes.
    hooks = folder_hash(hooks) + folder_hash(common / "hooks")
    return {"head": head, "index": index, "files": files, "config": config, "hooks": hooks}


def violations(before, after):
    """What the planner did beyond writing .uak/TASKS.md and .uak/OWNERS.md, in words for the person."""
    found = []
    if before["head"] != after["head"]:
        found.append("The planner made a commit or moved the current branch (HEAD changed).")
    if before["index"] != after["index"]:
        found.append("The planner staged files (git add).")
    if before["config"] != after["config"]:
        found.append("The planner changed Git's configuration (.git/config).")
    if before["hooks"] != after["hooks"]:
        found.append("The planner changed the Git hooks folder.")
    for name in sorted(set(before["files"]) | set(after["files"])):
        if name in CHANGEABLE or name == NOTE_FILE:
            continue
        if before["files"].get(name, "absent") != after["files"].get(name, "absent"):
            found.append("The planner changed %s, which only you may change." % name)
    return found


def lint(run, root, uak, bash):
    result = run([bash, str(uak), "lint"], cwd=str(root), timeout=180)
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    lines = [line[len("LINT: "):] for line in output.splitlines() if line.startswith("LINT: ")]
    ok = result.returncode == 0 and "LINT_OK" in output.splitlines()
    if not ok and not lines:
        # A failure that is not a LINT: line (Git, network, no main yet) still reaches the page with its reason.
        # Why (UI-005): the page said "the kit's checks found problems" with an empty list.
        raw = [line.strip() for line in output.splitlines() if re.search(r"ERROR|fatal|failed|refused", line)]
        if any("refs/heads/main" in line or "couldn't find remote ref" in line for line in raw):
            lines.append("The kit is not on main yet: publish the kit to main first, then check the plan again.")
        lines.extend(raw[:3] or ["uak lint stopped without a reason (exit %d); see Technical details." % result.returncode])
    return {"ok": ok, "lines": lines[:20]}


# What "Publish the kit to main" may commit: only files the installer placed (its manifest), never by directory
# prefix, and never the plan before its approval. Why (UI-005 review): a prefix published .github/private-note.txt.
MANIFEST = ".uak/installed-files.txt"
NOT_PUBLISHED = ("IDEA.md", ".uak/TASKS.md", ".uak/OWNERS.md", NOTE_FILE, ".uak/INSTALLING")


def manifest_paths(root):
    path = regular_file(root, MANIFEST)
    if not path.is_file():
        raise ValueError("This kit has no list of the files it installed (it predates that list). "
                         "Choose Repair or update kit, then publish.")
    paths = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/") or line.startswith(".git/") or ".." in Path(line).parts or "\\" in line:
            raise ValueError("The kit's file list (.uak/installed-files.txt) has an invalid entry. Repair or update the kit.")
        paths.add(line)
    return paths


def publish_files(run, root):
    """Kit files (from the installer's manifest) that differ from HEAD: new, changed or deleted. Nothing else."""
    root = Path(root)
    owned = manifest_paths(root) - set(NOT_PUBLISHED)
    status = git_out(run, root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    files, skip = [], False
    for entry in status.split("\0"):
        if skip:
            skip = False
            continue
        if len(entry) < 4:
            continue
        if entry[0] in "RC":
            skip = True
        name = entry[3:]
        if name in owned and name not in files:
            files.append(name)
    return sorted(files)


def set_freeze(root, epoch):
    """Freeze-Epoch in .uak/PROJECT.md, as `uak clock --write` sets it, but never through a link or a predictable
    temporary file (UI-005 review): a regular file inside the project, replaced atomically from a random temp name."""
    path = regular_file(root, ".uak/PROJECT.md")
    if not path.is_file():
        raise ValueError(".uak/PROJECT.md is missing. Repair or update the kit.")
    text = path.read_bytes().decode("utf-8")
    pattern = re.compile(r"(?m)^([-* ]*)Freeze-Epoch:[^\r\n]*")
    if not pattern.search(text):
        raise ValueError(".uak/PROJECT.md has no Freeze-Epoch line. Repair or update the kit.")
    write_atomic(path, pattern.sub(lambda m: m.group(1) + "Freeze-Epoch: %d" % int(epoch), text).encode("utf-8"))


def publish_digest(root, files):
    """What the person saw in the preview: each listed path and its content (or its absence)."""
    total = hashlib.sha256()
    for name in files:
        total.update(name.encode("utf-8", "replace") + b"\0" + file_hash(Path(root) / name).encode() + b"\0")
    return total.hexdigest()


def kit_on_main(run, root, remote="origin", base="main"):
    """True when the remote's base branch already has the kit (agents read .uak/ from there)."""
    fetched = git(run, root, "fetch", "-q", remote, base, timeout=120)
    if fetched.returncode:
        return False
    return git(run, root, "cat-file", "-e", "FETCH_HEAD:.uak/PROJECT.md").returncode == 0


ID = re.compile(r"[A-Z][A-Z0-9]*-[0-9]+")


def cards(text):
    """The plan as cards for the person: ID, title, priority, wave, dependencies and tests, all as text."""
    tasks, order, current = {}, [], None
    for line in (text or "").splitlines():
        heading = re.match(r"^## (%s)\s*[·—-]*\s*(.*)$" % ID.pattern, line)
        if heading:
            current = heading.group(1)
            order.append(current)
            tasks[current] = {"id": current, "title": heading.group(2).strip(), "priority": "", "type": "",
                              "estimate": "", "depends": [], "tests": [], "test_first": "", "wave": 0}
            continue
        if line.startswith("# "):
            current = None
        if not current:
            continue
        key, _, value = re.sub(r"\*\*", "", line).strip().lstrip("-").strip().partition(":")
        value, card = value.strip(), tasks[current]
        if key in ("Priority", "Type", "Estimate"):
            card[key.lower()] = value
        elif key == "Depends on":
            card["depends"] = ID.findall(re.sub(r"\([^)]*\)", "", value))
        elif key == "Tests":
            card["tests"] = [t.strip().strip("`") for t in value.split(",") if t.strip()]
        elif key == "Test-First":
            card["test_first"] = value

    def wave(tid, seen):
        card = tasks[tid]
        if card["wave"] or tid in seen:
            return card["wave"]  # 0 inside a cycle: lint reports it
        levels = [wave(dep, seen | {tid}) for dep in card["depends"] if dep in tasks]
        if 0 in levels:
            return 0
        card["wave"] = 1 + max(levels or [0])
        return card["wave"]

    for tid in order:
        wave(tid, frozenset())
    return [tasks[tid] for tid in order]


def digest(root):
    """What the person reviews and approves: the four plan files, byte for byte."""
    total = hashlib.sha256()
    for name in PLAN_FILES:
        path = regular_file(root, name)
        total.update(name.encode() + b"\0" + (path.read_bytes() if path.exists() else b"<absent>") + b"\0")
    return total.hexdigest()


def approve_config(root):
    """Backlog-Approved: yes in the executable block of .uak/PROJECT.md, atomically. Returns the new bytes."""
    path = regular_file(root, ".uak/PROJECT.md")
    text = path.read_bytes().decode("utf-8")
    blocks = list(re.finditer(r"(?ms)^```text\r?\n(.*?)^```", text))
    if len(blocks) != 1:
        raise ValueError("Expected one executable configuration block in .uak/PROJECT.md.")
    block = blocks[0].group(1)
    if len(re.findall(r"(?m)^Backlog-Approved:[^\r\n]*", block)) != 1 or \
            len(re.findall(r"(?m)^[-* ]*Backlog-Approved:", text)) != 1:
        raise ValueError("Keep exactly one Backlog-Approved line in .uak/PROJECT.md's configuration block.")
    block = re.sub(r"(?m)^Backlog-Approved:[^\r\n]*", "Backlog-Approved: yes", block)
    data = (text[:blocks[0].start(1)] + block + text[blocks[0].end(1):]).encode("utf-8")
    write_atomic(path, data)
    return data
