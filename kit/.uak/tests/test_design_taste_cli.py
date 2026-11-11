#!/usr/bin/env python3
"""UAK-064: `uak design taste` prints the human's profile (--update folds this project's rounds, --forget PROJECT drops one
project), and a save in `uak design pick` folds that round into the picker's profile right away; a profile that cannot be
written never fails the save, the answer says so. Real subprocesses and sockets on loopback; the profile lives in a
temp UAK_TASTE_HOME."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from test_hack import expect, resolve_binary

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000" "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
GENES = {"type": "grotesk", "scale": "bold", "color": "dark media", "layout": "split hero", "components": "glass",
         "imagery": "video loop", "motion": "entrance", "voice": "plain"}


class Env:
    def __init__(self, tmp, bash, package):
        self.tmp, self.bash = Path(tmp), bash
        self.pkg = Path(package) / ".uak"  # the candidate under test (smoke passes --package)
        self.home = self.tmp / "taste home"
        self.base = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester", UAK_NO_COLOR="1", UAK_TASTE_HOME=str(self.home), UAK_HUMAN="")
        for k in ("SSH_CONNECTION", "SSH_TTY"):
            self.base.pop(k, None)

    def project(self, name, n=3):
        d = self.tmp / name
        rnd = d / ".uak/design/rounds/R1"
        for i in range(1, n + 1):
            v = rnd / ("v%d" % i)
            v.mkdir(parents=True)
            (v / "1280.png").write_bytes(PNG)
            g = dict(GENES, type=["grotesk", "serif display", "mono-led"][i % 3])
            (v / "genome.json").write_text(json.dumps({"id": "R1-v%d" % i, "variant": i, "genes": g, "recipe": "landing-story"}), encoding="utf-8")
        return d

    def design(self, cwd, *args, env=None, ok=(0,)):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design")] + list(args), cwd=str(cwd),
                             env=dict(self.base, **(env or {})), capture_output=True, text=True, timeout=90)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out

    def start(self, d, env=None):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design-gallery"), "--round", "R1", "--no-open"], cwd=str(d),
                             env=dict(self.base, **(env or {})), capture_output=True, text=True, timeout=90)
        m = re.search(r"http://127\.0\.0\.1:(\d+)/", out.stdout)
        expect(out.returncode == 0 and m, "start: " + out.stdout + out.stderr)
        return int(m.group(1))

    def stop(self, d):
        subprocess.run([self.bash, str(self.pkg / "bin" / "design-gallery"), "--round", "R1", "--stop"], cwd=str(d), env=self.base,
                       capture_output=True, text=True, timeout=60)

    def save_picks(self, d, picked, by="ana"):
        (d / ".uak/design/rounds/R1/picks.json").write_text(json.dumps({"picked": picked, "notes": {}, "by": by, "at": "2026-11-11T00:00:00Z"}), encoding="utf-8")


def post(port, body):
    req = urllib.request.Request("http://127.0.0.1:%d/save" % port, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def taste_command_prints_profile(e):
    d = e.project("proj-a")
    e.save_picks(d, ["v2", "v1"])
    none = e.design(d, "taste", "--human", "ana")
    expect("confidence: low" in none.stdout and "0 picks" in none.stdout, "an empty profile says so: " + none.stdout)
    up = e.design(d, "taste", "--update", "--human", "ana")
    expect("2 picks" in up.stdout, "update folds the project: " + up.stdout)
    out = e.design(d, "taste", "--human", "ana")
    expect("type" in out.stdout and "serif display" in out.stdout and "confidence: low" in out.stdout and "past directions" in out.stdout
           and "proj-a" in out.stdout, "show: " + out.stdout)
    expect(len(out.stdout.splitlines()) < 40, "under 40 lines")
    # the name comes from UAK_HUMAN when --human is not given
    env = e.design(d, "taste", env={"UAK_HUMAN": "ana"})
    expect("TASTE ana: 2 picks" in env.stdout, "UAK_HUMAN: " + env.stdout)
    bad = e.design(d, "taste", "--bogus", ok=(2,))
    expect("Usage" in bad.stderr, "usage on a bad flag")
    return "update and show"


def pick_save_updates_profile(e):
    d = e.project("proj-b")
    port = e.start(d)
    try:
        st, res = post(port, {"picked": ["v2", "v3"], "notes": {"v2": "me gusto"}, "by": "lia"})
        expect(st == 200 and res["ok"] and "lia" in res.get("taste", "") and "2 picks" in res["taste"], "answer says the profile was updated: %s" % res)
        prof = json.loads((e.home / "lia.json").read_text(encoding="utf-8"))
        expect(prof["rounds"]["proj-b:R1"]["picks"] == 2 and "proj-b" in prof["directions"], "folded right away: %s" % list(prof["rounds"]))
        st, res = post(port, {"picked": ["v1"], "notes": {}, "by": "lia"})
        prof = json.loads((e.home / "lia.json").read_text(encoding="utf-8"))
        expect(prof["rounds"]["proj-b:R1"]["picks"] == 1, "a second save replaces the round")
        st, res = post(port, {"picked": ["v3"], "notes": {}})
        expect(res.get("taste"), "no name on the page: falls back to UAK_HUMAN/git/human: %s" % res)
    finally:
        e.stop(d)
    # a profile that cannot be written: the save still succeeds and the answer says so
    blocked = e.tmp / "blocked"
    blocked.write_text("a file, not a folder", encoding="utf-8")
    d2 = e.project("proj-c")
    port = e.start(d2, env={"UAK_TASTE_HOME": str(blocked)})
    try:
        st, res = post(port, {"picked": ["v1"], "notes": {}, "by": "lia"})
        expect(st == 200 and res["ok"] and "taste profile not updated" in res.get("taste_error", ""), "report, not fail: %s" % res)
        expect(json.loads((d2 / ".uak/design/rounds/R1/picks.json").read_text(encoding="utf-8"))["picked"] == ["v1"], "picks.json written")
    finally:
        e.stop(d2)
    return "save folds into the profile; failure reported"


def forget_drops_a_project(e):
    a, b = e.project("proj-d"), e.project("proj-e")
    for d, pk in ((a, ["v1"]), (b, ["v2", "v3"])):
        e.save_picks(d, pk, by="gus")
        e.design(d, "taste", "--update", "--human", "gus")
    out = e.design(a, "taste", "--forget", "proj-d", "--human", "gus")
    expect("forgot proj-d: 1 rounds and its direction" in out.stdout, "forget: " + out.stdout)
    prof = json.loads((e.home / "gus.json").read_text(encoding="utf-8"))
    expect(list(prof["rounds"]) == ["proj-e:R1"] and list(prof["directions"]) == ["proj-e"], "only proj-e remains: %s" % prof)
    shown = e.design(a, "taste", "--human", "gus").stdout
    expect("proj-d" not in shown and "proj-e" in shown, "show: " + shown)
    e.design(a, "taste", "--forget", "--human", "gus", ok=(2,))
    return "one project dropped"


TESTS = [taste_command_prints_profile, pick_save_updates_profile, forget_drops_a_project]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-design-taste-cli-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_TASTE_CLI_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
