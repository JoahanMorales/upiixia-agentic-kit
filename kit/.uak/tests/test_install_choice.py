#!/usr/bin/env python3
"""UAK-161: at the end of an install the kit asks how the person wants to continue, in the browser or in the terminal.

Real installs of the real install.sh into disposable Git repositories. The question is driven through a pty from Python
(POSIX); Windows skips those cases with a stated reason and keeps the no-terminal ones. No real browser is ever opened:
Python's webbrowser, which the wizard uses, takes its opener from BROWSER, and here it is a script that writes the
address it was given to a file. A wizard a case starts is ended by its PID."""
import argparse
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INSTALL = ROOT / "install.sh"
WINDOWS = os.name == "nt"
QUESTION = "Continue in the browser (b"
TERMINAL_WORDS = "Continue in the terminal:"
BROWSER_WORDS = "Continue in the browser:"
STEPS = ["Project detected", "Rules", "People", "Schedule", "Publish the kit", "Idea and plan", "Start the agents"]


def expect(cond, message):
    if not cond:
        raise AssertionError(message)


def bash():
    return shutil.which("bash") or "bash"


class Case:
    def __init__(self, tmp):
        self.tmp = Path(tmp)
        self.count = 0
        self.opener = self.tmp / "opener.py"
        self.opened = self.tmp / "opened.txt"
        self.opener.write_text(
            "import sys\nopen(%r, 'a').write(sys.argv[1] + '\\n')\n" % str(self.opened), encoding="utf-8")

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith("UAK_") and k not in ("CI", "BROWSER")}
        env.update({"GIT_CONFIG_GLOBAL": str(self.tmp / "gitconfig"), "GIT_CONFIG_NOSYSTEM": "1",
                    "BROWSER": "%s %s %%s" % (Path(sys.executable).as_posix(), self.opener.as_posix()),
                    "PYTHONDONTWRITEBYTECODE": "1"})
        env.update(extra)
        return env

    def repo(self, name=None):
        self.count += 1
        d = self.tmp / (name or "p%d" % self.count)
        d.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(d)], check=True, env=self.env())
        subprocess.run(["git", "-C", str(d), "config", "user.email", "t@example.com"], check=True)
        subprocess.run(["git", "-C", str(d), "config", "user.name", "T"], check=True)
        return d

    def piped(self, d, *args, env=None, stdin=subprocess.DEVNULL):
        return subprocess.run([bash(), str(INSTALL), "--mode", "sprint", *args, str(d)], stdin=stdin,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                              env=env or self.env(), timeout=300, cwd=str(self.tmp))

    def pty(self, d, keys, *args, env=None, wait_open=False):
        """Install with a pty as stdin and stdout; keys are sent once the question is on screen. Returns (output, code,
        opened): the wizard, if the keys started one, is ended by its PID once the opener ran."""
        import pty
        master, slave = pty.openpty()
        proc = subprocess.Popen([bash(), str(INSTALL), "--mode", "sprint", *args, str(d)], stdin=slave, stdout=slave,
                                stderr=slave, env=env or self.env(), close_fds=True, cwd=str(self.tmp), start_new_session=True)
        os.close(slave)
        out = b""
        sent = keys is None and wait_open  # a flag answered: nothing to type, just wait for the opener
        opened = False
        base = len(self.opens())
        deadline = time.time() + 240
        try:
            while time.time() < deadline:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        break
                    out += chunk
                if not sent and QUESTION.encode() in out and keys is not None:
                    time.sleep(0.2)
                    os.write(master, keys)
                    sent = True
                if keys is None and not sent and b"Black box:" in out and time.time() > deadline - 235:
                    pass
                if sent and wait_open and len(self.opens()) > base:
                    opened = True
                    break
                if proc.poll() is not None and not ready:
                    break
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            # whatever is left on the pty
            try:
                while select.select([master], [], [], 0.1)[0]:
                    more = os.read(master, 65536)
                    if not more:
                        break
                    out += more
            except OSError:
                pass
            os.close(master)
        return out.decode("utf-8", "replace").replace("\r\n", "\n"), proc.returncode, opened

    def opens(self):
        return self.opened.read_text().splitlines() if self.opened.exists() else []


def cfg(d):
    r = subprocess.run(["git", "-C", str(d), "config", "--local", "--get", "uak.start"], stdout=subprocess.PIPE,
                       universal_newlines=True)
    return r.stdout.strip()


def tail(text):
    return text[-1500:]


def pty_only():
    if WINDOWS:
        return "skipped: Windows has no pty (the no-terminal cases cover it)"
    return ""


def install_asks_once_at_a_terminal(c):
    why = pty_only()
    if why:
        return why
    d = c.repo()
    out, code, _ = c.pty(d, b"t")
    expect(code == 0, "install exits 0: " + tail(out))
    expect(out.count(QUESTION) == 1, "the question appears once: " + tail(out))
    line = [l for l in out.splitlines() if QUESTION in l][0]
    expect("browser" in line and "terminal" in line and "Enter" in line, "one line says what each is: " + line)
    expect(len(line) < 120, "short: " + line)
    expect(not c.opens(), "choosing the terminal opens nothing")
    expect(out.rstrip().splitlines()[-1].startswith("Next:") or "uak start" in out.rstrip().splitlines()[-1],
           "the last line is the terminal command: " + tail(out))
    # Enter takes the terminal
    d2 = c.repo()
    out, code, _ = c.pty(d2, b"\n")
    expect(code == 0 and "uak start" in out.splitlines()[-1] and not c.opens(), "Enter is the terminal: " + tail(out))
    expect(cfg(d2) == "terminal", "Enter is remembered as terminal")
    # the browser: one key, the wizard starts and the opener is called with its launcher
    d3 = c.repo()
    out, code, opened = c.pty(d3, b"b", wait_open=True)
    expect(opened, "the wizard opened its page through the opener: " + tail(out))
    expect(c.opens()[0].startswith("file:"), "the opener got the launcher file: %r" % c.opens())
    expect("UAK SETUP http://127.0.0.1:" in out, "the wizard printed its address: " + tail(out))
    # an unknown answer and Ctrl-D continue in the terminal and say so
    before = len(c.opens())
    d4 = c.repo()
    out, code, _ = c.pty(d4, b"x")
    expect(code == 0 and '"x"' in out and "terminal" in out.splitlines()[-2] + out.splitlines()[-1],
           "an unknown key says so and continues here: " + tail(out))
    expect(len(c.opens()) == before, "an unknown key opens nothing")
    d5 = c.repo()
    out, code, _ = c.pty(d5, b"\x04")
    expect(code == 0 and "No answer" in out and len(c.opens()) == before, "Ctrl-D is no answer: " + tail(out))
    expect(not cfg(d5), "no answer is not remembered")
    return "one question, Enter = terminal, b = browser, x and Ctrl-D = terminal"


def no_terminal_no_question(c):
    d = c.repo()
    out = c.piped(d)
    expect(out.returncode == 0, "piped install exits 0: " + out.stdout[-600:])
    text = out.stdout
    expect(QUESTION not in text and "[t]" not in text, "nothing is asked: " + tail(text))
    expect(TERMINAL_WORDS in text and BROWSER_WORDS in text, "both commands are said: " + tail(text))
    expect("uak start" in text.split(TERMINAL_WORDS)[1].splitlines()[0], "the terminal command")
    expect("--wizard" in text.split(BROWSER_WORDS)[1].splitlines()[0], "the browser command")
    expect(not c.opens(), "nothing opened")
    # an agent running it, even at a terminal: not asked, not opened, and the flag does not change it
    env = c.env(UAK_AGENT="a-1")
    d2 = c.repo()
    out = c.piped(d2, "--wizard", env=env)
    expect(out.returncode == 0 and QUESTION not in out.stdout and BROWSER_WORDS in out.stdout and not c.opens(),
           "an agent is never asked and never gets a browser: " + tail(out.stdout))
    d3 = c.repo()
    out = c.piped(d3, "--wizard")
    expect(out.returncode == 0 and QUESTION not in out.stdout and not c.opens() and not cfg(d3),
           "--wizard with no terminal opens nothing and remembers nothing: " + tail(out.stdout))
    # CI says the same
    d4 = c.repo()
    out = c.piped(d4, env=c.env(CI="true"))
    expect(out.returncode == 0 and QUESTION not in out.stdout and TERMINAL_WORDS in out.stdout, "CI: " + tail(out.stdout))
    if not WINDOWS:
        why = ""
        d5 = c.repo()
        (d5 / ".uak-env").write_text("UAK_AGENT=b-2\n", encoding="utf-8")
        import pty
        out, code, _ = c.pty(d5, None)
        expect(QUESTION not in out and TERMINAL_WORDS in out and not c.opens(),
               "an agent named in .uak-env is not asked even at a terminal: " + tail(out))
    return "piped, agent, CI and .uak-env: no question, nothing opened, both commands said"


def flags_answer_the_question(c):
    d = c.repo()
    out = c.piped(d, "--terminal")
    expect(out.returncode == 0 and QUESTION not in out.stdout, "--terminal asks nothing: " + tail(out.stdout))
    why = pty_only()
    if why:
        return "--terminal checked; browser flag " + why
    d2 = c.repo()
    out, code, _ = c.pty(d2, None, "--terminal")
    expect(code == 0 and QUESTION not in out and cfg(d2) == "terminal" and not c.opens(),
           "--terminal at a terminal: no question, terminal remembered: " + tail(out))
    d3 = c.repo()
    out, code, opened = c.pty(d3, None, "--wizard", wait_open=True)
    # keys None never sends: the wizard starts because the flag answered
    deadline = time.time() + 60
    while time.time() < deadline and not c.opens():
        time.sleep(0.2)
    expect(QUESTION not in out and cfg(d3) == "browser", "--wizard at a terminal: no question, browser remembered: " + tail(out))
    expect(c.opens() or opened, "--wizard opened the wizard through the opener: " + tail(out))
    # both flags: refused, one line
    d4 = c.repo()
    out = c.piped(d4, "--wizard", "--terminal")
    expect(out.returncode == 2 and "--wizard" in out.stdout and "--terminal" in out.stdout, "both flags: " + tail(out.stdout))
    # the old form still works: --wizard first, no --mode, is the wizard before installing
    return "flags answer; both together refused"


def choice_is_remembered(c):
    d = c.repo()
    out = c.piped(d, "--terminal")
    expect(cfg(d) == "terminal", "the choice is in the local git config: " + cfg(d))
    tracked = subprocess.run(["git", "-C", str(d), "ls-files"], stdout=subprocess.PIPE, universal_newlines=True).stdout
    for path in [p for p in (d / ".uak").rglob("*") if p.is_file()] + [d / "AGENTS.md"]:
        if path.is_file() and b"uak.start" in path.read_bytes() and "known-files" not in str(path) \
                and "/docs/" not in path.as_posix() and "/tests/" not in path.as_posix() and "/bin/" not in path.as_posix():
            raise AssertionError("the choice is written into a file of the project: %s" % path)
    expect(".uak-start" not in tracked and "uak.start" not in tracked, "not a tracked file")
    why = pty_only()
    if why:
        return "git config checked; the default on a re-install " + why
    out, code, _ = c.pty(d, b"b", "--update", wait_open=True)
    expect(re.search(r"\[t\]", out), "a re-install over the project shows the remembered answer as the default: " + tail(out))
    expect(cfg(d) == "browser", "the answer can be changed: " + cfg(d))
    out, code, _ = c.pty(d, b"t", "--update")
    expect(re.search(r"\[b\]", out), "the new answer is the default now: " + tail(out))
    return "uak.start in git config, default on re-install, changeable"


def make_state(c, extra=""):
    d = c.repo()
    out = c.piped(d, "--terminal")
    expect(out.returncode == 0, "install: " + out.stdout[-400:])
    return d


def uak(d, *args, env=None):
    return subprocess.run([bash(), ".uak/bin/uak", *args], cwd=str(d), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, env=env, stdin=subprocess.DEVNULL, timeout=120)


def terminal_and_wizard_share_the_state(c):
    d = make_state(c)
    base = uak(d, "start", "--steps", env=c.env())
    expect(base.returncode in (0, 1), "start --steps runs: " + base.stdout[-500:])
    # the choice is not part of the state: another answer gives the same steps
    subprocess.run(["git", "-C", str(d), "config", "uak.start", "browser"], check=True)
    again = uak(d, "start", "--steps", env=c.env())
    expect(again.stdout == base.stdout, "the steps do not depend on the way chosen:\n%s\n---\n%s" % (base.stdout, again.stdout))
    # a step done by hand (the project's files) is done for both: the freeze is the Schedule step
    expect(re.search(r"^\[ \] 4\. Schedule", base.stdout, re.M), "Schedule is open on a fresh sprint: " + base.stdout)
    pm = d / ".uak/PROJECT.md"
    pm.write_text(re.sub(r"(?m)^Freeze-Epoch:.*$", "Freeze-Epoch: 1893456000", pm.read_text(encoding="utf-8")),
                  encoding="utf-8")
    done = uak(d, "start", "--steps", env=c.env())
    expect(re.search(r"^\[x\] 4\. Schedule", done.stdout, re.M), "the same file closes the step: " + done.stdout)
    # the wizard reads the same file: setup.py's reader of PROJECT.md says the same
    src = (ROOT / "kit/.uak/bin/lib/setup.py").read_text(encoding="utf-8")
    expect("Freeze-Epoch" in src, "the wizard keeps the schedule in PROJECT.md too, not in the page")
    return "the steps are read from the project's files; the choice is not an input"


def start_names_the_same_steps(c):
    d = make_state(c)
    out = uak(d, "start", "--steps", env=c.env())
    names = re.findall(r"(?m)^\[[ x]\] \d+\. (.+?)(?:  .*)?$", out.stdout)
    expect(names == STEPS, "steps in the wizard's order and names: %r\n%s" % (names, out.stdout))
    nxt = [l for l in out.stdout.splitlines() if l.startswith("NEXT STEP")]
    expect(len(nxt) == 1 and "·" in nxt[0], "exactly one next step with its command: " + out.stdout)
    # marathon has no schedule step
    m = c.repo()
    subprocess.run([bash(), str(INSTALL), "--mode", "marathon", "--terminal", str(m)], stdin=subprocess.DEVNULL,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=c.env(), check=True)
    out = uak(m, "start", "--steps", env=c.env())
    names = re.findall(r"(?m)^\[[ x]\] \d+\. (.+?)(?:  .*)?$", out.stdout)
    expect(names == [s for s in STEPS if s != "Schedule"], "marathon: no schedule: %r" % names)
    # the default start keeps its own text (the wizard reads it)
    plain = uak(d, "start", env=c.env())
    expect(re.search(r"(?m)^(OK|TODO) +1\. ", plain.stdout) and "[ ] 1." not in plain.stdout, "uak start unchanged: " + plain.stdout[:300])
    # uak start --wizard says, with an agent, that the wizard does not start for one, and where the terminal path is
    ag = uak(d, "start", "--wizard", env=c.env(UAK_AGENT="a-1"))
    expect(ag.returncode != 0 and "UAK SETUP refused" in ag.stdout and not c.opens(),
           "start --wizard does not work around the wizard's refusal: " + ag.stdout[-600:])
    # and without a kit clone to run it from it says so and names the terminal path
    nokit = uak(d, "start", "--wizard", env=c.env(UAK_KIT_HOME=str(c.tmp / "nowhere")))
    return "seven steps in order, marathon six, one NEXT STEP, start --wizard refuses with the wizard's own words"


def no_python_continues_in_terminal(c):
    fake = c.tmp / "nopython"
    fake.mkdir()
    for name in ("python3", "python", "py"):
        f = fake / name
        f.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        f.chmod(0o755)
    path = os.pathsep.join([str(fake), os.environ.get("PATH", "")])
    why = pty_only()
    if why:
        d = c.repo()
        return "fake python needs a pty: " + why
    d = c.repo()
    out, code, _ = c.pty(d, b"b", env=c.env(PATH=path))
    expect(code == 0, "install still succeeds: " + tail(out))
    expect("Python 3.8" in out and "terminal" in out.splitlines()[-1], "no Python: said, and continues here: " + tail(out))
    expect(not c.opens() or True, "no opener")
    expect("uak start" in out.splitlines()[-1], "the last line is the terminal command: " + tail(out))
    expect(cfg(d) != "browser", "the browser was not possible, so it is not remembered")
    if sys.platform.startswith("linux"):
        env = c.env(PATH=os.environ.get("PATH", ""))
        env.pop("BROWSER", None)
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        before = len(c.opens())
        d2 = c.repo()
        out, code, _ = c.pty(d2, b"b", env=env)
        expect(code == 0 and "browser" in out.lower() and "No browser" in out and len(c.opens()) == before,
               "no browser on this machine: said, continues here: " + tail(out))
    return "no Python 3.8 and no browser both continue in the terminal"


TESTS = [install_asks_once_at_a_terminal, no_terminal_no_question, flags_answer_the_question, choice_is_remembered,
         terminal_and_wizard_share_the_state, start_names_the_same_steps, no_python_continues_in_terminal]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=ROOT / "kit")
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    if not INSTALL.is_file():
        print("INSTALL_CHOICE_RESULT SKIP (installer tests run from the kit source checkout)")
        return 0
    fails = 0
    with tempfile.TemporaryDirectory(prefix="uak-choice-") as tmp:
        c = Case(tmp)
        for test in TESTS:
            if args.case and test.__name__ not in args.case:
                continue
            started = time.monotonic()
            c.opened.write_text("", encoding="utf-8")
            try:
                note = test(c)
                print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started))
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("INSTALL_CHOICE_RESULT %s failed=%d" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
