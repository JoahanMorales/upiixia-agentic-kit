#!/usr/bin/env python3
"""UAK-031: after the freeze, `claim` on a not-allowed task is refused, and the refusal never said that retrying is
useless: one agent retried the same frozen claim 7 times (DevDay hackathon). It now ends with "Do not retry" and
"Take other work: uak next", and keeps UAK_CODE=freeze and the `uak allow` line. Real git, a local bare remote."""
import argparse
import tempfile
from pathlib import Path

from test_hack import Runner, expect, resolve_binary


def freeze_claim_says_do_not_retry(r):
    f = r.fixture("fc-frozen", count=1)
    cfg = f.seed / ".uak/PROJECT.md"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "Freeze-Epoch: 1000000\n", encoding="utf-8")
    r.g(f.seed, "add", ".uak/PROJECT.md")
    r.g(f.seed, "commit", "-q", "-m", "Human schedules freeze")
    r.g(f.seed, "push", "-q", "origin", "main")
    out = f.claim(0, "HACK-001", now=1000010, allowed=None)
    text = out.stdout + out.stderr
    expect(out.returncode != 0 and "FREEZE" in text, "expected the FREEZE refusal, rc %d" % out.returncode)
    expect("UAK_CODE" in text or "freeze" in text.lower(), "the refusal still names the freeze")
    expect("uak allow" in text and "UAK_HUMAN=NAME" in text, "the allow line stays")
    expect("Do not retry: the answer only changes when a human runs it. Take other work: uak next." in text,
           "expected the do-not-retry sentence at the end of the refusal")
    return "refusal says do not retry"


TESTS = [freeze_claim_says_do_not_retry]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--case")
    args = parser.parse_args()
    ok_all = True
    with tempfile.TemporaryDirectory(prefix="uak-freeze-claim-") as tmp:
        runner = Runner(args.package.resolve(), Path(tmp), resolve_binary("bash"), resolve_binary("git"))
        for test in TESTS:
            if args.case and test.__name__ != args.case:
                continue
            try:
                print("PASS %s (%s)" % (test.__name__, test(runner)))
            except Exception as exc:  # noqa: BLE001
                ok_all = False
                print("FAIL %s (%s)" % (test.__name__, str(exc)[:2500]))
    print("FREEZE_CLAIM_RESULT " + ("PASS" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
