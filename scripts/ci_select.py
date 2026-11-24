#!/usr/bin/env python3
"""ci_select: which tests a pull request runs on macOS and Windows, and the small decisions around it (UAK-168).

    python3 scripts/ci_select.py BASE HEAD            # the files per system and the predicted seconds, for a person
    python3 scripts/ci_select.py BASE HEAD --github-output --event pull_request --labels ci-full >> "$GITHUB_OUTPUT"
    python3 scripts/ci_select.py run --kind smoke --retry --job NAME --out result.json test_a test_b
    python3 scripts/ci_select.py gate                 # reads NEEDS (toJSON(needs)) and PLANNED; fails unless discover and every planned job succeeded
    python3 scripts/ci_select.py issue --sha SHA --run-id ID --repo OWNER/REPO [--apply]

Why: every push of every pull request paid the whole matrix (19 jobs, macOS 15 to 19 minutes, Windows 17 to 26, plus the
wait for a runner). Two tiers: a pull request runs the whole suite on Linux and, on macOS and Windows, the test files it
adds or edits, the tests that name a command or a library it touches (the selector of `smoke --affected`, kit/.uak/bin/lib/
tests.sh, WITHOUT its escalation to the whole suite: a shared file is listed as "runs on main") and a fixed portability set
(kit_lint.PORTABILITY_SET). Main and tags run the whole matrix. The workflow always runs and decides here, so the one
required check, `ci`, is never "Pending" behind a skipped workflow. Standard library only; Linux runs it before any setup."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "kit"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit_lint as lint  # noqa: E402

FIRST_TIER_BOUND_S = 600      # a macOS or Windows job of the first tier is predicted under this; over it, two jobs
MAX_JOBS_PER_SYSTEM = 2
MACOS_SETUP_S = 60            # checkout, Git identity and the runner start, before the first file
FULL_LABEL = "ci-full"
TIMINGS_PREFIX = "kit/.uak/tests/timings/"
# A change to these runs the whole matrix on a pull request: the workflow decides what runs, and this is the selector.
FORCE_PREFIXES = (".github/workflows/",)
FORCE_FILES = ("scripts/ci_select.py", "kit/.uak/bin/lib/tests.sh")
RED_TITLE = "main is red at "
NOT_COUNTED = ("ci", "red-main")   # jobs that are not the matrix: the gate and the issue job
# UAK-169: a failed file runs once more only when the second run fits.
RETRY_MAX_S = 300             # a file whose timing entry is over this fails the job on its first failure
SLOW_FACTOR = 3.0             # the median file is this many times slower than its entry (windows (4) at 14ccdbc0: 9 to 10 times)
SLOW_MIN_TABLE_S = 30         # table seconds measured before the speed is judged: one short file says nothing
SLOW_MIN_FILES = 5            # finished files before it is judged: one stale entry (test_done_without_github: 68 s, really 187 to 263) must not decide
JOB_LIMIT_S = (("windows", 45 * 60), ("suite", 60 * 60))   # timeout-minutes of the jobs, to tell a time limit from a hand


def tests_on_disk(kit=None):
    return sorted(p.stem for p in ((kit or KIT) / ".uak" / "tests").glob("test_*.py"))


# ---- the diff -------------------------------------------------------------------------------------------------------
def changed_files(repo, base, head):
    """[(status, path)] of what HEAD brings against the merge base with BASE (renames are a delete and an add)."""
    def git(*a):
        return subprocess.run(["git", "-C", str(repo)] + list(a), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    mb = git("merge-base", base, head)
    start = mb.stdout.decode().strip() if mb.returncode == 0 and mb.stdout.strip() else base
    out = git("-c", "core.quotePath=false", "diff", "--name-status", "--no-renames", "-z", start, head)
    if out.returncode != 0:
        raise SystemExit("ci_select: git diff %s %s failed: %s" % (start, head, out.stderr.decode(errors="replace").strip()))
    parts = out.stdout.decode("utf-8", "replace").split("\0")
    return [(parts[i][:1], parts[i + 1]) for i in range(0, len(parts) - 1, 2) if parts[i]]


def forced_by(changed):
    for _, path in changed:
        if path.startswith(FORCE_PREFIXES) or path in FORCE_FILES:
            return path
    return ""


def decide(event, labels, dispatch_tier, changed, ref=""):
    """('full'|'first', why). Push and tags: the second tier. A pull request: the first, unless the label or the files say otherwise."""
    if event == "push":
        return "full", "a push to %s runs the whole matrix" % (ref or "main or a tag")
    if event == "workflow_dispatch":
        if dispatch_tier == "first":
            return "first", "a manual run asked for the first tier"
        return "full", "a manual run of the branch runs the whole matrix"
    if FULL_LABEL in labels:
        return "full", "the label %s asks for the whole matrix" % FULL_LABEL
    path = forced_by(changed)
    if path:
        return "full", "the change touches %s (the workflow or the selector itself)" % path
    return "first", "a pull request runs the first tier"


# ---- the selection --------------------------------------------------------------------------------------------------
# A selector that fails for a file is a failure of the job, not "no test names it" (that one is an answer: a `-` line).
_BASH = r'''
set -u
. "$KIT/.uak/bin/lib/tests.sh"
while IFS= read -r f; do
  [ -n "$f" ] || continue
  printf '%s\n' "$f" > "$TMP/one"
  printf '@@\t%s\n' "$f"
  tf_affected_select "$KIT" "$TMP/one" "$TMP/tests" 2>"$TMP/err"; rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '@!\t%s\t%s\t%s\n' "$f" "$rc" "$(tail -c 300 "$TMP/err" | tr '\n\r\t' '   ')"
  fi
done < "$TMP/changed"
'''


def _kit_relative(path):
    return path[4:] if path.startswith("kit/") else "../" + path


def _bash():
    """Git's bash on Windows (the first `bash` on PATH there can be WSL's), the PATH's elsewhere."""
    if os.name == "nt":
        for root in (os.environ.get("ProgramFiles", "C:/Program Files"), os.environ.get("ProgramW6432", "")):
            cand = Path(root) / "Git" / "bin" / "bash.exe"
            if root and cand.is_file():
                return str(cand)
    return "bash"


def _affected(paths, kit):
    """Run smoke --affected's selector once per changed file, so an escalation to ALL of one file loses nothing of the others.
    Returns {path: [("ALL"|test.py|"-", why)]}."""
    if not paths:
        return {}
    with tempfile.TemporaryDirectory(prefix="uak-ci-select-") as tmp:
        tmp = Path(tmp)
        # LF only: a CRLF list (Python's text mode on Windows) leaves a \r on every name for bash
        with open(str(tmp / "changed"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(_kit_relative(p) + "\n" for p in paths))
        with open(str(tmp / "tests"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(t + ".py\n" for t in tests_on_disk(kit)))
        r = subprocess.run([_bash(), "-c", _BASH], env=dict(os.environ, KIT=Path(kit).as_posix(), TMP=tmp.as_posix()), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    broke = [l.replace("\r", "").split("\t", 3) for l in r.stdout.splitlines() if l.startswith("@!\t")]
    if broke:
        raise SystemExit("ci_select: the selector of smoke --affected failed for %s (exit %s): %s" % (broke[0][1], broke[0][2], (broke[0][3] if len(broke[0]) > 3 else "").strip() or "no message"))
    if r.stdout.count("@@\t") != len(paths):
        raise SystemExit("ci_select: the selector of smoke --affected answered for %d of %d files (rc %d): %s"
                         % (r.stdout.count("@@\t"), len(paths), r.returncode, r.stderr.strip()[-300:]))
    got, cur = {}, None
    by_rel = {_kit_relative(p): p for p in paths}
    for line in r.stdout.replace("\r", "").splitlines():
        if line.startswith("@@\t"):
            cur = by_rel.get(line[3:])
            got.setdefault(cur, [])
        elif cur is not None and "\t" in line:
            t, why = line.split("\t", 1)
            got[cur].append((t, why))
    return got


def select(changed, kit=None):
    """{"macos": {test: [reasons]}, "windows": {test: [reasons]}, "withheld": [(file, why)], "new": [tests], "forced": path}.
    Never the whole suite: the files smoke --affected would answer ALL for are listed in "withheld" and run on main."""
    kit = kit or KIT
    on_disk = set(tests_on_disk(kit))
    sel = {"macos": {}, "windows": {}, "withheld": [], "new": [], "forced": forced_by(changed)}

    def add(systems, test, why):
        for s in systems:
            sel[s].setdefault(test, [])
            if why not in sel[s][test]:
                sel[s][test].append(why)
    both = ("macos", "windows")
    to_ask = []
    for status, path in sorted(changed):
        name = path.rsplit("/", 1)[-1]
        if path.startswith("kit/.uak/tests/") and name.startswith("test_") and name.endswith(".py") and path.count("/") == 3:
            if status != "D":
                stem = name[:-3]
                if status == "A":
                    sel["new"].append(stem)
                    add(both, stem, "new test file: runs on the three systems so its seconds can be measured")
                else:
                    add(both, stem, "changed test file")
            to_ask.append(path)
        elif path.startswith(TIMINGS_PREFIX) and name.endswith(".txt") and path.count("/") == 4:
            # A timing file (UAK-187): not a test and not a reason to run everything; the test it times runs, so its seconds can be measured again.
            stem = name[:-4]
            if status != "D" and stem in on_disk:
                add(both, stem, "changed timing file: its seconds are measured again")
        elif path.startswith("tests/") and path.endswith(".py"):
            add(("windows",), "mcp_tools", "changed tests/ (the MCP tools)")
        elif status != "D":
            to_ask.append(path)
        else:
            to_ask.append(path)
    answers = _affected(to_ask, kit)
    for path, rows in answers.items():
        for t, why in rows:
            if t == "ALL":
                sel["withheld"].append((path, why))
            elif t == "-":
                continue
            elif t.endswith(".py") and t[:-3] in on_disk:
                add(both, t[:-3], why)
    for t, why in lint.PORTABILITY_SET.items():
        add(both, t, "portability: " + why)
    # The first tier has a budget: what the change adds or edits and the portability set always run; the tests chosen
    # because they name a file the change touches are added cheapest first while every job stays under the bound, and the
    # rest (a 900 s test that names README.md) runs on main. Without it a doc change selected 37 minutes of Windows.
    sel["budget"] = {}
    for system, seconds, setup in (("macos", lint.ci_seconds, MACOS_SETUP_S), ("windows", lint.ci_windows_seconds, lint.WINDOWS_SETUP_S)):
        mandatory = [t for t, why in sel[system].items() if any(x.startswith(("changed test file", "new test file", "changed timing file", "changed tests/", "portability")) for x in why)]
        optional = sorted((t for t in sel[system] if t not in mandatory), key=lambda t: (seconds(t), t))
        keep = list(mandatory)
        sel["budget"][system] = []
        for t in optional:
            shards, _ = _split_jobs(keep + [t], seconds, setup)
            if max(x["seconds"] for x in shards) < FIRST_TIER_BOUND_S:   # "under": a job predicted at exactly the bound is over it
                keep.append(t)
            else:
                sel["budget"][system].append(t)
                del sel[system][t]
    for system in both:
        for t in sel[system]:
            sel[system][t] = [x.replace(" ../", " ") for x in sel[system][t]]
    return sel


def _split_jobs(names, seconds, setup):
    """(list of shards [{seconds, tests}], total seconds): one job, two when the total is predicted over the bound."""
    total = setup + sum(seconds(t) for t in names)
    k = 1 if total < FIRST_TIER_BOUND_S else MAX_JOBS_PER_SYSTEM   # "under the bound", as the selection loop in select() reads it
    shards = lint._split(names, k, seconds)
    return [{"n": s["n"], "tests": s["tests"], "seconds": setup + sum(seconds(t) for t in s["tests"].split())} for s in shards], total


def predict(sel):
    mac_names = sorted(sel["macos"])
    win_names = sorted(sel["windows"])
    out = {}
    out["macos"] = dict(zip(("shards", "seconds"), _split_jobs(mac_names, lint.ci_seconds, MACOS_SETUP_S)))
    out["windows"] = dict(zip(("shards", "seconds"), _split_jobs(win_names, lint.ci_windows_seconds, lint.WINDOWS_SETUP_S)))
    return out


def matrices(tier, sel, full_shards=None, full_windows=None):
    """The job matrices the workflow runs: {"shards": [{os, n, tests, checks}], "wshards": [{n, tests}]}."""
    linux = full_shards or lint.ci_shards(4)
    shards = [dict(s, os="ubuntu-latest", checks=s["n"] == 1) for s in linux]
    if tier == "full":
        shards += [dict(s, os="macos-latest", checks=s["n"] == 1) for s in linux]
        wshards = full_windows or lint.ci_windows_shards(lint.windows_shard_count())
        return {"shards": shards, "wshards": [{"n": s["n"], "tests": s["tests"]} for s in wshards]}
    pred = predict(sel)
    shards += [{"os": "macos-latest", "n": s["n"], "tests": s["tests"], "checks": False} for s in pred["macos"]["shards"]]
    return {"shards": shards, "wshards": [{"n": s["n"], "tests": s["tests"]} for s in pred["windows"]["shards"]]}


def job_count(m):
    """The jobs that run tests: discover, the suite shards, the Windows shards (the gate `ci` and `red-main` are not counted)."""
    return 1 + len(m["shards"]) + len(m["wshards"])


# ---- reports ---------------------------------------------------------------------------------------------------------
def report(tier, why, changed, sel, m, markdown=False):
    pred = predict(sel)
    suite = tests_on_disk()
    h = "### " if markdown else ""
    lines = ["%stier: %s (%s)" % (h, tier, why), "changed files: %d" % len(changed)]
    if tier == "full":
        lines.append("the whole matrix runs (%d jobs): nothing is left for main" % job_count(m))
        return "\n".join(lines) + "\n"
    for system, label in (("macos", "macOS"), ("windows", "Windows")):
        p = pred[system]
        names = sorted(sel[system], key=lambda t: -(lint.ci_seconds(t) if system == "macos" else lint.ci_windows_seconds(t)))
        lines.append("")
        lines.append("%s%s: %d test files, predicted %d s (%s)" % (h, label, len(names), p["seconds"],
                     ", ".join("job %d: %d s" % (s["n"], s["seconds"]) for s in p["shards"])))
        for t in names:
            secs = lint.ci_seconds(t) if system == "macos" else lint.ci_windows_seconds(t)
            lines.append("  %s%s  %d s  (%s)" % ("- " if markdown else "", t, secs, "; ".join(sel[system][t])))
    left = [t for t in suite if t not in sel["macos"] or t not in sel["windows"]]
    lines.append("")
    lines.append("%sruns on main: macOS %d of %d, Windows %d of %d test files are not in this run" % (
        h, len([t for t in suite if t not in sel["macos"]]), len(suite), len([t for t in suite if t not in sel["windows"]]), len(suite)))
    for system, label in (("macos", "macOS"), ("windows", "Windows")):
        if sel["budget"].get(system):
            lines.append("over the first tier's budget on %s, they run on main: %s" % (label, " ".join(sel["budget"][system])))
    if sel["withheld"]:
        lines.append("the selector would run the whole suite for these; here it does not, they run on main:")
        for f, why in sel["withheld"]:
            lines.append("  %s%s: %s" % ("- " if markdown else "", f, why))
    lines.append("ask for the whole matrix: the label %s, or a manual run of the branch" % FULL_LABEL)
    return "\n".join(lines) + "\n"


def github_output(tier, why, m):
    planned = ["discover"] + (["suite"] if m["shards"] else []) + (["windows"] if m["wshards"] else [])
    return "tier=%s\nreason=%s\nplanned=%s\nshards=%s\nwshards=%s\n" % (tier, why.replace("\n", " "), ",".join(planned),
                                                                       json.dumps(m["shards"], separators=(",", ":")), json.dumps(m["wshards"], separators=(",", ":")))


# ---- running files, with one retry on macOS and Windows -------------------------------------------------------------
def _say(line):
    print(line, flush=True)


def _stamp(secs):
    return "%d s" % secs


def write_result(path, job, res, running=""):
    """The result JSON, written before each file and at the end: a job cancelled by its time limit leaves it, so the artifact
    says which file the job was in (windows (1) at e4f2f83d was cancelled with no log left and nothing to say where)."""
    if not path:
        return
    done = [f for f in res["ran"] if f in res["counts"]]
    body = {"job": job, "conclusion": "running" if running else res.get("conclusion", "passed"), "running": running, "done": done,
            "failed": res["failed"], "flaky": res["flaky"], "counts": res["counts"], "not_rerun": res["not_rerun"],
            "slow": res["slow"], "stopped": res["stopped"]}
    tmp = str(path) + ".part"
    Path(tmp).write_text(json.dumps(body), encoding="utf-8")
    os.replace(tmp, str(path))


def _time_left(runner, bound, start, clock):
    """Every run of a file, the first or the second, gets what is left of the job's bound."""
    if hasattr(runner, "timed_out"):
        runner.timed_out = False
    if bound is not None and hasattr(runner, "timeout"):
        runner.timeout = max(bound - (clock() - start), 1)


def run_files(files, runner, retry, log=_say, seconds=None, bound=None, clock=time.monotonic, out=None, job="job"):
    """Run each file; with retry a failed file runs once more, but only when the second run fits (its timing entry is at most
    RETRY_MAX_S and the job's elapsed time plus that entry stays under `bound`, the job's seconds for tests). {ran, failed,
    flaky, counts, not_rerun, slow, stopped}: failed = failed every time, flaky = failed then passed (the job passes, and
    says so), not_rerun = {file: why} for a failure that was not run again, slow = the "slow runner, re-run" line when the
    files left cannot end inside the bound at the speed seen so far, stopped = the file the job did not start or cut short.
    Speed is the median of the per-file ratios (actual / entry) of the files finished on their first run, judged after
    SLOW_MIN_FILES files and SLOW_MIN_TABLE_S table seconds: one stale entry cannot decide it. Before each file the name and
    the clock are printed (flushed) and the partial result is written; a run that passes the bound is killed (the runner's
    `timeout`, the time left) and the job stops there."""
    res = {"ran": list(files), "failed": [], "flaky": [], "counts": {}, "not_rerun": {}, "slow": "", "stopped": ""}
    start = clock()
    ratios, seen_table = [], 0.0
    for i, f in enumerate(files):
        elapsed = clock() - start
        entry = seconds(f) if seconds else 0
        if bound is not None and elapsed >= bound:
            res["stopped"] = f
            log("stopped before %s: the job used %s of its %s for tests" % (f, _stamp(elapsed), _stamp(bound)))
            break
        log("::group::" + f)
        log("%s %s starts, job elapsed %s%s" % (time.strftime("%H:%M:%SZ", time.gmtime()), f, _stamp(elapsed), (", table %d s" % entry) if seconds else ""))
        write_result(out, job, res, running=f)
        _time_left(runner, bound, start, clock)
        began = clock()
        ok = runner(f)
        took = clock() - began
        runs, failures = 1, 0 if ok else 1
        if not ok and getattr(runner, "timed_out", False):
            res["failed"].append(f)
            res["counts"][f] = {"runs": 1, "failures": 1}
            res["stopped"] = f
            log("::endgroup::")
            break
        if not ok and retry:
            used = clock() - start
            if seconds and entry > RETRY_MAX_S:
                res["not_rerun"][f] = "not run again: %s takes %d s (over %d s)" % (f, entry, RETRY_MAX_S)
            elif seconds and bound is not None and used + entry >= bound:
                res["not_rerun"][f] = "not run again: %s takes %d s and the job used %s of its %s for tests" % (f, entry, _stamp(used), _stamp(bound))
            else:
                log("::endgroup::")
                log("::group::%s (second run)" % f)
                _time_left(runner, bound, start, clock)
                ok = runner(f)
                runs, failures = 2, failures + (0 if ok else 1)
                if not ok and getattr(runner, "timed_out", False):
                    res["failed"].append(f)
                    res["counts"][f] = {"runs": 2, "failures": 2}
                    res["stopped"] = f
                    log("::endgroup::")
                    break
                if ok:
                    res["flaky"].append(f)
        if not ok:
            res["failed"].append(f)
        res["counts"][f] = {"runs": runs, "failures": failures}
        log("::endgroup::")
        if runs == 1 and seconds and entry:
            ratios.append(took / entry)
            seen_table += entry
            left = sum(seconds(g) for g in files[i + 1:])
            if left and len(ratios) >= SLOW_MIN_FILES and seen_table >= SLOW_MIN_TABLE_S:
                median = sorted(ratios)[len(ratios) // 2] if len(ratios) % 2 else sum(sorted(ratios)[len(ratios) // 2 - 1:len(ratios) // 2 + 1]) / 2
                ends = (clock() - start) + left * median
                if median >= SLOW_FACTOR and bound is not None and ends > bound:
                    res["slow"] = ("slow runner, re-run: the median file ran %.1f times its entry over the %d files done (%d table seconds); the %d table seconds left would end at %d s, past the %d s for tests"
                                   % (median, len(ratios), seen_table, left, ends, bound))
                    res["stopped"] = files[i + 1]
                    log(res["slow"])
                    break
    res["conclusion"] = "failed" if (res["failed"] or res["slow"] or res["stopped"]) else ("flaky" if res["flaky"] else "passed")
    write_result(out, job, res)
    return res


def flaky_report(job, res):
    """The summary, the annotations and the conclusion of a job: passed, flaky (never shown as a plain pass) or failed."""
    ann, md = [], []
    for f in res["flaky"]:
        ann.append("::warning title=flaky test::flaky: %s passed on the second run (%s)" % (f, job))
        md.append("- flaky: %s passed on the second run" % f)
    for f in res["failed"]:
        n = res["counts"].get(f, {}).get("runs", 1)
        if f == res.get("stopped"):
            ann.append("::error title=test failed::%s was cut at the job's bound (%s)" % (f, job))
        else:
            ann.append("::error title=test failed::%s failed%s (%s)" % (f, " both times" if n > 1 else "", job))
    extra = []
    for f, why in res.get("not_rerun", {}).items():
        ann.append("::error title=not run again::%s (%s)" % (why, job))
        extra.append(why)
    if res.get("slow"):
        ann.append("::error title=slow runner::%s (%s)" % (res["slow"], job))
        extra.append(res["slow"])
    if res.get("stopped") and not res.get("slow"):
        why = "stopped at %s (stopped at the job's bound for tests): the run was killed there and the files after it did not run" % res["stopped"]
        ann.append("::error title=time bound::%s (%s)" % (why, job))
        extra.append(why)
    conclusion = "failed" if (res["failed"] or res.get("slow") or res.get("stopped")) else ("flaky" if res["flaky"] else "passed")
    head = {"passed": "### %s: passed" % job, "flaky": "### %s: passed, with flaky files" % job, "failed": "### %s: failed" % job}[conclusion]
    summary = [head] + md + ["- " + x for x in extra]
    if res["failed"]:
        summary.append("Failed test files (%s):%s" % (job, "".join(" " + f for f in res["failed"])))
        both = [f for f in res["failed"] if res["counts"].get(f, {}).get("runs", 1) > 1 and f != res.get("stopped")]
        if both:
            summary.append("Failed both times: " + " ".join(both))
    return {"job": job, "conclusion": conclusion, "annotations": ann, "summary": "\n".join(summary) + "\n",
            "failed": res["failed"], "flaky": res["flaky"], "counts": res["counts"], "not_rerun": res.get("not_rerun", {}),
            "slow": res.get("slow", ""), "stopped": res.get("stopped", "")}


def _start(argv, **kw):
    """Popen with the file in its own session on POSIX (its process group is its pid), so the bound's kill reaches the
    grandchildren too: one that survived, reparented to PID 1, kept the step's pipes open."""
    if os.name != "nt":
        kw["start_new_session"] = True
    return subprocess.Popen(argv, **kw)


class _RealRunner:
    """Runs one file; `timeout` (seconds, set by run_files to the time left to the job's bound) stops a file that would end
    the job by the platform's cancel: the whole group (POSIX) or tree (Windows) is killed and `timed_out` is set."""
    def __init__(self, kind):
        self.kind = kind
        self.timeout = None
        self.timed_out = False

    def _kill(self, p):
        if os.name == "nt":
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.kill()
            p.wait()
        else:
            self._kill_tree(p)

    @staticmethod
    def _children_map():
        """{ppid: [pid]} of every process: /proc where it exists (Linux), `ps -A -o pid=,ppid=` otherwise (macOS)."""
        kids = {}
        pairs = []
        if os.path.isdir("/proc/self"):
            for name in os.listdir("/proc"):
                if name.isdigit():
                    try:
                        pairs.append((int(name), int(Path("/proc/%s/stat" % name).read_text().rsplit(")", 1)[1].split()[1])))
                    except (OSError, ValueError, IndexError):
                        pass
        else:
            out = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True).stdout
            for line in out.splitlines():
                f = line.split()
                if len(f) == 2 and f[0].isdigit() and f[1].isdigit():
                    pairs.append((int(f[0]), int(f[1])))
        for pid, ppid in pairs:
            kids.setdefault(ppid, []).append(pid)
        return kids

    def _descendants(self, root):
        """Every live descendant of root (not root), found by walking parent links: it follows a child that called setsid, which
        a process group does not. Limit: a process that double-forked and was reparented to PID 1 before this ran has no parent
        link to root, so a tree walk cannot find it."""
        kids = self._children_map()
        seen, todo = [], [root]
        while todo:
            for c in kids.get(todo.pop(), []):
                if c not in seen and c != root:
                    seen.append(c)
                    todo.append(c)
        return seen

    GRACE_S = 5   # SIGTERM to SIGKILL

    def _kill_tree(self, p):
        """POSIX cancel and bound kill: collect the file's descendants first (killing the parent would reparent them out of the
        walk), SIGTERM them, wait at most GRACE_S, then SIGKILL what is left, always (`finally`). A further SIGTERM, SIGHUP or
        SIGINT while this runs is ignored, so a burst of signals cannot stop the cleanup half way. Never pid 0 or 1, never the
        driver, its parent or its own process group."""
        import signal
        me, mine = os.getpid(), os.getpgrp()
        old = {}
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            try:
                old[sig] = signal.signal(sig, signal.SIG_IGN)
            except (ValueError, OSError):
                pass

        def hit(pids, sig):
            for pid in pids:
                if pid <= 1 or pid in (me, os.getppid()):
                    continue
                try:
                    if os.getpgid(pid) == mine:
                        continue
                    os.kill(pid, sig)
                except OSError:
                    pass
        family = [p.pid]
        try:
            family += self._descendants(p.pid)
            hit(family, signal.SIGTERM)
            end = time.monotonic() + self.GRACE_S
            while time.monotonic() < end and (p.poll() is None or any(self._alive(x) for x in family if x != p.pid)):
                time.sleep(0.05)
        finally:
            family = list(dict.fromkeys(family + self._descendants(p.pid)))
            hit(family, signal.SIGKILL)
            try:
                if os.getpgid(p.pid) != mine:   # the file's own group (a session of its own, never the driver's)
                    os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            end = time.monotonic() + 10   # confirm the tree is gone
            while time.monotonic() < end and any(self._alive(x) for x in family if x != p.pid):
                time.sleep(0.05)
            for sig, handler in old.items():
                try:
                    signal.signal(sig, handler)
                except (ValueError, OSError):
                    pass

    @staticmethod
    def _alive(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        try:   # a zombie waiting for its parent is gone for this purpose
            return Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except (OSError, IndexError):
            return True

    def _wait(self, p):
        try:
            return p.wait(timeout=self.timeout) == 0
        except subprocess.TimeoutExpired:
            self.timed_out = True
            self._kill(p)
            return False

    def _popen(self, name):
        if self.kind == "smoke":
            # stdin held open, as in a terminal: a command that reads it (BSD awk -W version did) hangs here, not on a laptop.
            return _start(["bash", ".uak/bin/smoke", "--package-only"], cwd=str(KIT), env=dict(os.environ, UAK_SMOKE_TESTS=name), stdin=subprocess.PIPE)
        if name == "mcp_tools":
            return _start([sys.executable, "tests/test_mcp_tools.py"], cwd=str(ROOT), stdin=subprocess.DEVNULL)
        return _start([sys.executable, ".uak/tests/%s.py" % name, "--package", str(KIT)], cwd=str(KIT), stdin=subprocess.DEVNULL)

    def __call__(self, name):
        sys.stdout.flush()
        p = self._popen(name)
        try:
            return self._wait(p)
        except BaseException:
            # the driver was cancelled (SIGINT, or SIGTERM and SIGHUP turned into SystemExit by cmd_run): the file runs in its own
            # session, so it would outlive us; end its whole tree (POSIX: walked by parent links, so a child that called setsid
            # goes too; Windows: taskkill /T) before leaving
            self._kill(p)
            raise
        finally:
            if p.stdin:
                p.stdin.close()


def _real_runner(kind):
    return _RealRunner(kind)


def _end_on_sigterm():
    """SIGTERM and SIGHUP (a cancelled step, a closed terminal; either left the whole tree running) end the driver as `SystemExit(143)` from the main thread, so
    the runner's cleanup kills the file's group. Windows has no catchable SIGTERM (it is TerminateProcess); there Ctrl-C and
    Ctrl-Break still arrive as KeyboardInterrupt and take the same path."""
    import signal

    def handler(signum, frame):
        for sig in (signal.SIGTERM, signal.SIGINT, getattr(signal, "SIGHUP", signal.SIGTERM)):   # the first signal is the one that counts
            signal.signal(sig, signal.SIG_IGN)
        raise SystemExit(128 + signum)
    old = {}
    try:
        for sig in (signal.SIGTERM, signal.SIGINT, getattr(signal, "SIGHUP", None)):
            if sig is not None:
                old[sig] = signal.signal(sig, handler)
    except (ValueError, OSError):   # not the main thread, or a platform without it
        pass
    return old


def cmd_run(argv):
    import signal
    old = _end_on_sigterm()
    try:
        return _cmd_run(argv)
    finally:   # a process that calls this twice (the tests do) keeps its own handlers
        for sig, h in old.items():
            try:
                signal.signal(sig, h)
            except (ValueError, OSError, TypeError):
                pass


def _cmd_run(argv):
    ap = argparse.ArgumentParser(prog="ci_select.py run", description="run test files one by one; a failed file runs once more with --retry")
    ap.add_argument("--kind", choices=("smoke", "windows"), required=True, help="smoke: bash .uak/bin/smoke --package-only per file; windows: python per file")
    ap.add_argument("--job", default="job", help="the job's name, as GitHub shows it")
    ap.add_argument("--retry", action="store_true", help="run a failed file once more (macOS and Windows; Linux never retries)")
    ap.add_argument("--out", help="write the result JSON here (the artifact of the run), before each file and at the end")
    ap.add_argument("--bound", type=int, help="the job's seconds for tests: a retry must fit under it, the job stops itself at it and says which file it was in")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    if not a.files:
        print("FAILED: this shard has no test files (empty list)")
        return 1
    retry = a.retry and os.environ.get("RUNNER_OS") != "Linux"   # Linux never retries, whatever the workflow passes
    seconds = lint.ci_windows_seconds if a.kind == "windows" else lint.ci_seconds
    res = run_files(a.files, _real_runner(a.kind), retry, seconds=seconds, bound=a.bound, out=a.out, job=a.job)
    rep = flaky_report(a.job, res)
    for line in rep["annotations"]:
        print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(rep["summary"])
    else:
        print(rep["summary"])
    if a.out:
        write_result(a.out, a.job, dict(res, conclusion=rep["conclusion"]))
    return 1 if rep["conclusion"] == "failed" else 0


# ---- the gate and the issue ------------------------------------------------------------------------------------------
def gate(needs, planned=None):
    """Problems of the jobs before the gate. With `planned` (the jobs the tier planned, from discover): discover and every
    planned job must have concluded `success`; `skipped` and `cancelled` fail, only a job the tier did not plan may be
    skipped. Without it (a caller that does not know) a skipped job is a job that did not run, as before UAK-169."""
    must = None if planned is None else set(planned) | {"discover"}
    out = []
    for name, v in sorted(needs.items()):
        r = v.get("result")
        if r == "success" or (r == "skipped" and (must is None or name not in must)):
            continue
        out.append("%s: %s" % (name, r or "no result"))
    for name in sorted((must or set()) - set(needs)):
        out.append("%s: not among the jobs the gate waits for" % name)
    return out


def cmd_gate(argv):
    raw = os.environ.get("NEEDS") or "{}"
    needs = json.loads(raw)
    # An empty PLANNED (discover failed before it could say) plans everything: fail closed.
    planned = [x for x in (os.environ.get("PLANNED") or "").split(",") if x] or list(needs)
    problems = gate(needs, planned)
    text = "### ci: %s\n" % ("failed" if problems else "discover and every planned job succeeded") + "".join("- %s\n" % p for p in problems)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 1 if problems else 0


def job_outcome(job):
    """success | failed | time limit | cancelled | skipped, of a job row {name, conclusion, started_at, completed_at}. A job
    cancelled by its own timeout-minutes says `cancelled` like one cancelled by a hand; it ran about as long as its limit."""
    import datetime as dt
    c = job.get("conclusion") or ""
    if c in ("failure", "timed_out"):
        return "failed"
    if c != "cancelled":
        return c or "skipped"
    try:
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        ran = (dt.datetime.strptime(job["completed_at"], fmt) - dt.datetime.strptime(job["started_at"], fmt)).total_seconds()
    except (KeyError, TypeError, ValueError):
        return "cancelled"
    limit = next((s for prefix, s in JOB_LIMIT_S if job.get("name", "").startswith(prefix)), 0)
    return "time limit" if limit and ran >= limit - 90 else "cancelled"


def plan_issue(sha, failed_jobs, failed_both, pr, open_issues, run_url, ci_result="success", causes=None, attempt=1):
    """What to do about the issue of a red main, as data: create one, add to the open one, close it, or nothing. The issue is
    closed only by a run whose `ci` job succeeded (a run cancelled by hand, or one that failed without a named job, closes
    nothing). `causes` = {job: failed|time limit|slow runner|set-up}; a file that failed both times needs no re-run, any other
    failure is not confirmed until the failed jobs ran again (attempt 2 of the run)."""
    short = sha[:7]
    causes = causes or {}
    existing = next((i for i in open_issues if i.get("title", "").startswith(RED_TITLE)), None)
    if not failed_jobs:
        if existing and ci_result == "success":
            return {"action": "close", "number": existing["number"], "body": "main is green again at %s (%s). Closing." % (short, run_url)}
        return {"action": "none"}
    lines = ["The whole matrix failed at %s (%s)." % (short, run_url), "", "Failed jobs:"]
    for j in failed_jobs:
        lines.append("- %s%s" % (j, (" (%s)" % causes[j]) if causes.get(j) else ""))
    lines += ["", "Files that failed both times (each file runs a second time in its job on macOS and Windows, when the second run fits):"]
    any_both = False
    for job in failed_jobs:
        files = failed_both.get(job) or []
        if files:
            any_both = True
            lines.append("- %s: %s" % (job, " ".join(files)))
    if not any_both:
        lines.append("- none recorded (a Linux job never retries; a job can also fail before its tests, or hit its time limit)")
    open_ones = [j for j in failed_jobs if not failed_both.get(j)]
    lines.append("")
    if attempt > 1:
        lines.append("This is attempt %d: the failed jobs ran again and failed after a re-run of the failed jobs." % attempt)
    elif open_ones and any_both:
        lines.append("Jobs with a file that failed both times need no re-run. Not confirmed by a re-run: %s. Run: gh run rerun %s --failed (attempt 2 confirms or closes this issue)."
                     % (", ".join(open_ones), run_url.rsplit("/", 1)[-1]))
    elif open_ones:
        lines.append("Not confirmed by a re-run: a Linux failure, a set-up failure, a slow runner or a time limit can pass on the same commit. Run: gh run rerun %s --failed (attempt 2 confirms or closes this issue)."
                     % run_url.rsplit("/", 1)[-1])
    else:
        lines.append("Every failed job has a file that failed both times: no re-run needed.")
    if pr:
        lines += ["", "Brought by #%s: %s" % (pr["number"], pr.get("title", ""))]
    lines += ["", "Nobody merges on a red main except the fix or the revert (AGENTS.md)."]
    body = "\n".join(lines)
    if existing:
        return {"action": "comment", "number": existing["number"], "body": body}
    return {"action": "create", "title": RED_TITLE + short, "body": body}


def _gh(*args):
    r = subprocess.run(["gh"] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if r.returncode != 0:
        raise SystemExit("ci_select: gh %s failed: %s" % (" ".join(args[:3]), r.stderr.strip()[-300:]))
    return r.stdout


def cmd_issue(argv):
    ap = argparse.ArgumentParser(prog="ci_select.py issue", description="plan (and with --apply, do) the issue of a red main")
    ap.add_argument("--sha", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--results", help="the folder of the jobs' result JSON files (artifacts)")
    ap.add_argument("--ci-result", default="success", help="the result of the run's `ci` job (needs.ci.result): only success closes the issue")
    ap.add_argument("--attempt", type=int, default=1, help="the run's attempt (github.run_attempt): 2 or more is a re-run of the failed jobs")
    ap.add_argument("--apply", action="store_true", help="open, comment or close the issue; without it the plan is only printed")
    a = ap.parse_args(argv)
    rows = _gh("api", "repos/%s/actions/runs/%s/jobs" % (a.repo, a.run_id), "--paginate", "--jq", ".jobs[] | {name, conclusion, started_at, completed_at}")
    jobs = [json.loads(l) for l in rows.splitlines() if l.strip()]
    causes = {j["name"]: job_outcome(j) for j in jobs if j["name"] not in NOT_COUNTED}
    failed = [n for n, c in causes.items() if c in ("failed", "time limit")]
    both = {}
    for p in sorted(Path(a.results).rglob("*.json")) if a.results else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        files = [f for f in r.get("failed", []) if r.get("counts", {}).get(f, {}).get("runs", 1) > 1 and f != r.get("stopped")]
        if r.get("slow") and r.get("job") in causes:
            causes[r["job"]] = "slow runner"
        elif r.get("running") and causes.get(r.get("job")) == "time limit":
            causes[r["job"]] = "time limit, in %s" % r["running"]
        elif r.get("stopped") and r.get("job") in causes:
            causes[r["job"]] = "time bound, stopped at %s" % r["stopped"]
        if files:
            both[r.get("job", p.stem)] = files
    pr = None
    if failed:
        pulls = _gh("api", "repos/%s/commits/%s/pulls" % (a.repo, a.sha), "--jq", ".[0] | {number, title}").strip()
        pr = json.loads(pulls) if pulls and pulls != "null" else None
        if pr and not pr.get("number"):
            pr = None
    listing = _gh("issue", "list", "--repo", a.repo, "--state", "open", "--search", RED_TITLE + " in:title", "--json", "number,title")
    plan = plan_issue(a.sha, failed, both, pr, json.loads(listing or "[]"), "https://github.com/%s/actions/runs/%s" % (a.repo, a.run_id),
                      ci_result=a.ci_result, causes=causes, attempt=a.attempt)
    print(json.dumps(plan, indent=2))
    if not a.apply or plan["action"] == "none":
        return 0
    if plan["action"] == "create":
        _gh("issue", "create", "--repo", a.repo, "--title", plan["title"], "--body", plan["body"])
    elif plan["action"] == "comment":
        _gh("issue", "comment", str(plan["number"]), "--repo", a.repo, "--body", plan["body"])
    else:
        _gh("issue", "close", str(plan["number"]), "--repo", a.repo, "--comment", plan["body"])
    return 0


# ---- the command line ------------------------------------------------------------------------------------------------
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("run", "gate", "issue"):
        return {"run": cmd_run, "gate": cmd_gate, "issue": cmd_issue}[argv[0]](argv[1:])
    ap = argparse.ArgumentParser(description="the files a pull request runs on macOS and Windows, and the predicted seconds")
    ap.add_argument("base", nargs="?")
    ap.add_argument("head", nargs="?")
    ap.add_argument("--repo", default=str(ROOT), help="the Git repository to diff (default: this one)")
    ap.add_argument("--changed", action="append", default=[], metavar="'S<TAB>PATH'", help="a changed file instead of a diff, for tests")
    ap.add_argument("--event", default="pull_request")
    ap.add_argument("--ref", default="")
    ap.add_argument("--labels", default="", help="the pull request's labels, comma separated")
    ap.add_argument("--dispatch-tier", default="", help="workflow_dispatch input: full or first")
    ap.add_argument("--full-shards", help="JSON of the suite's shards (kit_lint.py --ci-shards), used on the second tier")
    ap.add_argument("--full-windows", help="JSON of the Windows shards (kit_lint.py --ci-windows), used on the second tier")
    ap.add_argument("--github-output", action="store_true", help="print tier, reason, shards and wshards for $GITHUB_OUTPUT")
    ap.add_argument("--summary", action="store_true", help="print the markdown for the job summary")
    a = ap.parse_args(argv)
    if a.changed:
        changed = [tuple(c.split("\t", 1)) for c in a.changed]
    elif a.base and a.head:
        changed = changed_files(a.repo, a.base, a.head)
    elif a.event in ("push", "workflow_dispatch") and not (a.base or a.head):
        changed = []
    else:
        ap.error("give BASE and HEAD (or --changed)")
    tier, why = decide(a.event, [l for l in a.labels.split(",") if l], a.dispatch_tier, changed, ref=a.ref)
    sel = select(changed)
    m = matrices(tier, sel, json.loads(a.full_shards) if a.full_shards else None, json.loads(a.full_windows) if a.full_windows else None)
    if a.github_output:
        sys.stdout.write(github_output(tier, why, m))
    else:
        sys.stdout.write(report(tier, why, changed, sel, m, markdown=a.summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
