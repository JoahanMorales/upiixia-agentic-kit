#!/usr/bin/env python3
"""ci_select: which tests a pull request runs on macOS and Windows, and the small decisions around it (UAK-168).

    python3 scripts/ci_select.py BASE HEAD            # the files per system and the predicted seconds, for a person
    python3 scripts/ci_select.py BASE HEAD --github-output --event pull_request --labels ci-full >> "$GITHUB_OUTPUT"
    python3 scripts/ci_select.py run --kind smoke --retry --job NAME --out result.json test_a test_b
    python3 scripts/ci_select.py gate                 # reads NEEDS (toJSON(needs)); fails unless every job that ran passed
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "kit"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit_lint as lint  # noqa: E402

FIRST_TIER_BOUND_S = 600      # a macOS or Windows job of the first tier is predicted under this; over it, two jobs
MAX_JOBS_PER_SYSTEM = 2
MACOS_SETUP_S = 60            # checkout, Git identity and the runner start, before the first file
FULL_LABEL = "ci-full"
# A change to these runs the whole matrix on a pull request: the workflow decides what runs, and this is the selector.
FORCE_PREFIXES = (".github/workflows/",)
FORCE_FILES = ("scripts/ci_select.py", "kit/.uak/bin/lib/tests.sh")
RED_TITLE = "main is red at "
NOT_COUNTED = ("ci", "red-main")   # jobs that are not the matrix: the gate and the issue job


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
_BASH = r'''
set -u
. "$KIT/.uak/bin/lib/tests.sh"
while IFS= read -r f; do
  [ -n "$f" ] || continue
  printf '%s\n' "$f" > "$TMP/one"
  printf '@@\t%s\n' "$f"
  tf_affected_select "$KIT" "$TMP/one" "$TMP/tests" 2>/dev/null || true
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
        mandatory = [t for t, why in sel[system].items() if any(x.startswith(("changed test file", "new test file", "changed tests/", "portability")) for x in why)]
        optional = sorted((t for t in sel[system] if t not in mandatory), key=lambda t: (seconds(t), t))
        keep = list(mandatory)
        sel["budget"][system] = []
        for t in optional:
            shards, _ = _split_jobs(keep + [t], seconds, setup)
            if max(x["seconds"] for x in shards) <= FIRST_TIER_BOUND_S:
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
    k = 1 if total <= FIRST_TIER_BOUND_S else MAX_JOBS_PER_SYSTEM
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
    lines.append("%sruns on main: %d of %d test files on macOS and Windows are not in this run" % (h, len([t for t in suite if t not in sel["macos"]]), len(suite)))
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
    return "tier=%s\nreason=%s\nshards=%s\nwshards=%s\n" % (tier, why.replace("\n", " "), json.dumps(m["shards"], separators=(",", ":")),
                                                            json.dumps(m["wshards"], separators=(",", ":")))


# ---- running files, with one retry on macOS and Windows -------------------------------------------------------------
def run_files(files, runner, retry, log=print):
    """Run each file; with retry a failed file runs once more. {ran, failed, flaky, counts}: failed = failed every time,
    flaky = failed then passed (the job passes, and says so)."""
    res = {"ran": list(files), "failed": [], "flaky": [], "counts": {}}
    for f in files:
        log("::group::" + f)
        ok = runner(f)
        runs, failures = 1, 0 if ok else 1
        if not ok and retry:
            log("::endgroup::")
            log("::group::%s (second run)" % f)
            ok = runner(f)
            runs, failures = 2, failures + (0 if ok else 1)
            if ok:
                res["flaky"].append(f)
        if not ok:
            res["failed"].append(f)
        res["counts"][f] = {"runs": runs, "failures": failures}
        log("::endgroup::")
    return res


def flaky_report(job, res):
    """The summary, the annotations and the conclusion of a job: passed, flaky (never shown as a plain pass) or failed."""
    ann, md = [], []
    for f in res["flaky"]:
        ann.append("::warning title=flaky test::flaky: %s passed on the second run (%s)" % (f, job))
        md.append("- flaky: %s passed on the second run" % f)
    for f in res["failed"]:
        n = res["counts"].get(f, {}).get("runs", 1)
        ann.append("::error title=test failed::%s failed%s (%s)" % (f, " both times" if n > 1 else "", job))
    conclusion = "failed" if res["failed"] else ("flaky" if res["flaky"] else "passed")
    head = {"passed": "### %s: passed" % job, "flaky": "### %s: passed, with flaky files" % job, "failed": "### %s: failed" % job}[conclusion]
    summary = [head] + md
    if res["failed"]:
        summary.append("Failed test files (%s):%s" % (job, "".join(" " + f for f in res["failed"])))
        both = [f for f in res["failed"] if res["counts"].get(f, {}).get("runs", 1) > 1]
        if both:
            summary.append("Failed both times: " + " ".join(both))
    return {"job": job, "conclusion": conclusion, "annotations": ann, "summary": "\n".join(summary) + "\n",
            "failed": res["failed"], "flaky": res["flaky"], "counts": res["counts"]}


def _real_runner(kind):
    def run(name):
        sys.stdout.flush()
        if kind == "smoke":
            env = dict(os.environ, UAK_SMOKE_TESTS=name)
            # stdin held open, as in a terminal: a command that reads it (BSD awk -W version did) hangs here, not on a laptop.
            p = subprocess.Popen(["bash", ".uak/bin/smoke", "--package-only"], cwd=str(KIT), env=env, stdin=subprocess.PIPE)
            try:
                return p.wait() == 0
            finally:
                p.stdin.close()
        if name == "mcp_tools":
            return subprocess.call([sys.executable, "tests/test_mcp_tools.py"], cwd=str(ROOT), stdin=subprocess.DEVNULL) == 0
        return subprocess.call([sys.executable, ".uak/tests/%s.py" % name, "--package", str(KIT)], cwd=str(KIT), stdin=subprocess.DEVNULL) == 0
    return run


def cmd_run(argv):
    ap = argparse.ArgumentParser(prog="ci_select.py run", description="run test files one by one; a failed file runs once more with --retry")
    ap.add_argument("--kind", choices=("smoke", "windows"), required=True, help="smoke: bash .uak/bin/smoke --package-only per file; windows: python per file")
    ap.add_argument("--job", default="job", help="the job's name, as GitHub shows it")
    ap.add_argument("--retry", action="store_true", help="run a failed file once more (macOS and Windows; Linux never retries)")
    ap.add_argument("--out", help="write the result JSON here (the artifact of the run)")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    if not a.files:
        print("FAILED: this shard has no test files (empty list)")
        return 1
    res = run_files(a.files, _real_runner(a.kind), a.retry)
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
        Path(a.out).write_text(json.dumps({k: rep[k] for k in ("job", "conclusion", "failed", "flaky", "counts")}), encoding="utf-8")
    return 1 if rep["conclusion"] == "failed" else 0


# ---- the gate and the issue ------------------------------------------------------------------------------------------
def gate(needs):
    """Problems of the jobs before the gate: every job that ran must have passed (skipped is a job that did not run)."""
    return ["%s: %s" % (name, v.get("result")) for name, v in sorted(needs.items()) if v.get("result") not in ("success", "skipped")]


def cmd_gate(argv):
    raw = os.environ.get("NEEDS") or "{}"
    problems = gate(json.loads(raw))
    text = "### ci: %s\n" % ("failed" if problems else "every job that ran passed") + "".join("- %s\n" % p for p in problems)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 1 if problems else 0


def plan_issue(sha, failed_jobs, failed_both, pr, open_issues, run_url):
    """What to do about the issue of a red main, as data: create one, add to the open one, close it, or nothing."""
    short = sha[:7]
    existing = next((i for i in open_issues if i.get("title", "").startswith(RED_TITLE)), None)
    if not failed_jobs:
        if existing:
            return {"action": "close", "number": existing["number"], "body": "main is green again at %s (%s). Closing." % (short, run_url)}
        return {"action": "none"}
    lines = ["The whole matrix failed at %s (%s)." % (short, run_url), "", "Failed jobs:"] + ["- %s" % j for j in failed_jobs]
    lines += ["", "Files that failed both times (each file runs a second time in its job on macOS and Windows):"]
    any_both = False
    for job in failed_jobs:
        files = failed_both.get(job) or []
        if files:
            any_both = True
            lines.append("- %s: %s" % (job, " ".join(files)))
    if not any_both:
        lines.append("- none recorded (a Linux job never retries; a job can also fail before its tests)")
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
    ap.add_argument("--apply", action="store_true", help="open, comment or close the issue; without it the plan is only printed")
    a = ap.parse_args(argv)
    rows = _gh("api", "repos/%s/actions/runs/%s/jobs" % (a.repo, a.run_id), "--paginate", "--jq", ".jobs[] | {name, conclusion}")
    jobs = [json.loads(l) for l in rows.splitlines() if l.strip()]
    failed = [j["name"] for j in jobs if j["conclusion"] in ("failure", "timed_out") and j["name"] not in NOT_COUNTED]
    both = {}
    for p in sorted(Path(a.results).rglob("*.json")) if a.results else []:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        files = [f for f in r.get("failed", []) if r.get("counts", {}).get(f, {}).get("runs", 1) > 1]
        if files:
            both[r.get("job", p.stem)] = files
    pr = None
    if failed:
        pulls = _gh("api", "repos/%s/commits/%s/pulls" % (a.repo, a.sha), "--jq", ".[0] | {number, title}").strip()
        pr = json.loads(pulls) if pulls and pulls != "null" else None
        if pr and not pr.get("number"):
            pr = None
    listing = _gh("issue", "list", "--repo", a.repo, "--state", "open", "--search", RED_TITLE + " in:title", "--json", "number,title")
    plan = plan_issue(a.sha, failed, both, pr, json.loads(listing or "[]"), "https://github.com/%s/actions/runs/%s" % (a.repo, a.run_id))
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
