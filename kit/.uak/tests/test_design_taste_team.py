#!/usr/bin/env python3
"""UAK-076: a team's taste lives in the repo (.uak/design/taste.json, `uak design taste --team`) and one person has one
profile: a first round draws from team, else personal, else the prior; names that differ in case, accents or by an alias
map to one profile (the pick page too, whose name field defaults to UAK_HUMAN / git user.name and suggests existing
profiles); `--merge A B` folds two profiles of one person."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
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
        sys.path.insert(0, str(self.pkg / "bin" / "lib"))
        self.n = 0
        self.use_home("taste0")
        import design_taste
        self.dt = design_taste

    def use_home(self, name):
        self.home = self.tmp / name  # one taste folder per case: no cross-talk
        os.environ["UAK_TASTE_HOME"] = str(self.home)
        self.base = dict(os.environ, UAK_NO_OPEN="1", UAK_AGENT="tester", UAK_NO_COLOR="1", UAK_HUMAN="", UAK_TASTE_HOME=str(self.home),
                         GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"), GIT_CONFIG_NOSYSTEM="1")
        for k in ("SSH_CONNECTION", "SSH_TTY"):
            self.base.pop(k, None)

    def project(self, name=None, n=3, picked=("v1", "v2"), by="ana"):
        self.n += 1
        d = self.tmp / (name or "proj%d" % self.n)
        for i in range(1, n + 1):
            v = d / ".uak/design/rounds/R1" / ("v%d" % i)
            v.mkdir(parents=True)
            (v / "1280.png").write_bytes(PNG)
            g = dict(GENES, type=["grotesk", "serif display", "mono-led"][i % 3])
            (v / "genome.json").write_text(json.dumps({"id": "R1-v%d" % i, "variant": i, "genes": g, "recipe": "landing-story"}), encoding="utf-8")
        (d / ".uak/design/rounds/R1/picks.json").write_text(json.dumps({"picked": list(picked), "notes": {}, "by": by, "at": "2026-11-12T00:00:00Z"}), encoding="utf-8")
        return d

    def design(self, cwd, *args, env=None, ok=(0,)):
        out = subprocess.run([self.bash, str(self.pkg / "bin" / "design")] + list(args), cwd=str(cwd), env=dict(self.base, **(env or {})),
                             capture_output=True, text=True, timeout=120)
        expect(out.returncode in ok, "rc %d: %s" % (out.returncode, out.stdout + out.stderr))
        return out


def team_profile_in_repo(e):
    e.use_home("t1")
    d = e.project("team-a", picked=("v1", "v2"))
    out = e.design(d, "taste", "--team")
    f = d / ".uak/design/taste.json"
    expect(f.is_file() and "TASTE team updated" in out.stdout, "written in the repo: " + out.stdout)
    doc = json.loads(f.read_text(encoding="utf-8"))
    expect(doc["human"] == "team" and doc["rounds"]["team-a:R1"]["picks"] == 2 and "team-a" in doc["directions"], "same schema as a personal profile: %s" % list(doc))
    expect(not e.home.exists() or not list(e.home.glob("*.json")), "no personal profile was written")
    before = f.read_bytes()
    e.design(d, "taste", "--team")
    expect(f.read_bytes() == before, "folding twice changes nothing (the file is committed, so it must not churn)")
    text = f.read_text(encoding="utf-8")
    expect(not re.search(r"#[0-9a-fA-F]{3,8}\b", text), "traits only, as in a personal profile")
    # a teammate's machine: the same repo, another taste folder, sees the same team profile
    e.use_home("t1-other")
    expect(e.dt.confidence(e.dt.load_team(d)) == "low" and e.dt.pick_count(e.dt.load_team(d)) == 2, "read from the repo on any machine")
    return "taste.json in the repo, idempotent"


def order_team_personal_prior(e):
    e.use_home("t2")
    d = e.project("order-a")
    liked = lambda picks: {"rounds": {"x:R1": {"picks": picks, "shown": 6, "genes": {"type": {"grotesk": {"shown": 6, "first": 0, "picked": picks, "notes": []}}}}}, "directions": {}}
    big, small = liked(12), liked(3)
    prior = dict(liked(20), human="prior")
    # nothing at all
    doc, src = e.dt.effective(d, "ana")
    expect(src == "none" and e.dt.pick_count(doc) == 0, "empty: %s" % src)
    # only a prior
    doc, src = e.dt.effective(d, "ana", prior=prior)
    expect(src == "prior", "the prior is the last resort: %s" % src)
    # personal (ok) beats the prior
    e.dt.save("ana", dict(big, human="ana"))
    expect(e.dt.effective(d, "ana", prior=prior)[1] == "personal", "personal before prior")
    # team (ok) beats personal
    e.dt._save_to(e.dt.team_path(d), dict(big, human="team"))
    expect(e.dt.effective(d, "ana", prior=prior)[1] == "team", "team before personal")
    # a team profile that is still learning gives way to a personal one that is not
    e.dt._save_to(e.dt.team_path(d), dict(small, human="team"))
    doc, src = e.dt.effective(d, "ana", prior=prior)
    expect(src == "personal" and e.dt.pick_count(doc) == 12, "low-confidence team yields: %s" % src)
    # both low: the richer one, still low
    e.dt.save("ana", dict(liked(5), human="ana"))
    doc, src = e.dt.effective(d, "ana", prior=prior)
    expect(src == "prior" or (src == "personal" and e.dt.confidence(doc) == "low"), "both low: %s" % src)
    return "team, personal, prior"


def name_variants_map_to_one_profile(e):
    e.use_home("t3")
    a = e.project("var-a", by="ana")
    e.dt.update(a, "José Pérez")
    names = e.dt.profile_names()
    expect(names == ["José-Pérez"] or len(names) == 1, "one profile: %s" % names)
    first = e.dt.profile_path("José Pérez")
    for typed in ("jose perez", "JOSÉ PÉREZ", "Jose Pérez", "josé  pérez"):
        expect(e.dt.profile_path(typed) == first, "%r maps to the same file: %s vs %s" % (typed, e.dt.profile_path(typed), first))
    b = e.project("var-b", by="ana")
    e.dt.update(b, "JOSE PEREZ")
    expect(len(e.dt.profile_names()) == 1 and e.dt.pick_count(e.dt.load("jose perez")) == 4, "two saves, one profile with both projects")
    # an alias: "joahan" and "JoahanMorales" are not the same name, but one person
    e.dt.update(a, "joahan")
    (e.home / "aliases").write_text("# one person\nJoahanMorales = joahan\n", encoding="utf-8")
    expect(e.dt.profile_path("JoahanMorales") == e.dt.profile_path("joahan") == e.dt.profile_path("JOAHAN-MORALES"), "alias, and the alias in other case/accents")
    e.dt.update(b, "JoahanMorales")
    expect(sorted(p.stem for p in e.home.glob("*.json")) == ["José-Pérez", "joahan"], "still two profiles on disk: %s" % sorted(p.name for p in e.home.glob("*")))
    # the project's alias file, in the other spelling
    proj = e.project("var-c")
    (proj / ".uak/design/aliases").write_text("joahan: jmp, J. Morales\n", encoding="utf-8")
    old = os.getcwd()
    os.chdir(str(proj))
    try:
        expect(e.dt.profile_path("J. Morales") == e.dt.profile_path("joahan") == e.dt.profile_path("jmp"), "project aliases, name: a, b form")
    finally:
        os.chdir(old)
    # the pick page: the name typed on the page lands in the profile it maps to, and the page suggests the existing ones
    d = e.project("var-d", n=2, picked=("v1",), by="")
    out = subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--no-open"], cwd=str(d),
                         env=dict(e.base, UAK_HUMAN="joahan"), capture_output=True, text=True, timeout=90)
    m = re.search(r"http://127\.0\.0\.1:(\d+)/", out.stdout)
    expect(out.returncode == 0 and m, "start: " + out.stdout + out.stderr)
    port = int(m.group(1))
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/pick.html" % port, timeout=10) as r:
            page = r.read().decode("utf-8")
        expect('id="by"' in page and 'value="joahan"' in page and 'list="names"' in page, "the name defaults to UAK_HUMAN: " + page[page.index('id="by"') - 80:page.index('id="by"') + 200])
        expect('<option value="José-Pérez">' in page and '<option value="joahan">' in page, "and suggests the existing profiles")
        req = urllib.request.Request("http://127.0.0.1:%d/save" % port, data=json.dumps({"picked": ["v2"], "notes": {}, "by": "JOAHAN"}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read().decode("utf-8"))
        expect(res["ok"] and "taste" in res, "saved: %s" % res)
        expect(sorted(p.stem for p in e.home.glob("*.json") if ".metrics" not in p.name) == ["José-Pérez", "joahan"], "typed in capitals, still joahan: %s" % sorted(p.name for p in e.home.glob("*.json")))
    finally:
        subprocess.run([e.bash, str(e.pkg / "bin" / "design-gallery"), "--round", "R1", "--stop"], cwd=str(d), env=e.base, capture_output=True, text=True, timeout=60)
    return "case, accents, aliases, pick page"


def merge_two_profiles(e):
    e.use_home("t4")
    a, b = e.project("m-a", picked=("v1",)), e.project("m-b", picked=("v2", "v3"))
    e.dt.update(a, "joahan")
    e.dt.update(b, "JoahanMorales")
    expect(sorted(p.stem for p in e.home.glob("*.json")) == ["JoahanMorales", "joahan"], "the real case: two profiles")
    (e.home / "JoahanMorales.metrics.json").write_text(json.dumps({"m-b:R1:v1": {"round": "R1", "variant": "v1", "family": "light", "tokens": 5, "seconds": 9}}), encoding="utf-8")
    out = e.design(a, "taste", "--merge", "joahan", "JoahanMorales")
    expect("merged JoahanMorales into joahan: 3 picks in 2 rounds" in out.stdout, out.stdout)
    doc = e.dt.load("joahan")
    expect(set(doc["rounds"]) == {"m-a:R1", "m-b:R1"} and set(doc["directions"]) == {"m-a", "m-b"} and e.dt.pick_count(doc) == 3, "both rounds and both directions: %s" % list(doc["rounds"]))
    expect(sorted(p.name for p in e.home.glob("*.json") if ".metrics" not in p.name) == ["joahan.json"] and list(e.home.glob("JoahanMorales.json.merged-into-joahan.bak")), "the merged file is kept as a .bak: %s" % sorted(p.name for p in e.home.glob("*")))
    expect(e.dt.profile_path("JoahanMorales") == e.dt.profile_path("joahan"), "and the old name maps to the new one from now on")
    expect(json.loads((e.home / "joahan.metrics.json").read_text(encoding="utf-8")) and "m-b:R1:v1" in json.loads((e.home / "joahan.metrics.json").read_text(encoding="utf-8")), "the metrics store moves too")
    again = e.design(a, "taste", "--merge", "joahan", "JoahanMorales")
    expect("already the same profile" in again.stdout, "merging twice is harmless: " + again.stdout)
    bad = e.design(a, "taste", "--merge", "joahan", "ghost", ok=(1,))
    expect("no profile named ghost" in bad.stderr, bad.stderr)
    e.design(a, "taste", "--merge", "joahan", ok=(2,))
    return "merged, backed up, aliased"


TESTS = [team_profile_in_repo, order_team_personal_prior, name_variants_map_to_one_profile, merge_two_profiles]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    tests = [t for t in TESTS if not args.case or t.__name__ == args.case]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="uak-taste-team-") as tmp:
        e = Env(tmp, resolve_binary("bash"), args.package.resolve())
        for t in tests:
            try:
                print("PASS %s (%s)" % (t.__name__, t(e)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s (%s)" % (t.__name__, str(exc)[:1500]))
    print("DESIGN_TASTE_TEAM_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
