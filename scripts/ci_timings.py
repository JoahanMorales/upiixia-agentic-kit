#!/usr/bin/env python3
"""ci_timings: the seconds each test file took on the CI runners, read from the job logs of the last green runs of main,
and the timing entry the rule gives (UAK-197).

    python3 scripts/ci_timings.py                      # the last 10 green runs of main: a table, nothing written
    python3 scripts/ci_timings.py --runs 20
    python3 scripts/ci_timings.py --run 45654821354    # these runs instead (a pull request's run, repeatable)
    python3 scripts/ci_timings.py --write kit/.uak/tests/timings/test_x.txt …   # rewrite only these timing files

The rule: a timing entry is the maximum measured over the runs read, per system it stands for (`ci`: Linux and macOS, the
suite shards of both read it; `windows`: Windows), times 1.25, rounded up, and never less than the maximum plus 2 s.
Why: with "maximum plus 1 s" a test that takes 25 to 96 s on macOS from run to run forced five pushes of nothing but a
number (UAK-192), and public issue #85 lists nine files below their measurement.

Where the seconds come from: the runner (scripts/ci_select.py run) opens a log group named after each file
(`::group::test_x`, then `test_x starts, job elapsed …` with the clock) and closes it when the file ends; a second run is
the group `test_x (second run)`. A file's seconds are the time from its group line to its endgroup line (the log's own
timestamps); both runs of a file count. Jobs that were cancelled or skipped are not read; in a job that failed, the files
the runner names as failed are not measurements; a group that never closes (a job killed inside the file) is not one either. A file measured on one system only keeps the entry of the other.
Needs `gh` (authenticated); nothing else touches the network. The parsing is pure and tested offline
(kit/.uak/tests/test_ci_timings.py, ci_timings_reads_runs_and_writes_entries)."""
import argparse
import datetime as dt
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMINGS_DIR = ROOT / "kit/.uak/tests/timings"
REPO = "JoahanMorales/upiixia-agentic-kit"
WORKFLOW = "test.yml"
FACTOR = 1.25
FLOOR_S = 2
RULE = "max x 1.25 rounded up, never less than max + 2 s"

_STAMP = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z ?(.*)$")
_GROUP = re.compile(r"^(?:##\[group\]|::group::)((?:test_[A-Za-z0-9_]+|mcp_tools))( \(second run\))?\s*$")
_END = re.compile(r"^(?:##\[endgroup\]|::endgroup::)\s*$")
_LINE = re.compile(r"(ci|windows)[ \t]+([0-9]+)")


class Failure(Exception):
    """A reason this script cannot go on, said in one line (no traceback)."""


def entry_for(seconds):
    """The timing entry for a file whose longest measured run took `seconds`: max x 1.25 rounded up, never under max + 2."""
    m = float(seconds)
    if m < 0:
        raise ValueError("seconds cannot be negative: %r" % seconds)
    return max(math.ceil(round(m * FACTOR, 6)), math.ceil(round(m + FLOOR_S, 6)), 1)


def system_of(job):
    """linux, macos or windows from a job name of the workflow (`suite (ubuntu-latest, 2)`, `windows (3)`); None otherwise."""
    if re.match(r"^suite \(ubuntu", job):
        return "linux"
    if re.match(r"^suite \(macos", job):
        return "macos"
    if re.match(r"^windows \(\d+\)", job):
        return "windows"
    return None


def _when(stamp):
    head, _, frac = stamp.partition(".")
    t = dt.datetime.strptime(head, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    return t.timestamp() + (float("0." + frac) if frac else 0.0)


def parse_job_log(text):
    """({file: seconds}, notes) from one job's log: each file's longest run (first or second). A line may carry a prefix
    (`gh run view --log` adds `JOB<TAB>STEP<TAB>`, the raw log a byte-order mark): the timestamp is found anywhere.
    A file's run is a group the runner opened: `NAME` directly followed by the runner's `HH:MM:SSZ NAME starts, job elapsed`
    line, or `NAME (second run)` of a file seen so, and NAME is in the job's `SHARD_TESTS` when the log shows that list.
    Test output may print groups of its own (test_ci_tiers runs a fake runner): those are not files, and the file's run
    ends at the last endgroup before the next file, the next step or the end of the log. A run with no endgroup after it (the job stopped inside the file) is not a measurement."""
    rows = []
    for raw in text.splitlines():
        m = _STAMP.search(raw)
        if m:
            rows.append((_when(m.group(1)), m.group(2).strip()))
    seconds, notes, seen = {}, [], set()
    cur, last_end = None, None
    # The job's own list of files (`SHARD_TESTS: test_a test_b`, printed with the step's env): a group of another name
    # is a test's output, not a file of the job.
    listed = None
    for _, body in rows:
        m = re.match(r"^SHARD_TESTS:\s*(.*)$", body)
        if m:
            listed = set(m.group(1).split())
            break

    def close():
        if cur is None:
            return
        name, began = cur
        if last_end is None or last_end < began:
            notes.append("%s: no endgroup after it (the job stopped inside the file): not measured" % name)
        else:
            seconds[name] = max(seconds.get(name, 0.0), round(last_end - began, 1))

    for i, (when, body) in enumerate(rows):
        g = _GROUP.match(body)
        nxt = rows[i + 1][1] if i + 1 < len(rows) else ""
        if g and listed is not None and g.group(1) not in listed:
            g = None
        if g and ((g.group(2) and g.group(1) in seen)
                  or (not g.group(2) and re.match(r"^\d\d:\d\d:\d\dZ %s starts, job elapsed" % re.escape(g.group(1)), nxt))):
            close()
            cur, last_end = (g.group(1), when), None
            seen.add(g.group(1))
        elif _END.match(body):
            last_end = when
        elif cur is not None and re.match(r"^(##\[group\]Run |##\[error\]Process completed)", body):
            close()
            cur = None
    close()
    if not seconds:
        notes.append("no file timings in this log")
    return seconds, notes


def failed_files(text):
    """The files the runner says failed in a job (`##[error]test_x failed (job)` or `failed both times`)."""
    return set(re.findall(r"##\[error\](test_[A-Za-z0-9_]+|mcp_tools) failed\b", text))


def measure(jobs):
    """{file: {system: (seconds, run)}} from [(run, job name, conclusion, log text)], and notes. A job that was cancelled,
    skipped or never ended is left out; in a job that failed, the files the runner names as failed are left out and every
    file that passed is a measurement (a pull request's run fails on its own new test, the others ran whole). Jobs of no
    known system are left out."""
    table, notes = {}, []
    for run, job, conclusion, text in jobs:
        system = system_of(job)
        if system is None:
            continue
        if conclusion not in ("success", "failure"):
            notes.append("run %s, %s: %s, not read" % (run, job, conclusion or "no conclusion"))
            continue
        got, why = parse_job_log(text)
        notes.extend("run %s, %s: %s" % (run, job, w) for w in why)
        if conclusion == "failure":
            bad = failed_files(text)
            for name in sorted(bad & set(got)):
                notes.append("run %s, %s: %s failed there, not measured" % (run, job, name))
                del got[name]
        for name, s in got.items():
            have = table.setdefault(name, {}).get(system)
            if have is None or s > have[0]:
                table[name][system] = (s, run)
    return table, notes


def rule_entries(row):
    """(ci, windows) entries the rule gives for one file's row; None for a system with no measurement."""
    ci = [row[s][0] for s in ("linux", "macos") if s in row]
    return (entry_for(max(ci)) if ci else None, entry_for(row["windows"][0]) if "windows" in row else None)


def read_entry(path):
    """(ci, windows) of a timing file, None where it has no line (or no file)."""
    got = {}
    p = Path(path)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = _LINE.fullmatch(line.strip())
            if m:
                got[m.group(1)] = int(m.group(2))
    return got.get("ci"), got.get("windows")


def render(table, folder=TIMINGS_DIR):
    """The table: per file the maximum per system (with its run), the entry now and the entry the rule gives; `raise`
    marks a file whose entry is below the rule."""
    lines = ["%-44s %10s %10s %10s   %-13s %-13s" % ("file", "linux", "macos", "windows", "ci now>rule", "win now>rule")]
    for name in sorted(table):
        row = table[name]
        cell = lambda s: ("%.0f" % row[s][0]) if s in row else "-"
        now_ci, now_win = read_entry(Path(folder) / (name + ".txt"))
        rule_ci, rule_win = rule_entries(row)
        low = [x for x, now, rule in (("ci", now_ci, rule_ci), ("windows", now_win, rule_win))
               if rule is not None and (now is None or now < rule)]
        lines.append("%-44s %10s %10s %10s   %-13s %-13s%s" % (
            name, cell("linux"), cell("macos"), cell("windows"),
            "%s>%s" % (now_ci if now_ci is not None else "-", rule_ci if rule_ci is not None else "-"),
            "%s>%s" % (now_win if now_win is not None else "-", rule_win if rule_win is not None else "-"),
            ("  raise " + ",".join(low)) if low else ""))
    return "\n".join(lines)


def write_entry(path, row, date, run):
    """Rewrite one timing file from its row: the measured systems get the rule's entry, an unmeasured one keeps its line.
    Comment lines stay, except an older `# measured` or `# rule` line. Returns (ci, windows) written."""
    p = Path(path)
    if p.suffix != ".txt" or p.parent.resolve() != TIMINGS_DIR.resolve() and p.parent.name != "timings":
        raise Failure("%s is not a timing file (kit/.uak/tests/timings/NAME.txt)" % path)
    old_ci, old_win = read_entry(p)
    rule_ci, rule_win = rule_entries(row)
    ci = rule_ci if rule_ci is not None else old_ci
    win = rule_win if rule_win is not None else old_win
    if ci is None or win is None:
        raise Failure("%s: no measurement and no entry for %s: not written" % (p.name, "ci" if ci is None else "windows"))
    for v in (ci, win):
        if not 1 <= v <= 3600:
            raise Failure("%s: the rule gives %d s, outside 1 to 3600: split the file" % (p.name, v))
    keep = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if _LINE.fullmatch(s) or re.match(r"#\s*(measured|rule)\b", s):
                continue
            keep.append(line)
    seen = ", ".join("%s %.1f s (%s)" % (s, row[s][0], row[s][1]) for s in ("linux", "macos", "windows") if s in row)
    text = "# measured %s %s\n# rule: %s; maxima %s\n" % (date, run, RULE, seen)
    text += "".join(l + "\n" for l in keep) + "ci %d\nwindows %d\n" % (ci, win)
    p.write_text(text, encoding="utf-8")
    return ci, win


def run_gh(args):
    """stdout of `gh ARGS`; a Failure naming the command when gh is missing or fails (no network, not logged in)."""
    if not shutil.which("gh"):
        raise Failure("gh is not installed: https://cli.github.com (then gh auth login)")
    try:
        r = subprocess.run(["gh"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    except subprocess.TimeoutExpired:
        raise Failure("gh %s took over 300 s" % " ".join(args[:4]))
    if r.returncode != 0:
        raise Failure("gh %s failed (%d): %s" % (" ".join(args[:4]), r.returncode, (r.stderr or r.stdout).strip()[-300:]))
    return r.stdout


def fetch(repo, runs=10, only=None, gh=run_gh, cache=None):
    """[(run, job, conclusion, log)] and [(run, date)] of the last `runs` green runs of main (or of the runs in `only`).
    A run that did not succeed is skipped and named; logs are kept in `cache` (a folder) when one is given."""
    picked, notes = [], []
    if only:
        for rid in only:
            info = json.loads(gh(["run", "view", str(rid), "-R", repo, "--json", "databaseId,conclusion,createdAt"]))
            picked.append(info)
    else:
        picked = json.loads(gh(["run", "list", "-R", repo, "--workflow", WORKFLOW, "--branch", "main", "--status",
                                "success", "--limit", str(runs), "--json", "databaseId,conclusion,createdAt"]))
    out, dates = [], []
    for info in picked:
        rid = info["databaseId"]
        if info.get("conclusion") != "success" and not only:
            notes.append("run %s: %s, not read" % (rid, info.get("conclusion") or "not finished"))
            continue
        jobs = json.loads(gh(["run", "view", str(rid), "-R", repo, "--json", "jobs"])).get("jobs", [])
        dates.append((rid, (info.get("createdAt") or "")[:10]))
        for job in jobs:
            if system_of(job.get("name", "")) is None:
                continue
            if job.get("conclusion") not in ("success", "failure"):
                out.append((rid, job["name"], job.get("conclusion"), ""))
                continue
            text = None
            hit = Path(cache) / ("%s.log" % job["databaseId"]) if cache else None
            if hit and hit.is_file():
                text = hit.read_text(encoding="utf-8", errors="replace")
            if text is None:
                text = gh(["run", "view", str(rid), "-R", repo, "--log", "--job", str(job["databaseId"])])
                if hit:
                    hit.parent.mkdir(parents=True, exist_ok=True)
                    hit.write_text(text, encoding="utf-8")
            out.append((rid, job["name"], job.get("conclusion"), text))
    if not dates:
        notes.append("no run read")
    return out, dates, notes


def timing_path(arg):
    p = Path(arg)
    if p.suffix != ".txt":
        p = TIMINGS_DIR / (p.name + ".txt")
    return p if p.is_absolute() else (Path.cwd() / p)


def main(argv=None, gh=run_gh, out=sys.stdout):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", type=int, default=10, help="how many green runs of main to read (default 10)")
    ap.add_argument("--run", action="append", default=[], help="read this run instead (repeatable)")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--cache", help="a folder that keeps the job logs read")
    ap.add_argument("--write", nargs="+", metavar="FILE", help="rewrite only these timing files with the rule's entries")
    a = ap.parse_args(argv)
    try:
        jobs, dates, notes = fetch(a.repo, a.runs, a.run, gh=gh, cache=a.cache)
        table, more = measure(jobs)
        notes += more
        if not table:
            raise Failure("no file timings in the runs read (%s): nothing to say" % (", ".join(str(r) for r, _ in dates) or "none"))
        print("Read %d run(s): %s. Rule: %s." % (len(dates), ", ".join(str(r) for r, _ in dates), RULE), file=out)
        print(render(table), file=out)
        for n in notes:
            print("note: " + n, file=out)
        for arg in a.write or []:
            p = timing_path(arg)
            name = p.stem
            if name not in table:
                raise Failure("%s: no measurement of %s in the runs read: not written" % (p.name, name))
            newest = max(dates, key=lambda d: (d[1], d[0]))
            ci, win = write_entry(p, table[name], newest[1], newest[0])
            print("wrote %s: ci %d, windows %d" % (p.name, ci, win), file=out)
    except Failure as exc:
        print("ci_timings: %s" % exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
