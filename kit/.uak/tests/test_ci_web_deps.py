#!/usr/bin/env python3
"""UAK-027: the team workflow ran `npm --prefix web run build` in the product smoke with no web/node_modules, so main
failed 9 times and every PR with "tsc: not found" (DevDay hackathon, 2026-11-08). A step before "Product smoke" now installs
the dependencies of every one of ., web, frontend, client that has a lockfile. The test reads the YAML text (no PyYAML) and
runs the step's script against fake npm/pnpm/yarn/corepack commands."""
import argparse
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

from test_hack import Failure, expect, resolve_binary

STEP = "Web dependencies"


def step_block(text, name):
    """The lines of the step `- name: NAME` up to the next step at the same indent."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)- name: " + re.escape(name) + r"\s*$", line)
        if m:
            indent = len(m.group(1))
            out = [line]
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt.strip().startswith("#") and re.match(r"^\s*- ", nxt) and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                out.append(nxt)
            return out
    return None


def run_script(block):
    """The body of the step's `run: |` block, dedented."""
    for i, line in enumerate(block):
        if re.match(r"^\s*run: \|\s*$", line):
            body = block[i + 1:]
            base = min(len(b) - len(b.lstrip()) for b in body if b.strip())
            return "\n".join(b[base:] for b in body)
    raise Failure("the step has no `run: |` block")


def workflow_installs_web_deps_before_smoke(package):
    text = (package / ".github/workflows/uak.yml").read_text(encoding="utf-8")
    block = step_block(text, STEP)
    expect(block is not None, "expected a step named '%s' in the workflow" % STEP)
    expect(text.index("- name: " + STEP) < text.index("- name: Product smoke"), "the step must come before Product smoke")
    joined = "\n".join(block)
    for token in ("npm", "ci --no-audit --no-fund", "pnpm install --frozen-lockfile", "corepack", "yarn install --frozen-lockfile",
                  "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "web", "frontend", "client"):
        expect(token in joined, "the step should mention %s" % token)
    return "step before smoke"


def fake_bin(tmp):
    b = tmp / "fakebin"
    b.mkdir()
    for tool in ("npm", "pnpm", "yarn", "corepack"):
        f = b / tool
        f.write_text('#!/bin/sh\necho "$(basename "$0") $* @ $(pwd | sed "s|.*/||")" >> "$CALLS"\n', encoding="utf-8")
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    return b


def run_in(package, tmp, name, files):
    block = step_block((package / ".github/workflows/uak.yml").read_text(encoding="utf-8"), STEP)
    expect(block is not None, "expected a step named '%s' in the workflow" % STEP)
    repo = tmp / name
    repo.mkdir()
    for rel in files:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("{}\n", encoding="utf-8")
    calls = tmp / (name + ".calls")
    calls.write_text("", encoding="utf-8")
    env = dict(os.environ, CALLS=str(calls), PATH=str(tmp / "fakebin") + os.pathsep + os.environ["PATH"])
    res = subprocess.run([resolve_binary("bash"), "-e", "-c", run_script(block)], cwd=repo, env=env, capture_output=True, text=True)
    expect(res.returncode == 0, "the step script failed: rc %d" % res.returncode)
    return calls.read_text(encoding="utf-8").splitlines()


def workflow_skips_install_without_a_lockfile(package):
    text = (package / ".github/workflows/uak.yml").read_text(encoding="utf-8")
    block = step_block(text, STEP)
    expect(block is not None, "expected a step named '%s' in the workflow" % STEP)
    expect(any(re.match(r"^\s*if: hashFiles\(", l) for l in block), "the step needs an `if: hashFiles(...)` guard")
    with tempfile.TemporaryDirectory(prefix="uak-ci-web-") as t:
        tmp = Path(t)
        fake_bin(tmp)
        expect(run_in(package, tmp, "none", ["package.json", "web/package.json"]) == [], "no lockfile: nothing is installed")
        npm = run_in(package, tmp, "npm", ["web/package-lock.json"])
        expect(len(npm) == 1 and npm[0].startswith("npm ") and "ci" in npm[0] and "--no-audit --no-fund" in npm[0], "npm ci for web/package-lock.json: %s" % npm)
        many = run_in(package, tmp, "many", ["package-lock.json", "frontend/pnpm-lock.yaml", "client/yarn.lock", "other/package-lock.json"])
        expect(len(many) == 4 or len([c for c in many if not c.startswith("corepack")]) == 3, "root npm, frontend pnpm, client yarn, not other/: %s" % many)
        expect(any(c.startswith("pnpm install --frozen-lockfile") for c in many) and any(c.startswith("yarn install --frozen-lockfile") for c in many)
               and not any("other" in c for c in many), "pnpm and yarn frozen installs, nothing for other/: %s" % many)
    return "skips and picks by lockfile"


TESTS = [workflow_installs_web_deps_before_smoke, workflow_skips_install_without_a_lockfile]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    for test in TESTS:
        if args.case and test.__name__ != args.case:
            continue
        try:
            print("PASS %s (%s)" % (test.__name__, test(args.package.resolve())))
        except Exception as exc:  # noqa: BLE001
            ok_all = False
            print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("CI_WEB_DEPS_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
